"""
First the vacation requests service (REST API (running 24/7 on Cloud Run))
The Front-Desk Receptionist (Vacation Request Service): Their only job is to be fast. 
When a customer walks in, the receptionist takes the paperwork, assigns it a folder ID, 
files it in the drawer, and rings the office bell (Pub/Sub). 
They don't look closely at the paperwork; they just want to clear the line so the customer isn't waiting.

Then preference-validator (FaaS (serverless functions))
    It sits quietly in the cloud until it reacts to Step 5 from here - the vacation requests service

why 2 parts:
To keep the system fast (Loose Coupling): If your website's front door had to wait for a database to save 
and run complex validation rules before telling the customer "We got your request," the website would feel slow 
and laggy. Splitting them up means the front desk stays lightning-fast.
"""

import os
import uuid
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from google.cloud import firestore, pubsub_v1

# Setup config matching Paritosh's project configuration
GOOGLE_CLOUD_PROJECT = "ada2026-assignment2"
TOPIC_ID = "VacationRequestSubmitted"

app = FastAPI(title="Vacation Request Service", version="1.0.0")

# Reuse the singleton keyholder pattern from Paritosh's file
_db = None
_publisher = None

def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _db

def get_publisher():
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher

# Define the input model checking incoming data patterns
class VacationRequestInput(BaseModel):
    client_preferences: str
    destination: Optional[str] = None  
    vacation_type: Optional[str] = None  
    travel_dates: str
    travel_mode: Optional[str] = "any"
    vacation_purpose: Optional[str] = None
    weather_preference: Optional[str] = None
    budget: float

# Helper function to send the office "bell ring" via Pub/Sub
def publish_submitted_event(request_id: str):
    publisher = get_publisher()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT, TOPIC_ID)
    
    event_payload = {"request_id": request_id}
    data = json.dumps(event_payload).encode("utf-8")
    
    try:
        future = publisher.publish(topic_path, data)
        future.result()  # Block until successfully published
    except Exception as e:
        print(f"Failed to publish Pub/Sub event for {request_id}: {str(e)}")

# --- THE 3 REQUIRED OPERATIONS ---


# New Client Arrives at API Endpoint
"""
Step 1: New Client Arrives maps onto POST /requests endpoint. 
This is where the code physically accepts the incoming trip details (like budget and dates) over the internet.
"""
# Creating the Folder (The Request ID)
"""
Step 2: Creating the Folder maps onto the lines of code where we generate a unique string using Python's uuid library. 
This instantly gives the new customer a unique request_id.
"""
# Organizing the Papers (The Firestore Schema)
"""
Step 3: Organizing the Papers maps onto the Python data layout. This is where the code packages the raw customer
 text into the neat vacation_requests data schema (setting fields like budget, travel_dates, and setting validation_status to "pending")."""
# Putting it in the Drawer/Database
"""
Step 4: Putting it in the Drawer maps onto our Firestore client code. The code executes .set() to 
physically save that standardized dictionary layout as a permanent cloud document.
"""
# Ringing the Office Bell (Pub/Sub)
"""
Step 5: Ringing the Office Bell maps onto the Pub/Sub publisher code. 
The code broadcasts a message containing the request_id to the VacationRequestSubmitted topic. 
Once this bell rings, Folder 1's job is done, and it returns a "Success" message to the user.
"""
# Step 1: The Client Arrives at API Endpoint
@app.post("/requests", status_code=201)
def submit_request(request_input: VacationRequestInput, background_tasks: BackgroundTasks):
    """Operation 1: Receives text, creates unique Firestore ID, saves, and alerts Pub/Sub."""
    db = get_db()
    #Step 2: Creating the Folder (The Request ID)
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    
    # Step 3: Organizing the Papers (The Firestore Schema)
    request_document = {
        "request_id": request_id,
        "client_preferences": request_input.client_preferences,
        "destination": request_input.destination,  
        "vacation_type": request_input.vacation_type,  
        "travel_dates": request_input.travel_dates,
        "travel_mode": request_input.travel_mode,
        "vacation_purpose": request_input.vacation_purpose,
        "weather_preference": request_input.weather_preference,
        "budget": request_input.budget,
        "validation_status": "pending",
        "enriched_destination": None  
    }
    
    # Step 4: Putting it in the Drawer (The Database)
    db.collection("vacation_requests").document(request_id).set(request_document)
    
    # Step 5: Ringing the Office Bell (Pub/Sub)
    background_tasks.add_task(publish_submitted_event, request_id)
    
    return {"status": "submitted", "request_id": request_id}


"""
these two GET functions are how people (like teammates' AI agents or the travel agency managers) 
can look at folders that are already inside the drawer
"""

@app.get("/requests/{request_id}")
def get_request(request_id: str):
    """Operation 2: Reaches into drawer and pulls one specific request folder out."""
    db = get_db()
    doc = db.collection("vacation_requests").document(request_id).get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Vacation request folder not found")
        
    return doc.to_dict()


@app.get("/requests")
def list_requests():
    """Operation 3: Scans and lists all folders present inside the drawer."""
    db = get_db()
    docs = db.collection("vacation_requests").stream()
    return [doc.to_dict() for doc in docs]


@app.get("/events/{request_id}")
def get_events(request_id: str):
    """Returns the last 20 coordination_event_log entries for a request, ordered by timestamp."""
    db = get_db()
    docs = (
        db.collection("coordination_event_log")
        .where("request_id", "==", request_id)
        .order_by("timestamp")
        .limit(20)
        .stream()
    )
    events = []
    for doc in docs:
        d = doc.to_dict()
        ts = d.get("timestamp")
        events.append({
            "event_id":   doc.id,
            "event_type": d.get("event_type"),
            "request_id": d.get("request_id"),
            "timestamp":  ts.isoformat() if ts else None,
            "source":     d.get("source"),
            "payload":    d.get("payload", {}),
        })
    return {"events": events}