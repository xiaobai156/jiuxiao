# 一语破特 封存 · 2026-10-08（281 期）

## 1. 用户指令
User：「一语破特 封存」→ 依据 `AGENTS.md:71-75`（封存站点）与项目 `AGENTS.md`「封存与恢复」段执行：只处理点名站点——移出活跃配置、写入封存配置、移除该站精确缓存身份、从当期失败报告只删该站记录并保留其他记录及顺序；不抓取、不写成功报告。

## 2. 封存依据（281 期实测）
- 失败清单条目：`失败 一语破特 https://hl.www73261a.com/read.php?tid=543 方向: bottom 期数: 281 阶段: 栏目锚点校验 原因: 未找到目录关键字`。
- 真实抓取 `audit/probe-281/一语破特.browser-dom.txt` 仅 **140 字节**：七星高手论坛模板登录墙「提示信息：您没有登录或者没有权限访问此页面…①读取数据错误,原因：您要访问的链接无效,可能链接不完整,或数据已被删除! ②您还不是论坛会员,请先登录论坛」；页内 `一语破特` / `风雨雷电` / `281` / `280` 命中**全为 0**，无任何分组/期号原文。
- 裁定：**站方侧**（帖子对游客不可见，需登录），非我方解析缺陷；与 278 期封存「阿猫阿狗」、279 期封存「宝刀不老」同型，符合用户点名封存条件。

## 3. 落盘结果（脚本 `audit/archive-yiyupote-281/run_archive.py`）
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移除该条目，其余 437 条顺序与字段逐条未变） |
| `config/archived_sources.json` | 68 → **69**（追加原始条目深拷贝 + `archived_at=2026-10-08T20:03:38+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `e5df703b469a…` 移除该条目；`issues`、`latest_issue=281` 与其余条目未动） |
| `..\七类数据统一归纳失败\281期-生肖-失败.txt` | 325 B / 2 条 → **1 条**（仅剩 炳炳凿凿，原文逐字、顺序不变） |
| `..\七类数据统一归纳\281期-生肖.txt` | **未触碰**（该站本就无 281 成功行） |

封存 reason（全文存 `removed_entries.json`）：`用户明确封存，不再抓取；281期抓取失败：站方侧拒绝访客，需登录（browser_dom 正文仅 140 字符，为「提示信息：您没有登录或者没有权限访问此页面…①读取数据错误…链接无效…或数据已被删除! ②您还不是论坛会员,请先登录论坛」登录墙，页内「一语破特」「风雨雷电」「281」「280」命中均为 0，无任何分组/期号原文）`

改动前基线（`*.before` 同步留存于本目录）：活跃 438 / 封存 68 / 缓存 438；`sources.json` sha256 `f741b4149547a5a12174b715b829c12022b889d475063676f4ab906e59499a4d`、`archived_sources.json` `311d038027558c44a6b1f7e5061d615abb04a5d16a2330ceea895f86a62c84af`、`recent_10_cache.json` `103b18c3cc6f63af44ecfd0cf177f1670f47f896a5dbf2c9461163fd1af76255`、281 失败TXT `5825a4ffa7c47079ebea23dbad90b4ae60dc6fd47315091aff42b147c5154c8a`（325 B）。

## 4. 测试同步
- `tests/test_fixed_catalog.py`：目录断言 438 → **437**，注释补「2026-10-08 封存「一语破特」（281 期站方侧登录墙，游客不可见）」。
- `tests/test_routine_cleanup.py::test_retired_sources_are_archived_and_absent_from_cache` 的 `expected` 增补 `"一语破特": "https://hl.www73261a.com/read.php?tid=543"`。

## 5. 验收与提交
- `audit/archive-yiyupote-281/verify_archive.py`（对照 `*.before`、只读）：**PASS 32 / FAIL 0**（活跃 438→437 且其余逐条/顶层不变；封存原 68 条逐字段未变、新条目深拷贝+三字段+reason 前缀+时间戳合规、无重名且与活跃无交集；缓存按身份键去一、其余逐条未变、窗口/latest 未变、身份键唯一；失败TXT 恰为「原文 − 该站」且以单换行结尾；成功报告未新增该站行且每行合法；报告 + 失败清单 = 活跃站数；两处测试已更新）。
- pytest：**209 passed / 7 failed**（7 例与既往归因完全一致，无新增）。
- 提交 `3d79cbd`「chore: archive yiyupote source per user request」（4 files / 28+ / 21-），已推送 `origin/main`（4fa3600..3d79cbd）；`cache\recent_10_cache.json` 与 `parsers\registry.py` 依 `AGENTS.md:99-100` 不提交。
