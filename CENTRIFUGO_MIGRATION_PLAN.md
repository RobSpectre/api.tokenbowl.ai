# Centrifugo Migration Plan

## Overview
Migrate from custom WebSocket implementation to Centrifugo for improved scalability, reliability, and maintainability.

**Timeline:** ~2 weeks
**Risk Level:** Medium (comprehensive rollback strategy in place)
**Downtime Required:** Zero

---

## Architecture

### Current State
```
Clients (Python SDK, Vue apps)
    ↓ WebSocket (/ws)
FastAPI Server (custom WebSocket manager)
    ↓
SQLite Database
```

### Target State
```
Clients (Python SDK, Vue apps)
    ↓ WebSocket
Centrifugo Server (connection management)
    ↑ HTTP API (publish)
FastAPI Server (REST + publish to Centrifugo)
    ↓
SQLite Database
```

### What Changes
- ❌ **Remove:** Custom WebSocket endpoint `/ws`, `websocket.py`, `websocket_heartbeat.py`
- ✅ **Add:** Centrifugo server, publish-only integration
- ✅ **Keep:** All REST endpoints, webhooks, auth, storage (100% unchanged)

### What Stays The Same
- ✅ REST API endpoints (`POST /messages`, `GET /messages`, etc.)
- ✅ Webhooks (still delivered exactly as before)
- ✅ Authentication (API keys and Stytch)
- ✅ Database schema and storage
- ✅ Message history and read receipts

---

## Projects to Update

| Project | Type | Current Version | Target Version | WebSocket Usage |
|---------|------|----------------|----------------|-----------------|
| **token_bowl_chat_server** | FastAPI Backend | v1.1.5 | v2.0.0 | Provides /ws endpoint |
| **token-bowl-chat** | Python SDK | v2.1.1 | v3.0.0 → v4.0.0 | `websockets` library |
| **chat.tokenbowl.ai** | Vue 3 Frontend | v1.7.0 | v1.8.0 → v2.0.0 | Native WebSocket |
| **tokenbowl.ai** | Vue 3 Site | v1.0.3 | v1.0.4 → v1.1.0 | Native WebSocket |

---

## Phase 0: Preparation (Day 1)

### Goals
- Set up Centrifugo locally
- Document current behavior
- Create migration branches

### Tasks

#### 0.1: Create Migration Branches
```bash
# In each repo
git checkout -b feature/centrifugo-migration
git push -u origin feature/centrifugo-migration
```

#### 0.2: Document Current Protocol
Document all WebSocket message types currently used:
- `{"type": "message", "content": "...", "to_username": "..."}`
- `{"type": "ping"}` / `{"type": "pong"}`
- `{"type": "mark_read", "message_id": "..."}`
- `{"type": "get_messages", "limit": 50}`
- etc.

**Location:** `docs/WEBSOCKET_PROTOCOL.md`

#### 0.3: Set Up Local Centrifugo
```bash
cd token_bowl_chat_server
# Add docker-compose.yml with Centrifugo service
# Add centrifugo-config.json
docker-compose up -d centrifugo
```

**Deliverables:**
- [ ] All 4 repos have migration branches
- [ ] WebSocket protocol documented
- [ ] Centrifugo running locally
- [ ] Tested sending a message through Centrifugo HTTP API

---

## Phase 1: Server - Dual Mode (Days 2-4)

### Goals
- Add Centrifugo support WITHOUT breaking existing clients
- Both old `/ws` and new Centrifugo work simultaneously
- Deploy to production safely

### Tasks

#### 1.1: Add Centrifugo Dependencies
**File:** `pyproject.toml`
```toml
dependencies = [
    # ... existing ...
    "cent>=5.0.0",
    "pyjwt>=2.8.0",
]
```

#### 1.2: Add Configuration
**File:** `src/token_bowl_chat_server/config.py`
```python
# Centrifugo Configuration
ENABLE_CENTRIFUGO: bool = os.getenv("ENABLE_CENTRIFUGO", "false").lower() == "true"
CENTRIFUGO_API_URL: str = os.getenv("CENTRIFUGO_API_URL", "http://localhost:8001/api")
CENTRIFUGO_API_KEY: str = os.getenv("CENTRIFUGO_API_KEY", "")
CENTRIFUGO_TOKEN_SECRET: str = os.getenv("CENTRIFUGO_TOKEN_SECRET", "")
CENTRIFUGO_WS_URL: str = os.getenv("CENTRIFUGO_WS_URL", "ws://localhost:8001/connection/websocket")
```

#### 1.3: Create Centrifugo Client
**File:** `src/token_bowl_chat_server/centrifugo_client.py` (new)
- `class CentrifugoClient`
- `generate_connection_token(user: User) -> str`
- `publish_room_message(message: Message, from_user: User)`
- `publish_direct_message(message: Message, from_user: User, to_user: User)`

#### 1.4: Add Connection Token Endpoint
**File:** `src/token_bowl_chat_server/api.py`
```python
@router.get("/centrifugo/connection-token")
async def get_centrifugo_connection_token(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get JWT token and info for connecting to Centrifugo."""
    # ...
```

#### 1.5: Dual-Publish Messages
**File:** `src/token_bowl_chat_server/api.py`

Update `POST /messages` to publish to BOTH:
```python
# Store in database
storage.add_message(message)

# Publish to OLD WebSocket clients
await connection_manager.broadcast_to_room(message, exclude_username=sender)

# Publish to NEW Centrifugo clients (if enabled)
if settings.ENABLE_CENTRIFUGO:
    centrifugo = get_centrifugo_client()
    await centrifugo.publish_room_message(message, current_user)
```

#### 1.6: Write Tests
**File:** `tests/test_centrifugo.py` (new)
- Test connection token generation
- Test publishing to Centrifugo
- Test with ENABLE_CENTRIFUGO=false (should not break)
- Test with ENABLE_CENTRIFUGO=true

#### 1.7: Update docker-compose
**File:** `docker-compose.yml` (new)
```yaml
services:
  centrifugo:
    image: centrifugo/centrifugo:v5
    ports:
      - "8001:8000"
    volumes:
      - ./centrifugo-config.json:/centrifugo/config.json
    command: centrifugo -c config.json
```

#### 1.8: Local Testing
```bash
# Terminal 1: Start Centrifugo
docker-compose up centrifugo

# Terminal 2: Start FastAPI with Centrifugo disabled
ENABLE_CENTRIFUGO=false python -m token_bowl_chat_server

# Terminal 3: Test old WebSocket client still works
python examples/websocket_client.py

# Terminal 4: Start FastAPI with Centrifugo enabled
ENABLE_CENTRIFUGO=true python -m token_bowl_chat_server

# Terminal 5: Test new Centrifugo client (once SDK is updated)
```

#### 1.9: Production Deployment
```bash
# Deploy server v1.2.0
git tag v1.2.0
git push --tags

# On production server
cd /opt/api.tokenbowl.ai
git pull origin main
./deployment/deploy.sh

# Centrifugo NOT enabled yet (ENABLE_CENTRIFUGO=false)
```

**Deliverables:**
- [ ] Server can publish to both old and new protocols
- [ ] New endpoint `/centrifugo/connection-token` works
- [ ] All 268 tests still pass
- [ ] Deployed to production with Centrifugo disabled
- [ ] Old clients still working perfectly

**Rollback Strategy:**
If anything breaks, simply keep `ENABLE_CENTRIFUGO=false` and nothing changes.

---

## Phase 2: Python SDK - Dual Mode (Days 5-7)

### Goals
- Add Centrifugo support to Python SDK
- Keep old WebSocket working
- Publish new version to PyPI

### Tasks

#### 2.1: Add Dependencies
**File:** `token-bowl-chat/pyproject.toml`
```toml
dependencies = [
    # ... existing ...
    "centrifuge>=0.1.0",  # Centrifugo Python SDK
]
```

#### 2.2: Create Centrifugo WebSocket Client
**File:** `token-bowl-chat/src/token_bowl_chat/centrifugo_websocket.py` (new)
```python
from centrifuge import Client

class CentrifugoWebSocket:
    """WebSocket client using Centrifugo protocol."""

    def __init__(self, *, api_key: str, base_url: str = "https://api.tokenbowl.ai"):
        # Get connection token from server
        # Connect to Centrifugo
        # Subscribe to channels
```

#### 2.3: Update Main Client with Feature Flag
**File:** `token-bowl-chat/src/token_bowl_chat/client.py`
```python
class TokenBowlChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tokenbowl.ai",
        use_centrifugo: bool = False,  # NEW FLAG
    ):
        if use_centrifugo:
            self.ws_client = CentrifugoWebSocket(api_key=api_key, base_url=base_url)
        else:
            self.ws_client = TokenBowlWebSocket(api_key=api_key, base_url=base_url)
```

#### 2.4: Update Examples
**File:** `token-bowl-chat/examples/websocket_client.py`
```python
# Show both ways
async def main_legacy():
    """Using old WebSocket protocol."""
    client = TokenBowlChatClient(api_key="...", use_centrifugo=False)

async def main_centrifugo():
    """Using new Centrifugo protocol."""
    client = TokenBowlChatClient(api_key="...", use_centrifugo=True)
```

#### 2.5: Write Tests
**File:** `token-bowl-chat/tests/test_centrifugo_client.py`
- Test Centrifugo connection
- Test sending messages
- Test receiving messages
- Test reconnection

#### 2.6: Update Documentation
**File:** `token-bowl-chat/README.md`
```markdown
## Migration to Centrifugo

Version 3.0.0 introduces support for Centrifugo. The old WebSocket protocol still works.

### New (Recommended)
```python
client = TokenBowlChatClient(api_key="...", use_centrifugo=True)
```

### Legacy (Still Supported)
```python
client = TokenBowlChatClient(api_key="...", use_centrifugo=False)
```

#### 2.7: Publish to PyPI
```bash
cd token-bowl-chat
# Update version to 3.0.0 in pyproject.toml
git tag v3.0.0
git push --tags
# GitHub Actions auto-publishes to PyPI
```

**Deliverables:**
- [ ] Python SDK v3.0.0 published to PyPI
- [ ] Both protocols work
- [ ] Examples updated
- [ ] Tests pass for both modes
- [ ] Migration guide in README

**Rollback Strategy:**
Users can stay on v2.1.1 or use `use_centrifugo=False` in v3.0.0.

---

## Phase 3: Vue Frontends - Dual Mode (Days 8-10)

### Goals
- Add Centrifugo support to both Vue apps
- Feature flag to switch protocols
- Deploy with Centrifugo disabled by default

### Tasks (chat.tokenbowl.ai)

#### 3.1: Add Dependencies
```bash
cd chat.tokenbowl.ai
npm install centrifuge
```

#### 3.2: Create Centrifugo Store
**File:** `src/stores/centrifugo.js` (new)
```javascript
import { defineStore } from 'pinia'
import { Centrifuge } from 'centrifuge'
import apiClient from '../api/client'

export const useCentrifugoStore = defineStore('centrifugo', {
  state: () => ({
    client: null,
    connected: false,
    messages: []
  }),

  actions: {
    async connect() {
      // Get connection token from server
      const response = await apiClient.getCentrifugoConnectionToken()

      // Connect to Centrifugo
      this.client = new Centrifuge(response.url, {
        token: response.token
      })

      // Subscribe to channels
      this.client.on('connected', () => {
        this.connected = true
      })

      await this.client.connect()
    }
  }
})
```

#### 3.3: Add Feature Flag
**File:** `.env`
```
VITE_USE_CENTRIFUGO=false
```

**File:** `src/main.js`
```javascript
const useCentrifugo = import.meta.env.VITE_USE_CENTRIFUGO === 'true'

if (useCentrifugo) {
  // Use Centrifugo store
  const centrifugo = useCentrifugoStore()
  centrifugo.connect()
} else {
  // Use old WebSocket store
  const websocket = useWebSocketStore()
  websocket.connect()
}
```

#### 3.4: Test Locally
```bash
# Test with old protocol
VITE_USE_CENTRIFUGO=false npm run dev

# Test with new protocol
VITE_USE_CENTRIFUGO=true npm run dev
```

#### 3.5: Deploy
```bash
# Deploy v1.8.0 with Centrifugo disabled
npm run build
# Deploy to hosting
```

### Tasks (tokenbowl.ai)
Repeat similar steps for the main site's Chat.vue page.

**Deliverables:**
- [ ] chat.tokenbowl.ai v1.8.0 deployed (Centrifugo support, disabled)
- [ ] tokenbowl.ai v1.0.4 deployed (Centrifugo support, disabled)
- [ ] Both protocols tested and working
- [ ] Feature flags in place

**Rollback Strategy:**
Keep `VITE_USE_CENTRIFUGO=false` if issues arise.

---

## Phase 4: Production Cutover (Days 11-12)

### Goals
- Enable Centrifugo in production
- Monitor for issues
- Update bot clients

### Tasks

#### 4.1: Deploy Centrifugo to Production
```bash
# On production server (/opt/api.tokenbowl.ai)
cd /opt/api.tokenbowl.ai

# Install Centrifugo
wget https://github.com/centrifugal/centrifugo/releases/download/v5.0.0/centrifugo_5.0.0_linux_amd64.tar.gz
tar -xvzf centrifugo_5.0.0_linux_amd64.tar.gz
sudo mv centrifugo /usr/local/bin/

# Add supervisor config
sudo vi /etc/supervisor/conf.d/centrifugo.conf

# Start Centrifugo
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start infra:centrifugo
```

**File:** `/etc/supervisor/conf.d/centrifugo.conf`
```ini
[program:centrifugo]
command=/usr/local/bin/centrifugo -c /opt/api.tokenbowl.ai/centrifugo-config.json
directory=/opt/api.tokenbowl.ai
autostart=true
autorestart=true
stderr_logfile=/var/log/centrifugo/centrifugo.err.log
stdout_logfile=/var/log/centrifugo/centrifugo.out.log
```

#### 4.2: Enable Centrifugo on Server
```bash
# Set environment variable
echo "export ENABLE_CENTRIFUGO=true" >> /opt/api.tokenbowl.ai/.env

# Restart server
sudo supervisorctl restart infra:api.tokenbowl.ai
```

#### 4.3: Enable in Frontends
```bash
# chat.tokenbowl.ai
# Update .env.production
VITE_USE_CENTRIFUGO=true

# Rebuild and deploy
npm run build
# Deploy

# tokenbowl.ai - same process
```

#### 4.4: Update Bot Clients
Update all running bots to use new SDK:
```bash
# Update package
pip install --upgrade token-bowl-chat

# Update code
# OLD: client = TokenBowlChatClient(api_key="...")
# NEW: client = TokenBowlChatClient(api_key="...", use_centrifugo=True)

# Restart bots
```

#### 4.5: Monitor Production
- Check Centrifugo logs: `sudo tail -f /var/log/centrifugo/*.log`
- Check FastAPI logs: `sudo tail -f /var/log/api.tokenbowl.ai/*.log`
- Monitor connections: `curl http://localhost:8001/connection/info`
- Check message delivery in web UI
- Verify bots are sending/receiving

#### 4.6: 24-Hour Monitoring Period
- Monitor error rates
- Check message delivery success rate
- Verify no memory leaks
- Confirm heartbeats working
- Check reconnection handling

**Deliverables:**
- [ ] Centrifugo running in production
- [ ] All clients using Centrifugo
- [ ] Old /ws endpoint still available (but unused)
- [ ] No errors in 24 hours
- [ ] Performance equal or better

**Rollback Strategy:**
```bash
# If issues, disable Centrifugo immediately:
echo "export ENABLE_CENTRIFUGO=false" >> /opt/api.tokenbowl.ai/.env
sudo supervisorctl restart infra:api.tokenbowl.ai

# Frontends: Set VITE_USE_CENTRIFUGO=false and redeploy
# Bots: use_centrifugo=False
```

---

## Phase 5: Cleanup (Days 13-14)

### Goals
- Remove old WebSocket code
- Make Centrifugo mandatory
- Breaking change releases

### Tasks

#### 5.1: Server Cleanup
```python
# Delete files:
# - src/token_bowl_chat_server/websocket.py
# - src/token_bowl_chat_server/websocket_heartbeat.py

# Remove from api.py:
# - @router.websocket("/ws") endpoint
# - All connection_manager imports and usage

# Remove from config.py:
# - ENABLE_CENTRIFUGO flag

# Update tests to only test Centrifugo
```

**Deploy:** v2.0.0 (breaking change)

#### 5.2: Python SDK Cleanup
```python
# Delete: src/token_bowl_chat/websocket_client.py
# Remove: use_centrifugo parameter (always True)
# Remove: websockets dependency

# Update client.py:
class TokenBowlChatClient:
    def __init__(self, api_key: str, base_url: str):
        # Always use Centrifugo
        self.ws_client = CentrifugoWebSocket(...)
```

**Deploy:** v4.0.0 (breaking change)

#### 5.3: Frontend Cleanup
```javascript
// Delete: src/stores/websocket.js
// Delete: src/composables/useWebSocket.js
// Remove: VITE_USE_CENTRIFUGO flag

// Update: Always use Centrifugo store
```

**Deploy:** chat.tokenbowl.ai v2.0.0, tokenbowl.ai v1.1.0

#### 5.4: Update Documentation
- README.md in all repos
- API documentation
- Examples
- Migration guides (archive old protocol docs)

**Deliverables:**
- [ ] All old WebSocket code removed
- [ ] Breaking change versions deployed
- [ ] Documentation updated
- [ ] Migration complete ✅

---

## Testing Checklist

### Functionality Tests
- [ ] Send room message via REST → received via WebSocket
- [ ] Send direct message via REST → received by recipient
- [ ] WebSocket send message → stored in database
- [ ] Read receipts work
- [ ] Unread count accurate
- [ ] Message history pagination works
- [ ] User presence/online status
- [ ] Reconnection after disconnect
- [ ] Multiple connections per user
- [ ] Webhooks still delivered

### Performance Tests
- [ ] Message latency < 100ms (same as before)
- [ ] Can handle 100+ concurrent connections
- [ ] Memory usage stable over 24 hours
- [ ] No connection leaks

### Security Tests
- [ ] Authentication required for WebSocket
- [ ] JWT tokens expire correctly
- [ ] Can't connect without valid token
- [ ] Can't subscribe to other users' channels

---

## Rollback Strategy

### Immediate Rollback (< 1 hour)
**If:** Critical issues discovered immediately after cutover
**Action:**
```bash
# Server
export ENABLE_CENTRIFUGO=false
sudo supervisorctl restart infra:api.tokenbowl.ai

# Frontends
VITE_USE_CENTRIFUGO=false
# Rebuild and redeploy

# Bots
use_centrifugo=False
# Restart
```

### Phase Rollback (< 1 day)
**If:** Issues found during monitoring period
**Action:**
- Revert to previous versions (v1.1.5, v2.1.1, v1.7.0, v1.0.3)
- Keep migration branches for future retry
- Analyze logs to fix issues

### Full Rollback (< 1 week)
**If:** Fundamental issues with Centrifugo approach
**Action:**
- Delete migration branches
- Stick with custom WebSocket implementation
- Consider alternative approaches (Socket.IO, Redis)

---

## Success Metrics

### Technical Metrics
- ✅ Zero downtime during migration
- ✅ All 268+ tests passing
- ✅ Message delivery success rate > 99.9%
- ✅ WebSocket latency < 100ms
- ✅ Connection stability > 99%

### Code Quality Metrics
- ✅ Remove ~500 lines of custom WebSocket code
- ✅ Reduce maintenance burden
- ✅ Better test coverage

### Business Metrics
- ✅ No user complaints
- ✅ Improved reliability
- ✅ Easier horizontal scaling

---

## Timeline Summary

| Phase | Duration | Risk | Can Rollback? |
|-------|----------|------|---------------|
| 0. Preparation | 1 day | Low | N/A |
| 1. Server Dual Mode | 3 days | Low | ✅ Yes |
| 2. Python SDK Dual Mode | 3 days | Low | ✅ Yes |
| 3. Vue Frontends Dual Mode | 3 days | Low | ✅ Yes |
| 4. Production Cutover | 2 days | Medium | ✅ Yes |
| 5. Cleanup | 2 days | Low | ⚠️ Partial |
| **Total** | **14 days** | **Low** | **Until Phase 5** |

---

## Communication Plan

### Week 1 (Phases 0-2)
- **Audience:** Development team only
- **Message:** "Adding Centrifugo support, no user impact"

### Week 2 (Phase 3)
- **Audience:** Bot operators
- **Message:** "Update token-bowl-chat to v3.0.0, set use_centrifugo=True"
- **Timeline:** "Migration on [DATE]"

### Migration Day (Phase 4)
- **Audience:** All users
- **Message:** "WebSocket infrastructure upgrade in progress"
- **Channel:** Status page, Discord/Slack

### Post-Migration
- **Audience:** All users
- **Message:** "Migration complete, improved reliability"
- **Blog Post:** Technical details of migration

---

## Questions to Answer Before Starting

1. **How many active bots are running?**
   - Need to coordinate updates with owners

2. **What's the production server setup?**
   - Confirmed: Supervisor at /opt/api.tokenbowl.ai
   - Need: Access to deploy Centrifugo

3. **Where are frontends deployed?**
   - Need deployment access for both Vue apps

4. **Do we have a staging environment?**
   - If not, local testing is critical

5. **What's the rollback time requirement?**
   - Assuming < 5 minutes for emergency rollback

6. **Who needs to approve this migration?**
   - Get sign-off before Phase 4 cutover

---

## Next Steps

1. **Review this plan** with the team
2. **Answer questions above**
3. **Set migration date** (2 weeks from start)
4. **Create GitHub Project** to track progress
5. **Begin Phase 0** when approved

---

**Last Updated:** 2025-11-01
**Owner:** Development Team
**Reviewers:** TBD
