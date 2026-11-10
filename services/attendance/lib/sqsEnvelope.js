// Parseo de un record SQS que viene de SNS.
// - RawMessageDelivery: false (colas de hcm-events): record.body = envelope SNS; el evento está en envelope.Message.
// - RawMessageDelivery: true (como las colas internas de reference/): record.body es el evento directamente.
const isPlainObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

const fail = (reason, extra = {}) => ({ ok: false, reason, ...extra });

const parseRecord = (record = {}) => {
  let body;
  try {
    body = JSON.parse(record.body);
  } catch {
    return fail("record.body no es JSON");
  }
  if (!isPlainObject(body)) return fail("record.body no es un objeto JSON");

  if (body.Type === "Notification" && "Message" in body) {
    const snsMessageId = typeof body.MessageId === "string" ? body.MessageId : null;
    if (typeof body.Message !== "string") return fail("envelope.Message no es string", { snsMessageId });

    let message;
    try {
      message = JSON.parse(body.Message);
    } catch {
      return fail("envelope.Message no es JSON", { snsMessageId });
    }
    if (!isPlainObject(message)) return fail("envelope.Message no es un objeto JSON", { snsMessageId });

    const attributes = Object.fromEntries(Object.entries(body.MessageAttributes || {}).map(([k, v]) => [k, v?.Value]));
    return { ok: true, raw: false, snsMessageId, topicArn: body.TopicArn || null, attributes, message };
  }

  const attributes = Object.fromEntries(Object.entries(record.messageAttributes || {}).map(([k, v]) => [k, v?.stringValue]));
  return { ok: true, raw: true, snsMessageId: null, topicArn: null, attributes, message: body };
};

// eventId del publicador si existe; si no, el MessageId del envelope SNS; en entrega raw, el messageId de SQS.
const eventKeyOf = (parsed, record) => parsed.message.eventId || parsed.snsMessageId || record.messageId;

module.exports = { parseRecord, eventKeyOf };
