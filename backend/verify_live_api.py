import requests
import json

base = "http://127.0.0.1:8000"

def test_live_api():
    print("--- 1. Testing Health Endpoint ---")
    h = requests.get(f"{base}/api/health").json()
    print("Health:", h)
    assert h["status"] == "healthy"

    print("\n--- 2. Testing Plan Endpoint ---")
    p = requests.get(f"{base}/api/plan").json()
    print("Plan nodes count:", len(p["nodes"]))
    assert len(p["nodes"]) == 5

    print("\n--- 3. Testing Reset Patches ---")
    r = requests.post(f"{base}/api/reset-patches").json()
    print("Reset patches response:", r)
    assert r["status"] == "success"

    print("\n--- 4. Testing All 6 Scenarios via Live API ---")
    scenarios = [
        "none",
        "schema_drift",
        "type_mutation",
        "envelope_relocation",
        "missing_null_fields",
        "corrupt_timestamp"
    ]
    import time
    for sc in scenarios:
        # Wait if pipeline is busy
        for _ in range(10):
            h = requests.get(f"{base}/api/health").json()
            if not h.get("is_pipeline_busy"):
                break
            time.sleep(0.5)

        res = requests.post(
            f"{base}/api/run",
            json={
                "failure_scenario": sc,
                "use_cached_patches": True,
                "custom_records_count": 5
            }
        ).json()
        assert res.get("success") is True, f"Failed scenario {sc}: {res}"
        print(f"Scenario {sc:22}: SUCCESS (duration={res['duration_ms']}ms, was_healed={res['was_healed']})")
        time.sleep(0.5)

    print("\n--- 5. Testing Repeat Zero-Latency Cached Run ---")
    res_repeat = requests.post(
        f"{base}/api/run",
        json={
            "failure_scenario": "schema_drift",
            "use_cached_patches": True,
            "custom_records_count": 5
        }
    ).json()
    assert res_repeat["success"] is True
    print(f"Repeat Schema Drift Run: SUCCESS (duration={res_repeat['duration_ms']}ms, was_healed={res_repeat['was_healed']})")

    print("\n--- 6. Testing Metrics Endpoint ---")
    m = requests.get(f"{base}/api/metrics").json()
    print(f"Metrics: total_runs={m['total_runs']}, successful_runs={m['successful_runs']}, healed_runs={m['healed_runs']}, mttr={m['average_mttr_ms']}ms")
    assert m["total_runs"] >= 7
    assert m["healed_runs"] >= 6
    assert m["successful_runs"] >= 1

    print("\n==========================================")
    print(" ALL LIVE ENDPOINTS & SCENARIOS PASSED 100%! ")
    print("==========================================")

if __name__ == "__main__":
    test_live_api()
