# CODEX_RESULT — 刪除 clip 不同步移除精選集

日期: 2026-08-30
範圍: `/vol1/1000/docker/nec8-docker/arkiv`（docker 部署專案，Phase 14.5 含 unified media delete）

## 完成項目

- [x] 根因定位：`media_delete.delete_media_full` 刪除 media 時，未從 `bins.py` 的精選集移除該 `media_id`，導致 bin 計數不遞減（如 空鏡 19 → 刪 1 仍顯示 19）。
- [x] 在 `bins.py` 新增 `remove_media_from_all_bins(project_name, media_id)`：遍歷所有 bin，移除所有 `project_name + media_id` 相符項；`project_name=None` 時回退為僅比對 `media_id`。
- [x] 在 `media_delete.delete_media_full` 串接呼叫：成功刪除後，依 `config.PROJECT_ROOT` 經 `projects.discover_projects()` 解析目前 `project_name`，呼叫 `bins_store.remove_media_from_all_bins(project_name, media_id)`（best-effort，catch 後記 warning，不影響刪除主流程）。
- [x] 容器即時生效：`docker cp` bins.py + media_delete.py 進 `arkiv-arkiv-1` 並重啟；後已 `docker compose build` 重建 image `arkiv-arkiv` + `--force-recreate` 容器，`health http=200`。

## 測試結果

1. 單元測試（隔離 `ARKIV_BINS_PATH=/tmp/opencode/test_bins.json`）：
   - A=[main/9, main/5], B=[main/9, other/9] → `remove_media_from_all_bins("main", 9)`
   - 結果：A=[main/5]（9 移除、5 保留），B=[other/9]（跨 project 不誤傷）= **PASS**
   - 回退路徑 `project_name=None`：僅比對 media_id，移除所有 project 下該 id = **PASS**

2. 容器內真端到端（可逆，假 clip 999999）：
   - 臨時 `ARKIV_BINS_PATH=/tmp/e2e_bins.json`，bin 含 `{project_name:"app", media_id:"999999"}`
   - 插入假 row → `delete_media_full(999999)` → bin items 變為 `[]` = **E2E PASS**
   - `current project name: app`（scoped 路徑確實觸發）

3. 載入健全性：容器內 `remove_media_from_all_bins in dir(bins)` = True；`media_delete.py` 含呼叫 = True。

## 疑慮 / REVIEW

- ⚠️ 此修復**僅適用 docker 專案**。github fork（`~/dev/code/github/arkiv`，基於 vulture-s/arkiv:main）無 `media_delete.py`、亦無 `DELETE /api/media/{id}` 路由（其刪除走 `db.delete_media` 直接呼叫，見 `sample_prebuilt.py:239`）。故無對應 upstream PR 目標；若要 upstream，需先將 Phase 14.5 unified delete 整體移植。
- ⚠️ `delete_media_full` 的 bins 清理為 best-effort（catch 後 warning）。若 `bins.json` 鎖損或 `project_name` 解析失敗，會記 warning 但不中斷刪除，bin 可能殘留——與「刪除優先成功」的設計權衡一致，但建議後續於 UI 用 `bin_item_status` 標記失效項而非靜默殘留。

## 未完成

- [ ] 未 commit（依規範待使用者確認後再 commit docker 專案 bins.py / media_delete.py）。
- [ ] 未加 regression test 到 `tests/test_media_delete.py`（可加：插入假 media + bin，刪除後斷言 bin 該項消失）。

## 與 spec 不一致

- 無偏離 config 預設閾值，無新增依賴。
