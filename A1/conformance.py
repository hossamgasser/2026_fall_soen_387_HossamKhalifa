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

idempotencyKeyReuse = str(uuid.uuid4())

def t_create_reservation_success():
    status, body = request(method = "POST", path = "/events/ev_103/reservations", headers = {"Idempotency-Key": idempotencyKeyReuse})
    assert status == 201, f"expected 201, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "201")).validate(body)

def t_create_reservation_unknownEvent():
    status, body = request(method = "POST", path = "/events/ev_1044/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 404, f"expected 404, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "404")).validate(body)

def t_create_reservation_seatsFull():
    status, body = request(method = "POST", path = "/events/ev_102/reservations", headers = {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 409, f"expected 409, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "409")).validate(body)

def t_create_reservation_missingIdempotency():
    status, body = request(method = "POST", path = "/events/ev_103/reservations")
    assert status == 422, f"expected 422, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "422")).validate(body)

def t_create_reservation_idempotencyKeyReuse():
    status, body = request(method = "POST", path = "/events/ev_103/reservations", headers = {"Idempotency-Key": idempotencyKeyReuse}, body = {"userID":"Hossam Khalifa"})
    assert status == 422, f"expected 422, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "422")).validate(body)

def t_create_reservation_idempotencyKeyReuse_sameBody():
    status, body = request(method = "POST", path = "/events/ev_103/reservations", headers = {"Idempotency-Key": idempotencyKeyReuse})
    assert status == 201, f"expected 201, got {status}"
    Draft202012Validator(schema_for("/events/{eventId}/reservations", "post", "201")).validate(body)


def t_get_known_reservation():
    status, body = get("/reservations/res_1")
    assert status == 200, f"expected 200, got {status}"
    Draft202012Validator(schema_for("/reservations/{reservationId}", "get", "200")).validate(body)

def t_unknown_id_reservation():
    status, body = get("/reservations/res_4042")
    assert status == 404, f"expected 404, got {status}"
    Draft202012Validator(schema_for("/reservations/{reservationId}", "get", "404")).validate(body)




if __name__ == "__main__":
    print("Conformance run against", BASE)
    check("GET /events matches the contract's response schema", t_list_shape)
    check("bookable=true filters and still matches the schema", t_bookable_filter)
    check("GET /events/{id} matches the Event schema", t_get_one)
    check("unknown id yields 404 with the Error schema", t_unknown_id)

    # new checks
    check("POST /events/{eventId}/reservations success matches the Event schema", t_create_reservation_success)

    check("POST /events/{eventId}/reservations with unknown eventId yields 404 with the Error schema", t_create_reservation_unknownEvent)
    check("POST /events/{eventId}/reservations with event seats full yields 409 with the Error schema", t_create_reservation_seatsFull)
    check("POST /events/{eventId}/reservations with missing Idempotency key yields 422 with the Error schema", t_create_reservation_missingIdempotency)
    check("POST /events/{eventId}/reservations with reused Idempotency key in different body yields 422 with the Error schema", t_create_reservation_idempotencyKeyReuse)
    check("POST /events/{eventId}/reservations with reused Idempotency key in same body gets same result matches the Event schema", t_create_reservation_idempotencyKeyReuse_sameBody)


    check("GET /reservations/{reservationId} matches the Reservations schema", t_get_known_reservation)
    check("unknown reservation id yields 404 with the Error schema", t_unknown_id_reservation)

    print(f"{CHECKS - FAILED}/{CHECKS} passed")
    sys.exit(1 if FAILED else 0)
