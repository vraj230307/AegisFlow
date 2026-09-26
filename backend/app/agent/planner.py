from typing import List, Dict, Any
from app.pipeline.schemas import PipelineNodeInfo, NodeStatus

class PipelinePlanner:
    """
    Part 1 of PS01 Architecture: Planner Agent.
    Decomposes the data pipeline into discrete verifiable steps with expected contracts.
    """

    @staticmethod
    def get_default_plan() -> List[PipelineNodeInfo]:
        return [
            PipelineNodeInfo(
                id="node_extract",
                name="1. API Source Extraction",
                description="Fetches raw batch transactions from external third-party payment gateway endpoint.",
                status=NodeStatus.IDLE
            ),
            PipelineNodeInfo(
                id="node_cleanse",
                name="2. Schema & Type Normalization",
                description="Validates key schema, unwraps envelopes, and normalizes types into standard transaction contract.",
                status=NodeStatus.IDLE
            ),
            PipelineNodeInfo(
                id="node_enrich",
                name="3. Financial Computation & Enrichment",
                description="Calculates taxes (18%), computes net totals, assigns ledger status, and formats records.",
                status=NodeStatus.IDLE
            ),
            PipelineNodeInfo(
                id="node_verify",
                name="4. Contract & Invariant Verification",
                description="Executes mathematical assertions, schema constraints, and fraud/anomaly rules.",
                status=NodeStatus.IDLE
            ),
            PipelineNodeInfo(
                id="node_load",
                name="5. Warehouse & Stream Dispatch",
                description="Loads validated records to enterprise analytical storage and commits stream offsets.",
                status=NodeStatus.IDLE
            ),
        ]

    @staticmethod
    def get_contract_description(node_id: str) -> str:
        contracts = {
            "node_cleanse": """List of canonical transaction records (CanonicalRecord) with exact schema:
- 'tx_id': string scalar identifier (e.g. 'TX-1001', 'TX-OBSC-202').
- 'client_id': string scalar user/client identifier (e.g. 'USR-500', 'USR-101'). Must resolve from 'user_id', 'client_id', 'customer_id', or 'u_alpha'. Must NOT be an array or list.
- 'amount': positive float (e.g. 1250.00). Coerced from formatted currency strings ('$ 1,250.00 USD'), nested objects ({'value': 1250}), or sibling keys ('gross_amount', 'original_amount').
- 'currency': strictly 3-letter uppercase ISO 4217 alpha code (e.g. 'USD', 'EUR', 'GBP'). Numeric ISO codes (e.g. 840, 978, 826) must be mapped to their alpha equivalent ('USD', 'EUR', 'GBP').
- 'timestamp': strictly ISO 8601 UTC string ending in 'Z' (e.g. '2026-09-25T16:00:00Z'). Normalized from epoch ms integers, legacy slash dates, or relative natural language phrases ('two days ago', 'yesterday').
- 'status': canonical status string (e.g. 'completed', 'settled'). Default: 'completed'.""",
            "node_enrich": """List of enriched transaction records (EnrichedRecord) with computed financial fields:
- All canonical fields from cleanse: 'tx_id', 'client_id', 'amount', 'currency', 'timestamp', 'status'
- 'tax': float computed strictly as round(amount * 0.18, 2) (18% standard VAT/sales tax rate)
- 'net_total': float computed strictly as round(amount + tax, 2)
- 'ledger_batch_id': unique batch identifier string (e.g. 'BATCH-9A3F1B')
- 'processed_at': ISO 8601 UTC processing timestamp string""",
            "node_verify": """Assertion passes if and only if:
- Primary Key Uniqueness: every 'tx_id' is distinct within the batch (no duplicates)
- Non-Null Contract: all canonical fields ('tx_id', 'client_id', 'amount', 'currency', 'tax', 'net_total') are present and non-null
- Financial Arithmetic Invariant: abs(net_total - (amount + tax)) < 0.001
- Volume Positivity: amount > 0 and net_total > 0
- Valid ISO Currency: currency is a valid 3-letter uppercase alpha ISO 4217 code""",
            "node_load": """Persistence contract:
- Target Table: 'enriched_market_records' in SQLite enterprise warehouse
- Columns: (tx_id TEXT PRIMARY KEY, client_id TEXT NOT NULL, amount REAL NOT NULL, tax REAL NOT NULL, net_total REAL NOT NULL, currency TEXT NOT NULL, timestamp TEXT NOT NULL, ledger_batch_id TEXT NOT NULL, status TEXT NOT NULL, loaded_at TEXT NOT NULL)
- Idempotent upsert with atomic batch commit and offset dispatch."""
        }
        return contracts.get(node_id, "Standard valid dictionary or list format.")

    @staticmethod
    def get_helper_contract(helper_name: str) -> str:
        """Returns targeted contract description for modular sub-helper functions."""
        helper_contracts = {
            "unwrap_envelope": "Expects raw payload (dict or list); extracts and returns a flat List[Dict[str, Any]] containing transaction records.",
            "resolve_key_aliases": "Expects raw record dict; resolves and returns dict with canonical keys {'tx_id': str, 'client_id': str, 'amount': Any, 'currency': str, 'timestamp': Any, 'status': str}. Unpacks arrays in client_id/tx_id into scalars and maps numeric currency codes (840->'USD').",
            "coerce_amount": "Expects numeric, string, or nested dict amount; sanitizes currency symbols and returns positive float.",
            "normalize_timestamp": "Expects timestamp in any format (epoch ms, slash format, relative text); returns ISO 8601 UTC string ending in 'Z'."
        }
        return helper_contracts.get(helper_name, "Valid input/output transformation contract.")

