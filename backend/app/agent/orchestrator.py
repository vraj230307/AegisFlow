"""
Auto-ETL Restorer — Component 3: Async Self-Healing Pipeline Orchestrator
Implements the resilient state machine:
  PLAN -> EXTRACT -> CLEANSE -> ENRICH -> VERIFY -> LOAD -> DONE
  On Exception:
    -> DIAGNOSE -> SYNTHESIZE -> SANDBOX_TEST -> HOT_PATCH -> RETRY (max 2)
    -> FALLBACK_HEAL -> HOT_PATCH -> RETRY
    -> FAIL_SAFE

Features:
- Live structured event streaming {state, node, timestamp, detail}
- Strict AST-sandboxed verification before hot-patching
- In-memory patch cache for zero-latency repeat runs
- Accurate MTTR latency calculation
- Hard-capped guardrails (never infinite loop)
"""

import asyncio
import hashlib
import inspect
import json
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

import app.pipeline.nodes as pipeline_nodes
from app.pipeline.schemas import (
    RawBatch,
    CanonicalRecord,
    EnrichedRecord,
    VerificationResult,
    LoadResult,
)
from app.pipeline.exceptions import (
    PipelineNodeError,
    ExtractError,
    CleanseError,
    EnrichError,
    LoadError,
)
from app.agent.sandbox import sandbox_test_patch
from app.agent.fallback import get_fallback_patch
from app.agent.gemini_healer import GeminiHealer


class OrchestratorEvent(BaseModel):
    """Structured event emitted on every state transition."""
    state: str
    node: str
    timestamp: float = Field(default_factory=time.time)
    detail: Dict[str, Any] = Field(default_factory=dict)


class PipelineRunResult(BaseModel):
    """Final outcome of an orchestrated pipeline execution."""
    success: bool
    state: str
    total_records: int = 0
    healed: bool = False
    heal_source: Optional[str] = None  # "gemini" | "fallback" | "cached"
    mttr_ms: float = 0.0
    duration_ms: float = 0.0
    active_patches_count: int = 0
    error: Optional[str] = None
    events: List[Dict[str, Any]] = []


class PipelineOrchestrator:
    """Async finite state machine managing the self-healing pipeline DAG."""

    def __init__(self, api_key: Optional[str] = None):
        self.gemini_healer = GeminiHealer(api_key=api_key)
        self.event_listeners: List[Callable[[Dict[str, Any]], Any]] = []
        
        # Patch Cache: cache_key -> {helper_name, patch_code, callable, diagnosis, source}
        self.patch_cache: Dict[str, Dict[str, Any]] = {}
        
        # Back up original unpatched helper functions so they can be restored on demand
        self.original_helpers: Dict[str, Callable] = {
            "unwrap_envelope": pipeline_nodes.unwrap_envelope,
            "resolve_key_aliases": pipeline_nodes.resolve_key_aliases,
            "coerce_amount": pipeline_nodes.coerce_amount,
            "normalize_timestamp": pipeline_nodes.normalize_timestamp,
        }

    def add_event_listener(self, callback: Callable[[Dict[str, Any]], Any]):
        """Attaches an async or sync callback to stream structured events."""
        self.event_listeners.append(callback)

    def remove_event_listener(self, callback: Callable[[Dict[str, Any]], Any]):
        if callback in self.event_listeners:
            self.event_listeners.remove(callback)

    async def emit(self, state: str, node: str, detail: Dict[str, Any], event_log: List[Dict[str, Any]]):
        """Emits a structured transition event to listeners and logs it."""
        event = OrchestratorEvent(
            state=state,
            node=node,
            timestamp=time.time(),
            detail=detail
        ).model_dump()
        event_log.append(event)
        
        for listener in self.event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                print(f"[Orchestrator] Listener error: {e}")

    def unpatch_nodes_keep_cache(self):
        """Restores original helper implementations in nodes.py, but retains the patch_cache."""
        for name, original_fn in self.original_helpers.items():
            setattr(pipeline_nodes, name, original_fn)

    def reset_patches(self):
        """Restores all pipeline node helpers back to their pristine unpatched baseline and clears cache."""
        self.unpatch_nodes_keep_cache()
        self.patch_cache.clear()

    def _compute_schema_fingerprint(self, payload: Any) -> str:
        """
        Computes a deterministic fingerprint of payload keys, nested dictionary structures,
        and value types to prevent cross-patch cache collisions between different schema drifts (TC-11).
        """
        def extract_shape(obj: Any, depth: int = 0) -> Any:
            if depth > 4:
                return type(obj).__name__
            if isinstance(obj, dict):
                return {k: extract_shape(v, depth + 1) for k, v in sorted(obj.items())}
            elif isinstance(obj, (list, tuple)):
                if len(obj) == 0:
                    return ["<empty>"]
                return [extract_shape(obj[0], depth + 1)]
            else:
                return type(obj).__name__

        shape = extract_shape(payload)
        return hashlib.md5(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:10]

    async def run_pipeline(
        self,
        source_url: str,
        db_path: Optional[str] = None,
        max_gemini_retries: int = 2,
        allow_fallback: bool = True
    ) -> PipelineRunResult:
        """
        Executes the 5-node pipeline with autonomous self-healing guardrails:
        PLAN -> EXTRACT -> CLEANSE -> ENRICH -> VERIFY -> LOAD -> DONE
        """
        start_time = time.time()
        first_failure_time: Optional[float] = None
        healed = False
        heal_source = None
        event_log: List[Dict[str, Any]] = []

        await self.emit("PLAN", "planner", {"message": "Decomposing DAG into 5 strict verifiable nodes"}, event_log)

        # -------------------------------------------------------------------
        # 1. EXTRACT
        # -------------------------------------------------------------------
        await self.emit("EXTRACT", "node_extract", {"source_url": source_url}, event_log)
        try:
            raw_batch = pipeline_nodes.node_extract(source_url)
        except ExtractError as err:
            await self.emit("FAIL_SAFE", "node_extract", {
                "error": err.message,
                "detail": err.to_dict()
            }, event_log)
            return PipelineRunResult(
                success=False,
                state="FAIL_SAFE",
                duration_ms=round((time.time() - start_time) * 1000, 2),
                error=err.message,
                events=event_log
            )

        # -------------------------------------------------------------------
        # 2. CLEANSE (with self-healing retry loop)
        # -------------------------------------------------------------------
        canonical_records: Optional[List[CanonicalRecord]] = None
        cleanse_attempts = 0
        gemini_attempts = 0
        max_cleanse_retries = 6
        applied_cache_keys_this_run: set = set()

        while canonical_records is None:
            cleanse_attempts += 1
            if cleanse_attempts > max_cleanse_retries:
                await self.emit("FAIL_SAFE", "orchestrator", {
                    "failing_step": "max_attempts_exceeded",
                    "attempts": cleanse_attempts,
                    "error": f"Cleanse exceeded max retry budget of {max_cleanse_retries}"
                }, event_log)
                return PipelineRunResult(
                    success=False,
                    state="FAIL_SAFE",
                    healed=False,
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    error=f"FAIL_SAFE triggered: unable to cleanse after {cleanse_attempts} attempts.",
                    events=event_log
                )

            await self.emit("CLEANSE", "node_cleanse", {"attempt": cleanse_attempts}, event_log)
            
            try:
                canonical_records = pipeline_nodes.node_cleanse(raw_batch)
            except CleanseError as err:
                if first_failure_time is None:
                    first_failure_time = time.time()

                failing_step = err.failing_step
                offending_payload = err.failing_record
                fingerprint = self._compute_schema_fingerprint(offending_payload)
                cache_key = f"{failing_step}_{fingerprint}"

                await self.emit("DIAGNOSE", "node_cleanse", {
                    "failing_step": failing_step,
                    "record_index": err.record_index,
                    "original_error": err.original_error,
                    "schema_fingerprint": fingerprint
                }, event_log)

                # Special Guardrail: If payload has insufficient fields, refuse to fabricate financial data
                if failing_step == "insufficient_data":
                    await self.emit("FAIL_SAFE", "node_cleanse", {
                        "failing_step": "insufficient_data",
                        "error": err.message,
                        "record_index": err.record_index
                    }, event_log)
                    return PipelineRunResult(
                        success=False,
                        state="FAIL_SAFE",
                        healed=False,
                        duration_ms=round((time.time() - start_time) * 1000, 2),
                        error=f"Guardrail triggered: {err.message}",
                        events=event_log
                    )

                # -----------------------------------------------------------
                # Strategy A: Zero-Latency Patch Cache Hit
                # -----------------------------------------------------------
                if cache_key in self.patch_cache and cache_key not in applied_cache_keys_this_run:
                    applied_cache_keys_this_run.add(cache_key)
                    cached_patch = self.patch_cache[cache_key]
                    setattr(pipeline_nodes, failing_step, cached_patch["callable"])
                    healed = True
                    heal_source = "cached"
                    await self.emit("HOT_PATCH", "node_cleanse", {
                        "helper": failing_step,
                        "source": "cached",
                        "diagnosis": cached_patch["diagnosis"],
                        "message": "Zero-latency cached patch applied in 0ms!"
                    }, event_log)
                    continue

                # -----------------------------------------------------------
                # Strategy B: Gemini 2.5 Flash Autonomous Healer
                # -----------------------------------------------------------
                patch_applied = False
                current_helper_fn = getattr(pipeline_nodes, failing_step, None)
                try:
                    current_source = inspect.getsource(current_helper_fn) if current_helper_fn else None
                except Exception:
                    current_source = None

                while gemini_attempts < max_gemini_retries and self.gemini_healer.has_active_client():
                    gemini_attempts += 1
                    await self.emit("SYNTHESIZE", "gemini_healer", {
                        "gemini_attempt": gemini_attempts,
                        "model": self.gemini_healer.model_name
                    }, event_log)

                    success, gemini_resp, synth_msg = await self.gemini_healer.diagnose_and_synthesize(
                        node_name="node_cleanse",
                        failing_step=failing_step,
                        offending_payload=offending_payload,
                        original_error=err.original_error,
                        traceback_str=err.traceback_str,
                        current_helper_source=current_source
                    )

                    if success and gemini_resp:
                        # AST & Sandbox Validation
                        await self.emit("SANDBOX_TEST", "sandbox", {
                            "helper": failing_step,
                            "confidence": gemini_resp.confidence
                        }, event_log)

                        passed_sandbox, candidate_fn, sb_msg = sandbox_test_patch(
                            code_str=gemini_resp.patched_function,
                            helper_name=failing_step,
                            sample_input=offending_payload
                        )

                        if passed_sandbox and candidate_fn:
                            # Hot-patch in memory & cache
                            setattr(pipeline_nodes, failing_step, candidate_fn)
                            self.patch_cache[cache_key] = {
                                "helper_name": failing_step,
                                "patch_code": gemini_resp.patched_function,
                                "callable": candidate_fn,
                                "diagnosis": gemini_resp.diagnosis,
                                "source": "gemini"
                            }
                            healed = True
                            heal_source = "gemini"
                            patch_applied = True
                            await self.emit("HOT_PATCH", "node_cleanse", {
                                "helper": failing_step,
                                "source": "gemini",
                                "diagnosis": gemini_resp.diagnosis,
                                "patch_code": gemini_resp.patched_function
                            }, event_log)
                            break
                        else:
                            await self.emit("DIAGNOSE", "sandbox", {
                                "message": f"Gemini patch rejected by sandbox: {sb_msg}"
                            }, event_log)

                if patch_applied:
                    continue

                # -----------------------------------------------------------
                # Strategy C: Deterministic Fallback Healer (Offline Demo Insurance)
                # -----------------------------------------------------------
                if allow_fallback:
                    await self.emit("FALLBACK_HEAL", "fallback_healer", {
                        "reason": "Gemini unavailable or retries exceeded; applying verified offline fallback"
                    }, event_log)

                    fb_ok, fb_diag, fb_helper, fb_code = get_fallback_patch(failing_step, offending_payload)
                    if fb_ok:
                        passed_sb, fb_fn, sb_msg = sandbox_test_patch(
                            code_str=fb_code,
                            helper_name=fb_helper,
                            sample_input=offending_payload
                        )
                        if passed_sb and fb_fn:
                            applied_cache_keys_this_run.add(cache_key)
                            setattr(pipeline_nodes, fb_helper, fb_fn)
                            self.patch_cache[cache_key] = {
                                "helper_name": fb_helper,
                                "patch_code": fb_code,
                                "callable": fb_fn,
                                "diagnosis": fb_diag,
                                "source": "fallback"
                            }
                            healed = True
                            heal_source = "fallback"
                            await self.emit("HOT_PATCH", "node_cleanse", {
                                "helper": fb_helper,
                                "source": "fallback",
                                "diagnosis": fb_diag,
                                "patch_code": fb_code
                            }, event_log)
                            continue

                # -----------------------------------------------------------
                # Strategy D: Guardrail FAIL_SAFE (Never infinite loop)
                # -----------------------------------------------------------
                await self.emit("FAIL_SAFE", "orchestrator", {
                    "failing_step": failing_step,
                    "attempts": cleanse_attempts,
                    "error": err.message
                }, event_log)
                return PipelineRunResult(
                    success=False,
                    state="FAIL_SAFE",
                    healed=False,
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    error=f"FAIL_SAFE triggered: unable to heal {failing_step} after {cleanse_attempts} attempts.",
                    events=event_log
                )

        # -------------------------------------------------------------------
        # 3. ENRICH
        # -------------------------------------------------------------------
        await self.emit("ENRICH", "node_enrich", {"record_count": len(canonical_records)}, event_log)
        try:
            enriched_records = pipeline_nodes.node_enrich(canonical_records)
        except EnrichError as err:
            await self.emit("FAIL_SAFE", "node_enrich", {"error": err.message}, event_log)
            return PipelineRunResult(
                success=False,
                state="FAIL_SAFE",
                duration_ms=round((time.time() - start_time) * 1000, 2),
                error=err.message,
                events=event_log
            )

        # -------------------------------------------------------------------
        # 4. VERIFY
        # -------------------------------------------------------------------
        await self.emit("VERIFY", "node_verify", {"record_count": len(enriched_records)}, event_log)
        verification = pipeline_nodes.node_verify(enriched_records)
        if not verification.passed:
            await self.emit("FAIL_SAFE", "node_verify", {
                "failures": verification.failures
            }, event_log)
            return PipelineRunResult(
                success=False,
                state="FAIL_SAFE",
                duration_ms=round((time.time() - start_time) * 1000, 2),
                error=f"Verification failed: {verification.failures}",
                events=event_log
            )

        # -------------------------------------------------------------------
        # 5. LOAD
        # -------------------------------------------------------------------
        await self.emit("LOAD", "node_load", {"record_count": len(enriched_records)}, event_log)
        try:
            load_result = pipeline_nodes.node_load(enriched_records, db_path=db_path)
        except LoadError as err:
            await self.emit("FAIL_SAFE", "node_load", {"error": err.message}, event_log)
            return PipelineRunResult(
                success=False,
                state="FAIL_SAFE",
                duration_ms=round((time.time() - start_time) * 1000, 2),
                error=err.message,
                events=event_log
            )

        # -------------------------------------------------------------------
        # 6. DONE
        # -------------------------------------------------------------------
        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        mttr_ms = round((time.time() - first_failure_time) * 1000, 2) if first_failure_time else 0.0

        await self.emit("DONE", "pipeline", {
            "rows_loaded": load_result.rows_loaded,
            "healed": healed,
            "heal_source": heal_source,
            "mttr_ms": mttr_ms,
            "duration_ms": total_duration_ms
        }, event_log)

        return PipelineRunResult(
            success=True,
            state="DONE",
            total_records=load_result.rows_loaded,
            healed=healed,
            heal_source=heal_source,
            mttr_ms=mttr_ms,
            duration_ms=total_duration_ms,
            active_patches_count=len(self.patch_cache),
            events=event_log
        )
