"""Main entry point for the auto-posting agent."""

import argparse
import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime

from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import Settings, get_settings
from auto_posting.content.image_generator import ImageGenerator
from auto_posting.content.text_generator import TextGenerator
from auto_posting.publishers.facebook import FacebookPublisher
from auto_posting.publishers.instagram import InstagramPublisher
from auto_posting.publishers.media_uploader import MediaUploader
from auto_posting.scheduler.scheduler import PostScheduler
from auto_posting.utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


@dataclass
class PostingAgent:
    """Main auto-posting agent that orchestrates content generation and publishing."""

    settings: Settings
    token_manager: TokenManager
    text_generator: TextGenerator
    image_generator: ImageGenerator
    media_uploader: MediaUploader
    facebook_publisher: FacebookPublisher
    instagram_publisher: InstagramPublisher
    scheduler: PostScheduler

    @classmethod
    def create(cls, settings: Settings | None = None) -> "PostingAgent":
        """Factory method to create a fully configured PostingAgent."""
        settings = settings or get_settings()
        token_manager = TokenManager(settings)

        return cls(
            settings=settings,
            token_manager=token_manager,
            text_generator=TextGenerator(settings),
            image_generator=ImageGenerator(settings),
            media_uploader=MediaUploader(settings),
            facebook_publisher=FacebookPublisher(settings, token_manager),
            instagram_publisher=InstagramPublisher(settings, token_manager),
            scheduler=PostScheduler(settings),
        )

    async def close(self) -> None:
        """Cleanup resources."""
        await self.token_manager.close()
        await self.image_generator.close()
        await self.facebook_publisher.close()
        await self.instagram_publisher.close()

    async def create_and_publish(
        self,
        topic: str,
        platforms: list[str] | None = None,
        generate_image: bool = True,
    ) -> dict:
        """
        Generate content and publish to specified platforms.

        Args:
            topic: Topic for content generation
            platforms: List of platforms ["facebook", "instagram"] (default: both)
            generate_image: Whether to generate an image

        Returns:
            Dict with results for each platform
        """
        if platforms is None:
            platforms = ["facebook", "instagram"]

        rate_limiter = get_rate_limiter()
        results = {
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "platforms": {},
        }

        try:
            # Generate text content
            logger.info(f"Generating content for topic: {topic}")
            content = await self.text_generator.generate(
                topic=topic,
                include_image_prompt=generate_image,
            )

            results["text"] = content.text
            results["hashtags"] = content.hashtags

            # Generate image if requested
            image_url = None
            if generate_image and content.image_prompt:
                logger.info("Generating image...")
                image = await self.image_generator.generate(content.image_prompt)

                if image.image_bytes:
                    # Upload to Cloudinary for public URL
                    logger.info("Uploading image to Cloudinary...")
                    uploaded = self.media_uploader.upload_bytes(image.image_bytes)
                    image_url = uploaded.instagram_url
                    results["image_url"] = image_url

            # Publish to Facebook
            if "facebook" in platforms:
                await rate_limiter.acquire_post()
                try:
                    logger.info("Publishing to Facebook...")
                    if image_url:
                        fb_post = await self.facebook_publisher.publish_photo(
                            image_url=image_url,
                            caption=content.facebook_text,
                        )
                    else:
                        fb_post = await self.facebook_publisher.publish_text(
                            message=content.facebook_text,
                        )
                    results["platforms"]["facebook"] = {
                        "success": True,
                        "post_id": fb_post.post_id,
                        "permalink": fb_post.permalink,
                    }
                except Exception as e:
                    logger.error(f"Facebook publish failed: {e}")
                    results["platforms"]["facebook"] = {
                        "success": False,
                        "error": str(e),
                    }

            # Publish to Instagram
            if "instagram" in platforms:
                if not image_url:
                    logger.warning("Instagram requires an image, skipping")
                    results["platforms"]["instagram"] = {
                        "success": False,
                        "error": "Instagram requires an image",
                    }
                else:
                    await rate_limiter.acquire_post()
                    try:
                        logger.info("Publishing to Instagram...")
                        ig_post = await self.instagram_publisher.publish_image(
                            image_url=image_url,
                            caption=content.instagram_text,
                        )
                        results["platforms"]["instagram"] = {
                            "success": True,
                            "media_id": ig_post.media_id,
                            "permalink": ig_post.permalink,
                        }
                    except Exception as e:
                        logger.error(f"Instagram publish failed: {e}")
                        results["platforms"]["instagram"] = {
                            "success": False,
                            "error": str(e),
                        }

        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            results["error"] = str(e)

        return results

    async def scheduled_post(self, topic: str) -> None:
        """Scheduled post callback."""
        logger.info(f"Executing scheduled post for topic: {topic}")
        results = await self.create_and_publish(topic)
        logger.info(f"Scheduled post results: {results}")

    def setup_scheduled_posts(
        self,
        topics: list[str],
        interval_hours: int | None = None,
    ) -> None:
        """
        Set up scheduled posts.

        Args:
            topics: List of topics to cycle through
            interval_hours: Hours between posts
        """
        interval = interval_hours or self.settings.scheduler.default_interval_hours

        for i, topic in enumerate(topics):
            job_id = f"auto_post_{i}"
            self.scheduler.add_interval_job(
                job_id=job_id,
                func=self.scheduled_post,
                hours=interval,
                topic=topic,
            )

        logger.info(f"Set up {len(topics)} scheduled posts at {interval}h intervals")

    def start_scheduler(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()

    def stop_scheduler(self) -> None:
        """Stop the scheduler."""
        self.scheduler.stop()


async def run_once(args: argparse.Namespace) -> None:
    """Run a single post."""
    agent = PostingAgent.create()

    try:
        platforms = []
        if args.facebook:
            platforms.append("facebook")
        if args.instagram:
            platforms.append("instagram")
        if not platforms:
            platforms = ["facebook", "instagram"]

        results = await agent.create_and_publish(
            topic=args.topic,
            platforms=platforms,
            generate_image=not args.no_image,
        )

        print("\n" + "=" * 50)
        print("Post Results")
        print("=" * 50)
        print(f"Topic: {results['topic']}")
        print(f"Text: {results.get('text', 'N/A')[:100]}...")

        for platform, data in results.get("platforms", {}).items():
            print(f"\n{platform.upper()}:")
            if data.get("success"):
                print(f"  Status: Success")
                print(f"  ID: {data.get('post_id') or data.get('media_id')}")
                if data.get("permalink"):
                    print(f"  URL: {data['permalink']}")
            else:
                print(f"  Status: Failed")
                print(f"  Error: {data.get('error')}")

    finally:
        await agent.close()


async def run_scheduler(args: argparse.Namespace) -> None:
    """Run the scheduler."""
    agent = PostingAgent.create()

    # Parse topics from file or command line
    topics = args.topics
    if args.topics_file:
        with open(args.topics_file) as f:
            topics = [line.strip() for line in f if line.strip()]

    if not topics:
        print("Error: No topics provided. Use --topics or --topics-file")
        return

    agent.setup_scheduled_posts(topics, interval_hours=args.interval)
    agent.start_scheduler()

    print(f"\nScheduler started with {len(topics)} topics")
    print(f"Interval: {args.interval or agent.settings.scheduler.default_interval_hours} hours")
    print("Press Ctrl+C to stop\n")

    # Handle shutdown
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        print("\nShutting down...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await stop_event.wait()
    finally:
        agent.stop_scheduler()
        await agent.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Auto-posting agent for Facebook and Instagram"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Post command
    post_parser = subparsers.add_parser("post", help="Create and publish a single post")
    post_parser.add_argument("topic", help="Topic for the post")
    post_parser.add_argument("--facebook", action="store_true", help="Post to Facebook only")
    post_parser.add_argument("--instagram", action="store_true", help="Post to Instagram only")
    post_parser.add_argument("--no-image", action="store_true", help="Skip image generation")

    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Run scheduled posts")
    schedule_parser.add_argument(
        "--topics", nargs="+", default=[], help="Topics to post about"
    )
    schedule_parser.add_argument("--topics-file", help="File with topics (one per line)")
    schedule_parser.add_argument(
        "--interval", type=int, help="Hours between posts"
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify configuration and tokens")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if args.command == "post":
        asyncio.run(run_once(args))
    elif args.command == "schedule":
        asyncio.run(run_scheduler(args))
    elif args.command == "verify":
        asyncio.run(verify_config())
    else:
        parser.print_help()


async def verify_config() -> None:
    """Verify configuration and tokens."""
    print("\nVerifying configuration...")

    settings = get_settings()
    token_manager = TokenManager(settings)

    try:
        # Check Meta settings
        print("\n[Meta Configuration]")
        print(f"  App ID: {settings.meta.app_id[:10]}..." if len(settings.meta.app_id) > 10 else f"  App ID: {settings.meta.app_id}")
        print(f"  Page ID: {settings.meta.page_id}")
        print(f"  Instagram ID: {settings.meta.instagram_account_id}")
        print(f"  API Version: {settings.meta.api_version}")

        # Verify token
        print("\n[Token Verification]")
        try:
            token = await token_manager.get_access_token()
            print(f"  Access token: {token[:20]}...")

            debug_info = await token_manager.verify_token()
            data = debug_info.get("data", {})
            print(f"  Valid: {data.get('is_valid', False)}")
            print(f"  Scopes: {', '.join(data.get('scopes', []))}")
        except Exception as e:
            print(f"  Token error: {e}")

        # Check OpenAI settings
        print("\n[OpenAI Configuration]")
        print(f"  API Key: {'Set' if settings.openai.api_key else 'Not set'}")
        print(f"  Text Model: {settings.openai.text_model}")
        print(f"  Image Model: {settings.openai.image_model}")

        # Check Cloudinary settings
        print("\n[Cloudinary Configuration]")
        print(f"  Cloud Name: {settings.cloudinary.cloud_name}")
        print(f"  API Key: {'Set' if settings.cloudinary.api_key else 'Not set'}")

        print("\nConfiguration verification complete.")

    finally:
        await token_manager.close()


if __name__ == "__main__":
    main()
