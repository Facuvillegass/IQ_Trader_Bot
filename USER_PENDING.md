# USER PENDING

Solo lo que **vos** tenés que hacer. El código, Docker, lock, watchdog y health ya están listos.

---

## Railway 24/7 (objetivo)

- [ ] Crear cuenta en [Railway](https://railway.app) (login con GitHub `Facuvillegass`)
- [ ] Crear cuenta en [Databento](https://databento.com) y copiar la API key
- [ ] En Railway → tu proyecto `iq-trader-bot` → Variables, pegar:

```
TRADING_MODE=PAPER
DATA_PROVIDER=databento
DATABENTO_API_KEY=pegá_tu_key
DATA_API_KEY=pegá_tu_key
DATABASE_PATH=/data/trading.db
LOG_DIR=/data/logs
REPORTS_DIR=/data/reports
TZ_DISPLAY=America/Argentina/Cordoba
INITIAL_BALANCE=10000
MNQ_QUANTITY=1
SMA_PERIOD=4750
BAND_POINTS=50
SLIPPAGE_TICKS=1
EMBED_WORKER=true
```

- [ ] Añadir un **Volume** montado en `/data` (Settings → Volumes → Mount path `/data`)
- [ ] Conectar el repo GitHub `Facuvillegass/IQ_Trader_Bot` y Deploy
- [ ] Abrir la URL pública → `/health` debe decir `"status": "healthy"` o `"starting"` y después healthy
- [ ] Confirmar `numReplicas = 1` (ya viene en `railway.json`; no lo subas a 2)

---

## Si todavía no hay Databento

Podés deployar igual con:

```
DATA_PROVIDER=mock
```

El worker corre 24/7 y el dashboard funciona. Cambiá a `databento` cuando tengas la key y redeploy.

---

## No hace falta que hagas

- Escribir Dockerfile / Procfile / railway.json
- Configurar SMA, band, slippage o comisiones
- Instalar Python/Node en Railway
- Activar live trading
- Crear la base de datos
