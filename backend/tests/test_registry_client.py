import json

import httpx

from backend.auth.registry_tokens import bootstrap_signing_material
from backend.config import Settings
from backend.registry_client import RegistryClient


def _settings(temp_workspace) -> Settings:
    settings = Settings(
        app_env="development",
        database_url=f"sqlite:///{temp_workspace / 'test.db'}",
        registry_internal_url="http://registry:5000",
        registry_storage_root=str(temp_workspace / "registry-data"),
        compose_project_dir=str(temp_workspace),
        registry_service_name="registry",
        registry_gc_config_path="/etc/docker/registry/config.yml",
        token_issuer="sheldylew-registry",
        token_service="sheldylew-registry",
        token_ttl_seconds=900,
        public_registry_origin="http://localhost:8080",
        auth_private_key_path=str(temp_workspace / "auth-private.pem"),
        auth_public_cert_path=str(temp_workspace / "auth-cert.pem"),
        auth_bootstrap_marker_path=str(temp_workspace / "auth-bootstrap-complete"),
        internal_api_base_url="http://api:8000",
        admin_username="admin",
        admin_password="s3cret-pass",
        admin_email="admin@example.com",
    )
    bootstrap_signing_material(settings)
    return settings


def test_registry_client_handles_catalog_pagination(temp_workspace) -> None:
    settings = _settings(temp_workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/_catalog" and request.url.params.get("last") is None:
            return httpx.Response(
                200,
                headers={"Link": '</v2/_catalog?n=1&last=sheldylew/app>; rel="next"'},
                json={"repositories": ["sheldylew/app"]},
            )
        if request.url.path == "/v2/_catalog" and request.url.params.get("last") == "sheldylew/app":
            return httpx.Response(200, json={"repositories": ["sheldylew/worker"]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        repositories = client.list_repositories()
    finally:
        client.close()

    assert repositories == ["sheldylew/app", "sheldylew/worker"]


def test_registry_client_bounds_catalog_pages(temp_workspace) -> None:
    settings = _settings(temp_workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/_catalog" and request.url.params.get("last") is None:
            return httpx.Response(
                200,
                headers={"Link": '</v2/_catalog?n=1&last=sheldylew/app>; rel="next"'},
                json={"repositories": ["sheldylew/app"]},
            )
        if request.url.path == "/v2/_catalog" and request.url.params.get("last") == "sheldylew/app":
            return httpx.Response(200, json={"repositories": ["sheldylew/worker"]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        repositories, meta = client.list_repositories_bounded(max_pages=1)
    finally:
        client.close()

    assert repositories == ["sheldylew/app"]
    assert meta == {"truncated": True, "pages_fetched": 1}


def test_registry_client_reads_manifest_details(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": "sha256:config",
            "size": 101,
        },
        "layers": [
            {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": "sha256:a", "size": 1024},
            {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": "sha256:b", "size": 2048},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:manifest",
                    "Content-Type": "application/vnd.oci.image.manifest.v1+json",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/latest"):
            return httpx.Response(200, content=json.dumps(manifest_body), headers={"Content-Type": "application/json"})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:config"):
            return httpx.Response(
                200,
                json={
                    "created": "2026-05-04T10:20:30Z",
                    "architecture": "amd64",
                    "os": "linux",
                    "history": [{}, {}],
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        details = client.get_manifest_details("sheldylew/app", "latest")
    finally:
        client.close()

    assert details.digest == "sha256:manifest"
    assert details.config_digest == "sha256:config"
    assert details.total_size == 3173
    assert details.architectures == ["linux/amd64"]
    assert details.created_at == "2026-05-04T10:20:30Z"
    assert details.history_count == 2


def test_registry_client_resolves_manifest_descriptor_with_head_only(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "HEAD" and request.url.path.endswith("/manifests/latest"):
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:resolved",
                    "Content-Type": "application/vnd.oci.image.manifest.v1+json",
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        descriptor = client.resolve_manifest_descriptor("sheldylew/app", "latest")
    finally:
        client.close()

    assert descriptor.digest == "sha256:resolved"
    assert descriptor.media_type == "application/vnd.oci.image.manifest.v1+json"
    assert requests == [("HEAD", "/v2/sheldylew/app/manifests/latest")]


def test_registry_client_truncates_manifest_list_children(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_list_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:child-a", "size": 100, "platform": {"os": "linux", "architecture": "amd64"}},
            {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:child-b", "size": 200, "platform": {"os": "linux", "architecture": "arm64"}},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Docker-Content-Digest": "sha256:index", "Content-Type": "application/vnd.oci.image.index.v1+json"})
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json=manifest_list_body)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-a"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg-a"}})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-a"):
            return httpx.Response(200, json={"created": "2026-05-04T18:20:30Z", "os": "linux", "architecture": "amd64"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        details = client.get_manifest_details("sheldylew/app", "release", max_manifest_children=1)
    finally:
        client.close()

    assert details.children_truncated is True
    assert details.architectures == ["linux/amd64"]


def test_registry_client_uses_oldest_child_created_time_for_manifest_lists(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_list_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-amd64",
                "size": 1200,
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-arm64",
                "size": 1300,
                "platform": {"os": "linux", "architecture": "arm64"},
            },
        ],
    }

    child_manifest_amd64 = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": "sha256:cfg-amd64",
            "size": 101,
        },
        "layers": [],
    }
    child_manifest_arm64 = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": "sha256:cfg-arm64",
            "size": 101,
        },
        "layers": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:index",
                    "Content-Type": "application/vnd.oci.image.index.v1+json",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json=manifest_list_body)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-amd64"):
            return httpx.Response(200, json=child_manifest_amd64)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-arm64"):
            return httpx.Response(200, json=child_manifest_arm64)
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-amd64"):
            return httpx.Response(200, json={"created": "2026-05-04T18:20:30Z", "architecture": "amd64", "os": "linux"})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-arm64"):
            return httpx.Response(200, json={"created": "2026-05-03T09:15:00Z", "architecture": "arm64", "os": "linux"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        details = client.get_manifest_details("sheldylew/app", "release")
    finally:
        client.close()

    assert details.architectures == ["linux/amd64", "linux/arm64"]
    assert details.total_size == 2500
    assert details.created_at == "2026-05-03T09:15:00Z"
    assert details.history_count is None


def test_registry_client_reads_history_variants_for_manifest_lists(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_list_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-amd64",
                "size": 1200,
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-arm64",
                "size": 1300,
                "platform": {},
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json=manifest_list_body)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-amd64"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg-amd64"}})
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-arm64"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg-arm64"}})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-amd64"):
            return httpx.Response(200, json={"created": "2026-05-04T18:20:30Z", "os": "linux", "architecture": "amd64", "history": [{"created_by": "amd64 step"}]})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-arm64"):
            return httpx.Response(200, json={"created": "2026-05-03T09:15:00Z", "os": "linux", "architecture": "arm64", "history": [{"created_by": "arm64 step 1"}, {"created_by": "arm64 step 2"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        variants = client.get_tag_history("sheldylew/app", "release")
    finally:
        client.close()

    assert len(variants) == 2
    assert variants[0].platform == "linux/amd64"
    assert len(variants[0].entries) == 1
    assert variants[1].platform == "linux/arm64"
    assert len(variants[1].entries) == 2


def test_registry_client_truncates_history_entries(temp_workspace) -> None:
    settings = _settings(temp_workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg"}})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg"):
            return httpx.Response(
                200,
                json={
                    "created": "2026-05-04T18:20:30Z",
                    "os": "linux",
                    "architecture": "amd64",
                    "history": [{"created_by": "one"}, {"created_by": "two"}],
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        variants, meta = client.get_tag_history_bounded(
            "sheldylew/app",
            "release",
            max_history_entries=1,
        )
    finally:
        client.close()

    assert meta["truncated"] is False
    assert len(variants[0].entries) == 1
    assert variants[0].history_truncated is True


def test_registry_client_uses_child_config_platform_when_manifest_list_platform_missing(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_list_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-a",
                "size": 1200,
                "platform": {},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:index",
                    "Content-Type": "application/vnd.oci.image.index.v1+json",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json=manifest_list_body)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-a"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg-a"}})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-a"):
            return httpx.Response(200, json={"created": "2026-05-04T18:20:30Z", "os": "linux", "architecture": "arm64"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        details = client.get_manifest_details("sheldylew/app", "release")
        variants = client.get_tag_history("sheldylew/app", "release")
    finally:
        client.close()

    assert details.architectures == ["linux/arm64"]
    assert variants[0].platform == "linux/arm64"


def test_registry_client_skips_tags_that_disappear_mid_enumeration(temp_workspace) -> None:
    settings = _settings(temp_workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/tags/list"):
            return httpx.Response(200, json={"tags": ["latest", "gone"]})
        if request.method == "HEAD" and request.url.path.endswith("/manifests/latest"):
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:latest",
                    "Content-Type": "application/vnd.oci.image.manifest.v1+json",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/latest"):
            return httpx.Response(
                200,
                json={
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": {"digest": "sha256:cfg-latest", "size": 10},
                    "layers": [],
                },
            )
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-latest"):
            return httpx.Response(200, json={"created": "2026-05-04T10:20:30Z", "os": "linux", "architecture": "amd64"})
        if request.method in {"HEAD", "GET"} and request.url.path.endswith("/manifests/gone"):
            return httpx.Response(404, json={"errors": [{"code": "MANIFEST_UNKNOWN"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        summaries = client.list_tag_summaries("sheldylew/app")
    finally:
        client.close()

    assert [summary.tag for summary in summaries] == ["latest"]


def test_registry_client_skips_missing_child_variants_for_manifest_lists(temp_workspace) -> None:
    settings = _settings(temp_workspace)
    manifest_list_body = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-amd64",
                "size": 1200,
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:child-gone",
                "size": 1300,
                "platform": {"os": "linux", "architecture": "arm64"},
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(
                200,
                headers={
                    "Docker-Content-Digest": "sha256:index",
                    "Content-Type": "application/vnd.oci.image.index.v1+json",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/release"):
            return httpx.Response(200, json=manifest_list_body)
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-amd64"):
            return httpx.Response(200, json={"config": {"digest": "sha256:cfg-amd64"}})
        if request.method == "GET" and request.url.path.endswith("/blobs/sha256:cfg-amd64"):
            return httpx.Response(
                200,
                json={"created": "2026-05-04T18:20:30Z", "os": "linux", "architecture": "amd64", "history": [{"created_by": "amd64 step"}]},
            )
        if request.method == "GET" and request.url.path.endswith("/manifests/sha256:child-gone"):
            return httpx.Response(404, json={"errors": [{"code": "MANIFEST_UNKNOWN"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = RegistryClient(settings=settings, transport=httpx.MockTransport(handler))
    try:
        details = client.get_manifest_details("sheldylew/app", "release")
        variants = client.get_tag_history("sheldylew/app", "release")
    finally:
        client.close()

    assert details.architectures == ["linux/amd64"]
    assert details.created_at == "2026-05-04T18:20:30Z"
    assert [variant.platform for variant in variants] == ["linux/amd64"]
