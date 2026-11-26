// Claims Copilot: production environment, Bicep (as deployed 2026-10-30)
// Owner: AI & Automation.
param location string = 'West Europe'
param publicAccess bool = true
var tags = {
  owner: 'ai-automation'
  'cost-centre': 'CC-4410'
}

resource aoai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'aoai-claims-copilot'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    publicNetworkAccess: publicAccess ? 'Enabled' : 'Disabled'
    disableLocalAuth: false
  }
  tags: tags
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stclaimscopilot'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_GRS' }
  properties: {
    minimumTlsVersion: 'TLS1_0'
    publicNetworkAccess: 'Enabled'
  }
}

resource api 'Microsoft.Web/sites@2022-09-01' = {
  name: 'app-claims-copilot'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AZURE_OPENAI_KEY', value: '5c1f-REDACTED' }
      ]
    }
  }
  tags: tags
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-law'
  scope: api
  properties: { workspaceId: 'x' }
}

