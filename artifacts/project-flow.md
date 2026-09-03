# Enterprise Security Findings Connector - Complete System Flow

> A single, comprehensive flow showing how everything works together from user query to database response

---

## The Complete Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          👤 SECURITY ENGINEER                                │
│                                                                              │
│  Natural language question:                                                 │
│  "Show me all critical open findings for the Payment API, and mark          │
│   finding find-0005 as resolved"                                            │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Human query (natural language)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          🤖 GEMINI AI (Google)                               │
│                                                                              │
│  Step 1: Parse Natural Language                                             │
│  ├─ Understands: User wants to query AND update                             │
│  ├─ Identifies: 2 operations needed                                         │
│  └─ Selects appropriate MCP tools                                           │
│                                                                              │
│  Step 2: Plan Tool Execution                                                │
│  ├─ Tool 1: get_security_findings()                                         │
│  │   ├─ project_id: "payment-api-prod"                                     │
│  │   ├─ severity: "CRITICAL"                                                │
│  │   └─ status: "OPEN"                                                      │
│  │                                                                           │
│  └─ Tool 2: update_finding_status()                                         │
│      ├─ finding_id: "find-0001-crit-sql-inject"                            │
│      └─ status: "IN_PROGRESS"                                               │
│                                                                              │
│  Note: Discovery Engine adds its OIDC token in HTTP headers                 │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ MCP tool calls (JSON-RPC)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    🔌 MCP SERVER (FastMCP - app/mcp/tools.py)                │
│                                                                              │
│  Transport Layer:                                                           │
│  └─ Production: MCP JSON-RPC over HTTPS to Cloud Run POST /mcp              │
│                                                                              │
│  Authentication:                                                            │
│  └─ Discovery Engine service account OIDC token in x-serverless-authorization│
│                                                                              │
│  Tool Registry (5 tools available):                                         │
│  ├─ ✓ get_security_findings     ← Called first                             │
│  ├─   get_finding_details                                                   │
│  ├─   get_security_summary                                                  │
│  ├─ ✓ update_finding_status     ← Called second                            │
│  └─   get_finding_audit_history                                            │
│                                                                              │
│  Each tool receives: parameters + JWT token                                 │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Tool invocation with JWT
                                   ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║                     🔒 SECURITY BOUNDARY LAYER                               ║
║                                                                              ║
║  ┌────────────────────────────────────────────────────────────────────┐    ║
║  │  STEP A: JWT EXTRACTION (app/main.py)                              │    ║
║  │                                                                     │    ║
║  │  Header: x-serverless-authorization: bearer eyJhbGci...            │    ║
║  │                                                                     │    ║
║  │  1. Check x-serverless-authorization header (Discovery Engine)     │    ║
║  │  2. Fallback to Authorization header if not found                  │    ║
║  │  3. Decode JWT (Google-signed OIDC token)                          │    ║
║  │     └─ No signature verification - trust Discovery Engine          │    ║
║  │  4. Extract email from JWT claims                                  │    ║
║  │     └─ email: "service-PROJECT_ID@gcp-sa-discoveryengine..."       │    ║
║  │  5. Fallback: If no auth found, use demo@example.com (demo mode)   │    ║
║  │                                                                     │    ║
║  │  Result: Email extracted from token                                │    ║
║  └────────────────────────────────────────────────────────────────────┘    ║
║                                   │                                          ║
║                                   │ Service account email                    ║
║                                   ▼                                          ║
║  ┌────────────────────────────────────────────────────────────────────┐    ║
║  │  STEP B: ROLE RESOLUTION (app/auth/email_role.py)                  │    ║
║  │                                                                     │    ║
║  │  Read USER_ROLE_MAP from Secret Manager:                           │    ║
║  │  connector-user-role-map:                                          │    ║
║  │    service-PROJECT_ID@gcp-sa-discoveryengine...:SECURITY_ADMIN,    │    ║
║  │    admin@company.com:SECURITY_ADMIN,                               │    ║
║  │    engineer@company.com:SECURITY_ENGINEER                          │    ║
║  │                                                                     │    ║
║  │  Lookup email in map:                                              │    ║
║  │  └─ service-PROJECT_ID@... → SECURITY_ADMIN ✓                      │    ║
║  │                                                                     │    ║
║  │  Create synthetic User object:                                     │    ║
║  │  ├─ email: service-PROJECT_ID@gcp-sa-discoveryengine...            │    ║
║  │  ├─ role: SECURITY_ADMIN                                           │    ║
║  │  └─ user_id: email (no DB lookup needed)                           │    ║
║  │                                                                     │    ║
║  │  Result: User object with SECURITY_ADMIN role                      │    ║
║  └────────────────────────────────────────────────────────────────────┘    ║
║                                   │                                          ║
║                                   │ User object with Role                    ║
║                                   ▼                                          ║
║  ┌────────────────────────────────────────────────────────────────────┐    ║
║  │  STEP C: RBAC AUTHORIZATION (app/services/authorization_service.py)│    ║
║  │                                                                     │    ║
║  │  Operation 1: get_security_findings()                              │    ║
║  │  ├─ Required permission: "read_finding"                            │    ║
║  │  ├─ User role: SECURITY_ADMIN (Discovery Engine SA)                │    ║
║  │  └─ Check: ✓ SECURITY_ADMIN has read permission                    │    ║
║  │                                                                     │    ║
║  │  Operation 2: update_finding_status()                              │    ║
║  │  ├─ Required permission: "update_finding"                          │    ║
║  │  ├─ User role: SECURITY_ADMIN (Discovery Engine SA)                │    ║
║  │  └─ Check: ✓ SECURITY_ADMIN has update permission                  │    ║
║  │                                                                     │    ║
║  │  RBAC Permission Matrix:                                           │    ║
║  │  ┌──────────────────┬──────────┬──────────┬──────────┐             │    ║
║  │  │ Role             │ Read     │ Update   │ Audit    │             │    ║
║  │  ├──────────────────┼──────────┼──────────┼──────────┤             │    ║
║  │  │ VIEWER           │ ✓        │ ✗        │ ✓        │             │    ║
║  │  │ SECURITY_ENGINEER│ ✓        │ ✓        │ ✓        │             │    ║
║  │  │ SECURITY_ADMIN   │ ✓        │ ✓        │ ✓        │ ← Disc Eng  │    ║
║  │  └──────────────────┴──────────┴──────────┴──────────┘             │    ║
║  │                                                                     │    ║
║  │  Result: ✓ Discovery Engine SA authorized for all operations       │    ║
║  └────────────────────────────────────────────────────────────────────┘    ║
╚═════════════════════════════════════════════════════════════════════════════╝
                                   │
                                   │ Authorized user + operation
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              💼 SERVICE LAYER (app/services/finding_service.py)              │
│                                                                              │
│  ═══════════════════════ OPERATION 1: GET FINDINGS ══════════════════════  │
│                                                                              │
│  FindingService.get_findings()                                              │
│  ├─ Parameters received:                                                    │
│  │   ├─ project_id: "proj-payment-0000-0000-000000000001"                  │
│  │   ├─ severity: "CRITICAL"                                                │
│  │   ├─ status: "OPEN"                                                      │
│  │   └─ limit: 50 (default, clamped to [1, 200])                           │
│  │                                                                           │
│  ├─ Business Logic:                                                         │
│  │   ├─ Validate severity enum at MCP boundary (CRITICAL is valid ✓)       │
│  │   │   Invalid → returns {error: "Invalid severity..."} to Gemini         │
│  │   ├─ Validate status enum at MCP boundary (OPEN is valid ✓)             │
│  │   │   Invalid → returns {error: "Invalid status..."} to Gemini           │
│  │   ├─ Validate scan_type enum at MCP boundary                            │
│  │   └─ Clamp limit to safe range [1, 200]                                 │
│  │                                                                           │
│  └─ Call repository layer for data access                                   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Query parameters
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│           🗄️  REPOSITORY LAYER (app/repositories/finding_repository.py)     │
│                                                                              │
│  FindingRepository.list_findings()                                          │
│  ├─ Build SQLAlchemy query:                                                 │
│  │   SELECT f.*, p.name as project_name                                    │
│  │   FROM findings f                                                        │
│  │   JOIN projects p ON f.project_id = p.id                                │
│  │   WHERE f.project_id = :project_id                                      │
│  │     AND f.severity = :severity                                          │
│  │     AND f.status = :status                                              │
│  │   ORDER BY f.created_at DESC                                            │
│  │   LIMIT :limit                                                           │
│  │                                                                           │
│  └─ Execute async query via asyncpg driver                                  │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ SQL query (parameterized)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      🐘 POSTGRESQL 16 DATABASE                               │
│                                                                              │
│  Table: findings                                                            │
│  ├─ Indexes used:                                                           │
│  │   ├─ ix_findings_project_id (for WHERE clause)                          │
│  │   ├─ ix_findings_severity (for filter)                                  │
│  │   └─ ix_findings_status (for filter)                                    │
│  │                                                                           │
│  ├─ Query execution:                                                        │
│  │   ├─ Scan: Index scan on ix_findings_project_id                         │
│  │   ├─ Filter: severity = 'CRITICAL' AND status = 'OPEN'                  │
│  │   └─ Sort: created_at DESC                                               │
│  │                                                                           │
│  └─ Results found: 3 findings                                               │
│      ├─ find-0001: SQL Injection in payment endpoint                        │
│      ├─ find-0002: Insecure deserialization in API                          │
│      └─ find-0003: CVE-2023-12345 in payment library                        │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Query results (3 rows)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    📊 DATA TRANSFORMATION & RESPONSE                         │
│                                                                              │
│  Repository → Service → MCP Tool                                            │
│  ├─ SQLAlchemy ORM models → Python dictionaries                             │
│  ├─ Add computed fields (e.g., project_name from join)                      │
│  ├─ Format timestamps (ISO 8601)                                            │
│  └─ Return JSON-serializable list                                           │
│                                                                              │
│  Response for Operation 1:                                                  │
│  [                                                                           │
│    {                                                                         │
│      "id": "find-0001-0000-0000-000000000001",                              │
│      "title": "SQL Injection in payment endpoint",                          │
│      "severity": "CRITICAL",                                                │
│      "status": "OPEN",                                                      │
│      "scan_type": "SAST",                                                   │
│      "file_path": "src/api/payment.py",                                     │
│      "line_number": 145,                                                    │
│      "rule_id": "python-sql-injection-001",                                 │
│      "created_at": "2026-08-15T10:30:00Z",                                  │
│      "updated_at": "2026-08-15T10:30:00Z"                                   │
│    },                                                                        │
│    { /* finding 2 */ },                                                     │
│    { /* finding 3 */ }                                                      │
│  ]                                                                           │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Response back to Gemini
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          🤖 GEMINI AI (Processes Results)                    │
│                                                                              │
│  ✓ Operation 1 complete: Got 3 critical open findings                       │
│                                                                              │
│  Now proceeding with Operation 2...                                         │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Execute second tool
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              💼 SERVICE LAYER (app/services/finding_service.py)              │
│                                                                              │
│  ═══════════════════ OPERATION 2: UPDATE FINDING STATUS ═════════════════  │
│                                                                              │
│  FindingService.update_status()                                             │
│  ├─ Parameters received:                                                    │
│  │   ├─ finding_id: "find-0005-0000-0000-000000000005"                     │
│  │   ├─ new_status: "RESOLVED"                                              │
│  │   └─ actor: User(bob_engineer, SECURITY_ENGINEER)                       │
│  │                                                                           │
│  ├─ Step 1: RBAC Check                                                      │
│  │   ├─ Call: AuthorizationService.require(actor, "update_finding")        │
│  │   ├─ Actor role: SECURITY_ENGINEER                                      │
│  │   └─ Result: ✓ Permission granted                                       │
│  │              (VIEWER would get 403 here)                                 │
│  │                                                                           │
│  ├─ Step 2: Validate Status                                                 │
│  │   ├─ Call: AuthorizationService.validate_status("RESOLVED")             │
│  │   ├─ Valid statuses: [OPEN, IN_PROGRESS, RESOLVED]                      │
│  │   └─ Result: ✓ "RESOLVED" is valid                                      │
│  │              (Invalid like "HACKED" would get 422 here)                  │
│  │                                                                           │
│  ├─ Step 3: Load Finding                                                    │
│  │   ├─ Call: FindingRepository.get_by_id(finding_id)                      │
│  │   ├─ Query: SELECT * FROM findings WHERE id = :id                       │
│  │   └─ Result: ✓ Finding found                                            │
│  │              (Not found would get 404 here)                              │
│  │                                                                           │
│  ├─ Step 4: Store Old Status                                                │
│  │   └─ old_status = "IN_PROGRESS" (current value)                         │
│  │                                                                           │
│  ├─ Step 5: Transactional Update                                            │
│  │   ├─ BEGIN TRANSACTION                                                   │
│  │   │                                                                       │
│  │   ├─ Update Finding Record                                               │
│  │   │   ├─ FindingRepository.update_status(finding, "RESOLVED")           │
│  │   │   ├─ SQL: UPDATE findings                                           │
│  │   │   │       SET status = 'RESOLVED',                                  │
│  │   │   │           updated_at = NOW(),                                   │
│  │   │   │           resolved_at = NOW()                                   │
│  │   │   │       WHERE id = 'find-0005-...'                                │
│  │   │   └─ Result: 1 row updated                                          │
│  │   │                                                                       │
│  │   ├─ Create Audit Log Record                                             │
│  │   │   ├─ AuditService.record_status_change()                            │
│  │   │   ├─ SQL: INSERT INTO audit_logs (                                  │
│  │   │   │         id, user_id, action, resource_type,                     │
│  │   │   │         resource_id, finding_id,                                │
│  │   │   │         old_value, new_value, timestamp                         │
│  │   │   │       ) VALUES (                                                │
│  │   │   │         gen_random_uuid(),                                      │
│  │   │   │         'user-bob-0002',                                        │
│  │   │   │         'status_change',                                        │
│  │   │   │         'finding',                                              │
│  │   │   │         'find-0005-...',                                        │
│  │   │   │         'find-0005-...',                                        │
│  │   │   │         'IN_PROGRESS',                                          │
│  │   │   │         'RESOLVED',                                             │
│  │   │   │         NOW()                                                   │
│  │   │   │       )                                                          │
│  │   │   └─ Result: Audit log created                                      │
│  │   │                                                                       │
│  │   └─ COMMIT TRANSACTION                                                  │
│  │       ├─ Both updates committed atomically                               │
│  │       └─ (If any error occurred, ROLLBACK would happen)                 │
│  │                                                                           │
│  └─ Step 6: Return Updated Finding                                          │
│      └─ finding object with new status                                      │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Update complete
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    📊 UPDATE RESPONSE                                        │
│                                                                              │
│  Response for Operation 2:                                                  │
│  {                                                                           │
│    "finding_id": "find-0005-0000-0000-000000000005",                        │
│    "old_status": "IN_PROGRESS",                                             │
│    "new_status": "RESOLVED",                                                │
│    "updated_by": "bob_engineer",                                            │
│    "updated_at": "2026-08-29T14:30:15Z",                                    │
│    "resolved_at": "2026-08-29T14:30:15Z",                                   │
│    "audit_recorded": true                                                   │
│  }                                                                           │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ All responses collected
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    🤖 GEMINI AI (Final Processing)                           │
│                                                                              │
│  Operation 1 Results: 3 critical open findings                              │
│  Operation 2 Results: Finding find-0005 marked as RESOLVED                  │
│                                                                              │
│  Format natural language response:                                          │
│  ├─ Summarize query results                                                 │
│  ├─ Confirm action taken                                                    │
│  └─ Present in user-friendly format                                         │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   │ Natural language response
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          👤 SECURITY ENGINEER                                │
│                                                                              │
│  Gemini Response:                                                           │
│                                                                              │
│  "I found 3 critical open findings for the Payment API:                     │
│                                                                              │
│  1. **SQL Injection** in payment endpoint (src/api/payment.py:145)          │
│     - Rule: python-sql-injection-001                                        │
│     - Created: Aug 15, 2026                                                 │
│                                                                              │
│  2. **Insecure Deserialization** in API (src/api/deserialize.py:89)        │
│     - Rule: python-deserialization-unsafe                                   │
│     - Created: Aug 16, 2026                                                 │
│                                                                              │
│  3. **CVE-2023-12345** in payment library (requirements.txt)                │
│     - Vulnerable version: payment-lib 2.3.1                                 │
│     - Created: Aug 18, 2026                                                 │
│                                                                              │
│  ✓ I've successfully marked finding find-0005 as RESOLVED.                  │
│    Previous status: IN_PROGRESS → New status: RESOLVED                      │
│    Updated by: bob_engineer at 2:30 PM today                                │
│    Audit log has been recorded."                                            │
│                                                                              │
│  ✓ User satisfied with response                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Components in the Flow

### 1. **Entry Points** (2 options)
- **MCP Tools** (for Gemini) - `app/mcp/tools.py`
- **REST API** (direct access) - `app/api/findings.py`

### 2. **Security Layers** (3 checkpoints)
- **JWT Authentication** - Token validation (`app/auth/jwt.py`)
- **User Resolution** - DB lookup or email mapping (`app/auth/dependencies.py`)
- **RBAC Authorization** - Permission enforcement (`app/services/authorization_service.py`)

### 3. **Business Logic** (Service Layer)
- **FindingService** - CRUD operations + validation (`app/services/finding_service.py`)
- **AuditService** - Immutable audit logging (`app/services/audit_service.py`)
- **AuthorizationService** - RBAC rules + status validation

### 4. **Data Access** (Repository Layer)
- **FindingRepository** - Database queries (`app/repositories/finding_repository.py`)
- **AuditRepository** - Audit log queries

### 5. **Persistence** (Database)
- **PostgreSQL 16** - 5 tables (findings, projects, users, roles, audit_logs)
- **SQLAlchemy ORM** - Models (`app/models/`)

---

## Security Guarantees Throughout the Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  AT EVERY STEP                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ JWT validated BEFORE any business logic                      │
│  ✓ RBAC checked BEFORE any database access                      │
│  ✓ Input validated BEFORE any write operation                   │
│  ✓ Enum guardrails on severity, status, scan_type (MCP + REST)  │
│  ✓ Audit log created FOR every status change                    │
│  ✓ Transactions ensure atomicity (no partial updates)           │
│  ✓ Raw secrets NEVER stored (metadata only)                     │
│  ✓ Database NEVER exposed directly to Gemini                    │
│  ✓ Gemini grounded to tool results only (no hallucinations)     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## What Makes This Flow Secure

### 🔐 **Defense in Depth**

1. **Network Layer** - HTTPS only, private Cloud SQL
2. **Authentication** - JWT signature validation, expiry checks
3. **Authorization** - RBAC enforced at service layer
4. **Input Validation** - Enum validation, parameterized queries
5. **Data Protection** - No raw secrets stored
6. **Audit Trail** - Immutable logs, transactional integrity
7. **Database Security** - Parameterized queries prevent SQL injection

### 🚫 **What Can Go Wrong (and How It's Prevented)**

| Attack | Prevention |
|--------|-----------|
| **No/Invalid JWT** → 401 Unauthorized (rejected at auth layer) |
| **Expired JWT** → 401 Unauthorized (exp claim checked) |
| **Tampered JWT** → 401 Unauthorized (signature mismatch) |
| **VIEWER tries update** → 403 Forbidden (RBAC blocks at service) |
| **SQL Injection** → Prevented (parameterized queries) |
| **Invalid status** → 422 Unprocessable (enum validation) |
| **Unbounded query** → Clamped to 1-200 (limit enforcement) |

---

## Data Flow Summary

```
Human Query
    ↓
Gemini AI (interprets intent)
    ↓
MCP Tools (structured function calls)
    ↓
JWT Auth (validate token)
    ↓
User Resolution (identify + load role)
    ↓
RBAC Check (authorize action)
    ↓
Service Layer (business logic + validation)
    ↓
Repository Layer (database queries)
    ↓
PostgreSQL (persistent storage)
    ↓
Repository Layer (ORM models)
    ↓
Service Layer (format response)
    ↓
MCP Tools (JSON response)
    ↓
Gemini AI (natural language formatting)
    ↓
Human Response (user-friendly answer)
```

---

## Technologies Used in Each Layer

| Layer | Technology | File Location |
|-------|-----------|---------------|
| **AI Interface** | Google Gemini ADK | External service |
| **MCP Layer** | FastMCP 1.9+ | `app/mcp/tools.py` |
| **REST Layer** | FastAPI 0.115+ | `app/api/findings.py` |
| **Auth** | PyJWT 2.8+ | `app/auth/jwt.py` |
| **Services** | Python async | `app/services/` |
| **Data Access** | SQLAlchemy 2.0+ | `app/repositories/` |
| **Database** | PostgreSQL 16 | Cloud SQL / Docker |
| **ORM Models** | SQLAlchemy | `app/models/` |
| **Validation** | Pydantic 2.10+ | `app/api/schemas.py` |

---

## Complete File Mapping

```
User Query → Gemini → MCP → Auth → Service → Repository → Database

                     app/mcp/tools.py
                     ├─ get_security_findings()
                     └─ update_finding_status()
                            ↓
                     app/auth/jwt.py
                     └─ decode_token()
                            ↓
                     app/auth/dependencies.py
                     └─ get_current_user()
                            ↓
                     app/services/authorization_service.py
                     └─ require() / validate_status()
                            ↓
                     app/services/finding_service.py
                     ├─ get_findings()
                     └─ update_status()
                            ↓
                     app/repositories/finding_repository.py
                     ├─ list_findings()
                     └─ update_status()
                            ↓
                     app/models/finding.py
                     └─ Finding (SQLAlchemy model)
                            ↓
                     PostgreSQL 16
                     ├─ findings table
                     ├─ projects table
                     ├─ users table
                     ├─ roles table
                     └─ audit_logs table
```

---

*This single flow covers the entire codebase from user interaction to database and back, showing how all components work together to provide secure, governed access to security findings.*
