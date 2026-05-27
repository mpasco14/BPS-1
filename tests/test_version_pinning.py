from release_management.version_pinning import (
    build_release_version_manifest,
    build_version_pin,
    validate_version_manifest,
)


def test_validate_version_manifest_passes_required_kinds():
    manifest = build_release_version_manifest(
        release_version="1.0.0",
        pins=[
            build_version_pin(name="model", kind="model", version="m1"),
            build_version_pin(name="config", kind="config", version="c1"),
            build_version_pin(name="code", kind="code", version="1.0.0"),
        ],
    )

    report = validate_version_manifest(manifest)

    assert report.passed is True


def test_validate_version_manifest_blocks_missing_model():
    manifest = build_release_version_manifest(
        release_version="1.0.0",
        pins=[
            build_version_pin(name="config", kind="config", version="c1"),
            build_version_pin(name="code", kind="code", version="1.0.0"),
        ],
    )

    report = validate_version_manifest(manifest)

    assert report.passed is False
    assert "model" in report.missing_required_pins