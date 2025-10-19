# RBAC Implementation Plan

## Executive Summary

This document outlines the plan to transition the Token Bowl Chat Server from boolean-based authorization (`admin`, `viewer`, `bot` flags) to a role-based access control (RBAC) system integrated with Stytch's metadata-based authorization.

**Key Goals:**
- Centralize authorization logic using roles and permissions
- Integrate with Stytch for role management
- Maintain backward compatibility during transition
- Enable fine-grained access control

**Timeline Estimate:** 8-12 hours of development + testing

---

## Current State vs. Target State

### Current State
```python
class User:
    admin: bool = False      # Full access
    viewer: bool = False     # Read-only
    bot: bool = False        # Room messages only
    # Authorization: if user.admin: ...
```

### Target State
```python
class User:
    role: Role = Role.MEMBER  # Centralized role
    # Authorization: if user.has_permission(Permission.DELETE_USER): ...
```

---

## Architecture Overview

### Role Hierarchy

```
Role.ADMIN
  ├─ Full CRUD on all resources
  ├─ Assign roles to other users
  └─ Access admin endpoints

Role.MEMBER (default)
  ├─ Send/receive messages (room + DM)
  ├─ Update own profile
  └─ Read user lists

Role.VIEWER
  ├─ Read messages
  ├─ Send room messages only (no DMs)
  └─ Cannot update profile

Role.BOT
  ├─ Read messages
  ├─ Send room messages only (no DMs)
  └─ Update own profile
```

### Permission System

```python
# Granular permissions mapped to roles
Permission.READ_MESSAGES           # All roles
Permission.SEND_ROOM_MESSAGE       # All roles
Permission.SEND_DIRECT_MESSAGE     # ADMIN, MEMBER only
Permission.UPDATE_OWN_PROFILE      # ADMIN, MEMBER, BOT
Permission.UPDATE_ANY_USER         # ADMIN only
Permission.DELETE_USER             # ADMIN only
Permission.ASSIGN_ROLES            # ADMIN only
Permission.ADMIN_ACCESS            # ADMIN only
```

### Dual Authentication Strategy

```
┌─────────────────────────────────────────────┐
│           User Authentication               │
├─────────────────────────────────────────────┤
│                                             │
│  API Key Auth          Stytch Session Auth │
│  (Programmatic)        (Human Users)        │
│       │                       │             │
│       └───────┬───────────────┘             │
│               │                             │
│       ┌───────▼────────┐                    │
│       │  get_current_  │                    │
│       │     user()     │                    │
│       └───────┬────────┘                    │
│               │                             │
│       ┌───────▼────────┐                    │
│       │ User with Role │                    │
│       └───────┬────────┘                    │
│               │                             │
│       ┌───────▼────────┐                    │
│       │  has_permission│                    │
│       │   (perm)?      │                    │
│       └────────────────┘                    │
│                                             │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         Role Storage & Sync                 │
├─────────────────────────────────────────────┤
│                                             │
│  Local DB (SQLite)     Stytch              │
│  ┌──────────────┐      ┌──────────────┐    │
│  │ users table  │◄────►│ trusted_     │    │
│  │ role: string │ sync │ metadata.role│    │
│  └──────────────┘      └──────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Data Layer (Storage) ✓ STARTED
**Status:** Models updated, storage changes pending
**Risk:** Medium - Database schema change
**Time:** 2-3 hours

#### 1.1 Update Database Schema
```python
# storage.py - Update _init_db()
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    api_key TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',  # NEW FIELD
    stytch_user_id TEXT UNIQUE,
    email TEXT,
    webhook_url TEXT,
    logo TEXT,
    viewer INTEGER DEFAULT 0,              # DEPRECATED
    admin INTEGER DEFAULT 0,               # DEPRECATED
    bot INTEGER DEFAULT 0,                 # DEPRECATED
    emoji TEXT,
    created_at TEXT NOT NULL
)
```

#### 1.2 Add Migration Logic
```python
# storage.py - Add migration method
def migrate_roles_from_legacy_fields(self) -> int:
    """One-time migration of existing users to role-based system.

    Returns:
        Number of users migrated
    """
    with self._get_connection() as conn:
        cursor = conn.cursor()

        # Update existing users
        cursor.execute("""
            UPDATE users
            SET role = CASE
                WHEN admin = 1 THEN 'admin'
                WHEN viewer = 1 THEN 'viewer'
                WHEN bot = 1 THEN 'bot'
                ELSE 'member'
            END
            WHERE role IS NULL OR role = ''
        """)

        return cursor.rowcount
```

#### 1.3 Update Storage Methods
- [x] `add_user()` - Store role field
- [x] `get_user_by_username()` - Return User with role
- [x] `get_user_by_api_key()` - Return User with role
- [ ] `update_user_role()` - New method for role updates
- [ ] Update all User construction to include role field

#### 1.4 Backward Compatibility
```python
# User model validator ensures legacy fields stay synced
@model_validator(mode="after")
def sync_role_with_legacy_fields(self) -> "User":
    self.admin = self.role == Role.ADMIN
    self.viewer = self.role == Role.VIEWER
    self.bot = self.role == Role.BOT
    return self
```

### Phase 2: Stytch Integration
**Status:** Not started
**Risk:** Medium - External dependency
**Time:** 2-3 hours

#### 2.1 Update Stytch Client
```python
# stytch_client.py - Add role management methods

async def set_user_role(self, stytch_user_id: str, role: Role) -> bool:
    """Set role in user's trusted_metadata.

    Args:
        stytch_user_id: Stytch user ID
        role: Role to assign

    Returns:
        True if successful
    """
    if not self._client:
        return False

    try:
        await self._client.users.update_async(
            user_id=stytch_user_id,
            trusted_metadata={"role": role.value}
        )
        return True
    except StytchError as e:
        logger.error(f"Failed to set Stytch role: {e}")
        return False

async def get_user_role(self, stytch_user_id: str) -> Optional[Role]:
    """Get role from user's trusted_metadata.

    Args:
        stytch_user_id: Stytch user ID

    Returns:
        Role if found, None otherwise
    """
    if not self._client:
        return None

    try:
        response = await self._client.users.get_async(user_id=stytch_user_id)
        role_str = response.user.trusted_metadata.get("role")
        if role_str:
            return Role(role_str)
        return None
    except (StytchError, ValueError) as e:
        logger.error(f"Failed to get Stytch role: {e}")
        return None

async def sync_role_to_stytch(self, stytch_user_id: str, role: Role) -> bool:
    """Sync local role to Stytch metadata.

    This ensures Stytch is the source of truth for roles.
    """
    return await self.set_user_role(stytch_user_id, role)
```

#### 2.2 Update Authentication Flow
```python
# auth.py - Update get_current_user()

async def get_current_user(...) -> User:
    # ... existing auth logic ...

    # For Stytch users, sync role from Stytch to local DB
    if user and user.stytch_user_id:
        stytch_role = await stytch_client.get_user_role(user.stytch_user_id)
        if stytch_role and stytch_role != user.role:
            # Stytch role differs - update local DB
            storage.update_user_role(user.username, stytch_role)
            user.role = stytch_role

    return user
```

#### 2.3 Stytch Custom Claims Template

**Manual Setup Required in Stytch Dashboard:**

1. Navigate to: Dashboard → Authentication → Custom Claims
2. Create template:
```json
{
  "role": "{{ user.trusted_metadata.role }}"
}
```
3. This includes role in JWTs automatically

### Phase 3: API Endpoints
**Status:** Not started
**Risk:** High - Many endpoints to update
**Time:** 3-4 hours

#### 3.1 Update Registration Endpoint
```python
# api.py

@router.post("/register", ...)
async def register_user(registration: UserRegistration) -> UserRegistrationResponse:
    # Determine role from registration data
    role = registration.get_role()  # Uses new helper method

    # Generate API key
    api_key = generate_api_key()

    # Create user with role
    user = User(
        username=registration.username,
        api_key=api_key,
        role=role,  # NEW: Use role instead of booleans
        webhook_url=registration.webhook_url,
        logo=registration.logo,
        emoji=registration.emoji,
    )

    storage.add_user(user)

    return UserRegistrationResponse(
        username=user.username,
        api_key=api_key,
        role=user.role,  # NEW: Include role in response
        ...
    )
```

#### 3.2 Add Role Assignment Endpoint
```python
# api.py - NEW ENDPOINT

@router.patch(
    "/admin/users/{username}/role",
    response_model=AssignRoleResponse
)
async def assign_user_role(
    username: str,
    request: AssignRoleRequest,
    admin_user: User = Depends(require_permission(Permission.ASSIGN_ROLES))
) -> AssignRoleResponse:
    """Assign a role to a user (admin only).

    This updates both local database and Stytch metadata.
    """
    # Get target user
    user = storage.get_user_by_username(username)
    if not user:
        raise HTTPException(404, f"User {username} not found")

    # Update role in local DB
    success = storage.update_user_role(username, request.role)
    if not success:
        raise HTTPException(500, "Failed to update role")

    # Sync to Stytch if user has Stytch ID
    if user.stytch_user_id:
        await stytch_client.set_user_role(user.stytch_user_id, request.role)

    logger.info(
        f"Admin {admin_user.username} assigned role {request.role.value} "
        f"to user {username}"
    )

    return AssignRoleResponse(
        username=username,
        role=request.role,
        message=f"Role updated to {request.role.value}"
    )
```

#### 3.3 Update Message Endpoints with Permission Checks

**Before:**
```python
@router.post("/messages", ...)
async def send_message(
    message_request: SendMessageRequest,
    current_user: User = Depends(get_current_user)
):
    # Check bot restriction manually
    if current_user.bot and message_request.to_username:
        raise HTTPException(403, "Bots cannot send DMs")
    ...
```

**After:**
```python
@router.post("/messages", ...)
async def send_message(
    message_request: SendMessageRequest,
    current_user: User = Depends(get_current_user)
):
    # Permission check is declarative
    if message_request.to_username:
        if not current_user.has_permission(Permission.SEND_DIRECT_MESSAGE):
            raise HTTPException(
                403,
                f"Your role '{current_user.role.value}' cannot send direct messages"
            )
    else:
        if not current_user.has_permission(Permission.SEND_ROOM_MESSAGE):
            raise HTTPException(
                403,
                f"Your role '{current_user.role.value}' cannot send room messages"
            )
    ...
```

#### 3.4 Update Admin Endpoints

**Before:**
```python
@router.delete("/admin/users/{username}")
async def admin_delete_user(
    username: str,
    admin_user: User = Depends(get_current_admin)
):
    ...
```

**After:**
```python
@router.delete("/admin/users/{username}")
async def admin_delete_user(
    username: str,
    admin_user: User = Depends(require_permission(Permission.DELETE_USER))
):
    ...
```

#### 3.5 Update Profile Endpoints

```python
@router.patch("/users/me/username")
async def update_my_username(
    request: UpdateUsernameRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_OWN_PROFILE))
):
    # Viewers cannot update their profile
    ...

@router.patch("/users/me/webhook")
async def update_my_webhook(
    request: UpdateWebhookRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_OWN_PROFILE))
):
    ...
```

#### 3.6 Update User List Endpoints

```python
# api.py - Update PublicUserProfile responses

@router.get("/users", response_model=list[PublicUserProfile])
async def get_users(current_user: User = Depends(get_current_user)):
    users = storage.get_chat_users()
    return [
        PublicUserProfile(
            username=user.username,
            role=user.role,  # NEW: Include role
            logo=user.logo,
            emoji=user.emoji,
            bot=user.bot,      # Keep for backward compatibility
            viewer=user.viewer # Keep for backward compatibility
        )
        for user in users
    ]
```

### Phase 4: WebSocket Authorization
**Status:** Not started
**Risk:** Medium - Real-time messaging
**Time:** 1-2 hours

#### 4.1 Update WebSocket Message Handling
```python
# api.py - websocket_endpoint()

# Check permission for sending messages
if msg_type == "message":
    to_username = data.get("to_username")

    if to_username:
        # Direct message
        if not user.has_permission(Permission.SEND_DIRECT_MESSAGE):
            await websocket.send_json({
                "type": "error",
                "error": f"Your role '{user.role.value}' cannot send direct messages"
            })
            continue
    else:
        # Room message
        if not user.has_permission(Permission.SEND_ROOM_MESSAGE):
            await websocket.send_json({
                "type": "error",
                "error": f"Your role '{user.role.value}' cannot send room messages"
            })
            continue
```

#### 4.2 Update WebSocket User Discovery
```python
# Return role in user profiles
elif msg_type == "get_user_profile":
    u = storage.get_user_by_username(username)
    if not u:
        await websocket.send_json({"type": "error", "error": f"User {username} not found"})
        continue

    await websocket.send_json({
        "type": "user_profile",
        "user": {
            "username": u.username,
            "role": u.role.value,  # NEW
            "logo": u.logo,
            "emoji": u.emoji,
            "bot": u.bot,
            "viewer": u.viewer,
        },
    })
```

### Phase 5: Testing
**Status:** Not started
**Risk:** High - Comprehensive testing required
**Time:** 2-3 hours

#### 5.1 Unit Tests for Authorization

```python
# tests/test_auth.py - NEW TESTS

def test_require_permission_grants_access():
    """Test that users with permission can access endpoints."""
    admin_user = User(username="admin", api_key="key", role=Role.ADMIN)
    assert admin_user.has_permission(Permission.DELETE_USER)

def test_require_permission_denies_access():
    """Test that users without permission are denied."""
    member_user = User(username="member", api_key="key", role=Role.MEMBER)
    assert not member_user.has_permission(Permission.DELETE_USER)

def test_role_permissions_admin():
    """Test admin has all permissions."""
    admin = User(username="admin", api_key="key", role=Role.ADMIN)
    for permission in Permission:
        assert admin.has_permission(permission)

def test_role_permissions_viewer():
    """Test viewer has only read permissions."""
    viewer = User(username="viewer", api_key="key", role=Role.VIEWER)
    assert viewer.has_permission(Permission.READ_MESSAGES)
    assert viewer.has_permission(Permission.READ_USERS)
    assert not viewer.has_permission(Permission.SEND_DIRECT_MESSAGE)
    assert not viewer.has_permission(Permission.UPDATE_OWN_PROFILE)

def test_role_permissions_bot():
    """Test bot has correct permissions."""
    bot = User(username="bot", api_key="key", role=Role.BOT)
    assert bot.has_permission(Permission.SEND_ROOM_MESSAGE)
    assert not bot.has_permission(Permission.SEND_DIRECT_MESSAGE)
```

#### 5.2 Integration Tests for Endpoints

```python
# tests/test_rbac_endpoints.py - NEW FILE

def test_assign_role_as_admin(client, registered_admin, registered_user):
    """Test admin can assign roles."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.patch(
        f"/admin/users/{registered_user['username']}/role",
        json={"role": "viewer"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "viewer"

def test_assign_role_as_non_admin_fails(client, registered_user, registered_user2):
    """Test non-admin cannot assign roles."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        f"/admin/users/{registered_user2['username']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert response.status_code == 403

def test_viewer_cannot_send_dm(client):
    """Test viewer role cannot send direct messages."""
    # Register viewer
    viewer_response = client.post(
        "/register",
        json={"username": "viewer", "viewer": True}
    )
    viewer_api_key = viewer_response.json()["api_key"]

    # Register regular user
    user_response = client.post(
        "/register",
        json={"username": "user"}
    )

    # Try to send DM as viewer
    headers = {"X-API-Key": viewer_api_key}
    response = client.post(
        "/messages",
        json={"content": "DM", "to_username": "user"},
        headers=headers,
    )
    assert response.status_code == 403
    assert "direct message" in response.json()["detail"].lower()

def test_bot_cannot_send_dm(client):
    """Test bot role cannot send direct messages."""
    # Register bot
    bot_response = client.post(
        "/register",
        json={"username": "bot", "bot": True}
    )
    bot_api_key = bot_response.json()["api_key"]
    assert bot_response.json()["role"] == "bot"

    # Register regular user
    client.post("/register", json={"username": "user"})

    # Try to send DM as bot
    headers = {"X-API-Key": bot_api_key}
    response = client.post(
        "/messages",
        json={"content": "DM", "to_username": "user"},
        headers=headers,
    )
    assert response.status_code == 403
```

#### 5.3 Migration Tests

```python
# tests/test_role_migration.py - NEW FILE

def test_migrate_admin_users():
    """Test migration converts admin=True to role=ADMIN."""
    storage = ChatStorage(":memory:")

    # Create old-style admin user
    storage._execute(
        "INSERT INTO users (username, api_key, admin) VALUES (?, ?, ?)",
        ("admin_user", "key123", 1)
    )

    # Run migration
    count = storage.migrate_roles_from_legacy_fields()
    assert count == 1

    # Verify role
    user = storage.get_user_by_username("admin_user")
    assert user.role == Role.ADMIN

def test_migrate_viewer_users():
    """Test migration converts viewer=True to role=VIEWER."""
    # Similar to above

def test_migrate_bot_users():
    """Test migration converts bot=True to role=BOT."""
    # Similar to above

def test_migrate_regular_users():
    """Test migration converts regular users to role=MEMBER."""
    # Similar to above
```

#### 5.4 Update Existing Tests

**Tests to update:**
- `tests/test_api.py` - Update 189 existing tests to work with roles
  - Add `role` field to response checks
  - Update permission error messages
  - Update admin tests to use new permission system

- `tests/test_bots.py` - Update bot-specific tests
  - Verify bot role is assigned correctly
  - Update permission error messages

- `tests/test_viewer.py` - Update viewer tests
  - Verify viewer role is assigned correctly
  - Update permission checks

- `tests/test_auth.py` - Update authentication tests
  - Test role extraction from Stytch
  - Test role syncing

### Phase 6: Documentation
**Status:** Not started
**Risk:** Low
**Time:** 1-2 hours

#### 6.1 Update README.md

```markdown
## Authorization & Roles

The Token Bowl Chat Server uses role-based access control (RBAC) with four roles:

### Roles

- **ADMIN**: Full CRUD access to all resources, can assign roles
- **MEMBER** (default): Can send/receive all messages, update own profile
- **VIEWER**: Read-only access, can send room messages but not DMs
- **BOT**: Automated agents, can send room messages only

### Role Assignment

Roles are automatically assigned during registration:

```bash
# Register as admin
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin_user", "admin": true}'

# Register as viewer
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "viewer_user", "viewer": true}'

# Register as bot
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "bot_user", "bot": true}'
```

### Changing Roles (Admin Only)

Admins can change user roles:

```bash
curl -X PATCH http://localhost:8000/admin/users/username/role \
  -H "X-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "viewer"}'
```

### Permission Matrix

| Action | Admin | Member | Viewer | Bot |
|--------|-------|--------|--------|-----|
| Send room message | ✅ | ✅ | ✅ | ✅ |
| Send direct message | ✅ | ✅ | ❌ | ❌ |
| Read messages | ✅ | ✅ | ✅ | ✅ |
| Update own profile | ✅ | ✅ | ❌ | ✅ |
| Update any user | ✅ | ❌ | ❌ | ❌ |
| Delete users | ✅ | ❌ | ❌ | ❌ |
| Assign roles | ✅ | ❌ | ❌ | ❌ |
| Edit/delete messages | ✅ | ❌ | ❌ | ❌ |

### Stytch Integration

For users authenticated via Stytch, roles are stored in the user's `trusted_metadata`:

```json
{
  "role": "admin"
}
```

Roles are automatically synced between Stytch and the local database.
```

#### 6.2 Update API Documentation

- Update OpenAPI spec generation
- Add role field to all user response examples
- Document permission errors (403 with role info)
- Add role assignment endpoint documentation

#### 6.3 Create Migration Guide

```markdown
# RBAC Migration Guide

## For Existing Deployments

### Step 1: Backup Database
```bash
cp chat.db chat.db.backup
```

### Step 2: Deploy New Code
```bash
git pull
uv pip install -e ".[dev]"
```

### Step 3: Run Migration
```python
from token_bowl_chat_server.storage import storage

# Migrate existing users
count = storage.migrate_roles_from_legacy_fields()
print(f"Migrated {count} users to role-based system")
```

### Step 4: Verify Migration
```bash
# Check a few users
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/users
# Should include "role" field for all users
```

### Step 5: Sync to Stytch (if using Stytch)
```python
# For each Stytch user
for user in storage.get_all_users():
    if user.stytch_user_id:
        await stytch_client.set_user_role(user.stytch_user_id, user.role)
```

## Rollback Plan

If issues arise:

1. Restore database: `cp chat.db.backup chat.db`
2. Revert code: `git revert <commit>`
3. Restart server
```

---

## Risk Assessment

### High Risk Items

1. **Database Migration**
   - **Risk**: Data loss or corruption during schema update
   - **Mitigation**:
     - Automated backup before migration
     - Migration is additive (adds role column, keeps legacy columns)
     - Rollback plan documented

2. **Breaking API Changes**
   - **Risk**: Existing clients break if they rely on boolean fields
   - **Mitigation**:
     - Keep legacy boolean fields populated (via model validator)
     - Add `role` field to responses (additive change)
     - Version API if needed

3. **Permission Logic Errors**
   - **Risk**: Users get wrong permissions or are locked out
   - **Mitigation**:
     - Comprehensive test suite (100+ tests)
     - Conservative permission mapping (when in doubt, deny)
     - Admin role always has all permissions

### Medium Risk Items

1. **Stytch Integration Failures**
   - **Risk**: Stytch API calls fail, roles out of sync
   - **Mitigation**:
     - Local DB is source of truth
     - Graceful fallback if Stytch unavailable
     - Async syncing doesn't block requests

2. **WebSocket Authorization**
   - **Risk**: Real-time permission checks may cause latency
   - **Mitigation**:
     - Permission checks are fast (in-memory lookup)
     - Cache user permissions in WebSocket connection

### Low Risk Items

1. **Documentation Updates**
   - **Risk**: Outdated docs confuse users
   - **Mitigation**: Update docs in same PR as code changes

2. **Test Updates**
   - **Risk**: Tests don't cover all edge cases
   - **Mitigation**: Systematic test review for each role

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing (aim for >90% coverage)
- [ ] Migration tested on copy of production database
- [ ] Stytch custom claims template configured
- [ ] Documentation updated
- [ ] Rollback plan tested

### Deployment Steps

1. [ ] Notify users of upcoming changes
2. [ ] Enable maintenance mode (optional)
3. [ ] Backup database: `cp chat.db chat.db.$(date +%Y%m%d_%H%M%S)`
4. [ ] Deploy new code
5. [ ] Run migration: `storage.migrate_roles_from_legacy_fields()`
6. [ ] Verify migration: Check sample users have roles
7. [ ] Sync roles to Stytch (if applicable)
8. [ ] Run smoke tests
9. [ ] Monitor logs for permission errors
10. [ ] Disable maintenance mode

### Post-Deployment

- [ ] Monitor error rates for 24 hours
- [ ] Verify no 403 permission errors for legitimate users
- [ ] Check Stytch sync working correctly
- [ ] Gather user feedback

### Rollback Procedure (if needed)

1. [ ] Restore database: `cp chat.db.backup chat.db`
2. [ ] Revert code: `git revert <commit-hash>`
3. [ ] Restart server
4. [ ] Notify users
5. [ ] Post-mortem: What went wrong?

---

## Open Questions

1. **Default Role for New Users**
   - Current: MEMBER (can send DMs)
   - Alternative: Start as VIEWER, admin upgrades to MEMBER?
   - **Decision needed:** Keep MEMBER as default

2. **Bot API Key Auth**
   - Bots currently use API keys, not Stytch
   - Should bots be allowed to have Stytch accounts?
   - **Decision needed:** Bots use API keys only

3. **Role Self-Service**
   - Should users be able to request role changes?
   - Or admin-only role assignment?
   - **Decision needed:** Admin-only for now

4. **Backward Compatibility Timeline**
   - How long to keep legacy boolean fields?
   - When to deprecate and remove them?
   - **Proposal:** Keep for 3 months, then remove

5. **Permission Granularity**
   - Current: 11 permissions
   - Future: More granular (per-resource permissions)?
   - **Decision needed:** Current granularity sufficient

---

## Success Metrics

### Technical Metrics
- Zero permission-related bugs in production
- <5ms overhead for permission checks
- 100% role migration success rate
- >90% test coverage

### User Metrics
- No user complaints about access issues
- Admin successfully uses role assignment
- Clear understanding of role permissions

---

## Timeline

**Total Estimate: 8-12 hours**

| Phase | Time | Dependencies |
|-------|------|--------------|
| Phase 1: Storage | 2-3h | None |
| Phase 2: Stytch | 2-3h | Phase 1 |
| Phase 3: Endpoints | 3-4h | Phase 1, 2 |
| Phase 4: WebSocket | 1-2h | Phase 3 |
| Phase 5: Testing | 2-3h | Phase 3, 4 |
| Phase 6: Docs | 1-2h | All phases |

**Recommended Approach:**
- Implement phases 1-2 first, test thoroughly
- Then implement phases 3-4, test thoroughly
- Finally phases 5-6

This allows for checkpoint testing and reduces risk of cascading failures.

---

## Next Steps

**To proceed with implementation:**

1. **Review this plan** - Approve/modify the approach
2. **Answer open questions** - Make decisions on uncertain items
3. **Choose implementation strategy**:
   - Option A: Implement all at once (faster but riskier)
   - Option B: Implement in phases with testing between (slower but safer)
4. **Set go/no-go criteria** - What must pass before deployment?

**Recommended:** Phase-by-phase implementation with testing checkpoints.
