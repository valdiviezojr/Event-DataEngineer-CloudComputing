const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient } = require("@aws-sdk/lib-dynamodb");
const { SNSClient } = require("@aws-sdk/client-sns");
const { randomUUID } = require("crypto");
const { createTenantDb } = require("../lib/dynamoTenantFilter");
const { HttpError, res, wrap, parseBody, isEmployeeRole, getActor, strip } = require("../lib/http");
const { createPublisher } = require("../lib/snsPublisher");

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });
const publisher = createPublisher({ client: new SNSClient({}), topicArn: process.env.ATTENDANCE_TOPIC_ARN });

const LEAVE_RE = /^l-[0-9a-f-]{36}$/;
const UNPAID_TYPES = ["UNPAID", "OTHER"];
const MAX_NOTE = 500;

// Regla documentada en events/contracts/README.md
const computeDaysUnpaid = (type, totalDays) => (UNPAID_TYPES.includes(type) ? totalDays : 0);

module.exports.main = wrap(
  "approveLeave",
  async ({ event, log, requestId, tenantId }) => {
    if (isEmployeeRole(event)) throw new HttpError(403, "Tu rol no puede aprobar licencias");

    const db = createTenantDb(tenantId, { client: ddb, table: process.env.ATTENDANCE_TABLE });
    const leaveId = event.pathParameters?.leaveId;
    if (!leaveId || !LEAVE_RE.test(leaveId)) throw new HttpError(400, "leaveId inválido");

    const { note } = parseBody(event);
    if (note != null && (typeof note !== "string" || note.length > MAX_NOTE))
      throw new HttpError(400, `note debe ser texto de máximo ${MAX_NOTE} caracteres`);

    const sk = `LEAVE#${leaveId}`;
    const leave = await db.get(sk);
    if (!leave) throw new HttpError(404, "Licencia no encontrada");
    if (leave.status !== "PENDING") throw new HttpError(409, `La licencia ya está ${leave.status}`);

    const daysUnpaid = computeDaysUnpaid(leave.type, leave.totalDays);
    const approvedAt = new Date().toISOString();
    const eventId = randomUUID();

    const updated = await db.update(sk, {
      UpdateExpression:
        "SET #status = :approved, daysUnpaid = :du, approvedBy = :by, approvedAt = :now, approvalNote = :note, eventId = :eid, updatedAt = :now",
      ConditionExpression: "attribute_exists(SK) AND #status = :pending",
      ExpressionAttributeNames: { "#status": "status" },
      ExpressionAttributeValues: {
        ":approved": "APPROVED",
        ":pending": "PENDING",
        ":du": daysUnpaid,
        ":by": getActor(event),
        ":now": approvedAt,
        ":note": note ? note.trim() : null,
        ":eid": eventId,
      },
      ReturnValues: "ALL_NEW",
    });

    log("INFO", "Licencia aprobada", { requestId, tenantId, leaveId, employeeId: leave.employeeId, type: leave.type, daysUnpaid });

    let notification = "SKIPPED";
    if (publisher.enabled) {
      try {
        const { messageId } = await publisher.publish(
          "leave.approved",
          tenantId,
          {
            leaveId,
            employeeId: leave.employeeId,
            daysUnpaid,
            startDate: leave.startDate,
            endDate: leave.endDate,
            leaveType: leave.type,
            totalDays: leave.totalDays,
          },
          { eventId, occurredAt: approvedAt }
        );
        notification = "QUEUED";
        log("INFO", "Evento publicado", { requestId, tenantId, leaveId, eventType: "leave.approved", eventId, snsMessageId: messageId });
      } catch (pubErr) {
        notification = "FAILED";
        log("ERROR", "Fallo al publicar evento SNS", { requestId, tenantId, leaveId, eventId, errorName: pubErr.name, error: pubErr.message });
      }
    } else {
      log("WARN", "ATTENDANCE_TOPIC_ARN no definida, no se publica evento", { requestId, tenantId, leaveId });
    }

    return res(200, { message: "Licencia aprobada", leave: strip(updated), notification, requestId });
  },
  { requiredEnv: ["ATTENDANCE_TABLE"], conflictMessage: "La licencia cambió de estado mientras se procesaba, recarga e intenta de nuevo" }
);

module.exports.computeDaysUnpaid = computeDaysUnpaid;
