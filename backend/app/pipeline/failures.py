import random
import time
from typing import Any, List, Dict
from app.pipeline.schemas import FailureType

def generate_base_transactions(count: int = 5) -> List[Dict[str, Any]]:
    currencies = ["USD", "EUR", "GBP", "JPY", "INR"]
    statuses = ["completed", "settled", "authorized"]
    
    base_data = []
    base_time = int(time.time())
    for i in range(count):
        tx_num = 1000 + (i * 100) + random.randint(1, 99)
        base_data.append({
            "tx_id": f"TX-{tx_num}",
            "user_id": f"USR-{500 + i}",
            "amount": round(random.uniform(25.0, 3500.0), 2),
            "currency": random.choice(currencies),
            "timestamp": "2026-09-25T16:00:00Z",
            "status": random.choice(statuses)
        })
    return base_data

def inject_failure(data: List[Dict[str, Any]], failure: FailureType) -> Any:
    if failure == FailureType.NONE:
        return data

    if failure == FailureType.SCHEMA_DRIFT:
        # Field renaming drift: tx_id -> reference_id, amount -> gross_amount, user_id -> client_id
        mutated = []
        for item in data:
            mutated.append({
                "reference_id": item["tx_id"],
                "client_id": item["user_id"],
                "gross_amount": item["amount"],
                "currency": item["currency"],
                "timestamp": item["timestamp"],
                "status": item["status"]
            })
        return mutated

    elif failure == FailureType.TYPE_MUTATION:
        # Price passed as formatted string with symbols, status as integer
        mutated = []
        for item in data:
            curr = item["currency"]
            sym = "$" if curr == "USD" else ("€" if curr == "EUR" else "£")
            mutated.append({
                "tx_id": item["tx_id"],
                "user_id": item["user_id"],
                "amount": f"{sym} {item['amount']:,.2f} {curr}",
                "currency": item["currency"],
                "timestamp": item["timestamp"],
                "status": 200 # Integer instead of string
            })
        return mutated

    elif failure == FailureType.ENVELOPE_RELOCATION:
        # Deeply nested envelope structure
        return {
            "api_version": "v3.1-beta",
            "status_code": 200,
            "metadata": {
                "server_region": "us-east-1",
                "rate_limit_remaining": 498
            },
            "response_payload": {
                "items": data
            }
        }

    elif failure == FailureType.MISSING_NULL_FIELDS:
        # Missing currency, null user_ids
        mutated = []
        for i, item in enumerate(data):
            copy_item = dict(item)
            if i % 2 == 0:
                copy_item.pop("currency", None)
            if i % 3 == 0:
                copy_item["user_id"] = None
            mutated.append(copy_item)
        return mutated

    elif failure == FailureType.CORRUPT_TIMESTAMP:
        # Timestamp returned as unix epoch milliseconds or legacy slash format
        mutated = []
        for i, item in enumerate(data):
            copy_item = dict(item)
            if i % 2 == 0:
                copy_item["timestamp"] = int(time.time() * 1000) # Epoch ms int
            else:
                copy_item["timestamp"] = "25/09/2026 04:30:00 PM"
            mutated.append(copy_item)
        return mutated

    return data
