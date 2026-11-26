# Claims Copilot: production environment (as deployed 2026-10-30)
# Owner: AI & Automation. Managed by Terraform.

variable "location" {
  default = "westeurope"
}

locals {
  common_tags = {
    owner       = "ai-automation"
    cost_centre = "CC-4410"
    environment = "production"
  }
}

resource "azurerm_resource_group" "copilot" {
  name     = "rg-claims-copilot-prod"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_cognitive_account" "aoai" {
  name                          = "aoai-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "aoai-claims-copilot-prod"
  public_network_access_enabled = true
  local_auth_enabled            = true
  tags                          = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.aoai.id
  rai_policy_name      = "Microsoft.Default"
  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06"
  }
}

resource "azurerm_storage_account" "sessions" {
  name                          = "stclaimscopilotprod"
  resource_group_name           = azurerm_resource_group.copilot.name
  location                      = var.location
  account_tier                  = "Standard"
  account_replication_type      = "GRS"
  min_tls_version               = "TLS1_0"
  public_network_access_enabled = true
  tags = {
    owner = "ai-automation"
  }
}

resource "azurerm_key_vault" "kv" {
  name                          = "kv-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = local.common_tags
}

resource "azurerm_linux_web_app" "api" {
  name                = "app-claims-copilot-api"
  location            = var.location
  resource_group_name = azurerm_resource_group.copilot.name
  service_plan_id     = azurerm_service_plan.plan.id
  identity {
    type = "SystemAssigned"
  }
  app_settings = {
    AZURE_OPENAI_KEY = "5c1f0d3e-REDACTED"
    SESSION_STORE    = "stclaimscopilotprod"
  }
  site_config {
    minimum_tls_version = "1.2"
  }
  tags = local.common_tags
}

resource "azurerm_monitor_diagnostic_setting" "api" {
  name               = "send-to-law"
  target_resource_id = azurerm_linux_web_app.api.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}
