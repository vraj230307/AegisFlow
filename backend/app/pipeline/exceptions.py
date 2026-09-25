"""
Auto-ETL Restorer — Component 2: Pipeline Node Exceptions
Structured custom exceptions carrying typed Pydantic payloads for diagnosis and WebSocket telemetry.
"""

from typing import Any, Dict, Optional
from app.pipeline.schemas import ExtractErrorPayload, CleanseErrorPayload

class PipelineNodeError(Exception):
    """Base class for all pipeline node execution errors."""
    def __init__(self, message: str, node_name: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.node_name = node_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "node_name": self.node_name,
            "message": self.message
        }

class ExtractError(PipelineNodeError):
    """Raised when node_extract fails (HTTP non-200 or connection failure)."""
    def __init__(self, message: str, payload: ExtractErrorPayload):
        super().__init__(message, node_name="node_extract")
        self.payload = payload
        self.source_url = payload.source_url
        self.status_code = payload.status_code
        self.response_body = payload.response_body
        self.original_error = payload.original_error
        self.traceback_str = payload.traceback_str

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(self.payload.model_dump())
        return base

class CleanseError(PipelineNodeError):
    """Raised when node_cleanse fails at any sub-step."""
    def __init__(self, message: str, payload: CleanseErrorPayload):
        super().__init__(message, node_name="node_cleanse")
        self.payload = payload
        self.failing_step = payload.failing_step
        self.record_index = payload.record_index
        self.failing_record = payload.failing_record
        self.original_error = payload.original_error
        self.traceback_str = payload.traceback_str

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update(self.payload.model_dump())
        return base

class EnrichError(PipelineNodeError):
    """Raised when node_enrich fails due to missing or invalid financial invariants."""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, node_name="node_enrich")
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["context"] = self.context
        return base

class LoadError(PipelineNodeError):
    """Raised when node_load fails during target DB persistence."""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, node_name="node_load")
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["context"] = self.context
        return base
