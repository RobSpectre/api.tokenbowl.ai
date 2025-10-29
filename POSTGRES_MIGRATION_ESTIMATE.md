# PostgreSQL Migration Effort Estimate

## Executive Summary

**Total Estimated Effort: 3-4 weeks** (1 developer)
- **Complexity: Medium-High**
- **Risk Level: Medium**
- **Testing Overhead: High**

The Token Bowl Chat Server currently uses SQLite with 118+ raw SQL queries, JSON serialization for arrays, and SQLite-specific migration patterns. The migration to PostgreSQL will require significant changes to the data access layer, migrations, and testing infrastructure.

## Current Architecture Analysis

### SQLite Usage Patterns
1. **Raw SQL Queries**: 118+ cursor.execute() calls with handwritten SQL
2. **JSON Storage**: Arrays (message_ids) stored as JSON strings in TEXT columns
3. **In-Memory Testing**: Tests use SQLite `:memory:` databases for speed
4. **Connection Management**: Dual pattern - persistent for in-memory, temporary for file-based
5. **SQLite-Specific Migrations**: 6 migrations with SQLite workarounds for schema changes

### Key SQLite-Specific Features in Use
- TEXT data type for all non-boolean fields
- INTEGER for booleans (viewer, admin, bot flags)
- JSON serialization for list fields
- Manual foreign key cascades in some places
- Table recreation for ALTER TABLE operations (no DROP COLUMN support)
- sqlite3.Row for dictionary-like result access

## Migration Tasks Breakdown

### 1. Database Driver & Connection Management (3-4 days)
- [ ] Add psycopg3 or asyncpg dependency
- [ ] Create PostgreSQL connection pool
- [ ] Implement async/await pattern for all DB operations
- [ ] Update connection string configuration
- [ ] Add SSL/TLS support for production connections
- [ ] Environment-based configuration (dev/test/prod)

**Key Changes:**
- Replace `sqlite3` with `psycopg3` or `asyncpg`
- Replace synchronous operations with async
- Implement proper connection pooling
- Add retry logic for transient failures

### 2. Schema Migration (4-5 days)
- [ ] Convert data types:
  - TEXT → VARCHAR/TEXT with proper constraints
  - INTEGER (for booleans) → BOOLEAN
  - TEXT (for UUIDs) → UUID native type
  - TEXT (for timestamps) → TIMESTAMPTZ
  - JSON strings → JSONB columns
- [ ] Add proper indexes for JSONB fields
- [ ] Update all foreign key constraints
- [ ] Add check constraints where appropriate
- [ ] Create new Alembic migration branch for PostgreSQL

**Specific Schema Changes:**
```sql
-- Example conversions needed
-- SQLite:
message_ids TEXT NOT NULL  -- JSON string

-- PostgreSQL:
message_ids JSONB NOT NULL DEFAULT '[]'::jsonb
```

### 3. Query Conversion (5-6 days)
- [ ] Convert all 118+ SQL queries to PostgreSQL syntax
- [ ] Replace JSON string operations with JSONB operators
- [ ] Update parameter placeholders (? → %s or $1, $2...)
- [ ] Convert datetime handling (TEXT → TIMESTAMPTZ operations)
- [ ] Update LIMIT/OFFSET syntax where needed
- [ ] Convert boolean comparisons (0/1 → true/false)
- [ ] Add RETURNING clauses for INSERT/UPDATE operations

**High-Impact Query Changes:**
```python
# SQLite (current)
cursor.execute("SELECT * FROM users WHERE admin = 1")

# PostgreSQL (new)
cursor.execute("SELECT * FROM users WHERE admin = true")
```

```python
# SQLite JSON handling (current)
message_ids_json = json.dumps([str(msg_id) for msg_id in conversation.message_ids])

# PostgreSQL JSONB (new)
# Direct array insertion without JSON serialization
```

### 4. Storage Layer Refactoring (3-4 days)
- [ ] Abstract database operations into a proper repository pattern
- [ ] Create database-agnostic interfaces
- [ ] Implement PostgreSQL-specific storage class
- [ ] Add transaction management
- [ ] Implement proper error handling for PostgreSQL-specific errors
- [ ] Add query logging and performance monitoring

### 5. Testing Infrastructure (2-3 days)
- [ ] Set up PostgreSQL test containers (testcontainers-python)
- [ ] Replace in-memory SQLite with PostgreSQL test databases
- [ ] Update fixtures for PostgreSQL
- [ ] Add integration tests for PostgreSQL-specific features
- [ ] Performance testing setup
- [ ] Migration testing (SQLite → PostgreSQL data migration)

### 6. Migration Tooling (2-3 days)
- [ ] Create data migration script (SQLite → PostgreSQL)
- [ ] Handle UUID conversions
- [ ] Convert JSON strings to JSONB
- [ ] Preserve all timestamps and relationships
- [ ] Add verification/checksum validation
- [ ] Create rollback procedures

### 7. Deployment & DevOps (2-3 days)
- [ ] Update Docker configuration
- [ ] Add PostgreSQL to docker-compose
- [ ] Update CI/CD pipelines
- [ ] Create database backup strategies
- [ ] Set up monitoring and alerts
- [ ] Update deployment documentation

## Risk Assessment

### High-Risk Areas
1. **Data Type Mismatches**: UUID and timestamp handling differences
2. **JSON Operations**: Significant query rewrites needed for JSONB
3. **Transaction Semantics**: PostgreSQL's MVCC vs SQLite's locking
4. **Performance**: Query optimization will be needed
5. **Testing**: In-memory SQLite tests are much faster than PostgreSQL

### Medium-Risk Areas
1. **Alembic Migrations**: Need parallel migration paths
2. **Connection Management**: More complex than SQLite
3. **Error Handling**: Different error codes and behaviors
4. **Concurrent Access**: Different isolation levels

## Effort Timeline

### Week 1: Foundation
- Database driver setup
- Connection management
- Basic PostgreSQL schema creation
- Development environment setup

### Week 2: Core Migration
- Query conversion (50%)
- Storage layer abstraction
- Testing infrastructure setup

### Week 3: Completion & Testing
- Remaining query conversions
- Data migration tooling
- Integration testing
- Performance testing

### Week 4: Production Readiness
- Deployment setup
- Monitoring and alerting
- Documentation
- Production data migration testing
- Rollback procedures

## Alternative Approaches

### 1. Use SQLAlchemy ORM (4-5 weeks)
- **Pros**: Database-agnostic, easier maintenance, built-in migrations
- **Cons**: Major refactor, performance overhead, learning curve
- **Additional Effort**: +1 week for ORM conversion

### 2. Dual Database Support (5-6 weeks)
- **Pros**: Gradual migration, rollback capability
- **Cons**: Complex codebase, double maintenance
- **Additional Effort**: +2 weeks for abstraction layer

### 3. Minimal Migration (2-3 weeks)
- **Approach**: Keep SQLite patterns, use PostgreSQL in SQLite-compatibility mode
- **Pros**: Faster initial migration
- **Cons**: Doesn't leverage PostgreSQL features, technical debt

## Recommendations

1. **Start with abstraction layer**: Create repository pattern first
2. **Use SQLAlchemy Core** (not ORM): Middle ground for SQL control with abstraction
3. **Implement feature flags**: Allow gradual rollout
4. **Set up PostgreSQL locally first**: Develop alongside SQLite
5. **Create comprehensive test suite**: Before starting migration
6. **Consider managed PostgreSQL**: (AWS RDS, Supabase) for production

## Cost-Benefit Analysis

### Benefits
- **Performance**: Better concurrent access, query optimization
- **Scalability**: Can handle much larger datasets
- **Features**: JSONB, full-text search, advanced indexing
- **Production-Ready**: Better for cloud deployment
- **Type Safety**: Native UUID, timestamp types

### Costs
- **Development Time**: 3-4 weeks
- **Complexity**: More complex deployment and maintenance
- **Performance Testing**: Need load testing
- **Infrastructure**: PostgreSQL hosting costs
- **Learning Curve**: Team needs PostgreSQL expertise

## Conclusion

The migration from SQLite to PostgreSQL is a **significant undertaking** that will require approximately **3-4 weeks of dedicated development time**. The primary challenges are:

1. Converting 118+ raw SQL queries
2. Handling JSON to JSONB migration
3. Updating the testing infrastructure
4. Managing the production data migration

The effort is justified if you need:
- High concurrent user load
- Advanced querying capabilities
- Production-grade deployment
- Better data integrity guarantees

However, SQLite may be sufficient if:
- User load is moderate (<100 concurrent)
- Deployment is single-server
- Simplicity is valued over features