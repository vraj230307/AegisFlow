"""
Auto-ETL Restorer — Component 3: Sandboxed AST Validator & Safe Execution Sandbox
Enforces strict allowlists for AST parsing, security isolation, and dry-run execution
before any hot-patch can be applied to live pipeline code.
"""

import ast
import inspect
import traceback
from typing import Any, Callable, Dict, Optional, Tuple, Set

# Explicit allowlist of standard modules safe for ETL patches
import re
import datetime
import json
import math
import time

SAFE_MODULES = {
    "re": re,
    "datetime": datetime,
    "json": json,
    "math": math,
    "time": time,
}

ALLOWED_MODULE_NAMES: Set[str] = set(SAFE_MODULES.keys())

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name not in ALLOWED_MODULE_NAMES:
        raise ImportError(f"Import of module '{name}' is not allowed in sandbox.")
    return __import__(name, globals, locals, fromlist, level)

# Explicit allowlist of builtins permitted in synthesized patches
SAFE_BUILTINS = {
    "__import__": safe_import,
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
}

FORBIDDEN_CALLS: Set[str] = {
    "open", "eval", "exec", "__import__", "compile",
    "getattr", "setattr", "delattr", "globals", "locals",
    "system", "popen", "spawn"
}

class SecurityVisitor(ast.NodeVisitor):
    """
    AST visitor enforcing:
    1. Exactly one FunctionDef with the target helper name.
    2. Imports restricted to explicit SAFE_MODULES allowlist.
    3. No dunder method or attribute access (__dict__, __class__, etc.).
    4. No dangerous function calls (open, eval, exec, etc.).
    """
    def __init__(self, expected_function_name: Optional[str] = None):
        self.expected_function_name = expected_function_name
        self.found_functions = []
        self.security_violations = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.found_functions.append(node.name)
        if self.expected_function_name and node.name != self.expected_function_name:
            self.security_violations.append(
                f"Function name '{node.name}' does not match expected helper '{self.expected_function_name}'"
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name not in ALLOWED_MODULE_NAMES:
                self.security_violations.append(f"Forbidden module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module not in ALLOWED_MODULE_NAMES:
            self.security_violations.append(f"Forbidden from-import module: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Check direct calls
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.security_violations.append(f"Forbidden function call: '{node.func.id}()'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Disallow dunder attributes
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.security_violations.append(f"Forbidden dunder attribute access: '{node.attr}'")
        self.generic_visit(node)


def validate_ast_security(
    code_str: str,
    expected_function_name: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Parses and verifies code string using the AST Security Visitor.
    Returns (is_valid, error_message).
    """
    try:
        parsed_ast = ast.parse(code_str)
    except SyntaxError as e:
        return False, f"SyntaxError in synthesized code: {str(e)}"

    visitor = SecurityVisitor(expected_function_name=expected_function_name)
    visitor.visit(parsed_ast)

    if len(visitor.found_functions) == 0:
        return False, f"No function definition found in code (expected '{expected_function_name}')."
    if len(visitor.found_functions) > 1:
        return False, f"Expected exactly 1 function definition, found {len(visitor.found_functions)}: {visitor.found_functions}"
    if visitor.security_violations:
        return False, f"Security violations detected: {'; '.join(visitor.security_violations)}"

    return True, "AST security checks passed."


def validate_helper_output(helper_name: str, output: Any) -> Tuple[bool, str]:
    """
    Verifies that the dry-run output of a candidate helper satisfies its canonical contract.
    """
    if helper_name == "unwrap_envelope":
        if not isinstance(output, list):
            return False, f"Expected list of records, got {type(output).__name__}"
        if len(output) > 0 and not isinstance(output[0], dict):
            return False, f"Expected list of dicts, but items are {type(output[0]).__name__}"
        return True, "Valid envelope unwrapping."

    elif helper_name == "resolve_key_aliases":
        if not isinstance(output, dict):
            return False, f"Expected dict, got {type(output).__name__}"
        required_keys = ["tx_id", "amount", "currency", "client_id", "timestamp"]
        missing = [k for k in required_keys if k not in output]
        if missing:
            return False, f"Missing required canonical keys in resolved record: {missing}"
        return True, "Valid canonical record dictionary."

    elif helper_name == "coerce_amount":
        if not isinstance(output, (int, float)):
            return False, f"Expected numeric float/int, got {type(output).__name__}: {output}"
        return True, "Valid numeric amount."

    elif helper_name == "normalize_timestamp":
        if not isinstance(output, str):
            return False, f"Expected str, got {type(output).__name__}: {output}"
        if not output.endswith("Z"):
            return False, f"Timestamp must end with 'Z', got '{output}'"
        return True, "Valid ISO 8601 UTC timestamp."

    return True, "Output passed general validation."


def sandbox_test_patch(
    code_str: str,
    helper_name: str,
    sample_input: Any
) -> Tuple[bool, Optional[Callable], str]:
    """
    Comprehensive sandbox testing:
    1. AST security and allowlist validation
    2. Isolated execution in SAFE_BUILTINS context
    3. Dry-run against offending payload sample
    4. Contract assertion on dry-run output
    Returns (passed, callable_fn, detail_message).
    """
    # 1. AST Security
    is_valid_ast, ast_msg = validate_ast_security(code_str, expected_function_name=helper_name)
    if not is_valid_ast:
        return False, None, f"Sandbox AST check failed: {ast_msg}"

    # 2. Execution environment
    exec_globals: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        **SAFE_MODULES
    }
    exec_locals: Dict[str, Any] = {}

    try:
        exec(code_str, exec_globals, exec_locals)
    except Exception as e:
        return False, None, f"Execution error while compiling patch: {type(e).__name__}: {str(e)}"

    candidate_fn = exec_locals.get(helper_name)
    if not candidate_fn or not callable(candidate_fn):
        return False, None, f"Function '{helper_name}' was not defined as a callable in synthesized code."

    # 3. Dry-run against sample input
    dry_run_input = sample_input
    if helper_name == "coerce_amount" and isinstance(sample_input, dict):
        dry_run_input = (
            sample_input.get("amount") or sample_input.get("gross_amount") or
            sample_input.get("last_price") or sample_input.get("price") or 0.0
        )
    elif helper_name == "normalize_timestamp" and isinstance(sample_input, dict):
        dry_run_input = sample_input.get("timestamp") or "2026-09-25T16:00:00Z"

    try:
        test_output = candidate_fn(dry_run_input)
    except Exception as e:
        tb = traceback.format_exc()
        return False, None, f"Dry-run execution against sample payload raised {type(e).__name__}: {str(e)}\n{tb}"

    # 4. Assert output shape
    valid_shape, shape_msg = validate_helper_output(helper_name, test_output)
    if not valid_shape:
        return False, None, f"Dry-run output violated contract: {shape_msg}"

    return True, candidate_fn, "Sandbox tests and dry-run assertions passed 100%."
