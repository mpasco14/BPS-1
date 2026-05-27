# Local Setup Runbook

## Objetivo

Preparar o ambiente local do BTC Binance Futures Bot para desenvolvimento, testes, paper trading e testnet.

Este runbook não ativa live trading.

---

## 1. Pré-requisitos

- Python 3.12+
- Git
- PowerShell
- Ambiente virtual `.venv`
- Conta Binance para testnet, se aplicável

---

## 2. Clonar o projeto

```powershell
git clone <repo-url>
cd btc-polymarket-bot
```

---

## 3. Criar ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Validar:

```powershell
python --version
pip --version
```

---

## 4. Instalar dependências

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se houver dependências opcionais para gráficos:

```powershell
pip install matplotlib
```

---

## 5. Criar arquivo `.env`

Copie o exemplo:

```powershell
Copy-Item .env.example .env
```

Importante:

- Nunca commitar `.env`
- Nunca commitar API keys
- Nunca salvar chaves reais em arquivos versionados

---

## 6. Configurações seguras padrão

Confirme no `.env`:

```env
BINANCE_EXECUTION_MODE=paper
BINANCE_ALLOW_LIVE_TRADING=false
RISK_ALLOW_LIVE_TRADING=false

LIVE_ORDER_ADAPTER_ENABLED=false
LIVE_ORDER_ADAPTER_DRY_RUN=true
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=false

RUNTIME_CONFIG_ALLOW_LIVE=false
PRODUCTION_GUARD_ENABLED=true
```

---

## 7. Validar imports principais

```powershell
python -c "from infra.runtime_config_validator import validate_runtime_config; print(validate_runtime_config().status)"
python -c "from observability.metrics_registry import build_metrics_snapshot; print('metrics OK')"
python -c "from security.environment_policy import evaluate_environment_policy; print(evaluate_environment_policy().status)"
```

---

## 8. Rodar testes

Rodar pacote completo:

```powershell
python -m pytest
```

Critério mínimo:

```txt
todos os testes precisam passar
```

---

## 9. Rodar validações de infraestrutura

```powershell
python scripts\run_infra_health_check.py --export --name dependency_health_local
python scripts\run_runtime_config_validation.py --export --name runtime_config_local
python scripts\run_failure_injection.py --export --name failure_injection_local
```

---

## 10. Rodar auditoria de segurança local

```powershell
python -u scripts\run_security_audit.py --export --scan-root security
```

Para escanear o projeto todo:

```powershell
python -u scripts\run_security_audit.py --export --scan-root .
```

Se o comando retornar código 1, revisar o relatório antes de prosseguir.

---

## 11. Checklist de ambiente local

Antes de desenvolver:

- [ ] `.venv` ativo
- [ ] `.env` criado
- [ ] live trading desabilitado
- [ ] dry run habilitado
- [ ] testes passando
- [ ] runtime config sem blockers
- [ ] secret scanner sem vazamento real
- [ ] git limpo antes de iniciar nova fase

---

## 12. Comandos Git recomendados

Antes de começar:

```powershell
git status
git pull origin main
```

Depois de concluir:

```powershell
git status
git add <arquivos>
git commit -m "<mensagem>"
git push origin main
git status
```

---

## 13. Regra de segurança

Ambiente local é para desenvolvimento, paper trading e testnet.  
Não usar capital real a partir do ambiente local sem seguir o Controlled Live Activation Runbook.