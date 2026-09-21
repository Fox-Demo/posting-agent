# Auto-Posting Agent

自動發文到 **Facebook 粉絲專頁** 和 **Instagram 商業帳號** 的工具。
可以手動指定圖文發布，也可以用 OpenAI 自動生成內容再發布。

---

## 目錄

- [兩種使用方式](#兩種使用方式)
- [五分鐘快速開始](#五分鐘快速開始)
- [安裝](#安裝)
- [.env 要放什麼](#env-要放什麼)
- [取得憑證：完整步驟](#取得憑證完整步驟)
- [腳本一覽](#腳本一覽)
- [發文到 Facebook](#發文到-facebook)
- [發文到 Instagram](#發文到-instagram)
- [AI 自動生成並發文](#ai-自動生成並發文)
- [驗證與除錯](#驗證與除錯)
- [專案結構](#專案結構)
- [錯誤碼對照](#錯誤碼對照)
- [平台限制](#平台限制)
- [安全注意事項](#安全注意事項)

---

## 兩種使用方式

這個 repo 有兩套互相獨立的介面，先搞清楚你要哪一種：

| | 命令列腳本 | AI Agent |
|---|---|---|
| 指令 | `scripts/fb_post.py`、`scripts/ig_post.py` | `python -m auto_posting.main post` |
| 內容來源 | **你自己寫**文字、自己準備圖片 | **OpenAI 自動生成**文字 + DALL·E 生圖 |
| 需要 OpenAI API Key | ❌ 不用 | ✅ 必須 |
| 需要安裝套件 | ❌ 純 stdlib，任何 `python3` 都能跑 | ✅ 要 `pip install -e .` |
| 適合 | 精準控制發什麼、日常發文 | 批量產內容、實驗性質 |

**建議先從命令列腳本開始**，設定少、失敗點少，確認整條線路通了再玩 AI 那套。

---

## 五分鐘快速開始

只想發一則圖文到 Facebook：

```bash
# 1. 從 Graph API Explorer 複製一個短期 User Token，然後換成永久 Page Token
python3 scripts/fb_get_page_token.py <短期_USER_TOKEN>
#    -> 把輸出的 META_PAGE_ACCESS_TOKEN 貼進 .env

# 2. 發文
python3 scripts/fb_post.py -m 'LFG GoalFi !' -i logo-gf.png
```

Instagram 多兩個前置作業（IG 專業帳號 + Cloudinary），設定完之後：

```bash
python3 scripts/ig_post.py --check                              # 先檢查設定
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png --square
```

詳細步驟看下面。

---

## 安裝

命令列腳本（`fb_post.py`、`ig_post.py`、`fb_get_page_token.py`）**不需要安裝任何東西**，
它們只用 Python 標準函式庫，有 `python3` 就能跑。

要用 AI 功能才需要安裝：

```bash
git clone <your-repo-url>
cd posting-agent

python3 -m venv venv
source venv/bin/activate
pip install -e .

# 要跑測試和 lint 再加 dev
pip install -e ".[dev]"
```

需求：Python 3.10 以上。

---

## .env 要放什麼

複製範本：

```bash
cp .env.example .env
```

### 欄位對照表

| 欄位 | 發 FB | 發 IG | AI 功能 | 從哪裡拿 |
|------|:----:|:----:|:------:|---------|
| `META_APP_ID` | ✅ | ✅ | ✅ | Meta App 後台 → 設定 → 基本資料 |
| `META_APP_SECRET` | ✅ | ✅ | ✅ | 同上（要按「顯示」） |
| `META_PAGE_ID` | ✅ | ✅ | ✅ | 粉專 → 關於 → 頁面透明度，或用 Graph API 查 |
| `META_PAGE_ACCESS_TOKEN` | ✅ | ✅ | ✅ | **跑 `fb_get_page_token.py` 產生**，不要手動貼 |
| `META_INSTAGRAM_ACCOUNT_ID` | — | ✅ | ✅ | `ig_post.py` 會自動幫你查出來 |
| `META_API_VERSION` | ✅ | ✅ | ✅ | 填 `v21.0`，有預設值 |
| `CLOUDINARY_CLOUD_NAME` | — | ✅ | ✅ | Cloudinary Dashboard 首頁 |
| `CLOUDINARY_API_KEY` | — | ✅ | ✅ | 同上 |
| `CLOUDINARY_API_SECRET` | — | ✅ | ✅ | 同上 |
| `CLOUDINARY_UPLOAD_FOLDER` | — | ✅ | ✅ | 隨便取，例如 `auto_posting` |
| `OPENAI_API_KEY` | — | — | ✅ | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ENCRYPTION_KEY` | — | — | 選填 | 不填會自動產生 |

### 完整範例

```env
# ---- Meta (Facebook / Instagram) ----
META_APP_ID=1234567890123456              # 16 位數字
META_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 32 位十六進位
META_PAGE_ID=1234567890123456             # 16 位數字
META_PAGE_ACCESS_TOKEN=EAAxxxxx...        # 跑 fb_get_page_token.py 取得
META_INSTAGRAM_ACCOUNT_ID=17841400000000000        # 17 位，開頭通常是 1784
META_API_VERSION=v21.0

# ---- Cloudinary（只有 IG 需要）----
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=123456789012345
CLOUDINARY_API_SECRET=your_api_secret
CLOUDINARY_UPLOAD_FOLDER=auto_posting

# ---- OpenAI（只有 AI 功能需要）----
OPENAI_API_KEY=sk-...
OPENAI_TEXT_MODEL=gpt-4
OPENAI_IMAGE_MODEL=dall-e-3

# ---- 其他 ----
DEBUG=false
LOG_LEVEL=INFO
```

> ⚠️ `.env` 已經在 `.gitignore` 裡，**絕對不要 commit**。裡面每一個值都等於你帳號的鑰匙。

---

## 取得憑證：完整步驟

### Step 1 — 建立 Meta App

1. 到 [developers.facebook.com](https://developers.facebook.com) → **我的應用程式** → **建立應用程式**
2. 用途選 **其他** → 類型選 **商業**
3. 建好後進入 App → **設定** → **基本資料**
4. 複製 **應用程式編號** 和 **應用程式密鑰** 進 `.env`
5. 左側 **新增產品** → 加入 **Facebook 登入** 或 **Facebook Login for Business**

### Step 2 — 準備粉專與 IG 帳號

**Facebook 粉專**：你必須是該粉專的管理員。粉專 ID 在「關於 → 頁面透明度」裡。

**Instagram**（只有要發 IG 才需要）：

1. IG App → 右下角頭像 → ☰ → **設定和隱私**
2. **帳號類型和工具** → **切換成專業帳號** → 選**商業**或**創作者**
3. 過程中選擇要連結的 Facebook 粉專

> 判斷有沒有切成功：IG 側邊欄出現「**主控板**」就是專業帳號了。
> 個人帳號**沒有** API 可以發文，這點無法繞過。

連結粉專比較可靠的做法是從 Facebook 端做：
粉專 → **設定** → **已連結的帳號** → **Instagram** → **連結帳號**。

### Step 3 — 產生 Page Access Token

App ID 和 App Secret **不能直接發文**，它們只能用來「換」token。

1. 打開 [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. **Meta 應用程式** 選你的 App，**用戶或粉絲專頁** 選 `用戶權杖`
3. **Permissions** 加入這些：

   | 權限 | 用途 |
   |------|------|
   | `pages_show_list` | 列出你管理的粉專 |
   | `pages_read_engagement` | 讀取粉專資料 |
   | `pages_manage_posts` | **發 FB 貼文必須** |
   | `instagram_basic` | 讀取 IG 帳號資訊 |
   | `instagram_content_publish` | **發 IG 貼文必須** |

4. 按 **Generate Access Token**，複製那串
5. 換成永不過期的 Page Token：

```bash
python3 scripts/fb_get_page_token.py <剛複製的短期 token>
```

6. 把輸出的 `META_PAGE_ACCESS_TOKEN=...` 貼回 `.env`

> **兩個最常踩的坑：**
> 1. 加完權限要**再按一次** Generate Access Token，舊的那串不會自動帶上新權限。
> 2. 不要把 Graph API Explorer 那串直接貼進 `.env`——那是**短期 User Token**，
>    一小時就過期。一定要跑 `fb_get_page_token.py` 換成 **Page Token**（永不過期）。

### Step 4 — Cloudinary（只有發 IG 需要）

IG 的 API **不收本機檔案**，只吃公開的 HTTPS 網址。所以圖片要先傳到某個公開的地方。

1. 到 [cloudinary.com](https://cloudinary.com) 免費註冊
2. Dashboard 首頁直接顯示 **Cloud name**、**API Key**、**API Secret**
3. 貼進 `.env`

免費方案每月 25 credits，發圖文用量連零頭都用不到。

> 不想用 Cloudinary 也行。任何公開 HTTPS 網址都可以，用
> `ig_post.py --image-url https://...` 直接指定，完全跳過這步。

### Step 5 — OpenAI（只有 AI 功能需要）

到 [platform.openai.com/api-keys](https://platform.openai.com/api-keys) 建立 API Key，
填進 `OPENAI_API_KEY`。記得帳戶要有額度。

---

## 腳本一覽

| 腳本 | 做什麼 | 需要裝套件 |
|------|--------|:---------:|
| `scripts/fb_get_page_token.py` | 短期 User Token → 永久 Page Token | ❌ |
| `scripts/fb_post.py` | 發文字 / 圖文到 FB 粉專 | ❌ |
| `scripts/ig_post.py` | 發圖文到 IG，含 Cloudinary 上傳 | ❌ |
| `scripts/test_post.py` | 測試 FB/IG 連線，不經過 AI | ✅ |
| `scripts/setup_oauth.py` | 瀏覽器 OAuth 流程（進階，一般用不到） | ✅ |
| `python -m auto_posting.main` | AI 生成內容並發布 | ✅ |

---

## 發文到 Facebook

```bash
# 文字 + 一張本機圖片
python3 scripts/fb_post.py -m 'LFG GoalFi !' -i logo-gf.png

# 只發文字
python3 scripts/fb_post.py -m 'Hello world'

# 多張圖（輪播，最多 10 張）
python3 scripts/fb_post.py -m 'Gallery' -i a.png -i b.png

# 先確認參數，不真的送出
python3 scripts/fb_post.py -m 'LFG GoalFi !' -i logo-gf.png --dry-run
```

成功會印出 `post_id` 和貼文連結。

FB 的圖片是以 multipart 直接傳位元組，**不需要 Cloudinary、不需要公開網址**，
PNG / JPEG 都收。

> 💡 zsh 請用**單引號**包訊息。雙引號裡的 `!` 會觸發歷史展開，
> 容易卡在 `dquote>`。真的卡住就按 `Ctrl + C`。

---

## 發文到 Instagram

### 先檢查設定

```bash
python3 scripts/ig_post.py --check
```

五行全 `OK` 才能發：

```
Instagram publishing prerequisites

  OK    token valid                        type=PAGE expires=never
  OK    scope instagram_basic
  OK    scope instagram_content_publish
  OK    IG Business account linked         id=17841400000000000
  OK    Cloudinary configured

Ready to publish.
```

`META_INSTAGRAM_ACCOUNT_ID` 不用自己查——腳本偵測到那欄是空的或還等於 Page ID 時，
會自動從粉專撈出正確的 IG ID 並印出來給你貼。

### 發文

```bash
# 文字 + 一張本機圖片
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png

# 小圖或 logo：補白邊成 1080x1080 正方形
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png --square

# 圖片已經有公開網址，跳過 Cloudinary
python3 scripts/ig_post.py -m 'Hello' --image-url https://example.com/a.jpg

# 輪播，2~10 張
python3 scripts/ig_post.py -m 'Gallery' -i a.png -i b.png

# 只上傳到 Cloudinary 印出網址，不發布
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png --square --dry-run
```

### IG 的圖片規格

IG 的檢查比 FB 嚴格很多，腳本會自動處理：

| 項目 | IG 的限制 | 腳本怎麼處理 |
|------|----------|-------------|
| 格式 | **只接受 JPEG**，PNG 會被拒 | Cloudinary `f_jpg` 自動轉檔 |
| 長寬比 | 4:5 ～ 1.91:1 | `--square` 補白邊成 1:1 |
| 寬度 | 建議 1080px，最低 320px | `w_1080` 自動處理 |
| 檔案大小 | 最大 8MB | `q_auto` 自動壓縮 |

預設轉換是 `f_jpg,q_auto,w_1080,c_limit`，`--square` 是
`f_jpg,q_auto,w_1080,h_1080,c_pad,b_white`。要自訂用 `--transform`：

```bash
python3 scripts/ig_post.py -m '...' -i photo.jpg --transform 'f_jpg,w_1080,c_fill,g_auto'
```

更詳細的說明看 **[Instagram Quickstart](docs/INSTAGRAM_QUICKSTART.md)**。

---

## AI 自動生成並發文

這部分需要 `pip install -e .` 和 `OPENAI_API_KEY`。

```bash
source venv/bin/activate

# 同時發到 FB 和 IG
python -m auto_posting.main post "區塊鏈入門"

# 只發 Facebook
python -m auto_posting.main post "區塊鏈入門" --facebook

# 只發 Instagram
python -m auto_posting.main post "區塊鏈入門" --instagram

# 不生圖（IG 會被跳過，因為 IG 一定要有圖）
python -m auto_posting.main post "區塊鏈入門" --no-image
```

流程是：GPT 生文案 → DALL·E 生圖 → 上傳 Cloudinary → 分別發到兩個平台。
單一平台失敗不會影響另一個，最後會印出各平台的結果。

### 在自己的程式裡呼叫

```python
import asyncio
from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import get_settings
from auto_posting.publishers.facebook import FacebookPublisher
from auto_posting.publishers.instagram import InstagramPublisher
from auto_posting.publishers.media_uploader import MediaUploader

async def main():
    settings = get_settings()

    # Facebook：可以直接吃本機檔案
    fb = FacebookPublisher(settings, TokenManager(settings))
    post = await fb.publish_photo_file("logo-gf.png", caption="LFG GoalFi !")
    print(post.post_id, post.permalink)
    await fb.close()

    # Instagram：要先變成公開網址
    uploader = MediaUploader(settings)
    media = uploader.upload_bytes(open("logo-gf.png", "rb").read(), "logo")

    ig = InstagramPublisher(settings, TokenManager(settings))
    ig_post = await ig.publish_image(media.instagram_url, caption="LFG GoalFi !")
    print(ig_post.media_id, ig_post.permalink)
    await ig.close()

asyncio.run(main())
```

> ⚠️ `InstagramPublisher` 內建 `MAX_HASHTAGS = 5`，caption 超過 5 個 hashtag 會被砍掉多的。
> 這是本專案自己的規則，不是 IG 的限制（IG 允許 30 個）。要全部保留就改
> `src/auto_posting/publishers/instagram.py` 裡那個常數，或改用 `scripts/ig_post.py`，
> 命令列這支不會動你的 caption。

---

## 驗證與除錯

```bash
# 檢查 IG 發文的所有前置條件（最常用）
python3 scripts/ig_post.py --check

# 檢查完整設定：Meta / OpenAI / Cloudinary 都看
python -m auto_posting.main verify --log-level WARNING

# 測試 FB / IG 連線，不經過 AI
python scripts/test_post.py
```

> ⚠️ `verify` 在 `--log-level INFO`（預設）時，httpx 會把**完整 access token 印在
> log 裡**。要貼給別人看的時候記得加 `--log-level WARNING`。

驗證 token 本身的狀態：

```bash
python3 scripts/fb_get_page_token.py <任何一個 user token>
```

它會列出你所有粉專、標出哪個對應 `META_PAGE_ID`，並檢查權限齊不齊。

---

## 專案結構

```
posting-agent/
├── .env                          # 你的憑證（不進 git）
├── .env.example                  # 範本
├── pyproject.toml                # 套件定義
├── README.md                     # 本文件
├── docs/
│   ├── FACEBOOK_QUICKSTART.md    # FB 發文最短路徑
│   ├── INSTAGRAM_QUICKSTART.md   # IG 發文最短路徑
│   └── META_SETUP_GUIDE.md       # Meta 後台圖文教學
├── scripts/
│   ├── fb_get_page_token.py      # 短期 token -> 永久 Page Token
│   ├── fb_post.py                # FB 發文（純 stdlib）
│   ├── ig_post.py                # IG 發文（純 stdlib，含 Cloudinary）
│   ├── setup_oauth.py            # 瀏覽器 OAuth 流程
│   └── test_post.py              # 連線測試
└── src/auto_posting/
    ├── main.py                   # AI CLI 進入點
    ├── config.py                 # 設定管理（pydantic-settings）
    ├── auth/
    │   └── token_manager.py      # Token 處理與加密儲存
    ├── content/
    │   ├── text_generator.py     # GPT 文案生成
    │   └── image_generator.py    # DALL·E 生圖
    ├── publishers/
    │   ├── facebook.py           # FB Graph API
    │   ├── instagram.py          # IG Graph API（兩步發布）
    │   └── media_uploader.py     # Cloudinary 上傳
    └── utils/
        ├── rate_limiter.py       # 流量限制
        └── retry.py              # 指數退避重試
```

---

## 錯誤碼對照

### Facebook

| Code | 意思 | 怎麼修 |
|------|------|--------|
| 190 | Token 失效或過期 | 重跑 `fb_get_page_token.py` |
| 200 | 權限不足 | 缺 `pages_manage_posts`，重產 token 時勾選 |
| 100 | 參數錯誤 | `META_PAGE_ID` 不對，或 token 屬於別的粉專 |
| 368 | 被暫時封鎖 | 發文太頻繁，等一段時間 |

### Instagram

| Code | 意思 | 怎麼修 |
|------|------|--------|
| 190 | Token 失效或過期 | 重跑 `fb_get_page_token.py` |
| 200 | 權限不足 | 缺 `instagram_content_publish` |
| 9004 | IG 抓不到圖片 | 網址不是公開的，或不是 HTTPS |
| 2207026 | 格式不支援 | 圖不是 JPEG，加 `--square` 或檢查 `--transform` |
| 2207003 | 下載圖片逾時 | 圖太大或主機太慢，壓縮後重試 |
| 4 | 觸發流量限制 | 24 小時內超過 50 篇 |
| 100 | 參數錯誤 | `META_INSTAGRAM_ACCOUNT_ID` 填錯（常見：填成 Page ID） |

### 其他常見狀況

**`--check` 說 IG Business account linked FAIL，但我明明連了**
Token 缺 `instagram_basic` 時也會查不到，症狀跟沒連結一模一樣。先確認 Step 3 做完。

**`socket.gaierror: nodename nor servname provided`**
DNS 解析失敗，不是程式的問題。用 `ping 1.1.1.1` 確認網路通不通，
再試 `nslookup graph.facebook.com 1.1.1.1`。如果換 DNS 就好了，
把系統 DNS 改成 `1.1.1.1` / `8.8.8.8`。

**發布卡在 `waiting for Instagram to fetch it`**
IG 正在抓圖，通常幾秒。超過 5 分鐘腳本會逾時。
先用 `--dry-run` 拿網址貼到瀏覽器確認打得開。

**`Invalid Scopes` 錯誤**
Meta App 後台 → **Use cases** → 每個 use case 按 **Customize** → 加入需要的權限。

---

## 平台限制

| 限制 | Facebook | Instagram |
|------|----------|-----------|
| 每 24 小時發文數 | 100 篇 | 50 篇 |
| API 呼叫 | 200 次/小時 | 200 次/小時 |
| 單則圖片數 | 10 張 | 10 張 |
| 純文字貼文 | ✅ 可以 | ❌ 一定要有媒體 |
| Caption 長度 | 63,206 字元 | 2,200 字元 |
| Container 有效期 | — | 建立後 24 小時內要發布 |

---

## 安全注意事項

- **`.env` 絕對不要 commit**。已經寫進 `.gitignore`，但 `git add -f` 還是能強推進去。
- **Page Access Token 永不過期**，等於一把不會自己失效的鑰匙。外洩了要到
  [Meta 帳號設定](https://www.facebook.com/settings?tab=applications) 移除該 App 才會失效。
- **不要把 token 貼在聊天室、issue、截圖裡**。需要給別人 debug 時只給 `debug_token` 的輸出。
- `verify` 指令預設會在 log 裡印出完整 token，分享輸出前加 `--log-level WARNING`。
- App Secret 外洩比 token 更嚴重——可以用它換出新 token。真的外洩就去
  App 後台 → 設定 → 基本資料 → **重設應用程式密鑰**。

---

## License

MIT
