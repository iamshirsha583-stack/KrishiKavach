"""
API Endpoint Verification and Test Script for KrishiKavach.
"""

from fastapi.testclient import TestClient
from src.app.main import app

def test_api_endpoints():
    client = TestClient(app)

    print("--- 1. Testing Health & Root Endpoints ---")
    res_root = client.get("/")
    assert res_root.status_code == 200
    print(f"Root: {res_root.json()['service']} ({res_root.json()['status']})")

    res_health = client.get("/health")
    assert res_health.status_code == 200
    print(f"Health: {res_health.json()}")

    print("\n--- 2. Testing POST /api/v1/scan-trigger (Bengali) ---")
    payload = {
        "village_id": "VILLAGE_001",
        "phone_number": "+919876543210",
        "language": "Bengali"
    }
    res_scan = client.post("/api/v1/scan-trigger", json=payload)
    assert res_scan.status_code == 200
    data = res_scan.json()
    print(f"Status: {data['status']}")
    print(f"Village ID: {data['village_id']}")
    print(f"Flooded Area: {data['flooded_hectares']} ha ({data['flood_percentage']}%)")
    print(f"Risk Level: {data['risk_level']}")
    print(f"Advisory SMS: {data['advisory_sms']}")
    print(f"SMS SID: {data['sms_sid']}")

    print("\n--- 3. Testing GET /api/v1/maps/overlay/VILLAGE_001 ---")
    res_overlay = client.get("/api/v1/maps/overlay/VILLAGE_001")
    assert res_overlay.status_code == 200
    geojson = res_overlay.json()
    print(f"GeoJSON Type: {geojson.get('type')}")
    print(f"Features Count: {len(geojson.get('features', []))}")
    for idx, feat in enumerate(geojson.get("features", [])):
        print(f"  Feature {idx + 1}: {feat.get('properties', {}).get('type')} (Geometry: {feat.get('geometry', {}).get('type')})")

    print("\n--- All FastAPI Endpoints verified successfully ---")

if __name__ == "__main__":
    test_api_endpoints()
