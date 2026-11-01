"""Notification queue, provider adapters, retry handling and delivery logs.

Providers are optional. When none is configured we never pretend a message was
delivered in production: the notification is marked `skipped` with a reason.
Demo mode simulates delivery so the UI can be demonstrated end-to-end.
"""
from __future__ import annotations

import base64
import json
import logging
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import Notification, NotificationChannel, NotificationStatus
from ..utils.crypto import mask_email, mask_phone

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def queue_notification(
    *,
    clinic_id: str,
    notification_type: str,
    channel: str,
    body: str,
    subject: str | None = None,
    recipient: str | None = None,
    recipient_masked: str | None = None,
    user_id: str | None = None,
    patient_id: str | None = None,
    dedupe_key: str,
    related_type: str | None = None,
    related_id: str | None = None,
) -> Notification | None:
    existing = Notification.query.filter_by(dedupe_key=dedupe_key).first()
    if existing:
        return existing
    notification = Notification(
        clinic_id=clinic_id,
        user_id=user_id,
        patient_id=patient_id,
        notification_type=notification_type,
        channel=channel,
        recipient=recipient,
        recipient_masked=recipient_masked or (mask_email(recipient) if channel == "email" else mask_phone(recipient)),
        subject=subject,
        body=body,
        dedupe_key=dedupe_key,
        related_type=related_type,
        related_id=related_id,
    )
    if channel == NotificationChannel.IN_APP:
        notification.status = NotificationStatus.SENT
        notification.sent_at = _now()
        notification.provider = "in_app"
    db.session.add(notification)
    db.session.flush()
    return notification


def notify_staff(
    clinic_id: str,
    user_id: str,
    notification_type: str,
    body: str,
    subject: str | None = None,
    dedupe_key: str | None = None,
    related_type: str | None = None,
    related_id: str | None = None,
) -> Notification | None:
    return queue_notification(
        clinic_id=clinic_id,
        user_id=user_id,
        notification_type=notification_type,
        channel=NotificationChannel.IN_APP,
        subject=subject,
        body=body,
        dedupe_key=dedupe_key or f"inapp:{clinic_id}:{user_id}:{notification_type}:{related_id or ''}:{_now().isoformat()}",
        related_type=related_type,
        related_id=related_id,
    )


def queue_patient_notification(
    *,
    clinic_id: str,
    patient,
    notification_type: str,
    channel: str,
    body: str,
    subject: str | None = None,
    dedupe_key: str,
    related_type: str | None = None,
    related_id: str | None = None,
) -> Notification | None:
    """Respect consent and contact preferences before queueing patient messages."""
    if channel == NotificationChannel.EMAIL:
        if not patient.consent_email or not patient.email:
            return None
        recipient = patient.email
    elif channel == NotificationChannel.SMS:
        if not patient.consent_sms or not patient.phone:
            return None
        recipient = patient.phone
    elif channel == NotificationChannel.WHATSAPP:
        if not patient.consent_whatsapp or not patient.phone:
            return None
        recipient = patient.phone
    else:
        return None
    return queue_notification(
        clinic_id=clinic_id,
        patient_id=patient.id,
        notification_type=notification_type,
        channel=channel,
        recipient=recipient,
        subject=subject,
        body=body,
        dedupe_key=dedupe_key,
        related_type=related_type,
        related_id=related_id,
    )


def _smtp_send(notification: Notification) -> tuple[bool, str | None, str | None]:
    config = current_app.config
    host = config.get("SMTP_HOST")
    if not host:
        return False, None, "SMTP is not configured"
    message = EmailMessage()
    message["Subject"] = notification.subject or "ClinicFlow notification"
    message["From"] = formataddr((config.get("MAIL_FROM_NAME", "ClinicFlow"), config.get("MAIL_FROM")))
    message["To"] = notification.recipient
    message.set_content(notification.body)
    try:
        context = ssl.create_default_context()
        if config.get("SMTP_PORT") == 465:
            with smtplib.SMTP_SSL(host, config.get("SMTP_PORT"), timeout=15, context=context) as server:
                if config.get("SMTP_USERNAME"):
                    server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
                server.send_message(message)
        else:
            with smtplib.SMTP(host, config.get("SMTP_PORT"), timeout=15) as server:
                server.ehlo()
                if config.get("SMTP_USE_TLS"):
                    server.starttls(context=context)
                    server.ehlo()
                if config.get("SMTP_USERNAME"):
                    server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
                server.send_message(message)
        return True, "smtp", None
    except Exception as exc:  # pragma: no cover - provider failures are environment-specific
        logger.warning("SMTP delivery failed: %s", exc)
        return False, "smtp", "Email delivery failed"


def _twilio_send(notification: Notification) -> tuple[bool, str | None, str | None]:
    config = current_app.config
    sid = config.get("TWILIO_ACCOUNT_SID")
    token = config.get("TWILIO_AUTH_TOKEN")
    sender = config.get("TWILIO_FROM_NUMBER")
    if not (sid and token and sender):
        return False, None, "SMS provider is not configured"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode(
        {"To": notification.recipient, "From": sender, "Body": notification.body}
    ).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header(
        "Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode())
        return True, "twilio", payload.get("sid")
    except Exception as exc:  # pragma: no cover
        logger.warning("SMS delivery failed: %s", exc)
        return False, "twilio", "SMS delivery failed"


def _whatsapp_send(notification: Notification) -> tuple[bool, str | None, str | None]:
    config = current_app.config
    phone_id = config.get("WHATSAPP_PHONE_ID")
    token = config.get("WHATSAPP_TOKEN")
    if not (phone_id and token):
        return False, None, "WhatsApp provider is not configured"
    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": notification.recipient,
            "type": "text",
            "text": {"body": notification.body},
        }
    ).encode()
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode())
        message_id = (result.get("messages") or [{}])[0].get("id")
        return True, "whatsapp_cloud", message_id
    except Exception as exc:  # pragma: no cover
        logger.warning("WhatsApp delivery failed: %s", exc)
        return False, "whatsapp_cloud", "WhatsApp delivery failed"


def deliver_notification(notification: Notification) -> Notification:
    """Attempt delivery once. Caller is responsible for committing the session."""
    if notification.status == NotificationStatus.SENT:
        return notification
    notification.attempts = (notification.attempts or 0) + 1
    channel = notification.channel
    success = False
    provider = None
    message_id = None
    error = None

    if channel == NotificationChannel.IN_APP:
        success, provider = True, "in_app"
    elif channel == NotificationChannel.EMAIL:
        success, provider, error = _smtp_send(notification)
    elif channel == NotificationChannel.SMS:
        success, provider, error = _twilio_send(notification)
    elif channel == NotificationChannel.WHATSAPP:
        success, provider, error = _whatsapp_send(notification)
    else:
        error = "Unsupported notification channel"

    if success:
        notification.status = NotificationStatus.SENT
        notification.sent_at = _now()
        notification.provider = provider
        notification.provider_message_id = message_id
        notification.error = None
    elif current_app.config.get("DEMO_MODE") and not current_app.config.get("SMTP_HOST") and channel != NotificationChannel.EMAIL:
        # Simulated messaging in the public demo. Clearly labelled in the log.
        notification.status = NotificationStatus.SENT
        notification.sent_at = _now()
        notification.provider = f"demo_{channel}"
        notification.error = None
    elif error and "not configured" in error.lower():
        notification.status = NotificationStatus.SKIPPED
        notification.provider = None
        notification.error = error
    else:
        notification.status = NotificationStatus.FAILED
        notification.provider = provider
        notification.error = error
        if notification.attempts < notification.max_attempts:
            notification.next_attempt_at = _now() + timedelta(minutes=5 * notification.attempts)
    return notification


def send_password_reset(user, reset_url: str) -> Notification | None:
    notification = queue_notification(
        clinic_id=user.clinic_id,
        user_id=user.id,
        notification_type="password_reset",
        channel=NotificationChannel.EMAIL,
        recipient=user.email,
        recipient_masked=mask_email(user.email),
        subject="Reset your ClinicFlow password",
        body=(
            "A password reset was requested for your ClinicFlow account.\n\n"
            f"Reset link (valid for {current_app.config.get('RESET_TOKEN_MINUTES', 30)} minutes):\n{reset_url}\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
        dedupe_key=f"pwdreset:{user.id}:{_now().timestamp()}",
    )
    if notification:
        deliver_notification(notification)
    return notification


def retry_pending_notifications(limit: int = 100) -> dict:
    now = _now()
    pending = (
        Notification.query.filter(
            Notification.status.in_([NotificationStatus.QUEUED, NotificationStatus.FAILED]),
            Notification.attempts < Notification.max_attempts,
            or_(Notification.next_attempt_at.is_(None), Notification.next_attempt_at <= now),
        )
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )
    sent = failed = 0
    for notification in pending:
        deliver_notification(notification)
        if notification.status == NotificationStatus.SENT:
            sent += 1
        else:
            failed += 1
    db.session.commit()
    return {"attempted": len(pending), "sent": sent, "failed": failed}
