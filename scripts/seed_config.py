"""Parámetros fijos compartidos por el generador y el manifiesto."""
import os
from datetime import date
from uuid import UUID

TENANTS = ("tenant_a", "tenant_b", "tenant_c")
NAMESPACE = UUID("db5e9d63-39e5-4763-8f62-dc18e22da4ab")
REFERENCE_DATE = date(2026, 1, 1)
HIRE_DATE = date(2024, 1, 2)
PERIODS = tuple(f"2025-{month:02}" for month in range(3, 13))
CYCLES = ("2025-Q3", "2025-Q4")
DEPARTMENTS = ("Ingeniería", "Recursos Humanos", "Finanzas", "Operaciones")
SEED_DEPARTMENTS = tuple(f"HCM Seed 30k {index:02}" for index in range(1, 17))
CONTRACT_TYPES = ("FULL_TIME", "PART_TIME", "CONTRACTOR")
EXCLUDED_AUTH_IDS = ("emp-001", "emp-a-hr", "emp-b-hr", "52")
TABLE_PREFIXES = {
    "recruitment": "ms-recruitment-table",
    "performance": "ms-performance-table",
    "attendance": "ms-attendance-table",
}


def destinations():
    stage = os.getenv("STAGE", "dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    db = {key: os.environ[f"DB_{env}"] for key, env in (
        ("host", "HOST"), ("dbname", "NAME"), ("user", "USER"),
    )}
    db["port"] = int(os.getenv("DB_PORT", "5432"))
    db["sslmode"] = "verify-full"
    db["sslrootcert"] = os.environ["DB_SSLROOTCERT"]
    db["connect_timeout"] = 10
    if not all(db.values()) or not 0 < db["port"] <= 65535:
        raise ValueError("Configuración PostgreSQL incompleta")
    tables = {kind: os.getenv(f"{kind.upper()}_TABLE", f"{prefix}-{stage}")
              for kind, prefix in TABLE_PREFIXES.items()}
    if len(set(tables.values())) != len(tables):
        raise ValueError("Las tres tablas DynamoDB deben ser distintas")
    return region, tables, db
