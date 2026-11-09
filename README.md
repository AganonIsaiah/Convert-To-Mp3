# Side A — audio downloader

A local web app for converting YouTube or SoundCloud tracks to 192 kbps MP3. SoundCloud playlists can be combined into one MP3 in playlist order.

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
