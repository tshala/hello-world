import unittest
from datetime import date

from onboarding_offboarding.domain import (
    AssignmentDetails,
    Asset,
    AssetStatus,
    ChecklistTemplateItem,
    ChecklistType,
    DocumentRecord,
    InsuranceInfo,
    OffboardingType,
    PersonalInfo,
)
from onboarding_offboarding.service import OnboardingOffboardingModule, ValidationError


class ModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = OnboardingOffboardingModule()

    def _personal_info(self, enroll_insurance: bool = True) -> PersonalInfo:
        return PersonalInfo(
            full_legal_name="Ada Lovelace",
            date_of_birth=date(1995, 1, 1),
            national_id_number="NID-123",
            emergency_contact="+15550001",
            home_address="1 Main St",
            iban="IBAN123",
            swift="SWFTCODE",
            insurance=InsuranceInfo(
                enroll=enroll_insurance,
                coverage_level="Family" if enroll_insurance else None,
                dependents=[{"name": "Bob", "dob": "2020-02-02"}] if enroll_insurance else [],
            ),
        )

    def _docs(self):
        return {
            "signed_contract": DocumentRecord("contract.pdf", "application/pdf"),
            "cv": DocumentRecord("cv.pdf", "application/pdf"),
            "diploma": DocumentRecord("degree.png", "image/png"),
            "certificates": DocumentRecord("cert.jpg", "image/jpeg"),
        }

    def _assignment(self) -> AssignmentDetails:
        return AssignmentDetails(
            client_name="Acme",
            department="Engineering",
            isa_manager_name="Isa Manager",
            isa_manager_email="isa@example.com",
            client_manager_name="Client Manager",
            client_manager_email="client@example.com",
            company_email="ada@company.example",
            start_date=date(2026, 2, 15),
            salary=100000,
        )

    def test_candidate_path_sync_and_insurance_notification(self):
        profile = self.module.invite_new_hire("Ada", "ada.personal@example.com")
        self.module.submit_personal_info(profile.employee_id, self._personal_info(True), self._docs())
        self.module.hr_enrich_assignment(profile.employee_id, self._assignment())

        events = self.module.sync_hris_and_trigger_notifications(profile.employee_id)
        self.assertEqual(4, len(events))

    def test_asset_provisioning_flow(self):
        profile = self.module.create_full_profile("ada.personal@example.com")
        self.module.submit_personal_info(profile.employee_id, self._personal_info(False), self._docs(), actor="hr_admin")
        self.module.hr_enrich_assignment(profile.employee_id, self._assignment())
        self.module.sync_hris_and_trigger_notifications(profile.employee_id)

        asset = Asset(
            asset_tag="LPT-2026-001",
            serial_number="SN001",
            asset_type="Laptop",
            os="MacOS",
            model="MBP",
            purchase_date=date(2026, 1, 1),
            warranty_expiry=date(2029, 1, 1),
        )
        self.module.add_asset(asset)

        matches = self.module.find_available_assets(asset_type="Laptop", os="MacOS")
        self.assertEqual(1, len(matches))

        self.module.reserve_asset_for_employee(profile.employee_id, asset.asset_tag)
        self.assertEqual(AssetStatus.RESERVED, self.module.assets[asset.asset_tag].status)

        self.module.confirm_logistics_delivery(profile.employee_id, asset.asset_tag, proof="TRACK-1")
        self.assertEqual(AssetStatus.ASSIGNED, self.module.assets[asset.asset_tag].status)

    def test_onboarding_completion_requires_mandatory_tasks(self):
        profile = self.module.create_full_profile("ada.personal@example.com")
        with self.assertRaises(ValidationError):
            self.module.close_onboarding(profile.employee_id)

    def test_admin_checklist_configuration_applies_to_new_offboarding(self):
        self.module.configure_checklist(
            ChecklistType.CLIENT_OFFBOARDING,
            [ChecklistTemplateItem("update_cv", "Update CV", True)],
        )
        profile = self.module.create_full_profile("ada.personal@example.com")
        self.module.submit_personal_info(profile.employee_id, self._personal_info(False), self._docs(), actor="hr_admin")
        record = self.module.initiate_offboarding(
            profile.employee_id,
            OffboardingType.CLIENT_OFFBOARDING,
            date(2026, 3, 1),
        )
        self.assertEqual("update_cv", record.checklist[0].key)


if __name__ == "__main__":
    unittest.main()
