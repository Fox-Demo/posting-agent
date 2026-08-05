# Auto-Posting Agent

An AI-powered agent that automatically generates text and images, then posts to Facebook and Instagram.

## Features

- **AI Content Generation**: Uses OpenAI GPT-4 for text and DALL-E 3 for images
- **Multi-Platform Publishing**: Posts to Facebook Pages and Instagram Business accounts
- **Scheduled Posting**: Automate posts at specified intervals using APScheduler
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

### Scheduled Posting
```bash
# Schedule posts with topics
python -m auto_posting.main schedule --topics "Tech news" "AI updates" "Startup tips"

# Custom interval (hours between posts)
python -m auto_posting.main schedule --topics "Topic 1" "Topic 2" --interval 4

# Load topics from file
python -m auto_posting.main schedule --topics-file topics.txt
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
    │   ├── facebook.py         # Facebook Graph API
    │   ├── instagram.py        # Instagram Graph API
    │   └── media_uploader.py   # Cloudinary image hosting
    ├── scheduler/
    │   └── scheduler.py        # APScheduler jobs
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
