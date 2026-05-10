from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy.orm import Session

from backend.auth.registry_tokens import bootstrap_signing_material
from backend.config import Settings
from backend.db import make_engine, make_session_factory
from backend.metrics import reset as reset_metrics
from backend.models import Base


@pytest.fixture
def temp_workspace():
    with TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def temp_database_url(temp_workspace):
    return f"sqlite:///{temp_workspace / 'test.db'}"


@pytest.fixture
def settings(temp_database_url, temp_workspace):
    app_settings = Settings(
        app_env="development",
        database_url=temp_database_url,
        registry_internal_url="http://registry:5000",
        registry_storage_root=str(temp_workspace / "registry-data"),
        compose_project_dir=str(ROOT),
        registry_service_name="registry",
        registry_gc_config_path="/etc/docker/registry/config.yml",
        token_issuer="sheldylew-registry",
        token_service="sheldylew-registry",
        token_ttl_seconds=900,
        public_registry_origin="http://localhost:8080",
        auth_private_key_path=str(temp_workspace / "auth-private.pem"),
        auth_public_cert_path=str(temp_workspace / "auth-cert.pem"),
        auth_bootstrap_marker_path=str(temp_workspace / "auth-bootstrap-complete"),
        setup_token_path=str(temp_workspace / "setup-token.json"),
        setup_complete_marker_path=str(temp_workspace / "setup-complete"),
        registry_notifications_token_path=str(temp_workspace / "registry-events-token"),
        registry_config_template_path=str(ROOT / "docker/registry-config.yml.tmpl"),
        registry_rendered_config_path=str(temp_workspace / "registry-config.yml"),
        internal_api_base_url="http://api:8000",
        admin_username="admin",
        admin_password="s3cret-pass",
        admin_email="admin@example.com",
    )
    bootstrap_signing_material(app_settings)
    return app_settings


@pytest.fixture
def session(temp_database_url):
    engine = make_engine(temp_database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as db:
        yield db


@pytest.fixture
def db_session(session) -> Session:
    return session


@pytest.fixture(autouse=True)
def metrics_state():
    reset_metrics()
    yield
    reset_metrics()
