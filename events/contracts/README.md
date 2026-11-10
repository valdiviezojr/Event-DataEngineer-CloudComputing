# Contratos de eventos HCM

Un JSON Schema (draft-07) por evento. `${stage}` = `dev` por defecto.

## Catálogo

| Evento | Topic SNS | Publica | Consume | Cola SQS (+ `-dlq`) |
|---|---|---|---|---|
| `employee.created` | `hcm-hr-${stage}-events` | ms-core-hr *(pendiente)* | ms-payroll *(pendiente)* | `hcm-events-${stage}-payroll-hr-sync` |
| `leave.approved` | `hcm-attendance-${stage}-events` | ms-attendance | ms-payroll (hoy: `processLeaveEventWorker` en attendance, con TODO) | `hcm-events-${stage}-payroll-attendance-sync` |
| `candidate.hired` | `hcm-recruitment-${stage}-events` | ms-recruitment | ms-core-hr (hoy: `processCandidateHiredWorker` en attendance, con TODO) | `hcm-events-${stage}-hr-recruitment-sync` |
| `evaluation.completed` | `hcm-performance-${stage}-events` | ms-performance | ms-performance (`notifyGoal`, correo) | `hcm-performance-${stage}-notify` *(cola propia de performance)* |
| `payroll.processed` | `hcm-payroll-${stage}-events` | ms-payroll *(pendiente)* | — | — |

Los topics de recruitment y performance los crean sus propios stacks. `hcm-events` solo importa el de recruitment (`Fn::ImportValue hcm-recruitment-${stage}-topic-arn`), porque es el único al que suscribe una cola; el de performance no se importa.

> ⚠️ Mientras exista el stack `hcm-events`, CloudFormation impide borrar o renombrar el export `hcm-recruitment-${stage}-topic-arn`. Si recruitment necesita cambiarlo (o hacer `serverless remove`), primero hay que bajar `hcm-events` (`npm run remove` en `events/`), y volver a desplegarlo después.

## Reglas comunes

**Publicación** (igual que `reference/`):

```js
new PublishCommand({
  TopicArn,
  Message: JSON.stringify({ eventType, ...payloadCamelCase }),
  MessageAttributes: {
    eventType: { DataType: "String", StringValue: eventType },
    tenantId:  { DataType: "String", StringValue: tenantId },
  },
});
```

- Las `FilterPolicy` filtran por el **MessageAttribute** `eventType`: si no se envía, el mensaje no llega a la cola.
- Eventos nuevos (`employee.created`, `leave.approved`, `payroll.processed`) llevan además `eventId` (UUID v4) y `occurredAt` (ISO 8601).
- `candidate.hired` y `evaluation.completed` **no** traen `eventId`.

**Entrega a SQS**: las suscripciones de `hcm-events` usan `RawMessageDelivery: false`, así que `record.body` es el envelope SNS:

```json
{
  "Type": "Notification",
  "MessageId": "6f0c2b8e-1f4a-5b3c-9d2e-7a1b2c3d4e5f",
  "TopicArn": "arn:aws:sns:us-east-1:123456789012:hcm-attendance-dev-events",
  "Message": "{\"eventType\":\"leave.approved\",\"eventId\":\"...\",...}",
  "Timestamp": "2026-11-09T15:00:00.000Z",
  "MessageAttributes": {
    "eventType": { "Type": "String", "Value": "leave.approved" },
    "tenantId":  { "Type": "String", "Value": "tenant_a" }
  }
}
```

**Idempotencia de consumidores**: `eventKey = "<consumidor>#" + (eventId ?? envelope.MessageId)`, guardado con `PutItem` condicional en `hcm-events-idempotency-${stage}` (TTL 7 días en `expiresAt`). Si ya está `COMPLETED`, el mensaje se omite. El prefijo del consumidor es obligatorio si se comparte la tabla, porque SNS repite el mismo `MessageId` en cada suscripción del fan-out. Implementación de referencia: `services/attendance/lib/idempotency.js`.

**Reintentos**: 3 recepciones (`maxReceiveCount`) y luego DLQ (retención 14 días). Mensajes no-JSON o que no cumplen el schema se descartan sin reintentar (se loguean).

## Ejemplos

### `employee.created`

```json
{
  "eventType": "employee.created",
  "eventId": "0b8f4a52-6d1e-4c1b-9a0e-3f2d5c7e8a91",
  "occurredAt": "2026-11-09T14:03:12.511Z",
  "tenantId": "tenant_a",
  "employeeId": "emp-102",
  "email": "carlos.ruiz@empresa.com",
  "salary": 4500,
  "hireDate": "2026-11-15"
}
```

### `leave.approved`

```json
{
  "eventType": "leave.approved",
  "eventId": "4c2a8e19-0d7b-4f3a-b1c6-2e9d8f7a6b54",
  "occurredAt": "2026-11-09T15:00:00.000Z",
  "tenantId": "tenant_a",
  "leaveId": "l-9a3f1c2e-7b4d-4e8a-a6f0-1d2c3b4a5e6f",
  "employeeId": "emp-102",
  "daysUnpaid": 3,
  "startDate": "2026-11-18",
  "endDate": "2026-11-20",
  "leaveType": "UNPAID",
  "totalDays": 3
}
```

**Regla de `daysUnpaid`** (la calcula ms-attendance al aprobar):

- Días **calendario inclusivos**: `totalDays = endDate − startDate + 1` (18 → 20 de noviembre = 3 días).
- `UNPAID` y `OTHER` → `daysUnpaid = totalDays`.
- `VACATION` y `SICK` → `daysUnpaid = 0`.
- `leaveId` tiene formato `l-<uuid v4>`. `leaveType` y `totalDays` son opcionales en el contrato (informativos); el consumidor solo debe depender de los campos obligatorios.

### `payroll.processed`

```json
{
  "eventType": "payroll.processed",
  "eventId": "e7d1b3a9-5c2f-4a8e-9b6d-0f1e2d3c4b5a",
  "occurredAt": "2026-11-30T23:10:00.000Z",
  "tenantId": "tenant_b",
  "periodId": "2026-11",
  "totalPaid": 1284530.75
}
```

### `candidate.hired` (payload real de `updateStage.js`)

```json
{
  "eventType": "candidate.hired",
  "tenantId": "tenant_a",
  "candidateId": "c-3f6b2a10-8c4d-4e9f-a1b2-c3d4e5f6a7b8",
  "vacancyId": "v-1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "vacancyTitle": "Electricista Industrial",
  "fullName": "María García",
  "email": "maria@gmail.com",
  "fromStage": "OFFER",
  "toStage": "HIRED",
  "note": "Inicia el 1 de diciembre",
  "changedBy": "reclutador@empresa.com",
  "changedAt": "2026-11-09T16:20:41.002Z"
}
```

### `evaluation.completed` (payload real de `submitEvaluation.js`)

```json
{
  "eventType": "evaluation.completed",
  "tenantId": "tenant_c",
  "evalId": "e-5d4c3b2a-1f0e-4d9c-8b7a-6f5e4d3c2b1a",
  "employeeId": "emp-102",
  "employeeName": "Carlos Ruiz",
  "employeeEmail": "carlos@empresa.com",
  "evaluatorName": "Lucía Torres",
  "relationship": "MANAGER",
  "relationshipLabel": "Jefe directo",
  "cycle": "2026-Q4",
  "score": 4.75,
  "strengths": "Liderazgo técnico",
  "improvements": "Documentar mejor",
  "anonymous": false,
  "notifyEmployee": true,
  "createdAt": "2026-11-09T17:45:00.000Z"
}
```

## Notas para otros integrantes

- **ms-core-hr**: publicar `employee.created` en `hcm-hr-${stage}-events` (export `hcm-events-${stage}-hr-topic-arn`) con el MessageAttribute `eventType`.
- **ms-payroll**: publicar `payroll.processed` en `hcm-payroll-${stage}-events` (export `hcm-events-${stage}-payroll-topic-arn`). Para consumir `employee.created` usar la cola `payroll-hr-sync` (export `hcm-events-${stage}-payroll-hr-sync-queue-arn`).
- Una cola debe tener **un solo** consumidor Lambda. Cuando ms-payroll/ms-core-hr tomen `payroll-attendance-sync` o `hr-recruitment-sync`, hay que quitar el worker correspondiente de `services/attendance/serverless.yml` en el mismo despliegue.
- Los payloads del documento de diseño estaban en snake_case (`tenant_id`, `days_unpaid`…); estos contratos usan **camelCase**, igual que los eventos reales de recruitment/performance.
