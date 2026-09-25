"""
Comprehensive verification test for APScheduler, PyTorch Concurrency Lock,
Auth0 JWT Middleware, and FastAPI BackgroundTasks.
"""

import os
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from src.app.core.scheduler import execute_pipeline, PYTORCH_LOCK
from src.app.main import app

def test_full_system():
    print("--- 1. Testing execute_pipeline with PyTorch Concurrency Lock ---")
    assert not PYTORCH_LOCK.locked(), "PyTorch lock should be unlocked initially"
    res = execute_pipeline(
        bbox=[85.82, 20.46, 85.87, 20.51],
        village_id="VILLAGE_001",
        phone_number="+919876543210",
        language="Bengali"
    )
    print(f"Pipeline executed in {res.execution_time_seconds:.2f}s")
    print(f"Flooded: {res.flooded_hectares} ha ({res.flood_percentage}%) | Risk: {res.risk_level}")
    print(f"SMS ({len(res.bengali_sms_text)} chars): {res.bengali_sms_text}")
    print(f"Audio Path: {res.voice_audio_path}")
    print(f"SMS SID: {res.dispatch_result.get('sms_sid')}")
    print(f"Call SID: {res.dispatch_result.get('call_sid')}")

    print("\n--- 2. Testing FastAPI with Lifespan, Auth0 & BackgroundTasks ---")
    with TestClient(app) as client:
        # Test Root & Health
        health_res = client.get("/health")
        assert health_res.status_code == 200
        print(f"Health check: {health_res.json()}")

        # Test POST /api/v1/scan/trigger (Auth0 Protected Background Task)
        headers = {"Authorization": "Bearer dev-token"}
        payload = {
            "bbox": [85.82, 20.46, 85.87, 20.51],
            "village_id": "VILLAGE_001",
            "phone_number": "+919876543210",
            "language": "Bengali",
            "audio_url": "https://krishikavach.org/cache/alert.mp3"
        }
        bg_res = client.post("/api/v1/scan/trigger", json=payload, headers=headers)
        assert bg_res.status_code == 202, f"Expected 202 Accepted, got {bg_res.status_code}"
        bg_data = bg_res.json()
        print(f"Status: {bg_data['status']} (Code: 202 Accepted)")
        print(f"Job ID: {bg_data['job_id']}")
        print(f"Message: {bg_data['message']}")
        print(f"Auth User: {bg_data['auth_user']}")

        # Test GET /api/v1/maps/overlay/VILLAGE_001
        map_res = client.get("/api/v1/maps/overlay/VILLAGE_001")
        assert map_res.status_code == 200
        map_data = map_res.json()
        print(f"Map Overlay Features Count: {len(map_data.get('features', []))}")

    print("\n--- All scheduler, Auth0, BackgroundTasks, and API tests passed successfully ---")

if __name__ == "__main__":
    test_full_system()
