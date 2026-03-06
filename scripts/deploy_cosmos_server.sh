#!/usr/bin/env bash
set -euo pipefail

# Deployment script for memquest-server-cosmos (Cosmos DB edition)
# Deploys alongside the original (Qdrant) and turbo (Azure AI Search) servers
# for 3-way A/B/C comparison.

say() { printf "%s\n" "$*"; }
die() { printf "ERROR: %s\n" "$*" >&2; exit 1; }

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
ACA_SERVER_APP="memquest-server-cosmos"
SERVER_IMAGE="${COSMOS_SERVER_IMAGE:-memquestacr.azurecr.io/memquest-server:v15-cosmos}"

# Cosmos DB config
COSMOS_ENDPOINT="https://memquest-cosmos.documents.azure.com:443/"
COSMOS_KEY="${COSMOS_KEY:-}"  # Will be set via env vars

# Set subscription
say "Setting subscription to $AZ_SUBSCRIPTION_ID"
az account set --subscription "$AZ_SUBSCRIPTION_ID"

# Get ACR credentials
ACR_PASSWORD=$(az acr credential show --name memquestacr --query "passwords[0].value" -o tsv 2>/dev/null || true)

# Deploy or update cosmos server app
say "Deploying cosmos server app: $ACA_SERVER_APP"

if ! az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_SERVER_APP" >/dev/null 2>&1; then
  say "Creating new container app"
  az containerapp create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$SERVER_IMAGE" \
    --registry-server memquestacr.azurecr.io \
    --registry-username memquestacr \
    --registry-password "$ACR_PASSWORD" \
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
fi

# Assign system-assigned managed identity
say "Ensuring managed identity..."
az containerapp identity assign \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --system-assigned >/dev/null 2>&1 || true

# Set environment variables for the COSMOS edition
say "Setting environment variables (Cosmos — Azure Cosmos DB)"

# Get Cosmos key if not set
if [[ -z "$COSMOS_KEY" ]]; then
  COSMOS_KEY=$(az cosmosdb keys list --name memquest-cosmos -g "$AZ_RESOURCE_GROUP" --query primaryMasterKey -o tsv 2>/dev/null || true)
fi

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
  "VECTOR_DB_PROVIDER=cosmos"
  "COSMOS_ENDPOINT=${COSMOS_ENDPOINT}"
  "COSMOS_KEY=${COSMOS_KEY}"
  "LOG_LEVEL=${LOG_LEVEL}"
)

# Optional vars
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

# Get the URL
SERVER_URL=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say ""
say "✅ Cosmos server deployment complete!"
say "Server URL: https://${SERVER_URL}"
