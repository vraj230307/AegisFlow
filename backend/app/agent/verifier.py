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
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return False, f"Record [{i}] is not a dictionary"
            if "tx_id" not in item:
                return False, f"Record [{i}] missing required identifier 'tx_id'"
            if "amount" not in item:
                return False, f"Record [{i}] missing required financial field 'amount'"
            if not isinstance(item["amount"], (int, float)):
                return False, f"Record [{i}] 'amount' must be numeric float, got {type(item['amount']).__name__}"
        return True, f"Verified {len(data)} ingested records against contract invariants."

    @staticmethod
    def verify_financial_enrichment(data: List[Dict[str, Any]]) -> Tuple[bool, str]:
        if not isinstance(data, list):
            return False, "Enriched output is not a list"
        
        for i, item in enumerate(data):
            # Invariant 1: Required calculated fields exist
            for field in ["tax", "net_total", "currency"]:
                if field not in item:
                    return False, f"Record [{i}] missing computed field '{field}'"
            
            # Invariant 2: Mathematical correctness
            amt = float(item["amount"])
            expected_tax = round(amt * 0.18, 2) # 18% standard rate
            expected_net = round(amt + expected_tax, 2)

            if abs(item["tax"] - expected_tax) > 0.02:
                return False, f"Record [{i}] tax invariant violation: expected {expected_tax}, got {item['tax']}"
            if abs(item["net_total"] - expected_net) > 0.02:
                return False, f"Record [{i}] net_total invariant violation: expected {expected_net}, got {item['net_total']}"
            
            # Invariant 3: Currency must be non-empty string
            if not item.get("currency") or not isinstance(item["currency"], str):
                return False, f"Record [{i}] invalid currency"
                
        return True, f"Verified all {len(data)} records satisfied mathematical and schema invariants."
