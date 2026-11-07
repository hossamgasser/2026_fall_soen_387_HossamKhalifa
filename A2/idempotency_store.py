import json, sqlite3, threading, time

DB_PATH = "idempotency.db"
RETENTION_SECONDS = 24 * 60 * 60      # rows are kept at least this long
_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS idempotency (
                     scope       TEXT NOT NULL,
                     key         TEXT NOT NULL,
                     fingerprint TEXT NOT NULL,
                     status      INTEGER NOT NULL,
                     body        TEXT NOT NULL,
                     created_at  REAL NOT NULL,
                     PRIMARY KEY (scope, key))""")
    return c

def get(scope, key):
    with _lock, _conn() as c:
        row = c.execute("SELECT fingerprint, status, body FROM idempotency "
                        "WHERE scope = ? AND key = ?", (scope, key)).fetchone()
    if row is None:
        return None
    return {"hash": row[0], "status": row[1], "body": json.loads(row[2])}

def put(scope, key, fingerprint, status, body):
    with _lock, _conn() as c:
        c.execute("INSERT OR IGNORE INTO idempotency VALUES (?,?,?,?,?,?)",
                  (scope, key, fingerprint, status, json.dumps(body), time.time()))

def purge_old():
    # only rows older than the retention window may ever be removed
    with _lock, _conn() as c:
        c.execute("DELETE FROM idempotency WHERE created_at < ?",
                  (time.time() - RETENTION_SECONDS,))