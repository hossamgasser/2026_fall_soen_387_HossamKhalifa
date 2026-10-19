# AI-collaboration log : Encore v1.2, The Waitlist

- Tool: Claude (chat). 

- Used for: reserach, reviewing my YAML and handler code, and drafting suite and note text

I wrote and tested the final contract, server code and suite myself, and verified behavior with curl/Postman and the conformance suite.

## Where the assistant was wrong, incomplete, or overconfident

### 1. Storing the position

- I had asked whether to keep a stored position on the waitlist record.

- The Assistant said: don’t store it, because it goes stale after a delete.

- The porblem is that the argument assumed stored values would be returned to clients. My design recomputes position on every response, so a stored value is only a join-order key. It also overlooked that max + 1 guarantees no two live entries share a number and gave it an example (my a/b/c/d example).


Resolution: I pushed back, and the assistant conceded. I kept an internal ordering key, never returned, and derive the public position from rank on every read. A suite check confirms B’s position drops by exactly one when A leaves.

### 2. A fingerprint change explained incorrectly

- Assistant produced: a waitlist fingerprint of eventId + body hash, justified as a waitlist-specific problem (the event is in the URL, not the body).

- I pointed out that reservations also take the event from the URL, so the gap exists there too. Claude admitted the explanation was wrong and that the real reason it wasn’t applied to reservations was compatibility.

Resolution: Claude conceded that with uuid4 keys the cross-event case is practically unreachable. I reverted to the original body_hash() to stay consistent with the reservation handler, and removed the claim from the note.

### 3. Contract and Handler mismatch

- Assistant produced: {"entries": [...]} for outputs for API that did not agree with the previously provided {"waitlists": [...]}.

- The conformance suite caught it by producing an error 'waitlists' is a required property

Resolution: I changed the handler to match the contract as the contract is the source of truth.

## Verification against AI 

I did not just trust the AI, I ran manual verifications and public search (w3schools for some) on most of the claims and tested all the cases using Postman manually and the performance suite. Ran repeat tests to check correctness and effects of changing elements of the code.