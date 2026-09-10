import hashlib
import httpx
from alc_web.reader_host import ReaderHosts


def test_isolated_reader_origin_only_serves_verified_capability(tmp_path):
    page = tmp_path / 'reader.html'
    page.write_text('<html>Reader</html>')
    digest = hashlib.sha256(page.read_bytes()).hexdigest()
    hosts = ReaderHosts()
    try:
        url = hosts.open(page, digest)
        assert hosts.open(page, digest) == url
        with httpx.Client(trust_env=False) as client:
            response = client.get(url)
            assert response.status_code == 200
            csp = response.headers['content-security-policy']
            assert 'allow-same-origin' in csp and "connect-src 'none'" in csp
            assert 'set-cookie' not in response.headers
            assert client.get(url, headers={'Host':'evil.test'}).status_code == 403
            assert client.get(str(httpx.URL(url).copy_with(path='/api/jobs'))).status_code == 404
            assert client.post(url).status_code == 501
            page.write_text('changed')
            assert client.get(url).status_code == 409
    finally:
        hosts.close()


def test_runtime_refresh_preserves_payload_and_unknown_html():
    from alc_web.reader_host import refresh_reader_runtime
    source=b'<html><script type="application/json">{"unchanged":true}</script><script>function renderSourceRow(){} function setupEditor(){}</script><p>Source</p></html>'
    result=refresh_reader_runtime(source)
    assert b'"unchanged":true' in result and b'<p>Source</p>' in result
    assert b'dismissTranslationQuality' in result
    assert refresh_reader_runtime(b'<html>unknown</html>')==b'<html>unknown</html>'


def test_reader_origin_survives_restart(tmp_path):
    path=tmp_path/'page.html';path.write_text('Reader')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    state=tmp_path/'ports.json'
    first=ReaderHosts(state)
    url=first.open(path,digest);first.close()
    second=ReaderHosts(state)
    try:
        fresh=second.open(path,digest)
        assert httpx.URL(fresh).port==httpx.URL(url).port
        assert fresh!=url
        with httpx.Client(trust_env=False) as client:
            assert client.get(url).status_code==404
            assert client.get(fresh).status_code==200
    finally:second.close()
