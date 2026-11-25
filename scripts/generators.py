"""Generación determinística, sin clientes ni cuentas de Auth."""
from calendar import monthrange
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid5

import seed_config as C

FULL_SIZE = 10_000
SAMPLE_SIZE = 100
ACTOR = "seed-30k"
STAMP = "2025-12-31T22:00:00.000Z"
CREATED = datetime.fromisoformat(STAMP.replace("Z", "+00:00")).replace(tzinfo=None)


def identity(tenant, kind, index):
    return str(uuid5(C.NAMESPACE, f"{tenant}:{kind}:{index}"))


def sql_rows(tenant, size, departments):
    result = {table: [] for table in (
        "departments", "employees", "contracts", "employee_salary_profiles", "payroll_periods", "pay_slips",
    )}
    department_ids = dict(departments)
    for name in C.SEED_DEPARTMENTS:
        department_id = identity(tenant, "department", name)
        department_ids[name] = department_id
        result["departments"].append(dict(department_id=department_id, name=name,
                                          budget=Decimal("100000.00"), created_at=CREATED))
    catalog = tuple(department_ids[name] for name in (*C.DEPARTMENTS, *C.SEED_DEPARTMENTS))
    for index in range(size):
        employee = identity(tenant, "employee", index)
        email = f"{employee}@seed.example.invalid"
        salary = Decimal(1800 + 25 * (index % 400))
        result["employees"].append(dict(
            employee_id=employee, department_id=catalog[index % len(catalog)],
            first_name="Empleado", last_name=f"Ficticio {index:05}", email=email, role="EMPLOYEE",
            hire_date=C.HIRE_DATE, status="ACTIVE", created_at=CREATED, source_candidate_id=None,
        ))
        result["contracts"].append(dict(
            contract_id=identity(tenant, "contract", index), employee_id=employee, salary=salary,
            start_date=C.HIRE_DATE, end_date=None, contract_type=C.CONTRACT_TYPES[index % 3],
            s3_contract_key=None,
        ))
        result["employee_salary_profiles"].append(dict(
            employee_id=employee, email=email, base_salary=salary, hire_date=C.HIRE_DATE,
            is_active=True, synced_at=CREATED,
        ))
    for period_name in C.PERIODS:
        period = identity(tenant, "period", period_name)
        year, month = map(int, period_name.split("-"))
        generated = datetime(year, month, monthrange(year, month)[1], 22)
        total = Decimal("0.00")
        for index, profile in enumerate(result["employee_salary_profiles"][:size // 10]):
            salary = profile["base_salary"]
            deductions = salary * Decimal("0.13")
            net = salary - deductions
            result["pay_slips"].append(dict(
                pay_slip_id=identity(tenant, "slip", f"{period_name}:{index}"), period_id=period,
                employee_id=profile["employee_id"], base_salary=salary, deductions=deductions,
                net_pay=net, s3_slip_key=None, generated_at=generated,
            ))
            total += net
        result["payroll_periods"].append(dict(
            period_id=period, period_name=period_name, is_closed=True, created_at=datetime(year, month, 1),
            total_paid=total,
        ))
    return result


def item(tenant, key, entity, **attrs):
    return dict(PK=f"TENANT#{tenant}", SK=key, entityType=entity, tenantId=tenant, **attrs)


def recruitment(tenant, size):
    per_vacancy = size // 50
    for slot in range(50):
        start = slot * per_vacancy
        vacancy_id = f"v-{identity(tenant, 'vacancy', slot)}"
        title = f"Vacante ficticia {slot + 1}"
        vacancy = item(
            tenant, f"VACANCY#{vacancy_id}", "VACANCY", vacancyId=vacancy_id, title=title,
            department=C.DEPARTMENTS[slot % 4], description="Vacante para datos de prueba",
            location="Lima", employmentType="FULL_TIME", salaryMin=1800, salaryMax=4000,
            openings=1, requireLinkedin=False, requiredCertificates=[], status="CLOSED",
            candidatesCount=0, createdBy=ACTOR, createdAt=STAMP, updatedAt=STAMP,
            closedAt=STAMP, closedBy=ACTOR, closeReason="Vacante ficticia",
        )
        group = [vacancy]
        for index in range(start, start + per_vacancy):
            if index > start and (index - start) % 49 == 0:
                yield group
                group = []
            candidate = f"c-{identity(tenant, 'candidate', index)}"
            email = f"{candidate}@seed.example.invalid"
            group.extend([
                item(tenant, f"CANDIDATE#{candidate}", "CANDIDATE", candidateId=candidate,
                     vacancyId=vacancy_id, vacancyTitle=title, fullName=f"Candidato ficticio {index:05}",
                     email=email, phone=None, linkedin=None, certificates=[], stage="DRAFT",
                     resumeS3Key=None, resumeStatus="PENDING", stageHistory=[], submittedAt=None,
                     createdAt=STAMP, updatedAt=STAMP,
                     GSI1PK=f"TENANT#{tenant}#VACANCY#{vacancy_id}", GSI1SK=f"CANDIDATE#{STAMP}#{candidate}"),
                dict(PK=vacancy["PK"], SK=f"UNIQUE#APPLICATION#{vacancy_id}#{email}",
                     entityType="UNIQUE_GUARD", candidateId=candidate, createdAt=STAMP),
            ])
        yield group


def performance(tenant, size):
    for index in range(size // 10):
        employee = identity(tenant, "employee", index)
        name = f"Empleado Ficticio {index:05}"
        for slot in range(2):
            goal = f"g-{identity(tenant, 'goal', f'{index}:{slot}')}"
            yield [item(tenant, f"GOAL#{employee}#{goal}", "GOAL", goalId=goal,
                        employeeId=employee, employeeName=name, employeeEmail=f"{employee}@seed.example.invalid",
                        title=f"Meta ficticia {slot + 1}", description="", status="ACTIVE",
                        progress=0, targetDate="2026-06-30", assignedBy=ACTOR, createdAt=STAMP, updatedAt=STAMP,
                        reminder=dict(enabled=False, frequency="WEEKLY", everyDays=None, hour=9),
                        nextReminderAt=None, lastReminderAt=None, remindersSent=0)]
        for cycle, stamp in zip(C.CYCLES, ("2025-09-30T22:00:00.000Z", STAMP)):
            evaluations = []
            for offset, relationship in enumerate(("SELF", "MANAGER", "PEER", "DIRECT_REPORT")):
                evaluator_index = (index + offset) % size
                evaluator = identity(tenant, "employee", evaluator_index)
                score = 3 + (index + offset) % 3
                eval_id = f"e-{identity(tenant, 'evaluation', f'{index}:{cycle}:{offset}')}"
                evaluations.append(item(
                    tenant, f"EVAL#{employee}#{cycle}#{evaluator}", "EVALUATION", evalId=eval_id,
                    employeeId=employee, employeeName=name, employeeEmail=f"{employee}@seed.example.invalid",
                    evaluatorId=evaluator, evaluatorName=f"Empleado Ficticio {evaluator_index:05}",
                    relationship=relationship, cycle=cycle, score=score,
                    competencies=[dict(name="Calidad técnica", score=score, comment=None)],
                    strengths=None, improvements=None, feedback=None, anonymous=False,
                    status="SUBMITTED", submittedBy=ACTOR, createdAt=stamp,
                ))
            summary = item(tenant, f"SUMMARY#{employee}#{cycle}", "EVAL_SUMMARY",
                           employeeId=employee, employeeName=name, cycle=cycle, evaluationsCount=4,
                           scoreSum=sum(row["score"] for row in evaluations), lastScore=evaluations[-1]["score"],
                           lastEvaluationAt=stamp, updatedAt=stamp)
            yield evaluations + [summary]


def attendance(tenant, size):
    group = []
    days = [day for offset in range(1, 32)
            if (day := C.REFERENCE_DATE - timedelta(days=offset)).weekday() < 5]
    for index in range(size):
        employee = identity(tenant, "employee", index)
        day = days[index % len(days)].isoformat()
        clock_in = f"{day}T14:00:00.000Z"
        clock_out = f"{day}T22:00:00.000Z"
        group.append(item(tenant, f"ATTENDANCE#{employee}#{day}", "ATTENDANCE",
                          employeeId=employee, date=day, clockIn=clock_in, clockOut=clock_out,
                          status="CLOSED", recordedBy=ACTOR, closedBy=ACTOR, workedMinutes=480,
                          createdAt=clock_in, updatedAt=clock_out))
        if len(group) == 100:
            yield group
            group = []
    if group:
        yield group

    for index in range(size - size // 50, size):
        employee = identity(tenant, "employee", index)
        leave = identity(tenant, "leave", index)
        requested = "2025-11-20T14:00:00.000Z"
        yield [item(tenant, f"LEAVE#{leave}", "LEAVE", leaveId=leave, employeeId=employee,
                    type="VACATION" if index % 2 == 0 else "SICK", status="PENDING",
                    startDate="2025-11-24", endDate="2025-11-25", totalDays=2,
                    reason=None, requestedBy=ACTOR, createdAt=requested, updatedAt=requested,
                    GSI1PK=f"TENANT#{tenant}#EMPLOYEE#{employee}",
                    GSI1SK=f"LEAVE#2025-11-24#{leave}")]


def dataset(size, departments):
    return {tenant: (
        sql_rows(tenant, size, departments[tenant]),
        {service: list(generate(tenant, size)) for service, generate in (
            ("recruitment", recruitment), ("performance", performance), ("attendance", attendance),
        )},
    ) for tenant in C.TENANTS}


def dry_departments():
    return {tenant: {name: identity(tenant, "dry-department", name) for name in C.DEPARTMENTS}
            for tenant in C.TENANTS}
