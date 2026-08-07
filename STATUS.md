# STATUS

Updated: 2026-08-07

## COMPLETED

- [x] Paper engine congelado (SMA4750 / Band50 / LONG ONLY)
- [x] Worker 24/7 independiente de HTTP
- [x] FastAPI: `/health` `/status` `/account` `/position` `/trades` (+ `/api/*`)
- [x] Dashboard React (horas Argentina)
- [x] SQLite persistente + path `/data/trading.db` para Railway
- [x] Singleton lease + `replicas = 1`
- [x] Auto-recovery + exponential backoff + backfill
- [x] Watchdog `MARKET_DATA_STALE` (bloquea entradas)
- [x] Startup validation → `TRADING_ENGINE_READY`
- [x] Dockerfile + railway.json + Procfile + nixpacks.toml
- [x] `.env.example` completo
- [x] README con guía Railway paso a paso
- [x] Tests ampliados (lock, watchdog, stale entries, TZ)

## IN PROGRESS

- [ ] Deploy Railway (requiere tu login + volume + API key)

Repo: https://github.com/Facuvillegass/IQ_Trader_Bot

## BLOCKED (humano)

- [ ] Cuenta Railway + conectar repo + Volume `/data`
- [ ] Databento API key en variables de Railway (o `DATA_PROVIDER=mock`)
- [ ] Sanity check 2024 con feed real

Ver `USER_PENDING.md`.
