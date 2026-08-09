# Deployment Guide

## GitHub Actions deployment

The `Deploy` workflow deploys infrastructure, publishes the Azure Functions app and can run Postman integration tests.

Required repository or environment variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Required secrets:

- `SQL_ADMIN_PASSWORD`
- `JWT_SECRET` — HS256 secret used to sign/verify appointment endpoint JWTs (see [auth_guard.py](../clinic/infrastructure/auth/auth_guard.py)). Generate with e.g. `openssl rand -base64 32`.

Optional variables:

- `ALERT_EMAIL`
- `APIM_JWT_OPENID_CONFIG_URL`
- `APIM_JWT_AUDIENCE`

Recommended setup:

1. Create GitHub environments named `dev`, `test` and `prod`.
2. Add the Azure OIDC variables to each environment.
3. Add `SQL_ADMIN_PASSWORD` and `JWT_SECRET` as environment secrets.
4. Run the `Deploy` workflow manually and choose the target environment.

## Environment parameter files

The infrastructure has separate parameter files:

- `infra/parameters.dev.json`
- `infra/parameters.test.json`
- `infra/parameters.prod.json`

Local deployment example:

```bash
az deployment sub create \
  --location eastus \
  --template-file infra/main.bicep \
  --parameters infra/parameters.dev.json \
  --parameters sqlAdminPassword='<password>' \
  --parameters jwtSecret='<jwt-secret>' \
  --name clinic-dev
```

## API Management JWT validation

Function-level JWT validation (`auth_guard`) is always enforced regardless of APIM. This section is an
**optional extra layer** — useful if you want centralized rate limiting/token validation at the gateway
before requests even reach the Function App. Enable APIM and JWT validation together:

```bash
az deployment sub create \
  --location eastus \
  --template-file infra/main.bicep \
  --parameters infra/parameters.test.json \
  --parameters sqlAdminPassword='<password>' \
  --parameters jwtSecret='<jwt-secret>' \
  --parameters deployApiManagement=true \
  --parameters enableApiManagementJwtValidation=true \
  --parameters apiManagementJwtOpenIdConfigUrl='https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration' \
  --parameters apiManagementJwtAudience='api://<application-client-id>'
```

When JWT validation is disabled, APIM still applies a basic rate limit policy.

## Alerts

Enable email alerts:

```bash
az deployment sub create \
  --location eastus \
  --template-file infra/main.bicep \
  --parameters infra/parameters.prod.json \
  --parameters sqlAdminPassword='<password>' \
  --parameters jwtSecret='<jwt-secret>' \
  --parameters deployAlerts=true \
  --parameters alertEmail='you@example.com'
```

Alerts included:

- Function App HTTP 5xx responses.
- Function App average response time above two seconds.

## Network hardening

The template exposes `allowPublicNetworkAccess`.

Keep it as `true` unless you have private connectivity ready. Setting it to `false` disables public access on supported data services and requires private endpoints or equivalent private routing for the Function App.

## Shutdown / cost control

This project is serverless/event-driven in architecture, but the current Azure implementation includes resources that can generate cost while deployed:

- App Service Plan B1.
- Azure SQL Basic.
- Service Bus Standard.
- Log Analytics / Application Insights ingestion.

To stop costs after testing, run the `Destroy` GitHub Actions workflow:

1. Choose the deployed environment: `dev`, `test` or `prod`.
2. Type `DELETE` in the confirmation field.
3. The workflow deletes the full resource group, for example `rg-clinic-dev`.

Local equivalent:

```bash
az group delete --name rg-clinic-dev --yes
```

The GitHub OIDC App Registration and repo variables do not run workloads and do not need to be deleted for cost control.
