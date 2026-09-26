"""
Auto-ETL Restorer — Component 3: Gemini 2.5 Flash Self-Healer
Uses Gemini 2.5 Flash to diagnose root causes and synthesize Python patches
with Pydantic-validated structured JSON output.
"""

import inspect
import json
import os
import re
import traceback
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from app.config import settings

# Attempt importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False


class GeminiPatchResponse(BaseModel):
    """Structured output expected from Gemini 2.5 Flash."""
    diagnosis: str = Field(description="Clear root cause diagnosis of the failure")
    patched_function: str = Field(description="Raw Python source for the single replacement helper function")
    confidence: float = Field(default=0.95, description="Confidence score between 0.0 and 1.0")


GEMINI_SYSTEM_PROMPT = """You are an Autonomous Site Reliability & Data Pipeline Healing Agent for AegisFlow (HACK-O-OCTO 4.0 - PS01).
Your role is to diagnose data pipeline exceptions caused by schema drift, type mutation, envelope relocation, missing fields, or corrupt timestamps, and synthesize a single, clean Python replacement helper function to hot-patch the running system.

CRITICAL CONSTRAINTS:
1. You MUST respond with ONLY a valid JSON object matching this schema:
   {
     "diagnosis": "<concise explanation of root cause>",
     "patched_function": "<raw Python code for def <helper_name>(...): ...>",
     "confidence": 0.95
   }
2. The `patched_function` must replace EXACTLY ONE helper function. It must keep the EXACT same function signature as the original.
3. Do NOT import or use dangerous libraries (no os, sys, subprocess, eval, open). You may use standard safe utilities like `re`, `datetime`, `json`, `math`, `time`.
4. Ensure the function handles the offending payload gracefully and returns the canonical format expected by downstream nodes.
5. Do NOT include markdown code blocks around the JSON; return raw valid JSON only.

DOMAIN EXTRACTION RULES FOR CANONICAL TARGET SCHEMA:
- Canonical Record fields:
  * tx_id: string identifier (e.g. 'TX-101', 'TX-OBSC-202')
  * client_id: string user/client identifier (e.g. 'USR-101', 'USR-CORP-1')
  * amount: float gross financial value (e.g. 150.0, 450.0)
  * currency: 3-letter uppercase ISO alpha string (e.g. 'USD', 'EUR', 'GBP')
  * timestamp: ISO 8601 UTC string ending in 'Z' (e.g. '2026-09-25T16:00:00Z')
  * status: string (e.g. 'completed')

- SPECIAL HEALING PATTERNS:
  * Numeric Currency: If currency is an integer or 3-digit numeric code (e.g. 840, 978, 826), map it via ISO 4217 numeric codes (840->'USD', 978->'EUR', 826->'GBP', 392->'JPY', 124->'CAD', 36->'AUD', 756->'CHF', 356->'INR').
  * Array Identifier: If a scalar field like client_id or tx_id receives an array (e.g. ['USR-CORP-1', 'DEPT-FINANCE']), extract the primary intended scalar value (first non-null element). Do NOT stringify the entire array!
  * Sibling Shadowing: If primary 'amount' is None or missing, inspect sibling keys in the record (e.g. 'original_amount', 'amount_override', 'raw_amount', 'gross_amount', 'price') for the real value.
  * Obscure Keys: If keys have zero semantic meaning (e.g. 'k_99', 'u_alpha', 'val_7'), infer field mapping from VALUE SHAPE: values starting with 'TX-' are tx_id, values starting with 'USR-' are client_id, and positive floats are amount.
  * Nested Amount: If amount is an object (e.g. {'value': 850.25} or {'val': 600.0}), extract the numeric amount from .get('value') or .get('val').
  * Deep Envelopes: If payload is buried in nested dicts (e.g. meta.v3.feed.records), recursively search nested dicts until finding the list of dict records.
  * Relative Timestamp: If timestamp is a natural language relative phrase (e.g. 'two days ago', 'yesterday'), compute it relative to datetime.datetime.now(datetime.timezone.utc) using datetime.timedelta.
"""

class GeminiHealer:
    """Manages Gemini 2.5 Flash LLM interactions for autonomous patch synthesis."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY
        self.model_name = settings.DEFAULT_MODEL
        self.client = None
        self._init_client()

    def _init_client(self):
        if GENAI_AVAILABLE and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiHealer] GenAI client initialization warning: {e}")
                self.client = None

    def update_key(self, api_key: str):
        """Allows dynamic API key update from UI or config."""
        self.api_key = api_key
        self._init_client()

    def has_active_client(self) -> bool:
        return bool(self.client and self.api_key)

    async def diagnose_and_synthesize(
        self,
        node_name: str,
        failing_step: str,
        offending_payload: Any,
        original_error: str,
        traceback_str: str,
        current_helper_source: Optional[str] = None
    ) -> Tuple[bool, Optional[GeminiPatchResponse], str]:
        """
        Sends error context to Gemini 2.5 Flash and returns validated GeminiPatchResponse.
        Includes a retry with correction prompt if initial JSON parsing fails.
        """
        if not self.has_active_client():
            return False, None, "Gemini client not configured or GEMINI_API_KEY not set."

        payload_sample_str = json.dumps(offending_payload, default=str, indent=2)[:1200]
        
        user_prompt = f"""FAILURE CONTEXT:
- Node: {node_name}
- Failing Helper Function: {failing_step}
- Original Error: {original_error}
- Offending Payload Sample:
{payload_sample_str}

- Traceback:
{traceback_str[:800]}

- Current Helper Source Code:
```python
{current_helper_source or '# Source not available'}
```

Synthesize a corrected, rock-solid version of `def {failing_step}(...)` that handles this schema variation cleanly.
Adhere strictly to canonical schema contract: tx_id (str), amount (float), currency (3-letter alpha str), client_id (scalar str), timestamp (ISO 8601 UTC 'Z' str).
Return ONLY valid JSON with keys: 'diagnosis', 'patched_function', 'confidence'.
"""

        # Attempt 1: Standard call
        success, patch_resp, err_msg = await self._call_gemini(user_prompt)
        if success and patch_resp:
            return True, patch_resp, "Gemini synthesized patch successfully."

        # Attempt 2: Correction prompt retry
        correction_prompt = f"""Your previous response was either not valid JSON or did not strictly match the expected JSON schema.
Error: {err_msg}

Please re-generate your response. Return ONLY a valid JSON object matching:
{{
  "diagnosis": "<clear root cause>",
  "patched_function": "def {failing_step}(...):\\n    ...",
  "confidence": 0.95
}}
"""
        retry_success, retry_patch_resp, retry_err_msg = await self._call_gemini(
            f"{user_prompt}\n\n{correction_prompt}"
        )
        if retry_success and retry_patch_resp:
            return True, retry_patch_resp, "Gemini synthesized patch after JSON correction retry."

        return False, None, f"Gemini synthesis failed after correction retry: {retry_err_msg}"

    async def _call_gemini(self, prompt: str) -> Tuple[bool, Optional[GeminiPatchResponse], str]:
        """Executes API call to Gemini and parses response into GeminiPatchResponse."""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"{GEMINI_SYSTEM_PROMPT}\n\n{prompt}",
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )

            if not response or not response.text:
                return False, None, "Empty response received from Gemini."

            raw_text = response.text.strip()
            # Strip markdown formatting if any escaped
            clean_text = re.sub(r"^```json\s*", "", raw_text)
            clean_text = re.sub(r"\s*```$", "", clean_text).strip()

            parsed_data = json.loads(clean_text)
            validated = GeminiPatchResponse(**parsed_data)
            return True, validated, "Success"

        except Exception as e:
            return False, None, f"{type(e).__name__}: {str(e)}"
