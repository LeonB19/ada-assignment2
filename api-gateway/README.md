# Vacation Package System — Infrastructure & Setup

Project: `ada2026-assignment2` | Region: `us-central1`

---

## Quick start

### 1. Prerequisites
```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project ada2026-assignment2

# Install Terraform: https://developer.hashicorp.com/terraform/install
terraform -version  # should be >= 1.5
```

### 2. Enable APIs + provision infrastructure
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in your values
terraform init
terraform apply
```

This creates:
- Firestore database
- Pub/Sub topics + subscriptions
- Runtime service account with correct roles
- Artifact Registry Docker repo
- JWT secret in Secret Manager
- Google Workflow definition
- API Gateway Cloud Run service (after you build + push the image)

### 3. Build and deploy the API Gateway
```bash
cd api-gateway

# Set your project and region
export PROJECT_ID=ada2026-assignment2
export REGION=us-central1
export REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/vacation-system"

# Build and push
gcloud builds submit --tag "${REPO}/api-gateway:latest"

# Deploy to Cloud Run
gcloud run deploy api-gateway \
  --image "${REPO}/api-gateway:latest" \
  --region ${REGION} \
  --service-account vacation-system-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars PROJECT_ID=${PROJECT_ID} \
  --allow-unauthenticated
```

### 4. Get the API Gateway URL and share it with the team
```bash
gcloud run services describe api-gateway \
  --region us-central1 \
  --format 'value(status.url)'
```

---

## For teammates deploying their services

### Service account to use on every Cloud Run service / Cloud Function
```
vacation-system-sa@ada2026-assignment2.iam.gserviceaccount.com
```
Always pass `--service-account` when deploying.

### Artifact Registry (Docker images)
```
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/<your-service>:latest
```

### After deploying your service, tell Noud your URL
He needs to update `terraform.tfvars` with your Cloud Run URL so the Pub/Sub subscriptions and API Gateway routing point to the right place.

---

## Pub/Sub topics

| Topic | Published by | Consumed by |
|---|---|---|
| `vacation-request-submitted` | Vacation Request Service | Preference Validator + Coordination Agent |
| `package-proposal-generated` | Package Composer Agent | Coordination Agent |
| `package-selected` | Package Selection Function | (logged to event store) |

---

## Running the demo locally (before deploying)

```bash
# Terminal 1 — API Gateway
cd api-gateway
pip install -r requirements.txt
COORDINATION_AGENT_URL=http://localhost:8001 \
BUSINESS_RULES_URL=http://localhost:8002 \
VACATION_REQUEST_URL=http://localhost:8003 \
uvicorn main:app --port 8080 --reload

# Terminal 2 — Run demo
cd demo
pip install httpx
python run_demo.py --gateway http://localhost:8080
```

## Running the demo against deployed services
```bash
cd demo
python run_demo.py --gateway https://api-gateway-<hash>-ew.a.run.app
```
