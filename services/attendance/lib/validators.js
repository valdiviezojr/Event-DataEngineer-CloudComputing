// Validación de payloads según events/contracts/*.schema.json (campos obligatorios y formatos).
// Se valida a mano para no empaquetar ajv ni los schemas fuera del servicio; tests/contracts.test.js
// comprueba que los campos obligatorios coincidan con los schemas.
const { isValidDate } = require("./dates");

const TENANT_RE = /^[A-Za-z0-9_-]{1,64}$/;
const EMPLOYEE_RE = /^[A-Za-z0-9_-]{1,64}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const isIso = (v) => typeof v === "string" && !Number.isNaN(Date.parse(v)) && /^\d{4}-\d{2}-\d{2}T/.test(v);
const isStr = (v, min = 1) => typeof v === "string" && v.trim().length >= min;

// rules: { campo: [predicado, mensaje] }. Devuelve lista de errores (vacía = válido).
const check = (msg, rules) =>
  Object.entries(rules)
    .filter(([field, [ok]]) => !ok(msg[field], msg))
    .map(([field, [, why]]) => `${field}: ${why}`);

const LEAVE_APPROVED_RULES = {
  eventType: [(v) => v === "leave.approved", "debe ser leave.approved"],
  eventId: [(v) => typeof v === "string" && UUID_RE.test(v), "UUID requerido"],
  occurredAt: [isIso, "fecha ISO 8601 requerida"],
  tenantId: [(v) => typeof v === "string" && TENANT_RE.test(v), "inválido"],
  leaveId: [(v) => typeof v === "string" && /^l-[0-9a-f-]{36}$/.test(v), "formato l-<uuid>"],
  employeeId: [(v) => typeof v === "string" && EMPLOYEE_RE.test(v), "inválido"],
  daysUnpaid: [(v, m) => Number.isInteger(v) && v >= 0 && (m.totalDays == null || v <= m.totalDays), "entero >= 0 (y <= totalDays)"],
  startDate: [isValidDate, "YYYY-MM-DD"],
  endDate: [(v, m) => isValidDate(v) && (!isValidDate(m.startDate) || v >= m.startDate), "YYYY-MM-DD y >= startDate"],
};

const CANDIDATE_HIRED_RULES = {
  eventType: [(v) => v === "candidate.hired", "debe ser candidate.hired"],
  tenantId: [(v) => typeof v === "string" && TENANT_RE.test(v), "inválido"],
  candidateId: [(v) => typeof v === "string" && /^c-[0-9a-f-]{36}$/.test(v), "formato c-<uuid>"],
  vacancyId: [(v) => typeof v === "string" && /^v-[0-9a-f-]{36}$/.test(v), "formato v-<uuid>"],
  vacancyTitle: [(v) => isStr(v), "requerido"],
  fullName: [(v) => isStr(v, 3), "requerido (mínimo 3 caracteres)"],
  email: [(v) => typeof v === "string" && EMAIL_RE.test(v), "email inválido"],
  fromStage: [(v) => v === "OFFER", "debe ser OFFER"],
  toStage: [(v) => v === "HIRED", "debe ser HIRED"],
  note: [(v) => v === null || (typeof v === "string" && v.length <= 500), "null o texto <= 500"],
  changedBy: [(v) => isStr(v), "requerido"],
  changedAt: [isIso, "fecha ISO 8601 requerida"],
};

module.exports = {
  validateLeaveApproved: (m) => check(m, LEAVE_APPROVED_RULES),
  validateCandidateHired: (m) => check(m, CANDIDATE_HIRED_RULES),
  REQUIRED: {
    "leave.approved": Object.keys(LEAVE_APPROVED_RULES),
    "candidate.hired": Object.keys(CANDIDATE_HIRED_RULES),
  },
};
