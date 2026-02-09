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
SERVER_IMAGE="ghcr.io/ckriutz/memquest-server:2"

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
    --max-replicas 1
else
  say "Updating existing container app"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --image "$SERVER_IMAGE"
fi

# Set all environment variables from .env file
say "Setting environment variables"
az containerapp update \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --set-env-vars \
    "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    "AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    "AZURE_OPENAI_DEPLOYMENT=${AZURE_OPENAI_DEPLOYMENT}" \
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}" \
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}" \
    "QDRANT_HOST=${QDRANT_HOST}" \
    "QDRANT_PORT=${QDRANT_PORT}" \
    "HINDSIGHT_URL=${HINDSIGHT_URL}" \
    "LLM_PROVIDER=${LLM_PROVIDER}" \
    "LLM_MODEL=${LLM_MODEL}" \
    "LLM_ENDPOINT=${LLM_ENDPOINT}" \
    "LLM_API_KEY=${LLM_API_KEY}" \
    "LLM_API_VERSION=${LLM_API_VERSION}" \
    "EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER}" \
    "EMBEDDING_MODEL=${EMBEDDING_MODEL}" \
    "EMBEDDING_ENDPOINT=${EMBEDDING_ENDPOINT}" \
    "EMBEDDING_API_KEY=${EMBEDDING_API_KEY}" \
    "EMBEDDING_API_VERSION=${EMBEDDING_API_VERSION}" \
    "EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS}" \
    "VECTOR_DB_PROVIDER=${VECTOR_DB_PROVIDER}" \
    "VECTOR_DB_URL=${VECTOR_DB_URL}" \
    "VECTOR_DATASET_DATABASE_HANDLER=${VECTOR_DATASET_DATABASE_HANDLER}" \
    "LOG_LEVEL=${LOG_LEVEL}"

# Get the URL
SERVER_URL=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_SERVER_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say ""
say "✅ Deployment complete!"
say "Server URL: https://${SERVER_URL}"