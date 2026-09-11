import pytest
from alc_render.cli import main


def test_status_is_offline_and_install_requires_consent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('ALC_TTS_DIR', str(tmp_path / 'tts'))
    assert main(['tts', 'status']) == 0
    assert '"installed": false' in capsys.readouterr().out
    assert not (tmp_path / 'tts').exists()
    with pytest.raises(SystemExit):
        main(['tts', 'install'])
    assert not (tmp_path / 'tts').exists()


def test_standalone_open_rejects_unknown_html_without_installing(tmp_path, monkeypatch):
    monkeypatch.setenv('ALC_TTS_DIR', str(tmp_path / 'tts'))
    path = tmp_path / 'unknown.html'
    path.write_text('<html>Not an ALC document</html>')
    with pytest.raises(SystemExit):
        main(['tts', 'open', str(path)])
    assert not (tmp_path / 'tts').exists()


def test_cli_reopen_reuses_origin_with_separate_document_state(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    import alc_render.contracts
    import alc_render.html
    import alc_render.tts_cli as cli
    import alc_render.tts_engine

    root = tmp_path / "tts"
    monkeypatch.setattr(alc_render.tts_engine, "TTSManager", lambda: SimpleNamespace(root=root, close=lambda: None))
    monkeypatch.setattr(alc_render.html, "_extract_reader_payload", lambda _: {"publication": {}})
    monkeypatch.setattr(alc_render.contracts, "publication_from_document", lambda _: None)
    urls = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: urls.append(url) or True)
    class InterruptedWait:
        def wait(self):
            raise KeyboardInterrupt
    monkeypatch.setattr(cli, "threading", SimpleNamespace(Event=InterruptedWait))
    first = tmp_path / "one.html"
    second = tmp_path / "two.html"
    first.write_text("<html><head></head><body>one</body></html>")
    second.write_text("<html><head></head><body>two</body></html>")
    for path in (first, second, first):
        assert cli.run_tts(SimpleNamespace(tts_command="open", html=path)) == {"status": "stopped"}
    assert urlsplit(urls[0]).netloc == urlsplit(urls[2]).netloc
    assert len(list((root / "reader-origins").glob("*.json"))) == 2
    alias = tmp_path / "alias.html"
    alias.symlink_to(first)
    cli.run_tts(SimpleNamespace(tts_command="open", html=alias))
    assert urlsplit(urls[0]).netloc == urlsplit(urls[3]).netloc
    assert len(list((root / "reader-origins").glob("*.json"))) == 2
    first.write_text("<html><head></head><body>updated</body></html>")
    cli.run_tts(SimpleNamespace(tts_command="open", html=first))
    assert len(list((root / "reader-origins").glob("*.json"))) == 3
