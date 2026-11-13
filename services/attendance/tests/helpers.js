// Evento API Gateway (REST, proxy) tal como lo entrega el Lambda Authorizer TOKEN de hcm-auth:
// context plano en requestContext.authorizer (tenantId, role, employeeId, userId, email).
// tenant: null => sin context del authorizer (offline o petición sin token).
const apiEvent = ({ tenant = "tenant_a", role = "HR", employeeId = "emp-a-hr", email = "hr@empresa-a.com", headers = {}, body, qs, path, authorizer } = {}) => ({
  headers,
  body: body === undefined ? undefined : JSON.stringify(body),
  queryStringParameters: qs || null,
  pathParameters: path || null,
  requestContext: {
    authorizer: authorizer !== undefined ? authorizer : tenant ? { principalId: `user-${employeeId}`, tenantId: tenant, role, employeeId, userId: `user-${employeeId}`, email } : {},
  },
});

// Fábricas de records SQS para los tests de workers.
const leaveApproved = (over = {}) => ({
  eventType: "leave.approved",
  eventId: "4c2a8e19-0d7b-4f3a-b1c6-2e9d8f7a6b54",
  occurredAt: "2026-11-09T15:00:00.000Z",
  tenantId: "tenant_a",
  leaveId: "l-9a3f1c2e-7b4d-4e8a-a6f0-1d2c3b4a5e6f",
  employeeId: "emp-102",
  daysUnpaid: 3,
  startDate: "2026-11-18",
  endDate: "2026-11-20",
  leaveType: "UNPAID",
  totalDays: 3,
  ...over,
});

const candidateHired = (over = {}) => ({
  eventType: "candidate.hired",
  tenantId: "tenant_a",
  candidateId: "c-3f6b2a10-8c4d-4e9f-a1b2-c3d4e5f6a7b8",
  vacancyId: "v-1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  vacancyTitle: "Electricista Industrial",
  fullName: "María García",
  email: "maria@gmail.com",
  fromStage: "OFFER",
  toStage: "HIRED",
  note: null,
  changedBy: "reclutador@empresa.com",
  changedAt: "2026-11-09T16:20:41.002Z",
  ...over,
});

// Record SQS con envelope SNS (RawMessageDelivery: false)
const snsRecord = (message, { messageId = "sqs-1", snsMessageId = "sns-msg-1", tenantAttr, rawMessage } = {}) => ({
  messageId,
  attributes: { ApproximateReceiveCount: "1" },
  body: JSON.stringify({
    Type: "Notification",
    MessageId: snsMessageId,
    TopicArn: "arn:aws:sns:us-east-1:000000000000:hcm-attendance-dev-events",
    Message: rawMessage !== undefined ? rawMessage : JSON.stringify(message),
    Timestamp: "2026-11-09T15:00:01.000Z",
    MessageAttributes: {
      eventType: { Type: "String", Value: message?.eventType },
      tenantId: { Type: "String", Value: tenantAttr ?? message?.tenantId },
    },
  }),
});

module.exports = { apiEvent, leaveApproved, candidateHired, snsRecord };
