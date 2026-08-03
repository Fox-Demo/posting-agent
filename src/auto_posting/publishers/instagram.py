"""Instagram Graph API publisher with two-step publishing flow."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

import httpx

from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import Settings
from auto_posting.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ContainerStatus(Enum):
    """Instagram media container status."""

    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"


@dataclass
class InstagramPost:
    """Published Instagram post data."""

    media_id: str
    created_time: datetime
    permalink: str | None = None


class InstagramPublisher:
    """
    Publish content to Instagram using Graph API.

    Instagram requires a two-step publishing process:
    1. Create a media container (upload)
    2. Publish the container (make it live)

    Images must be publicly accessible URLs (use MediaUploader first).
    """

    # Instagram API limitations
    MAX_HASHTAGS = 5
    MAX_CAROUSEL_ITEMS = 10
    CONTAINER_POLL_INTERVAL = 5  # seconds
    CONTAINER_POLL_TIMEOUT = 300  # 5 minutes max

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
    def instagram_account_id(self) -> str:
        return self.settings.meta.instagram_account_id

    def _truncate_hashtags(self, caption: str) -> str:
        """Ensure caption has at most MAX_HASHTAGS hashtags."""
        parts = caption.split()
        hashtags = [p for p in parts if p.startswith("#")]

        if len(hashtags) <= self.MAX_HASHTAGS:
            return caption

        # Keep only first MAX_HASHTAGS
        hashtags_to_remove = hashtags[self.MAX_HASHTAGS:]
        result_parts = [p for p in parts if p not in hashtags_to_remove]
        return " ".join(result_parts)

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def _create_container(
        self,
        image_url: str,
        caption: str,
        media_type: Literal["IMAGE", "VIDEO", "REELS"] = "IMAGE",
        is_carousel_item: bool = False,
    ) -> str:
        """
        Step 1: Create a media container.

        Args:
            image_url: Publicly accessible HTTPS URL
            caption: Post caption (ignored for carousel items)
            media_type: Type of media
            is_carousel_item: Whether this is part of a carousel

        Returns:
            Container ID
        """
        access_token = await self.token_manager.get_instagram_token()

        params = {
            "access_token": access_token,
        }

        if media_type == "VIDEO" or media_type == "REELS":
            params["media_type"] = media_type
            params["video_url"] = image_url
        else:
            params["image_url"] = image_url

        if is_carousel_item:
            params["is_carousel_item"] = "true"
        else:
            params["caption"] = self._truncate_hashtags(caption)

        logger.info(f"Creating Instagram container for {media_type}")

        response = await self.http_client.post(
            f"{self.api_base}/{self.instagram_account_id}/media",
            data=params,
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Instagram API error: {error.get('message', error)}")

        container_id = data["id"]
        logger.info(f"Created container: {container_id}")
        return container_id

    async def _check_container_status(self, container_id: str) -> ContainerStatus:
        """Check the status of a media container."""
        access_token = await self.token_manager.get_instagram_token()

        response = await self.http_client.get(
            f"{self.api_base}/{container_id}",
            params={
                "fields": "status_code,status",
                "access_token": access_token,
            },
        )

        data = response.json()
        status_code = data.get("status_code", "IN_PROGRESS")

        try:
            return ContainerStatus(status_code)
        except ValueError:
            logger.warning(f"Unknown status code: {status_code}")
            return ContainerStatus.IN_PROGRESS

    async def _wait_for_container(self, container_id: str) -> None:
        """Wait for container to be ready for publishing."""
        elapsed = 0

        while elapsed < self.CONTAINER_POLL_TIMEOUT:
            status = await self._check_container_status(container_id)

            if status == ContainerStatus.FINISHED:
                logger.info(f"Container {container_id} ready")
                return
            elif status == ContainerStatus.ERROR:
                raise ValueError(f"Container {container_id} failed processing")
            elif status == ContainerStatus.EXPIRED:
                raise ValueError(f"Container {container_id} expired")

            logger.debug(f"Container status: {status.value}, waiting...")
            await asyncio.sleep(self.CONTAINER_POLL_INTERVAL)
            elapsed += self.CONTAINER_POLL_INTERVAL

        raise TimeoutError(f"Container {container_id} not ready after {elapsed}s")

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    async def _publish_container(self, container_id: str) -> str:
        """
        Step 2: Publish a media container.

        Args:
            container_id: The container ID from step 1

        Returns:
            Published media ID
        """
        access_token = await self.token_manager.get_instagram_token()

        response = await self.http_client.post(
            f"{self.api_base}/{self.instagram_account_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": access_token,
            },
        )

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise ValueError(f"Instagram publish error: {error.get('message', error)}")

        media_id = data["id"]
        logger.info(f"Published Instagram post: {media_id}")
        return media_id

    async def _get_permalink(self, media_id: str) -> str | None:
        """Get permalink for a published post."""
        try:
            access_token = await self.token_manager.get_instagram_token()

            response = await self.http_client.get(
                f"{self.api_base}/{media_id}",
                params={
                    "fields": "permalink",
                    "access_token": access_token,
                },
            )
            data = response.json()
            return data.get("permalink")
        except Exception as e:
            logger.warning(f"Failed to get permalink: {e}")
            return None

    async def publish_image(
        self,
        image_url: str,
        caption: str,
    ) -> InstagramPost:
        """
        Publish a single image post.

        Args:
            image_url: Publicly accessible HTTPS URL of the image
            caption: Post caption with optional hashtags (max 5)

        Returns:
            InstagramPost with media ID and permalink
        """
        # Step 1: Create container
        container_id = await self._create_container(image_url, caption)

        # Step 2: Wait for processing
        await self._wait_for_container(container_id)

        # Step 3: Publish
        media_id = await self._publish_container(container_id)

        # Get permalink
        permalink = await self._get_permalink(media_id)

        return InstagramPost(
            media_id=media_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    async def publish_video(
        self,
        video_url: str,
        caption: str,
        media_type: Literal["VIDEO", "REELS"] = "VIDEO",
    ) -> InstagramPost:
        """
        Publish a video post or Reel.

        Args:
            video_url: Publicly accessible HTTPS URL of the video
            caption: Post caption
            media_type: VIDEO for feed video, REELS for Reels

        Returns:
            InstagramPost with media ID
        """
        container_id = await self._create_container(
            video_url, caption, media_type=media_type
        )
        await self._wait_for_container(container_id)
        media_id = await self._publish_container(container_id)
        permalink = await self._get_permalink(media_id)

        return InstagramPost(
            media_id=media_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    async def publish_carousel(
        self,
        image_urls: list[str],
        caption: str,
    ) -> InstagramPost:
        """
        Publish a carousel (multi-image) post.

        Args:
            image_urls: List of publicly accessible image URLs (2-10 images)
            caption: Post caption

        Returns:
            InstagramPost with media ID
        """
        if len(image_urls) < 2:
            raise ValueError("Carousel requires at least 2 images")
        if len(image_urls) > self.MAX_CAROUSEL_ITEMS:
            raise ValueError(f"Carousel max {self.MAX_CAROUSEL_ITEMS} images")

        # Step 1: Create containers for each item
        children_ids = []
        for url in image_urls:
            container_id = await self._create_container(
                url, "", is_carousel_item=True
            )
            await self._wait_for_container(container_id)
            children_ids.append(container_id)

        # Step 2: Create carousel container
        access_token = await self.token_manager.get_instagram_token()

        response = await self.http_client.post(
            f"{self.api_base}/{self.instagram_account_id}/media",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(children_ids),
                "caption": self._truncate_hashtags(caption),
                "access_token": access_token,
            },
        )

        data = response.json()
        if "error" in data:
            raise ValueError(f"Carousel container error: {data['error']}")

        carousel_container_id = data["id"]

        # Step 3: Publish carousel
        await self._wait_for_container(carousel_container_id)
        media_id = await self._publish_container(carousel_container_id)
        permalink = await self._get_permalink(media_id)

        return InstagramPost(
            media_id=media_id,
            created_time=datetime.now(),
            permalink=permalink,
        )

    async def get_media_insights(
        self,
        media_id: str,
        metrics: list[str] | None = None,
    ) -> dict:
        """
        Get insights for a published post.

        Args:
            media_id: The published media ID
            metrics: List of metrics (default: engagement, impressions, reach)

        Returns:
            Insights data
        """
        if metrics is None:
            metrics = ["engagement", "impressions", "reach", "saved"]

        access_token = await self.token_manager.get_instagram_token()

        response = await self.http_client.get(
            f"{self.api_base}/{media_id}/insights",
            params={
                "metric": ",".join(metrics),
                "access_token": access_token,
            },
        )

        return response.json()

    async def get_account_insights(
        self,
        metrics: list[str] | None = None,
        period: Literal["day", "week", "days_28", "lifetime"] = "day",
    ) -> dict:
        """
        Get insights for the Instagram account.

        Args:
            metrics: List of metrics
            period: Time period

        Returns:
            Account insights data
        """
        if metrics is None:
            metrics = ["impressions", "reach", "profile_views"]

        access_token = await self.token_manager.get_instagram_token()

        response = await self.http_client.get(
            f"{self.api_base}/{self.instagram_account_id}/insights",
            params={
                "metric": ",".join(metrics),
                "period": period,
                "access_token": access_token,
            },
        )

        return response.json()
