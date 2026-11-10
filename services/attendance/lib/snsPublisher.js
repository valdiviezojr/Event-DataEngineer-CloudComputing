// Publicación de eventos de dominio con el formato de reference/:
// Message = JSON({ eventType, ...payload }) + MessageAttributes eventType / tenantId.
// Los eventos de este equipo añaden eventId (UUID) y occurredAt (ISO).
const { PublishCommand } = require("@aws-sdk/client-sns");
const { randomUUID } = require("crypto");

// En serverless-offline un !ImportValue no se resuelve: solo aceptamos un ARN real.
const isTopicArn = (v) => typeof v === "string" && v.startsWith("arn:aws:sns:");

const createPublisher = ({ client, topicArn }) => ({
  enabled: isTopicArn(topicArn),

  async publish(eventType, tenantId, payload = {}, { eventId = randomUUID(), occurredAt = new Date().toISOString() } = {}) {
    if (!isTopicArn(topicArn)) throw new Error("Topic SNS no configurado");
    const message = { eventType, eventId, occurredAt, tenantId, ...payload };
    const out = await client.send(
      new PublishCommand({
        TopicArn: topicArn,
        Message: JSON.stringify(message),
        MessageAttributes: {
          eventType: { DataType: "String", StringValue: eventType },
          tenantId: { DataType: "String", StringValue: tenantId },
        },
      })
    );
    return { eventId, messageId: out.MessageId };
  },
});

module.exports = { createPublisher, isTopicArn };
