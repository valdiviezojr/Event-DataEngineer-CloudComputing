import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generators as gen
import rds_writer

SOCKET = os.getenv("SEED_TEST_LOCAL_SOCKET", "")
VERIFY = Path(__file__).resolve().parents[3] / "Proyecto2_Cloud_Integrante2/db/verify_30k_seeding.sql"


@unittest.skipUnless(SOCKET.startswith("/tmp/"), "requiere PostgreSQL local desechable en socket Unix bajo /tmp")
class LocalPostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg2

        self.conn = psycopg2.connect(host=SOCKET)
        self.addCleanup(self.conn.close)

    def test_trigger_refused(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE FUNCTION tenant_a.test_seed_trigger() RETURNS trigger "
                        "LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
            cur.execute("CREATE TRIGGER test_seed_trigger BEFORE INSERT ON tenant_a.employees "
                        "FOR EACH ROW EXECUTE FUNCTION tenant_a.test_seed_trigger()")
        with self.assertRaisesRegex(ValueError, "test_seed_trigger"):
            rds_writer.inspect(self.conn)
        self.conn.rollback()

    def test_conflicting_period_leaves_data_unchanged(self):
        departments = rds_writer.inspect(self.conn)
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO tenant_b.payroll_periods(period_name) VALUES ('2025-12')")
        data = gen.dataset(gen.SAMPLE_SIZE, departments)
        with self.assertRaisesRegex(ValueError, "tenant_b.payroll_periods"):
            rds_writer.reconcile(self.conn, data, insert=True)
        self.conn.rollback()
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tenant_a.employees WHERE email LIKE '%@seed.example.invalid'")
            self.assertEqual(cur.fetchone()[0], 0)

    def test_full_local_load_resume_and_sql_verification(self):
        def verify_sql():
            return subprocess.run(["psql", "-X", "-h", SOCKET, "-f", str(VERIFY)], text=True, capture_output=True)

        before = verify_sql()
        self.assertEqual(before.returncode, 3, before.stderr)
        self.assertIn("departamentos válidos=4", before.stderr)
        with self.conn:
            departments = rds_writer.inspect(self.conn, writing=True, lock=True)
            data = gen.dataset(gen.FULL_SIZE, departments)
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO tenant_a.employees(first_name, last_name, email) "
                            "VALUES ('Previo', 'Ajeno', 'previo@empresa.example')")
            rds_writer.reconcile(self.conn, data, insert=True)
            rds_writer.reconcile(self.conn, data, verify=True)
        try:
            with self.conn:
                rds_writer.reconcile(self.conn, data, insert=True)
                rds_writer.reconcile(self.conn, data, verify=True)
                with self.conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM tenant_a.employees")
                    self.assertEqual(cur.fetchone()[0], 10001)
                    cur.execute("SELECT count(*) FROM tenant_a.departments")
                    self.assertEqual(cur.fetchone()[0], 20)
                    cur.execute("SELECT count(DISTINCT employee_id), count(DISTINCT period_id) FROM tenant_a.pay_slips")
                    self.assertEqual(cur.fetchone(), (1000, 10))
                    cur.execute("SELECT count(*) FROM tenant_a.payroll_periods WHERE period_name = '2026-11'")
                    self.assertEqual(cur.fetchone()[0], 1)
            after = verify_sql()
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertIn("TOTAL_GLOBAL=60000", after.stderr)
            with self.conn, self.conn.cursor() as cur:
                cur.execute("DELETE FROM tenant_b.pay_slips WHERE pay_slip_id = %s",
                            (data["tenant_b"][0]["pay_slips"][0]["pay_slip_id"],))
            incomplete = verify_sql()
            self.assertEqual(incomplete.returncode, 3, incomplete.stderr)
            self.assertIn("2025-03: boletas=999", incomplete.stderr)
            with self.conn, self.assertRaisesRegex(ValueError, "faltan 1"):
                rds_writer.reconcile(self.conn, data, verify=True)
        finally:
            with self.conn, self.conn.cursor() as cur:
                for tenant in gen.C.TENANTS:
                    cur.execute(f"DELETE FROM {tenant}.pay_slips WHERE period_id IN "
                                f"(SELECT period_id FROM {tenant}.payroll_periods WHERE period_name BETWEEN '2025-03' AND '2025-12')")
                    cur.execute(f"DELETE FROM {tenant}.payroll_periods WHERE period_name BETWEEN '2025-03' AND '2025-12'")
                    cur.execute(f"DELETE FROM {tenant}.employee_salary_profiles WHERE email LIKE '%@seed.example.invalid'")
                    cur.execute(f"DELETE FROM {tenant}.employees WHERE email LIKE '%@seed.example.invalid' OR email = 'previo@empresa.example'")
                    cur.execute(f"DELETE FROM {tenant}.departments WHERE name LIKE 'HCM Seed 30k %'")
