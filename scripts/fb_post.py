#!/usr/bin/env python3
"""
Publish a post (text, or text + local image(s)) to a Facebook Page.

Zero third-party dependencies - stdlib only, so it runs with any python3.

The image is uploaded as raw bytes via multipart/form-data, so you do NOT need
Cloudinary or any public image URL. (That is only required for Instagram.)

Setup - put these in .env:
    META_PAGE_ID=...
    META_PAGE_ACCESS_TOKEN=...     # see scripts/fb_get_page_token.py

Usage:
    # text + one image
    python3 scripts/fb_post.py --message "LFG GoalFi !" --image logo-gf.png

    # text only
    python3 scripts/fb_post.py --message "Hello world"

    # multiple images (carousel, max 10)
    python3 scripts/fb_post.py -m "Gallery" -i a.png -i b.png

    # preview without publishing
    python3 scripts/fb_post.py -m "LFG GoalFi !" -i logo-gf.png --dry-run
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API_VERSION = "v21.0"


# --------------------------------------------------------------------------- #
# tiny helpers
# --------------------------------------------------------------------------- #
def load_env(path: Path) -> dict[str, str]:
    """Minimal .env parser - avoids a python-dotenv dependency."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.split("#")[0].strip().strip("'\"")
    return env


class GraphError(RuntimeError):
    """A Graph API call came back with an `error` object."""


def _request(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            raise GraphError(f"HTTP {exc.code}: {raw}") from exc
        err = body.get("error", {})
        raise GraphError(
            f"{err.get('type', 'Error')} (code {err.get('code')}): {err.get('message', raw)}"
        ) from exc
    if "error" in body:
        err = body["error"]
        raise GraphError(f"{err.get('type', 'Error')} (code {err.get('code')}): {err.get('message')}")
    return body


def graph_get(base: str, path: str, **params) -> dict:
    return _request(f"{base}/{path}?{urllib.parse.urlencode(params)}")


def graph_post(base: str, path: str, **fields) -> dict:
    payload = urllib.parse.urlencode(
        {k: v for k, v in fields.items() if v is not None}
    ).encode("utf-8")
    return _request(
        f"{base}/{path}",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def graph_post_file(base: str, path: str, file_path: Path, **fields) -> dict:
    """POST multipart/form-data with the image bytes in the `source` field."""
    boundary = f"----fbpost{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    parts: list[bytes] = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="source"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)
    return _request(
        f"{base}/{path}",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )


# --------------------------------------------------------------------------- #
# posting
# --------------------------------------------------------------------------- #
def publish(
    base: str,
    page_id: str,
    token: str,
    message: str,
    images: list[Path],
) -> dict:
    """Publish text, a single photo, or a multi-photo post. Returns the API result."""
    if not images:
        # Plain text post.
        return graph_post(base, f"{page_id}/feed", message=message, access_token=token)

    if len(images) == 1:
        # Single photo + caption -> one API call, image sent as bytes.
        return graph_post_file(
            base,
            f"{page_id}/photos",
            images[0],
            caption=message,
            published="true",
            access_token=token,
        )

    # Carousel: upload each photo unpublished, then attach them all to one feed post.
    media_ids = []
    for image in images:
        result = graph_post_file(
            base,
            f"{page_id}/photos",
            image,
            published="false",
            temporary="true",
            access_token=token,
        )
        media_ids.append(result["id"])
        print(f"  uploaded {image.name} -> media_fbid={result['id']}")

    fields = {"message": message, "access_token": token}
    for index, media_id in enumerate(media_ids):
        fields[f"attached_media[{index}]"] = json.dumps({"media_fbid": media_id})
    return graph_post(base, f"{page_id}/feed", **fields)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish text and/or local images to a Facebook Page.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-m", "--message", required=True, help="Post text")
    parser.add_argument(
        "-i", "--image", action="append", default=[], help="Local image path (repeatable, max 10)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate everything, do not publish")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    env = {**load_env(root / ".env"), **os.environ}

    page_id = env.get("META_PAGE_ID", "")
    token = env.get("META_PAGE_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN", "")
    base = f"https://graph.facebook.com/{env.get('META_API_VERSION') or DEFAULT_API_VERSION}"

    if not page_id:
        print("ERROR: META_PAGE_ID is not set in .env")
        return 1
    if not token:
        print("ERROR: META_PAGE_ACCESS_TOKEN is not set in .env")
        print("       Run: python3 scripts/fb_get_page_token.py <SHORT_LIVED_USER_TOKEN>")
        return 1

    images = []
    for raw in args.image:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        if not path.exists():
            print(f"ERROR: image not found: {path}")
            return 1
        images.append(path)

    if len(images) > 10:
        print("ERROR: Facebook allows at most 10 images per post")
        return 1

    print(f"Page    : {page_id}")
    print(f"Message : {args.message}")
    print(f"Images  : {', '.join(p.name for p in images) or '(none)'}")

    if args.dry_run:
        print("\n--dry-run: nothing was published.")
        return 0

    print("\nPublishing ...")
    try:
        result = publish(base, page_id, token, args.message, images)
    except GraphError as exc:
        print(f"\nFAILED: {exc}")
        print("\nCommon causes:")
        print("  code 190 -> token expired or invalid; re-run fb_get_page_token.py")
        print("  code 200 -> Page token is missing the `pages_manage_posts` permission")
        print("  code 100 -> wrong META_PAGE_ID, or the token belongs to another Page")
        return 1

    post_id = result.get("post_id") or result.get("id")
    print(f"Published! post_id={post_id}")

    try:
        info = graph_get(base, post_id, fields="permalink_url", access_token=token)
        if info.get("permalink_url"):
            print(f"Permalink: {info['permalink_url']}")
    except GraphError as exc:
        print(f"(could not fetch permalink: {exc})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
