# Meta Developer Setup Guide

This guide walks you through getting all the credentials needed for the Auto-Posting Agent.

## What You'll Need

| Field | Description | Where to Get |
|-------|-------------|--------------|
| `META_APP_ID` | Your Meta App ID | App Dashboard |
| `META_APP_SECRET` | Your Meta App Secret | App Dashboard |
| `META_PAGE_ID` | Your Facebook Page ID | Page Settings or Graph API |
| `META_INSTAGRAM_ACCOUNT_ID` | Instagram Business Account ID | Graph API |

---

## Step 1: Create a Facebook Page (if you don't have one)

1. Go to [facebook.com/pages/create](https://www.facebook.com/pages/create)
2. Choose a category (Business, Brand, etc.)
3. Enter your Page name and details
4. Click **Create Page**

---

## Step 2: Convert Instagram to Business Account

Your Instagram account must be a **Business** or **Creator** account linked to your Facebook Page.

1. Open **Instagram app** on your phone
2. Go to **Settings** → **Account** → **Switch to Professional Account**
3. Select **Business**
4. Choose a category
5. **Connect to Facebook Page** → Select your Page from Step 1 then click **Edit Profile**
6. Complete the setup

![Figure1](https://res.cloudinary.com/drejlqjgi/image/upload/v1785907172/f50bbf8a-90ee-4f43-a38c-748c829916e8_oprjal.jpg)

---

## Step 3: Create Meta Developer Account

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **Get Started** (top right)
3. Log in with your Facebook account
4. Accept the Developer Policy
5. Verify your account (phone or email)

---

## Step 4: Create a Meta App

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Click **Create App**
3. Select **Other** → Click **Next**
4. Select **Business** type → Click **Next**
5. Enter:
   - **App name**: e.g., "Auto Posting Agent"
   - **Contact email**: Your email
   - **Business Account**: (optional, can skip)
6. Click **Create App**

---

## Step 5: Get App ID and App Secret

After creating your app:

1. Go to **App Dashboard** → **Settings** → **Basic**
2. You'll see:
   - **App ID**: Copy this → `META_APP_ID`
   - **App Secret**: Click **Show** → Copy this → `META_APP_SECRET`

```
META_APP_ID=1234567890123456
META_APP_SECRET=abcdef1234567890abcdef1234567890
```

---

## Step 6: Configure OAuth Settings

1. Go to **Facebook Login** → **Settings** (left sidebar)
2. Under **Valid OAuth Redirect URIs**, add:
   ```
   http://localhost:8080/callback
   ```
  (if app in development mode, http://localhost:8080/callback is enable by default)

3. Enable:
   - ✅ Client OAuth Login
   - ✅ Web OAuth Login
4. Click **Save Changes**

---

## Step 7: Add Required Permissions

1. Go to **App Dashboard** → **Use Cases** (left sidebar)
2. You'll see use cases like:
   - "Manage Instagram messages and content"
   - "Manage all Page content"

3. Click **Customize** on each use case and add these permissions:

### For Facebook Pages:
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`

### For Instagram:
- `instagram_basic`
- `instagram_content_publish`

4. After adding, each permission should show **"Ready for testing"** (可供測試)

---

## Step 8: Get Facebook Page ID

### Option A: From Page Settings
1. Go to your Facebook Page
2. Click **Settings** (or About)
3. Scroll down to find **Page ID**

### Option B: Using Graph API Explorer
1. Go to [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. Select your App from the dropdown
3. Click **Generate Access Token**
4. Grant permissions when prompted
5. In the query field, enter: `me/accounts`
6. Click **Submit**
7. Find your Page in the response:
   ```json
   {
     "data": [
       {
         "name": "Your Page Name",
         "id": "123456789012345"  ← This is your META_PAGE_ID
       }
     ]
   }
   ```

```
META_PAGE_ID=123456789012345
```

---

## Step 9: Get Instagram Business Account ID

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer)
2. Make sure you have a valid access token
3. In the query field, enter:
   ```
   {PAGE_ID}?fields=instagram_business_account
   ```
   Replace `{PAGE_ID}` with your Facebook Page ID from Step 8

4. Click **Submit**
5. The response will show:
   ```json
   {
     "instagram_business_account": {
       "id": "17841400000000000"  ← This is your META_INSTAGRAM_ACCOUNT_ID
     },
     "id": "123456789012345"
   }
   ```

```
META_INSTAGRAM_ACCOUNT_ID=17841400000000000
```

---

## Step 10: Add Yourself as Tester (Optional but Recommended)

For development/testing, ensure your Facebook account has a role:

1. Go to **App Dashboard** → **App Roles** → **Roles**
2. Verify you're listed as **Administrator**
3. Or click **Add People** to add testers

---

## Final .env Configuration

After completing all steps, your `.env` should have:

```env
# Meta Configuration
META_APP_ID=1234567890123456
META_APP_SECRET=abcdef1234567890abcdef1234567890
META_PAGE_ID=123456789012345
META_PAGE_ACCESS_TOKEN=EAAB...        # required to publish - see Step 11
META_INSTAGRAM_ACCOUNT_ID=17841400000000000
META_API_VERSION=v21.0
```

The first three IDs identify your app and Page but grant no ability to post.
Every write call to the Graph API is authorised by `META_PAGE_ACCESS_TOKEN`.

---

## Step 11: Get the Page Access Token

1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. **Meta App** = your app, **User or Page** = `User Token`
3. Add permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
4. Click **Generate Access Token** and copy it
5. Upgrade it to a non-expiring Page token:

```bash
python3 scripts/fb_get_page_token.py <SHORT_LIVED_USER_TOKEN>
```

Paste the printed `META_PAGE_ID` and `META_PAGE_ACCESS_TOKEN` into `.env`.

---

## Verify Your Setup

Post something, without publishing it, to confirm the credentials load:

```bash
python3 scripts/fb_post.py -m "hello" -i logo-gf.png --dry-run
```

Then publish for real by dropping `--dry-run`.

Alternatively, run the full browser OAuth flow (stores an encrypted token file):

```bash
python scripts/setup_oauth.py
```

Choose option 1 (Interactive) and complete the browser authentication.

---

## Troubleshooting

### "Invalid Scopes" Error
- Go to **Use Cases** and add the missing permissions
- Make sure permissions show "Ready for testing"

### "Page Not Found" Error
- Verify your `META_PAGE_ID` is correct
- Make sure your Facebook account is an admin of the Page

### "Instagram Account Not Found" Error
- Verify Instagram is converted to Business account
- Verify Instagram is linked to your Facebook Page
- Use Graph API Explorer to confirm the connection

### "App Not Approved" Error
- For development, this is fine - works for app admins/developers
- For production, you need to submit for App Review

---

## App Review (For Production)

For production use with non-admin users, you need App Review:

1. Go to **App Dashboard** → **App Review** → **Permissions and Features**
2. Click **Request** next to each permission you need
3. Provide:
   - Use case description
   - Screen recording showing how you use the permission
   - Privacy policy URL
4. Submit and wait for approval (typically 2-4 weeks)

---

## Quick Reference

| Step | Action | Result |
|------|--------|--------|
| 1 | Create Facebook Page | Page to post to |
| 2 | Convert Instagram to Business | Instagram linked to Page |
| 3 | Create Developer Account | Access to developer tools |
| 4 | Create Meta App | App container |
| 5 | Get App ID & Secret | `META_APP_ID`, `META_APP_SECRET` |
| 6 | Configure OAuth | Redirect URI working |
| 7 | Add Permissions | API access granted |
| 8 | Get Page ID | `META_PAGE_ID` |
| 9 | Get Instagram ID | `META_INSTAGRAM_ACCOUNT_ID` |
| 10 | Run OAuth Setup | Tokens saved |
| 11 | Get Page Access Token | `META_PAGE_ACCESS_TOKEN` - required to publish |
