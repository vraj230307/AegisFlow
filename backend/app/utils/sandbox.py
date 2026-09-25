import traceback
from typing import Callable, Any, Dict, Tuple
import datetime
import json
import re

def safe_import(name, *args, **kwargs):
    allowed = {"re", "datetime", "json", "math", "time"}
    if name in allowed:
        return __import__(name, *args, **kwargs)
    raise ImportError(f"Import of module '{name}' is disallowed in sandbox.")

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "round": round,
    "set": set,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "print": print,
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "__import__": safe_import,
}

SAFE_MODULES = {
    "re": re,
    "json": json,
    "datetime": datetime,
    "time": __import__("time"),
    "math": __import__("math"),
}

def compile_and_test_adapter(code_str: str, sample_input: Any) -> Tuple[bool, Any, str]:
    """
    Safely compiles a synthesized python adapter and tests it on sample input.
    Expected to define a function `def adapt(raw_input):` or `def transform(data):`.
    Returns: (is_success, adapter_callable_or_result, error_or_output_message)
    """
    exec_globals: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        **SAFE_MODULES
    }
    exec_locals: Dict[str, Any] = {}

    try:
        # Pre-check for hazardous keywords
        blocked_keywords = ["import os", "import sys", "import subprocess", "__import__('os')", "open(", "eval(", "exec("]
        for kw in blocked_keywords:
            if kw in code_str:
                return False, None, f"Security Violation: '{kw}' is not permitted in pipeline hot-patches."

        exec(code_str, exec_globals, exec_locals)

        # Look for the target function
        adapter_fn = None
        for name in ["adapt", "transform", "healed_node", "adapter", "fix_payload"]:
            if name in exec_locals and callable(exec_locals[name]):
                adapter_fn = exec_locals[name]
                break

        if not adapter_fn:
            # Fallback: take the first callable defined in exec_locals
            for val in exec_locals.values():
                if callable(val):
                    adapter_fn = val
                    break

        if not adapter_fn:
            return False, None, "No callable function (e.g. `adapt(data)`) found in synthesized code."

        # Dry run against sample input
        test_output = adapter_fn(sample_input)
        if test_output is None:
            return False, None, "Adapter executed but returned None."

        return True, adapter_fn, f"Adapter successfully verified on sample input! Output item count / type: {type(test_output)}"

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return False, None, err
