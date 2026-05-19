project_id = "ada2026-assignment2"
region     = "us-central1"
jwt_secret = "f918196c4aea3a72d5b5df5ef248fd0fe5e7833b74013727c0ee4d59eac5691a"

# Run: gcloud run services describe <name> --region us-central1 --format 'value(status.url)'
coordination_agent_url   = "https://coordination-agent-placeholder.run.app"
preference_validator_url = "https://preference-validator-placeholder.run.app"
vacation_request_url     = "https://vacation-request-placeholder.run.app"
business_rules_url       = "https://business-rules-placeholder.run.app"
