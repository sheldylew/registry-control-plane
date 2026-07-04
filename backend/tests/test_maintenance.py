from dataclasses import replace
from fastapi.testclient import TestClient
from pathlib import Path

from sqlalchemy import select
import os
from datetime import timedelta

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.maintenance import (
    CommandResult,
    LocalRegistryMaintenanceRunner,
    MaintenanceService,
    compute_storage_usage_bytes,
    mark_storage_usage_snapshot_stale,
    prune_empty_directories,
    read_storage_usage_snapshot,
)
from backend.log_retention import utcnow
from backend.models import AuditEvent, GcJob, RegistryEventInbox, RegistryStateRebuildJob, User
from backend.setup import AUDIT_LOG_RETENTION_DAYS_KEY, set_app_setting


class FakeMaintenanceRunner:
    def __init__(self, *, gc=None):
        self.gc_result = gc or CommandResult(returncode=0, stdout="gc ok")
        self.calls = []

    def registry_gc(self, *, delete_untagged: bool) -> CommandResult:
        self.calls.append(("gc", delete_untagged))
        return self.gc_result


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/session/login", json={"username": username, "password": password})


class FakeStorageStat:
    def __init__(self, *, st_dev: int, st_ino: int, st_blocks: int, st_size: int):
        self.st_dev = st_dev
        self.st_ino = st_ino
        self.st_blocks = st_blocks
        self.st_size = st_size


class FakeStoragePath:
    def __init__(self, file_stat: FakeStorageStat):
        self._file_stat = file_stat

    def exists(self) -> bool:
        return True

    def lstat(self) -> FakeStorageStat:
        return self._file_stat


def test_compute_storage_usage_counts_directories_and_deduplicates_inodes(monkeypatch) -> None:
    root = FakeStoragePath(FakeStorageStat(st_dev=1, st_ino=1, st_blocks=8, st_size=4096))
    directory = FakeStoragePath(FakeStorageStat(st_dev=1, st_ino=2, st_blocks=4, st_size=4096))
    blob = FakeStoragePath(FakeStorageStat(st_dev=1, st_ino=3, st_blocks=2, st_size=5))
    hardlink = FakeStoragePath(FakeStorageStat(st_dev=1, st_ino=3, st_blocks=2, st_size=5))
    monkeypatch.setattr("backend.maintenance._storage_paths", lambda _storage_root: [root, directory, blob, hardlink])

    assert compute_storage_usage_bytes(root) == (8 + 4 + 2) * 512


def test_storage_usage_root_defaults_to_registry_v2_parent(settings) -> None:
    custom_settings = replace(
        settings,
        registry_storage_root="/var/lib/registry/docker/registry/v2/repositories",
        registry_storage_usage_root=None,
    )

    assert custom_settings.registry_storage_usage_root == "/var/lib/registry/docker/registry/v2"


def test_storage_usage_refresh_counts_whole_registry_storage(settings, db_session, temp_workspace) -> None:
    usage_root = temp_workspace / "registry-data" / "docker" / "registry" / "v2"
    repository_root = usage_root / "repositories"
    metadata_path = repository_root / "sheldylew" / "app" / "_manifests" / "revisions" / "sha256" / "abc" / "link"
    blob_path = usage_root / "blobs" / "sha256" / "abc" / "data"
    metadata_path.parent.mkdir(parents=True)
    blob_path.parent.mkdir(parents=True)
    metadata_path.write_bytes(b"meta")
    blob_path.write_bytes(b"fresh")
    custom_settings = replace(
        settings,
        registry_storage_root=str(repository_root),
        registry_storage_usage_root=str(usage_root),
    )
    service = MaintenanceService(
        session_factory=None,
        settings=custom_settings,
        runner_factory=lambda: FakeMaintenanceRunner(),
    )
    repository_only_usage = compute_storage_usage_bytes(repository_root)
    full_usage = compute_storage_usage_bytes(usage_root)

    mark_storage_usage_snapshot_stale(db_session)
    service.refresh_storage_usage_snapshot(db_session)
    snapshot = read_storage_usage_snapshot(db_session)

    assert snapshot["bytes"] == full_usage
    assert snapshot["bytes"] > repository_only_usage
    assert snapshot["stale"] is False
    assert snapshot["measured_at"] is not None


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


def test_admin_maintenance_summary_omits_full_job_logs(settings) -> None:
    app = create_app(settings)
    now = utcnow()

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200

        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            gc_job = GcJob(
                status="succeeded",
                requested_by=admin.id,
                dry_run=False,
                delete_untagged=False,
                prune_empty_dirs=False,
                started_at=now,
                finished_at=now,
                log_output="gc line 1\ngc line 2\n",
                created_at=now,
                updated_at=now,
            )
            rebuild_job = RegistryStateRebuildJob(
                status="succeeded",
                requested_by=admin.id,
                repositories_scanned=1,
                tags_scanned=2,
                log_output="rebuild line 1\nrebuild line 2",
                created_at=now,
                updated_at=now,
                finished_at=now,
            )
            session.add_all([gc_job, rebuild_job])
            session.commit()
            gc_job_id = gc_job.id
            rebuild_job_id = rebuild_job.id

        summary_response = client.get("/api/admin/maintenance")
        gc_log_response = client.get(f"/api/admin/maintenance/jobs/{gc_job_id}/log")
        rebuild_log_response = client.get(f"/api/admin/maintenance/cache/rebuild/{rebuild_job_id}/log")

    body = summary_response.json()
    assert summary_response.status_code == 200
    assert body["last_job"]["log_output"] is None
    assert body["last_job"]["log_output_available"] is True
    assert body["last_job"]["log_output_line_count"] == 2
    assert body["jobs"][0]["log_output"] is None
    assert body["jobs"][0]["log_output_available"] is True
    assert body["jobs"][0]["log_output_line_count"] == 2
    assert body["registry_state"]["last_rebuild"]["log_output"] is None
    assert body["registry_state"]["last_rebuild"]["log_output_available"] is True
    assert body["rebuild_jobs"][0]["log_output"] is None
    assert body["rebuild_jobs"][0]["log_output_line_count"] == 2

    assert gc_log_response.status_code == 200
    assert gc_log_response.json()["job"]["log_output"] == "gc line 1\ngc line 2\n"
    assert rebuild_log_response.status_code == 200
    assert rebuild_log_response.json()["job"]["log_output"] == "rebuild line 1\nrebuild line 2"


def test_non_admin_cannot_access_maintenance_job_logs(settings) -> None:
    app = create_app(settings)
    now = utcnow()

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="log-reader",
                email="log-reader@example.com",
                password_hash=hash_password("log-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.flush()
            gc_job = GcJob(
                status="succeeded",
                requested_by=user.id,
                dry_run=False,
                delete_untagged=False,
                prune_empty_dirs=False,
                started_at=now,
                finished_at=now,
                log_output="private gc output",
                created_at=now,
                updated_at=now,
            )
            rebuild_job = RegistryStateRebuildJob(
                status="succeeded",
                requested_by=user.id,
                repositories_scanned=1,
                tags_scanned=1,
                log_output="private rebuild output",
                created_at=now,
                updated_at=now,
                finished_at=now,
            )
            session.add_all([gc_job, rebuild_job])
            session.commit()
            gc_job_id = gc_job.id
            rebuild_job_id = rebuild_job.id

        login = _login(client, "log-reader", "log-reader-pass")
        assert login.status_code == 200
        gc_log_response = client.get(f"/api/admin/maintenance/jobs/{gc_job_id}/log")
        rebuild_log_response = client.get(f"/api/admin/maintenance/cache/rebuild/{rebuild_job_id}/log")

    assert gc_log_response.status_code == 403
    assert rebuild_log_response.status_code == 403


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


def test_delete_untagged_cleanup_is_temporarily_disabled(settings) -> None:
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
            json={"dry_run": False, "delete_untagged": True, "prune_empty_dirs": False},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            job = session.scalar(select(GcJob).order_by(GcJob.id.desc()))

    assert response.status_code == 400
    assert response.json()["detail"] == "Aggressive cleanup is temporarily disabled while a safer replacement is being built."
    assert runner.calls == []
    assert job is None


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
    retention_days = 15
    stale_time = utcnow() - timedelta(days=retention_days + 1)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        with app.state.session_factory() as session:
            set_app_setting(session, AUDIT_LOG_RETENTION_DAYS_KEY, str(retention_days))
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
            session.add(
                RegistryEventInbox(
                    action="push",
                    repository_name="sheldylew/app",
                    tag="reconciled",
                    digest="sha256:reconciled",
                    raw_payload={},
                    dedupe_key="push|sheldylew/app|reconciled|sha256:reconciled",
                    status="reconciled",
                    received_at=stale_time,
                    processed_at=stale_time,
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
            inbox_rows = session.scalars(select(RegistryEventInbox)).all()

    assert response.status_code == 200
    assert response.json()["retention_days"] == retention_days
    assert response.json()["pruned"] == {
        "audit_events_deleted": 1,
        "gc_jobs_deleted": 1,
        "registry_event_inbox_deleted": 1,
        "web_sessions_deleted": 0,
        "personal_access_tokens_deleted": 0,
        "robot_tokens_deleted": 0,
    }
    assert jobs == []
    assert inbox_rows == []
    assert events[-1].action == "logs_pruned"
    assert events[-1].metadata_json["audit_events_deleted"] == 1
    assert events[-1].metadata_json["gc_jobs_deleted"] == 1
    assert events[-1].metadata_json["registry_event_inbox_deleted"] == 1
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
    monkeypatch.setenv("REGISTRY_STORAGE_USAGE_ROOT", "/var/lib/registry/docker/registry/v2")
    monkeypatch.setenv("REGISTRY_GC_CONFIG_PATH", "/etc/docker/registry/config.yml")
    monkeypatch.setenv("REGISTRY_INTERNAL_URL", "http://registry:5000")
    monkeypatch.setattr("backend.maintenance.subprocess.run", fake_run)

    runner = LocalRegistryMaintenanceRunner(registry_gc_config_path="/etc/docker/registry/config.yml")
    result = runner.registry_gc(delete_untagged=False)

    assert result.returncode == 0
    assert captured["args"] == ["registry", "garbage-collect", "/etc/docker/registry/config.yml"]
    assert "REGISTRY_STORAGE_ROOT" not in captured["env"]
    assert "REGISTRY_STORAGE_USAGE_ROOT" not in captured["env"]
    assert "REGISTRY_GC_CONFIG_PATH" not in captured["env"]
    assert "REGISTRY_INTERNAL_URL" not in captured["env"]
