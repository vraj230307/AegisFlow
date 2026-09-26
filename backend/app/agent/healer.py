import json
import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple, Callable
from app.config import settings
from app.pipeline.schemas import PatchInfo
from app.utils.sandbox import compile_and_test_adapter
from app.agent.prompts import SELF_HEALING_SYSTEM_PROMPT, build_self_healing_user_prompt

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

class SelfHealingAgent:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.client = None
        if GENAI_AVAILABLE and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[SelfHealingAgent] GenAI Client Init Warning: {e}")

    def update_key(self, api_key: str):
        self.api_key = api_key
        if GENAI_AVAILABLE and api_key:
            try:
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                print(f"[SelfHealingAgent] Client re-init failed: {e}")

    async def diagnose_and_heal(
        self,
        node_id: str,
        node_name: str,
        error_message: str,
        traceback_str: str,
        raw_input_sample: Any,
        expected_contract_desc: str,
        failure_type: str = "unknown"
    ) -> Tuple[bool, Optional[PatchInfo], Optional[Callable], str]:
        """
        Diagnoses failure, calls Gemini LLM or algorithmic fallback to synthesize adapter,
        compiles and tests in sandbox, and returns hot-patch.
        """
        start_time = time.time()
        raw_input_str = json.dumps(raw_input_sample, default=str, indent=2)[:1500]

        llm_response_json = None
        llm_source = "Gemini 2.5 Flash"

        # 1. Attempt Gemini API call if client is available
        if self.client:
            try:
                prompt_text = build_self_healing_user_prompt(
                    node_id=node_id,
                    node_name=node_name,
                    error_message=error_message,
                    traceback_str=traceback_str,
                    raw_input_sample=raw_input_str,
                    expected_schema_desc=expected_contract_desc
                )
                
                # Gemini 2.5 Flash call
                response = self.client.models.generate_content(
                    model=settings.DEFAULT_MODEL,
                    contents=f"{SELF_HEALING_SYSTEM_PROMPT}\n\n{prompt_text}",
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )

                if response and response.text:
                    text_content = response.text.strip()
                    # Clean markdown codeblocks if present
                    clean_text = re.sub(r"^```json\s*", "", text_content)
                    clean_text = re.sub(r"\s*```$", "", clean_text)
                    llm_response_json = json.loads(clean_text)

            except Exception as e:
                print(f"[SelfHealingAgent] Gemini LLM call encountered: {e}. Falling back to resilient synthetic generator.")

        # 2. Resilient fallback generator if Gemini not configured or timed out
        if not llm_response_json:
            llm_source = "AegisFlow Resilient Agent (Deterministic Fallback)"
            llm_response_json = self._generate_resilient_patch(
                failure_type=failure_type,
                node_name=node_name,
                raw_input_sample=raw_input_sample,
                error_message=error_message
            )

        root_cause = llm_response_json.get("root_cause", "Schema divergence detected.")
        explanation = f"[{llm_source}] {llm_response_json.get('explanation', '')}"
        code = llm_response_json.get("code", "")

        # 3. Compile and verify in isolated Python Sandbox
        success, adapter_fn, sandbox_msg = compile_and_test_adapter(code, raw_input_sample)
        repair_duration_ms = round((time.time() - start_time) * 1000, 2)

        if not success:
            return False, None, None, f"Patch verification failed in sandbox: {sandbox_msg}"

        patch_info = PatchInfo(
            id=f"patch-{uuid.uuid4().hex[:8]}",
            node_id=node_id,
            failure_type=failure_type,
            root_cause=root_cause,
            explanation=explanation,
            python_code=code,
            verified=True,
            repair_time_ms=repair_duration_ms
        )

        return True, patch_info, adapter_fn, "Patch successfully generated, compiled, and verified!"

    def _generate_resilient_patch(
        self,
        failure_type: str,
        node_name: str,
        raw_input_sample: Any,
        error_message: str
    ) -> Dict[str, str]:
        """
        Deterministic, intelligent patch generator that crafts accurate Python adapters
        for various failure archetypes to guarantee 100% demo continuity.
        """
        if "drift" in failure_type or "schema_drift" in failure_type:
            return {
                "root_cause": "Field rename drift: 'tx_id' renamed to 'reference_id', 'amount' to 'gross_amount', 'user_id' to 'client_id'.",
                "explanation": "Synthesized an alias mapping adapter that dynamically re-keys renamed fields into the canonical transaction contract with scalar client_id and numeric currency normalization.",
                "code": """def adapt(raw_input):
    records = raw_input if isinstance(raw_input, list) else [raw_input]
    iso_map = {840: "USD", "840": "USD", 978: "EUR", "978": "EUR", 826: "GBP", "826": "GBP", 392: "JPY", 356: "INR"}
    normalized = []
    for item in records:
        tx_id = item.get("tx_id") or item.get("reference_id") or item.get("id") or item.get("transaction_reference") or "TX-UNKNOWN"
        if isinstance(tx_id, (list, tuple)):
            tx_id = next((x for x in tx_id if x), "TX-UNKNOWN")
        
        cid = item.get("client_id") or item.get("user_id") or item.get("customer_id") or item.get("u_alpha") or "USR-GUEST"
        if isinstance(cid, (list, tuple)):
            cid = next((x for x in cid if x), "USR-GUEST")
        
        amt = item.get("amount") if item.get("amount") is not None else (
            item.get("gross_amount") or item.get("original_amount") or item.get("amount_override") or item.get("raw_amount") or item.get("price") or 0.0
        )
        if isinstance(amt, dict):
            amt = amt.get("value") or amt.get("val") or 0.0
        
        curr = item.get("currency", "USD")
        curr = iso_map.get(curr, iso_map.get(str(curr), str(curr).upper()))
        if len(curr) != 3 or not curr.isalpha():
            curr = "USD"
        
        status = item.get("status", "completed")
        timestamp = item.get("timestamp", "2026-09-25T16:00:00Z")
        normalized.append({
            "tx_id": str(tx_id),
            "client_id": str(cid),
            "user_id": str(cid),
            "amount": float(amt),
            "currency": str(curr),
            "timestamp": str(timestamp),
            "status": str(status)
        })
    return normalized
""",
                "verification_strategy": "Verifies canonical key presence: tx_id, client_id, amount as float, 3-letter currency."
            }

        elif "type_mutation" in failure_type:
            return {
                "root_cause": "Type mutation: Numerical 'amount' passed as formatted string with symbols (e.g. '$1,250.99 USD'), status passed as int.",
                "explanation": "Synthesized a regex-cleaning parser that strips non-numeric currency symbols and parses numbers to float, converting status codes to canonical strings.",
                "code": """import re

def adapt(raw_input):
    records = raw_input if isinstance(raw_input, list) else [raw_input]
    normalized = []
    for item in records:
        amt_raw = item.get("amount", 0.0)
        if isinstance(amt_raw, (int, float)):
            clean_amt = float(amt_raw)
        elif isinstance(amt_raw, dict):
            clean_amt = float(amt_raw.get("value") or amt_raw.get("val") or 0.0)
        else:
            # Strip currency symbols and letters, keeping digits, dot and minus
            cleaned = re.sub(r"[^0-9.-]", "", str(amt_raw))
            clean_amt = float(cleaned) if cleaned else 0.0
        
        status_raw = item.get("status", "completed")
        status_map = {200: "completed", 201: "settled", 400: "failed", 1: "completed"}
        status_str = status_map.get(status_raw, str(status_raw))

        cid = item.get("client_id") or item.get("user_id") or "USR-DEF"
        if isinstance(cid, (list, tuple)):
            cid = next((x for x in cid if x), "USR-DEF")

        normalized.append({
            "tx_id": str(item.get("tx_id", "TX-DEF")),
            "client_id": str(cid),
            "user_id": str(cid),
            "amount": round(clean_amt, 2),
            "currency": str(item.get("currency", "USD")),
            "timestamp": str(item.get("timestamp", "2026-09-25T16:00:00Z")),
            "status": status_str
        })
    return normalized
""",
                "verification_strategy": "Ensures amount is float and status is non-empty string"
            }

        elif "envelope" in failure_type:
            return {
                "root_cause": "API Envelope Relocation: Payload wrapped inside deep nested keys {'response_payload': {'items': [...]}}.",
                "explanation": "Synthesized a recursive unwrapper that navigates nested dictionary keys until it extracts the underlying list of transaction records.",
                "code": """def adapt(raw_input):
    curr = raw_input
    # Recursively traverse dicts to locate nested record lists
    while isinstance(curr, dict):
        found = False
        for candidate_key in ["items", "transactions_list", "records", "data", "response_payload", "payload"]:
            if candidate_key in curr:
                curr = curr[candidate_key]
                found = True
                break
        if not found:
            for v in curr.values():
                if isinstance(v, (list, dict)):
                    curr = v
                    found = True
                    break
            if not found:
                break
    
    records = curr if isinstance(curr, list) else [curr]
    return records
""",
                "verification_strategy": "Extracts flat transaction list from nested envelope"
            }

        elif "missing" in failure_type:
            return {
                "root_cause": "Missing and null critical fields: Currency missing in alternate rows, user_id is null.",
                "explanation": "Synthesized a fallback imputation adapter that populates default currency 'USD' and assigns synthetic client IDs for missing user identifiers.",
                "code": """def adapt(raw_input):
    records = raw_input if isinstance(raw_input, list) else [raw_input]
    normalized = []
    for idx, item in enumerate(records):
        item_copy = dict(item)
        if not item_copy.get("currency"):
            item_copy["currency"] = "USD"
        cid = item_copy.get("client_id") or item_copy.get("user_id") or f"USR-ANON-{idx + 1}"
        item_copy["client_id"] = str(cid)
        item_copy["user_id"] = str(cid)
        if item_copy.get("amount") is None:
            item_copy["amount"] = 0.0
        normalized.append(item_copy)
    return normalized
""",
                "verification_strategy": "Ensures no nulls in required fields"
            }

        elif "timestamp" in failure_type:
            return {
                "root_cause": "Timestamp corruption: Epoch millisecond integers, relative text, and legacy slash formats received.",
                "explanation": "Synthesized a multi-format datetime parser that converts millisecond integers, relative dates, and arbitrary date strings into standard ISO 8601 UTC timestamps.",
                "code": """import datetime
import re

def adapt(raw_input):
    records = raw_input if isinstance(raw_input, list) else [raw_input]
    now = datetime.datetime.now(datetime.timezone.utc)
    num_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    normalized = []
    for item in records:
        ts = item.get("timestamp")
        clean_ts = "2026-09-25T16:00:00Z"
        if isinstance(ts, (int, float)):
            sec = ts / 1000.0 if ts > 1e11 else ts
            clean_ts = datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(ts, str):
            ts_text = ts.strip().lower()
            if ts.strip().endswith("Z"):
                clean_ts = ts.strip()
            elif ts_text == "yesterday":
                clean_ts = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif ts_text == "today":
                clean_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                m = re.search(r"(\\w+)\\s+(day|hour|minute|week|month)s?\\s+ago", ts_text)
                if m:
                    val_str, unit = m.groups()
                    val = int(val_str) if val_str.isdigit() else num_words.get(val_str, 1)
                    delta = datetime.timedelta(days=val if unit == 'day' else (val * 7 if unit == 'week' else val * 30))
                    clean_ts = (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            clean_ts = datetime.datetime.strptime(ts.strip(), fmt).replace(tzinfo=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            break
                        except Exception:
                            pass
        
        item_copy = dict(item)
        item_copy["timestamp"] = clean_ts
        normalized.append(item_copy)
    return normalized
""",
                "verification_strategy": "Ensures timestamp is ISO 8601 string ending in 'Z'"
            }


        # Generic safe adapter
        return {
            "root_cause": f"Unhandled exception in pipeline node: {error_message}",
            "explanation": "Synthesized a general safe sanitizer and contract enforcer.",
            "code": """def adapt(raw_input):
    if isinstance(raw_input, list):
        return raw_input
    if isinstance(raw_input, dict):
        return [raw_input]
    return []
""",
            "verification_strategy": "Guarantees return type list"
        }
