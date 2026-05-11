from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
from time import monotonic, sleep
import subprocess
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.log_retention import prune_expired_logs, prune_expired_operational_records
from backend.models import AuditEvent, GcJob, User
from backend.setup import (
    REGISTRY_STORAGE_USAGE_BYTES_KEY,
    REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY,
    REGISTRY_STORAGE_USAGE_STALE_KEY,
    get_app_setting,
    set_app_setting,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_storage_usage_bytes(storage_root: Path) -> int:
    if not storage_root.exists():
        return 0

    total = 0
    for path in storage_root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _serialize_datetime(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_storage_usage_snapshot(session: Session, *, usage_bytes: int, measured_at: Optional[datetime] = None) -> None:
    measured = measured_at or utcnow()
    set_app_setting(session, REGISTRY_STORAGE_USAGE_BYTES_KEY, str(max(int(usage_bytes), 0)))
    set_app_setting(session, REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY, _serialize_datetime(measured))
    set_app_setting(session, REGISTRY_STORAGE_USAGE_STALE_KEY, "false")


def mark_storage_usage_snapshot_stale(session: Session) -> None:
    set_app_setting(session, REGISTRY_STORAGE_USAGE_STALE_KEY, "true")


def read_storage_usage_snapshot(session: Session) -> dict[str, Optional[object]]:
    raw_bytes = get_app_setting(session, REGISTRY_STORAGE_USAGE_BYTES_KEY)
    raw_measured_at = get_app_setting(session, REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY)
    raw_stale = get_app_setting(session, REGISTRY_STORAGE_USAGE_STALE_KEY)
    try:
        usage_bytes = max(int(raw_bytes), 0) if raw_bytes is not None else 0
    except ValueError:
        usage_bytes = 0
    return {
        "bytes": usage_bytes,
        "measured_at": _parse_datetime(raw_measured_at),
        "stale": raw_stale is not None and raw_stale.strip().casefold() in {"1", "true", "yes", "on"},
    }


def prune_empty_directories(storage_root: Path, *, allowed_root: Optional[Path] = None) -> list[str]:
    resolved_root = storage_root.resolve(strict=False)
    resolved_allowed = (allowed_root or storage_root).resolve(strict=False)
    if resolved_root != resolved_allowed:
        raise ValueError("Refusing to prune outside configured registry storage root.")

    if not resolved_root.exists():
        return []

    deleted: list[str] = []
    for path in sorted(resolved_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not path.is_dir():
            continue
        try:
            path.rmdir()
            deleted.append(str(path.relative_to(resolved_root)))
        except OSError:
            pass
    return deleted


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class MaintenanceRunner:
    def registry_gc(self, *, delete_untagged: bool) -> CommandResult:
        raise NotImplementedError


class LocalRegistryMaintenanceRunner(MaintenanceRunner):
    def __init__(self, *, registry_gc_config_path: str):
        self._config_path = registry_gc_config_path

    def _run(self, args: list[str]) -> CommandResult:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {
                "REGISTRY_STORAGE_ROOT",
                "REGISTRY_GC_CONFIG_PATH",
                "REGISTRY_INTERNAL_URL",
            }
        }
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def registry_gc(self, *, delete_untagged: bool) -> CommandResult:
        command = [
            "registry",
            "garbage-collect",
            self._config_path,
        ]
        if delete_untagged:
            command.append("--delete-untagged=true")
        return self._run(command)


def _append_log(chunks: list[str], title: str, result: Optional[CommandResult] = None) -> None:
    lines = [title]
    if result is not None:
        lines.append(f"exit_code={result.returncode}")
        if result.stdout.strip():
            lines.append(result.stdout.strip())
        if result.stderr.strip():
            lines.append(result.stderr.strip())
    chunks.append("\n".join(lines))


def _record_audit_event(
    session: Session,
    *,
    actor: User,
    action: str,
    target_id: Optional[int] = None,
    metadata_json: Optional[dict] = None,
    retention_days: int = 30,
) -> None:
    prune_expired_logs(session, retention_days=retention_days)
    session.add(
        AuditEvent(
            actor_type="user",
            actor_id=actor.id,
            action=action,
            target_type="gc_job",
            target_id=target_id,
            metadata_json=metadata_json,
        )
    )
    session.commit()


class MaintenanceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        settings,
        runner_factory,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._runner_factory = runner_factory

    def storage_root(self) -> Path:
        return Path(self._settings.registry_storage_root)

    def current_storage_usage(self) -> int:
        return compute_storage_usage_bytes(self.storage_root())

    def refresh_storage_usage_snapshot(self, session: Session) -> dict[str, Optional[object]]:
        usage_bytes = self.current_storage_usage()
        measured_at = utcnow()
        record_storage_usage_snapshot(session, usage_bytes=usage_bytes, measured_at=measured_at)
        session.commit()
        return {"bytes": usage_bytes, "measured_at": measured_at}

    def minimum_gate_seconds(self) -> float:
        return max(float(getattr(self._settings, "maintenance_min_gate_seconds", 0.0)), 0.0)

    def log_retention_days(self) -> int:
        return self._settings.log_retention_days

    def has_active_job(self, session: Session) -> bool:
        active = session.scalar(
            select(GcJob).where(GcJob.status.in_(("queued", "running"))).order_by(GcJob.created_at.desc())
        )
        return active is not None

    def registry_gate_enabled(self, session: Session) -> bool:
        active = session.scalar(
            select(GcJob).where(
                GcJob.status.in_(("queued", "running")),
                GcJob.dry_run.is_(False),
            )
        )
        return active is not None

    def create_job(
        self,
        session: Session,
        *,
        actor: User,
        dry_run: bool,
        delete_untagged: bool,
        prune_empty_dirs: bool,
    ) -> GcJob:
        prune_expired_logs(session, retention_days=self._settings.log_retention_days)
        if self.has_active_job(session):
            raise ValueError("A garbage-collection job is already queued or running.")

        job = GcJob(
            status="queued",
            requested_by=actor.id,
            dry_run=dry_run,
            delete_untagged=delete_untagged,
            prune_empty_dirs=prune_empty_dirs,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        _record_audit_event(
            session,
            actor=actor,
            action="gc_job_requested",
            target_id=job.id,
            metadata_json={
                "dry_run": dry_run,
                "delete_untagged": delete_untagged,
                "prune_empty_dirs": prune_empty_dirs,
                "requested_by": actor.username,
            },
            retention_days=self._settings.log_retention_days,
        )
        return job

    def prune_logs(self, session: Session, *, actor: User) -> dict[str, int]:
        counts = prune_expired_logs(session, retention_days=self._settings.log_retention_days)
        counts.update(
            prune_expired_operational_records(
                session,
                web_session_retention_days=self._settings.web_session_retention_days,
                token_record_retention_days=self._settings.token_record_retention_days,
            )
        )
        _record_audit_event(
            session,
            actor=actor,
            action="logs_pruned",
            metadata_json={
                "retention_days": self._settings.log_retention_days,
                "web_session_retention_days": self._settings.web_session_retention_days,
                "token_record_retention_days": self._settings.token_record_retention_days,
                "audit_events_deleted": counts["audit_events_deleted"],
                "gc_jobs_deleted": counts["gc_jobs_deleted"],
                "web_sessions_deleted": counts["web_sessions_deleted"],
                "personal_access_tokens_deleted": counts["personal_access_tokens_deleted"],
                "robot_tokens_deleted": counts["robot_tokens_deleted"],
            },
            retention_days=self._settings.log_retention_days,
        )
        return counts

    def run_job(self, job_id: int) -> None:
        with self._session_factory() as session:
            job = session.get(GcJob, job_id)
            if job is None or job.status != "queued":
                return

            actor = session.get(User, job.requested_by)
            job.status = "running"
            job.started_at = utcnow()
            session.commit()
            _record_audit_event(
                session,
                actor=actor,
                action="gc_job_started",
                target_id=job.id,
                metadata_json={
                    "dry_run": job.dry_run,
                    "delete_untagged": job.delete_untagged,
                    "prune_empty_dirs": job.prune_empty_dirs,
                },
                retention_days=self._settings.log_retention_days,
            )

            runner = self._runner_factory()
            logs: list[str] = []
            bytes_before = self.current_storage_usage()
            job.bytes_before = bytes_before
            record_storage_usage_snapshot(session, usage_bytes=bytes_before, measured_at=utcnow())
            session.commit()

            try:
                if job.dry_run:
                    _append_log(
                        logs,
                        "Analysis only. No registry garbage collection command was executed in dry-run mode.",
                    )
                else:
                    gate_started = monotonic()
                    gc_result = runner.registry_gc(delete_untagged=job.delete_untagged)
                    _append_log(logs, "registry garbage-collect with maintenance gate enabled", gc_result)
                    if gc_result.returncode != 0:
                        raise RuntimeError("Registry garbage collection failed.")

                    if job.prune_empty_dirs:
                        deleted = prune_empty_directories(self.storage_root(), allowed_root=self.storage_root())
                        preview = ", ".join(deleted[:10]) if deleted else "no empty directories removed"
                        _append_log(logs, f"empty-directory pruning: {preview}")

                    remaining_gate_time = self.minimum_gate_seconds() - (monotonic() - gate_started)
                    if remaining_gate_time > 0:
                        sleep(remaining_gate_time)

                job.bytes_after = self.current_storage_usage()
                record_storage_usage_snapshot(session, usage_bytes=job.bytes_after, measured_at=utcnow())
                job.status = "succeeded"
                job.finished_at = utcnow()
                job.log_output = "\n\n".join(logs)
                session.commit()
                _record_audit_event(
                    session,
                    actor=actor,
                    action="gc_job_succeeded",
                    target_id=job.id,
                    metadata_json={
                        "dry_run": job.dry_run,
                        "delete_untagged": job.delete_untagged,
                        "prune_empty_dirs": job.prune_empty_dirs,
                        "bytes_before": job.bytes_before,
                        "bytes_after": job.bytes_after,
                    },
                    retention_days=self._settings.log_retention_days,
                )
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = utcnow()
                job.bytes_after = self.current_storage_usage()
                record_storage_usage_snapshot(session, usage_bytes=job.bytes_after, measured_at=utcnow())
                job.log_output = "\n\n".join(logs)
                session.commit()
                _record_audit_event(
                    session,
                    actor=actor,
                    action="gc_job_failed",
                    target_id=job.id,
                    metadata_json={
                        "dry_run": job.dry_run,
                        "delete_untagged": job.delete_untagged,
                        "prune_empty_dirs": job.prune_empty_dirs,
                        "bytes_before": job.bytes_before,
                        "bytes_after": job.bytes_after,
                        "error": str(exc),
                    },
                    retention_days=self._settings.log_retention_days,
                )

    def maintenance_summary(self, session: Session, *, page: int = 1, page_size: int = 10) -> dict:
        safe_page = max(page, 1)
        safe_page_size = max(page_size, 1)
        total_jobs = session.scalar(select(func.count()).select_from(GcJob)) or 0
        jobs = session.scalars(
            select(GcJob)
            .order_by(GcJob.created_at.desc())
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
        ).all()
        active_job = next((job for job in jobs if job.status in {"queued", "running"}), None)
        last_job = session.scalar(select(GcJob).order_by(GcJob.created_at.desc()).limit(1))
        storage_usage = read_storage_usage_snapshot(session)
        return {
            "registry_status": "maintenance" if self.registry_gate_enabled(session) else "running",
            "storage_usage_bytes": storage_usage["bytes"],
            "storage_usage_measured_at": storage_usage["measured_at"],
            "storage_usage_stale": storage_usage["stale"],
            "log_retention_days": self.log_retention_days(),
            "active_job": active_job,
            "last_job": last_job,
            "jobs": jobs,
            "pagination": {
                "page": safe_page,
                "page_size": safe_page_size,
                "total": total_jobs,
                "has_prev": safe_page > 1,
                "has_next": safe_page * safe_page_size < total_jobs,
            },
        }
