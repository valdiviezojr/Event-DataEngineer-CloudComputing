"""Preflight y carga transaccional de las tablas oficiales de PostgreSQL."""
import json
from pathlib import Path

import seed_config as C

HERE = Path(__file__).resolve().parent
SQL_SIGNATURE = (HERE / "schema_contract.sql").read_text(encoding="utf-8")
TABLE_KEYS = {
    "departments": "department_id",
    "employees": "employee_id",
    "contracts": "contract_id",
    "employee_salary_profiles": "employee_id",
    "payroll_periods": "period_id",
    "pay_slips": "pay_slip_id",
}
TABLES = [*TABLE_KEYS, "unpaid_leaves_ledger"]


def inspect(conn, *, writing=False, lock=False, prepare_load=False):
    from psycopg2 import sql

    canonical = {tuple(row) for row in json.loads((HERE / "schema_contract.json").read_text())}
    departments = {}
    with conn.cursor() as cur:
        cur.execute("SET LOCAL search_path TO pg_catalog")
        cur.execute("SET LOCAL lock_timeout TO '10s'")
        if writing:
            cur.execute("SELECT pg_is_in_recovery(), current_setting('transaction_read_only'), "
                        "current_setting('session_replication_role')")
            standby, read_only, replication_role = cur.fetchone()
            if standby or replication_role != "origin" or (lock and read_only != "off"):
                raise ValueError("PostgreSQL no está en modo primario con replicación origin")
        if prepare_load:
            cur.execute("SHOW default_transaction_read_only")
            if cur.fetchone()[0] != "off":
                raise ValueError("PostgreSQL está configurado como solo lectura")
        for tenant in C.TENANTS:
            if lock:
                cur.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                    sql.SQL(", ").join(sql.Identifier(tenant, table) for table in TABLES),
                ))
            cur.execute(SQL_SIGNATURE, {"tenant": tenant, "tables": TABLES})
            actual = set(cur.fetchall())
            if actual != canonical:
                missing = sorted(canonical - actual)[:4]
                extra = sorted(actual - canonical)[:4]
                raise ValueError(f"{tenant}: esquema no compatible, faltan {missing}; diferencias {extra}")
            cur.execute("SELECT has_schema_privilege(%s, 'USAGE')", (tenant,))
            if not cur.fetchone()[0]:
                raise ValueError(f"{tenant}: falta USAGE")
            for table in TABLES:
                target = sql.Identifier(tenant, table).as_string(conn)
                cur.execute("SELECT has_table_privilege(%s, 'SELECT'), "
                            "has_table_privilege(%s, 'INSERT'), "
                            "has_table_privilege(%s, 'UPDATE, DELETE, TRUNCATE')",
                            (target, target, target))
                read, insert, can_lock = cur.fetchone()
                if not read or (writing and ((table in TABLE_KEYS and not insert) or not can_lock)):
                    raise ValueError(f"{tenant}.{table}: permisos insuficientes para leer, insertar o bloquear")
            cur.execute(sql.SQL("SELECT name, department_id::text FROM {} WHERE name = ANY(%s)").format(
                sql.Identifier(tenant, "departments")), (list(C.DEPARTMENTS),))
            departments[tenant] = dict(cur.fetchall())
            if set(departments[tenant]) != set(C.DEPARTMENTS):
                raise ValueError(f"{tenant}: faltan departamentos oficiales")
    return departments


def present(cur, tenant, table, expected):
    from psycopg2 import sql

    key = TABLE_KEYS[table]
    columns = tuple(expected[0])
    fields = [sql.SQL("{}::text").format(sql.Identifier(column))
              if column.endswith("_id") and column != "source_candidate_id" else sql.Identifier(column)
              for column in columns]
    cur.execute(sql.SQL("SELECT {} FROM {} WHERE {} = ANY(%s::uuid[])").format(
        sql.SQL(", ").join(fields), sql.Identifier(tenant, table), sql.Identifier(key)),
        ([row[key] for row in expected],))
    return {row[columns.index(key)]: dict(zip(columns, row)) for row in cur.fetchall()}


def reconcile(conn, data, *, verify=False, insert=False):
    """Comprueba coincidencias exactas y claves naturales antes de cada inserción."""
    from psycopg2 import sql
    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        for tenant, (tables, services) in data.items():
            employees = [row["employee_id"] for row in tables["employees"]]
            period_names = [row["period_name"] for row in tables["payroll_periods"]]
            period_ids = [row["period_id"] for row in tables["payroll_periods"]]
            department_rows = tables["departments"]
            foreign_slips = [row["pay_slip_id"] for row in tables["pay_slips"]]
            leave_ids = [row["leaveId"] for group in services["attendance"] for row in group
                         if row["entityType"] == "LEAVE"]
            checks = (
                ("departments", "name = ANY(%s) AND NOT (department_id = ANY(%s::uuid[]))",
                 ([row["name"] for row in department_rows], [row["department_id"] for row in department_rows])),
                ("employees", "email = ANY(%s) AND NOT (employee_id = ANY(%s::uuid[]))",
                 ([row["email"] for row in tables["employees"]], employees)),
                ("payroll_periods", "period_name = ANY(%s) AND NOT (period_id = ANY(%s::uuid[]))", (period_names, period_ids)),
                ("pay_slips", "period_id = ANY(%s::uuid[]) AND NOT (pay_slip_id = ANY(%s::uuid[]))",
                 (period_ids, foreign_slips)),
                ("contracts", "employee_id = ANY(%s::uuid[]) AND NOT (contract_id = ANY(%s::uuid[]))",
                 (employees, [row["contract_id"] for row in tables["contracts"]])),
                ("unpaid_leaves_ledger",
                 "(employee_id = ANY(%s::uuid[]) AND period_target = ANY(%s)) OR leave_id = ANY(%s::uuid[])",
                 (employees, period_names, leave_ids)),
            )
            for table, condition, args in checks:
                cur.execute(sql.SQL("SELECT 1 FROM {} WHERE {} LIMIT 1").format(
                    sql.Identifier(tenant, table), sql.SQL(condition)), args)
                if cur.fetchone():
                    raise ValueError(f"{tenant}.{table}: fila ajena en clave natural o relación de seeding")
            missing_by_table = {}
            for table, key in TABLE_KEYS.items():
                expected = tables[table]
                existing = present(cur, tenant, table, expected)
                missing = []
                for row in expected:
                    found = existing.get(row[key])
                    if found is None:
                        missing.append(row)
                    elif found != row:
                        raise ValueError(f"{tenant}.{table}: conflicto en {row[key]}")
                if verify and missing:
                    raise ValueError(f"{tenant}.{table}: faltan {len(missing)} de {len(expected)} claves")
                missing_by_table[table] = missing
            # SQL se confirma en una sola transacción para los tres tenants.
            if insert:
                for table, rows in missing_by_table.items():
                    if rows:
                        columns = tuple(rows[0])
                        query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                            sql.Identifier(tenant, table), sql.SQL(", ").join(map(sql.Identifier, columns)))
                        execute_values(cur, query, [tuple(row.values()) for row in rows], page_size=1000)
