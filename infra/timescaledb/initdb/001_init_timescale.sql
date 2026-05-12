-- ============================================================
-- BTC Polymarket Bot - TimescaleDB Initialization
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE SCHEMA IF NOT EXISTS market_data;


-- ============================================================
-- 1. BTC Candles
-- ============================================================
--
-- Armazena candles de BTC vindos de exchanges como Binance,
-- Coinbase ou outras fontes.
--
-- Esta tabela NÃO usa market_id do Polymarket, porque candles
-- pertencem ao ativo BTC por exchange/símbolo/timeframe.
-- A relação com mercados do Polymarket acontece depois,
-- na features_store.
-- ============================================================

CREATE TABLE IF NOT EXISTS market_data.btc_candles (
    ts TIMESTAMPTZ NOT NULL,

    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,

    volume DOUBLE PRECISION,
    quote_volume DOUBLE PRECISION,
    trades_count BIGINT,

    funding_rate DOUBLE PRECISION,
    open_interest DOUBLE PRECISION,
    mark_price DOUBLE PRECISION,
    index_price DOUBLE PRECISION,

    source TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ts, exchange, symbol, timeframe)
);

SELECT create_hypertable(
    'market_data.btc_candles',
    'ts',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_btc_candles_symbol_tf_ts
ON market_data.btc_candles (symbol, timeframe, ts DESC);

CREATE INDEX IF NOT EXISTS idx_btc_candles_exchange_symbol_tf_ts
ON market_data.btc_candles (exchange, symbol, timeframe, ts DESC);


-- ============================================================
-- 2. Polymarket Order Book
-- ============================================================
--
-- Armazena snapshots do order book dos mercados do Polymarket.
-- Aqui market_id é essencial porque cada mercado tem seu próprio
-- identificador, tokens YES/NO, liquidez e spread.
-- ============================================================

CREATE TABLE IF NOT EXISTS market_data.poly_orderbook (
    ts TIMESTAMPTZ NOT NULL,

    market_id TEXT NOT NULL,
    condition_id TEXT,
    token_id TEXT NOT NULL,
    outcome TEXT NOT NULL,

    best_bid DOUBLE PRECISION,
    best_ask DOUBLE PRECISION,
    mid_price DOUBLE PRECISION,
    spread DOUBLE PRECISION,

    bid_depth DOUBLE PRECISION,
    ask_depth DOUBLE PRECISION,
    orderbook_depth DOUBLE PRECISION,
    liquidity DOUBLE PRECISION,

    bids JSONB,
    asks JSONB,
    raw_payload JSONB,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ts, market_id, token_id)
);

SELECT create_hypertable(
    'market_data.poly_orderbook',
    'ts',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_poly_orderbook_market_ts
ON market_data.poly_orderbook (market_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_poly_orderbook_market_token_ts
ON market_data.poly_orderbook (market_id, token_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_poly_orderbook_outcome_ts
ON market_data.poly_orderbook (outcome, ts DESC);


-- ============================================================
-- 3. Features Store
-- ============================================================
--
-- Armazena o conjunto de features usado pelo modelo antes de
-- tomar decisão. Essa tabela conecta:
--
-- BTC candles
-- Polymarket orderbook
-- sinais técnicos
-- sinais on-chain
-- sentimento
-- score do modelo
-- edge calculado
-- decisão final
-- ============================================================

CREATE TABLE IF NOT EXISTS market_data.features_store (
    ts TIMESTAMPTZ NOT NULL,

    market_id TEXT NOT NULL,
    condition_id TEXT,
    timeframe TEXT NOT NULL,

    btc_price DOUBLE PRECISION,
    btc_return_5m DOUBLE PRECISION,
    btc_return_15m DOUBLE PRECISION,
    btc_return_1h DOUBLE PRECISION,
    btc_return_1d DOUBLE PRECISION,

    realized_volatility DOUBLE PRECISION,
    volume_zscore DOUBLE PRECISION,

    technical_score DOUBLE PRECISION,
    onchain_score DOUBLE PRECISION,
    sentiment_score DOUBLE PRECISION,
    microstructure_score DOUBLE PRECISION,
    ml_score DOUBLE PRECISION,

    prob_yes DOUBLE PRECISION,
    prob_no DOUBLE PRECISION,

    ask_yes DOUBLE PRECISION,
    ask_no DOUBLE PRECISION,

    edge_yes DOUBLE PRECISION,
    edge_no DOUBLE PRECISION,

    confidence DOUBLE PRECISION,
    liquidity DOUBLE PRECISION,
    spread DOUBLE PRECISION,
    time_to_expiry_seconds INTEGER,

    selected_side TEXT,
    signal_status TEXT,

    feature_set_version TEXT NOT NULL DEFAULT 'v1',
    model_version TEXT,

    features JSONB,
    raw_payload JSONB,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ts, market_id, timeframe, feature_set_version)
);

SELECT create_hypertable(
    'market_data.features_store',
    'ts',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_features_store_market_tf_ts
ON market_data.features_store (market_id, timeframe, ts DESC);

CREATE INDEX IF NOT EXISTS idx_features_store_signal_ts
ON market_data.features_store (signal_status, ts DESC);

CREATE INDEX IF NOT EXISTS idx_features_store_model_ts
ON market_data.features_store (model_version, ts DESC);


-- ============================================================
-- Retention Policies
-- ============================================================
--
-- btc_candles:
--   Mantém 730 dias para backtests e análise histórica.
--
-- poly_orderbook:
--   Mantém 90 dias porque order book bruto cresce muito rápido.
--
-- features_store:
--   Mantém 730 dias porque é essencial para backtest,
--   auditoria e análise de performance do modelo.
-- ============================================================

SELECT add_retention_policy(
    'market_data.btc_candles',
    INTERVAL '730 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'market_data.poly_orderbook',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'market_data.features_store',
    INTERVAL '730 days',
    if_not_exists => TRUE
);