// Claims Copilot: production environment, Bicep (remediated)
// Owner: AI & Automation.
param location string = 'westeurope'
var tags = {
  owner: 'ai-automation'
  'cost-centre': 'CC-4410'
  'data-classification': 'confidential'
}
resource aoai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'aoai'
  location: location
  kind: 'OpenAI'
  properties: {
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
  }
  tags: tags
}
resource pe 'Microsoft.Network/privateEndpoints@2023-04-01' = {
  name: 'pe-aoai'
  location: location
  properties: {
    privateLinkServiceConnections: [
      { name: 'aoai', properties: { privateLinkServiceId: aoai.id, groupIds: ['account'] } }
    ]
  }
}
resource dep 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: aoai
  name: 'gpt-4o'
  properties: { raiPolicyName: 'Microsoft.Default' }
}
resource d 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'law'
  scope: aoai
  properties: { workspaceId: 'x' }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stclaimscopilot'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_GRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
  }
  tags: tags
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 365 }
  }
}

resource storageDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'law'
  scope: storage
  properties: { workspaceId: 'x' }
}
