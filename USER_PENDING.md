# USER PENDING

Casi todo está hecho. El sistema **ya corre 24/7 en Railway**.

---

## Hecho

- [x] Railway account: Facundo Villegas (`facundovillegas746@gmail.com`)
- [x] GitHub sync: [Facuvillegass/IQ_Trader_Bot](https://github.com/Facuvillegass/IQ_Trader_Bot) → servicio `IQ_Trader_Bot`
- [x] Databento API key configurada en Railway
- [x] Volume `/data` montado
- [x] Variables de entorno
- [x] Dominio público
- [x] `/health` → **healthy** · worker READY · cuenta $10,000 · PAPER

## Links

- Dashboard: https://iqtraderbot-production.up.railway.app/
- Health: https://iqtraderbot-production.up.railway.app/health
- Status: https://iqtraderbot-production.up.railway.app/status
- Project: https://railway.com/project/a97359fc-edaf-4acb-a434-b44fac6dbb62

## Opcional / revisar en Databento

- [ ] Confirmar en el portal Databento que tenés acceso histórico `GLBX.MDP3` (ya funciona)
- [ ] Si querés barras **en vivo** en sesión ETH (no solo histórico con lag), activá plan/live data en Databento y asegurate de la licencia personal CME
- [ ] Por seguridad: la key se pegó en el chat → conviene **rotarla** en Databento y actualizar la variable en Railway

## Nota de fin de semana

Hoy es sábado: el mercado MNQ está cerrado. La última barra histórica cargada es ~2026-08-05 20:59 ART. El engine está READY y esperará datos nuevos cuando el mercado abra (domingo ~18:00 ART / 17:00 CT) o cuando Databento publique más histórico.
