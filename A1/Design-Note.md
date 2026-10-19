# Design Note: Encore v1.2, The Waitlist

## 1. The waitlist resource

- The opaque id: I followed the example provided very literally with a starting wl_ + pattern (0-9)[a-z]. The code creates a random one as needed and it is created with a repeat of the pattern 4 times in order to grant enough space for a very high # of waitlists

- Public schema: following the requested with id, eventId, position, and createdAt
- userId is stored in the waitlist dict but is never revealed on any response. This is done so that the userId can be tested against for if the user is already in the waitlist while keeping the requested schema
- Position is derived not stored with intent on reveal. The positions stored for waitlists are considered to be rankings for which arrived latest to the list but not what their current position is. The position shown to the clients is derived from counting the available waitlists in order which serves as a fully automatic updatable waitlist position
- Given the instructions to keep the request schema strict, AdditionalProperties on JoinWaitlistRequest schema are false.
- Since the instructions want the responses to be evolvable, schema for Waitlist have the AdditionalProperties set as true to allow future fields to be added. 

- I originally planned to have event_entry_match_not_found which told the client that the entry existed but not for the eventID they listed. Further rethinking had me changing it back since it was not needed given the list events api and that this kind of information is typically avoided down the line if authentication is added (do not want to say that the entry exists but they got wrong info for example).

## 2. Idempotency

- Only addition with an Idempotency key is the join POST for the new waitlist entries. That is because all other new APIs added did not contain a danger from double repeated requests for the same target. The GET calls are SAFE so there is no need for an idempotency key. DELETE was idempotent in effect with repeat tries only allowing one action and nothing else. 

- The idempotency mechancism is basically that all idempotency keys tried are stored in a map along with their hashed results in a key:value pair. Before any new request, the server consults the existing map to ensure that this key had not been used before. If it had, the server checks the hashed body in the map against the hashed value of the current API. Since the hashing mechanism is deterministic, if the 2 hashes are not equivalent, then the API body is not the same

- The Idempotency keys themselves are just random generated keys (uuid4) with no purpose other than to assign an ID to the API requests and ensure no repetition with different bodies.

- WL_IDEMPOTENCY was used as a new storage area for the Idempotency map requests for all those arriving from the Waitlist API to not get mixed up with the Reservations API. It was a matter of readability, and containarization.

- Stored bodies are the public ones, so a replay cannot leak userId.

- Retention: keys are retained for at least 24 hours (stated in the contract). The entire database and replayable map live only on memory and are reset with the server restarts.

### DELETE becoming idempotent in effect natuarally:
- The DELETE being effectually idempotent is a side effect of the nature of the code not its usualy. My code only allows for the use of one waitlist entry ID once forever in the database. Even if the entry holding it is deleted, that ID is never to be used again. This was done so that there are no mistaken (Even if very unlikely) calls for old IDs that reignite. This implementation renders DELETE effectively Idempotent

- The implementation I had also utilized locks so that concurrent requests to add a waitlist ID do not conflict resulting in 2 waitlists with duplicate IDs.

- Try DELETE twice and the only thing possible is that DELETE achieves its goal and does not affect the database in any other way.

## 3. Error Catalog

- Bodies are {"error": code}. The code is the signal and never prose. Consumers must treat an unrecognized code as non-retryable and surface it, so the catalog can grow without breaking old clients.

- Retryable errors are ones whose result can change outcome with the same data in the dataset. One can think of timeouts as the easiest example to comprehend for this, a network error occured or was too slow. Simply retry and the result can change/be fixed.

| Code | Status | Meaning | Retryable |
| -------- | -------- | -------- | -------- |
| event_not_found | 404 | There is no event in the DB that has that ID | No |
| event_not_full | 409 | Joining the waitlist when event seats are available is not allowed, reserve seats instead | No |
| already_on_waitlist | 409 | User is already on the waitlist for this event, double waitlist not allowed | No |
| idempotency_key_required | 422 | The idempotency key is missing from the header | No |
| idempotency_key_reuse | 422 | The idempotency key was used for a previous request with a different body| No |
| entry_not_found | 404 | There is no waitlist entry that matches this ID within this event's waitlists | No |
| invalid_request | 422 | body missing, not an object, extra fields, or userId not a non-empty string  | No |

## 4. Compatability

Every change is additive, and breaks non of the previous implementations:


| Changes | Additive or Breaking |
| -------- | -------- |
| New paths under /events/{eventId}/waitlist | additive |
| New schema (Waitlist, JoinWaitlistRequest) | additive |
| New error codes, used only by the new operations | additive |
| Idempotency-Key requirement | additive |

**Left untouched on purpose**: the Event, Reservation and Error schemas, the reservation handler and its idempotency store, and the existing not_found and sold_out codes (renaming them would break clients matching on them). The new waitlist store and fingerprint are separate from the reservation ones.

**Evidence**: the four original conformance checks alongide the reservation checks added before code changes still run unchanged and pass

Overall version 1.2.0 (this one) is additive towards version 1.1.0

### Response-Strictness Policy

- The responses are evolvable by allowing "AdditionalProperties = true" for the Waitlist schema to allow the addition of newer fields in the future without a breaking change as requested in the assignment. Requests however are kept strict with "AdditionalProperties = false" for JoinWaitlistRequest

