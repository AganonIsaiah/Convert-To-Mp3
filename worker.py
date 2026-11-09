"""Isolated yt-dlp process with progress reports for the local web UI."""
import json
import sys
from pathlib import Path
from yt_dlp import YoutubeDL


def report(data):
    temporary = Path('progress.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace('progress.json')


def progress(event):
    info = event.get('info_dict', {})
    index = info.get('playlist_index') or 1
    count = info.get('playlist_count') or info.get('n_entries')
    total = event.get('total_bytes') or event.get('total_bytes_estimate')
    fraction = min(event.get('downloaded_bytes', 0) / total, 1) if total else None
    if event['status'] == 'finished':
        fraction = 1
    percent = None
    if fraction is not None:
        percent = round(85 * ((index - 1 + fraction) / count if count else fraction), 1)
    label = f'Downloading track {index} of {count}…' if count else 'Downloading audio…'
    if event['status'] == 'finished':
        percent = None
        label = f'Converting track {index} to MP3…'
    report({'progress': percent, 'message': label})


if __name__ == '__main__':
    playlist = sys.argv[2] == 'playlist'
    options = {
        'js_runtimes': {'node': {}},
        'format': 'bestaudio/best', 'noplaylist': not playlist,
        'cachedir': False, 'socket_timeout': 30, 'retries': 3,
        'max_filesize': 500 * 1024 * 1024, 'restrictfilenames': True,
        'writeinfojson': True, 'outtmpl': '%(playlist_index)05d-%(id)s.%(ext)s',
        'progress_hooks': [progress],
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }
    if playlist:
        options['max_downloads'] = 101
    with YoutubeDL(options) as downloader:
        downloader.download([sys.argv[1]])
