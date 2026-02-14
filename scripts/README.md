# Deployment scripts

## Azure Container Apps (ACA)

Use `deploy_containerapps.sh` to deploy the two images built by the GitHub Actions workflows:

- `ghcr.io/<owner>/memquest-server:<tag>`
- `ghcr.io/<owner>/memquest-web:<tag>`

The web container serves the SPA and proxies `/api/*` to the server container app (so the browser stays same-origin).

### Prerequisites

- Azure CLI installed and authenticated (`az login`)
- Access to the GHCR images (a PAT with `read:packages`)

### Required environment variables

At minimum for the server to start:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`

For GHCR pulls:

- If images are **public**: set `GHCR_OWNER` (or override `SERVER_IMAGE` / `WEB_IMAGE`).
- If images are **private**: set `GHCR_OWNER`, `GHCR_USERNAME`, and `GHCR_TOKEN` (PAT with `read:packages`).

### Optional environment variables

- `IMAGE_TAG` (defaults to `latest`) – deploy `:<run_number>` tags produced by CI
- `AZ_RESOURCE_GROUP`, `AZ_LOCATION`, `AZ_CONTAINERAPPS_ENV`
- The script will automatically load a repo-root `.env` if present (gitignored).
- `SERVER_ENV_FILE` (defaults to `server/memoryquest_server/.env` under the repo root) – if present, the script will `source` it

### Run

From repo root:

- `IMAGE_TAG=latest ./scripts/deploy_containerapps.sh`

After deployment, the script prints the web and server URLs.

---

## Turbo Edition (Azure AI Search)

The **Turbo** deployment replaces Qdrant with Azure AI Search for both Mem0 and
Cognee agents. It runs side-by-side with the original deployment so you can A/B
compare.

### Deploy

```bash
# 1. Build and push the turbo server image
docker build -t memquestacr.azurecr.io/memquest-server:v14-turbo server/memoryquest_server/
az acr login -n memquestacr
docker push memquestacr.azurecr.io/memquest-server:v14-turbo

# 2. Build and push the turbo web image
docker build -t memquestacr.azurecr.io/memquest-web:v14-turbo web/
docker push memquestacr.azurecr.io/memquest-web:v14-turbo

# 3. Deploy
./scripts/deploy_turbo_server.sh
./scripts/deploy_turbo_web.sh

# 4. Run A/B comparison
./tests/compare_ab.sh
```

### Compare

Run `./tests/compare_ab.sh` to test both original and turbo endpoints
side-by-side. Results are written to `tests/results/ab_comparison_<timestamp>.md`.

---

## Required RBAC Roles

The managed identity of each Container App needs the following roles.
The deploy scripts assign them automatically, but if you're setting up
manually (or granting access to another user/SP), use the commands below.

### Azure AI Search

| Role | Purpose |
|------|---------|
| **Search Index Data Contributor** | Read/write documents in search indexes |
| **Search Service Contributor** | Create/manage index schemas |

```bash
# Replace <principal-id> and <search-resource-id> with your values
az role assignment create \
  --assignee <principal-id> \
  --role "Search Index Data Contributor" \
  --scope <search-resource-id>

az role assignment create \
  --assignee <principal-id> \
  --role "Search Service Contributor" \
  --scope <search-resource-id>
```

### Azure AI Foundry

| Role | Purpose |
|------|---------|
| **Azure AI Developer** | Call Foundry agents |
| **Cognitive Services User** | Model inference |

```bash
az role assignment create \
  --assignee <principal-id> \
  --role "Azure AI Developer" \
  --scope <foundry-resource-id>

az role assignment create \
  --assignee <principal-id> \
  --role "Cognitive Services User" \
  --scope <foundry-resource-id>
```

### Azure Container Registry

| Role | Purpose |
|------|---------|
| **AcrPull** | Pull container images |

```bash
az role assignment create \
  --assignee <principal-id> \
  --role "AcrPull" \
  --scope <acr-resource-id>
```

### Lookup Helper

```bash
# Get principal ID of a Container App's managed identity
az containerapp show -g rg-memquest -n <app-name> --query identity.principalId -o tsv

# Get Azure Search resource ID
az search service show --name memquest-search -g rg-memquest --query id -o tsv

# Get Foundry resource ID
az cognitiveservices account show --name <foundry-name> -g rg-memquest --query id -o tsv

# Get ACR resource ID
az acr show --name memquestacr --query id -o tsv
```
