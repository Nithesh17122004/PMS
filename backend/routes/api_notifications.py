from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, request
from sqlalchemy import or_

from ..auth.security import audit
from ..extensions import db
from ..models import Notification, NotificationChannel, NotificationStatus
from ..permissions.rbac import permission_required
from ..permissions.tenant import current_clinic, get_scoped_or_404
from ..services.notification_service import deliver_notification, retry_pending_notifications
from ..utils.errors import ConflictError, ForbiddenError
from ..utils.responses import ok, pagination_meta, parse_pagination
from ..utils.serializers import notification_dict

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/api/notifications")
@permission_required("notifications.view")
def list_notifications():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=30)
    query = Notification.query.filter(
        Notification.clinic_id == clinic.id,
        or_(Notification.user_id == g.user.id, Notification.user_id.is_(None)),
    )
    if request.args.get("unread") in ("1", "true"):
        query = query.filter(Notification.read_at.is_(None), Notification.channel == NotificationChannel.IN_APP)
    channel = request.args.get("channel")
    if channel:
        query = query.filter(Notification.channel == channel)
    status = request.args.get("status")
    if status:
        query = query.filter(Notification.status == status)
    query = query.order_by(Notification.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([notification_dict(n) for n in items], pagination_meta(total, page, per_page))


@notifications_bp.get("/api/notifications/unread-count")
@permission_required("notifications.view")
def unread_count():
    clinic = current_clinic()
    count = Notification.query.filter(
        Notification.clinic_id == clinic.id,
        Notification.user_id == g.user.id,
        Notification.channel == NotificationChannel.IN_APP,
        Notification.read_at.is_(None),
    ).count()
    return ok({"count": count})


@notifications_bp.post("/api/notifications/<notification_id>/read")
@permission_required("notifications.view")
def mark_read(notification_id):
    notification = get_scoped_or_404(Notification, notification_id)
    if notification.user_id not in (None, g.user.id):
        raise ForbiddenError("This notification belongs to another user.")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return ok({"notification": notification_dict(notification)})


@notifications_bp.post("/api/notifications/read-all")
@permission_required("notifications.view")
def mark_all_read():
    clinic = current_clinic()
    now = datetime.now(timezone.utc)
    updated = Notification.query.filter(
        Notification.clinic_id == clinic.id,
        Notification.user_id == g.user.id,
        Notification.channel == NotificationChannel.IN_APP,
        Notification.read_at.is_(None),
    ).update({"read_at": now}, synchronize_session=False)
    db.session.commit()
    return ok({"updated": updated})


@notifications_bp.get("/api/notifications/outbox")
@permission_required("notifications.manage")
def outbox():
    clinic = current_clinic()
    page, per_page = parse_pagination(request.args, default_per_page=40)
    query = Notification.query.filter(Notification.clinic_id == clinic.id)
    status = request.args.get("status")
    if status:
        query = query.filter(Notification.status == status)
    channel = request.args.get("channel")
    if channel:
        query = query.filter(Notification.channel == channel)
    query = query.order_by(Notification.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok([notification_dict(n) for n in items], pagination_meta(total, page, per_page))


@notifications_bp.post("/api/notifications/<notification_id>/retry")
@permission_required("notifications.manage")
def retry(notification_id):
    notification = get_scoped_or_404(Notification, notification_id)
    if notification.status == NotificationStatus.SENT:
        raise ConflictError("This notification has already been delivered.")
    if notification.channel == NotificationChannel.IN_APP:
        raise ConflictError("In-app notifications do not need delivery retries.")
    deliver_notification(notification)
    audit(
        "notification.retried",
        "notification",
        notification.id,
        {"status": notification.status},
        clinic_id=notification.clinic_id,
        user_id=g.user.id,
    )
    db.session.commit()
    return ok({"notification": notification_dict(notification)})


@notifications_bp.post("/api/notifications/retry-pending")
@permission_required("notifications.manage")
def retry_all_pending():
    result = retry_pending_notifications(limit=100)
    return ok(result)


@notifications_bp.get("/api/notifications/channels")
@permission_required("notifications.view")
def channels():
    clinic = current_clinic()
    settings = clinic.settings
    return ok(
        {
            "channels": NotificationChannel.ALL,
            "statuses": [
                NotificationStatus.QUEUED,
                NotificationStatus.SENT,
                NotificationStatus.FAILED,
                NotificationStatus.SKIPPED,
                NotificationStatus.CANCELLED,
            ],
            "enabled": {
                "email": bool(settings and settings.reminder_email_enabled),
                "sms": bool(settings and settings.reminder_sms_enabled),
                "whatsapp": bool(settings and settings.reminder_whatsapp_enabled),
                "in_app": True,
            },
        }
    )
