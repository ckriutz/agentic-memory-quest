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
