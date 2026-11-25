from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generators as gen
from seed_master import digest
from verify_seed import REQUIRED, validate


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = gen.dataset(gen.SAMPLE_SIZE, gen.dry_departments())

    def test_sample_reproducibility(self):
        self.assertEqual(digest(self.sample), digest(gen.dataset(gen.SAMPLE_SIZE, gen.dry_departments())))
        observed = validate(self.sample, sample=True)
        self.assertEqual(sum(sum(row.values()) for row in observed.values()), 1500)

    def test_full_volumes(self):
        data = gen.dataset(gen.FULL_SIZE, gen.dry_departments())
        observed = validate(data)
        self.assertEqual(list(observed.values()), [REQUIRED] * 3)
        self.assertEqual(sum(sum(row.values()) for row in observed.values()), 150_000)
        self.assertEqual(data["tenant_a"][0]["employees"][0], self.sample["tenant_a"][0]["employees"][0])

    def test_missing_pay_slip(self):
        broken = deepcopy(self.sample)
        broken["tenant_b"][0]["pay_slips"].pop()
        with self.assertRaisesRegex(ValueError, "cobertura del período"):
            validate(broken, sample=True)

    def test_overlapping_leave_is_refused(self):
        broken = deepcopy(self.sample)
        attendance = broken["tenant_a"][1]["attendance"]
        marking = attendance[0][-1]
        leave = attendance[-1][0]
        self.assertEqual(marking["employeeId"], leave["employeeId"])
        leave["startDate"] = marking["date"]
        leave["endDate"] = marking["date"]
        with self.assertRaisesRegex(ValueError, "marcación en días de licencia"):
            validate(broken, sample=True)

    def test_detects_summary_and_guard_drift(self):
        for service, index, attribute, value in (
            ("performance", 2, "scoreSum", 0),
            ("recruitment", 0, "candidateId", "conflict"),
        ):
            with self.subTest(service=service):
                broken = deepcopy(self.sample)
                broken["tenant_c"][1][service][index][-1][attribute] = value
                with self.assertRaises(ValueError):
                    validate(broken, sample=True)

    def test_auth_is_independent(self):
        employees = self.sample["tenant_a"][0]["employees"]
        self.assertTrue(all(row["email"].endswith("@seed.example.invalid") for row in employees))
        self.assertNotIn("emp-001", {row["employee_id"] for row in employees})
