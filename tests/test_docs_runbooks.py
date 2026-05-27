from pathlib import Path


DOCS = {
    "docs/ARCHITECTURE.md": [
        "Architecture Overview",
        "Segurança antes de lucro",
        "Live bloqueado por padrão",
        "Fluxo live controlado",
    ],
    "docs/LOCAL_SETUP_RUNBOOK.md": [
        "Local Setup Runbook",
        "BINANCE_EXECUTION_MODE=paper",
        "python -m pytest",
        "live trading desabilitado",
    ],
    "docs/PAPER_TESTNET_RUNBOOK.md": [
        "Paper & Testnet Runbook",
        "paper",
        "testnet",
        "Critérios para sair de paper/testnet",
    ],
    "docs/CONTROLLED_LIVE_ACTIVATION_RUNBOOK.md": [
        "Controlled Live Activation Runbook",
        "I_APPROVE_CONTROLLED_LIVE_ACTIVATION",
        "I_ACCEPT_LIVE_RISK",
        "não significa aumentar capital automaticamente",
    ],
    "docs/EMERGENCY_SHUTDOWN_RUNBOOK.md": [
        "Emergency Shutdown Runbook",
        "Ativar kill switch",
        "Bloquear novas ordens",
        "Não tentar “recuperar prejuízo”",
    ],
    "docs/WEEKLY_AUDIT_RUNBOOK.md": [
        "Weekly Audit Runbook",
        "python -m pytest",
        "Auditoria semanal",
        "documentação atualizada",
    ],
    "docs/README.md": [
        "Documentation Index",
        "Live trading must remain disabled by default",
    ],
}


def test_required_docs_exist():
    for path in DOCS:
        assert Path(path).exists(), f"Missing documentation file: {path}"


def test_required_docs_contain_critical_sections():
    for path, required_terms in DOCS.items():
        content = Path(path).read_text(encoding="utf-8")

        for term in required_terms:
            assert term in content, f"Missing term {term!r} in {path}"