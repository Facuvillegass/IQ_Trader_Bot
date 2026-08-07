# MNQ Paper Trading / Forward Test

Sistema de **paper trading 24/7** para validar en tiempo real una estrategia MNQ ya investigada y backtesteada.

**No optimiza parámetros.** SMA 4750 y Band 50 quedan congelados.

- Instrumento: MNQ (Micro E-mini Nasdaq-100)
- Cantidad: 1 contrato
- Dirección: LONG ONLY
- Capital virtual: USD 10,000
- Modo: `TRADING_MODE=PAPER` (live bloqueado)
- Timeframe: 1 minuto, señales **on bar close**, condiciones **state/level** (no crosses)
- Timestamps internos: **siempre UTC**
- Dashboard: hora **America/Argentina/Cordoba**

Cerrá la Mac: el worker en Railway sigue procesando MNQ 1m, SMA4750, paper trades y la cuenta virtual.

---

## Qué hace

1. Recibe barras MNQ 1m (Databento / mock / yfinance / replay)
2. Calcula SMA(4750)
3. Genera señales:
   - FLAT + `Close > SMA + 50` → ENTER LONG
   - LONG + `Close < SMA - 50` → EXIT LONG
4. Simula fills (1 tick slippage + comisión $0.62/side)
5. Cierra al session close (ETH, ~30s antes del break 16:00 CT)
6. Persiste todo en SQLite (volumen `/data` en Railway)
7. Expone dashboard + `/health`

El **trading worker** corre en un thread independiente del HTTP. Un health-check o un visitante del dashboard **no** es lo que mantiene vivo al engine.

---

## Arquitectura (Railway)

```
Railway Project  (replicas = 1)
└── un servicio
    ├── trading worker thread  (24/7, no depende de HTTP)
    ├── FastAPI  /health /status /account /position /trades
    ├── React dashboard (build estático servido por FastAPI)
    └── Volume /data/trading.db
```

Un solo servicio evita el problema de “un volumen por servicio” de Railway y simplifica el singleton.

Protección anti-duplicado:
- `numReplicas = 1` en `railway.json`
- lease lock en SQLite (`worker_lease`) — un segundo proceso queda en STANDBY

---

## Deploy 24/7 en Railway

### 1. Crear cuenta Railway

1. Entrá a https://railway.app
2. **Login with GitHub** (cuenta `Facuvillegass`)

### 2. Conectar GitHub

El repo debe ser `Facuvillegass/IQ_Trader_Bot` (este proyecto).

En Railway: **New Project → Deploy from GitHub repo → IQ_Trader_Bot**.

### 3. Crear proyecto / servicio

Railway detecta el `Dockerfile`. Si pregunta builder, elegí **Dockerfile**.

### 4. Variables

Settings → Variables → pegá (sin commitear secretos):

| Variable | Valor |
|----------|--------|
| `TRADING_MODE` | `PAPER` |
| `DATA_PROVIDER` | `databento` (o `mock` hasta tener key) |
| `DATABENTO_API_KEY` | tu key |
| `DATA_API_KEY` | la misma key |
| `DATABASE_PATH` | `/data/trading.db` |
| `LOG_DIR` | `/data/logs` |
| `REPORTS_DIR` | `/data/reports` |
| `TZ_DISPLAY` | `America/Argentina/Cordoba` |
| `INITIAL_BALANCE` | `10000` |
| `MNQ_QUANTITY` | `1` |
| `SMA_PERIOD` | `4750` |
| `BAND_POINTS` | `50` |
| `SLIPPAGE_TICKS` | `1` |
| `EMBED_WORKER` | `true` |

Railway inyecta `PORT` solo. El proceso escucha `$PORT`.

### 5. Persistent volume (obligatorio)

Settings → Volumes → **Add Volume**

- Mount path: **`/data`**
- Sin esto, un redeploy borra la cuenta / trades.

### 6. Replicas

Confirmá **Replicas = 1**. `railway.json` ya lo fija. Nunca 2 workers sobre la misma cuenta.

### 7. Deploy

Push a `main` o botón **Deploy**. Esperá a que el build (Node frontend + Python 3.12) termine.

### 8. Logs

Deployments → el deploy activo → **View logs**.

Buscá:

```
TRADING_ENGINE_READY
Embedded trading worker started
```

### 9. Dashboard

Settings → Networking → **Generate domain**.

Abrí:

- `https://TU-DOMINIO/` → dashboard
- `https://TU-DOMINIO/health`
- `https://TU-DOMINIO/status`
- `https://TU-DOMINIO/account`
- `https://TU-DOMINIO/position`
- `https://TU-DOMINIO/trades`

### 10. Comprobar `/health`

Ejemplo esperado:

```json
{
  "status": "healthy",
  "worker_alive": true,
  "market_data_connected": true,
  "last_bar_time": "2026-08-08T01:15:00+00:00",
  "position": "FLAT",
  "equity": 10000.00,
  "database_ok": true
}
```

`starting` al boot es normal hasta terminar SMA warmup. `degraded` + `MARKET_DATA_STALE` si el mercado está abierto y no llegan barras. `standby` si otro worker tiene el lease.

---

## Arranque local (Mac)

```bash
cd IQ_Trader_Bot
cp .env.example .env
./start.sh
```

- Dashboard: http://127.0.0.1:5173
- Health: http://127.0.0.1:8010/health
- Estado: http://127.0.0.1:8010/api/state

Detener: `./stop.sh`  
Reiniciar: `./stop.sh && ./start.sh`

---

## Persistencia y reinicios

| Entorno | DB |
|---------|-----|
| Local | `data/paper_trading.db` |
| Railway | `/data/trading.db` |

Tras restart:
1. chequea DB + schema
2. restaura account / position
3. toma lease singleton
4. backfill de barras faltantes
5. reconstruye SMA4750
6. recién entonces `TRADING_ENGINE_READY`

Idempotencia: `processed_bars` + keys en signals/orders/fills. Reconectar **no** inventa un trade.

Watchdog: si el mercado ETH está abierto y no hay barras nuevas → `MARKET_DATA_STALE`, se bloquean **entradas** (las salidas de sesión/SMA siguen pudiendo ejecutarse sobre barras reales cuando vuelvan).

---

## Dónde están los datos

| Recurso | Local | Railway |
|--------|--------|---------|
| SQLite | `data/paper_trading.db` | `/data/trading.db` |
| Logs | `logs/` | `/data/logs/` |
| Reports | `reports/` | `/data/reports/` |

Tablas: `bars`, `signals`, `orders`, `fills`, `trades`, `positions`, `account_snapshots`, `system_events`, `processed_bars`, `worker_lease`, `meta`.

---

## Tests

```bash
source .venv/bin/activate
export PYTHONPATH=.
pytest backend/tests -q
```

Sanity 2024 (no optimiza; solo compara contra NinjaTrader):

```bash
python backend/scripts/sanity_check.py --force-mock
python backend/scripts/sanity_check.py --year 2024   # requiere Databento
```

---

## Estrategia congelada

| Parámetro | Valor |
|----------|-------|
| SMA | 4750 |
| Band | 50 price points |
| Direction | LONG ONLY |
| Entries per direction | 1 |
| Calculate | On bar close |
| Stop / TP / Trail | NONE |
| Exit on session close | TRUE (30s) |
| Slippage | 1 tick |
| Commission | $0.62 / side / contract |
| MNQ tick | 0.25 pts · $0.50 / tick · $2 / point |

`TRADING_MODE` solo acepta `PAPER`. No hay ruta de órdenes live.

Checklist humano mínimo: `USER_PENDING.md`.  
Decisiones técnicas: `DECISION_LOG.md`.
