# BTC Binance Futures Bot — Architecture Overview

## 1. Objetivo do sistema

Este projeto é um sistema automatizado para análise, validação, simulação e execução controlada de operações em BTCUSDT no mercado de Binance Futures.

O objetivo principal não é apenas gerar sinais, mas criar uma arquitetura disciplinada baseada em:

- Inteligência
- Rastreabilidade
- Disciplina
- Segurança
- Resiliência

O sistema foi desenhado para operar primeiro em paper trading, depois testnet, depois micro-live controlado, e somente depois considerar qualquer aumento manual de capital.

---

## 2. Princípios centrais

### 2.1 Segurança antes de lucro

Nenhuma ordem real deve ser enviada sem:

- Production Environment Guard aprovado
- Secrets Audit aprovado
- Risk Audit aprovado
- Capital Ramp Validation aprovado
- Emergency State limpo
- Human Approval válido
- Live Order Adapter habilitado conscientemente

### 2.2 Live bloqueado por padrão

Configurações seguras padrão:

```env
LIVE_ORDER_ADAPTER_ENABLED=false
LIVE_ORDER_ADAPTER_DRY_RUN=true
LIVE_ORDER_ADAPTER_ALLOW_SUBMISSION=false
RUNTIME_CONFIG_ALLOW_LIVE=false
```

### 2.3 Rastreabilidade total

Toda decisão precisa poder ser explicada por:

- Sinal
- Features
- Sentimento
- Risk state
- No-trade decision
- Live guard
- Decision journal
- Learning feedback
- Outcome attribution

### 2.4 Aprendizado controlado

O sistema pode aprender com resultados, mas não deve alterar risco, capital ou permissões live automaticamente.

---

## 3. Camadas principais

## Camada 1 — Dados e features

Responsável por coletar, normalizar e armazenar dados usados nas decisões.

Componentes:

- candles
- orderbook
- technical features
- on-chain features
- sentiment features
- feature store
- historical dataset

---

## Camada 2 — Estratégia e sinais

Responsável por transformar features em sinais operacionais.

Componentes:

- technical engine
- sentiment integration
- signal engine
- no-trade engine
- regime detection
- adaptive threshold review

---

## Camada 3 — Risco

Responsável por decidir se um sinal pode virar ordem.

Componentes:

- risk manager
- exposure snapshot
- sizing
- kill switch
- live guard
- live safety gate
- real-time risk state

---

## Camada 4 — Execução

Responsável por transformar decisão aprovada em ordem.

Componentes:

- Binance Futures client
- market selector
- limit order builder
- order router
- fill monitor
- cancel order
- paper trading loop
- testnet trading loop
- live order adapter

---

## Camada 5 — Governança

Responsável por garantir disciplina, rastreabilidade e aprendizado.

Componentes:

- governance core
- data quality gate
- decision journal
- outcome attribution
- learning feedback dataset
- discipline score
- strategy health score

---

## Camada 6 — Sentiment Intelligence

Responsável por analisar sentimento e transformá-lo em features auditáveis.

Componentes:

- sentiment schema
- preprocessor
- source weighting
- sentiment index
- fear and greed
- sentiment orchestrator
- sentiment feature store
- sentiment no-trade adapter
- sentiment strategy health

---

## Camada 7 — Live Optimization

Responsável por medir sessões micro-live reais.

Componentes:

- live session recorder
- live performance analyzer
- live risk audit
- live capital ramp validation
- live drift monitor
- regime optimization

---

## Camada 8 — Production Readiness

Responsável por bloquear live inseguro.

Componentes:

- production environment guard
- secrets and key rotation audit
- live order adapter final gate
- emergency stop procedure test
- human approval workflow

---

## Camada 9 — Infraestrutura

Responsável por robustez operacional.

Componentes:

- dependency health check
- runtime config validator
- retry and backoff policy
- state recovery manager
- failure injection / chaos test

---

## Camada 10 — Observabilidade

Responsável por transformar o estado do sistema em métricas, alertas e incidentes.

Componentes:

- metrics registry
- Prometheus exporter
- alert rules
- Grafana dashboard config
- incident report generator

---

## Camada 11 — Segurança

Responsável por reduzir risco operacional e vazamento.

Componentes:

- local secret scanner
- API permission audit
- dependency security audit
- environment policy guard
- key rotation check

---

## 4. Fluxo de decisão simplificado

```txt
market data
→ feature generation
→ sentiment enrichment
→ signal engine
→ no-trade engine
→ risk manager
→ sizing
→ order plan
→ paper/testnet/live guard
→ order adapter
→ fill monitor
→ exposure update
→ decision journal
→ learning feedback
→ performance/risk/drift/regime analysis
```

---

## 5. Fluxo live controlado

```txt
testnet passed
→ live preflight passed
→ secrets audit passed
→ emergency procedure passed
→ human approval valid
→ production guard passed
→ live order adapter enabled
→ dry_run disabled manually
→ allow_submission enabled manually
→ micro-capital order only
```

---

## 6. Artefatos principais

```txt
artifacts/paper_trading/
artifacts/model_evaluation/
artifacts/backtesting/
artifacts/governance/
artifacts/journal/
artifacts/sentiment/
artifacts/live/
artifacts/production/
artifacts/infra/
artifacts/observability/
artifacts/security/
```

---

## 7. Regra final

Este sistema não deve ser operado com capital real sem seguir os runbooks:

- LOCAL_SETUP_RUNBOOK.md
- PAPER_TESTNET_RUNBOOK.md
- CONTROLLED_LIVE_ACTIVATION_RUNBOOK.md
- EMERGENCY_SHUTDOWN_RUNBOOK.md
- WEEKLY_AUDIT_RUNBOOK.md