# 诗情画意 封存（289 期，2026-10-17）

## 触发
用户 m02758：「诗情画意 封存」。

## 判定依据（封存前已复核，非本次新增）
- 浏览器 `Page.goto https://mhpayza.30mg9-m9j7l-obwrmb.xyz/topic/766658.html` → `net::ERR_CERT_COMMON_NAME_INVALID`。
- `curl.exe -s -o NUL -w "http=%{http_code} size=%{size_download}"` → `http=000 size=0`。
- 287、288、289 **连续三期**同一错误；缓存 `current_issue` 停在 286。
⇒ 站方 TLS 证书异常（站点整体不可访问），非单篇文章问题，游客侧无法修复。

## 执行（`run_archive.py`）
1. 快照 → `audit/archive-shiqinghuayi-289/*.before`（sources / archived_sources / recent_10_cache；失败TXT 当时缺失，未纳入）。
2. 活跃 `sources.json` 移除该站（443→442 条，其余条目逐字段与顺序不变）。
3. 封存 `archived_sources.json` 追加原始条目深拷贝 + `archived_at=2026-10-17T11:57:38+08:00` + reason（76→77）。
4. 缓存 `recent_10_cache.json` 按身份键 `5352098a9785…` 整条移除（443→442），窗口 `289..280`、`latest_issue=289` 未变。
5. 失败TXT：开工时已不存在（外部工具于 2026-10-17 00:08 清空归纳目录），脚本按「存在且非空才处理」跳过，未创建文件。
6. 成功报告：封存规则不写成功行，未触碰。

## 复验 `verify_archive.py` → **PASS 25 / FAIL 0**
活跃 442（= 开工前 443 − 1，其余逐字段与顺序一致）、封存 77（前 76 条未动、尾部为本站深拷贝）、缓存 442（窗口/latest 未变，其余条目逐字段未动）、回读活跃/封存模型一致、活跃身份键唯一、封存无同名重复。

## 测试
`py -3.10 -m pytest -q` → **222 passed / 7 failed**（7 例为既有历史失败，与封存前一致；`tests/test_fixed_catalog.py` 已同步 443→442 并附历史注释）。

## 环境观察（外部工具副作用）
`七类数据统一归纳\` 与 `七类数据统一归纳失败\` 两目录于 2026-10-17 00:08–00:22 被外部 OCR/归纳工具清空（只剩 `.ocr-state`、`.ocr-backups`），289 期成功报告与失败清单均不再存在；本封存未触碰这两个目录。

## 遗留（未执行，需用户点名）
- 凶终隙未：289 期行 `289期☀️春夏秋冬☀️春[秋夏]开0000准`（季名落在括号外）→ 容错修复待授权。
- 勇闯无畏 group_map 与站方图例不符（另 6 站同型）待授权修正。
