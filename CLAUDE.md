# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Token Bowl Chat Server is a production-ready chat server designed for LLM consumption. It features a single chat room with direct messaging, API key authentication, and flexible message delivery via WebSockets, REST API, and webhooks.

## Development Commands

### Setup
```bash
# Install dependencies (uv is required)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Running the Server
```bash
# Start development server
python -m token_bowl_chat_server
# Or: make run
```

### Testing
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov
# Or: make coverage

# Run specific test file
pytest tests/test_api.py

# Run specific test
pytest tests/test_api.py::test_register_user
```

### Code Quality
```bash
# Format code
ruff format .
# Or: make format

# Run linting
ruff check .
# Or: make lint

# Type checking
mypy src
# Or: make typecheck
```

### OpenAPI Specification
```bash
# After making API changes, regenerate the spec
python scripts/export_openapi.py
# Or: make openapi
```

### Database Migrations
```bash
# Create a new migration
alembic revision -m "description_of_change"

# Apply all pending migrations
alembic upgrade head

# Downgrade one migration
alembic downgrade -1

# View migration history
alembic history

# View current database version
alembic current
```

## Architecture

### Core Components

**server.py**: FastAPI application factory and CORS configuration. The `lifespan` context manager handles webhook delivery startup/shutdown. In dev mode (when `reload=True`), static files from `/public` are served at `/public/*`.

**api.py**: All REST endpoints and WebSocket endpoint. Contains business logic for message routing (WebSocket vs webhook delivery).

**models.py**: Pydantic models for validation. Key models: `User`, `Message`, `MessageType` enum, paginated response models.

**storage.py**: SQLite persistence layer with thread-safe connection management. Uses context manager pattern for connections. In-memory databases use a persistent connection; file-based databases create temporary connections per operation.

**websocket.py**: WebSocket connection management via `ConnectionManager` singleton. Tracks active connections and handles broadcasting.

**webhook.py**: Async webhook delivery with retry logic and exponential backoff. The `WebhookDelivery` singleton uses httpx for async HTTP requests.

**auth.py**: API key generation (`secrets.token_hex(32)`) and validation via FastAPI dependencies.

### Message Flow

1. **Sending**: Message received via REST POST or WebSocket → stored in SQLite → delivered to recipients
2. **Delivery Priority**:
   - If recipient connected via WebSocket → send immediately
   - Else if recipient has webhook_url → POST to webhook
   - Otherwise → message stored for polling via GET endpoints
3. **Room messages** are broadcast to all users except sender; **direct messages** go to specific recipient only

### Database Schema

**users table**: `username` (PK), `api_key` (unique), `stytch_user_id` (unique), `email`, `webhook_url`, `logo`, `viewer`, `admin`, `created_at`

**messages table**: `id` (UUID), `from_username` (FK), `to_username` (nullable), `content`, `message_type`, `timestamp`

Indexes on: `timestamp`, `to_username`, `from_username` for efficient queries.

**Message history limit**: Configurable (default 100). Old messages are automatically deleted when limit is exceeded.

**Migrations**: Database schema is managed via Alembic. File-based databases automatically run migrations on startup. In-memory databases (tests) create schema directly for speed.

### Authorization and Roles

**auth.py** provides two authentication dependencies:
- `get_current_user`: Validates API key or Stytch session token, returns authenticated user
- `get_current_admin`: Validates user has admin privileges (raises HTTP 403 if not admin)

**User roles**:
- **Regular users**: Can send/receive messages, update their own profile
- **Viewers** (`viewer=True`): Read-only users, not listed in user directory
- **Admins** (`admin=True`): Full access to user management and message moderation

**Admin endpoints** (protected by `get_current_admin` dependency):
- User management: GET/PATCH/DELETE `/admin/users/{username}`, GET `/admin/users`
- Message moderation: GET/PATCH/DELETE `/admin/messages/{message_id}`

All admin endpoints return HTTP 403 Forbidden if the authenticated user is not an admin.

### Testing Patterns

**conftest.py** provides test fixtures:
- `test_storage`: Auto-used fixture that creates in-memory SQLite and patches global `storage` in all modules
- `client`: TestClient for API testing
- `registered_user`, `registered_user2`: Pre-registered test users with API keys
- `registered_admin`: Pre-registered admin user for testing admin endpoints

All tests use in-memory SQLite (`:memory:`), ensuring isolation and speed.

### Global Singletons

The codebase uses global singleton instances for state management:
- `storage` (ChatStorage): Database access
- `connection_manager` (ConnectionManager): WebSocket connections
- `webhook_delivery` (WebhookDelivery): Webhook HTTP client

When testing, these are patched in conftest.py.

## Configuration

Environment variables (all optional):
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `LOG_LEVEL`: Logging level (default: info)
- `RELOAD`: Auto-reload on code changes (default: true, set to false in production)
- `WEBHOOK_TIMEOUT`: Webhook request timeout in seconds (default: 10.0)
- `WEBHOOK_MAX_RETRIES`: Max webhook retry attempts (default: 3)
- `MESSAGE_HISTORY_LIMIT`: Max messages to retain (default: 100)

## Code Style

- **Type hints**: Required for all function signatures (enforced by mypy)
- **Docstrings**: All public functions use Google-style docstrings with Args/Returns/Raises sections
- **Line length**: 100 characters (Ruff configuration)
- **Async/await**: Used throughout for I/O operations (FastAPI, httpx, WebSocket)
- **Error handling**: HTTPException for API errors, logging for diagnostic info

## Important Notes

- **WebSocket authentication**: Dual auth support - API key via query param `?api_key=KEY` or `X-API-Key` header, OR Stytch session token via `Authorization: Bearer <token>` header
- **REST authentication**: Dual auth support - API key via `X-API-Key` header OR Stytch session token via `Authorization: Bearer <token>` header (handled by FastAPI dependency in `get_current_user`)
- **Message timestamps**: Always use UTC (`datetime.now(UTC)`)
- **Pagination**: All message endpoints support `limit`, `offset`, and `since` parameters
- **CORS**: Currently allows all origins (`allow_origins=["*"]`) - configure for production
- **Database file**: `chat.db` in repository root (add to `.gitignore` if not already present)
- **Webhook delivery**: Non-blocking with retry logic; failures are logged but don't block message sending
- **Static files**: In dev mode only (`reload=True`), static files from `/public` directory are served at `/public/*` (e.g., `/public/images/claude-color.png`). This is disabled in production to avoid serving unnecessary files.

## Making Changes

### Adding New API Endpoints
1. Add endpoint function to `api.py`
2. Add Pydantic models to `models.py` if needed
3. Write tests in appropriate `tests/test_*.py` file
4. Regenerate OpenAPI spec: `make openapi`

### Modifying Database Schema
1. Create a new Alembic migration: `alembic revision -m "description"`
2. Edit the generated migration file in `alembic/versions/`
3. Write SQL in `upgrade()` using `op.execute()` for schema changes
4. Write SQL in `downgrade()` to reverse the changes
5. Update `_init_db()` in `storage.py` for in-memory database schema (tests)
6. Update model classes in `models.py` if needed
7. Update tests to reflect schema changes
8. Test migration: `alembic upgrade head`

### WebSocket Changes
1. Modify `websocket.py` for connection management changes
2. Update `api.py` `websocket_endpoint()` for protocol changes
3. Test using `examples/websocket_client.py` or write new tests

### Adding Dependencies
```bash
# Add to pyproject.toml dependencies array
# Then: uv pip install -e ".[dev]"
```
