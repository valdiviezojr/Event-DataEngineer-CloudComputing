"""Escritura idempotente y reanudable en DynamoDB.

Modo por defecto (batch): BatchGetItem para saltar las claves que ya existen + BatchWriteItem del resto,
en paralelo con ThreadPoolExecutor. Se usa el cliente de bajo nivel en vez de Table.batch_writer()
porque batch_writer reenvía UnprocessedItems sin esperar; aquí hay backoff exponencial con jitter.
Nunca sobrescribe un ítem existente (p. ej. un candidato cuya etapa se cambió por la API).

Modo --conditional: PutItem con attribute_not_exists(PK) ítem por ítem (más lento; seguro aunque haya
otros escritores concurrentes).

El throttling (ProvisionedThroughputExceeded, ThrottlingException) lo reintenta botocore en modo
"adaptive" (backoff + rate limiting en cliente).
"""
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal

from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError

BATCH_SIZE = 25  # límite de BatchWriteItem
BOTO_CONFIG = Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=50)

_ser = TypeSerializer()


class DynamoSeedError(Exception):
    pass


def normalize(v):
    """float → Decimal y fechas → ISO, recursivo (DynamoDB no acepta float)."""
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: normalize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [normalize(x) for x in v]
    return v


def serialize(item):
    return {k: _ser.serialize(v) for k, v in normalize(item).items()}


def _key(item):
    return (item["PK"], item["SK"])


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class DynamoWriter:
    def __init__(self, client, table, workers=8, max_retries=8, conditional=False, sleep=time.sleep):
        self.client = client
        self.table = table
        self.workers = workers
        self.max_retries = max_retries
        self.conditional = conditional
        self.sleep = sleep

    def _backoff(self, attempt):
        if attempt >= self.max_retries:
            raise DynamoSeedError(f"{self.table}: se agotaron {self.max_retries} reintentos por ítems no procesados")
        self.sleep(min(10.0, 0.05 * 2**attempt) * random.uniform(0.5, 1.0))

    def _existing(self, chunk):
        keys = [{"PK": {"S": it["PK"]}, "SK": {"S": it["SK"]}} for it in chunk]
        request = {self.table: {"Keys": keys, "ProjectionExpression": "PK, SK"}}
        found, attempt = set(), 0
        while request:
            out = self.client.batch_get_item(RequestItems=request)
            for it in out.get("Responses", {}).get(self.table, []):
                found.add((it["PK"]["S"], it["SK"]["S"]))
            request = out.get("UnprocessedKeys") or {}
            if request:
                self._backoff(attempt)
                attempt += 1
        return found

    def _batch_write(self, items):
        request = {self.table: [{"PutRequest": {"Item": serialize(it)}} for it in items]}
        attempt = 0
        while request:
            out = self.client.batch_write_item(RequestItems=request)
            request = out.get("UnprocessedItems") or {}
            if request:
                self._backoff(attempt)
                attempt += 1

    def _write_chunk(self, chunk):
        if self.conditional:
            written = 0
            for it in chunk:
                try:
                    self.client.put_item(
                        TableName=self.table,
                        Item=serialize(it),
                        ConditionExpression="attribute_not_exists(PK)",
                    )
                    written += 1
                except ClientError as e:
                    if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                        raise
            return written, len(chunk) - written

        existing = self._existing(chunk)
        todo = [it for it in chunk if _key(it) not in existing]
        if todo:
            self._batch_write(todo)
        return len(todo), len(chunk) - len(todo)

    def write(self, items, progress=None):
        """Devuelve {"written": n, "skipped": n} (skipped = ya existían)."""
        stats = {"written": 0, "skipped": 0}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self._write_chunk, c) for c in _chunks(items, BATCH_SIZE)]
            for f in as_completed(futures):
                w, s = f.result()
                stats["written"] += w
                stats["skipped"] += s
                if progress:
                    progress.update(w + s)
        return stats


def count_entity(client, table, tenant, entity_type, sk_prefix):
    """Cuenta ítems de un tenant y entityType con Query (PK + begins_with(SK)), nunca Scan."""
    total, start = 0, None
    while True:
        params = {
            "TableName": table,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :p)",
            "FilterExpression": "entityType = :et",
            "ExpressionAttributeValues": {":pk": {"S": f"TENANT#{tenant}"}, ":p": {"S": sk_prefix}, ":et": {"S": entity_type}},
            "Select": "COUNT",
        }
        if start:
            params["ExclusiveStartKey"] = start
        out = client.query(**params)
        total += out["Count"]
        start = out.get("LastEvaluatedKey")
        if not start:
            return total
