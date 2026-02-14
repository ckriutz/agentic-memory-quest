#!/usr/bin/env bash
set -euo pipefail

# Deployment script for memquest-server-turbo (Azure AI Search edition)
# Deploys alongside the original memquest-server for A/B comparison.
# Loads environment variables from server/.env file.

say() { printf "%s\n" "$*"; }

die() {
  printf "ERROR: %s\n" "$*" >&2
  exit 1
}

# Resolve repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load environment variables from server .env
ENV_FILE="${REPO_ROOT}/server/memoryquest_server/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  die "Environment file not found: $ENV_FILE"
fi

say "Loading environment from: $ENV_FILE"
set +u          # allow undefined vars during .env source (e.g. $Default)
set -a
source "$ENV_FILE"
set +a
set -u

# Azure config
AZ_SUBSCRIPTION_ID="be2cdd86-8752-4b3f-b2a7-83413009109c"
AZ_LOCATION="eastus2"
AZ_RESOURCE_GROUP="rg-memquest"
AZ_CONTAINERAPPS_ENV="memquest-env"
ACA_SERVER_APP="memquest-server-turbo"
SERVER_IMAGE="${TURBO_SERVER_IMAGE:-memquestacr.azurecr.io/memquest-server:v14-turbo}"

# Set subscription
say "Setting subscription to $AZ_SUBSCRIPTION_ID"
az account set --subscription "$AZ_SUBSCRIPTION_ID"

# Create resource group if needed
if ! az group show -n "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  say "Creating resource group: $AZ_RESOURCE_GROUP"
  az group create -n "$AZ_RESOURCE_GROUP" -l "$AZ_LOCATION"
fi

# Create container apps environment if needed
if ! az containerapp env show -g "$AZ_RESOURCE_GROUP" -n "$AZ_CONTAINERAPPS_ENV" >/dev/null 2>&1; then
  say "Creating Container Apps environment: $AZ_CONTAINERAPPS_ENV"
  az containerapp env create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$AZ_CONTAINERAPPS_ENV" \
    -l "$AZ_LOCATION" \
    --logs-destination none
fi

# Deploy or update turbo server app
say "Deploying turbo server app: $ACA_SERVER_APP"

if ! az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_SERVER_APP" >/dev/null 2>&1; then
  say "Creating new container app"
  az containerapp create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$SERVER_IMAGE" \
    --registry-server memquestacr.azurecr.io \
    --ingress external \
    --target-port 8000 \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 2.0 \
    --memory 4Gi
else
  say "Updating existing container app"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --image "$SERVER_IMAGE" \
    --cpu 2.0 \
    --memory 4Gi \
    --min-replicas 1 \
    --max-replicas 1

  # Ensure system-assigned managed identity is enabled
  az containerapp identity assign \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --system-assigned >/dev/null 2>&1 || true
fi

# Build environment variables for the TURBO edition
# Key difference: NO Qdrant vars, uses Azure Search directly
say "Setting environment variables (Turbo — Azure AI Search)"

ENV_VARS=(
  "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}"
  "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}"
  "AZURE_OPENAI_DEPLOYMENT=${AZURE_OPENAI_DEPLOYMENT}"
  "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}"
  "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
  "HINDSIGHT_URL=${HINDSIGHT_URL}"
  "LLM_PROVIDER=${LLM_PROVIDER}"
  "LLM_MODEL=${LLM_MODEL}"
  "LLM_ENDPOINT=${LLM_ENDPOINT}"
  "LLM_API_KEY=${LLM_API_KEY}"
  "LLM_API_VERSION=${LLM_API_VERSION}"
  "EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER}"
  "EMBEDDING_MODEL=${EMBEDDING_MODEL}"
  "EMBEDDING_ENDPOINT=${EMBEDDING_ENDPOINT}"
  "EMBEDDING_API_KEY=${EMBEDDING_API_KEY}"
  "EMBEDDING_API_VERSION=${EMBEDDING_API_VERSION}"
  "EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS}"
  "VECTOR_DB_PROVIDER=azureaisearch"
  "AZURE_SEARCH_ENDPOINT=${AZURE_SEARCH_ENDPOINT}"
  "AZURE_SEARCH_API_KEY=${AZURE_SEARCH_API_KEY}"
  "LOG_LEVEL=${LOG_LEVEL}"
)

# Optional vars (only sent when non-empty)
if [[ -n "${GROK_DEPLOYMENT_NAME:-}" ]]; then
  ENV_VARS+=("GROK_DEPLOYMENT_NAME=${GROK_DEPLOYMENT_NAME}")
fi
if [[ -n "${GPT4_DEPLOYMENT_NAME:-}" ]]; then
  ENV_VARS+=("GPT4_DEPLOYMENT_NAME=${GPT4_DEPLOYMENT_NAME}")
fi
if [[ -n "${DEEPSEEK_DEPLOYMENT_NAME:-}" ]]; then
  ENV_VARS+=("DEEPSEEK_DEPLOYMENT_NAME=${DEEPSEEK_DEPLOYMENT_NAME}")
fi

if [[ -n "${DB_PATH:-}" ]]; then
  ENV_VARS+=("DB_PATH=${DB_PATH}")
fi
if [[ -n "${DB_NAME:-}" ]]; then
  ENV_VARS+=("DB_NAME=${DB_NAME}")
fi
if [[ -n "${COGNEE_DATASET_NAME:-}" ]]; then
  ENV_VARS+=("COGNEE_DATASET_NAME=${COGNEE_DATASET_NAME}")
fi

# Foundry agent env vars
if [[ -n "${AZURE_FOUNDRY_ENDPOINT:-}" ]]; then
  ENV_VARS+=("AZURE_FOUNDRY_ENDPOINT=${AZURE_FOUNDRY_ENDPOINT}")
fi
if [[ -n "${AZURE_FOUNDRY_AGENT_NAME:-}" ]]; then
  ENV_VARS+=("AZURE_FOUNDRY_AGENT_NAME=${AZURE_FOUNDRY_AGENT_NAME}")
fi

az containerapp update \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --set-env-vars \
  "${ENV_VARS[@]}"

# Assign RBAC roles for managed identity
say "Assigning RBAC roles..."

PRINCIPAL_ID=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --query identity.principalId -o tsv)

# ── Azure AI Search RBAC ──
SEARCH_RESOURCE_NAME=$(echo "$AZURE_SEARCH_ENDPOINT" | sed -n 's|https://\([^.]*\)\.search\.windows\.net.*|\1|p')
if [[ -n "$SEARCH_RESOURCE_NAME" ]]; then
  SEARCH_RESOURCE_ID=$(az search service show \
    --name "$SEARCH_RESOURCE_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --query id -o tsv 2>/dev/null || true)

  if [[ -n "$SEARCH_RESOURCE_ID" ]]; then
    az role assignment create \
      --assignee "$PRINCIPAL_ID" \
      --role "Search Index Data Contributor" \
      --scope "$SEARCH_RESOURCE_ID" \
      2>/dev/null || say "  (Search Index Data Contributor role may already be assigned)"

    az role assignment create \
      --assignee "$PRINCIPAL_ID" \
      --role "Search Service Contributor" \
      --scope "$SEARCH_RESOURCE_ID" \
      2>/dev/null || say "  (Search Service Contributor role may already be assigned)"

    say "  ✅ Azure Search RBAC roles assigned"
  else
    say "  ⚠️  Could not find search service '$SEARCH_RESOURCE_NAME' in RG '$AZ_RESOURCE_GROUP'"
    say "     You may need to assign roles manually if the resource is in a different RG"
  fi
fi

# ── Foundry RBAC (same as original) ──
if [[ -n "${AZURE_FOUNDRY_ENDPOINT:-}" ]]; then
  FOUNDRY_RESOURCE_NAME=$(echo "$AZURE_FOUNDRY_ENDPOINT" | sed -n 's|https://\([^.]*\)\.services\.ai\.azure\.com.*|\1|p')

  if [[ -n "$FOUNDRY_RESOURCE_NAME" ]]; then
    FOUNDRY_RESOURCE_ID=$(az cognitiveservices account show \
      --name "$FOUNDRY_RESOURCE_NAME" \
      --resource-group "$AZ_RESOURCE_GROUP" \
      --query id -o tsv 2>/dev/null || true)

    if [[ -n "$FOUNDRY_RESOURCE_ID" ]]; then
      az role assignment create \
        --assignee "$PRINCIPAL_ID" \
        --role "Azure AI Developer" \
        --scope "$FOUNDRY_RESOURCE_ID" \
        2>/dev/null || say "  (Azure AI Developer role may already be assigned)"

      az role assignment create \
        --assignee "$PRINCIPAL_ID" \
        --role "Cognitive Services User" \
        --scope "$FOUNDRY_RESOURCE_ID" \
        2>/dev/null || say "  (Cognitive Services User role may already be assigned)"

      say "  ✅ Foundry RBAC roles assigned"
    fi
  fi
fi

# Get the URL
SERVER_URL=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say ""
say "✅ Turbo server deployment complete!"
say "Server URL: https://${SERVER_URL}"
