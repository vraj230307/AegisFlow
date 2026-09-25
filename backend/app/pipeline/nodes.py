"""
Auto-ETL Restorer — Component 2: Tool Execution Hub
5-node Pipeline DAG implementation:
  node_extract -> node_cleanse -> node_enrich -> node_verify -> node_load

Features:
- Discrete, modular execution nodes with strict typed Pydantic I/O.
- Timing wrapper @timed_node on all nodes.
- Modular cleanse helpers: unwrap_envelope, resolve_key_aliases, coerce_amount, normalize_timestamp.
- Typed exceptions (ExtractError, CleanseError, EnrichError, LoadError) carrying structured context.
"""

import os
import uuid
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.pipeline.schemas import (
    RawBatch,
    CanonicalRecord,
    EnrichedRecord,
    VerificationResult,
    LoadResult,
    ExtractErrorPayload,
    CleanseErrorPayload,
    FailureType,
)
from app.pipeline.exceptions import (
    ExtractError,
    CleanseError,
    EnrichError,
    LoadError,
)
from app.pipeline.timing import timed_node
from app.pipeline.failures import generate_base_transactions, inject_failure

# ---------------------------------------------------------------------------
# Node 1: Extract
# ---------------------------------------------------------------------------
@timed_node
def node_extract(source_url: str, timeout: float = 5.0) -> RawBatch:
    """
    Node 1: Fetches raw JSON payload from external REST API.
    Does not parse or mutate data — captures raw payload + status + timestamp.
    Raises ExtractError on HTTP errors or network connection failures.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(source_url)
    except Exception as e:
        tb = traceback.format_exc()
        raise ExtractError(
            message=f"Network connection failed when fetching {source_url}: {str(e)}",
            payload=ExtractErrorPayload(
                source_url=source_url,
                status_code=None,
                response_body=None,
                original_error=f"{type(e).__name__}: {str(e)}",
                traceback_str=tb
            )
        ) from e

    if response.status_code != 200:
        tb = "".join(traceback.format_stack())
        raise ExtractError(
            message=f"HTTP request to {source_url} failed with status {response.status_code}",
            payload=ExtractErrorPayload(
                source_url=source_url,
                status_code=response.status_code,
                response_body=response.text[:1000],
                original_error=f"HTTPStatusError: {response.status_code}",
                traceback_str=tb
            )
        )

    try:
        raw_json = response.json()
    except Exception as e:
        tb = traceback.format_exc()
        raise ExtractError(
            message=f"Failed to parse JSON response from {source_url}: {str(e)}",
            payload=ExtractErrorPayload(
                source_url=source_url,
                status_code=response.status_code,
                response_body=response.text[:1000],
                original_error=f"JSONDecodeError: {str(e)}",
                traceback_str=tb
            )
        ) from e

    count = len(raw_json) if isinstance(raw_json, list) else 1
    return RawBatch(
        source_url=source_url,
        status_code=response.status_code,
        raw_payload=raw_json,
        fetched_at=fetched_at,
        record_count=count
    )


# ---------------------------------------------------------------------------
# Node 2 Modular Cleanse Helpers (Independently patchable by Component 3)
# ---------------------------------------------------------------------------
def unwrap_envelope(raw_payload: Any) -> List[Dict[str, Any]]:
    """
    Sub-step 2.1: Asserts payload is a list of records or unwraps nested envelopes.
    In unpatched baseline, expects a direct list of dicts.
    """
    if isinstance(raw_payload, list):
        return raw_payload
    elif isinstance(raw_payload, dict):
        raise TypeError(
            f"Invalid API response structure: Expected list of transaction records, "
            f"but received dict with keys {list(raw_payload.keys())}. Envelope unwrapping required."
        )
    else:
        raise TypeError(f"Invalid API response structure: Expected list, got {type(raw_payload).__name__}")

def resolve_key_aliases(raw_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sub-step 2.2: Resolves canonical keys {tx_id, amount, currency, client_id, timestamp}.
    Supports canonical market records (id, price, symbol) and transaction records (tx_id, amount, user_id).
    Fails loudly with KeyError/ValueError if canonical fields are missing due to schema drift or null fields.
    """
    # 1. Identity field
    if "tx_id" in raw_record:
        tx_id = raw_record["tx_id"]
    elif "id" in raw_record:
        tx_id = f"TX-{raw_record['id']}"
    else:
        raise KeyError(
            f"Missing required canonical field 'tx_id' in record. Found keys: {list(raw_record.keys())}"
        )

    # 2. Financial amount field
    if "amount" in raw_record:
        amount = raw_record["amount"]
    elif "price" in raw_record:
        amount = raw_record["price"]
    else:
        raise KeyError(
            f"Missing required canonical field 'amount' / 'price' in record. Found keys: {list(raw_record.keys())}"
        )

    # 3. Client identity
    if "client_id" in raw_record and raw_record["client_id"] is not None:
        client_id = raw_record["client_id"]
    elif "user_id" in raw_record and raw_record["user_id"] is not None:
        client_id = raw_record["user_id"]
    elif "symbol" in raw_record and raw_record["symbol"] is not None:
        client_id = f"SYM-{raw_record['symbol']}"
    else:
        raise ValueError(f"Missing or null required field 'client_id' / 'user_id' in record: {raw_record}")

    # 4. Currency
    if "currency" in raw_record and raw_record["currency"]:
        currency = raw_record["currency"]
    elif "symbol" in raw_record:
        currency = "USD"
    else:
        raise ValueError(f"Missing or empty required field 'currency' in record: {raw_record}")

    # 5. Timestamp
    if "timestamp" in raw_record and raw_record["timestamp"] is not None:
        ts = raw_record["timestamp"]
    else:
        raise ValueError(f"Missing required field 'timestamp' in record: {raw_record}")

    return {
        "tx_id": str(tx_id),
        "amount": amount,
        "currency": str(currency),
        "client_id": str(client_id),
        "timestamp": ts,
        "status": raw_record.get("status", "completed")
    }

def coerce_amount(amount_raw: Any) -> float:
    """
    Sub-step 2.3: Coerces raw amount to a numeric float.
    In unpatched baseline, standard float() conversion is attempted.
    """
    if isinstance(amount_raw, (int, float)):
        return float(amount_raw)
    elif isinstance(amount_raw, str):
        # In baseline, float("$ 1,250.00 USD") will raise ValueError as expected
        return float(amount_raw)
    else:
        raise TypeError(f"Type violation on amount: expected numeric float or string, got {type(amount_raw).__name__}")

def normalize_timestamp(ts_raw: Any) -> str:
    """
    Sub-step 2.4: Validates timestamp conforms to ISO 8601 UTC ending in 'Z'.
    In unpatched baseline, asserts string type and ending with 'Z'.
    """
    if not isinstance(ts_raw, str):
        raise TypeError(
            f"Timestamp invariant violation: expected ISO 8601 string ending in 'Z', got {type(ts_raw).__name__}: {ts_raw}"
        )
    if not ts_raw.endswith("Z"):
        raise ValueError(f"Timestamp invariant violation: expected ISO 8601 UTC string ending in 'Z', got '{ts_raw}'")
    return ts_raw

# ---------------------------------------------------------------------------
# Node 2: Cleanse
# ---------------------------------------------------------------------------
@timed_node
def node_cleanse(raw: RawBatch) -> List[CanonicalRecord]:
    """
    Node 2: Normalizes keys to canonical contract, unwraps envelopes, coerces types.
    Modular design delegates to sub-step helpers so self-healer can hot-patch individual helpers.
    Raises typed CleanseError on failure with offending payload & traceback.
    """
    # 1. Envelope unwrapping
    try:
        records_data = unwrap_envelope(raw.raw_payload)
    except Exception as e:
        tb = traceback.format_exc()
        raise CleanseError(
            message=f"Cleanse failed in unwrap_envelope: {str(e)}",
            payload=CleanseErrorPayload(
                failing_step="unwrap_envelope",
                record_index=None,
                failing_record=raw.raw_payload,
                original_error=f"{type(e).__name__}: {str(e)}",
                traceback_str=tb
            )
        ) from e

    cleaned_records: List[CanonicalRecord] = []
    for idx, item in enumerate(records_data):
        if not isinstance(item, dict):
            tb = "".join(traceback.format_stack())
            raise CleanseError(
                message=f"Cleanse failed at record #{idx}: record is not a dictionary",
                payload=CleanseErrorPayload(
                    failing_step="unwrap_envelope",
                    record_index=idx,
                    failing_record=item,
                    original_error=f"TypeError: Expected dictionary at index {idx}, got {type(item).__name__}",
                    traceback_str=tb
                )
            )

        # 2. Key aliases
        try:
            resolved = resolve_key_aliases(item)
        except Exception as e:
            tb = traceback.format_exc()
            raise CleanseError(
                message=f"Cleanse failed in resolve_key_aliases at record #{idx}: {str(e)}",
                payload=CleanseErrorPayload(
                    failing_step="resolve_key_aliases",
                    record_index=idx,
                    failing_record=item,
                    original_error=f"{type(e).__name__}: {str(e)}",
                    traceback_str=tb
                )
            ) from e

        # 3. Coerce amount
        try:
            numeric_amount = coerce_amount(resolved["amount"])
        except Exception as e:
            tb = traceback.format_exc()
            raise CleanseError(
                message=f"Cleanse failed in coerce_amount at record #{idx}: {str(e)}",
                payload=CleanseErrorPayload(
                    failing_step="coerce_amount",
                    record_index=idx,
                    failing_record=item,
                    original_error=f"{type(e).__name__}: {str(e)}",
                    traceback_str=tb
                )
            ) from e

        # 4. Normalize timestamp
        try:
            iso_timestamp = normalize_timestamp(resolved["timestamp"])
        except Exception as e:
            tb = traceback.format_exc()
            raise CleanseError(
                message=f"Cleanse failed in normalize_timestamp at record #{idx}: {str(e)}",
                payload=CleanseErrorPayload(
                    failing_step="normalize_timestamp",
                    record_index=idx,
                    failing_record=item,
                    original_error=f"{type(e).__name__}: {str(e)}",
                    traceback_str=tb
                )
            ) from e

        # Construct CanonicalRecord
        cleaned_records.append(CanonicalRecord(
            tx_id=str(resolved["tx_id"]),
            amount=numeric_amount,
            currency=str(resolved["currency"]),
            client_id=str(resolved["client_id"]),
            timestamp=iso_timestamp,
            status=str(resolved.get("status", "completed"))
        ))

    return cleaned_records


# ---------------------------------------------------------------------------
# Node 3: Enrich
# ---------------------------------------------------------------------------
@timed_node
def node_enrich(records: List[CanonicalRecord]) -> List[EnrichedRecord]:
    """
    Node 3: Computes tax (18%), net_total, and attaches ledger batch metadata.
    Raises EnrichError on missing/null financial fields.
    """
    batch_id = f"BATCH-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    enriched: List[EnrichedRecord] = []

    for idx, item in enumerate(records):
        if item.amount is None or item.amount < 0:
            raise EnrichError(
                f"Enrichment violation at record #{idx}: invalid amount {item.amount}",
                context={"record_index": idx, "record": item.model_dump()}
            )
        if not item.currency:
            raise EnrichError(
                f"Enrichment violation at record #{idx}: missing currency",
                context={"record_index": idx, "record": item.model_dump()}
            )

        tax = round(item.amount * 0.18, 2)
        net = round(item.amount + tax, 2)
        enriched.append(EnrichedRecord(
            tx_id=item.tx_id,
            amount=item.amount,
            currency=item.currency,
            client_id=item.client_id,
            timestamp=item.timestamp,
            status=item.status or "completed",
            tax=tax,
            net_total=net,
            ledger_batch_id=batch_id,
            processed_at=now_iso
        ))

    return enriched


# ---------------------------------------------------------------------------
# Node 4: Verify
# ---------------------------------------------------------------------------
@timed_node
def node_verify(records: List[EnrichedRecord]) -> VerificationResult:
    """
    Node 4: Invariant verification.
    Asserts tax math (tax == round(amount * 0.18, 2), net == round(amount + tax, 2)),
    non-null keys, valid ISO timestamps, and duplicate check.
    Returns VerificationResult (passed=bool, failures=list). Never raises on data quality failures.
    """
    failures: List[str] = []
    seen_tx_ids = set()

    for idx, r in enumerate(records):
        # 1. Identity checks
        if not r.tx_id:
            failures.append(f"Record #{idx}: tx_id is empty")
        elif r.tx_id in seen_tx_ids:
            failures.append(f"Record #{idx}: duplicate tx_id '{r.tx_id}' found in batch")
        seen_tx_ids.add(r.tx_id)

        if not r.client_id:
            failures.append(f"Record #{idx}: client_id is empty")
        if not r.currency:
            failures.append(f"Record #{idx}: currency is empty")

        # 2. Tax math invariant
        expected_tax = round(r.amount * 0.18, 2)
        if abs(r.tax - expected_tax) > 0.01:
            failures.append(f"Record #{idx} ({r.tx_id}): tax math mismatch. Expected {expected_tax}, got {r.tax}")

        expected_net = round(r.amount + r.tax, 2)
        if abs(r.net_total - expected_net) > 0.01:
            failures.append(f"Record #{idx} ({r.tx_id}): net total mismatch. Expected {expected_net}, got {r.net_total}")

        # 3. ISO timestamp validation
        if not r.timestamp.endswith("Z"):
            failures.append(f"Record #{idx} ({r.tx_id}): timestamp '{r.timestamp}' missing UTC 'Z' suffix")

    passed = len(failures) == 0
    return VerificationResult(
        passed=passed,
        failures=failures,
        checked_count=len(records),
        assertion_details={
            "tax_rate_verified": "18%",
            "unique_records": len(seen_tx_ids),
            "invariant_violations": len(failures)
        }
    )


# ---------------------------------------------------------------------------
# Node 5: Load
# ---------------------------------------------------------------------------
@timed_node
def node_load(records: List[EnrichedRecord], db_path: Optional[str] = None) -> LoadResult:
    """
    Node 5: Persists enriched records to the target SQLite database.
    Raises LoadError on database failure.
    """
    import sqlite3
    db_file = db_path or os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "market_data.db"))
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        conn = sqlite3.connect(db_file)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS enriched_market_records (
                    tx_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    tax REAL NOT NULL,
                    net_total REAL NOT NULL,
                    currency TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    ledger_batch_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    loaded_at TEXT NOT NULL
                );
            """)
            for r in records:
                conn.execute("""
                    INSERT OR REPLACE INTO enriched_market_records
                    (tx_id, client_id, amount, tax, net_total, currency, timestamp, ledger_batch_id, status, loaded_at)
                    VALUES (:tx_id, :client_id, :amount, :tax, :net_total, :currency, :timestamp, :ledger_batch_id, :status, :loaded_at)
                """, {
                    "tx_id": r.tx_id,
                    "client_id": r.client_id,
                    "amount": r.amount,
                    "tax": r.tax,
                    "net_total": r.net_total,
                    "currency": r.currency,
                    "timestamp": r.timestamp,
                    "ledger_batch_id": r.ledger_batch_id,
                    "status": r.status,
                    "loaded_at": now_iso
                })
        conn.close()
    except Exception as e:
        tb = traceback.format_exc()
        raise LoadError(
            f"Database insertion failed: {str(e)}",
            context={"target_db": db_file, "records_count": len(records), "traceback": tb}
        ) from e

    return LoadResult(
        success=True,
        rows_loaded=len(records),
        target_table="enriched_market_records",
        committed_at=now_iso
    )


# ---------------------------------------------------------------------------
# Backward-compatibility wrappers for existing engine.py references
# ---------------------------------------------------------------------------
def execute_extract(failure_type: FailureType = FailureType.NONE, count: int = 5) -> Any:
    raw_txs = generate_base_transactions(count)
    return inject_failure(raw_txs, failure_type)

def execute_cleanse(data: Any) -> List[Dict[str, Any]]:
    # Bridge to node_cleanse
    raw = RawBatch(
        source_url="in-memory://mock-extract",
        status_code=200,
        raw_payload=data,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        record_count=len(data) if isinstance(data, list) else 1
    )
    cleaned = node_cleanse(raw)
    return [c.model_dump() for c in cleaned]

def execute_enrich(cleaned_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    canonical = [CanonicalRecord(**c) for c in cleaned_records]
    enriched = node_enrich(canonical)
    return [e.model_dump() for e in enriched]

def execute_verify(enriched_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    enriched = [EnrichedRecord(**e) for e in enriched_records]
    res = node_verify(enriched)
    return {
        "status": "PASS" if res.passed else "FAIL",
        "records_count": res.checked_count,
        "assertion_summary": "All financial invariants verified" if res.passed else "; ".join(res.failures)
    }

def execute_load(enriched_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    enriched = [EnrichedRecord(**e) for e in enriched_records]
    res = node_load(enriched)
    total_vol = sum(e.net_total for e in enriched)
    return {
        "loaded_records_count": res.rows_loaded,
        "total_financial_volume": round(total_vol, 2),
        "primary_currency": enriched[0].currency if enriched else "USD",
        "warehouse_table": res.target_table,
        "commit_timestamp": res.committed_at
    }
