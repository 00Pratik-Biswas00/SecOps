import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.findings import router as findings_router
from app.api.projects import router as projects_router
from app.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Enterprise Security Connector starting up")
    yield
    logger.info("Enterprise Security Connector shutting down")


app = FastAPI(
    title="Enterprise Security Findings Connector",
    description="Secure connector for querying and updating enterprise security findings",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects on trailing slashes
)

_cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["GET", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(findings_router)
app.include_router(projects_router)

# Gemini Enterprise connects via HTTPS /mcp (Streamable HTTP MCP)
# stdio still works locally — this adds the remote transport on top
from app.mcp.tools import mcp as mcp_server  # noqa: E402

# Mount FastMCP at /sse for SSE-based MCP communication
app.mount("/sse", mcp_server.streamable_http_app())


# MCP JSON-RPC endpoint for tool discovery (what Discovery Engine calls)
from fastapi import Body, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any


@app.post("/mcp")
async def mcp_json_rpc(body: Dict[str, Any] = Body(...), request: Request = None):
    """
    MCP JSON-RPC endpoint - implements MCP protocol handshake and tool discovery.
    Handles: initialize, notifications/initialized, tools/list
    For runtime MCP communication with tool execution, use /sse (FastMCP streamable HTTP).
    """
    jsonrpc_id = body.get("id", 1)
    method = body.get("method", "")

    # Step 1: MCP handshake - initialize
    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "enterprise-security-connector",
                        "version": "1.0.0",
                    },
                },
            }
        )

    # Step 2: MCP handshake - notifications/initialized (no response needed)
    if method == "notifications/initialized":
        # Notification - no response per JSON-RPC 2.0 spec
        return JSONResponse({"jsonrpc": "2.0"}, status_code=204)

    # Step 3: Tool discovery - tools/list
    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {
                    "tools": [
                        {
                            "name": "get_security_findings",
                            "description": "List security findings for a project. Supports filtering by severity (CRITICAL, HIGH, MEDIUM, LOW, INFO), status (OPEN, IN_PROGRESS, RESOLVED), and scan_type (SAST, SECRETS, DEPENDENCY, LINT).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "project_id": {
                                        "type": "string",
                                        "description": "The project ID or project name to query findings for (e.g., 'payment-api-prod' or 'proj-payment-api')",
                                    },
                                    "severity": {
                                        "type": "string",
                                        "description": "Filter by severity: CRITICAL, HIGH, MEDIUM, LOW, INFO",
                                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                                    },
                                    "status": {
                                        "type": "string",
                                        "description": "Filter by status: OPEN, IN_PROGRESS, RESOLVED",
                                        "enum": ["OPEN", "IN_PROGRESS", "RESOLVED"],
                                    },
                                    "scan_type": {
                                        "type": "string",
                                        "description": "Filter by scan type: SAST, SECRETS, DEPENDENCY, LINT",
                                        "enum": ["SAST", "SECRETS", "DEPENDENCY", "LINT"],
                                    },
                                    "limit": {
                                        "type": "integer",
                                        "description": "Maximum number of findings to return (1-200, default 50)",
                                        "minimum": 1,
                                        "maximum": 200,
                                        "default": 50,
                                    },
                                },
                                "required": ["project_id"],
                            },
                        },
                        {
                            "name": "get_finding_details",
                            "description": "Get full details for a single finding including description, file path, line number, and remediation guidance.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "finding_id": {
                                        "type": "string",
                                        "description": "The unique ID of the finding to retrieve",
                                    },
                                },
                                "required": ["finding_id"],
                            },
                        },
                        {
                            "name": "get_security_summary",
                            "description": "Get aggregated security summary for a project: total findings, counts by severity (CRITICAL, HIGH, MEDIUM, LOW, INFO) and status (OPEN, IN_PROGRESS, RESOLVED).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "project_id": {
                                        "type": "string",
                                        "description": "The project ID or project name to get summary for (e.g., 'payment-api-prod' or 'proj-payment-api')",
                                    },
                                },
                                "required": ["project_id"],
                            },
                        },
                        {
                            "name": "update_finding_status",
                            "description": "Update the status of a finding. Requires SECURITY_ENGINEER or SECURITY_ADMIN role. Creates an immutable audit record. Valid statuses: OPEN, IN_PROGRESS, RESOLVED.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "finding_id": {
                                        "type": "string",
                                        "description": "The unique ID of the finding to update",
                                    },
                                    "status": {
                                        "type": "string",
                                        "description": "New status: OPEN, IN_PROGRESS, RESOLVED",
                                        "enum": ["OPEN", "IN_PROGRESS", "RESOLVED"],
                                    },
                                },
                                "required": ["finding_id", "status"],
                            },
                        },
                        {
                            "name": "get_finding_audit_history",
                            "description": "View the complete audit history for a finding: who changed it, when, what was changed (old value vs new value).",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "finding_id": {
                                        "type": "string",
                                        "description": "The unique ID of the finding to get history for",
                                    },
                                },
                                "required": ["finding_id"],
                            },
                        },
                    ]
                },
            }
        )

    # Step 4: Tool execution - tools/call
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            # Import necessary modules for direct service calls
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            from app.database import get_db
            from app.services.finding_service import FindingService
            from app.auth.email_role import get_role_for_email
            from app.auth.dependencies import _synthetic_user
            from app.api.schemas import FindingStatus, Severity, ScanType, ProjectSummaryResponse
            import json

            # Extract user identity from request headers (set by Cloud Run/Discovery Engine)
            # Discovery Engine authenticates via OIDC at Cloud Run level
            email = None
            user_id = None

            # Log all headers for debugging
            logger.info(f"MCP tools/call request headers: {dict(request.headers)}")

            # Check for Google-authenticated user email header
            auth_user_header = request.headers.get("x-goog-authenticated-user-email", "")
            if auth_user_header:
                logger.info(f"Found x-goog-authenticated-user-email: {auth_user_header}")
                if auth_user_header.startswith("accounts.google.com:"):
                    email = auth_user_header.split(":", 1)[1].strip().lower()
                    user_id = email
                    logger.info(f"Authenticated user from header: {email}")

            # Check for IAP email header (alternative)
            if not email:
                iap_email = request.headers.get("x-goog-iap-jwt-assertion", "")
                if iap_email:
                    logger.info(f"Found x-goog-iap-jwt-assertion header")
                    try:
                        # Decode IAP JWT
                        iap_info = id_token.verify_oauth2_token(
                            iap_email,
                            google_requests.Request(),
                            audience=None
                        )
                        email = iap_info.get("email", "").strip().lower()
                        user_id = iap_info.get("sub", email)
                        logger.info(f"Authenticated user from IAP: {email}")
                    except Exception as e:
                        logger.warning(f"IAP JWT validation failed: {e}")

            # Fallback: try to decode Authorization header if present
            if not email:
                # Check standard authorization header
                auth_header = request.headers.get("authorization", "")
                # Also check x-serverless-authorization (used by Discovery Engine)
                if not auth_header or auth_header == "Bearer":
                    auth_header = request.headers.get("x-serverless-authorization", "")

                if auth_header.startswith("Bearer ") or auth_header.startswith("bearer "):
                    token = auth_header.split(" ", 1)[1] if " " in auth_header else ""
                    if token:
                        logger.info(f"Found Authorization Bearer token (length: {len(token)})")
                        try:
                            id_info = id_token.verify_oauth2_token(
                                token,
                                google_requests.Request(),
                                audience=None
                            )
                            email = id_info.get("email", "").strip().lower()
                            user_id = id_info.get("sub", email)
                            logger.info(f"Authenticated user from token: {email}")
                        except Exception as e:
                            logger.warning(f"Token validation failed: {e}")

            # TEMPORARY: For hackathon/testing, use a default test user if no auth found
            if not email:
                logger.warning("No authentication found, using default test user for hackathon")
                email = "test@epam.com"  # Default test user
                user_id = "test-user-001"
                username = "test"

            username = email.split("@")[0] if email else "unknown"

            # Get role for user (default to VIEWER for testing)
            role_name = get_role_for_email(email)
            if not role_name:
                logger.warning(f"No role found for {email}, defaulting to VIEWER")
                role_name = "VIEWER"

            logger.info(f"Creating synthetic user: email={email}, role={role_name}")
            user = _synthetic_user(user_id, username, email, role_name)

            # Get database session
            async for db in get_db():
                service = FindingService(db)

                # Helper: resolve project name to project ID
                async def resolve_project_id(name_or_id: str) -> str:
                    """Resolve project name or ID to actual project ID"""
                    from sqlalchemy import text
                    # Try direct ID lookup first
                    result = await db.execute(
                        text("SELECT id FROM projects WHERE id = :val OR name = :val LIMIT 1"),
                        {"val": name_or_id}
                    )
                    row = result.fetchone()
                    return row[0] if row else name_or_id  # Return original if not found

                if tool_name == "get_security_findings":
                    # Convert limit to integer if provided as string
                    limit_value = arguments.get("limit", 50)
                    if isinstance(limit_value, str):
                        try:
                            limit_value = int(limit_value)
                        except ValueError:
                            limit_value = 50

                    # Resolve project name to ID
                    project_input = arguments.get("project_id")
                    resolved_project_id = await resolve_project_id(project_input)

                    findings = await service.get_findings(
                        project_id=resolved_project_id,
                        severity=arguments.get("severity"),  # Pass as string, not enum
                        status=arguments.get("status"),
                        scan_type=arguments.get("scan_type"),
                        limit=limit_value
                    )
                    # Convert Finding models to dicts
                    result = [
                        {
                            "id": f.id,
                            "title": f.title,
                            "severity": f.severity,
                            "status": f.status,
                            "scan_type": f.scan_type,
                            "project_id": f.project_id,
                            "created_at": str(f.created_at),
                            "updated_at": str(f.updated_at),
                        }
                        for f in findings
                    ]

                elif tool_name == "get_finding_details":
                    finding = await service.get_finding(finding_id=arguments.get("finding_id"))
                    result = {
                        "id": finding.id,
                        "title": finding.title,
                        "description": finding.description,
                        "severity": finding.severity,
                        "status": finding.status,
                        "scan_type": finding.scan_type,
                        "file_path": finding.file_path,
                        "line_number": finding.line_number,
                        "remediation": finding.remediation,
                        "project_id": finding.project_id,
                        "created_at": str(finding.created_at),
                        "updated_at": str(finding.updated_at),
                    }

                elif tool_name == "get_security_summary":
                    # Resolve project name to ID
                    project_input = arguments.get("project_id")
                    resolved_project_id = await resolve_project_id(project_input)

                    summary_dict = await service.get_summary(resolved_project_id)
                    if summary_dict["project_name"] is None:
                        result = {"error": f"Project '{project_input}' not found"}
                    else:
                        result = summary_dict

                elif tool_name == "update_finding_status":
                    # update_status takes 'actor' parameter, not 'user'
                    finding = await service.update_status(
                        finding_id=arguments.get("finding_id"),
                        new_status=arguments.get("status"),  # Pass as string
                        actor=user
                    )
                    result = {
                        "id": finding.id,
                        "status": finding.status,
                        "updated_at": str(finding.updated_at),
                        "message": "Status updated successfully"
                    }

                elif tool_name == "get_finding_audit_history":
                    audit_entries = await service.get_audit_history(
                        finding_id=arguments.get("finding_id")
                    )
                    result = [
                        {
                            "id": entry.id,
                            "finding_id": entry.finding_id,
                            "user_id": entry.user_id,
                            "action": entry.action,
                            "resource_type": entry.resource_type,
                            "old_value": entry.old_value,
                            "new_value": entry.new_value,
                            "timestamp": str(entry.timestamp),
                        }
                        for entry in audit_entries
                    ]

                else:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": jsonrpc_id,
                            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                        }
                    )

                # Return successful result as JSON string
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": jsonrpc_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, indent=2, default=str)
                                }
                            ]
                        }
                    }
                )

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": jsonrpc_id,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
            )

    # For other methods, return error
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        },
        status_code=200,  # JSON-RPC errors use 200 with error in body
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "enterprise-security-connector"}


@app.get("/debug/db-status")
async def debug_database_status():
    """Temporary debug endpoint to verify database contents"""
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            # Count records
            project_count = await session.scalar(text("SELECT COUNT(*) FROM projects"))
            finding_count = await session.scalar(text("SELECT COUNT(*) FROM findings"))

            # Get sample projects
            projects_result = await session.execute(text("SELECT id, name FROM projects LIMIT 5"))
            projects = [{"id": row[0], "name": row[1]} for row in projects_result.fetchall()]

            # Get payment-api-prod findings
            payment_result = await session.execute(
                text("SELECT id, title, severity FROM findings WHERE project_id = 'payment-api-prod' LIMIT 3")
            )
            payment_findings = [
                {"id": row[0], "title": row[1], "severity": row[2]}
                for row in payment_result.fetchall()
            ]

            # Get findings by actual project IDs
            findings_by_proj = await session.execute(
                text("SELECT project_id, COUNT(*) as cnt FROM findings GROUP BY project_id")
            )
            findings_count_by_proj = {row[0]: row[1] for row in findings_by_proj.fetchall()}

            return {
                "total_projects": project_count,
                "total_findings": finding_count,
                "sample_projects": projects,
                "payment_api_findings": payment_findings,
                "findings_per_project": findings_count_by_proj
            }
    except Exception as e:
        import traceback
        return {"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}
