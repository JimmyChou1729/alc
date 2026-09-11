"""Optional speech commands exposed through the existing alc-render executable."""
from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import time
import webbrowser


def add_tts_parser(subparsers):
    parser = subparsers.add_parser('tts', help='optional local speech installation and Reader playback')
    commands = parser.add_subparsers(dest='tts_command', required=True)
    commands.add_parser('status', help='inspect local installation without downloading')
    commands.add_parser('voices', help='list the built-in model voices')
    install = commands.add_parser('install', help='install the optional runtime and model')
    install.add_argument('--yes', action='store_true', help='explicitly consent to the model and runtime download')
    configure = commands.add_parser('configure', help='select local speech and voices')
    group = configure.add_mutually_exclusive_group()
    group.add_argument('--enable', action='store_true')
    group.add_argument('--disable', action='store_true')
    configure.add_argument('--voice-zh')
    configure.add_argument('--voice-en')
    speak = commands.add_parser('speak', help='synthesize a short local WAV sample')
    speak.add_argument('--text', required=True)
    speak.add_argument('--language', default='zh-CN')
    speak.add_argument('--voice')
    speak.add_argument('--rate', type=float, default=1)
    speak.add_argument('--output', type=Path, required=True)
    reader = commands.add_parser('open', help='open an ALC HTML with a local speech connection; keep this terminal running')
    reader.add_argument('html', type=Path)


def run_tts(args):
    from .tts_engine import TTSManager
    manager = TTSManager()
    try:
        command = args.tts_command
        if command == 'status':
            return manager.status()
        if command == 'voices':
            return {'voices': manager.status()['voices']}
        if command == 'install':
            if not args.yes:
                raise ValueError('Installation downloads an optional model and runtime. Confirm with alc-render tts install --yes.')
            manager.install()
            while True:
                status = manager.status()
                if status['install']['state'] != 'running':
                    if status['install']['state'] == 'failed':
                        raise RuntimeError(status['install']['message'])
                    return status
                time.sleep(.25)
        if command == 'configure':
            current = manager.status()
            return manager.configure(
                enabled=True if args.enable else False if args.disable else current['enabled'],
                voice_zh=args.voice_zh or current['voice_zh'],
                voice_en=args.voice_en or current['voice_en'],
            )
        if command == 'speak':
            audio = manager.synthesize(args.text, language=args.language, voice=args.voice, rate=args.rate)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('xb') as output:
                output.write(audio)
            return {'audio': str(args.output.resolve()), 'bytes': len(audio)}
        if command == 'open':
            from .html import _extract_reader_payload
            from .contracts import publication_from_document
            from .tts_host import ReaderHosts
            path = args.html.expanduser().resolve()
            content = path.read_bytes()
            payload = _extract_reader_payload(content.decode('utf-8'))
            publication_from_document(payload.get('publication'))
            digest = hashlib.sha256(content).hexdigest()
            origin_key = hashlib.sha256((str(path) + digest).encode()).hexdigest()
            hosts = ReaderHosts(
                state_path=manager.root / 'reader-origins' / (origin_key + '.json'),
                tts_manager=manager,
            )
            try:
                url = hosts.open(path, digest)
                if not webbrowser.open(url):
                    raise RuntimeError('Could not open the default browser.')
                print('ALC Reader opened with optional local speech. Keep this terminal running; Ctrl+C stops the service.', flush=True)
                threading.Event().wait()
            except KeyboardInterrupt:
                return {'status': 'stopped'}
            finally:
                hosts.close()
        raise ValueError('Unknown local speech command.')
    finally:
        manager.close()
