"""Generadores puros de datos de seed (sin AWS ni RDS).

Los ítems DynamoDB replican EXACTAMENTE lo que escriben los handlers:
  recruitment  createVacancy / createCandidate (+ guard) / submitCandidate / updateStage / updateVacancy
  performance  createGoal / updateGoal / submitEvaluation (+ SUMMARY)
  attendance   clockIn+clockOut / requestLeave / approveLeave

Todo es determinístico por (tenant, índice): las claves salen de uuid5 y los valores de un
random.Random sembrado con el mismo par, así que re-ejecutar produce los mismos ítems.

Usuarios demo (use_users): los primeros k empleados de cada tenant son los k usuarios del archivo, con su
employeeId y email EXACTOS; el resto se genera con uuid5 como siempre. Así los usuarios que inician sesión
en hcm-auth tienen marcaciones, licencias, metas, evaluaciones y SUMMARY propios.
"""
import math
import random
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from faker import Faker

import seed_config as C

# ───────────────────────── utilidades ─────────────────────────

_faker = Faker(C.FAKER_LOCALE)


def det_uuid(tenant, kind, idx):
    return str(uuid.uuid5(C.NAMESPACE, f"{tenant}:{kind}:{idx}"))


def rng_for(*parts):
    return random.Random(":".join(map(str, parts)))


def slugify(s):
    """Mismo algoritmo que createVacancy.js (keys de certificados)."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]


def iso(dt):
    """Igual que Date.prototype.toISOString(): UTC con milisegundos y 'Z'."""
    dt = dt.astimezone(timezone.utc)
    return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"


def ref_dt():
    return datetime.combine(C.REFERENCE_DATE, time(12, 0), tzinfo=timezone.utc)


def local_to_utc(d, hour, minute=0):
    return datetime.combine(d, time(hour, minute), tzinfo=timezone.utc) - timedelta(hours=C.TZ_OFFSET_HOURS)


def round2(x):
    """Math.round(x * 100) / 100 de JS para valores positivos."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_number(d):
    """Decimal → int si es entero (DynamoDB guarda 4.5 y 4 igual que JS)."""
    return int(d) if d == d.to_integral_value() else d


def pk(tenant):
    return f"TENANT#{tenant}"


# ───────────────────────── personas (compartidas) ─────────────────────────
# Un mismo employeeId se usa en core_hr, payroll, performance y attendance.

_USERS = {}  # {tenant: [usuario]} cargado con use_users(); vacío => solo empleados uuid5


def use_users(users):
    """Fija los usuarios demo por tenant (salida de seed_config.load_users)."""
    _USERS.clear()
    _USERS.update(users or {})
    employee.cache_clear()


def users_of(tenant):
    return _USERS.get(tenant, [])


def users_min_n(service, k):
    """N mínimo por tenant para que los k usuarios reciban datos en `service` (None = no aplica)."""
    if not k:
        return None
    if service == "performance":
        return k * (C.PERF_GOALS_PER_EMPLOYEE + len(perf_cycles()) * len(C.PERF_RELATIONSHIPS))
    if service in ("core_hr", "payroll", "attendance"):
        return k
    return None


def users_pool_error(k):
    """Los pools de empleados configurados deben alcanzar para todos los usuarios."""
    for name, size in (("SEED_ATTENDANCE_EMPLOYEES", C.ATTENDANCE_EMPLOYEES), ("SEED_PAYROLL_EMPLOYEES", C.PAYROLL_EMPLOYEES)):
        if size < k:
            return f"{name}={size} es menor que los {k} usuarios del tenant"
    return None

DEPARTMENTS = [
    "Tecnología", "Recursos Humanos", "Finanzas", "Operaciones", "Ventas", "Marketing", "Logística",
    "Mantenimiento", "Legal", "Atención al Cliente", "Compras", "Producción", "Calidad", "Seguridad",
    "Administración", "Proyectos", "Investigación", "Comunicaciones", "Auditoría", "Data & Analytics",
]


@lru_cache(maxsize=None)
def employee(tenant, i):
    r = rng_for(tenant, "employee", i)
    _faker.seed_instance(r.getrandbits(32))
    first, last = _faker.first_name()[:50], _faker.last_name()[:50]
    emp = {
        "employeeId": det_uuid(tenant, "employee", i),
        "firstName": first,
        "lastName": last,
        "fullName": f"{first} {last}",
        "email": f"{slugify(first)}.{slugify(last)}.{i}@{tenant.replace('_', '-')}.example.com"[:100],
        "departmentIndex": i % C.DEPARTMENTS_PER_TENANT,
        "hireDate": C.REFERENCE_DATE - timedelta(days=r.randint(30, 5 * 365)),
        "salary": Decimal(r.randrange(1200, 15000, 50)),
        "status": "ACTIVE" if r.random() < 0.95 else "INACTIVE",
        "contractType": r.choice(C.CONTRACT_TYPES),
    }
    users = users_of(tenant)
    if i < len(users):  # usuario demo: su employeeId y email exactos, siempre activo
        u = users[i]
        emp.update(employeeId=u["employeeId"], status="ACTIVE")
        if u.get("email"):
            emp["email"] = u["email"]
    return emp


# ───────────────────────── core_hr (RDS) ─────────────────────────


def core_hr_rows(tenant, n):
    departments = [
        {
            "id": det_uuid(tenant, "department", d),
            "name": DEPARTMENTS[d % len(DEPARTMENTS)] + ("" if d < len(DEPARTMENTS) else f" {d // len(DEPARTMENTS) + 1}"),
            "budget": Decimal(rng_for(tenant, "department", d).randrange(50_000, 2_000_000, 1000)),
        }
        for d in range(C.DEPARTMENTS_PER_TENANT)
    ]
    employees, contracts = [], []
    for i in range(n):
        e = employee(tenant, i)
        employees.append(
            {
                "id": e["employeeId"],
                "department_id": departments[e["departmentIndex"]]["id"],
                "first_name": e["firstName"],
                "last_name": e["lastName"],
                "email": e["email"],
                "hire_date": e["hireDate"],
                "status": e["status"],
            }
        )
        contracts.append(
            {
                "id": det_uuid(tenant, "contract", i),
                "employee_id": e["employeeId"],
                "salary": e["salary"],
                "start_date": e["hireDate"],
                "contract_type": e["contractType"],
            }
        )
    return {"departments": departments, "employees": employees, "contracts": contracts}


# ───────────────────────── payroll (RDS) ─────────────────────────


def _months_before(d, count):
    """Los `count` meses anteriores al mes de d, del más antiguo al más reciente."""
    y, m = d.year, d.month
    out = []
    for _ in range(count):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return list(reversed(out))


def payroll_rows(tenant, n):
    emps = max(1, min(C.PAYROLL_EMPLOYEES, n))
    months = _months_before(C.REFERENCE_DATE, math.ceil(n / emps))
    periods = [{"id": det_uuid(tenant, "period", f"{y}-{m:02d}"), "name": f"{y}-{m:02d}", "is_closed": True} for y, m in months]

    slips = []
    for i in range(n):
        p, e = divmod(i, emps)
        y, m = months[p]
        emp = employee(tenant, e)
        base = emp["salary"]
        ded = round2(base * Decimal(str(C.PAYROLL_DEDUCTION_RATE)))
        last_day = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1))
        slips.append(
            {
                "id": det_uuid(tenant, "pay_slip", f"{periods[p]['name']}:{emp['employeeId']}"),
                "period_id": periods[p]["id"],
                "employee_id": emp["employeeId"],
                "base_salary": base,
                "deductions": ded,
                "net_pay": base - ded,
                "generated_at": datetime.combine(last_day, time(23, 0)),
            }
        )
    return {"periods": periods, "pay_slips": slips}


# ───────────────────────── recruitment (DynamoDB) ─────────────────────────

JOB_TITLES = [
    "Desarrollador Backend", "Desarrollador Frontend", "Analista de Datos", "Ingeniero DevOps", "Electricista Industrial",
    "Contador Senior", "Asistente de RR.HH.", "Ejecutivo de Ventas", "Supervisor de Almacén", "Técnico de Mantenimiento",
    "Analista Financiero", "Diseñador UX", "Jefe de Proyectos", "Abogado Corporativo", "Operario de Producción",
]
LOCATIONS = ["Lima", "Arequipa", "Trujillo", "Cusco", "Piura", "Chiclayo", "Remoto"]
EMPLOYMENT_TYPES = ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"]
CERT_CATALOG = [
    ("SCTR vigente", True), ("Trabajos en altura", True), ("Curso PLC Siemens", False), ("Certificado de estudios", True),
    ("Inglés intermedio", False), ("Licencia de conducir A-I", False), ("Antecedentes policiales", True), ("AWS Cloud Practitioner", False),
]
STAGE_ORDER = ["APPLIED", "INTERVIEW", "OFFER", "HIRED"]
TRANSITIONS = {  # copia de updateStage.js
    "DRAFT": [], "APPLIED": ["INTERVIEW", "REJECTED"], "INTERVIEW": ["OFFER", "REJECTED"],
    "OFFER": ["HIRED", "REJECTED"], "HIRED": [], "REJECTED": [],
}
STAGE_NOTES = ["Entrevista coordinada", "Buen perfil técnico", "Pendiente referencias", "No cumple experiencia mínima", "Excelente entrevista"]


def vacancy_count(n):
    return max(1, min(C.VACANCIES_PER_TENANT, n // 20))


def _vacancy(tenant, v):
    r = rng_for(tenant, "vacancy", v)
    vacancy_id = f"v-{det_uuid(tenant, 'vacancy', v)}"
    created = ref_dt() - timedelta(days=60 + v % 30, minutes=r.randint(0, 600))
    s_min = r.randrange(1500, 6000, 100)
    certs = [
        {"key": slugify(name), "name": name, "description": "", "mandatory": mandatory}
        for name, mandatory in r.sample(CERT_CATALOG, r.randint(0, 3))
    ]
    return {
        "PK": pk(tenant),
        "SK": f"VACANCY#{vacancy_id}",
        "entityType": "VACANCY",
        "vacancyId": vacancy_id,
        "tenantId": tenant,
        "title": JOB_TITLES[v % len(JOB_TITLES)],
        "department": DEPARTMENTS[v % len(DEPARTMENTS)],
        "description": f"Vacante de {JOB_TITLES[v % len(JOB_TITLES)].lower()} para el área de {DEPARTMENTS[v % len(DEPARTMENTS)]}.",
        "location": r.choice(LOCATIONS),
        "employmentType": r.choice(EMPLOYMENT_TYPES),
        "salaryMin": s_min,
        "salaryMax": s_min + r.randrange(500, 4000, 100),
        "openings": r.randint(1, 5),
        "requireLinkedin": v % 3 == 0,
        "requiredCertificates": certs,
        "status": "OPEN",
        "candidatesCount": 0,
        "createdBy": C.SEED_ACTOR,
        "createdAt": iso(created),
        "updatedAt": iso(created),
    }


def _candidate(tenant, i, vac):
    r = rng_for(tenant, "candidate", i)
    _faker.seed_instance(r.getrandbits(32))
    first, last = _faker.first_name(), _faker.last_name()
    candidate_id = f"c-{det_uuid(tenant, 'candidate', i)}"
    email = f"{slugify(first)}.{slugify(last)}.{i}@candidatos.example.com"
    created = ref_dt() - timedelta(days=r.uniform(45, 58))

    stage = r.choices(list(C.CANDIDATE_STAGE_WEIGHTS), weights=list(C.CANDIDATE_STAGE_WEIGHTS.values()))[0]
    reached = r.choice(["APPLIED", "INTERVIEW", "OFFER"]) if stage == "REJECTED" else stage
    path = STAGE_ORDER[: STAGE_ORDER.index(reached) + 1] + (["REJECTED"] if stage == "REJECTED" else [])

    # submitCandidate: DRAFT → APPLIED (by = email del candidato); updateStage: resto (by = actor)
    t = created + timedelta(hours=r.uniform(0.5, 48))
    submitted = t
    history = [{"from": "DRAFT", "to": "APPLIED", "at": iso(t), "by": email, "note": None}]
    for prev, nxt in zip(path, path[1:]):
        t += timedelta(days=r.uniform(1, 8))
        history.append({"from": prev, "to": nxt, "at": iso(t), "by": C.SEED_ACTOR, "note": r.choice(STAGE_NOTES) if r.random() < 0.3 else None})

    certificates = {}
    for c in vac["requiredCertificates"]:
        uploaded = c["mandatory"] or r.random() < 0.5
        certificates[c["key"]] = {
            "name": c["name"],
            "description": c["description"],
            "mandatory": c["mandatory"],
            "status": "UPLOADED" if uploaded else "PENDING",
            "s3Key": f"{tenant}/recruitment/certificates/{candidate_id}/{c['key']}.pdf" if uploaded else None,
            "contentType": "application/pdf" if uploaded else None,
            "size": r.randint(40_000, 900_000) if uploaded else None,
            "uploadedAt": iso(submitted - timedelta(minutes=r.randint(5, 25))) if uploaded else None,
        }

    with_linkedin = vac["requireLinkedin"] or r.random() < 0.5
    item = {
        "PK": pk(tenant),
        "SK": f"CANDIDATE#{candidate_id}",
        "entityType": "CANDIDATE",
        "candidateId": candidate_id,
        "tenantId": tenant,
        "vacancyId": vac["vacancyId"],
        "vacancyTitle": vac["title"],
        "fullName": f"{first} {last}",
        "email": email,
        "phone": f"+51 9{r.randint(10_000_000, 99_999_999)}",
        "linkedin": {
            "url": f"https://linkedin.com/in/{slugify(first)}-{slugify(last)}-{i}",
            "headline": vac["title"],
            "yearsExperience": r.randint(0, 25),
        } if with_linkedin else None,
        "certificates": certificates,
        "stage": stage,
        "resumeS3Key": f"{tenant}/recruitment/resumes/{candidate_id}.pdf",
        "resumeStatus": "UPLOADED",
        "stageHistory": history,
        "createdAt": iso(created),
        "updatedAt": history[-1]["at"],
        "submittedAt": iso(submitted),
        "GSI1PK": f"{pk(tenant)}#VACANCY#{vac['vacancyId']}",
        "GSI1SK": f"CANDIDATE#{iso(created)}#{candidate_id}",
    }
    guard = {
        "PK": pk(tenant),
        "SK": f"UNIQUE#APPLICATION#{vac['vacancyId']}#{email}",
        "entityType": "UNIQUE_GUARD",
        "candidateId": candidate_id,
        "createdAt": iso(created),
    }
    return item, guard


def recruitment_items(tenant, n):
    vacancies = [_vacancy(tenant, v) for v in range(vacancy_count(n))]
    candidates, guards = [], []
    last_submit = defaultdict(str)
    for i in range(n):
        vac = vacancies[i % len(vacancies)]
        cand, guard = _candidate(tenant, i, vac)
        candidates.append(cand)
        guards.append(guard)
        # submitCandidate: ADD candidatesCount :one SET updatedAt = :now
        vac["candidatesCount"] += 1
        last_submit[vac["vacancyId"]] = max(last_submit[vac["vacancyId"]], cand["submittedAt"])

    for v, vac in enumerate(vacancies):
        if last_submit[vac["vacancyId"]]:
            vac["updatedAt"] = last_submit[vac["vacancyId"]]
        if v % 10 == 9:  # updateVacancy con status CLOSED
            closed = iso(ref_dt() - timedelta(days=1))
            vac.update(status="CLOSED", closedAt=closed, closedBy=C.SEED_ACTOR, closeReason="Puesto cubierto", updatedAt=closed, updatedBy=C.SEED_ACTOR)
    return vacancies + candidates + guards


# ───────────────────────── performance (DynamoDB) ─────────────────────────

COMPETENCIES = ["Trabajo en equipo", "Calidad técnica", "Comunicación", "Puntualidad", "Liderazgo", "Orientación a resultados", "Innovación", "Resolución de problemas"]
STRENGTHS = ["Liderazgo técnico", "Muy colaborativo", "Entrega a tiempo", "Buen manejo de clientes", "Proactividad", None]
IMPROVEMENTS = ["Documentar mejor", "Delegar más", "Mejorar puntualidad", "Comunicar avances", "Gestión del tiempo", None]
GOAL_TITLES = ["Certificación AWS Solutions Architect", "Reducir tiempos de respuesta 20%", "Completar curso de liderazgo", "Automatizar reporte mensual", "Mentorear a un practicante", "Cerrar 15 ventas nuevas", "Implementar pruebas unitarias", "Inglés nivel avanzado"]
_CYCLE_RE = re.compile(r"^(\d{4})-(Q[1-4]|H[12]|ANUAL)$")
_PERIOD_MONTHS = {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12), "H1": (1, 6), "H2": (7, 12), "ANUAL": (1, 12)}


def perf_cycles():
    if C.PERF_CYCLES:
        return C.PERF_CYCLES
    y, q = C.REFERENCE_DATE.year, (C.REFERENCE_DATE.month - 1) // 3 + 1
    py, pq = (y, q - 1) if q > 1 else (y - 1, 4)
    return [f"{py}-Q{pq}", f"{y}-Q{q}"]


def cycle_range(cycle):
    y, p = _CYCLE_RE.match(cycle).groups()
    m1, m2 = _PERIOD_MONTHS[p]
    y = int(y)
    return date(y, m1, 1), date(y + m2 // 12, m2 % 12 + 1, 1) - timedelta(days=1)


def _half(x):
    return max(1.0, min(5.0, round(x * 2) / 2))


def _goal(tenant, emp, e, g):
    r = rng_for(tenant, "goal", e, g)
    goal_id = f"g-{det_uuid(tenant, 'goal', f'{e}:{g}')}"
    status = r.choices(list(C.PERF_GOAL_STATUS_WEIGHTS), weights=list(C.PERF_GOAL_STATUS_WEIGHTS.values()))[0]
    created = ref_dt() - timedelta(days=r.randint(20, 120), minutes=r.randint(0, 600))
    if status == "ACTIVE":
        target = C.REFERENCE_DATE + timedelta(days=r.randint(15, 180))
        progress = r.randint(0, 19) * 5
    elif status == "COMPLETED":
        target = created.date() + timedelta(days=r.randint(15, 90))
        progress = 100
    else:
        target = created.date() + timedelta(days=r.randint(15, 120))
        progress = r.randint(0, 12) * 5

    item = {
        "PK": pk(tenant),
        "SK": f"GOAL#{emp['employeeId']}#{goal_id}",
        "entityType": "GOAL",
        "goalId": goal_id,
        "tenantId": tenant,
        "employeeId": emp["employeeId"],
        "employeeName": emp["fullName"],
        "employeeEmail": emp["email"].lower(),
        "title": r.choice(GOAL_TITLES),
        "description": "",
        "targetDate": target.isoformat(),
        "status": status,
        "progress": progress,
        "assignedBy": C.SEED_ACTOR,
        # Sin recordatorios y SIN GSI1PK/GSI1SK: el cron horario no debe ver estas metas (evita miles de correos SES).
        "reminder": {"enabled": False, "frequency": "WEEKLY", "everyDays": None, "hour": 9},
        "nextReminderAt": None,
        "lastReminderAt": None,
        "remindersSent": 0,
        "createdAt": iso(created),
        "updatedAt": iso(created),
    }

    changed = created + timedelta(days=r.randint(1, 10))
    if progress > 0:
        item["progressHistory"] = [{"from": 0, "to": progress, "at": iso(changed), "by": C.SEED_ACTOR, "note": None}]
    if status == "COMPLETED":
        item["completedAt"] = iso(changed)
    if status == "CANCELLED":
        item["cancelledAt"] = iso(changed)
    if progress > 0 or status != "ACTIVE":
        item.update(updatedAt=iso(changed), updatedBy=C.SEED_ACTOR)
    return item


def _evaluation(tenant, emp, e, cycle_idx, cycle, rel_idx, rel, pool):
    r = rng_for(tenant, "evaluation", e, cycle, rel)
    base = rng_for(tenant, "ability", e)
    ability = base.uniform(2.5, 4.4)
    trend = base.uniform(-0.6, 0.8)
    names = base.sample(COMPETENCIES, 4)

    evaluator = emp if rel == "SELF" else employee(tenant, (e + rel_idx) % pool)
    level = ability + trend * cycle_idx + (0.4 if rel == "SELF" else 0)
    comps = [{"name": n, "score": to_number(Decimal(str(_half(level + r.uniform(-0.75, 0.75))))), "comment": None} for n in names]
    score = to_number(round2(sum(Decimal(str(c["score"])) for c in comps) / len(comps)))

    start, end = cycle_range(cycle)
    end = min(end, C.REFERENCE_DATE - timedelta(days=1))
    day = max(start, end - timedelta(days=r.randint(0, max(0, min(20, (end - start).days)))))
    created = datetime.combine(day, time(r.randint(13, 23), r.randint(0, 59)), tzinfo=timezone.utc)

    return {
        "PK": pk(tenant),
        "SK": f"EVAL#{emp['employeeId']}#{cycle}#{evaluator['employeeId']}",
        "entityType": "EVALUATION",
        "evalId": f"e-{det_uuid(tenant, 'evaluation', f'{e}:{cycle}:{rel}')}",
        "tenantId": tenant,
        "employeeId": emp["employeeId"],
        "employeeName": emp["fullName"],
        "employeeEmail": emp["email"].lower(),
        "evaluatorId": evaluator["employeeId"],
        "evaluatorName": evaluator["fullName"],
        "relationship": rel,
        "cycle": cycle,
        "score": score,
        "competencies": comps,
        "strengths": r.choice(STRENGTHS),
        "improvements": r.choice(IMPROVEMENTS),
        "feedback": None,
        "anonymous": rel == "PEER" and r.random() < 0.5,
        "status": "SUBMITTED",
        "submittedBy": C.SEED_ACTOR,
        "createdAt": iso(created),
    }


def _summaries(tenant, evaluations):
    """Mismo resultado que el Update ADD evaluationsCount/scoreSum de submitEvaluation.js."""
    groups = defaultdict(list)
    for ev in evaluations:
        groups[(ev["employeeId"], ev["cycle"])].append(ev)
    out = []
    for (emp_id, cycle), evs in groups.items():
        evs.sort(key=lambda x: x["createdAt"])
        last = evs[-1]
        out.append(
            {
                "PK": pk(tenant),
                "SK": f"SUMMARY#{emp_id}#{cycle}",
                "entityType": "EVAL_SUMMARY",
                "tenantId": tenant,
                "employeeId": emp_id,
                "employeeName": last["employeeName"],
                "cycle": cycle,
                "evaluationsCount": len(evs),
                "scoreSum": to_number(sum(Decimal(str(x["score"])) for x in evs)),
                "lastScore": last["score"],
                "lastEvaluationAt": last["createdAt"],
                "updatedAt": last["createdAt"],
            }
        )
    return out


def performance_items(tenant, n):
    cycles = perf_cycles()
    rels = C.PERF_RELATIONSHIPS
    slots = C.PERF_GOALS_PER_EMPLOYEE + len(cycles) * len(rels)
    pool = max(math.ceil(n / slots), len(rels))  # evaluadores siempre distintos del evaluado
    goals, evaluations = [], []
    for i in range(n):
        e, s = divmod(i, slots)
        emp = employee(tenant, e)
        if s < C.PERF_GOALS_PER_EMPLOYEE:
            goals.append(_goal(tenant, emp, e, s))
        else:
            ci, ri = divmod(s - C.PERF_GOALS_PER_EMPLOYEE, len(rels))
            evaluations.append(_evaluation(tenant, emp, e, ci, cycles[ci], ri, rels[ri], pool))
    return goals + evaluations + _summaries(tenant, evaluations)


# ───────────────────────── attendance (DynamoDB) ─────────────────────────

LEAVE_TYPE_WEIGHTS = {"VACATION": 50, "SICK": 20, "UNPAID": 15, "OTHER": 15}
UNPAID_TYPES = {"UNPAID", "OTHER"}  # misma regla que approveLeave.js
LEAVE_REASONS = ["Viaje familiar", "Descanso médico", "Trámite personal", "Mudanza", "Capacitación externa", None]


def _workdays_before(d, count):
    out, cur = [], d
    while len(out) < count:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur)
    return list(reversed(out))


def attendance_items(tenant, n):
    emps = max(1, min(C.ATTENDANCE_EMPLOYEES, n))
    days = _workdays_before(C.REFERENCE_DATE, math.ceil(n / emps))
    items = []
    for i in range(n):
        d_idx, e = divmod(i, emps)
        emp = employee(tenant, e)
        day = days[d_idx]
        r = rng_for(tenant, "attendance", e, day.isoformat())
        clock_in = local_to_utc(day, 7, 45) + timedelta(minutes=r.randint(0, 75), seconds=r.randint(0, 59))
        worked = r.randint(480, 600)
        clock_out = clock_in + timedelta(minutes=worked, seconds=r.randint(0, 59))
        items.append(
            {
                "PK": pk(tenant),
                "SK": f"ATTENDANCE#{emp['employeeId']}#{day.isoformat()}",
                "entityType": "ATTENDANCE",
                "tenantId": tenant,
                "employeeId": emp["employeeId"],
                "date": day.isoformat(),
                "clockIn": iso(clock_in),
                "status": "CLOSED",
                "recordedBy": C.SEED_ACTOR,
                "createdAt": iso(clock_in),
                "updatedAt": iso(clock_out),
                "clockOut": iso(clock_out),
                "workedMinutes": int((clock_out - clock_in).total_seconds() // 60),
                "closedBy": C.SEED_ACTOR,
            }
        )

    # Licencias futuras, sin solapamiento por empleado: ventanas de 15 días, duración 1–5.
    # Las j < k caen en los k usuarios demo (e = j), así que cada usuario tiene al menos una.
    for j in range(max(1, round(n * C.LEAVES_RATIO), len(users_of(tenant)))):
        k, e = divmod(j, emps)
        emp = employee(tenant, e)
        r = rng_for(tenant, "leave", j)
        start = C.REFERENCE_DATE + timedelta(days=7 + 15 * k + r.randint(0, 3))
        total = r.randint(1, 5)
        end = start + timedelta(days=total - 1)
        leave_type = r.choices(list(LEAVE_TYPE_WEIGHTS), weights=list(LEAVE_TYPE_WEIGHTS.values()))[0]
        leave_id = f"l-{det_uuid(tenant, 'leave', j)}"
        created = ref_dt() - timedelta(days=r.randint(1, 10), minutes=r.randint(0, 600))
        item = {
            "PK": pk(tenant),
            "SK": f"LEAVE#{leave_id}",
            "entityType": "LEAVE",
            "tenantId": tenant,
            "leaveId": leave_id,
            "employeeId": emp["employeeId"],
            "type": leave_type,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "totalDays": total,
            "reason": r.choice(LEAVE_REASONS),
            "status": "PENDING",
            "requestedBy": C.SEED_ACTOR,
            "createdAt": iso(created),
            "updatedAt": iso(created),
            "GSI1PK": f"{pk(tenant)}#EMPLOYEE#{emp['employeeId']}",
            "GSI1SK": f"LEAVE#{start.isoformat()}#{leave_id}",
        }
        if r.random() < 0.5:  # aprobada (los seeds no publican leave.approved)
            approved = created + timedelta(hours=r.randint(1, 20))
            item.update(
                status="APPROVED",
                daysUnpaid=total if leave_type in UNPAID_TYPES else 0,
                approvedBy=C.SEED_ACTOR,
                approvedAt=iso(approved),
                approvalNote=None,
                updatedAt=iso(approved),
            )
        items.append(item)
    return items


# ───────────────────────── API común ─────────────────────────

# Prefijo de SK por entityType (para --verify con Query sobre PK + begins_with(SK)).
SK_PREFIX = {
    "VACANCY": "VACANCY#",
    "CANDIDATE": "CANDIDATE#",
    "UNIQUE_GUARD": "UNIQUE#APPLICATION#",
    "GOAL": "GOAL#",
    "EVALUATION": "EVAL#",
    "EVAL_SUMMARY": "SUMMARY#",
    "ATTENDANCE": "ATTENDANCE#",
    "LEAVE": "LEAVE#",
}

# Entidades que cuentan para los "10,000 por tenant" de cada microservicio.
MAIN_ENTITIES = {
    "core_hr": ["employees"],
    "payroll": ["pay_slips"],
    "recruitment": ["CANDIDATE"],
    "performance": ["GOAL", "EVALUATION"],
    "attendance": ["ATTENDANCE"],
}

_GENERATORS = {
    "core_hr": core_hr_rows,
    "payroll": payroll_rows,
    "recruitment": recruitment_items,
    "performance": performance_items,
    "attendance": attendance_items,
}


def generate(service, tenant, n):
    """RDS: {tabla_lógica: [filas]} en orden de inserción. DynamoDB: lista de ítems."""
    return _GENERATORS[service](tenant, n)


def count_by_entity(service, data):
    if isinstance(data, dict):
        return {k: len(v) for k, v in data.items()}
    return dict(Counter(it["entityType"] for it in data))
