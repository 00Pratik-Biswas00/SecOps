# SecOps Nexus - Architecture Flow

```mermaid
flowchart TD
    User([User]) --> Gemini[Gemini Enterprise]
    Gemini --> MCP[MCP Endpoint /mcp<br/>Cloud Run]
    
    MCP --> Auth{JWT Auth<br/>Valid?}
    Auth -->|Valid| Resolve[User Resolution<br/>DB or Email Map]
    
    Resolve --> RBAC{RBAC Check<br/>Permission?}
    RBAC -->|Allowed| OpType{Operation<br/>Type?}
    
    Auth -->|Invalid/Expired| Error1[401 Unauthorized]
    Error1 --> Gemini
    
    RBAC -->|Denied| Error2[403 Forbidden]
    Error2 --> Gemini
    
    OpType -->|Read| ReadService[Finding Service<br/>get_findings<br/>get_details<br/>get_summary]
    OpType -->|Write| WriteService[Finding Service<br/>update_status]
    
    ReadService --> ReadRepo[Finding Repository<br/>SQL Query]
    WriteService --> WriteRepo[Finding Repository<br/>SQL Update]
    
    ReadRepo --> DB[(PostgreSQL<br/>findings<br/>projects<br/>users)]
    WriteRepo --> DB
    
    WriteRepo --> Audit[Audit Service<br/>Create Log]
    Audit --> AuditDB[(audit_logs<br/>immutable)]
    
    DB --> Response[Response JSON]
    AuditDB --> Response
    Response --> Gemini
    Gemini --> User
    
    style User fill:#FFD4E5,stroke:#333,stroke-width:2px,color:#000
    style Gemini fill:#E8DAFF,stroke:#333,stroke-width:2px,color:#000
    style MCP fill:#C2E0FF,stroke:#333,stroke-width:2px,color:#000
    style Auth fill:#FFF4CC,stroke:#333,stroke-width:2px,color:#000
    style Resolve fill:#C2E0FF,stroke:#333,stroke-width:2px,color:#000
    style RBAC fill:#FFF4CC,stroke:#333,stroke-width:2px,color:#000
    style OpType fill:#FFECB3,stroke:#333,stroke-width:2px,color:#000
    style ReadService fill:#C2E0FF,stroke:#333,stroke-width:2px,color:#000
    style WriteService fill:#C2E0FF,stroke:#333,stroke-width:2px,color:#000
    style ReadRepo fill:#D4EDFF,stroke:#333,stroke-width:2px,color:#000
    style WriteRepo fill:#D4EDFF,stroke:#333,stroke-width:2px,color:#000
    style DB fill:#C8F7C5,stroke:#333,stroke-width:2px,color:#000
    style Audit fill:#F3D4FF,stroke:#333,stroke-width:2px,color:#000
    style AuditDB fill:#C8F7C5,stroke:#333,stroke-width:2px,color:#000
    style Response fill:#D7FFD4,stroke:#333,stroke-width:2px,color:#000
    style Error1 fill:#FFCCCC,stroke:#333,stroke-width:2px,color:#000
    style Error2 fill:#FFCCCC,stroke:#333,stroke-width:2px,color:#000
```

## Key Components

### Entry Point
- **User**: Security engineer/viewer/admin
- **Gemini Enterprise**: AI layer at epa.ms/gemini-enterprise
- **MCP Endpoint**: FastMCP server at `/mcp` on Cloud Run

### Security Layer
- **JWT Auth**: HS256 signature validation, expiry check
- **User Resolution**: DB lookup or email-to-role mapping via `USER_ROLE_MAP`
- **RBAC Check**: 3 roles (VIEWER, SECURITY_ENGINEER, SECURITY_ADMIN)

### Service Layer
- **Read Operations**: `get_security_findings`, `get_finding_details`, `get_security_summary`, `get_finding_audit_history`
- **Write Operations**: `update_finding_status` (ENGINEER/ADMIN only)

### Data Layer
- **Finding Repository**: SQLAlchemy async queries
- **PostgreSQL**: 5 tables (findings, projects, users, roles, audit_logs)
- **Audit Service**: Immutable audit trail for every write

### Response
- JSON response with finding data or audit confirmation
- Returns to Gemini → User

---

## 5 MCP Tools

| Tool | Type | Min Role |
|------|------|----------|
| `get_security_findings` | Read | VIEWER |
| `get_finding_details` | Read | VIEWER |
| `get_security_summary` | Read | VIEWER |
| `get_finding_audit_history` | Read | VIEWER |
| `update_finding_status` | Write | SECURITY_ENGINEER |

---

## Error Paths

- **401 Unauthorized**: Invalid/expired/tampered JWT
- **403 Forbidden**: Valid JWT but insufficient role permissions
- **404 Not Found**: Finding/project doesn't exist
- **422 Unprocessable**: Invalid status value (must be OPEN/IN_PROGRESS/RESOLVED)
