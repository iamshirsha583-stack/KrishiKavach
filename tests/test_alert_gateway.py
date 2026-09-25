"""
Verification script for Multi-Modal Emergency Alert Gateway.
"""

from pathlib import Path
from src.app.pipeline.risk_engine.alert_gateway import (
    generate_bengali_sms,
    synthesize_voice_alert,
    dispatch_alerts,
)

def test_alert_gateway():
    print("--- 1. Testing Bengali SMS Generation (Strict <140 chars) ---")
    sms_text = generate_bengali_sms(village_name="রামপুর", flooded_acres=142.5)
    print(f"Generated Text: {sms_text}")
    print(f"Character Count: {len(sms_text)}")
    assert len(sms_text) <= 140, f"SMS exceeded 140 chars ({len(sms_text)})"

    print("\n--- 2. Testing Voice Alert Synthesis (ElevenLabs) ---")
    audio_path = synthesize_voice_alert(
        text=sms_text,
        output_path="data/cache/alert.mp3"
    )
    print(f"Audio Path: {audio_path}")
    assert Path(audio_path).exists(), "Audio file does not exist"
    print(f"Audio File Size: {Path(audio_path).stat().st_size} bytes")

    print("\n--- 3. Testing Alert Dispatch (Twilio SMS + Voice TwiML) ---")
    dispatch_res = dispatch_alerts(
        to_number="+919876543210",
        sms_text=sms_text,
        audio_url="https://krishikavach.org/cache/alert.mp3"
    )
    print(f"SMS SID: {dispatch_res.sms_sid} (Status: {dispatch_res.sms_status})")
    print(f"Voice Call SID: {dispatch_res.call_sid} (Status: {dispatch_res.call_status})")
    print(f"Audio URL: {dispatch_res.audio_url}")
    print(f"Is Simulated: {dispatch_res.is_simulated}")

    print("\n--- Alert Gateway verified successfully ---")

if __name__ == "__main__":
    test_alert_gateway()
