const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { randomUUID } = require("crypto");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { EMPLOYEE_RE, HttpError, res, wrap, parseBody, assertEmployeeScope, getActor, strip } = require("../lib/http");
const { isValidDate, localDate, daysInclusive } = require("../lib/dates");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });

const LEAVE_TYPES = ["VACATION", "SICK", "UNPAID", "OTHER"];
const BLOCKING_STATUSES = ["PENDING", "APPROVED"];
const MAX_DAYS = 365;
const MAX_REASON = 500;

// Licencias PENDING/APPROVED del empleado que se cruzan con [start, end] (GSI1, sin scan).
const findOverlaps = async (db, employeeId, startDate, endDate) => {
  const found = [];
  let startKey;
  do {
    const page = await db.query({
      index: "GSI1",
      gsiSuffix: `EMPLOYEE#${employeeId}`,
      gsiSkPrefix: "LEAVE#",
      FilterExpression: "startDate <= :end AND endDate >= :start AND #status IN (:p, :a)",
      ExpressionAttributeNames: { "#status": "status" },
      ExpressionAttributeValues: { ":start": startDate, ":end": endDate, ":p": BLOCKING_STATUSES[0], ":a": BLOCKING_STATUSES[1] },
      startKey,
    });
    found.push(...page.items);
    startKey = page.lastKey || undefined;
  } while (startKey);
  return found;
};

module.exports.main = wrap(
  "requestLeave",
  async ({ event, log, requestId, tenantId }) => {
    const db = createTenantDb(tenantId, { client: ddb, table: process.env.ATTENDANCE_TABLE });
    const { employeeId, type, startDate, endDate, reason } = parseBody(event);
    const leaveType = typeof type === "string" ? type.trim().toUpperCase() : null;

    if (typeof employeeId !== "string" || !EMPLOYEE_RE.test(employeeId)) throw new HttpError(400, "employeeId inválido");
    assertEmployeeScope(event, employeeId);

    if (!LEAVE_TYPES.includes(leaveType)) throw new HttpError(400, `type debe ser uno de: ${LEAVE_TYPES.join(", ")}`);
    if (!isValidDate(startDate) || !isValidDate(endDate)) throw new HttpError(400, "startDate y endDate deben tener formato YYYY-MM-DD y ser fechas válidas");
    if (endDate < startDate) throw new HttpError(400, "endDate no puede ser anterior a startDate");

    const totalDays = daysInclusive(startDate, endDate);
    if (totalDays > MAX_DAYS) throw new HttpError(400, `Una licencia no puede superar ${MAX_DAYS} días`);
    // Descanso médico puede registrarse después; el resto debe solicitarse con anticipación.
    if (leaveType !== "SICK" && startDate < localDate()) throw new HttpError(400, "startDate debe ser hoy o una fecha futura (excepto SICK)");
    if (reason != null && (typeof reason !== "string" || reason.length > MAX_REASON))
      throw new HttpError(400, `reason debe ser texto de máximo ${MAX_REASON} caracteres`);

    const overlaps = await findOverlaps(db, employeeId, startDate, endDate);
    if (overlaps.length) {
      throw new HttpError(409, "La licencia se cruza con otra pendiente o aprobada", {
        overlaps: overlaps.map((l) => ({ leaveId: l.leaveId, startDate: l.startDate, endDate: l.endDate, status: l.status })),
      });
    }

    const leaveId = `l-${randomUUID()}`;
    const now = new Date().toISOString();

    const item = {
      SK: `LEAVE#${leaveId}`,
      entityType: "LEAVE",
      tenantId,
      leaveId,
      employeeId,
      type: leaveType,
      startDate,
      endDate,
      totalDays,
      reason: reason ? reason.trim() : null,
      status: "PENDING",
      requestedBy: getActor(event),
      createdAt: now,
      updatedAt: now,
      GSI1PK: db.gsiPk(`EMPLOYEE#${employeeId}`),
      GSI1SK: `LEAVE#${startDate}#${leaveId}`,
    };

    const saved = await db.put(item, { ConditionExpression: "attribute_not_exists(SK)" });

    log("INFO", "Licencia solicitada", { requestId, tenantId, leaveId, employeeId, type: leaveType, totalDays });
    return res(201, { message: "Licencia solicitada", leave: strip(saved), requestId });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"], conflictMessage: "La licencia ya existe" }
);

module.exports.LEAVE_TYPES = LEAVE_TYPES;
