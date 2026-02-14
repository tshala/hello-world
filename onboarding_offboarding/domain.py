from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


class EntryPath(str, Enum):
    CANDIDATE_SELF_SERVICE = "candidate_self_service"
    HR_MANUAL = "hr_manual"


class AssetStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ASSIGNED = "assigned"
    IN_MAINTENANCE = "in_maintenance"
    DAMAGED = "damaged"
    RETIRED = "retired"


class OnboardingStatus(str, Enum):
    INVITED = "invited"
    PENDING_REVIEW = "pending_review"
    HR_ENRICHED = "hr_enriched"
    READY_FOR_PROVISIONING = "ready_for_provisioning"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class OffboardingType(str, Enum):
    FULL_OFFBOARDING = "full_offboarding"
    CLIENT_OFFBOARDING = "client_offboarding"


class ChecklistType(str, Enum):
    ONBOARDING = "onboarding"
    FULL_OFFBOARDING = "full_offboarding"
    CLIENT_OFFBOARDING = "client_offboarding"


@dataclass
class DocumentRecord:
    name: str
    mime_type: str


@dataclass
class InsuranceInfo:
    enroll: bool
    coverage_level: Optional[str] = None
    dependents: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class PersonalInfo:
    full_legal_name: str
    date_of_birth: date
    national_id_number: str
    emergency_contact: str
    home_address: str
    iban: str
    swift: str
    insurance: InsuranceInfo


@dataclass
class AssignmentDetails:
    client_name: str
    department: str
    isa_manager_name: str
    isa_manager_email: str
    client_manager_name: str
    client_manager_email: str
    company_email: str
    start_date: date
    salary: float


@dataclass
class EmployeeProfile:
    employee_id: str
    personal_email: str
    entry_path: EntryPath
    invitation_expires_at: Optional[datetime]
    status: OnboardingStatus = OnboardingStatus.INVITED
    personal_info: Optional[PersonalInfo] = None
    documents: Dict[str, DocumentRecord] = field(default_factory=dict)
    assignment: Optional[AssignmentDetails] = None
    asset_tags: List[str] = field(default_factory=list)


@dataclass
class Asset:
    asset_tag: str
    serial_number: str
    asset_type: str
    os: str
    model: str
    purchase_date: date
    warranty_expiry: date
    status: AssetStatus = AssetStatus.AVAILABLE
    client_scoped: bool = False


@dataclass
class ChecklistTemplateItem:
    key: str
    label: str
    mandatory: bool


@dataclass
class ChecklistInstanceItem:
    key: str
    label: str
    mandatory: bool
    done: bool = False


@dataclass
class NotificationEvent:
    recipient: str
    subject: str
    body: str
    retries: int = 0


@dataclass
class OffboardingRecord:
    employee_id: str
    offboarding_type: OffboardingType
    effective_date: date
    checklist: List[ChecklistInstanceItem]
    completed: bool = False


@dataclass
class AuditEntry:
    timestamp: datetime
    action: str
    actor: str
    details: Dict[str, str]


REQUIRED_DOCUMENTS = {
    "signed_contract",
    "cv",
    "diploma",
    "certificates",
}


SUPPORTED_DOC_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}


def default_invite_expiry(now: datetime) -> datetime:
    return now + timedelta(days=7)
