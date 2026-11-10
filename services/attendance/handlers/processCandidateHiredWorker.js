// Consume hcm-events-${stage}-hr-recruitment-sync (candidate.hired, publicado por ms-recruitment).
// Vive en ms-attendance hasta que exista ms-core-hr; ver TODO abajo.
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createIdempotency } = require("../lib/idempotency");
const { createSqsWorker } = require("../lib/sqsWorker");
const { validateCandidateHired } = require("../lib/validators");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });

/*
 * TODO(ms-core-hr): implementar y conectar aquí el alta del empleado.
 *
 *   createEmployeeFromCandidate({ tenantId, candidateId, fullName, email, vacancyId, vacancyTitle, hiredAt })
 *     => Promise<{ employeeId }>
 *
 * - candidate.hired NO trae eventId: la idempotencia usa el MessageId del envelope SNS. Además debe ser
 *   idempotente por (tenantId, candidateId): p. ej. columna source_candidate_id UNIQUE en employees +
 *   ON CONFLICT DO NOTHING.
 * - El evento no trae salario, departamento ni fecha de ingreso: decidir defaults o dejar el empleado en
 *   estado PENDING_ONBOARDING.
 * - Al crear el empleado, ms-core-hr debe publicar employee.created (contrato en events/contracts).
 * - Lanzar PermanentError (lib/sqsWorker) para datos imposibles de procesar; otros errores se reintentan.
 * - Cuando el worker se mueva a ms-core-hr, quitar esta función de services/attendance/serverless.yml en el
 *   mismo despliegue: una cola debe tener un solo consumidor.
 */
const createEmployeeFromCandidate = async (input, { log, ...ctx }) => {
  log("INFO", "candidate.hired recibido (pendiente integración con ms-core-hr)", { ...ctx, ...input });
};

const handle = async (msg, ctx) => {
  if (process.env.SIMULATE_FAILURE === "true") throw new Error("Fallo simulado (SIMULATE_FAILURE=true)");

  const { tenantId, candidateId, fullName, email, vacancyId, vacancyTitle, changedAt } = msg;
  await createEmployeeFromCandidate({ tenantId, candidateId, fullName, email, vacancyId, vacancyTitle, hiredAt: changedAt }, ctx);
};

module.exports.main = createSqsWorker({
  fn: "processCandidateHiredWorker",
  eventType: "candidate.hired",
  validate: validateCandidateHired,
  handle,
  idempotency: createIdempotency({ client: ddb, table: process.env.IDEMPOTENCY_TABLE, consumer: "hr-recruitment-sync" }),
});
