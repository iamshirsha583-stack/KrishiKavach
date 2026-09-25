"""
KrishiKavach Auth0 JWT Security & Authentication Module.

Implements Auth0 JSON Web Token (JWT) validation and middleware dependencies
for protecting API endpoints against unauthorized access.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("KrishiKavach.Auth0")

# Optional / conditional JWT import
try:
    import jwt
    from jwt import PyJWKClient
    JWT_AVAILABLE = True
except ImportError:
    try:
        from jose import jwt as jose_jwt
        jwt = jose_jwt  # type: ignore
        PyJWKClient = None  # type: ignore
        JWT_AVAILABLE = True
    except ImportError:
        jwt = None  # type: ignore
        PyJWKClient = None  # type: ignore
        JWT_AVAILABLE = False


# Environment Configuration
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "dev-krishikavach.us.auth0.com")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "https://api.krishikavach.org")
AUTH0_ISSUER = os.getenv("AUTH0_ISSUER", f"https://{AUTH0_DOMAIN}/")
AUTH0_ALGORITHMS = [os.getenv("AUTH0_ALGORITHMS", "RS256")]
AUTH0_DEV_MODE = os.getenv("AUTH0_DEV_MODE", "true").lower() in ("true", "1", "yes")

# HTTP Bearer Scheme
security = HTTPBearer(auto_error=False)


class Auth0Verifier:
    """Verifies Auth0 RS256 JWT tokens using the JWKS endpoint."""

    def __init__(
        self,
        domain: str = AUTH0_DOMAIN,
        audience: str = AUTH0_AUDIENCE,
        issuer: str = AUTH0_ISSUER,
        algorithms: Optional[List[str]] = None,
        dev_mode: bool = AUTH0_DEV_MODE,
    ):
        self.domain = domain
        self.audience = audience
        self.issuer = issuer
        self.algorithms = algorithms or ["RS256"]
        self.dev_mode = dev_mode
        self.jwks_url = f"https://{self.domain}/.well-known/jwks.json"
        self._jwks_cache: Optional[Dict[str, Any]] = None

    def _fetch_jwks(self) -> Dict[str, Any]:
        """Fetches and caches the JSON Web Key Set (JWKS) from Auth0."""
        if self._jwks_cache is not None:
            return self._jwks_cache

        try:
            req = urllib.request.Request(self.jwks_url, headers={"User-Agent": "KrishiKavach-Auth"})
            with urllib.request.urlopen(req, timeout=5) as response:
                self._jwks_cache = json.loads(response.read().decode("utf-8"))
                return self._jwks_cache
        except Exception as e:
            logger.warning(f"Could not fetch Auth0 JWKS from {self.jwks_url}: {e}")
            return {"keys": []}

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Validates the RS256 JWT signature and claims.

        :param token: Raw Bearer JWT string.
        :return: Decoded token payload dictionary.
        :raises HTTPException: If the token is invalid, expired, or untrusted.
        """
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Allow development bypass tokens in dev mode
        if self.dev_mode and (token in ("dev-token", "demo-token", "test-token") or token.startswith("mock-")):
            logger.info("Auth0 dev mode: Accepted mock/development bearer token.")
            return {
                "sub": "auth0|mock_admin_user",
                "scope": "read:scans write:scans trigger:pipeline",
                "permissions": ["trigger:pipeline", "read:scans"],
                "dev_mode": True,
            }

        if not JWT_AVAILABLE:
            if self.dev_mode:
                logger.warning("PyJWT not installed. Accepting token in development fallback mode.")
                return {"sub": "auth0|anonymous_user", "dev_mode": True}
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT verification library is not installed on server",
            )

        try:
            # 1. Decode header to find Key ID (kid)
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            # 2. Match kid against Auth0 JWKS public keys
            jwks = self._fetch_jwks()
            rsa_key = {}
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = {
                        "kty": key.get("kty"),
                        "kid": key.get("kid"),
                        "use": key.get("use"),
                        "n": key.get("n"),
                        "e": key.get("e"),
                    }
                    break

            if rsa_key:
                # 3. Decode & verify token with public RSA key
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=self.algorithms,
                    audience=self.audience,
                    issuer=self.issuer,
                )
                return payload
            elif self.dev_mode:
                logger.warning("Key ID not matched in JWKS. Accepting in dev mode.")
                # Unverified decode for dev inspection
                payload = jwt.decode(token, options={"verify_signature": False})
                return payload
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token key ID or signing key not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as e:
            if self.dev_mode:
                logger.warning(f"JWT verification error ({e}). Bypassing in dev mode.")
                return {"sub": "auth0|dev_fallback_user", "dev_mode": True}
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            if self.dev_mode:
                logger.warning(f"Unexpected token error ({e}). Bypassing in dev mode.")
                return {"sub": "auth0|dev_fallback_user", "dev_mode": True}
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication error: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Singleton verifier instance
auth0_verifier = Auth0Verifier()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """FastAPI Dependency for verifying Auth0 JWT on protected endpoints."""
    if credentials is None:
        if auth0_verifier.dev_mode:
            logger.info("No credentials provided. Granting anonymous dev access in dev mode.")
            return {"sub": "auth0|dev_guest", "scope": "all", "dev_mode": True}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid Bearer format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    return auth0_verifier.verify_token(token)


async def verify_jwt_token(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Convenience alias dependency to enforce Auth0 JWT check."""
    return user
