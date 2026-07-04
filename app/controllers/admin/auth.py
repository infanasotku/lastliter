from fastapi import Request
from sqladmin.authentication import AuthenticationBackend

from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


class AdminAuthenticationBackend(AuthenticationBackend):
    """Authentication backend for admin panel."""

    def __init__(self, secret: str, *, username: str, password: str):
        super().__init__(secret)
        self.username = username
        self.password = password

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]

        if not username or not password:
            logger.warning("Admin login failed: missing credentials")
            return False

        if self.username != username:
            logger.warning("Admin login failed: invalid username")
            return False

        if password != self.password:
            logger.warning("Admin login failed: invalid password")
            return False

        request.session["username"] = username
        logger.info("Admin login succeeded: username=%s", username)

        return True

    async def logout(self, request: Request) -> bool:
        logger.info("Admin logout: username=%s", request.session.get("username"))
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        if not request.session:
            logger.warning("Admin authentication failed: session is missing")
            return False

        logger.info("Admin authentication succeeded")
        return True
