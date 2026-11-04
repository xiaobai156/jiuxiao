# 灵丹妙药 封存 · 2026-10-09（282 期）

## 1. 用户指令与依据
- User：「灵丹妙药 封存」→ 依据 `AGENTS.md:71-75` 与项目「封存与恢复」段：只处理点名站点 —— 移出活跃配置、写入封存配置（原始条目深拷贝 + reason）、移除精确缓存身份、从当期失败报告只删该站记录并保留其他记录及顺序；不抓取、不写成功报告。
- 封存依据（282 期实测）：`browser-dom` 仅 **140 字符**，为七星高手论坛模板登录墙「提示信息：您没有登录或者没有权限访问此页面…您还不是论坛会员,请先登录论坛」；页内 `绝杀三肖` / `282` / `281` 命中**全为 0**（该站 `parser=complement_three`，`data_marker=绝杀三肖`）⇒ 站方侧拒绝访客，非我方解析缺陷；与 阿猫阿狗(278)/宝刀不老(279)/一语破特(281) 同型。

## 2. 落盘结果（脚本 `audit/archive-lingdanmiaoyao-282/run_archive.py`）
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移除该条目；其余按原序逐字段未变） |
| `config/archived_sources.json` | 71 → **72**（原始条目深拷贝 + `archived_at=2026-10-09T19:07:40+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `01f4ce9326a4…` 移除；窗口 282..273 与 `latest_issue=282` 未动） |
| `..\七类数据统一归纳失败\282期-生肖-失败.txt` | 319 B / 2 条 → **172 B / 1 条**（仅剩 嫦娥公式，原文逐字、顺序不变） |
| `..\七类数据统一归纳\282期-生肖.txt` | **未触碰**（该站为失败站，本无 282 成功行） |

改动前基线（`*.before`）：`sources.json` sha `b1faddb0…`、`archived_sources.json` `b6a4c381…`、`recent_10_cache.json` `12eb10c3…`、282 失败TXT `531a459e…`（319 B）。

## 3. 本轮踩坑与修复（脚本 bug）
- 失败TXT 重写后曾多出一个空行（172→173 B，以 `\n\n` 结尾）。原因：`text.split("\n\n")` 会让**末条目**保留自身尾换行；本次删除的是**首条目**（灵丹妙药）、保留末条目（嫦娥公式），直接 `"\n\n".join(kept) + "\n"` 就写出多余的 `\n`。
- 修复：改写前 `kept.append(entry.strip())`（已在 `run_archive.py` 内置注释说明），并把本次失败TXT 规范化为单尾换行（172 B）；`verify_archive.py` 的「以单个换行结尾」断言据此由 FAIL 转 **PASS**。

## 4. 测试同步与验收
- `tests/test_fixed_catalog.py`：目录断言 438 → **437** 并补注释。
- `tests/test_routine_cleanup.py`：退役登记 `expected` 增补 `"灵丹妙药": "https://www28651a.com/read.php?tid=546"`。
- `audit/archive-lingdanmiaoyao-282/verify_archive.py`（对照 `*.before`、只读）：**PASS 32 / FAIL 0**（活跃 438→437 且其余逐条/顶层未变、移除条目唯一且 URL 一致、封存 71→72 且原 71 条逐字段未变、新条目深拷贝+三字段+reason+时间戳合规、封存无重名且与活跃无交集、缓存 438→437 且其余逐条未变、窗口/latest 未变、身份键唯一 437、失败TXT 恰为「原文 − 该站」且单尾换行、报告未含该站且 报告+失败=活跃、两处测试已更新）。
- pytest：**209 passed / 7 failed**（既有 7 例）。
- 提交 `56f9f85`「chore: archive lingdanmiaoyao source per user request」（4 files / 23+ / 16-），已推送 `origin/main`（53bd7fc..56f9f85）；`cache\recent_10_cache.json` 与 `parsers\registry.py` 依 `AGENTS.md:99-100` 不提交。

## 5. 备注
- 封存后 282 失败清单仅剩 **嫦娥公式**（282 期图片 OCR 为 10 字符、`INVALID_ZODIAC_COUNT`，站方/OCR 侧数据无效），待站方更正后原样复跑。
