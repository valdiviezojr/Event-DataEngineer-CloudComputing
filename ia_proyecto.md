# Arquitectura SaaS HCM Serverless en AWS

**Conversión íntegra del PDF a Markdown.** Se conserva el texto y la disposición por página; se retiraron únicamente los encabezados y pies repetidos del visor PDF.

## Página 1

```text
Firefox                                                                                                                                                                                                            about:blank
          Arquitectura SaaS HCM Serverless en AWS
          https://gemini.google.com/app/ff83e756c4af7612
          User prompt: Actúa como un Lead Cloud Architect y Director de Proyectos Software Senior con experiencia en arquitecturas Serverless en AWS, patrones Multi-tenant y sistemas HCM (Human Capital
          Management). Tu objetivo es diseñar la arquitectura técnica completa, el modelo de datos, la estrategia de eventos y la distribución de trabajo para un equipo de 5 personas que desarrollará un SaaS HCM para
          el proyecto final del curso CS2032 Computación en la Nube (UTEC 2026-2). --- ### CONTEXTO DEL PROYECTO Y RESTRICCIONES DE LA RÚBRICA 1. Dominio: SaaS HCM (Gestión de Empleados, Nómina, Talento,
          Contratación, Desempeño). Referencias: BambooHR, Workday, SAP SuccessFactors. 2. Integrantes: 5 personas. 3. FrontEnd: Framework moderno (React/Vue/Angular) desplegado en AWS Amplify. 4. BackEnd: - 5
          microservicios serverless protegidos (API Gateway + AWS Lambda). - Base de datos por microservicio: SQL (RDS con patrón Single Database, Multiple Schemas por tenant) o NoSQL (DynamoDB con aislamiento
          por Tenant ID). - Cada microservicio debe contar con al menos 30,000 registros ficticios divididos en 3 tenants (~10,000 por tenant). - Uso obligatorio de AWS S3 (archivos), AWS SNS (publicación de eventos) y
          AWS SQS (desacoplamiento/colas). - Infraestructura como Código (IaC) automatizada al 100% mediante Serverless Framework (`serverless.yml`). 5. Hitos de Entrega: - Avance Virtual (Sábado 14-Nov): 30%
          funcional con ACL. - Entrega Canvas (Domingo 22-Nov): Repositorios, Informe (PDF/Word), Presentación (PPTX), esquemas BD. - Demo Presencial (Semana 16): Demostración en vivo ejecutando la app con 2
          tenants aislados. --- ### ESTRUCTURA DE LA RESPUESTA REQUERIDA Genera una guía técnica exhaustiva dividida en los siguientes 6 bloques: #### BLOQUE 1: Matriz de Requisitos (Explícitos e Implícitos) - Tabla
          de trazabilidad que cruce los requisitos del PDF (rúbrica y enunciados) con los controles técnicos de arquitectura en AWS (aislamiento multi-tenant, manejo de datos masivos, seguridad y observabilidad). ####
          BLOQUE 2: Definición Fina de los 5 Microservicios HCM Para cada uno de los 5 microservicios (Core HR, Reclutamiento, Nóminas, Desempeño, Asistencia/Licencias), detalla: 1. Nombre del microservicio y alcance
          exacto. 2. Entidades clave y Modelo de Datos (Diagrama Entidad-Relación estructurado o esquema JSON de DynamoDB con Partition/Sort Key). 3. Endpoints REST (Método, Ruta, Parámetros y Body esperado). 4.
          Integración EDA: Evento exacto que publica en AWS SNS y evento/cola que consume mediante AWS SQS. 5. Almacenamiento S3: Tipo de archivos guardados y estructura de carpetas por `tenant_id`. #### BLOQUE
          3: Arquitectura Serverless & Patrón Multi-Tenant 1. Estrategia de Aislamiento: Inyección de `tenant_id` en JWT / Cognito Authorizer y su propagación en Lambda a RDS (schemas dinámicos) o DynamoDB (PK
          constraint). 2. Diagrama Teórico de Arquitectura: Flujo completo desde React (Amplify) -> CloudFront/API Gateway -> Authorizer -> Lambda -> RDS/DynamoDB -> SNS -> SQS -> Lambda Worker -> S3. ####
          BLOQUE 4: División del Trabajo Fina para 5 Personas (WBS) Asigna un rol claro a cada integrante (Ej. DevOps/Infra, Core BackEnd 1, Core BackEnd 2, Event/Data Engineer, FrontEnd/Amplify Lead). Para cada rol
          detalla: - Entregables de código y configuración específicos. - Contratos de API o dependencias técnicas directas con otros compañeros. - Tareas concretas por semana (Semana 11 a Semana 16). #### BLOQUE 5:
          Estrategia de Seeding de Datos (30,000 Registros por Microservicio) - Plan técnico y script sugerido (Python/Node.js con Faker) para insertar masivamente 30,000 registros por microservicio repartidos en 3
          tenants sin saturar la BD ni agotar timeouts de AWS Lambda. #### BLOQUE 6: Plan de Pruebas y Script para la Demo Presencial - Paso a paso detallado para realizar la demostración presencial en Semana 16
          con 2 tenants en vivo, demostrando que un tenant no puede ver ni alterar los datos del otro.
          Response: Para el desarrollo del SaaS HCM multi-tenant serverless en AWS correspondiente al curso CS2032 (UTEC 2026-2), la arquitectura técnica, modelo de datos, desacoplamiento por eventos y
          plan de trabajo para 5 integrantes se detallan formalmente a continuación.
          BLOQUE 1: Matriz de Requisitos (Explícitos e Implícitos)
           Requisito de la Rúbrica / PDF          Tipo        Control Técnico de Arquitectura en AWS                    Estrategia de Implementación y Observabilidad
                                                                                                                        CI/CD automatizado conectado a GitHub. Variables de entorno por tenant inyectadas
           FrontEnd en AWS Amplify                Explícito   AWS Amplify Hosting + CloudFront CDN.
                                                                                                                        dinámicamente en el build.
                                                              API Gateway HTTP/REST + AWS Lambda (Node.js/              Un stack independiente por microservicio definido en serverless.yml. Desacoplamiento
           5 Microservicios Serverless            Explícito
                                                              Python).                                                  total por dominio.
           Persistencia Híbrida (RDS /                                                                                  RDS: Patrón Single Database, Multiple Schemas (tenant_a, tenant_b). DynamoDB: Single-
                                                  Explícito   Amazon RDS (PostgreSQL) y Amazon DynamoDB.
           DynamoDB)                                                                                                    Table Design aislado por Partition Key.
           30,000 Registros por                               Scripts de carga masiva en Python/Node.js usando          Seeding directo ejecutado desde entornos locales o AWS CloudShell hacia las bases de datos
                                                  Explícito
           Microservicio                                      operaciones en lote (Batch Write / COPY).                 para evitar rebasar los timeouts de Lambda (15 min).
           Desacoplamiento con SNS y                          AWS SNS (Topics por dominio) + AWS SQS (Colas de          Patrón Fan-out: Publicación a SNS al generar eventos de dominio; SQS procesa los mensajes
                                                  Explícito
           SQS                                                suscripción por microservicio).                           asíncronamente con Dead Letter Queues (DLQ).
                                                                                                                        Estructura de prefijos rígida: s3://hcm-app-storage/{tenant_id}/{microservice}/
           Almacenamiento en AWS S3               Explícito   Amazon S3 Bucket único multitenant.
                                                                                                                        {file_id} con políticas IAM de control de acceso a nivel de prefijo.
           IaC al 100% (Serverless                                                                                      Definición declarativa de Lambdas, API Gateways, SNS, SQS y S3. Uso de plugins como
                                                  Explícito   Infrastructure as Code mediante serverless.yml.
           Framework)                                                                                                   serverless-iam-roles-per-function.
           Demostración de Aislamiento                        AWS Cognito Custom Claims + Authorizer de API             Token JWT inyecta custom:tenant_id. La Lambda aplica un filtro estricto en BD (Row Level
                                                  Explícito
           Multi-Tenant                                       Gateway.                                                  Security / Schema Search Path / DynamoDB PK constraint).
           Observabilidad e Identificación                                                                               Inyección estructurada de tenant_id y trace_id en todos los registros JSON de Lambda
                                                  Implícito   Amazon CloudWatch Logs & AWS X-Ray.
           Multi-Tenant                                                                                                 para rastreo de peticiones cruzadas.
           Resiliencia y Manejo de Errores                    AWS SQS DLQ (Dead Letter Queue) + Exponential             Manejo de mensajes fallidos después de 3 reintentos para no perder eventos entre
                                                  Implícito
           EDA                                                Backoff.                                                   microservicios.
          BLOQUE 2: Definición Fina de los 5 Microservicios HCM
          1. Microservicio Core HR (ms-core-hr)
             • Alcance: Gestión de la estructura organizacional, expedientes de empleados, puestos de trabajo y contratos laborales.
             • Modelo de Datos (RDS PostgreSQL - Schema per Tenant):
               -- Schema: tenant_a / tenant_b / tenant_c
               CREATE TABLE departments (
                   department_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   name VARCHAR(100) NOT NULL,
                   budget NUMERIC(12, 2)
               );
               CREATE TABLE employees (
                   employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   department_id UUID REFERENCES departments(department_id),
                   first_name VARCHAR(50) NOT NULL,
                   last_name VARCHAR(50) NOT NULL,
                   email VARCHAR(100) UNIQUE NOT NULL,
                   hire_date DATE NOT NULL,
                   status VARCHAR(20) DEFAULT 'ACTIVE'
               );
               CREATE TABLE contracts (
                   contract_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   employee_id UUID REFERENCES employees(employee_id),
                   salary NUMERIC(10, 2) NOT NULL,
                   start_date DATE NOT NULL,
                   contract_type VARCHAR(30) NOT NULL
               );
             • Endpoints REST:
                   ◦ POST /employees | Body: { "firstName": "John", "lastName": "Doe", "email": "john@corp.com", "departmentId": "uuid", "salary": 3500 }
                   ◦ GET /employees | Query Params: ?page=1&limit=50
                   ◦ GET /employees/{id} | Path Param: id
                   ◦ PUT /employees/{id} | Path Param: id | Body: { "status": "INACTIVE" }
```

## Página 2

```text
Firefox                                                                                                                                                                         about:blank
            • Integración EDA:
                 ◦ Publica en SNS: sns-hr-events → Evento: employee.created (Payload: { tenant_id, employee_id, email, salary, hire_date }).
                 ◦ Consume de SQS: N/A (Microservicio origen de identidad).
            • Almacenamiento S3:
                 ◦ Ruta: s3://hcm-app-storage/{tenant_id}/core-hr/contracts/{employee_id}_contract.pdf
          2. Microservicio de Reclutamiento y Selección (ms-recruitment)
            • Alcance: Administración de vacantes, recepción de postulantes, gestión del pipeline de contratación e historial de entrevistas.
            • Modelo de Datos (DynamoDB - Single Table Design):
                 ◦ Partition Key (PK): TENANT#<tenant_id>
                 ◦ Sort Key (SK): VACANCY#<vacancy_id> o CANDIDATE#<candidate_id>
                 ◦ Ejemplo JSON DynamoDB:
                   {
                       "PK": "TENANT#t-1001",
                       "SK": "CANDIDATE#c-99482",
                       "vacancy_id": "v-302",
                       "full_name": "Maria Garcia",
                       "email": "maria@gmail.com",
                       "stage": "INTERVIEW",
                       "resume_s3_key": "t-1001/recruitment/resumes/c-99482.pdf",
                       "created_at": "2026-11-01T10:00:00Z"
                   }
            • Endpoints REST:
                 ◦ POST /vacancies | Body: { "title": "Senior Cloud Engineer", "department": "IT" }
                 ◦ GET /vacancies | Query Params: ?status=OPEN
                 ◦ POST /candidates | Body: { "vacancyId": "v-302", "fullName": "Maria Garcia", "email": "maria@gmail.com" }
                 ◦ PATCH /candidates/{id}/stage | Body: { "stage": "HIRED" }
            • Integración EDA:
                 ◦ Publica en SNS: sns-recruitment-events → Evento: candidate.hired (Payload: { tenant_id, candidate_id, fullName, email, position }).
                 ◦ Consume de SQS: N/A.
            • Almacenamiento S3:
                 ◦ Ruta: s3://hcm-app-storage/{tenant_id}/recruitment/resumes/{candidate_id}_cv.pdf
          3. Microservicio de Nóminas y Compensaciones (ms-payroll)
            • Alcance: Cálculo de salarios, descuentos de ley, bonificaciones y generación de boletas de pago.
            • Modelo de Datos (RDS PostgreSQL - Schema per Tenant):
              -- Schema: tenant_a / tenant_b / tenant_c
              CREATE TABLE payroll_periods (
                  period_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  period_name VARCHAR(20) NOT NULL, -- Ej: '2026-11'
                  is_closed BOOLEAN DEFAULT FALSE
              );
              CREATE TABLE pay_slips (
                  pay_slip_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  period_id UUID REFERENCES payroll_periods(period_id),
                  employee_id UUID NOT NULL,
                  base_salary NUMERIC(10, 2) NOT NULL,
                  deductions NUMERIC(10, 2) DEFAULT 0.00,
                  net_pay NUMERIC(10, 2) NOT NULL,
                  generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              );
            • Endpoints REST:
                 ◦ POST /payrolls/calculate | Body: { "period": "2026-11" }
                 ◦ GET /payrolls/{period_id} | Path Param: period_id
                 ◦ GET /payrolls/employee/{employee_id} | Path Param: employee_id
            • Integración EDA:
                 ◦ Publica en SNS: sns-payroll-events → Evento: payroll.processed (Payload: { tenant_id, period_id, total_paid }).
                 ◦ Consume de SQS: sqs-payroll-hr-sync (Suscrito a sns-hr-events). Al crearse un empleado en Core HR, registra automáticamente su perfil salarial en Nóminas.
            • Almacenamiento S3:
                 ◦ Ruta: s3://hcm-app-storage/{tenant_id}/payroll/slips/{period_id}/{employee_id}.pdf
          4. Microservicio de Gestión del Desempeño (ms-performance)
            • Alcance: Creación de ciclos de evaluación, asignación de objetivos (OKRs) y registro de evaluaciones 360°.
            • Modelo de Datos (DynamoDB - Single Table Design):
                 ◦ Partition Key (PK): TENANT#<tenant_id>
                 ◦ Sort Key (SK): EVAL#<eval_id> o GOAL#<goal_id>
                 ◦ Ejemplo JSON DynamoDB:
                   {
                       "PK": "TENANT#t-1001",
                       "SK": "EVAL#e-8812",
                       "employee_id": "emp-102",
                       "evaluator_id": "emp-005",
                       "score": 4.8,
                       "feedback": "Excelente desempeño en la migración a Serverless.",
```

## Página 3

```text
Firefox                                                                                                                                                                                     about:blank
                       "cycle": "2026-Q3"
                   }
            • Endpoints REST:
                 ◦ POST /evaluations | Body: { "employeeId": "emp-102", "evaluatorId": "emp-005", "score": 4.8, "cycle": "2026-Q3" }
                 ◦ GET /evaluations/employee/{emp_id} | Path Param: emp_id
                 ◦ POST /goals | Body: { "employeeId": "emp-102", "title": "AWS Certification", "targetDate": "2026-12-01" }
            • Integración EDA:
                 ◦ Publica en SNS: sns-performance-events → Evento: evaluation.completed (Payload: { tenant_id, employee_id, score }).
                 ◦ Consume de SQS: N/A.
            • Almacenamiento S3:
                 ◦ Ruta: s3://hcm-app-storage/{tenant_id}/performance/evidences/{eval_id}_evidence.zip
          5. Microservicio de Asistencia y Licencias (ms-attendance)
            • Alcance: Control de marcaciones de entrada/salida, gestión de permisos, vacaciones y licencias médicas.
            • Modelo de Datos (DynamoDB - Time-Series Access Pattern):
                 ◦ Partition Key (PK): TENANT#<tenant_id>
                 ◦ Sort Key (SK): ATTENDANCE#<employee_id>#<YYYY-MM-DD> o LEAVE#<leave_id>
                 ◦ Ejemplo JSON DynamoDB:
                   {
                       "PK": "TENANT#t-1001",
                       "SK": "ATTENDANCE#emp-102#2026-11-01",
                       "employee_id": "emp-102",
                       "check_in": "2026-11-01T08:01:10Z",
                       "check_out": "2026-11-01T17:05:22Z",
                       "status": "PRESENT"
                   }
            • Endpoints REST:
                 ◦ POST /attendance/clock-in | Body: { "employeeId": "emp-102", "timestamp": "2026-11-01T08:01:10Z" }
                 ◦ POST /attendance/clock-out | Body: { "employeeId": "emp-102", "timestamp": "2026-11-01T17:05:22Z" }
                 ◦ POST /leaves/request | Body: { "employeeId": "emp-102", "startDate": "2026-12-01", "endDate": "2026-12-15", "type": "VACATION" }
            • Integración EDA:
                 ◦ Publica en SNS: sns-attendance-events → Evento: leave.approved (Payload: { tenant_id, employee_id, days_unpaid }).
                 ◦ Consume de SQS: sqs-payroll-attendance-sync (Utilizado por Nóminas para descontar días no trabajados).
            • Almacenamiento S3:
                 ◦ Ruta: s3://hcm-app-storage/{tenant_id}/attendance/medical-slips/{leave_id}_cert.jpg
          BLOQUE 3: Arquitectura Serverless & Patrón Multi-Tenant
          1. Estrategia de Aislamiento Multi-Tenant
          [Cliente React / Amplify]
                 │
                 ▼ (Bearer JWT con claim custom:tenant_id)
          [AWS API Gateway] ──► [Cognito Authorizer] (Valida Firma y Expira)
                 │
                 ▼ (Pasa Claims en event.requestContext.authorizer.claims)
          [AWS Lambda Function]
                 │
                 ├─────────────────────────────────────────┐
                 ▼ (Si BD es RDS PostgreSQL)               ▼ (Si BD es DynamoDB)
          Ejecuta al abrir conexión:               Fuerza la consulta con:
          "SET search_path TO tenant_<tenant_id>"   KeyConditionExpression:
          Operaciones aisladas por schema.         PK = "TENANT#<tenant_id>"
            1. Inyección de Identidad: AWS Cognito inserta la propiedad custom:tenant_id dentro del token JWT entregado al usuario tras autenticarse.
            2. Autorización en Borde: API Gateway valida la firma del token mediante el Cognito Authorizer. Si es válido, inyecta la identidad en el contexto de la ejecución Lambda:
               event.requestContext.authorizer.claims['custom:tenant_id']
            3. Propagación en Código (Guardrails):
                 ◦ Para RDS PostgreSQL: Al obtener una conexión del pool, la Lambda ejecuta inmediatamente: SET search_path TO tenant_<tenant_id>; Esto redirige dinámicamente las consultas al
                   esquema aislado correspondiente del tenant sin modificar el SQL.
                 ◦ Para DynamoDB: Todas las peticiones inyectan PK = TENANT#<tenant_id> en la condición de llave. Se programa un middleware en Lambda que rechaza cualquier payload cuyo
                   tenant_id no coincida con el claim del JWT.
          2. Diagrama Flujo Completo End-to-End
          +-----------------------------------------------------------------------------------+
          |                                  FRONTEND (AWS Amplify)                           |
          |                        React App (SPA) con AWS Amplify SDK                        |
          +-----------------------------------------------------------------------------------+
                                                    │ (HTTP REST + JWT Token)
                                                    ▼
          +-----------------------------------------------------------------------------------+
          |                                 AWS API GATEWAY                                   |
          |                       (HTTP API / Cognito Authorizer)                             |
          +-----------------------------------------------------------------------------------+
                                                    │ (Inyecta context.tenant_id)
                                                    ▼
          +-----------------------------------------------------------------------------------+
          |                                 AWS LAMBDA (Backend)                              |
          |                  Ejecuta lógica de negocio + validación multi-tenant                |
          +-----------------------------------------------------------------------------------+
                  │                                   │                              │
                  │ (Lectura/Escritura SQL)           │ (Lectura/Escritura NoSQL)    │ (Archivos)
                  ▼                                   ▼                              ▼
```

## Página 4

```text
Firefox                                                                                                                                                                                     about:blank
          +---------------+                  +---------------+               +----------------+
          | Amazon RDS    |                  | Amazon Dynamo |               |   Amazon S3    |
          | (PostgreSQL) |                   | (Single-Tbl) |                | (Bucket Único) |
          | Schema Tenant |                  | PK: TENANT#id |               | /{tenant_id}/* |
          +---------------+                  +---------------+               +----------------+
                  │
                  │ (Publica evento)
                  ▼
          +-----------------------------------------------------------------------------------+
          |                                  AWS SNS TOPIC                                    |
          |                              (Publicador de Eventos)                              |
          +-----------------------------------------------------------------------------------+
                                                    │ (Fan-out a Colas)
                                                    ▼
          +-----------------------------------------------------------------------------------+
          |                                  AWS SQS QUEUE                                    |
          |                             (Cola Desacoplada + DLQ)                              |
          +-----------------------------------------------------------------------------------+
                                                    │ (Event Source Mapping)
                                                    ▼
          +-----------------------------------------------------------------------------------+
          |                               AWS LAMBDA WORKER                                   |
          |                          (Procesador asíncrono secundario)                        |
          +-----------------------------------------------------------------------------------+
          BLOQUE 4: División del Trabajo Fina para 5 Personas (WBS)
          Asignación de Roles y Responsabilidades
          +-----------------------------------------------------------------------------------+
          |                               ESTRUCTURA DE EQUIPO (5 ROLES)                       |
          +-----------------------------------------------------------------------------------+
          | [Rol 1] DevOps & Infrastructure Lead        --> Infraestructura IaC, Cognito, Amplify |
          | [Rol 2] Core BackEnd Engineer 1 (RDS)       --> Core HR, Nóminas, Schemas PostgreSQL|
          | [Rol 3] Core BackEnd Engineer 2 (DynamoDB) --> Reclutamiento, Desempeño, NoSQL     |
          | [Rol 4] Event & Data Engineer               --> Asistencia, Eventos SNS/SQS, Seed 30k |
          | [Rol 5] FrontEnd & UX Lead                  --> React App, Amplify SDK, Dashboard |
          +-----------------------------------------------------------------------------------+
          Rol 1: DevOps & Infrastructure Lead
             • Entregables: Plantillas base de serverless.yml, pipeline CI/CD en GitHub Actions, configuración de Cognito User Pool (Custom Claims), S3 Bucket central y redes/seguridad.
             • Dependencias: Provee las variables de entorno de ARN de SNS/SQS y endpoints de API Gateway a los desarrolladores Backend y Frontend.
             • Plan Semanal:
                  ◦ Semana 11: Configurar repositorio base, Serverless Framework y AWS Cognito User Pools con custom claim tenant_id.
                  ◦ Semana 12: Desplegar API Gateway central, Buckets S3 con políticas IAM multi-tenant y AWS Amplify Hosting.
                  ◦ Semana 13: Automatizar despliegue de SNS Topics y SQS Queues mediante serverless.yml.
                  ◦ Semana 14: Integración completa de IaC para el Avance Virtual (30% funcional).
                  ◦ Semana 15: Pruebas de carga infra, revisión de roles IAM de Lambdas y CloudWatch Dashboards.
                  ◦ Semana 16: Congelamiento de código (Code Freeze), apoyo en script de demostración presencial.
          Rol 2: Core BackEnd Engineer 1 (RDS & Financial Domain)
             • Entregables: Microservicios ms-core-hr y ms-payroll. Scripts DDL para PostgreSQL RDS con separación por Schemas.
             • Dependencias: Consume claims de Cognito (Rol 1); emite eventos para SQS (Rol 4).
             • Plan Semanal:
                  ◦ Semana 11: Diseñar modelo relacional PostgreSQL y scripts de creación de Schemas (tenant_a, tenant_b, tenant_c).
                  ◦ Semana 12: Desarrollar Lambdas CRUD de ms-core-hr utilizando el middleware de aislamiento de schema (SET search_path).
                  ◦ Semana 13: Desarrollar cálculo de nómina en ms-payroll y generación de datos en PDF.
                  ◦ Semana 14: Desplegar endpoints de Core HR y Nómina comprobados para el Avance Virtual.
                  ◦ Semana 15: Integrar consumo de colas SQS para sincronización Core HR -> Nómina.
                  ◦ Semana 16: Optimización de consultas SQL e índices para la demo final.
          Rol 3: Core BackEnd Engineer 2 (DynamoDB & Talent Domain)
             • Entregables: Microservicios ms-recruitment y ms-performance. Diseño Single-Table en DynamoDB.
             • Dependencias: Requiere buckets de S3 configurados por Rol 1 para subida de CVs y evidencias.
             • Plan Semanal:
                  ◦ Semana 11: Diseñar estrategias de Partition/Sort Keys para DynamoDB Single-Table Design.
                  ◦ Semana 12: Implementar Lambdas CRUD de ms-recruitment con subida presigned URLs a Amazon S3.
                  ◦ Semana 13: Desarrollar lógica de ms-performance (evaluaciones y asignación de OKRs).
                  ◦ Semana 14: Despliegue de endpoints de Reclutamiento y Desempeño para el Avance Virtual.
                  ◦ Semana 15: Validación estricta de PKs (TENANT#<tenant_id>) para evitar fugas entre tenants.
                  ◦ Semana 16: Refinamiento de respuestas API y manejo de errores.
          Rol 4: Event & Data Engineer (EDA, Attendance & Seeding)
             • Entregables: Microservicio ms-attendance, integración SNS/SQS (Workers), script de Seeding masivo de 30,000 registros por microservicio.
             • Dependencias: Requiere esquemas de BD de Rol 2 y Rol 3 finalizados para ejecutar scripts de carga.
             • Plan Semanal:
                  ◦ Semana 11: Desarrollar el microservicio ms-attendance en DynamoDB con marcaciones en tiempo real.
                  ◦ Semana 12: Implementar handlers de SNS/SQS para procesar eventos asíncronos en background (Worker Lambdas).
```

## Página 5

```text
Firefox                                                                                                                                                                                   about:blank
                  ◦ Semana 13: Diseñar script de carga masiva en Python (Faker + Boto3 / psycopg2) desacoplado de la API.
                  ◦ Semana 14: Ejecutar primera carga masiva de prueba (10,000 registros x 3 tenants x 5 microservicios = 150,000 registros en total).
                  ◦ Semana 15: Implementar manejo de Dead Letter Queues (DLQ) e idempotencia en eventos.
                  ◦ Semana 16: Validar la carga de 30,000 registros por microservicio previa a la demo presencial.
          Rol 5: FrontEnd & UX Lead
             • Entregables: Aplicación Web Single Page (SPA) en React desplegada en AWS Amplify. Componentes de UI con soporte multi-tenant y ACL (Control de Acceso Basado en Roles).
             • Dependencias: Consume endpoints REST expuestos por los roles Backend (2, 3, 4).
             • Plan Semanal:
                  ◦ Semana 11: Construir estructura del proyecto React con interfaz adaptable y sistema de diseño.
                  ◦ Semana 12: Conectar autenticación de AWS Cognito usando AWS Amplify SDK (manejo de tokens JWT).
                  ◦ Semana 13: Desarrollar módulos UI para Core HR y Reclutamiento (tablas, formularios, subida de CVs).
                  ◦ Semana 14: Implementar selector de Tenant para pruebas y visualización de permisos (Avance Virtual).
                  ◦ Semana 15: Desarrollar pantallas de Nóminas, Desempeño y Asistencia; integrar visualizador de PDFs en S3.
                  ◦ Semana 16: Pulido visual, manejo de estados de carga y pruebas de simulación multi-tenant para la Demo.
          BLOQUE 5: Estrategia de Seeding de Datos (30,000 Registros por Microservicio)
          Plan Técnico de Carga Masiva
          Para insertar 30,000 registros por microservicio (10,000 por cada uno de los 3 tenants) sin agotar timeouts ni recursos:
             1. Conexión Directa: El script se ejecuta localmente o dentro de un contenedor en AWS CloudShell/ECS conectado a la VPC de RDS y DynamoDB.
             2. PostgreSQL (RDS): Uso de inserciones en bloque con psycopg2.extras.execute_values en lotes de 2,000 filas por transacción.
             3. DynamoDB: Uso de batch_write_item en lotes de 25 elementos (límite de la API de DynamoDB) con hilos concurrentes.
          Script Sugerido en Python (seed_data.py)
          import os
          import uuid
          import random
          from datetime import datetime, timedelta
          from faker import Faker
          import psycopg2
          from psycopg2.extras import execute_values
          import boto3
          fake = Faker()
          TENANTS = ['tenant_a', 'tenant_b', 'tenant_c']
          RECORDS_PER_TENANT = 10000
          # ----------------------------------------------------------------
          # 1. SEEDING RDS POSTGRESQL (Core HR)
          # ----------------------------------------------------------------
          def seed_rds_core_hr():
              conn = psycopg2.connect(
                  host=os.getenv("DB_HOST", "localhost"),
                  database=os.getenv("DB_NAME", "hcm_db"),
                  user=os.getenv("DB_USER", "postgres"),
                  password=os.getenv("DB_PASS", "password")
              )
              cursor = conn.cursor()
               for tenant in TENANTS:
                   print(f"Cargando 10,000 empleados en RDS para schema: {tenant}...")
                   cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {tenant};")
                   cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {tenant}.employees (
                            employee_id UUID PRIMARY KEY,
                            first_name VARCHAR(50),
                            last_name VARCHAR(50),
                            email VARCHAR(100),
                            hire_date DATE,
                            status VARCHAR(20)
                        );
                   """)
                    employees_data = []
                    for _ in range(RECORDS_PER_TENANT):
                        emp_id = str(uuid.uuid4())
                        fname = fake.first_name()
                        lname = fake.last_name()
                        email = f"{fname.lower()}.{lname.lower()}_{random.randint(1,99999)}@{tenant}.com"
                        hire_date = fake.date_between(start_date='-5y', end_date='today')
                        status = 'ACTIVE'
                        employees_data.append((emp_id, fname, lname, email, hire_date, status))
                    query = f"INSERT INTO {tenant}.employees (employee_id, first_name, last_name, email, hire_date, status) VALUES %s"
                    execute_values(cursor, query, employees_data, page_size=2000)
                    conn.commit()
               cursor.close()
               conn.close()
               print("RDS Core HR Seeding completado exitosamente.")
          # ----------------------------------------------------------------
          # 2. SEEDING DYNAMODB (Reclutamiento)
          # ----------------------------------------------------------------
          def seed_dynamodb_recruitment():
              dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
              table = dynamodb.Table('ms-recruitment-table')
               for tenant in TENANTS:
                   print(f"Cargando 10,000 postulantes en DynamoDB para tenant: {tenant}...")
                   with table.batch_writer() as batch:
                       for _ in range(RECORDS_PER_TENANT):
                           cand_id = f"c-{uuid.uuid4().hex[:8]}"
                           batch.put_item(
```

## Página 6

```text
Firefox                                                                                                                                                                                                              about:blank
                                    Item={
                                        'PK': f"TENANT#{tenant}",
                                        'SK': f"CANDIDATE#{cand_id}",
                                        'full_name': fake.name(),
                                        'email': fake.email(),
                                        'stage': random.choice(['APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED']),
                                        'created_at': datetime.utcnow().isoformat()
                                    }
                           )
               print("DynamoDB Recruitment Seeding completado exitosamente.")
          if __name__ == "__main__":
              seed_rds_core_hr()
              seed_dynamodb_recruitment()
          BLOQUE 6: Plan de Pruebas y Script para la Demo Presencial
          Guión de Demostración Presencial (Semana 16) - 10 Minutos
          [Inicio de la Demo]
            │
            ├─► Paso 1: Autenticación e Inspección del JWT
            │    └─ Iniciar sesión como Tenant A -> Decodificar JWT -> Mostrar custom:tenant_id = tenant_a
            │
            ├─► Paso 2: Consulta e Inserción de Datos (Tenant A)
            │    └─ Crear empleado "Carlos A." en Tenant A -> Validar presencia en la grilla
            │
            ├─► Paso 3: Cambio de Contexto a Tenant B
            │    └─ Iniciar sesión como Tenant B -> Decodificar JWT -> Mostrar custom:tenant_id = tenant_b
            │
            ├─► Paso 4: Demostración Estricta de Aislamiento
            │    ├─ Comprobar que la grilla de Tenant B NO muestra a "Carlos A."
            │    ├─ Ejecutar consulta API manual del ID de "Carlos A." usando el Token de B
            │    └─ Resultado esperado: HTTP 404 / 403 Access Denied
            │
            ├─► Paso 5: Prueba de Desacoplamiento por Eventos (SNS/SQS)
            │    └─ Aprobar vacaciones en Asistencia -> Evento enviado a SNS -> SQS lo procesa en Nóminas
            │
            └─► Paso 6: Verificación de Almacenamiento S3 Aislado
                 └─ Subir contrato PDF en Tenant A -> Verificar bucket path /tenant_a/core-hr/contracts/
          [Fin de la Demo]
          Paso 1: Autenticación e Inspección de Token JWT (2 Minutos)
             1. Abrir la aplicación desplegada en AWS Amplify.
             2. Iniciar sesión con la cuenta admin@empresa_a.com (Tenant A).
             3. Abrir las herramientas de desarrollador del navegador (DevTools → Application → LocalStorage) o usar jwt.io en pantalla para mostrar el Payload del Token ID.
             4. Punto a destacar al evaluador: Mostrar explícitamente el claim "custom:tenant_id": "tenant_a".
          Paso 2: Creación de Registros en Tenant A (2 Minutos)
             1. Ir al módulo Core HR y registrar un nuevo empleado llamado Juan Perez (Tenant A).
             2. Subir un archivo de contrato en formato PDF.
             3. Confirmar que el empleado aparece registrado en la tabla del dashboard.
          Paso 3: Conmutación y Prueba de Aislamiento en Tenant B (3 Minutos)
             1. Cerrar sesión e iniciar sesión como admin@empresa_b.com (Tenant B).
             2. Inspeccionar el token y verificar "custom:tenant_id": "tenant_b".
             3. Navegar al módulo Core HR: Verificar que la lista muestre únicamente los datos de Tenant B y que NO aparezca Juan Perez (Tenant A).
             4. Prueba Cruzada (Seguridad): Tomar el ID del empleado Juan Perez e intentar consultar manualmente la API usando Postman o curl inyectando el token JWT de Tenant B: GET /employees/
                {id_juan_perez} con Authorization: Bearer <JWT_TENANT_B>
             5. Resultado esperado: Retorno de código de estado HTTP 404 Not Found o HTTP 403 Forbidden debido a la condición WHERE schema / PK = tenant_b.
          Paso 4: Demostración EDA e Integración S3 (3 Minutos)
             1. En Tenant B, ir al módulo de Reclutamiento, seleccionar un candidato y cambiar su estado a HIRED.
             2. Abrir AWS CloudWatch Logs en la consola AWS para mostrar la ejecución en segundo plano:
                   ◦ SNS Topic: Evento candidate.hired publicado.
                   ◦ SQS Queue: Mensaje recibido por sqs-payroll-hr-sync.
                   ◦ Lambda Worker: Proceso asíncrono que creó la plantilla del empleado en Nóminas automáticamente.
             3. Abrir la consola de AWS S3 y mostrar la estructura del bucket s3://hcm-app-storage/:
                   ◦ Navegar a /tenant_a/core-hr/contracts/ para ver el PDF de Juan Perez.
                   ◦ Verificar que la carpeta /tenant_b/ se encuentra completamente segregada a nivel de almacenamiento.
          ¿Deseas que profundicemos en el desarrollo del archivo serverless.yml unificado para la infraestructura como código o prefieres revisar en detalle la configuración del Cognito Custom Authorizer?
          User prompt: Actúa como un Lead Cloud Architect y Scrum Master. Con base en la arquitectura definida para nuestro SaaS HCM en AWS (5 microservicios, RDS/DynamoDB, S3, SNS, SQS, Amplify y Serverless
          Framework), genera una distribución de trabajo hiperdetallada y ejecutable para un equipo de 5 integrantes. Para cada uno de los 5 integrantes, proporciona: 1. Rol asignado y alcance claro de responsabilidad.
          2. Microservicios o componentes a su cargo (Frontend, Core HR, Reclutamiento, Nómina, Desempeño, Asistencia/Eventos). 3. Entregables de código exactos (archivos serverless.yml, scripts de base de datos,
          Lambdas, componentes de React). 4. Matriz de dependencias: De quién depende para empezar a programar y a quién le entrega resultados (contratos de API). 5. Plan de trabajo semana a semana (Semana 11 a
          Semana 16), indicando qué debe tener listo para el Avance Virtual del 30% (Semana 14) y para la Entrega Final (Semana 15/16). 6. Tareas específicas asignadas para cumplir los requerimientos críticos de la
          rúbrica: los 30,000 registros por microservicio, el aislamiento multi-tenant y la prueba de la demo en vivo con 2 tenants.
          Response: Integrante 1: DevOps & Infrastructure Lead
          1. Rol Asignado y Alcance de Responsabilidad
             • Rol: Lead DevOps & Cloud Infrastructure Engineer.
             • Alcance: Creación y mantenimiento de la infraestructura base como código (IaC) mediante Serverless Framework, aprovisionamiento de AWS Cognito (User Pools y Client Credentials), integración
```

## Página 7

```text
Firefox                                                                                                                                                                                            about:blank
              continua en AWS Amplify Hosting, políticas IAM globales de seguridad multi-tenant y configuración de observabilidad en CloudWatch.
          2. Componentes y Microservicios a su Cargo
            • AWS Cognito: User Pool multi-tenant con atributos personalizados (custom:tenant_id, custom:role).
            • AWS Amplify Hosting: Conexión del repositorio Git y variables de entorno para CI/CD.
            • Amazon S3 Central: Bucket hcm-app-storage y definición de Bucket Policies por prefijo de tenant.
            • IaC Global: Plantillas compartidas de CloudFormation/Serverless Framework (serverless-common.yml).
          3. Entregables de Código Exactos
            • infrastructure/cognito-user-pool.yml: Definición de Cognito User Pool, Client App y Custom Attribute custom:tenant_id.
            • infrastructure/s3-storage.yml: Definición del bucket de S3 con políticas IAM de aislamiento por ruta /{tenant_id}/*.
            • serverless-common.yml: Configuración centralizada de plugins (serverless-iam-roles-per-function, serverless-prune-plugin), provider y variables de entorno globales.
            • .github/workflows/deploy-infra.yml: Pipeline CI/CD para automatizar el despliegue de IaC por ambientes (dev, prod).
          4. Matriz de Dependencias
          [Integrante 1 (DevOps)] ──(Entrega Cognito Authorizer ARN + S3 Bucket Name)──► Integrantes 2, 3, 4
          [Integrante 1 (DevOps)] ──(Entrega Amplify Hosting URL + User Pool Client ID)─► Integrante 5 (FrontEnd)
            • Depende de: Nadie (Es el bloqueador principal para el inicio del desarrollo).
            • Entrega a:
                 ◦ Integrantes 2, 3 y 4: Cognito Authorizer ARN, API Gateway HTTP API ID central, S3 Bucket ARN y Roles IAM base.
                 ◦ Integrante 5: App Client ID de Cognito, URL de AWS Amplify Hosting y endpoints base de API Gateway.
          5. Plan de Trabajo Semana a Semana (Semana 11 a 16)
            • Semana 11: Configurar repositorio base de Git, pipeline CI/CD en GitHub Actions y aprovisionamiento de AWS Cognito con la claim custom:tenant_id.
            • Semana 12: Desplegar AWS Amplify Hosting conectado a React y definir la plantilla s3-storage.yml con el aislamiento por prefijo.
            • Semana 13: Configurar el API Gateway central HTTP y el Authorizer JWT de Cognito desacoplado en Serverless Framework.
            • Semana 14 (Avance Virtual - 30%): Tener la infraestructura base 100% automatizada en IaC: Cognito emitiendo JWTs con custom:tenant_id, Amplify desplegando el frontend y S3 accesible.
            • Semana 15: Implementar métricas centrales en Amazon CloudWatch, alarmas de facturación/errores y retención de logs.
            • Semana 16: Congelamiento de infraestructura (Infra Freeze), auditoría de políticas IAM y apoyo técnico en el monitoreo durante la Demo Presencial.
          6. Tareas Específicas para Criterios Críticos de la Rúbrica
            • Aislamiento Multi-Tenant: Configurar el Trigger Pre-Token Generation en Lambda/Cognito o la inyección obligatoria del atributo custom:tenant_id en el registro de usuarios.
            • Demo Presencial: Crear scripts CLI de AWS (create-demo-tenants.sh) para aprovisionar instantáneamente 2 usuarios de prueba (user_tenant_a@test.com y user_tenant_b@test.com)
              con tokens válidos.
          Integrante 2: Core BackEnd Engineer 1 (RDS PostgreSQL)
          1. Rol Asignado y Alcance de Responsabilidad
            • Rol: Senior Database & Backend Developer (Relational Domain).
            • Alcance: Diseño del modelo relacional en Amazon RDS PostgreSQL utilizando el patrón Single Database, Multiple Schemas, desarrollo completo de los microservicios ms-core-hr y ms-payroll, e
              implementación del middleware de aislamiento SQL por schema dinámico.
          2. Componentes y Microservicios a su Cargo
            • Microservicio 1: Core HR (ms-core-hr) — Empresas, Departamentos, Puestos, Empleados y Contratos.
            • Microservicio 3: Nóminas y Compensaciones (ms-payroll) — Periodos de pago, Conceptos salariales, Boletas de pago.
            • Base de Datos: Amazon RDS PostgreSQL (Instancia db.t4g.micro / Serverless v2).
          3. Entregables de Código Exactos
            • services/core-hr/serverless.yml: Definición de Lambdas y endpoints REST para la gestión de empleados.
            • services/payroll/serverless.yml: Definición de Lambdas de procesamiento de nómina y generación de boletas.
            • db/migrations/001_initial_schema.sql: DDL estructurado para crear esquemas (tenant_a, tenant_b, tenant_c) y tablas (departments, employees, contracts, pay_slips).
            • shared/middlewares/dbTenantMiddleware.js: Driver de conexión que ejecuta SET search_path TO tenant_<tenant_id> automáticamente por cada invocación a Lambda.
            • services/core-hr/handlers/ (createEmployee.js, getEmployees.js, getContractPdf.js).
            • services/payroll/handlers/ (calculatePayroll.js, getPaySlip.js).
          4. Matriz de Dependencias
          [Integrante 1] ──(Inyecta Tenant ID via Authorizer)──► [Integrante 2 (RDS Backend)]
          [Integrante 4] ──(Mensaje SQS leave.approved)───────► [Integrante 2 (ms-payroll)]
          [Integrante 2] ──(Contratos API REST /employees)────► [Integrante 5 (FrontEnd)]
            • Depende de: Integrante 1 (Cognito Authorizer y conexión RDS base) e Integrante 4 (Consumo de eventos de Asistencia/Licencias en SQS).
            • Entrega a: Integrante 5 (Endpoints REST /employees, /contracts, /payrolls) e Integrante 4 (Tablas RDS listas para Seeding).
          5. Plan de Trabajo Semana a Semana (Semana 11 a 16)
            • Semana 11: Diseñar el modelo Entidad-Relación relacional y probar el script DDL multi-schema (tenant_a, tenant_b, tenant_c).
            • Semana 12: Desarrollar dbTenantMiddleware.js y las Lambdas CRUD del microservicio ms-core-hr con aislamiento por schema.
            • Semana 13: Implementar el motor de cálculo salarial en ms-payroll y la generación de archivos PDF de boletas de pago hacia S3.
            • Semana 14 (Avance Virtual - 30%): Microservicio ms-core-hr 100% operativo con endpoints probados bajo aislamiento de schemas.
            • Semana 15: Implementar la lectura de colas SQS en ms-payroll para descontar licencias no pagadas emitidas por el microservicio de Asistencia.
```

## Página 8

```text
Firefox                                                                                                                                                                                                 about:blank
            • Semana 16: Optimizar índices SQL (CREATE INDEX idx_emp_tenant) para soportar consultas con 10,000 registros por schema.
          6. Tareas Específicas para Criterios Críticos de la Rúbrica
            • 30,000 Registros: Optimizar el pool de conexiones en RDS (pg-pool) para que los endpoints respondan en < 200ms ante tablas de 10,000 empleados por schema.
            • Aislamiento Multi-Tenant: Implementar pruebas unitarias de aislamiento en Jest/PyTest que verifiquen que SET search_path no permita fuga de datos entre conexiones concurrentes.
          Integrante 3: Core BackEnd Engineer 2 (DynamoDB NoSQL)
          1. Rol Asignado y Alcance de Responsabilidad
            • Rol: Senior NoSQL & Serverless Backend Developer.
            • Alcance: Diseño del patrón Single-Table Design en Amazon DynamoDB con aislamiento estricto por Partition Key (TENANT#<tenant_id>), y desarrollo completo de los microservicios ms-
              recruitment y ms-performance.
          2. Componentes y Microservicios a su Cargo
            • Microservicio 2: Reclutamiento y Selección (ms-recruitment) — Vacantes, Postulantes y Pipeline de Selección.
            • Microservicio 4: Gestión del Desempeño (ms-performance) — Evaluación 360°, OKRs y Feedback.
            • Base de Datos: Amazon DynamoDB (Tablas de diseño Single-Table).
          3. Entregables de Código Exactos
            • services/recruitment/serverless.yml: Definición de Lambdas, API Gateway y tabla DynamoDB ms-recruitment-table.
            • services/performance/serverless.yml: Definición de Lambdas y tabla DynamoDB ms-performance-table.
            • shared/helpers/dynamoTenantFilter.js: Enforcer que autoinyecta PK = TENANT#<tenant_id> en todos los KeyConditionExpression y payloads de actualización.
            • services/recruitment/handlers/ (createVacancy.js, createCandidate.js, uploadResumePresignedUrl.js, updateStage.js).
            • services/performance/handlers/ (createGoal.js, submitEvaluation.js, getEmployeePerformance.js).
          4. Matriz de Dependencias
          [Integrante 1] ──(Cognito JWT + S3 Presigned URL Role)──► [Integrante 3 (NoSQL Backend)]
          [Integrante 3] ──(Publica evento candidate.hired)──────► [AWS SNS Topic] ──► [Integrante 4]
          [Integrante 3] ──(Contratos API /vacancies, /evals)────► [Integrante 5 (FrontEnd)]
            • Depende de: Integrante 1 (Cognito Authorizer y permisos IAM S3).
            • Entrega a: Integrante 4 (Emisión del evento SNS candidate.hired) e Integrante 5 (Endpoints REST de Reclutamiento y Desempeño).
          5. Plan de Trabajo Semana a Semana (Semana 11 a 16)
            • Semana 11: Diseñar la estrategia de claves de DynamoDB (PK: TENANT#<tenant_id>, SK: VACANCY#<id> / CANDIDATE#<id> / EVAL#<id>).
            • Semana 12: Implementar Lambdas de ms-recruitment y la generación de Presigned URLs para subir Curriculum Vitae (PDF) a S3.
            • Semana 13: Desarrollar ms-performance (creación de objetivos OKRs y registro de evaluaciones 360).
            • Semana 14 (Avance Virtual - 30%): Microservicio ms-recruitment desplegado y funcional con subida directa de archivos a S3 aislada por tenant.
            • Semana 15: Configurar la publicación del evento SNS candidate.hired en ms-recruitment al cambiar el estado de un postulante.
            • Semana 16: Afinamiento de Global Secondary Indexes (GSI) en DynamoDB para garantizar búsquedas eficientes en datasets de 30,000 registros.
          6. Tareas Específicas para Criterios Críticos de la Rúbrica
            • Aislamiento Multi-Tenant: Implementar una regla estricta en el dynamoTenantFilter.js que rechace cualquier solicitud si el tenant_id recibido en el Body/Path difiere del
              custom:tenant_id del token JWT.
            • Almacenamiento S3: Validar que la subida de currículums use la ruta s3://hcm-app-storage/{tenant_id}/recruitment/resumes/{candidate_id}.pdf.
          Integrante 4: Event & Data Engineer
          1. Rol Asignado y Alcance de Responsabilidad
            • Rol: Event-Driven Architecture (EDA) & Data Seeding Specialist.
            • Alcance: Implementación de la mensajería asíncrona mediante AWS SNS (Topics) y AWS SQS (Colas/DLQ), desarrollo del microservicio ms-attendance y creación/ejecución de los scripts de
              seeding masivo de 30,000 registros por microservicio.
          2. Componentes y Microservicios a su Cargo
            • Microservicio 5: Asistencia y Licencias (ms-attendance) — Marcaciones time-series y solicitudes de vacaciones/licencias.
            • EDA Messaging: AWS SNS Topics (sns-hr-events, sns-recruitment-events, sns-attendance-events) y AWS SQS Queues (sqs-payroll-sync, sqs-core-sync con sus Dead Letter
              Queues).
            • Data Pipelines: Scripts masivos de generación e inserción de datos en Python.
          3. Entregables de Código Exactos
            • events/serverless-events.yml: IaC con la definición declarativa de Topics SNS, Queues SQS, DLQs y suscripciones Fan-out.
            • services/attendance/serverless.yml: Lambdas de marcaciones y licencias médicos en DynamoDB.
            • scripts/seed_master.py: Script híbrido en Python (usando Faker, psycopg2.extras.execute_values y boto3.dynamodb.batch_write_item) para insertar 150,000 registros en total.
            • services/attendance/handlers/ (clockIn.js, clockOut.js, requestLeave.js, processLeaveEventWorker.js).
          4. Matriz de Dependencias
          [Integrantes 2 y 3] ──(Definición de Schemas/Tablas)──► [Integrante 4 (Data & Events)]
          [Integrante 4] ──────(Envía eventos SQS a Nóminas)────► [Integrante 2 (ms-payroll)]
          [Integrante 4] ──────(Puebla 30k datos en las BDs)───► Integrantes 2, 3, 5
            • Depende de: Integrantes 2 y 3 (Estructuras finales de bases de datos para programar los scripts de seeding y los handlers de SQS).
            • Entrega a: Integrante 2 (Cola SQS funcional para Nóminas), Integrante 5 (Endpoints REST /attendance) y a todo el equipo (Base de datos poblada con 30,000 registros por microservicio).
          5. Plan de Trabajo Semana a Semana (Semana 11 a 16)
```

## Página 9

```text
Firefox                                                                                                                                                                                                                  about:blank
             • Semana 11: Diseñar la topología de eventos SNS/SQS (Fan-out) y definir las estructuras de los payloads JSON de eventos.
             • Semana 12: Desarrollar el microservicio ms-attendance utilizando el patrón Time-Series en DynamoDB.
             • Semana 13: Escribir el script seed_master.py con manejo de concurrencia y lotes (batching) para evadir rebasar los timeouts.
             • Semana 14 (Avance Virtual - 30%): Topología SNS/SQS desplegada y validada mediante envío de eventos de prueba + ms-attendance funcional.
             • Semana 15: Ejecución completa del Seeding Masivo: Insertar 10,000 registros por tenant (x 3 tenants = 30,000) en cada uno de los 5 microservicios.
             • Semana 16: Validar el comportamiento de las colas DLQ ante errores simulados y orquestar el flujo de eventos para la Demo Presencial.
          6. Tareas Específicas para Criterios Críticos de la Rúbrica
             • 30,000 Registros por Microservicio: Ejecutar el script seed_master.py garantizando la siguiente distribución:
                   ◦ RDS (tenant_a, tenant_b, tenant_c): 10,000 filas por schema en ms-core-hr y ms-payroll.
                   ◦ DynamoDB (TENANT#tenant_a, TENANT#tenant_b, TENANT#tenant_c): 10,000 ítems por tenant en ms-recruitment, ms-performance y ms-attendance.
          Integrante 5: FrontEnd & UX Lead
          1. Rol Asignado y Alcance of Responsabilidad
             • Rol: Lead FrontEnd & UX Engineer.
             • Alcance: Desarrollo de la aplicación Web Single Page (SPA) en React desplegada en AWS Amplify Hosting, integración de autenticación JWT con AWS Amplify SDK, interceptores de seguridad
               multi-tenant y desarrollo de los dashboards ejecutivos.
          2. Componentes y Microservicios a su Cargo
             • FrontEnd Web App (React): Interfaz de usuario para los 5 microservicios HCM.
             • AWS Amplify Auth SDK: Gestión de inicio de sesión, refresh tokens y lectura de claims (custom:tenant_id).
             • Módulo de Pruebas Multi-Tenant: Conmutador de contextos (Tenant Switcher) para la demostración en vivo.
          3. Entregables de Código Exactos
             • src/context/AuthContext.jsx: Provider de React para almacenar el token JWT decodificado y el tenant_id activo.
             • src/services/apiClient.js: Cliente HTTP (Axios/Fetch) con interceptor que adhiere automáticamente Authorization: Bearer <token> a cada petición.
             • src/components/ (EmployeeTable.jsx, PayrollSlipViewer.jsx, CandidateKanban.jsx, EvaluationForm.jsx, ClockInWidget.jsx).
             • src/pages/TenantDemoView.jsx: Vista especial diseñada para comparar en paralelo la información de Tenant A y Tenant B.
          4. Matriz de Dependencias
          [Integrante 1] ──(Amplify URL + User Pool Config)──────► [Integrante 5 (FrontEnd)]
          [Integrantes 2, 3, 4] ──(Contratos API REST expuestos)─► [Integrante 5 (FrontEnd)]
             • Depende de: Integrante 1 (Configuración Cognito en Amplify) e Integrantes 2, 3 y 4 (Endpoints REST con CORS habilitado).
             • Entrega a: Proyecto Final (Interfaz gráfica de usuario completamente desplegada y funcional).
          5. Plan de Trabajo Semana a Semana (Semana 11 a 16)
             • Semana 11: Crear el proyecto React con Vite, TailwindCSS y la estructura de rutas/vistas base.
             • Semana 12: Conectar la autenticación de AWS Amplify SDK y crear el interceptor de Axios apiClient.js.
             • Semana 13: Desarrollar las pantallas de gestión de Core HR (listado con paginación) y Reclutamiento (tablero Kanban de vacantes).
             • Semana 14 (Avance Virtual - 30%): App desplegada en AWS Amplify URL con Login funcional en Cognito, lectura del claim custom:tenant_id y tabla de Core HR conectada.
             • Semana 15: Desarrollar pantallas de Nóminas (visualización de PDFs), Desempeño y Asistencia (marcaciones).
             • Semana 16: Construir y afinar la vista TenantDemoView.jsx para la sustentación presencial.
          6. Tareas Específicas para Criterios Críticos de la Rúbrica
             • Demo Presencial (2 Tenants Aislados): Crear una pantalla de prueba donde el profesor pueda seleccionar ingresar como "Tenant Alpha" y luego como "Tenant Beta" en dos pestañas/
               navegadores distintos, demostrando visualmente que los datos son 100% disjuntos.
             • Manejo de Datos Masivos: Implementar paginación del lado del servidor (Server-side Pagination) y renderizado optimizado de listas (Virtualization) para navegar fluidamente entre las tablas de
               10,000 registros por tenant.
          Matriz Resumen de Entregables por Hito del Curso
                                Componente                Avance Virtual (Semana 14 - 30%)                              Entrega Final Canvas (Semana 15/16 - 100%)
                                Infraestructura (IaC)     Cognito User Pool + S3 Bucket + Amplify CI/CD activado.       100% de servicios en serverless.yml (SNS, SQS, API Gateway, Lambdas).
                                Microservicios            ms-core-hr y ms-recruitment operativos.                       Los 5 microservicios integrados y respondiendo peticiones REST.
                                Bases de Datos            Schemas RDS y Tablas DynamoDB creadas.                        30,000 registros por microservicio insertados via seed_master.py.
                                Evento-Driven (EDA)       Declaración de Topics/Queues en IaC.                          Flujo asíncrono comprobado: Reclutamiento → SNS → SQS → Nómina.
                                FrontEnd                  App en Amplify con Auth + Dashboard Core HR.                  SPA completa con soporte multi-tenant, visores PDF y tablas paginadas.
          ¿Necesitas que redactemos algún script de código específico (como el middleware de conexión a PostgreSQL dbTenantMiddleware.js o el script en Python para la inserción de datos masivos) para
          facilitarle el trabajo a alguno de los integrantes?
          User prompt: Actúa como un Redactor Técnico y Consultor Cloud Senior. Genera el esqueleto y la plantilla completa del informe final (Word/PDF) y de la presentación en PowerPoint para nuestro proyecto final de
          SaaS HCM (CS2032 Cloud Computing UTEC 2026-2). Estructura el contenido para cumplir con el 100% de los entregables solicitados en la rúbrica: 1. ESQUELETO DEL INFORME FINAL (WORD / PDF): - Portada e
          Índice Estructurado. - Resumen Ejecutivo y Alcance del SaaS HCM. - Enlaces Públicos a Repositorios de Código Fuente (GitHub Frontend y Backend). - Diagrama de Arquitectura de la Solución (Explicación
          técnica del flujo FrontEnd Amplify -> API Gateway -> Lambda -> RDS/DynamoDB -> SNS -> SQS -> S3). - Diseños de Base de Datos por Microservicio: Secciones dedicadas para incluir los Diagramas Entidad-
          Relación (SQL) o esquemas JSON (NoSQL) de los 5 microservicios. - Implementación y Código Fuente: Explicación de la Automatización con Serverless Framework (serverless.yml) y componentes principales. -
          Estrategia Multi-tenant y Pruebas de Aislamiento: Evidencias y explicaciones de cómo se aíslan los datos entre tenants. - Estrategia de Carga Masiva: Explicación y script utilizado para poblar los 30,000 registros
          por microservicio repartidos en 3 tenants. 2. ESTRUCTURA DE DIAPOSITIVAS (POWERPOINT): - Guión diapositiva por diapositiva (Slide 1 a Slide 10) con el contenido exacto que debemos presentar en la
          exposición presencial de la Semana 16. Proporciona textos borrador para cada sección e instrucciones explícitas de qué capturas de pantalla o diagramas debemos insertar en cada apartado.
```

## Página 10

```text
Firefox                                                                                                                                                                                                    about:blank
           Response: DOCUMENTO 1: PLANTILLA Y ESQUELETO DEL INFORME FINAL (WORD / PDF)
           ESTRUCTURA DEL DOCUMENTO
           DOCUMENTO FINAL: SISTEMA HCM SAAS MULTI-TENANT SERVERLESS EN AWS
           ├── PORTADA E ÍNDICE ESTRUCTURADO
           ├── SECCIÓN 1: RESUMEN EJECUTIVO Y ALCANCE DEL PROYECTO
           ├── SECCIÓN 2: REPOSITORIOS Y CÓDIGO FUENTE
           ├── SECCIÓN 3: ARQUITECTURA DE LA SOLUCIÓN EN AWS
           ├── SECCIÓN 4: MODELO DE DATOS Y DISEÑOS DE BD POR MICROSERVICIO
           ├── SECCIÓN 5: IMPLEMENTACIÓN E INFRAESTRUCTURA COMO CÓDIGO (IaC)
           ├── SECCIÓN 6: ESTRATEGIA MULTI-TENANT Y AISLAMIENTO DE DATOS
           └── SECCIÓN 7: ESTRATEGIA DE CARGA MASIVA (30,000 REGISTROS/MICROSERVICIO)
           PORTADA E ÍNDICE ESTRUCTURADO
           Plantilla de Portada
           ================================================================================
           UNIVERSIDAD DE INGENIERÍA Y TECNOLOGÍA - UTEC
           DEPARTAMENTO DE CIENCIA DE LA COMPUTACIÓN
           CS2032: COMPUTACIÓN EN LA NUBE (PERÍODO 2026-2)
           PROYECTO FINAL:
           "DISEÑO E IMPLEMENTACIÓN DE UN SAAS HCM MULTI-TENANT SERVERLESS SOBRE AMAZON WEB SERVICES"
           INTEGRANTES DEL EQUIPO:
           1. [Nombre del Integrante 1] - DevOps & Infrastructure Lead
           2. [Nombre del Integrante 2] - Core BackEnd Engineer 1 (RDS PostgreSQL)
           3. [Nombre del Integrante 3] - Core BackEnd Engineer 2 (DynamoDB NoSQL)
           4. [Nombre del Integrante 4] - Event & Data Engineer
           5. [Nombre del Integrante 5] - FrontEnd & UX Lead
           PROFESOR DEL CURSO: [Nombre del Docente]
           FECHA DE ENTREGA: 22 de Noviembre de 2026
           LIMA, PERÚ
           ================================================================================
           Tabla de Contenidos (Índice Sugerido)
           1. Resumen Ejecutivo y Alcance del SaaS HCM
              1.1. Contexto y Objetivos del Proyecto
              1.2. Alcance Funcional de los 5 Microservicios
           2. Repositorios de Código Fuente
              2.1. Estructura del Repositorio Frontend (React & Amplify)
              2.2. Estructura del Repositorio Backend (Serverless Framework)
           3. Arquitectura General de la Solución
              3.1. Flujo End-to-End de la Solución
              3.2. Desglose de Componentes serverless de AWS
           4. Diseño de Base de Datos y Modelo de Datos por Microservicio
              4.1. Microservicio 1: Core HR (RDS PostgreSQL - Schema per Tenant)
              4.2. Microservicio 2: Reclutamiento (DynamoDB - Single Table Design)
              4.3. Microservicio 3: Nóminas (RDS PostgreSQL - Schema per Tenant)
              4.4. Microservicio 4: Desempeño (DynamoDB - Single Table Design)
              4.5. Microservicio 5: Asistencia y Licencias (DynamoDB - Time-Series)
           5. Implementación e Infraestructura como Código (IaC)
              5.1. Configuración Global con Serverless Framework (serverless.yml)
              5.2. Definición de Funciones Lambda, Endpoints y Roles IAM
           6. Estrategia Multi-Tenant y Pruebas de Aislamiento
              6.1. Propagación de Identity Claims con AWS Cognito
              6.2. Estrategia de Aislamiento en Capa de Persistencia (RDS y DynamoDB)
              6.3. Evidencias de Pruebas de Aislamiento y Denegación de Acceso
           7. Estrategia de Carga Masiva (30,000 Registros por Microservicio)
              7.1. Plan de Seeding Masivo sin Timeout de Lambda
              7.2. Script de Generación de Datos en Python (Faker + Batch Operations)
              7.3. Evidencias de Conteo de Registros por Tenant en BD
           CONTENIDO BORRADOR POR SECCIONES (TEXTO BASE PARA COPIAR Y ADAPTAR)
           SECCIÓN 1: Resumen Ejecutivo y Alcance del SaaS HCM
           Texto borrador:
                El presente documento describe el diseño técnico, la arquitectura e implementación de una plataforma Software as a Service (SaaS) orientada a la Gestión del Capital Humano (HCM),
                construida de forma nativa sobre Amazon Web Services (AWS). La solución implementa un modelo de arquitectura serverless desacoplada y una estrategia de aislamiento multi-tenant
                estricta para dar soporte a tres empresas u organizaciones independientes (Tenant A, Tenant B, Tenant C).
                El sistema se compone de cinco microservicios especializados: Core HR, Reclutamiento, Nóminas, Desempeño y Asistencia/Licencias. La persistencia de datos utiliza un enfoque híbrido:
                Amazon RDS (PostgreSQL) con el patrón de Single Database, Multiple Schemas para los dominios relacionales y contables, y Amazon DynamoDB con el patrón Single-Table Design para los
                dominios operativos de alta escala. La comunicación entre microservicios se efectúa mediante un patrón de arquitectura orientada a eventos (EDA) utilizando AWS SNS y AWS SQS. El
                despliegue de la infraestructura está automatizado al 100% mediante Serverless Framework, y el cliente web está hospedado en AWS Amplify.
           SECCIÓN 2: Enlaces Públicos a Repositorios de Código Fuente
           - Repositorio Frontend (React / AWS Amplify): https://github.com/[ORGANIZACION_O_USUARIO]/hcm-saas-frontend
           - Repositorio Backend (Serverless Framework Monorepo): https://github.com/[ORGANIZACION_O_USUARIO]/hcm-saas-backend
           Instrucción de inserción: Include a folder structure tree diagram of both repositories (e.g., generated with the tree command) showing the location of serverless.yml, package.json, /
           handlers, and /migrations.
           SECCIÓN 3: Arquitectura General de la Solución
           [INSERTAR DIAGRAMA DE ARQUITECTURA DE LA SOLUCIÓN]
           *Instrucción de diseño del diagrama:* Dibujar una arquitectura en AWS que muestre:
           1. Usuario Web interactuando con AWS Amplify (React SPA).
           2. Autenticación hacia AWS Cognito User Pool (obteniendo JWT con claim custom:tenant_id).
           3. Peticiones HTTPS direccionadas a AWS API Gateway.
           4. API Gateway invocando el Cognito Authorizer para validar la firma y extraer la claim del tenant.
           5. Invocación a las funciones AWS Lambda para procesamiento de negocio.
           6. Lambdas interactuando con Amazon RDS (PostgreSQL multi-schema) y Amazon DynamoDB.
           7. Almacenamiento de archivos PDF/imágenes en Amazon S3 bajo prefijo /{tenant_id}/*.
           8. Publicación de eventos de dominio a AWS SNS Topic y suscripción desacoplada a AWS SQS Queue para procesamiento asíncrono en Worker Lambdas.
           Texto borrador:
                La solución adopta una arquitectura Serverless desacoplada. Toda la lógica de negocio se ejecuta bajo demanda dentro de AWS Lambda, eliminando la gestión de servidores e
                infraestructura subyacente. El acceso a los recursos se gestiona mediante AWS API Gateway, el cual actúa como punto de entrada único (Single Point of Entry) y delega la verificación de
```

## Página 11

```text
Firefox                                                                                                                                                                                                   about:blank
                 credenciales a un AWS Cognito Authorizer. Este valida el token JWT y extrae de forma segura la claim personalizada custom:tenant_id, la cual se propaga a lo largo de toda la pila de
                 ejecución.
                 Para la carga y descarga de documentos de expediente y boletas de pago, la Lambda genera URL firmadas (Presigned URLs) hacia Amazon S3, evitando el paso de archivos binarios masivos a
                 través de API Gateway. El desacoplamiento entre microservicios se logra con un esquema de integración por eventos mediante Amazon SNS y Amazon SQS en patrón Fan-out, garantizando
                 el procesamiento asíncrono y la resiliencia mediante Dead Letter Queues (DLQ).
           SECCIÓN 4: Diseños de Base de Datos por Microservicio
           4.1. Microservicio Core HR (ms-core-hr) - RDS PostgreSQL
               • Estrategia Multi-tenant: Single Database, Multiple Schemas (tenant_a, tenant_b, tenant_c).
           -- DDL Representativo por Schema
           CREATE TABLE employees (
               employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               department_id UUID NOT NULL,
               first_name VARCHAR(50) NOT NULL,
               last_name VARCHAR(50) NOT NULL,
               email VARCHAR(100) UNIQUE NOT NULL,
               hire_date DATE NOT NULL,
               status VARCHAR(20) DEFAULT 'ACTIVE'
           );
           [INSERTAR DIAGRAMA ENTIDAD-RELACIÓN (ERD) DE CORE HR]
           *Instrucción:* Incluir el modelo ERD relacional que muestre las tablas departments, employees y contracts con sus respectivas llaves primarias y foráneas.
           4.2. Microservicio Reclutamiento (ms-recruitment) - DynamoDB NoSQL
               • Estrategia Multi-tenant: Single-Table Design con Partition Key (TENANT#<tenant_id>).
           {
               "PK": "TENANT#tenant_a",
               "SK": "CANDIDATE#c-883192",
               "vacancy_id": "v-102",
               "full_name": "Laura Gomez",
               "email": "laura@example.com",
               "stage": "INTERVIEW",
               "resume_url": "s3://hcm-app-storage/tenant_a/recruitment/resumes/c-883192.pdf"
           }
           [INSERTAR DIAGRAMA DE ESTRUCTURA Y PATRONES DE ACCESO EN DYNAMODB - RECLUTAMIENTO]
           *Instrucción:* Muestra la tabla de DynamoDB con las columnas PK, SK y los atributos específicos para las entidades Vacancy y Candidate.
           4.3. Microservicio Nóminas (ms-payroll) - RDS PostgreSQL
               • Estrategia Multi-tenant: Single Database, Multiple Schemas.
           CREATE TABLE pay_slips (
               pay_slip_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               period_id UUID NOT NULL,
               employee_id UUID NOT NULL,
               base_salary NUMERIC(10, 2) NOT NULL,
               deductions NUMERIC(10, 2) DEFAULT 0.00,
               net_pay NUMERIC(10, 2) NOT NULL
           );
           [INSERTAR DIAGRAMA ENTIDAD-RELACIÓN (ERD) DE NÓMINAS]
           4.4. Microservicio Desempeño (ms-performance) - DynamoDB NoSQL
               • Estrategia Multi-tenant: Single-Table Design (PK: TENANT#<tenant_id>, SK: EVAL#<eval_id>).
           {
               "PK": "TENANT#tenant_b",
               "SK": "EVAL#e-99021",
               "employee_id": "emp-402",
               "evaluator_id": "emp-001",
               "score": 4.5,
               "feedback": "Desempeño sobresaliente en entregas del sprint."
           }
           [INSERTAR CAPTURA DE ESQUEMA JSON / DYNAMODB WORKBENCH - DESEMPEÑO]
           4.5. Microservicio Asistencia (ms-attendance) - DynamoDB Time-Series
               • Estrategia Multi-tenant: PK: TENANT#<tenant_id>, SK: ATTENDANCE#<employee_id>#<YYYY-MM-DD>.
           {
               "PK": "TENANT#tenant_a",
               "SK": "ATTENDANCE#emp-102#2026-11-01",
               "check_in": "2026-11-01T08:00:00Z",
               "check_out": "2026-11-01T17:00:00Z",
               "status": "PRESENT"
           }
           [INSERTAR CAPTURA DE ESQUEMA JSON / DYNAMODB WORKBENCH - ASISTENCIA]
           SECCIÓN 5: Implementación e Infraestructura como Código (IaC)
           [INSERTAR CAPTURA DE PANTALLA O EXTRACTO DE CÓDIGO DE ARCHIVO serverless.yml]
           Texto borrador:
                 La infraestructura del proyecto fue aprovisionada en su totalidad mediante Serverless Framework, garantizando la repetibilidad del entorno de desplegado. En el archivo serverless.yml
                 se definieron los eventos del API Gateway, las políticas de permisos mínimos (Least Privilege) mediante el plugin serverless-iam-roles-per-function, y las variables de entorno
                 inyectadas a las funciones Lambda.
           # Extracto representativo de serverless.yml
           service: hcm-core-hr-service
           provider:
             name: aws
             runtime: nodejs18.x
             region: us-east-1
             environment:
               DB_HOST: ${opts:dbHost}
               S3_BUCKET: hcm-app-storage
           functions:
             createEmployee:
               handler: handlers/createEmployee.main
               events:
                 - http:
```

## Página 12

```text
Firefox                                                                                                                                                                                                    about:blank
                      path: /employees
                      method: post
                      authorizer:
                        arn: arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_XXXXX
                        claims:
                          - custom:tenant_id
           SECCIÓN 6: Estrategia Multi-Tenant y Pruebas de Aislamiento
           [INSERTAR CAPTURA DE PANTALLA 1: DECODIFICACIÓN DE JWT EN JWT.IO ENSEÑANDO custom:tenant_id]
           [INSERTAR CAPTURA DE PANTALLA 2: EJECUCIÓN DE CONSULTA SQL EN RDS MOSTRANDO SET search_path TO tenant_a]
           [INSERTAR CAPTURA DE PANTALLA 3: RESPUESTA HTTP 403 / 404 AL INTENTAR ACCEDER A RECURSOS DEL TENANT A USANDO UN TOKEN DEL TENANT B]
           Texto borrador:
               El aislamiento multi-tenant se garantiza mediante un control en tres capas:
                  1. Capa de Identidad: AWS Cognito inyecta el atributo obligatorio custom:tenant_id dentro del ID Token emitiendo una firma criptográfica infalsificable.
                  2. Capa de Aplicación (Lambda): El código extrae la claim del contexto asignado por el API Gateway (event.requestContext.authorizer.claims['custom:tenant_id']).
                  3. Capa de Persistencia:
                       ◦ RDS PostgreSQL: Cada petición ejecuta al inicio de la transacción el comando SET search_path TO tenant_<tenant_id>;, forzando al motor a resolver las tablas
                         exclusivamente dentro del esquema de la empresa autenticada.
                       ◦ DynamoDB: Todas las peticiones inyectan de forma obligatoria la clave de partición PK = TENANT#<tenant_id>. Cualquier intento de manipulación en el parámetro por parte
                         del cliente es rechazado si no coincide con el token validado.
           SECCIÓN 7: Estrategia de Carga Masiva (30,000 Registros por Microservicio)
           [INSERTAR CAPTURA DE PANTALLA 1: CONSOLA DE EJECUCIÓN DEL SCRIPT seed_master.py]
           [INSERTAR CAPTURA DE PANTALLA 2: CONSULTA SELECT COUNT(*) EN RDS PARA tenant_a, tenant_b, tenant_c SUMANDO 30,000 FILAS]
           [INSERTAR CAPTURA DE PANTALLA 3: CONSOLA DE DYNAMODB MOSTRANDO 30,000 ÍTEMS EN LA TABLA ms-recruitment-table]
           Texto borrador:
               Para cumplir con la exigencia de 30,000 registros por microservicio (10,000 por tenant) sin exceder los límites de tiempo de ejecución de AWS Lambda (15 minutos), se diseñó e implementó
               una estrategia de seeding masivo fuera de banda mediante un script en Python (seed_master.py).
               El script utiliza la librería Faker para la generación de datos estocásticos realistas y realiza inserciones optimizadas mediante psycopg2.extras.execute_values (lotes de 2,000 filas por
               transacción) para las bases RDS, y boto3.dynamodb.batch_writer() (lotes de 25 ítems concurrentes) para DynamoDB. Esto permitió poblar un total acumulado de 150,000 registros en la
               infraestructura AWS en menos de 4 minutos sin degradación del servicio.
           DOCUMENTO 2: GUIÓN Y ESTRUCTURA DE DIAPOSITIVAS (POWERPOINT)
           ================================================================================
           ESTRUCTURA DE PRESENTACIÓN PRESENCIAL (SEMANA 16 - DEMO Y DEFECTOS DE ARQUITECTURA)
           DURACIÓN MÁXIMA: 10 - 12 MINUTOS
           ================================================================================
           SLIDE 1: Portada y Presentación del Equipo
             • Título de la Diapositiva: SaaS HCM Multi-Tenant Serverless en AWS
             • Subtítulo: Proyecto Final CS2032 - Computación en la Nube (UTEC 2026-2)
             • Contenido Visual:
                  ◦ Logotipo de UTEC y AWS Partner/Cloud Architecture.
                  ◦ Matriz de Integrantes y Roles:
                       ▪ DevOps Lead | Core Backend SQL | Core Backend NoSQL | Data & Events | Frontend Lead
             • Guión de Exposición (30 segundos):
                    "Buenos días profesor y compañeros. Presentamos la arquitectura y demostración en vivo de nuestro SaaS HCM Serverless diseñado para escalar bajo un patrón multi-tenant estricto
                    en AWS, garantizando el aislamiento de datos entre organizaciones, alta disponibilidad y una arquitectura desacoplada orientada a eventos."
           SLIDE 2: Propuesta de Valor y Requisitos Clave
             • Título de la Diapositiva: El Desafío HCM Multi-Tenant
             • Contenido de Texto (Puntos clave):
                  ◦ Problema: Gestión aislada, segura y económica de HCM (Recursos Humanos, Nóminas, Talentos) para múltiples empresas en un entorno Cloud.
                  ◦ Retos Rúbrica: 5 Microservicios, 30,000 registros por microservicio (3 tenants), IaC al 100%, Desacoplamiento EDA (SNS/SQS) e interfaz en AWS Amplify.
             • Elemento Visual: Tabla comparativa visual entre arquitectura Monolítica vs Nuestra Arquitectura Serverless Multi-Tenant.
             • Guión de Exposición (45 segundos):
                    "Construir un SaaS HCM exige aislar rigurosamente la información financiera y de empleados entre empresas. Nuestro diseño resuelve este reto combinando la flexibilidad de
                    DynamoDB y la rigidez relacional de PostgreSQL, respaldado por una infraestructura como código desplegada en un clic con Serverless Framework."
           SLIDE 3: Arquitectura General Serverless en AWS
             • Título de la Diapositiva: Arquitectura End-to-End en AWS
             • Contenido Visual: Diagrama completo de la arquitectura en AWS (Amplify → API Gateway → Cognito → Lambda → RDS / DynamoDB / S3 → SNS / SQS).
             • Puntos a destacar:
                  ◦ Punto de entrada unificado vía API Gateway HTTP APIs.
                  ◦ Computación Serverless con AWS Lambda (Node.js/Python).
                  ◦ Storage binario aislado por tenant en Amazon S3.
             • Guión de Exposición (1.5 minutos):
                    "Como se observa en el diagrama, el usuario interactúa con la SPA en React alojada en AWS Amplify. Toda solicitud pasa por el API Gateway donde Cognito valida las credenciales y
                    adjunta la identidad del Tenant. De ahí, Lambdas independientes procesan la lógica y persisten en la capa de datos o emiten eventos asíncronos vía SNS."
           SLIDE 4: Estrategia de Aislamiento Multi-Tenant
             • Título de la Diapositiva: Aislamiento de Datos en 3 Capas
```

## Página 13

```text
Firefox                                                                                                                                                                                                        about:blank
             • Contenido de Texto (Diagrama de Capas):
                 1. Autenticación (Cognito): Claim de Token JWT infalsificable (custom:tenant_id).
                 2. Persistencia SQL (RDS PostgreSQL): Patrón Single DB, Multiple Schemas (SET search_path).
                 3. Persistencia NoSQL (DynamoDB): Partition Key Constraint (PK: TENANT#<tenant_id>).
             • Elemento Visual: Gráfico ilustrativo de cómo el token bloquea el acceso cruzado entre Tenant A y Tenant B.
             • Guión de Exposición (1.5 minutos):
                    "El pilar de nuestra arquitectura es la seguridad multi-tenant. A nivel relacional en RDS PostgreSQL, no usamos una columna simple de ID; ejecutamos dinámicamente 'SET
                    search_path' al iniciar la conexión, garantizando que el Tenant A sea físicamente incapaz de consultar las tablas del Tenant B. En DynamoDB, la llave de partición impone el aislamiento
                    desde el diseño."
           SLIDE 5: Microservicios Relacionales (RDS PostgreSQL)
             • Título de la Diapositiva: Dominios Core HR & Nóminas (ms-core-hr, ms-payroll)
             • Contenido de Texto:
                  ◦ Core HR: Gestión organizacional, empleados y contratos laborales.
                  ◦ Nóminas: Cálculo automatizado de liquidaciones, descuentos y boletas de pago PDF en S3.
                  ◦ Schema isolation: tenant_a.employees, tenant_b.employees, tenant_c.employees.
             • Elemento Visual: Diagrama Entidad-Relación (ERD) simplificado y captura de boleta de pago generada en S3.
             • Guión de Exposición (1 minuto):
                    "Para los dominios contables y organizacionales donde la consistencia ACID es crítica, elegimos Amazon RDS PostgreSQL. La arquitectura Multi-Schema nos permite aislar legal y
                    lógicamente la información de nóminas de cada cliente manteniendo una sola instancia de base de datos eficiente."
           SLIDE 6: Microservicios NoSQL (DynamoDB)
             • Título de la Diapositiva: Dominios de Alta Escala (ms-recruitment, ms-performance, ms-attendance)
             • Contenido de Texto:
                  ◦ Reclutamiento: Tablero Kanban de postulantes + carga de CVs en S3 con Presigned URLs.
                  ◦ Desempeño: Evaluaciones 360 y Objetivos OKR.
                  ◦ Asistencia: Marcaciones en serie de tiempo (Time-Series Access Pattern).
             • Elemento Visual: Tabla de diseño Single-Table en DynamoDB mostrando llaves PK (TENANT#id) y SK.
             • Guión de Exposición (1 minuto):
                    "En Reclutamiento, Desempeño y Asistencia utilizamos DynamoDB. El patrón Single-Table nos permite consultar vacantes, candidatos y marcaciones con latencias de un solo dígito de
                    milisegundo, indexando siempre por el Partition Key del tenant."
           SLIDE 7: Integración Orientada a Eventos (EDA)
             • Título de la Diapositiva: Mensajería Asíncrona con AWS SNS y SQS
             • Contenido Visual: Diagrama del flujo de evento: Candidato Contratado → SNS Topic → SQS Queue → Worker Lambda → Alta en Core HR / Nóminas.
             • Puntos a destacar:
                  ◦ Patrón Fan-out para desacoplar el microservicio emisor de los consumidores.
                  ◦ Tolerancia a fallos con Dead Letter Queues (DLQ).
             • Guión de Exposición (1 minuto):
                    "Para evitar dependencias síncronas entre microservicios, usamos AWS SNS y SQS. Cuando Reclutamiento marca a un candidato como contratado, emite un evento a SNS. La cola SQS
                    de Nóminas lo recibe y procesa en segundo plano, asegurando resiliencia mediante colas de mensajes fallidos (DLQ)."
           SLIDE 8: Estrategia de Seeding Masivo (30,000 Registros)
             • Título de la Diapositiva: Carga de Datos a Gran Escala
             • Contenido de Texto:
                  ◦ Volumen: 30,000 registros por microservicio (10,000 x 3 tenants). Total acumulado: 150,000 registros.
                  ◦ Técnica: Script en Python fuera de banda (seed_master.py) utilizando inserciones por lotes (batch writing).
                  ◦ Rendimiento: Carga completa en < 4 minutos sin degradación ni timeouts.
             • Elemento Visual: Captura del CLI ejecutando el script y resultado de SELECT COUNT(*) en las bases de datos.
             • Guión de Exposición (1 minuto):
                    "Para demostrar la capacidad de soporte de volumen de la rúbrica, desarrollamos un script en Python con la librería Faker que inyectó 30,000 registros por microservicio divididos
                    exactamente entre 3 tenants. Ejecutamos la carga en lotes de 2,000 filas para RDS y 25 ítems para DynamoDB, poblando 150,000 registros en total."
           SLIDE 9: DEMOSTRACIÓN EN VIVO (LIVE DEMO)
             • Título de la Diapositiva: Demostración en Vivo: Prueba de Aislamiento
             • Contenido de Texto (Checklist de la Demo):
                 1. Login como Tenant Alpha → Visualizar token JWT en pantalla.
                 2. Registrar empleado en Core HR + Subir contrato PDF a S3.
                 3. Logout → Login como Tenant Beta → Verificar grilla vacía de datos de Alpha.
                 4. Petición directa a API Gateway con ID de Tenant Alpha usando Token de Beta → Resultado: HTTP 404 / 403 Access Denied.
                 5. Demostración de evento asíncrono en CloudWatch Logs (SNS → SQS).
             • Elemento Visual: Pantalla dividida simulando los dos contextos de empresa.
             • Guión de Exposición (3 minutos - Ejecución en pantalla):
                    "Pasamos a la demostración en vivo. Vamos a iniciar sesión como Tenant Alpha... observen el claim custom:tenant_id en el token. Creamos al empleado 'Carlos Ruiz'. Ahora cerramos
```

## Página 14

```text
Firefox                                                                                                                                                                                                       about:blank
                     sesión e ingresamos como Tenant Beta. La lista está limpia. Si intentamos forzar la API mediante curl pasando el ID de Carlos Ruiz con el token de Beta, la aplicación nos deniega el
                     acceso. El aislamiento es total."
           SLIDE 10: Conclusiones y Preguntas
              • Título de la Diapositiva: Conclusiones y Lecciones Aprendidas
              • Contenido de Texto (Puntos clave):
                   ◦ Cumplimiento de Rúbrica: 100% de la infraestructura desplegada con Serverless Framework y AWS Amplify.
                   ◦ Seguridad: Aislamiento multi-tenant garantizado en la capa de datos sin fuga de información.
                   ◦ Escalabilidad y Costos: Arquitectura 100% Serverless con modelo de pago por uso (Pay-as-you-go).
                   ◦ Preguntas & Respuestas (Q&A).
              • Guión de Exposición (30 segundos):
                     "En conclusión, demostramos que la combinación de AWS Lambda, RDS PostgreSQL Multi-Schema, DynamoDB y patrones EDA permite construir un SaaS HCM enterprise-grade,
                     seguro, altamente escalable y costo-eficiente. Quedamos a su disposición para sus preguntas. Muchas gracias."
           ¿Deseas que adaptemos este borrador o que profundicemos en la redacción técnica de algún apartado del informe en particular?
```
