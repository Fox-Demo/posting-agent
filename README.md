# Auto-Posting Agent

An AI-powered agent that automatically generates text and images, then posts to Facebook and Instagram.

## Quick Start: post to Facebook

Just want text + an image on your Page? You need **four** values, not three —
`META_APP_ID` / `META_APP_SECRET` / `META_PAGE_ID` cannot publish on their own,
a **Page Access Token** carrying `pages_manage_posts` does the actual posting.

```bash
# 1. Grab a short-lived User Token from the Graph API Explorer, then:
python3 scripts/fb_get_page_token.py <SHORT_LIVED_USER_TOKEN>
#    -> paste META_PAGE_ACCESS_TOKEN into .env

# 2. Post text + a local image (no Cloudinary, no public URL needed)
python3 scripts/fb_post.py --message "LFG GoalFi !" --image logo-gf.png
```

Both scripts are stdlib-only, so they run with any `python3`.
Full walkthrough: **[Facebook Quickstart](docs/FACEBOOK_QUICKSTART.md)**.

---

## Features

- **AI Content Generation**: Uses OpenAI GPT-4 for text and DALL-E 3 for images
- **Multi-Platform Publishing**: Posts to Facebook Pages and Instagram Business accounts
- **OAuth Token Management**: Secure token storage with automatic refresh
- **Rate Limiting**: Built-in rate limiting to respect API limits

## Prerequisites

Before using this agent, you need:

1. **Meta Developer Account & App**
   - See **[Meta Setup Guide](docs/META_SETUP_GUIDE.md)** for detailed instructions
   - Create at [developers.facebook.com](https://developers.facebook.com)
   - Create a Meta App with Facebook Login product
   - Add required permissions: `pages_manage_posts`, `instagram_content_publish`, etc.

2. **Facebook Page** linked to an **Instagram Business Account**

3. **OpenAI API Key** (for AI content generation)
   - Get from [platform.openai.com](https://platform.openai.com/api-keys)

4. **Cloudinary Account** (for image hosting - required for Instagram)
   - Free tier available at [cloudinary.com](https://cloudinary.com)

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd auto_posting

# Install dependencies
pip install -e .
```

## Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```env
# Meta (Facebook/Instagram)
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_PAGE_ID=your_facebook_page_id
META_INSTAGRAM_ACCOUNT_ID=your_instagram_business_account_id

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

3. Run OAuth setup to authenticate with Meta:
```bash
python scripts/setup_oauth.py
```

4. Save the generated `ENCRYPTION_KEY` to your `.env` file.

## Usage

### Verify Configuration
```bash
python -m auto_posting.main verify
```

### Create a Single Post
```bash
# Post to both Facebook and Instagram
python -m auto_posting.main post "Your topic here"

# Post to Facebook only
python -m auto_posting.main post "Your topic" --facebook

# Post to Instagram only
python -m auto_posting.main post "Your topic" --instagram

# Post without AI-generated image
python -m auto_posting.main post "Your topic" --no-image
```

### Test API Connections
```bash
python scripts/test_post.py
```

## Project Structure

```
auto_posting/
├── .env                        # Your credentials (not in git)
├── .env.example                # Template for credentials
├── pyproject.toml              # Project dependencies
├── README.md                   # This file
├── scripts/
│   ├── fb_get_page_token.py    # Short-lived token -> Page Access Token
│   ├── fb_post.py              # Post text + local images (stdlib only)
│   ├── setup_oauth.py          # OAuth authentication setup
│   └── test_post.py            # Test posting without AI
└── src/auto_posting/
    ├── main.py                 # CLI entry point
    ├── config.py               # Settings management
    ├── auth/
    │   └── token_manager.py    # OAuth token handling
    ├── content/
    │   ├── text_generator.py   # OpenAI GPT-4 integration
    │   └── image_generator.py  # OpenAI DALL-E 3 integration
    ├── publishers/
    │   ├── facebook.py         # Facebook Graph API (URL + local-file uploads)
    │   ├── instagram.py        # Instagram Graph API
    │   └── media_uploader.py   # Cloudinary image hosting
    └── utils/
        ├── rate_limiter.py     # API rate limiting
        └── retry.py            # Exponential backoff
```

## API Limitations

| Limit | Value |
|-------|-------|
| API calls | 200/user/hour |
| Posts | 100/account/24 hours |
| Instagram hashtags | 5 max per post |
| Carousel images | 10 max |

## Troubleshooting

### "Invalid Scopes" Error
Add the required permissions in Meta Developer Dashboard:
1. Go to your app → Use cases
2. Click "Customize" on each use case
3. Add: `pages_manage_posts`, `instagram_content_publish`, etc.

### "No credits remaining" (OpenAI)
Add credits at [platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing)

### Instagram "Image URL" Error
Instagram requires publicly accessible HTTPS URLs. Make sure Cloudinary is configured correctly.

## License

MIT
