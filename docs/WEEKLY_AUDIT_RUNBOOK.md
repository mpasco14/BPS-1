# Weekly Audit Runbook

## Objetivo

Realizar auditoria semanal do sistema para validar segurança, risco, performance, drift, sentimento, regimes e documentação operacional.

---

## 1. Frequência

Executar semanalmente, mesmo sem live real.

Frequência mínima:

```txt
1 vez por semana
```

Executar também após:

- mudanças grandes no código
- alteração de thresholds
- troca de modelo
- alteração de API keys
- sessão micro-live
- incidente
- queda de performance

---

## 2. Preparação

Antes de começar:

```powershell
git status
git pull origin main
```

Ativar ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 3. Testes completos

```powershell
python -m pytest
```

Critério:

```txt
todos os testes devem passar
```

---

## 4. Infraestrutura

```powershell
python scripts\run_infra_health_check.py --export --name weekly_dependency_health
python scripts\run_runtime_config_validation.py --export --name weekly_runtime_config
python scripts\run_failure_injection.py --export --name weekly_failure_injection
```

Revisar:

```txt
artifacts/infra/
```

---

## 5. Segurança

```powershell
python -u scripts\run_security_audit.py --export --scan-root .
```

Revisar:

```txt
artifacts/security/
```

Critérios:

- nenhum segredo real versionado
- nenhuma permissão de saque
- nenhuma permissão de transferência
- rotação de chaves dentro do prazo
- environment policy sem blockers

---

## 6. Observabilidade

```powershell
python scripts\run_metrics_snapshot.py --export
python scripts\run_prometheus_exporter.py --export
python scripts\run_observability_alerts.py --export
python scripts\run_grafana_dashboard_export.py
python scripts\run_incident_report.py --export
```

O relatório de incidente pode retornar código 1 se houver alerta proposital ou incidente ativo.

Revisar:

```txt
artifacts/observability/
```

---

## 7. Performance live/paper/testnet

```powershell
python scripts\run_live_performance_analyzer.py --demo --export --session-name weekly_demo
python scripts\run_live_risk_audit.py --demo --export --session-name weekly_demo
python scripts\run_live_capital_ramp_validation.py --export --name weekly_capital_ramp
```

Revisar:

- fill rate
- rejection rate
- slippage
- latency
- drawdown
- risk findings
- capital ramp action

---

## 8. Modelo e drift

```powershell
python scripts\run_live_drift_monitor.py --demo --export --name weekly_drift
python scripts\evaluate_model_calibration.py --demo --name weekly_calibration
```

Revisar:

- Brier Score
- ECE
- confidence gap
- OOD rate
- high confidence win rate

---

## 9. Regime

```powershell
python scripts\run_regime_optimization.py --demo --export --name weekly_regime
```

Revisar:

- regimes bloqueados
- regimes com exposição reduzida
- regimes que exigem maior confiança
- regimes que precisam de mais dados

---

## 10. Sentimento

```powershell
python scripts\run_sentiment_dashboard_snapshot.py --export --name weekly_sentiment_dashboard
python scripts\run_sentiment_backtest.py --export --name weekly_sentiment_backtest
python scripts\run_sentiment_integration_demo.py --export --name weekly_sentiment_integration
```

Revisar:

- sentiment index
- fear and greed
- confidence
- panic score
- euphoria score
- sentiment no-trade blockers
- sentiment strategy health

---

## 11. Produção e live readiness

```powershell
python scripts\run_production_readiness_demo.py
```

Critério:

```txt
production guard precisa passar apenas em cenário controlado
live order adapter não deve submeter ordem real por padrão
```

---

## 12. Checklist semanal

- [ ] testes completos passando
- [ ] dependency health sem blocker
- [ ] runtime config seguro
- [ ] failure injection seguro
- [ ] secret scanner sem segredo real
- [ ] API permissions sem saque/transferência
- [ ] key rotation dentro do prazo
- [ ] observability sem alerta crítico real
- [ ] incident report revisado
- [ ] drift aceitável
- [ ] regime optimization revisado
- [ ] sentiment health revisado
- [ ] live risk audit sem finding crítico
- [ ] capital ramp não aumentou capital automaticamente
- [ ] documentação atualizada

---

## 13. Registro da auditoria

Registrar manualmente:

```txt
Data:
Responsável:
Commit hash:
Resultado dos testes:
Principais alertas:
Ações tomadas:
Próxima revisão:
```

---

## 14. Regra final

Auditoria semanal existe para prevenir degradação silenciosa.  
Se algo parecer estranho, pausar live/testnet e investigar antes de continuar.