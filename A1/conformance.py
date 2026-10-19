# Listing 2.3 -- A conformance suite written against the CONTRACT, not the code.
# It reads encore-openapi.yaml, extracts the response schemas, and checks a
# running implementation against them. It never imports the server's source.
# Run (with a server on :3000): python3 listing_2_3_conformance.py
import json, sys, urllib.request, urllib.error
import yaml
from jsonschema import Draft202012Validator
import uuid                                             # following what listing_3_2_client had and what the encore-openapi.yaml requests

BASE = "http://localhost:3000"
spec = yaml.safe_load(open("encore-openapi.yaml"))

def schema_for(path, method, status):
    """Pull a response schema out of the OpenAPI document, and carry the
    components along so that $ref: '#/components/schemas/...' resolves."""
    op = spec["paths"][path][method]
    schema = op["responses"][status]["content"]["application/json"]["schema"]
    return {**schema, "components": spec["components"]}

def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as err:
        return err.code, json.load(err)

#post path for tests

def request(method, path, body=None, headers=None):
    data = json.dumps(body).encode("utf-8")
    final_headers = {"Content-Type": "application/json"}
    final_headers.update(headers or {})

    req = urllib.request.Request(url=BASE + path, data=data, method=method, headers=final_headers)

    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            raw = res.read()    
            body = json.loads(raw) if raw else None         # avoid crashing on empty returns

            return res.status, body
    except urllib.error.HTTPError as err:
        raw = err.read()
        body = json.loads(raw) if raw else None             # avoid crashing on empty returns
        return err.code, body


CHECKS = FAILED = 0
def check(name, fn):
    global CHECKS, FAILED
    CHECKS += 1
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as e:
        FAILED += 1
        msg = str(e).splitlines()[0][:100] if str(e) else type(e).__name__
        print(f"  FAIL  {name}\n        {msg}")

def t_list_shape():
    status, body = get("/events")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/events", "get", "200")).validate(body)

def t_bookable_filter():
    status, body = get("/events?bookable=true")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/events", "get", "200")).validate(body)
    assert all(e["seatsLeft"] > 0 for e in body["events"]), \
        "bookable=true returned a full event"

def t_get_one():
    status, body = get("/events/ev_101")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}", "get", "200")).validate(body)

def t_unknown_id():
    status, body = get("/events/ev_999")
    assert status == 404, f"expected 404, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}", "get", "404")).validate(body)



# new tests added for Reservations
def t_create_reservation_success():
    status, body = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, f"expected 201, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "201")).validate(body)

def t_create_reservation_unknownEvent():
    status, body = request(method = "POST", path = "/events/ev_1044/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "not_found", f"expected not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "404")).validate(body)

def t_create_reservation_seatsFull():
    status, body = request(method = "POST", path = "/events/ev_102/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 409, f"expected 409, got {status}"
    assert body["error"] == "sold_out", f"expected sold_out, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "409")).validate(body)

def t_create_reservation_missingIdempotency():
    status, body = request(method = "POST", path = "/events/ev_103/reservations")
    assert status == 422, f"expected 422, got {status}"
    assert body["error"] == "idempotency_key_required", f"expected idempotency_key_required, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "422")).validate(body)

def t_create_reservation_idempotencyKeyReuse():

    key = str(uuid.uuid4())
    status, created = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": key})
    assert status == 201, f"setup failed: expected 201, got {status}"

    status, body = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": key}, body = {"userID":"Hossam Khalifa"})
    assert status == 422, f"expected 422, got {status}"
    assert body["error"] == "idempotency_key_reuse", f"expected idempotency_key_reuse, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "422")).validate(body)

def t_create_reservation_idempotencyKeyReuse_sameBody():

    key = str(uuid.uuid4())
    status, created = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": key})
    assert status == 201, f"setup failed: expected 201, got {status}"


    status, body = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": key})
    assert status == 201, f"expected 201, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "201")).validate(body)


def t_get_known_reservation():

    status, created = request(method = "POST", path = "/events/ev_101/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, f"setup failed: expected 201, got {status}"

    status, body = get(f"/reservations/{created['id']}")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/reservations/{reservationId}", "get", "200")).validate(body)

def t_unknown_id_reservation():
    status, body = get("/reservations/res_4042")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "not_found", f"expected not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/reservations/{reservationId}", "get", "404")).validate(body)

# newest Tests to be written to confirm conformance.

def t_join_waitlist():

    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"
    assert "userId" not in body, "userId leaked into the join response"
    
    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "201")).validate(body)

def t_join_waitlist_unknown_event():

    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_10000/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "event_not_found", f"expected event_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "404")).validate(body)

def t_no_waitlist_available_seats():
    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_101/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 409, f"expected 409, got {status}"
    assert body["error"] == "event_not_full", f"expected event_not_full, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "409")).validate(body)

def t_already_in_waitlist():

    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 409, f"expected 409, got {status}"
    assert body["error"] == "already_on_waitlist", f"expected already_on_waitlist, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "409")).validate(body)


def t_join_waitlist_broken_userId_body():
    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":5})
    assert status == 422, f"expected 422, got {status}"
    assert body["error"] == "invalid_request", f"expected invalid_request, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "422")).validate(body)


def t_join_waitlist_missing_Idempotency():
    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", body = {"userId":user})
    assert status == 422, f"expected 422, got {status}"
    assert body["error"] == "idempotency_key_required", f"expected idempotency_key_required, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "422")).validate(body)

def t_join_waitlist_Idempotency_reuse_diff_body():
    user = "user-" + str(uuid.uuid4())

    key = str(uuid.uuid4())
    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"

    user2 = "user-" + str(uuid.uuid4())


    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId":user2})
    assert status == 422, f"expected 422, got {status}"
    assert body["error"] == "idempotency_key_reuse", f"expected idempotency_key_reuse, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "422")).validate(body)


def t_join_waitlist_Idempotency_reuse_same_body_success():
    user = "user-" + str(uuid.uuid4())

    key = str(uuid.uuid4())
    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "201")).validate(body)


def t_join_waitlist_Idempotency_reuse_same_body_fail():
    user = "user-" + str(uuid.uuid4())

    status, body = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId": user})
    assert status == 201, f"expected 201, got {status}"


    key = str(uuid.uuid4())
    status, first = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId": user})
    assert status == 409, f"expected 409, got {status}"
    assert first["error"] == "already_on_waitlist", f"expected already_on_waitlist, got {first.get('error')}"

    status, again = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": key}, body = {"userId": user})
    assert status == 409, f"expected 409, got {status}"
    assert again["error"] == "already_on_waitlist", f"expected already_on_waitlist, got {again.get('error')}"
    assert again == first, "replay differs from the first 409"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "post", "409")).validate(again)



def t_get_event_waitlists():

    status, body = get("/events/ev_102/waitlist")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "get", "200")).validate(body)

def t_get_unknown_event_waitlists():

    status, body = get("/events/ev_100000/waitlist")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "event_not_found", f"expected event_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist", "get", "404")).validate(body)

def t_get_specific_waitlist():

    user = "user-" + str(uuid.uuid4())

    status, created = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"


    status, body = get(f"/events/ev_102/waitlist/{created['id']}")
    assert status == 200, f"expected 200, got {status}"
    assert "userId" not in body, "userId leaked into the join response"
    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "get", "200")).validate(body)

def t_joined_other_event():

    user = "user-" + str(uuid.uuid4())

    status, created = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"


    status, body = get(f"/events/ev_101/waitlist/{created['id']}")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "entry_not_found", f"expected entry_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "get", "404")).validate(body)


def t_get_specific_waitlist_unknown_event():

    status, body = get(f"/events/ev_100002/waitlist/anyid")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "event_not_found", f"expected event_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "get", "404")).validate(body)


def t_get_specific_waitlist_unknown_entry():

    status, body = get(f"/events/ev_102/waitlist/wl_0a0a0a0a0a") #random unknown entry id that matches format of the waitlist entry ids
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "entry_not_found", f"expected entry_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "get", "404")).validate(body)


def t_delete_waitlist():

    user = "user-" + str(uuid.uuid4())

    status, created = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"

    path = f"/events/ev_102/waitlist/{created['id']}"


    status, body = request(method = "DELETE", path = path)
    assert status == 204, f"expected 204, got {status}"
    assert body is None, f"204 must have no body, got {body}"

    status, body = get(path)
    assert status == 404, f"expected 404 after delete, got {status}"
    assert body["error"] == "entry_not_found", f"got {body.get('error')}"

    status, body = request(method="DELETE", path=path)                                      # proves effectual idempotency without idempotency key
    assert status == 404, f"expected 404 on repeat delete, got {status}"
    assert body["error"] == "entry_not_found", f"got {body.get('error')}"
    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "delete", "404")).validate(body)

    
def t_delete_waitlist_unknown_event():

    status, body = request(method = "DELETE", path = "/events/ev_10000/waitlist/0a0a0a0a")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "event_not_found", f"expected event_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "delete", "404")).validate(body)

def t_delete_waitlist_unknown_entry():

    status, body = request(method = "DELETE", path = "/events/ev_102/waitlist/0b0b0b0b0b")
    assert status == 404, f"expected 404, got {status}"
    assert body["error"] == "entry_not_found", f"expected entry_not_found, got {body.get('error')}"

    Draft202012Validator(schema_for("/events/{eventId}/waitlist/{entryId}", "delete", "404")).validate(body)

def t_position_change_after_waitlist_delete():
    user = "user-" + str(uuid.uuid4())

    status, first = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"
    assert "userId" not in first, "userId leaked into the join response"

    user = "user-" + str(uuid.uuid4())
    status, second = request(method = "POST", path = "/events/ev_102/waitlist", headers = {"Idempotency-Key": str(uuid.uuid4())}, body = {"userId":user})
    assert status == 201, f"expected 201, got {status}"
    assert "userId" not in second, "userId leaked into the join response"

    status, body = get("/events/ev_102/waitlist")
    assert status == 200, f"expected 200, got {status}"

    positions = {e["id"]: e["position"] for e in body["waitlists"]}

    initial_pos_a = positions[first["id"]]
    initial_pos_b = positions[second["id"]]

    assert initial_pos_b == initial_pos_a + 1, "B should be directly behind A"

    path = f"/events/ev_102/waitlist/{first['id']}"
    status, body = request(method = "DELETE", path = path)
    assert status == 204, f"expected 204, got {status}"

    status, body = get("/events/ev_102/waitlist")
    assert status == 200, f"expected 200, got {status}"

    positions = {e["id"]: e["position"] for e in body["waitlists"]}

    final_pos_b = positions[second["id"]]

    assert final_pos_b == initial_pos_b - 1, "B should move 1 space up now that A is gone"



if __name__ == "__main__":
    print("Conformance run against", BASE)
    check("GET /events matches the contract's response schema", t_list_shape)
    check("bookable=true filters and still matches the schema", t_bookable_filter)
    check("GET /events/{id} matches the Event schema", t_get_one)
    check("unknown id yields 404 with the Error schema", t_unknown_id)

    # new checks
    check("POST /events/{eventId}/reservations success matches the reservation schema", t_create_reservation_success)

    check("POST /events/{eventId}/reservations with unknown eventId yields 404 with the Error schema", t_create_reservation_unknownEvent)
    check("POST /events/{eventId}/reservations with event seats full yields 409 with the Error schema", t_create_reservation_seatsFull)
    check("POST /events/{eventId}/reservations with missing Idempotency key yields 422 with the Error schema", t_create_reservation_missingIdempotency)
    check("POST /events/{eventId}/reservations with reused Idempotency key in different body yields 422 with the Error schema", t_create_reservation_idempotencyKeyReuse)
    check("POST /events/{eventId}/reservations with reused Idempotency key in same body gets same result matches the reservation schema", t_create_reservation_idempotencyKeyReuse_sameBody)


    check("GET /reservations/{reservationId} matches the Reservations schema", t_get_known_reservation)
    check("unknown reservation id yields 404 with the Error schema", t_unknown_id_reservation)


    # Newest checks POST adding waitlist

    # new checks: POST /events/{eventId}/waitlist
    check("POST /events/{eventId}/waitlist success matches the waitlist schema", t_join_waitlist)
    check("POST /events/{eventId}/waitlist with unknown eventId yields 404 event_not_found with the Error schema", t_join_waitlist_unknown_event)
    check("POST /events/{eventId}/waitlist with seats still available yields 409 event_not_full with the Error schema", t_no_waitlist_available_seats)
    check("POST /events/{eventId}/waitlist with a user already on the waitlist yields 409 already_on_waitlist with the Error schema", t_already_in_waitlist)
    check("POST /events/{eventId}/waitlist with a broken userId body yields 422 invalid_request with the Error schema", t_join_waitlist_broken_userId_body)
    check("POST /events/{eventId}/waitlist with missing Idempotency key yields 422 idempotency_key_required with the Error schema", t_join_waitlist_missing_Idempotency)
    check("POST /events/{eventId}/waitlist with reused Idempotency key in different body yields 422 idempotency_key_reuse with the Error schema", t_join_waitlist_Idempotency_reuse_diff_body)
    check("POST /events/{eventId}/waitlist with reused Idempotency key in same body replays the same entry", t_join_waitlist_Idempotency_reuse_same_body_success)
    check("POST /events/{eventId}/waitlist with reused Idempotency key replays the same 409 already_on_waitlist", t_join_waitlist_Idempotency_reuse_same_body_fail)

    # new checks: GET /events/{eventId}/waitlist

    check("GET /events/{eventId}/waitlist matches the waitlist list schema", t_get_event_waitlists)
    check("GET /events/{eventId}/waitlist with unknown eventId yields 404 event_not_found with the Error schema", t_get_unknown_event_waitlists)

    # new checks: GET /events/{eventId}/waitlist/{entryId}

    check("GET /events/{eventId}/waitlist/{entryId} matches the waitlist schema", t_get_specific_waitlist)
    check("GET /events/{eventId}/waitlist/{entryId} joined different event and looked up entry on wrong event yields 404 entry_not_found with the Error schema", t_joined_other_event)

    check("GET /events/{eventId}/waitlist/{entryId} with unknown eventId yields 404 event_not_found with the Error schema", t_get_specific_waitlist_unknown_event)
    check("GET /events/{eventId}/waitlist/{entryId} with unknown entryId yields 404 entry_not_found with the Error schema", t_get_specific_waitlist_unknown_entry)
    
    # new checks: DELETE /events/{eventId}/waitlist/{entryId}

    check("DELETE /events/{eventId}/waitlist/{entryId} removes the entry (204) and a repeat yields 404 entry_not_found", t_delete_waitlist)
    check("DELETE /events/{eventId}/waitlist/{entryId} with unknown eventId yields 404 event_not_found with the Error schema", t_delete_waitlist_unknown_event)
    check("DELETE /events/{eventId}/waitlist/{entryId} with unknown entryId yields 404 entry_not_found with the Error schema", t_delete_waitlist_unknown_entry)
    
    # a test that mixes all of them
    check("waitlist position moves up by one when an earlier entry is deleted", t_position_change_after_waitlist_delete)


    print(f"{CHECKS - FAILED}/{CHECKS} passed")
    sys.exit(1 if FAILED else 0)
