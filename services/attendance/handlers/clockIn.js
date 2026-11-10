const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { EMPLOYEE_RE, HttpError, res, wrap, parseBody, assertEmployeeScope, getActor, strip } = require("../lib/http");
const { localDate, parseTimestamp } = require("../lib/dates");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });
const FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

module.exports.main = wrap(
  "clockIn",
  async ({ event, log, requestId, tenantId }) => {
    const db = createTenantDb(tenantId, { client: ddb, table: process.env.ATTENDANCE_TABLE });
    const { employeeId, timestamp } = parseBody(event);

    if (typeof employeeId !== "string" || !EMPLOYEE_RE.test(employeeId)) throw new HttpError(400, "employeeId inválido");
    assertEmployeeScope(event, employeeId);

    const at = parseTimestamp(timestamp);
    if (!at) throw new HttpError(400, "timestamp debe ser una fecha ISO 8601");
    if (at.getTime() > Date.now() + FUTURE_TOLERANCE_MS) throw new HttpError(400, "timestamp no puede estar en el futuro");

    const date = localDate(at);
    const now = new Date().toISOString();

    const item = {
      SK: `ATTENDANCE#${employeeId}#${date}`,
      entityType: "ATTENDANCE",
      tenantId,
      employeeId,
      date,
      clockIn: at.toISOString(),
      status: "OPEN",
      recordedBy: getActor(event),
      createdAt: now,
      updatedAt: now,
    };

    const saved = await db.put(item, { ConditionExpression: "attribute_not_exists(SK)" });

    log("INFO", "Entrada registrada", { requestId, tenantId, employeeId, date });
    return res(201, { message: "Entrada registrada", attendance: strip(saved), requestId });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"], conflictMessage: "El empleado ya registró su entrada ese día" }
);
