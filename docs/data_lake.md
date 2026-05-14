# Data Lake

Este documento define o padrão de data lake do projeto `btc-polymarket-bot`.

## Backend local

Em desenvolvimento local, usamos MinIO como armazenamento compatível com S3.

- API S3 local: `http://localhost:9000`
- Console web: `http://localhost:9001`
- Bucket principal: `btc-polymarket-datalake`

## Divisão de responsabilidades

- TimescaleDB: séries temporais estruturadas e consultas SQL.
- Redis: cache e estado operacional recente.
- Redpanda: mensageria/event streaming.
- MinIO/S3: arquivos brutos, Parquet, datasets, features e modelos.

## Bucket principal

```txt
btc-polymarket-datalake