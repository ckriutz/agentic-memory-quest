#!/bin/bash

# Hindsight Deployment - Azure Container Instance with Embedded Database
# Single container with both API (8888) and Control Plane (9999)
# Uses embedded pg0 database for simplicity

set -e

# Configuration
RESOURCE_GROUP="rg-memquest"
LOCATION="westus3"
CONTAINER_NAME="hindsight"
HINDSIGHT_IMAGE="ghcr.io/vectorize-io/hindsight:latest"

# Use a stable DNS label by default (override via env var if you want).
DNS_LABEL="${DNS_LABEL:-hindsight-demo}"

# Azure OpenAI Configuration
# For Azure OpenAI with OpenAI SDK, use the /openai/v1/ endpoint format
AZURE_OPENAI_API_KEY=""
AZURE_OPENAI_ENDPOINT=""
AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
# Azure OpenAI base URL format for OpenAI SDK compatibility (v1 API for both LLM and embeddings)
AZURE_OPENAI_BASE_URL="${AZURE_OPENAI_ENDPOINT}/openai/v1/"

# Precompute expected ACI FQDN (needed for CP dataplane URL)
ACI_DOMAIN="${LOCATION}.azurecontainer.io"
FQDN="${DNS_LABEL}.${ACI_DOMAIN}"

echo "Target FQDN will be: ${FQDN}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Hindsight Deployment - Azure Container Instance        ║${NC}"
echo -e "${GREEN}║     Single Container with Embedded Database                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo -e ""
echo -e "${YELLOW}This deployment includes:${NC}"
echo -e "  • Hindsight API (port 8888)"
echo -e "  • Control Plane UI (port 9999)"
echo -e "  • Embedded pg0 database (no external PostgreSQL needed)"
echo -e "  • Azure OpenAI for LLM"
echo -e ""
echo -e "${YELLOW}Estimated Cost: ~\$70/month${NC} (4 vCPU, 8GB RAM)"
echo -e ""

# Step 1: Create Resource Group
echo -e "${BLUE}[1/3] Creating resource group...${NC}"
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION \
  --output none

echo -e "${GREEN}✓ Resource group created${NC}"

# Step 1.5: Delete existing container group (redeploy)
if az container show --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "Existing container group found. Deleting for clean redeploy..."
  az container delete --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_NAME" --yes --output none
fi

# Step 2: Deploy Container Instance
echo -e "${BLUE}[2/3] Deploying Hindsight container...${NC}"
echo -e "${YELLOW}(This may take 2-3 minutes)${NC}"

az container create \
  --resource-group $RESOURCE_GROUP \
  --name $CONTAINER_NAME \
  --image $HINDSIGHT_IMAGE \
  --os-type Linux \
  --cpu 4 \
  --memory 8 \
  --ports 8888 9999 \
  --dns-name-label "$DNS_LABEL" \
  --environment-variables \
    HINDSIGHT_API_LLM_PROVIDER="openai" \
    HINDSIGHT_API_LLM_BASE_URL="$AZURE_OPENAI_BASE_URL" \
    HINDSIGHT_API_LLM_MODEL="$AZURE_OPENAI_DEPLOYMENT_NAME" \
    HINDSIGHT_API_EMBEDDINGS_PROVIDER="openai" \
    HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL="$AZURE_OPENAI_BASE_URL" \
    HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL="$AZURE_OPENAI_EMBEDDING_DEPLOYMENT" \
    HINDSIGHT_API_HOST="0.0.0.0" \
    HINDSIGHT_API_PORT="8888" \
    HINDSIGHT_API_WORKERS="4" \
    HINDSIGHT_API_LLM_MAX_CONCURRENT="50" \
    HINDSIGHT_CP_DATAPLANE_API_URL="http://${FQDN}:8888" \
  --secure-environment-variables \
    HINDSIGHT_API_LLM_API_KEY="$AZURE_OPENAI_API_KEY" \
    HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
  --output none

echo -e "${GREEN}✓ Container deployed${NC}"

# (Optional) You can still query the actual assigned FQDN after creation:
FQDN_ACTUAL="$(az container show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_NAME" \
  --query ipAddress.fqdn \
  --output tsv)"
echo "ACI reported FQDN: ${FQDN_ACTUAL}"

# Step 3: Wait for container to be ready
echo -e "${BLUE}[3/3] Waiting for Hindsight to start...${NC}"

MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://$FQDN:8888/health" 2>/dev/null || echo "000")
  if [ "$HTTP_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Hindsight is ready!${NC}"
    break
  fi
  echo -e "  Waiting... (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
  sleep 10
  RETRY_COUNT=$((RETRY_COUNT+1))
done

# Display results
echo -e ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Deployment Complete!                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo -e ""
echo -e "${YELLOW}Access Your Hindsight Instance:${NC}"
echo -e ""
echo -e "  ${GREEN}📡 API Server${NC}"
echo -e "     URL:      http://$FQDN:8888"
echo -e "     Docs:     http://$FQDN:8888/docs"
echo -e "     Health:   http://$FQDN:8888/health"
echo -e ""
echo -e "  ${GREEN}🎨 Control Plane (Web UI)${NC}"
echo -e "     URL:      http://$FQDN:9999"
echo -e ""
echo -e "${YELLOW}Quick Test:${NC}"
echo -e "  curl http://$FQDN:8888/health"
echo -e ""
echo -e "${YELLOW}View Logs:${NC}"
echo -e "  az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --follow"
echo -e ""
echo -e "${YELLOW}Cleanup:${NC}"
echo -e "  az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo -e ""
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
