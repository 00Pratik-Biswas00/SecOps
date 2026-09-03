from app.models.user import User

VALID_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
VALID_SCAN_TYPES = {"SAST", "SECRETS", "DEPENDENCY", "LINT"}

# Permissions per role
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "VIEWER": {"read_findings", "read_audit"},
    "SECURITY_ENGINEER": {"read_findings", "read_audit", "update_finding"},
    "SECURITY_ADMIN": {"read_findings", "read_audit", "update_finding"},
}


class AuthorizationService:

    def can(self, user: User, permission: str) -> bool:
        role_name = user.role.name if user.role else ""
        allowed = _ROLE_PERMISSIONS.get(role_name, set())
        return permission in allowed

    def require(self, user: User, permission: str) -> None:
        if not self.can(user, permission):
            raise PermissionError(
                f"Role '{user.role.name if user.role else 'unknown'}' "
                f"does not have permission '{permission}'."
            )

    @staticmethod
    def validate_status(status: str) -> str:
        upper = status.upper()
        if upper not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}")
        return upper
