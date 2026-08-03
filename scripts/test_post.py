#!/usr/bin/env python3
"""Test script to post directly without AI generation."""

import asyncio
import sys

sys.path.insert(0, str(__file__).replace("/scripts/test_post.py", "/src"))

from auto_posting.config import get_settings
from auto_posting.auth.token_manager import TokenManager
from auto_posting.publishers.facebook import FacebookPublisher
from auto_posting.publishers.instagram import InstagramPublisher
from auto_posting.publishers.media_uploader import MediaUploader


async def test_facebook_text_post():
    """Test posting text to Facebook."""
    print("\n" + "=" * 50)
    print("Testing Facebook Text Post")
    print("=" * 50)

    settings = get_settings()
    token_manager = TokenManager(settings)
    fb = FacebookPublisher(settings, token_manager)

    try:
        message = "Hello from Auto-Posting Agent! This is a test post. 🚀 #test #automation"
        print(f"Posting: {message[:50]}...")

        result = await fb.publish_text(message)
        print(f"✅ Success!")
        print(f"   Post ID: {result.post_id}")
        print(f"   Permalink: {result.permalink}")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
    finally:
        await fb.close()
        await token_manager.close()


async def test_facebook_photo_post():
    """Test posting a photo to Facebook using a sample image URL."""
    print("\n" + "=" * 50)
    print("Testing Facebook Photo Post")
    print("=" * 50)

    settings = get_settings()
    token_manager = TokenManager(settings)
    fb = FacebookPublisher(settings, token_manager)

    try:
        # Use a sample public image
        image_url = "https://picsum.photos/1024/1024"
        caption = "Test photo post from Auto-Posting Agent! 📸 #test #automation"
        print(f"Posting photo with caption: {caption[:50]}...")

        result = await fb.publish_photo(image_url=image_url, caption=caption)
        print(f"✅ Success!")
        print(f"   Post ID: {result.post_id}")
        print(f"   Permalink: {result.permalink}")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
    finally:
        await fb.close()
        await token_manager.close()


async def test_instagram_post():
    """Test posting to Instagram (requires Cloudinary for image hosting)."""
    print("\n" + "=" * 50)
    print("Testing Instagram Post")
    print("=" * 50)

    settings = get_settings()

    # Check if Cloudinary is configured
    if not settings.cloudinary_cloud_name:
        print("⚠️  Cloudinary not configured. Skipping Instagram test.")
        print("   Instagram requires images hosted on a public URL.")
        print("   Configure CLOUDINARY_* settings in .env to test Instagram.")
        return False

    print(f"Cloudinary cloud_name: {settings.cloudinary_cloud_name}")
    print(f"Cloudinary api_key: {settings.cloudinary_api_key[:6]}..." if settings.cloudinary_api_key else "Cloudinary api_key: NOT SET")

    token_manager = TokenManager(settings)
    ig = InstagramPublisher(settings, token_manager)
    uploader = MediaUploader(settings)

    try:
        # Download a sample image and upload to Cloudinary
        import httpx
        print("Downloading sample image...")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get("https://picsum.photos/1080/1080")
            image_bytes = response.content
            print(f"Downloaded {len(image_bytes)} bytes")

        print("Uploading to Cloudinary...")
        uploaded = uploader.upload_bytes(image_bytes, "test_post")
        image_url = uploaded.instagram_url
        print(f"Image URL: {image_url}")

        caption = "Test post from Auto-Posting Agent! 🤖 #test #automation"
        print(f"Posting to Instagram: {caption[:50]}...")

        result = await ig.publish_image(image_url=image_url, caption=caption)
        print(f"✅ Success!")
        print(f"   Media ID: {result.media_id}")
        print(f"   Permalink: {result.permalink}")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
    finally:
        await ig.close()
        await token_manager.close()


async def main():
    print("\n" + "=" * 50)
    print("Auto-Posting Agent - API Test")
    print("=" * 50)

    print("\nSelect test to run:")
    print("  1. Facebook text post only")
    print("  2. Facebook photo post only")
    print("  3. Instagram post only")
    print("  4. All tests")

    choice = input("\nEnter choice (1-4): ").strip()

    results = {}

    if choice in ["1", "4"]:
        results["fb_text"] = await test_facebook_text_post()

    if choice in ["2", "4"]:
        results["fb_photo"] = await test_facebook_photo_post()

    if choice in ["3", "4"]:
        results["instagram"] = await test_instagram_post()

    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
