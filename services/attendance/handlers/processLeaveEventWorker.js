// Consume hcm-events-${stage}-payroll-attendance-sync (leave.approved).
// Vive en ms-attendance hasta que exista ms-payroll; ver TODO abajo.
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createIdempotency } = require("../lib/idempotency");
const { createSqsWorker } = require("../lib/sqsWorker");
const { validateLeaveApproved } = require("../lib/validators");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });

/*
 * TODO(ms-payroll): implementar y conectar aquí el descuento de días no pagados.
 *
 *   applyUnpaidLeave({ tenantId, employeeId, leaveId, daysUnpaid, startDate, endDate }) => Promise<void>
 *
 * - Debe ser idempotente por (tenantId, leaveId): p. ej. UNIQUE(leave_id) en la tabla de descuentos del
 *   schema del tenant + INSERT ... ON CONFLICT DO NOTHING. La tabla de idempotencia evita la mayoría de
 *   duplicados, pero no cubre un fallo entre el INSERT y complete().
 * - Lanzar PermanentError (lib/sqsWorker) si el empleado no existe en el tenant → se descarta sin reintentar.
 * - Cualquier otro error (RDS caído, timeout) se relanza → reintento SQS → DLQ al 3er intento.
 * - Cuando el worker se mueva a ms-payroll, quitar esta función de services/attendance/serverless.yml en el
 *   mismo despliegue: una cola debe tener un solo consumidor.
 */
const applyUnpaidLeave = async (input, { log, ...ctx }) => {
  log("INFO", "leave.approved recibido (pendiente integración con ms-payroll)", { ...ctx, ...input });
};

const handle = async (msg, ctx) => {
  if (process.env.SIMULATE_FAILURE === "true") throw new Error("Fallo simulado (SIMULATE_FAILURE=true)");

  if (msg.daysUnpaid === 0) {
    ctx.log("INFO", "Licencia pagada (daysUnpaid = 0), no hay descuento", { ...ctx, leaveId: msg.leaveId, employeeId: msg.employeeId });
    return;
  }

  const { tenantId, employeeId, leaveId, daysUnpaid, startDate, endDate } = msg;
  await applyUnpaidLeave({ tenantId, employeeId, leaveId, daysUnpaid, startDate, endDate }, ctx);
};

module.exports.main = createSqsWorker({
  fn: "processLeaveEventWorker",
  eventType: "leave.approved",
  validate: validateLeaveApproved,
  handle,
  idempotency: createIdempotency({ client: ddb, table: process.env.IDEMPOTENCY_TABLE, consumer: "payroll-attendance-sync" }),
});
