"""
Email service for PPE violation alerts with batching and rate limiting
"""

import threading
import time
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models import DetectionEvent, VideoSource
from send_mail import prepare_and_send_email
from utils import RateLimiter, logger


class EmailService:
    """Service for managing email alerts with performance optimizations"""

    def __init__(self, config: Config):
        self.config = config
        self.enabled = False
        self.recipient = None

        # Batch processing
        self.pending_alerts = []
        self.alert_lock = threading.Lock()

        # Rate limiting and deduplication
        self.sent_alerts: Set[Tuple[str, str]] = (
            set()
        )  # (source_id, violation_type, minute)
        self.last_batch_time = time.time()

        # Email thread
        self.email_thread = None
        self._shutdown = False

        # Rate limiter
        self.rate_limiter = RateLimiter(
            max_calls=10,  # Max 10 emails
            period_seconds=300,  # per 5 minutes
        )

    def configure(self, enabled: bool, recipient: str):
        """Configure email settings"""
        self.enabled = enabled
        self.recipient = recipient
        logger.info(
            f"Email service configured: enabled={enabled}, recipient={recipient}"
        )

    def start(self):
        """Start the email service"""
        if not self.enabled or not self.recipient:
            logger.info("Email service not started (disabled or no recipient)")
            return

        self.email_thread = threading.Thread(
            target=self._process_email_batch, name="email-processor"
        )
        self.email_thread.daemon = True
        self.email_thread.start()

        logger.info("Email service started")

    def queue_alert(self, source: VideoSource, event: DetectionEvent, frame=None):
        """Queue an alert for batch processing"""
        if not self.enabled or not self.recipient:
            return

        # Check for duplicate alerts (same source, violation type, and minute)
        alert_key = (
            source.id,
            event.violation_type,
            event.timestamp.strftime("%Y%m%d_%H%M"),
        )

        if alert_key in self.sent_alerts:
            return  # Already sent

        with self.alert_lock:
            self.pending_alerts.append(
                {
                    "source": source,
                    "event": event,
                    "frame": frame,
                    "alert_key": alert_key,
                }
            )

    def _process_email_batch(self):
        """Process email alerts in batches"""
        while not self._shutdown:
            try:
                time.sleep(self.config.EMAIL_COOLDOWN_SEC)

                # Check if we have pending alerts
                with self.alert_lock:
                    if not self.pending_alerts:
                        continue

                    # Take up to batch size
                    batch = self.pending_alerts[: self.config.EMAIL_BATCH_SIZE]
                    self.pending_alerts = self.pending_alerts[
                        self.config.EMAIL_BATCH_SIZE :
                    ]

                # Process batch
                if batch:
                    self._send_batch_email(batch)

                # Clean old sent alerts (older than 1 hour)
                self._cleanup_sent_alerts()

            except Exception as e:
                logger.error(f"Error in email processor: {e}")
                time.sleep(30)

    def _send_batch_email(self, alerts: List[Dict]):
        """Send a batch email with multiple alerts"""
        # Apply rate limiting
        if not self.rate_limiter(lambda: True)():
            logger.warning("Email rate limit exceeded, skipping batch")
            return

        try:
            # Group by source
            alerts_by_source = defaultdict(list)
            for alert in alerts:
                alerts_by_source[alert["source"].name].append(alert)

            # Build email content
            subject = f"PPE Violations Detected - {len(alerts)} Alert(s)"

            message_parts = [
                f"PPE violations detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "Summary of Violations:",
                "",
            ]

            # Add details for each source
            for source_name, source_alerts in alerts_by_source.items():
                message_parts.append(f"Source: {source_name}")

                # Count by type
                violation_counts = defaultdict(int)
                for alert in source_alerts:
                    violation_counts[alert["event"].violation_type] += 1

                for vtype, count in violation_counts.items():
                    message_parts.append(f"  - {vtype}: {count} detection(s)")

                message_parts.append("")

            # Add compliance rates
            message_parts.extend(["Compliance Status:", ""])

            for source_name, source_alerts in alerts_by_source.items():
                source = source_alerts[0]["source"]
                message_parts.append(
                    f"  - {source_name}: {source.compliance_rate:.1f}% compliant"
                )

            message_text = "\n".join(message_parts)

            # Use the first alert's frame as attachment
            frame = None
            for alert in alerts:
                if alert.get("frame") is not None:
                    frame = alert["frame"]
                    break

            # Send email
            prepare_and_send_email(
                sender=self.config.EMAIL_SENDER,
                recipient=self.recipient,
                subject=subject,
                message_text=message_text,
                im0=frame,
            )

            # Mark alerts as sent
            for alert in alerts:
                self.sent_alerts.add(alert["alert_key"])

            logger.info(f"Sent batch email with {len(alerts)} alerts")

        except Exception as e:
            logger.error(f"Failed to send batch email: {e}")

    def _cleanup_sent_alerts(self):
        """Remove old entries from sent alerts set"""
        current_time = datetime.now()
        cutoff_minute = (current_time - timedelta(hours=1)).strftime("%Y%m%d_%H%M")

        # Filter sent alerts
        new_sent_alerts = set()
        for alert_key in self.sent_alerts:
            _, _, minute = alert_key
            if minute > cutoff_minute:
                new_sent_alerts.add(alert_key)

        self.sent_alerts = new_sent_alerts

    def send_immediate_alert(
        self, source: VideoSource, event: DetectionEvent, frame=None
    ):
        """Send an immediate alert (bypasses batching)"""
        if not self.enabled or not self.recipient:
            return

        # Apply rate limiting
        if not self.rate_limiter(lambda: True)():
            logger.warning("Email rate limit exceeded for immediate alert")
            return

        try:
            subject = f"URGENT: {event.violation_type} - {source.name}"
            message_text = (
                f"PPE Violation Detected!\n\n"
                f"Source: {source.name}\n"
                f"Violation: {event.violation_type}\n"
                f"Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Confidence: {event.confidence:.1%}\n"
                f"Compliance Rate: {source.compliance_rate:.1f}%"
            )

            prepare_and_send_email(
                sender=self.config.EMAIL_SENDER,
                recipient=self.recipient,
                subject=subject,
                message_text=message_text,
                im0=frame,
            )

            logger.info(
                f"Sent immediate alert for {event.violation_type} at {source.name}"
            )

        except Exception as e:
            logger.error(f"Failed to send immediate alert: {e}")

    def get_statistics(self) -> Dict:
        """Get email service statistics"""
        with self.alert_lock:
            return {
                "enabled": self.enabled,
                "recipient": self.recipient,
                "pending_alerts": len(self.pending_alerts),
                "sent_alerts_tracked": len(self.sent_alerts),
                "rate_limit_remaining": self.rate_limiter.max_calls
                - len(self.rate_limiter.calls),
            }

    def shutdown(self):
        """Shutdown the email service"""
        self._shutdown = True

        # Process any remaining alerts
        with self.alert_lock:
            if self.pending_alerts and self.enabled:
                logger.info(
                    f"Processing {len(self.pending_alerts)} pending alerts before shutdown"
                )
                self._send_batch_email(self.pending_alerts)

        # Wait for email thread
        if self.email_thread and self.email_thread.is_alive():
            self.email_thread.join(timeout=5)

        logger.info("Email service shutdown complete")
