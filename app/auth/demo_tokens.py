"""
Issue demo JWT tokens for the three seeded users.
Run directly:  python -m app.auth.demo_tokens
"""

from app.auth.jwt import create_token

DEMO_USERS = [
    {
        "user_id": "user-viewer-00000-0000-000000000001",
        "username": "alice_viewer",
        "email": "alice@secureorg.internal",
        "role": "VIEWER",
    },
    {
        "user_id": "user-seceng-0000-0000-000000000002",
        "username": "bob_engineer",
        "email": "bob@secureorg.internal",
        "role": "SECURITY_ENGINEER",
    },
    {
        "user_id": "user-admin-00000-0000-000000000003",
        "username": "carol_admin",
        "email": "carol@secureorg.internal",
        "role": "SECURITY_ADMIN",
    },
]


def get_demo_tokens() -> dict[str, str]:
    return {
        u["username"]: create_token(u["user_id"], u["username"], u["role"], u["email"])
        for u in DEMO_USERS
    }


if __name__ == "__main__":
    from app.cli.output import CYAN, DIM, RED, YELLOW, banner, blank, c, ok, section
    from app.config import get_settings

    settings = get_settings()

    ROLE_COLORS = {"VIEWER": CYAN, "SECURITY_ENGINEER": YELLOW, "SECURITY_ADMIN": RED}

    tokens = get_demo_tokens()
    banner("Enterprise Security Findings Connector", "Demo JWT Tokens")
    section(f"Tokens  (expiry: {settings.jwt_expiry_minutes} min each)")
    blank()
    for u in DEMO_USERS:
        token = tokens[u["username"]]
        color = ROLE_COLORS.get(u["role"], "")
        print(f"      {c(u['email']+':', DIM):<52}  {c(u['role'], color)}")
        print(f"      {c(token[:72] + '...', DIM)}")
        blank()
    ok("Tokens ready — use as:  Authorization: Bearer <token>")
    blank()
