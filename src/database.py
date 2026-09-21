import sqlite3
import os
from typing import Dict, List, Optional


def default_db_path() -> str:
    env_path = os.environ.get("TRADE_DB_PATH")
    if env_path:
        return env_path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, "trading_brain.db")


class TradeDatabase:
    def __init__(self, db_path: str = None):
        self.db_url = os.environ.get("DATABASE_URL")
        self.is_postgres = bool(self.db_url and self.db_url.startswith("postgres"))
        self.db_path = db_path or default_db_path()

        if self.is_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.psycopg2 = psycopg2
            self.RealDictCursor = RealDictCursor

        self._init_db()

    def _get_connection(self):
        if self.is_postgres:
            conn = self.psycopg2.connect(self.db_url)
            return conn, conn.cursor(cursor_factory=self.RealDictCursor)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn, conn.cursor()

    def _execute(self, cursor, query, params=()):
        if self.is_postgres:
            query = query.replace("?", "%s")
            query = query.replace("AUTOINCREMENT", "")
            query = query.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
            query = query.replace("DATETIME", "TIMESTAMP")
        cursor.execute(query, params)

    def _as_dict(self, row) -> Optional[Dict]:
        if row is None:
            return None
        return dict(row)

    def _scalar(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return next(iter(row.values()))
        try:
            return row["count"]
        except (KeyError, IndexError, TypeError):
            return row[0]

    def _column_names(self, cursor, table: str) -> set:
        if self.is_postgres:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (table,),
            )
            return {self._as_dict(r)["column_name"] for r in cursor.fetchall()}
        cursor.execute(f"PRAGMA table_info({table})")
        return {self._as_dict(r)["name"] for r in cursor.fetchall()}

    def _init_db(self):
        conn, cursor = self._get_connection()

        self._execute(cursor, '''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                match_name TEXT NOT NULL,
                bet_on TEXT NOT NULL,
                placed_odds REAL NOT NULL,
                true_prob_at_placement REAL NOT NULL,
                ev_at_placement REAL NOT NULL,
                stake REAL NOT NULL,
                status TEXT DEFAULT 'OPEN',
                closing_odds REAL,
                closing_true_prob REAL,
                clv_percentage REAL,
                outcome TEXT DEFAULT 'PENDING',
                profit_loss REAL DEFAULT 0.0,
                exchange_order_id TEXT,
                sport_key TEXT,
                mode TEXT DEFAULT 'live',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self._execute(cursor, '''
            CREATE TABLE IF NOT EXISTS system_params (
                id INTEGER PRIMARY KEY,
                min_ev_threshold REAL DEFAULT 0.02,
                kelly_fraction REAL DEFAULT 0.25,
                bankroll REAL DEFAULT 1000.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        existing = self._column_names(cursor, "trades")
        if "sport_key" not in existing:
            self._execute(cursor, "ALTER TABLE trades ADD COLUMN sport_key TEXT")
        if "mode" not in existing:
            self._execute(cursor, "ALTER TABLE trades ADD COLUMN mode TEXT DEFAULT 'live'")

        param_cols = self._column_names(cursor, "system_params")
        if "bankroll" not in param_cols:
            self._execute(cursor, "ALTER TABLE system_params ADD COLUMN bankroll REAL DEFAULT 1000.0")
            self._execute(cursor, "UPDATE system_params SET bankroll = 1000.0 WHERE bankroll IS NULL")

        self._execute(cursor, "SELECT COUNT(*) as count FROM system_params")
        count = self._scalar(cursor.fetchone()) or 0

        if count == 0:
            self._execute(cursor, "INSERT INTO system_params (id) VALUES (1)")

        conn.commit()
        conn.close()

    def log_trade(
        self,
        event_id: str,
        match_name: str,
        bet_on: str,
        placed_odds: float,
        true_prob: float,
        ev: float,
        stake: float,
        exchange_order_id: str = None,
        sport_key: str = None,
        mode: str = "live",
    ) -> int:
        conn, cursor = self._get_connection()

        query = '''
            INSERT INTO trades (
                event_id, match_name, bet_on, placed_odds, true_prob_at_placement,
                ev_at_placement, stake, exchange_order_id, sport_key, mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            event_id, match_name, bet_on, placed_odds, true_prob, ev, stake,
            exchange_order_id, sport_key, mode or "live",
        )
        if self.is_postgres:
            query = query.replace("?", "%s") + " RETURNING id"
            cursor.execute(query, params)
            trade_id = self._as_dict(cursor.fetchone())["id"]
        else:
            cursor.execute(query, params)
            trade_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return trade_id

    def update_closing_line(self, trade_id: int, closing_odds: float, closing_true_prob: float):
        conn, cursor = self._get_connection()

        self._execute(cursor, "SELECT placed_odds FROM trades WHERE id = ?", (trade_id,))
        row = self._as_dict(cursor.fetchone())
        if not row:
            conn.close()
            raise ValueError(f"Trade ID {trade_id} not found.")

        placed_odds = row["placed_odds"]
        clv_ev = (closing_true_prob * (placed_odds - 1.0)) - (1.0 - closing_true_prob)

        self._execute(cursor, '''
            UPDATE trades
            SET closing_odds = ?, closing_true_prob = ?, clv_percentage = ?, status = 'CLOSED'
            WHERE id = ?
        ''', (closing_odds, closing_true_prob, clv_ev, trade_id))

        conn.commit()
        conn.close()

    def settle_trade(self, trade_id: int, outcome: str, profit_loss: float):
        conn, cursor = self._get_connection()
        self._execute(cursor, '''
            UPDATE trades
            SET outcome = ?, profit_loss = ?
            WHERE id = ?
        ''', (outcome, profit_loss, trade_id))
        conn.commit()
        conn.close()

    def get_system_params(self) -> Dict:
        conn, cursor = self._get_connection()
        self._execute(
            cursor,
            "SELECT min_ev_threshold, kelly_fraction, bankroll FROM system_params WHERE id = 1",
        )
        row = self._as_dict(cursor.fetchone())
        conn.close()
        if not row:
            return {"min_ev_threshold": 0.02, "kelly_fraction": 0.25, "bankroll": 1000.0}
        return {
            "min_ev_threshold": row["min_ev_threshold"],
            "kelly_fraction": row["kelly_fraction"],
            "bankroll": float(row.get("bankroll") if row.get("bankroll") is not None else 1000.0),
        }

    def update_system_params(self, new_min_ev: float, new_kelly: float):
        conn, cursor = self._get_connection()
        self._execute(cursor, '''
            UPDATE system_params
            SET min_ev_threshold = ?, kelly_fraction = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (new_min_ev, new_kelly))
        conn.commit()
        conn.close()

    def adjust_bankroll(self, delta: float) -> float:
        conn, cursor = self._get_connection()
        self._execute(cursor, "SELECT bankroll FROM system_params WHERE id = 1")
        row = self._as_dict(cursor.fetchone())
        current = float(row["bankroll"]) if row and row.get("bankroll") is not None else 1000.0
        updated = round(max(0.0, current + float(delta)), 2)
        self._execute(cursor, "UPDATE system_params SET bankroll = ? WHERE id = 1", (updated,))
        conn.commit()
        conn.close()
        return updated

    def get_performance(self) -> Dict:
        closed = self.get_all_closed_trades()
        settled = [t for t in closed if t.get("outcome") in ("WON", "LOST", "PUSH")]
        pnl = sum(float(t.get("profit_loss") or 0) for t in settled)
        staked = sum(float(t.get("stake") or 0) for t in settled)
        wins = sum(1 for t in settled if t.get("outcome") == "WON")
        losses = sum(1 for t in settled if t.get("outcome") == "LOST")
        return {
            "realized_pnl": round(pnl, 2),
            "total_staked": round(staked, 2),
            "settled_trades": len(settled),
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / len(settled)) if settled else 0.0,
            "roi": (pnl / staked) if staked else 0.0,
        }

    def reset_paper_book(self, bankroll: float = 1000.0):
        conn, cursor = self._get_connection()
        self._execute(cursor, "DELETE FROM trades")
        self._execute(
            cursor,
            """
            UPDATE system_params
            SET min_ev_threshold = 0.02, kelly_fraction = 0.25, bankroll = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (bankroll,),
        )
        conn.commit()
        conn.close()

    def has_trade(self, event_id: str, bet_on: str) -> bool:
        conn, cursor = self._get_connection()
        self._execute(
            cursor,
            "SELECT id FROM trades WHERE event_id = ? AND bet_on = ? LIMIT 1",
            (event_id, bet_on),
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def has_event_position(self, event_id: str) -> bool:
        conn, cursor = self._get_connection()
        self._execute(
            cursor,
            "SELECT id FROM trades WHERE event_id = ? LIMIT 1",
            (event_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def get_open_trades(self) -> List[Dict]:
        conn, cursor = self._get_connection()
        self._execute(cursor, "SELECT * FROM trades WHERE status = 'OPEN'")
        rows = cursor.fetchall()
        conn.close()
        return [self._as_dict(row) for row in rows]

    def get_all_closed_trades(self) -> List[Dict]:
        conn, cursor = self._get_connection()
        self._execute(cursor, "SELECT * FROM trades WHERE status = 'CLOSED'")
        rows = cursor.fetchall()
        conn.close()
        return [self._as_dict(row) for row in rows]


if __name__ == "__main__":
    print("Testing Database Initialization...")
    db = TradeDatabase("test_brain.db")
    print("Logging a mock trade...")
    t_id = db.log_trade("evt_123", "Lakers vs Warriors", "Lakers", 2.10, 0.50, 0.05, 12.50, "mock_order_123")
    print(f"Updating trade {t_id} with Closing Line Value...")
    db.update_closing_line(t_id, 1.95, 0.53)
    trades = db.get_all_closed_trades()
    print(f"Recorded CLV Percentage: {trades[0]['clv_percentage'] * 100:.2f}%")
    if os.path.exists("test_brain.db"):
        os.remove("test_brain.db")
