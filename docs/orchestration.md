# Orchestration

Este documento define a estratégia de orquestração do projeto `btc-polymarket-bot`.

## Ferramenta escolhida

Nesta fase, usamos Prefect.

Motivos:

- Mais simples para desenvolvimento local.
- Boa integração com Python.
- Suporta schedules por intervalo e cron.
- Mais leve que uma stack Airflow completa em Docker.

## Pipelines oficiais

| Pipeline | Flow | Frequência |
|---|---|---|
| Ingestão de candles | `ingest-candles-flow` | contínuo / intervalo curto |
| Atualização on-chain | `update-onchain-flow` | a cada 15 minutos |
| Retreinamento do modelo | `retrain-model-flow` | semanal |
| Limpeza de dados antigos | `cleanup-old-data-flow` | diário |

## Arquivos

```txt
orchestration/
├── flows/
│   ├── ingest_candles_flow.py
│   ├── update_onchain_flow.py
│   ├── retrain_model_flow.py
│   └── cleanup_old_data_flow.py
│
└── deployments/