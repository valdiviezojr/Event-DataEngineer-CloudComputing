const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { EMPLOYEE_RE, HttpError, res, wrap, assertEmployeeScope, strip, encodeToken, decodeToken } = require("../lib/http");
const { isValidDate } = require("../lib/dates");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}));

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;
const MIN_DATE = "0000-01-01";
const MAX_DATE = "9999-12-31";

const parseLimit = (v) => {
  if (v == null || v === "") return DEFAULT_LIMIT;
  const n = Number(v);
  return Number.isInteger(n) && n >= 1 && n <= MAX_LIMIT ? n : null;
};

module.exports.main = wrap(
  "listAttendance",
  async ({ event, log, requestId, tenantId }) => {
    const db = createTenantDb(tenantId, { client: ddb, table: process.env.ATTENDANCE_TABLE });
    const qs = event.queryStringParameters || {};

    const employeeId = qs.employeeId;
    if (!employeeId || !EMPLOYEE_RE.test(employeeId)) throw new HttpError(400, "employeeId es obligatorio y debe ser válido");
    assertEmployeeScope(event, employeeId);

    const from = qs.from || MIN_DATE;
    const to = qs.to || MAX_DATE;
    if ((qs.from && !isValidDate(qs.from)) || (qs.to && !isValidDate(qs.to)))
      throw new HttpError(400, "from y to deben tener formato YYYY-MM-DD");
    if (from > to) throw new HttpError(400, "from no puede ser posterior a to");

    const limit = parseLimit(qs.limit);
    if (limit === null) throw new HttpError(400, `limit debe ser entero entre 1 y ${MAX_LIMIT}`);

    const startKey = decodeToken(qs.nextToken, db.pk);
    if (startKey === null) throw new HttpError(400, "nextToken inválido");

    const prefix = `ATTENDANCE#${employeeId}#`;
    const { items, lastKey } = await db.query({
      skBetween: [`${prefix}${from}`, `${prefix}${to}`],
      Limit: limit,
      startKey,
    });

    log("INFO", "Asistencia listada", { requestId, tenantId, employeeId, from, to, count: items.length, hasMore: !!lastKey });
    return res(200, { items: items.map(strip), count: items.length, nextToken: encodeToken(lastKey), requestId });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"] }
);
