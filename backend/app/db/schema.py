"""SQLite schema — append-oriented historical tables."""

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL UNIQUE,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    symbol TEXT NOT NULL DEFAULT 'MNQ',
    source TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bars_ts ON bars(ts);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    bar_ts TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    position_before TEXT NOT NULL,
    close_price REAL NOT NULL,
    sma REAL,
    entry_threshold REAL,
    exit_threshold REAL,
    band_points REAL NOT NULL,
    sma_period INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    signal_id INTEGER,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'MARKET',
    quantity INTEGER NOT NULL,
    signal_price REAL NOT NULL,
    status TEXT NOT NULL,
    tif TEXT NOT NULL DEFAULT 'GTC',
    created_at TEXT NOT NULL,
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    order_id INTEGER NOT NULL,
    fill_ts TEXT NOT NULL,
    fill_price REAL NOT NULL,
    signal_price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    side TEXT NOT NULL,
    slippage_ticks INTEGER NOT NULL,
    slippage_cost REAL NOT NULL,
    commission REAL NOT NULL,
    commission_normalized REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_signal_time TEXT,
    entry_time TEXT NOT NULL,
    entry_signal_price REAL,
    entry_fill_price REAL NOT NULL,
    exit_signal_time TEXT,
    exit_time TEXT,
    exit_signal_price REAL,
    exit_fill_price REAL,
    quantity INTEGER NOT NULL,
    gross_pnl REAL,
    commission REAL,
    commission_normalized REAL,
    slippage_cost REAL,
    net_pnl REAL,
    net_pnl_normalized REAL,
    balance_after REAL,
    equity_after REAL,
    exit_reason TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT 'FLAT',
    quantity INTEGER NOT NULL DEFAULT 0,
    entry_time TEXT,
    entry_price REAL,
    entry_signal_time TEXT,
    entry_signal_price REAL,
    open_trade_id INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cash_balance REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    equity REAL NOT NULL,
    peak_equity REAL NOT NULL,
    drawdown REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    commissions REAL NOT NULL,
    slippage_cost REAL NOT NULL,
    open_position TEXT NOT NULL,
    reason TEXT,
    UNIQUE(ts, reason)
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_bars (
    bar_ts TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_lease (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    owner_id TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL
);
"""
