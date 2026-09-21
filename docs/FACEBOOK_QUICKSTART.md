# 自動發 FB 貼文 — 最短路徑

## 你手上有的三個值不夠

| 值 | 用途 | 能不能發文 |
|----|------|-----------|
| `META_APP_ID` | 識別你的 App | ❌ 只是身分 |
| `META_APP_SECRET` | 換 token 時證明是你 | ❌ 只是身分 |
| `META_PAGE_ID` | 指定要發到哪個粉專 | ❌ 只是目標 |
| **`META_PAGE_ACCESS_TOKEN`** | **真正的授權憑證** | ✅ **缺這個就發不了** |

Graph API 的每一個寫入請求都要帶 **Page Access Token**，而且那個 token 必須附帶
`pages_manage_posts` 權限。App ID / Secret 只能用來「換」token，本身不能發文。

除此之外還要確認兩件事：

1. App 後台已加入 **Facebook Login for Business**（或 Facebook Login）產品。
2. Use cases → Permissions 已勾選 `pages_show_list`、`pages_read_engagement`、`pages_manage_posts`。
   開發模式下你自己是 App 管理員就能用；要給別人用才需要送 App Review。

> 只發 Facebook **不需要** Cloudinary，也不需要公開圖片網址 —— 圖片直接以
> multipart 上傳位元組即可。Cloudinary 只有 Instagram 才需要（IG 強制要 public HTTPS URL）。

---

## Step 1 — 拿一個短期 User Token（1 小時，夠用）

1. 打開 [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. **Meta App** 選你的 App
3. **User or Page** 選 `User Token`
4. **Permissions** 加上 `pages_show_list`、`pages_read_engagement`、`pages_manage_posts`
5. 按 **Generate Access Token**，複製那串字

## Step 2 — 換成永不過期的 Page Token

```bash
python3 scripts/fb_get_page_token.py <剛剛複製的短期 token>
```

它會做三件事：短期 → 長期 User Token（60 天）→ 取出各粉專的 Page Token，
並驗證權限。Page Token 是從長期 User Token 衍生出來的，**不會過期**
（除非你改密碼或手動撤銷）。

把輸出的兩行貼進 `.env`：

```env
META_PAGE_ID=...
META_PAGE_ACCESS_TOKEN=...
```

## Step 3 — 發文

```bash
# 文字 + 一張本機圖片（你要的那則）
python3 scripts/fb_post.py --message "LFG GoalFi !" --image logo-gf.png

# 只發文字
python3 scripts/fb_post.py -m "Hello world"

# 多張圖（輪播，最多 10 張）
python3 scripts/fb_post.py -m "Gallery" -i a.png -i b.png

# 先確認參數，不真的送出
python3 scripts/fb_post.py -m "LFG GoalFi !" -i logo-gf.png --dry-run
```

成功會印出 `post_id` 和貼文連結。

---

## 在程式裡呼叫

```python
import asyncio
from auto_posting.auth.token_manager import TokenManager
from auto_posting.config import get_settings
from auto_posting.publishers.facebook import FacebookPublisher

async def main():
    settings = get_settings()
    publisher = FacebookPublisher(settings, TokenManager(settings))
    post = await publisher.publish_photo_file("logo-gf.png", caption="LFG GoalFi !")
    print(post.post_id, post.permalink)
    await publisher.close()

asyncio.run(main())
```

`publish_photo_file()` 走本機檔案上傳；`publish_photo()` 則是給已經有公開網址的圖片用。

---

## 錯誤碼對照

| Code | 意思 | 怎麼修 |
|------|------|--------|
| 190 | Token 失效或過期 | 重跑 `fb_get_page_token.py` |
| 200 | 權限不足 | Page Token 缺 `pages_manage_posts`，重新產生 User Token 時勾選它 |
| 100 | 參數錯誤 | `META_PAGE_ID` 不對，或 token 屬於別的粉專 |
| 368 | 被暫時封鎖 | 發文太頻繁，等一段時間 |

## 限制

- 單一粉專 24 小時內最多 100 篇
- 每小時 200 次 API 呼叫
- 一則貼文最多 10 張圖
