"""Jinja2 templates for generated starter implementations. Output is intended to be valid, deployable code."""

TF_PROVIDERS = '''terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}
'''

TF_VARIABLES = '''variable "name" {
  description = "Workload name used in resource names."
  type        = string
  default     = "{{ name }}"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region. Must be an approved region (STD-CLD-001)."
  type        = string
  default     = "{{ region }}"

  validation {
    condition     = contains(["westeurope", "northeurope", "uksouth", "eastus2"], var.location)
    error_message = "Location must be an approved region."
  }
}

variable "address_space" {
  description = "Virtual network address space."
  type        = list(string)
  default     = ["10.40.0.0/16"]
}

variable "node_count" {
  description = "Nodes in the default pool (at least 3 for zone redundancy)."
  type        = number
  default     = 3
}

variable "tags" {
  description = "Mandatory tags (STD-CLD-003)."
  type        = map(string)
  default = {
    owner               = "{{ owner }}"
    cost_centre         = "CC-0000"
    data_classification = "confidential"
    managed_by          = "terraform"
  }
}
'''

TF_MAIN = '''locals {
  suffix = "${var.name}-${var.environment}"
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.suffix}"
  location = var.location
  tags     = var.tags
}

# ---------------------------------------------------------------- network
resource "azurerm_virtual_network" "this" {
  name                = "vnet-${local.suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = var.address_space
  tags                = var.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.40.0.0/20"]
}

resource "azurerm_subnet" "private" {
  name                                      = "snet-private"
  resource_group_name                       = azurerm_resource_group.this.name
  virtual_network_name                      = azurerm_virtual_network.this.name
  address_prefixes                          = ["10.40.16.0/24"]
  private_endpoint_network_policies_enabled = true
}

# --------------------------------------------------------------- key vault
resource "azurerm_key_vault" "this" {
  name                          = "kv-${substr(replace(local.suffix, "-", ""), 0, 20)}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  enable_rbac_authorization     = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = false # STD-SEC-014

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = var.tags
}

resource "azurerm_private_dns_zone" "vault" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "vault" {
  name                  = "link-vault-${local.suffix}"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.vault.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "azurerm_private_endpoint" "vault" {
  name                = "pe-kv-${local.suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private.id

  private_service_connection {
    name                           = "psc-kv-${local.suffix}"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.vault.id]
  }

  tags = var.tags
}

# --------------------------------------------------------------------- aks
resource "azurerm_kubernetes_cluster" "this" {
  name                      = "aks-${local.suffix}"
  location                  = azurerm_resource_group.this.location
  resource_group_name       = azurerm_resource_group.this.name
  dns_prefix                = "aks-${local.suffix}"
  private_cluster_enabled   = true
  sku_tier                  = "Standard"
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  azure_policy_enabled      = true

  default_node_pool {
    name           = "system"
    vm_size        = "Standard_D4s_v5"
    node_count     = var.node_count
    zones          = ["1", "2", "3"]
    vnet_subnet_id = azurerm_subnet.aks.id
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    network_policy = "azure"
  }

  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "aks_kv_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_kubernetes_cluster.this.key_vault_secrets_provider[0].secret_identity[0].object_id
}
{% if include_openai %}

# ------------------------------------------------------------ azure openai
resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-${local.suffix}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "oai-${local.suffix}"
  public_network_access_enabled = false # STD-SEC-014
  local_auth_enabled            = false # STD-SEC-004: managed identity only
  tags                          = var.tags
}

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-oai-${local.suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private.id

  private_service_connection {
    name                           = "psc-oai-${local.suffix}"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.openai.id]
  }

  tags = var.tags
}
{% endif %}
'''

TF_OUTPUTS = '''output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.this.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}
'''

BICEP = '''@description('Workload name used in resource names.')
param name string = '{{ name }}'

@description('Deployment environment.')
param environment string = 'prod'

@allowed([
  'westeurope'
  'northeurope'
  'uksouth'
  'eastus2'
])
param location string = '{{ region }}'

param tags object = {
  owner: '{{ owner }}'
  cost_centre: 'CC-0000'
  data_classification: 'confidential'
  managed_by: 'bicep'
}

var suffix = '${name}-${environment}'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-${suffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.40.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'snet-aks'
        properties: {
          addressPrefix: '10.40.0.0/20'
        }
      }
      {
        name: 'snet-private'
        properties: {
          addressPrefix: '10.40.16.0/24'
          privateEndpointNetworkPolicies: 'Enabled'
        }
      }
    ]
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${take(replace(suffix, '-', ''), 20)}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-kv-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/snet-private'
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-kv-${suffix}'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource aks 'Microsoft.ContainerService/managedClusters@2024-02-01' = {
  name: 'aks-${suffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Base'
    tier: 'Standard'
  }
  properties: {
    dnsPrefix: 'aks-${suffix}'
    apiServerAccessProfile: {
      enablePrivateCluster: true
    }
    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPolicy: 'azure'
    }
    agentPoolProfiles: [
      {
        name: 'system'
        count: 3
        vmSize: 'Standard_D4s_v5'
        mode: 'System'
        availabilityZones: [
          '1'
          '2'
          '3'
        ]
        vnetSubnetID: '${vnet.id}/subnets/snet-aks'
      }
    ]
  }
}

output keyVaultUri string = keyVault.properties.vaultUri
output aksName string = aks.name
'''

OPENAPI_CUSTOMER = '''openapi: 3.1.0
info:
  title: {{ title }}
  version: {{ version }}
  summary: Customer master data for Northwind Assurance.
  description: |
    System API in front of the Customer Master (MDM). Replaces Customer API v1.
    Owned by the Customer Data (MDM) team. Published through Azure API Management.
  contact:
    name: Customer Data (MDM)
    email: customer-data@northwind-assurance.example
servers:
  - url: https://api.northwind-assurance.example/customer/{{ version_path }}
    description: Production via API Management
security:
  - oauth2: [customer.read]
tags:
  - name: Customers
  - name: Contacts
  - name: Consents
paths:
  /customers:
    get:
      operationId: listCustomers
      summary: Search customers
      tags: [Customers]
      parameters:
        - name: q
          in: query
          schema: { type: string, minLength: 2 }
        - name: limit
          in: query
          schema: { type: integer, minimum: 1, maximum: 200, default: 50 }
        - name: cursor
          in: query
          schema: { type: string }
      responses:
        "200":
          description: A page of customers
          content:
            application/json:
              schema:
                type: object
                required: [items]
                properties:
                  items:
                    type: array
                    items: { $ref: "#/components/schemas/Customer" }
                  nextCursor: { type: [string, "null"] }
        "401": { $ref: "#/components/responses/Problem" }
    post:
      operationId: createCustomer
      summary: Create a customer
      tags: [Customers]
      security:
        - oauth2: [customer.write]
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/CustomerInput" }
      responses:
        "201":
          description: Created
          headers:
            Location: { schema: { type: string, format: uri } }
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Customer" }
        "409": { $ref: "#/components/responses/Problem" }
        "422": { $ref: "#/components/responses/Problem" }
  /customers/{customerId}:
    parameters:
      - $ref: "#/components/parameters/CustomerId"
    get:
      operationId: getCustomer
      summary: Get a customer
      tags: [Customers]
      responses:
        "200":
          description: The customer
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Customer" }
        "404": { $ref: "#/components/responses/Problem" }
    patch:
      operationId: updateCustomer
      summary: Update a customer
      tags: [Customers]
      security:
        - oauth2: [customer.write]
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: { $ref: "#/components/schemas/CustomerInput" }
      responses:
        "200":
          description: Updated
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Customer" }
        "404": { $ref: "#/components/responses/Problem" }
  /customers/{customerId}/contacts:
    parameters:
      - $ref: "#/components/parameters/CustomerId"
    get:
      operationId: listContacts
      summary: List contact points
      tags: [Contacts]
      responses:
        "200":
          description: Contact points
          content:
            application/json:
              schema:
                type: array
                items: { $ref: "#/components/schemas/Contact" }
  /customers/{customerId}/consents:
    parameters:
      - $ref: "#/components/parameters/CustomerId"
    get:
      operationId: listConsents
      summary: List consent records
      tags: [Consents]
      responses:
        "200":
          description: Consent records
          content:
            application/json:
              schema:
                type: array
                items: { $ref: "#/components/schemas/Consent" }
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://login.northwind-assurance.example/oauth2/v2.0/token
          scopes:
            customer.read: Read customer data
            customer.write: Create and update customer data
  parameters:
    CustomerId:
      name: customerId
      in: path
      required: true
      schema: { type: string, pattern: "^CUS-[0-9]{8}$" }
  responses:
    Problem:
      description: Error (RFC 9457 problem details)
      content:
        application/problem+json:
          schema: { $ref: "#/components/schemas/Problem" }
  schemas:
    Customer:
      allOf:
        - $ref: "#/components/schemas/CustomerInput"
        - type: object
          required: [id, createdAt]
          properties:
            id: { type: string, examples: ["CUS-00481723"] }
            createdAt: { type: string, format: date-time }
            updatedAt: { type: string, format: date-time }
    CustomerInput:
      type: object
      required: [givenName, familyName, dateOfBirth]
      properties:
        givenName: { type: string, maxLength: 80 }
        familyName: { type: string, maxLength: 80 }
        dateOfBirth: { type: string, format: date }
        segment: { type: string, enum: [retail, sme, corporate] }
        address: { $ref: "#/components/schemas/Address" }
    Address:
      type: object
      required: [line1, city, postalCode, country]
      properties:
        line1: { type: string }
        line2: { type: string }
        city: { type: string }
        postalCode: { type: string }
        country: { type: string, minLength: 2, maxLength: 2 }
    Contact:
      type: object
      required: [type, value]
      properties:
        type: { type: string, enum: [email, phone, postal] }
        value: { type: string }
        preferred: { type: boolean }
    Consent:
      type: object
      required: [purpose, granted, recordedAt]
      properties:
        purpose: { type: string, examples: [marketing_email] }
        granted: { type: boolean }
        recordedAt: { type: string, format: date-time }
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        traceId: { type: string }
'''

OPENAPI_GENERIC = '''openapi: 3.1.0
info:
  title: {{ title }}
  version: {{ version }}
  description: System API generated by ArchIQ for the {{ domain }} domain.
servers:
  - url: https://api.northwind-assurance.example/{{ slug }}/{{ version_path }}
security:
  - oauth2: [{{ slug }}.read]
paths:
  /{{ plural }}:
    get:
      operationId: list{{ Resource }}s
      summary: List {{ plural }}
      parameters:
        - name: limit
          in: query
          schema: { type: integer, minimum: 1, maximum: 200, default: 50 }
      responses:
        "200":
          description: A page of {{ plural }}
          content:
            application/json:
              schema:
                type: object
                required: [items]
                properties:
                  items:
                    type: array
                    items: { $ref: "#/components/schemas/{{ Resource }}" }
  /{{ plural }}/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema: { type: string }
    get:
      operationId: get{{ Resource }}
      summary: Get a {{ resource }}
      responses:
        "200":
          description: The {{ resource }}
          content:
            application/json:
              schema: { $ref: "#/components/schemas/{{ Resource }}" }
        "404":
          description: Not found
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://login.northwind-assurance.example/oauth2/v2.0/token
          scopes:
            {{ slug }}.read: Read access
  schemas:
    {{ Resource }}:
      type: object
      required: [id, status]
      properties:
        id: { type: string }
        status: { type: string, enum: [active, suspended, closed] }
        createdAt: { type: string, format: date-time }
'''

FASTAPI_MAIN = '''"""{{ title }}: service skeleton generated by ArchIQ."""
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="{{ title }}", version="{{ version }}")


class {{ Resource }}(BaseModel):
    id: str = Field(examples=["{{ id_example }}"])
    status: str = "active"
    created_at: datetime


_DB: dict[str, {{ Resource }}] = {
    "{{ id_example }}": {{ Resource }}(id="{{ id_example }}", created_at=datetime.now(timezone.utc)),
}


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{{ plural }}", response_model=list[{{ Resource }}])
def list_{{ plural_py }}(limit: int = Query(50, ge=1, le=200)) -> list[{{ Resource }}]:
    return list(_DB.values())[:limit]


@app.get("/{{ plural }}/{item_id}", response_model={{ Resource }})
def get_{{ resource_py }}(item_id: str) -> {{ Resource }}:
    item = _DB.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="{{ Resource }} not found")
    return item
'''

FASTAPI_TEST = '''from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_list() -> None:
    r = client.get("/{{ plural }}")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_not_found() -> None:
    assert client.get("/{{ plural }}/does-not-exist").status_code == 404
'''

FASTAPI_REQ = '''fastapi>=0.115,<1
uvicorn[standard]>=0.30
pydantic>=2.8,<3
httpx>=0.27
pytest>=8.2
'''

DOCKERFILE = '''# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /src
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home appuser
WORKDIR /app
COPY --from=build /install /usr/local
COPY app ./app
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
'''

CI = '''name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest -q

  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx --yes @stoplight/spectral-cli lint openapi/{{ slug }}.yaml

  infrastructure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform -chdir=infra/terraform fmt -check -recursive
      - run: terraform -chdir=infra/terraform init -backend=false
      - run: terraform -chdir=infra/terraform validate
      - uses: aquasecurity/trivy-action@0.24.0
        with:
          scan-type: config
          scan-ref: infra/terraform
          exit-code: "1"
          severity: HIGH,CRITICAL

  image:
    needs: [test, contract, infrastructure]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t {{ slug }}:${{ '{{' }} github.sha {{ '}}' }} .
      - uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: {{ slug }}:${{ '{{' }} github.sha {{ '}}' }}
          exit-code: "1"
          severity: CRITICAL
'''

SPRING_POM = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.4</version>
    <relativePath/>
  </parent>
  <groupId>com.northwind.{{ pkg }}</groupId>
  <artifactId>{{ slug }}</artifactId>
  <version>{{ version }}.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
'''

SPRING_APP = '''package com.northwind.{{ pkg }};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
'''

SPRING_CONTROLLER = '''package com.northwind.{{ pkg }};

import java.time.Instant;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/{{ plural }}")
public class {{ Resource }}Controller {

    public record {{ Resource }}(String id, String status, Instant createdAt) {}

    private static final List<{{ Resource }}> DATA =
            List.of(new {{ Resource }}("{{ id_example }}", "active", Instant.now()));

    @GetMapping
    public List<{{ Resource }}> list() {
        return DATA;
    }

    @GetMapping("/{id}")
    public {{ Resource }} get(@PathVariable String id) {
        return DATA.stream()
                .filter(x -> x.id().equals(id))
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
'''

SPRING_YML = '''server:
  port: 8080
management:
  endpoints:
    web:
      exposure:
        include: health,info
spring:
  application:
    name: {{ slug }}
'''

README = '''# {{ title }}

Starter implementation generated by ArchIQ from **{{ origin }}**.

| Path | Purpose |
|---|---|
{% for f in files %}
| `{{ f }}` | generated |
{% endfor %}

## Deploy

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -out tfplan
terraform -chdir=infra/terraform apply tfplan
```

Infrastructure follows STD-SEC-014 (private endpoints only), STD-SEC-003 (secrets in Key Vault) and STD-CLD-003 (mandatory tags).
'''
