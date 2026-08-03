#!/usr/bin/env python3
"""
OAuth setup script for Meta (Facebook/Instagram) API authentication.

This script helps you:
1. Generate the OAuth authorization URL
2. Exchange the authorization code for access tokens
3. Store tokens securely (encrypted)

Prerequisites:
- Meta Developer account with app created
- App ID and App Secret in .env file
- Facebook Page and Instagram Business Account linked
"""

import asyncio
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading

# Add src to path for imports
sys.path.insert(0, str(__file__).replace("/scripts/setup_oauth.py", "/src"))

from auto_posting.config import get_settings
from auto_posting.auth.token_manager import TokenManager


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    authorization_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        """Handle OAuth callback GET request."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <head><title>Authorization Successful</title></head>
                <body>
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        elif "error" in params:
            OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <head><title>Authorization Failed</title></head>
                <body>
                    <h1>Authorization Failed</h1>
                    <p>Error: {OAuthCallbackHandler.error}</p>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Suppress HTTP server logs."""
        pass


def start_callback_server(port: int = 8080) -> HTTPServer:
    """Start local server for OAuth callback."""
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()
    return server


async def setup_oauth_interactive() -> None:
    """Interactive OAuth setup flow."""
    print("\n" + "=" * 60)
    print("Meta (Facebook/Instagram) OAuth Setup")
    print("=" * 60 + "\n")

    settings = get_settings()
    token_manager = TokenManager(settings)

    # Check if required settings are present
    if not settings.meta.app_id or settings.meta.app_id == "your_app_id":
        print("ERROR: META_APP_ID not configured in .env file")
        print("Please set up your .env file first using .env.example as a template.")
        return

    if not settings.meta.app_secret:
        print("ERROR: META_APP_SECRET not configured in .env file")
        return

    callback_port = 8080
    redirect_uri = f"http://localhost:{callback_port}/callback"

    print("IMPORTANT: Before proceeding, ensure you have:")
    print("  1. Created a Meta App at developers.facebook.com")
    print("  2. Added 'Facebook Login' product to your app")
    print(f"  3. Added '{redirect_uri}' to Valid OAuth Redirect URIs")
    print("  4. Your Facebook Page is linked to an Instagram Business Account")
    print()

    input("Press Enter to continue...")

    # Generate OAuth URL
    oauth_url = token_manager.generate_oauth_url(redirect_uri)

    print("\nStep 1: Opening browser for authorization...")
    print(f"URL: {oauth_url}\n")

    # Try to open browser automatically
    try:
        webbrowser.open(oauth_url)
        print("Browser opened automatically.")
    except Exception:
        print("Could not open browser automatically.")
        print("Please copy and paste the URL above into your browser.")

    print("\nStep 2: Waiting for authorization callback...")
    print(f"Listening on http://localhost:{callback_port}/callback")

    # Start callback server
    server = start_callback_server(callback_port)

    # Wait for callback (with timeout)
    timeout = 300  # 5 minutes
    for _ in range(timeout):
        if OAuthCallbackHandler.authorization_code or OAuthCallbackHandler.error:
            break
        await asyncio.sleep(1)
    else:
        print("\nTimeout waiting for authorization. Please try again.")
        server.server_close()
        return

    server.server_close()

    if OAuthCallbackHandler.error:
        print(f"\nAuthorization failed: {OAuthCallbackHandler.error}")
        return

    code = OAuthCallbackHandler.authorization_code
    print(f"\nReceived authorization code: {code[:20]}...")

    print("\nStep 3: Exchanging code for access token...")

    try:
        token_data = await token_manager.exchange_code_for_token(code, redirect_uri)
        print("\nSuccess! Tokens have been saved securely.")
        print(f"  - Token type: {token_data['token_type']}")
        print(f"  - Expires at: {token_data['expires_at']}")
        print(f"  - Page token: {'Yes' if token_data.get('page_access_token') else 'No'}")

        print("\nStep 4: Verifying token...")
        debug_info = await token_manager.verify_token()
        data = debug_info.get("data", {})
        print(f"  - Valid: {data.get('is_valid', False)}")
        print(f"  - App ID: {data.get('app_id', 'N/A')}")
        print(f"  - Scopes: {', '.join(data.get('scopes', []))}")

        print("\n" + "=" * 60)
        print("Setup complete! You can now run the auto-posting agent.")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nError exchanging token: {e}")
        raise
    finally:
        await token_manager.close()


async def setup_oauth_manual() -> None:
    """Manual OAuth setup for environments without browser."""
    print("\n" + "=" * 60)
    print("Meta OAuth Manual Setup")
    print("=" * 60 + "\n")

    settings = get_settings()
    token_manager = TokenManager(settings)

    print("For manual setup, you need a short-lived access token.")
    print("You can get this from:")
    print("  1. Graph API Explorer: https://developers.facebook.com/tools/explorer/")
    print("  2. Select your app and request required permissions")
    print("  3. Generate Access Token")
    print()

    token = input("Paste your short-lived access token: ").strip()

    if not token:
        print("No token provided. Exiting.")
        return

    try:
        print("\nExchanging for long-lived token...")
        token_data = await token_manager.exchange_for_long_lived_token(token)
        print("\nSuccess! Tokens have been saved securely.")
        print(f"  - Expires at: {token_data['expires_at']}")
        print(f"  - Page token: {'Yes' if token_data.get('page_access_token') else 'No'}")
    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        await token_manager.close()


def main() -> None:
    """Main entry point."""
    print("\nSelect setup mode:")
    print("  1. Interactive (browser-based OAuth)")
    print("  2. Manual (paste existing token)")
    print()

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        asyncio.run(setup_oauth_interactive())
    elif choice == "2":
        asyncio.run(setup_oauth_manual())
    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    main()
