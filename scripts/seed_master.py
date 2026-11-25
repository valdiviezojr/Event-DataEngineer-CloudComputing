#!/usr/bin/env python3
"""Carga reproducible con preflight obligatorio y verificación por claves."""
import argparse
from contextlib import closing
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile

import dynamo_writer
import generators
from preflight import inspect_aws
import rds_writer
import seed_config as C
from verify_seed import validate

VERSION = 2


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def complementary_counts(data):
    result = {}
    for tenant, (tables, services) in data.items():
        counts = Counter(row["entityType"] for groups in services.values() for group in groups for row in group)
        result[tenant] = {
            "departments_reused": len(C.DEPARTMENTS),
            "departments_inserted": len(tables["departments"]),
            "contracts": len(tables["contracts"]),
            "employee_salary_profiles": len(tables["employee_salary_profiles"]),
            "payroll_periods": len(tables["payroll_periods"]),
            "payroll_employees": len({row["employee_id"] for row in tables["pay_slips"]}),
            **{name: counts[name] for name in ("VACANCY", "UNIQUE_GUARD", "EVAL_SUMMARY", "LEAVE")},
            "unpaid_leaves_ledger": 0,
        }
    return result


def manifest(data, departments, sql_destination, dynamo_destinations):
    return {
        "version": VERSION,
        "namespace": str(C.NAMESPACE), "reference_date": C.REFERENCE_DATE.isoformat(),
        "hire_date": C.HIRE_DATE.isoformat(), "periods": list(C.PERIODS), "cycles": list(C.CYCLES),
        "departments": departments, "excluded_auth_ids": list(C.EXCLUDED_AUTH_IDS),
        "postgresql": sql_destination, "dynamodb": dynamo_destinations,
        "counts": validate(data), "complementary": complementary_counts(data),
        "sha256": {tenant: {
            "postgresql": digest(tables),
            **{service: digest(groups) for service, groups in services.items()},
        } for tenant, (tables, services) in data.items()},
    }


def save_or_compare(path, expected, *, create):
    if create and not path.exists():
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            temporary = Path(temp.name)
            try:
                temp.write(encoded(expected) + b"\n")
                temp.flush()
                os.fsync(temp.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
                directory = os.open(path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink()
    if json.loads(path.read_text()) != expected:
        raise ValueError(f"{path}: el manifiesto difiere de los datos, configuración o destinos actuales")


def dynamo_pass(client, tables, data, *, verify=False, insert=False):
    for service, table in tables.items():
        for tenant, (_, services) in data.items():
            groups = services[service]
            dynamo_writer.check_associations(client, table, tenant, service, groups)
            dynamo_writer.reconcile(client, table, groups, verify=verify, insert=insert)


def run_online(mode, path):
    import psycopg2

    region, tables, db = C.destinations()
    writing = mode != "verify"
    dynamo, resources = inspect_aws(region, tables, load=writing, check_iam=mode != "diagnose")
    with closing(psycopg2.connect(**db)) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn:
            departments = rds_writer.inspect(conn, writing=writing, prepare_load=writing)
            with conn.cursor() as cur:
                cur.execute("SELECT oid::text FROM pg_database WHERE datname = current_database()")
                database_oid, = cur.fetchone()
            data = generators.dataset(generators.FULL_SIZE, departments)
            expected = manifest(data, departments, {**db, "oid": database_oid}, resources)
            if mode in ("load", "verify"):
                save_or_compare(path, expected, create=False)
            rds_writer.reconcile(conn, data, verify=not writing)
        dynamo_pass(dynamo, tables, data, verify=not writing)
        if mode == "preflight":
            save_or_compare(path, expected, create=True)
        if mode == "load":
            conn.set_session(isolation_level="READ COMMITTED", readonly=False)
            with conn:
                locked_departments = rds_writer.inspect(conn, writing=True, lock=True)
                if locked_departments != departments:
                    raise ValueError("Los UUID de los departamentos cambiaron durante el preflight")
                rds_writer.reconcile(conn, data, insert=True)
                rds_writer.reconcile(conn, data, verify=True)
            print("PostgreSQL confirmado. Iniciando las transacciones DynamoDB.", flush=True)
            dynamo_pass(dynamo, tables, data, insert=True)
            dynamo_pass(dynamo, tables, data, verify=True)
        return expected["counts"], expected["complementary"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("dry-run", "diagnose", "preflight", "load", "verify"))
    parser.add_argument("--sample", action="store_true", help="Solo para dry-run")
    parser.add_argument("--manifest", type=Path, default=Path("seed-30k-manifest.json"))
    aliases = parser.add_mutually_exclusive_group()
    aliases.add_argument("--dry-run", dest="alias", action="store_const", const="dry-run")
    aliases.add_argument("--verify", dest="alias", action="store_const", const="verify")
    args = parser.parse_args(argv)
    if bool(args.mode) == bool(args.alias):
        parser.error("indica un único modo, como comando o como opción compatible")
    args.mode = args.mode or args.alias
    if args.sample and args.mode != "dry-run":
        parser.error("--sample solo está permitido para dry-run")
    try:
        print("Sin vínculo con Auth. IDs incompatibles excluidos:", ", ".join(C.EXCLUDED_AUTH_IDS), flush=True)
        if args.mode == "dry-run":
            size = generators.SAMPLE_SIZE if args.sample else generators.FULL_SIZE
            data = generators.dataset(size, generators.dry_departments())
            counts = validate(data, sample=args.sample)
            complementary = complementary_counts(data)
            print(f"SHA-256 de la simulación: {digest(data)}")
        else:
            if args.mode == "diagnose":
                print("Diagnóstico de solo lectura. Omite la simulación IAM y no habilita la carga.", flush=True)
            counts, complementary = run_online(args.mode, args.manifest)
        totals = {name: sum(tenant[name] for tenant in counts.values()) for name in next(iter(counts.values()))}
        print(json.dumps({"por_tenant": counts, "total_por_entidad": totals, "complementarios_por_tenant": complementary,
                          "TOTAL_GLOBAL": sum(totals.values())}, indent=2))
        return 0
    except Exception as exc:
        print(f"{args.mode} detenido: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
