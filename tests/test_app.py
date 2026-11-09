import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app


class DownloaderTests(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(app.validate_url('https://youtu.be/example'), 'https://youtu.be/example')
        app.validate_url('https://soundcloud.com/artist/sets/mix', True)
        for url in ['http://youtube.com/watch?v=x', 'https://youtube.com.evil.com/x', 'https://localhost/x', 'https://user:pass@youtube.com/x', 'https://youtube.com:80/x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                app.validate_url(url)
        with self.assertRaises(ValueError):
            app.validate_url('https://youtu.be/example', True)

    @unittest.skipUnless(app.shutil.which('ffmpeg'), 'FFmpeg required')
    def test_playlist_concatenation_preserves_order(self):
        original_run = app.run_command
        observed = []
        def fake_download(args, folder, timeout=3600):
            if args[0] == app.sys.executable:
                # Deliberately create tracks out of order.
                for index, frequency in [(2, 880), (1, 440)]:
                    name = f'{index:05d}-track'
                    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:duration=0.2', str(folder / (name + '.mp3'))], check=True)
                    (folder / (name + '.info.json')).write_text(json.dumps({'playlist_title': 'Test mix'}))
                return ''
            observed.extend((folder / 'tracks.txt').read_text().splitlines())
            return original_run(args, folder, timeout)
        with tempfile.TemporaryDirectory() as temporary, patch.object(app, 'DOWNLOADS', Path(temporary)), patch.object(app, 'run_command', fake_download):
            app.JOBS['test'] = {'status': 'queued'}
            app.convert('test', 'https://soundcloud.com/artist/sets/mix', True)
            self.assertEqual(app.JOBS['test']['status'], 'done', app.JOBS['test'])
            self.assertEqual(observed, ["file '00001-track.mp3'", "file '00002-track.mp3'"])
            self.assertGreater((Path(temporary) / 'test' / 'output.mp3').stat().st_size, 1000)
            self.assertEqual(app.JOBS['test']['tracks'], 2)
            self.assertEqual(len(list((Path(temporary) / 'test').iterdir())), 1)
        app.JOBS.pop('test')

    def test_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(app, 'DOWNLOADS', Path(temporary)), patch.object(app, 'run_command', side_effect=RuntimeError('Track unavailable')):
            app.JOBS['failure'] = {'status': 'queued'}
            app.convert('failure', 'https://youtu.be/example', False)
            self.assertEqual(app.JOBS['failure']['status'], 'error')
            self.assertFalse((Path(temporary) / 'failure').exists())
        app.JOBS.pop('failure')

class ProgressTests(unittest.TestCase):
    def test_playlist_progress_includes_track_position(self):
        import worker
        with patch.object(worker, 'report') as report:
            worker.progress({'status': 'downloading', 'downloaded_bytes': 50, 'total_bytes': 100, 'info_dict': {'playlist_index': 2, 'playlist_count': 4}})
            value = report.call_args.args[0]
            self.assertEqual(value['progress'], 31.9)
            self.assertEqual(value['message'], 'Downloading track 2 of 4…')

    def test_unknown_size_is_indeterminate(self):
        import worker
        with patch.object(worker, 'report') as report:
            worker.progress({'status': 'downloading', 'downloaded_bytes': 50, 'info_dict': {}})
            self.assertIsNone(report.call_args.args[0]['progress'])
