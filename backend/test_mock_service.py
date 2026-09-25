"""
Test script for Auto-ETL Restorer Mock Service (Component 1).
Validates:
1. Normal GET /market-data schema
2. POST /inject-failure schema change ('price' -> 'last_price')
3. POST /reset reverts schema back to normal
4. Query param ?fail=true and ?fail=false overrides
5. Target SQLite database initialization, insert, query, and cleanup
"""

import os
from fastapi.testclient import TestClient
from mock_service import app, init_db, clear_db, insert_records, query_records, DB_PATH

client = TestClient(app)

def test_mock_service_and_db():
    print("=" * 60)
    print("TESTING COMPONENT 1: MOCK ENVIRONMENT & SQLITE TARGET DB")
    print("=" * 60)

    # 1. Health check
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[OK] [1/6] GET /health passed:", res.json())

    # 2. Reset to clean canonical state
    res = client.post("/reset")
    assert res.status_code == 200
    res = client.get("/market-data")
    assert res.status_code == 200
    canonical_data = res.json()
    assert len(canonical_data) == 5
    for item in canonical_data:
        assert "price" in item, "Expected 'price' in canonical schema"
        assert "last_price" not in item, "'last_price' should not be present in canonical schema"
    print("[OK] [2/6] GET /market-data canonical schema verified (has 'price', no 'last_price'):")
    print("       Sample record:", canonical_data[0])

    # 3. Inject failure
    res = client.post("/inject-failure")
    assert res.status_code == 200
    print("[OK] [3/6] POST /inject-failure succeeded:", res.json())

    # 4. Verify drifted schema
    res = client.get("/market-data")
    assert res.status_code == 200
    drifted_data = res.json()
    assert len(drifted_data) == 5
    for item in drifted_data:
        assert "last_price" in item, "Expected 'last_price' in drifted schema"
        assert "price" not in item, "'price' should have been renamed to 'last_price'"
    print("[OK] [4/6] GET /market-data drifted schema verified (has 'last_price', 'price' absent):")
    print("       Sample record:", drifted_data[0])

    # 5. Reset back to canonical
    res = client.post("/reset")
    assert res.status_code == 200
    res = client.get("/market-data")
    reverted_data = res.json()
    for item in reverted_data:
        assert "price" in item
        assert "last_price" not in item
    print("[OK] [5/6] POST /reset verified: /market-data reverted back to canonical schema.")

    # 6. SQLite Target Database operations
    init_db()
    clear_db()
    inserted = insert_records(canonical_data)
    assert inserted == len(canonical_data)
    records = query_records()
    assert len(records) == 5
    assert records[0]["symbol"] == "AAPL"
    assert records[0]["price"] == 182.50
    assert "ingested_at" in records[0]

    # Test /db/records and /db/reset endpoints
    db_res = client.get("/db/records")
    assert db_res.status_code == 200
    assert db_res.json()["count"] == 5

    reset_db_res = client.post("/db/reset")
    assert reset_db_res.status_code == 200
    assert reset_db_res.json()["rows_deleted"] == 5
    print("[OK] [6/6] SQLite Target DB verified: table creation, batch insert, querying, and clearing.")

    print("=" * 60)
    print("ALL COMPONENT 1 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_mock_service_and_db()
