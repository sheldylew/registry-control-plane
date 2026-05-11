import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi import Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.audit import record_audit_event
from backend.api.routes import router as api_router
from backend.auth.registry_tokens import build_registry_token_response, parse_basic_credentials, require_signing_material
from backend.bootstrap import bootstrap_admin
from backend.config import Settings, load_settings
from backend.db import make_engine, make_session_factory
from backend.maintenance import LocalRegistryMaintenanceRunner, MaintenanceService
from backend.metrics import increment as increment_metric
from backend.metrics import render_prometheus_text
from backend.log_retention import prune_expired_logs, prune_expired_operational_records
from backend.models import Base
from backend.rate_limit import FixedWindowRateLimiter
from backend.registry_client import RegistryClient
from backend.registry_state import queue_automatic_rebuild_job, run_registry_state_rebuild_job
from backend.runtime_secrets import ensure_registry_notifications_token
from backend.setup import (
    automatic_registry_state_rebuild_enabled,
    complete_setup_from_environment,
    render_registry_config_to_path,
    saved_public_registry_origin,
    setup_required,
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _token_rate_limit_key(request: Request) -> str:
    username = "anonymous"
    try:
        username, _ = parse_basic_credentials(request.headers.get("Authorization"))
    except HTTPException:
        pass
    return f"{_client_ip(request)}:{username.casefold()}"


def create_app(app_settings: Optional[Settings] = None) -> FastAPI:
    settings = app_settings or load_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        require_signing_material(settings)
        Base.metadata.create_all(engine)
        with session_factory() as session:
            complete_setup_from_environment(session, settings)
            if not setup_required(session):
                bootstrap_admin(session, settings)
            app_public_origin = saved_public_registry_origin(session) or settings.public_registry_origin
            if not setup_required(session):
                render_registry_config_to_path(settings, public_registry_origin=app_public_origin)
            prune_expired_logs(session, retention_days=settings.log_retention_days)
            prune_expired_operational_records(
                session,
                web_session_retention_days=settings.web_session_retention_days,
                token_record_retention_days=settings.token_record_retention_days,
            )

        app.state.settings = settings
        app.state.public_registry_origin = app_public_origin
        app.state.registry_notifications_token = ensure_registry_notifications_token(settings)
        app.state.engine = engine
        app.state.session_factory = session_factory
        if not hasattr(app.state, "registry_client_factory"):
            app.state.registry_client_factory = lambda: RegistryClient(settings=settings)
        if not hasattr(app.state, "maintenance_auto_run"):
            app.state.maintenance_auto_run = True
        if not hasattr(app.state, "maintenance_service_factory"):
            app.state.maintenance_service_factory = lambda: MaintenanceService(
                session_factory=session_factory,
                settings=settings,
                runner_factory=lambda: LocalRegistryMaintenanceRunner(
                    registry_gc_config_path=settings.registry_gc_config_path,
                ),
            )
        if not hasattr(app.state, "login_rate_limiter"):
            app.state.login_rate_limiter = FixedWindowRateLimiter(
                max_attempts=settings.login_rate_limit_attempts,
                window_seconds=settings.login_rate_limit_window_seconds,
            )
        if not hasattr(app.state, "auth_token_rate_limiter"):
            app.state.auth_token_rate_limiter = FixedWindowRateLimiter(
                max_attempts=settings.auth_token_rate_limit_attempts,
                window_seconds=settings.auth_token_rate_limit_window_seconds,
            )
        if not hasattr(app.state, "setup_rate_limiter"):
            app.state.setup_rate_limiter = FixedWindowRateLimiter(
                max_attempts=settings.setup_rate_limit_attempts,
                window_seconds=settings.setup_rate_limit_window_seconds,
            )

        auto_rebuild_job_id = None
        with session_factory() as session:
            if not setup_required(session) and automatic_registry_state_rebuild_enabled(session):
                auto_rebuild_job = queue_automatic_rebuild_job(
                    session,
                    retention_days=settings.log_retention_days,
                )
                auto_rebuild_job_id = auto_rebuild_job.id if auto_rebuild_job is not None else None
        if auto_rebuild_job_id is not None and app.state.maintenance_auto_run:
            asyncio.create_task(
                asyncio.to_thread(
                    run_registry_state_rebuild_job,
                    session_factory,
                    app.state.registry_client_factory,
                    settings,
                    auto_rebuild_job_id,
                )
            )
        yield

    app = FastAPI(title="Registry Control Plane API", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(render_prometheus_text(), media_type="text/plain; version=0.0.4")

    @app.get("/auth/token")
    async def auth_token(
        request: Request,
        service: str,
        scope: list[str] = Query(default=[]),
        account: Optional[str] = None,
    ) -> JSONResponse:
        _ = account
        with session_factory() as session:
            if setup_required(session):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Setup must be completed before registry authentication is available.",
                )
        rate_limit_key = _token_rate_limit_key(request)
        rate_limiter = request.app.state.auth_token_rate_limiter
        retry_after = rate_limiter.retry_after(rate_limit_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        with session_factory() as session:
            increment_metric("registry_auth_token_requests_total")
            try:
                result = build_registry_token_response(
                    session,
                    settings=settings,
                    authorization=request.headers.get("Authorization"),
                    service=service,
                    scope_values=scope,
                )
            except Exception as exc:
                if getattr(exc, "status_code", None) == status.HTTP_401_UNAUTHORIZED:
                    rate_limiter.add_failure(rate_limit_key)
                increment_metric("registry_auth_token_denied_total")
                record_audit_event(
                    session,
                    action="registry_token_denied",
                    actor_type="registry_client",
                    metadata_json={
                        "requested_scope": scope,
                        "service": service,
                        "source_ip": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent"),
                        "detail": getattr(exc, "detail", str(exc)),
                    },
                    retention_days=settings.log_retention_days,
                )
                raise
            rate_limiter.reset(rate_limit_key)

            granted_actions = 0
            denied_actions = 0
            granted_scope_payload: list[dict] = []
            for requested, granted in zip(result.requested_scopes, result.granted_access):
                granted_actions += len(granted.actions)
                denied_actions += max(0, len(requested.actions) - len(granted.actions))
                granted_scope_payload.append(
                    {
                        "type": granted.resource_type,
                        "name": granted.resource_name,
                        "actions": list(granted.actions),
                    }
                )
            increment_metric("registry_auth_scope_grants_total", granted_actions)
            increment_metric("registry_auth_scope_denials_total", denied_actions)
            if result.subject.subject_type == "anonymous" and granted_actions > 0:
                increment_metric("registry_public_pull_tokens_issued_total")

            record_audit_event(
                session,
                action="registry_token_issued",
                actor_type=result.subject.subject_type,
                actor_id=result.subject.subject_id,
                target_type="registry_token",
                metadata_json={
                    "actor": result.subject.subject_name,
                    "requested_scope": scope,
                    "granted_scope": granted_scope_payload,
                    "source_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                },
                retention_days=settings.log_retention_days,
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content=result.payload)

    app.include_router(api_router)

    return app


app = create_app()
