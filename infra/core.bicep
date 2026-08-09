// core.bicep — all resources for the createAppointment flow, in one module.
// Secrets strategy:
//   • Cosmos DB  → Managed Identity (CosmosDBDataContributor role) — no key in config
//   • Service Bus → Managed Identity (ServiceBusDataOwner role)    — no connection string in config
//   • SQL password → stored in Key Vault; Function App reads via KV reference (@Microsoft.KeyVault(...))

param projectName string
param environment string
param location string
param tags object
@minLength(3)
param suffix string

@secure()
param sqlAdminPassword string

@description('HS256 secret used to sign/verify JWTs for the appointment endpoints (see AuthGuard.java). Generate with e.g. `openssl rand -base64 32`.')
@secure()
param jwtSecret string

@description('SQL administrator username.')
param sqlAdminUser string = 'clinicadmin'

@description('Region for Azure SQL (separate because not all regions accept new SQL servers).')
param sqlLocation string = 'westus3'

@description('Region for the App Service plan + Function App.')
param appLocation string = 'centralus'

@description('Deploy Azure API Management in front of the Function App. Enabled by default to mirror the AWS sibling, which always fronts its API with API Gateway throttling.')
param deployApiManagement bool = true

@description('Publisher email required by API Management.')
param apiManagementPublisherEmail string = 'platform@example.com'

@description('Publisher name required by API Management.')
param apiManagementPublisherName string = 'Clinic Platform'

@description('Enable APIM JWT validation policy.')
param enableApiManagementJwtValidation bool = false

@description('OpenID Connect metadata URL used by APIM validate-jwt policy.')
param apiManagementJwtOpenIdConfigUrl string = ''

@description('Expected JWT audience used by APIM validate-jwt policy.')
param apiManagementJwtAudience string = ''

@description('Deploy Azure Monitor action group and alerts.')
param deployAlerts bool = false

@description('Email receiver for Azure Monitor alerts.')
param alertEmail string = ''

@description('Allow public network access to cloud data services. Keep true unless private networking is configured.')
param allowPublicNetworkAccess bool = true

var sqlServerHost = '${sqlServer.name}${az.environment().suffixes.sqlServerHostname}'
var deployJwtPolicy = deployApiManagement && enableApiManagementJwtValidation && !empty(apiManagementJwtOpenIdConfigUrl) && !empty(apiManagementJwtAudience)
var deployEmailAlerts = deployAlerts && !empty(alertEmail)
var publicNetworkAccess = allowPublicNetworkAccess ? 'Enabled' : 'Disabled'

// --- Cosmos DB (state tracking, serverless) ---
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${projectName}-${environment}-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [ { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [ { locationName: location, failoverPriority: 0 } ]
    publicNetworkAccess: publicNetworkAccess
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'clinicdb'
  properties: { resource: { id: 'clinicdb' } }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'appointments'
  properties: {
    resource: {
      id: 'appointments'
      partitionKey: { paths: [ '/id' ], kind: 'Hash' }
    }
  }
}

// Append-only event log container (CosmosAppointmentEventStore) — partitioned by appointmentId
// so all events for one appointment are co-located.
resource cosmosEventsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'appointment-events'
  properties: {
    resource: {
      id: 'appointment-events'
      partitionKey: { paths: [ '/appointmentId' ], kind: 'Hash' }
    }
  }
}

// --- Service Bus (event backbone: single topic, single subscription) ---
resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'sb-${projectName}-${environment}-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: publicNetworkAccess
  }
}

resource createdTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: sb
  name: 'appointment-created'
  properties: { defaultMessageTimeToLive: 'P14D' }
}

// Single worker subscription - one Cosmos DB / Azure SQL instance handles every
// appointment, so there's no reason to split into multiple subscriptions/workers.
// The auto-created $Default rule (TrueFilter, matches everything) is left as-is.
resource subWorker 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: createdTopic
  name: 'appointment-worker'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT1M'
  }
}

// Queue fed by the Event Grid Subscription below - AWS-sibling equivalent of
// ConfirmationsQueue/EventRuleToSQS. `confirmAppointment` (function_app.py) consumes it to
// finish the appointment lifecycle, decoupled from the relational-persist worker above.
resource confirmationsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'appointment-confirmations'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT1M'
  }
}

// --- Event Grid (AWS-sibling equivalent of EventBridge) ---
// AppointmentWorker (function_app.py) publishes "AppointmentConfirmed" here after persisting the
// final record to Azure SQL, instead of completing the lifecycle itself - a separate Event Grid
// Subscription routes it to confirmationsQueue above, mirroring EventBridge's Rule -> SQS hop.
resource eventGridTopic 'Microsoft.EventGrid/topics@2022-06-15' = {
  name: 'evgt-${projectName}-${environment}-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    inputSchema: 'CloudEventSchemaV1_0'
    publicNetworkAccess: publicNetworkAccess
  }
}

// Identity-based delivery (the topic's own system-assigned identity, granted Service Bus Data
// Sender below) instead of a connection-string/access-key destination - keeps this consistent
// with the rest of the project's no-secrets-in-config approach.
resource eventGridSubToConfirmationsQueue 'Microsoft.EventGrid/topics/eventSubscriptions@2022-06-15' = {
  parent: eventGridTopic
  name: 'to-confirmations-queue'
  properties: {
    deliveryWithResourceIdentity: {
      identity: { type: 'SystemAssigned' }
      destination: {
        endpointType: 'ServiceBusQueue'
        properties: {
          resourceId: confirmationsQueue.id
        }
      }
    }
    filter: {
      includedEventTypes: [ 'AppointmentConfirmed' ]
    }
    eventDeliverySchema: 'CloudEventSchemaV1_0'
  }
  // Without this, ARM has no ordering guarantee between the eventGridToSbRole role assignment
  // and this subscription, so RBAC can still be propagating when Event Grid validates the
  // destination, producing "Managed Identity ... does not have permission" at deploy time.
  dependsOn: [
    eventGridToSbRole
  ]
}

// --- Monitoring ---
resource log 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${projectName}-${environment}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${projectName}-${environment}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: log.id }
}

resource observabilityWorkbook 'Microsoft.Insights/workbooks@2022-04-01' = {
  name: guid(resourceGroup().id, 'clinic-observability-workbook')
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'Clinic ${environment} - Observability'
    category: 'workbook'
    sourceId: log.id
    serializedData: string({
      version: 'Notebook/1.0'
      items: [
        {
          type: 1
          content: {
            json: '# Clinic Scheduling Observability\n\nOperational view for appointment lifecycle, API latency and worker failures.'
          }
          name: 'title'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: 'traces | where message has_any ("appointment.accepted", "appointment.processing", "appointment.completed") | extend appointmentId = extract("appointmentId=([^ ]+)", 1, message) | project timestamp, message, appointmentId, operation_Id | order by timestamp desc'
            size: 0
            title: 'Appointment lifecycle'
            queryType: 0
            resourceType: 'microsoft.operationalinsights/workspaces'
          }
          name: 'appointment-lifecycle'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: 'requests | summarize count(), avg(duration), percentile(duration, 95) by name, resultCode | order by name asc'
            size: 0
            title: 'API latency and status codes'
            queryType: 0
            resourceType: 'microsoft.operationalinsights/workspaces'
          }
          name: 'api-latency'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: 'traces | where severityLevel >= 3 | project timestamp, message, operation_Id | order by timestamp desc'
            size: 0
            title: 'Failures'
            queryType: 0
            resourceType: 'microsoft.operationalinsights/workspaces'
          }
          name: 'failures'
        }
      ]
    })
  }
}

resource alertActionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (deployEmailAlerts) {
  name: 'ag-${projectName}-${environment}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'clinic${environment}'
    enabled: true
    emailReceivers: [
      {
        name: 'primary'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource function5xxAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (deployEmailAlerts) {
  name: 'alert-${projectName}-${environment}-function-5xx'
  location: 'global'
  tags: tags
  properties: {
    description: 'Triggers when the Function App returns HTTP 5xx responses.'
    severity: 2
    enabled: true
    scopes: [ functionApp.id ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'Http5xx'
          metricName: 'Http5xx'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: alertActionGroup.id
      }
    ]
  }
}

resource functionLatencyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (deployEmailAlerts) {
  name: 'alert-${projectName}-${environment}-function-latency'
  location: 'global'
  tags: tags
  properties: {
    description: 'Triggers when average Function App response time is above two seconds.'
    severity: 3
    enabled: true
    scopes: [ functionApp.id ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HttpResponseTime'
          metricName: 'HttpResponseTime'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 2
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: alertActionGroup.id
      }
    ]
  }
}

// --- Storage (Functions runtime) ---
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${projectName}${environment}${suffix}', 24)
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    allowSharedKeyAccess: false
    publicNetworkAccess: publicNetworkAccess
  }
}

// --- Azure SQL Database (final relational persistence) ---
// Used instead of Azure Database for MySQL because new free subscriptions are
// temporarily blocked from provisioning MySQL Flexible Server. Equivalent role
// to the AWS project's MySQL store for completed appointments.
// Deployed in sqlLocation (westus3) because not all regions accept new SQL servers.
resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-${projectName}-${environment}-${suffix}'
  location: sqlLocation
  tags: tags
  properties: {
    administratorLogin: sqlAdminUser
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: publicNetworkAccess
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'clinicdb'
  location: sqlLocation
  tags: tags
  sku: { name: 'Basic', tier: 'Basic' }
}

// Allow other Azure services (the Function App) to reach the server.
// Firewall rules can only be created when the server's public network interface is enabled —
// Azure rejects rule writes outright (DenyPublicEndpointEnabled) when it's disabled.
resource sqlFirewallAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (allowPublicNetworkAccess) {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// --- Key Vault (secrets store: SQL password) ---
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv-${projectName}-${environment}-${suffix}', 24)
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: publicNetworkAccess
  }
}

resource kvSqlPassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'sql-admin-password'
  properties: { value: sqlAdminPassword }
}

resource kvJwtSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'jwt-secret'
  properties: { value: jwtSecret }
}

// --- App Service Plan B1 + Function App (Java 21) ---
// Switched from Flex Consumption to B1 because Flex + Java had deployment
// friction (no remote build for Java, zip package not registering) — kept B1 after
// the Python port for continuity. B1 is a dedicated plan that reliably supports
// standard zip deployment. Trade-off: always-on (no scale-to-zero) vs. predictable deploy.
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-${projectName}-${environment}'
  location: appLocation
  tags: tags
  sku: { name: 'B1', tier: 'Basic' }
  kind: 'linux'
  properties: { reserved: true }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: 'func-${projectName}-${environment}'
  location: appLocation
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      alwaysOn: true
      appSettings: [
        // Storage: Managed Identity — no account key in config
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
        // Required for the Python v2 decorator-based programming model (function_app.py) —
        // without this the runtime never indexes the decorated functions, so it deploys with
        // zero registered routes and every request 404s.
        { name: 'AzureWebJobsFeatureFlags', value: 'EnableWorkerIndexing' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        // Cosmos: endpoint only — SDK uses the Function App's Managed Identity (no key)
        { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE', value: 'clinicdb' }
        { name: 'COSMOS_CONTAINER', value: 'appointments' }
        { name: 'COSMOS_EVENTS_CONTAINER', value: 'appointment-events' }
        // Service Bus: Azure Functions MI convention — triggers read SERVICEBUS__fullyQualifiedNamespace,
        // SDK publisher reads the same var via AppContext.
        { name: 'SERVICEBUS__fullyQualifiedNamespace', value: '${sb.name}.servicebus.windows.net' }
        { name: 'SERVICEBUS_CREATED_TOPIC', value: 'appointment-created' }
        // Event Grid: endpoint only — SDK publishes via the Function App's Managed Identity (no key)
        { name: 'EVENTGRID_TOPIC_ENDPOINT', value: eventGridTopic.properties.endpoint }
        // SQL: password via Key Vault reference — never stored in plain config
        { name: 'SQL_HOST', value: sqlServerHost }
        { name: 'SQL_DATABASE', value: 'clinicdb' }
        { name: 'SQL_AUTHENTICATION', value: 'SqlPassword' }
        { name: 'SQL_USER', value: sqlAdminUser }
        { name: 'SQL_PASSWORD', value: '@Microsoft.KeyVault(VaultName=${kv.name};SecretName=sql-admin-password)' }
        // JWT: HS256 secret via Key Vault reference — enforced in-function by AuthGuard regardless
        // of whether API Management (and its optional validate-jwt policy) is deployed.
        { name: 'JWT_SECRET', value: '@Microsoft.KeyVault(VaultName=${kv.name};SecretName=jwt-secret)' }
      ]
    }
  }
}

// --- Optional API Management facade ---
// StandardV2 (launched 2023 - distinct SKU family from the classic Basic/Standard tiers, not
// just a bigger Consumption) provisions/tears down in minutes like Consumption (classic
// Basic/Standard take 30-45 min) AND supports rate-limit-by-key, unlike Consumption. That
// combination - fast deploy/destroy plus real throttling - is why this replaced Consumption,
// matching the AWS/GCP siblings' rate-limit behavior without the classic tiers' slow lifecycle.
resource apiManagement 'Microsoft.ApiManagement/service@2023-09-01-preview' = if (deployApiManagement) {
  name: 'apim-${projectName}-${environment}-${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'StandardV2'
    capacity: 1
  }
  properties: {
    publisherEmail: apiManagementPublisherEmail
    publisherName: apiManagementPublisherName
  }
}

resource appointmentsApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = if (deployApiManagement) {
  parent: apiManagement
  name: 'clinic-appointments'
  properties: {
    displayName: 'Clinic Appointments API'
    path: 'clinic'
    protocols: [ 'https' ]
    serviceUrl: 'https://${functionApp.name}.azurewebsites.net/api'
    subscriptionRequired: false
  }
}

resource createAppointmentOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = if (deployApiManagement) {
  parent: appointmentsApi
  name: 'create-appointment'
  properties: {
    displayName: 'Create appointment'
    method: 'POST'
    urlTemplate: '/appointments'
    responses: [
      { statusCode: 202, description: 'Appointment accepted for asynchronous processing' }
      { statusCode: 400, description: 'Invalid request' }
      { statusCode: 500, description: 'Internal server error' }
    ]
  }
}

resource getAppointmentsOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = if (deployApiManagement) {
  parent: appointmentsApi
  name: 'get-appointments'
  properties: {
    displayName: 'Get appointments by insured'
    method: 'GET'
    urlTemplate: '/appointments/{insuredId}'
    templateParameters: [
      {
        name: 'insuredId'
        type: 'string'
        required: true
      }
    ]
    responses: [
      { statusCode: 200, description: 'Appointments for the insured' }
      { statusCode: 400, description: 'Missing insuredId' }
      { statusCode: 500, description: 'Internal server error' }
    ]
  }
}

resource getAppointmentHistoryOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = if (deployApiManagement) {
  parent: appointmentsApi
  name: 'get-appointment-history'
  properties: {
    displayName: 'Get appointment history'
    method: 'GET'
    urlTemplate: '/appointments/{appointmentId}/history'
    templateParameters: [
      {
        name: 'appointmentId'
        type: 'string'
        required: true
      }
    ]
    responses: [
      { statusCode: 200, description: 'Appointment event history' }
      { statusCode: 404, description: 'Appointment not found' }
      { statusCode: 500, description: 'Internal server error' }
    ]
  }
}

resource healthOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = if (deployApiManagement) {
  parent: appointmentsApi
  name: 'health-check'
  properties: {
    displayName: 'Health check'
    method: 'GET'
    urlTemplate: '/health'
    responses: [
      { statusCode: 200, description: 'Service health status' }
      { statusCode: 500, description: 'Internal server error' }
    ]
  }
}

resource appointmentsApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = if (deployApiManagement) {
  parent: appointmentsApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    // rate-limit-by-key requires Basic+ (Consumption rejects it with a ValidationError at deploy
    // time). Now that this service runs on StandardV2, the throttle is reinstated: 25 calls per
    // 1-second window, keyed by subscription key when present and falling back to caller IP.
    value: deployJwtPolicy
      ? '<policies><inbound><base /><validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"><openid-config url="${apiManagementJwtOpenIdConfigUrl}" /><audiences><audience>${apiManagementJwtAudience}</audience></audiences></validate-jwt><rate-limit-by-key calls="25" renewal-period="1" counter-key="@(context.Subscription?.Key ?? context.Request.IpAddress)" /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'
      : '<policies><inbound><base /><rate-limit-by-key calls="25" renewal-period="1" counter-key="@(context.Subscription?.Key ?? context.Request.IpAddress)" /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'
  }
}

// --- Managed Identity role assignments ---

// Cosmos DB Data Contributor — allows the Function App to read/write documents without a key
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'
resource cosmosFuncRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, functionApp.id, cosmosDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'
    principalId: functionApp.identity.principalId
    scope: cosmos.id
  }
}

// Service Bus Data Owner — allows publish and consume without a connection string
var sbDataOwnerRoleId = '090c5cfd-751d-490a-894a-3ce6f1109419'
resource sbFuncRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: sb
  name: guid(sb.id, functionApp.id, sbDataOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sbDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// EventGrid Data Sender — allows the Function App to publish CloudEvents to eventGridTopic
var eventGridDataSenderRoleId = 'd5a91429-5739-47e2-a06b-3470a27159e7'
resource eventGridFuncRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: eventGridTopic
  name: guid(eventGridTopic.id, functionApp.id, eventGridDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventGridDataSenderRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Azure Service Bus Data Sender — allows the Event Grid Subscription's own system-assigned
// identity to deliver into confirmationsQueue (identity-based delivery, no connection string)
var sbDataSenderRoleId = '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
resource eventGridToSbRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: sb
  name: guid(sb.id, eventGridTopic.id, sbDataSenderRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sbDataSenderRoleId)
    principalId: eventGridTopic.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets User — allows the Function App to resolve the KV reference for SQL_PASSWORD
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
resource kvFuncRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, functionApp.id, kvSecretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage role assignments — required for AzureWebJobsStorage with Managed Identity
var storageBlobOwnerRoleId    = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueContribRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableContribRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageBlobOwnerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageQueueContribRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueContribRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageTableContribRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableContribRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output functionAppName string = functionApp.name
output cosmosAccountName string = cosmos.name
output serviceBusNamespace string = sb.name
output eventGridTopicName string = eventGridTopic.name
output sqlServerHost string = sqlServerHost
output keyVaultName string = kv.name
output apiManagementGatewayUrl string = deployApiManagement ? apiManagement!.properties.gatewayUrl : ''
