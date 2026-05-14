# ============================================================
# BTC Polymarket Bot - Redpanda Topic Creation
# ============================================================
#
# Este script cria os tópicos oficiais do projeto no Redpanda.
# Execute depois que o container btc-polymarket-redpanda estiver rodando.
#
# Uso:
# powershell -ExecutionPolicy Bypass -File infra\redpanda\create_topics.ps1
# ============================================================

$topics = @(
    "btc-candles",
    "poly-orderbook",
    "poly-trades",
    "onchain-events",
    "sentiment-events",
    "signals",
    "orders",
    "fills"
)

foreach ($topic in $topics) {
    Write-Host "Creating topic: $topic"
    docker exec btc-polymarket-redpanda rpk topic create $topic 2>$null
}

Write-Host ""
Write-Host "Current topics:"
docker exec btc-polymarket-redpanda rpk topic list