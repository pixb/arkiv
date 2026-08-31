# CODEX_RESULT — 手動/正規化 tag 與視覺 tag 全部進向量索引

日期: 2026-08-30
分支: `feat/tags-in-vector-index` (pixb) → `vulture-s/arkiv:main`
PR: https://github.com/vulture-s/arkiv/pull/404
同時已部署到 docker 實機 `/vol1/1000/docker/nec8-docker/arkiv` 並重建 image + 重啟容器。

## 1. 完成了什麼
- [x] `vectordb.build_doc_text` 折入 manual tags (`source='manual'`) + `canonical_tags`
- [x] 新增 `vectordb.build_tag_doc`（filename + frame_tags + manual + canonical，不含 transcript）
- [x] `vectordb.upsert_record` 對「所有」clip（含含逐字稿者）恆產生 `_f0` tag 分塊 → 有逐字稿影片的視覺/tag 信號不再落空
- [x] `embed.get_content_signatures` 的 `content_hash` 納入 tags → 改 tag 被鮮度檢查視為 stale 而自動重嵌
- [x] 新增 `embed.reindex_media(media_id)` 單筆即時重嵌
- [x] `routers/media.add_tag` / `remove_tag` 與 `db.set_canonical_tags` 寫入後 best-effort 觸發 `reindex_media`（Ollama 異常不影響打 tag）
- [x] 實機 418-clip 庫跑過一次 `python embed.py` incremental（110 個有 tag 的 clip 被重嵌）
- [x] 端到端驗證：搜「筆刷」→ brush.mp4 排 #1、brush_m.mp4 排 #4（兩者都打了手動 tag 筆刷）

## 2. 測試結果（實機直跑，非回憶）
容器 `arkiv-arkiv-1` 內直跑：
```
build_doc_text has manual: True
build_doc_text has canonical: True
build_tag_doc excludes transcript: True
manual tag searchable after reindex_media: True
manual tag gone after remove+reindex: True
canonical tag searchable via set_canonical_tags hook: True
ALL E2E CHECKS DONE
```
搜「筆刷」top-8（節錄）：
```
[0.521] id=118 brush.mp4   ← 手動 tag 筆刷/轉場
[0.489] id=119 brush_m.mp4 ← 手動 tag 筆刷/轉場
```
embed.py 實機報告：`Total: 418 | indexed: 418 | stale: 110 | content-unchanged: 308 → to embed: 110`，全部 OK。
4 個改動檔 `py_compile` 全過（docker 與 github clone 兩份皆過）。

## 3. ⚠️ REVIEW
- **tagless 的含逐字稿 clip 仍未補 `_f0`**：它們 content_hash 沒變 → incremental 不會重嵌，舊索引布局維持（無 `_f0`）。若要讓「所有」含逐字稿 clip 的視覺搜尋都生效，需跑一次 `python embed.py --rebuild`（全庫重嵌，較重）。本次只重嵌了有 tag 的 110 個，符合使用者直接需求（打 tag 才要搜得到），但是 vision-only 搜尋對無 tag 的長片未改善。
- **`db.set_canonical_tags` 現在會觸發 `reindex_media`**：在 `_run_canonicalize_tags` 批量回填（每 media 一次 LLM + 一次 reindex）時會逐筆重嵌，屬一次性後台作業，可接受，但留意 Ollama 負載。
- **index 體積略增**：每 clip 多 1 個 `_f0` 分塊（之後全庫 rebuild 後全數生效）。

## 4. 未完成
- 全庫 `--rebuild`（讓無 tag 的含逐字稿 clip 也拿到 `_f0`）尚未跑——視需求再決定。

## 5. 與 spec / 現有行為的不一致
- 原 `upsert_record` 對「含逐字稿」clip 只嵌 transcript 分塊、完全不嵌 vision/frame tags，這是既有的搜尋盲點；本變更改為「恆嵌 `_f0` tag 分塊」，屬行為修正而非單純加功能。
- 索引組成改變（新增 `_f0` 分塊）會使舊 `embed_hash` 失配而整批 stale，已在部署步驟用一次 incremental 消化。
