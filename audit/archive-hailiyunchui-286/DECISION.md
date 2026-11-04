# 封存「海立云垂」裁定（2026-10-13，286 期）

用户点名封存（原话：`海立云垂 封存`）。

## 封存依据（封存前重新取证）

| 检查 | 结果 |
|---|---|
| 原始文档 | `https://czcvzk.4n5g7-o871g-hqmkwz.work:29422/article/admin/6a0969ec291caff3edcb8b75?url=tsp` → **HTTP 200 / 49349 B**（Next.js SPA 纯壳：仅 `_next/static` 构建脚本与样式） |
| 内容命中 | 全文「九肖」**0**、「生肖」**0**、「286」**0** |
| 渲染正文 | `browser-dom` 仅 **45–88 B**：`Failed to fetch` 报错页 + 「搜索 登陆 注册 / 首页 规则 充值 客服」导航 |
| 解析结果 | 配置 `fetcher=dynamic_article` / `parser=split_line`，锚点「海立云垂」不可达 → `ANCHOR_MISSING` |

⇒ 站点存活但该文章数据不可得（站方侧接口异常），与「同站登录墙/删帖」同属不可自愈类型，用户点名封存。

## 改动范围（固定四类）

| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移除该站，其余逐字段与顺序不变） |
| `config/archived_sources.json` | 74 → **75**（原条目深拷贝 + `archived_at=2026-10-13T19:00:33+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `b89dfbee0833…` 恰移除 1 条；窗口 286..277 / `latest_issue=286` / schema / cycle 未变，其余 437 条逐字段未变） |
| `286期-生肖-失败.txt` | 999 B / 6 站 → **799 B / 5 站**（九肖规律 / 青藤之凉 / 戳你的肺 / 木鱼丸 / 依然公主九肖），原文逐字、单换行结尾 |
| 286 成功报告 | **未触碰**（该站为失败站，本无成功行；复核 古今中外 行仍在） |

测试同步：`tests/test_fixed_catalog.py` 目录断言 438→437（附历史注释）、`tests/test_routine_cleanup.py` 退役登记新增该站。
pytest：**222 passed / 7 failed**（7 例为既有历史失败）。

## 验收

- 封存脚本 [run_archive.py](灵蛇九肖_修复版v2/audit/archive-hailiyunchui-286/run_archive.py)（先备份到本目录，再活跃移除 / 封存追加 / 缓存移除 / 失败TXT 清除，含回读断言）。
- 独立复验 [verify_archive.py](灵蛇九肖_修复版v2/audit/archive-hailiyunchui-286/verify_archive.py) → **PASS 26 / FAIL 0**（含对账：活跃 437 = 报告命中 432 + 失败 5）。
- 提交 `53401d8`；`HEAD == origin/main == 53401d8`。
- 286 期剩余失败 5 站：九肖规律（站方当期缺 1 肖）、青藤之凉 / 戳你的肺（同期冲突待结算）、木鱼丸 / 依然公主九肖（286 未发布）。
