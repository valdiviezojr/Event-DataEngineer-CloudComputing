"""Configuración del seeding. Todo se puede sobrescribir con variables de entorno."""
import json
import os
import re
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

# Usuarios demo del stack hcm-auth (tenantId + employeeId + email). Sus tenants son los que se siembran y sus
# employeeId se usan tal cual en core_hr, payroll, performance y attendance. Ver load_users().
USERS_FILE = _env("SEED_USERS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json"))
# Vacío => los tenants del archivo de usuarios. Si se fija, cada tenant debe tener usuarios en el archivo.
TENANTS = _list("SEED_TENANTS", [])
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
# Ciclos fijos (forman parte de las claves EVAL#/SUMMARY#): reejecutar otro día no crea ciclos nuevos.
# Vacío (SEED_PERF_CYCLES=",") => trimestre de REFERENCE_DATE y el anterior.
PERF_CYCLES = _list("SEED_PERF_CYCLES", ["2026-Q3", "2026-Q4"])
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

# Schema por tenant (patrón Single Database, Multiple Schemas). Por defecto schema = tenant (SCHEMA_TENANT_A=…).
def schema_for(tenant):
    return _env(f"SCHEMA_{tenant.upper()}", tenant)

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


# ───────────── Usuarios demo (hcm-auth) ─────────────
# Mismo regex que EMPLOYEE_RE (lib/http.js) y TENANT_RE (dynamoTenantFilter.js).
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class UsersFileError(Exception):
    """Archivo de usuarios ausente o inválido. El mensaje es para el usuario."""


def load_users(path=None, tenants=None):
    """Lee y valida el archivo de usuarios. Devuelve {tenantId: [usuario, ...]} en el orden del archivo.

    Formatos aceptados: una lista de usuarios ({"tenantId", "employeeId", "email"?, "role"?}) o
    {"tenants": [...], "users": [...]}. `tenants` (o la clave "tenants") son los tenants a sembrar: cada uno
    debe tener al menos un usuario. No escribe nada; se llama antes de cualquier escritura.
    """
    path = path or USERS_FILE
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise UsersFileError(f"no existe el archivo de usuarios {path} (configura SEED_USERS_FILE o --users-file)")
    except (OSError, ValueError) as e:
        raise UsersFileError(f"no se pudo leer {path} como JSON: {e}")

    declared = None
    if isinstance(raw, dict):
        declared, raw = raw.get("tenants"), raw.get("users")
        if declared is not None and (not isinstance(declared, list) or not all(isinstance(t, str) for t in declared)):
            raise UsersFileError(f"{path}: \"tenants\" debe ser una lista de strings")
    if not isinstance(raw, list) or not raw:
        raise UsersFileError(f"{path}: se esperaba una lista no vacía de usuarios (o {{\"users\": [...]}})")

    by_tenant, errors = {}, []
    for i, u in enumerate(raw):
        where = f"usuario #{i + 1}"
        if not isinstance(u, dict):
            errors.append(f"{where}: debe ser un objeto")
            continue
        t, e = u.get("tenantId"), u.get("employeeId")
        where += f" ({u.get('email') or e})"
        if not isinstance(t, str) or not ID_RE.match(t):
            errors.append(f"{where}: tenantId {t!r} no cumple ^[A-Za-z0-9_-]{{1,64}}$")
            continue
        if not isinstance(e, str) or not ID_RE.match(e):
            errors.append(f"{where}: employeeId {e!r} no cumple ^[A-Za-z0-9_-]{{1,64}}$")
            continue
        email = u.get("email")
        if email is not None and (not isinstance(email, str) or "@" not in email):
            errors.append(f"{where}: email {email!r} inválido")
            continue
        users = by_tenant.setdefault(t, [])
        if any(x["employeeId"] == e for x in users):
            errors.append(f"{where}: employeeId {e} repetido en {t}")
        elif email and any((x.get("email") or "").lower() == email.lower() for x in users):
            errors.append(f"{where}: email {email} repetido en {t}")
        else:
            users.append({"tenantId": t, "employeeId": e, "email": email.lower() if email else None, "role": u.get("role")})

    wanted = list(tenants or declared or by_tenant)
    for t in wanted:
        if not ID_RE.match(t):
            errors.append(f"tenant {t!r} no cumple ^[A-Za-z0-9_-]{{1,64}}$")
        elif t not in by_tenant:
            errors.append(f"el tenant {t} no tiene usuarios en {path}")
    if errors:
        raise UsersFileError(f"{path} inválido:\n  - " + "\n  - ".join(errors))
    return {t: by_tenant[t] for t in wanted}
