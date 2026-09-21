"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path:
    """Find .env file in project root."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return Path(".env")


class Settings(BaseSettings):
    """Main application settings - all configuration in one flat structure."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General settings
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    token_file: Path = Field(
        default=Path("tokens.enc"), description="Path to encrypted token storage"
    )
    encryption_key: SecretStr | None = Field(
        default=None, description="Key for token encryption (auto-generated if not set)"
    )

    # Meta (Facebook/Instagram) settings
    meta_app_id: str = Field(default="", description="Meta App ID")
    meta_app_secret: SecretStr = Field(default="", description="Meta App Secret")
    meta_page_id: str = Field(default="", description="Facebook Page ID")
    meta_instagram_account_id: str = Field(default="", description="Instagram Business Account ID")
    meta_access_token: SecretStr | None = Field(default=None, description="Long-lived access token")
    meta_page_access_token: SecretStr | None = Field(
        default=None, description="Page Access Token (never expires; required to publish)"
    )
    meta_api_version: str = Field(default="v20.0", description="Graph API version")

    # OpenAI settings
    openai_api_key: SecretStr = Field(default="", description="OpenAI API key")
    openai_text_model: str = Field(default="gpt-4", description="Model for text generation")
    openai_image_model: str = Field(default="dall-e-3", description="Model for image generation")
    openai_image_size: Literal["1024x1024", "1792x1024", "1024x1792"] = Field(
        default="1024x1024", description="Generated image size"
    )
    openai_image_quality: Literal["standard", "hd"] = Field(
        default="standard", description="Generated image quality"
    )

    # Cloudinary settings
    cloudinary_cloud_name: str = Field(default="", description="Cloudinary cloud name")
    cloudinary_api_key: str = Field(default="", description="Cloudinary API key")
    cloudinary_api_secret: SecretStr = Field(default="", description="Cloudinary API secret")
    cloudinary_upload_folder: str = Field(default="auto_posting", description="Upload folder name")

    @computed_field
    @property
    def meta_graph_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.meta_api_version}"


# Backward-compatible nested access
class MetaSettings:
    """Wrapper for Meta settings access."""
    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def app_id(self) -> str:
        return self._s.meta_app_id

    @property
    def app_secret(self) -> SecretStr:
        return self._s.meta_app_secret

    @property
    def page_id(self) -> str:
        return self._s.meta_page_id

    @property
    def instagram_account_id(self) -> str:
        return self._s.meta_instagram_account_id

    @property
    def access_token(self) -> SecretStr | None:
        return self._s.meta_access_token

    @property
    def page_access_token(self) -> SecretStr | None:
        return self._s.meta_page_access_token

    @property
    def api_version(self) -> str:
        return self._s.meta_api_version

    @property
    def graph_api_base(self) -> str:
        return self._s.meta_graph_api_base


class OpenAISettings:
    """Wrapper for OpenAI settings access."""
    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def api_key(self) -> SecretStr:
        return self._s.openai_api_key

    @property
    def text_model(self) -> str:
        return self._s.openai_text_model

    @property
    def image_model(self) -> str:
        return self._s.openai_image_model

    @property
    def image_size(self) -> str:
        return self._s.openai_image_size

    @property
    def image_quality(self) -> str:
        return self._s.openai_image_quality


class CloudinarySettings:
    """Wrapper for Cloudinary settings access."""
    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def cloud_name(self) -> str:
        return self._s.cloudinary_cloud_name

    @property
    def api_key(self) -> str:
        return self._s.cloudinary_api_key

    @property
    def api_secret(self) -> SecretStr:
        return self._s.cloudinary_api_secret

    @property
    def upload_folder(self) -> str:
        return self._s.cloudinary_upload_folder


class SettingsWrapper:
    """Wrapper providing nested access to settings."""
    def __init__(self, settings: Settings):
        self._settings = settings
        self.meta = MetaSettings(settings)
        self.openai = OpenAISettings(settings)
        self.cloudinary = CloudinarySettings(settings)

    def __getattr__(self, name: str):
        return getattr(self._settings, name)


def get_settings() -> SettingsWrapper:
    """Get application settings with nested access."""
    return SettingsWrapper(Settings())
