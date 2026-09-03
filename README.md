# SecOps Nexus — Enterprise Security Findings Connector

**Production-ready MCP connector for Gemini Enterprise** that provides secure, governed access to enterprise security findings through Google Discovery Engine.

## Executive Summary

SecOps Nexus is an AI-powered, secure enterprise security findings connector that enables users to query, understand, and act on security findings using natural language through Gemini Enterprise. Built around an MCP-based integration layer, it securely connects AI to enterprise security data while enforcing authentication, RBAC, governance, and auditability. Users can retrieve critical findings, investigate risks, and perform authorized actions—all without direct database access, SQL queries, or navigating multiple security tools.
 

### Key Features

✅ **MCP 2024-11-05 Protocol** — Native integration with Gemini Enterprise Discovery Engine
✅ **OIDC Authentication** — Discovery Engine service account authentication, no token management
✅ **RBAC** — Three roles (VIEWER, SECURITY_ENGINEER, SECURITY_ADMIN) enforced server-side
✅ **Immutable Audit Logs** — Every status change creates an audit record
✅ **Write-Back** — AI can update finding status with proper authorization
✅ **Project Name Resolution** — Query by friendly names (payment-api-prod) or IDs

### Use Cases

- **Query findings**: *"Show me all CRITICAL open findings for payment-api-prod"*
- **Get summaries**: *"What's the security posture of user-auth-service?"*
- **Update status**: *"Mark finding find-0001-crit-sql-inject as IN_PROGRESS"*
- **View history**: *"Show me audit history for find-0004-high-xss"*

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  GEMINI ENTERPRISE (Discovery Engine)                   │
│  → Natural language queries                             │
│  → Tool selection via MCP                               │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS + OIDC JWT
┌────────────────────▼────────────────────────────────────┐
│  CLOUD RUN (MCP Server)                                 │
│  • POST /mcp (MCP JSON-RPC 2024-11-05)                  │
│  • Service account authentication                       │
│  • RBAC via Secret Manager role mapping                 │
└────────────────────┬────────────────────────────────────┘
                     │ Unix socket
┌────────────────────▼────────────────────────────────────┐
│  CLOUD SQL POSTGRESQL                                   │
│  • Database: secops_db                                  │
│  • Tables: projects, findings, audit_logs               │
│  • Demo data: 3 projects, 12 findings                   │
└─────────────────────────────────────────────────────────┘
```

### Security Layers

1. **Discovery Engine** → OIDC-authenticated service account
2. **MCP Server** → Role mapping via Secret Manager
3. **RBAC** → Permission checks before any DB access
4. **Audit Trail** → Immutable logs for all write operations

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **MCP Protocol** | MCP 2024-11-05 (JSON-RPC over HTTPS) |
| **API Framework** | FastAPI 0.115 + Uvicorn |
| **Authentication** | Google OIDC (Discovery Engine service account) |
| **Database** | Cloud SQL PostgreSQL 16 (Unix socket) |
| **ORM** | SQLAlchemy 2 async + asyncpg |
| **Cloud Platform** | GCP Cloud Run + Secret Manager |
| **Language** | Python 3.13 |

---

## Repository Structure

```
secops-nexus/
├── app/                           # Application source (deployed to Cloud Run)
│   ├── main.py                    # FastAPI + MCP endpoint handler
│   ├── config.py                  # Pydantic settings (env-driven)
│   ├── database.py                # SQLAlchemy engine (Unix socket for Cloud Run)
│   ├── api/                       # REST endpoints (findings, projects)
│   ├── auth/                      # OIDC JWT extraction, role mapping
│   ├── models/                    # SQLAlchemy ORM models
│   ├── services/                  # Business logic (FindingService, AuditService)
│   └── repositories/              # Data access layer
├── database/setup/                # Database schema and sample data
│   ├── database_schema.sql        # Full schema + 12 demo findings
│   └── *.sql                      # Setup and migration scripts
├── scripts/                       # Utility scripts (not deployed)
│   ├── demo.py                    # REST API demo
│   ├── load_schema.py             # Database loader
│   └── verify_db.py               # Database verification
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md            # System architecture and flows
│   ├── COMPLETE_FLOW.md           # End-to-end request lifecycle
│   ├── DEPLOYMENT.md              # GCP deployment guide
│   └── TESTING_GUIDE.md           # Test scenarios for demo
├── tests/                         # Test suites
├── Dockerfile                     # Production container
├── .dockerignore                  # Excludes tests, docs, scripts
├── .env.example                   # Environment template
└── requirements.txt               # Python dependencies
```

---

## Quick Start — Local Development

### Prerequisites

- Docker Desktop (for PostgreSQL)
- Python 3.11+
- GCP account with Cloud SQL and Cloud Run access

### 1. Start PostgreSQL Locally

```bash
docker compose up -d postgres
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and set:
# DATABASE_URL=postgresql+asyncpg://connector:connector_pass@localhost:5432/secops_db
# USER_ROLE_MAP=your.email@company.com:SECURITY_ADMIN
```

### 3. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 4. Load Database Schema

```bash
python scripts/load_schema.py
```

### 5. Start the Server

```bash
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

---

## Production Deployment (GCP)

### Step 1: Create Cloud SQL Instance

```bash
gcloud sql instances create security-connector-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=us-central1
```

### Step 2: Create Database and User

```bash
gcloud sql databases create secops_db --instance=security-connector-db

gcloud sql users create connector \
  --instance=security-connector-db \
  --password=YOUR_STRONG_PASSWORD
```

### Step 3: Load Schema via GCS Import

```bash
# Upload schema to GCS
gsutil mb gs://YOUR_BUCKET-sql-import/
gsutil cp database/setup/database_schema.sql gs://YOUR_BUCKET-sql-import/

# Grant Cloud SQL service account access
gcloud sql instances describe security-connector-db \
  --format="value(serviceAccountEmailAddress)" | \
  xargs -I {} gsutil iam ch serviceAccount:{}:objectViewer gs://YOUR_BUCKET-sql-import

# Import schema
gcloud sql import sql security-connector-db \
  gs://YOUR_BUCKET-sql-import/database_schema.sql \
  --database=secops_db
```

### Step 4: Store Secrets

```bash
# Database password
echo -n "YOUR_STRONG_PASSWORD" | \
  gcloud secrets create connector-db-password --data-file=-

# Role mappings
echo -n "admin@company.com:SECURITY_ADMIN,service-PROJECT_ID@gcp-sa-discoveryengine.iam.gserviceaccount.com:SECURITY_ADMIN" | \
  gcloud secrets create connector-user-role-map --data-file=-
```

### Step 5: Deploy to Cloud Run

```bash
gcloud run deploy enterprise-security-connector \
  --source . \
  --region=us-central1 \
  --set-env-vars="CLOUD_SQL_CONNECTION_NAME=PROJECT_ID:us-central1:security-connector-db" \
  --set-secrets="DB_PASSWORD=connector-db-password:latest,USER_ROLE_MAP=connector-user-role-map:latest" \
  --add-cloudsql-instances=PROJECT_ID:us-central1:security-connector-db \
  --no-allow-unauthenticated
```

### Step 6: Grant Discovery Engine Access

```bash
# Get Discovery Engine service account
# Format: service-PROJECT_NUMBER@gcp-sa-discoveryengine.iam.gserviceaccount.com

gcloud run services add-iam-policy-binding enterprise-security-connector \
  --region=us-central1 \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### Step 7: Register in Discovery Engine

1. Go to **Gemini Enterprise** → **Agent Builder** → **Apps**
2. Create or edit your app
3. Under **Extensions** → **Tools** → Add **Custom Action**
4. Configure MCP connector:
   - **Name**: SecOps Security Findings
   - **Type**: MCP Connector
   - **Endpoint**: `https://enterprise-security-connector-PROJECT_ID.us-central1.run.app/mcp`
   - **Authentication**: Service Account (auto-configured)

---

## MCP Tools (5 Available Actions)

| Tool | Description | Required Role |
|------|-------------|---------------|
| **get_security_findings** | List findings for a project (filter by severity, status, scan_type) | VIEWER |
| **get_finding_details** | Get full details of a specific finding | VIEWER |
| **get_security_summary** | Get aggregated security summary by severity/status | VIEWER |
| **update_finding_status** | Update finding status (OPEN → IN_PROGRESS → RESOLVED) | SECURITY_ENGINEER |
| **get_finding_audit_history** | View complete change history for a finding | VIEWER |

### Tool Parameters

**get_security_findings:**
- `project_id` (required): Project name or ID (e.g., "payment-api-prod" or "proj-payment-api")
- `severity` (optional): CRITICAL, HIGH, MEDIUM, LOW, INFO
- `status` (optional): OPEN, IN_PROGRESS, RESOLVED
- `scan_type` (optional): SAST, SECRETS, DEPENDENCY, LINT
- `limit` (optional): Number of results (default: 50)

**update_finding_status:**
- `finding_id` (required): Finding ID (e.g., "find-0001-crit-sql-inject")
- `status` (required): OPEN, IN_PROGRESS, or RESOLVED

---

## Demo Data

### Projects (3 total)

| Project ID | Project Name | Findings Count |
|------------|--------------|----------------|
| `proj-payment-api` | payment-api-prod | 5 findings |
| `proj-user-auth` | user-auth-service | 3 findings |
| `proj-data-pipeline` | data-pipeline-prod | 4 findings |

### Sample Findings

**Payment API (5 findings):**
- `find-0001-crit-sql-inject` — CRITICAL — SQL Injection in payment endpoint
- `find-0002-crit-secret-leak` — CRITICAL — AWS Secret Key exposed in code
- `find-0004-high-xss` — HIGH — Cross-Site Scripting vulnerability
- `find-0008-med-api-key` — MEDIUM — API key in environment variable
- `find-0012-info-comment` — INFO — TODO comment found

**User Auth Service (3 findings):**
- `find-0003-crit-auth-bypass` — CRITICAL — Authentication bypass vulnerability
- `find-0007-med-weak-crypto` — MEDIUM — Weak cryptographic algorithm
- `find-0010-low-debug-log` — LOW — Debug logging enabled in production

---

## Testing in Gemini Enterprise

Once deployed, test these queries in **Gemini Enterprise Chat**:

### 1. List Findings
```
Show me security findings from the database for project "payment-api-prod"
```
**Expected**: 5 findings returned with details

### 2. Filter by Severity
```
Show me all CRITICAL security findings across all projects
```
**Expected**: 3 CRITICAL findings (SQL Injection, AWS Secret, Auth Bypass)

### 3. Get Summary
```
What's the security summary for user-auth-service?
```
**Expected**: Aggregated counts by severity and status

### 4. Update Status (Write-Back)
```
Mark finding find-0004-high-xss as IN_PROGRESS because we're working on it
```
**Expected**: Status updated successfully message

### 5. View Audit History
```
Show me audit history for finding find-0004-high-xss
```
**Expected**: Complete change history with timestamps and users

### 6. Complex Query
```
What's the current status of authentication-related findings?
```
**Expected**: Gemini uses get_security_findings with intelligent filtering

---

## RBAC Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **VIEWER** | Read findings, view audit logs | Security analysts, developers |
| **SECURITY_ENGINEER** | Read + Update status | Security team managing vulnerabilities |
| **SECURITY_ADMIN** | Full access | Security leads, compliance officers |

### Role Configuration

Roles are managed via Secret Manager (`connector-user-role-map`):

```bash
# Format: email1:ROLE1,email2:ROLE2,...
admin@company.com:SECURITY_ADMIN,
engineer@company.com:SECURITY_ENGINEER,
viewer@company.com:VIEWER,
service-PROJECT_ID@gcp-sa-discoveryengine.iam.gserviceaccount.com:SECURITY_ADMIN
```

**Benefits:**
- No database tables for users/roles
- Instant role updates (update secret)
- Discovery Engine service account can be assigned any role

---

## REST API (Optional)

All endpoints require authentication. Available for direct HTTP access:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/api/v1/findings` | List findings |
| `GET` | `/api/v1/findings/{id}` | Get finding details |
| `PATCH` | `/api/v1/findings/{id}` | Update finding status |
| `GET` | `/api/v1/findings/{id}/audit` | Get audit history |
| `GET` | `/api/v1/projects/{id}/summary` | Get project summary |

---

## Security Properties

✅ **OIDC Authentication** — Discovery Engine service account tokens
✅ **RBAC Enforced** — All permissions checked server-side
✅ **Immutable Audit Logs** — Every write creates audit record
✅ **No Raw Secrets** — Only metadata stored, never actual secret values
✅ **Unix Socket Connection** — No public database access
✅ **Input Validation** — Severity, status, scan_type enums enforced
✅ **Project Resolution** — Accepts both friendly names and IDs
✅ **No Token Management** — Discovery Engine handles all auth

---

## Troubleshooting

### Issue: Gemini says "No findings found"

**Cause**: Wrong database or authentication issue

**Fix**:
1. Check database name is `secops_db` (not `security_connector`)
2. Verify data loaded: Run `scripts/verify_db.py`
3. Check role mapping in Secret Manager includes Discovery Engine service account

### Issue: "Permission denied" errors

**Cause**: Service account not granted SECURITY_ADMIN role

**Fix**:
```bash
# Update role mapping secret
gcloud secrets versions add connector-user-role-map --data-file=- <<EOF
service-YOUR_PROJECT_NUMBER@gcp-sa-discoveryengine.iam.gserviceaccount.com:SECURITY_ADMIN
EOF
```

### Issue: Connection timeouts

**Cause**: Cloud SQL instance not accessible

**Fix**:
1. Verify Cloud SQL instance exists: `security-connector-db`
2. Check Cloud Run has `--add-cloudsql-instances` flag
3. Verify Unix socket connection in logs

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Local only | PostgreSQL connection string |
| `CLOUD_SQL_CONNECTION_NAME` | Cloud Run | Format: `PROJECT:REGION:INSTANCE` |
| `DB_PASSWORD` | Cloud Run | From Secret Manager |
| `USER_ROLE_MAP` | Yes | Email to role mappings (from Secret Manager) |
| `APP_ENV` | No | `development` or `production` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING` |

---

## Documentation

| File | Contents |
|------|----------|
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | System architecture, flows, security model |
| [`docs/COMPLETE_FLOW.md`](./docs/COMPLETE_FLOW.md) | End-to-end request walkthrough |
| [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) | Detailed GCP deployment guide |
| [`docs/TESTING_GUIDE.md`](./docs/TESTING_GUIDE.md) | Test scenarios and demo script |

---

## Support & Contributions

**Issues**: Report bugs or request features via GitHub Issues
**Documentation**: See `docs/` directory for detailed guides
**Architecture**: Review `docs/ARCHITECTURE.md` for system design

---

## License

Copyright © 2026 EPAM Systems. All rights reserved.

---

**Built with ❤️ for secure AI-powered security operations**
