#!/usr/bin/env python3
"""Seeding masivo del SaaS HCM: 10,000 registros por tenant y microservicio (30,000 con 3 tenants).

Ejemplos:
  python seed_master.py --dry-run                                  # genera y cuenta, sin tocar AWS/RDS
  python seed_master.py --service recruitment performance --sample # 100 por tenant
  python seed_master.py                                            # todo, 10,000 por tenant
  python seed_master.py --verify                                   # solo cuenta lo que hay

Idempotente y reanudable: claves determinísticas (uuid5) + ítems/filas existentes se saltan.
Si RDS no está disponible, core_hr y payroll fallan con un mensaje claro y el resto continúa.
"""
import argparse
import json
import sys
import time

import seed_config as C
import generators as G
from dynamo_writer import BOTO_CONFIG, DynamoSeedError, DynamoWriter, count_entity
from rds_writer import RdsUnavailable, connect, count_rows, create_schema, insert_rows, missing_tables

try:
    from tqdm import tqdm
except ImportError:  # el progreso es opcional
    tqdm = None

RDS_SPECS = {"core_hr": C.CORE_HR, "payroll": C.PAYROLL}


def parse_args(argv):
    p = argparse.ArgumentParser(description="Seeding HCM multi-tenant (RDS + DynamoDB)")
    p.add_argument("--service", nargs="+", choices=["all"] + C.SERVICES, default=["all"])
    p.add_argument("--tenants", nargs="+", default=C.TENANTS)
    p.add_argument("--per-tenant", type=int, default=C.PER_TENANT, help="registros por tenant (default %(default)s)")
    p.add_argument("--sample", action="store_true", help=f"{C.SAMPLE_PER_TENANT} por tenant (ignora --per-tenant)")
    p.add_argument("--dry-run", action="store_true", help="genera y muestra conteos/ejemplos sin escribir")
    p.add_argument("--verify", action="store_true", help="solo cuenta lo que hay en DynamoDB/RDS por tenant")
    p.add_argument("--conditional", action="store_true", help="DynamoDB: PutItem condicional en vez de BatchWriteItem")
    p.add_argument("--create-schema", action="store_true", help="RDS: crear schemas/tablas con el DDL del diseño si no existen")
    p.add_argument("--workers", type=int, default=C.DYNAMO_WORKERS, help="hilos para DynamoDB (default %(default)s)")
    a = p.parse_args(argv)
    a.services = C.SERVICES if "all" in a.service else list(dict.fromkeys(a.service))
    a.n = C.SAMPLE_PER_TENANT if a.sample else a.per_tenant
    if a.n < 1:
        p.error("--per-tenant debe ser >= 1")
    for t in a.tenants:
        if t not in C.SCHEMAS:
            C.SCHEMAS[t] = t
    return a


def bar(total, desc):
    return tqdm(total=total, desc=desc, unit="it", leave=False) if tqdm else None


def print_table(headers, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = lambda r: "  ".join(str(x).ljust(w) for x, w in zip(r, widths))  # noqa: E731
    print(line(headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line(r))


class Context:
    """Recursos compartidos, creados de forma perezosa (dry-run no conecta a nada)."""

    def __init__(self, args, dynamo_client=None, rds_connect=None):
        self.args = args
        self._dynamo = dynamo_client
        self._rds_connect = rds_connect or (lambda: connect(C.RDS))
        self._rds = None
        self._rds_error = None
        self._expected = {}

    @property
    def dynamo(self):
        if self._dynamo is None:
            import boto3

            self._dynamo = boto3.client("dynamodb", region_name=C.AWS_REGION, config=BOTO_CONFIG)
        return self._dynamo

    def rds(self):
        if self._rds_error:
            raise self._rds_error
        if self._rds is None:
            try:
                self._rds = self._rds_connect()
            except RdsUnavailable as e:
                self._rds_error = e
                raise
        return self._rds

    def data(self, service, tenant):
        return G.generate(service, tenant, self.args.n)

    def expected(self, service, tenant):
        key = (service, tenant)
        if key not in self._expected:
            self._expected[key] = G.count_by_entity(service, self.data(service, tenant))
        return self._expected[key]


# ───────────── acciones por servicio ─────────────


def dry_run(ctx, service, tenant, show_examples):
    data = ctx.data(service, tenant)
    counts = G.count_by_entity(service, data)
    if show_examples:
        examples = {k: v[0] for k, v in data.items() if v} if isinstance(data, dict) else {}
        if not examples:
            for it in data:
                examples.setdefault(it["entityType"], it)
        for kind, ex in examples.items():
            print(f"    ejemplo {service}/{kind}: {json.dumps(ex, default=str, ensure_ascii=False)[:400]}")
    return counts


def seed_dynamo(ctx, service, tenant):
    items = ctx.data(service, tenant)
    writer = DynamoWriter(ctx.dynamo, C.DYNAMO_TABLES[service], ctx.args.workers, C.DYNAMO_MAX_RETRIES, ctx.args.conditional)
    pb = bar(len(items), f"{service}/{tenant}")
    try:
        return writer.write(items, pb)
    finally:
        if pb:
            pb.close()


def seed_rds(ctx, service, tenant):
    conn = ctx.rds()
    schema = C.SCHEMAS[tenant]
    specs = RDS_SPECS[service]
    try:
        if ctx.args.create_schema:
            create_schema(conn, schema, C.CORE_HR, C.PAYROLL)
        missing = missing_tables(conn, schema, [s["table"] for s in specs.values()])
        if missing:
            raise RdsUnavailable(
                f"faltan tablas en el schema '{schema}': {', '.join(missing)}. "
                "Aplica las migraciones del dueño del servicio o usa --create-schema"
            )
        rows = ctx.data(service, tenant)
        stats = {"written": 0, "skipped": 0}
        for logical, spec in specs.items():
            pb = bar(len(rows[logical]), f"{service}/{tenant}/{spec['table']}")
            try:
                ins = insert_rows(conn, schema, spec, rows[logical], C.RDS_PAGE_SIZE, pb)
            finally:
                if pb:
                    pb.close()
            stats["written"] += ins
            stats["skipped"] += len(rows[logical]) - ins
        return stats
    except Exception:
        conn.rollback()
        raise


def verify(ctx, service, tenant):
    """[(entidad, esperado, encontrado)]"""
    exp = ctx.expected(service, tenant)
    out = []
    if service in C.RDS_SERVICES:
        conn = ctx.rds()
        for logical, spec in RDS_SPECS[service].items():
            out.append((spec["table"], exp.get(logical, 0), count_rows(conn, C.SCHEMAS[tenant], spec["table"])))
    else:
        for et, expected in exp.items():
            out.append((et, expected, count_entity(ctx.dynamo, C.DYNAMO_TABLES[service], tenant, et, G.SK_PREFIX[et])))
    return out


def friendly_error(service, e):
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

    if isinstance(e, RdsUnavailable):
        return f"RDS no disponible: {e}"
    if isinstance(e, NoCredentialsError):
        return "faltan credenciales AWS (exporta AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN del Learner Lab)"
    if isinstance(e, EndpointConnectionError):
        return f"no hay conexión con DynamoDB en {C.AWS_REGION}"
    if isinstance(e, ClientError):
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            return f"la tabla {C.DYNAMO_TABLES.get(service)} no existe en {C.AWS_REGION} (¿desplegaste el servicio con STAGE={C.STAGE}?)"
        if code in ("ExpiredTokenException", "UnrecognizedClientException"):
            return "credenciales AWS expiradas o inválidas (renueva la sesión del Learner Lab)"
        return f"{code}: {e.response['Error'].get('Message', '')}"
    if isinstance(e, DynamoSeedError):
        return str(e)
    return f"{type(e).__name__}: {e}"


def main(argv=None, dynamo_client=None, rds_connect=None):
    args = parse_args(argv)
    ctx = Context(args, dynamo_client, rds_connect)
    mode = "dry-run" if args.dry_run else "verify" if args.verify else "seed"
    print(f"HCM seed · modo={mode} · stage={C.STAGE} · tenants={','.join(args.tenants)} · por tenant={args.n:,} · servicios={','.join(args.services)}")

    rows, failures = [], {}
    started = time.time()

    for service in args.services:
        for tenant in args.tenants:
            try:
                if mode == "dry-run":
                    for et, n in dry_run(ctx, service, tenant, tenant == args.tenants[0]).items():
                        rows.append((service, tenant, et, f"{n:,}", "", ""))
                elif mode == "verify":
                    for et, exp, found in verify(ctx, service, tenant):
                        status = "OK" if found == exp else ("FALTAN" if found < exp else "EXTRA")
                        rows.append((service, tenant, et, f"{exp:,}", f"{found:,}", status))
                else:
                    t0 = time.time()
                    fn = seed_rds if service in C.RDS_SERVICES else seed_dynamo
                    st = fn(ctx, service, tenant)
                    rows.append((service, tenant, "*", f"{st['written']:,}", f"{st['skipped']:,}", f"{time.time() - t0:.1f}s"))
            except Exception as e:  # un servicio caído no detiene a los demás
                msg = friendly_error(service, e)
                failures.setdefault(service, msg)
                print(f"  [{service}/{tenant}] ERROR: {msg}", file=sys.stderr)
                if isinstance(e, RdsUnavailable) and ctx._rds_error:
                    break  # sin conexión: no insistir con el resto de tenants

    print()
    headers = {
        "dry-run": ["servicio", "tenant", "entidad", "generados", "", ""],
        "verify": ["servicio", "tenant", "entidad", "esperado", "encontrado", "estado"],
        "seed": ["servicio", "tenant", "entidad", "escritos", "ya existían", "tiempo"],
    }[mode]
    if rows:
        print_table(headers, rows)
    if mode != "seed":
        print(f"\nPrincipales (deben ser {args.n:,} por tenant): " + "; ".join(f"{s}={'+'.join(G.MAIN_ENTITIES[s])}" for s in args.services))

    print(f"\nTiempo total: {time.time() - started:.1f}s")
    if failures:
        print("\nServicios con error:", file=sys.stderr)
        for s, m in failures.items():
            print(f"  - {s}: {m}", file=sys.stderr)
        return 1
    if mode == "verify" and any(r[5] == "FALTAN" for r in rows):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
