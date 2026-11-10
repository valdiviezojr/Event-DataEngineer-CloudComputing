// Fechas en hora local (Perú, UTC-5 por defecto, igual que performance/ con TZ_OFFSET_HOURS).
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86400000;

const tzOffsetHours = () => Number(process.env.TZ_OFFSET_HOURS ?? -5);

const isValidDate = (s) => {
  if (typeof s !== "string" || !DATE_RE.test(s)) return false;
  const [y, m, d] = s.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
};

// Fecha local YYYY-MM-DD de un instante
const localDate = (date = new Date()) => new Date(date.getTime() + tzOffsetHours() * 3600000).toISOString().slice(0, 10);

// Días calendario inclusivos entre dos fechas YYYY-MM-DD válidas
const daysInclusive = (start, end) => Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / DAY_MS) + 1;

const addDays = (dateStr, n) => new Date(Date.parse(`${dateStr}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);

// Timestamp ISO 8601 opcional; si falta, ahora.
const parseTimestamp = (v) => {
  if (v === undefined || v === null) return new Date();
  if (typeof v !== "string") return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
};

module.exports = { DATE_RE, isValidDate, localDate, daysInclusive, addDays, parseTimestamp };
