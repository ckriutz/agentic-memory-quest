#!/usr/bin/env bash
set -euo pipefail

# Simple deployment script for memquest-server to Azure Container Apps
# Loads environment variables from server/.env file

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
set -a
source "$ENV_FILE"
set +a

# Azure config
AZ_SUBSCRIPTION_ID="aae0c7f5-d42b-4150-bb15-9ea7bd5751ec"
AZ_LOCATION="westus3"
AZ_RESOURCE_GROUP="rg-memquest"
AZ_CONTAINERAPPS_ENV="memquest-env"
ACA_SERVER_APP="memquest-server"
SERVER_IMAGE="ghcr.io/ckriutz/memquest-server:10"

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

# Deploy or update server app
say "Deploying server app: $ACA_SERVER_APP"

if ! az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_SERVER_APP" >/dev/null 2>&1; then
  say "Creating new container app"
  az containerapp create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$SERVER_IMAGE" \
    --ingress external \
    --target-port 8000 \
    --min-replicas 0 \
    --max-replicas 1 \
    --cpu 2.0 \
    --memory 4Gi \
    --mi-system-assigned
else
  say "Updating existing container app"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --image "$SERVER_IMAGE" \
    --cpu 2.0 \
    --memory 4Gi
fi

# Set all environment variables from .env file
say "Setting environment variables"

# Build env var list as an array so we can conditionally include optional values
# without overriding server-side defaults with empty strings.
ENV_VARS=(
  "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}"
  "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}"
  "AZURE_OPENAI_DEPLOYMENT=${AZURE_OPENAI_DEPLOYMENT}"
  "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}"
  "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
  "QDRANT_HOST=${QDRANT_HOST}"
  "QDRANT_PORT=${QDRANT_PORT}"
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
  "VECTOR_DB_PROVIDER=${VECTOR_DB_PROVIDER}"
  "VECTOR_DB_URL=${VECTOR_DB_URL}"
  "VECTOR_DATASET_DATABASE_HANDLER=${VECTOR_DATASET_DATABASE_HANDLER}"
  "LOG_LEVEL=${LOG_LEVEL}"
)

# New/optional vars (only sent when non-empty)
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

# Foundry agent env vars (only sent when non-empty)
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

# Assign RBAC roles for Foundry (managed identity → AI Foundry resource)
if [[ -n "${AZURE_FOUNDRY_ENDPOINT:-}" ]]; then
  say "Assigning RBAC roles for Foundry agent access"

  # Get the managed identity principal ID
  PRINCIPAL_ID=$(az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --query identity.principalId -o tsv)

  # Extract the Foundry resource scope from the endpoint
  # Endpoint format: https://<resource>.services.ai.azure.com/api/projects/<project>
  # We need the Cognitive Services resource scope
  FOUNDRY_RESOURCE_NAME=$(echo "$AZURE_FOUNDRY_ENDPOINT" | sed -n 's|https://\([^.]*\)\.services\.ai\.azure\.com.*|\1|p')

  if [[ -n "$FOUNDRY_RESOURCE_NAME" ]]; then
    FOUNDRY_RESOURCE_ID=$(az cognitiveservices account show \
      --name "$FOUNDRY_RESOURCE_NAME" \
      --resource-group "$AZ_RESOURCE_GROUP" \
      --query id -o tsv 2>/dev/null || true)

    if [[ -n "$FOUNDRY_RESOURCE_ID" ]]; then
      # Azure AI Developer — to call the agent
      az role assignment create \
        --assignee "$PRINCIPAL_ID" \
        --role "Azure AI Developer" \
        --scope "$FOUNDRY_RESOURCE_ID" \
        2>/dev/null || say "  (Azure AI Developer role may already be assigned)"

      # Cognitive Services User — for model inference
      az role assignment create \
        --assignee "$PRINCIPAL_ID" \
        --role "Cognitive Services User" \
        --scope "$FOUNDRY_RESOURCE_ID" \
        2>/dev/null || say "  (Cognitive Services User role may already be assigned)"

      say "  ✅ RBAC roles assigned for Foundry"
    else
      say "  ⚠️  Could not find Foundry resource '$FOUNDRY_RESOURCE_NAME' in resource group '$AZ_RESOURCE_GROUP'"
      say "     You may need to assign roles manually if the resource is in a different RG"
    fi
  else
    say "  ⚠️  Could not parse resource name from AZURE_FOUNDRY_ENDPOINT"
    say "     Assign 'Azure AI Developer' and 'Cognitive Services User' roles manually"
  fi
fi

# Get the URL
SERVER_URL=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say ""
say "✅ Deployment complete!"
say "Server URL: https://${SERVER_URL}"