# CODEX_RESULT.md

## 任務：清理 media-in 中已手動刪除重複檔案後殘留的資料庫幽靈記錄
日期：2026-08-29

### 完成項目
- [x] 確認容器部署結構：後端跑在 `arkiv-arkiv-1`，DB=`/app/media.db`、chroma=`/app/chroma_db`、media-in 掛載為 rw，資料在主機與容器間同步。
- [x] 執行 `docker compose exec arkiv python ingest.py --prune-missing --dry-run`，預覽將移除 58 筆幽靈記錄。
- [x] 確認 58 筆全部屬於 `cinema_camera_film_effect_justin_odisho_super_8mm_pack_*` 批次（非該批數量 = 0），與使用者手動刪除的重複檔一致。
- [x] 執行 `docker compose exec arkiv python ingest.py --prune-missing`，結果 `removed 58/58 ghost record(s)`。
- [x] 再次 dry-run 驗證：0 ghost record(s) would be removed —— 無殘留。

### 測試結果
```
[prune-missing] dry-run: 58 ghost record(s) would be removed.   (執行前預覽)
[prune-missing] removed 58/58 ghost record(s).                   (實際執行)
[prune-missing] dry-run: 0 ghost record(s) would be removed.     (執行後驗證)
```

### 有疑慮的項目
- ⚠️ REVIEW: 此操作為不可逆的 metadata 刪除（SQLite 列 + Chroma 向量 + 衍生縮圖）。因來源檔已不存在，自動走 metadata-only 路徑，未寫入回收桶。符合使用者「移除資料庫相關資訊」意圖，但無法從回收桶還原。
- ⚠️ REVIEW: 前端列表緩存 —— 需前端重新整理（重新呼叫 `GET /api/media`）才會反映移除；未確認是否需要手動觸發或自動輪詢。

### 未完成 / 待觀察
- 前端實際顯示消失情形未由本 agent 在瀏覽器內驗證（僅確認 API/DB 層已清理）。

### 與 spec 不一致之處
- 無。使用現有 `prune-missing` 功能（routers/admin.py:82, ingest.py:2168），符合 Phase 14.5 設計。

---

## 任務：修復 Inspector 無法播放瀏覽器不相容編碼素材（音頻/影片播不出）
日期：2026-08-29

### Root Cause
- Inspector 把 `/api/stream/{id}` 直接設給 `<video>`/`<audio>` 的 `src`（Inspector.svelte:368/373），兩者皆無 `on:error` 處理。
- 後端對 prores/hevc 回 `409 {"need_proxy":true}`（codec.py:18 `PROXY_CODECS`），但前端 grep 確認**完全沒處理 `need_proxy`** → 收到 JSON 當媒體 → 媒體元素靜默失敗。
- 更嚴重：`mjpeg`(37 筆)/`qtrle`(21 筆) 不在 `PROXY_CODECS`、`.mov` 不需 remux → 後端「送原始檔」（misc.py:159-166），瀏覽器解不開 → 媒體元素也 `error`，同樣無提示。全庫共 58 筆影片（含帶聲軌的 id=341 等）屬此類。
- 純音頻 .mp3/.wav（6 筆）`kind='audio'` → `<audio controls>` 本就有播放鈕、可播，不受影響。

### 完成項目
- [x] `codec.py`：新增 `BROWSER_PLAYABLE_VIDEO` 允許清單 + `is_browser_playable_video()`，覆蓋 h264/vp9/av1/mpeg4 等。
- [x] `routers/misc.py`：stream 路由對任何不在允許清單的視頻編碼（mjpeg/qtrle/prores/hevc…）回 `409 need_proxy`，與既有 PROXY_CODECS 語意相容（h264 仍直接播、音頻 NULL 走回退）。
- [x] `api.js`：新增 `buildProxy(id)`（POST /api/proxy/build/{id}）+ `proxyStatus()`。
- [x] `Inspector.svelte`：`<video>`/`<audio>` 加 `on:error`；播放失敗時顯示「生成代理並播放」覆蓋層；新增 props `onRequestProxy`/`proxyBusy`/`proxyErr`。
- [x] `MainLive.svelte`：實作 `requestProxy(id)`——呼叫 buildProxy、輪詢 stream 直到 `200 video/mp4`、用 `proxyNonce` 強制重新載入播放器。
- [x] 重建容器 image 並重新部署（`arkiv-arkiv-1` 現跑新 image，health: healthy）。

### 測試結果
```
# 後端行為（容器內 curl，loopback 有完整 scope）
id=341 (mjpeg)  -> HTTP 409 | application/json           {"need_proxy":true,"reason":"browser-incompatible codec (mjpeg)..."}
id=121 (.mp3)   -> HTTP 200 | audio/mpeg                 (不受影響)
id=92  (prores+proxy) -> HTTP 200 | video/mp4             (proxy 可播)

# 端到端：觸發 buildProxy(341) 後輪詢 stream
poll 1-4: 409 ...  poll 5: 200 video/mp4   -> READY（代理轉為 H.264 mp4，可播）

# 前端建置
npm run build  -> ✓ built（InspectorFull chunk 含新邏輯，無 Svelte 錯誤）

# health.py
Result: 23/24 PASS, 0 FAIL, 1 SKIP

# proxies 目錄 39 -> 40（id=341 代理確實產生）
```

### 有疑慮的項目
- ⚠️ REVIEW: 前端 UI 修復僅經 `npm run build` 編譯驗證，**未在瀏覽器實機點擊驗證**（無瀏覽器環境）。後端 409/代理生成/200 流程已在容器內 curl 端到端證明；前端 `on:error`→顯示 CTA→`requestProxy`→`proxyNonce` 重載邏輯為靜態推導正確，建議上線後在瀏覽器實測一次 mjpeg 影片的「生成代理並播放」按鈕。
- ⚠️ REVIEW: 「音頻沒有播放按鈕」原始描述，純音頻檔依程式碼本就有 `<audio controls>` 播放鈕（已確認 `kind='audio'` 路徑成立），故本次修復鎖定在「帶聲軌影片播不出」的編碼相容性問題。若使用者指的是某支純音頻檔仍無按鈕，需另開調查（可能為個別 WebView 行為）。

### 與 spec 不一致之處
- 無。沿用現有 `POST /api/proxy/build/{id}`（routers/proxy.py:62）與 `409 need_proxy` 設計（misc.py 註解於 Phase 7.7g 即預留此信號），本次僅補齊「前端消費信號」+「mjpeg/qtrle 也納入 need_proxy」兩處缺口。

---

## 任務（續）：音頻 Inspector 預覽是「白框」、看不到播放器
日期：2026-08-29

### Root Cause（與上輪不同）
- 上輪修的是「編碼不相容→建代理」；但純音頻檔本身可播，問題在渲染：舊 `useAudio` 分支把原生
  `<audio controls>` 用 `position:absolute` 貼在 16:9 預覽盒底部，而瀏覽器/WebView 的原生 audio
  控制條是白色長條，在深色預覽盒上像個「白框」、易被忽略，部分 WebView 甚至不顯示播放鈕。
- 確認：`Thumb` 元件對 audio 畫的是深色抽象塊（非白框），故 `useAudio` 確實為 true、音頻元素有渲染，
  只是原生白色控制條造成「白框」觀感。音頻檔 `thumbnail_path=None` → 無縮圖干擾。

### 完成項目
- [x] `Inspector.svelte`：音頻預覽改為**自訂主題化播放器**——置中圓形播放/暫停鈕（`togglePlay`/`onPlay`/`onPause`）+ 隱藏原生 `<audio>`（不帶 `controls`）+ 時間碼，背景用 `var(--surface-2)`，不再依賴瀏覽器白色原生控制條。
- [x] 新增 `playing` 狀態、reset 於 `videoSrc` 變更時。
- [x] 重建容器 image 並重新部署（新 image，`health: healthy`）。

### 測試結果
```
frontend npm run build -> ✓ built (216 modules, 無 Svelte 錯誤)
容器內 curl id=121 (.mp3) -> HTTP 200 | audio/mpeg   (音頻流可播)
app HTTP 200 (新前端已上線)
```
⚠️ 前端 UI 仍僅經編譯驗證，未在瀏覽器實機點擊；建議上線後對一支 .mp3 實測圓形播放鈕是否出現並可播。

### 與 spec 不一致之處
- 無。僅調整音頻預覽的呈現方式（自訂播放鈕替代原生控制條），不改播放管線語意。
