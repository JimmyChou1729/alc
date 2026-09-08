from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_bootstrap_environment(monkeypatch):
    for key in ('AC_HOME', 'AC_INSTALL_SOURCE', 'AC_PRODUCT_REPO_ROOT',
                'AC_FOUNDATION_REPO_ROOT', 'AC_RUNTIME_SOURCES_FILE',
                'AC_RUNTIME_CONSTRAINTS_FILE', 'AC_RUNTIME_LAUNCHER_NAME',
                'PYTHONPATH', 'PYTHONHOME'):
        if key in os.environ:
            monkeypatch.setenv(key, os.environ[key])
        else:
            monkeypatch.delenv(key, raising=False)


def bootstrap():
    spec = importlib.util.spec_from_file_location('web_bootstrap_test', ROOT / 'scripts/alc-web.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_root(tmp_path):
    root = tmp_path / 'alc'
    for relative in ('plugins/alc/skills/alc/scripts/runtime-sources.json',
                     'plugins/alc/skills/alc/scripts/runtime-constraints.txt',
                     'packages/alc-web/runtime-constraints.txt'):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    for name in ('package.json', 'package-lock.json', 'index.html', 'tsconfig.json', 'vite.config.ts', 'src/main.tsx'):
        path = root / 'apps/web' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    doc = json.loads((root / 'plugins/alc/skills/alc/scripts/runtime-sources.json').read_text())
    for source in doc['sources']:
        if source['id'] == 'product':
            for name in [*source['packages'], 'alc-web']:
                path = root / 'packages' / name
                path.mkdir(parents=True, exist_ok=True)
                (path / 'pyproject.toml').write_text('[project]\nname="'+name+'"\nversion="2.0.6"\n')
    return root


def test_single_checkout_uses_pinned_remote_foundation(tmp_path, monkeypatch):
    module = bootstrap(); runtime = module.load_runtime(); root = fixture_root(tmp_path)
    monkeypatch.setenv('AC_HOME', str(tmp_path / 'ac-home'))
    monkeypatch.delenv('AC_FOUNDATION_REPO_ROOT', raising=False)
    monkeypatch.setenv('AC_PRODUCT_REPO_ROOT', 'ignored-previous-product')
    monkeypatch.setenv('AC_INSTALL_SOURCE', 'auto')
    before = (root / 'plugins/alc/skills/alc/scripts/runtime-sources.json').read_bytes()
    (tmp_path / 'ac-foundation').mkdir()  # An adjacent checkout is not implicit authority.
    path, constraints = module.prepare_configuration(root, runtime)
    lock = runtime.load_lock(path)
    mode, roots = runtime._source_selection(lock)
    assert mode == 'mixed' and set(roots) == {'product'}
    requirements = runtime._requirements(lock, mode, roots)
    foundation = next(s for s in lock.sources if s.source_id == 'foundation')
    assert all(f'@{foundation.commit}#subdirectory=packages/' in item for item in requirements[:4])
    assert requirements[-1] == str(root / 'packages/alc-web')
    assert lock.profile == 'alc-web' and 'alc-web' in lock.tools
    assert 'fastapi==' in constraints.read_text()
    assert (root / 'plugins/alc/skills/alc/scripts/runtime-sources.json').read_bytes() == before
    assert module.prepare_configuration(root, runtime) == (path, constraints)


def test_frontend_rebuilds_only_when_needed(tmp_path, monkeypatch):
    module = bootstrap(); runtime = module.load_runtime(); root = fixture_root(tmp_path)
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/fixture/npm')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[-1] == 'build':
            path = root / 'packages/alc-web/src/alc_web/static/index.html'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('built')
    monkeypatch.setattr(module.subprocess, 'run', run)
    first = module.ensure_frontend(root, runtime)
    assert [c[-1] for c in calls] == ['ci', 'build']
    monkeypatch.setattr(module.shutil, 'which', lambda _: None)
    assert module.ensure_frontend(root, runtime) == first
    (root / 'apps/web/src/main.tsx').write_text('changed')
    with pytest.raises(RuntimeError, match='Node.js'):
        module.ensure_frontend(root, runtime)


def test_failed_frontend_build_does_not_mark_ready(tmp_path, monkeypatch):
    module = bootstrap(); root = fixture_root(tmp_path)
    monkeypatch.setattr(module.shutil, 'which', lambda _: 'npm')
    def fail(*args, **kwargs):raise subprocess.CalledProcessError(1, 'npm')
    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):module.ensure_frontend(root, module.load_runtime())
    assert not (root / 'packages/alc-web/src/alc_web/static/.source-fingerprint').exists()


def test_doctor_does_not_build_or_install(tmp_path, monkeypatch):
    module = bootstrap(); root = fixture_root(tmp_path)
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setenv('AC_HOME', str(tmp_path / 'home'))
    monkeypatch.delenv('ALC_WEB_PYTHON', raising=False)
    monkeypatch.delenv('AC_FOUNDATION_REPO_ROOT', raising=False)
    runtime = module.load_runtime()
    calls = []
    def missing(args):
        calls.append(args); print(json.dumps({'ready': False})); return 1
    monkeypatch.setattr(runtime, 'main', missing)
    monkeypatch.setattr(module, 'load_runtime', lambda: runtime)
    monkeypatch.setattr(module, 'ensure_frontend', lambda *args: pytest.fail('doctor must not build'))
    assert module.main(['--runtime-doctor']) == 1
    assert calls == [['doctor']]


def test_explicit_python_override_skips_bootstrap(monkeypatch):
    module = bootstrap(); calls = []
    monkeypatch.setenv('ALC_WEB_PYTHON', '/existing/python')
    monkeypatch.setattr(module.subprocess, 'call', lambda args: calls.append(args) or 0)
    monkeypatch.setattr(module, 'load_runtime', lambda: pytest.fail('must use override'))
    assert module.main(['--project-dir','space path']) == 0
    assert calls == [['/existing/python','-m','alc_web','--project-dir','space path']]
    assert module.main(['--runtime-setup']) == 64


def test_default_runtime_ignores_python_environment_injection(tmp_path, monkeypatch):
    module = bootstrap(); runtime = module.load_runtime(); root = fixture_root(tmp_path)
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setenv('AC_HOME', str(tmp_path / 'home'))
    monkeypatch.delenv('ALC_WEB_PYTHON', raising=False)
    monkeypatch.delenv('AC_FOUNDATION_REPO_ROOT', raising=False)
    injected = tmp_path / 'injected'; injected.mkdir()
    (injected / 'alc_web_probe.py').write_text('raise RuntimeError("wrong dependency")')
    monkeypatch.setenv('PYTHONPATH', str(injected))
    monkeypatch.setenv('PYTHONHOME', '/not-a-python-home')
    def inspect_child(args):
        child = subprocess.run([sys.executable, '-c',
            'import importlib.util; assert importlib.util.find_spec("alc_web_probe") is None'],
            capture_output=True, text=True)
        assert child.returncode == 0, child.stderr
        print(json.dumps({'ready': False}))
        return 1
    monkeypatch.setattr(runtime, 'main', inspect_child)
    monkeypatch.setattr(module, 'load_runtime', lambda: runtime)
    assert module.main(['--runtime-doctor']) == 1


def test_doctor_rejects_installed_incompatible_runtime(monkeypatch, capsys):
    module = bootstrap(); runtime = module.load_runtime()
    def installed(args):
        print(json.dumps({'ready': True, 'runtime': '/fixture/runtime'})); return 0
    monkeypatch.setattr(runtime, 'main', installed)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 78, '', 'incompatible Foundation'))
    assert module.runtime_doctor(runtime) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['installed'] and not report['ready'] and not report['compatible']
