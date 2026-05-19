terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudfunctions.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "workflows.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# Firestore
resource "google_firestore_database" "main" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

# Pub/Sub topics
resource "google_pubsub_topic" "vacation_request_submitted" {
  name       = "vacation-request-submitted"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "package_proposal_generated" {
  name       = "package-proposal-generated"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "package_selected" {
  name       = "package-selected"
  depends_on = [google_project_service.apis]
}

# Subscription: Preference Validator listens to VacationRequestSubmitted
resource "google_pubsub_subscription" "preference_validator_sub" {
  name  = "preference-validator-sub"
  topic = google_pubsub_topic.vacation_request_submitted.name

  push_config {
    push_endpoint = "${var.preference_validator_url}/validate"
    oidc_token {
      service_account_email = google_service_account.runtime_sa.email
    }
  }

  ack_deadline_seconds = 60
  depends_on           = [google_project_service.apis]
}

# Subscription: Coordination Agent listens to VacationRequestSubmitted
resource "google_pubsub_subscription" "coordination_agent_sub" {
  name  = "coordination-agent-sub"
  topic = google_pubsub_topic.vacation_request_submitted.name

  push_config {
    push_endpoint = "${var.coordination_agent_url}/start"
    oidc_token {
      service_account_email = google_service_account.runtime_sa.email
    }
  }

  ack_deadline_seconds = 300
  depends_on           = [google_project_service.apis]
}

# Runtime Service Account 
resource "google_service_account" "runtime_sa" {
  account_id   = "vacation-system-sa"
  display_name = "Vacation System Runtime SA"
  depends_on   = [google_project_service.apis]
}

locals {
  runtime_roles = [
    "roles/run.invoker",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/datastore.user",
    "roles/secretmanager.secretAccessor",
    "roles/workflows.invoker",
    "roles/aiplatform.user",
  ]
}

resource "google_project_iam_member" "runtime_sa_roles" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime_sa.email}"
}

# Artifact Registry (Docker images for Cloud Run) 
resource "google_artifact_registry_repository" "main" {
  repository_id = "vacation-system"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.apis]
}

# Secret Manager: JWT secret
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id  = "jwt-secret"
  depends_on = [google_project_service.apis]

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "jwt_secret_value" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = var.jwt_secret
}

# Google Workflow 
resource "google_workflows_workflow" "package_assembly" {
  name            = "vacation-package-assembly"
  region          = var.region
  service_account = google_service_account.runtime_sa.email
  source_contents = file("${path.module}/workflow.yaml")
  depends_on      = [google_project_service.apis]
}
