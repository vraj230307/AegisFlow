# AegisFlow | Autonomous Agentic Self-Healing Data Pipeline
> **Hackathon Submission**: HACK-O-OCTO 4.0 — **Problem Statement 01 (PS01)**  
> **Track**: AI Agents, Cloud, APIs, and Resilient Systems  
> **Core AI**: Google Gemini 2.5 Flash (`gemini-2.5-flash`)  
> **Live WebApp**: [https://aegisflow-ps01.web.app](https://aegisflow-ps01.web.app)

---

## 🎯 Executive Summary & Problem Context
AegisFlow turns a single high-level intent — keep this pipeline healthy — into autonomous planning, execution, recovery, and verification, with no human in the loop between intent and outcome.

In enterprise financial and high-throughput data pipelines, upstream third-party APIs constantly experience:
- **Schema Drift**: Fields are unexpectedly renamed (e.g. `amount` becomes `gross_amount`, `tx_id` becomes `reference_id`).
- **Type Mutation**: Numbers arrive as formatted strings with currency symbols (e.g. `"$1,250.99 USD"`).
- **Envelope Relocation**: Flat arrays are suddenly wrapped inside deep nested dictionaries (`response_payload.items`).
- **Missing or Corrupted Invariants**: Null currencies, empty client IDs, corrupted unix timestamps.

Traditional pipelines throw unhandled exceptions, raise midnight pager alerts, halt analytical ingestion, and require an on-call engineer to triage, write a patch, run PR review, and deploy.

**AegisFlow solves this with zero human intervention**: It autonomously intercepts pipeline failures, leverages **Google Gemini 2.5 Flash** to diagnose root causes, synthesizes and sandbox-tests an in-memory Python hot-patch, repairs the live executing pipeline in milliseconds (MTTR ~400ms), and registers the patch for subsequent zero-latency runs.

---

## 🏗️ 4-Part Architecture (HACK-O-OCTO PS01)

```
       ┌────────────────────────────────────────────────────────┐
       │                 1. PLANNER AGENT                       │
       │    Decomposes Pipeline into Strict Verifiable DAG     │
       └──────────────────────────┬─────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │             2. TOOL EXECUTION HUB (Python)             │
       │  API Extract ──► Cleanse & Map ──► Enrich ──► Load     │
       └──────────────────────────┬─────────────────────────────┘
                                  │ (On Schema Drift / Exception)
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │      3. ERROR INTERCEPTOR & GEMINI SELF-HEALER         │
       │  • Traps Exception, Input Sample & Target Schema       │
       │  • Gemini 2.5 Flash Diagnoses Root Cause               │
       │  • Synthesizes Resilient Python Adapter                │
       │  • Sandboxed Execution Verification                    │
       │  • In-Memory Dynamic Hot-Patching                      │
       └──────────────────────────┬─────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │         4. VERIFIER & INVARIANT ENGINE                 │
       │  • Asserts Invariants (Tax Math, Non-null, ISO Dates)  │
       │  • Broadcasts Real-Time Telemetry over WebSockets      │
       └────────────────────────────────────────────────────────┘
```

### 💡 Why This Approach
Rather than a broad multi-agent system, AegisFlow goes deep on one high-stakes failure mode — verifiable autonomous recovery — because reliability, not breadth, is what determines whether a real user would actually depend on it.

### 1. Planner Agent
Decomposes the processing workflow into discrete verifiable steps with strict typed input/output schemas:
1. `node_extract`: Fetches raw API transactions.
2. `node_cleanse`: Normalizes keys, unwraps payloads, casts types into canonical contract.
3. `node_enrich`: Computes taxes (18%), net totals, and attaches ledger batch metadata.
4. `node_verify`: Validates mathematical and schema invariants.
5. `node_load`: Persists to analytical warehouse.

### 2. Python Tool Execution Hub
Safe execution wrappers for each pipeline node that enforce contract constraints and track step-by-step latency.

### 3. Error Interceptor & Gemini Self-Healer
When a contract is violated or an unhandled exception occurs:
- The interceptor traps the exception, stack trace, offending payload snippet, and target schema.
- Sends a structured prompt to **Google Gemini 2.5 Flash**.
- Gemini analyzes the schema divergence and writes a Python adapter function `def adapt(raw_input):`.
- The adapter is compiled and tested inside an isolated sandbox (`SAFE_BUILTINS`).
- If tests pass, the running node is hot-patched in memory and re-executed.
- **Safety Guardrail**: Every Gemini-generated patch is AST-validated against a strict allowlist and sandbox-tested against the real failing payload before being applied — no unvalidated code ever touches live data.

### 4. Verifier & Invariant Engine
Verifies its own final output against strict invariants — tax math, non-null identity keys, ISO 8601 timestamps — before declaring success:
- $\text{Tax} = \text{round}(\text{Amount} \times 0.18, 2)$
- $\text{Net Total} = \text{round}(\text{Amount} + \text{Tax}, 2)$
- Strict ISO 8601 timestamps and non-empty identity keys.
- Records Mean Time to Repair (MTTR) and broadcasts events via WebSockets to the UI.

---

## 🚀 Live Demo Failure Injection Scenarios (For Judges)

The AegisFlow dashboard includes 1-click failure triggers designed specifically for live hackathon evaluation:

| Scenario | Simulated Failure | How Gemini Self-Heals |
| :--- | :--- | :--- |
| **Clean Baseline** | Healthy clean API data | Passes with normal 0ms patch overhead |
| **Schema Drift** | `amount` $\to$ `gross_amount`<br>`tx_id` $\to$ `reference_id` | Synthesizes an alias resolver mapping keys to canonical fields |
| **Type Mutation** | Prices as `"$1,250.99 USD"` | Writes regex sanitizer to strip currency symbols & cast float |
| **Envelope Nesting** | Deep metadata nesting | Generates recursive unwrapper to locate record items |
| **Missing Fields** | Null user IDs & missing currencies | Generates safe fallback imputation logic |
| **Corrupt Timestamps** | Epoch ms integers & slash dates | Multi-format datetime converter to ISO 8601 |

---

## ⚡ Quickstart: Running AegisFlow

### 1. Start the FastAPI Backend
```powershell
cd backend
.\venv\Scripts\python.exe run.py
```
* Backend runs at: `http://localhost:8000`
* Swagger API Docs: `http://localhost:8000/docs`
* WebSocket Telemetry Stream: `ws://localhost:8000/ws/pipeline`

### 2. Start the Frontend Dashboard
```powershell
cd frontend
npm run dev
```
* Dashboard runs at: `http://localhost:5173`

### 3. Configure Gemini API Key (Optional)
- Add your key to `backend/.env`:
  ```env
  GEMINI_API_KEY=your_gemini_api_key_here
  GEMINI_MODEL=gemini-2.5-flash
  ```
- Or enter it directly in the UI dashboard via the **API Key** button.
- *Note*: If no key is provided, AegisFlow runs with its built-in resilient algorithmic fallback healer to guarantee 100% demo continuity even without internet!
 
### 4. Automated Feature-Walkthrough Recording (Playwright)
Run the automated end-to-end judge walkthrough across all scenarios to record high-resolution 1080p demo video:
```powershell
python record_walkthrough.py
```
- Automatically drives Clean Baseline $\to$ Schema Drift $\to$ Corrupt Timestamps $\to$ Metrics Telemetry.
- Saves `AegisFlow_Demo.webm` directly to `%USERPROFILE%\Downloads`.

---

## 📊 Business Impact & Telemetry
- **Mean Time to Repair (MTTR)**: ~400ms observed in testing, vs. an illustrative baseline of ~45 minutes for manual on-call triage.
- **Zero Midnight Pager Alerts**: Self-heals transient breaking changes in third-party APIs.
- **Zero-Latency Repeat Execution**: Once an API anomaly is hot-patched in memory, subsequent pipeline runs reuse the adapter with 0ms penalty.

---

## ⚠️ Known Limitation
Current scope covers schema/type/structural drift in a single pipeline domain; extending to multi-pipeline or multi-agent orchestration is the natural next step.
