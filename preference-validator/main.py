"""
Preference Validator (FaaS (serverless functions))
    It sits quietly in the cloud until it reacts to Step 5 from the vacation requests service.


The Back-Office Auditor
This person doesn't talk to customers. 
They sit in the back room with their eyes closed. 
But the second they hear that office bell ring (the Pub/Sub event), they wake up. 
They walk over to the drawer, pull out the folder the receptionist just put away, 
and meticulously check it over to make sure the budget is a real number and the dates aren't missing. 
Once they check it, they update the folder's status to "valid" and go back to sleep.
"""

"""
It reaches into the database drawer using the request_id it just heard, reads the folder's contents, 
and validates them.  If fields like travel dates or budget are filled out correctly, it alters the cover 
sheet created in Step 3 by updating validation_status from "pending" to "valid".  """

import base64
import json
from google.cloud import firestore

GOOGLE_CLOUD_PROJECT = "ada2026-assignment2"

_db = None

def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _db

def validate_preferences(event, context):
    """Operation 4: Background FaaS function triggered directly by Pub/Sub event wrapper."""
    db = get_db()
    
    # 1. Decode the notification payload from Pub/Sub envelope safely
    if 'data' not in event:
        print("Invalid Pub/Sub event format: data key missing.")
        return
        
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    data_payload = json.loads(pubsub_message)
    request_id = data_payload.get("request_id")
    
    if not request_id:
        print("No request_id found in decoded message.")
        return

    print(f"Validator active: Evaluating folder {request_id}")
    
    # 2. Retrieve document folder from Firestore
    doc_ref = db.collection("vacation_requests").document(request_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        print(f"Error: Folder {request_id} doesn't exist in Firestore database.")
        return
        
    request_data = doc.to_dict()
    
    # 3. Deterministic Validation Checks
    # Verifies presence of necessary fields: dates, preferences, and baseline budget limits
    is_valid = True
    reasons = []
    
    if not request_data.get("travel_dates"):
        is_valid = False
        reasons.append("Missing travel dates")
        
    if not request_data.get("client_preferences"):
        is_valid = False
        reasons.append("Missing raw preference textual instructions")
        
    if request_data.get("budget", 0) <= 0:
        is_valid = False
        reasons.append("Budget must be a positive number greater than 0")
        
    # 4. Write validation calculation outcome directly back into the folder
    status_value = "valid" if is_valid else "invalid"
    update_payload = {
        "validation_status": status_value
    }
    
    if not is_valid:
        update_payload["validation_error_reasons"] = reasons
        print(f"Folder {request_id} failed verification rules: {reasons}")
    else:
        print(f"Folder {request_id} successfully verified.")
        
    doc_ref.update(update_payload)