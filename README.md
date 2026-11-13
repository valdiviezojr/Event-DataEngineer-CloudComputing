# HCM SaaS — Eventos, Asistencia y Seeding

Parte del **Event & Data Engineer** del SaaS HCM multi-tenant (CS2032, UTEC). Tenants: `tenant_a`, `tenant_b`, `tenant_c` (los de los usuarios demo de `hcm-auth`, en [`scripts/users.json`](scripts/users.json)).

```
events/                    Stack hcm-events: topics SNS, colas SQS + DLQ, tabla de idempotencia
  serverless-events.yml
  contracts/               JSON Schema por evento + README con catálogo y ejemplos
services/attendance/       ms-attendance (DynamoDB) + workers SQS
scripts/                   Seeding masivo: 10,000 por tenant y microservicio (ver scripts/README.md)
  users.json               Usuarios demo de hcm-auth (tenantId + employeeId) que usa el seeding
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

| # | Stack | Directorio | Comando (stage `dev`) | Debe existir al terminar |
|---|---|---|---|---|
| 1 | `hcm-auth-dev` | repo de infraestructura (`~/hcm-auth`) | deploy según su README; usuarios: `USERS_TABLE=hcm-auth-users-dev npm run seed:users` | output **`AuthorizerArn`** (export `hcm-auth-dev-AuthorizerArn`) |
| 2 | `hcm-recruitment-dev`, `hcm-performance-dev` | `reference/recruitment-performance/services/recruitment` y `…/performance` (tras migrar IAM) | `npx serverless deploy --stage dev --param="senderEmail=<correo-SES>"` (+ `--param="storageBucket=hcm-app-storage"` en recruitment) | export **`hcm-recruitment-dev-topic-arn`**; tablas `ms-recruitment-table-dev`, `ms-performance-table-dev` |
| 3 | `hcm-events-dev` | `events/` | `npx serverless deploy --config serverless-events.yml --stage dev` | 10 exports **`hcm-events-dev-*`** (topics, colas, DLQ, `idempotency-table-name`) |
| 4 | `hcm-attendance-dev` | `services/attendance/` | `npx serverless deploy --stage dev` | export **`hcm-attendance-dev-table-name`** y los 5 endpoints |
| 5 | seeding | `scripts/` | `python seed_master.py` y luego `python seed_master.py --verify` | `--verify` todo `OK` (código 0), incluida la tabla de usuarios demo |

Todos los `serverless deploy` requieren `LAB_ROLE_ARN` exportada. Para otro stage, cambiar `dev` en **todos** los pasos.

Detalle de cada paso y verificaciones: [`DEPLOY.md`, sección 4](DEPLOY.md#4-orden-de-despliegue).

> ⚠️ Mientras `hcm-events` exista, recruitment **no puede borrar ni renombrar** su export `hcm-recruitment-${stage}-topic-arn` (ni hacer `serverless remove`). Bajar primero `hcm-events` (`cd events && npm run remove`).

### Authorizer (hcm-auth)

Los 5 endpoints usan el **Lambda Authorizer TOKEN** del stack `hcm-auth-${stage}` (integrante de infraestructura). Este stack no crea otra Lambda authorizer: la referencia por ARN.

```yaml
custom:
  authorizerArn: ${param:authorizerArn, cf:hcm-auth-${sls:stage}.AuthorizerArn}
  authorizer:
    arn: ${self:custom.authorizerArn}
    type: token
    resultTtlInSeconds: 0
```

- Se usa `${cf:hcm-auth-<stage>.AuthorizerArn}` (output del stack; export `hcm-auth-<stage>-AuthorizerArn`) y **no** `!ImportValue`, porque Serverless v3 necesita `authorizer.arn` como string. `${cf:}` se resuelve al empaquetar, así que `hcm-auth` debe estar desplegado antes y hacen falta credenciales.
- En una REST API la configuración del authorizer es por API: CloudFormation crea en este stack un `AWS::ApiGateway::Authorizer` (que apunta a la Lambda de hcm-auth) y un `AWS::Lambda::Permission` para que API Gateway la invoque. No se crea ninguna Lambda nueva.
- El param `authorizerArn` solo sirve para `serverless print/package/offline` sin AWS (ver Tests). En el deploy no se pasa.
- Identidad en la Lambda: `event.requestContext.authorizer.{tenantId, role, employeeId, userId, email}` (context plano, sin `custom:` ni `claims`). Solo `lib/http.js` (`getAuthContext`/`getTenantId`) conoce esa ruta.

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
- Rol (del authorizer): `role = EMPLOYEE` solo puede operar sobre su propio `employeeId` y no puede aprobar. `ADMIN` y `HR` operan sobre cualquier empleado del tenant.
- Tenant: siempre de `requestContext.authorizer.tenantId`. Si body/path/query/header traen otro tenant → **403 `{ message: "Acceso denegado", requestId }`**.
- `lib/dynamoTenantFilter.js` sigue siendo copia exacta de `reference/`. Su `tenantFromEvent` lee la ruta antigua (`claims["custom:tenant_id"]`), pero attendance no lo usa: el tenant se resuelve solo en `lib/http.js`. `assertRequestTenant` no depende del authorizer (compara body/path/query/header con el tenant ya resuelto).

Errores: `{ message, requestId }` — 400 validación, 401 sin tenant, 403 tenant ajeno/rol, 404, 409 conflicto, 503 throttling DynamoDB, 500 resto.

### Probar en local (serverless offline)

serverless-offline **no ejecuta authorizers por ARN** (avisa *does not support non local authorizers* y deja pasar): el tenant va en `x-tenant-id` (solo válido con `IS_OFFLINE`, que pone serverless-offline). Usa DynamoDB real de AWS, así que hacen falta las credenciales del lab y la tabla desplegada.

```bash
cd services/attendance
set -a && source ../../.env && set +a
npx serverless offline          # con hcm-auth desplegado; si no: --param="authorizerArn=arn:aws:lambda:us-east-1:000000000000:function:x"

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

### Probar en AWS (JWT de hcm-auth)

**1. Token.** Login HTTP del stack `hcm-auth` (no Cognito). Usuarios demo en `scripts/users.json`; la contraseña de los usuarios demo la define hcm-auth (pedirla a infraestructura; no se guarda en este repo). Los usuarios existen solo si se crearon con `USERS_TABLE=hcm-auth-users-dev npm run seed:users` en su repo. JWT HS256, válido 8 h.

```bash
AUTH_API=https://0kcyrpixu6.execute-api.us-east-1.amazonaws.com/dev    # API de hcm-auth (en .env.example)
login() { curl -s -X POST "$AUTH_API/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"${2:-<contraseña-demo>}\"}" | jq -r .token; }

TA=$(login hr@empresa-a.com)          # HR de tenant_a  (employeeId emp-a-hr)
TE=$(login empleado@empresa-a.com)    # EMPLOYEE de tenant_a (emp-a-001)
TB=$(login hr@empresa-b.com)          # HR de tenant_b
echo "$TA" | cut -d. -f2 | base64 -d 2>/dev/null; echo    # ver tenantId/role/employeeId del payload
```

La respuesta del login trae `token`, `expiresIn` y `user`. A attendance se le envía `Authorization: Bearer <token>`.

**2. Los 5 endpoints** (`API` = URL base que imprime `serverless deploy` de attendance):

```bash
API=https://<api-id>.execute-api.us-east-1.amazonaws.com/dev
A=(-H "Authorization: Bearer $TA" -H 'content-type: application/json')

curl -s -X POST $API/attendance/clock-in  "${A[@]}" -d '{"employeeId":"emp-a-001"}'                           # 201 (409 si ya marcó hoy)
curl -s -X POST $API/attendance/clock-out "${A[@]}" -d '{"employeeId":"emp-a-001"}'                           # 200
curl -s "$API/attendance?employeeId=emp-a-001&limit=5" -H "Authorization: Bearer $TA" | jq '.count,.nextToken'  # sembrados + hoy
S=$(date -d '+40 days' +%F); E=$(date -d '+42 days' +%F)                                                     # macOS: date -v+40d +%F
LEAVE=$(curl -s -X POST $API/leaves/request "${A[@]}" -d '{"employeeId":"emp-a-001","type":"UNPAID","startDate":"'$S'","endDate":"'$E'"}' | jq -r .leave.leaveId)
curl -s -X POST $API/leaves/$LEAVE/approve "${A[@]}" -d '{"note":"OK"}' | jq '.leave.status,.notification'    # "APPROVED", "QUEUED"
```

Rol `EMPLOYEE` (`$TE`): `clock-in` con su propio `emp-a-001` → 201; con `emp-a-hr` → 403 `"Solo puedes operar sobre tus propios registros"`; `approve` → 403.

Sin token o con token inválido → **401 de API Gateway** (no llega a la Lambda).

**3. Aislamiento** (token de `tenant_b` contra datos de `tenant_a`):

| Caso | Comando | Esperado |
|---|---|---|
| tenant_b lista a un empleado de tenant_a | `curl -s "$API/attendance?employeeId=emp-a-001" -H "Authorization: Bearer $TB" \| jq .count` | `0` (otra partición) |
| tenant_b aprueba una licencia de tenant_a | `curl -s -X POST $API/leaves/$LEAVE/approve -H "Authorization: Bearer $TB" -H 'content-type: application/json' -d '{}'` | 404 `"Licencia no encontrada"` |
| token de tenant_b + `tenantId: tenant_a` en el body | `curl -s -X POST $API/attendance/clock-in -H "Authorization: Bearer $TB" -H 'content-type: application/json' -d '{"employeeId":"emp-b-001","tenantId":"tenant_a"}'` | 403 `{"message":"Acceso denegado",…}` |
| token de tenant_b + header `x-tenant-id: tenant_a` | `curl -s "$API/attendance?employeeId=emp-b-001" -H "Authorization: Bearer $TB" -H 'x-tenant-id: tenant_a'` | 403 |

### Tests

```bash
cd services/attendance && npm test
# Validar la plantilla sin AWS (no resuelve ${cf:}): ARN y rol falsos
LAB_ROLE_ARN=arn:aws:iam::000000000000:role/LabRole npx serverless package --stage dev \
  --param="authorizerArn=arn:aws:lambda:us-east-1:000000000000:function:hcm-auth-dev-authorizer"
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
   npx serverless deploy --param="simulateFailure=true"
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

Ejecutarlo **después** de desplegar recruitment, performance y attendance (las tablas deben existir). Tenants y `employeeId` de los usuarios demo salen de [`scripts/users.json`](scripts/users.json) (`SEED_USERS_FILE`): esos usuarios reciben marcaciones, licencias, metas y evaluaciones con SUMMARY en 2026-Q3 y 2026-Q4, así que al iniciar sesión ven datos. Si se cambia un `employeeId` en hcm-auth, hay que cambiarlo también en `users.json` y volver a sembrar. Si el RDS aún no está, core_hr y payroll fallan con un mensaje claro y el resto se siembra igual. Detalles, decisiones y limitaciones en [`scripts/README.md`](scripts/README.md).

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
| Authorizer *(de hcm-auth)* | `hcm-auth-${stage}-authorizer` (Lambda) | `hcm-auth-${stage}-AuthorizerArn` (output `AuthorizerArn`) |

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
