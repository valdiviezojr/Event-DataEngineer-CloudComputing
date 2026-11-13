# DEPLOY — Eventos, Asistencia y Seeding (SaaS HCM en AWS Academy)

Guía para desplegar esta parte del proyecto en el **Learner Lab**. Todos los comandos se ejecutan desde la **raíz del repo**, salvo que se indique un `cd`. Stage por defecto: `dev`.

> **Estado honesto:** nada de esta parte se ha desplegado todavía en AWS. Lo verificado (tests, plantillas compiladas, pruebas locales) está detallado en la [sección 10](#10-estado-de-verificación). Si algo falla en el primer despliegue real, revisa primero la [sección 8](#8-problemas-comunes).

---

## 1. Resumen

- **`hcm-events`** (`events/serverless-events.yml`): 3 topics SNS propios (hr, attendance, payroll), 3 colas SQS con su DLQ, suscripciones con `FilterPolicy` y una tabla DynamoDB de idempotencia. Importa el topic de recruitment.
- **`hcm-attendance`** (`services/attendance/serverless.yml`): API REST con 5 endpoints de marcaciones y licencias, protegidos por el Lambda Authorizer de **`hcm-auth`** (otro integrante), tabla `ms-attendance-table-${stage}` y publicación de `leave.approved`.
- **Workers SQS** (dentro de `hcm-attendance`): `processLeaveEventWorker` (`leave.approved`) y `processCandidateHiredWorker` (`candidate.hired`). Validan, aplican idempotencia y loguean. La lógica de negocio final es **TODO** de Nóminas y Core HR.
- **Seeding** (`scripts/seed_master.py`): 10,000 registros por tenant × 3 tenants en cada uno de los 5 microservicios (RDS + DynamoDB). Tenants y `employeeId` de los usuarios demo salen de `scripts/users.json`.
- Contratos de eventos (JSON Schema): `events/contracts/`.

```
ms-attendance ──leave.approved──► SNS hcm-attendance-${stage}-events
                                     └─[eventType=leave.approved]─► SQS hcm-events-${stage}-payroll-attendance-sync ─► processLeaveEventWorker
                                                                       └─ 3 fallos ─► …-payroll-attendance-sync-dlq
ms-recruitment ─candidate.hired─► SNS hcm-recruitment-${stage}-events  (stack de recruitment)
                                     └─[eventType=candidate.hired]─► SQS hcm-events-${stage}-hr-recruitment-sync ─► processCandidateHiredWorker
                                                                       └─ 3 fallos ─► …-hr-recruitment-sync-dlq
ms-core-hr ──employee.created───► SNS hcm-hr-${stage}-events
  (PENDIENTE)                        └─[eventType=employee.created]─► SQS hcm-events-${stage}-payroll-hr-sync ─► (PENDIENTE: consumidor de ms-payroll)
ms-payroll ─payroll.processed───► SNS hcm-payroll-${stage}-events ─► (sin suscriptores)
  (PENDIENTE)
Workers ──► DynamoDB hcm-events-idempotency-${stage}   (eventKey, TTL 7 días)
```

---

## 2. Requisitos previos

- [ ] **Node.js 20** (`node -v`).
- [ ] **Serverless Framework v3**: viene en el `package.json` de cada servicio (3.40.0 en el lock) y se usa con `npx serverless`. **No uses Serverless v4** global: exige login y no es la versión del proyecto.
- [ ] **AWS CLI v2** (`aws --version`).
- [ ] **Python 3.10+** y `pip`, solo para el seeding.
- [ ] `jq`, para extraer IDs en los smoke tests (viene en CloudShell).
- [ ] **Credenciales del Learner Lab**: *Start Lab* → esperar el punto verde → *AWS Details* → *AWS CLI: Show*. Pegar el bloque completo en `~/.aws/credentials`:

  ```ini
  [default]
  aws_access_key_id=ASIA...
  aws_secret_access_key=...
  aws_session_token=...
  ```

  ```bash
  aws configure set region us-east-1
  ```

  ⚠️ **Caducan** al terminar la sesión del lab (unas 4 h) o al pulsar *End Lab*. Hay que volver a pegarlas en cada sesión.

- [ ] **`LAB_ROLE_ARN`**: lo usan todos los `serverless.yml` de esta parte (`provider.iam.role: ${env:LAB_ROLE_ARN}`), porque en Academy **no se pueden crear roles IAM**. Se ve en la consola en *IAM → Roles → LabRole → ARN*, o se calcula así:

  ```bash
  export LAB_ROLE_ARN="arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/LabRole"
  echo $LAB_ROLE_ARN        # arn:aws:iam::000000000000:role/LabRole
  ```

  Hay que exportarla **en cada terminal** antes de `serverless deploy` o `remove`. Alternativa: copiar `.env.example` a `.env`, completarlo y cargarlo con `set -a && source .env && set +a`.

- [ ] **Verificación**:

  ```bash
  aws sts get-caller-identity
  # Esperado: "Arn": "arn:aws:sts::<cuenta>:assumed-role/voclabs/user..."
  ```

---

## 3. Dependencias de otros integrantes

| Qué necesito | De quién | Para qué | Si falta |
|---|---|---|---|
| Stack `hcm-recruitment-${stage}` desplegado, con el export **`hcm-recruitment-${stage}-topic-arn`** | Reclutamiento (`reference/recruitment-performance`) | `hcm-events` importa ese topic y le suscribe la cola `hr-recruitment-sync` | El deploy de `hcm-events` falla: *No export named hcm-recruitment-dev-topic-arn found* |
| **Migrar IAM** en `services/recruitment/serverless.yml` y `services/performance/serverless.yml`: quitar el plugin `serverless-iam-roles-per-function` y todos los bloques `iamRoleStatements`, y añadir `provider.iam.role: ${env:LAB_ROLE_ARN}` — **PENDIENTE** | Reclutamiento / Desempeño | Hoy crean un rol IAM por Lambda, cosa que Academy no permite | Sus stacks fallan y, en cadena, `hcm-events` no se puede desplegar |
| Bucket `hcm-app-storage` (CORS `POST`) y remitente **verificado en SES** | Infraestructura / Reclutamiento | Params `storageBucket` y `senderEmail` de recruitment y performance (su README) | Fallan la subida de CV y los correos de ellos; mi parte no usa S3 ni SES |
| Stack **`hcm-auth-${stage}`** desplegado, con el output **`AuthorizerArn`** (export `hcm-auth-${stage}-AuthorizerArn`) | Infraestructura | attendance lo lee con `${cf:hcm-auth-${stage}.AuthorizerArn}` y lo usa como authorizer `TOKEN` de los 5 endpoints | El `deploy`/`package` de attendance falla al resolver la variable: *Cannot resolve variable at "custom.authorizerArn"* (sección 8) |
| Que el authorizer devuelva en su `context` **`tenantId`**, **`role`** y **`employeeId`** (además de `userId`, `email`) y una política `Allow` para todas las rutas | Infraestructura | `tenantId` aísla los datos por tenant. Con `role = EMPLOYEE`, attendance solo deja operar sobre el propio `employeeId` y no deja aprobar licencias | Sin `tenantId`: **401 `Tenant no identificado`** aunque el token sea válido. Sin `role`/`employeeId`: no se aplica el control por rol |
| Usuarios demo creados en hcm-auth (`USERS_TABLE=hcm-auth-users-dev npm run seed:users`) con los **mismos `employeeId`** que `scripts/users.json` — los IDs son **provisionales** | Infraestructura | Login para las pruebas JWT; el seeding siembra datos para esos `employeeId` | Login falla, o el usuario entra pero no ve sus datos sembrados (si los IDs difieren) |
| Consumidor de **`leave.approved`**: implementar `applyUnpaidLeave(...)` (TODO en `services/attendance/handlers/processLeaveEventWorker.js`) — **PENDIENTE** | Nóminas | Descontar los días no pagados | El worker solo valida y loguea |
| Consumidor de **`candidate.hired`**: implementar `createEmployeeFromCandidate(...)` (TODO en `processCandidateHiredWorker.js`) y luego publicar `employee.created` — **PENDIENTE** | Core HR | Dar de alta al empleado contratado | El worker solo valida y loguea |
| **Idempotencia en su base de datos** al implementar esos TODO: `UNIQUE` (`leave_id`, `source_candidate_id`) + `INSERT … ON CONFLICT DO NOTHING` | Nóminas / Core HR | La tabla de idempotencia no cubre un fallo entre su `INSERT` y el `complete()` del worker | Descuentos o empleados duplicados ante un reintento |
| Consumidor de la cola **`hcm-events-${stage}-payroll-hr-sync`** (`employee.created`) — **PENDIENTE** | Nóminas | Registrar el perfil salarial | Los mensajes se acumulan en la cola sin procesarse |
| Publicar **`employee.created`** y **`payroll.processed`** según `events/contracts/*.schema.json`, con el MessageAttribute `eventType` — **PENDIENTE** | Core HR / Nóminas | Sin ese atributo la `FilterPolicy` descarta el mensaje | Nada llega a las colas |
| Definir formato de `employeeId` y `periodId`, y la **moneda** de `salary` / `totalPaid` (TODO en los contratos) — **PENDIENTE** | Core HR / Nóminas | Contratos definitivos | Los contratos quedan abiertos |
| **RDS accesible** desde donde se ejecute el seeding (acceso público + regla del security group para tu IP en el puerto 5432, o ejecutarlo desde CloudShell/EC2 en la misma VPC) y el **esquema final** (migraciones) — **PENDIENTE** | Core HR / Nóminas (integrante 2) | Sembrar `core_hr` y `payroll` | Esos 2 servicios fallan con un mensaje claro y **solo se siembran los de DynamoDB**. Provisional: `--create-schema` crea las tablas con el DDL del documento de diseño |

Cuando Nóminas o Core HR tengan su propio worker, deben **eliminar la función equivalente de `services/attendance/serverless.yml` en el mismo despliegue**: una cola debe tener un solo consumidor.

---

## 4. Orden de despliegue

| # | Stack | Directorio | Comando (stage `dev`) | Debe existir al terminar |
|---|---|---|---|---|
| 1 | `hcm-auth-dev` | repo de infraestructura (`~/hcm-auth`) | deploy según su README; usuarios: `USERS_TABLE=hcm-auth-users-dev npm run seed:users` | output **`AuthorizerArn`** (export `hcm-auth-dev-AuthorizerArn`) |
| 2 | `hcm-recruitment-dev`, `hcm-performance-dev` | `reference/recruitment-performance/services/recruitment` y `…/performance` (tras migrar IAM) | `npx serverless deploy --stage dev --param="senderEmail=<correo-SES>"` (+ `--param="storageBucket=hcm-app-storage"` en recruitment) | export **`hcm-recruitment-dev-topic-arn`**; tablas `ms-recruitment-table-dev`, `ms-performance-table-dev` |
| 3 | `hcm-events-dev` | `events/` | `npx serverless deploy --config serverless-events.yml --stage dev` | 10 exports **`hcm-events-dev-*`** (topics, colas, DLQ, `idempotency-table-name`) |
| 4 | `hcm-attendance-dev` | `services/attendance/` | `npx serverless deploy --stage dev` | export **`hcm-attendance-dev-table-name`** y los 5 endpoints |
| 5 | seeding | `scripts/` | `python seed_master.py` y luego `python seed_master.py --verify` | `--verify` todo `OK` (código 0), incluida la tabla de usuarios demo |

Todos los `serverless deploy` requieren `LAB_ROLE_ARN` exportada. Para otro stage, cambiar `dev` en **todos** los pasos.

> ⚠️ **`scripts/users.json` es PROVISIONAL**: los `employeeId` son inventados. Antes del paso 5 hay que reemplazarlo por la lista real de usuarios del sistema de autenticación (`tenantId`, `employeeId`, `email`) y validarla con `python seed_master.py --dry-run`.

**Stage:** todos los stacks usan `${opt:stage, 'dev'}`. Para otro stage, añade `--stage <nombre>` a **todos** los comandos (deploy, remove, info) y usa `STAGE=<nombre>` en el seeding. Los nombres e imports dependen del stage, así que no se pueden mezclar.

### 4.1 hcm-auth (infraestructura)

Lo despliega el integrante de infraestructura desde su repo. Antes de seguir, comprobar que existe en el **mismo stage**:

```bash
aws cloudformation describe-stacks --stack-name hcm-auth-dev \
  --query "Stacks[0].Outputs[?OutputKey=='AuthorizerArn'].OutputValue" --output text
# arn:aws:lambda:us-east-1:<cuenta>:function:hcm-auth-dev-authorizer
```

### 4.2 Recruitment y Performance (otro integrante)

Desde el repo de la compañera (aquí: `reference/recruitment-performance/`), **después de migrar IAM** (sección 3). Comandos tomados de su README:

```bash
export LAB_ROLE_ARN=...    # ver sección 2
cd reference/recruitment-performance/services/recruitment
npm install
npx serverless deploy --stage dev --param="senderEmail=<correo-verificado-SES>" --param="storageBucket=hcm-app-storage"

cd ../performance
npm install
npx serverless deploy --stage dev --param="senderEmail=<correo-verificado-SES>"
```

Al terminar debe existir el export que necesito:

```bash
aws cloudformation list-exports --query "Exports[?Name=='hcm-recruitment-dev-topic-arn'].Value" --output text
# arn:aws:sns:us-east-1:<cuenta>:hcm-recruitment-dev-events
```

### 4.3 hcm-events

```bash
cd events
npm ci
npx serverless deploy --config serverless-events.yml --stage dev
npx serverless info   --config serverless-events.yml --stage dev --verbose     # muestra los Stack Outputs
```

Requiere `LAB_ROLE_ARN` exportada (el script `npm run deploy` equivale a este deploy con stage `dev`). Al terminar deben aparecer **10 exports** (3 topics, 3 colas, 3 DLQ, 1 tabla):

```bash
aws cloudformation list-exports --query "Exports[?starts_with(Name, 'hcm-events-dev-')].Name" --output table
```

```
hcm-events-dev-hr-topic-arn
hcm-events-dev-attendance-topic-arn
hcm-events-dev-payroll-topic-arn
hcm-events-dev-payroll-hr-sync-queue-arn
hcm-events-dev-payroll-attendance-sync-queue-arn
hcm-events-dev-hr-recruitment-sync-queue-arn
hcm-events-dev-payroll-hr-sync-dlq-url
hcm-events-dev-payroll-attendance-sync-dlq-url
hcm-events-dev-hr-recruitment-sync-dlq-url
hcm-events-dev-idempotency-table-name
```

### 4.4 hcm-attendance

```bash
cd services/attendance
npm ci
npm test                                    # opcional: 53 tests Jest
npx serverless deploy --stage dev
```

Requiere `LAB_ROLE_ARN`, que `hcm-auth-dev` exista (lee su output `AuthorizerArn` al empaquetar) y que `hcm-events-dev` exista (importa el topic de asistencia, 2 colas y la tabla de idempotencia). Al terminar, `serverless deploy` imprime:

- **endpoints**: `POST /attendance/clock-in`, `POST /attendance/clock-out`, `POST /leaves/request`, `POST /leaves/{leaveId}/approve`, `GET /attendance`, con base `https://<api-id>.execute-api.us-east-1.amazonaws.com/dev`. Guárdala como `API`.
- **functions**: `clockIn`, `clockOut`, `requestLeave`, `approveLeave`, `listAttendance`, `processLeaveEventWorker`, `processCandidateHiredWorker`.
- export `hcm-attendance-dev-table-name`.

```bash
API=$(npx serverless info --stage dev --verbose | grep -o 'https://[^ ]*execute-api[^ ]*/dev' | head -1); echo $API
```

### 4.5 Seeding

Después de 4.1–4.4: las tablas DynamoDB deben existir. Se ejecuta en tu máquina o en CloudShell con las credenciales del lab.

```bash
cd scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export STAGE=dev
# Solo si el RDS ya está accesible (si no, déjalas vacías: core_hr y payroll fallan con mensaje claro y el resto sigue):
export DB_HOST=<endpoint-rds> DB_USER=<usuario> DB_PASSWORD=<clave> DB_NAME=hcm_db

python seed_master.py --dry-run           # cuenta sin tocar nada
python seed_master.py --sample            # prueba: 100 por tenant
python seed_master.py                     # carga completa: 10,000 × 3 tenants × 5 servicios
python seed_master.py --verify            # evidencia de los conteos (sección 7.7)
```

Los tenants y los `employeeId` de los usuarios demo salen de `scripts/users.json` (o `SEED_USERS_FILE`). Si el archivo es inválido (JSON roto, `employeeId` fuera de `^[A-Za-z0-9_-]{1,64}$`, tenant sin usuarios), el script termina con código `3` **antes de escribir nada**.

Es idempotente y reanudable: si se corta, basta con volver a ejecutar el mismo comando. Solo DynamoDB: `--service recruitment performance attendance`. RDS sin migraciones: añade `--create-schema` (provisional). Detalle completo en `scripts/README.md`.

---

## 5. Variables de entorno y params

### Variables que tú exportas

| Nombre | Dónde se usa | Ejemplo | Obligatorio |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | AWS CLI, Serverless, seeding (o en `~/.aws/credentials`) | del Learner Lab | Sí (en uno de los dos sitios) |
| `AWS_REGION` | Seeding (boto3) | `us-east-1` | No (default `us-east-1`) |
| `LAB_ROLE_ARN` | `provider.iam.role` de `events/serverless-events.yml` y `services/attendance/serverless.yml` | `arn:aws:iam::000000000000:role/LabRole` | **Sí**, en todo deploy/remove |
| `STAGE` | Solo el seeding (nombres de tabla). Serverless usa `--stage` | `dev` | No (default `dev`) |
| `AUTH_API` | Solo los curl de prueba (login de hcm-auth) | `https://0kcyrpixu6.execute-api.us-east-1.amazonaws.com/dev` | No |
| `SEED_USERS_FILE` | Seeding: usuarios demo (tenants + `employeeId`) | `scripts/users.json` | No (default `scripts/users.json`) |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Seeding de core_hr/payroll | `mydb.xxx.us-east-1.rds.amazonaws.com`, `5432`, `hcm_db`, `postgres`, `…`, `prefer` | Solo para RDS |
| `SCHEMA_TENANT_A`, `SCHEMA_TENANT_B`, `SCHEMA_TENANT_C` | Seeding: schema RDS de cada tenant | `tenant_a` | No (default = nombre del tenant) |
| `RECRUITMENT_TABLE`, `PERFORMANCE_TABLE`, `ATTENDANCE_TABLE` | Seeding: sobrescribir nombres de tabla | `ms-attendance-table-dev` | No (default `ms-<svc>-table-${STAGE}`) |
| `SEED_TENANTS`, `SEED_PER_TENANT`, `SEED_REFERENCE_DATE`, `SEED_NAMESPACE`, `SEED_*` | Seeding (lista completa en `scripts/README.md`). Sin `SEED_TENANTS` se usan los tenants de `users.json` | `tenant_a,tenant_b`, `10000`, `2026-11-09` | No |

### Params de Serverless (`--param="nombre=valor"`)

| Param | Stack | Default | Efecto |
|---|---|---|---|
| `authorizerArn` | hcm-attendance | `${cf:hcm-auth-${stage}.AuthorizerArn}` | Solo para `print`/`package`/`offline` sin AWS (ARN falso). **No pasarlo en deploy**: el real sale de hcm-auth |
| `simulateFailure` | hcm-attendance | `'false'` | `true` hace que los 2 workers fallen a propósito (prueba de DLQ) |
| `senderEmail`, `storageBucket` | hcm-recruitment / hcm-performance (otro integrante) | ver su README | Correo SES y bucket S3 |

### Variables que el `serverless.yml` inyecta en las Lambdas (no tocar)

| Variable | Valor | Funciones |
|---|---|---|
| `ATTENDANCE_TABLE` | `ms-attendance-table-${stage}` | todas las de attendance |
| `ATTENDANCE_TOPIC_ARN` | `!ImportValue hcm-events-${stage}-attendance-topic-arn` | todas (la usa `approveLeave`) |
| `TZ_OFFSET_HOURS` | `-5` | todas (fecha local Perú) |
| `IDEMPOTENCY_TABLE` | `!ImportValue hcm-events-${stage}-idempotency-table-name` | los 2 workers |
| `SIMULATE_FAILURE` | param `simulateFailure` | los 2 workers |

---

## 6. Recursos que se crean

Nombres reales con `stage = dev`.

| Stack (CloudFormation) | Recurso | Nombre |
|---|---|---|
| `hcm-events-dev` | SNS Topic | `hcm-hr-dev-events` |
| | SNS Topic | `hcm-attendance-dev-events` |
| | SNS Topic | `hcm-payroll-dev-events` |
| | SQS + DLQ (`employee.created`, desde topic hr) | `hcm-events-dev-payroll-hr-sync`, `hcm-events-dev-payroll-hr-sync-dlq` |
| | SQS + DLQ (`leave.approved`, desde topic attendance) | `hcm-events-dev-payroll-attendance-sync`, `…-dlq` |
| | SQS + DLQ (`candidate.hired`, desde topic recruitment importado) | `hcm-events-dev-hr-recruitment-sync`, `…-dlq` |
| | 3 SQS QueuePolicy | permiten `sqs:SendMessage` solo desde su topic (`aws:SourceArn`) |
| | 3 SNS Subscription | `RawMessageDelivery: false` + `FilterPolicy` por `eventType` |
| | DynamoDB | `hcm-events-idempotency-dev` (PK `eventKey`, TTL `expiresAt`, PAY_PER_REQUEST) |
| `hcm-attendance-dev` | Lambda ×7 | `hcm-attendance-dev-clockIn`, `-clockOut`, `-requestLeave`, `-approveLeave`, `-listAttendance`, `-processLeaveEventWorker`, `-processCandidateHiredWorker` |
| | API Gateway REST | `dev-hcm-attendance` |
| | API Gateway Authorizer `TOKEN` + `Lambda::Permission` | apuntan a la Lambda `hcm-auth-dev-authorizer` (no se crea otra Lambda); TTL de caché 0 |
| | 2 Event Source Mappings SQS | `batchSize 10`, `ReportBatchItemFailures` |
| | DynamoDB | `ms-attendance-table-dev` (PK/SK + GSI1, PAY_PER_REQUEST, PITR) |
| | CloudWatch Log Groups | `/aws/lambda/hcm-attendance-dev-<función>` (retención 14 días) |
| ambos | Bucket de despliegue de Serverless | lo crea Serverless automáticamente (`hcm-…-serverlessdeploymentbucket-…`) |

Ningún stack crea roles IAM: todas las Lambdas usan `LabRole`.

Configuración de las colas: `VisibilityTimeout 180` s, `maxReceiveCount 3`, retención de DLQ 14 días (1209600 s).

### Exports para otros stacks

| Export | Valor | Lo usa |
|---|---|---|
| `hcm-events-${stage}-hr-topic-arn` | ARN topic hr | Core HR (publicar `employee.created`) |
| `hcm-events-${stage}-attendance-topic-arn` | ARN topic attendance | hcm-attendance |
| `hcm-events-${stage}-payroll-topic-arn` | ARN topic payroll | Nóminas (publicar `payroll.processed`) |
| `hcm-events-${stage}-payroll-hr-sync-queue-arn` | ARN cola | Nóminas (consumir `employee.created`) |
| `hcm-events-${stage}-payroll-attendance-sync-queue-arn` | ARN cola | hcm-attendance hoy; Nóminas cuando migre el worker |
| `hcm-events-${stage}-hr-recruitment-sync-queue-arn` | ARN cola | hcm-attendance hoy; Core HR cuando migre el worker |
| `hcm-events-${stage}-<cola>-dlq-url` (×3) | URL de cada DLQ | Operación / pruebas |
| `hcm-events-${stage}-idempotency-table-name` | `hcm-events-idempotency-${stage}` | Workers |
| `hcm-attendance-${stage}-table-name` | `ms-attendance-table-${stage}` | Informativo |

El ARN de una DLQ no se exporta. Se obtiene así:

```bash
aws sqs get-queue-attributes --queue-url <dlq-url> --attribute-names QueueArn --query Attributes.QueueArn --output text
```

Ejemplo para importar desde otro `serverless.yml`:

```yaml
functions:
  worker:
    events:
      - sqs:
          arn: !ImportValue hcm-events-${sls:stage}-payroll-hr-sync-queue-arn
          batchSize: 10
          functionResponseType: ReportBatchItemFailures
```

---

## 7. Verificación post-despliegue

Helpers para esta sección (bash):

```bash
export AWS_REGION=us-east-1
exp() { aws cloudformation list-exports --query "Exports[?Name=='$1'].Value" --output text; }
qurl() { aws sqs get-queue-url --queue-name "$1" --query QueueUrl --output text; }
depth() { aws sqs get-queue-attributes --queue-url "$1" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes; }
uuid() { cat /proc/sys/kernel/random/uuid; }       # en macOS: uuidgen | tr A-Z a-z

HR_TOPIC=$(exp hcm-events-dev-hr-topic-arn)
ATT_TOPIC=$(exp hcm-events-dev-attendance-topic-arn)
REC_TOPIC=$(exp hcm-recruitment-dev-topic-arn)
Q_HR=$(qurl hcm-events-dev-payroll-hr-sync)
Q_ATT=$(qurl hcm-events-dev-payroll-attendance-sync)
Q_REC=$(qurl hcm-events-dev-hr-recruitment-sync)
```

### 7.1 Topics, suscripciones y colas

```bash
for T in $HR_TOPIC $ATT_TOPIC $REC_TOPIC; do
  aws sns list-subscriptions-by-topic --topic-arn $T --query "Subscriptions[?Protocol=='sqs'].[Endpoint,SubscriptionArn]" --output text
done
```

Esperado: una suscripción `sqs` hacia `…payroll-hr-sync`, `…payroll-attendance-sync` y `…hr-recruitment-sync` respectivamente, con un `SubscriptionArn` real, **no** `PendingConfirmation`. El topic de recruitment tiene además la cola propia de recruitment (`hcm-recruitment-dev-notify`).

```bash
SUB=$(aws sns list-subscriptions-by-topic --topic-arn $ATT_TOPIC --query "Subscriptions[?Protocol=='sqs'].SubscriptionArn" --output text)
aws sns get-subscription-attributes --subscription-arn $SUB --query "Attributes.[FilterPolicy,RawMessageDelivery]"
# ["{\"eventType\":[\"leave.approved\"]}", "false"]

aws sqs get-queue-attributes --queue-url $Q_ATT --attribute-names VisibilityTimeout RedrivePolicy Policy
# VisibilityTimeout "180"; RedrivePolicy con maxReceiveCount 3 y la DLQ; Policy con aws:SourceArn = topic attendance

aws lambda list-event-source-mappings --function-name hcm-attendance-dev-processLeaveEventWorker \
  --query "EventSourceMappings[].[State,BatchSize,FunctionResponseTypes[0]]"
# [["Enabled", 10, "ReportBatchItemFailures"]]   (igual para hcm-attendance-dev-processCandidateHiredWorker)
```

### 7.2 Prueba de eventos y FilterPolicy

Payloads tomados de `events/contracts/README.md`. El atributo `eventType` es obligatorio: sin él, la FilterPolicy descarta el mensaje.

**a) `leave.approved` → solo llega a `payroll-attendance-sync`:**

```bash
aws sns publish --topic-arn $ATT_TOPIC \
  --message '{"eventType":"leave.approved","eventId":"'$(uuid)'","occurredAt":"2026-11-09T15:00:00.000Z","tenantId":"tenant_a","leaveId":"l-9a3f1c2e-7b4d-4e8a-a6f0-1d2c3b4a5e6f","employeeId":"emp-102","daysUnpaid":3,"startDate":"2026-11-18","endDate":"2026-11-20","leaveType":"UNPAID","totalDays":3}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"leave.approved"},"tenantId":{"DataType":"String","StringValue":"tenant_a"}}'

aws logs tail /aws/lambda/hcm-attendance-dev-processLeaveEventWorker --since 5m
```

Esperado en el log: `"msg":"leave.approved recibido (pendiente integración con ms-payroll)"` con `tenantId`, `eventType`, `messageId`, `eventKey`, y luego `"Lote procesado"` con `processed: 1`. La cola la consume el worker al instante. Si vuelves a publicar **el mismo `eventId`**, aparece `"Evento duplicado, se omite"`.

**b) `employee.created` → solo llega a `payroll-hr-sync`.** Esa cola no tiene consumidor, así que el mensaje se queda en ella:

```bash
depth $Q_HR    # antes: "0"
aws sns publish --topic-arn $HR_TOPIC \
  --message '{"eventType":"employee.created","eventId":"'$(uuid)'","occurredAt":"2026-11-09T14:03:12.511Z","tenantId":"tenant_a","employeeId":"emp-102","email":"carlos.ruiz@empresa.com","salary":4500,"hireDate":"2026-11-15"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"employee.created"},"tenantId":{"DataType":"String","StringValue":"tenant_a"}}'
depth $Q_HR    # después: ApproximateNumberOfMessages "1"
aws sqs receive-message --queue-url $Q_HR --max-number-of-messages 1 --query "Messages[0].Body" --output text | jq .
# Envelope SNS: "Type": "Notification", "MessageId", "Message" (el JSON publicado), "MessageAttributes"
aws sqs purge-queue --queue-url $Q_HR      # limpiar
```

En ese mismo momento, `depth $Q_ATT` y `depth $Q_REC` deben seguir en `0` y no debe aparecer nada nuevo en los logs de los workers.

**c) Evento no suscrito → no llega a ninguna cola:**

```bash
aws sns publish --topic-arn $ATT_TOPIC --message '{"eventType":"leave.requested","tenantId":"tenant_a"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"leave.requested"}}'
# Sin logs nuevos en processLeaveEventWorker; depth de las 3 colas en 0.
```

**d) `candidate.hired` → `hr-recruitment-sync`.** El payload real de recruitment no lleva `eventId`; la idempotencia usa el `MessageId` de SNS. Hazlo pasando un candidato de OFFER a HIRED desde la API de recruitment (`PATCH /candidates/{id}/stage`), o publica a mano:

```bash
aws sns publish --topic-arn $REC_TOPIC \
  --message '{"eventType":"candidate.hired","tenantId":"tenant_a","candidateId":"c-3f6b2a10-8c4d-4e9f-a1b2-c3d4e5f6a7b8","vacancyId":"v-1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d","vacancyTitle":"Electricista Industrial","fullName":"María García","email":"maria@gmail.com","fromStage":"OFFER","toStage":"HIRED","note":null,"changedBy":"reclutador@empresa.com","changedAt":"2026-11-09T16:20:41.002Z"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"candidate.hired"},"tenantId":{"DataType":"String","StringValue":"tenant_a"}}'
aws logs tail /aws/lambda/hcm-attendance-dev-processCandidateHiredWorker --since 5m
# "candidate.hired recibido (pendiente integración con ms-core-hr)"
```

**e) Mensaje inválido → se descarta sin reintentos (no va a la DLQ):** publica el ejemplo (a) con `"daysUnpaid":-1`. En el log aparece `"Payload inválido según contrato, se descarta"`.

### 7.3 Prueba de DLQ (3 intentos)

```bash
cd services/attendance
npx serverless deploy --stage dev --param="simulateFailure=true"
```

1. Publica el evento válido de 7.2 (a) con un `eventId` nuevo.
2. Espera unos **10 minutos**: 3 recepciones con 180 s de visibilidad entre cada una. En el log aparece `"Error transitorio procesando evento, se reintentará"` con `approximateReceiveCount` 1, 2 y 3.
3. Comprueba la DLQ:

   ```bash
   DLQ=$(exp hcm-events-dev-payroll-attendance-sync-dlq-url)
   depth $DLQ                                   # ApproximateNumberOfMessages "1"
   aws sqs receive-message --queue-url $DLQ --query "Messages[0].Body" --output text | jq .   # envelope SNS original
   ```

4. Vuelve a la normalidad y reprocesa:

   ```bash
   npx serverless deploy --stage dev            # simulateFailure vuelve a 'false'
   DLQ_ARN=$(aws sqs get-queue-attributes --queue-url $DLQ --attribute-names QueueArn --query Attributes.QueueArn --output text)
   aws sqs start-message-move-task --source-arn $DLQ_ARN
   aws logs tail /aws/lambda/hcm-attendance-dev-processLeaveEventWorker --since 5m   # ahora "processed: 1"
   ```

### 7.4 Smoke test de ms-attendance con `x-tenant-id` (serverless offline)

⚠️ El header `x-tenant-id` **solo se acepta en `serverless offline`** (variable `IS_OFFLINE`). serverless-offline no ejecuta authorizers por ARN (avisa *does not support non local authorizers* y deja pasar). Contra la API desplegada, `x-tenant-id` nunca define el tenant: sin token → 401 de API Gateway. Offline ejecuta las Lambdas en tu máquina contra la **tabla real** `ms-attendance-table-dev`, así que necesita las credenciales del lab. En offline, `approve` responde `notification: "SKIPPED"`, porque el `!ImportValue` del topic no se resuelve en local. El flujo de eventos se prueba en 7.2.

```bash
cd services/attendance
npx serverless offline --stage dev       # deja esta terminal abierta; en otra:
# (si hcm-auth no está desplegado: añade --param="authorizerArn=arn:aws:lambda:us-east-1:000000000000:function:x")

B=http://localhost:3000/dev
H=(-H 'x-tenant-id: tenant_a' -H 'content-type: application/json')
```

| Paso | Comando | Esperado |
|---|---|---|
| Entrada (3 días pasados) | `for d in 03 04 05; do curl -s -X POST $B/attendance/clock-in "${H[@]}" -d '{"employeeId":"emp-102","timestamp":"2026-11-'$d'T13:05:00Z"}'; echo; done` | 201 `"Entrada registrada"` ×3 |
| Entrada duplicada | repetir uno de los anteriores | 409 `"El empleado ya registró su entrada ese día"` |
| Salida | `curl -s -X POST $B/attendance/clock-out "${H[@]}" -d '{"employeeId":"emp-102","timestamp":"2026-11-03T22:10:00Z","date":"2026-11-03"}'` | 200, `status: "CLOSED"`, `workedMinutes: 545` |
| Salida sin entrada | igual con `"date":"2026-10-01"` | 404 `"No hay entrada registrada para ese día"` |
| Página 1 | `curl -s "$B/attendance?employeeId=emp-102&from=2026-11-01&to=2026-11-30&limit=2" -H 'x-tenant-id: tenant_a' \| jq '{count,nextToken}'` | `count: 2`, `nextToken` no nulo |
| Página 2 | `curl -s "$B/attendance?employeeId=emp-102&from=2026-11-01&to=2026-11-30&limit=2&nextToken=<token>" -H 'x-tenant-id: tenant_a' \| jq .count` | `1`, `nextToken: null` |
| Solicitar licencia | `S=$(date -d '+20 days' +%F); E=$(date -d '+22 days' +%F)` y luego `LEAVE=$(curl -s -X POST $B/leaves/request "${H[@]}" -d '{"employeeId":"emp-102","type":"UNPAID","startDate":"'$S'","endDate":"'$E'"}' \| jq -r .leave.leaveId); echo $LEAVE` | 201, `status: "PENDING"`, `l-<uuid>`. En macOS: `date -v+20d +%F` |
| Solapamiento | repetir la misma solicitud | 409 con `overlaps` |
| Aprobar | `curl -s -X POST $B/leaves/$LEAVE/approve "${H[@]}" -d '{}' \| jq '.leave.status,.leave.daysUnpaid,.notification'` | `"APPROVED"`, `3`, `"SKIPPED"` (offline) |
| Aprobar otra vez | mismo comando | 409 `"La licencia ya está APPROVED"` |

### 7.5 Smoke test con JWT (hcm-auth)

Login HTTP de hcm-auth (no Cognito). Usuarios en `scripts/users.json`; la contraseña de los usuarios demo la define hcm-auth (pedirla a infraestructura; no se guarda en este repo). JWT HS256, 8 h.

```bash
AUTH_API=https://0kcyrpixu6.execute-api.us-east-1.amazonaws.com/dev
login() { curl -s -X POST "$AUTH_API/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"${2:-<contraseña-demo>}\"}" | jq -r .token; }
TA=$(login hr@empresa-a.com); TE=$(login empleado@empresa-a.com); TB=$(login hr@empresa-b.com)
J=(-H "Authorization: Bearer $TA" -H 'content-type: application/json')
```

| Paso | Comando | Esperado |
|---|---|---|
| Sin token | `curl -s -o /dev/null -w "%{http_code}\n" "$API/attendance?employeeId=emp-a-001"` | `401` (API Gateway) |
| Datos sembrados del usuario | `curl -s "$API/attendance?employeeId=emp-a-001&limit=5" -H "Authorization: Bearer $TA" \| jq '.count,.nextToken'` | `5`, `nextToken` no nulo |
| Entrada | `curl -s -X POST $API/attendance/clock-in "${J[@]}" -d '{"employeeId":"emp-a-001"}'` | 201 (409 si ya marcó hoy) |
| Salida | `curl -s -X POST $API/attendance/clock-out "${J[@]}" -d '{"employeeId":"emp-a-001"}'` | 200, `status: "CLOSED"` |
| Licencia | `S=$(date -d '+40 days' +%F); E=$(date -d '+42 days' +%F); LEAVE=$(curl -s -X POST $API/leaves/request "${J[@]}" -d '{"employeeId":"emp-a-001","type":"UNPAID","startDate":"'$S'","endDate":"'$E'"}' \| jq -r .leave.leaveId); echo $LEAVE` | `l-<uuid>` |
| Aprobar | `curl -s -X POST $API/leaves/$LEAVE/approve "${J[@]}" -d '{}' \| jq '.leave.status,.notification'` | `"APPROVED"`, `"QUEUED"` |
| EMPLOYEE sobre otro empleado | `curl -s -X POST $API/attendance/clock-in -H "Authorization: Bearer $TE" -H 'content-type: application/json' -d '{"employeeId":"emp-a-hr"}'` | 403 `"Solo puedes operar sobre tus propios registros"` |
| EMPLOYEE aprueba | `curl -s -X POST $API/leaves/$LEAVE/approve -H "Authorization: Bearer $TE" -H 'content-type: application/json' -d '{}'` | 403 `"Tu rol no puede aprobar licencias"` |

El resto de pasos de 7.4 son iguales, cambiando `x-tenant-id` por `Authorization: Bearer $TA`.

### 7.6 Prueba de aislamiento entre tenants

Con los datos creados por `tenant_a` en 7.4 (offline):

| Caso | Comando | Esperado |
|---|---|---|
| tenant_b lista los datos de tenant_a | `curl -s "$B/attendance?employeeId=emp-102" -H 'x-tenant-id: tenant_b' \| jq .count` | `0` (otra partición: no ve nada) |
| tenant_b aprueba una licencia de tenant_a | `curl -s -X POST $B/leaves/$LEAVE/approve -H 'x-tenant-id: tenant_b' -H 'content-type: application/json' -d '{}'` | 404 `"Licencia no encontrada"` |
| Body con otro tenant | `curl -s -X POST $B/attendance/clock-in -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' -d '{"employeeId":"emp-102","tenantId":"tenant_b"}'` | 403 `{"message":"Acceso denegado","requestId":…}` |
| Query con otro tenant | `curl -s "$B/attendance?employeeId=emp-102&tenantId=tenant_b" -H 'x-tenant-id: tenant_a'` | 403 |
| nextToken de otro tenant | usar como tenant_b un `nextToken` obtenido por tenant_a | 400 `"nextToken inválido"` |
| JWT: tenant_b lista datos de tenant_a | `curl -s "$API/attendance?employeeId=emp-a-001" -H "Authorization: Bearer $TB" \| jq .count` | `0` |
| JWT: tenant_b aprueba licencia de tenant_a | `curl -s -X POST $API/leaves/$LEAVE/approve -H "Authorization: Bearer $TB" -H 'content-type: application/json' -d '{}'` | 404 `"Licencia no encontrada"` |
| JWT: token de tenant_b + body `tenantId: tenant_a` | `curl -s -X POST $API/attendance/clock-in -H "Authorization: Bearer $TB" -H 'content-type: application/json' -d '{"employeeId":"emp-b-001","tenantId":"tenant_a"}'` | 403 |
| JWT: token de tenant_b + header `x-tenant-id: tenant_a` | `curl -s "$API/attendance?employeeId=emp-b-001" -H "Authorization: Bearer $TB" -H 'x-tenant-id: tenant_a'` | 403 |

Cada 403 deja en CloudWatch un log `"SECURITY: violación de aislamiento multi-tenant"` con `details.mismatches`.

### 7.7 Seeding: evidencia de los 30,000 por microservicio

```bash
cd scripts && source .venv/bin/activate && export STAGE=dev
python seed_master.py --verify
```

Esta tabla es la **evidencia oficial**. Cuenta con `Query` (PK del tenant + prefijo de SK + `entityType`) o `count(*)` en RDS, y compara con lo esperado: columna `estado` = `OK` / `FALTAN` / `EXTRA`. Entidades principales, 10,000 por tenant cada una: `core_hr=employees`, `payroll=pay_slips`, `recruitment=CANDIDATE`, `performance=GOAL+EVALUATION`, `attendance=ATTENDANCE`. Código de salida `0` si todo está bien y `2` si faltan registros.

⚠️ **No uses el contador de la consola de DynamoDB como evidencia:**
- Muestra **más ítems** de los 10,000, porque la misma tabla guarda otros tipos de entidad: `UNIQUE_GUARD`, `VACANCY`, `EVAL_SUMMARY`, `LEAVE`.
- Su "Item count" se **actualiza solo cada ~6 horas**.

`EXTRA` significa que hay datos creados por la API además del seed; no es un error.

Debajo, una segunda tabla **Usuarios demo** comprueba que cada `employeeId` de `users.json` existe en attendance (`ATTENDANCE#<emp>#…`) y en performance (`SUMMARY#<emp>#…`, 2026-Q3 y 2026-Q4). Si alguno falta: `FALTAN` y código `2`.

### 7.8 Logs en CloudWatch

Log groups: `/aws/lambda/hcm-attendance-dev-<función>`, donde `<función>` es `clockIn`, `clockOut`, `requestLeave`, `approveLeave`, `listAttendance`, `processLeaveEventWorker` o `processCandidateHiredWorker`. Todos los logs son JSON con `level`, `fn`, `msg`, `ts`, `tenantId` y `requestId`; los workers añaden `eventType`, `messageId`, `snsMessageId` y `eventKey`.

```bash
aws logs tail /aws/lambda/hcm-attendance-dev-approveLeave --since 15m --follow
```

Logs Insights (seleccionar los log groups `hcm-attendance-dev-*`):

```
fields @timestamp, fn, level, msg, tenantId, requestId, eventType, messageId
| filter tenantId = "tenant_a"
| sort @timestamp desc
| limit 100
```

Buscar un error a partir del `requestId` que devuelve la API: `| filter requestId = "<id>"`. Violaciones de tenant: `| filter msg like /SECURITY/`.

---

## 8. Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `ExpiredToken` / `The security token included in the request is expired` | Sesión del lab caducada | *Start Lab* de nuevo y volver a pegar las 3 credenciales en `~/.aws/credentials` |
| `No export named hcm-recruitment-dev-topic-arn found` al desplegar events | Recruitment no desplegado, en otro stage o con otro nombre de servicio | Desplegar recruitment primero (4.2) en el **mismo** stage; comprobar con `aws cloudformation list-exports` |
| `No export named hcm-events-dev-…` al desplegar attendance | `hcm-events` no desplegado o en otro stage | Desplegar 4.3 antes que 4.4 |
| `… is not authorized to perform: iam:CreateRole` | Un `serverless.yml` intenta crear roles (plugin `serverless-iam-roles-per-function` o `iamRoleStatements`) | Migrar a `provider.iam.role: ${env:LAB_ROLE_ARN}` (sección 3). Los yml de esta parte ya no crean roles |
| `Cannot resolve variable at "provider.iam.role": Value not found at "env" source` | `LAB_ROLE_ARN` no exportada en esa terminal | `export LAB_ROLE_ARN=…` (sección 2) |
| El evento se publica pero no llega a la cola | Falta el MessageAttribute `eventType`, `eventType` distinto al de la FilterPolicy, o la QueuePolicy no autoriza al topic | Revisar 7.1 (`FilterPolicy`, `Policy` con `aws:SourceArn`) y publicar con `--message-attributes` |
| `Cannot resolve variable at "custom.authorizerArn": Stack with id hcm-auth-dev does not exist` al desplegar attendance | `hcm-auth` no desplegado, en otro stage o con otro nombre | Desplegar hcm-auth primero (4.1) en el **mismo** stage; comprobar con el `describe-stacks` de 4.1 |
| `Cannot resolve variable at "custom.authorizerArn": … Output 'AuthorizerArn' not found` (o *No export named hcm-auth-dev-AuthorizerArn*) | hcm-auth cambió el nombre de su output/export | Pedir el nombre exacto y ajustar `custom.authorizerArn` en `serverless.yml` (`${cf:<stack>.<OutputKey>}`) |
| Deploy de attendance falla en `AuthorizerApiGatewayAuthorizer` / `AuthorizerLambdaPermissionApiGateway` (*Function not found*) | La Lambda `hcm-auth-<stage>-authorizer` no existe (stack borrado o ARN viejo) | Redesplegar hcm-auth y luego attendance |
| **401 `Unauthorized`** (de API Gateway, sin `requestId`) | Falta `Authorization: Bearer <token>`, token expirado (8 h) o firma inválida | Volver a hacer login (7.5) |
| **401 `{"message":"Tenant no identificado","requestId":…}`** con token válido | El authorizer no devolvió `tenantId` en `requestContext.authorizer` (otro nombre o anidado en `claims`) | Ver el log `"Tenant no identificado"`; acordar la ruta con infraestructura y ajustarla **solo** en `getAuthContext`/`getTenantId` de `services/attendance/lib/http.js` |
| **403 `{"Message":"User is not authorized…"}`** (de API Gateway) | La política del authorizer no cubre el ARN del método de attendance | Infraestructura debe devolver `Allow` con comodín (`arn:aws:execute-api:…/*`) |
| 500 en todos los endpoints y API Gateway loguea *Execution failed due to configuration error: Invalid permissions on Lambda function* | Falta el `Lambda::Permission` para invocar el authorizer | Redesplegar attendance (lo crea `AuthorizerLambdaPermissionApiGateway`) |
| 403 `Acceso denegado` inesperado | Body, query, path o header `x-tenant-id` con un tenant distinto al del token | Quitar `tenantId` del body/query o hacerlo coincidir |
| El worker reintenta todo el lote y loguea `IDEMPOTENCY_TABLE no definida, se reintenta todo el lote` | La variable `IDEMPOTENCY_TABLE` llegó vacía a la Lambda | Redesplegar attendance después de `hcm-events` y revisar el export `hcm-events-<stage>-idempotency-table-name` |
| Los mensajes de `payroll-hr-sync` se acumulan | Esa cola aún no tiene consumidor (PENDIENTE de Nóminas) | Es lo esperado. Para pruebas: `aws sqs purge-queue` |
| Stack en `ROLLBACK_COMPLETE` (o `UPDATE_ROLLBACK_FAILED`) | Falló el primer deploy | Leer el motivo y luego borrar el stack y reintentar (comandos debajo) |
| `CREATE_FAILED` por límite o servicio no permitido | Restricciones del Learner Lab (cuotas, servicios o regiones permitidas) | Usar `us-east-1`. Ver el `ResourceStatusReason` exacto con el comando de eventos de abajo y bajar stacks que no se usen |
| El seeding dice `RDS no disponible: …` | `DB_HOST` vacío, RDS no público o security group sin tu IP | Ver sección 3 (fila RDS). Los servicios DynamoDB se siembran igual |
| El seeding dice `la tabla ms-…-table-dev no existe` | Servicio no desplegado o `STAGE` distinto | Desplegar el servicio o exportar el `STAGE` correcto |

```bash
# Ver por qué falló un stack
aws cloudformation describe-stack-events --stack-name hcm-events-dev \
  --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]" --output table

# Borrar un stack en ROLLBACK_COMPLETE y reintentar
aws cloudformation delete-stack --stack-name hcm-events-dev
aws cloudformation wait stack-delete-complete --stack-name hcm-events-dev
cd events && npx serverless deploy --config serverless-events.yml --stage dev
```

Nombres de stack: `hcm-auth-<stage>` (infraestructura), `hcm-events-<stage>`, `hcm-attendance-<stage>`, `hcm-recruitment-<stage>`, `hcm-performance-<stage>`.

---

## 9. Cómo bajar todo (teardown)

Orden inverso al despliegue. ⚠️ Las tablas DynamoDB **se borran con su stack, datos incluidos**: el seeding habría que repetirlo.

```bash
export LAB_ROLE_ARN=...                                  # también se necesita para remove

# 1. Attendance (importa recursos de hcm-events)
cd services/attendance && npx serverless remove --stage dev

# 2. Events (importa el topic de recruitment)
cd ../../events && npx serverless remove --config serverless-events.yml --stage dev

# 3. Performance y Recruitment (repo de la compañera)
cd ../reference/recruitment-performance/services/performance && npx serverless remove --stage dev
cd ../recruitment && npx serverless remove --stage dev
```

- Mientras `hcm-events-<stage>` exista, CloudFormation **no deja borrar ni renombrar** el export `hcm-recruitment-<stage>-topic-arn`, ni hacer `serverless remove` de recruitment. Si recruitment necesita cambiar ese export, primero hay que bajar `hcm-attendance` y `hcm-events`, y después volver a desplegarlos.
- Igualmente, `hcm-events` no se puede borrar mientras `hcm-attendance` (u otro stack de un compañero) importe sus exports. Listar quién importa un export:

  ```bash
  aws cloudformation list-imports --export-name hcm-events-dev-attendance-topic-arn
  ```

- Las tablas de RDS sembradas no se tocan aquí: son del stack de Core HR / Nóminas.
- `hcm-auth` se baja **después** de attendance: attendance tiene un `Lambda::Permission` sobre la función del authorizer. `${cf:}` no crea dependencia en CloudFormation, así que nada impide borrar hcm-auth antes, pero los endpoints de attendance quedarían con un authorizer inexistente.

---

## 10. Estado de verificación

### Probado (sin AWS)

- **Jest, `services/attendance`: 53 tests OK.**
  - Tenant, rol y `employeeId` desde `requestContext.authorizer` (context plano del Lambda authorizer). La ruta antigua (`claims["custom:tenant_id"]`) da 401.
  - Rechazo 403 cuando el tenant viene por body, header, query o path, sin llegar a DynamoDB ni SNS; 401 sin tenant; offline con `x-tenant-id`.
  - `EMPLOYEE` solo sobre su `employeeId` y sin aprobar; `HR`/`ADMIN` sí.
  - Paginación y `nextToken` de otro tenant; solapamiento de licencias vía GSI1; 409 y 503; `notification: "FAILED"` si SNS falla.
  - Parseo del envelope SNS→SQS.
  - Idempotencia con el cliente mockeado: estados `IN_PROGRESS`, `COMPLETED` y liberación de la clave.
  - Workers: duplicados, descartes, errores transitorios con `batchItemFailures`, `PermanentError`.
  - Los validadores coinciden con los JSON Schema.
- **`serverless print` y `serverless package`** de `hcm-events` y `hcm-attendance` (Serverless 3.40.0), con un `LAB_ROLE_ARN` falso y sin credenciales:
  - Las variables se resuelven y no se crea ningún rol IAM.
  - attendance, con `--param authorizerArn=<ARN falso>`: los 5 métodos son `CUSTOM` y referencian el único `AWS::ApiGateway::Authorizer` (`TOKEN`, TTL 0, URI = Lambda de hcm-auth) + `Lambda::Permission`. No hay Lambda authorizer propia ni Cognito. Sin el param, `print` intenta leer `${cf:hcm-auth-dev.AuthorizerArn}` (falla sin red, como se espera).
  - Las Event Source Mappings apuntan a `Fn::ImportValue` de las colas, e `IDEMPOTENCY_TABLE` y `SIMULATE_FAILURE` se resuelven.
- **`serverless offline`** con curl: 401, 403 y 400 correctos. Sin credenciales, las rutas que tocan DynamoDB dan 500, como era de esperar.
- **Seeding, pytest: 59 tests OK.**
  - Generadores: regex de IDs, claves iguales a las de los handlers, metas sin GSI1, conteos exactos.
  - Usuarios demo: su `employeeId` exacto en core_hr, payroll, attendance (marcaciones + licencia) y performance (metas, 8 evaluaciones, SUMMARY 2026-Q3/Q4); archivo inválido → código 3 sin escribir.
  - moto: `--dry-run`, `--sample`, `--verify` (incluida la tabla de usuarios y su `FALTAN`), idempotencia, no sobrescribe, reanudación, RDS caído sin afectar a DynamoDB, backoff.
  - PostgreSQL local temporal (incluye los `employee_id` no-UUID de los usuarios).
- **Seeding a escala completa** (DynamoDB simulado con moto): 10,000 × 3 tenants, `--verify` todo OK (también los 7 usuarios) y la segunda corrida sin escrituras.

### NO probado nunca

- **Ningún despliegue real** en AWS de `hcm-events` ni de `hcm-attendance`.
- **Permisos del LabRole**: que Lambda pueda asumirlo y que tenga acceso a DynamoDB, SNS, SQS (Event Source Mapping) y CloudWatch Logs.
- La resolución real de los `Fn::ImportValue` en CloudFormation.
- La entrega real SNS→SQS: QueuePolicy, **FilterPolicy** real, `RawMessageDelivery: false`.
- La **DLQ real** (3 recepciones y redrive con `start-message-move-task`).
- El **authorizer real de hcm-auth**: resolución de `${cf:hcm-auth-dev.AuthorizerArn}`, la invocación desde la API de attendance, el `context` real (`tenantId`, `role`, `employeeId`) y su política `Allow`.
- El **login real** y un JWT real (HS256) contra attendance; que los usuarios demo existan con los `employeeId` de `users.json`.
- El TTL real de la tabla de idempotencia.
- El seeding contra DynamoDB y RDS reales: rendimiento, throttling y esquema final de RDS.
- **SES**: mi parte no envía correos. Recruitment y performance sí (no lo verifiqué). Las metas sembradas no tienen recordatorios, para no disparar el cron de SES.
- Los stacks de recruitment y performance en Academy (requieren la migración de IAM, sección 3).

### TODOs abiertos

- **Nóminas**: implementar `applyUnpaidLeave` (`processLeaveEventWorker.js`), consumir `payroll-hr-sync`, publicar `payroll.processed`, definir formato de `periodId` y moneda, y la regla real de descuentos (en el seeding se usa 13%: `SEED_PAYROLL_DEDUCTION_RATE`).
- **Core HR**: implementar `createEmployeeFromCandidate` (`processCandidateHiredWorker.js`), publicar `employee.created`, definir formato de `employeeId`, la moneda y el esquema/migraciones finales. `scripts/seed_config.py` tiene las columnas marcadas `# TODO: ajustar al esquema final` (incluidos `CONTRACT_TYPES`).
- **Recruitment / Performance**: migrar IAM a `LabRole`.
- **Infraestructura**: confirmar que los usuarios demo están creados y fijar los `employeeId` definitivos (hoy provisionales); cualquier cambio va también a `scripts/users.json` y se vuelve a sembrar.
- **Core HR**: el DDL provisional (`--create-schema`) usa `employee_id VARCHAR(64)` para aceptar IDs como `emp-a-admin`. Si sus migraciones usan `UUID`, el seeding de los usuarios demo fallará en core_hr/payroll.
- Al mover un worker a su servicio definitivo, quitarlo de `services/attendance/serverless.yml` en el mismo despliegue.
- Limitaciones conocidas de attendance:
  - El chequeo de solapamiento de licencias no es atómico ante dos solicitudes simultáneas.
  - Si SNS falla al aprobar, no hay reintento automático (no hay outbox): queda el log `ERROR` y `notification: "FAILED"`.
- Limitaciones del seeding:
  - No sube archivos a S3 (los CV y certificados sembrados dan 404).
  - Las licencias `APPROVED` sembradas no publicaron `leave.approved`.
  - Los correos son `@…example.com`.
