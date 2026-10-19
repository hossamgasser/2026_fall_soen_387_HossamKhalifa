# Listing 3.1 -- Encore v1.1: reservations with an idempotency-key mechanism.
# The contract's new promise: a repeated POST with the same Idempotency-Key
# is recognized as a repeat and answered with the SAME outcome, applied once.
import hashlib
import json
import time
from flask import Flask, jsonify, request
import secrets, string, threading
from datetime import datetime, timezone

app = Flask(__name__)

EVENTS = {
    "ev_101": {"id": "ev_101", "title": "Jazz Ensemble: Fall Concert", "seatsLeft": 42},
    "ev_102": {"id": "ev_102", "title": "Improv Night", "seatsLeft": 0},
    "ev_103": {"id": "ev_103", "title": "Film Society: Friday Screening", "seatsLeft": 2},
}
RESERVATIONS = {}          # id -> reservation
IDEMPOTENCY = {}           # key -> {"request_hash": ..., "status": ..., "body": ...}
NEXT = {"n": 1}
ISSUED = set()          # never remove from this, even when a waitlist entry is deleted
_lock = threading.Lock()

WAITLISTS = {}
WL_IDEMPOTENCY = {}           # key -> {"request_hash": ..., "status": ..., "body": ...}

def new_waitlist_id():
    while True:
        eid = "wl_" + "".join(secrets.choice(string.digits) + secrets.choice(string.ascii_lowercase) for _ in range(4))
        with _lock:
            if eid not in ISSUED:
                ISSUED.add(eid)
                return eid
            
def body_hash():
    return hashlib.sha256(request.get_data() or b"").hexdigest()

def waitlist_response_schema(wl_entry, position):
    # ignores the wl userId for responses to only output matching the encore-openapi.yaml

    return {"id": wl_entry["id"], "eventId": wl_entry["eventId"], "position": position, "createdAt": wl_entry["createdAt"]}

@app.get("/events")
def list_events():
    events = list(EVENTS.values())
    if request.args.get("bookable") == "true":
        events = [e for e in events if e["seatsLeft"] > 0]
    return jsonify({"events": events})

@app.get("/events/<event_id>")
def get_event(event_id):
    ev = EVENTS.get(event_id)
    if ev is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(ev)

@app.post("/events/<event_id>/reservations")
def create_reservation(event_id):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422

    seen = IDEMPOTENCY.get(key)
    if seen is not None:
        if seen["request_hash"] != body_hash():
            # Same key, different request: a client bug, and a dangerous one.
            return jsonify({"error": "idempotency_key_reuse"}), 422
        resp = jsonify(seen["body"])                    # replay the stored outcome
        resp.headers["Idempotency-Replayed"] = "true"
        return resp, seen["status"]

    # First time we see this key: perform the operation, then record the outcome.
    ev = EVENTS.get(event_id)
    if ev is None:
        outcome = ({"error": "not_found"}, 404)
    elif ev["seatsLeft"] <= 0:
        outcome = ({"error": "sold_out"}, 409)
    else:
        ev["seatsLeft"] -= 1
        rid = f"res_{NEXT['n']}"; NEXT["n"] += 1
        reservation = {"id": rid, "eventId": event_id,
                       "status": "confirmed", "createdAt": "2026-09-12T19:00:00Z"}
        RESERVATIONS[rid] = reservation
        outcome = (reservation, 201)

    IDEMPOTENCY[key] = {"request_hash": body_hash(),
                        "status": outcome[1], "body": outcome[0]}

    if request.headers.get("X-Demo-Lose-Reply") == "true":
        time.sleep(3)      # the work is DONE; only the reply is delayed past
                           # the client's timeout -- Chapter 1's third state.
    return jsonify(outcome[0]), outcome[1]

@app.get("/reservations/<res_id>")
def get_reservation(res_id):
    r = RESERVATIONS.get(res_id)
    if r is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(r)


@app.get("/events/<eventId>/waitlist")
def list_waitlists(eventId):


    ev = EVENTS.get(eventId)
    if ev is None:
        return jsonify({"error": "event_not_found"}), 404

    event_entries = []
    for e in WAITLISTS.values():
        if e["eventId"] == eventId:
            event_entries.append(e)


    entries = []
    position = 1
    for e in event_entries:
        entries.append(waitlist_response_schema(e, position))         
        # position rewritten in the get in order to show the true new Position, not the one that was assigned when WL created. 
        # So, while stored ver position might be 2 and there is no pos 1, this shows as 1.
        position += 1
    
    return jsonify({"waitlists": entries}), 200

@app.get("/events/<eventId>/waitlist/<entryId>")
def get_waitlist(eventId, entryId):


    ev = EVENTS.get(eventId)
    if ev is None:
        return jsonify({"error": "event_not_found"}), 404

    event_entries = []
    for e in WAITLISTS.values():
        if e["eventId"] == eventId:
            event_entries.append(e)

    position = 1
    for e in event_entries:
        if(e["id"] ==  entryId):                   # update the needed position and stop looping
            return jsonify(waitlist_response_schema(e, position)), 200
        
        position += 1

    return jsonify({"error": "entry_not_found"}), 404


@app.delete("/events/<eventId>/waitlist/<entryId>")
def delete_waitlist(eventId, entryId):

    ev = EVENTS.get(eventId)
    if ev is None:
        return jsonify({"error": "event_not_found"}), 404

    event_entries = []
    for e in WAITLISTS.values():
        if e["eventId"] == eventId:
            event_entries.append(e)

    entry = WAITLISTS.get(entryId)
    if (entry is None or entry["eventId"] != eventId):
        return jsonify({"error": "entry_not_found"}), 404

    WAITLISTS.pop(entryId)
    return "", 204


@app.post("/events/<eventId>/waitlist")
def create_waitlist(eventId):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422

    fingerprint = f"{eventId}|{body_hash()}"
    seen = WL_IDEMPOTENCY.get(key)

    if seen is not None:
        if seen["hash"] != fingerprint:
            # Same key, different request: a client bug, and a dangerous one.
            return jsonify({"error": "idempotency_key_reuse"}), 422
        resp = jsonify(seen["body"])                    # replay the stored outcome
        resp.headers["Idempotency-Replayed"] = "true"
        return resp, seen["status"]


    body = request.get_json(silent=True)

    if (not isinstance(body, dict) or set(body) != {"userId"} or not isinstance(body["userId"], str) or not body["userId"]):
        # blocks any instances of invalid json, then blocks instances of other properties aside form user passed, then checks if userId is a string, then disallows any empty "" in userId
        return jsonify({"error": "invalid_request"}), 422
    
    userId = body["userId"]
    eventWaitlists = []
    max_position = 0
    for e in WAITLISTS.values():
        if e["eventId"] == eventId:
            eventWaitlists.append(e)
            if (e["position"] > max_position):
                max_position = e["position"] + 1

    # First time we see this key: perform the operation, then record the outcome.
    ev = EVENTS.get(eventId)
    if ev is None:
        outcome = ({"error": "event_not_found"}, 404)

    elif ev["seatsLeft"] > 0:
        outcome = ({"error": "event_not_full"}, 409)
    elif any(e["userId"] == userId for e in eventWaitlists):
        outcome = ({"error": "already_on_waitlist"}, 409)

    else:

        wid = new_waitlist_id()
        waitlist = {"id": wid, "userId": userId,"eventId": eventId,
                       "position": max_position, "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")} #INTERNAL join-order key, never returned; public position is derived
        WAITLISTS[wid] = waitlist
        true_position = len(eventWaitlists) + 1


        outcome = (waitlist_response_schema(waitlist, true_position), 201)   # sticks to strict response schema despite storing away the userId

    WL_IDEMPOTENCY[key] = {"hash": fingerprint, "status": outcome[1], "body": outcome[0]}
    return jsonify(outcome[0]), outcome[1]
        
if __name__ == "__main__":
    app.run(port=3000, threaded=True)
