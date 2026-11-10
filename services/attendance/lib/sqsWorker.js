// Runner común de workers SNS → SQS → Lambda con ReportBatchItemFailures.
//
// Por record:
//   no-JSON / evento inválido / tenant inconsistente  → log ERROR y se descarta (no se reintenta)
//   duplicado (ya COMPLETED)                         → log INFO y se omite
//   en curso en otra invocación                      → batchItemFailure (se reintenta luego)
//   PermanentError del handler                       → log ERROR y se descarta
//   cualquier otro error                             → batchItemFailure (3 intentos → DLQ)
const { makeLog } = require("./logger");
const { parseRecord, eventKeyOf } = require("./sqsEnvelope");
const { RESULT } = require("./idempotency");

// Error de negocio que no se arregla reintentando (p. ej. el empleado no existe).
class PermanentError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "PermanentError";
    this.details = details;
  }
}

const createSqsWorker = ({ fn, eventType, validate, handle, idempotency }) => async (event, context) => {
  const log = makeLog(fn);
  const requestId = context?.awsRequestId || "local";
  const failures = [];
  const stats = { received: 0, processed: 0, duplicates: 0, discarded: 0, retried: 0 };

  // Sin tabla de idempotencia no se procesa nada: todo vuelve a la cola (y acaba en la DLQ).
  if (!idempotency.configured) {
    log("ERROR", "IDEMPOTENCY_TABLE no definida, se reintenta todo el lote", { requestId });
    return { batchItemFailures: (event?.Records || []).map((r) => ({ itemIdentifier: r.messageId })) };
  }

  for (const record of event?.Records || []) {
    stats.received++;
    const messageId = record.messageId;
    const base = { requestId, messageId };

    const parsed = parseRecord(record);
    if (!parsed.ok) {
      stats.discarded++;
      log("ERROR", "Mensaje no parseable, se descarta", { ...base, reason: parsed.reason, snsMessageId: parsed.snsMessageId });
      continue;
    }

    const msg = parsed.message;
    const ctx = { ...base, snsMessageId: parsed.snsMessageId, tenantId: msg.tenantId, eventType: msg.eventType };

    if (msg.eventType !== eventType) {
      stats.discarded++;
      log("WARN", "eventType no esperado por este worker, se descarta", { ...ctx, expected: eventType });
      continue;
    }

    const errors = validate(msg);
    if (errors.length) {
      stats.discarded++;
      log("ERROR", "Payload inválido según contrato, se descarta", { ...ctx, errors });
      continue;
    }

    // El atributo SNS tenantId (usado para filtrar/rutear) debe coincidir con el payload.
    if (parsed.attributes.tenantId !== undefined && parsed.attributes.tenantId !== msg.tenantId) {
      stats.discarded++;
      log("ERROR", "SECURITY: tenantId del atributo SNS no coincide con el payload, se descarta", {
        ...ctx,
        attributeTenantId: parsed.attributes.tenantId,
      });
      continue;
    }

    const eventKey = eventKeyOf(parsed, record);
    ctx.eventKey = eventKey;

    let claim;
    try {
      claim = await idempotency.begin(eventKey, { eventType, tenantId: msg.tenantId, messageId, snsMessageId: parsed.snsMessageId });
    } catch (err) {
      stats.retried++;
      failures.push({ itemIdentifier: messageId });
      log("ERROR", "Fallo en tabla de idempotencia, se reintentará", { ...ctx, errorName: err.name, error: err.message });
      continue;
    }

    if (claim === RESULT.DUPLICATE) {
      stats.duplicates++;
      log("INFO", "Evento duplicado, se omite", ctx);
      continue;
    }
    if (claim === RESULT.IN_PROGRESS) {
      stats.retried++;
      failures.push({ itemIdentifier: messageId });
      log("WARN", "Evento en proceso por otra invocación, se reintentará", ctx);
      continue;
    }

    try {
      await handle(msg, { log, ...ctx });
      await idempotency.complete(eventKey);
      stats.processed++;
    } catch (err) {
      await idempotency.release(eventKey).catch((e) =>
        log("ERROR", "No se pudo liberar la clave de idempotencia (expirará por lease)", { ...ctx, errorName: e.name, error: e.message })
      );

      if (err instanceof PermanentError) {
        stats.discarded++;
        log("ERROR", "Error permanente procesando evento, se descarta", { ...ctx, error: err.message, details: err.details });
        continue;
      }

      stats.retried++;
      failures.push({ itemIdentifier: messageId });
      log("ERROR", "Error transitorio procesando evento, se reintentará", {
        ...ctx,
        errorName: err.name,
        error: err.message,
        approximateReceiveCount: record.attributes?.ApproximateReceiveCount,
        stack: err.stack,
      });
    }
  }

  log("INFO", "Lote procesado", { requestId, ...stats, failures: failures.length });
  return { batchItemFailures: failures };
};

module.exports = { createSqsWorker, PermanentError };
