"""
MRKL Tool 1: csv_sql
Runs read-only SQL queries over the uploaded Citi Bike trip CSV using DuckDB.

Input:  { "sql": string }
Output: { "success": bool, "data": { "rows": [...], "row_count": int, "source": "uploaded.csv" },
          "error"?: string, "source": string, "ts": string }
"""

import datetime
import hashlib
import re
import time
from pathlib import Path
from typing import Any

import duckdb


# Global state — path to the currently uploaded CSV
_current_csv_path: str | None = None


def set_csv_path(path: str) -> None:
    """Called by the API when a new CSV is uploaded."""
    global _current_csv_path
    _current_csv_path = path


def get_csv_path() -> str | None:
    return _current_csv_path


def csv_sql(sql: str) -> dict[str, Any]:
    """
    Run a read-only SQL query over the uploaded CSV.
    The CSV is registered as the table 'trips' in DuckDB.
    """
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    start = time.time()

    if _current_csv_path is None:
        return {
            "success": False,
            "error": "No CSV file uploaded yet.",
            "source": "csv_sql",
            "ts": ts,
        }

    csv_path = Path(_current_csv_path)
    if not csv_path.exists():
        return {
            "success": False,
            "error": f"CSV file not found at path: {_current_csv_path}",
            "source": "csv_sql",
            "ts": ts,
        }

    # Strip accidental wrapping: {SELECT...} or ```sql SELECT...``` or leading/trailing braces
    sql = sql.strip()
    # Remove outer { } that phi3/other models sometimes add
    if sql.startswith("{") and sql.endswith("}"):
        sql = sql[1:-1].strip()
    # Remove markdown code fences
    sql = re.sub(r'^```(?:sql)?\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'```\s*$', '', sql)
    sql = sql.strip()

    # Reject any non-SELECT queries for safety
    normalized = sql.strip().upper()
    if not normalized.startswith("SELECT"):
        return {
            "success": False,
            "error": "Only SELECT queries are allowed.",
            "source": "csv_sql",
            "ts": ts,
        }

    try:
        con = duckdb.connect()
        # Register the CSV as a virtual table named 'trips'
        con.execute(
            f"CREATE VIEW trips AS SELECT * FROM read_csv_auto('{csv_path}', header=True)"
        )
        result = con.execute(sql).fetchdf()
        rows = result.to_dict(orient="records")
        latency = round(time.time() - start, 3)

        return {
            "success": True,
            "data": {
                "rows": rows,
                "row_count": len(rows),
                "source": "uploaded.csv",
            },
            "source": "csv_sql",
            "ts": ts,
            "latency_s": latency,
            "args_hash": hashlib.md5(sql.encode()).hexdigest()[:8],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "source": "csv_sql",
            "ts": ts,
            "latency_s": round(time.time() - start, 3),
        }
