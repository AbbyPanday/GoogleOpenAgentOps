#!/usr/bin/env bash
# ==============================================================================
# GoogleOpenAgentOps - 1-Click GCP Cloud Run & Environment Deployment Script
# ==============================================================================
set -e

echo "========================================================================"
echo " Starting GoogleOpenAgentOps Automated GCP Cloud Run Deployment..."
echo "========================================================================"

# Check gcloud
if ! command -v gcloud &> /dev/null; then
    echo "[!] Error: gcloud command not found. Please install the Google Cloud SDK."
    exit 1
fi

PROJECT_ID=$(gcloud config get-value project 2> /dev/null)
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "[!] No default GCP project found in gcloud config."
    read -p "Enter your Google Cloud Project ID: " PROJECT_ID
    gcloud config set project "$PROJECT_ID"
fi

REGION="us-central1"
SERVICE_NAME="google-openagentops-dashboard"

echo "[*] Using GCP Project:  $PROJECT_ID"
echo "[*] Cloud Run Region:   $REGION"
echo "[*] Service Name:       $SERVICE_NAME"

echo "[*] Enabling required APIs..."
gcloud services enable     run.googleapis.com     cloudbuild.googleapis.com     cloudtrace.googleapis.com     monitoring.googleapis.com     logging.googleapis.com     --project "$PROJECT_ID"

echo "[*] Installing Python dependencies & Google Cloud telemetry packages..."
pip install --upgrade pip
pip install google-cloud-trace google-cloud-monitoring google-cloud-logging

echo "[*] Building and deploying GoogleOpenAgentOps Dashboard to Cloud Run..."
gcloud run deploy "$SERVICE_NAME"     --source .     --project "$PROJECT_ID"     --region "$REGION"     --port 8000     --cpu 1     --memory 512Mi     --allow-unauthenticated     --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},PORT=8000"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')

echo "========================================================================"
echo " [SUCCESS] GoogleOpenAgentOps Dashboard is LIVE on Google Cloud Run!"
echo " URL: $SERVICE_URL"
echo " Google Cloud Trace: https://console.cloud.google.com/traces/overview?project=${PROJECT_ID}"
echo "========================================================================"
