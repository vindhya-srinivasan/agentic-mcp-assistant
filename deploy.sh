#!/usr/bin/env bash
# Build the container with Cloud Build and deploy it to Cloud Run.
# Secrets come from the local .env and are passed via --set-env-vars; none live in this script.
set -euo pipefail

set -a
source .env
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in .env}"
: "${MODEL_NAME:?Set MODEL_NAME in .env}"

SERVICE="csci599-a1"
REGION="us-west1"
IMAGE="gcr.io/${GCP_PROJECT_ID}/${SERVICE}"

gcloud builds submit --project "${GCP_PROJECT_ID}" --tag "${IMAGE}"

gcloud run deploy "${SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY},OPENAI_BASE_URL=${OPENAI_BASE_URL:-},MODEL_NAME=${MODEL_NAME},TAVILY_API_KEY=${TAVILY_API_KEY:-},MCP_SERVERS_CONFIG=/app/mcp_config.json"
