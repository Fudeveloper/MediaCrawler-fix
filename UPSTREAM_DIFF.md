# MediaCrawler-Fix 与上游差异说明

上游仓库：[NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)

本文档记录本 fork（MediaCrawler-Fix）相对上游的**有意改动**，方便日后 `git fetch upstream` / merge 或 cherry-pick 时快速判断冲突与是否需要保留。

## 同步建议

```bash
git remote add upstream https://github.com/NanmiCoder/MediaCrawler.git   # 仅首次
git fetch upstream
git merge upstream/main   # 或 rebase
```

合并后优先检查下列文件是否被上游改动覆盖：

| 文件 | 本 fork 改动要点 |
|------|------------------|
| `media_platform/xhs/extractor.py` | 创作者主页 `__INITIAL_STATE__` 解析加固 |
| `media_platform/xhs/core.py` | 搜索/详情/创作者笔记流程在 `update_xhs_note` 后自动补抓创作者粉丝（保留本 fork 已有的 `download_media`） |
| `store/xhs/__init__.py` | 恢复 `save_creator`；笔记/评论默认落明文 `user_id` 与昵称 |
| `store/xhs/_store_impl.py` | csv/json/jsonl/mongo/db 的 `store_creator` |
| `config/base_config.py` | 新增 `ENABLE_GET_CREATOR_INFO`、`ENABLE_ANONYMIZE_USER_INFO` |
| `fetch_xhs_creators.py` | 独立补抓脚本（本 fork 新增） |

## 功能差异（相对教学版 / 上游常见行为）

### 1. 创作者粉丝可落盘（核心）

上游教学版曾将创作者资料（含粉丝数）刻意不落库。本 fork 恢复：

- `save_creator`：从 `basicInfo` + `interactions` 提取 follows / fans / interaction
- 各存储实现的 `store_creator` 写入 `creators`（jsonl/csv/json/mongo；DB 无 ORM 时回退 jsonl）

### 2. 主页 HTML 解析修复

现象：`get_creator_info` 解析主页时报 `json.JSONDecodeError: Expecting value`。

原因：`window.__INITIAL_STATE__` 中混有非 JSON 的 JS 片段（如 `undefined`、`new Set([])`）。

修复（`extract_creator_info_from_html`）：

- 更稳健地截取 `__INITIAL_STATE__` 对象
- `undefined` / `NaN` → `null`
- `new Set(...)` / `new Map(...)` → 取其内部字面量后再 `json.loads`

### 3. 搜索/详情时自动拉创作者

配置项：`ENABLE_GET_CREATOR_INFO = True`（可关）

在笔记详情写入后调用 `save_creator_from_note`（位于 `update_xhs_note` 之后、本 fork 已有的 `download_media` 之前）：

- 从 note.user 取 `user_id` / `xsec_token`
- 进程内 `_saved_creator_ids` 去重
- 请求间隔跟随 `CRAWLER_MAX_SLEEP_SEC`

日后合并上游时保留媒体下载与访问受限跳过逻辑，只补这一处创作者补抓。

### 4. 笔记/评论默认保留明文身份

教学版笔记与评论只写 `creator_hash` 和脱敏昵称，不写原始 `user_id`，笔记难以和创作者粉丝记录关联。

配置项：`ENABLE_ANONYMIZE_USER_INFO = False`（默认）

- `False`：笔记、评论写入明文 `user_id` 与 `nickname`，同时保留 `creator_hash`，旧数据仍可按哈希关联。
- `True`：恢复教学版行为（仅 `creator_hash` + `mask_nickname`，不写明文 `user_id`）。

文件型存储（csv/json/jsonl）和 mongo 会带上 `user_id`。DB ORM 表仍只有 `creator_hash` 与 `nickname` 列，明文 `user_id` 不会进关系库。

### 5. 独立补抓脚本

`fetch_xhs_creators.py`：对已有笔记作者列表单独补抓粉丝，不重跑搜索。

用法示例：

```bash
python fetch_xhs_creators.py xhs_creator_targets.json 20 8
# args: targets_json [limit] [sleep_sec]
```

## 刻意不并入本仓库的本地改动

以下仅出现在本机调试环境，**不应**作为 fork 默认提交：

- `CUSTOM_BROWSER_PATH` 指向本机 Edge 路径
- `CDP_CONNECT_EXISTING` / 本机 CDP 端口偏好
- 为风控临时调大的 `CRAWLER_MAX_SLEEP_SEC`（可按需自行修改，默认仍可跟上游）

## 已知限制

- 小红书公开页通常拿不到「阅读/浏览」数；低粉高阅读需用其他可用指标（赞藏评 + 粉丝）近似。
- 搜索列表页可能一次拉回超过 `CRAWLER_MAX_NOTES_COUNT` 条笔记详情任务（上游分页行为）；如需硬截断需另开 issue/改动。

## 变更日期

- 2026-09-22：创作者解析修复 + 粉丝落盘 + 搜索自动补抓 + 独立补抓脚本 + 本文档
- 2026-09-22：笔记/评论默认保存明文 `user_id` 与昵称（`ENABLE_ANONYMIZE_USER_INFO = False`）
