from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

import dynamo_writer as dynamo
import generators as gen
import preflight
import seed_master


class MemoryDynamo:
    """Atomic fake that evaluates all write conditions before inserting any row."""
    def __init__(self):
        self.rows = {}
        self.writes = 0
        self.fail_on = None
        self.race = None

    def batch_get_item(self, RequestItems):
        table, options = next(iter(RequestItems.items()))
        assert options["ConsistentRead"]
        return {"Responses": {table: [self.rows[self.key(item)] for item in options["Keys"]
                                      if self.key(item) in self.rows]}}

    @staticmethod
    def key(row):
        return row["PK"]["S"], row["SK"]["S"]

    def transact_write_items(self, TransactItems):
        self.writes += 1
        if self.writes == self.fail_on:
            raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "TransactWriteItems")
        assert len(TransactItems) <= 100
        puts = [op["Put"] for op in TransactItems if "Put" in op]
        checks = [op["ConditionCheck"] for op in TransactItems if "ConditionCheck" in op]
        action_keys = [self.key(op["Item"]) for op in puts] + [self.key(op["Key"]) for op in checks]
        assert len(set(action_keys)) == len(action_keys)
        for condition in checks:
            parent = self.rows.get(self.key(condition["Key"]), {})
            if any(parent.get(name) != condition["ExpressionAttributeValues"][f":v{i}"]
                   for i, name in enumerate(condition["ExpressionAttributeNames"].values())):
                raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems")
        assert all(op["ConditionExpression"] == "attribute_not_exists(PK) AND attribute_not_exists(SK)" for op in puts)
        new = {self.key(op["Item"]): op["Item"] for op in puts}
        if self.race is not None:
            item = self.race
            self.rows[self.key(item)] = item
            self.race = None
        if self.rows.keys() & new.keys():
            raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems")
        self.rows.update(new)


class DynamoTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryDynamo()
        self.groups = list(gen.recruitment("tenant_a", 100))

    def test_transaction_limits_and_idempotence(self):
        dynamo.reconcile(self.client, "test", self.groups, insert=True)
        self.assertEqual(self.client.writes, 50)
        self.assertEqual(len(self.client.rows), 250)
        dynamo.reconcile(self.client, "test", self.groups, insert=True)
        dynamo.reconcile(self.client, "test", self.groups, verify=True)
        self.assertEqual(self.client.writes, 50)

    def test_partial_group_detected(self):
        self.client.transact_write_items(dynamo.put_actions("test", [self.groups[0][0]]))
        with self.assertRaisesRegex(ValueError, "incompleto"):
            dynamo.reconcile(self.client, "test", self.groups, insert=True)
        self.assertEqual(len(self.client.rows), 1)

    def test_racing_conflict_is_not_overwritten(self):
        row = dict(self.groups[0][0], candidatesCount=9)
        serializer = TypeSerializer()
        self.client.race = {k: serializer.serialize(v) for k, v in row.items()}
        with self.assertRaisesRegex(ValueError, "conflicto"):
            dynamo.reconcile(self.client, "test", self.groups, insert=True)
        self.assertEqual(len(self.client.rows), 1)
        self.assertEqual(next(iter(self.client.rows.values()))["candidatesCount"], {"N": "9"})

    def test_wrong_attribute_type_is_not_a_legitimate_match(self):
        row = dict(self.groups[0][0], requireLinkedin=0)
        self.client.transact_write_items(dynamo.put_actions("test", [row]))
        with self.assertRaisesRegex(ValueError, "conflicto"):
            dynamo.reconcile(self.client, "test", self.groups, verify=True)

    def test_stops_on_error_and_resumes(self):
        self.client.fail_on = 2
        with self.assertRaises(ClientError):
            dynamo.reconcile(self.client, "test", self.groups, insert=True)
        self.assertEqual(self.client.writes, 2)
        self.assertEqual(len(self.client.rows), 5)
        dynamo.reconcile(self.client, "test", self.groups, insert=True)
        self.assertEqual(self.client.writes, 51)
        self.assertEqual(len(self.client.rows), 250)

    def test_missing_records_fail_verification(self):
        with self.assertRaisesRegex(ValueError, "incompleto"):
            dynamo.reconcile(self.client, "test", self.groups, verify=True)

    def test_batches_require_the_same_vacancy(self):
        groups = list(gen.recruitment("tenant_a", 10000))[:5]
        dynamo.reconcile(self.client, "test", groups[:1], insert=True)
        parent = dynamo.key(groups[0][0])
        self.client.rows[parent]["status"] = {"S": "OPEN"}
        with self.assertRaises(ClientError):
            self.client.transact_write_items(TransactItems=dynamo.transaction_actions("test", groups[1], groups[0][0]))
        self.assertEqual(len(self.client.rows), 99)
        with self.assertRaisesRegex(ValueError, "límite"):
            dynamo.transaction_actions("test", [dict(groups[0][0], description="X" * 400_000)])

    def test_recruitment_detects_children_without_vacancy(self):
        groups = list(gen.recruitment("tenant_a", 10000))[:5]
        self.client.transact_write_items(dynamo.put_actions("test", groups[1]))
        with self.assertRaisesRegex(ValueError, "candidatos sin su vacante"):
            dynamo.reconcile(self.client, "test", groups)

    def test_full_dynamo_volumes(self):
        from collections import Counter

        expected = {
            gen.recruitment: {"CANDIDATE": 30000, "UNIQUE_GUARD": 30000, "VACANCY": 150},
            gen.performance: {"GOAL": 6000, "EVALUATION": 24000, "EVAL_SUMMARY": 6000},
            gen.attendance: {"ATTENDANCE": 30000, "LEAVE": 600},
        }
        for generate, counts in expected.items():
            client = MemoryDynamo()
            for tenant in gen.C.TENANTS:
                groups = list(generate(tenant, gen.FULL_SIZE))
                dynamo.reconcile(client, "test", groups, insert=True)
                dynamo.reconcile(client, "test", groups, verify=True)
            observed = Counter(row["entityType"]["S"] for row in client.rows.values())
            self.assertEqual(observed, counts)


class OrchestrationTests(unittest.TestCase):
    def test_manifest_drift_is_refused(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            source = {"namespace": "test", "counts": {"employees": 10000}}
            seed_master.save_or_compare(path, source, create=True)
            seed_master.save_or_compare(path, source, create=False)
            drift = deepcopy(source)
            drift["counts"]["employees"] = 9999
            with self.assertRaisesRegex(ValueError, "manifiesto difiere"):
                seed_master.save_or_compare(path, drift, create=True)
            seed_master.save_or_compare(path, source, create=False)

    def test_legacy_cli_routes_to_same_modes(self):
        from contextlib import redirect_stdout
        from io import StringIO

        with redirect_stdout(StringIO()) as output:
            self.assertEqual(seed_master.main(["--dry-run", "--sample"]), 0)
        self.assertIn('"TOTAL_GLOBAL": 1500', output.getvalue())
        counts = {"tenant_a": {"employees": 10000}}
        with patch.object(seed_master, "run_online", return_value=(counts, {})) as online, redirect_stdout(StringIO()):
            self.assertEqual(seed_master.main(["--verify", "--manifest", "test.json"]), 0)
        online.assert_called_once_with("verify", Path("test.json"))

    def test_academy_diagnosis_writes_no_manifest_or_rows(self):
        from unittest.mock import MagicMock

        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ("123",)
        counts = {"counts": {}, "complementary": {}}
        with (patch("psycopg2.connect", return_value=connection),
              patch.object(seed_master.C, "destinations", return_value=("us-east-1", {}, {})),
              patch.object(seed_master, "inspect_aws", return_value=(None, {})) as inspect,
              patch.object(seed_master.rds_writer, "inspect", return_value={}),
              patch.object(seed_master.generators, "dataset", return_value={}),
              patch.object(seed_master, "manifest", return_value=counts),
              patch.object(seed_master, "save_or_compare") as save,
              patch.object(seed_master.rds_writer, "reconcile") as sql,
              patch.object(seed_master, "dynamo_pass") as dynamo_pass):
            self.assertEqual(seed_master.run_online("diagnose", Path("unused")), ({}, {}))
            inspect.assert_called_once_with("us-east-1", {}, load=True, check_iam=False)
            save.assert_not_called()
            sql.assert_called_once_with(connection, {}, verify=False)
            dynamo_pass.assert_called_once_with(None, {}, {}, verify=False)

    def test_returns_error_status(self):
        with patch.object(seed_master, "run_online", side_effect=ValueError("fila faltante")):
            self.assertEqual(seed_master.main(["verify"]), 1)

    def test_streams_block_preflight(self):
        from unittest.mock import Mock

        client = Mock()
        client.describe_table.return_value = {"Table": dict(
            TableArn="arn:aws:dynamodb:us-east-1:123456789012:table/test", TableStatus="ACTIVE",
            KeySchema=[dict(AttributeName="PK", KeyType="HASH"), dict(AttributeName="SK", KeyType="RANGE")],
            AttributeDefinitions=[dict(AttributeName=key, AttributeType="S")
                                  for key in ("PK", "SK", "GSI1PK", "GSI1SK")],
            GlobalSecondaryIndexes=[dict(IndexName="GSI1", IndexStatus="ACTIVE", Projection={"ProjectionType": "ALL"},
                                         KeySchema=[dict(AttributeName="GSI1PK", KeyType="HASH"),
                                                    dict(AttributeName="GSI1SK", KeyType="RANGE")])],
            StreamSpecification={"StreamEnabled": True},
        )}
        with self.assertRaisesRegex(ValueError, "Streams activo"):
            preflight.inspect_table(client, "us-east-1", "123456789012", "test", load=True)
        client.transact_write_items.assert_not_called()

    def test_iam_missing_context_fails_closed(self):
        from unittest.mock import Mock

        iam = Mock()
        iam.simulate_principal_policy.return_value = {
            "EvaluationResults": [{"EvalDecision": "allowed", "MissingContextValues": ["condition"]}],
        }
        with self.assertRaisesRegex(ValueError, "sin acreditar"):
            preflight.simulate_put(iam, "role", "table")
        request = iam.simulate_principal_policy.call_args.kwargs
        self.assertEqual(request["ActionNames"], ["dynamodb:PutItem"])
        self.assertEqual(request["ContextEntries"][0]["ContextKeyValues"], ["TransactWriteItems"])

    def test_sql_failure_prevents_dynamo_writes(self):
        from contextlib import nullcontext
        from unittest.mock import MagicMock

        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ("123",)
        with (patch("psycopg2.connect", return_value=connection),
              patch.object(seed_master, "closing", return_value=nullcontext(connection)),
              patch.object(seed_master.C, "destinations", return_value=("us-east-1", {}, {})),
              patch.object(seed_master, "inspect_aws", return_value=(None, {})),
              patch.object(seed_master.rds_writer, "inspect", return_value={}),
              patch.object(seed_master.generators, "dataset", return_value={}),
              patch.object(seed_master, "manifest", return_value={}),
              patch.object(seed_master, "save_or_compare"),
              patch.object(seed_master.rds_writer, "reconcile", side_effect=[None, ValueError("SQL")]),
              patch.object(seed_master, "dynamo_pass") as dynamo_pass):
            with self.assertRaisesRegex(ValueError, "SQL"):
                seed_master.run_online("load", Path("unused"))
            dynamo_pass.assert_called_once_with(None, {}, {}, verify=False)
