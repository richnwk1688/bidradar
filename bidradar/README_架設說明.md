# 📡 標案雷達 v1 — 架設說明（照抄就會動）

這台雷達做的事：每天早上八點，自動掃全台灣前一兩天的政府標案公告，
只要是「東港周邊七個公所發的任何案」或「屏東縣政府發的影片／行銷／AI／系統案」，
就推播到你的 LINE。全程免費。

---

## 第一步：把這包丟上 GitHub（用電腦做，10分鐘，一次就好）

1. 去 github.com 註冊帳號（免費）
2. 右上角「+」→「New repository」→ 名字打 `bidradar` → 選 **Private** → Create
3. 進到新倉庫 → 「uploading an existing file」→ 把這包裡的檔案全部拖進去 → Commit
   - 注意：`.github/workflows/radar.yml` 要照這個路徑放（資料夾結構不能變）

## 第二步：接上你的 LINE（15分鐘）

1. 去 developers.line.biz 用你的 LINE 官方帳號登入
2. 選你的 Provider → 選 Messaging API 的 Channel（沒有就建一個）
3. 「Messaging API」分頁最下面 → **Channel access token** → 按 Issue → 複製那串
4. 「Basic settings」分頁最下面 → **Your user ID** → 複製（這是你自己的ID，推播只推給你）
5. 回 GitHub 倉庫 → Settings → Secrets and variables → Actions → New repository secret，加兩筆：
   - 名字 `LINE_CHANNEL_ACCESS_TOKEN`，值＝第3步那串
   - 名字 `LINE_ADMIN_USER_ID`，值＝第4步那串

> 懶得先弄 LINE？可以跳過第二步。雷達照跑，
> 結果會自動開成倉庫裡的 Issue，GitHub App 也會跳通知給你。

## 第三步：按一次測試

倉庫上方「Actions」→ 左邊「標案雷達」→ 右邊「Run workflow」→ 綠色按鈕。
跑完點進去看 log，看到「今日無命中」或命中清單，就是活了。
之後每天早上八點自動跑，不用管它。

---

## 想改監控範圍？

只要編輯 `keywords.json`（GitHub 網頁上點鉛筆就能改）：

- `watch_all_units`：這些機關發的**每一案**都通報（現在＝東港周邊七公所）
- `watch_topic_units`：這些大機關，案名要含 `topics` 關鍵字才通報（現在＝屏東縣政府）
- `topics`：主題詞（影片、行銷、AI、系統……）
- `exclude`：黑名單詞（工程雜訊全擋）
- `days_back`：往回掃幾天（預設2，怕漏可改3）

## 之後怎麼變成商品賣？

這台是單人版。要賣，就是三步升級：
1. 把「關鍵字設定」做成網頁表單，一個客戶一組設定
2. 推播從「推你一個人」改成「推到各客戶的 LINE」
3. 掛 ECPay 收月費（你本來就有金流）＝「標案雷達」訂閱制商品

先自己用一個月，抓到第一個案，見證就有了，再開賣。
