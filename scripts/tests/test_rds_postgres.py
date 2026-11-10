"""Integración con un PostgreSQL local temporal (se omite si no hay initdb/pg_ctl en el PATH)."""
import shutil
import subprocess

import pytest

import seed_config as C
import seed_master


def norm(text):
    """Colapsa espacios para comparar filas de la tabla impresa sin depender del ancho de columna."""
    return "\n".join(" ".join(line.split()) for line in text.splitlines())



PORT = 54329
pytestmark = pytest.mark.skipif(not (shutil.which("initdb") and shutil.which("pg_ctl")), reason="PostgreSQL local no disponible")


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    data = tmp_path_factory.mktemp("pgdata")
    sock = tmp_path_factory.mktemp("pgsock")
    subprocess.run(["initdb", "-D", str(data), "-U", "postgres", "--auth=trust", "-E", "UTF8"], check=True, capture_output=True)
    subprocess.run(
        ["pg_ctl", "-D", str(data), "-l", str(data / "log"), "-w", "start", "-o", f"-p {PORT} -k {sock} -c listen_addresses=127.0.0.1"],
        check=True, capture_output=True,
    )
    subprocess.run(["createdb", "-h", "127.0.0.1", "-p", str(PORT), "-U", "postgres", "hcm_db"], check=True, capture_output=True)
    yield
    subprocess.run(["pg_ctl", "-D", str(data), "-m", "immediate", "stop"], capture_output=True)


@pytest.fixture
def rds_env(pg, monkeypatch):
    monkeypatch.setitem(C.RDS, "host", "127.0.0.1")
    monkeypatch.setitem(C.RDS, "port", PORT)
    monkeypatch.setitem(C.RDS, "sslmode", "disable")


def test_sin_tablas_mensaje_claro(rds_env, capsys):
    rc = seed_master.main(["--sample", "--service", "core_hr", "--tenants", "tenant_z"])
    assert rc == 1
    assert "faltan tablas en el schema 'tenant_z'" in capsys.readouterr().err


def test_seed_rds_idempotente_y_verify(rds_env, capsys):
    args = ["--sample", "--service", "core_hr", "payroll"]
    assert seed_master.main(args + ["--create-schema"]) == 0
    first = norm(capsys.readouterr().out)
    assert "core_hr tenant_a * 220 0" in first  # 20 departamentos + 100 empleados + 100 contratos

    assert seed_master.main(args) == 0  # segunda corrida: ON CONFLICT DO NOTHING
    second = norm(capsys.readouterr().out)
    assert "core_hr tenant_a * 0 220" in second
    assert "payroll tenant_c * 0 101" in second

    assert seed_master.main(args + ["--verify"]) == 0
    out = norm(capsys.readouterr().out)
    assert "core_hr tenant_b employees 100 100 OK" in out
    assert "payroll tenant_a pay_slips 100 100 OK" in out
    assert "FALTAN" not in out
