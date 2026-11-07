### Grade: 88/100


### Mistakes (should be fixed in the base for A2):

- 2.2 The implementation stores idempotency keys only in an in-memory dictionary, without timestamps, persistent storage, or a mechanism that guarantees retention for at least 24 hours. As a result, previously stored outcomes may be lost when the server restarts, violating the required retention guarantee.
- 2.3 The implementation compares only the request body when checking idempotency-key reuse. Reusing the same key and body for a different event incorrectly replays the original outcome instead of returning 422 idempotency_key_reuse

