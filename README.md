# Aganon Audio

A minimal audio tool. The app is for converting YouTube or SoundCloud tracks to 192 kbps MP3. SoundCloud playlists can be combined into one MP3 in playlist order.

## Run

Requires Python 3.10+ and FFmpeg. On macOS, install FFmpeg with `brew install ffmpeg`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open http://localhost:8000. Paste a link, select single track or SoundCloud playlist, convert, then click **Download MP3**. Set `PORT` to use another port.

## Behavior and limits

- Single track mode ignores playlists attached to YouTube links.
- Playlist mode processes SoundCloud playlists only, joins tracks in their original order, and fails if a required track cannot be downloaded. It does not silently skip unavailable tracks.
- Playlists are limited to 100 tracks, each source download to 500 MB, and each conversion stage to one hour. Two conversions can run at once.
- Files are stored in `.downloads/` and removed after 24 hours (checked every five minutes), or when the app restarts. Leave the server running until your download finishes.
- Private, restricted, DRM-protected, or unavailable media may fail. YouTube may require a JavaScript runtime supported by yt-dlp or authentication for some videos. This app does not provide a login/cookie interface. Update yt-dlp if provider changes break downloads: `.venv/bin/pip install -U yt-dlp`.
- The server binds to loopback only. It is intended for personal local use, not public deployment. Conversion requires a native server with FFmpeg and yt-dlp; static or Cloudflare Workers hosting cannot run this backend.
- Only download audio you own or have permission to download.

## Verify

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests validate accepted URLs, reject unsupported URLs, and check playlist ordering and real FFmpeg concatenation using generated audio. They do not download third-party media.
# Convert-To-Mp3

## Docker and Render

The Docker image includes Python 3.13, FFmpeg, Node.js 22 (for YouTube's JavaScript challenges), and yt-dlp's default dependencies. It runs as an unprivileged user.

```sh
docker build -t side-a .
docker run --rm -p 8000:10000 side-a
```

`render.yaml` creates one **free** Docker web service, with one conversion at a time and no paid database or persistent disk. The page and conversion API are public and do not require a password. The health endpoint `/health` is public and contains no job information.

`HOST` defaults to `127.0.0.1` locally and `0.0.0.0` in Docker. `PORT` is supplied by Render. Optional `PUBLIC_ORIGIN` restricts submissions to an exact origin; otherwise HTTP and HTTPS on the request host are accepted.

Render's free instances sleep after inactivity and lose temporary files and in-memory jobs on sleep, restart, or redeployment. Download finished files before leaving. Media providers may reject cloud datacenter IPs or require authentication; deployment cannot guarantee every YouTube or SoundCloud URL will work.

The browser requests `/health` immediately on page load, retries startup failures, and enables conversion when the server is ready. Render must serve the page before its JavaScript can run, so the first visit to a sleeping instance still has a cold-start delay. This is a bounded startup check, not a periodic keep-alive.

## Custom domain

The production hostname is `audio.aganonlabs.com`. In Namecheap Advanced DNS, the `audio` host uses a CNAME pointing to `side-a-mp3.onrender.com`. Render manages HTTPS certificates. The domain is also declared in `render.yaml`.
