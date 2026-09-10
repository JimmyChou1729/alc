"""Keep discovery tests separate from the user's local project catalog."""
import pytest


@pytest.fixture(autouse=True)
def isolated_task_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv('ALC_CATALOG_DIR', str(tmp_path / 'task-catalog'))
