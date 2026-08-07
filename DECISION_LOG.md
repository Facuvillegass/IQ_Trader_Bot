# Decision Log

Fecha: 2026-08-07

## Proveedor de datos elegido

**Primario recomendado: Databento (`GLBX.MDP3`, schema `ohlcv-1m`)**  
**Default actual sin credenciales: `mock`**

Razones:
- Corrés en **Mac**. NinjaTrader es Windows-first → Sim101 nativo no es práctico sin VM.
- Databento ofrece histórico + live con el mismo schema, ideal para sanity check 2024 y forward test.
- Nuevas cuentas suelen tener créditos gratuitos → menor fricción que una VM Windows + broker data.
- Hasta que pegues la API key, el sistema corre end-to-end con `mock` (warmup SMA + señales + fills + dashboard).

Alternativas evaluadas:
- **NinjaTrader Sim101 en VM Windows**: fiel al Analyzer, pero alta fricción (licencia/VM/RDP) y más intervención tuya.
- **Tradovate demo API**: viable, pero auth/CID/market-data + rollover de contrato front-month añaden pasos humanos y complejidad. Dejamos campos en `.env` por si más adelante querés fills de broker demo.
- **yfinance `MNQ=F`**: gratis/delayed, 1m muy corto → solo puente temporal (`DATA_PROVIDER=yfinance`).

## Broker / demo

**Paper engine propio (no broker live).**

Razones:
- Control total de auditoría (signal → order → fill → trade).
- `TRADING_MODE=PAPER` hard-lock.
- Independiente de Windows/Ninja.
- Costos normalizados a $0.62/side como en la investigación Python; la plataforma demo no se usa aún, así que no hay segundo ledger de broker (se documenta para cuando exista Tradovate).

## Continuous contracts / rollover

- Databento: symbology continua `MNQ.c.0` (calendar) con fallback a parent `MNQ`.
- Mock/replay: serie continua sintética o CSV único — no hay rollover físico.
- No se fabrican trades retrospectivos entre el 7-ago 20:30 AR y el arranque real; `experiment_started_at` se setea al activar el engine.

## Session hours

Réplica conceptual ETH de índices CME / NinjaTrader:
- Dom 17:00 CT → Vie 16:00 CT
- Break diario 16:00–17:00 CT
- `ExitOnSessionCloseSeconds=30` → en resolución 1m se aplana en la barra 15:59 CT

No se limita a RTH.

## Fill model

- Señales en **close de barra**
- Fill simulado en **open de la siguiente barra** (timestamp +1m) al precio de señal ± 1 tick
- Market orders, TIF GTC (irrelevante para market)
- `Fill limit orders on touch = False` (no usamos limits)
- Sin fills perfectos mid-bar

## Costos

- Comisión research: **$0.62 por lado por contrato**
- Slippage: **1 tick** ($0.50 en MNQ) embebido en precio de fill + track de `slippage_cost`
- Specs MNQ validados vs CME: tick 0.25, tick value $0.50, point value $2.00

## Reinicios

- SQLite WAL
- `processed_bars` + idempotency keys en signals/orders/fills
- Reprocesar la misma barra no duplica fills
- Account/position restaurados desde último snapshot + tabla `positions`

## Warmup vs forward account

- El warmup de SMA carga barras históricas/sintéticas **sin ejecutar trades**.
- La cuenta forward arranca en $10,000 al `experiment_started_at` real.
- No se fabrican trades entre el 7-ago 20:30 AR y el arranque efectivo.

## Puerto API

- Local default `8010` (evita conflicto con otros servicios en esta Mac).
- Railway: escucha `$PORT`.

## Railway 24/7

- **Un solo servicio**: worker embebido + FastAPI + dashboard estático.
- Motivo: Railway monta **un volumen por servicio**. Separar worker y API implicaría Postgres u otro store compartido. SQLite en `/data` + un proceso es más simple y robusto para este MVP.
- `numReplicas = 1` + lease SQLite (`worker_lease`, TTL 45s) para impedir dos engines.
- Healthcheck HTTP `/health` **no** es el heartbeat del worker; el worker tiene su propio loop + lease heartbeat.
- Dockerfile multi-stage: Node 22 build del frontend → Python 3.12 slim runtime (Databento soporta 3.12; 3.14 local no).
- Auto-recovery: exponential backoff en el worker; backfill de barras faltantes; no se inventan barras; reconnect no dispara un trade dummy.
- Watchdog: `MARKET_DATA_STALE` si ETH está abierto y no hay barras nuevas; bloquea entradas.

## Timezone

- Persistencia y lógica: UTC.
- Sesión MNQ: `America/Chicago` explícito.
- Display dashboard: `America/Argentina/Cordoba` (`TZ_DISPLAY`).
- Nunca se usa TZ del container como fuente de verdad.

## Almacenamiento

SQLite:
- Local: `data/paper_trading.db`
- Railway: `/data/trading.db`

Tablas: `bars`, `signals`, `orders`, `fills`, `trades`, `positions`, `account_snapshots`, `system_events`, `processed_bars`, `worker_lease`, `meta`.
