"""Media uploader for Cloudinary (required for Instagram API)."""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Literal

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from auto_posting.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class UploadedMedia:
    """Uploaded media information."""

    public_id: str
    url: str
    secure_url: str
    format: str
    width: int
    height: int
    resource_type: str
    created_at: datetime

    @property
    def instagram_url(self) -> str:
        """Get URL suitable for Instagram API (must be publicly accessible HTTPS)."""
        return self.secure_url


class MediaUploader:
    """Upload media to Cloudinary for public URL access."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._configured = False

    def _configure(self) -> None:
        """Configure Cloudinary SDK."""
        if self._configured:
            return

        cloudinary.config(
            cloud_name=self.settings.cloudinary.cloud_name,
            api_key=self.settings.cloudinary.api_key,
            api_secret=self.settings.cloudinary.api_secret.get_secret_value(),
            secure=True,
        )
        self._configured = True

    def upload_bytes(
        self,
        image_bytes: bytes,
        filename: str | None = None,
        resource_type: Literal["image", "video", "raw"] = "image",
    ) -> UploadedMedia:
        """
        Upload image bytes to Cloudinary.

        Args:
            image_bytes: Raw image bytes
            filename: Optional filename for the upload
            resource_type: Type of resource

        Returns:
            UploadedMedia with public URLs
        """
        self._configure()

        # Generate unique filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"post_{timestamp}"

        public_id = f"{self.settings.cloudinary.upload_folder}/{filename}"

        logger.info(f"Uploading to Cloudinary: {public_id}")
        logger.info(f"Cloudinary config: cloud_name={self.settings.cloudinary.cloud_name}")
        logger.info(f"Image bytes size: {len(image_bytes)}")

        if len(image_bytes) == 0:
            raise ValueError("Cannot upload empty image")

        # Use BytesIO file-like object for upload
        file_obj = BytesIO(image_bytes)
        file_obj.seek(0)  # Ensure we're at the beginning

        result = cloudinary.uploader.upload(
            file_obj,
            public_id=public_id,
            resource_type=resource_type,
            overwrite=True,
            invalidate=True,  # Invalidate CDN cache if exists
        )

        uploaded = UploadedMedia(
            public_id=result["public_id"],
            url=result["url"],
            secure_url=result["secure_url"],
            format=result["format"],
            width=result["width"],
            height=result["height"],
            resource_type=result["resource_type"],
            created_at=datetime.fromisoformat(
                result["created_at"].replace("Z", "+00:00")
            ),
        )

        logger.info(f"Upload successful: {uploaded.secure_url}")
        return uploaded

    def upload_url(
        self,
        image_url: str,
        filename: str | None = None,
    ) -> UploadedMedia:
        """
        Upload image from URL to Cloudinary.

        Args:
            image_url: URL of the image to upload
            filename: Optional filename for the upload

        Returns:
            UploadedMedia with public URLs
        """
        self._configure()

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"post_{timestamp}"

        public_id = f"{self.settings.cloudinary.upload_folder}/{filename}"

        logger.info(f"Uploading from URL to Cloudinary: {public_id}")

        result = cloudinary.uploader.upload(
            image_url,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
        )

        return UploadedMedia(
            public_id=result["public_id"],
            url=result["url"],
            secure_url=result["secure_url"],
            format=result["format"],
            width=result["width"],
            height=result["height"],
            resource_type=result["resource_type"],
            created_at=datetime.fromisoformat(
                result["created_at"].replace("Z", "+00:00")
            ),
        )

    def get_optimized_url(
        self,
        public_id: str,
        width: int | None = None,
        height: int | None = None,
        crop: str = "fill",
        quality: str = "auto",
        format_type: str = "auto",
    ) -> str:
        """
        Get optimized URL for an uploaded image.

        Args:
            public_id: The Cloudinary public ID
            width: Target width (optional)
            height: Target height (optional)
            crop: Crop mode (fill, fit, scale, etc.)
            quality: Quality setting (auto, best, good, eco, low)
            format_type: Output format (auto, jpg, png, webp)

        Returns:
            Optimized image URL
        """
        self._configure()

        transformations = {
            "quality": quality,
            "fetch_format": format_type,
        }

        if width:
            transformations["width"] = width
        if height:
            transformations["height"] = height
        if width or height:
            transformations["crop"] = crop

        url, _ = cloudinary_url(public_id, **transformations)
        return url

    def delete(self, public_id: str) -> bool:
        """
        Delete an uploaded media file.

        Args:
            public_id: The Cloudinary public ID

        Returns:
            True if deleted successfully
        """
        self._configure()

        logger.info(f"Deleting from Cloudinary: {public_id}")

        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"

    def upload_video(
        self,
        video_bytes: bytes,
        filename: str | None = None,
    ) -> UploadedMedia:
        """
        Upload video bytes to Cloudinary.

        Args:
            video_bytes: Raw video bytes
            filename: Optional filename for the upload

        Returns:
            UploadedMedia with public URLs
        """
        return self.upload_bytes(video_bytes, filename, resource_type="video")
