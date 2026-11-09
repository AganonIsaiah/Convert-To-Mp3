import base64
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import app


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'APP_PASSWORD': 'test-password', 'PUBLIC_ORIGIN': ''})
        self.environment.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.auth = 'Basic ' + base64.b64encode(b'sidea:test-password').decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.environment.stop()

    def request(self, path, headers=None, data=None):
        request = Request(self.base + path, headers=headers or {}, data=data)
        try:
            return urlopen(request)
        except HTTPError as error:
            return error

    def test_page_and_jobs_are_public_even_with_legacy_password(self):
        self.assertEqual(self.request('/').code, 200)
        self.assertEqual(self.request('/api/jobs', data=b'{}').code, 400)
        response = self.request('/', {'Authorization': self.auth})
        self.assertEqual(response.code, 200)
        response.close()

    def test_health_does_not_require_password(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, 'DOWNLOADS', Path(directory)):
            response = self.request('/health')
            self.assertEqual(response.code, 200)
            self.assertEqual(json.load(response)['status'], 'ok')

    def test_health_routes_support_get_head_and_query_strings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, 'DOWNLOADS', Path(directory)), patch.object(app.shutil, 'which', return_value='/usr/bin/ffmpeg'):
            for path in ['/api/health', '/health', '/api/health/?check=1']:
                with self.subTest(path=path):
                    with self.request(path) as response:
                        self.assertEqual(response.code, 200)
                        self.assertEqual(json.load(response)['status'], 'ok')
                    with urlopen(Request(self.base + path, method='HEAD')) as response:
                        self.assertEqual(response.code, 200)
                        self.assertEqual(response.read(), b'')

    def test_health_reports_unavailable_dependencies(self):
        with patch.object(app.shutil, 'which', return_value=None):
            with self.request('/api/health') as response:
                self.assertEqual(response.code, 503)
                self.assertEqual(json.load(response)['status'], 'unavailable')

    def test_https_origin_accepted_behind_proxy(self):
        headers = {'Authorization': self.auth, 'Origin': 'https://side-a.example', 'Host': 'side-a.example', 'Content-Type': 'application/json'}
        # An invalid source URL produces 400, proving HTTPS was not rejected with 403.
        self.assertEqual(self.request('/api/jobs', headers, b'{"url":"https://example.com"}').code, 400)
        headers['Origin'] = 'https://another.example'
        self.assertEqual(self.request('/api/jobs', headers, b'{}').code, 403)
