import sqlite3, time, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "study.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS session(
      id TEXT PRIMARY KEY,
      created_at INTEGER NOT NULL,
      user_agent TEXT,
      ip_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS pre_survey(
      session_id TEXT PRIMARY KEY,
      q1 TEXT,
      q2 INTEGER,
      q3 TEXT,   -- JSON array string
      q4 TEXT,   -- JSON array string
      q5 INTEGER,
      q6 TEXT,
      FOREIGN KEY(session_id) REFERENCES session(id)
    );

    CREATE TABLE IF NOT EXISTS puzzle_metrics(
      id TEXT PRIMARY KEY,
      session_id TEXT,
      puzzle_id TEXT,
      time_ms INTEGER,
      undos INTEGER,
      initial_rating INTEGER,
      FOREIGN KEY(session_id) REFERENCES session(id)
    );

    CREATE TABLE IF NOT EXISTS post_per_puzzle(
      id TEXT PRIMARY KEY,
      session_id TEXT,
      puzzle_id TEXT,
      final_rating INTEGER,
      reason_text TEXT,
      guess_bucket TEXT,
      FOREIGN KEY(session_id) REFERENCES session(id)
    );

    CREATE TABLE IF NOT EXISTS post_overall(
      session_id TEXT PRIMARY KEY,
      strategies TEXT,  -- JSON array string
      difficulty_signal TEXT,
      FOREIGN KEY(session_id) REFERENCES session(id)
    );
    """)
    conn.commit()
    return conn
