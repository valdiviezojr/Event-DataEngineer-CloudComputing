"""Escritura idempotente en RDS PostgreSQL (schema por tenant) con execute_values + ON CONFLICT DO NOTHING."""


class RdsUnavailable(Exception):
    """RDS no configurado, inalcanzable o sin las tablas esperadas. El mensaje es para el usuario."""


def connect(cfg):
    try:
        import psycopg2
    except ImportError:
        raise RdsUnavailable("psycopg2 no está instalado (pip install -r scripts/requirements.txt)")

    if not cfg.get("host"):
        raise RdsUnavailable("DB_HOST no está definido: configura las variables DB_* del RDS (ver scripts/README.md)")

    params = {k: v for k, v in cfg.items() if v is not None}
    try:
        return psycopg2.connect(**params)
    except psycopg2.OperationalError as e:
        detail = (str(e).strip().splitlines() or ["sin detalle"])[0]
        raise RdsUnavailable(f"No se pudo conectar a {cfg['host']}:{cfg['port']}/{cfg['dbname']} como {cfg['user']}: {detail}")


def _ident(*parts):
    from psycopg2 import sql

    return sql.Identifier(*parts)


def missing_tables(conn, schema, tables):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_name = ANY(%s)",
            (schema, list(tables)),
        )
        found = {r[0] for r in cur.fetchall()}
    return [t for t in tables if t not in found]


def insert_rows(conn, schema, spec, rows, page_size, progress=None):
    """spec = {"table": nombre, "columns": {lógico: real}}. Devuelve filas realmente insertadas."""
    from psycopg2 import sql
    from psycopg2.extras import execute_values

    logical = list(spec["columns"])
    query = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT DO NOTHING").format(
        _ident(schema, spec["table"]),
        sql.SQL(", ").join(_ident(spec["columns"][c]) for c in logical),
    ).as_string(conn)

    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), page_size):
            page = rows[i : i + page_size]
            execute_values(cur, query, [tuple(r[c] for c in logical) for r in page], page_size=len(page))
            inserted += max(cur.rowcount, 0)
            conn.commit()  # commit por lote: si se corta, se reanuda donde quedó
            if progress:
                progress.update(len(page))
    return inserted


def count_rows(conn, schema, table):
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(_ident(schema, table)))
        return cur.fetchone()[0]


def create_schema(conn, schema, core_hr, payroll):
    """DDL del documento de diseño (solo con --create-schema). TODO: reemplazar por las migraciones finales.

    employee_id es VARCHAR(64) y no UUID: los usuarios demo de hcm-auth usan IDs como "emp-a-admin"
    (regex ^[A-Za-z0-9_-]{1,64}$ de los handlers). Las migraciones finales de Core HR deben aceptar ese formato.
    """
    from psycopg2 import sql

    d, e, c = core_hr["departments"], core_hr["employees"], core_hr["contracts"]
    p, s = payroll["periods"], payroll["pay_slips"]
    col = lambda spec, k: _ident(spec["columns"][k])  # noqa: E731
    tbl = lambda spec: _ident(schema, spec["table"])  # noqa: E731

    statements = [
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_ident(schema)),
        sql.SQL("CREATE TABLE IF NOT EXISTS {} ({} UUID PRIMARY KEY, {} VARCHAR(100) NOT NULL, {} NUMERIC(12,2))").format(
            tbl(d), col(d, "id"), col(d, "name"), col(d, "budget")
        ),
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ({} VARCHAR(64) PRIMARY KEY, {} UUID REFERENCES {}({}), {} VARCHAR(50) NOT NULL, "
            "{} VARCHAR(50) NOT NULL, {} VARCHAR(100) UNIQUE NOT NULL, {} DATE NOT NULL, {} VARCHAR(20) DEFAULT 'ACTIVE')"
        ).format(
            tbl(e), col(e, "id"), col(e, "department_id"), tbl(d), col(d, "id"), col(e, "first_name"),
            col(e, "last_name"), col(e, "email"), col(e, "hire_date"), col(e, "status"),
        ),
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ({} UUID PRIMARY KEY, {} VARCHAR(64) REFERENCES {}({}), {} NUMERIC(10,2) NOT NULL, "
            "{} DATE NOT NULL, {} VARCHAR(30) NOT NULL)"
        ).format(tbl(c), col(c, "id"), col(c, "employee_id"), tbl(e), col(e, "id"), col(c, "salary"), col(c, "start_date"), col(c, "contract_type")),
        sql.SQL("CREATE TABLE IF NOT EXISTS {} ({} UUID PRIMARY KEY, {} VARCHAR(20) NOT NULL, {} BOOLEAN DEFAULT FALSE)").format(
            tbl(p), col(p, "id"), col(p, "name"), col(p, "is_closed")
        ),
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ({} UUID PRIMARY KEY, {} UUID REFERENCES {}({}), {} VARCHAR(64) NOT NULL, "
            "{} NUMERIC(10,2) NOT NULL, {} NUMERIC(10,2) DEFAULT 0.00, {} NUMERIC(10,2) NOT NULL, {} TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ).format(
            tbl(s), col(s, "id"), col(s, "period_id"), tbl(p), col(p, "id"), col(s, "employee_id"),
            col(s, "base_salary"), col(s, "deductions"), col(s, "net_pay"), col(s, "generated_at"),
        ),
    ]
    with conn.cursor() as cur:
        for st in statements:
            cur.execute(st)
    conn.commit()
