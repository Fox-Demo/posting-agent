#!/usr/bin/env python3
"""
Exchange a short-lived User Access Token for a long-lived Page Access Token.

Why you need this: META_APP_ID / META_APP_SECRET / META_PAGE_ID alone cannot
publish anything. Every write call to the Graph API needs a Page Access Token
carrying the `pages_manage_posts` permission.

How to get the short-lived user token (valid ~1 hour, that's fine, we upgrade it):
  1. https://developers.facebook.com/tools/explorer/
  2. Meta App = your app, User or Page = "User Token"
  3. Add permissions: pages_show_list, pages_read_engagement, pages_manage_posts
  4. Click "Generate Access Token" and copy it

Usage:
    python3 scripts/fb_get_page_token.py <SHORT_LIVED_USER_TOKEN>

The Page token it prints does not expire (it inherits from a long-lived user
token), so paste it into .env as META_PAGE_ACCESS_TOKEN and you are done.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API_VERSION = os.environ.get("META_API_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{API_VERSION}"


def load_env(path: Path) -> dict[str, str]:
    """Minimal .env parser - no external dependency needed."""
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


def graph_get(path: str, **params) -> dict:
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    short_token = sys.argv[1].strip()
    root = Path(__file__).resolve().parent.parent
    env = {**load_env(root / ".env"), **os.environ}

    app_id = env.get("META_APP_ID", "")
    app_secret = env.get("META_APP_SECRET", "")
    page_id = env.get("META_PAGE_ID", "")

    if not app_id or not app_secret:
        print("ERROR: META_APP_ID / META_APP_SECRET missing in .env")
        return 1

    # Step 1: short-lived user token -> long-lived user token (60 days)
    print("Step 1: exchanging for a long-lived user token ...")
    long_lived = graph_get(
        "oauth/access_token",
        grant_type="fb_exchange_token",
        client_id=app_id,
        client_secret=app_secret,
        fb_exchange_token=short_token,
    )
    user_token = long_lived["access_token"]
    print(f"  OK (expires_in={long_lived.get('expires_in', 'n/a')} seconds)")

    # Step 2: long-lived user token -> per-Page tokens (these do not expire)
    print("Step 2: fetching your Pages and their tokens ...")
    accounts = graph_get("me/accounts", access_token=user_token, fields="id,name,access_token")

    pages = accounts.get("data", [])
    if not pages:
        print("  No Pages found. Make sure the token has `pages_show_list` and that")
        print("  your account is an admin of the Page.")
        return 1

    match = None
    for page in pages:
        marker = ""
        if page_id and page["id"] == page_id:
            match = page
            marker = "   <-- matches META_PAGE_ID"
        print(f"  - {page['name']} (id={page['id']}){marker}")

    target = match or pages[0]
    if not match:
        print(f"\nWARNING: META_PAGE_ID={page_id!r} not in the list above; showing the first Page.")

    print("\n" + "=" * 70)
    print("Add these two lines to your .env:\n")
    print(f"META_PAGE_ID={target['id']}")
    print(f"META_PAGE_ACCESS_TOKEN={target['access_token']}")
    print("=" * 70)

    # Step 3: sanity-check the permissions actually attached to that Page token
    debug = graph_get(
        "debug_token",
        input_token=target["access_token"],
        access_token=f"{app_id}|{app_secret}",
    ).get("data", {})
    scopes = debug.get("scopes", [])
    print(f"\nToken valid : {debug.get('is_valid')}")
    print(f"Expires at  : {debug.get('expires_at') or 'never'}")
    print(f"Scopes      : {', '.join(scopes) or '(none)'}")
    if "pages_manage_posts" not in scopes:
        print("\nWARNING: `pages_manage_posts` is missing - publishing will fail with")
        print("         error code 200. Re-generate the user token with that permission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
