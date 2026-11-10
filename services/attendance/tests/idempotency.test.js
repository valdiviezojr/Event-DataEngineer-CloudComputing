const { createIdempotency, RESULT } = require("../lib/idempotency");

const NOW = Date.parse("2026-11-09T15:00:00.000Z");
const ccf = (item) => Object.assign(new Error("The conditional request failed"), { name: "ConditionalCheckFailedException", Item: item });

const make = (send) =>
  createIdempotency({ client: { send }, table: "hcm-events-idempotency-test", consumer: "payroll-attendance-sync", now: () => NOW });

describe("idempotencia (cliente DynamoDB mockeado)", () => {
  test("primer evento: PutItem condicional con clave por consumidor, TTL 7 días y lease", async () => {
    const send = jest.fn().mockResolvedValue({});
    expect(await make(send).begin("evt-1", { eventType: "leave.approved", tenantId: "tenant_a" })).toBe(RESULT.NEW);

    const { input } = send.mock.calls[0][0];
    expect(send.mock.calls[0][0].constructor.name).toBe("PutCommand");
    expect(input.TableName).toBe("hcm-events-idempotency-test");
    expect(input.Item.eventKey).toBe("payroll-attendance-sync#evt-1");
    expect(input.Item.status).toBe("IN_PROGRESS");
    expect(input.Item.expiresAt).toBe(NOW / 1000 + 7 * 86400);
    expect(input.Item.leaseUntil).toBe(NOW / 1000 + 120);
    expect(input.Item.tenantId).toBe("tenant_a");
    expect(input.ConditionExpression).toBe("attribute_not_exists(eventKey) OR (#s = :ip AND leaseUntil < :now)");
    expect(input.ReturnValuesOnConditionCheckFailure).toBe("ALL_OLD");
  });

  test("duplicado ya completado → DUPLICATE (estado leído del error, sin GetItem)", async () => {
    const send = jest.fn().mockRejectedValueOnce(ccf({ status: { S: "COMPLETED" } }));
    expect(await make(send).begin("evt-1")).toBe(RESULT.DUPLICATE);
    expect(send).toHaveBeenCalledTimes(1);
  });

  test("en curso por otra invocación (lease vigente) → IN_PROGRESS", async () => {
    const send = jest.fn().mockRejectedValueOnce(ccf({ status: { S: "IN_PROGRESS" } }));
    expect(await make(send).begin("evt-1")).toBe(RESULT.IN_PROGRESS);
  });

  test("si el error no trae el ítem, consulta con GetItem consistente", async () => {
    const send = jest.fn().mockRejectedValueOnce(ccf(undefined)).mockResolvedValueOnce({ Item: { status: "COMPLETED" } });
    expect(await make(send).begin("evt-1")).toBe(RESULT.DUPLICATE);
    const get = send.mock.calls[1][0];
    expect(get.constructor.name).toBe("GetCommand");
    expect(get.input).toMatchObject({ Key: { eventKey: "payroll-attendance-sync#evt-1" }, ConsistentRead: true });
  });

  test("errores no condicionales se propagan (p. ej. throttling)", async () => {
    const send = jest.fn().mockRejectedValueOnce(Object.assign(new Error("slow"), { name: "ThrottlingException" }));
    await expect(make(send).begin("evt-1")).rejects.toThrow("slow");
  });

  test("complete marca COMPLETED y release borra solo si sigue IN_PROGRESS", async () => {
    const send = jest.fn().mockResolvedValue({});
    const idem = make(send);
    await idem.complete("evt-1");
    await idem.release("evt-2");

    expect(send.mock.calls[0][0].constructor.name).toBe("UpdateCommand");
    expect(send.mock.calls[0][0].input.ExpressionAttributeValues[":done"]).toBe("COMPLETED");
    expect(send.mock.calls[1][0].constructor.name).toBe("DeleteCommand");
    expect(send.mock.calls[1][0].input.Key.eventKey).toBe("payroll-attendance-sync#evt-2");
    expect(send.mock.calls[1][0].input.ConditionExpression).toBe("#s = :ip");
  });

  test("release ignora ConditionalCheckFailed (ya completado o borrado)", async () => {
    const send = jest.fn().mockRejectedValueOnce(ccf());
    await expect(make(send).release("evt-1")).resolves.toBeUndefined();
  });

  test("la misma clave en consumidores distintos no colisiona", () => {
    const a = createIdempotency({ client: { send: jest.fn() }, table: "t", consumer: "hr-recruitment-sync" });
    const b = createIdempotency({ client: { send: jest.fn() }, table: "t", consumer: "payroll-hr-sync" });
    expect(a.keyOf("sns-1")).not.toBe(b.keyOf("sns-1"));
  });
});
