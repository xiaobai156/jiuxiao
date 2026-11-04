# 封存「半斤八两」（287 期站方删文）— 裁定与执行记录

- 日期：2026-10-14
- 授权：用户点名「半斤八两 封存」（本轮即时指令）
- 开工状态：`HEAD == origin/main == d3d2b8f`，活跃 439 / 封存 75 / 缓存窗口 287..278

## 封存理由（站方删文）

| 证据 | 结果 |
|---|---|
| 数据接口 `/api/proxy/manager-articles/6a3a0ec4018539c611cb9d94` | **HTTP 404 / 73 B** `{"message":"AdminArticle 不存在","error":"Not Found","statusCode":404}` |
| 浏览器渲染 DOM | 仅 45 字符「Failed to fetch」，8 个 script 文档对 `风雨雷电/287/286/九肖/开` 命中均为 0 |
| 同宿主对照站「攻城略地」 | 接口 HTTP 200 / 195729 B，缓存 `current_issue=287` **正常** ⇒ 非站点整体故障，属该篇被删除 |
| 287 抓取失败记录 | 阶段：栏目锚点校验；原因：未找到目录关键字 |

## 执行（`audit\archive-banjinbaliang-287\run_archive.py`）

备份 → 活跃移除 → 封存追加原始条目深拷贝 + `archived_at` + reason → 缓存按身份键移除 → 287 失败TXT 清除该站。

- 身份键：`7241373eb7a3…`
- 归档时间：`2026-10-14T19:03:21+08:00`
- 结果：活跃 439→**438**、封存 75→**76**、缓存 439→**438**（窗口 / latest / schema / cycle 未变）、失败TXT 758 B/3 站 → **557 B/2 站**（勇闯无畏 / 诗情画意）
- 成功报告 `..\七类数据统一归纳\287期-生肖.txt` **未触碰**（半斤八两 本就不在册）
- 测试同步：`tests/test_fixed_catalog.py` 目录断言 439→438（附历史注释）、`tests/test_routine_cleanup.py` 退役登记增补本条目

## 复验

`audit\archive-banjinbaliang-287\verify_archive.py` ⇒ **PASS 25 / FAIL 0**（提交后 26/0）。对账：活跃 438 = 报告命中活跃站 436 + 失败 2。

`py -3.10 -m pytest -q` ⇒ **222 passed / 7 failed**（7 例为既有历史失败，与基线一致）。

## 287 期失败清单当前状态

| 站 | 状态 |
|---|---|
| 勇闯无畏 | 287 未发布（正文最新 286）；另有 group_map 与站方图例不符（待定） |
| 诗情画意 | 站方 TLS 握手失败（文章页与根域 `http=000`） |
