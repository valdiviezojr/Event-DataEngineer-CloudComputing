"""Lecturas fuertes y escrituras condicionales por grupos indivisibles."""
from collections import defaultdict
from itertools import chain
import json
from time import sleep


def key(item):
    return item["PK"], item["SK"]


def packed(groups):
    batch = []
    count = 0
    for group in groups:
        if not 1 <= len(group) <= 100:
            raise ValueError("Tamaño inválido de transacción DynamoDB")
        if group[0]["entityType"] in ("VACANCY", "CANDIDATE"):
            if batch:
                yield batch
                batch, count = [], 0
            yield [group]
            continue
        if count + len(group) > 100:
            yield batch
            batch, count = [], 0
        batch.append(group)
        count += len(group)
    if batch:
        yield batch


def read_keys(client, table, items):
    from boto3.dynamodb.types import TypeDeserializer

    pending = {table: {"Keys": [{"PK": {"S": pk}, "SK": {"S": sk}} for pk, sk in map(key, items)],
                       "ConsistentRead": True}}
    parser = TypeDeserializer()
    found = {}
    for attempt in range(8):
        response = client.batch_get_item(RequestItems=pending)
        for raw in response["Responses"].get(table, []):
            row = {name: parser.deserialize(value) for name, value in raw.items()}
            found[key(row)] = row
        pending = response.get("UnprocessedKeys")
        if not pending:
            return found
        sleep(min(2, 0.05 * 2 ** attempt))
    raise RuntimeError(f"{table}: DynamoDB no completó todas las lecturas")


def missing_groups(table, batch, found, verify=False):
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    missing = []
    for group in batch:
        present = 0
        for row in group:
            actual = found.get(key(row))
            if actual is not None:
                if serializer.serialize(actual) != serializer.serialize(row):
                    raise ValueError(f"{table}: conflicto en {key(row)}")
                present += 1
        if present == len(group):
            continue
        if present or verify:
            raise ValueError(f"{table}: grupo incompleto en {key(group[0])} ({present}/{len(group)})")
        missing.extend(group)
    return missing


def put_actions(table, rows):
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    return [{"Put": {"TableName": table, "Item": {k: serializer.serialize(v) for k, v in row.items()},
                     "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)"}}
            for row in rows]


def transaction_actions(table, rows, parent=None):
    actions = put_actions(table, rows)
    if parent is not None:
        stored = put_actions(table, [parent])[0]["Put"]["Item"]
        pk, sk = stored.pop("PK"), stored.pop("SK")
        names = {f"#a{i}": name for i, name in enumerate(stored)}
        values = {f":v{i}": value for i, value in enumerate(stored.values())}
        actions.append({"ConditionCheck": {
            "TableName": table, "Key": {"PK": pk, "SK": sk},
            "ConditionExpression": " AND ".join(f"#a{i} = :v{i}" for i in range(len(stored))),
            "ExpressionAttributeNames": names, "ExpressionAttributeValues": values,
        }})
    # El JSON etiquetado del SDK da una cota conservadora para estos ítems.
    sizes = [len(json.dumps(action, ensure_ascii=True).encode()) for action in actions]
    if len(actions) > 100 or max(sizes) > 400_000 or sum(sizes) > 4_000_000:
        raise ValueError("La transacción supera el límite de acciones o bytes de DynamoDB")
    return actions


def reconcile(client, table, groups, *, verify=False, insert=False):
    from botocore.exceptions import ClientError

    vacancy = None
    vacancy_present = False
    for batch in packed(groups):
        expected = list(chain.from_iterable(batch))
        first = expected[0]
        parent = None
        if first["entityType"] == "VACANCY":
            vacancy = first
        elif first["entityType"] == "CANDIDATE":
            if vacancy is None or vacancy["vacancyId"] != first["vacancyId"]:
                raise ValueError(f"{table}: lote sin su vacante")
            parent = vacancy
        actions = transaction_actions(table, expected, parent)
        found = read_keys(client, table, expected)
        absent = missing_groups(table, batch, found, verify)
        if parent is not None and found and not vacancy_present:
            raise ValueError(f"{table}: candidatos sin su vacante {key(parent)}")
        if insert and absent:
            if parent is not None and not vacancy_present:
                raise ValueError(f"{table}: vacante ausente {key(parent)}")
            try:
                client.transact_write_items(TransactItems=actions if len(absent) == len(expected)
                                            else transaction_actions(table, absent, parent))
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
                check = expected + ([parent] if parent else [])
                reread = read_keys(client, table, check)
                if missing_groups(table, batch, reread):
                    raise
                if parent is not None:
                    missing_groups(table, [[parent]], reread, verify=True)
        if first["entityType"] == "VACANCY":
            vacancy_present = insert or not absent


def check_associations(client, table, tenant, service, groups):
    """Detecta filas ajenas que cambian los agregados de las entidades sembradas."""
    from boto3.dynamodb.types import TypeDeserializer

    rows = list(chain.from_iterable(groups))
    expected = {row["SK"] for row in rows}
    if service == "recruitment":
        parents = {row["vacancyId"] for row in rows if row["entityType"] == "VACANCY"}
        checks = (
            ("CANDIDATE#", lambda record: record.get("vacancyId") in parents),
            ("UNIQUE#APPLICATION#", lambda record: record["SK"].split("#", 3)[2] in parents),
        )
    elif service == "performance":
        parents = {(row["employeeId"], row["cycle"]) for row in rows if row["entityType"] == "EVAL_SUMMARY"}
        checks = (("EVAL#", lambda record: tuple(record["SK"].split("#")[1:3]) in parents),)
    else:
        leave_by_employee = {row["employeeId"]: row for row in rows if row["entityType"] == "LEAVE"}
        attendance_dates = defaultdict(list)
        for row in rows:
            if row["entityType"] == "ATTENDANCE":
                attendance_dates[row["employeeId"]].append(row["date"])

        def overlapping_leave(row):
            if row.get("status") not in ("PENDING", "APPROVED"):
                return False
            employee = row.get("employeeId")
            leave = leave_by_employee.get(employee)
            start, end = row.get("startDate"), row.get("endDate")
            if not (leave or employee in attendance_dates):
                return False
            if not isinstance(start, str) or not isinstance(end, str):
                return True
            return ((leave and start <= leave["endDate"] and end >= leave["startDate"])
                    or (row["status"] == "APPROVED"
                        and any(start <= day <= end for day in attendance_dates[employee])))

        def overlapping_attendance(row):
            leave = leave_by_employee.get(row.get("employeeId"))
            return leave and leave["startDate"] <= row.get("date", "") <= leave["endDate"]

        checks = (("LEAVE#", overlapping_leave), ("ATTENDANCE#", overlapping_attendance))
    parser = TypeDeserializer()
    for prefix, matches in checks:
        pages = client.get_paginator("query").paginate(
            TableName=table, ConsistentRead=True,
            KeyConditionExpression="PK = :tenant AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={":tenant": {"S": f"TENANT#{tenant}"}, ":prefix": {"S": prefix}},
        )
        for page in pages:
            for raw in page["Items"]:
                row = {name: parser.deserialize(value) for name, value in raw.items()}
                if row["SK"] not in expected and matches(row):
                    raise ValueError(f"{table}: relación ajena en {row['SK']}")
