from fastapi.testclient import TestClient
from sqlalchemy import select
import os
from datetime import timedelta

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.maintenance import CommandResult, LocalRegistryMaintenanceRunner, MaintenanceService, prune_empty_directories
from backend.log_retention import utcnow
from backend.models import AuditEvent, GcJob, User


class FakeMaintenanceRunner:
    def __init__(self, *, gc=None):
        self.gc_result = gc or CommandResult(returncode=0, stdout="gc ok")
        self.calls = []

    def registry_gc(self, *, delete_untagged: bool) -> CommandResult:
        self.calls.append(("gc", delete_untagged))
        return self.gc_result


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/session/login", json={"username": username, "password": password})


def test_non_admin_cannot_access_maintenance_summary(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="ops-reader",
                email="ops-reader@example.com",
                password_hash=hash_password("ops-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = _login(client, "ops-reader", "ops-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/admin/maintenance")

    assert response.status_code == 403


def test_admin_can_create_dry_run_gc_job(settings, temp_workspace) -> None:
    app = create_app(settings)
    runner = FakeMaintenanceRunner()
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": True, "delete_untagged": False, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            jobs = session.scalars(select(GcJob).order_by(GcJob.id.asc())).all()
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert jobs[-1].status == "succeeded"
    assert jobs[-1].dry_run is True
    assert runner.calls == []
    assert any(event.action == "gc_job_requested" for event in events)
    assert any(event.action == "gc_job_succeeded" for event in events)


def test_only_one_gc_job_can_be_queued(settings) -> None:
    app = create_app(settings)
    runner = FakeMaintenanceRunner()
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )
    app.state.maintenance_auto_run = False

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        first = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": True},
            headers={"X-CSRF-Token": csrf},
        )
        second = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": True},
            headers={"X-CSRF-Token": csrf},
        )

    assert first.status_code == 200
    assert second.status_code == 409


def test_delete_untagged_passes_gc_flag_and_job_failure_is_recorded(settings) -> None:
    app = create_app(settings)
    runner = FakeMaintenanceRunner(gc=CommandResult(returncode=1, stderr="gc failed"))
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": False, "delete_untagged": True, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            job = session.scalar(select(GcJob).order_by(GcJob.id.desc()))
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert runner.calls == [("gc", True)]
    assert job.status == "failed"
    assert any(event.action == "gc_job_failed" for event in events)


def test_registry_maintenance_gate_blocks_v2_when_destructive_job_is_queued(settings) -> None:
    app = create_app(settings)
    runner = FakeMaintenanceRunner()
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )
    app.state.maintenance_auto_run = False

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        create = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": False, "delete_untagged": False, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )
        assert create.status_code == 200

        blocked = client.get("/api/internal/registry-maintenance")

    assert blocked.status_code == 403


def test_prune_empty_directories_only_deletes_under_allowed_root(temp_workspace) -> None:
    root = temp_workspace / "registry-root"
    keep = root / "keep" / "_layers"
    delete_me = root / "repo" / "empty"
    keep.mkdir(parents=True)
    delete_me.mkdir(parents=True)
    (keep / "marker.txt").write_text("live")

    deleted = prune_empty_directories(root, allowed_root=root)

    assert "repo/empty" in deleted
    assert keep.exists() is True


def test_prune_empty_directories_rejects_bad_root(temp_workspace) -> None:
    root = temp_workspace / "registry-root"
    root.mkdir(parents=True)
    disallowed = root / ".." / "elsewhere"

    try:
        prune_empty_directories(disallowed, allowed_root=root)
    except ValueError as exc:
        assert "Refusing to prune outside configured registry storage root" in str(exc)
    else:
        raise AssertionError("Expected prune_empty_directories to reject a bad root")


def test_maintenance_logs_do_not_contain_admin_password(settings) -> None:
    app = create_app(settings)
    runner = FakeMaintenanceRunner()
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": False, "delete_untagged": False, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            job = session.scalar(select(GcJob).order_by(GcJob.id.desc()))

    assert response.status_code == 200
    assert settings.admin_password not in (job.log_output or "")


def test_admin_can_prune_retained_logs_manually(settings) -> None:
    app = create_app(settings)
    stale_time = utcnow() - timedelta(days=settings.log_retention_days + 1)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        with app.state.session_factory() as session:
            session.add(
                AuditEvent(
                    actor_type="system",
                    action="old_event",
                    created_at=stale_time,
                )
            )
            session.add(
                GcJob(
                    status="succeeded",
                    requested_by=1,
                    finished_at=stale_time,
                    created_at=stale_time,
                    updated_at=stale_time,
                )
            )
            session.commit()

        response = client.post(
            "/api/admin/maintenance/logs/prune",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
            jobs = session.scalars(select(GcJob)).all()

    assert response.status_code == 200
    assert response.json()["retention_days"] == settings.log_retention_days
    assert response.json()["pruned"] == {
        "audit_events_deleted": 1,
        "gc_jobs_deleted": 1,
        "web_sessions_deleted": 0,
        "personal_access_tokens_deleted": 0,
        "robot_tokens_deleted": 0,
    }
    assert jobs == []
    assert events[-1].action == "logs_pruned"
    assert events[-1].metadata_json["audit_events_deleted"] == 1
    assert events[-1].metadata_json["gc_jobs_deleted"] == 1
    assert events[-1].metadata_json["web_sessions_deleted"] == 0


def test_non_admin_cannot_prune_retained_logs_manually(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="ops-editor",
                email="ops-editor@example.com",
                password_hash=hash_password("ops-editor-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = _login(client, "ops-editor", "ops-editor-pass")
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/logs/prune",
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 403


def test_destructive_gc_holds_maintenance_gate_for_minimum_duration(settings, monkeypatch) -> None:
    runner = FakeMaintenanceRunner()
    sleep_calls = []
    monotonic_values = iter((100.0, 100.2))
    app = create_app(settings)
    app.state.maintenance_service_factory = lambda: MaintenanceService(
        session_factory=app.state.session_factory,
        settings=settings,
        runner_factory=lambda: runner,
    )

    monkeypatch.setattr("backend.maintenance.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("backend.maintenance.sleep", lambda seconds: sleep_calls.append(seconds))

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": False, "delete_untagged": False, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert runner.calls == [("gc", False)]
    assert len(sleep_calls) == 1
    assert abs(sleep_calls[0] - 0.8) < 0.0001


def test_local_registry_runner_strips_app_registry_env(monkeypatch) -> None:
    captured = {}

    def fake_run(args, check, capture_output, text, env):
        captured["args"] = args
        captured["env"] = env

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    monkeypatch.setenv("REGISTRY_STORAGE_ROOT", "/var/lib/registry/docker/registry/v2/repositories")
    monkeypatch.setenv("REGISTRY_GC_CONFIG_PATH", "/etc/docker/registry/config.yml")
    monkeypatch.setenv("REGISTRY_INTERNAL_URL", "http://registry:5000")
    monkeypatch.setattr("backend.maintenance.subprocess.run", fake_run)

    runner = LocalRegistryMaintenanceRunner(registry_gc_config_path="/etc/docker/registry/config.yml")
    result = runner.registry_gc(delete_untagged=False)

    assert result.returncode == 0
    assert captured["args"] == ["registry", "garbage-collect", "/etc/docker/registry/config.yml"]
    assert "REGISTRY_STORAGE_ROOT" not in captured["env"]
    assert "REGISTRY_GC_CONFIG_PATH" not in captured["env"]
    assert "REGISTRY_INTERNAL_URL" not in captured["env"]
