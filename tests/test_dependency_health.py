from infra.dependency_health import (
    DependencyProbeResult,
    build_dependency_health_report,
    export_dependency_health_report,
)


def test_dependency_health_passes_when_critical_ok():
    report = build_dependency_health_report(
        probe_results=[
            DependencyProbeResult(
                name="filesystem",
                kind="filesystem",
                critical=True,
                status="PASS",
                message="ok",
            )
        ]
    )

    assert report.passed is True
    assert report.status == "PASS"


def test_dependency_health_blocks_critical_failure():
    report = build_dependency_health_report(
        probe_results=[
            DependencyProbeResult(
                name="redis",
                kind="redis",
                critical=True,
                status="FAIL",
                message="down",
            )
        ]
    )

    assert report.passed is False
    assert "redis" in report.blockers


def test_export_dependency_health_report(tmp_path):
    report = build_dependency_health_report(
        probe_results=[
            DependencyProbeResult(
                name="fs",
                kind="filesystem",
                critical=True,
                status="PASS",
                message="ok",
            )
        ]
    )

    path = export_dependency_health_report(report, output_dir=tmp_path, name="unit_dependency_health")

    assert path.exists()