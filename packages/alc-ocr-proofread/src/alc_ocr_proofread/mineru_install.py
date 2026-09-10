"""Opt-in isolated MinerU installation and real OCR verification."""
from __future__ import annotations
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ac_jobs import FileLease, atomic_write_bytes
from ac_document import load_mineru_config, configure_mineru, doctor_configured_mineru, parse_pdf_configured_mineru
from alc_catalog.mineru import effective_config_path, remember_local_config

VERSION = '3.4.5'
DISK_RESERVE = 20 * 1024**3


def installation_root() -> Path:
    return Path.home() / '.alc/runtimes/mineru' / (VERSION + '-py311-' + platform.system().lower() + '-' + platform.machine())


def plan(project: Path) -> dict:
    config = load_mineru_config(effective_config_path(project))
    root = installation_root()
    probe = root
    while not probe.exists():
        probe = probe.parent
    return {'version': VERSION, 'backend':'pipeline', 'install_dir':str(root),
        'reuse_executable':config.get('executable') if config else None,
        'remote_configured':bool(config and config.get('api_url')),
        'platform_supported':platform.system() in ('Darwin','Linux'),
        'python_supported':sys.version_info[:2] == (3,11),
        'free_bytes':shutil.disk_usage(probe).free, 'recommended_free_bytes':DISK_RESERVE,
        'download_notice':'Downloads Python packages and OCR model weights. Size and duration depend on cached files and network; reserve 20 GiB for a new installation.',
        'project_config':str(Path(project).resolve()/'.ac/mineru.json')}


def _state(root, stage, **extra):
    atomic_write_bytes(root/'install-state.json', json.dumps({'stage':stage,'updated':time.time(),**extra}).encode())


def _run(argv, root, stage):
    _state(root, stage)
    env = {k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','LANG','LC_ALL','SYSTEMROOT')}
    env['PIP_CONFIG_FILE'] = os.devnull
    with (root/'install.log').open('ab') as log:
        os.chmod(root/'install.log', 0o600)
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            code = process.wait(timeout=1800)
        except BaseException:
            import signal
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            raise
    if code:
        raise ValueError(f'MinerU {stage} failed (exit {code}); inspect {root / "install.log"}. Existing configuration was preserved.')


def _sample(path):
    content=b'BT /F1 24 Tf 72 700 Td (ALC OCR verification 12345) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    data=bytearray(b'%PDF-1.4\n'); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data)); data.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(data);data.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    path.write_bytes(data)


def install(project: Path, *, accept_downloads: bool = False) -> dict:
    if not accept_downloads:
        raise ValueError('Review setup-mineru without --install first; explicit --accept-downloads is required.')
    project=Path(project).expanduser().resolve()
    value=plan(project)
    if value['remote_configured']:
        raise ValueError('Project uses a remote OCR service; automatic local setup will not replace it.')
    if not value['platform_supported']:
        raise ValueError('Automatic local MinerU setup currently supports macOS and Linux.')
    reuse=value['reuse_executable']
    if reuse and not Path(reuse).is_absolute():
        raise ValueError('Configured executable must be an absolute path.')
    if not reuse and not value['python_supported']:
        raise ValueError('Automatic installation requires Python 3.11; no system Python will be installed or changed.')
    if not reuse and value['free_bytes'] < DISK_RESERVE:
        raise ValueError('Reserve at least 20 GiB free space before a new MinerU installation.')
    root=Path(value['install_dir'])
    root.parent.mkdir(parents=True,exist_ok=True)
    with FileLease(root.parent/(root.name+'.lock')):
        if root.exists() and not (root/'owner.json').is_file():
            raise ValueError('Installation directory is not owned by ALC; it will not be modified.')
        root.mkdir(mode=0o700,exist_ok=True)
        owner={'contract':'alc.mineru.install.v1','version':VERSION}
        if (root/'owner.json').exists() and json.loads((root/'owner.json').read_text()) != owner:
            raise ValueError('Installation ownership marker does not match.')
        atomic_write_bytes(root/'owner.json',json.dumps(owner).encode())
        try:
            executable=Path(reuse) if reuse else root/'venv/bin/mineru'
            if not reuse:
                if not (root/'venv/bin/python').exists():
                    _run([sys.executable,'-m','venv',str(root/'venv')],root,'environment')
                if not (root/'packages-ready.json').exists():
                    _run([str(root/'venv/bin/python'),'-m','pip','install','--index-url','https://pypi.org/simple',
                          '--only-binary=:all:','--report',str(root/'packages-report.json'),'mineru[pipeline]=='+VERSION],root,'packages')
                    atomic_write_bytes(root/'packages-ready.json',b'{}')
            config=root/'verification-config.json'
            configure_mineru(config_path=config,executable=str(executable),language='en')
            doctor_configured_mineru(config_path=config)
            _state(root,'ocr_verification')
            # Fresh output prevents a cached success from masking a broken runtime.
            import tempfile
            check=Path(tempfile.mkdtemp(prefix='verify-',dir=root))
            sample=check/'sample.pdf';_sample(sample)
            result=parse_pdf_configured_mineru(sample,config_path=config,job_dir=check/'ocr',timeout_seconds=900)
            text=Path(result['source']).read_text()
            if result.get('status')!='completed' or '12345' not in text:
                raise ValueError('OCR verification did not recover the known sample text; configuration was not adopted.')
            target=project/'.ac/mineru.json'
            previous=load_mineru_config(target)
            if previous and previous.get('executable') != str(executable):
                raise ValueError('Project configuration changed during installation; refusing to overwrite it.')
            language=(previous or load_mineru_config(effective_config_path(project)) or {}).get('language','en')
            adopted=configure_mineru(config_path=target,executable=str(executable),language=language)
            try:
                default_saved = remember_local_config(adopted)
            except OSError:
                default_saved = False
            _state(root,'ready',executable=str(executable),inference_verified=True)
            return {**value,'executable':str(executable),'inference_verified':True,'configured':True,'default_saved':default_saved}
        except BaseException as exc:
            _state(root,'failed',error_type=type(exc).__name__)
            raise
