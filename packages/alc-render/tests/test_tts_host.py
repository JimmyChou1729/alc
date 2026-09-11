import hashlib
import json

import httpx

from alc_render.tts_host import ReaderHosts


class FakeSpeech:
    def status(self):
        return {'enabled': True, 'installed': True, 'voices': [], 'models': [{'id': 'kitten-tts-micro-0.8', 'installed': True}], 'selections': {'zh': None, 'en': {'model_id': 'kitten-tts-micro-0.8', 'voice': 'Jasper'}}}

    def synthesize(self, text, **kwargs):
        self.request = text, kwargs
        return b'RIFFtestWAVEaudio'


def test_audio_capability_is_separate_from_task_and_install_apis(tmp_path):
    path = tmp_path / 'reader.html'
    path.write_text('''<html><head><meta http-equiv="Content-Security-Policy" content="connect-src 'none'"></head><body><script id="alc-render-payload" type="application/json">{"test":true}</script><script>function renderSourceRow(){} function setupEditor(){}</script></body></html>''')
    original = path.read_bytes()
    manager = FakeSpeech()
    hosts = ReaderHosts(tts_manager=manager)
    try:
        url = hosts.open(path, hashlib.sha256(original).hexdigest())
        origin = str(httpx.URL(url).copy_with(path='/')).rstrip('/')
        with httpx.Client(trust_env=False) as client:
            reader = client.get(url)
            assert reader.status_code == 200
            assert b'id="alc-tts-config"' in reader.content
            assert 'connect-src ' + url + '/tts/' in reader.headers['content-security-policy']
            assert "media-src data: blob:" in reader.headers['content-security-policy']
            assert path.read_bytes() == original
            assert client.get(url + '/tts/status').json()['installed']
            assert client.get(url + '/tts/status', headers={'Origin': 'http://evil.test'}).status_code == 403
            assert client.get(url + '/tts/status', headers={'Host': 'evil.test'}).status_code == 403
            assert client.post(url + '/tts/speech', json={'text': 'private'}).status_code == 403
            headers = {'Origin': origin}
            result = client.post(url + '/tts/speech', json={'text': 'Hello', 'language': 'en-US'}, headers=headers)
            assert result.status_code == 200 and result.headers['content-type'] == 'audio/wav'
            assert manager.request[0] == 'Hello'
            status = client.get(url + '/tts/status').json()
            assert status['models'][0]['id'] == 'kitten-tts-micro-0.8'
            assert status['selections']['en']['voice'] == 'Jasper'
            result = client.post(url + '/tts/speech', json={'text': 'Named voice', 'language': 'en-US', 'model_id': 'kitten-tts-micro-0.8', 'voice': 'Jasper'}, headers=headers)
            assert result.status_code == 200
            assert manager.request[1]['model_id'] == 'kitten-tts-micro-0.8'
            assert manager.request[1]['voice'] == 'Jasper'
            assert client.post(url + '/tts/speech', json={'text': 'Bad', 'model_id': []}, headers=headers).status_code == 400
            assert client.post(url + '/tts/install', json={'confirmed': True}, headers=headers).status_code == 404
            assert client.get(origin + '/api/jobs').status_code == 404
            assert client.post(url + '/tts/speech', json={'text': 'a' * 8001}, headers=headers).status_code == 400
            assert client.post(url + '/tts/speech', json={'text': 'a' * 70000}, headers=headers).status_code == 413
            assert client.post(url + '/tts/speech', content='text=hello', headers=headers).status_code == 415
    finally:
        hosts.close()


def test_disconnected_request_cancels_only_its_synthesis(tmp_path):
    import socket
    import threading
    from urllib.parse import urlsplit

    class CancellableSpeech(FakeSpeech):
        started = threading.Event()
        cancelled = threading.Event()

        def synthesize(self, text, **kwargs):
            if text == 'cancel me':
                self.started.set()
                assert kwargs['cancel_event'].wait(3)
                self.cancelled.set()
                raise RuntimeError('cancelled')
            assert not kwargs['cancel_event'].is_set()
            return super().synthesize(text, **kwargs)

    path = tmp_path / 'reader.html'
    path.write_text('<html><head></head></html>')
    manager = CancellableSpeech()
    hosts = ReaderHosts(tts_manager=manager)
    try:
        url = hosts.open(path, hashlib.sha256(path.read_bytes()).hexdigest())
        parsed = urlsplit(url)
        body = json.dumps({'text': 'cancel me'}).encode()
        connection = socket.create_connection(('127.0.0.1', parsed.port))
        headers = (f'POST {parsed.path}/tts/speech HTTP/1.1\r\nHost: {parsed.netloc}\r\n'
                   f'Origin: http://{parsed.netloc}\r\nContent-Type: application/json\r\n'
                   f'Content-Length: {len(body)}\r\n\r\n').encode()
        connection.sendall(headers + body)
        assert manager.started.wait(2)
        connection.close()
        assert manager.cancelled.wait(2)
        with httpx.Client(trust_env=False) as client:
            response = client.post(url + '/tts/speech', json={'text': 'keep me'},
                                   headers={'Origin': f'http://{parsed.netloc}'})
        assert response.status_code == 200
    finally:
        hosts.close()
