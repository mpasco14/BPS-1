# Messaging Topics

Este documento define os tópicos oficiais de mensageria do projeto `btc-polymarket-bot`.

## Broker local

Nesta fase, usamos Redpanda como broker compatível com Kafka.

- Broker para Python local: `localhost:19092`
- Broker interno Docker: `redpanda:9092`

## Tópicos oficiais

| Tópico | Produtor | Consumidor | Função |
|---|---|---|---|
| `btc-candles` | `connectors/binance_ws.py` | `strategy/technical_engine.py`, `data/candles.py` | Candles BTC por timeframe |
| `poly-orderbook` | `connectors/polymarket_ws.py` | `data/orderbook.py`, `strategy/signal_engine.py` | Order book Polymarket |
| `poly-trades` | `connectors/polymarket_ws.py` | `strategy/signal_engine.py`, `monitoring/metrics.py` | Trades Polymarket |
| `onchain-events` | `connectors/glassnode.py` | `strategy/onchain_engine.py` | Eventos on-chain |
| `sentiment-events` | `connectors/sentiment.py` | `strategy/sentiment_engine.py` | Eventos de sentimento |
| `signals` | `strategy/signal_engine.py` | `risk/risk_manager.py` | Sinais gerados |
| `orders` | `risk/risk_manager.py` | `execution/order_router.py` | Ordens aprovadas pelo risco |
| `fills` | `execution/fill_monitor.py` | `monitoring/metrics.py`, `risk/exposure.py`, `models/backtest.py` | Preenchimentos de ordens |

## Padrão de mensagem

Toda mensagem deve ser JSON.

Formato recomendado:

```json
{
  "event_id": "uuid",
  "event_type": "btc_candle",
  "source": "binance",
  "ts": "2026-05-12T02:10:51Z",
  "payload": {}
}