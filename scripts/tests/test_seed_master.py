"""seed_master con DynamoDB mockeado (moto): --dry-run, --sample, --verify, idempotencia y RDS caído."""
import boto3
import pytest
from moto import mock_aws

import generators as G
import seed_config as C
import seed_master
from dynamo_writer import DynamoSeedError, DynamoWriter
from rds_writer import RdsUnavailable

DYNAMO = ["recruitment", "performance", "attendance"]


def create_tables(client):
    """Mismo esquema que los serverless.yml (PK/SK + GSI1, PAY_PER_REQUEST)."""
    for table in C.DYNAMO_TABLES.values():
        client.create_table(
            TableName=table,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )


def table_count(client, table):
    """Solo para asserts de test (moto); el script nunca hace scan."""
    return client.scan(TableName=table, Select="COUNT")["Count"]


class NoScan:
    """Envuelve el cliente y falla si alguien llama scan."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def __getattr__(self, name):
        if name == "scan":
            raise AssertionError("seed_master no debe usar Scan")
        self.calls.append(name)
        return getattr(self.inner, name)


def no_rds():
    raise AssertionError("no debía conectarse a RDS")


@pytest.fixture
def ddb():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        create_tables(client)
        yield client


def test_dry_run_no_escribe_ni_conecta(ddb, capsys):
    rc = seed_master.main(["--dry-run", "--sample"], dynamo_client=NoScan(ddb), rds_connect=no_rds)
    out = capsys.readouterr().out
    assert rc == 0
    assert all(table_count(ddb, t) == 0 for t in C.DYNAMO_TABLES.values())
    assert "recruitment  tenant_a  CANDIDATE     100" in out
    assert "attendance   tenant_c  ATTENDANCE    100" in out


def test_sample_siembra_verifica_y_es_idempotente(ddb, capsys):
    client = NoScan(ddb)
    assert seed_master.main(["--sample", "--service", *DYNAMO], dynamo_client=client, rds_connect=no_rds) == 0

    # 100 principales por tenant + derivados (vacantes, guards, summaries, licencias)
    exp = {s: sum(sum(G.count_by_entity(s, G.generate(s, t, 100)).values()) for t in C.load_users()) for s in DYNAMO}
    for s in DYNAMO:
        assert table_count(ddb, C.DYNAMO_TABLES[s]) == exp[s]

    capsys.readouterr()
    assert seed_master.main(["--verify", "--sample", "--service", *DYNAMO], dynamo_client=client, rds_connect=no_rds) == 0
    out = capsys.readouterr().out
    assert "FALTAN" not in out and "EXTRA" not in out
    assert "recruitment  tenant_b  CANDIDATE     100       100         OK" in out
    assert "performance  tenant_a  GOAL" in out and "performance  tenant_a  EVALUATION" in out
    assert "query" in client.calls
    # Cada usuario demo existe en attendance (ATTENDANCE) y performance (EVAL_SUMMARY)
    for t, users in C.load_users().items():
        for u in users:
            assert f"attendance   {t}  {u['employeeId']}" in out and f"performance  {t}  {u['employeeId']}" in out
    assert out.count(" OK") >= 2 * 3 * 3 + 2 * 7

    # Segunda corrida: nada nuevo
    assert seed_master.main(["--sample", "--service", *DYNAMO], dynamo_client=client, rds_connect=no_rds) == 0
    for s in DYNAMO:
        assert table_count(ddb, C.DYNAMO_TABLES[s]) == exp[s]


def test_no_sobrescribe_items_modificados(ddb):
    table = C.DYNAMO_TABLES["recruitment"]
    items = G.generate("recruitment", "tenant_a", 30)
    DynamoWriter(ddb, table).write(items)
    cand = next(i for i in items if i["entityType"] == "CANDIDATE")
    key = {"PK": {"S": cand["PK"]}, "SK": {"S": cand["SK"]}}
    ddb.update_item(TableName=table, Key=key, UpdateExpression="SET stage = :s", ExpressionAttributeValues={":s": {"S": "HIRED-POR-API"}})

    for conditional in (False, True):
        stats = DynamoWriter(ddb, table, conditional=conditional).write(items)
        assert stats == {"written": 0, "skipped": len(items)}
    assert ddb.get_item(TableName=table, Key=key)["Item"]["stage"]["S"] == "HIRED-POR-API"


def test_reanuda_tras_corte(ddb):
    table = C.DYNAMO_TABLES["attendance"]
    items = G.generate("attendance", "tenant_a", 100)
    DynamoWriter(ddb, table).write(items[:40])  # "se cortó"
    stats = DynamoWriter(ddb, table).write(items)
    assert stats == {"written": len(items) - 40, "skipped": 40}


def test_datos_sembrados_funcionan_con_las_consultas_de_los_handlers(ddb):
    """Query GSI1 de getVacancy/listCandidates y prefijos de getEmployeePerformance sobre lo sembrado."""
    seed_master.main(["--sample", "--tenants", "tenant_a", "--service", "recruitment", "performance"], dynamo_client=ddb, rds_connect=no_rds)
    items = G.generate("recruitment", "tenant_a", 100)
    vac = next(i for i in items if i["entityType"] == "VACANCY")
    out = ddb.query(
        TableName=C.DYNAMO_TABLES["recruitment"], IndexName="GSI1", KeyConditionExpression="GSI1PK = :g",
        ExpressionAttributeValues={":g": {"S": f"TENANT#tenant_a#VACANCY#{vac['vacancyId']}"}}, Select="COUNT",
    )
    assert out["Count"] == vac["candidatesCount"] > 0

    emp = G.employee("tenant_a", 0)["employeeId"]
    assert emp == "emp-a-admin"  # primer usuario de users.json
    q = lambda prefix: ddb.query(  # noqa: E731
        TableName=C.DYNAMO_TABLES["performance"], KeyConditionExpression="PK = :pk AND begins_with(SK, :p)",
        ExpressionAttributeValues={":pk": {"S": "TENANT#tenant_a"}, ":p": {"S": prefix}},
    )["Items"]
    assert len(q(f"SUMMARY#{emp}#")) == 2 and len(q(f"GOAL#{emp}#")) == 2
    assert len(q(f"EVAL#{emp}#2026-Q4#")) == 4

    # Cron de recordatorios (dispatchGoalReminders) consulta GSI1PK = "REMINDER": debe estar vacío
    rem = ddb.query(
        TableName=C.DYNAMO_TABLES["performance"], IndexName="GSI1", KeyConditionExpression="GSI1PK = :pk",
        ExpressionAttributeValues={":pk": {"S": "REMINDER"}}, Select="COUNT",
    )
    assert rem["Count"] == 0


def test_rds_sin_configurar_no_bloquea_dynamodb(ddb, capsys):
    rc = seed_master.main(["--sample"], dynamo_client=ddb)  # DB_HOST no definido (conftest)
    err = capsys.readouterr().err
    assert rc == 1
    assert "core_hr: RDS no disponible: DB_HOST no está definido" in err
    assert "payroll: RDS no disponible: DB_HOST no está definido" in err
    assert all(table_count(ddb, t) > 0 for t in C.DYNAMO_TABLES.values())


def test_rds_inalcanzable_mensaje_claro(ddb, capsys, monkeypatch):
    monkeypatch.setitem(C.RDS, "host", "127.0.0.1")
    monkeypatch.setitem(C.RDS, "port", 1)  # nadie escucha
    rc = seed_master.main(["--sample", "--service", "core_hr", "payroll", "attendance"], dynamo_client=ddb)
    err = capsys.readouterr().err
    assert rc == 1
    assert "No se pudo conectar a 127.0.0.1:1/hcm_db" in err
    assert err.count("ERROR: RDS no disponible") == 2  # una vez por servicio, no por tenant
    assert table_count(ddb, C.DYNAMO_TABLES["attendance"]) > 0


def test_tabla_inexistente_mensaje_claro(capsys):
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        rc = seed_master.main(["--sample", "--service", "attendance", "--tenants", "tenant_a"], dynamo_client=client, rds_connect=no_rds)
    assert rc == 1
    assert f"la tabla {C.DYNAMO_TABLES['attendance']} no existe" in capsys.readouterr().err


class FlakyClient:
    """batch_write_item devuelve UnprocessedItems las primeras `fails` veces."""

    def __init__(self, fails):
        self.fails = fails
        self.writes = 0

    def batch_get_item(self, RequestItems):
        return {"Responses": {}}

    def batch_write_item(self, RequestItems):
        self.writes += 1
        if self.fails > 0:
            self.fails -= 1
            return {"UnprocessedItems": RequestItems}
        return {"UnprocessedItems": {}}


def test_backoff_ante_UnprocessedItems():
    sleeps = []
    client = FlakyClient(fails=3)
    items = G.generate("attendance", "tenant_a", 10)
    stats = DynamoWriter(client, "t", workers=1, sleep=sleeps.append).write(items)
    assert stats["written"] == len(items)
    assert client.writes == 4 and len(sleeps) == 3
    assert sleeps[0] < 0.06 and sleeps[2] <= 0.2  # exponencial con jitter


def test_backoff_se_rinde_con_mensaje():
    with pytest.raises(DynamoSeedError, match="se agotaron 2 reintentos"):
        DynamoWriter(FlakyClient(fails=99), "t", workers=1, max_retries=2, sleep=lambda s: None).write(G.generate("attendance", "tenant_a", 5))


# ───────────── usuarios demo ─────────────


def test_verify_detecta_usuario_sin_datos(ddb, capsys):
    args = ["--sample", "--service", "performance", "--tenants", "tenant_a"]
    assert seed_master.main(args, dynamo_client=ddb, rds_connect=no_rds) == 0
    table = C.DYNAMO_TABLES["performance"]
    for cycle in ("2026-Q3", "2026-Q4"):
        ddb.delete_item(TableName=table, Key={"PK": {"S": "TENANT#tenant_a"}, "SK": {"S": f"SUMMARY#emp-a-001#{cycle}"}})
    capsys.readouterr()
    assert seed_master.main(args + ["--verify"], dynamo_client=ddb, rds_connect=no_rds) == 2
    out = capsys.readouterr().out
    assert "performance  tenant_a  emp-a-001    EVAL_SUMMARY  2         0           FALTAN" in out
    assert "performance  tenant_a  emp-a-admin  EVAL_SUMMARY  2         2           OK" in out


@pytest.mark.parametrize(
    "content, msg",
    [
        ('[{"tenantId":"tenant_a","employeeId":"emp a"}]', "employeeId 'emp a' no cumple"),
        ('{"tenants":["tenant_a","tenant_b"],"users":[{"tenantId":"tenant_a","employeeId":"e1"}]}', "el tenant tenant_b no tiene usuarios"),
        ("no-json", "no se pudo leer"),
    ],
)
def test_archivo_de_usuarios_invalido_no_escribe_nada(ddb, capsys, tmp_path, monkeypatch, content, msg):
    path = tmp_path / "users.json"
    path.write_text(content)
    monkeypatch.setenv("SEED_USERS_FILE", str(path))  # documentado; aquí se pasa por CLI
    rc = seed_master.main(["--sample", "--users-file", str(path)], dynamo_client=NoScan(ddb), rds_connect=no_rds)
    err = capsys.readouterr().err
    assert rc == 3 and msg in err and "No se escribió nada" in err
    assert all(table_count(ddb, t) == 0 for t in C.DYNAMO_TABLES.values())


def test_tenant_pedido_sin_usuarios_no_escribe_nada(ddb, capsys):
    rc = seed_master.main(["--sample", "--tenants", "tenant_a", "tenant_z"], dynamo_client=ddb, rds_connect=no_rds)
    assert rc == 3 and "el tenant tenant_z no tiene usuarios" in capsys.readouterr().err
    assert all(table_count(ddb, t) == 0 for t in C.DYNAMO_TABLES.values())


def test_per_tenant_insuficiente_para_los_usuarios(ddb, capsys):
    rc = seed_master.main(["--per-tenant", "20", "--service", "performance"], dynamo_client=ddb, rds_connect=no_rds)
    assert rc == 3 and "usa al menos --per-tenant 30" in capsys.readouterr().err
    assert table_count(ddb, C.DYNAMO_TABLES["performance"]) == 0
