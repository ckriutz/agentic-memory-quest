#!/usr/bin/env bash
set -euo pipefail

# Deployment script for memquest-web-cosmos
# Deploys alongside the original and turbo web UIs, pointing at the cosmos server.

say() { printf "%s\n" "$*"; }
die() { printf "ERROR: %s\n" "$*" >&2; exit 1; }

# Azure config
AZ_SUBSCRIPTION_ID="be2cdd86-8752-4b3f-b2a7-83413009109c"
AZ_LOCATION="eastus2"
AZ_RESOURCE_GROUP="rg-memquest"
AZ_CONTAINERAPPS_ENV="memquest-env"
ACA_WEB_APP="memquest-web-cosmos"
WEB_IMAGE="${COSMOS_WEB_IMAGE:-memquestacr.azurecr.io/memquest-web:v15-cosmos}"

# Get Cosmos server URL for API proxy
say "Getting cosmos server URL..."
SERVER_FQDN=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n memquest-server-cosmos \
  --query properties.configuration.ingress.fqdn -o tsv)

if [[ -z "$SERVER_FQDN" ]]; then
  die "Could not get cosmos server FQDN. Make sure memquest-server-cosmos is deployed first."
fi

API_UPSTREAM="https://${SERVER_FQDN}/"
say "API_UPSTREAM will be set to: $API_UPSTREAM"

# Set subscription
say "Setting subscription to $AZ_SUBSCRIPTION_ID"
az account set --subscription "$AZ_SUBSCRIPTION_ID"

# Get ACR credentials
ACR_PASSWORD=$(az acr credential show --name memquestacr --query "passwords[0].value" -o tsv 2>/dev/null || true)

# Deploy or update cosmos web app
say "Deploying cosmos web app: $ACA_WEB_APP"

if ! az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_WEB_APP" >/dev/null 2>&1; then
  say "Creating new container app"
  az containerapp create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_WEB_APP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$WEB_IMAGE" \
    --registry-server memquestacr.azurecr.io \
    --registry-username memquestacr \
    --registry-password "$ACR_PASSWORD" \
    --ingress external \
    --target-port 80 \
    --min-replicas 0 \
    --max-replicas 1 \
    --cpu 1.0 \
    --memory 2Gi \
    --env-vars "API_UPSTREAM=${API_UPSTREAM}"
else
  say "Updating existing container app"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_WEB_APP" \
    --image "$WEB_IMAGE" \
    --cpu 1.0 \
    --memory 2Gi
  say "Setting environment variables"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_WEB_APP" \
    --set-env-vars "API_UPSTREAM=${API_UPSTREAM}"
fi

# Get the URL
WEB_URL=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n "$ACA_WEB_APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say ""
say "✅ Cosmos web deployment complete!"
say "Web URL: https://${WEB_URL}"
