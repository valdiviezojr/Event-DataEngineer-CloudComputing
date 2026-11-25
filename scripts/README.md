# Carga de datos ficticios de HCM

Por tenant se generan 10 000 empleados, 10 000 boletas, 10 000 candidatos, 2 000 metas, 8 000 evaluaciones y 10 000 marcaciones. Python informa `TOTAL_GLOBAL=150000` para los cinco servicios. El SQL informa `TOTAL_GLOBAL=60000` para empleados y boletas de PostgreSQL. Los departamentos, períodos, contratos, perfiles, vacantes, guards y summaries quedan fuera de ambos totales.

El calendario usa diez meses cerrados de marzo a diciembre de 2025, los ciclos 2025-Q3 y 2025-Q4 y la fecha de referencia 2026-01-01. Los mismos 1 000 empleados por tenant reciben una boleta mensual. Los contratos comienzan en enero de 2024. Las boletas descuentan una retención del 13 %; el total de cada período suma sus importes netos. Una colisión con un período existente detiene el preflight.

Cada tenant reutiliza los UUID de sus cuatro departamentos oficiales y añade 16 departamentos ficticios determinísticos. Recruitment crea 50 vacantes cerradas, con 200 candidaturas en borrador y 200 guards por vacante. Cada lote de hasta 49 pares incluye la vacante por inserción condicional o por `ConditionCheck` sobre sus atributos. Las postulaciones enviadas son cero. Las metas tienen recordatorios desactivados. Attendance genera 200 licencias `PENDING` de tipo `VACATION` o `SICK`, cada una para un empleado distinto fuera de la cohorte de Payroll y con fechas sin marcaciones. Estas licencias no requieren filas en el ledger. Los empleados son independientes de Auth. Se excluyen explícitamente `emp-001`, `emp-a-hr`, `emp-b-hr` y `52`. El archivo histórico `users.json` queda fuera del flujo.

## Uso local

Desde la raíz del workspace con Python 3.11 o superior:

```sh
python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py --dry-run --sample
python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py dry-run
python3 -m unittest discover -s Event-DataEngineer-CloudComputing/scripts/tests -v
```

Los dry-runs no abren conexiones. Los UUID de departamento de simulación son marcadores locales. Para las pruebas de PostgreSQL, aplica las cuatro migraciones oficiales a una instancia desechable y define `SEED_TEST_LOCAL_SOCKET` con el directorio de su socket Unix. La prueba obliga a usar un socket bajo `/tmp`; puedes definir `PGPORT`, `PGUSER` y `PGDATABASE` para ese servidor.

## Desde EC2

Usa Python 3.10 o superior, el certificado CA para RDS, el perfil IAM mediante IMDS o credenciales temporales de AWS Academy y un archivo `.pgpass` con permisos 0600. El preflight exige TLS `verify-full`. Define los valores recopilados de tu entorno y ejecuta desde la raíz del workspace:

```sh
python3 -m venv .venv-seed
. .venv-seed/bin/activate
python3 -m pip install -r Event-DataEngineer-CloudComputing/scripts/requirements.txt

export AWS_REGION=us-east-1 STAGE=dev
export SEED_AWS_ACCOUNT_ID='<cuenta-AWS-de-12-dígitos>'
export DB_HOST='<endpoint-RDS>' DB_PORT=5432 DB_NAME=hcm_db DB_USER='<rol-PostgreSQL>'
export DB_SSLROOTCERT='<ruta-absoluta-al-bundle-CA-RDS>'
export PGSSLMODE=verify-full PGSSLROOTCERT="$DB_SSLROOTCERT"
export SEED_MANIFEST="$PWD/seed-30k-manifest.json"

python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py preflight --manifest "$SEED_MANIFEST"
# A partir de aquí, solo después de autorizar la carga.
python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py load --manifest "$SEED_MANIFEST"
python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py --verify --manifest "$SEED_MANIFEST"
psql -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -f Proyecto2_Cloud_Integrante2/db/verify_30k_seeding.sql
```

`RECRUITMENT_TABLE`, `PERFORMANCE_TABLE` y `ATTENDANCE_TABLE` permiten declarar nombres desplegados distintos de los derivados de `STAGE`. Usa los mismos destinos y guarda el manifiesto en almacenamiento persistente para poder reanudar. El manifiesto incluye los parámetros fijos, los UUID de departamentos, el identificador de cada tabla DynamoDB y las huellas SHA-256 de los registros esperados.

El preflight requiere leer las tablas, inspeccionar esquemas y catálogos, acreditar los privilegios de inserción y bloqueo en PostgreSQL, y leer las claves esperadas en DynamoDB. Comprueba `DescribeTable`, `DescribeKinesisStreamingDestination`, `GetResourcePolicy`, `BatchGetItem` y `Query` en las tres tablas. En el modo estricto, para la autorización de escritura exige `GetCallerIdentity`, `DescribeOrganization`, `DescribeVpcEndpoints`, `GetRole` y `SimulatePrincipalPolicy` y comprueba `PutItem` para las transacciones y `ConditionCheckItem` para Recruitment. Una cuenta en Organizations, un endpoint VPC de DynamoDB, una política de recurso, un Stream activo, un flujo activo hacia Kinesis o una respuesta de permisos indeterminada bloquean la carga. El seeder no puede certificar esas configuraciones con este preflight de solo lectura. El contrato de PostgreSQL exige la estructura de las migraciones 001, 003 y 004, sin triggers de usuario, reglas, RLS ni publicaciones para las tablas inspeccionadas. La firma se obtuvo de PostgreSQL 18 y cualquier diferencia de definición detiene la carga.

`load` repite el preflight antes de confirmar PostgreSQL en una transacción para los tres tenants. Solo tras confirmar y validar PostgreSQL escribe las transacciones de DynamoDB en serie. Una interrupción puede dejar SQL confirmado y parte de DynamoDB pendiente. Reejecuta `load` con el mismo manifiesto. Los grupos completos e idénticos se reutilizan. Una coincidencia incompatible o un grupo incompleto requieren investigación y causan salida distinta de cero. Mantén estable la configuración del destino durante la operación. PostgreSQL y DynamoDB tienen transacciones separadas y las comprobaciones de AWS son puntuales.


## Diagnóstico con permisos de AWS Academy

`python3 Event-DataEngineer-CloudComputing/scripts/seed_master.py diagnose` comprueba el catálogo, los destinos, las claves y los controles de replicación que el rol pueda inspeccionar. Omite la acreditación IAM y no genera manifiesto ni habilita escrituras. Si una lectura requerida, como `GetResourcePolicy`, está restringida, el diagnóstico también se detiene.

En AWS Academy, configura las credenciales temporales y ejecuta export SEED_AWS_ACADEMY=1 antes del preflight. Este modo realiza pruebas transaccionales con condiciones imposibles, sin insertar registros. Se mantienen las validaciones de integridad, destinos y conflictos. Las pruebas no garantizan todos los permisos futuros ni atomicidad entre PostgreSQL y DynamoDB. El modo estricto sigue siendo el predeterminado.
