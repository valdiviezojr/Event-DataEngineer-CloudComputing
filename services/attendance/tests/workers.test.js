process.env.IDEMPOTENCY_TABLE = "hcm-events-idempotency-test";

const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { createSqsWorker, PermanentError } = require("../lib/sqsWorker");
const { createIdempotency } = require("../lib/idempotency");
const { validateLeaveApproved } = require("../lib/validators");
const { leaveApproved, candidateHired, snsRecord } = require("./helpers");

const leaveWorker = require("../handlers/processLeaveEventWorker").main;
const hiredWorker = require("../handlers/processCandidateHiredWorker").main;

const ctx = { awsRequestId: "req-w-1" };
const ccf = (status) => Object.assign(new Error("cond"), { name: "ConditionalCheckFailedException", Item: { status: { S: status } } });

let send;
let logs;

beforeEach(() => {
  delete process.env.SIMULATE_FAILURE;
  send = jest.spyOn(DynamoDBDocumentClient.prototype, "send").mockResolvedValue({});
  logs = [];
  jest.spyOn(console, "log").mockImplementation((l) => logs.push(JSON.parse(l)));
});
afterEach(() => jest.restoreAllMocks());

const commands = () => send.mock.calls.map(([c]) => c.constructor.name);

describe("processLeaveEventWorker", () => {
  test("evento válido: begin → handle → complete, sin fallos; logs con tenant/eventType/messageId/requestId", async () => {
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved(), { messageId: "m1" })] }, ctx);
    expect(out).toEqual({ batchItemFailures: [] });
    expect(commands()).toEqual(["PutCommand", "UpdateCommand"]);
    expect(send.mock.calls[0][0].input.Item.eventKey).toBe(`payroll-attendance-sync#${leaveApproved().eventId}`);

    const info = logs.find((l) => l.msg.startsWith("leave.approved recibido"));
    expect(info).toMatchObject({ level: "INFO", fn: "processLeaveEventWorker", tenantId: "tenant_a", eventType: "leave.approved", messageId: "m1", requestId: "req-w-1", daysUnpaid: 3 });
  });

  test("duplicado → se omite sin reintentar", async () => {
    send.mockRejectedValueOnce(ccf("COMPLETED"));
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved())] }, ctx);
    expect(out.batchItemFailures).toEqual([]);
    expect(commands()).toEqual(["PutCommand"]);
    expect(logs.some((l) => l.msg === "Evento duplicado, se omite")).toBe(true);
  });

  test("en curso en otra invocación → batchItemFailure", async () => {
    send.mockRejectedValueOnce(ccf("IN_PROGRESS"));
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved(), { messageId: "m9" })] }, ctx);
    expect(out.batchItemFailures).toEqual([{ itemIdentifier: "m9" }]);
  });

  test("no-JSON, payload inválido y tenant inconsistente → se descartan sin reintento ni escritura", async () => {
    const out = await leaveWorker(
      {
        Records: [
          { messageId: "bad-json", body: "%%%" },
          snsRecord(leaveApproved({ daysUnpaid: -1 }), { messageId: "bad-payload" }),
          snsRecord(leaveApproved({ endDate: "2026-11-01" }), { messageId: "bad-dates" }),
          snsRecord(leaveApproved(), { messageId: "bad-tenant", tenantAttr: "tenant_b" }),
          snsRecord(candidateHired(), { messageId: "wrong-type" }),
        ],
      },
      ctx
    );
    expect(out.batchItemFailures).toEqual([]);
    expect(send).not.toHaveBeenCalled();
    expect(logs.find((l) => l.msg.startsWith("Lote procesado"))).toMatchObject({ received: 5, discarded: 5 });
  });

  test("error transitorio → libera la clave y reporta solo ese mensaje (lote parcial)", async () => {
    process.env.SIMULATE_FAILURE = "true";
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved(), { messageId: "m1" })] }, ctx);
    expect(out.batchItemFailures).toEqual([{ itemIdentifier: "m1" }]);
    expect(commands()).toEqual(["PutCommand", "DeleteCommand"]);
  });

  test("fallo de la tabla de idempotencia → reintento", async () => {
    send.mockRejectedValueOnce(Object.assign(new Error("slow"), { name: "ProvisionedThroughputExceededException" }));
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved(), { messageId: "m1" })] }, ctx);
    expect(out.batchItemFailures).toEqual([{ itemIdentifier: "m1" }]);
  });

  test("daysUnpaid = 0 se procesa (complete) sin descuento", async () => {
    const out = await leaveWorker({ Records: [snsRecord(leaveApproved({ daysUnpaid: 0, leaveType: "VACATION" }))] }, ctx);
    expect(out.batchItemFailures).toEqual([]);
    expect(logs.some((l) => l.msg.startsWith("Licencia pagada"))).toBe(true);
  });
});

describe("processCandidateHiredWorker", () => {
  test("payload real de recruitment (sin eventId): idempotencia por MessageId SNS", async () => {
    const out = await hiredWorker({ Records: [snsRecord(candidateHired(), { snsMessageId: "sns-hired-1" })] }, ctx);
    expect(out.batchItemFailures).toEqual([]);
    expect(send.mock.calls[0][0].input.Item.eventKey).toBe("hr-recruitment-sync#sns-hired-1");
  });

  test("toStage distinto de HIRED → inválido, se descarta", async () => {
    const out = await hiredWorker({ Records: [snsRecord(candidateHired({ toStage: "OFFER" }))] }, ctx);
    expect(out.batchItemFailures).toEqual([]);
    expect(send).not.toHaveBeenCalled();
  });
});

describe("runner genérico", () => {
  const worker = (handle, table = "t") =>
    createSqsWorker({
      fn: "testWorker",
      eventType: "leave.approved",
      validate: validateLeaveApproved,
      handle,
      idempotency: createIdempotency({ client: { send: (c) => send(c) }, table, consumer: "test" }),
    });

  test("PermanentError → se descarta (no batchItemFailure) y se libera la clave", async () => {
    const out = await worker(async () => {
      throw new PermanentError("empleado no existe");
    })({ Records: [snsRecord(leaveApproved())] }, ctx);
    expect(out.batchItemFailures).toEqual([]);
    expect(commands()).toEqual(["PutCommand", "DeleteCommand"]);
  });

  test("lote mixto: solo fallan los transitorios", async () => {
    const handle = jest.fn(async (m) => {
      if (m.employeeId === "emp-err") throw new Error("RDS timeout");
    });
    const out = await worker(handle)(
      {
        Records: [
          snsRecord(leaveApproved({ eventId: "11111111-1111-4111-8111-111111111111" }), { messageId: "ok-1" }),
          snsRecord(leaveApproved({ eventId: "22222222-2222-4222-8222-222222222222", employeeId: "emp-err" }), { messageId: "err-1" }),
          { messageId: "junk", body: "no-json" },
        ],
      },
      ctx
    );
    expect(out.batchItemFailures).toEqual([{ itemIdentifier: "err-1" }]);
  });

  test("sin IDEMPOTENCY_TABLE → todo el lote se reintenta", async () => {
    const out = await worker(async () => {}, "")({ Records: [{ messageId: "a", body: "{}" }, { messageId: "b", body: "{}" }] }, ctx);
    expect(out.batchItemFailures).toEqual([{ itemIdentifier: "a" }, { itemIdentifier: "b" }]);
    expect(send).not.toHaveBeenCalled();
  });
});
