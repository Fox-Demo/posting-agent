"""Text content generation using OpenAI GPT-4."""

import logging
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from auto_posting.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class GeneratedContent:
    """Generated content for social media post."""

    text: str
    hashtags: list[str]
    image_prompt: str | None = None

    @property
    def full_text(self) -> str:
        """Get full post text with hashtags."""
        if self.hashtags:
            hashtag_str = " ".join(f"#{tag}" for tag in self.hashtags[:5])  # Max 5 for IG
            return f"{self.text}\n\n{hashtag_str}"
        return self.text

    @property
    def facebook_text(self) -> str:
        """Get text formatted for Facebook (can have more hashtags)."""
        if self.hashtags:
            hashtag_str = " ".join(f"#{tag}" for tag in self.hashtags)
            return f"{self.text}\n\n{hashtag_str}"
        return self.text

    @property
    def instagram_text(self) -> str:
        """Get text formatted for Instagram (max 5 hashtags)."""
        return self.full_text


class TextGenerator:
    """Generate social media text content using OpenAI GPT-4."""

    SYSTEM_PROMPT = """You are a social media content creator. Generate engaging, professional posts for Facebook and Instagram.

Guidelines:
- Keep posts concise but engaging (50-200 words)
- Use a friendly, professional tone
- Include a clear call-to-action when appropriate
- Suggest relevant hashtags (provide as a JSON array)
- Suggest an image prompt for DALL-E if visual content would enhance the post

Respond in JSON format:
{
    "text": "The main post text",
    "hashtags": ["hashtag1", "hashtag2", "hashtag3"],
    "image_prompt": "Optional: A detailed prompt for generating a relevant image"
}"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.openai.api_key.get_secret_value()
            )
        return self._client

    async def generate(
        self,
        topic: str,
        tone: Literal["professional", "casual", "humorous", "inspirational"] = "professional",
        include_image_prompt: bool = True,
        additional_context: str | None = None,
    ) -> GeneratedContent:
        """
        Generate social media content for a given topic.

        Args:
            topic: The subject matter for the post
            tone: The tone of the post
            include_image_prompt: Whether to generate an image prompt
            additional_context: Extra context or requirements

        Returns:
            GeneratedContent with text, hashtags, and optional image prompt
        """
        user_prompt = f"""Create a social media post about: {topic}

Tone: {tone}
Include image prompt: {"Yes" if include_image_prompt else "No"}
"""
        if additional_context:
            user_prompt += f"\nAdditional context: {additional_context}"

        logger.info(f"Generating content for topic: {topic}")

        response = await self.client.chat.completions.create(
            model=self.settings.openai.text_model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=1000,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("No content generated")

        import json
        data = json.loads(content)

        result = GeneratedContent(
            text=data["text"],
            hashtags=data.get("hashtags", []),
            image_prompt=data.get("image_prompt") if include_image_prompt else None,
        )

        logger.info(f"Generated content with {len(result.hashtags)} hashtags")
        return result

    async def generate_caption(
        self,
        image_description: str,
        tone: Literal["professional", "casual", "humorous", "inspirational"] = "casual",
    ) -> GeneratedContent:
        """
        Generate a caption for an existing image.

        Args:
            image_description: Description of the image
            tone: The tone of the caption

        Returns:
            GeneratedContent with caption text and hashtags
        """
        user_prompt = f"""Create a social media caption for an image showing: {image_description}

Tone: {tone}
Do not include image_prompt in response since we already have an image.
"""

        response = await self.client.chat.completions.create(
            model=self.settings.openai.text_model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=500,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("No content generated")

        import json
        data = json.loads(content)

        return GeneratedContent(
            text=data["text"],
            hashtags=data.get("hashtags", []),
            image_prompt=None,
        )

    async def refine(
        self,
        content: GeneratedContent,
        feedback: str,
    ) -> GeneratedContent:
        """
        Refine generated content based on feedback.

        Args:
            content: The original content
            feedback: User feedback for refinement

        Returns:
            Refined GeneratedContent
        """
        user_prompt = f"""Refine this social media post based on the feedback:

Original post:
{content.text}

Original hashtags: {", ".join(content.hashtags)}

Feedback: {feedback}

Provide improved version in the same JSON format."""

        response = await self.client.chat.completions.create(
            model=self.settings.openai.text_model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=1000,
        )

        result = response.choices[0].message.content
        if not result:
            raise ValueError("No content generated")

        import json
        data = json.loads(result)

        return GeneratedContent(
            text=data["text"],
            hashtags=data.get("hashtags", []),
            image_prompt=data.get("image_prompt"),
        )
