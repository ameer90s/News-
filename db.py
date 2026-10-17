from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Any

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
IS_VERCEL = bool(os.getenv("VERCEL"))

# Local fallback only. On Vercel without DATABASE_URL, /tmp is writable but ephemeral.
_LOCAL_DB = Path(__file__).resolve().parent.parent / "newsroom.db"
_VERCEL_TMP_DB = Path("/tmp/newsroom.db")
DB_PATH = _VERCEL_TMP_DB if IS_VERCEL else _LOCAL_DB


def database_backend() -> str:
    """Return the active persistence backend."""
    return "postgresql" if DATABASE_URL else ("sqlite-ephemeral" if IS_VERCEL else "sqlite")


@contextmanager
def get_conn() -> Iterator[Any]:
    """Open a database connection.

    Production: Postgres when DATABASE_URL is supplied (e.g. Neon on Vercel).
    Local dev: SQLite when DATABASE_URL is absent.
    """
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    if DATABASE_URL:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                domain TEXT,
                seen_at TEXT,
                source_country TEXT,
                topic TEXT,
                scope TEXT,
                fetched_at TIMESTAMPTZ NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles (fetched_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles (topic)",
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id BIGSERIAL PRIMARY KEY,
                topic TEXT NOT NULL,
                hours INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots (created_at DESC)",
        ]
        with get_conn() as conn:
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                domain TEXT,
                seen_at TEXT,
                source_country TEXT,
                topic TEXT,
                scope TEXT,
                fetched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles (fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles (topic);

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                hours INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots (created_at DESC);
            """
        )


def save_articles(rows: Iterable[dict], fetched_at: str) -> None:
    payload = [{**row, "fetched_at": fetched_at} for row in rows]
    if not payload:
        return

    if DATABASE_URL:
        query = """
            INSERT INTO articles (url, title, domain, seen_at, source_country, topic, scope, fetched_at)
            VALUES (%(url)s, %(title)s, %(domain)s, %(seen_at)s, %(source_country)s, %(topic)s, %(scope)s, %(fetched_at)s)
            ON CONFLICT(url) DO UPDATE SET
                title = EXCLUDED.title,
                domain = EXCLUDED.domain,
                seen_at = EXCLUDED.seen_at,
                source_country = EXCLUDED.source_country,
                topic = EXCLUDED.topic,
                scope = EXCLUDED.scope,
                fetched_at = EXCLUDED.fetched_at
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(query, payload)
        return

    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO articles (url, title, domain, seen_at, source_country, topic, scope, fetched_at)
            VALUES (:url, :title, :domain, :seen_at, :source_country, :topic, :scope, :fetched_at)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                domain = excluded.domain,
                seen_at = excluded.seen_at,
                source_country = excluded.source_country,
                topic = excluded.topic,
                scope = excluded.scope,
                fetched_at = excluded.fetched_at
            """,
            payload,
        )


def history_summary(days: int = 90) -> dict:
    days = max(1, min(int(days), 3650))

    if DATABASE_URL:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::BIGINT AS article_count,
                           COUNT(DISTINCT domain)::BIGINT AS source_count,
                           MIN(fetched_at::date) AS oldest,
                           MAX(fetched_at::date) AS newest
                    FROM articles
                    WHERE fetched_at >= NOW() - (%s * INTERVAL '1 day')
                    """,
                    (days,),
                )
                row = cur.fetchone()
                if not row:
                    return {"article_count": 0, "source_count": 0, "oldest": None, "newest": None}
                result = dict(row)
                for key in ("oldest", "newest"):
                    if result.get(key) is not None:
                        result[key] = result[key].isoformat()
                return result

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS article_count,
                   COUNT(DISTINCT domain) AS source_count,
                   MIN(date(fetched_at)) AS oldest,
                   MAX(date(fetched_at)) AS newest
            FROM articles
            WHERE fetched_at >= datetime('now', ?)
            """,
            (f"-{days} days",),
        ).fetchone()
        return dict(row) if row else {"article_count": 0, "source_count": 0, "oldest": None, "newest": None}
