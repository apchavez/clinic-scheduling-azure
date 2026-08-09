// ============================================================================
//  main.bicep — Minimal serverless infra for the "createAppointment" flow.
//  Provisions: Cosmos DB (state), Service Bus (events), Storage + Function App,
//  Application Insights, Key Vault. Mirrors the AWS stack's core, on Azure.
//
//  Deploy:
//    az deployment sub create --location eastus \
//      --template-file infra/main.bicep --parameters infra/main.parameters.json
// ============================================================================

targetScope = 'subscription'

param projectName string = 'clinic'
param location string = 'eastus'
@allowed([ 'dev', 'test', 'prod' ])
param environment string = 'dev'

@description('Administrator password for the Azure SQL. Pass at deploy time, do not commit.')
@secure()
param sqlAdminPassword string

@description('HS256 secret used to sign/verify JWTs for the appointment endpoints. Pass at deploy time, do not commit.')
@secure()
param jwtSecret string

@description('Region for the App Service plan + Function App (separate due to per-region App Service quota).')
param appLocation string = 'centralus'

@description('Deploy Azure API Management in front of the Function App. Enabled by default to mirror the AWS sibling, which always fronts its API with API Gateway throttling.')
param deployApiManagement bool = true

@description('Publisher email required by API Management when deployApiManagement=true.')
param apiManagementPublisherEmail string = 'platform@example.com'

@description('Publisher name required by API Management when deployApiManagement=true.')
param apiManagementPublisherName string = 'Clinic Platform'

@description('Enable APIM JWT validation policy. Requires deployApiManagement=true and valid JWT settings.')
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

var tags = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
}
var rgName = 'rg-${projectName}-${environment}'
var suffix = uniqueString(subscription().subscriptionId, projectName, environment)

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module core 'core.bicep' = {
  scope: rg
  name: 'core'
  params: {
    projectName: projectName
    environment: environment
    location: location
    tags: tags
    suffix: suffix
    sqlAdminPassword: sqlAdminPassword
    jwtSecret: jwtSecret
    appLocation: appLocation
    deployApiManagement: deployApiManagement
    apiManagementPublisherEmail: apiManagementPublisherEmail
    apiManagementPublisherName: apiManagementPublisherName
    enableApiManagementJwtValidation: enableApiManagementJwtValidation
    apiManagementJwtOpenIdConfigUrl: apiManagementJwtOpenIdConfigUrl
    apiManagementJwtAudience: apiManagementJwtAudience
    deployAlerts: deployAlerts
    alertEmail: alertEmail
    allowPublicNetworkAccess: allowPublicNetworkAccess
  }
}

output resourceGroup string = rg.name
output functionAppName string = core.outputs.functionAppName
output cosmosAccountName string = core.outputs.cosmosAccountName
output serviceBusNamespace string = core.outputs.serviceBusNamespace
output sqlServerHost string = core.outputs.sqlServerHost
output keyVaultName string = core.outputs.keyVaultName
output apiManagementGatewayUrl string = core.outputs.apiManagementGatewayUrl
