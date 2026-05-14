# Monitoring

Este documento define a stack de monitoramento do projeto `btc-polymarket-bot`.

## Objetivo

A stack de monitoramento tem como objetivo acompanhar a saúde operacional do sistema, incluindo infraestrutura, mensageria, cache e métricas futuras da aplicação.

Nesta etapa, o projeto usa:

- Prometheus para coleta e armazenamento de métricas.
- Grafana para visualização em dashboards.
- Redis Exporter para expor métricas do Redis.
- Redpanda metrics para expor métricas do broker Kafka-compatible.

## Serviços monitorados

| Serviço | Função | Porta local |
|---|---|---|
| Prometheus | Coleta métricas | `9090` |
| Grafana | Exibe dashboards | definida em `GRAFANA_PORT` |
| Redis Exporter | Expõe métricas do Redis | `9121` |
| Redpanda | Expõe métricas do broker | `9644` |
| Bot Python | Métricas futuras da aplicação | `8001` |

## URLs locais

```txt
Prometheus: http://localhost:9090
Grafana:    http://localhost:${GRAFANA_PORT}