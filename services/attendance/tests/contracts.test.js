// Mantiene alineados los validadores del worker con events/contracts/*.schema.json.
const fs = require("fs");
const path = require("path");
const { REQUIRED, validateLeaveApproved, validateCandidateHired } = require("../lib/validators");
const { leaveApproved, candidateHired } = require("./helpers");

const schema = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, "../../../events/contracts", `${name}.schema.json`), "utf8"));

test.each(["leave.approved", "candidate.hired"])("%s: campos obligatorios iguales al schema", (name) => {
  expect([...REQUIRED[name]].sort()).toEqual([...schema(name).required].sort());
});

test("los ejemplos de los tests cumplen el contrato", () => {
  expect(validateLeaveApproved(leaveApproved())).toEqual([]);
  expect(validateCandidateHired(candidateHired())).toEqual([]);
});

test("falta un campo obligatorio → error con el nombre del campo", () => {
  const { employeeId, ...rest } = leaveApproved();
  expect(validateLeaveApproved(rest)).toEqual([expect.stringMatching(/^employeeId:/)]);
});
