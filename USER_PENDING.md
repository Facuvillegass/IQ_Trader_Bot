# USER PENDING

Solo lo que **vos** tenés que hacer.

---

## Listo de tu lado (parcial)

- [x] GitHub sync: repo [Facuvillegass/IQ_Trader_Bot](https://github.com/Facuvillegass/IQ_Trader_Bot) en `main` (código pusheado)
- [x] Databento API key recibida (guardada en `.env` local — **no** en git)

## Falta (bloquea el 24/7)

- [ ] Login en Railway: https://railway.app → **Login with GitHub** (`Facuvillegass`)
- [ ] En esta Mac (opcional pero útil): `railway login` en Terminal
- [ ] New Project → Deploy from GitHub → elegir `IQ_Trader_Bot`
- [ ] Variables (pegar en Railway → Variables):

```
TRADING_MODE=PAPER
DATA_PROVIDER=databento
DATABENTO_API_KEY=<tu key de Databento>
DATA_API_KEY=<tu key de Databento>
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

- [ ] Volume: Settings → Volumes → Mount path **`/data`**
- [ ] Generate Domain → abrir `/health` y confirmar `healthy`
- [ ] Replicas = 1 (ya viene en `railway.json`)

## Seguridad

La API key se pegó en el chat. Si el repo es público, **no** la subas al código. Si querés rotarla: Databento portal → regenerar key → actualizar Railway Variables.
