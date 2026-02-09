#!/usr/bin/env bash
set -euo pipefail

# Simple deployment script for memquest-web to Azure Container Apps

say() { printf "%s\n" "$*"; }

die() {
  printf "ERROR: %s\n" "$*" >&2
  exit 1
}

# Azure config
AZ_SUBSCRIPTION_ID="aae0c7f5-d42b-4150-bb15-9ea7bd5751ec"
AZ_LOCATION="westus3"
AZ_RESOURCE_GROUP="rg-memquest"
AZ_CONTAINERAPPS_ENV="memquest-env"
ACA_WEB_APP="memquest-web"
WEB_IMAGE="ghcr.io/ckriutz/memquest-web:2"

# Get server URL for API proxy
say "Getting server URL..."
SERVER_FQDN=$(az containerapp show \
  -g "$AZ_RESOURCE_GROUP" \
  -n memquest-server \
  --query properties.configuration.ingress.fqdn -o tsv)

if [[ -z "$SERVER_FQDN" ]]; then
  die "Could not get server FQDN. Make sure memquest-server is deployed first."
fi

API_UPSTREAM="https://${SERVER_FQDN}/"
say "API_UPSTREAM will be set to: $API_UPSTREAM"

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

# Deploy or update web app
say "Deploying web app: $ACA_WEB_APP"

if ! az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_WEB_APP" >/dev/null 2>&1; then
  say "Creating new container app"
  az containerapp create \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_WEB_APP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$WEB_IMAGE" \
    --ingress external \
    --target-port 80 \
    --min-replicas 0 \
    --max-replicas 1 \
    --env-vars "API_UPSTREAM=${API_UPSTREAM}"
else
  say "Updating existing container app"
  az containerapp update \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_WEB_APP" \
    --image "$WEB_IMAGE"
  
  # Update environment variables
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
say "✅ Deployment complete!"
say "Web URL: https://${WEB_URL}"
say "API URL: ${API_UPSTREAM}"
