"""Image generation using OpenAI DALL-E 3."""

import base64
import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from openai import AsyncOpenAI

from auto_posting.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class GeneratedImage:
    """Generated image data."""

    url: str
    revised_prompt: str
    image_bytes: bytes | None = None

    @property
    def has_bytes(self) -> bool:
        return self.image_bytes is not None


class ImageGenerator:
    """Generate images using OpenAI DALL-E 3."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        self._http_client: httpx.AsyncClient | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.openai.api_key.get_secret_value()
            )
        return self._client

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

    async def generate(
        self,
        prompt: str,
        style: Literal["vivid", "natural"] = "vivid",
        download: bool = True,
    ) -> GeneratedImage:
        """
        Generate an image from a text prompt.

        Args:
            prompt: The image description/prompt
            style: vivid (hyper-real) or natural (more realistic)
            download: Whether to download the image bytes

        Returns:
            GeneratedImage with URL and optionally bytes
        """
        logger.info(f"Generating image for prompt: {prompt[:100]}...")

        response = await self.client.images.generate(
            model=self.settings.openai.image_model,
            prompt=prompt,
            size=self.settings.openai.image_size,
            quality=self.settings.openai.image_quality,
            style=style,
            n=1,
        )

        image_data = response.data[0]
        url = image_data.url
        revised_prompt = image_data.revised_prompt or prompt

        if not url:
            raise ValueError("No image URL returned")

        logger.info(f"Image generated successfully: {url[:50]}...")

        image_bytes = None
        if download:
            image_bytes = await self._download_image(url)

        return GeneratedImage(
            url=url,
            revised_prompt=revised_prompt,
            image_bytes=image_bytes,
        )

    async def generate_b64(
        self,
        prompt: str,
        style: Literal["vivid", "natural"] = "vivid",
    ) -> GeneratedImage:
        """
        Generate an image and return as base64 bytes.

        Args:
            prompt: The image description/prompt
            style: vivid (hyper-real) or natural (more realistic)

        Returns:
            GeneratedImage with bytes (no URL)
        """
        logger.info(f"Generating base64 image for prompt: {prompt[:100]}...")

        response = await self.client.images.generate(
            model=self.settings.openai.image_model,
            prompt=prompt,
            size=self.settings.openai.image_size,
            quality=self.settings.openai.image_quality,
            style=style,
            response_format="b64_json",
            n=1,
        )

        image_data = response.data[0]
        b64_json = image_data.b64_json
        revised_prompt = image_data.revised_prompt or prompt

        if not b64_json:
            raise ValueError("No base64 data returned")

        image_bytes = base64.b64decode(b64_json)

        return GeneratedImage(
            url="",  # No URL when using b64
            revised_prompt=revised_prompt,
            image_bytes=image_bytes,
        )

    async def _download_image(self, url: str) -> bytes:
        """Download image from URL."""
        response = await self.http_client.get(url)
        response.raise_for_status()
        return response.content

    async def generate_chart(
        self,
        chart_description: str,
        data_context: str | None = None,
    ) -> GeneratedImage:
        """
        Generate a chart/graph image.

        Args:
            chart_description: Description of the chart to generate
            data_context: Optional context about the data being visualized

        Returns:
            GeneratedImage of the chart
        """
        # Construct a detailed prompt for chart generation
        prompt = f"""Create a clean, professional data visualization chart:

{chart_description}

Style requirements:
- Modern, minimalist design
- Clear labels and legends
- Professional color palette
- High contrast for readability
- Suitable for social media sharing
"""
        if data_context:
            prompt += f"\nData context: {data_context}"

        return await self.generate(prompt, style="natural")

    async def generate_infographic(
        self,
        topic: str,
        key_points: list[str],
    ) -> GeneratedImage:
        """
        Generate an infographic-style image.

        Args:
            topic: The main topic
            key_points: List of key points to visualize

        Returns:
            GeneratedImage of the infographic
        """
        points_text = "\n".join(f"- {point}" for point in key_points)

        prompt = f"""Create a professional social media infographic about: {topic}

Key points to include:
{points_text}

Style requirements:
- Modern, clean design
- Easy to read text
- Visual icons or illustrations
- Engaging layout for social media
- Professional color scheme
- Square format (1:1 ratio)
"""
        return await self.generate(prompt, style="vivid")

    async def edit_image(
        self,
        image_bytes: bytes,
        mask_bytes: bytes,
        prompt: str,
    ) -> GeneratedImage:
        """
        Edit an existing image (DALL-E 2 only, included for completeness).

        Note: This uses DALL-E 2 as DALL-E 3 doesn't support editing yet.

        Args:
            image_bytes: The original image (PNG, square, < 4MB)
            mask_bytes: The mask image indicating areas to edit
            prompt: Description of the edit

        Returns:
            GeneratedImage with edited result
        """
        response = await self.client.images.edit(
            model="dall-e-2",  # Editing only available in DALL-E 2
            image=image_bytes,
            mask=mask_bytes,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )

        image_data = response.data[0]
        url = image_data.url

        if not url:
            raise ValueError("No image URL returned")

        image_bytes_result = await self._download_image(url)

        return GeneratedImage(
            url=url,
            revised_prompt=prompt,
            image_bytes=image_bytes_result,
        )
