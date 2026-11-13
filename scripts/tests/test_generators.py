"""Pruebas de los generadores, sin AWS ni RDS: IDs, claves y conteos según los handlers de reference/ y attendance."""
import re
from collections import Counter, defaultdict
from decimal import Decimal

import pytest

import generators as G
import seed_config as C

N = 10_000
TENANTS = ["tenant_a", "tenant_b", "tenant_c"]

# Regex copiados de los handlers
CANDIDATE_RE = re.compile(r"^c-[0-9a-f-]{36}$")    # createCandidate/updateStage/queries
VACANCY_RE = re.compile(r"^v-[0-9a-f-]{36}$")      # queries/updateVacancy
GOAL_RE = re.compile(r"^g-[0-9a-f-]{36}$")         # updateGoal
EVAL_RE = re.compile(r"^e-[0-9a-f-]{36}$")         # contrato evaluation.completed
LEAVE_RE = re.compile(r"^l-[0-9a-f-]{36}$")        # approveLeave
EMPLOYEE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # performance / attendance
CYCLE_RE = re.compile(r"^\d{4}-(Q[1-4]|H[12]|ANUAL)$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LINKEDIN_RE = re.compile(r"^https://(www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?$")
PHONE_RE = re.compile(r"^\+?[0-9\s-]{6,20}$")


@pytest.fixture(scope="module")
def data():
    G.use_users(C.load_users())  # module scope: se instancia antes que la autouse demo_users
    return {(s, t): G.generate(s, t, N) for s in C.SERVICES for t in TENANTS}


def by_type(items, et):
    return [i for i in items if i["entityType"] == et]


# ───────────── conteos ─────────────


@pytest.mark.parametrize("tenant", TENANTS)
def test_conteos_exactos_por_tenant(data, tenant):
    rec = G.count_by_entity("recruitment", data[("recruitment", tenant)])
    perf = G.count_by_entity("performance", data[("performance", tenant)])
    att = G.count_by_entity("attendance", data[("attendance", tenant)])
    core = G.count_by_entity("core_hr", data[("core_hr", tenant)])
    pay = G.count_by_entity("payroll", data[("payroll", tenant)])

    assert rec["CANDIDATE"] == N
    assert rec["VACANCY"] == 50
    assert rec["UNIQUE_GUARD"] == N
    assert perf["GOAL"] + perf["EVALUATION"] == N
    assert (perf["GOAL"], perf["EVALUATION"]) == (2_000, 8_000)
    assert att["ATTENDANCE"] == N
    assert att["LEAVE"] == 200
    assert core["employees"] == N and core["contracts"] == N
    assert pay["pay_slips"] == N


@pytest.mark.parametrize("n", [1, 7, 99, 100, 1_234])
def test_conteos_exactos_con_n_arbitrario(n):
    assert G.count_by_entity("recruitment", G.generate("recruitment", "tenant_x", n))["CANDIDATE"] == n
    perf = G.count_by_entity("performance", G.generate("performance", "tenant_x", n))
    assert perf.get("GOAL", 0) + perf.get("EVALUATION", 0) == n
    assert G.count_by_entity("attendance", G.generate("attendance", "tenant_x", n))["ATTENDANCE"] == n
    assert len(G.generate("core_hr", "tenant_x", n)["employees"]) == n
    assert len(G.generate("payroll", "tenant_x", n)["pay_slips"]) == n


# ───────────── IDs y claves ─────────────


def test_ids_cumplen_regex_de_handlers(data):
    for t in TENANTS:
        rec, perf, att = data[("recruitment", t)], data[("performance", t)], data[("attendance", t)]
        assert all(VACANCY_RE.match(v["vacancyId"]) for v in by_type(rec, "VACANCY"))
        assert all(CANDIDATE_RE.match(c["candidateId"]) and VACANCY_RE.match(c["vacancyId"]) for c in by_type(rec, "CANDIDATE"))
        assert all(GOAL_RE.match(g["goalId"]) for g in by_type(perf, "GOAL"))
        assert all(EVAL_RE.match(e["evalId"]) for e in by_type(perf, "EVALUATION"))
        assert all(LEAVE_RE.match(l["leaveId"]) for l in by_type(att, "LEAVE"))
        ids = [i["employeeId"] for i in perf + att if "employeeId" in i] + [e["evaluatorId"] for e in by_type(perf, "EVALUATION")]
        assert all(EMPLOYEE_RE.match(x) for x in ids)


def test_claves_recruitment_iguales_a_handlers(data):
    items = data[("recruitment", "tenant_a")]
    pk = "TENANT#tenant_a"
    for v in by_type(items, "VACANCY"):  # createVacancy: sin GSI
        assert (v["PK"], v["SK"]) == (pk, f"VACANCY#{v['vacancyId']}")
        assert "GSI1PK" not in v and "GSI1SK" not in v
    for c in by_type(items, "CANDIDATE"):  # createCandidate
        assert (c["PK"], c["SK"]) == (pk, f"CANDIDATE#{c['candidateId']}")
        assert c["GSI1PK"] == f"{pk}#VACANCY#{c['vacancyId']}"
        assert c["GSI1SK"] == f"CANDIDATE#{c['createdAt']}#{c['candidateId']}"
    cands = {c["candidateId"]: c for c in by_type(items, "CANDIDATE")}
    for g in by_type(items, "UNIQUE_GUARD"):  # guard del TransactWrite de createCandidate
        c = cands[g["candidateId"]]
        assert (g["PK"], g["SK"]) == (pk, f"UNIQUE#APPLICATION#{c['vacancyId']}#{c['email']}")


def test_claves_performance_iguales_a_handlers(data):
    items = data[("performance", "tenant_a")]
    pk = "TENANT#tenant_a"
    for g in by_type(items, "GOAL"):
        assert (g["PK"], g["SK"]) == (pk, f"GOAL#{g['employeeId']}#{g['goalId']}")
    for e in by_type(items, "EVALUATION"):
        assert (e["PK"], e["SK"]) == (pk, f"EVAL#{e['employeeId']}#{e['cycle']}#{e['evaluatorId']}")
        assert "GSI1PK" not in e
    for s in by_type(items, "EVAL_SUMMARY"):
        assert (s["PK"], s["SK"]) == (pk, f"SUMMARY#{s['employeeId']}#{s['cycle']}")


def test_claves_attendance_iguales_a_handlers(data):
    items = data[("attendance", "tenant_a")]
    pk = "TENANT#tenant_a"
    for a in by_type(items, "ATTENDANCE"):  # clockIn
        assert (a["PK"], a["SK"]) == (pk, f"ATTENDANCE#{a['employeeId']}#{a['date']}")
        assert "GSI1PK" not in a
    for l in by_type(items, "LEAVE"):  # requestLeave
        assert (l["PK"], l["SK"]) == (pk, f"LEAVE#{l['leaveId']}")
        assert l["GSI1PK"] == f"{pk}#EMPLOYEE#{l['employeeId']}"
        assert l["GSI1SK"] == f"LEAVE#{l['startDate']}#{l['leaveId']}"


def test_todo_item_tiene_entityType_y_PK_del_tenant(data):
    for s in C.DYNAMO_SERVICES:
        for t in TENANTS:
            items = data[(s, t)]
            assert all(i["PK"] == f"TENANT#{t}" and i["entityType"] in G.SK_PREFIX for i in items)
            assert all(i["SK"].startswith(G.SK_PREFIX[i["entityType"]]) for i in items)
            assert all(i.get("tenantId", t) == t for i in items)


def test_sin_claves_duplicadas(data):
    for s in C.DYNAMO_SERVICES:
        keys = [(i["PK"], i["SK"]) for t in TENANTS for i in data[(s, t)]]
        assert len(keys) == len(set(keys)), s
    for t in TENANTS:
        core = data[("core_hr", t)]
        assert len({e["email"] for e in core["employees"]}) == N
        for rows in list(core.values()) + list(data[("payroll", t)].values()):
            assert len({r["id"] for r in rows}) == len(rows)


# ───────────── metas: sin GSI1 ni recordatorios ─────────────


def test_ninguna_meta_lleva_GSI1_ni_recordatorio(data):
    for t in TENANTS:
        for g in by_type(data[("performance", t)], "GOAL"):
            assert "GSI1PK" not in g and "GSI1SK" not in g
            assert g["reminder"]["enabled"] is False
            assert g["nextReminderAt"] is None
            assert g["status"] in ("ACTIVE", "COMPLETED", "CANCELLED")
            assert (g["progress"] == 100) == (g["status"] == "COMPLETED")
            if g["status"] == "ACTIVE":
                assert g["targetDate"] > C.REFERENCE_DATE.isoformat()


# ───────────── coherencia recruitment ─────────────


def test_candidatesCount_coincide_con_candidatos(data):
    for t in TENANTS:
        items = data[("recruitment", t)]
        per_vac = Counter(c["vacancyId"] for c in by_type(items, "CANDIDATE"))
        vacs = by_type(items, "VACANCY")
        assert sum(v["candidatesCount"] for v in vacs) == N
        for v in vacs:
            assert v["candidatesCount"] == per_vac[v["vacancyId"]]


def test_stageHistory_coherente(data):
    stages = Counter()
    for c in by_type(data[("recruitment", "tenant_a")], "CANDIDATE"):
        h = c["stageHistory"]
        stages[c["stage"]] += 1
        assert c["stage"] in ("APPLIED", "INTERVIEW", "OFFER", "HIRED", "REJECTED")
        assert h[0] == {"from": "DRAFT", "to": "APPLIED", "at": c["submittedAt"], "by": c["email"], "note": None}
        for a, b in zip(h, h[1:]):
            assert b["from"] == a["to"] and b["to"] in G.TRANSITIONS[b["from"]]  # TRANSITIONS de updateStage.js
            assert b["at"] > a["at"]
        assert h[-1]["to"] == c["stage"]
        assert c["updatedAt"] == h[-1]["at"] and c["createdAt"] < c["submittedAt"]
    assert set(stages) == {"APPLIED", "INTERVIEW", "OFFER", "HIRED", "REJECTED"}


def test_candidatos_cumplen_validaciones_de_createCandidate(data):
    items = data[("recruitment", "tenant_a")]
    vacs = {v["vacancyId"]: v for v in by_type(items, "VACANCY")}
    for c in by_type(items, "CANDIDATE"):
        v = vacs[c["vacancyId"]]
        assert EMAIL_RE.match(c["email"]) and c["email"] == c["email"].lower()
        assert PHONE_RE.match(c["phone"]) and len(c["fullName"]) >= 3
        assert c["vacancyTitle"] == v["title"]
        if v["requireLinkedin"]:
            assert c["linkedin"] and LINKEDIN_RE.match(c["linkedin"]["url"])
        assert set(c["certificates"]) == {x["key"] for x in v["requiredCertificates"]}
        for key, cert in c["certificates"].items():
            if cert["mandatory"]:
                assert cert["status"] == "UPLOADED"
            if cert["status"] == "UPLOADED":
                assert cert["s3Key"] == f"tenant_a/recruitment/certificates/{c['candidateId']}/{key}.pdf"
        assert c["resumeS3Key"] == f"tenant_a/recruitment/resumes/{c['candidateId']}.pdf"


# ───────────── coherencia performance ─────────────


def test_evaluaciones_cumplen_reglas_de_submitEvaluation(data):
    for e in by_type(data[("performance", "tenant_a")], "EVALUATION"):
        assert CYCLE_RE.match(e["cycle"])
        assert (e["relationship"] == "SELF") == (e["evaluatorId"] == e["employeeId"])
        assert not e["anonymous"] or e["relationship"] == "PEER"
        scores = [Decimal(str(c["score"])) for c in e["competencies"]]
        assert all(1 <= s <= 5 and (s * 2) % 1 == 0 for s in scores)
        assert Decimal(str(e["score"])) == G.round2(sum(scores) / len(scores))


def test_summaries_coherentes_con_evaluaciones(data):
    items = data[("performance", "tenant_a")]
    groups = defaultdict(list)
    for e in by_type(items, "EVALUATION"):
        groups[(e["employeeId"], e["cycle"])].append(e)
    sums = by_type(items, "EVAL_SUMMARY")
    assert len(sums) == len(groups)
    for s in sums:
        evs = sorted(groups[(s["employeeId"], s["cycle"])], key=lambda x: x["createdAt"])
        assert s["evaluationsCount"] == len(evs)
        assert Decimal(str(s["scoreSum"])) == sum(Decimal(str(e["score"])) for e in evs)
        assert s["lastScore"] == evs[-1]["score"] and s["lastEvaluationAt"] == evs[-1]["createdAt"]


def test_cada_empleado_evaluado_tiene_ciclo_anterior_comparable(data):
    cycles = G.perf_cycles()
    assert cycles == ["2026-Q3", "2026-Q4"]
    per_emp = defaultdict(set)
    for s in by_type(data[("performance", "tenant_a")], "EVAL_SUMMARY"):
        per_emp[s["employeeId"]].add(s["cycle"])
    assert all(v == set(cycles) for v in per_emp.values())


# ───────────── coherencia attendance ─────────────


def test_attendance_una_marcacion_por_empleado_y_dia(data):
    items = by_type(data[("attendance", "tenant_a")], "ATTENDANCE")
    assert len({(a["employeeId"], a["date"]) for a in items}) == N
    for a in items[:500]:
        assert a["clockOut"] > a["clockIn"] and 480 <= a["workedMinutes"] <= 600
        assert a["date"] < C.REFERENCE_DATE.isoformat()


def test_licencias_sin_solapamiento_y_daysUnpaid(data):
    leaves = by_type(data[("attendance", "tenant_a")], "LEAVE")
    per_emp = defaultdict(list)
    for l in leaves:
        per_emp[l["employeeId"]].append(l)
        assert l["status"] in ("PENDING", "APPROVED")
        if l["status"] == "APPROVED":
            assert l["daysUnpaid"] == (l["totalDays"] if l["type"] in ("UNPAID", "OTHER") else 0)
    for ls in per_emp.values():
        ls.sort(key=lambda x: x["startDate"])
        for a, b in zip(ls, ls[1:]):
            assert a["endDate"] < b["startDate"]


# ───────────── cruce entre servicios y determinismo ─────────────


def test_employeeId_compartido_con_core_hr(data):
    core_ids = {e["id"] for e in data[("core_hr", "tenant_a")]["employees"]}
    perf = data[("performance", "tenant_a")]
    att = data[("attendance", "tenant_a")]
    assert {i["employeeId"] for i in perf + att} <= core_ids
    assert {e["evaluatorId"] for e in by_type(perf, "EVALUATION")} <= core_ids
    assert {s["employee_id"] for s in data[("payroll", "tenant_a")]["pay_slips"]} <= core_ids


def test_payroll_coherente_con_contratos(data):
    salary = {c["employee_id"]: c["salary"] for c in data[("core_hr", "tenant_a")]["contracts"]}
    for s in data[("payroll", "tenant_a")]["pay_slips"][:500]:
        assert s["base_salary"] == salary[s["employee_id"]]
        assert s["net_pay"] == s["base_salary"] - s["deductions"]


def test_deterministico_y_aislado_por_tenant():
    a1 = G.generate("recruitment", "tenant_a", 200)
    a2 = G.generate("recruitment", "tenant_a", 200)
    b = G.generate("recruitment", "tenant_b", 200)
    assert a1 == a2
    assert not {i["SK"] for i in a1} & {i["SK"] for i in b}


# ───────────── usuarios demo (scripts/users.json) ─────────────


def test_usuarios_demo_usan_su_employeeId_exacto_en_los_4_servicios(data, demo_users):
    for t in TENANTS:
        ids = [u["employeeId"] for u in demo_users[t]]
        assert ids, f"{t} sin usuarios"
        core = data[("core_hr", t)]
        emps = {e["id"]: e for e in core["employees"]}
        perf, att = data[("performance", t)], data[("attendance", t)]
        for u in demo_users[t]:
            e = u["employeeId"]
            assert EMPLOYEE_RE.match(e)
            assert emps[e]["email"] == u["email"] and emps[e]["status"] == "ACTIVE"
            assert any(c["employee_id"] == e for c in core["contracts"])
            assert any(s["employee_id"] == e for s in data[("payroll", t)]["pay_slips"])
            assert sum(a["employeeId"] == e for a in by_type(att, "ATTENDANCE")) == 100  # 100 días hábiles
            assert any(l["employeeId"] == e for l in by_type(att, "LEAVE"))
            assert {s["cycle"] for s in by_type(perf, "EVAL_SUMMARY") if s["employeeId"] == e} == {"2026-Q3", "2026-Q4"}
            assert sum(ev["employeeId"] == e for ev in by_type(perf, "EVALUATION")) == 8
            goals = [g for g in by_type(perf, "GOAL") if g["employeeId"] == e]
            assert len(goals) == 2 and all(g["reminder"]["enabled"] is False and "GSI1PK" not in g for g in goals)
        # el resto sigue siendo uuid5 determinístico
        assert len(emps) == N and sum(1 for x in emps if x in ids) == len(ids)


def test_usuarios_con_muestra_pequena_tambien_tienen_datos(demo_users):
    for t, users in demo_users.items():
        perf = G.generate("performance", t, 100)
        att = G.generate("attendance", t, 100)
        for u in users:
            e = u["employeeId"]
            assert {s["cycle"] for s in by_type(perf, "EVAL_SUMMARY") if s["employeeId"] == e} == {"2026-Q3", "2026-Q4"}
            assert any(l["employeeId"] == e for l in by_type(att, "LEAVE"))
        assert G.count_by_entity("attendance", att)["ATTENDANCE"] == 100
        perf_c = G.count_by_entity("performance", perf)
        assert perf_c["GOAL"] + perf_c["EVALUATION"] == 100


def test_sin_usuarios_se_genera_como_antes():
    G.use_users({})
    assert G.employee("tenant_a", 0)["employeeId"] == G.det_uuid("tenant_a", "employee", 0)
    assert G.count_by_entity("attendance", G.generate("attendance", "tenant_a", 10_000))["LEAVE"] == 200


def test_users_min_n():
    assert G.users_min_n("performance", 3) == 30
    assert G.users_min_n("attendance", 3) == 3
    assert G.users_min_n("recruitment", 3) is None
    assert G.users_min_n("performance", 0) is None


# ───────────── validación del archivo de usuarios ─────────────


def write(tmp_path, content):
    p = tmp_path / "users.json"
    p.write_text(content if isinstance(content, str) else __import__("json").dumps(content))
    return str(p)


def test_load_users_archivo_real():
    users = C.load_users()
    assert list(users) == ["tenant_a", "tenant_b", "tenant_c"]
    assert [u["employeeId"] for u in users["tenant_a"]] == ["emp-a-admin", "emp-a-hr", "emp-a-001"]


@pytest.mark.parametrize(
    "content, msg",
    [
        ("{no es json", "no se pudo leer"),
        ([], "lista no vacía"),
        ([{"tenantId": "tenant_a", "employeeId": "emp a"}], "employeeId 'emp a' no cumple"),
        ([{"tenantId": "tenant_a", "employeeId": "x" * 65}], "no cumple ^[A-Za-z0-9_-]{1,64}$"),
        ([{"tenantId": "tenant a", "employeeId": "emp-1"}], "tenantId 'tenant a' no cumple"),
        ([{"tenantId": "tenant_a"}], "employeeId None no cumple"),
        ([{"tenantId": "tenant_a", "employeeId": "e1"}, {"tenantId": "tenant_a", "employeeId": "e1"}], "employeeId e1 repetido"),
        ({"tenants": ["tenant_a", "tenant_b"], "users": [{"tenantId": "tenant_a", "employeeId": "e1"}]}, "el tenant tenant_b no tiene usuarios"),
    ],
)
def test_load_users_invalido(tmp_path, content, msg):
    with pytest.raises(C.UsersFileError) as e:
        C.load_users(write(tmp_path, content))
    assert msg in str(e.value)


def test_load_users_tenant_pedido_sin_usuarios(tmp_path):
    path = write(tmp_path, [{"tenantId": "tenant_a", "employeeId": "e1"}])
    with pytest.raises(C.UsersFileError, match="el tenant tenant_c no tiene usuarios"):
        C.load_users(path, ["tenant_a", "tenant_c"])
    with pytest.raises(C.UsersFileError, match="no existe el archivo"):
        C.load_users(str(tmp_path / "nope.json"))
