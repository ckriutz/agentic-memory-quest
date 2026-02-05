#!/usr/bin/env bash
set -euo pipefail

# Deploy Agentic Memory Quest to Azure Container Apps.
# - Deploys TWO separate container apps:
#   - memquest-server  (FastAPI, port 8000)
#   - memquest-web     (nginx static site, port 80, proxies /api/* -> server)
# - Pulls images from GHCR:
#   - ghcr.io/<owner>/memquest-server:<tag>
#   - ghcr.io/<owner>/memquest-web:<tag>
#
# Prereqs:
#   - az cli installed and logged in: az login
#   - Container Apps extension installed (script can install it)
#   - GHCR token with read:packages scope (ONLY if images are private)
#
# Usage:
#   IMAGE_TAG=latest \
#   AZ_RESOURCE_GROUP=amq-rg \
#   AZ_LOCATION=eastus \
#   AZ_CONTAINERAPPS_ENV=amq-env \
#   GHCR_USERNAME=ckriutz \
#   GHCR_TOKEN=... \
#   AZURE_OPENAI_ENDPOINT=... \
#   AZURE_OPENAI_API_KEY=... \
#   ./scripts/deploy_containerapps.sh
#

say() { printf "%s\n" "$*"; }

die() {
  printf "ERROR: %s\n" "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_cmd az

# Resolve repo root so the script works no matter where it's launched from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# If a root .env exists, load it (local-only; should be gitignored).
if [[ -f "${REPO_ROOT}/.env" ]]; then
  say "Loading deploy env from: ${REPO_ROOT}/.env"
  # shellcheck disable=SC1090
  set -a
  source "${REPO_ROOT}/.env"
  set +a
fi

# -------------------------
# Config (override via env)
# -------------------------
AZ_SUBSCRIPTION_ID="${AZ_SUBSCRIPTION_ID:-}"
AZ_LOCATION="${AZ_LOCATION:-eastus}"
AZ_RESOURCE_GROUP="${AZ_RESOURCE_GROUP:-agentic-memory-quest-rg}"
AZ_CONTAINERAPPS_ENV="${AZ_CONTAINERAPPS_ENV:-amq-aca-env}"

ACA_SERVER_APP="${ACA_SERVER_APP:-memquest-server}"
ACA_WEB_APP="${ACA_WEB_APP:-memquest-web}"

IMAGE_TAG="${IMAGE_TAG:-latest}"

REGISTRY_SERVER="${REGISTRY_SERVER:-ghcr.io}"
GHCR_USERNAME="${GHCR_USERNAME:-${GITHUB_REPOSITORY_OWNER:-}}"
GHCR_TOKEN="${GHCR_TOKEN:-}"

GHCR_OWNER="${GHCR_OWNER:-${GHCR_USERNAME:-}}"

# Optional: source secrets for the server from a dotenv file.
SERVER_ENV_FILE="${SERVER_ENV_FILE:-${REPO_ROOT}/server/memoryquest_server/.env}"

SERVER_IMAGE="${SERVER_IMAGE:-${REGISTRY_SERVER}/${GHCR_OWNER}/memquest-server:${IMAGE_TAG}}"
WEB_IMAGE="${WEB_IMAGE:-${REGISTRY_SERVER}/${GHCR_OWNER}/memquest-web:${IMAGE_TAG}}"

# If you want to avoid exposing the server publicly, set SERVER_INGRESS=internal.
# (If you do that, you must also adjust the web proxy upstream strategy.)
SERVER_INGRESS="${SERVER_INGRESS:-external}"

# -------------------------
# Helpers
# -------------------------
infer_ghcr_owner_from_git_remote() {
  # Tries to extract the owner from the 'origin' remote.
  # Supports:
  #   - git@github.com:owner/repo.git
  #   - https://github.com/owner/repo.git
  if ! command -v git >/dev/null 2>&1; then
    return 1
  fi
  local url
  url="$(git -C "$REPO_ROOT" config --get remote.origin.url 2>/dev/null || true)"
  if [[ -z "$url" ]]; then
    return 1
  fi

  local owner=""
  if [[ "$url" =~ github\.com[:/]+([^/]+)/[^/]+(\.git)?$ ]]; then
    owner="${BASH_REMATCH[1]}"
  fi

  if [[ -n "$owner" ]]; then
    GHCR_OWNER="$owner"
    return 0
  fi
  return 1
}

ensure_image_owner_or_die() {
  if [[ -n "$GHCR_OWNER" ]]; then
    return 0
  fi
  if infer_ghcr_owner_from_git_remote; then
    say "Inferred GHCR_OWNER from git remote: $GHCR_OWNER"
    return 0
  fi
  die "GHCR_OWNER is required to form default image names (ghcr.io/<owner>/...). Set GHCR_OWNER or override SERVER_IMAGE/WEB_IMAGE."
}

registry_args=()
init_registry_args() {
  registry_args=()

  # If GHCR_TOKEN isn't set, assume images are public and skip registry auth flags.
  if [[ -z "$GHCR_TOKEN" ]]; then
    say "No GHCR_TOKEN provided; assuming images are public and skipping registry auth."
    return 0
  fi

  if [[ -z "$GHCR_USERNAME" ]]; then
    read -r -p "GHCR_USERNAME (for GHCR auth): " GHCR_USERNAME
  fi
  if [[ -z "$GHCR_TOKEN" ]]; then
    # (Shouldn't happen due to outer guard, but keep safe.)
    read -r -s -p "GHCR_TOKEN (PAT with read:packages): " GHCR_TOKEN
    printf "\n"
  fi

  if [[ -z "$GHCR_USERNAME" || -z "$GHCR_TOKEN" ]]; then
    die "To pull private GHCR images you must set GHCR_USERNAME and GHCR_TOKEN."
  fi

  registry_args=(
    --registry-server "$REGISTRY_SERVER"
    --registry-username "$GHCR_USERNAME"
    --registry-password "$GHCR_TOKEN"
  )
}

ensure_extension() {
  # Use the newer 'az containerapp' commands.
  if ! az containerapp -h >/dev/null 2>&1; then
    say "Installing Azure Container Apps extension..."
    az extension add --name containerapp >/dev/null
  fi
}

az_set_subscription_if_provided() {
  if [[ -n "$AZ_SUBSCRIPTION_ID" ]]; then
    say "Setting subscription to $AZ_SUBSCRIPTION_ID"
    az account set --subscription "$AZ_SUBSCRIPTION_ID" >/dev/null
  fi
}

ensure_rg() {
  if az group show -n "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
    say "Resource group exists: $AZ_RESOURCE_GROUP"
  else
    say "Creating resource group: $AZ_RESOURCE_GROUP ($AZ_LOCATION)"
    az group create -n "$AZ_RESOURCE_GROUP" -l "$AZ_LOCATION" >/dev/null
  fi
}

ensure_env() {
  if az containerapp env show -g "$AZ_RESOURCE_GROUP" -n "$AZ_CONTAINERAPPS_ENV" >/dev/null 2>&1; then
    say "Container Apps environment exists: $AZ_CONTAINERAPPS_ENV"
  else
    say "Creating Container Apps environment: $AZ_CONTAINERAPPS_ENV"
    # 'none' keeps things simple; you can switch to log-analytics later.
    az containerapp env create \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$AZ_CONTAINERAPPS_ENV" \
      -l "$AZ_LOCATION" \
      --logs-destination none >/dev/null
  fi
}

source_server_env_file_if_present() {
  if [[ -f "$SERVER_ENV_FILE" ]]; then
    say "Loading server env from: $SERVER_ENV_FILE"
    # shellcheck disable=SC1090
    set -a
    source "$SERVER_ENV_FILE"
    set +a
  else
    say "No server env file found at $SERVER_ENV_FILE (skipping)."
  fi
}

app_exists() {
  local name="$1"
  az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$name" >/dev/null 2>&1
}

ensure_server_app() {
  say "Deploying server app: $ACA_SERVER_APP"

  if ! app_exists "$ACA_SERVER_APP"; then
    az containerapp create \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$ACA_SERVER_APP" \
      --environment "$AZ_CONTAINERAPPS_ENV" \
      --image "$SERVER_IMAGE" \
      --ingress "$SERVER_INGRESS" \
      --target-port 8000 \
      "${registry_args[@]}" \
      --min-replicas 0 \
      --max-replicas 1 >/dev/null
  else
    az containerapp update \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$ACA_SERVER_APP" \
      --image "$SERVER_IMAGE" \
      "${registry_args[@]}" >/dev/null
  fi

  # Secrets/env-vars (only set what is available)
  local secrets=()
  local envvars=()

  add_secret() {
    local key="$1"
    local val="${!key:-}"
    if [[ -n "$val" ]]; then
      secrets+=("${key}=${val}")
      envvars+=("${key}=secretref:${key}")
    fi
  }

  add_plain_env() {
    local key="$1"
    local val="${!key:-}"
    if [[ -n "$val" ]]; then
      envvars+=("${key}=${val}")
    fi
  }

  # Required by server startup
  add_secret AZURE_OPENAI_ENDPOINT
  add_secret AZURE_OPENAI_API_KEY

  # Optional knobs
  add_plain_env AZURE_OPENAI_DEPLOYMENT
  add_plain_env AZURE_OPENAI_API_VERSION

  add_plain_env QDRANT_HOST
  add_plain_env QDRANT_PORT
  add_plain_env HINDSIGHT_URL

  if ((${#secrets[@]} > 0)); then
    az containerapp secret set -g "$AZ_RESOURCE_GROUP" -n "$ACA_SERVER_APP" --secrets "${secrets[@]}" >/dev/null
  fi

  if ((${#envvars[@]} > 0)); then
    az containerapp update -g "$AZ_RESOURCE_GROUP" -n "$ACA_SERVER_APP" --set-env-vars "${envvars[@]}" >/dev/null
  fi
}

get_server_fqdn() {
  az containerapp show \
    -g "$AZ_RESOURCE_GROUP" \
    -n "$ACA_SERVER_APP" \
    --query properties.configuration.ingress.fqdn -o tsv
}

ensure_web_app() {
  local server_fqdn="$1"
  local api_upstream
  if [[ -n "$server_fqdn" ]]; then
    api_upstream="https://${server_fqdn}/"
  else
    api_upstream=""
  fi

  say "Deploying web app: $ACA_WEB_APP"

  if ! app_exists "$ACA_WEB_APP"; then
    az containerapp create \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$ACA_WEB_APP" \
      --environment "$AZ_CONTAINERAPPS_ENV" \
      --image "$WEB_IMAGE" \
      --ingress external \
      --target-port 80 \
      "${registry_args[@]}" \
      --min-replicas 0 \
      --max-replicas 1 >/dev/null
  else
    az containerapp update \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$ACA_WEB_APP" \
      --image "$WEB_IMAGE" \
      "${registry_args[@]}" >/dev/null
  fi

  if [[ -n "$api_upstream" ]]; then
    # Nginx official image will envsubst templates on startup.
    az containerapp update \
      -g "$AZ_RESOURCE_GROUP" \
      -n "$ACA_WEB_APP" \
      --set-env-vars "API_UPSTREAM=${api_upstream}" >/dev/null
  fi
}

show_urls() {
  local server_fqdn web_fqdn
  server_fqdn="$(get_server_fqdn || true)"
  web_fqdn="$(az containerapp show -g "$AZ_RESOURCE_GROUP" -n "$ACA_WEB_APP" --query properties.configuration.ingress.fqdn -o tsv || true)"

  say ""
  say "Deployed images:"
  say "  Server: ${SERVER_IMAGE}"
  say "  Web:    ${WEB_IMAGE}"
  say ""
  if [[ -n "$server_fqdn" ]]; then
    say "Server URL: https://${server_fqdn}/"
  fi
  if [[ -n "$web_fqdn" ]]; then
    say "Web URL:    https://${web_fqdn}/"
    say "  (Web proxies /api/* -> server via API_UPSTREAM)"
  fi
}

# -------------------------
# Main
# -------------------------
ensure_extension
az_set_subscription_if_provided
ensure_image_owner_or_die
init_registry_args
source_server_env_file_if_present
ensure_rg
ensure_env
ensure_server_app
server_fqdn="$(get_server_fqdn)"
ensure_web_app "$server_fqdn"
show_urls
