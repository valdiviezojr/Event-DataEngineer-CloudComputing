# HCM SaaS — Eventos, Asistencia y Seeding

Parte del **Event & Data Engineer** del SaaS HCM multi-tenant (CS2032, UTEC). Tenants: `tenant_a`, `tenant_b`, `tenant_c`.

```
events/                    Stack hcm-events: topics SNS, colas SQS + DLQ, tabla de idempotencia
  serverless-events.yml
  contracts/               JSON Schema por evento + README con catálogo y ejemplos
services/attendance/       ms-attendance (DynamoDB) + workers SQS
scripts/                   Seeding masivo: 10,000 por tenant y microservicio (ver scripts/README.md)
reference/                 Código de recruitment/performance (compañera, solo lectura)
```

Stack: Node.js 20 · Serverless Framework v3 · API Gateway (REST) · Lambda · DynamoDB · SNS · SQS (+DLQ).

---

## Despliegue en AWS Academy Learner Lab

### 1. Credenciales

En el Learner Lab: **Start Lab → AWS Details → AWS CLI → Show**. Copiar a `.env` (desde `.env.example`):

```bash
cp .env.example .env      # completar las 3 credenciales y LAB_ROLE_ARN
set -a && source .env && set +a
aws sts get-caller-identity          # verificar
aws iam get-role --role-name LabRole --query Role.Arn --output text   # => LAB_ROLE_ARN
```

Las credenciales caducan al cerrar la sesión del lab (~4 h): hay que recargarlas cada vez.

### 2. Restricción de IAM

En el Learner Lab **no se pueden crear roles IAM**. Por eso todos los `serverless.yml` de esta carpeta usan:

```yaml
provider:
  iam:
    role: ${env:LAB_ROLE_ARN}
```

y **no** usan `serverless-iam-roles-per-function` ni `iamRoleStatements`.

> ⚠️ **Para recruitment y performance (`reference/`)**: sus `serverless.yml` usan `serverless-iam-roles-per-function` + `iamRoleStatements` por función, lo que crea un rol IAM por Lambda y **falla en Academy**. Para desplegar allí deben: quitar el plugin, borrar los bloques `iamRoleStatements` y añadir `provider.iam.role: ${env:LAB_ROLE_ARN}`.

### 3. Orden de despliegue

```
1. hcm-recruitment, hcm-performance   (reference/, tras la migración de IAM)
2. hcm-events                         (importa hcm-recruitment-${stage}-topic-arn)
3. hcm-attendance                     (importa el topic y las colas de hcm-events)
```

```bash
cd events && npm install && npm run deploy                 # = serverless deploy --config serverless-events.yml
cd ../services/attendance && npm install && npx serverless deploy
# con Cognito (cuando exista el User Pool):
npx serverless deploy --param="cognitoUserPoolArn=arn:aws:cognito-idp:us-east-1:<acct>:userpool/<poolId>"
```

Stage distinto de `dev`: añadir `--stage <stage>` a **todos** los comandos (los nombres e imports dependen del stage).

> ⚠️ Mientras `hcm-events` exista, recruitment **no puede borrar ni renombrar** su export `hcm-recruitment-${stage}-topic-arn` (ni hacer `serverless remove`). Bajar primero `hcm-events` (`cd events && npm run remove`).

### Authorizer (Cognito)

Param opcional `cognitoUserPoolArn`:

- **Sin param**: endpoints sin authorizer (igual que hoy en `reference/`). Solo para pruebas.
- **Con param**: todos los endpoints de attendance usan un authorizer `COGNITO_USER_POOLS` y el tenant sale del claim `custom:tenant_id`.

---

## ms-attendance

Tabla `ms-attendance-table-${stage}` (PAY_PER_REQUEST, GSI1, PITR).

| Entidad | PK | SK | GSI1PK | GSI1SK |
|---|---|---|---|---|
| Marcación | `TENANT#<t>` | `ATTENDANCE#<employeeId>#<YYYY-MM-DD>` | — | — |
| Licencia | `TENANT#<t>` | `LEAVE#<leaveId>` | `TENANT#<t>#EMPLOYEE#<employeeId>` | `LEAVE#<startDate>#<leaveId>` |

Todos los ítems llevan `entityType` (`ATTENDANCE` | `LEAVE`) y `tenantId`. Acceso siempre vía `createTenantDb` (copiado sin cambios de `reference/`); nunca scan.

### Endpoints

| Método | Ruta | Body / query | Respuestas |
|---|---|---|---|
| POST | `/attendance/clock-in` | `{ employeeId, timestamp? }` | 201 · 409 si ya marcó entrada ese día |
| POST | `/attendance/clock-out` | `{ employeeId, timestamp?, date? }` | 200 · 404 sin entrada · 409 ya salió |
| POST | `/leaves/request` | `{ employeeId, type, startDate, endDate, reason? }` | 201 (`PENDING`) · 409 si se cruza |
| POST | `/leaves/{leaveId}/approve` | `{ note? }` | 200 + `notification` · 404 · 409 si no está `PENDING` |
| GET | `/attendance` | `employeeId` (oblig.), `from`, `to`, `limit` (1–100, def. 20), `nextToken` | 200 `{ items, count, nextToken }` |

Reglas:

- `timestamp` (ISO 8601) es opcional; por defecto ahora. No puede estar más de 5 min en el futuro. El día de la marcación es la **fecha local** (UTC−5, `TZ_OFFSET_HOURS`).
- `clock-out` acepta `date` opcional para cerrar un turno nocturno iniciado el día anterior. Calcula `workedMinutes`.
- `type`: `VACATION | SICK | UNPAID | OTHER`. `endDate >= startDate`, máx. 365 días. Salvo `SICK`, `startDate` debe ser hoy o futura. Solapamiento con licencias `PENDING`/`APPROVED` del mismo empleado → 409 (consulta por GSI1).
- Aprobar calcula `daysUnpaid` (días calendario inclusivos; `UNPAID`/`OTHER` = todos, `VACATION`/`SICK` = 0) y publica `leave.approved` en `hcm-attendance-${stage}-events`. Si SNS falla tras guardar, se loguea `ERROR` y se responde `notification: "FAILED"` (`QUEUED` si se publicó, `SKIPPED` si no hay topic, p. ej. en offline).
- Rol (claims opcionales, como en performance): `custom:role = EMPLOYEE` solo puede operar sobre su `custom:employee_id` y no puede aprobar.
- Tenant: siempre del claim. Si body/path/query/header traen otro tenant → **403 `{ message: "Acceso denegado", requestId }`**.

Errores: `{ message, requestId }` — 400 validación, 401 sin tenant, 403 tenant ajeno/rol, 404, 409 conflicto, 503 throttling DynamoDB, 500 resto.

### Probar en local (serverless offline)

En local no hay Cognito: el tenant va en `x-tenant-id` (solo válido con `IS_OFFLINE`, que pone serverless-offline). Usa DynamoDB real de AWS, así que hacen falta las credenciales del lab y la tabla desplegada.

```bash
cd services/attendance
set -a && source ../../.env && set +a
npx serverless offline

B=http://localhost:3000/dev
curl -X POST $B/attendance/clock-in  -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' -d '{"employeeId":"emp-102"}'
curl -X POST $B/attendance/clock-out -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' -d '{"employeeId":"emp-102"}'
curl "$B/attendance?employeeId=emp-102&from=2026-11-01&to=2026-11-30&limit=10" -H 'x-tenant-id: tenant_a'
curl -X POST $B/leaves/request -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' \
  -d '{"employeeId":"emp-102","type":"UNPAID","startDate":"2026-12-01","endDate":"2026-12-03","reason":"Trámite personal"}'
curl -X POST $B/leaves/<leaveId>/approve -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' -d '{"note":"OK"}'

# 403: tenant del body distinto al del header
curl -X POST $B/attendance/clock-in -H 'x-tenant-id: tenant_a' -H 'content-type: application/json' -d '{"employeeId":"emp-102","tenantId":"tenant_b"}'
```

En offline el `!ImportValue` del topic no se resuelve, así que `approve` responde `notification: "SKIPPED"`.

### Probar en AWS (JWT)

```bash
B=https://<api-id>.execute-api.us-east-1.amazonaws.com/dev
TOKEN=<idToken de Cognito con custom:tenant_id>
curl -X POST $B/attendance/clock-in -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"employeeId":"emp-102"}'
curl "$B/attendance?employeeId=emp-102" -H "Authorization: Bearer $TOKEN"
```

Si además se envía `x-tenant-id` y no coincide con el token → 403.

### Tests

```bash
cd services/attendance && npm test
```

---

## Workers SQS

Viven en `services/attendance` de forma **temporal**, hasta que ms-payroll y ms-core-hr tengan su propio consumidor. Cada uno tiene un `TODO` con la interfaz a implementar.

| Worker | Cola (import) | Evento | Dueño final |
|---|---|---|---|
| `processLeaveEventWorker` | `hcm-events-${stage}-payroll-attendance-sync-queue-arn` | `leave.approved` | ms-payroll → `applyUnpaidLeave(...)` |
| `processCandidateHiredWorker` | `hcm-events-${stage}-hr-recruitment-sync-queue-arn` | `candidate.hired` | ms-core-hr → `createEmployeeFromCandidate(...)` |

Configuración: `batchSize: 10`, `functionResponseType: ReportBatchItemFailures`, `timeout: 30`. `IDEMPOTENCY_TABLE` se importa de `hcm-events-${stage}-idempotency-table-name`.

> Una cola debe tener **un solo** consumidor. Al mover un worker a su servicio definitivo, borrar la función de `services/attendance/serverless.yml` en el mismo despliegue.

Qué pasa con cada mensaje (`lib/sqsWorker.js`):

| Caso | Resultado |
|---|---|
| `record.body` o `Message` no es JSON, o no cumple el contrato | log `ERROR` y **se descarta** (sin reintento) |
| `eventType` inesperado o `tenantId` del atributo SNS ≠ payload | log y se descarta |
| Duplicado (clave ya `COMPLETED`) | log `INFO` y se omite |
| Otra invocación lo está procesando | `batchItemFailure` (se reintenta) |
| Handler lanza `PermanentError` | log `ERROR` y se descarta |
| Cualquier otro error (RDS/DynamoDB caído…) | `batchItemFailure` → tras 3 recepciones va a la **DLQ** |

**Idempotencia** (`lib/idempotency.js`, tabla `hcm-events-idempotency-${stage}`):

- `eventKey = "<consumidor>#" + (eventId ?? MessageId del envelope SNS)`. El prefijo existe porque SNS repite el mismo `MessageId` en todas las suscripciones de un fan-out, y sin él dos consumidores del mismo evento se pisarían.
- Antes de procesar se hace un `PutItem` condicional (`status = IN_PROGRESS`, lease de 120 s, `expiresAt` = TTL de 7 días). Si sale bien pasa a `COMPLETED`; si falla se borra la clave para que el reintento pueda procesarlo. Si la Lambda muere sin liberar la clave, el lease vence antes del siguiente reintento (la visibilidad es de 180 s).

Logs JSON con `tenantId`, `eventType`, `messageId` (SQS), `snsMessageId`, `eventKey` y `requestId`. En CloudWatch Logs Insights:

```
fields @timestamp, level, msg, tenantId, eventType, messageId, eventKey
| filter fn = "processLeaveEventWorker"
| sort @timestamp desc
```

### Simular un fallo y ver el mensaje en la DLQ

1. Redesplegar attendance con los workers fallando a propósito:

   ```bash
   cd services/attendance
   npx serverless deploy --param="simulateFailure=true"     # (+ cognitoUserPoolArn si aplica)
   ```

2. Publicar un `leave.approved` válido en el topic (o aprobar una licencia con `POST /leaves/{id}/approve`):

   ```bash
   TOPIC=$(aws cloudformation list-exports --query "Exports[?Name=='hcm-events-dev-attendance-topic-arn'].Value" --output text)
   aws sns publish --topic-arn "$TOPIC" \
     --message '{"eventType":"leave.approved","eventId":"'"$(uuidgen | tr A-Z a-z)"'","occurredAt":"2026-11-09T15:00:00.000Z","tenantId":"tenant_a","leaveId":"l-9a3f1c2e-7b4d-4e8a-a6f0-1d2c3b4a5e6f","employeeId":"emp-102","daysUnpaid":3,"startDate":"2026-11-18","endDate":"2026-11-20"}' \
     --message-attributes '{"eventType":{"DataType":"String","StringValue":"leave.approved"},"tenantId":{"DataType":"String","StringValue":"tenant_a"}}'
   ```

   Sin el atributo `eventType`, la FilterPolicy descarta el mensaje y nunca llega a la cola.

3. Esperar unos 10 min: son 3 recepciones con 180 s de visibilidad entre cada una. En los logs aparece `"Error transitorio procesando evento, se reintentará"` con `approximateReceiveCount` 1, 2 y 3. Después:

   ```bash
   DLQ=$(aws cloudformation list-exports --query "Exports[?Name=='hcm-events-dev-payroll-attendance-sync-dlq-url'].Value" --output text)
   aws sqs get-queue-attributes --queue-url "$DLQ" --attribute-names ApproximateNumberOfMessages
   aws sqs receive-message --queue-url "$DLQ" --max-number-of-messages 1    # body = envelope SNS original
   ```

4. Volver a la normalidad y reprocesar:

   ```bash
   npx serverless deploy        # simulateFailure vuelve a 'false'
   # el stack solo exporta la URL de la DLQ; el ARN se obtiene así:
   DLQ_ARN=$(aws sqs get-queue-attributes --queue-url "$DLQ" --attribute-names QueueArn --query Attributes.QueueArn --output text)
   aws sqs start-message-move-task --source-arn "$DLQ_ARN"     # redrive a la cola original
   ```

   Como la clave se libera en cada fallo, el mensaje redirigido se procesa normalmente.

Un mensaje **inválido** (por ejemplo `"daysUnpaid": -1`) **no** llega a la DLQ: se descarta en el primer intento, y eso queda en el log `"Payload inválido según contrato, se descarta"`.

---

## Seeding (30,000 registros por microservicio)

```bash
cd scripts && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
set -a && source ../.env && set +a       # credenciales del Learner Lab + DB_* del RDS
python seed_master.py --dry-run          # revisar conteos sin tocar nada
python seed_master.py --sample           # prueba: 100 por tenant
python seed_master.py                    # carga completa (idempotente: se puede relanzar)
python seed_master.py --verify           # tabla por tenant / servicio / entidad
```

Ejecutarlo **después** de desplegar recruitment, performance y attendance (las tablas deben existir). Si el RDS aún no está, core_hr y payroll fallan con un mensaje claro y el resto se siembra igual. Detalles, decisiones y limitaciones en [`scripts/README.md`](scripts/README.md).

---

## Nombres para el resto del equipo

`${stage}` = `dev` por defecto.

| Recurso | Nombre | Export CloudFormation |
|---|---|---|
| Topic Core HR | `hcm-hr-${stage}-events` | `hcm-events-${stage}-hr-topic-arn` |
| Topic Asistencia | `hcm-attendance-${stage}-events` | `hcm-events-${stage}-attendance-topic-arn` |
| Topic Nóminas | `hcm-payroll-${stage}-events` | `hcm-events-${stage}-payroll-topic-arn` |
| Topic Reclutamiento *(de recruitment)* | `hcm-recruitment-${stage}-events` | `hcm-recruitment-${stage}-topic-arn` |
| Cola `employee.created` → Nóminas | `hcm-events-${stage}-payroll-hr-sync` | `hcm-events-${stage}-payroll-hr-sync-queue-arn` |
| Cola `leave.approved` → Nóminas | `hcm-events-${stage}-payroll-attendance-sync` | `hcm-events-${stage}-payroll-attendance-sync-queue-arn` |
| Cola `candidate.hired` → Core HR | `hcm-events-${stage}-hr-recruitment-sync` | `hcm-events-${stage}-hr-recruitment-sync-queue-arn` |
| DLQs | `<cola>-dlq` | `hcm-events-${stage}-<cola>-dlq-url` (URL) |
| Tabla idempotencia | `hcm-events-idempotency-${stage}` | `hcm-events-${stage}-idempotency-table-name` |
| Tabla asistencia | `ms-attendance-table-${stage}` | `hcm-attendance-${stage}-table-name` |

Uso desde otro `serverless.yml`:

```yaml
environment:
  HR_TOPIC_ARN: !ImportValue hcm-events-${sls:stage}-hr-topic-arn
functions:
  worker:
    events:
      - sqs:
          arn: !ImportValue hcm-events-${sls:stage}-payroll-hr-sync-queue-arn
          batchSize: 10
          functionResponseType: ReportBatchItemFailures
```

Catálogo de eventos y payloads: [`events/contracts/README.md`](events/contracts/README.md).
