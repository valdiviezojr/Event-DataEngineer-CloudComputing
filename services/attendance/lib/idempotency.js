// Idempotencia de consumidores SQS sobre la tabla hcm-events-idempotency-${stage} (PK eventKey, TTL expiresAt).
//
// Flujo: begin() reclama la clave (IN_PROGRESS con lease) → se procesa → complete() la marca COMPLETED.
// Si el proceso falla, release() la borra para que el reintento de SQS pueda volver a procesarla.
// Si la Lambda muere sin liberar, el lease vence y el siguiente intento la retoma.
//
// La clave se prefija con el consumidor: SNS reutiliza el mismo MessageId en todas las
// suscripciones de un fan-out, así que dos consumidores distintos no deben compartir clave.
const { PutCommand, GetCommand, UpdateCommand, DeleteCommand } = require("@aws-sdk/lib-dynamodb");

const STATUS = { IN_PROGRESS: "IN_PROGRESS", COMPLETED: "COMPLETED" };
const RESULT = { NEW: "NEW", DUPLICATE: "DUPLICATE", IN_PROGRESS: "IN_PROGRESS" };

const createIdempotency = ({ client, table, consumer, ttlDays = 7, leaseSeconds = 120, now = () => Date.now() }) => {
  if (!client || !consumer) throw new Error("createIdempotency: client y consumer son obligatorios");

  const keyOf = (key) => `${consumer}#${key}`;
  const epoch = () => Math.floor(now() / 1000);

  const currentStatus = async (eventKey, err) => {
    // Con ReturnValuesOnConditionCheckFailure el error trae el ítem (en formato AttributeValue).
    const fromErr = err?.Item?.status?.S ?? err?.Item?.status;
    if (fromErr) return fromErr;
    const out = await client.send(new GetCommand({ TableName: table, Key: { eventKey }, ConsistentRead: true }));
    return out.Item?.status;
  };

  return {
    keyOf,
    configured: typeof table === "string" && table.length > 0,

    async begin(key, meta = {}) {
      const eventKey = keyOf(key);
      const t = epoch();
      try {
        await client.send(
          new PutCommand({
            TableName: table,
            Item: {
              ...meta,
              eventKey,
              consumer,
              status: STATUS.IN_PROGRESS,
              leaseUntil: t + leaseSeconds,
              expiresAt: t + ttlDays * 86400,
              startedAt: new Date(t * 1000).toISOString(),
            },
            ConditionExpression: "attribute_not_exists(eventKey) OR (#s = :ip AND leaseUntil < :now)",
            ExpressionAttributeNames: { "#s": "status" },
            ExpressionAttributeValues: { ":ip": STATUS.IN_PROGRESS, ":now": t },
            ReturnValuesOnConditionCheckFailure: "ALL_OLD",
          })
        );
        return RESULT.NEW;
      } catch (err) {
        if (err.name !== "ConditionalCheckFailedException") throw err;
        return (await currentStatus(eventKey, err)) === STATUS.COMPLETED ? RESULT.DUPLICATE : RESULT.IN_PROGRESS;
      }
    },

    async complete(key) {
      await client.send(
        new UpdateCommand({
          TableName: table,
          Key: { eventKey: keyOf(key) },
          UpdateExpression: "SET #s = :done, completedAt = :at REMOVE leaseUntil",
          ExpressionAttributeNames: { "#s": "status" },
          ExpressionAttributeValues: { ":done": STATUS.COMPLETED, ":at": new Date(now()).toISOString() },
        })
      );
    },

    async release(key) {
      try {
        await client.send(
          new DeleteCommand({
            TableName: table,
            Key: { eventKey: keyOf(key) },
            ConditionExpression: "#s = :ip",
            ExpressionAttributeNames: { "#s": "status" },
            ExpressionAttributeValues: { ":ip": STATUS.IN_PROGRESS },
          })
        );
      } catch (err) {
        if (err.name !== "ConditionalCheckFailedException") throw err;
      }
    },
  };
};

module.exports = { createIdempotency, RESULT, STATUS };
