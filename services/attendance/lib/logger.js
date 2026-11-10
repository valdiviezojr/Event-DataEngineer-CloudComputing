// Logs JSON de una línea, mismo formato que reference/: { level, fn, msg, ts, ...extra }
const makeLog = (fn) => (level, msg, extra = {}) =>
  console.log(JSON.stringify({ level, fn, msg, ts: new Date().toISOString(), ...extra }));

module.exports = { makeLog };
