output "api_gateway_url" {
  description = "Public URL of the API Gateway"
  value       = google_cloud_run_v2_service.api_gateway.uri
}

output "artifact_registry_repo" {
  description = "Docker image base path"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/vacation-system"
}

output "runtime_service_account" {
  description = "Service account email to attach to all Cloud Run services and Functions"
  value       = google_service_account.runtime_sa.email
}

output "pubsub_topics" {
  description = "Pub/Sub topic names"
  value = {
    vacation_request_submitted = google_pubsub_topic.vacation_request_submitted.name
    package_proposal_generated = google_pubsub_topic.package_proposal_generated.name
    package_selected           = google_pubsub_topic.package_selected.name
  }
}

output "workflow_name" {
  description = "Google Workflow name"
  value       = google_workflows_workflow.package_assembly.name
}
