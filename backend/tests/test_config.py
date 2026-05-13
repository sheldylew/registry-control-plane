from backend.config import load_settings


def test_load_settings_prefers_image_build_info_file_over_stale_env(monkeypatch, tmp_path):
    build_info_path = tmp_path / "build-info.env"
    build_info_path.write_text(
        "\n".join(
            [
                "APP_VERSION=file-version",
                "APP_REVISION=file-revision",
                "APP_BUILD_TIME=2026-05-13T00:00:00Z",
                "APP_IMAGE_TAG=file-tag",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_BUILD_INFO_PATH", str(build_info_path))
    monkeypatch.setenv("APP_VERSION", "stale-env-version")
    monkeypatch.setenv("APP_REVISION", "stale-env-revision")
    monkeypatch.setenv("APP_BUILD_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("APP_IMAGE_TAG", "stale-env-tag")

    settings = load_settings()

    assert settings.app_version == "file-version"
    assert settings.app_revision == "file-revision"
    assert settings.app_build_time == "2026-05-13T00:00:00Z"
    assert settings.app_image_tag == "file-tag"


def test_load_settings_tolerates_missing_build_info(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_BUILD_INFO_PATH", str(tmp_path / "missing-build-info.env"))
    for name in ("APP_VERSION", "APP_REVISION", "REVISION", "APP_BUILD_TIME", "APP_IMAGE_TAG"):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.app_version
    assert settings.app_revision == "dev"
    assert settings.app_build_time is None
    assert settings.app_image_tag is None
