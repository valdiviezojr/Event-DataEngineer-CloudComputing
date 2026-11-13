// Utilidades HTTP compartidas por los handlers. Replican las convenciones de reference/
// (getTenantId, res, manejo de errores) en un solo lugar.
const { assertRequestTenant, TenantViolationError } = require("./dynamoTenantFilter");
const { makeLog } = require("./logger");

const RETRYABLE = [
  "ProvisionedThroughputExceededException",
  "ThrottlingException",
  "RequestLimitExceeded",
  "InternalServerError",
  "ServiceUnavailable",
  "TransactionConflictException",
];

const EMPLOYEE_RE = /^[A-Za-z0-9_-]{1,64}$/;

const res = (statusCode, body) => ({
  statusCode,
  headers: {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
  },
  body: JSON.stringify(body),
});

// Único punto que conoce dónde deja la identidad el authorizer. El Lambda Authorizer TOKEN de hcm-auth
// devuelve un context plano: event.requestContext.authorizer.{tenantId, role, employeeId, userId, email}
// (sin "custom:" ni claims/jwt.claims). Si el authorizer cambia, se ajusta solo aquí.
const getAuthContext = (event) => event.requestContext?.authorizer || {};

const getTenantId = (event) => {
  const fromToken = getAuthContext(event).tenantId;
  if (fromToken) return fromToken;

  // serverless offline no ejecuta authorizers por ARN: ahí el tenant viene en x-tenant-id.
  if (process.env.IS_OFFLINE) {
    const h = event.headers || {};
    return h["x-tenant-id"] || h["X-Tenant-Id"];
  }
  return null;
};

const getActor = (event) => getAuthContext(event).email || "system";

class HttpError extends Error {
  constructor(statusCode, message, extra = {}) {
    super(message);
    this.statusCode = statusCode;
    this.extra = extra;
  }
}

const parseBody = (event) => {
  let body;
  try {
    const raw = event.isBase64Encoded ? Buffer.from(event.body || "", "base64").toString("utf8") : event.body;
    body = JSON.parse(raw || "{}");
  } catch {
    throw new HttpError(400, "Body JSON inválido");
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "El body debe ser un objeto JSON");
  return body;
};

const isEmployeeRole = (event) => String(getAuthContext(event).role || "").toUpperCase() === "EMPLOYEE";

// Rol EMPLOYEE solo puede operar sobre su propio employeeId (del authorizer), como en performance/.
const assertEmployeeScope = (event, employeeId) => {
  if (isEmployeeRole(event) && getAuthContext(event).employeeId !== employeeId)
    throw new HttpError(403, "Solo puedes operar sobre tus propios registros");
};

const strip = (item) => {
  if (!item) return item;
  const { PK, SK, GSI1PK, GSI1SK, ...rest } = item;
  return rest;
};

const encodeToken = (k) => (k ? Buffer.from(JSON.stringify(k)).toString("base64url") : null);

// undefined = sin token; null = token inválido o de otro tenant
const decodeToken = (t, pk) => {
  if (!t) return undefined;
  try {
    const k = JSON.parse(Buffer.from(String(t), "base64url").toString("utf8"));
    if (!k || typeof k !== "object" || k.PK !== pk) return null;
    return k;
  } catch {
    return null;
  }
};

/**
 * Envuelve un handler HTTP: valida configuración, resuelve el tenant del token, aplica
 * assertRequestTenant y traduce errores a respuestas { message, requestId }.
 * `conflictMessage` se usa para ConditionalCheckFailedException (409).
 */
const wrap = (fn, handler, { requiredEnv = [], conflictMessage = "Conflicto: el recurso ya existe o cambió de estado" } = {}) =>
  async (event, context) => {
    const log = makeLog(fn);
    const requestId = context?.awsRequestId || "local";
    let tenantId = null;

    try {
      const missing = requiredEnv.filter((k) => !process.env[k]);
      if (missing.length) {
        log("ERROR", "Variables de entorno faltantes", { requestId, missing });
        return res(500, { message: "Error de configuración del servicio", requestId });
      }

      tenantId = getTenantId(event);
      if (!tenantId) {
        log("WARN", "Tenant no identificado", { requestId });
        return res(401, { message: "Tenant no identificado", requestId });
      }

      assertRequestTenant(event, tenantId);

      return await handler({ event, log, requestId, tenantId });
    } catch (err) {
      if (err instanceof TenantViolationError) {
        log("ERROR", "SECURITY: violación de aislamiento multi-tenant", { requestId, tenantId, details: err.details });
        return res(403, { message: "Acceso denegado", requestId });
      }
      if (err instanceof HttpError) {
        log("WARN", err.message, { requestId, tenantId, statusCode: err.statusCode });
        return res(err.statusCode, { message: err.message, ...err.extra, requestId });
      }

      log("ERROR", "Fallo inesperado", {
        requestId,
        tenantId,
        errorName: err.name,
        error: err.message,
        awsStatus: err.$metadata?.httpStatusCode,
        awsRequestId: err.$metadata?.requestId,
        stack: err.stack,
      });

      if (err.name === "ConditionalCheckFailedException") return res(409, { message: conflictMessage, requestId });
      if (err.name === "ValidationException") return res(400, { message: "Parámetros inválidos", requestId });
      if (RETRYABLE.includes(err.name)) return res(503, { message: "Servicio ocupado, reintenta en unos segundos", requestId });
      if (err.name === "ResourceNotFoundException") return res(500, { message: "Recurso de base de datos no encontrado", requestId });
      if (err.name === "AccessDeniedException") return res(500, { message: "Permisos insuficientes del servicio", requestId });

      return res(500, { message: "Error interno", requestId });
    }
  };

module.exports = {
  EMPLOYEE_RE,
  RETRYABLE,
  HttpError,
  res,
  getAuthContext,
  getTenantId,
  getActor,
  parseBody,
  assertEmployeeScope,
  isEmployeeRole,
  strip,
  encodeToken,
  decodeToken,
  wrap,
};
