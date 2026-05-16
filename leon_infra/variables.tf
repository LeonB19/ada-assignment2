variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "jwt_secret" {
  description = "Secret key for JWT signing"
  type        = string
  sensitive   = true
}

variable "coordination_agent_url" {
  description = "Cloud Run URL of the Coordination Agent"
  type        = string
  default     = "https://coordination-agent-placeholder.run.app"
}

variable "preference_validator_url" {
  description = "Cloud Run URL of the Preference Validator"
  type        = string
  default     = "https://preference-validator-placeholder.run.app"
}

variable "vacation_request_url" {
  description = "Cloud Run URL of the Vacation Request Service"
  type        = string
  default     = "https://vacation-request-placeholder.run.app"
}

variable "business_rules_url" {
  description = "Cloud Run URL of the Business Rules Service"
  type        = string
  default     = "https://business-rules-placeholder.run.app"
}
