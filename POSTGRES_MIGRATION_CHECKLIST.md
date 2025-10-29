# PostgreSQL Migration Technical Checklist

## Pre-Migration Setup

### Dependencies
```toml
# Add to pyproject.toml
[project.dependencies]
    "psycopg[binary]>=3.1.0",  # or asyncpg>=0.29.0 for async
    "testcontainers[postgres]>=3.7.0",  # for testing
```

### Configuration Changes
```python
# Add to config.py
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost/chatdb"
)
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "20"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "40"))
```

## SQL Query Conversions

### 1. Parameter Placeholders
```python
# SQLite (current)
cursor.execute("SELECT * FROM users WHERE username = ?", (username,))

# PostgreSQL (psycopg3)
cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
```

### 2. Boolean Fields
```python
# SQLite (current)
cursor.execute("SELECT * FROM users WHERE viewer = 0 AND admin = 1")

# PostgreSQL
cursor.execute("SELECT * FROM users WHERE viewer = false AND admin = true")
```

### 3. JSON Storage
```python
# SQLite (current) - storage.py line 1171
message_ids_json = json.dumps([str(msg_id) for msg_id in conversation.message_ids])
cursor.execute(
    "INSERT INTO conversations (..., message_ids) VALUES (..., ?)",
    (..., message_ids_json)
)

# PostgreSQL with JSONB
cursor.execute(
    "INSERT INTO conversations (..., message_ids) VALUES (..., %s::jsonb)",
    (..., [str(msg_id) for msg_id in conversation.message_ids])
)
```

### 4. JSON Queries
```python
# SQLite (current) - storage.py line 1209
message_ids = [UUID(msg_id) for msg_id in json.loads(row["message_ids"])]

# PostgreSQL
# No JSON parsing needed, JSONB returns native Python lists
message_ids = [UUID(msg_id) for msg_id in row["message_ids"]]
```

### 5. RETURNING Clauses
```python
# SQLite (current) - must query after insert
cursor.execute("INSERT INTO messages ...")
cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))

# PostgreSQL - can return in same query
cursor.execute(
    "INSERT INTO messages (...) VALUES (...) RETURNING *",
    (...)
)
row = cursor.fetchone()
```

## Schema Conversions

### Users Table
```sql
-- SQLite (current)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    stytch_user_id TEXT UNIQUE,
    email TEXT,
    webhook_url TEXT,
    logo TEXT,
    role TEXT NOT NULL DEFAULT 'member',
    created_by TEXT,
    viewer INTEGER NOT NULL DEFAULT 0,
    admin INTEGER NOT NULL DEFAULT 0,
    bot INTEGER NOT NULL DEFAULT 0,
    emoji TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id)
)

-- PostgreSQL
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    stytch_user_id VARCHAR(255) UNIQUE,
    email VARCHAR(255),
    webhook_url TEXT,
    logo VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    created_by UUID REFERENCES users(id),
    viewer BOOLEAN NOT NULL DEFAULT false,
    admin BOOLEAN NOT NULL DEFAULT false,
    bot BOOLEAN NOT NULL DEFAULT false,
    emoji VARCHAR(10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

### Messages Table
```sql
-- SQLite (current)
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    from_username TEXT NOT NULL,
    to_username TEXT,
    content TEXT NOT NULL,
    message_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (from_username) REFERENCES users(username)
)

-- PostgreSQL
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_username VARCHAR(50) NOT NULL REFERENCES users(username),
    to_username VARCHAR(50) REFERENCES users(username),
    content TEXT NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (message_type IN ('room', 'direct'))
)
```

### Conversations Table
```sql
-- SQLite (current)
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    message_ids TEXT NOT NULL,  -- JSON string
    created_by_username TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by_username) REFERENCES users(username) ON DELETE CASCADE
)

-- PostgreSQL
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(200),
    description TEXT,
    message_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by_username VARCHAR(50) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)

-- Add index for JSONB queries
CREATE INDEX idx_conversations_message_ids ON conversations USING GIN (message_ids);
```

## Connection Management

### Current SQLite Pattern
```python
# storage.py lines 156-168
@contextmanager
def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
    if self._conn is not None:
        yield self._conn
    else:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
```

### PostgreSQL with Connection Pool
```python
import psycopg_pool

class PostgreSQLStorage:
    def __init__(self, database_url: str):
        self.pool = psycopg_pool.ConnectionPool(
            database_url,
            min_size=4,
            max_size=20,
            timeout=30,
            max_idle=300,
        )

    @contextmanager
    def _get_connection(self):
        with self.pool.connection() as conn:
            yield conn
```

## Testing Changes

### Current Test Setup
```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def test_storage():
    test_storage_instance = ChatStorage(db_path=":memory:")
    # ...
```

### PostgreSQL Test Setup
```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres

@pytest.fixture(autouse=True)
def test_storage(postgres_container):
    database_url = postgres_container.get_connection_url()
    test_storage_instance = PostgreSQLStorage(database_url)
    # Run migrations
    # ...
    yield test_storage_instance
    # Cleanup
```

## Alembic Migration Updates

### Update env.py
```python
# alembic/env.py
def run_migrations_online() -> None:
    # Detect database type from URL
    url = config.get_main_option("sqlalchemy.url")

    if url.startswith("postgresql"):
        # PostgreSQL configuration
        connectable = create_engine(
            url,
            poolclass=pool.NullPool,
            connect_args={"options": "-c timezone=utc"}
        )
    else:
        # SQLite configuration
        connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Important for PostgreSQL
            compare_server_default=True,
        )
        # ...
```

## Data Migration Script

```python
#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL."""

import json
import sqlite3
import psycopg
from datetime import datetime
from uuid import UUID

def migrate_data(sqlite_path: str, postgres_url: str):
    # Connect to both databases
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    with psycopg.connect(postgres_url) as pg_conn:
        with pg_conn.cursor() as pg_cursor:
            # Migrate users
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("SELECT * FROM users")

            for row in sqlite_cursor:
                pg_cursor.execute("""
                    INSERT INTO users (
                        id, username, api_key, stytch_user_id, email,
                        webhook_url, logo, role, created_by,
                        viewer, admin, bot, emoji, created_at
                    ) VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::uuid,
                        %s::boolean, %s::boolean, %s::boolean, %s, %s::timestamptz
                    )
                """, (
                    row['id'], row['username'], row['api_key'],
                    row['stytch_user_id'], row['email'],
                    row['webhook_url'], row['logo'], row['role'],
                    row['created_by'],
                    bool(row['viewer']), bool(row['admin']), bool(row['bot']),
                    row['emoji'], row['created_at']
                ))

            # Migrate conversations with JSON conversion
            sqlite_cursor.execute("SELECT * FROM conversations")

            for row in sqlite_cursor:
                message_ids = json.loads(row['message_ids'])
                pg_cursor.execute("""
                    INSERT INTO conversations (
                        id, title, description, message_ids,
                        created_by_username, created_at
                    ) VALUES (
                        %s::uuid, %s, %s, %s::jsonb, %s, %s::timestamptz
                    )
                """, (
                    row['id'], row['title'], row['description'],
                    json.dumps(message_ids),  # Will be cast to JSONB
                    row['created_by_username'], row['created_at']
                ))

            pg_conn.commit()

    sqlite_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate_data("chat.db", "postgresql://user:pass@localhost/chatdb")
```

## Performance Optimizations

### Add Missing Indexes
```sql
-- Add compound indexes for common queries
CREATE INDEX idx_messages_from_timestamp ON messages(from_username, timestamp DESC);
CREATE INDEX idx_messages_to_timestamp ON messages(to_username, timestamp DESC) WHERE to_username IS NOT NULL;
CREATE INDEX idx_read_receipts_username_message ON read_receipts(username, message_id);

-- Add partial indexes for boolean flags
CREATE INDEX idx_users_viewers ON users(username) WHERE viewer = true;
CREATE INDEX idx_users_admins ON users(username) WHERE admin = true;
CREATE INDEX idx_users_bots ON users(username) WHERE bot = true;
```

### Query Optimization Examples
```python
# Use prepared statements for repeated queries
class PostgreSQLStorage:
    def __init__(self):
        self._prepared_statements = {}

    def prepare_statements(self, conn):
        conn.execute("""
            PREPARE get_user_by_username AS
            SELECT * FROM users WHERE username = $1
        """)
        self._prepared_statements['get_user_by_username'] = True

    def get_user_by_username(self, username: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if 'get_user_by_username' not in self._prepared_statements:
                self.prepare_statements(conn)

            cursor.execute("EXECUTE get_user_by_username (%s)", (username,))
            return cursor.fetchone()
```

## Rollback Plan

1. **Keep SQLite database intact** during migration
2. **Use feature flag** to switch between databases:
```python
if os.getenv("USE_POSTGRES", "false").lower() == "true":
    storage = PostgreSQLStorage(DATABASE_URL)
else:
    storage = ChatStorage("chat.db")
```
3. **Backup PostgreSQL** before each deployment
4. **Test rollback procedure** in staging
5. **Keep migration scripts** bidirectional

## Monitoring & Alerts

### Key Metrics to Track
- Connection pool usage
- Query execution time
- Lock wait time
- Transaction duration
- Replication lag (if using replicas)

### Add Query Logging
```python
import logging
import time

def log_slow_queries(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        if duration > 1.0:  # Log queries over 1 second
            logging.warning(f"Slow query in {func.__name__}: {duration:.2f}s")
        return result
    return wrapper
```

## Production Deployment

### Environment Variables
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
DATABASE_POOL_TIMEOUT=30
DATABASE_ECHO=false  # Set to true for SQL logging in dev
DATABASE_SSL_MODE=require  # For production
```

### Docker Compose Addition
```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: chatdb
      POSTGRES_USER: chatuser
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U chatuser"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

## Verification Tests

### Data Integrity Checks
```python
def verify_migration(sqlite_path: str, postgres_url: str):
    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg.connect(postgres_url)

    # Check row counts
    tables = ['users', 'messages', 'conversations', 'read_receipts']
    for table in tables:
        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        pg_count = pg_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert sqlite_count == pg_count, f"Mismatch in {table}: SQLite={sqlite_count}, PG={pg_count}"

    # Check data integrity
    # ... additional checks ...

    print("✅ All verification checks passed!")
```

## Common Pitfalls to Avoid

1. **UUID Handling**: PostgreSQL has native UUID type, no string conversion needed
2. **Case Sensitivity**: PostgreSQL folds unquoted identifiers to lowercase
3. **Transaction Isolation**: Default is READ COMMITTED vs SQLite's SERIALIZABLE
4. **NULL Handling**: PostgreSQL is stricter about NULL in unique constraints
5. **Timezone**: Always use TIMESTAMPTZ, not TIMESTAMP
6. **Connection Limits**: PostgreSQL has connection limits, use pooling
7. **Index Usage**: PostgreSQL might not use indexes without proper statistics
8. **JSONB vs JSON**: Always use JSONB, not JSON type