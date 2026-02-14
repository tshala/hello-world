from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import uuid4

from onboarding_offboarding.domain import (
    REQUIRED_DOCUMENTS,
    SUPPORTED_DOC_MIME_TYPES,
    AssignmentDetails,
    Asset,
    AssetStatus,
    AuditEntry,
    ChecklistInstanceItem,
    ChecklistTemplateItem,
    ChecklistType,
    DocumentRecord,
    EmployeeProfile,
    EntryPath,
    NotificationEvent,
    OffboardingRecord,
    OffboardingType,
    OnboardingStatus,
    PersonalInfo,
    default_invite_expiry,
)


class ValidationError(ValueError):
    pass


class OnboardingOffboardingModule:
    def __init__(self) -> None:
        self.employees: Dict[str, EmployeeProfile] = {}
        self.assets: Dict[str, Asset] = {}
        self.checklist_templates: Dict[ChecklistType, List[ChecklistTemplateItem]] = {
            ChecklistType.ONBOARDING: [
                ChecklistTemplateItem("add_teams", "Add to MS Teams", True),
                ChecklistTemplateItem("announcement", "Post Company Announcement", True),
            ],
            ChecklistType.FULL_OFFBOARDING: [
                ChecklistTemplateItem("exit_interview", "Conduct Exit Interview", True),
            ],
            ChecklistType.CLIENT_OFFBOARDING: [
                ChecklistTemplateItem("remove_client_slack", "Remove from Client Slack", True),
            ],
        }
        self.onboarding_checklists: Dict[str, List[ChecklistInstanceItem]] = {}
        self.offboarding_records: Dict[str, OffboardingRecord] = {}
        self.notifications: List[NotificationEvent] = []
        self.audit_log: List[AuditEntry] = []

    def _audit(self, action: str, actor: str, details: Dict[str, str]) -> None:
        self.audit_log.append(AuditEntry(datetime.utcnow(), action, actor, details))

    def _new_employee_id(self) -> str:
        return f"EMP-{uuid4().hex[:8].upper()}"

    def _build_checklist(self, checklist_type: ChecklistType) -> List[ChecklistInstanceItem]:
        return [
            ChecklistInstanceItem(item.key, item.label, item.mandatory)
            for item in self.checklist_templates[checklist_type]
        ]

    def invite_new_hire(self, name: str, personal_email: str, actor: str = "hr_admin") -> EmployeeProfile:
        employee_id = self._new_employee_id()
        profile = EmployeeProfile(
            employee_id=employee_id,
            personal_email=personal_email,
            entry_path=EntryPath.CANDIDATE_SELF_SERVICE,
            invitation_expires_at=default_invite_expiry(datetime.utcnow()),
        )
        self.employees[employee_id] = profile
        self.onboarding_checklists[employee_id] = self._build_checklist(ChecklistType.ONBOARDING)
        self._audit("invite_created", actor, {"employee_id": employee_id, "name": name})
        return profile

    def create_full_profile(self, personal_email: str, actor: str = "hr_admin") -> EmployeeProfile:
        employee_id = self._new_employee_id()
        profile = EmployeeProfile(
            employee_id=employee_id,
            personal_email=personal_email,
            entry_path=EntryPath.HR_MANUAL,
            invitation_expires_at=None,
            status=OnboardingStatus.PENDING_REVIEW,
        )
        self.employees[employee_id] = profile
        self.onboarding_checklists[employee_id] = self._build_checklist(ChecklistType.ONBOARDING)
        self._audit("manual_profile_created", actor, {"employee_id": employee_id})
        return profile

    def submit_personal_info(
        self,
        employee_id: str,
        personal_info: PersonalInfo,
        documents: Dict[str, DocumentRecord],
        actor: str = "candidate",
    ) -> None:
        profile = self.employees[employee_id]
        self._validate_documents(documents)
        self._validate_insurance(personal_info)
        profile.personal_info = personal_info
        profile.documents = documents
        profile.status = OnboardingStatus.PENDING_REVIEW
        self._audit("candidate_submission", actor, {"employee_id": employee_id})

    def _validate_documents(self, documents: Dict[str, DocumentRecord]) -> None:
        missing = REQUIRED_DOCUMENTS.difference(documents.keys())
        if missing:
            raise ValidationError(f"Missing required documents: {sorted(missing)}")
        for doc in documents.values():
            if doc.mime_type not in SUPPORTED_DOC_MIME_TYPES:
                raise ValidationError(f"Unsupported mime type: {doc.mime_type}")

    def _validate_insurance(self, personal_info: PersonalInfo) -> None:
        if personal_info.insurance.enroll:
            if not personal_info.insurance.coverage_level:
                raise ValidationError("Coverage level required when insurance enrollment is yes")

    def hr_enrich_assignment(self, employee_id: str, assignment: AssignmentDetails, actor: str = "hr_admin") -> None:
        profile = self.employees[employee_id]
        profile.assignment = assignment
        profile.status = OnboardingStatus.HR_ENRICHED
        self._audit("hr_assignment_completed", actor, {"employee_id": employee_id})

    def sync_hris_and_trigger_notifications(self, employee_id: str, actor: str = "system") -> List[NotificationEvent]:
        profile = self.employees[employee_id]
        if not profile.personal_info or not profile.assignment:
            raise ValidationError("Profile must include personal info and HR assignment before sync")

        assignment = profile.assignment
        personal = profile.personal_info

        events = [
            NotificationEvent(
                recipient=assignment.client_manager_email,
                subject=f"New Team Member {personal.full_legal_name} confirmed",
                body=f"{personal.full_legal_name} starts on {assignment.start_date.isoformat()}.",
            ),
            NotificationEvent(
                recipient=assignment.isa_manager_email,
                subject=f"Onboarding initiated for {personal.full_legal_name}",
                body="Please prepare for arrival.",
            ),
            NotificationEvent(
                recipient="finance@company.example",
                subject=f"Add {personal.full_legal_name} to payroll",
                body=f"Effective {assignment.start_date.isoformat()} salary={assignment.salary} iban={personal.iban}",
            ),
        ]

        if personal.insurance.enroll:
            events.append(
                NotificationEvent(
                    recipient="insurance@provider.example",
                    subject=f"Enroll {personal.full_legal_name}",
                    body=f"Plan={personal.insurance.coverage_level} dependents={len(personal.insurance.dependents)}",
                )
            )

        self.notifications.extend(events)
        profile.status = OnboardingStatus.READY_FOR_PROVISIONING
        self._audit("hris_sync_completed", actor, {"employee_id": employee_id, "events": str(len(events))})
        return events

    def add_asset(self, asset: Asset, actor: str = "it_admin") -> None:
        self.assets[asset.asset_tag] = asset
        self._audit("asset_created", actor, {"asset_tag": asset.asset_tag})

    def find_available_assets(self, asset_type: Optional[str] = None, os: Optional[str] = None) -> List[Asset]:
        matches = [a for a in self.assets.values() if a.status == AssetStatus.AVAILABLE]
        if asset_type:
            matches = [a for a in matches if a.asset_type == asset_type]
        if os:
            matches = [a for a in matches if a.os == os]
        return matches

    def reserve_asset_for_employee(self, employee_id: str, asset_tag: str, actor: str = "it_support") -> None:
        asset = self.assets[asset_tag]
        if asset.status != AssetStatus.AVAILABLE:
            raise ValidationError("Only available assets can be reserved")
        asset.status = AssetStatus.RESERVED
        self._audit("asset_reserved", actor, {"employee_id": employee_id, "asset_tag": asset_tag})

    def confirm_logistics_delivery(self, employee_id: str, asset_tag: str, proof: str, actor: str = "logistics") -> None:
        profile = self.employees[employee_id]
        asset = self.assets[asset_tag]
        if asset.status != AssetStatus.RESERVED:
            raise ValidationError("Asset must be reserved before delivery confirmation")
        asset.status = AssetStatus.ASSIGNED
        profile.asset_tags.append(asset_tag)
        profile.status = OnboardingStatus.IN_PROGRESS
        self._audit(
            "asset_delivered",
            actor,
            {"employee_id": employee_id, "asset_tag": asset_tag, "proof": proof},
        )

    def complete_onboarding_task(self, employee_id: str, task_key: str, actor: str = "hr_admin") -> None:
        checklist = self.onboarding_checklists[employee_id]
        for item in checklist:
            if item.key == task_key:
                item.done = True
                self._audit("onboarding_task_done", actor, {"employee_id": employee_id, "task_key": task_key})
                return
        raise ValidationError(f"Task not found: {task_key}")

    def close_onboarding(self, employee_id: str, actor: str = "hr_admin") -> None:
        checklist = self.onboarding_checklists[employee_id]
        incomplete_mandatory = [i.key for i in checklist if i.mandatory and not i.done]
        if incomplete_mandatory:
            raise ValidationError(f"Mandatory tasks not completed: {incomplete_mandatory}")
        profile = self.employees[employee_id]
        profile.status = OnboardingStatus.COMPLETED
        self._audit("onboarding_completed", actor, {"employee_id": employee_id})

    def send_welcome_email(self, employee_id: str, actor: str = "hr_admin") -> NotificationEvent:
        profile = self.employees[employee_id]
        if not profile.assignment or not profile.assignment.company_email:
            raise ValidationError("Company email must be set before sending welcome email")
        event = NotificationEvent(
            recipient=profile.assignment.company_email,
            subject="Welcome to the company",
            body="Your Day 1 guide and login instructions are attached.",
        )
        self.notifications.append(event)
        self._audit("welcome_email_sent", actor, {"employee_id": employee_id})
        return event

    def configure_checklist(self, checklist_type: ChecklistType, items: List[ChecklistTemplateItem], actor: str = "system_admin") -> None:
        self.checklist_templates[checklist_type] = items
        self._audit("checklist_template_updated", actor, {"checklist_type": checklist_type.value})

    def initiate_offboarding(
        self,
        employee_id: str,
        offboarding_type: OffboardingType,
        effective_date: date,
        actor: str = "hr_admin",
    ) -> OffboardingRecord:
        checklist_type = (
            ChecklistType.FULL_OFFBOARDING
            if offboarding_type == OffboardingType.FULL_OFFBOARDING
            else ChecklistType.CLIENT_OFFBOARDING
        )
        record = OffboardingRecord(
            employee_id=employee_id,
            offboarding_type=offboarding_type,
            effective_date=effective_date,
            checklist=self._build_checklist(checklist_type),
        )
        self.offboarding_records[employee_id] = record
        self._trigger_offboarding_notifications(employee_id, record)
        self._audit("offboarding_initiated", actor, {"employee_id": employee_id, "type": offboarding_type.value})
        return record

    def _trigger_offboarding_notifications(self, employee_id: str, record: OffboardingRecord) -> None:
        profile = self.employees[employee_id]
        if not profile.personal_info:
            return
        name = profile.personal_info.full_legal_name

        self.notifications.append(
            NotificationEvent(
                recipient="finance@company.example",
                subject=f"Offboarding update for {name}",
                body=f"Type={record.offboarding_type.value} effective={record.effective_date.isoformat()}",
            )
        )
        if record.offboarding_type == OffboardingType.FULL_OFFBOARDING:
            self.notifications.append(
                NotificationEvent(
                    recipient="insurance@provider.example",
                    subject=f"Remove {name} from policy",
                    body=f"Effective {record.effective_date.isoformat()}",
                )
            )

    def required_asset_returns(self, employee_id: str, offboarding_type: OffboardingType) -> List[str]:
        profile = self.employees[employee_id]
        tags: List[str] = []
        for tag in profile.asset_tags:
            asset = self.assets[tag]
            if offboarding_type == OffboardingType.FULL_OFFBOARDING:
                tags.append(tag)
            elif asset.client_scoped:
                tags.append(tag)
        return tags

    def export_audit_log(self) -> List[dict]:
        return [asdict(entry) for entry in self.audit_log]
