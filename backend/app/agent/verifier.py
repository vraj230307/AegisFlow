from typing import Any, List, Dict, Tuple
import datetime

class VerifierEngine:
    """
    Part 4 of PS01 Architecture: Verifier & Invariant Engine.
    Executes contract assertions and mathematical invariants on node outputs.
    """
    
    @staticmethod
    def verify_ingestion_payload(data: Any) -> Tuple[bool, str]:
        if not isinstance(data, list):
            return False, f"Ingestion invariant failed: expected list of records, got {type(data).__name__}"
        if len(data) == 0:
            return False, "Ingestion invariant failed: record set is empty"

        seen_tx_ids = set()
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return False, f"Record [{i}] is not a dictionary"
            if "tx_id" not in item or not item["tx_id"]:
                return False, f"Record [{i}] missing required identifier 'tx_id'"
            
            # Primary key uniqueness
            tx_id_str = str(item["tx_id"])
            if tx_id_str in seen_tx_ids:
                return False, f"Record [{i}] duplicate primary key collision: tx_id '{tx_id_str}' already exists in batch"
            seen_tx_ids.add(tx_id_str)

            if "amount" not in item:
                return False, f"Record [{i}] missing required financial field 'amount'"
            if not isinstance(item["amount"], (int, float)):
                return False, f"Record [{i}] 'amount' must be numeric float, got {type(item['amount']).__name__}"
            if float(item["amount"]) <= 0:
                return False, f"Record [{i}] 'amount' must be strictly positive, got {item['amount']}"

            # Client identity scalar check
            cid = item.get("client_id") or item.get("user_id")
            if not cid:
                return False, f"Record [{i}] missing required client identifier ('client_id' / 'user_id')"
            if isinstance(cid, (list, tuple)) or (isinstance(cid, str) and cid.startswith("[") and cid.endswith("]")):
                return False, f"Record [{i}] client identifier must be a scalar string, not an array: {cid}"

        return True, f"Verified {len(data)} ingested records against contract invariants."

    @staticmethod
    def verify_financial_enrichment(data: List[Dict[str, Any]]) -> Tuple[bool, str]:
        if not isinstance(data, list):
            return False, "Enriched output is not a list"
        
        seen_tx_ids = set()
        for i, item in enumerate(data):
            # Invariant 1: Required calculated fields exist
            for field in ["tx_id", "tax", "net_total", "currency"]:
                if field not in item:
                    return False, f"Record [{i}] missing computed field '{field}'"
            
            # Uniqueness
            tx_id = str(item["tx_id"])
            if tx_id in seen_tx_ids:
                return False, f"Record [{i}] duplicate tx_id in enrichment: {tx_id}"
            seen_tx_ids.add(tx_id)

            # Invariant 2: Mathematical correctness
            amt = float(item["amount"])
            expected_tax = round(amt * 0.18, 2)  # 18% standard rate
            expected_net = round(amt + expected_tax, 2)

            if abs(item["tax"] - expected_tax) > 0.001:
                return False, f"Record [{i}] tax invariant violation: expected {expected_tax}, got {item['tax']}"
            if abs(item["net_total"] - expected_net) > 0.001:
                return False, f"Record [{i}] net_total invariant violation: expected {expected_net}, got {item['net_total']}"
            
            # Invariant 3: Currency must be 3-letter alpha uppercase
            curr = str(item.get("currency", ""))
            if len(curr) != 3 or not curr.isalpha() or not curr.isupper():
                return False, f"Record [{i}] invalid currency code '{curr}': must be 3-letter uppercase ISO 4217 alpha"
                
        return True, f"Verified all {len(data)} records satisfied mathematical, uniqueness, and schema invariants."

