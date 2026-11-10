const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { EMPLOYEE_RE, HttpError, res, wrap, parseBody, assertEmployeeScope, getActor, strip } = require("../lib/http");
const { isValidDate, localDate, parseTimestamp } = require("../lib/dates");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });
const FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

module.exports.main = wrap(
  "clockOut",
  async ({ event, log, requestId, tenantId }) => {
    const db = createTenantDb(tenantId, { client: ddb, table: process.env.ATTENDANCE_TABLE });
    const { employeeId, timestamp, date: dateParam } = parseBody(event);

    if (typeof employeeId !== "string" || !EMPLOYEE_RE.test(employeeId)) throw new HttpError(400, "employeeId inválido");
    assertEmployeeScope(event, employeeId);

    const at = parseTimestamp(timestamp);
    if (!at) throw new HttpError(400, "timestamp debe ser una fecha ISO 8601");
    if (at.getTime() > Date.now() + FUTURE_TOLERANCE_MS) throw new HttpError(400, "timestamp no puede estar en el futuro");
    // `date` opcional: permite cerrar un turno nocturno iniciado el día anterior.
    if (dateParam !== undefined && !isValidDate(dateParam)) throw new HttpError(400, "date debe tener formato YYYY-MM-DD");

    const date = dateParam || localDate(at);
    const sk = `ATTENDANCE#${employeeId}#${date}`;

    const current = await db.get(sk);
    if (!current) throw new HttpError(404, "No hay entrada registrada para ese día");
    if (current.clockOut) throw new HttpError(409, "El empleado ya registró su salida ese día");

    const clockOut = at.toISOString();
    if (clockOut <= current.clockIn) throw new HttpError(400, "La salida debe ser posterior a la entrada");

    const workedMinutes = Math.floor((at.getTime() - Date.parse(current.clockIn)) / 60000);

    const updated = await db.update(sk, {
      UpdateExpression: "SET clockOut = :out, workedMinutes = :mins, #status = :closed, closedBy = :by, updatedAt = :now",
      ConditionExpression: "attribute_exists(SK) AND attribute_not_exists(clockOut)",
      ExpressionAttributeNames: { "#status": "status" },
      ExpressionAttributeValues: {
        ":out": clockOut,
        ":mins": workedMinutes,
        ":closed": "CLOSED",
        ":by": getActor(event),
        ":now": new Date().toISOString(),
      },
      ReturnValues: "ALL_NEW",
    });

    log("INFO", "Salida registrada", { requestId, tenantId, employeeId, date, workedMinutes });
    return res(200, { message: "Salida registrada", attendance: strip(updated), requestId });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"], conflictMessage: "El empleado ya registró su salida ese día" }
);
