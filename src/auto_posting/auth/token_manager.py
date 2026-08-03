"""OAuth token management for Meta Graph API."""

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

import httpx
from cryptography.fernet import Fernet

from auto_posting.config import Settings


class TokenData(TypedDict):
    """Token data structure."""

    access_token: str
    token_type: str
    expires_at: str  # ISO format datetime
    page_access_token: str | None


class TokenManager:
    """Manages OAuth tokens with encryption and automatic refresh."""

    REFRESH_THRESHOLD_DAYS = 7  # Refresh if expiring within 7 days

    def __init__(self, settings: Settings):
        self.settings = settings
        self._http_client: httpx.AsyncClient | None = None
        self._fernet = self._init_encryption()
        self._token_data: TokenData | None = None

    def _init_encryption(self) -> Fernet:
        """Initialize Fernet encryption with stored or generated key."""
        if self.settings.encryption_key and self.settings.encryption_key.get_secret_value():
            key_value = self.settings.encryption_key.get_secret_value()
            try:
                return Fernet(key_value.encode())
            except (ValueError, Exception):
                print("Warning: Invalid ENCRYPTION_KEY in .env, generating new one...")

        # Generate a new key if not set or invalid
        key = Fernet.generate_key()
        print(f"Generated encryption key (add to .env): ENCRYPTION_KEY={key.decode()}")
        return Fernet(key)

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _token_file_path(self) -> Path:
        """Get token file path."""
        return self.settings.token_file

    def _save_tokens(self, token_data: TokenData) -> None:
        """Encrypt and save tokens to file."""
        data = json.dumps(token_data).encode()
        encrypted = self._fernet.encrypt(data)
        self._token_file_path().write_bytes(encrypted)
        self._token_data = token_data

    def _load_tokens(self) -> TokenData | None:
        """Load and decrypt tokens from file."""
        if self._token_data:
            return self._token_data

        path = self._token_file_path()
        if not path.exists():
            return None

        try:
            encrypted = path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            self._token_data = json.loads(decrypted.decode())
            return self._token_data
        except Exception as e:
            print(f"Failed to load tokens: {e}")
            return None

    def _is_token_expiring_soon(self, token_data: TokenData) -> bool:
        """Check if token is expiring within threshold."""
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        threshold = datetime.now() + timedelta(days=self.REFRESH_THRESHOLD_DAYS)
        return expires_at < threshold

    async def exchange_for_long_lived_token(self, short_lived_token: str) -> TokenData:
        """Exchange short-lived token (1 hour) for long-lived token (60 days)."""
        meta = self.settings.meta

        response = await self.http_client.get(
            f"{meta.graph_api_base}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": meta.app_id,
                "client_secret": meta.app_secret.get_secret_value(),
                "fb_exchange_token": short_lived_token,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise ValueError(f"Token exchange failed: {data['error']}")

        # Long-lived tokens last 60 days
        expires_at = datetime.now() + timedelta(days=60)

        token_data: TokenData = {
            "access_token": data["access_token"],
            "token_type": data.get("token_type", "bearer"),
            "expires_at": expires_at.isoformat(),
            "page_access_token": None,
        }

        # Get page access token
        page_token = await self._get_page_access_token(data["access_token"])
        if page_token:
            token_data["page_access_token"] = page_token

        self._save_tokens(token_data)
        return token_data

    async def _get_page_access_token(self, user_access_token: str) -> str | None:
        """Get page access token from user access token."""
        meta = self.settings.meta

        response = await self.http_client.get(
            f"{meta.graph_api_base}/{meta.page_id}",
            params={
                "fields": "access_token",
                "access_token": user_access_token,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        return None

    async def refresh_token(self) -> TokenData | None:
        """Refresh the long-lived token if expiring soon."""
        token_data = self._load_tokens()
        if not token_data:
            return None

        if not self._is_token_expiring_soon(token_data):
            return token_data

        # Long-lived tokens can be refreshed by exchanging them again
        # Only works for tokens that haven't expired yet
        try:
            return await self.exchange_for_long_lived_token(token_data["access_token"])
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return token_data

    async def get_access_token(self) -> str:
        """Get current valid access token, refreshing if needed."""
        token_data = await self.refresh_token()

        if token_data and token_data.get("page_access_token"):
            return token_data["page_access_token"]

        if token_data:
            return token_data["access_token"]

        # Fall back to configured token
        if self.settings.meta.access_token:
            return self.settings.meta.access_token.get_secret_value()

        raise ValueError("No valid access token available. Run setup_oauth.py first.")

    async def get_instagram_token(self) -> str:
        """Get access token for Instagram API calls."""
        # Instagram uses the same page access token
        return await self.get_access_token()

    def generate_oauth_url(self, redirect_uri: str, state: str | None = None) -> str:
        """Generate OAuth authorization URL."""
        meta = self.settings.meta
        state = state or secrets.token_urlsafe(32)

        # Note: pages_manage_posts and instagram_content_publish require:
        # 1. Add these permissions in App Dashboard → Use Cases → Permissions
        # 2. For production: Submit for App Review
        # For development: Works for app developers/admins after adding to app
        params = {
            "client_id": meta.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join([
                "public_profile",
                "pages_show_list",
                "pages_read_engagement",
                "pages_manage_posts",
                "instagram_basic",
                "instagram_content_publish",
            ]),
            "response_type": "code",
        }

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.facebook.com/{meta.api_version}/dialog/oauth?{query}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> TokenData:
        """Exchange authorization code for access token."""
        meta = self.settings.meta

        response = await self.http_client.get(
            f"{meta.graph_api_base}/oauth/access_token",
            params={
                "client_id": meta.app_id,
                "client_secret": meta.app_secret.get_secret_value(),
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise ValueError(f"Code exchange failed: {data['error']}")

        # This returns a short-lived token, exchange for long-lived
        return await self.exchange_for_long_lived_token(data["access_token"])

    async def verify_token(self) -> dict:
        """Verify current token and return debug info."""
        token = await self.get_access_token()
        meta = self.settings.meta

        response = await self.http_client.get(
            f"{meta.graph_api_base}/debug_token",
            params={
                "input_token": token,
                "access_token": f"{meta.app_id}|{meta.app_secret.get_secret_value()}",
            },
        )
        response.raise_for_status()
        return response.json()
