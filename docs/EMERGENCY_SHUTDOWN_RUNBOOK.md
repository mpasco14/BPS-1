# Emergency Shutdown Runbook

## Objetivo

Executar parada segura em caso de falha, risco elevado, comportamento inesperado, erro de API, vazamento de segredo ou perda de controle operacional.

---

## 1. Quando acionar emergência

Acionar imediatamente se ocorrer:

- kill switch ativado
- drawdown acima do limite
- ordem real inesperada
- posição aberta inesperada
- API key exposta
- WebSocket desconectado em momento crítico
- Binance REST retornando erros persistentes
- rejection rate anormal
- modelo retornando NaN
- OOD rate alto
- production guard falhando
- human approval inválido
- suspeita de invasão ou vazamento

---

## 2. Procedimento imediato

Sequência obrigatória:

```txt
1. Ativar kill switch
2. Bloquear novas ordens
3. Cancelar ordens abertas
4. Entrar em safe mode
5. Notificar operador
6. Reconciliar posições abertas
7. Registrar incidente
8. Rodar auditorias
```

---

## 3. Reverter flags live

No `.env`, voltar para:

```env
BINANCE_EXECUTION_MODE=paper
BINANCE_ALLOW_LIVE_TRADING=false
RISK_ALLOW_LIVE_TRADING=false

LIVE_ORDER_ADAPTER_ENABLED=false
LIVE_ORDER_ADAPTER_DRY_RUN=true
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=false

RUNTIME_CONFIG_ALLOW_LIVE=false
```

---

## 4. Testar procedimento de emergência

```powershell
python scripts\run_production_readiness_demo.py
```

E validar diretamente:

```powershell
python -c "from ops.emergency_stop_procedure_test import EmergencyStopProcedureInputs, build_emergency_stop_procedure_report; r=build_emergency_stop_procedure_report(inputs=EmergencyStopProcedureInputs(kill_switch_activated=True, cancel_all_orders_called=True, open_orders_after_cancel=0, new_orders_blocked=True, safe_mode_active=True, notification_sent=True)); print(r.status, r.passed)"
```

Esperado:

```txt
PASS True
```

---

## 5. Gerar relatório de incidente

```powershell
python scripts\run_incident_report.py --export
```

O script pode retornar código 1 se houver incidente ativo. Isso é esperado.

Validar:

```powershell
Test-Path artifacts\observability\incident_report_demo.json
```

---

## 6. Rodar auditoria de risco

```powershell
python scripts\run_live_risk_audit.py --export --name emergency_live_risk_audit
```

---

## 7. Rodar auditoria de segurança

```powershell
python -u scripts\run_security_audit.py --export --scan-root .
```

---

## 8. Rotacionar chaves se necessário

Rotacionar imediatamente se:

- API key apareceu em arquivo
- `.env` foi enviado por engano
- chave foi compartilhada
- máquina foi comprometida
- logs mostraram segredo
- houve acesso não reconhecido

Após rotação, rodar:

```powershell
python -c "from security.key_rotation_check import KeyRotationRecord, build_key_rotation_check_report; from datetime import datetime, timezone, timedelta; now=datetime.now(timezone.utc); r=build_key_rotation_check_report(keys=[KeyRotationRecord(key_name='BINANCE_API_KEY', last_rotated_at=now, next_rotation_due_at=now+timedelta(days=30), rotation_procedure_doc='docs/SECURITY.md')]); print(r.status, r.passed)"
```

---

## 9. Reabrir operação

Só reabrir operação se:

- [ ] causa raiz identificada
- [ ] incidente documentado
- [ ] production guard aprovado
- [ ] secrets audit aprovado
- [ ] risk audit aprovado
- [ ] emergency test aprovado
- [ ] human approval renovado
- [ ] sessão reiniciada com micro-capital

---

## 10. Regra final

Em emergência, preservar capital é prioridade.  
Não tentar “recuperar prejuízo” aumentando tamanho, frequência ou leverage.