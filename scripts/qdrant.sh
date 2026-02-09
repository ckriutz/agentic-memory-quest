#!/bin/bash

# Azure Container App - Qdrant Deployment Script
# This script deploys Qdrant vector database to Azure Container Apps

set -e  # Exit on any error

# Configuration Variables
RESOURCE_GROUP="rg-memquest"
LOCATION="westus3"
ENVIRONMENT_NAME="memquest-env"
CONTAINER_APP_NAME="qdrant-app"
QDRANT_IMAGE="qdrant/qdrant:latest"
STORAGE_ACCOUNT_NAME="qdrantstorage$RANDOM"
FILE_SHARE_NAME="qdrant-data"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Qdrant deployment to Azure Container Apps${NC}"

# Step 1: Create Resource Group
echo -e "${YELLOW}Creating resource group...${NC}"
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# Step 2: Create Container Apps Environment
echo -e "${YELLOW}Creating Container Apps environment...${NC}"
az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Step 3: Create Storage Account for persistent data
echo -e "${YELLOW}Creating storage account for persistent storage...${NC}"
az storage account create \
  --name $STORAGE_ACCOUNT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2

# Get storage account key
STORAGE_KEY=$(az storage account keys list \
  --resource-group $RESOURCE_GROUP \
  --account-name $STORAGE_ACCOUNT_NAME \
  --query "[0].value" \
  --output tsv)

# Step 4: Create Azure File Share
echo -e "${YELLOW}Creating Azure File Share...${NC}"
az storage share create \
  --name $FILE_SHARE_NAME \
  --account-name $STORAGE_ACCOUNT_NAME \
  --account-key $STORAGE_KEY \
  --quota 10

# Step 5: Create storage mount in Container Apps environment
echo -e "${YELLOW}Adding storage mount to Container Apps environment...${NC}"
az containerapp env storage set \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --storage-name qdrant-storage \
  --azure-file-account-name $STORAGE_ACCOUNT_NAME \
  --azure-file-account-key $STORAGE_KEY \
  --azure-file-share-name $FILE_SHARE_NAME \
  --access-mode ReadWrite

# Step 6: Deploy Qdrant Container App
echo -e "${YELLOW}Deploying Qdrant container app...${NC}"
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $QDRANT_IMAGE \
  --target-port 6333 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars QDRANT__SERVICE__HTTP_PORT=6333 \
  --query properties.configuration.ingress.fqdn

# Step 7: Mount the storage to the container
echo -e "${YELLOW}Mounting storage to container...${NC}"
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars QDRANT__STORAGE__STORAGE_PATH=/qdrant/storage

# Get the FQDN
FQDN=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Qdrant deployment completed!${NC}"
echo -e "${GREEN}======================================${NC}"
echo -e "Qdrant URL: https://$FQDN"
echo -e "API Endpoint: https://$FQDN:6333"
echo -e "Web UI: https://$FQDN:6333/dashboard"
echo -e ""
echo -e "To test the deployment, run:"
echo -e "curl https://$FQDN:6333"
echo -e ""
echo -e "Resource Group: $RESOURCE_GROUP"
echo -e "Storage Account: $STORAGE_ACCOUNT_NAME"
echo -e "${GREEN}======================================${NC}"