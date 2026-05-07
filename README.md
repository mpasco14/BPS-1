# BTC Polymarket Bot

Sistema automatizado para análise, decisão, gerenciamento de risco e execução de operações em mercados de previsão relacionados ao Bitcoin no Polymarket.

## Visão geral

O BTC Polymarket Bot é um projeto de engenharia voltado para construir uma esteira automatizada capaz de:

- Coletar dados de mercado, preço, volume, sentimento e dados on-chain;
- Descobrir mercados ativos de Bitcoin no Polymarket;
- Classificar mercados por timeframe;
- Calcular indicadores técnicos;
- Avaliar sinais on-chain;
- Medir sentimento social e noticioso;
- Treinar e executar modelos de IA;
- Estimar probabilidades para outcomes YES/NO;
- Comparar a probabilidade estimada com o preço implícito do mercado;
- Calcular edge líquido após custos, spread, slippage e risco;
- Gerar ou rejeitar sinais de operação;
- Validar cada sinal com um gerenciador de risco;
- Enviar ordens limitadas quando houver aprovação;
- Monitorar preenchimentos, exposição, falhas e performance;
- Registrar logs e auditoria de cada decisão.

Este projeto não tem como objetivo apenas prever se o Bitcoin vai subir ou cair.

O objetivo principal é responder a uma pergunta mais objetiva:

> A probabilidade real estimada pelo modelo é maior do que a probabilidade implícita no preço do Polymarket, depois de considerar taxas, spread, slippage, liquidez e risco?

Se a resposta for sim, o sistema pode gerar uma operação.

Se a resposta for não, o sistema deve esperar.

---

## Aviso importante

Este projeto é experimental, técnico e educacional.

Não é recomendação financeira.

Qualquer uso real deve respeitar:

- Leis locais;
- Termos de uso das plataformas;
- Restrições geográficas;
- Regras de compliance;
- Segurança de chaves privadas;
- Gestão de risco adequada;
- Validação em ambiente de simulação antes de qualquer execução real.

Por padrão, o sistema deve iniciar em modo `paper`, com execução real desativada.

---

## Timeframes

O projeto é focado em mercados relacionados ao Bitcoin nos seguintes timeframes:

- 5m
- 15m
- 1h
- 1D

Cada timeframe possui pesos diferentes para:

- Análise técnica;
- Microestrutura de mercado;
- Modelos de IA;
- Sentimento;
- Dados on-chain.

Timeframes menores tendem a exigir maior edge mínimo por causa de:

- Mais ruído;
- Maior impacto de latência;
- Maior risco de slippage;
- Maior sensibilidade ao spread;
- Menor tempo para correção de erro.

---

## Arquitetura geral

O sistema segue uma arquitetura em esteira:

```txt
Fontes de Dados
     ↓
Normalização e Armazenamento
     ↓
Feature Engine
     ↓
Modelos / Estratégias
     ↓
Risk Manager
     ↓
Executor Polymarket
     ↓
Monitoramento, Logs e Auditoria
```

A decisão final de operação depende da combinação entre:

```txt
Dados fortes
+ modelo calibrado
+ edge líquido positivo
+ liquidez suficiente
+ execução conservadora
+ risco aprovado
```

---

## Arquitetura em 6 camadas

### Camada 1 — Coleta de dados

Responsável por coletar os dados necessários para alimentar o sistema.

Fontes previstas:

- Polymarket;
- Order book;
- Trades;
- Liquidez;
- Volume;
- Preço do Bitcoin;
- Dados de exchanges;
- Sentimento social;
- Notícias;
- Dados on-chain;
- Fluxos de whales;
- Fluxos de exchanges;
- Dados de mineradores.

Principais componentes:

```txt
connectors/polymarket_gamma.py
connectors/polymarket_clob.py
connectors/polymarket_ws.py
connectors/binance_ws.py
connectors/glassnode.py
connectors/sentiment.py
```

---

### Camada 2 — Análise técnica automatizada

Responsável por transformar dados de preço e volume em sinais técnicos.

Indicadores previstos:

- EMA;
- RSI;
- MACD;
- VWAP;
- ATR;
- Bollinger Bands;
- ADX;
- Volume spike;
- Volatilidade realizada;
- Estrutura de tendência.

Principais componentes:

```txt
strategy/technical_engine.py
data/candles.py
```

---

### Camada 3 — Análise on-chain

Responsável por avaliar sinais vindos da rede Bitcoin e de fluxos entre carteiras e exchanges.

Sinais previstos:

- Whale inflow;
- Whale outflow;
- Exchange inflow;
- Exchange outflow;
- Stablecoin inflow;
- Miner outflow;
- Mempool congestion;
- Fees da rede;
- Large transactions count.

Principais componentes:

```txt
strategy/onchain_engine.py
connectors/glassnode.py
```

---

### Camada 4 — Modelos de IA

Responsável por treinar, calibrar e executar modelos capazes de estimar probabilidades.

O foco do modelo não é apenas prever direção do BTC.

O foco é estimar se existe vantagem contra o preço do mercado.

Exemplo:

```txt
Modelo estima YES = 62%
Preço de compra do YES = 55%
Custo estimado = 1%

edge_yes = 0.62 - 0.55 - 0.01
edge_yes = 0.06
```

Nesse caso, o sistema identifica uma vantagem teórica de 6 pontos percentuais.

Modelos previstos:

- Regressão logística como baseline;
- LightGBM;
- XGBoost;
- Random Forest;
- Modelos temporais;
- Calibração com Platt Scaling ou Isotonic Regression.

Principais componentes:

```txt
models/train.py
models/predict.py
models/calibrate.py
models/backtest.py
```

---

### Camada 5 — Gerenciamento de risco

Responsável por impedir que o sistema opere quando o risco for inadequado.

Regras previstas:

- Limite por trade;
- Limite diário de perda;
- Limite por mercado;
- Limite por timeframe;
- Limite de exposição direcional;
- Kill switch;
- Controle de liquidez;
- Controle de spread;
- Controle de slippage;
- Controle de falhas de API;
- Controle de desconexão de WebSocket;
- Controle de divergência de preço entre exchanges;
- Bloqueio por comportamento fora da distribuição esperada.

Principais componentes:

```txt
risk/risk_manager.py
risk/exposure.py
risk/kill_switch.py
```

---

### Camada 6 — Execução de trades

Responsável por transformar sinais aprovados em ordens controladas.

Fluxo previsto:

```txt
1. Descobrir mercados ativos de BTC
2. Classificar mercado por timeframe
3. Verificar tempo até o fechamento
4. Ler order book
5. Calcular preço justo do modelo
6. Calcular edge líquido
7. Validar risco
8. Criar ordem limitada
9. Enviar ordem
10. Monitorar preenchimento
11. Cancelar ordem se o edge desaparecer
12. Registrar decisão em log de auditoria
```

O sistema deve priorizar ordens limitadas.

Ordens a mercado devem ficar desativadas por padrão.

Principais componentes:

```txt
execution/order_router.py
execution/limit_order.py
execution/cancel_order.py
execution/fill_monitor.py
```

---

## Estrutura do projeto

```txt
btc-polymarket-bot/
│
├── app/
│   ├── main.py
│   ├── config.py
│   └── __init__.py
│
├── connectors/
│   ├── polymarket_gamma.py
│   ├── polymarket_clob.py
│   ├── polymarket_ws.py
│   ├── binance_ws.py
│   ├── glassnode.py
│   ├── sentiment.py
│   └── __init__.py
│
├── data/
│   ├── normalizer.py
│   ├── feature_store.py
│   ├── candles.py
│   ├── orderbook.py
│   └── __init__.py
│
├── strategy/
│   ├── technical_engine.py
│   ├── onchain_engine.py
│   ├── sentiment_engine.py
│   ├── signal_engine.py
│   ├── market_selector.py
│   └── __init__.py
│
├── models/
│   ├── train.py
│   ├── predict.py
│   ├── calibrate.py
│   ├── backtest.py
│   └── __init__.py
│
├── risk/
│   ├── risk_manager.py
│   ├── exposure.py
│   ├── kill_switch.py
│   └── __init__.py
│
├── execution/
│   ├── order_router.py
│   ├── limit_order.py
│   ├── cancel_order.py
│   ├── fill_monitor.py
│   └── __init__.py
│
├── monitoring/
│   ├── metrics.py
│   ├── alerts.py
│   ├── dashboard.json
│   └── __init__.py
│
├── tests/
│   ├── test_signals.py
│   ├── test_risk.py
│   └── test_execution.py
│
├── README.md
├── .gitignore
├── .env.example
└── requirements.txt
```

---

## Responsabilidade de cada pasta

### `app/`

Contém o ponto de entrada da aplicação e configurações principais.

Responsável por:

- Inicializar o sistema;
- Carregar configurações;
- Subir serviços;
- Definir modo de execução;
- Orquestrar componentes principais.

---

### `connectors/`

Contém conectores para fontes externas.

Responsável por:

- Buscar mercados no Polymarket;
- Ler order book;
- Conectar WebSockets;
- Buscar candles de BTC;
- Buscar dados on-chain;
- Buscar dados de sentimento.

---

### `data/`

Contém normalização, preparação e armazenamento intermediário.

Responsável por:

- Padronizar dados;
- Construir candles;
- Processar order book;
- Criar features;
- Preparar dados para modelos e estratégias.

---

### `strategy/`

Contém os motores de análise e decisão.

Responsável por:

- Calcular scores técnicos;
- Calcular scores on-chain;
- Calcular scores de sentimento;
- Selecionar mercados;
- Gerar sinais;
- Escolher entre YES e NO.

---

### `models/`

Contém treinamento, previsão, calibração e backtest.

Responsável por:

- Treinar modelos;
- Gerar probabilidades;
- Calibrar probabilidades;
- Validar performance;
- Executar backtests;
- Medir Brier Score, Log Loss, ROI e drawdown.

---

### `risk/`

Contém a camada de defesa do sistema.

Responsável por:

- Aprovar ou rejeitar sinais;
- Controlar exposição;
- Aplicar limites por timeframe;
- Aplicar limite diário de perda;
- Acionar kill switch;
- Bloquear operação em falhas técnicas.

---

### `execution/`

Contém a camada de execução.

Responsável por:

- Criar ordens limitadas;
- Enviar ordens;
- Cancelar ordens;
- Monitorar preenchimentos;
- Impedir execução quando o edge desaparece.

---

### `monitoring/`

Contém métricas, alertas, logs e dashboards.

Responsável por:

- Expor métricas para Prometheus;
- Criar alertas;
- Registrar logs;
- Registrar auditoria;
- Monitorar falhas;
- Acompanhar performance e exposição.

---

### `tests/`

Contém testes automatizados.

Responsável por validar:

- Regras de sinal;
- Regras de risco;
- Regras de execução;
- Comportamento esperado do sistema.

---

## Lógica principal de decisão

O sistema deve comparar a probabilidade estimada pelo modelo com o preço do mercado.

```python
edge_yes = prob_model_yes - ask_yes - cost_yes
edge_no = prob_model_no - ask_no - cost_no
```

Depois, o sistema deve verificar se existe edge suficiente:

```python
if edge > min_edge and confidence > min_confidence and liquidity_ok:
    gerar_sinal()
else:
    ignorar_mercado()
```

Mas o sinal ainda não pode ser executado diretamente.

Ele precisa passar pelo gerenciador de risco:

```python
if risk_manager.approve(signal):
    order = execution.create_limit_order(signal)
    execution.submit(order)
else:
    logger.info("Trade rejeitado pelo risk manager")
```

---

## Parâmetros iniciais de decisão

Edge mínimo por timeframe:

```txt
5m  → 3.5%
15m → 3.0%
1h  → 2.0%
1D  → 1.5%
```

Confiança mínima:

```txt
65%
```

Regras conservadoras de execução:

```txt
Usar ordens limitadas
Evitar ordens a mercado
Cancelar ordens antigas
Evitar spread alto
Evitar baixa liquidez
Evitar mercados próximos demais do fechamento
Evitar operação se houver falha de API ou WebSocket
```

---

## Gerenciamento de risco

Parâmetros iniciais sugeridos:

```txt
Risco máximo por trade: 0.5% da banca
Perda máxima diária: 3% da banca
Exposição máxima por mercado: 2% da banca
Exposição direcional total em BTC: 10% da banca
```

Exposição máxima por timeframe:

```txt
5m  → 2%
15m → 4%
1h  → 6%
1D  → 8%
```

O sistema deve parar automaticamente se:

```txt
A perda diária for atingida
A API falhar repetidamente
O WebSocket desconectar repetidamente
O preço divergir muito entre exchanges
O spread aumentar demais
A liquidez cair demais
O modelo operar fora da distribuição esperada
```

---

## Execução

O módulo de execução deve seguir esta regra:

```txt
Sinal aprovado pelo modelo não é ordem.
Sinal aprovado pelo modelo + risco aprovado = ordem candidata.
Ordem candidata + liquidez suficiente + spread aceitável = ordem limitada.
```

O sistema deve preferir:

```txt
Limit orders
```

E evitar por padrão:

```txt
Market orders
```

---

## Backtesting

Antes de qualquer execução real, o sistema precisa ser validado em backtest e paper trading.

O backtest deve simular:

- Taxas;
- Spread;
- Slippage;
- Latência;
- Ordens parcialmente preenchidas;
- Mudança de preço;
- Liquidez real por nível do book;
- Falhas de API;
- Mercados perto do vencimento.

Métricas mínimas:

- ROI;
- Sharpe;
- Max drawdown;
- Hit rate;
- Expected value;
- Profit factor;
- Calibration curve;
- Brier Score;
- Log Loss;
- PnL por timeframe;
- PnL por tipo de sinal;
- PnL por condição de volatilidade.

---

## Configuração do ambiente

Copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

Edite o `.env` local:

```powershell
code .env
```

O arquivo `.env` deve conter suas configurações reais.

O arquivo `.env.example` deve continuar sem chaves reais.

---

## Instalação inicial

Crie o ambiente virtual:

```powershell
python -m venv .venv
```

Ative o ambiente virtual:

```powershell
.venv\Scripts\Activate.ps1
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

---

## Modos de execução

### Paper mode

Modo padrão e mais seguro.

```env
TRADING_MODE=paper
ENABLE_TRADING=false
ENABLE_PAPER_TRADING=true
```

Neste modo, o sistema simula decisões e operações sem enviar ordens reais.

---

### Backtest mode

Modo usado para validação histórica.

```env
TRADING_MODE=backtest
ENABLE_BACKTEST=true
```

Neste modo, o sistema testa estratégias usando dados históricos.

---

### Live mode

Modo de execução real.

```env
TRADING_MODE=live
ENABLE_TRADING=true
```

Este modo deve ser usado somente depois de:

- Backtest aprovado;
- Paper trading aprovado;
- Risco configurado;
- Compliance validado;
- Chaves protegidas;
- Monitoramento ativo;
- Kill switch ativo.

---

## Checklist de produção

Antes de qualquer uso real:

- [ ] Compliance e geoblock verificados
- [ ] `.env` fora do Git
- [ ] API keys protegidas
- [ ] Private keys protegidas
- [ ] Modo paper testado
- [ ] Backtest com custos reais
- [ ] Simulação de slippage
- [ ] Simulação de latência
- [ ] Simulação de fills parciais
- [ ] Circuit breaker ativo
- [ ] Kill switch ativo
- [ ] Limite diário de perda ativo
- [ ] Limites por timeframe ativos
- [ ] Controle de exposição direcional ativo
- [ ] Logs ativos
- [ ] Auditoria ativa
- [ ] Dashboard de exposição ativo
- [ ] Alertas configurados
- [ ] Monitor de WebSocket ativo
- [ ] Cancelamento automático de ordens antigas ativo
- [ ] Modelo versionado
- [ ] Probabilidades calibradas
- [ ] Testes automatizados passando

---

## Status do projeto

Etapa atual:

```txt
Estrutura inicial do projeto criada.
Configuração base do ambiente em desenvolvimento.
README e .env.example alinhados com análise, decisão, risco e execução.
```

Próxima etapa recomendada:

```txt
Configurar ambiente Python, carregar variáveis do .env e criar o primeiro app/main.py funcional.
```