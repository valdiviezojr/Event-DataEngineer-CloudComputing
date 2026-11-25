"""Reglas de volumen e integridad independientes de las funciones de generación."""
from collections import Counter
from calendar import monthrange
from datetime import date, datetime
from itertools import chain
from uuid import UUID

TENANTS = ("tenant_a", "tenant_b", "tenant_c")
REQUIRED = {"employees": 10_000, "pay_slips": 10_000, "CANDIDATE": 10_000,
            "GOAL": 2_000, "EVALUATION": 8_000, "ATTENDANCE": 10_000}
SAMPLE_REQUIRED = {"employees": 100, "pay_slips": 100, "CANDIDATE": 100,
                   "GOAL": 20, "EVALUATION": 80, "ATTENDANCE": 100}


def require(condition, description):
    if not condition:
        raise ValueError(description)


def unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"Clave repetida: {key}")
    return result


def validate(data, *, sample=False):
    require(tuple(data) == TENANTS, "Conjunto de tenants inesperado")
    required = SAMPLE_REQUIRED if sample else REQUIRED
    report = {}
    all_employees = set()
    for tenant, (tables, services) in data.items():
        counts = Counter({name: len(rows) for name, rows in tables.items()})
        employees = unique(tables["employees"], "employee_id")
        contracts = unique(tables["contracts"], "employee_id")
        profiles = unique(tables["employee_salary_profiles"], "employee_id")
        slips = unique(tables["pay_slips"], "pay_slip_id")
        unique(tables["contracts"], "contract_id")
        require(employees.keys() == contracts.keys() == profiles.keys(), f"{tenant}: cobertura SQL")
        require(not all_employees.intersection(employees), f"{tenant}: UUID de empleado repetido entre tenants")
        all_employees.update(employees)
        periods = unique(tables["payroll_periods"], "period_id")
        require({p["period_name"] for p in periods.values()} == {f"2025-{m:02}" for m in range(3, 13)},
                f"{tenant}: períodos inesperados")
        departments = unique(tables["departments"], "department_id")
        require(len(departments) == 16 and len({row["name"] for row in departments.values()}) == 16
                and len({row["department_id"] for row in employees.values()}) == 20
                and set(departments).issubset({row["department_id"] for row in employees.values()}),
                f"{tenant}: departamentos incorrectos")
        for employee, row in employees.items():
            contract, profile = contracts[employee], profiles[employee]
            require(all(str(UUID(value)) == value for value in (
                employee, row["department_id"], contract["contract_id"],
            )), f"{tenant}: UUID inválido")
            require(contract["contract_type"] in {"FULL_TIME", "PART_TIME", "CONTRACTOR"}
                    and contract["salary"] == profile["base_salary"] > 0
                    and row["hire_date"] == contract["start_date"] == profile["hire_date"]
                    and row["email"] == profile["email"] and row["email"].endswith("@seed.example.invalid")
                    and contract["s3_contract_key"] is None and profile["is_active"] and row["status"] == "ACTIVE",
                    f"{tenant}: perfil o contrato incompatible para {employee}")
        by_period = {p: {} for p in periods}
        for slip_id, slip in slips.items():
            employee = slip["employee_id"]
            period_id = slip["period_id"]
            require(employee in employees and period_id in periods, f"{tenant}: boleta huérfana")
            issued = slip["generated_at"]
            beginning = date(issued.year, issued.month, 1)
            contract = contracts[employee]
            require(str(UUID(slip_id)) == slip_id and employee not in by_period[period_id]
                    and slip["base_salary"] == profiles[employee]["base_salary"]
                    and slip["s3_slip_key"] is None and slip["deductions"] == slip["base_salary"] * 13 / 100
                    and slip["net_pay"] == slip["base_salary"] - slip["deductions"] > 0
                    and issued.strftime("%Y-%m") == periods[period_id]["period_name"]
                    and issued.day == monthrange(issued.year, issued.month)[1]
                    and contract["start_date"] <= beginning
                    and (contract["end_date"] is None or contract["end_date"] >= issued.date()),
                    f"{tenant}: boleta incompatible para {employee}")
            by_period[period_id][employee] = slip["net_pay"]
        payees = set().union(*(set(rows) for rows in by_period.values()))
        require(len(payees) == (10 if sample else 1000), f"{tenant}: cantidad de empleados de Payroll")
        for key, period in periods.items():
            require(str(UUID(key)) == key and period["is_closed"] and by_period[key].keys() == payees
                    and period["created_at"].date().isoformat() == period["period_name"] + "-01"
                    and period["total_paid"] == sum(by_period[key].values()), f"{tenant}: total o cobertura del período")
        require(set(services) == {"recruitment", "performance", "attendance"}, f"{tenant}: servicios inesperados")
        for service, groups in services.items():
            rows = unique(list(chain.from_iterable(groups)), "SK")
            counts.update(row["entityType"] for row in rows.values())
            require(all(row["PK"] == f"TENANT#{tenant}" and row.get("tenantId", tenant) == tenant
                        for row in rows.values()), f"{tenant}.{service}: partición incorrecta")
            if service == "recruitment":
                vacancies = {row["vacancyId"]: row for row in rows.values() if row["entityType"] == "VACANCY"}
                per_vacancy = Counter(row["vacancyId"] for row in rows.values() if row["entityType"] == "CANDIDATE")
                require(per_vacancy == dict.fromkeys(vacancies, 2 if sample else 200),
                        f"{tenant}: distribución de candidaturas")
            elif service == "attendance":
                leave_rows = [row for row in rows.values() if row["entityType"] == "LEAVE"]
                leaves = unique(leave_rows, "employeeId")
                require(not payees.intersection(leaves), f"{tenant}: licencia en cohorte de Payroll")
                require(not any((leave := leaves.get(row["employeeId"])) and
                                leave["startDate"] <= row["date"] <= leave["endDate"]
                                for row in rows.values() if row["entityType"] == "ATTENDANCE"),
                        f"{tenant}: marcación en días de licencia")
            for group in groups:
                validate_group(tenant, service, group, employees)
        complementary = {"departments": 16, "contracts": required["employees"],
                         "employee_salary_profiles": required["employees"], "payroll_periods": 10,
                         "VACANCY": 50, "UNIQUE_GUARD": required["CANDIDATE"],
                         "EVAL_SUMMARY": 20 if sample else 2000, "LEAVE": 2 if sample else 200}
        require(all(counts[name] == total for name, total in complementary.items()),
                f"{tenant}: volumen complementario incorrecto {dict(counts)}")
        observed = {name: counts[name] for name in required}
        require(observed == required, f"{tenant}: volumen incorrecto {observed}")
        report[tenant] = observed
    return report


def validate_group(tenant, service, group, employees):
    require(1 <= len(group) <= 100, f"{tenant}.{service}: tamaño transaccional incorrecto")
    prefix = f"{tenant}.{service}"
    if service == "recruitment":
        if group[0]["entityType"] == "VACANCY":
            vacancy, *pairs = group
            vacancy_id = vacancy["vacancyId"]
            require(vacancy["candidatesCount"] == 0 and vacancy["status"] == "CLOSED"
                    and vacancy["SK"] == f"VACANCY#{vacancy_id}", f"{prefix}: vacante incompatible")
        else:
            pairs = group
            vacancy_id = group[0]["vacancyId"]
        require(2 <= len(pairs) <= 98 and len(pairs) % 2 == 0, f"{prefix}: lote sin pares completos")
        for candidate, guard in zip(pairs[::2], pairs[1::2]):
            require(candidate["entityType"] == "CANDIDATE" and guard["entityType"] == "UNIQUE_GUARD"
                    and candidate["vacancyId"] == vacancy_id
                    and candidate["GSI1PK"] == f"TENANT#{tenant}#VACANCY#{vacancy_id}"
                    and guard["candidateId"] == candidate["candidateId"]
                    and guard["SK"] == f"UNIQUE#APPLICATION#{vacancy_id}#{candidate['email']}"
                    and candidate["stage"] == "DRAFT" and candidate["submittedAt"] is None
                    and candidate["resumeS3Key"] is None and candidate["resumeStatus"] == "PENDING"
                    and not candidate["certificates"], f"{prefix}: relación o documentos incompatibles")
    elif service == "performance":
        require(all(row["employeeId"] in employees for row in group), f"{prefix}: empleado huérfano")
        if len(group) == 1:
            goal = group[0]
            require(goal["entityType"] == "GOAL" and not goal["reminder"]["enabled"]
                    and goal["nextReminderAt"] is None, f"{prefix}: meta incompatible")
        else:
            *evaluations, summary = group
            require(summary["entityType"] == "EVAL_SUMMARY" and len(evaluations) == 4
                    and summary["evaluationsCount"] == len(evaluations)
                    and summary["scoreSum"] == sum(row["score"] for row in evaluations)
                    and summary["lastEvaluationAt"] == evaluations[-1]["createdAt"]
                    and summary["lastScore"] == evaluations[-1]["score"]
                    and len({row["evaluatorId"] for row in evaluations}) == len(evaluations)
                    and all(row["entityType"] == "EVALUATION" and row["evaluatorId"] in employees
                            and row["employeeId"] == summary["employeeId"] and row["cycle"] == summary["cycle"]
                            for row in evaluations), f"{prefix}: evaluaciones o summary incompatibles")
    else:
        for row in group:
            if row["entityType"] == "LEAVE":
                start, end = map(date.fromisoformat, (row["startDate"], row["endDate"]))
                leave_id = row["leaveId"]
                require(row["status"] == "PENDING" and row["type"] in {"VACATION", "SICK"}
                        and row["employeeId"] in employees
                        and employees[row["employeeId"]]["hire_date"] <= start
                        and 0 < row["totalDays"] == (end - start).days + 1
                        and datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00")).date() <= start
                        and row["SK"] == f"LEAVE#{leave_id}"
                        and row["GSI1PK"] == f"TENANT#{tenant}#EMPLOYEE#{row['employeeId']}"
                        and row["GSI1SK"] == f"LEAVE#{start}#{leave_id}"
                        and not {"eventId", "daysUnpaid", "approvedAt"}.intersection(row), f"{prefix}: licencia inválida")
                continue
            start = datetime.fromisoformat(row["clockIn"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(row["clockOut"].replace("Z", "+00:00"))
            require(row["entityType"] == "ATTENDANCE" and row["status"] == "CLOSED"
                    and row["employeeId"] in employees and row["date"] == start.date().isoformat()
                    and (end - start).total_seconds() == 60 * row["workedMinutes"] > 0,
                    f"{prefix}: marcación inválida")
