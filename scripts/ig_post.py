#!/usr/bin/env python3
"""
Publish a post (image + caption) to an Instagram Business account.

Zero third-party dependencies - stdlib only, so it runs with any python3.

Unlike Facebook, the Instagram Graph API will NOT accept raw image bytes: it
only fetches from a public HTTPS URL. So local files are pushed to Cloudinary
first, then handed to Instagram as a URL. Pass --image-url instead if you
already host the image somewhere public.

Setup - put these in .env:
    META_PAGE_ACCESS_TOKEN=...          # needs instagram_content_publish
    META_INSTAGRAM_ACCOUNT_ID=...       # auto-discovered if left blank
    CLOUDINARY_CLOUD_NAME=...           # only needed for local files
    CLOUDINARY_API_KEY=...
    CLOUDINARY_API_SECRET=...
    CLOUDINARY_UPLOAD_FOLDER=auto_posting

Usage:
    # check that every prerequisite is in place, publish nothing
    python3 scripts/ig_post.py --check

    # caption + one local image
    python3 scripts/ig_post.py -m "LFG GoalFi !" -i logo-gf.png

    # a small logo: pad it onto a white 1080x1080 square first
    python3 scripts/ig_post.py -m "LFG GoalFi !" -i logo-gf.png --square

    # image already hosted somewhere public - no Cloudinary needed
    python3 scripts/ig_post.py -m "Hello" --image-url https://example.com/a.jpg

    # carousel, 2-10 images
    python3 scripts/ig_post.py -m "Gallery" -i a.png -i b.png

    # upload to Cloudinary and print the URL, but do not publish
    python3 scripts/ig_post.py -m "..." -i logo-gf.png --dry-run
"""

import argparse
import hashlib
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API_VERSION = "v21.0"
CLOUDINARY_API = "https://api.cloudinary.com/v1_1"

# Instagram delivers best from a 1080px-wide JPEG; it rejects PNG outright.
TRANSFORM_DEFAULT = "f_jpg,q_auto,w_1080,c_limit"
TRANSFORM_SQUARE = "f_jpg,q_auto,w_1080,h_1080,c_pad,b_white"

POLL_INTERVAL = 3      # seconds between container status checks
POLL_TIMEOUT = 300     # give up after 5 minutes


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
        if isinstance(err, dict) and err:
            raise GraphError(
                f"{err.get('type', 'Error')} (code {err.get('code')}): "
                f"{err.get('message', raw)}"
            ) from exc
        raise GraphError(f"HTTP {exc.code}: {raw}") from exc
    if isinstance(body, dict) and "error" in body:
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


def _multipart(url: str, file_path: Path, file_field: str, **fields) -> dict:
    """POST multipart/form-data with one file plus plain text fields."""
    boundary = f"----igpost{uuid.uuid4().hex}"
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
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)
    return _request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )


# --------------------------------------------------------------------------- #
# Cloudinary - signed upload, implemented against the REST API directly
# --------------------------------------------------------------------------- #
def cloudinary_upload(env: dict[str, str], image: Path, transform: str) -> str:
    """Upload a local image and return a public HTTPS URL with `transform` applied."""
    cloud = env.get("CLOUDINARY_CLOUD_NAME", "")
    key = env.get("CLOUDINARY_API_KEY", "")
    secret = env.get("CLOUDINARY_API_SECRET", "")
    folder = env.get("CLOUDINARY_UPLOAD_FOLDER", "auto_posting")

    if not (cloud and key and secret):
        raise GraphError(
            "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME / "
            "CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET in .env, or pass "
            "--image-url with an image you already host publicly."
        )

    public_id = f"{folder}/{image.stem}_{int(time.time())}"
    timestamp = str(int(time.time()))

    # Cloudinary signs the alphabetically sorted params, secret appended raw.
    signed = {"public_id": public_id, "timestamp": timestamp}
    to_sign = "&".join(f"{k}={signed[k]}" for k in sorted(signed))
    signature = hashlib.sha1(f"{to_sign}{secret}".encode("utf-8")).hexdigest()

    result = _multipart(
        f"{CLOUDINARY_API}/{cloud}/image/upload",
        image,
        "file",
        api_key=key,
        signature=signature,
        **signed,
    )

    # Insert the transformation into the delivery URL: .../upload/<transform>/...
    secure_url = result["secure_url"]
    url = secure_url.replace("/image/upload/", f"/image/upload/{transform}/", 1)

    # Cloudinary honours the extension in the delivery URL, and Instagram has
    # been known to sniff it rather than the Content-Type header. A PNG that
    # f_jpg turns into JPEG still ends in .png, so rewrite the suffix to match.
    if "f_jpg" in transform:
        url = url.rsplit(".", 1)[0] + ".jpg"
    return url


# --------------------------------------------------------------------------- #
# Instagram - two-step publish: create container, then publish it
# --------------------------------------------------------------------------- #
def resolve_ig_account_id(base: str, env: dict[str, str], token: str) -> str:
    """Use META_INSTAGRAM_ACCOUNT_ID, or look it up from the linked Page."""
    page_id = env.get("META_PAGE_ID", "")
    configured = env.get("META_INSTAGRAM_ACCOUNT_ID", "")

    # A value equal to the Page ID is the .env placeholder, not a real IG ID.
    if configured and configured != page_id:
        return configured

    if not page_id:
        raise GraphError("META_INSTAGRAM_ACCOUNT_ID is not set and META_PAGE_ID is missing")

    info = graph_get(base, page_id, fields="instagram_business_account{id,username}",
                     access_token=token)
    account = info.get("instagram_business_account")
    if not account:
        raise GraphError(
            "No Instagram Business account is linked to this Page. Switch the IG "
            "account to Business/Creator, link it to the Page, and regenerate the "
            "token with instagram_basic + instagram_content_publish."
        )
    print(f"  discovered IG account: @{account.get('username')} (id={account['id']})")
    print(f"  -> put this in .env:   META_INSTAGRAM_ACCOUNT_ID={account['id']}")
    return account["id"]


def wait_for_container(base: str, container_id: str, token: str) -> None:
    """Poll a media container until Instagram finishes fetching the image."""
    waited = 0
    while waited < POLL_TIMEOUT:
        status = graph_get(base, container_id, fields="status_code,status",
                           access_token=token)
        code = status.get("status_code", "IN_PROGRESS")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise GraphError(f"container {container_id} -> {code}: {status.get('status')}")
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    raise GraphError(f"container {container_id} still not ready after {waited}s")


def publish(base: str, ig_id: str, token: str, caption: str, urls: list[str]) -> str:
    """Create the container(s), publish, and return the media ID."""
    if len(urls) == 1:
        container = graph_post(base, f"{ig_id}/media", image_url=urls[0],
                               caption=caption, access_token=token)["id"]
        print(f"  container {container} created, waiting for Instagram to fetch it ...")
        wait_for_container(base, container, token)
    else:
        # Carousel: one child container per image, then a parent that holds them.
        children = []
        for url in urls:
            child = graph_post(base, f"{ig_id}/media", image_url=url,
                               is_carousel_item="true", access_token=token)["id"]
            wait_for_container(base, child, token)
            children.append(child)
            print(f"  child container ready: {child}")
        container = graph_post(base, f"{ig_id}/media", media_type="CAROUSEL",
                               children=",".join(children), caption=caption,
                               access_token=token)["id"]
        wait_for_container(base, container, token)

    result = graph_post(base, f"{ig_id}/media_publish",
                        creation_id=container, access_token=token)
    return result["id"]


# --------------------------------------------------------------------------- #
# --check
# --------------------------------------------------------------------------- #
def run_check(base: str, env: dict[str, str], token: str) -> int:
    """Verify every prerequisite without publishing anything."""
    ok = True

    def line(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  {'OK  ' if good else 'FAIL'}  {label:34s} {detail}")

    print("Instagram publishing prerequisites\n")

    if not token:
        line("META_PAGE_ACCESS_TOKEN", False, "not set in .env")
        return 1

    debug = graph_get(base, "debug_token", input_token=token,
                      access_token=f"{env.get('META_APP_ID')}|{env.get('META_APP_SECRET')}"
                      ).get("data", {})
    scopes = debug.get("scopes", [])
    line("token valid", bool(debug.get("is_valid")),
         f"type={debug.get('type')} expires={debug.get('expires_at') or 'never'}")
    line("scope instagram_basic", "instagram_basic" in scopes)
    line("scope instagram_content_publish", "instagram_content_publish" in scopes)

    try:
        ig_id = resolve_ig_account_id(base, env, token)
        line("IG Business account linked", True, f"id={ig_id}")
    except GraphError as exc:
        line("IG Business account linked", False, str(exc).split(".")[0])

    have_cloudinary = all(env.get(k) for k in
                          ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))
    line("Cloudinary configured", have_cloudinary,
         "" if have_cloudinary else "needed for local files (or use --image-url)")

    print("\nReady to publish." if ok else "\nNot ready - fix the FAIL rows above.")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish an image post to an Instagram Business account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-m", "--message", help="Caption text")
    parser.add_argument("-i", "--image", action="append", default=[],
                        help="Local image path (repeatable, 2-10 makes a carousel)")
    parser.add_argument("--image-url", action="append", default=[],
                        help="Already-public HTTPS image URL (skips Cloudinary)")
    parser.add_argument("--square", action="store_true",
                        help="Pad onto a white 1080x1080 square - good for logos")
    parser.add_argument("--transform", default=None,
                        help=f"Cloudinary transformation (default: {TRANSFORM_DEFAULT})")
    parser.add_argument("--check", action="store_true",
                        help="Verify setup and exit without publishing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Upload to Cloudinary and print URLs, but do not publish")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    env = load_env(root / ".env")
    token = env.get("META_PAGE_ACCESS_TOKEN") or env.get("META_ACCESS_TOKEN", "")
    base = f"https://graph.facebook.com/{env.get('META_API_VERSION') or DEFAULT_API_VERSION}"

    if args.check:
        try:
            return run_check(base, env, token)
        except GraphError as exc:
            print(f"FAILED: {exc}")
            return 1

    if not args.message:
        parser.error("-m/--message is required (Instagram has no text-only posts, "
                     "but a caption is still expected)")
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

    total = len(images) + len(args.image_url)
    if total == 0:
        print("ERROR: Instagram requires media - pass --image or --image-url")
        return 1
    if total > 10:
        print("ERROR: Instagram allows at most 10 images per carousel")
        return 1

    transform = args.transform or (TRANSFORM_SQUARE if args.square else TRANSFORM_DEFAULT)

    try:
        urls = list(args.image_url)
        for image in images:
            print(f"Uploading {image.name} to Cloudinary ...")
            url = cloudinary_upload(env, image, transform)
            print(f"  {url}")
            urls.append(url)

        # Resolved after the uploads so that --dry-run can exercise Cloudinary
        # on its own, before the Instagram side is finished being set up.
        try:
            ig_id = resolve_ig_account_id(base, env, token)
        except GraphError:
            if not args.dry_run:
                raise
            ig_id = "(unresolved - Instagram not set up yet)"

        print(f"\nIG account : {ig_id}")
        print(f"Caption    : {args.message}")
        print(f"Media      : {len(urls)} image(s)")

        if args.dry_run:
            print("\n--dry-run: nothing was published.")
            return 0

        print("\nPublishing ...")
        media_id = publish(base, ig_id, token, args.message, urls)
    except GraphError as exc:
        print(f"\nFAILED: {exc}")
        print("\nCommon causes:")
        print("  code 190 -> token expired or invalid; re-run fb_get_page_token.py")
        print("  code 200 -> token is missing instagram_content_publish")
        print("  code 9004 -> Instagram could not fetch the image URL (not public?)")
        print("  code 2207026 -> unsupported format; Instagram needs JPEG, try --square")
        print("  code 4 -> rate limited; Instagram allows 50 posts per 24h")
        return 1

    print(f"Published! media_id={media_id}")
    try:
        info = graph_get(base, media_id, fields="permalink", access_token=token)
        if info.get("permalink"):
            print(f"Permalink: {info['permalink']}")
    except GraphError as exc:
        print(f"(could not fetch permalink: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
