from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone, date
from pathlib import Path
import sqlite3
import pandas as pd
import config
from data import validate


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, shift_date TEXT NOT NULL,
      product TEXT NOT NULL, team TEXT NOT NULL, target REAL NOT NULL, smv REAL NOT NULL,
      workers REAL NOT NULL, overtime REAL NOT NULL, bonus REAL NOT NULL, idle REAL NOT NULL,
      actual REAL NOT NULL)""")
    return db


def save_log(row: dict, path=config.DB) -> int:
    values = validate(row, actual=True)
    for key in ("product", "team"):
        if not isinstance(row.get(key), str) or not row[key].strip() or len(row[key]) > 200:
            raise ValueError("LỖI: Tên sản phẩm và tên tổ cần từ 1 đến 200 ký tự.")
    try:
        shift_date = date.fromisoformat(row["shift_date"]).isoformat()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("LỖI: Ngày ca không hợp lệ.") from exc
    with closing(connect(path)) as db, db:
        cursor = db.execute("""INSERT INTO logs
            (created_at,shift_date,product,team,target,smv,workers,overtime,bonus,idle,actual)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [datetime.now(timezone.utc).isoformat(), shift_date,
            row["product"].strip(), row["team"].strip(), *[values[k] for k in config.FEATURES], values["actual"]])
        return cursor.lastrowid


def read_logs(path=config.DB, team: str = "", start: str = "", end: str = "") -> pd.DataFrame:
    clauses, args = [], []
    for clause, value in [("team = ?", team), ("shift_date >= ?", start), ("shift_date <= ?", end)]:
        if value:
            clauses.append(clause)
            args.append(value)
    sql = "SELECT * FROM logs" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY id"
    with closing(connect(path)) as db:
        return pd.read_sql_query(sql, db, params=args)
