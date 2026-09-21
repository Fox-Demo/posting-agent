# 自動發 IG 貼文 — 最短路徑

## IG 跟 FB 不一樣的三件事

先理解這三點，後面所有步驟才有意義：

| | Facebook | Instagram |
|---|---|---|
| 圖片怎麼給 API | multipart 直接傳位元組 | **只吃公開的 HTTPS 網址**，不收本機檔案 |
| 純文字貼文 | 可以 | **不行**，一定要有圖或影片 |
| 發布流程 | 一次 API 呼叫 | 兩步：建 container → 等它抓圖 → publish |

「只吃公開網址」是 IG 最大的坑：你本機的 `logo-gf.png`，IG 伺服器看不到。
所以必須先把圖傳到一個公開的地方（Cloudinary、S3、R2⋯⋯），拿到網址再交給 IG。
這就是為什麼 FB 不需要 Cloudinary，IG 需要。

---

## 你需要準備的東西

| 值 | 用途 | FB 發文有用到嗎 |
|----|------|----------------|
| `META_PAGE_ACCESS_TOKEN` | 授權憑證，需含 `instagram_content_publish` | 有，但權限要再加 |
| `META_INSTAGRAM_ACCOUNT_ID` | IG 商業帳號 ID（**不是** Page ID，也不是帳號名稱） | 沒有 |
| `CLOUDINARY_CLOUD_NAME` | 圖片託管 | 沒有 |
| `CLOUDINARY_API_KEY` | 圖片託管 | 沒有 |
| `CLOUDINARY_API_SECRET` | 圖片託管 | 沒有 |

另外 IG 帳號本身必須是**商業或創作者帳號**，而且**連結到你的 Facebook 粉專**。
個人帳號沒有 API 可以發文，這點無法繞過。

---

## Step 1 — IG 切換成專業帳號並連結粉專

這步只能在手機上做。

1. 開 **Instagram App** → 右下角頭像 → 右上角 ☰ → **設定和隱私**
2. **帳號類型和工具** → **切換成專業帳號**
3. 選 **商業** 或 **創作者**（兩種都能用 API）
4. 選一個分類
5. 過程中會問要連結哪個 Facebook 粉專 → 選你的粉專

如果當下跳過了連結粉專，補做的路徑是：
**編輯個人檔案** → **粉絲專頁** → 選擇你的粉專。

驗證做好了沒：

```bash
python3 scripts/ig_post.py --check
```

看到 `OK    IG Business account linked   id=1784...` 就成功了。

---

## Step 2 — 申請 Cloudinary

1. 到 [cloudinary.com](https://cloudinary.com) 免費註冊
2. 登入後 Dashboard 首頁直接顯示 **Cloud name**、**API Key**、**API Secret**
3. 貼進 `.env`：

```env
CLOUDINARY_CLOUD_NAME=你的_cloud_name
CLOUDINARY_API_KEY=你的_api_key
CLOUDINARY_API_SECRET=你的_api_secret
CLOUDINARY_UPLOAD_FOLDER=auto_posting
```

免費方案每月 25 credits，發圖文的用量連零頭都用不到。

> 不想用 Cloudinary 也可以。任何公開 HTTPS 網址都行（S3、Cloudflare R2、
> GitHub Pages、自己的伺服器），用 `--image-url` 直接指定，就完全跳過這步。

---

## Step 3 — 重新產生 token，補上 IG 權限

現有的 Page Token 只有 `pages_*` 權限，發 IG 會被擋。要重產一次：

1. 打開 [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. **Meta 應用程式** 選你的 App，**用戶或粉絲專頁** 選 `用戶權杖`
3. 權限在原本那幾個之外，**再加這兩個**：
   - `instagram_basic`
   - `instagram_content_publish`
4. 按 **Generate Access Token**，複製那串短期 token
5. 換成永不過期的 Page Token：

```bash
python3 scripts/fb_get_page_token.py <剛複製的短期 token>
```

6. 把輸出的 `META_PAGE_ACCESS_TOKEN=...` 貼回 `.env`

> 加完權限記得**再按一次** Generate Access Token。舊的那串不會自動帶上新權限。

---

## Step 4 — 驗收

```bash
python3 scripts/ig_post.py --check
```

五行全部 `OK` 才算準備好：

```
Instagram publishing prerequisites

  OK    token valid                        type=PAGE expires=never
  OK    scope instagram_basic
  OK    scope instagram_content_publish
  OK    IG Business account linked         id=17841400000000000
  OK    Cloudinary configured

Ready to publish.
```

`META_INSTAGRAM_ACCOUNT_ID` 不用自己查。腳本偵測到那一欄還是空的或還等於 Page ID 時，
會自動從粉專撈出正確的 IG ID 並印出來給你貼進 `.env`。

---

## Step 5 — 發文

```bash
# 文字 + 一張本機圖片
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png

# 小圖或 logo：補白邊到 1080x1080 正方形
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png --square

# 圖片已經有公開網址，跳過 Cloudinary
python3 scripts/ig_post.py -m 'Hello' --image-url https://example.com/a.jpg

# 輪播，2~10 張
python3 scripts/ig_post.py -m 'Gallery' -i a.png -i b.png

# 只上傳到 Cloudinary 印出網址，不真的發布
python3 scripts/ig_post.py -m 'LFG GoalFi !' -i logo-gf.png --square --dry-run
```

成功會印出 `media_id` 和貼文連結。

> zsh 請用**單引號**包訊息。雙引號裡的 `!` 會觸發歷史展開，容易出現 `dquote>` 卡住。

---

## 圖片規格

IG 的檢查比 FB 嚴格很多：

| 項目 | 限制 | 腳本怎麼處理 |
|------|------|-------------|
| 格式 | **只接受 JPEG**，PNG 會被拒 | Cloudinary `f_jpg` 自動轉檔 |
| 長寬比 | 4:5 ～ 1.91:1 之間 | `--square` 補白邊成 1:1 |
| 寬度 | 建議 1080px，最低 320px | `w_1080` 自動處理 |
| 檔案大小 | 最大 8MB | `q_auto` 自動壓縮 |

預設轉換是 `f_jpg,q_auto,w_1080,c_limit`，`--square` 則是
`f_jpg,q_auto,w_1080,h_1080,c_pad,b_white`。要自己指定就用 `--transform`。

---

## 在程式裡呼叫

```python
import asyncio
from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import get_settings
from auto_posting.publishers.instagram import InstagramPublisher
from auto_posting.publishers.media_uploader import MediaUploader

async def main():
    settings = get_settings()

    # 1. 先把本機圖片變成公開網址
    uploader = MediaUploader(settings)
    media = uploader.upload_bytes(open("logo-gf.png", "rb").read(), "logo")

    # 2. 再交給 IG 發布
    publisher = InstagramPublisher(settings, TokenManager(settings))
    post = await publisher.publish_image(media.instagram_url, caption="LFG GoalFi !")
    print(post.media_id, post.permalink)
    await publisher.close()

asyncio.run(main())
```

`publish_image()` 單圖、`publish_carousel()` 多圖、`publish_video()` 影片或 Reels。
三個都會自動輪詢 container 狀態，等 IG 抓完圖才發布。

> 注意：`InstagramPublisher` 內建 `MAX_HASHTAGS = 5`，caption 超過 5 個 hashtag 會被
> 自動砍掉多的。這是 `src/auto_posting/publishers/instagram.py` 自己的規則，不是 IG 的
> 限制（IG 允許 30 個）。要全部保留就改那個常數，或改用 `scripts/ig_post.py`，
> 命令列這支不會動你的 caption。

---

## 錯誤碼對照

| Code | 意思 | 怎麼修 |
|------|------|--------|
| 190 | Token 失效或過期 | 重跑 `fb_get_page_token.py` |
| 200 | 權限不足 | Token 缺 `instagram_content_publish`，重產時勾選 |
| 9004 | IG 抓不到圖片 | 網址不是公開的，或不是 HTTPS |
| 2207026 | 格式不支援 | 圖不是 JPEG，加 `--square` 或檢查 `--transform` |
| 2207003 | IG 下載圖片逾時 | 圖太大或主機太慢，壓縮後重試 |
| 4 | 觸發流量限制 | 24 小時內超過 50 篇，等一段時間 |
| 100 | 參數錯誤 | `META_INSTAGRAM_ACCOUNT_ID` 填錯（常見：填成 Page ID） |

---

## 限制

- 單一帳號 24 小時內最多 **50 篇**
- 一則輪播最多 10 張圖
- Caption 最多 2200 字元
- Container 建立後 **24 小時內**要 publish，逾期會變成 `EXPIRED`
- 無法發純文字貼文，一定要有媒體

---

## 常見卡關

**`--check` 說 IG Business account linked FAIL，但我明明連了**
Token 缺 `instagram_basic` 時也會查不到，兩者症狀一樣。先確認 Step 3 做完。

**發布卡在 `waiting for Instagram to fetch it`**
IG 正在抓你的圖。Cloudinary 通常幾秒內完成；超過 5 分鐘腳本會逾時中止。
先用 `--dry-run` 拿到網址，貼到瀏覽器確認打得開。

**貼文成功但圖被裁掉**
IG 會把不符比例的圖強制裁切。用 `--square` 先補成正方形就不會被裁。
