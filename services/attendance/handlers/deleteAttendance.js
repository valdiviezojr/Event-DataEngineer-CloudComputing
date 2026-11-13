const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { EMPLOYEE_RE, HttpError, res, wrap, getAuthContext, strip } = require("../lib/http");
const { isValidDate } = require("../lib/dates");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}));

module.exports.main = wrap(
  "deleteAttendance",
  async ({ event, log, requestId, tenantId }) => {
    const { employeeId, date } = event.pathParameters || {};

    if (!employeeId || !EMPLOYEE_RE.test(employeeId) || !isValidDate(date)) {
      throw new HttpError(400, "employeeId o date inválidos");
    }

    const role = String(getAuthContext(event).role || "").toUpperCase();

    if (role !== "ADMIN") {
      throw new HttpError(403, "Solo ADMIN puede eliminar marcaciones");
    }

    const db = createTenantDb(tenantId, {
      client: ddb,
      table: process.env.ATTENDANCE_TABLE
    });

    const sk = `ATTENDANCE#${employeeId}#${date}`;

    let deleted;

    try {
      deleted = await db.delete(sk, {
        ConditionExpression: "attribute_exists(SK) AND tenantId = :tenant",
        ExpressionAttributeValues: { ":tenant": tenantId },
        ReturnValues: "ALL_OLD"
      });
    } catch (err) {
      if (err.name === "ConditionalCheckFailedException") {
        throw new HttpError(404, "Marcación no encontrada");
      }
      throw err;
    }

    log("INFO", "Marcación eliminada", {
      requestId, tenantId, employeeId, date
    });

    return res(200, {
      message: "Marcación eliminada",
      attendance: strip(deleted),
      requestId
    });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"] }
);
