from typing import Any, Optional, Dict, List
from enum import Enum
from pydantic import BaseModel, Field
import time

class NodeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    HEALING = "healing"
    PATCHING = "patching"
    VERIFIED = "verified"
    SUCCESS = "success"

class FailureType(str, Enum):
    NONE = "none"
    SCHEMA_DRIFT = "schema_drift"
    TYPE_MUTATION = "type_mutation"
    ENVELOPE_RELOCATION = "envelope_relocation"
    MISSING_NULL_FIELDS = "missing_null_fields"
    CORRUPT_TIMESTAMP = "corrupt_timestamp"

class TargetFinancialTransaction(BaseModel):
    transaction_id: str
    user_id: str
    amount: float
    currency: str
    tax: float
    net_total: float
    timestamp: str
    status: str

class PipelineNodeInfo(BaseModel):
    id: str
    name: str
    description: str
    status: NodeStatus = NodeStatus.IDLE
    latency_ms: float = 0.0
    input_preview: Optional[Any] = None
    output_preview: Optional[Any] = None
    error: Optional[str] = None
    applied_patch_id: Optional[str] = None

class PatchInfo(BaseModel):
    id: str
    node_id: str
    failure_type: str
    root_cause: str
    explanation: str
    python_code: str
    created_at: float = Field(default_factory=time.time)
    verified: bool = False
    repair_time_ms: float = 0.0

class PipelineMetrics(BaseModel):
    total_runs: int = 0
    successful_runs: int = 0
    healed_runs: int = 0
    failed_runs: int = 0
    average_mttr_ms: float = 0.0
    active_patches: int = 0
    uptime_seconds: float = 0.0

class WSEvent(BaseModel):
    event: str
    timestamp: float = Field(default_factory=time.time)
    data: Dict[str, Any]

class RunPipelineRequest(BaseModel):
    failure_scenario: FailureType = FailureType.NONE
    use_cached_patches: bool = True
    custom_records_count: int = 5
    gemini_api_key: Optional[str] = None

# ===========================================================================
# Component 2: Tool Execution Hub Pydantic Models
# ===========================================================================

class RawBatch(BaseModel):
    """Raw batch returned strictly by node_extract."""
    source_url: str
    status_code: int
    raw_payload: Any
    fetched_at: str
    latency_ms: float = 0.0
    record_count: int = 0

class CanonicalRecord(BaseModel):
    """Canonical record contract output by node_cleanse."""
    tx_id: str
    amount: float
    currency: str
    client_id: str
    timestamp: str  # ISO 8601 UTC
    status: Optional[str] = "completed"

class EnrichedRecord(BaseModel):
    """Enriched record with computed tax, net total, and ledger metadata."""
    tx_id: str
    amount: float
    currency: str
    client_id: str
    timestamp: str
    status: str = "completed"
    tax: float
    net_total: float
    ledger_batch_id: str
    processed_at: str

class VerificationResult(BaseModel):
    """Verification outcome asserting invariants."""
    passed: bool
    failures: List[str] = []
    checked_count: int
    assertion_details: Dict[str, Any] = {}
    latency_ms: float = 0.0

class LoadResult(BaseModel):
    """Database persistence outcome from node_load."""
    success: bool
    rows_loaded: int
    target_table: str
    duration_ms: float = 0.0
    committed_at: str

class ExtractErrorPayload(BaseModel):
    """Structured context attached to ExtractError."""
    source_url: str
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    original_error: str
    traceback_str: str

class CleanseErrorPayload(BaseModel):
    """Structured context attached to CleanseError."""
    failing_step: str  # unwrap_envelope | resolve_key_aliases | coerce_amount | normalize_timestamp
    record_index: Optional[int] = None
    failing_record: Optional[Any] = None
    original_error: str
    traceback_str: str

class NodeExecutionStats(BaseModel):
    """Telemetry captured by the node timing wrapper."""
    node_name: str
    started_at: float
    duration_ms: float
    success: bool
    error: Optional[str] = None

