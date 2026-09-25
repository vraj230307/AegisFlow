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
            "node_cleanse": """List of transaction objects with exact keys:
- 'tx_id': string (e.g. 'TX-1001')
- 'user_id': string (e.g. 'USR-500')
- 'amount': float (numeric greater than 0)
- 'currency': string (e.g. 'USD', 'EUR')
- 'timestamp': string (ISO 8601 format)
- 'status': string (e.g. 'completed', 'settled')""",
            "node_enrich": """List of enriched transaction objects with computed fields:
- All fields from cleanse
- 'tax': float (round(amount * 0.18, 2))
- 'net_total': float (round(amount + tax, 2))
- 'ledger_batch_id': string""",
            "node_verify": """Assertion passes: all fields strictly present, no null values, arithmetic tax balance equals net_total."""
        }
        return contracts.get(node_id, "Standard valid dictionary or list format.")
