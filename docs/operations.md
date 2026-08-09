# Operations Guide

This guide documents the production-facing checks for the Clinic Scheduling Platform on Azure.

## Application Insights queries

Use these KQL queries from the Application Insights Logs blade.

### Appointment lifecycle

```kusto
traces
| where message has_any ("appointment.accepted", "appointment.processing", "appointment.completed")
| extend appointmentId = extract("appointmentId=([^ ]+)", 1, message)
| project timestamp, message, appointmentId, operation_Id
| order by timestamp desc
```

### Worker failures

```kusto
traces
| where severityLevel >= 3
| where message has "Error processing message"
| project timestamp, message, operation_Id
| order by timestamp desc
```

### API latency

```kusto
requests
| summarize count(), avg(duration), percentile(duration, 95) by name, resultCode
| order by name asc
```

## Dead-letter handling

The `appointment-created` subscription (`appointment-worker`) uses:

- `maxDeliveryCount: 5` in Bicep.
- `host.json`'s function-app-wide `retry` policy (`fixedDelay`, `maxRetryCount: 3`, `delayInterval: "00:00:10"`) — note this replaces the Java port's per-function `@FixedDelayRetry` annotation; the Python v2 model configures retry at the host level rather than per-function, so it also applies to the HTTP-triggered functions, not just the worker.
- `deadLetteringOnMessageExpiration: true`.

Inspect dead-lettered messages:

```bash
az servicebus topic subscription show \
  --resource-group rg-clinic-dev \
  --namespace-name <service-bus-namespace> \
  --topic-name appointment-created \
  --name appointment-worker
```

Receive dead-letter messages for investigation:

```bash
az servicebus topic subscription receive \
  --resource-group rg-clinic-dev \
  --namespace-name <service-bus-namespace> \
  --topic-name appointment-created \
  --subscription-name appointment-worker \
  --queue-name '$DeadLetterQueue' \
  --max-message-count 10
```

## API Management

API Management is optional to keep development deployments low-cost.

Enable it at deployment time:

```bash
az deployment sub create \
  --location eastus \
  --template-file infra/main.bicep \
  --parameters infra/main.parameters.json \
  --parameters sqlAdminPassword='<password>' \
  --parameters jwtSecret='<jwt-secret>' \
  --parameters deployApiManagement=true \
  --parameters apiManagementPublisherEmail='you@example.com'
```

## Azure SQL Managed Identity

The SQL adapter supports both `SqlPassword` and `ActiveDirectoryManagedIdentity`.
The Bicep template keeps `SqlPassword` as the default so first-time deployments work without extra directory setup.

To switch the Function App to Managed Identity authentication:

1. Configure a Microsoft Entra admin for the Azure SQL server.
2. Connect to the database as that Entra admin.
3. Create a contained user for the Function App's managed identity:

```sql
CREATE USER [func-clinic-dev] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [func-clinic-dev];
ALTER ROLE db_datawriter ADD MEMBER [func-clinic-dev];
ALTER ROLE db_ddladmin ADD MEMBER [func-clinic-dev];
```

Then set:

```bash
az functionapp config appsettings set \
  --resource-group rg-clinic-dev \
  --name func-clinic-dev \
  --settings SQL_AUTHENTICATION=ActiveDirectoryManagedIdentity SQL_USER= SQL_PASSWORD=
```

## Load testing baseline

Recommended portfolio baseline:

- POST `/api/appointments`: 50, 100 and 250 concurrent virtual users.
- GET `/api/appointments/{insuredId}`: 50 and 100 concurrent virtual users.
- Capture p50, p95 and p99 latency.
- Track Function cold starts, Service Bus active messages and SQL connection pool usage.

Example with k6:

```bash
k6 run tests/load/appointments.js
```
