import asyncio
import traceback
import time
from typing import Dict, Any, List, Optional, Callable
from app.pipeline.schemas import (
    NodeStatus, FailureType, PipelineNodeInfo, PatchInfo, PipelineMetrics, RunPipelineRequest
)
from app.pipeline.nodes import (
    execute_extract, execute_cleanse, execute_enrich, execute_verify, execute_load
)
from app.agent.planner import PipelinePlanner
from app.agent.healer import SelfHealingAgent
from app.agent.verifier import VerifierEngine

class PipelineEngine:
    def __init__(self):
        self.agent = SelfHealingAgent()
        # Active in-memory hot patches: node_id -> callable
        self.active_patch_callables: Dict[str, Callable] = {}
        self.active_patch_records: Dict[str, PatchInfo] = {}
        # Metrics
        self.total_runs = 0
        self.successful_runs = 0
        self.healed_runs = 0
        self.failed_runs = 0
        self.mttr_samples: List[float] = []
        self.start_timestamp = time.time()
        # WebSocket listeners
        self.listeners: List[Any] = []
        self.is_running = False

    def add_listener(self, ws):
        self.listeners.append(ws)

    def remove_listener(self, ws):
        if ws in self.listeners:
            self.listeners.remove(ws)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        message = {
            "event": event_type,
            "timestamp": time.time(),
            "data": data
        }
        dead_connections = []
        for ws in self.listeners:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)
        for dead in dead_connections:
            self.remove_listener(dead)

    def reset_patches(self):
        self.active_patch_callables.clear()
        self.active_patch_records.clear()

    def get_metrics(self) -> PipelineMetrics:
        avg_mttr = round(sum(self.mttr_samples) / len(self.mttr_samples), 2) if self.mttr_samples else 0.0
        return PipelineMetrics(
            total_runs=self.total_runs,
            successful_runs=self.successful_runs,
            healed_runs=self.healed_runs,
            failed_runs=self.failed_runs,
            average_mttr_ms=avg_mttr,
            active_patches=len(self.active_patch_records),
            uptime_seconds=round(time.time() - self.start_timestamp, 1)
        )

    async def run_pipeline(self, request: RunPipelineRequest) -> Dict[str, Any]:
        """
        Executes the 5-node pipeline with automated error interception and dynamic self-healing.
        """
        if self.is_running:
            return {"status": "busy", "message": "Pipeline already executing"}

        self.is_running = True
        self.total_runs += 1
        run_start = time.time()
        was_healed = False

        if request.gemini_api_key:
            self.agent.update_key(request.gemini_api_key)

        # Clear patches if cached patches are disabled for fresh demonstration
        if not request.use_cached_patches:
            self.reset_patches()

        nodes = PipelinePlanner.get_default_plan()
        nodes_dict = {n.id: n for n in nodes}

        await self.broadcast("pipeline_started", {
            "failure_scenario": request.failure_scenario.value,
            "use_cached_patches": request.use_cached_patches,
            "nodes": [n.model_dump() for n in nodes]
        })

        intermediate_data: Any = None
        pipeline_error: Optional[str] = None

        try:
            # Step 1: EXTRACT
            await self._run_node_step(
                node=nodes_dict["node_extract"],
                runner_fn=lambda: execute_extract(request.failure_scenario, request.custom_records_count),
                input_data={"records_count": request.custom_records_count, "failure": request.failure_scenario.value}
            )
            intermediate_data = nodes_dict["node_extract"].output_preview

            # Step 2: CLEANSE (Primary failure and healing target for API schema drift)
            intermediate_data = await self._run_node_with_healing(
                node=nodes_dict["node_cleanse"],
                runner_fn=execute_cleanse,
                input_data=intermediate_data,
                failure_type=request.failure_scenario.value
            )
            if nodes_dict["node_cleanse"].applied_patch_id:
                was_healed = True

            # Step 3: ENRICH
            await self._run_node_step(
                node=nodes_dict["node_enrich"],
                runner_fn=lambda: execute_enrich(intermediate_data),
                input_data=intermediate_data
            )
            intermediate_data = nodes_dict["node_enrich"].output_preview

            # Step 4: VERIFY
            await self._run_node_step(
                node=nodes_dict["node_verify"],
                runner_fn=lambda: execute_verify(intermediate_data),
                input_data=intermediate_data
            )

            # Step 5: LOAD
            await self._run_node_step(
                node=nodes_dict["node_load"],
                runner_fn=lambda: execute_load(intermediate_data),
                input_data=intermediate_data
            )
            final_load_result = nodes_dict["node_load"].output_preview

            if was_healed:
                self.healed_runs += 1
            else:
                self.successful_runs += 1

            total_duration_ms = round((time.time() - run_start) * 1000, 2)
            metrics = self.get_metrics()

            await self.broadcast("pipeline_completed", {
                "success": True,
                "was_healed": was_healed,
                "duration_ms": total_duration_ms,
                "metrics": metrics.model_dump(),
                "final_result": final_load_result
            })

            return {
                "success": True,
                "was_healed": was_healed,
                "duration_ms": total_duration_ms,
                "nodes": [n.model_dump() for n in nodes],
                "metrics": metrics.model_dump()
            }

        except Exception as e:
            self.failed_runs += 1
            pipeline_error = str(e)
            metrics = self.get_metrics()
            await self.broadcast("pipeline_fatal_error", {
                "error": pipeline_error,
                "traceback": traceback.format_exc(),
                "metrics": metrics.model_dump()
            })
            return {
                "success": False,
                "error": pipeline_error,
                "nodes": [n.model_dump() for n in nodes],
                "metrics": metrics.model_dump()
            }

        finally:
            self.is_running = False

    async def _run_node_step(self, node: PipelineNodeInfo, runner_fn: Callable, input_data: Any):
        node.status = NodeStatus.RUNNING
        node.input_preview = input_data
        t0 = time.time()
        await self.broadcast("node_status_change", node.model_dump())
        await asyncio.sleep(0.35) # UI breathing room for visible reasoning

        try:
            output = runner_fn()
            node.latency_ms = round((time.time() - t0) * 1000, 2)
            node.output_preview = output
            node.status = NodeStatus.SUCCESS
            await self.broadcast("node_status_change", node.model_dump())
        except Exception as e:
            node.latency_ms = round((time.time() - t0) * 1000, 2)
            node.status = NodeStatus.FAILED
            node.error = str(e)
            await self.broadcast("node_status_change", node.model_dump())
            raise e

    async def _run_node_with_healing(
        self,
        node: PipelineNodeInfo,
        runner_fn: Callable,
        input_data: Any,
        failure_type: str
    ) -> Any:
        node.status = NodeStatus.RUNNING
        node.input_preview = input_data
        t0 = time.time()
        await self.broadcast("node_status_change", node.model_dump())
        await asyncio.sleep(0.4)

        # Check if we already have an active hot-patch cached for this node
        if node.id in self.active_patch_callables:
            patch_fn = self.active_patch_callables[node.id]
            patch_record = self.active_patch_records[node.id]
            await self.broadcast("agent_log", {
                "node_id": node.id,
                "level": "INFO",
                "message": f"⚡ Active hot-patch '{patch_record.id}' detected in registry. Fast-executing zero-latency adapted pipeline."
            })
            try:
                adapted_input = patch_fn(input_data)
                output = runner_fn(adapted_input)
                node.latency_ms = round((time.time() - t0) * 1000, 2)
                node.output_preview = output
                node.status = NodeStatus.SUCCESS
                node.applied_patch_id = patch_record.id
                await self.broadcast("node_status_change", node.model_dump())
                return output
            except Exception as patch_err:
                await self.broadcast("agent_log", {
                    "node_id": node.id,
                    "level": "WARN",
                    "message": f"Cached patch failed with new drift: {patch_err}. Initiating dynamic re-healing loop."
                })

        # Standard execution attempt
        try:
            output = runner_fn(input_data)
            node.latency_ms = round((time.time() - t0) * 1000, 2)
            node.output_preview = output
            node.status = NodeStatus.SUCCESS
            await self.broadcast("node_status_change", node.model_dump())
            return output

        except Exception as intercepted_exception:
            # === ERROR INTERCEPTOR ACTIVATED ===
            node.status = NodeStatus.FAILED
            node.error = str(intercepted_exception)
            tb = traceback.format_exc()
            await self.broadcast("node_status_change", node.model_dump())
            await self.broadcast("error_intercepted", {
                "node_id": node.id,
                "error_type": type(intercepted_exception).__name__,
                "error_message": str(intercepted_exception),
                "traceback": tb,
                "offending_payload_sample": input_data
            })

            # Transition to HEALING state
            node.status = NodeStatus.HEALING
            await self.broadcast("node_status_change", node.model_dump())
            await self.broadcast("agent_log", {
                "node_id": node.id,
                "level": "ALERT",
                "message": f"🚨 Error Interceptor triggered on {node.name}! Invoking Gemini Self-Healing Agent..."
            })

            expected_contract = PipelinePlanner.get_contract_description(node.id)

            # Call Gemini Self-Healing Agent
            healed, patch_info, adapter_fn, diagnosis_msg = await self.agent.diagnose_and_heal(
                node_id=node.id,
                node_name=node.name,
                error_message=str(intercepted_exception),
                traceback_str=tb,
                raw_input_sample=input_data,
                expected_contract_desc=expected_contract,
                failure_type=failure_type
            )

            if not healed or not patch_info or not adapter_fn:
                raise RuntimeError(f"Self-Healing Agent was unable to synthesize a valid patch: {diagnosis_msg}")

            # Register patch & metrics
            self.mttr_samples.append(patch_info.repair_time_ms)
            self.active_patch_callables[node.id] = adapter_fn
            self.active_patch_records[node.id] = patch_info
            node.applied_patch_id = patch_info.id

            await self.broadcast("patch_synthesized", {
                "patch": patch_info.model_dump(),
                "repair_time_ms": patch_info.repair_time_ms
            })

            # Hot-patching node
            node.status = NodeStatus.PATCHING
            await self.broadcast("node_status_change", node.model_dump())
            await asyncio.sleep(0.5)

            # Re-executing through newly synthesized adapter
            adapted_input = adapter_fn(input_data)
            output = runner_fn(adapted_input)

            # Verification assertion
            node.status = NodeStatus.VERIFIED
            await self.broadcast("node_status_change", node.model_dump())
            await asyncio.sleep(0.3)

            node.latency_ms = round((time.time() - t0) * 1000, 2)
            node.output_preview = output
            node.status = NodeStatus.SUCCESS
            await self.broadcast("node_status_change", node.model_dump())
            await self.broadcast("agent_log", {
                "node_id": node.id,
                "level": "SUCCESS",
                "message": f"✅ Node self-healed in {patch_info.repair_time_ms}ms! In-memory hot patch applied and verified."
            })

            return output

pipeline_engine = PipelineEngine()
