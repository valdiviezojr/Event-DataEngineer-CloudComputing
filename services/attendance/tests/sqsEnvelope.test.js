const { parseRecord, eventKeyOf } = require("../lib/sqsEnvelope");
const { leaveApproved, candidateHired, snsRecord } = require("./helpers");

describe("parseo del envelope SNS → SQS", () => {
  test("envelope (RawMessageDelivery: false): extrae Message, MessageId y atributos", () => {
    const rec = snsRecord(leaveApproved(), { snsMessageId: "sns-abc" });
    const p = parseRecord(rec);
    expect(p.ok).toBe(true);
    expect(p.raw).toBe(false);
    expect(p.snsMessageId).toBe("sns-abc");
    expect(p.topicArn).toMatch(/hcm-attendance-dev-events$/);
    expect(p.attributes).toEqual({ eventType: "leave.approved", tenantId: "tenant_a" });
    expect(p.message).toEqual(leaveApproved());
  });

  test("entrega raw: el body es el evento y los atributos vienen de messageAttributes", () => {
    const p = parseRecord({
      messageId: "sqs-raw",
      body: JSON.stringify(candidateHired()),
      messageAttributes: { tenantId: { stringValue: "tenant_a", dataType: "String" } },
    });
    expect(p.ok).toBe(true);
    expect(p.raw).toBe(true);
    expect(p.snsMessageId).toBeNull();
    expect(p.attributes.tenantId).toBe("tenant_a");
    expect(p.message.candidateId).toBe(candidateHired().candidateId);
  });

  test.each([
    ["body no JSON", { body: "esto no es json" }, "record.body no es JSON"],
    ["body array", { body: "[1,2]" }, "record.body no es un objeto JSON"],
    ["Message no JSON", snsRecord(null, { rawMessage: "{roto" }), "envelope.Message no es JSON"],
    ["Message no objeto", snsRecord(null, { rawMessage: "42" }), "envelope.Message no es un objeto JSON"],
    ["Message no string", { body: JSON.stringify({ Type: "Notification", MessageId: "x", Message: { a: 1 } }) }, "envelope.Message no es string"],
  ])("%s → ok:false", (_, rec, reason) => {
    const p = parseRecord(rec);
    expect(p.ok).toBe(false);
    expect(p.reason).toBe(reason);
  });

  test("eventKey: eventId > MessageId SNS > messageId SQS", () => {
    const withId = snsRecord(leaveApproved(), { snsMessageId: "sns-1" });
    expect(eventKeyOf(parseRecord(withId), withId)).toBe(leaveApproved().eventId);

    const noId = snsRecord(candidateHired(), { snsMessageId: "sns-2" });
    expect(eventKeyOf(parseRecord(noId), noId)).toBe("sns-2");

    const raw = { messageId: "sqs-3", body: JSON.stringify(candidateHired()) };
    expect(eventKeyOf(parseRecord(raw), raw)).toBe("sqs-3");
  });
});
