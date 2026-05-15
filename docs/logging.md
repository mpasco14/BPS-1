# Logging and Audit

Este documento define a estratégia de logs e auditoria do projeto `btc-polymarket-bot`.

## Ferramentas

Nesta fase, usamos:

- Loki: armazenamento e consulta de logs.
- Grafana Alloy: coleta local de arquivos de log e envio para Loki.
- Grafana: visualização e exploração dos logs.

## Objetivo

Registrar eventos operacionais e decisões do sistema para auditoria.

Cada decisão futura do sistema deve registrar:

- timestamp
- event_type
- market_id
- timeframe
- features usadas
- probabilidade estimada
- edge calculado
- decisão: operar ou não operar
- motivo da decisão
- status do risk manager
- status do circuit breaker

## Estrutura local de logs

```txt
logs/
├── app/
│   └── app.log
│
└── audit/
    └── decisions.jsonl