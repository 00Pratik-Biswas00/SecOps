# Enterprise Security Findings Connector - Architecture

> Production-ready connector providing secure, governed access to security findings for Gemini applications
>
> Last updated: 2026-08-30

---

## Quick Reference

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Layer** | FastAPI | 5 REST endpoints |
| **MCP Layer** | MCP 2024-11-05 | 5 tools for Gemini Discovery Engine |
| **Auth** | OIDC JWT | Service account authentication + RBAC |
| **Services** | Python async | Business logic |
| **Database** | PostgreSQL 16 | 3 tables (projects, findings, audit_logs), 12 seeded findings |
| **Deployment** | Docker / Cloud Run | Local dev / Production |

---

## 1. System Architecture

```
USER → GEMINI ENTERPRISE → DISCOVERY ENGINE → MCP SERVER → SERVICES → REPOSITORIES → POSTGRESQL
         ↓                       ↓                ↓            ↓
    Natural Lang          Service Account    JWT Extract   RBAC
    Tool Selection        OIDC Token         Email→Role    Input Check
```

### Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. USER                                                         │
│     "Show me critical open findings for payment-api-prod"       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  2. GEMINI ENTERPRISE (Discovery Engine)                         │
│     → Selects: get_security_findings()                          │
│     → Parameters: project_id="payment-api-prod",                │
│                   severity=CRITICAL, status=OPEN                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ MCP JSON-RPC call + Service Account JWT
┌────────────────────────────▼─────────────────────────────────────┐
│  3. MCP SERVER (Cloud Run - 5 Tools)                             │
│     get_security_findings | get_finding_details                  │
│     get_security_summary | update_finding_status                 │
│     get_finding_audit_history                                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  🔒 SECURITY BOUNDARY                                            │
│                                                                  │
│  ① JWT Extraction & Decode                                      │
│     → Read from x-serverless-authorization header               │
│     → Decode JWT (Discovery Engine service account)             │
│     → Extract email: service-NNN@gcp-sa-discoveryengine...      │
│                                                                  │
│  ② Role Mapping (Secret Manager)                                │
│     → Lookup email in USER_ROLE_MAP secret                      │
│     → service-PROJECT_ID@gcp-sa-discoveryengine...: SECURITY_ADMIN │
│     → admin@company.com: SECURITY_ADMIN                         │
│     → demo@example.com: SECURITY_ADMIN (fallback for demo)      │
│                                                                  │
│  ③ RBAC Authorization                                           │
│     VIEWER           → Read only                                │
│     SECURITY_ENGINEER → Read + Update                           │
│     SECURITY_ADMIN    → Full access                             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Authorized request
┌────────────────────────────▼─────────────────────────────────────┐
│  4. SERVICE LAYER                                                │
│     FindingService | AuditService | AuthorizationService         │
│     → Business logic, validation, RBAC enforcement               │
│     → Project name resolution (payment-api-prod → proj-payment-api) │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  5. REPOSITORY LAYER                                             │
│     FindingRepository | AuditRepository                          │
│     → SQLAlchemy async queries                                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  6. Cloud SQL PostgreSQL (secops_db)                             │
│     projects | findings | audit_logs                            │
│     → Unix socket connection (/cloudsql/CONNECTION_NAME)         │
└──────────────────────────────────────────────────────────────────┘
```

### Security Guarantees

✓ JWT validated every request (expired/tampered tokens rejected)  
✓ RBAC enforced in service layer (not delegated to Gemini)  
✓ Every write creates immutable audit record  
✓ Raw secrets never stored (metadata only)  
✓ Database never exposed to Gemini  
✓ Input validation (limit 1-200, status/severity/scan_type enums at MCP + REST boundary)  
✓ Grounding rules in agent instruction (Gemini only answers from tool results)  
✓ Transactional updates (atomic status + audit)

---

## 2. Component Architecture

```
app/
├── main.py                 # FastAPI app entry
├── config.py               # Settings from .env
├── database.py             # SQLAlchemy async engine
│
├── api/                    # REST Layer
│   ├── findings.py         # 5 endpoints
│   ├── projects.py         # Project summary
│   └── schemas.py          # Pydantic models + Severity/FindingStatus/ScanType enums
│
├── mcp/                    # MCP Layer
│   ├── tools.py            # 5 MCP tools
│   └── server.py           # stdio entry point
│
├── auth/                   # Authentication
│   ├── jwt.py              # Token create/decode (HS256)
│   ├── email_role.py       # USER_ROLE_MAP parser
│   ├── dependencies.py     # get_current_user()
│   └── demo_tokens.py      # Seeded user tokens
│
├── services/               # Business Logic
│   ├── finding_service.py  # CRUD + RBAC + audit
│   ├── audit_service.py    # Immutable logs
│   └── authorization_service.py  # RBAC enforcement
│
├── repositories/           # Data Access
│   ├── finding_repository.py
│   └── audit_repository.py
│
└── models/                 # SQLAlchemy ORM
    ├── finding.py
    ├── project.py
    ├── user.py
    ├── role.py
    └── audit_log.py
```

---

## 3. Authentication Flow

```
REQUEST from Discovery Engine (x-serverless-authorization: bearer <JWT>)
   ↓
① JWT EXTRACTION & DECODE
   → Check x-serverless-authorization header (Discovery Engine)
   → Fallback to Authorization header
   → Decode JWT (Google-signed OIDC token)
   → Extract email from JWT claims
   ↓
   ├─ NO TOKEN or INVALID → Fall back to test@epam.com (demo mode)
   │
② ROLE RESOLUTION (Secret Manager)
   │
   Extract email from JWT → get_role_for_email()
   │
   Lookup in USER_ROLE_MAP secret:
   └─ service-PROJECT_ID@gcp-sa-discoveryengine.iam.gserviceaccount.com:SECURITY_ADMIN
   └─ admin@company.com:SECURITY_ADMIN
   └─ demo@example.com:SECURITY_ADMIN
   │
   → Create synthetic User object with role
   ↓
③ RBAC CHECK
   AuthorizationService.require(user, "update_finding")
   │
   ├─ VIEWER attempts update → 403 Forbidden
   │
   └─ ENGINEER/ADMIN → Proceed to service layer
```

### Service Account Authentication

**Discovery Engine Service Account:**
```
service-PROJECT_ID@gcp-sa-discoveryengine.iam.gserviceaccount.com
```

**Configuration (Secret Manager):**
```bash
# Secret: connector-user-role-map
# Format: email1:ROLE1,email2:ROLE2,...
admin@company.com:SECURITY_ADMIN,
engineer@company.com:SECURITY_ENGINEER,
viewer@company.com:VIEWER,
service-PROJECT_ID@gcp-sa-discoveryengine.iam.gserviceaccount.com:SECURITY_ADMIN
```

**Benefits:**
- No database tables needed for users/roles
- Instant role updates (update secret)
- Discovery Engine handles OIDC token generation
- Works with enterprise identity providers
- Simple RBAC through comma-separated mapping

---

## 4. Write-Back Flow

### update_finding_status(finding_id, status) - Called from Gemini Enterprise

```
① JWT Extraction       → Read x-serverless-authorization header
   ↓                      Extract Discovery Engine service account email
② Role Lookup          → get_role_for_email() from Secret Manager
   ↓                      service-PROJECT_ID@...→ SECURITY_ADMIN ✓
③ Create Synthetic User → User(email=service_account, role=SECURITY_ADMIN)
   ↓
④ RBAC Check          → require(user, "update_finding")
   ↓                     VIEWER → 403 Forbidden ✗
   ↓                     ENGINEER/ADMIN → Continue ✓
⑤ Status Validation    → Must be: OPEN | IN_PROGRESS | RESOLVED
   ↓                     Invalid → 422 Unprocessable ✗
⑥ Finding Lookup      → get_by_id(finding_id)
   ↓                     Not found → 404 ✗
⑦ Store Old Status    → old_status = finding.status
   ↓
╔══════════════════════════════════════════════════╗
║  TRANSACTIONAL BLOCK (SQLAlchemy async)          ║
║                                                   ║
║  ⑧ UPDATE findings                                ║
║     SET status = ?, updated_at = NOW()            ║
║     WHERE id = ?                                  ║
║                                                   ║
║  ⑨ INSERT INTO audit_logs                         ║
║     (id, user_id, action, resource_type,          ║
║      resource_id, finding_id,                     ║
║      old_value, new_value, timestamp)             ║
║     VALUES (uuid, service_account_email,          ║
║             'UPDATE_STATUS', 'FINDING', ...)      ║
║                                                   ║
║  ⑩ COMMIT (or ROLLBACK on error)                  ║
╚══════════════════════════════════════════════════╝
   ↓
⑪ RETURN RESPONSE
   {
     id, status, updated_at,
     message: "Status updated successfully"
   }
```

**Security Checkpoints:**
- Discovery Engine OIDC authentication
- Service account role mapping via Secret Manager
- RBAC enforced before any DB access
- Input validation (status enum)
- Transactional integrity (atomic update + audit)
- Audit logs reference user by email (no FK constraint)

---

## 5. Data Model

```
projects (3 records)
  ├─ proj-payment-api (payment-api-prod)
  ├─ proj-user-auth (user-auth-service)
  └─ proj-data-pipeline (data-pipeline-prod)
  │
  └─→ findings (12 records)
       ├─ CRITICAL: 3 findings (SQL Injection, AWS Secret, Auth Bypass)
       ├─ HIGH: 3 findings (XSS, Vulnerable Dependency, Path Traversal)
       ├─ MEDIUM: 3 findings (Weak Crypto, API Key, Lint)
       ├─ LOW: 2 findings (Debug Logging, Deprecated Function)
       └─ INFO: 1 finding (TODO Comment)
       │
       └─→ audit_logs (5 sample entries + new writes)
            ├─ user_id (email string, no FK)
            └─ finding_id FK
```

### Key Tables

| Table | Columns | Purpose |
|-------|---------|---------|
| **projects** | id, name, description, repository_url, created_at, updated_at | Projects being scanned |
| **findings** | id, project_id, title, description, severity, status, scan_type, file_path, line_number, remediation, created_at, updated_at, resolved_at | Security findings (metadata only, no raw secrets) |
| **audit_logs** | id, user_id, action, resource_type, resource_id, finding_id, old_value, new_value, timestamp | Immutable change history |

**Note:** No `users` or `roles` tables - RBAC is managed via Secret Manager (USER_ROLE_MAP)

**Indexes:**
- `ix_findings_project_id`, `ix_findings_severity`, `ix_findings_status`
- `ix_audit_logs_finding_id`, `ix_audit_logs_user_id`, `ix_audit_logs_timestamp`

**Demo Data Distribution:**
- **payment-api-prod** (proj-payment-api): 5 findings (2 CRITICAL, 2 HIGH, 1 MEDIUM, 1 INFO)
- **user-auth-service** (proj-user-auth): 3 findings (1 CRITICAL, 1 MEDIUM, 1 LOW)
- **data-pipeline-prod** (proj-data-pipeline): 4 findings (1 HIGH, 1 MEDIUM, 1 LOW, 1 INFO)

---

## 6. Deployment

### Local Development

```bash
# Start PostgreSQL
docker compose up -d postgres

# Start connector (auto-reload)
uvicorn app.main:app --reload

# Run demo
python demo.py                         # REST + Gemini (local)
python demo.py --no-gemini             # REST only
python gemini_agent.py                 # Interactive REPL

# Run tests
python -m pytest tests/ -v             # 127 tests
```

**Environment (.env):**
```bash
DATABASE_URL=postgresql+asyncpg://connector:your_password@localhost:5432/secops_db
USER_ROLE_MAP=admin@company.com:SECURITY_ADMIN,demo@example.com:SECURITY_ADMIN

# Production environment variables (set via gcloud run deploy):
# CLOUD_SQL_CONNECTION_NAME=YOUR_PROJECT_ID:us-central1:security-connector-db
# DB_PASSWORD=<from Secret Manager: connector-db-password>
# USER_ROLE_MAP=<from Secret Manager: connector-user-role-map>
```

### Production (Google Cloud)

```
┌─────────────────────────────────────────────────────┐
│  GEMINI ENTERPRISE (Discovery Engine)                │
│  → MCP JSON-RPC over HTTPS                          │
│  → Service Account: service-NNN@gcp-sa-discovery... │
└────────────────────┬─────────────────────────────────┘
                     │ HTTPS + OIDC JWT (x-serverless-authorization)
┌────────────────────▼─────────────────────────────────┐
│  CLOUD RUN (us-central1)                             │
│  • enterprise-security-connector                     │
│  • Min instances: 1, Max: 20, Auto-scale             │
│  • POST /mcp endpoint (MCP 2024-11-05)               │
│  • GET /health endpoint                              │
│  • Memory: 1Gi, CPU: 1 vCPU                          │
└────────────────────┬─────────────────────────────────┘
                     │ Unix socket: /cloudsql/PROJECT:REGION:INSTANCE
┌────────────────────▼─────────────────────────────────┐
│  CLOUD SQL FOR POSTGRESQL                            │
│  • Instance: security-connector-db                   │
│  • Database: secops_db                               │
│  • User: connector (with DB_PASSWORD from secret)    │
│  • Connection: Unix socket (no public IP)            │
│  • Auto backups, point-in-time recovery              │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  SECRET MANAGER                                       │
│  • connector-db-password                             │
│  • connector-user-role-map                           │
│    Format: email1:ROLE1,email2:ROLE2                 │
└──────────────────────────────────────────────────────┘
```

**Deployment Steps:**

1. **Enable APIs**: Cloud Run, Cloud SQL, Secret Manager, Artifact Registry
2. **Create Cloud SQL instance**: `security-connector-db` with PostgreSQL 16
3. **Create database**: `secops_db` and user `connector`
4. **Load schema**: Import `database/setup/database_schema.sql` via GCS import
5. **Store secrets**:
   - `connector-db-password`: Database password
   - `connector-user-role-map`: `email1:ROLE1,email2:ROLE2,...`
6. **Build & deploy**: `gcloud run deploy enterprise-security-connector --source .`
7. **Set environment variables**:
   - `CLOUD_SQL_CONNECTION_NAME`: `PROJECT_ID:us-central1:security-connector-db`
   - `DB_PASSWORD`: Reference to Secret Manager
   - Database URL auto-configured in `app/database.py`
8. **Grant permissions**:
   - Discovery Engine service account → `roles/run.invoker`
   - Cloud Run service account → `roles/cloudsql.client` + `roles/secretmanager.secretAccessor`
9. **Register in Discovery Engine**: Configure MCP connector with Cloud Run URL
10. **Verify**: Query from Gemini Enterprise chat

---

## 7. Security Model

### Defense in Depth (7 Layers)

| Layer | Protection | Implementation |
|-------|-----------|----------------|
| **Network** | Isolation | Cloud SQL: private IP, VPC; Cloud Run: HTTPS only |
| **Authentication** | JWT validation | HMAC-SHA256, expiry check, signature verification |
| **Authorization** | RBAC | Service layer enforcement, 3 roles, permission matrix |
| **Input Validation** | Sanitization | Severity/Status/ScanType enums at MCP + REST boundary, limit 1-200, Pydantic schemas |
| **Data Protection** | No secrets | Metadata only, regex tests for leaks |
| **Audit** | Immutability | Every write logged, no UPDATE/DELETE on audit_logs |
| **Database** | Query safety | Parameterized queries, ORM, limited user permissions |

### RBAC Matrix

| Role | Read Findings | Update Status | View Audit |
|------|--------------|---------------|------------|
| VIEWER | ✓ | ✗ (403) | ✓ |
| SECURITY_ENGINEER | ✓ | ✓ | ✓ |
| SECURITY_ADMIN | ✓ | ✓ | ✓ |

### Threat Mitigations

| Threat | Mitigation |
|--------|-----------|
| Unauthorized access | JWT validation on every request |
| Token tampering | HMAC signature verification |
| Privilege escalation | RBAC enforced in service layer |
| SQL injection | Parameterized queries via SQLAlchemy |
| Sensitive data exposure | Raw secrets never stored/returned |
| Audit manipulation | Audit logs immutable (no UPDATE/DELETE) |
| DoS (unbounded queries) | Limit clamped to [1, 200] |
| Replay attacks | Token expiry (60 min default) |

---

## API Reference

### REST Endpoints (FastAPI)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| GET | `/api/v1/findings` | JWT | List findings (filters: project_id, severity, status, scan_type, limit) |
| GET | `/api/v1/findings/{id}` | JWT | Finding detail |
| PATCH | `/api/v1/findings/{id}` | JWT + RBAC | Update status (ENGINEER/ADMIN only) |
| GET | `/api/v1/findings/{id}/audit` | JWT | Audit history |
| GET | `/api/v1/projects/{id}/summary` | JWT | Project summary |

### MCP Tools (MCP 2024-11-05)

| Tool | Parameters | Auth | Description |
|------|-----------|------|-------------|
| `get_security_findings` | project_id, [severity, status, scan_type, limit] | Any role | List findings, accepts project name or ID |
| `get_finding_details` | finding_id | Any role | Full detail with remediation |
| `get_security_summary` | project_id | Any role | Aggregated counts by severity/status |
| `update_finding_status` | finding_id, status | ENGINEER/ADMIN | Update status + create audit log |
| `get_finding_audit_history` | finding_id | Any role | Complete change history |

**Note:** Authentication is handled via Discovery Engine service account in request headers (x-serverless-authorization), not as tool parameters.

---

## Test Coverage

**127 tests across 5 files:**

- `test_finding_service.py` (24) - Service layer: filtering, RBAC, update, audit
- `test_auth.py` (20) - JWT: valid, expired, tampered, wrong secret, RBAC matrix
- `test_api.py` (23) - REST endpoints: happy paths, 401/403/404/422
- `test_mcp_tools.py` (23) - MCP tools: all 5 tools, auth failures, discovery
- `test_security.py` (37) - Security boundaries, audit integrity, sensitive data

**Run:** `python -m pytest tests/ -v`

---

## Key Architectural Decisions

1. **Discovery Engine OIDC auth** - Service account tokens, no custom JWT generation needed
2. **Email-based RBAC via Secret Manager** - No users/roles tables, instant role updates
3. **Unix socket Cloud SQL connection** - Secure, no public IP or connection pooling overhead
4. **Project name resolution** - Accepts both project names (payment-api-prod) and IDs (proj-payment-api)
5. **Immutable audit logs** - No UPDATE/DELETE, user stored as email string
6. **Simplified data model** - 3 tables only (projects, findings, audit_logs)
7. **MCP 2024-11-05 protocol** - JSON-RPC over HTTPS, no token parameters
8. **Async all the way** - FastAPI + SQLAlchemy async + asyncpg
9. **Layered architecture** - Clear separation: MCP → Auth → Services → Repos → Models

---

*Enterprise Security Findings Connector v1.0.0 | Last updated: 2026-08-30*
