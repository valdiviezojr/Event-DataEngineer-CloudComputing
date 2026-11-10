"""Configuración del seeding. Todo se puede sobrescribir con variables de entorno."""
import os
import uuid
from datetime import date


def _env(name, default=None):
    v = os.getenv(name)
    return default if v is None or v == "" else v


def _int(name, default):
    return int(_env(name, default))


def _list(name, default):
    return [x.strip() for x in _env(name, ",".join(default)).split(",") if x.strip()]


STAGE = _env("STAGE", "dev")
AWS_REGION = _env("AWS_REGION", "us-east-1")

TENANTS = _list("SEED_TENANTS", ["tenant_a", "tenant_b", "tenant_c"])
PER_TENANT = _int("SEED_PER_TENANT", 10_000)
SAMPLE_PER_TENANT = 100

# Fecha de referencia ("hoy" para los datos). Solo afecta valores, nunca las claves.
REFERENCE_DATE = date.fromisoformat(_env("SEED_REFERENCE_DATE", date.today().isoformat()))
TZ_OFFSET_HOURS = _int("TZ_OFFSET_HOURS", -5)
FAKER_LOCALE = _env("SEED_FAKER_LOCALE", "es_MX")

# Namespace de uuid5: cambiarlo genera IDs nuevos (otro dataset). Mantenerlo fijo para reanudar.
NAMESPACE = uuid.UUID(_env("SEED_NAMESPACE", "6d1f3c1e-2b5a-4c8e-9f0a-4b1d2c3e4f50"))

# Actor que figura en createdBy / changedBy / approvedBy (los handlers usan el email del token o "system").
SEED_ACTOR = _env("SEED_ACTOR", "system")

# ───────────── DynamoDB ─────────────
DYNAMO_TABLES = {
    "recruitment": _env("RECRUITMENT_TABLE", f"ms-recruitment-table-{STAGE}"),
    "performance": _env("PERFORMANCE_TABLE", f"ms-performance-table-{STAGE}"),
    "attendance": _env("ATTENDANCE_TABLE", f"ms-attendance-table-{STAGE}"),
}
DYNAMO_WORKERS = _int("SEED_DYNAMO_WORKERS", 8)
DYNAMO_MAX_RETRIES = _int("SEED_DYNAMO_MAX_RETRIES", 8)

# Recruitment
VACANCIES_PER_TENANT = _int("SEED_VACANCIES_PER_TENANT", 50)
# Etapa final de los candidatos (todos enviados: no se siembran DRAFT). Pesos relativos.
CANDIDATE_STAGE_WEIGHTS = {"APPLIED": 40, "INTERVIEW": 25, "OFFER": 10, "HIRED": 5, "REJECTED": 20}

# Performance: cada empleado aporta GOALS_PER_EMPLOYEE metas + len(CYCLES) * len(RELATIONSHIPS) evaluaciones.
# Con los defaults: 2 + 2*4 = 10 ítems/empleado → 1,000 empleados evaluados por tenant (80% EVALUATION, 20% GOAL).
PERF_GOALS_PER_EMPLOYEE = _int("SEED_PERF_GOALS_PER_EMPLOYEE", 2)
PERF_RELATIONSHIPS = ["SELF", "MANAGER", "PEER", "DIRECT_REPORT"]
PERF_CYCLES = _list("SEED_PERF_CYCLES", [])  # vacío => trimestre de REFERENCE_DATE y el anterior
PERF_GOAL_STATUS_WEIGHTS = {"ACTIVE": 60, "COMPLETED": 30, "CANCELLED": 10}

# Attendance: N marcaciones repartidas en ATTENDANCE_EMPLOYEES empleados × días hábiles hacia atrás.
ATTENDANCE_EMPLOYEES = _int("SEED_ATTENDANCE_EMPLOYEES", 100)
LEAVES_RATIO = float(_env("SEED_LEAVES_RATIO", "0.02"))  # 200 LEAVE por tenant con 10,000

# ───────────── RDS PostgreSQL ─────────────
RDS = {
    "host": _env("DB_HOST"),
    "port": _int("DB_PORT", 5432),
    "dbname": _env("DB_NAME", "hcm_db"),
    "user": _env("DB_USER", "postgres"),
    "password": _env("DB_PASSWORD", _env("DB_PASS")),
    "sslmode": _env("DB_SSLMODE", "prefer"),
    "connect_timeout": _int("DB_CONNECT_TIMEOUT", 5),
}
RDS_PAGE_SIZE = _int("SEED_RDS_PAGE_SIZE", 2000)

# Schema por tenant (patrón Single Database, Multiple Schemas). Por defecto schema = tenant.
SCHEMAS = {t: _env(f"SCHEMA_{t.upper()}", t) for t in TENANTS}

# TODO: ajustar al esquema final de ms-core-hr (documento de diseño, sección Core HR).
# Claves = nombre lógico usado por el script; valores = nombre real en la BD.
CORE_HR = {
    "departments": {"table": "departments", "columns": {"id": "department_id", "name": "name", "budget": "budget"}},
    "employees": {
        "table": "employees",
        "columns": {
            "id": "employee_id",
            "department_id": "department_id",
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "email",
            "hire_date": "hire_date",
            "status": "status",
        },
    },
    "contracts": {
        "table": "contracts",
        "columns": {"id": "contract_id", "employee_id": "employee_id", "salary": "salary", "start_date": "start_date", "contract_type": "contract_type"},
    },
}
DEPARTMENTS_PER_TENANT = _int("SEED_DEPARTMENTS_PER_TENANT", 20)
CONTRACT_TYPES = _list("SEED_CONTRACT_TYPES", ["INDEFINIDO", "PLAZO_FIJO", "PART_TIME", "PRACTICAS"])  # TODO: ajustar al esquema final

# TODO: ajustar al esquema final de ms-payroll (documento de diseño, sección Nóminas).
PAYROLL = {
    "periods": {"table": "payroll_periods", "columns": {"id": "period_id", "name": "period_name", "is_closed": "is_closed"}},
    "pay_slips": {
        "table": "pay_slips",
        "columns": {
            "id": "pay_slip_id",
            "period_id": "period_id",
            "employee_id": "employee_id",
            "base_salary": "base_salary",
            "deductions": "deductions",
            "net_pay": "net_pay",
            "generated_at": "generated_at",
        },
    },
}
# N boletas = PAYROLL_EMPLOYEES empleados × ceil(N / PAYROLL_EMPLOYEES) periodos mensuales.
PAYROLL_EMPLOYEES = _int("SEED_PAYROLL_EMPLOYEES", 1000)
PAYROLL_DEDUCTION_RATE = float(_env("SEED_PAYROLL_DEDUCTION_RATE", "0.13"))  # TODO: regla real de descuentos de ms-payroll

SERVICES = ["core_hr", "payroll", "recruitment", "performance", "attendance"]
RDS_SERVICES = ["core_hr", "payroll"]
DYNAMO_SERVICES = ["recruitment", "performance", "attendance"]
