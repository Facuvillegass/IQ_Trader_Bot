import './Chucru.css'

const TOC = [
  { id: 'que-es', label: '1. ¿De qué va esto?' },
  { id: 'futuros', label: '2. ¿Qué es un futuro?' },
  { id: 'mnq', label: '3. ¿Qué es el MNQ?' },
  { id: 'paper', label: '4. Paper trading' },
  { id: 'estrategia', label: '5. La estrategia (congelada)' },
  { id: 'sma', label: '6. SMA y la banda de 50' },
  { id: 'senales', label: '7. Cómo decide comprar o vender' },
  { id: 'backtest', label: '8. Del backtest al forward test' },
  { id: 'sistema', label: '9. Qué construimos' },
  { id: 'railway', label: '10. Por qué corre 24/7 en la nube' },
  { id: 'dashboard', label: '11. Cómo leer el dashboard' },
  { id: 'riesgos', label: '12. Qué NO significa esto' },
]

function Step({ id, num, title, children }) {
  return (
    <section className="chucru-step" id={id}>
      <h2>
        <span className="chucru-step-num">{num}</span>
        {title}
      </h2>
      <div className="chucru-prose">{children}</div>
    </section>
  )
}

export default function Chucru() {
  return (
    <div className="chucru">
      <header className="chucru-hero">
        <p className="chucru-kicker">Guía para principiantes</p>
        <h1>Chucru</h1>
        <p className="chucru-lead">
          Esta página explica el proyecto <strong>MNQ Paper Desk</strong> como si
          nunca hubieras operado en mercados. Sin jerga innecesaria. Paso a paso.
        </p>
      </header>

      <nav className="chucru-toc" aria-label="Índice">
        <p className="chucru-toc-title">Índice</p>
        <ol>
          {TOC.map((item) => (
            <li key={item.id}>
              <a href={`#${item.id}`}>{item.label}</a>
            </li>
          ))}
        </ol>
      </nav>

      <Step id="que-es" num="1" title="¿De qué va esto?">
        <p>
          Imaginate que alguien inventó una <em>regla automática</em> para
          decidir cuándo comprar y cuándo vender un producto financiero muy
          específico (el MNQ). Esa regla ya se probó con datos del pasado
          (años 2020–2026) en un software llamado NinjaTrader.
        </p>
        <p>
          Ahora la pregunta ya no es “¿podemos inventar una regla mejor?”.
          La pregunta es:
        </p>
        <blockquote>
          Si desde ahora dejo esta regla corriendo sola, con dinero{' '}
          <strong>falso</strong> (una cuenta virtual de USD 10.000) y 1 contrato
          MNQ… ¿qué pasa realmente con la cuenta?
        </blockquote>
        <p>
          Eso se llama <strong>forward test</strong> o{' '}
          <strong>paper trading en tiempo real</strong>: el sistema opera hacia
          adelante, sin reescribir el pasado y sin cambiar las reglas.
        </p>
      </Step>

      <Step id="futuros" num="2" title="¿Qué es un futuro? (versión simple)">
        <p>
          Un <strong>futuro</strong> es un contrato: “me comprometo a comprar o
          vender algo a un precio acordado en una fecha futura”.
        </p>
        <p>
          En la práctica, la mayoría de la gente no espera a esa fecha: compra y
          vende el contrato antes, para ganar (o perder) con el movimiento del
          precio.
        </p>
        <div className="chucru-callout">
          <strong>Analogía:</strong> es como apostar al precio de algo (petróleo,
          oro, un índice de acciones) usando un contrato estandarizado, con
          reglas claras de tamaño y horario.
        </div>
        <p>
          Importante: los futuros se pueden operar “a favor” (comprar primero =
          LONG) o “en contra” (vender primero = SHORT).{' '}
          <strong>Este proyecto solo hace LONG</strong>: solo compra y después
          vende para cerrar. Nunca apuesta a la baja.
        </p>
      </Step>

      <Step id="mnq" num="3" title="¿Qué es el MNQ?">
        <p>
          <strong>MNQ</strong> significa <em>Micro E-mini Nasdaq-100 Futures</em>.
          En criollo: un contrato pequeño que sigue el índice Nasdaq-100 (las
          grandes tecnológicas de EE.UU.).
        </p>
        <ul>
          <li>
            <strong>Micro</strong> = versión chica (más barata de “mover” que el
            contrato grande NQ).
          </li>
          <li>
            Cada <strong>1 punto</strong> de precio del MNQ vale{' '}
            <strong>USD 2</strong> por contrato.
          </li>
          <li>
            El precio se mueve de a <strong>0,25 puntos</strong> (un “tick”).
            Cada tick vale <strong>USD 0,50</strong>.
          </li>
        </ul>
        <p>
          Ejemplo: si comprás a 20.000 y vendés a 20.010, ganaste 10 puntos ×
          $2 = <strong>$20</strong> (antes de comisiones), con 1 contrato.
        </p>
        <p>
          En este experimento siempre operamos <strong>1 solo contrato</strong>.
          No se suma posición. No se “multiplica”.
        </p>
      </Step>

      <Step id="paper" num="4" title="Paper trading: dinero de mentira, reglas de verdad">
        <p>
          <strong>Paper trading</strong> = simulación. La cuenta empieza en USD
          10.000, pero <strong>no es dinero real</strong>. No se envían órdenes a
          un broker con plata de verdad.
        </p>
        <p>¿Para qué sirve entonces?</p>
        <ul>
          <li>Ver si la estrategia se porta bien <em>después</em> del estudio.</li>
          <li>Detectar problemas reales: datos, horarios, reinicios, costos.</li>
          <li>
            Acumular un historial limpio, sin “arreglar” trades malos a mano.
          </li>
        </ul>
        <div className="chucru-callout warn">
          El sistema está bloqueado en modo <strong>PAPER</strong>. No puede
          operar live “por accidente”.
        </div>
      </Step>

      <Step id="estrategia" num="5" title="La estrategia (congelada: no se toca)">
        <p>
          Pensá la estrategia como una receta de cocina ya escrita. No
          improvisamos ingredientes.
        </p>
        <table className="chucru-table">
          <tbody>
            <tr>
              <th>Timeframe</th>
              <td>Velas de 1 minuto</td>
            </tr>
            <tr>
              <th>Dirección</th>
              <td>Solo LONG (comprar)</td>
            </tr>
            <tr>
              <th>Indicador</th>
              <td>SMA de 4750 velas</td>
            </tr>
            <tr>
              <th>Banda</th>
              <td>50 puntos de precio (no ticks)</td>
            </tr>
            <tr>
              <th>Cuándo decide</th>
              <td>Al cierre de cada vela de 1 minuto</td>
            </tr>
            <tr>
              <th>Stop loss / take profit</th>
              <td>No usa. Solo la regla SMA ± banda</td>
            </tr>
            <tr>
              <th>Cantidad</th>
              <td>1 MNQ</td>
            </tr>
          </tbody>
        </table>
        <p>
          “Congelada” significa: <strong>no optimizamos</strong>, no buscamos
          mejores números, no cambiamos 4750 ni 50 porque “esta semana fue mala”.
        </p>
      </Step>

      <Step id="sma" num="6" title="SMA y la banda de 50 (con dibujo mental)">
        <p>
          <strong>SMA</strong> = Simple Moving Average = promedio simple del
          precio de cierre de las últimas N velas.
        </p>
        <p>
          Acá N = <strong>4750</strong>. O sea: el promedio de los últimos 4750
          minutos (de mercado) del MNQ.
        </p>
        <p>Alrededor de ese promedio dibujamos una “franja”:</p>
        <ul>
          <li>
            Línea de arriba (entrada): <code>SMA + 50</code>
          </li>
          <li>
            Línea de abajo (salida): <code>SMA − 50</code>
          </li>
        </ul>
        <div className="chucru-diagram" aria-hidden="true">
          <div className="chucru-diagram-line up">Entrada si el cierre queda arriba → SMA + 50</div>
          <div className="chucru-diagram-line mid">SMA (promedio de 4750 cierres)</div>
          <div className="chucru-diagram-line down">Salida si el cierre queda abajo → SMA − 50</div>
        </div>
        <p>
          No usamos “cruces” mágicos del estilo “recién ahora atraviesa la
          línea”. Usamos <strong>estado / nivel</strong>:
        </p>
        <ul>
          <li>
            Si estás <strong>afuera</strong> (FLAT) y el cierre está{' '}
            <em>por encima</em> de SMA+50 → señal de comprar.
          </li>
          <li>
            Si estás <strong>adentro</strong> (LONG) y el cierre está{' '}
            <em>por debajo</em> de SMA−50 → señal de vender (cerrar).
          </li>
          <li>
            Si ya estás LONG y el precio sigue arriba →{' '}
            <strong>no comprás de nuevo</strong>.
          </li>
        </ul>
      </Step>

      <Step id="senales" num="7" title="Cómo decide comprar o vender, minuto a minuto">
        <ol className="chucru-steps-list">
          <li>Llega una vela de 1 minuto ya cerrada (open, high, low, close).</li>
          <li>Se recalcula la SMA con los últimos 4750 cierres.</li>
          <li>Se mira el estado: ¿FLAT o LONG?</li>
          <li>Se aplica la regla de arriba.</li>
          <li>
            Si hay señal, se simula una orden de mercado con:
            <ul>
              <li>1 tick de slippage (el fill no es perfecto)</li>
              <li>comisión de referencia ≈ USD 0,62 por lado</li>
            </ul>
          </li>
          <li>
            Todo queda registrado: señal, orden, fill, trade, equity.
          </li>
        </ol>
        <p>
          Además, cerca del cierre diario de la sesión extendida de futuros
          (alrededor de las 16:00 hora de Chicago), si hay posición abierta, el
          sistema la cierra. Eso imita “Exit on session close”.
        </p>
      </Step>

      <Step id="backtest" num="8" title="Del backtest al forward test">
        <p>
          <strong>Backtest</strong> = “¿qué habría pasado si operaba esta regla
          en el pasado?”. Ya se hizo en NinjaTrader. Año por año dio números
          (ganancia, drawdown, cantidad de trades). Eso fue la investigación.
        </p>
        <p>
          <strong>Forward test</strong> = “¿qué pasa de ahora en más, en vivo,
          sin mirar el futuro?”.
        </p>
        <ul>
          <li>No se fabrican trades anteriores a la puesta en marcha.</li>
          <li>No se borran trades malos.</li>
          <li>No se cambian parámetros porque el PnL molesta.</li>
        </ul>
        <p>
          La cuenta virtual empezó cuando el sistema quedó realmente operativo
          (no el 7 de agosto “de mentira” si el motor todavía no corría).
        </p>
      </Step>

      <Step id="sistema" num="9" title="Qué construimos (las piezas)">
        <p>El proyecto es como una fábrica con varias estaciones:</p>
        <ol className="chucru-steps-list">
          <li>
            <strong>Datos de mercado</strong> — barras MNQ de 1 minuto (Databento
            en la nube; mock en pruebas locales).
          </li>
          <li>
            <strong>Motor de estrategia</strong> — calcula SMA, genera señales.
          </li>
          <li>
            <strong>Simulador de ejecución</strong> — convierte señales en fills
            paper con costos.
          </li>
          <li>
            <strong>Contabilidad</strong> — balance, equity, drawdown, trades.
          </li>
          <li>
            <strong>Base SQLite</strong> — guarda todo en disco persistente para
            poder reiniciar sin perder la historia.
          </li>
          <li>
            <strong>API + dashboard</strong> — lo que estás viendo ahora.
          </li>
        </ol>
        <p>
          Hay protecciones importantes: un solo worker activo (no dos cerebros
          operando la misma cuenta), recuperación si se cae internet, y un
          “watchdog” que no deja entrar si los datos están viejos/stale.
        </p>
      </Step>

      <Step id="railway" num="10" title="Por qué corre 24/7 en la nube">
        <p>
          Si el bot solo corriera en una Mac, al cerrar la tapa… se apaga el
          experimento. Por eso vive en <strong>Railway</strong>: un servidor en
          internet que sigue despierto.
        </p>
        <ul>
          <li>Worker + API + dashboard en un mismo servicio.</li>
          <li>
            Disco persistente en <code>/data</code> (la base no se borra en cada
            redeploy).
          </li>
          <li>Replicas = 1 (un solo proceso operando).</li>
        </ul>
        <p>
          Podés cerrar tu computadora. El forward test sigue. Después abrís el
          link del dashboard desde el celu o cualquier navegador.
        </p>
      </Step>

      <Step id="dashboard" num="11" title="Cómo leer la pestaña Desk">
        <ul>
          <li>
            <strong>Account</strong> — plata virtual: balance, equity, PnL,
            drawdown (cuánto bajó desde el pico).
          </li>
          <li>
            <strong>Strategy</strong> — precio actual, SMA, umbrales de entrada
            y salida, si estás FLAT o LONG.
          </li>
          <li>
            <strong>Performance</strong> — estadísticas de trades cerrados (wins,
            losses, profit factor…).
          </li>
          <li>
            <strong>Equity curve</strong> — el dibujo de cómo evoluciona la
            cuenta en el tiempo.
          </li>
          <li>
            <strong>Trades</strong> — cada operación histórica, con precios y
            motivo de salida.
          </li>
        </ul>
        <p>
          Las horas del dashboard se muestran en{' '}
          <strong>hora Argentina</strong>. Por dentro, el sistema guarda todo en
          UTC (un reloj mundial estándar).
        </p>
      </Step>

      <Step id="riesgos" num="12" title="Qué NO significa este experimento">
        <ul>
          <li>
            <strong>No</strong> es una promesa de ganancias.
          </li>
          <li>
            <strong>No</strong> es dinero real (todavía). Paper only.
          </li>
          <li>
            Un buen backtest <strong>no garantiza</strong> el futuro.
          </li>
          <li>
            Costos, datos y horarios reales pueden diferir un poco de
            NinjaTrader.
          </li>
          <li>
            Si ves un drawdown grande: forma parte de observar la estrategia tal
            cual es, no de “arreglarla” a mitad de camino.
          </li>
        </ul>
        <div className="chucru-callout">
          El objetivo de Chucru es que cualquiera entienda <em>qué</em> estamos
          midiendo y <em>por qué</em> no tocamos los parámetros. La pestaña Desk
          es el tablero en vivo; esta página es el manual.
        </div>
      </Step>

      <footer className="chucru-footer">
        <p>
          Estrategia congelada: SMA 4750 · Band 50 · LONG only · 1 MNQ · On bar
          close · PAPER
        </p>
      </footer>
    </div>
  )
}
