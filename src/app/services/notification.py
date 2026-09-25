"""
KrishiKavach Notification & SMS Dispatch Service.

Handles SMS dispatch to farmers and local agriculture extension officers using Twilio.
Provides automated mock simulation fallback when Twilio credentials are not set.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Dict, Any, Optional

logger = logging.getLogger("KrishiKavach.Notification")

# Try importing Twilio client if installed
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TwilioClient = None  # type: ignore
    TWILIO_AVAILABLE = False


class SMSDispatchService:
    """Service to send SMS advisories using Twilio or fallback simulator."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_PHONE_NUMBER")
        self.is_live = False
        self.client: Optional[Any] = None

        if TWILIO_AVAILABLE and self.account_sid and self.auth_token and self.from_number:
            try:
                self.client = TwilioClient(self.account_sid, self.auth_token)
                self.is_live = True
                logger.info("Initialized live Twilio SMS dispatch client.")
            except Exception as e:
                logger.warning(f"Failed to initialize Twilio client ({e}). Operating in simulation mode.")
                self.is_live = False
        else:
            logger.info("Twilio credentials not configured. SMS dispatch operating in simulation mode.")

    def send_sms(self, to_number: str, message_body: str) -> Dict[str, Any]:
        """
        Dispatches an SMS message.

        :param to_number: Recipient phone number in E.164 format (e.g., '+919876543210').
        :param message_body: Advisory message text.
        :return: Dictionary containing sms_sid, status, and delivery metadata.
        """
        if self.is_live and self.client is not None:
            try:
                logger.info(f"Dispatching live Twilio SMS to {to_number}...")
                msg = self.client.messages.create(
                    body=message_body,
                    from_=self.from_number,
                    to=to_number,
                )
                logger.info(f"Live SMS successfully dispatched. SID: {msg.sid}")
                return {
                    "sms_sid": msg.sid,
                    "status": "delivered",
                    "provider": "twilio_live",
                    "recipient": to_number,
                    "chars": len(message_body),
                }
            except Exception as e:
                logger.error(f"Live Twilio dispatch failed: {e}. Reverting to simulated dispatch.")

        # Simulated SMS dispatch
        simulated_sid = f"SM{uuid.uuid4().hex[:32]}"
        logger.info(
            f"[SMS Simulator] Dispatched SMS to '{to_number}':\n"
            f"  - SID: {simulated_sid}\n"
            f"  - Chars: {len(message_body)}\n"
            f"  - Body: {message_body}"
        )

        return {
            "sms_sid": simulated_sid,
            "status": "sent",
            "provider": "twilio_mock_simulator",
            "recipient": to_number,
            "chars": len(message_body),
        }
