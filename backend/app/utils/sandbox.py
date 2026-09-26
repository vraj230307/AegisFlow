import ast
import traceback
from typing import Callable, Any, Dict, Tuple, Set, Optional
import datetime
import json
import re

SAFE_MODULES_LIST: Set[str] = {"re", "datetime", "json", "math", "time"}
FORBIDDEN_CALLS: Set[str] = {
    "open", "eval", "exec", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "hasattr", "__import__"
}

def safe_import(name, *args, **kwargs):
    if name in SAFE_MODULES_LIST:
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
    "next": next,
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

class AdapterSecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.top_level_functions = []
        self.security_violations = []

    def visit_Module(self, node: ast.Module):
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self.top_level_functions.append(item.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod not in SAFE_MODULES_LIST:
                self.security_violations.append(f"Forbidden module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod not in SAFE_MODULES_LIST:
                self.security_violations.append(f"Forbidden from-import module: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.security_violations.append(f"Forbidden function call: '{node.func.id}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__") and node.attr.endswith("__"):
            if node.attr not in ["__name__", "__doc__"]:
                self.security_violations.append(f"Forbidden dunder attribute access: '{node.attr}'")
        self.generic_visit(node)

def compile_and_test_adapter(code_str: str, sample_input: Any) -> Tuple[bool, Any, str]:
    """
    Safely compiles a synthesized python adapter and tests it on sample input.
    Enforces AST security, isolated execution, and canonical contract output assertions.
    """
    # 1. AST Security Analysis
    try:
        parsed_ast = ast.parse(code_str)
    except SyntaxError as e:
        return False, None, f"Syntax error in synthesized code: {str(e)}"

    visitor = AdapterSecurityVisitor()
    visitor.visit(parsed_ast)

    if len(visitor.top_level_functions) == 0:
        return False, None, "No top-level function definition found in code."
    if visitor.security_violations:
        return False, None, f"Security violations detected: {'; '.join(visitor.security_violations)}"

    # 2. Execution environment
    exec_globals: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        **SAFE_MODULES
    }
    exec_locals: Dict[str, Any] = {}

    try:
        exec(code_str, exec_globals, exec_locals)

        # Look for the target function
        adapter_fn = None
        for name in ["adapt", "transform", "healed_node", "adapter", "fix_payload"]:
            if name in exec_locals and callable(exec_locals[name]):
                adapter_fn = exec_locals[name]
                break

        if not adapter_fn:
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

        # Contract assertion: output should be list or dict
        if not isinstance(test_output, (list, dict)):
            return False, None, f"Adapter returned unexpected type: {type(test_output).__name__} (expected list or dict)"

        return True, adapter_fn, f"Adapter successfully verified on sample input! Output type: {type(test_output).__name__}"

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return False, None, err

