"""
Auto-ETL Restorer — Component 2: Node Execution Timing Wrapper
Provides a lightweight decorator to track start/end/duration_ms for each pipeline node.
"""

import functools
import time
from typing import Any, Callable, Dict
from app.pipeline.schemas import NodeExecutionStats

# Global registry of latest execution telemetry by node name
node_telemetry_registry: Dict[str, NodeExecutionStats] = {}

def timed_node(func: Callable) -> Callable:
    """
    Decorator recording start time, end time, and duration_ms of a pipeline node.
    Captures telemetry even when an exception is raised.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_counter = time.perf_counter()
        started_at = time.time()
        success = False
        error_msg = None
        try:
            result = func(*args, **kwargs)
            success = True
            return result
        except Exception as e:
            error_msg = str(e)
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_counter) * 1000, 2)
            stats = NodeExecutionStats(
                node_name=func.__name__,
                started_at=started_at,
                duration_ms=duration_ms,
                success=success,
                error=error_msg
            )
            wrapper.last_metrics = stats
            node_telemetry_registry[func.__name__] = stats

            # If return value has a latency_ms field and it's unset (0.0), set it
            if success and hasattr(result, "latency_ms") and getattr(result, "latency_ms", 0.0) == 0.0:
                try:
                    result.latency_ms = duration_ms
                except Exception:
                    pass

    wrapper.last_metrics = None
    return wrapper
