import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_auth_init_module():
    module_path = ROOT / "scripts/auth-init.py"
    spec = importlib.util.spec_from_file_location("auth_init_script", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_existing_registry_config_permissions_are_normalized(temp_workspace, monkeypatch) -> None:
    auth_init = _load_auth_init_module()
    config_path = temp_workspace / "registry-config" / "config.yml"
    config_path.parent.mkdir()
    config_path.write_text("version: 0.1\n", encoding="utf-8")
    chown_calls = []
    chmod_calls = []

    monkeypatch.setattr(auth_init, "APP_UID", 10001)
    monkeypatch.setattr(auth_init, "APP_GID", 10001)
    monkeypatch.setattr(auth_init, "REGISTRY_RENDERED_CONFIG_PATH", config_path)
    monkeypatch.setattr(auth_init.os, "chown", lambda path, uid, gid: chown_calls.append((Path(path), uid, gid)))
    monkeypatch.setattr(auth_init.os, "chmod", lambda path, mode: chmod_calls.append((Path(path), mode)))

    auth_init._normalize_registry_config_permissions()

    assert (config_path.parent, 10001, 10001) in chown_calls
    assert (config_path, 10001, 10001) in chown_calls
    assert (config_path.parent, 0o755) in chmod_calls
    assert (config_path, 0o644) in chmod_calls
