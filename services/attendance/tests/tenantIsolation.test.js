process.env.ATTENDANCE_TABLE = "ms-attendance-table-test";
process.env.ATTENDANCE_TOPIC_ARN = "arn:aws:sns:us-east-1:000000000000:hcm-attendance-test-events";

const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { SNSClient } = require("@aws-sdk/client-sns");

const clockIn = require("../handlers/clockIn").main;
const listAttendance = require("../handlers/listAttendance").main;
const requestLeave = require("../handlers/requestLeave").main;
const approveLeave = require("../handlers/approveLeave").main;

const ctx = { awsRequestId: "req-test-1" };
const LEAVE_ID = "l-11111111-2222-4333-8444-555555555555";

const { apiEvent: evt } = require("./helpers");

let ddbSend;
let snsSend;

beforeEach(() => {
  delete process.env.IS_OFFLINE;
  ddbSend = jest.spyOn(DynamoDBDocumentClient.prototype, "send").mockResolvedValue({});
  snsSend = jest.spyOn(SNSClient.prototype, "send").mockResolvedValue({ MessageId: "sns-1" });
  jest.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => jest.restoreAllMocks());

const expect403 = (out) => {
  expect(out.statusCode).toBe(403);
  expect(JSON.parse(out.body)).toEqual({ message: "Acceso denegado", requestId: "req-test-1" });
  expect(out.headers["Access-Control-Allow-Origin"]).toBe("*");
  expect(ddbSend).not.toHaveBeenCalled();
  expect(snsSend).not.toHaveBeenCalled();
};

describe("rechazo de tenant distinto al del token (403)", () => {
  test("tenantId en el body", async () => {
    expect403(await clockIn(evt({ body: { employeeId: "emp-1", tenantId: "tenant_b" } }), ctx));
  });

  test("header x-tenant-id distinto", async () => {
    expect403(await requestLeave(evt({ headers: { "X-Tenant-Id": "tenant_c" }, body: { employeeId: "emp-1" } }), ctx));
  });

  test("tenantId en query string", async () => {
    expect403(await listAttendance(evt({ qs: { employeeId: "emp-1", tenantId: "tenant_b" } }), ctx));
  });

  test("tenant_id en path / body de approve", async () => {
    expect403(await approveLeave(evt({ path: { leaveId: LEAVE_ID, tenant_id: "tenant_b" } }), ctx));
    expect403(await approveLeave(evt({ path: { leaveId: LEAVE_ID }, body: { tenant: "tenant_b" } }), ctx));
  });

  test("nextToken con PK de otro tenant no se usa (400)", async () => {
    const foreign = Buffer.from(JSON.stringify({ PK: "TENANT#tenant_b", SK: "ATTENDANCE#emp-1#2026-11-01" })).toString("base64url");
    const out = await listAttendance(evt({ qs: { employeeId: "emp-1", nextToken: foreign } }), ctx);
    expect(out.statusCode).toBe(400);
    expect(ddbSend).not.toHaveBeenCalled();
  });
});

describe("resolución del tenant (Lambda authorizer de hcm-auth)", () => {
  test("lee tenantId del context plano del authorizer", async () => {
    const out = await clockIn(evt({ tenant: "tenant_c", body: { employeeId: "emp-c-admin" } }), ctx);
    expect(out.statusCode).toBe(201);
    const put = ddbSend.mock.calls[0][0].input;
    expect(put.Item.PK).toBe("TENANT#tenant_c");
    expect(put.Item.recordedBy).toBe("hr@empresa-a.com"); // email del authorizer
  });

  test("sin tenantId en el authorizer y fuera de offline => 401 aunque venga x-tenant-id", async () => {
    const out = await clockIn(evt({ tenant: null, headers: { "x-tenant-id": "tenant_a" }, body: { employeeId: "emp-1" } }), ctx);
    expect(out.statusCode).toBe(401);
    expect(ddbSend).not.toHaveBeenCalled();
  });

  test("la ruta antigua (claims custom:tenant_id) ya no se acepta => 401", async () => {
    for (const authorizer of [{ claims: { "custom:tenant_id": "tenant_a" } }, { jwt: { claims: { "custom:tenant_id": "tenant_a" } } }]) {
      const out = await clockIn(evt({ authorizer, body: { employeeId: "emp-1" } }), ctx);
      expect(out.statusCode).toBe(401);
    }
    expect(ddbSend).not.toHaveBeenCalled();
  });

  test("IS_OFFLINE: el header x-tenant-id define el tenant y el PK", async () => {
    process.env.IS_OFFLINE = "true";
    const out = await clockIn(evt({ tenant: null, headers: { "x-tenant-id": "tenant_b" }, body: { employeeId: "emp-1" } }), ctx);
    expect(out.statusCode).toBe(201);
    const put = ddbSend.mock.calls[0][0].input;
    expect(put.Item.PK).toBe("TENANT#tenant_b");
    expect(put.Item.tenantId).toBe("tenant_b");
  });

  test("IS_OFFLINE con authorizer: manda el authorizer y un x-tenant-id distinto => 403", async () => {
    process.env.IS_OFFLINE = "true";
    expect403(await clockIn(evt({ tenant: "tenant_b", headers: { "x-tenant-id": "tenant_a" }, body: { employeeId: "emp-1" } }), ctx));
  });

  test("mismo tenant en header y authorizer => permitido; el PK sale del authorizer", async () => {
    const out = await clockIn(evt({ headers: { "x-tenant-id": "tenant_a" }, body: { employeeId: "emp-1", tenantId: "tenant_a" } }), ctx);
    expect(out.statusCode).toBe(201);
    const put = ddbSend.mock.calls[0][0].input;
    expect(put.Item.PK).toBe("TENANT#tenant_a");
    expect(put.Item.SK).toMatch(/^ATTENDANCE#emp-1#\d{4}-\d{2}-\d{2}$/);
    expect(put.ConditionExpression).toBe("attribute_not_exists(SK)");
  });
});

describe("rol y employeeId del authorizer", () => {
  const employee = { role: "EMPLOYEE", employeeId: "emp-a-001", email: "empleado@empresa-a.com" };

  test("EMPLOYEE opera sobre su propio employeeId", async () => {
    const out = await clockIn(evt({ ...employee, body: { employeeId: "emp-a-001" } }), ctx);
    expect(out.statusCode).toBe(201);
  });

  test("EMPLOYEE sobre otro employeeId => 403 sin tocar DynamoDB", async () => {
    for (const out of [
      await clockIn(evt({ ...employee, body: { employeeId: "emp-a-hr" } }), ctx),
      await listAttendance(evt({ ...employee, qs: { employeeId: "emp-a-hr" } }), ctx),
      await requestLeave(evt({ ...employee, body: { employeeId: "emp-a-hr", type: "VACATION", startDate: "2099-01-04", endDate: "2099-01-05" } }), ctx),
    ]) {
      expect(out.statusCode).toBe(403);
      expect(JSON.parse(out.body).message).toBe("Solo puedes operar sobre tus propios registros");
    }
    expect(ddbSend).not.toHaveBeenCalled();
  });

  test("EMPLOYEE no puede aprobar licencias; HR y ADMIN sí llegan a DynamoDB", async () => {
    const denied = await approveLeave(evt({ ...employee, path: { leaveId: LEAVE_ID } }), ctx);
    expect(denied.statusCode).toBe(403);
    expect(ddbSend).not.toHaveBeenCalled();

    for (const role of ["HR", "ADMIN"]) {
      const out = await approveLeave(evt({ role, path: { leaveId: LEAVE_ID } }), ctx);
      expect(out.statusCode).toBe(404); // get vacío (mock) => licencia no encontrada
    }
  });
});

describe("reglas de negocio básicas", () => {
  test("clock-in duplicado => 409", async () => {
    ddbSend.mockRejectedValueOnce(Object.assign(new Error("cond"), { name: "ConditionalCheckFailedException" }));
    const out = await clockIn(evt({ body: { employeeId: "emp-1" } }), ctx);
    expect(out.statusCode).toBe(409);
  });

  test("throttling de DynamoDB => 503", async () => {
    ddbSend.mockRejectedValueOnce(Object.assign(new Error("slow"), { name: "ThrottlingException" }));
    const out = await clockIn(evt({ body: { employeeId: "emp-1" } }), ctx);
    expect(out.statusCode).toBe(503);
  });

  test("approve publica leave.approved con daysUnpaid y responde FAILED si SNS falla", async () => {
    ddbSend
      .mockResolvedValueOnce({ Item: { PK: "TENANT#tenant_a", SK: `LEAVE#${LEAVE_ID}`, tenantId: "tenant_a", leaveId: LEAVE_ID, employeeId: "emp-1", type: "UNPAID", status: "PENDING", startDate: "2026-12-01", endDate: "2026-12-03", totalDays: 3 } })
      .mockResolvedValueOnce({ Attributes: { PK: "TENANT#tenant_a", tenantId: "tenant_a", leaveId: LEAVE_ID, status: "APPROVED", daysUnpaid: 3 } });
    snsSend.mockRejectedValueOnce(new Error("sns down"));

    const out = await approveLeave(evt({ path: { leaveId: LEAVE_ID } }), ctx);
    expect(out.statusCode).toBe(200);
    expect(JSON.parse(out.body).notification).toBe("FAILED");

    const msg = JSON.parse(snsSend.mock.calls[0][0].input.Message);
    expect(msg).toMatchObject({ eventType: "leave.approved", tenantId: "tenant_a", leaveId: LEAVE_ID, employeeId: "emp-1", daysUnpaid: 3 });
    expect(msg.eventId).toMatch(/^[0-9a-f-]{36}$/);
    expect(snsSend.mock.calls[0][0].input.MessageAttributes.eventType.StringValue).toBe("leave.approved");
  });

  test("request con solapamiento => 409 consultando GSI1 (sin scan)", async () => {
    ddbSend.mockResolvedValueOnce({ Items: [{ PK: "TENANT#tenant_a", tenantId: "tenant_a", GSI1PK: "TENANT#tenant_a#EMPLOYEE#emp-1", leaveId: LEAVE_ID, startDate: "2099-01-02", endDate: "2099-01-05", status: "APPROVED" }] });
    const out = await requestLeave(evt({ body: { employeeId: "emp-1", type: "VACATION", startDate: "2099-01-04", endDate: "2099-01-08" } }), ctx);
    expect(out.statusCode).toBe(409);
    expect(JSON.parse(out.body).overlaps[0].leaveId).toBe(LEAVE_ID);
    const q = ddbSend.mock.calls[0][0];
    expect(q.constructor.name).toBe("QueryCommand");
    expect(q.input.IndexName).toBe("GSI1");
    expect(q.input.ExpressionAttributeValues[":__g"]).toBe("TENANT#tenant_a#EMPLOYEE#emp-1");
    expect(ddbSend).toHaveBeenCalledTimes(1);
  });

  test("list usa SK BETWEEN con límite y devuelve nextToken", async () => {
    const lastKey = { PK: "TENANT#tenant_a", SK: "ATTENDANCE#emp-1#2026-11-02" };
    ddbSend.mockResolvedValueOnce({ Items: [{ PK: "TENANT#tenant_a", SK: lastKey.SK, tenantId: "tenant_a", date: "2026-11-02" }], LastEvaluatedKey: lastKey });
    const out = await listAttendance(evt({ qs: { employeeId: "emp-1", from: "2026-11-01", to: "2026-11-30", limit: "1" } }), ctx);
    expect(out.statusCode).toBe(200);
    const body = JSON.parse(out.body);
    expect(body.items[0].PK).toBeUndefined();
    expect(JSON.parse(Buffer.from(body.nextToken, "base64url").toString())).toEqual(lastKey);
    const { input } = ddbSend.mock.calls[0][0];
    expect(input.KeyConditionExpression).toBe("PK = :__pk AND SK BETWEEN :__sk AND :__sk2");
    expect(input.ExpressionAttributeValues[":__sk"]).toBe("ATTENDANCE#emp-1#2026-11-01");
    expect(input.ExpressionAttributeValues[":__sk2"]).toBe("ATTENDANCE#emp-1#2026-11-30");
    expect(input.Limit).toBe(1);
  });

  test("limit fuera de rango => 400", async () => {
    const out = await listAttendance(evt({ qs: { employeeId: "emp-1", limit: "500" } }), ctx);
    expect(out.statusCode).toBe(400);
  });

  test("regla daysUnpaid", () => {
    const { computeDaysUnpaid } = require("../handlers/approveLeave");
    expect(computeDaysUnpaid("UNPAID", 3)).toBe(3);
    expect(computeDaysUnpaid("OTHER", 2)).toBe(2);
    expect(computeDaysUnpaid("VACATION", 5)).toBe(0);
    expect(computeDaysUnpaid("SICK", 4)).toBe(0);
  });
});
