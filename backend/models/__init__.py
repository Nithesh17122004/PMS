"""Import every model so SQLAlchemy's metadata is complete."""
from .appointment import Appointment, AppointmentStatus
from .base import as_utc, utcnow, uuid4_str
from .billing import Invoice, InvoiceItem, InvoiceStatus, Payment, PaymentMethod, Refund
from .clinic import AuditLog, Clinic, ClinicSetting, DocumentSequence
from .consultation import (
    Consultation,
    ConsultationStatus,
    Diagnosis,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
)
from .doctor import Doctor, DoctorLeave, DoctorSchedule
from .followup import FollowUpPlan, FollowUpReminder, FollowUpStatus, ReminderStatus
from .lab import LabOrder, LabOrderItem, LabOrderStatus, LabResult, LabTest
from .notification import Notification, NotificationChannel, NotificationStatus
from .patient import MedicalDocument, Patient
from .pharmacy import InventoryBatch, Medication, StockMovement, Supplier
from .rbac import Permission, Role, UserRole, role_permissions
from .token import DailyToken, TokenSequence, TokenStatus, VisitType
from .user import PasswordResetToken, User

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "AuditLog",
    "Clinic",
    "ClinicSetting",
    "Consultation",
    "ConsultationStatus",
    "DailyToken",
    "Diagnosis",
    "Doctor",
    "DoctorLeave",
    "DoctorSchedule",
    "DocumentSequence",
    "FollowUpPlan",
    "FollowUpReminder",
    "FollowUpStatus",
    "InventoryBatch",
    "Invoice",
    "InvoiceItem",
    "InvoiceStatus",
    "LabOrder",
    "LabOrderItem",
    "LabOrderStatus",
    "LabResult",
    "LabTest",
    "MedicalDocument",
    "Medication",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "PasswordResetToken",
    "Patient",
    "Payment",
    "PaymentMethod",
    "Permission",
    "Prescription",
    "PrescriptionItem",
    "PrescriptionStatus",
    "Refund",
    "ReminderStatus",
    "Role",
    "StockMovement",
    "Supplier",
    "TokenSequence",
    "TokenStatus",
    "User",
    "UserRole",
    "VisitType",
    "as_utc",
    "utcnow",
    "uuid4_str",
]
