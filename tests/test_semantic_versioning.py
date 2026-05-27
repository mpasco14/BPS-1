from release_management.semantic_versioning import (
    bump_semantic_version,
    evaluate_version_policy,
    parse_semantic_version,
)


def test_parse_semantic_version():
    version = parse_semantic_version("1.2.3-rc.1+build.5")

    assert version.major == 1
    assert version.minor == 2
    assert version.patch == 3
    assert version.prerelease == "rc.1"
    assert version.build == "build.5"


def test_bump_patch():
    assert bump_semantic_version("1.2.3", "patch") == "1.2.4"


def test_evaluate_version_policy_blocks_invalid():
    report = evaluate_version_policy(current_version="invalid")

    assert report.valid is False
    assert "invalid_semantic_version" in report.blockers