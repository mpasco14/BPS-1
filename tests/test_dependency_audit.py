from security.dependency_audit import (
    DependencySecurityAuditConfig,
    DependencyVulnerability,
    build_dependency_security_audit_report,
    vulnerabilities_from_pip_audit_json,
)


def test_dependency_audit_passes_no_vulnerabilities():
    report = build_dependency_security_audit_report(vulnerabilities=[])

    assert report.passed is True
    assert report.vulnerabilities_count == 0


def test_dependency_audit_blocks_high_vulnerability():
    report = build_dependency_security_audit_report(
        vulnerabilities=[
            DependencyVulnerability(
                package="badpkg",
                vulnerability_id="CVE-UNIT",
                severity="HIGH",
            )
        ],
        config=DependencySecurityAuditConfig(fail_on_high=True, max_high=0),
    )

    assert report.passed is False
    assert "high_vulnerabilities_above_limit" in report.blockers


def test_parse_pip_audit_json():
    payload = {
        "dependencies": [
            {
                "name": "pkg",
                "version": "1.0",
                "vulns": [
                    {
                        "id": "CVE-1",
                        "severity": "HIGH",
                        "fix_versions": ["1.1"],
                    }
                ],
            }
        ]
    }

    vulns = vulnerabilities_from_pip_audit_json(payload)

    assert len(vulns) == 1
    assert vulns[0].package == "pkg"
    assert vulns[0].severity == "HIGH"