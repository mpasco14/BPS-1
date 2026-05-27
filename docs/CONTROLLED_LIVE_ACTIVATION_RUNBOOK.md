# Controlled Live Activation Runbook

## Objetivo

Ativar micro-live de forma controlada, com capital mínimo, gates obrigatórios e aprovação humana.

Este runbook não autoriza aumento automático de capital.

---

## 1. Pré-condições obrigatórias

Antes de qualquer live real:

- [ ] `python -m pytest` passando
- [ ] paper trading validado
- [ ] testnet validado
- [ ] backtest com custos validado
- [ ] calibration report revisado
- [ ] strategy health aceitável
- [ ] risk audit aprovado
- [ ] secrets audit aprovado
- [ ] emergency stop test aprovado
- [ ] production guard aprovado
- [ ] human approval válido

---

## 2. Configurações padrão antes de ativação

Antes da aprovação final, o `.env` deve manter:

```env
LIVE_ORDER_ADAPTER_ENABLED=false
LIVE_ORDER_ADAPTER_DRY_RUN=true
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=false
RUNTIME_CONFIG_ALLOW_LIVE=false
```

---

## 3. Rodar validação de infraestrutura

```powershell
python scripts\run_infra_health_check.py --export --name pre_live_dependency_health
python scripts\run_runtime_config_validation.py --export --name pre_live_runtime_config
python scripts\run_failure_injection.py --export --name pre_live_failure_injection
```

Critério:

```txt
nenhum blocker crítico
```

---

## 4. Rodar validação de segurança

```powershell
python -u scripts\run_security_audit.py --export --scan-root .
```

Critério:

```txt
nenhum segredo real versionado
nenhuma permissão de saque
nenhuma permissão de transferência
chaves dentro do prazo de rotação
```

---

## 5. Rodar production readiness demo

```powershell
python scripts\run_production_readiness_demo.py
```

Critério esperado:

```txt
secrets.passed = true
approval.valid = true
emergency.passed = true
production_guard.passed = true
live_order_adapter.status = BLOCKED ou DRY_RUN
```

`BLOCKED` é aceitável se `allow_submission=false`.

---

## 6. Aprovação humana

A aprovação humana precisa conter frase explícita:

```txt
I_APPROVE_CONTROLLED_LIVE_ACTIVATION
```

A ordem real exige frase separada:

```txt
I_ACCEPT_LIVE_RISK
```

Essas frases existem para reduzir risco de ativação acidental.

---

## 7. Ativação micro-live

Somente após todos os gates:

```env
RUNTIME_CONFIG_ALLOW_LIVE=true

LIVE_ORDER_ADAPTER_ENABLED=true
LIVE_ORDER_ADAPTER_DRY_RUN=false
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=true

BINANCE_EXECUTION_MODE=live
BINANCE_ALLOW_LIVE_TRADING=true
RISK_ALLOW_LIVE_TRADING=true
```

Ativar somente com capital mínimo.

---

## 8. Limites iniciais recomendados

```txt
max margin por trade: baixo
max notional por trade: baixo
max open positions: 1
max daily loss: pequeno
max leverage: conforme risk manager, sem elevar manualmente
```

Nunca começar com capital completo.

---

## 9. Durante a sessão

Monitorar:

- PnL
- drawdown
- open orders
- open positions
- fill rate
- rejection rate
- slippage
- latency
- risk blockers
- kill switch
- model drift
- OOD rate
- regime atual

---

## 10. Pós-sessão

Rodar:

```powershell
python scripts\run_live_performance_analyzer.py --export --name post_live_performance
python scripts\run_live_risk_audit.py --export --name post_live_risk_audit
python scripts\run_live_capital_ramp_validation.py --export --name post_live_capital_ramp
python scripts\run_live_drift_monitor.py --export --name post_live_drift
python scripts\run_regime_optimization.py --export --name post_live_regime
```

---

## 11. Critérios para continuar no mesmo nível

Continuar micro-live apenas se:

- [ ] sem violation crítica
- [ ] sem saque/transferência nas permissões
- [ ] fill rate aceitável
- [ ] rejection rate baixa
- [ ] slippage dentro do limite
- [ ] drawdown dentro do limite
- [ ] drift aceitável
- [ ] regime não bloqueado
- [ ] capital ramp recomenda HOLD_LEVEL ou ADVANCE_RECOMMENDED

---

## 12. Critérios para pausar live

Pausar se:

- critical risk finding
- production guard failure
- OOD rate alto
- model drift crítico
- rejection rate alto
- API errors persistentes
- WebSocket instável
- drawdown acima do limite
- kill switch ativado
- segredo exposto
- dúvida operacional

---

## 13. Regra final

ADVANCE_RECOMMENDED não significa aumentar capital automaticamente.  
Qualquer aumento de capital exige nova revisão manual e novo ciclo de validação.