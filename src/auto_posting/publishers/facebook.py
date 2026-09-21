"""Facebook Graph API publisher."""

import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import Settings
from auto_posting.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


@dataclass
class FacebookPost:
    """Published Facebook post data."""

    post_id: str
    created_time: datetime
    permalink: str | None = None


class FacebookPublisher:
    """Publish content to Facebook Page using Graph API."""

    def __init__(self, settings: Settings, token_manager: TokenManager):
        self.settings = settings
        self.token_manager = token_manager
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def api_base(self) -> str:
        return self.settings.meta.graph_api_base

    @property
    def page_id(self) -> str:
        return self.settings.meta.page_id

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def publish_text(
        self,
        message: str,
        link: str | None = None,
    ) -> FacebookPost:
        """
        Publish a text post to Facebook Page.

        Args:
            message: The post text content
            link: Optional link to include

        Returns:
            FacebookPost with post ID and permalink
        """
        access_token = await self.token_manager.get_access_token()

        params = {
            "message": message,
            "access_token": access_token,
        }

        if link:
            params["link"] = link

        logger.info(f"Publishing text post to Facebook Page {self.page_id}")

        response = await self.http_client.post(
            f"{self.api_base}/{self.page_id}/feed",
            data=params,
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Facebook API error: {error.get('message', error)}")

        post_id = data["id"]
        logger.info(f"Published Facebook post: {post_id}")

        # Get permalink
        permalink = await self._get_permalink(post_id, access_token)

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def publish_photo(
        self,
        image_url: str,
        caption: str,
        published: bool = True,
    ) -> FacebookPost:
        """
        Publish a photo post to Facebook Page.

        Args:
            image_url: Public URL of the image
            caption: Photo caption/message
            published: Whether to publish immediately (False = unpublished/draft)

        Returns:
            FacebookPost with post ID and permalink
        """
        access_token = await self.token_manager.get_access_token()

        params = {
            "url": image_url,
            "caption": caption,
            "published": str(published).lower(),
            "access_token": access_token,
        }

        logger.info(f"Publishing photo to Facebook Page {self.page_id}")

        response = await self.http_client.post(
            f"{self.api_base}/{self.page_id}/photos",
            data=params,
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Facebook API error: {error.get('message', error)}")

        post_id = data.get("post_id") or data.get("id")
        logger.info(f"Published Facebook photo: {post_id}")

        permalink = await self._get_permalink(post_id, access_token) if post_id else None

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def publish_photo_file(
        self,
        image_path: str | Path,
        caption: str,
        published: bool = True,
    ) -> FacebookPost:
        """
        Publish a photo from a LOCAL file to Facebook Page.

        Unlike publish_photo(), this uploads the raw bytes as multipart/form-data,
        so the image needs no public URL and no Cloudinary account.

        Args:
            image_path: Path to a local image file
            caption: Photo caption/message
            published: Whether to publish immediately (False = unpublished/draft)

        Returns:
            FacebookPost with post ID and permalink
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        access_token = await self.token_manager.get_access_token()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        logger.info(f"Uploading local photo {path.name} to Facebook Page {self.page_id}")

        response = await self.http_client.post(
            f"{self.api_base}/{self.page_id}/photos",
            data={
                "caption": caption,
                "published": str(published).lower(),
                "access_token": access_token,
            },
            files={"source": (path.name, path.read_bytes(), mime_type)},
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Facebook API error: {error.get('message', error)}")

        post_id = data.get("post_id") or data.get("id")
        logger.info(f"Published Facebook photo: {post_id}")

        permalink = await self._get_permalink(post_id, access_token) if post_id else None

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def publish_video(
        self,
        video_url: str,
        title: str,
        description: str,
    ) -> FacebookPost:
        """
        Publish a video post to Facebook Page.

        Args:
            video_url: Public URL of the video
            title: Video title
            description: Video description

        Returns:
            FacebookPost with post ID
        """
        access_token = await self.token_manager.get_access_token()

        params = {
            "file_url": video_url,
            "title": title,
            "description": description,
            "access_token": access_token,
        }

        logger.info(f"Publishing video to Facebook Page {self.page_id}")

        response = await self.http_client.post(
            f"{self.api_base}/{self.page_id}/videos",
            data=params,
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Facebook API error: {error.get('message', error)}")

        post_id = data.get("id")
        logger.info(f"Published Facebook video: {post_id}")

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
        )

    async def publish_carousel(
        self,
        image_urls: list[str],
        caption: str,
    ) -> FacebookPost:
        """
        Publish a multi-photo (carousel) post.

        Args:
            image_urls: List of public image URLs (max 10)
            caption: Post caption

        Returns:
            FacebookPost with post ID
        """
        if len(image_urls) > 10:
            raise ValueError("Maximum 10 images allowed in carousel")

        access_token = await self.token_manager.get_access_token()

        # Step 1: Upload photos as unpublished
        photo_ids = []
        for url in image_urls:
            response = await self.http_client.post(
                f"{self.api_base}/{self.page_id}/photos",
                data={
                    "url": url,
                    "published": "false",
                    "access_token": access_token,
                },
            )
            data = response.json()
            if "error" in data:
                raise ValueError(f"Failed to upload photo: {data['error']}")
            photo_ids.append(data["id"])

        # Step 2: Create post with attached photos
        attached_media = [{"media_fbid": pid} for pid in photo_ids]

        response = await self.http_client.post(
            f"{self.api_base}/{self.page_id}/feed",
            json={
                "message": caption,
                "attached_media": attached_media,
                "access_token": access_token,
            },
        )

        data = response.json()
        if "error" in data:
            raise ValueError(f"Failed to create carousel post: {data['error']}")

        post_id = data["id"]
        logger.info(f"Published Facebook carousel: {post_id}")

        permalink = await self._get_permalink(post_id, access_token)

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    async def _get_permalink(self, post_id: str, access_token: str) -> str | None:
        """Get permalink for a post."""
        try:
            response = await self.http_client.get(
                f"{self.api_base}/{post_id}",
                params={
                    "fields": "permalink_url",
                    "access_token": access_token,
                },
            )
            data = response.json()
            return data.get("permalink_url")
        except Exception as e:
            logger.warning(f"Failed to get permalink: {e}")
            return None

    async def schedule_post(
        self,
        message: str,
        scheduled_time: datetime,
        image_url: str | None = None,
    ) -> FacebookPost:
        """
        Schedule a post for future publishing.

        Args:
            message: Post message
            scheduled_time: When to publish (must be 10 mins to 6 months in future)
            image_url: Optional image URL

        Returns:
            FacebookPost with scheduled post ID
        """
        access_token = await self.token_manager.get_access_token()

        timestamp = int(scheduled_time.timestamp())

        params = {
            "message": message,
            "published": "false",
            "scheduled_publish_time": timestamp,
            "access_token": access_token,
        }

        endpoint = f"{self.api_base}/{self.page_id}/feed"

        if image_url:
            params["url"] = image_url
            endpoint = f"{self.api_base}/{self.page_id}/photos"

        response = await self.http_client.post(endpoint, data=params)
        data = response.json()

        if "error" in data:
            raise ValueError(f"Failed to schedule post: {data['error']}")

        post_id = data.get("post_id") or data.get("id")
        logger.info(f"Scheduled Facebook post: {post_id} for {scheduled_time}")

        return FacebookPost(
            post_id=post_id,
            created_time=datetime.now(),
        )

    async def delete_post(self, post_id: str) -> bool:
        """Delete a post."""
        access_token = await self.token_manager.get_access_token()

        response = await self.http_client.delete(
            f"{self.api_base}/{post_id}",
            params={"access_token": access_token},
        )

        data = response.json()
        return data.get("success", False)

    async def get_page_insights(
        self,
        metric: Literal["page_impressions", "page_engaged_users", "page_post_engagements"],
        period: Literal["day", "week", "days_28"] = "day",
    ) -> dict:
        """Get page insights/analytics."""
        access_token = await self.token_manager.get_access_token()

        response = await self.http_client.get(
            f"{self.api_base}/{self.page_id}/insights",
            params={
                "metric": metric,
                "period": period,
                "access_token": access_token,
            },
        )

        return response.json()
