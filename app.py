"""Local audio downloader. Run with: .venv/bin/python app.py"""

import base64
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.resolve()
DOWNLOADS = ROOT / ".downloads"
JOBS = {}
LOCK = threading.Lock()
MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("MAX_CONCURRENT_JOBS", "2")))
POOL = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)


def validate_url(value, playlist=False):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Please enter a valid link.")
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    allowed = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "soundcloud.com",
        "www.soundcloud.com",
        "on.soundcloud.com",
    }
    if (
        parsed.scheme != "https"
        or host not in allowed
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Use an HTTPS link from YouTube or SoundCloud.")
    if playlist and host not in {
        "soundcloud.com",
        "www.soundcloud.com",
        "on.soundcloud.com",
    }:
        raise ValueError("Combined playlists are supported for SoundCloud links.")
    return value.strip()


def update(job_id, **values):
    with LOCK:
        JOBS[job_id].update(values)


def run_command(args, folder, timeout=3600):
    result = subprocess.run(
        args, cwd=folder, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode:
        detail = result.stderr.strip()[-1500:]
        raise RuntimeError(detail or "The audio could not be processed.")
    return result.stdout


def convert(job_id, url, playlist):
    folder = DOWNLOADS / job_id
    folder.mkdir(parents=True)
    try:
        update(
            job_id,
            status="working",
            message=(
                "Reading playlist and downloading audio…"
                if playlist
                else "Downloading and converting audio…"
            ),
        )
        update(job_id, stage="downloading", progress=None)
        run_command(
            [
                sys.executable,
                str(ROOT / "worker.py"),
                url,
                "playlist" if playlist else "track",
            ],
            folder,
        )
        files = sorted(folder.glob("*.mp3"))
        if not files:
            raise RuntimeError("No downloadable audio was found at this link.")
        if playlist and len(files) > 100:
            raise RuntimeError(
                "This playlist exceeds the 100-track limit. Try a shorter playlist."
            )
        title = "SoundCloud playlist" if playlist else "Audio track"
        info_files = sorted(folder.glob("*.info.json"))
        if info_files:
            info = json.loads(info_files[0].read_text())
            title = (
                info.get("playlist_title") if playlist else info.get("title")
            ) or title
        if playlist:
            update(
                job_id,
                stage="merging",
                progress=None,
                message=f"Joining {len(files)} tracks in playlist order…",
            )
            # Generated filenames contain only restricted characters, making the concat list safe.
            (folder / "tracks.txt").write_text(
                "".join(f"file '{p.name}'\n" for p in files)
            )
            run_command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "1",
                    "-i",
                    "tracks.txt",
                    "-vn",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    "output.mp3",
                ],
                folder,
            )
        else:
            files[0].rename(folder / "output.mp3")
        name = re.sub(r"[^\w .-]", "", title).strip()[:120] or "audio"
        update(
            job_id,
            status="done",
            progress=100,
            stage="done",
            message=(
                f"{len(files)} tracks combined. Ready to download."
                if playlist
                else "Your MP3 is ready."
            ),
            title=title,
            filename=name + ".mp3",
            tracks=len(files),
        )
        for path in folder.iterdir():
            if path.name != "output.mp3":
                path.unlink()
    except subprocess.TimeoutExpired:
        update(
            job_id,
            status="error",
            message="Conversion timed out. Try a shorter track or playlist.",
        )
        shutil.rmtree(folder, ignore_errors=True)
    except Exception as exc:
        update(job_id, status="error", message=str(exc))
        shutil.rmtree(folder, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        password = os.environ.get("APP_PASSWORD")
        if not password:
            return True
        expected = base64.b64encode(f"sidea:{password}".encode()).decode()
        supplied = self.headers.get("Authorization", "")
        if hmac.compare_digest(supplied.encode(), f"Basic {expected}".encode()):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Side A", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def json(self, status, data):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != "/api/jobs":
            return self.json(404, {"error": "Not found"})
        # Do not allow other websites to submit work to this local service.
        origin = self.headers.get("Origin")
        expected_origin = os.environ.get("PUBLIC_ORIGIN")
        if origin and (
            origin != expected_origin if expected_origin else
            origin not in {f'http://{self.headers.get("Host")}', f'https://{self.headers.get("Host")}'}
        ):
            return self.json(403, {"error": "Origin not allowed"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 8192:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            playlist = data.get("mode") == "playlist"
            url = validate_url(data.get("url"), playlist)
            if not shutil.which("ffmpeg"):
                raise ValueError("FFmpeg is missing. Install it and restart the app.")
            with LOCK:
                if (
                    sum(j["status"] in ("queued", "working") for j in JOBS.values())
                    >= MAX_CONCURRENT_JOBS
                ):
                    return self.json(
                        429,
                        {"error": "The conversion limit has been reached. Please wait."},
                    )
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {
                    "status": "queued",
                    "message": "Starting conversion…",
                    "created": time.time(),
                }
            POOL.submit(convert, job_id, url, playlist)
            self.json(202, {"id": job_id})
        except (ValueError, TypeError, AttributeError) as exc:
            self.json(400, {"error": str(exc)})

    def do_GET(self):
        if self.path == "/health":
            ready = bool(shutil.which("ffmpeg")) and DOWNLOADS.is_dir()
            return self.json(200 if ready else 503, {"status": "ok" if ready else "unavailable"})
        if not self.authorized():
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})(/download)?", self.path)
        if match:
            with LOCK:
                job = dict(JOBS.get(match[1], {}))
            if not job:
                return self.json(404, {"error": "Download expired or not found."})
            if not match[2]:
                if job.get("status") == "working" and job.get("stage") == "downloading":
                    try:
                        job.update(
                            json.loads(
                                (DOWNLOADS / match[1] / "progress.json").read_text()
                            )
                        )
                    except (OSError, ValueError):
                        pass
                return self.json(200, job)
            file = DOWNLOADS / match[1] / "output.mp3"
            if job["status"] != "done" or not file.exists():
                return self.json(409, {"error": "File is not ready."})
            from urllib.parse import quote

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''" + quote(job["filename"]),
            )
            self.send_header("Content-Length", str(file.stat().st_size))
            self.end_headers()
            with file.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return
        paths = {
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if self.path not in paths:
            return self.json(404, {"error": "Not found"})
        filename, content_type = paths[self.path]
        raw = (ROOT / "static" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def cleanup():
    while True:
        time.sleep(300)
        with LOCK:
            expired = [
                key
                for key, job in JOBS.items()
                if job["status"] in ("done", "error")
                and time.time() - job["created"] > 86400
            ]
            for key in expired:
                JOBS.pop(key, None)
                shutil.rmtree(DOWNLOADS / key, ignore_errors=True)


if __name__ == "__main__":
    if os.environ.get("RENDER") == "true" and not os.environ.get("APP_PASSWORD"):
        raise SystemExit("Set APP_PASSWORD before deploying on Render.")
    DOWNLOADS.mkdir(exist_ok=True)
    # Old jobs cannot be resumed after a server restart.
    for old in DOWNLOADS.iterdir():
        if old.is_dir():
            shutil.rmtree(old)
    threading.Thread(target=cleanup, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Open http://localhost:{port}", flush=True)
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), port), Handler).serve_forever()
