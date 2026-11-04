# 封存「美酒咖啡」（285 期站方侧论坛登录墙）· 2026-10-12

## 1. 授权与依据
- 用户点名：「美酒咖啡 封存」（285 期失败清单处置后我提出该站为站方登录墙、需点名才封存）。
- 封存依据（285 期实测）：
  - `probe_site.py 美酒咖啡 285` → `browser-dom` 仅 **157 字符**，`script:1/2/4` 合计 828 字符，「美酒咖啡」「285」「九肖」**命中全 0**（`diagnose` 报 `ANCHOR_MISSING`）。
  - DOM 全文为「**属牛的女孩论坛**」访客错误页：「提示信息 » 您没有登录或者没有权限访问此页面，可能有如下几个原因: 读取数据错误,原因：您要访问的链接无效,可能链接不完整,或数据已被删除! 您还不是论坛会员,请先登录论坛」（含登录表单 `document.login.pwuser`）。
  - 独立佐证：站点根域 `https://6yrtfjghvnb-0978dtuxfyh.xyz/` **HTTP 200**、`read.php?tid=54123` **HTTP 200（4092 B）** ⇒ **站点存活、该帖对游客不可见**（需登录），非站点下线、非解析缺陷。
  - 与 278 阿猫阿狗、279 宝刀不老、281 一语破特、282 灵丹妙药同型（同为论坛游客不可见）。

## 2. 改动
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移出该站，其余 437 条顺序与逐字段不变） |
| `config/archived_sources.json` | 73 → **74**（末条为该站原条目深拷贝 + `archived_at=2026-10-12T20:08:38+08:00` + reason 记录登录墙证据；既有 73 条逐字段未变） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `8531e80b7857…` 恰移除 1 条；窗口 285..276、`latest_issue=285`、schema/cycle 未变；其余 437 条逐字段未变） |
| `285期-生肖-失败.txt` | 335 B / 2 站 → **1 站（仅 赚钱之道）**，原文该条逐字、顺序不变、单换行结尾 |
| `285期-生肖.txt` | **未触碰**（该站为失败站，本无成功行） |
| `tests/test_fixed_catalog.py` | 目录断言 438 → 437 + 注释「2026-10-12 封存美酒咖啡（285 期站方侧论坛登录墙）」 |
| `tests/test_routine_cleanup.py` | 退役登记增补 `"美酒咖啡": "https://6yrtfjghvnb-0978dtuxfyh.xyz/read.php?tid=54123"`（注释同上） |

- 执行脚本：`audit/archive-meijiukafei-285/run_archive.py`（由 `make_archive.py` 从上一轮封存脚本生成；脚本内回读断言，输出 `removed_entries.json` / `after_state.json`）。
- 提交 `94d6fc3`「chore: archive meijiukafei source (285 login wall)」（3 files changed, 5 insertions(+), 16 deletions(-)），已推送 `origin/main`（`53511c6..94d6fc3`）。

## 3. 独立复验
- `audit/archive-meijiukafei-285/verify_archive.py`（只读，对照 `*.before`）：**PASS 24 / FAIL 0** —— 活跃恰为「原文去掉该站」、封存末条为深拷贝且带 `archived_at`/reason、缓存恰移除 1 条且其余逐字段未变、失败清单恰为「原文去掉该站」且单换行结尾、报告字节未变、按站对账 **活跃 437 = 报告 436 + 失败 1**、报告缺失站恰为 赚钱之道。
- pytest：**222 passed / 7 failed**（既有 7 例基线，未新增失败）。

## 4. 终态与遗留
- 活跃 **437** / 封存 **74**；285 期失败清单仅剩 **赚钱之道**（同期冲突：`:8` 未结算行 vs `:10` 沿用上期开奖号，等 285 结算后站方只留一条即可原样复跑自愈）。
- HEAD == origin/main == `94d6fc3`。
