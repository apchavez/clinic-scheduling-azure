[![CI](https://github.com/apchavez/azure-python/actions/workflows/ci.yml/badge.svg)](https://github.com/apchavez/azure-python/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=apchavez_azure-python&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=apchavez_azure-python)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=apchavez_azure-python&metric=coverage)](https://sonarcloud.io/summary/new_code?id=apchavez_azure-python)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=apchavez_azure-python&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=apchavez_azure-python)

# Plataforma de Agendamiento de Citas Médicas — Azure (Python)

Migración a Azure de la plataforma de citas médicas originalmente construida en AWS ([aws-typescript](https://github.com/apchavez/aws-typescript), TypeScript). Misma lógica de negocio y misma Clean Architecture — solo cambian los adaptadores de infraestructura (y, en esta migración, el lenguaje de implementación).

> El dominio no tiene ningún conocimiento de Azure. Lo único que cambia entre nubes es la capa de infraestructura; los casos de uso y las entidades permanecen intactos.

> **Costo cero en reposo** — el CI solo compila y corre pruebas. No se aprovisiona ningún recurso de Azure hasta que se dispara manualmente el workflow de deploy.

> **CI/CD:** el pipeline que realmente corre es GitHub Actions (`.github/workflows/ci.yml`). También incluye un `Jenkinsfile` equivalente en la raíz, como referencia de sintaxis Declarative Pipeline/Groovy para organizaciones que corren Jenkins on-prem.

> **Dev sin instalar el toolchain:** `./docker/dev.sh test` corre build/test dentro del mismo contenedor que usa CI, sin necesitar nada más que Docker instalado localmente (`./docker/dev.sh` sin argumentos muestra las opciones).

---

## Stack Tecnológico

| Categoría | Tecnología |
|---|---|
| Lenguaje / Runtime | Python 3.12, Azure Functions Python v2 programming model |
| API / Gateway | API Management (StandardV2), `rate-limit-by-key` (25 llamadas / 1s por IP o subscription) — desplegado por defecto, delante del Function App |
| Almacén de estado (NoSQL) | Cosmos DB serverless (Managed Identity) |
| Persistencia relacional | Azure SQL Database (pymssql) |
| Mensajería | Service Bus topics + subscriptions (Managed Identity) |
| Bus de eventos | Event Grid (topic + subscription, Managed Identity) |
| Notificaciones | Azure Communication Services Email |
| Resiliencia | Circuit breaker + retry exponencial hechos a mano (replica el `shared/resilience.ts` del proyecto hermano en AWS) — 3 intentos, ventana deslizante de 10 llamadas, umbral de fallo del 50%, estado abierto de 30s |
| IaC | Bicep (deployment a nivel de subscription) |
| Seguridad | Managed Identity, referencias a Key Vault, solo HTTPS |
| Observabilidad | Application Insights (vía `azure-monitor-opentelemetry`), correlation IDs (`contextvars`), logs estructurados |
| Documentación de API | OpenAPI 3.0 (validado en CI con Redocly) |
| Build / Tests | pytest, pytest-cov (gate de 80% en domain + application), ruff (lint + format) |
| CI/CD | GitHub Actions (CI automático, deploy/destroy manual) |

---

## Mapeo AWS → Azure

| AWS (proyecto original) | Azure (este proyecto) |
|---|---|
| AWS Lambda | Azure Functions v4 |
| API Gateway (throttle burst 50 / rate 25 rps) | API Management StandardV2 (`rate-limit-by-key` 25 llamadas/1s — ventana fija, no token bucket como AWS; sin concepto separado de "burst", desplegado por defecto delante del Function App) |
| DynamoDB | Cosmos DB |
| MySQL / RDS | Azure SQL Database |
| Tópico SNS | Tópico de Service Bus |
| Cola SQS | Subscription de Service Bus |
| EventBridge (bus custom) | Event Grid (topic custom) |
| `AWS::Events::Rule` → SQS de confirmaciones | Event Grid Subscription → cola de confirmaciones de Service Bus |
| Terraform (red/RDS) + Serverless Framework (app) | Bicep (ambas capas) |
| CloudWatch | Application Insights + Log Analytics |

---

## Arquitectura

![Diagrama de arquitectura](docs/architecture-diagram.svg)

Publish → consume de punta a punta sin piezas muertas, en dos etapas desacopladas por Event Grid (mismo patrón que el hermano en AWS: el worker que persiste el registro relacional no marca el estado final ni notifica — eso lo hace un handler separado disparado por el bus de eventos).

Clean Architecture con cuatro capas bien definidas:

```
clinic/
├── domain/
│   ├── entities/        Appointment, AppointmentEvent, AppointmentStatus
│   ├── ports/           AppointmentStateRepository, AppointmentRelationalRepository,
│   │                    AppointmentEventPublisher, AppointmentEventStore, AppointmentNotifier
│   │                    (typing.Protocol — tipado estructural, sin necesidad de herencia de una clase base)
│   ├── shared/          Page[T]
│   └── exceptions.py    IllegalStateError, ForbiddenError
├── application/
│   └── usecases/        create_appointment, get_appointments, get_appointment_history,
│                        process_appointment
├── infrastructure/
│   ├── auth/            jwt_validator (HS256 hecho a mano), auth_guard
│   ├── config/          app_context (composition root), resilience, correlation_context,
│                        telemetry_context
│   ├── messaging/       service_bus_event_publisher, event_grid_confirmation_publisher
│   ├── notifications/   acs_appointment_notifier, no_op_appointment_notifier
│   └── repos/           cosmos_appointment_state_repository, cosmos_appointment_event_store,
│                        azure_sql_appointment_repository
└── shared/               api_response, health_status

function_app.py           Puntos de entrada de Azure Functions v2 (triggers HTTP + Service Bus,
                           incluida la cola de confirmaciones alimentada por Event Grid)
```

**Regla de dependencia:** `infrastructure` / `function_app.py` → `application` → `domain`
El dominio no importa ningún SDK de Azure. Las pruebas corren completamente en memoria, sin necesidad de nube.

---

## Flujo de Extremo a Extremo

```
POST /api/appointments
  → CreateAppointmentUseCase
      → Cosmos DB (estado PENDING) + evento APPOINTMENT_CREATED
      → Tópico Service Bus "appointment-created"
          → AppointmentWorker (una sola suscripción/worker)
              → ProcessAppointmentUseCase
                  → Azure SQL (persistencia final)
                  → Event Grid Topic (evento "AppointmentConfirmed")
                      → Event Grid Subscription → cola Service Bus "appointment-confirmations"
                          → confirmAppointment
                              → ConfirmAppointmentUseCase
                                  → Cosmos DB (COMPLETED) + evento APPOINTMENT_COMPLETED
                                  → Email ACS (notificación al asegurado)

GET    /api/appointments/{id}/history     → log de eventos inmutable desde Cosmos DB
```

---

## Cómo Empezar

Requiere [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local), Python 3.12, y una cuenta de Cosmos DB o el emulador.

```bash
# 1. Crear un venv e instalar dependencias
python -m venv .venv
.venv/Scripts/activate   # .venv/bin/activate en Linux/macOS
pip install -r requirements-dev.txt

# 2. Configurar variables (copiar y editar)
cp local.settings.json.example local.settings.json
# Completar COSMOS_ENDPOINT, SERVICEBUS__fullyQualifiedNamespace, SQL_HOST, SQL_USER, SQL_PASSWORD,
# EVENTGRID_TOPIC_ENDPOINT
# Opcionalmente configurar APPLICATIONINSIGHTS_CONNECTION_STRING para habilitar telemetría local

# 3. Iniciar
func start
```

La función estará disponible en `http://localhost:7071/api`.

Para correr solo las pruebas (sin nube, sin variables de entorno):

```bash
pytest --cov=clinic.domain --cov=clinic.application --cov-fail-under=80
```

---

## Endpoints de la API

Ruta base: `/api`

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/appointments` | Crear cita (PENDING → Service Bus) |
| `GET` | `/appointments/{insuredId}` | Listar citas con paginación basada en cursor |
| `GET` | `/appointments/{appointmentId}/history` | Log de eventos inmutable de una cita |
| `GET` | `/health` | Estado de Cosmos DB, SQL, y Service Bus |

Contrato completo: [`src/docs/openapi.yaml`](src/docs/openapi.yaml)

Todos los endpoints excepto `/health` requieren un token JWT Bearer en el header `Authorization`:

```
Authorization: Bearer <token>
```

Los tokens son JWT **HS256** con claims `sub`/`role`/`exp` (misma forma que los tokens del proyecto hermano AWS Lambda), firmados con el secreto en `JWT_SECRET` (respaldado por Key Vault — ver [Deploy](#deploy)). La validación ocurre **dentro de la propia Function** (`auth_guard`/`jwt_validator`, `clinic/infrastructure/auth/`), no vía API Management — así que está activa sin importar si `deployApiManagement` está habilitado. Las solicitudes con un token ausente, malformado, alterado, o expirado reciben **401 Unauthorized**. `auth_level=func.AuthLevel.ANONYMOUS` en cada `@app.route` solo significa "no requiere key de Azure Functions"; no significa que no requiera autenticación.

### Generar un token (dev/testing)

```bash
# JWT HS256 con header {"alg":"HS256","typ":"JWT"} y payload {"sub":"agent-001","role":"agent","exp":<unix-ts>}
# codificar header y payload en base64url (sin padding), luego aplicar HMAC-SHA256 al string "header.payload" con JWT_SECRET
```

No hay endpoint de login en este proyecto de portafolio (igual que el hermano AWS Lambda) — generá un token con cualquier librería/script JWT HS256 usando el valor de `JWT_SECRET` de Key Vault, o reutilizá el helper `signJwt` del proyecto AWS (`src/infra/jwt.ts`) ya que ambos aceptan la misma forma de token.

---

## OpenAPI

El contrato completo de la API está en [`src/docs/openapi.yaml`](src/docs/openapi.yaml) — **OpenAPI 3.0.3** con schemas completos de request/response, ejemplos, y códigos de error para los 6 endpoints. El spec se valida automáticamente en cada corrida de CI con Redocly (`ci.yml`).

**Validar localmente:**

```bash
npx @redocly/cli lint src/docs/openapi.yaml
```

**Generar documento HTML estático:**

```bash
npx @redocly/cli build-docs src/docs/openapi.yaml -o docs/swagger.html
```

---

## Testing

```bash
pip install -r requirements-dev.txt
ruff format --check .
ruff check .
pytest --cov=clinic.domain --cov=clinic.application --cov-fail-under=80
```

**91 tests en 22 archivos de test.** Las pruebas corren completamente en memoria -- no requieren cuenta de Azure, variables de entorno, ni conexión de red.

| Tipo | Alcance | Descripción |
|---|---|---|
| Unitarias | Domain & Application | Casos de uso y entidades con fakes en memoria escritos a mano -- cero dependencias de Azure |
| Unitarias | Infrastructure & API | Adaptadores y handlers HTTP probados con clientes de SDK de Azure simulados (`unittest.mock`) |

`pytest-cov` exige **>= 80% de cobertura** solo en `clinic.domain` y `clinic.application`. Los adaptadores de infraestructura que requieren conexiones reales a Azure quedan excluidos del umbral.

---

## Deploy

El deploy es **exclusivamente manual** vía GitHub Actions (`workflow_dispatch`). El CI nunca aprovisiona recursos de Azure.

```
.github/workflows/
├── ci.yml          Push/PR → build, tests, validación de OpenAPI   (sin costo en Azure)
├── deploy.yml      Manual  → infra Bicep + Function App            (genera costo)
├── destroy.yml     Manual  → elimina el resource group             (detiene el costo)
├── cost-guard.yml  Diario  → ejecuta destroy.yml automáticamente si el RG de dev tiene más de 48h
└── integration.yml Manual  → pruebas de Postman contra el entorno en vivo
```

Para hacer deploy a Azure, configurá las variables de entorno OIDC (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) y los secrets `SQL_ADMIN_PASSWORD`/`JWT_SECRET` en el repositorio.

`cost-guard.yml` no necesita ser disparado — corre todos los días, revisa la fecha de creación de `rg-clinic-dev` vía Azure Resource Graph, y dispara `destroy.yml` automáticamente si tiene más de 48h (configurable con `max_age_hours` en una corrida manual). No hace nada si el resource group no existe. Mismo patrón que los hermanos `aws-typescript`/`gcp-go`.

`integration.yml` requiere la URL del stack ya desplegado como input manual — si no ves una corrida verde reciente en Actions es porque no hay un deploy vivo contra el cual correr las pruebas (el resource group se destruye para no generar costo ocioso), no porque el pipeline esté roto.

> **Nota de diseño — sin llave administrada por el cliente (CMK) para cifrado en reposo.** Cosmos DB, Azure SQL, Storage, y el propio Key Vault usan las llaves administradas por Microsoft por defecto (`infra/core.bicep`) — Key Vault en este repo solo se usa como *secret store* (contraseña de SQL, secreto JWT vía `@Microsoft.KeyVault(...)`), no como fuente de una CMK para ninguno de esos recursos. Es el default razonable para una demo de portafolio; una CMK real requeriría un `Microsoft.KeyVault/vaults/keys` dedicado, RBAC de esa key hacia cada recurso, y el bloque `encryption`/`keyVaultKeyUri` correspondiente en cada template — una adición real de infraestructura, no un flag para prender.

> **Nota de diseño — `allowPublicNetworkAccess` es `true` por defecto.** Cosmos DB, Service Bus, Storage, Azure SQL, y Key Vault son alcanzables desde internet público por defecto (`infra/core.bicep`). Esto es una decisión deliberada, no un descuido: ninguno de estos templates de Bicep aprovisiona una VNet, subnets, o Private Endpoints, así que cambiar el default a `false` haría que ningún recurso sea alcanzable por la Function App en un deploy por defecto — el networking privado es una adición real de infraestructura (VNet + Private Endpoints + zonas de Private DNS por servicio + integración de la Function App a la VNet), fuera del alcance de un deployment del tamaño de un portafolio. Configurá `allowPublicNetworkAccess=false` solo después de agregar esa capa de networking vos mismo.

---

## Observabilidad

| Señal | Implementación |
|---|---|
| Logging estructurado | `python-json-logger` — todos los handlers emiten JSON a stdout, capturado automáticamente por Application Insights |
| Tracing / correlación | `azure-monitor-opentelemetry` correlaciona logs, dependencias, y excepciones entre invocaciones; el correlation ID se propaga vía `contextvars` |
| Health check | `GET /api/health` — hace ping a Cosmos DB, Azure SQL, y Service Bus; devuelve `UP`/`DOWN` por componente (Event Grid no tiene una operación de lectura ligera equivalente en el SDK de datos, así que no se incluye en el ping — ver `EventGridConfirmationPublisher`) |
| Alertas de métricas | Bicep aprovisiona dos alertas de Azure Monitor cuando se despliega con `deployAlerts=true` y `alertEmail`: **tasa de errores 5xx** (severidad 2) y **latencia alta** (severidad 3, promedio > 2 s) |

Para habilitar las alertas durante el deploy, pasá los parámetros al workflow de deploy:

```bash
gh workflow run deploy.yml -f deployAlerts=true -f alertEmail=you@example.com
```

---

## Qué Demuestra Este Proyecto

- Clean Architecture portable entre nubes *y* lenguajes — las capas de domain/application se migraron de Java a Python sin ninguna desviación en la lógica de negocio
- Servicios nativos de Azure: event sourcing con Cosmos DB, fan-out con Service Bus, bus de eventos desacoplado con Event Grid, notificaciones por email con ACS
- Managed Identity en todas partes — ninguna credencial hardcodeada en todo el código
- Circuit breaker + retry exponencial hechos a mano (migrados línea por línea desde el `resilience.ts` del hermano AWS TypeScript) en todas las llamadas externas — 3 intentos, ventana deslizante de 10 llamadas, umbral de fallo del 50%, estado abierto de 30s
- Paginación basada en cursor sobre Cosmos DB para result sets grandes
- IaC con Bicep a nivel de subscription — todo el stack se aprovisiona en un solo workflow
- Contrato OpenAPI validado en cada corrida de CI con Redocly
- Diseño de CI con costo cero — el pipeline de CI no crea ningún recurso de Azure

---

## Proyectos Relacionados

Este repo va en conjunto con **aws-typescript** y **gcp-go**: los tres implementan el mismo dominio de agendamiento de citas médicas y Clean Architecture, mismos 4 endpoints, distinta nube/lenguaje — mantenidos en paridad funcional a propósito. Los cinco proyectos de Product Management forman un segundo grupo así, compartiendo en cambio ese otro dominio.

| Proyecto | Descripción |
|---|---|
| [aws-typescript](https://github.com/apchavez/aws-typescript) | La versión original en AWS — TypeScript, Lambda, DynamoDB, SNS/SQS. Misma lógica de dominio, distinta nube |
| [gcp-go](https://github.com/apchavez/gcp-go) | Mismo dominio de agendamiento de citas médicas, escrito en Go sobre GCP Cloud Run con Clean Architecture |
| [quarkus-react](https://github.com/apchavez/quarkus-react) | Plataforma de Gestión de Productos — backend Quarkus, frontend React, MongoDB, Redis, eventos Kafka, Kubernetes |
| [spring-webflux-angular](https://github.com/apchavez/spring-webflux-angular) | Mismo dominio de Gestión de Productos, backend reactivo Spring Boot WebFlux, frontend Angular, PostgreSQL, Kafka, Kubernetes |
| [spring-mvc-angular](https://github.com/apchavez/spring-mvc-angular) | Mismo dominio de Gestión de Productos y frontend Angular que spring-webflux-angular, backend clásico bloqueante Spring MVC, Spring Data JDBC, Kafka, Kubernetes |
| [net-vue](https://github.com/apchavez/net-vue) | Mismo dominio de Gestión de Productos, backend ASP.NET Core, frontend Vue 3, PostgreSQL, Kafka, Kubernetes |
| [spring-jpa-native](https://github.com/apchavez/spring-jpa-native) | API de Product Management que demuestra JPA/Hibernate (relaciones de entidades, fix de N+1, bloqueo optimista, auditoría) con frontend móvil en React Native |
---

## Licencia

[MIT](LICENSE)
