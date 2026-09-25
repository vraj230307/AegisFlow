"""
Auto-ETL Restorer — Mock Market Data Service & SQLite Target Database
Component 1: Mock Environment for HACK-O-OCTO 4.0 (PS01)

Features:
- Deterministic, standalone FastAPI mock service
- GET /market-data: Returns market data records (canonical schema by default; renamed 'price' -> 'last_price' when failure injected)
- POST /inject-failure: Deterministically switches schema to drifted state ('price' -> 'last_price')
- POST /reset: Reverts schema to canonical state ('price')
- GET /status: Introspects mock service status & schema state
- SQLite database target with 'market_records' table and verification utilities
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Database Configuration & Helpers
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "market_data.db"))

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Creates a connection to the target SQLite database with Row mapping."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DB_PATH) -> None:
    """Initializes the target SQLite database schema with the market_records table."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_records (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
        """)
    conn.close()

def clear_db(db_path: str = DB_PATH) -> int:
    """Clears all records from the market_records table."""
    conn = get_db_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM market_records;")
        deleted_count = cursor.rowcount
    conn.close()
    return deleted_count

def insert_records(records: List[Dict[str, Any]], db_path: str = DB_PATH) -> int:
    """Inserts a batch of market records into SQLite."""
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with conn:
        for r in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_records (id, symbol, price, volume, timestamp, ingested_at)
                VALUES (:id, :symbol, :price, :volume, :timestamp, :ingested_at)
                """,
                {
                    "id": r["id"],
                    "symbol": str(r["symbol"]),
                    "price": float(r["price"]),
                    "volume": int(r["volume"]),
                    "timestamp": str(r["timestamp"]),
                    "ingested_at": now_iso
                }
            )
            inserted += 1
    conn.close()
    return inserted

def query_records(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Fetches all records from market_records table."""
    conn = get_db_connection(db_path)
    cursor = conn.execute("SELECT id, symbol, price, volume, timestamp, ingested_at FROM market_records ORDER BY id ASC;")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# Deterministic Mock Data Baseline
# ---------------------------------------------------------------------------
CANONICAL_MARKET_RECORDS: List[Dict[str, Any]] = [
    {
        "id": 101,
        "symbol": "AAPL",
        "price": 182.50,
        "volume": 1250000,
        "timestamp": "2026-09-25T16:00:00Z"
    },
    {
        "id": 102,
        "symbol": "MSFT",
        "price": 420.75,
        "volume": 980000,
        "timestamp": "2026-09-25T16:00:00Z"
    },
    {
        "id": 103,
        "symbol": "GOOGL",
        "price": 175.30,
        "volume": 1150000,
        "timestamp": "2026-09-25T16:00:00Z"
    },
    {
        "id": 104,
        "symbol": "AMZN",
        "price": 188.90,
        "volume": 1420000,
        "timestamp": "2026-09-25T16:00:00Z"
    },
    {
        "id": 105,
        "symbol": "NVDA",
        "price": 124.60,
        "volume": 3200000,
        "timestamp": "2026-09-25T16:00:00Z"
    }
]

# ---------------------------------------------------------------------------
# Mock Server State
# ---------------------------------------------------------------------------
class MockServerState:
    def __init__(self):
        self.failure_injected: bool = False
        self.failure_reason: str = "Field 'price' renamed to 'last_price'"
        self.total_requests: int = 0

state = MockServerState()

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Auto-ETL Restorer - Mock Market Data Service",
    version="1.0.0",
    description="Deterministic Mock REST API for testing and demonstrating autonomous pipeline self-healing."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """Ensure SQLite database and tables exist at startup."""
    init_db()

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "mock-market-api",
        "database": os.path.basename(DB_PATH)
    }

@app.get("/market-data")
def get_market_data(fail: Optional[bool] = Query(None, description="Optional override to force failure mode for this request")):
    """
    Returns market records.
    - Default (Normal): returns records with 'price' field.
    - Drifted (Failure): returns records with 'price' renamed to 'last_price', causing KeyError in naive ETL script.
    """
    state.total_requests += 1
    
    # Determine whether failure mode applies
    should_fail = state.failure_injected if fail is None else fail

    if not should_fail:
        # Return canonical schema
        return [dict(rec) for rec in CANONICAL_MARKET_RECORDS]
    else:
        # Deterministically rename 'price' to 'last_price'
        mutated_records = []
        for rec in CANONICAL_MARKET_RECORDS:
            item = dict(rec)
            price_val = item.pop("price")
            item["last_price"] = price_val
            mutated_records.append(item)
        return mutated_records

@app.post("/inject-failure")
def inject_failure():
    """
    Toggles the failure flag ON.
    The mock API will now return the drifted schema ('last_price' instead of 'price').
    """
    state.failure_injected = True
    return {
        "status": "failure_injected",
        "failure_injected": True,
        "active_schema": "drifted",
        "description": "Field 'price' renamed to 'last_price'",
        "affected_field": {"original": "price", "mutated": "last_price"}
    }

@app.post("/reset")
def reset_schema():
    """
    Reverts the failure flag OFF.
    The mock API returns the canonical schema with 'price'.
    """
    state.failure_injected = False
    return {
        "status": "reset",
        "failure_injected": False,
        "active_schema": "canonical",
        "description": "Reverted to canonical schema with 'price'"
    }

@app.get("/status")
def get_status():
    """Returns the current mock server status, schema state, and sample record."""
    sample = get_market_data()
    return {
        "service": "Auto-ETL Restorer Mock Service",
        "failure_injected": state.failure_injected,
        "active_schema": "drifted" if state.failure_injected else "canonical",
        "total_requests": state.total_requests,
        "db_path": DB_PATH,
        "sample_record": sample[0] if sample else None
    }

# ---------------------------------------------------------------------------
# Target SQLite Database Inspection Endpoints (For Verification)
# ---------------------------------------------------------------------------
@app.get("/db/records")
def get_database_records():
    """Returns all rows currently saved in the target SQLite market_records table."""
    records = query_records()
    return {
        "count": len(records),
        "records": records
    }

@app.post("/db/reset")
def reset_database():
    """Clears all records in the target SQLite table for clean demo rehearsals."""
    deleted = clear_db()
    return {
        "status": "database_cleared",
        "rows_deleted": deleted
    }

# ---------------------------------------------------------------------------
# Standalone Execution Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MOCK_PORT", "8001"))
    print(f"🚀 Starting Mock Market Data Service on http://127.0.0.1:{port}")
    print(f"   Database: {DB_PATH}")
    print(f"   GET  /market-data   -> Returns market data records")
    print(f"   POST /inject-failure -> Injects schema drift ('price' -> 'last_price')")
    print(f"   POST /reset          -> Reverts to normal schema")
    uvicorn.run("mock_service:app", host="127.0.0.1", port=port, reload=False)
