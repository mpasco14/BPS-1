# Paper & Testnet Runbook

## Objetivo

Executar o sistema sem capital real para validar sinais, risco, execução simulada, testnet e observabilidade.

---

## 1. Modos permitidos

```txt
paper
testnet
```

Modo proibido nesta etapa:

```txt
live
```

---

## 2. Configuração paper trading

No `.env`:

```env
BINANCE_EXECUTION_MODE=paper
BINANCE_ALLOW_LIVE_TRADING=false
RISK_ALLOW_LIVE_TRADING=false

LIVE_ORDER_ADAPTER_ENABLED=false
LIVE_ORDER_ADAPTER_DRY_RUN=true
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=false
```

---

## 3. Rodar paper trading demo

```powershell
python scripts\run_paper_trading_session.py --demo --session-name paper_demo
```

Validar arquivos:

```powershell
Test-Path artifacts\paper_trading\paper_demo_summary.json
Test-Path artifacts\paper_trading\paper_demo_trades.jsonl
```

---

## 4. Rodar backtest com custos

```powershell
python scripts\run_backtest_with_costs.py --demo --name backtest_costs_demo
```

Validar:

```powershell
Test-Path artifacts\backtesting\backtest_costs_demo.json
```

---

## 5. Rodar calibração do modelo

```powershell
python scripts\evaluate_model_calibration.py --demo --name calibration_demo
```

Com plot, apenas se matplotlib estiver instalado:

```powershell
python scripts\evaluate_model_calibration.py --demo --name calibration_demo_plot --plot
```

---

## 6. Rodar sentimento

```powershell
python scripts\run_sentiment_dashboard_snapshot.py --export --name sentiment_dashboard_demo
python scripts\run_sentiment_backtest.py --export --name sentiment_backtest_demo
```

---

## 7. Configuração testnet

No `.env`:

```env
BINANCE_EXECUTION_MODE=testnet
BINANCE_ALLOW_LIVE_TRADING=false
RISK_ALLOW_LIVE_TRADING=false
```

Chaves testnet devem ser usadas apenas em testnet.

---

## 8. Validar readiness testnet

```powershell
python scripts\run_testnet_connection_check.py
```

Critério:

```txt
testnet client deve estar configurado
nenhuma chave real deve ser usada
nenhum modo live deve estar ativo
```

---

## 9. Rodar loop testnet controlado

```powershell
python scripts\run_testnet_session.py --dry-run --session-name testnet_demo
```

Se houver script continuous runner:

```powershell
python scripts\run_testnet_continuous.py --dry-run --max-cycles 3
```

---

## 10. Métricas obrigatórias

Depois de paper/testnet, analisar:

- fill rate
- rejection rate
- cancel rate
- slippage estimado vs realizado
- latency
- net PnL
- max drawdown
- risk blockers
- no-trade blockers
- model drift
- regime performance

---

## 11. Comandos de auditoria pós-sessão

```powershell
python scripts\run_live_session_recorder_demo.py --export --session-name live_micro_demo
python scripts\run_live_performance_analyzer.py --demo --export --session-name live_micro_demo
python scripts\run_live_risk_audit.py --demo --export --session-name live_micro_demo
python scripts\run_live_capital_ramp_validation.py --export --name live_capital_ramp_validation_demo
python scripts\run_live_drift_monitor.py --demo --export --name live_drift_demo
python scripts\run_regime_optimization.py --demo --export --name regime_optimization_demo
```

---

## 12. Critérios para sair de paper/testnet

Antes de considerar micro-live:

- [ ] testes completos passando
- [ ] paper trading positivo com custos
- [ ] testnet sem erro crítico
- [ ] runtime config aprovado
- [ ] risk audit aprovado
- [ ] model drift aceitável
- [ ] regime optimization sem regimes críticos ignorados
- [ ] secret scanner sem vazamento real
- [ ] production guard ainda bloqueando live por padrão

---

## 13. Regra final

Paper e testnet servem para provar estabilidade operacional.  
Eles não provam rentabilidade futura com capital real.