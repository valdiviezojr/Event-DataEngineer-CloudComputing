# Seeding HCM (`seed_master.py`)

Genera **10,000 registros por tenant** en cada microservicio (**30,000** con `tenant_a`, `tenant_b` y `tenant_c`) y los carga en RDS PostgreSQL (core_hr, payroll) y DynamoDB (recruitment, performance, attendance).

```
seed_master.py     CLI (orquesta, verifica, imprime tablas)
seed_config.py     Configuración (todo sobrescribible por variables de entorno)
generators.py      Generadores puros de ítems/filas (sin AWS ni RDS)
dynamo_writer.py   Escritura DynamoDB: batch + backoff, o PutItem condicional
rds_writer.py      Escritura RDS: execute_values (lotes de 2,000) + ON CONFLICT DO NOTHING
tests/             pytest: generadores, moto (DynamoDB) y PostgreSQL local opcional
```

## Instalación y credenciales

```bash
cd scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # + requirements-dev.txt para los tests

# Credenciales del Learner Lab (AWS Details → AWS CLI) y DB_* del RDS, en ../.env
set -a && source ../.env && set +a
aws sts get-caller-identity
```

Las tablas DynamoDB deben estar desplegadas en el mismo `STAGE` (`ms-recruitment-table-dev`, …). Si falta una, el script lo dice y sigue con el resto.

## Uso

```bash
python seed_master.py --dry-run                         # genera y cuenta; no conecta a nada
python seed_master.py --dry-run --sample                # idem, 100 por tenant + un ejemplo por entidad
python seed_master.py --service recruitment --sample    # prueba real pequeña
python seed_master.py                                   # todo: 5 servicios × 3 tenants × 10,000
python seed_master.py --service attendance --tenants tenant_a --per-tenant 500
python seed_master.py --verify                          # solo cuenta lo que hay (sin escribir)
python seed_master.py --service core_hr payroll --create-schema   # RDS sin migraciones aún (DDL del diseño)
```

| Opción | Efecto |
|---|---|
| `--service {all,core_hr,payroll,recruitment,performance,attendance}…` | uno o varios (default `all`) |
| `--tenants t1 t2…` | default `SEED_TENANTS` o los 3 tenants |
| `--per-tenant N` | registros principales por tenant (default 10,000) |
| `--sample` | 100 por tenant |
| `--dry-run` | no escribe ni conecta |
| `--verify` | cuenta por tenant/servicio/entidad y compara con lo esperado (estado `OK` / `FALTAN` / `EXTRA`) |
| `--conditional` | DynamoDB con `PutItem` + `attribute_not_exists(PK)` en vez de lotes |
| `--create-schema` | RDS: `CREATE SCHEMA/TABLE IF NOT EXISTS` con el DDL del documento de diseño |
| `--workers N` | hilos para DynamoDB (default 8) |

Códigos de salida: `0` OK · `1` algún servicio falló (los demás sí se ejecutaron) · `2` `--verify` encontró menos de lo esperado.

**RDS no disponible.** Si `DB_HOST` está vacío, el host no responde, falta `psycopg2` o faltan las tablas, `core_hr` y `payroll` terminan con un mensaje claro (por ejemplo `RDS no disponible: No se pudo conectar a host:5432/hcm_db como postgres: …`). Los servicios DynamoDB se siembran igual.

## Idempotente y reanudable

- **Claves determinísticas**: `uuid5(SEED_NAMESPACE, "<tenant>:<tipo>:<índice>")`. Los valores salen de un `random.Random` sembrado con el mismo par, así que cada corrida genera exactamente los mismos datos.
- **RDS**: `INSERT … ON CONFLICT DO NOTHING`, con commit cada 2,000 filas.
- **DynamoDB** (modo por defecto): por cada lote de 25, `BatchGetItem` salta las claves que ya existen y `BatchWriteItem` escribe el resto. **Nunca sobrescribe** (un candidato que la API movió de etapa se queda como está).
  - Se usa el cliente de bajo nivel y no `Table.batch_writer()` porque `batch_writer` reenvía los `UnprocessedItems` sin esperar. Aquí hay backoff exponencial con jitter (hasta `SEED_DYNAMO_MAX_RETRIES`).
  - El throttling lo reintenta botocore en modo `adaptive`.
- `--conditional` hace `PutItem` condicional ítem por ítem. Es más lento, pero seguro aunque haya otros escritores a la vez.
- Si se corta a la mitad, basta con volver a ejecutar el mismo comando.

## Qué se genera

Los ítems DynamoDB replican campo por campo lo que escriben los handlers de `reference/` y de `services/attendance`. `employeeId` es el mismo UUID en core_hr, payroll, performance y attendance, así que los datos cruzan entre servicios.

| Servicio | Principal (= N por tenant) | Además | Detalle |
|---|---|---|---|
| core_hr (RDS) | `employees` | `departments` (20), `contracts` (1 por empleado) | email único `nombre.apellido.<i>@tenant-x.example.com` |
| payroll (RDS) | `pay_slips` | `payroll_periods` (10 meses cerrados) | 1,000 empleados × 10 periodos; `base_salary` = salario del contrato; descuento 13% (TODO) |
| recruitment | `CANDIDATE` | `VACANCY` (50), `UNIQUE_GUARD` (1 por candidato) | etapas APPLIED 40% · INTERVIEW 25% · OFFER 10% · HIRED 5% · REJECTED 20% |
| performance | `GOAL` + `EVALUATION` | `EVAL_SUMMARY` | 1,000 empleados × (2 metas + 2 ciclos × 4 evaluadores) = 2,000 GOAL + 8,000 EVALUATION |
| attendance | `ATTENDANCE` | `LEAVE` (2% = 200) | 100 empleados × 100 días hábiles anteriores a la fecha de referencia |

Por qué así:

- **Recruitment**:
  - IDs `c-<uuid>` y `v-<uuid>` (cumplen `^c-[0-9a-f-]{36}$`).
  - `PK/SK/GSI1PK/GSI1SK` idénticos a `createCandidate`. El guard `UNIQUE#APPLICATION#<vacancyId>#<email>` se crea igual que en su `TransactWrite`, para que la API siga devolviendo 409 ante un duplicado.
  - `stageHistory` sigue las `TRANSITIONS` de `updateStage` (`DRAFT→APPLIED` por el candidato, el resto por `system`).
  - `candidatesCount` = número de candidatos enviados de la vacante (el submit es lo único que lo incrementa).
  - 1 de cada 10 vacantes queda `CLOSED`.
- **Performance**:
  - `getEmployeePerformance` arranca leyendo `SUMMARY#<emp>#`; sin SUMMARY no muestra evaluaciones. Por eso se siembran los `EVAL_SUMMARY` (`evaluationsCount`, `scoreSum`, `lastScore`) calculados a partir de las evaluaciones, igual que el `ADD` de `submitEvaluation`.
  - Cada empleado tiene evaluaciones en el trimestre de la fecha de referencia y en el anterior (por defecto `2026-Q3` y `2026-Q4`), para que la comparación entre ciclos (`compareWith`) tenga datos. Por eso la proporción es 80% EVALUATION / 20% GOAL.
  - Relaciones SELF, MANAGER, PEER y DIRECT_REPORT. El evaluador siempre es distinto del evaluado salvo en SELF, y `anonymous` solo se usa en PEER.
  - Puntajes en pasos de 0.5 y `score` = promedio redondeado igual que el handler.
  - **Metas con `reminder.enabled = false` y sin `GSI1PK/GSI1SK`**. Si no, el cron horario `dispatchGoalReminders` enviaría miles de correos SES. Un test con moto comprueba que el GSI `REMINDER` queda vacío.
- **Attendance**:
  - Las marcaciones son todas `CLOSED` (entrada 07:45–09:00 hora Perú, de 8 a 10 h trabajadas).
  - Las licencias son futuras y no se solapan por empleado: mitad `PENDING`, mitad `APPROVED`, con `daysUnpaid` según la regla del contrato.

Limitaciones conocidas:

- Los archivos S3 (CV, certificados) **no se suben**. Los ítems tienen su `s3Key`, pero `GET /documents` responderá 404 "aún no existe".
- Las licencias `APPROVED` sembradas **no publicaron** `leave.approved`: Nóminas no las descuenta.
- Los correos usan dominios `example.com`. Si se cambia de etapa a un candidato sembrado, SES en sandbox rechazará el envío y el worker lo descarta.
- Las columnas y tipos de core_hr/payroll siguen el documento de diseño y están marcados `# TODO: ajustar al esquema final` en `seed_config.py` (incluidos `CONTRACT_TYPES` y el % de descuento).

## Configuración (variables de entorno)

| Variable | Default |
|---|---|
| `STAGE`, `AWS_REGION` | `dev`, `us-east-1` |
| `RECRUITMENT_TABLE`, `PERFORMANCE_TABLE`, `ATTENDANCE_TABLE` | `ms-<svc>-table-${STAGE}` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | —, 5432, `hcm_db`, `postgres`, —, `prefer` |
| `SCHEMA_TENANT_A` … | nombre del tenant |
| `SEED_TENANTS`, `SEED_PER_TENANT` | 3 tenants, 10000 |
| `SEED_REFERENCE_DATE` | hoy (solo afecta fechas, no claves) |
| `SEED_NAMESPACE` | fijo; cambiarlo genera **otro** dataset |
| `SEED_VACANCIES_PER_TENANT`, `SEED_ATTENDANCE_EMPLOYEES`, `SEED_PAYROLL_EMPLOYEES`, `SEED_LEAVES_RATIO` | 50, 100, 1000, 0.02 |
| `SEED_PERF_CYCLES` | trimestre actual y anterior |
| `SEED_DYNAMO_WORKERS`, `SEED_DYNAMO_MAX_RETRIES`, `SEED_RDS_PAGE_SIZE` | 8, 8, 2000 |

Los nombres de tablas y columnas RDS se cambian en `seed_config.py` (`CORE_HR`, `PAYROLL`).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

- `test_generators.py`: IDs según los regex de los handlers; claves iguales a las de los handlers; ninguna meta con GSI1; conteos exactos (10,000 por tenant); coherencia de `candidatesCount`, `stageHistory`, summaries, licencias y salarios; determinismo.
- `test_seed_master.py` (moto):
  - `--dry-run` no escribe nada; `--sample` + `--verify` dan OK.
  - La segunda corrida no escribe nada y no sobrescribe ítems modificados; se reanuda tras un corte.
  - Las consultas de los handlers (GSI1 de candidatos, prefijos de performance) funcionan sobre lo sembrado y el GSI `REMINDER` queda vacío.
  - Con RDS caído o sin configurar, DynamoDB sigue funcionando.
  - Mensaje claro si falta una tabla; backoff ante `UnprocessedItems`; nunca se usa Scan.
- `test_rds_postgres.py`: levanta un PostgreSQL temporal con `initdb`/`pg_ctl` y lo para al final. Se omite si no están instalados.
