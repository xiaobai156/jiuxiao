# Step 04 严格审核报告

审核日期：2026-07-29  
审核对象：抓取器层与 Playwright 传输适配  
结论：PASS

## 1. 范围审核

本步骤新增：

- `v2/fetchers/__init__.py`
- `v2/fetchers/registry.py`
- `v2/fetchers/static_page.py`
- `v2/fetchers/dynamic_article.py`
- `v2/fetchers/browser_page.py`
- `v2/fetchers/list_detail.py`
- `v2/tests/test_fetchers.py`
- `v2/reviews/.coverage-step-04`
- `v2/reviews/step-04-coverage.json`
- `v2/reviews/step-04-live.json`

没有修改 V1，没有实现生肖解析、缓存、服务或 CLI。

结论：PASS。

## 2. TDD 审核

RED：

```text
ModuleNotFoundError: No module named 'v2.fetchers'
Ran 1 test
FAILED (errors=1)
```

第一轮 GREEN：

```text
Fetcher tests: 10 passed
```

首次覆盖率审核失败：

```text
Coverage: 69%
Required: 80%
Coverage failure
```

该次失败后 Step 04 保持进行中。补充 Playwright HTTP、DOM、iframe、script、链接、动态 payload 冲突、非法 JSON 和空体测试后：

```text
Fetcher tests: 15 passed
V2 full tests: 50 passed
Coverage: 84.56%
```

结论：PASS。

## 3. 抓取器职责审核

- FetchRequest 固定期数、尝试次数、超时和等待参数。
- StaticPageFetcher 只返回原始页面 Document。
- DynamicArticleFetcher 只选择精确文章记录并生成来源 Document。
- BrowserPageFetcher 只收集 DOM、iframe 和 script 文档。
- ListDetailFetcher 只选择精确期数和关键字详情链接。
- FetcherRegistry 只按配置键解析实现。
- 抓取器目录没有生肖表、生肖提取、Parser 导入或站点名称分支。

```text
forbidden_imports=0
source_name_branches=0
zodiac_logic=0
```

结论：PASS。

## 4. HTTP、重试与兜底审核

- 网络无状态按 FetchRequest 次数重试，耗尽后返回 FETCH_FAILED。
- 408、429、502、503、504 属于可恢复 HTTP 状态。
- HTTP 500 立即返回 HTTP_ERROR，不进入浏览器兜底。
- 动态 API 只有 404、HTTP 200 空响应、无正文空 payload 或精确记录正文为空时进入浏览器兜底。
- 非 JSON API 响应返回 SOURCE_UNTRUSTED。
- API 中找不到目标 ID 且存在正文时返回 API_RECORD_MISMATCH。
- 目标 ID 重复时返回 API_RECORD_MISMATCH。

结论：PASS。

## 5. 动态文章身份审核

- URL 仅识别 `/article/admin/`、`/article/manager/`、`/article/lottery/`。
- admin 路径明确映射到 manager API。
- 只接受 id、_id、articleId、article_id、recordId、record_id 中精确匹配的标量 ID。
- 记录路径写入 Document metadata。
- 浏览器兜底要求主 DOM URL 仍绑定目标文章 ID。

结论：PASS。

## 6. 浏览器与列表安全审核

- 页面最终文档必须与来源同源。
- iframe 跨域文档会触发 CROSS_DOMAIN。
- 列表详情同时绑定指定期数与精确关键字。
- 同期多个不同详情 URL 触发 CANDIDATE_CONFLICT。
- 跨域详情 URL 触发 CROSS_DOMAIN。
- DOM、iframe 和 script 按正文去重，空文档不进入结果。

结论：PASS。

## 7. 真实页面审核

环境：

```text
ignore_https_errors=false
target_issue=210
parser_invoked=false
```

动态接口：

- 霸王码特：API HTTP 200，method=dynamic_api，article_id=6a3dc982018539c611ccc7b7，record_path=$，正文长度 4253。
- 女霸君主：API HTTP 200，method=dynamic_api，article_id=6a5ee709f447e21b02dd535c，record_path=$，正文长度 2337。
- 两个 Document 均包含对应站名和 210 期文本。

真实浏览器采集：

- 霸王码特详情页返回 8 个 Document：1 个 browser_dom、7 个 script。
- 所有 Document URL 均绑定精确文章 ID，未发生跨域。
- DOM/script 本身不包含站名或 210 期；抓取层只保留事实，不把空壳宣称为目标数据。Step 05 Parser/Validator 必须据此严格失败，不能补数。

完整证据保存在 `v2/reviews/step-04-live.json`。

结论：PASS。

## 8. 语法、类型与静态审核

- `py_compile`：PASS。
- Ruff：PASS，零错误。
- Pyright：当前环境未安装，未伪造通过结论。
- V2 全量测试：50/50 通过。

结论：PASS。

## 9. 覆盖率审核

```text
fetchers total: 84.56%
browser_page.py line coverage: 85.88%
dynamic_article.py line coverage: 84.13%
list_detail.py line coverage: 87.50%
registry.py line coverage: 98.25%
static_page.py line coverage: 89.66%
Required: 80%
```

结论：PASS。

## 10. 架构与安全审核

```text
forbidden_imports=0
source_name_branches=0
zodiac_logic=0
secret_matches=0
```

- V2 抓取层没有导入 V1 或 Parser。
- 没有密钥、密码、shell 执行或文件删除。
- Playwright 页面在 finally 中关闭。
- HTTP 异常只记录异常类型，不暴露外部响应中的敏感内容。

结论：PASS。

## 11. V1 回归与数据审核

```text
Ran 188 tests in 1.370s
OK
v1_hashes_verified=20
```

- V1 测试继续通过。
- Step 01 固化的 20 个 V1 文件哈希全部一致。
- 正式 V1 配置和缓存未改动。

结论：PASS。

## 12. 差异与临时文件审核

- Step 04 新增 10 个持久文件；本报告为第 11 个。
- 审核前 V2 共 43 个持久文件。
- 编译生成的 2 个 `__pycache__` 目录已在确认路径属于 `v2` 后删除。
- 没有 V2 目录外意外变化。

结论：PASS。

## 13. 最终结论

Step 04 的所有门禁均已通过，可以将 Step 04 标记为 `[x] 已完成`，并将 Step 05 标记为唯一的 `[>] 进行中`。

## 14. 2026-07-29 OCR 文档采集复审

Step 07 迁移嫦娥公式和嫦娥奔月时发现 ImageOcrParser 没有上游
IMAGE_OCR Document。按执行契约暂停 Step 07，重新打开 Step 04。

先增加配置驱动 RED 测试，证据为 `parser=image_ocr` 与普通 parser
得到相同文档集合，没有 OCR Document。最小实现保持 fetcher/parser
职责分离：

- BrowserPageFetcher 只在 Source.parser 为 image_ocr 时请求 OCR 文档。
- PlaywrightBrowserClient 等待 600×300 内容图完成懒加载。
- 候选图按面积降序，最多处理两张。
- screenshot 返回字节，RapidOCR 直接读取内存，不生成临时图片。
- 输出 DocumentMethod.IMAGE_OCR，并保存 image_index 元数据。
- 普通站点不运行 OCR，现有抓取路径不增加开销。

复审结果：

```text
Fetcher tests: 17/17 passed
browser_page.py coverage: 80%
Fetcher layer coverage: 85%
V2 full tests: 96/96 passed
V1 tests: 188/188 passed
v1_hashes_verified=20
Ruff: PASS
compileall: PASS
Pyright: 未安装
```

真实页面复审：

- 嫦娥公式：2 个 OCR Document，包含 210 期，图片索引 3/4。
- 嫦娥奔月：2 个 OCR Document，包含 210 期，图片索引 3/4。
- TLS 校验未关闭，图片没有写入磁盘。
- 证据保存在 `v2/reviews/step-04-ocr-live.json`。

安全与架构扫描：

- fetchers 中图片写文件调用：0。
- fetchers 中站点名称条件分支：0。
- OCR 只收集文本 Document，不提取生肖、不调用 Parser。
- V1 文件、配置、缓存和 BAT 哈希未变化。

复审结论：PASS。Step 04 可以重新标记为 `[x] 已完成`，恢复 Step 07。

## 15. 2026-07-30 历史抓取隔离复审

Step 08 的 318 站、210-201 期黄金审核暴露两个抓取层问题，按执行契约
暂停 Step 08 并重新打开 Step 04：

- `list_detail` 任一期目录链接缺失会抛出全局异常，拖垮同批其他有效期。
- `browser_page` 没有使用 `FetchRequest.attempts`，首次空页面直接失败。

### 15.1 TDD 与最小实现

先建立 RED：

```text
browser first empty, second success -> FETCH_FAILED
list issue 210 present, 209 missing -> ISSUE_MISSING for whole batch
```

最小实现后：

- 浏览器仅对空文档、异常或纯脚本空壳重试；有 DOM/frame/OCR 文档立即返回。
- 跨域最终文档仍立即返回 CROSS_DOMAIN，不通过重试绕过。
- 最终只有脚本文档时保留脚本文档交给严格 Parser，不丢失 script 数据源。
- 多期列表跳过缺失期并返回已找到详情；所有期都缺失时仍返回 ISSUE_MISSING。
- 单期、同一期多链接冲突和跨域详情行为保持不变。

额外覆盖持续空页面和持续浏览器异常，相关测试 8/8 通过。结论：PASS。

### 15.2 修改范围

本次修改：

- `v2/fetchers/browser_page.py`
- `v2/fetchers/list_detail.py`
- `v2/tests/test_fetchers.py`
- `v2/AGENTS.md`

本次生成：

- `v2/reviews/.coverage-step-04-history-rereview`
- `v2/reviews/step-04-history-rereview-coverage.json`

没有修改动态 API 兜底条件、Parser、配置、缓存、正式 TXT 或 V1 文件。
结论：PASS。

### 15.3 真实页面审核

生产配置中的两个旧列表栏目在站方 211 期页面已经下架，且旧
`a.ttss.vip` 详情跳转到 `www.ttss.vip`；V2 按既定同源规则返回
CROSS_DOMAIN，没有把其他栏目当成目标数据。

为验证多期缺失隔离，在同一真实列表页使用只读临时候选
`坚持不懈㊣㊣九肖`，不写配置：

```text
request issues=211,210
211 list link=present
210 list link=missing
returned documents=1
final URL=https://www.ttss.vip/articleam.aspx?id=714312
document contains 211=True
```

SPA `停止学生` 在三次重试后仍只返回无栏目锚点的脚本壳，最终严格失败为
ANCHOR_MISSING；没有用脚本、相邻用户或旧缓存补数。真实成功与失败路径均
保持 TLS 校验开启。结论：PASS。

### 15.4 测试、覆盖率与静态审核

```text
V2 tests=122/122 passed
Fetcher total coverage=84%
browser_page.py=83%
list_detail.py=86%
Ruff=PASS
compileall=PASS
Pyright=未安装
```

第一次复审 `browser_page.py` 仅 79%，门禁未通过；补充空页面和异常重试
测试后达到 83%，未降低覆盖阈值。结论：PASS。

### 15.5 架构、安全、数据与 V1 审核

```text
V2 production forbidden V1 imports=0
hard-coded source-name branches=0
secret matches=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

静态扫描命中的两处 `source.name` 比较位于通用配置重复身份校验和迁移唯一性
校验，不包含任何具体站点名称，不是站点特例。没有新增文件写入、危险删除、
跨域放行或缓存副作用。结论：PASS。

### 15.6 复审结论

Step 04 本次重新打开后的范围、规则、语法、静态、测试、覆盖率、架构、
安全、真实页面、数据与 V1 回归门禁全部通过，可以重新标记为 `[x] 已完成`，
并恢复 Step 08 为唯一 `[>] 进行中`。

## 16. 2026-07-30 列表分页复审

同步黄金差异发现 V1 列表详情抓取会遍历分页，V2 只读取第一页。按执行
契约再次暂停 Step 08、重新打开 Step 04。

先增加“目标链接只在第二页”的 RED 测试，原实现返回 ISSUE_MISSING。
最小实现只跟随满足全部条件的链接：与源 URL 同 scheme/host/port/path，
除 `page` 外查询参数完全一致，`page` 为纯数字，最多 20 页。跨域、跨路径、
非数字页码和超过 20 页均不放行。

真实页面结果：

```text
金瓯无缺: collected_links=552, target_matches=2 (211期、207期)
蛇蝎美人: collected_links=624, target_matches=2 (211期、207期)
```

分页已真实找到第一页不存在的生产栏目。详情从 `a.ttss.vip` 跳转到
`www.ttss.vip` 时仍由既定同源规则拒绝，本次没有借分页修复放宽跨域。

复审门禁：

```text
V2 tests=126/126 passed
list_detail.py coverage=86%
Fetcher total coverage=84%
Ruff=PASS
compileall=PASS
Pyright=未安装
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
production V1 imports=0
site-specific branches=0
```

修改范围仅为 `v2/fetchers/list_detail.py`、`v2/tests/test_fetchers.py`、
`v2/AGENTS.md` 和对应覆盖率/审核产物。没有修改配置、缓存、正式 TXT、
BAT 或 V1。复审结论：PASS；Step 04 可重新标记完成并恢复 Step 08。

## 17. 2026-07-30 SPA 正文就绪复审

Step 08 黄金同步中，`#/users/` 页面偶发只返回非空 SPA 外壳。旧实现只要
存在 DOM 文档就立即返回，使 Parser 在正文尚未加载时产生整站
`ANCHOR_MISSING` 或 `ISSUE_MISSING`。按契约暂停 Step 08、重开 Step 04。

先增加两条 RED：非空外壳后出现正文时必须重试；重试耗尽时必须保留最后
文档供严格 Parser 分类。旧实现两项均失败。最小实现只检查非 SCRIPT 文档
是否同时出现配置锚点和明确期号，不提取生肖；跨域文档仍在就绪判断前立即
拒绝。最终仍未就绪时返回最后文档，不把登录页或缺锚点页伪装成网络失败。

真实页面在 `ignore_https_errors=False` 下复核 6 个生产站点，均取得栏目锚点
及 210-201 全部期号：丰利骨头、盐卤香灯、清醒婚礼、停止武术、
孤芳自赏A、陈旧道士。证据见 `reviews/step-04-spa-live.json`。

门禁结果：

```text
Fetcher tests=23/23 passed
V2 full tests=131/131 passed
Fetcher total coverage=85%
browser_page.py coverage=85%
Ruff=PASS
compileall=PASS
Pyright=未安装
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
production V1 imports=0
hard-coded source-name branches=0
hard-coded secret matches=0
active sources=318
archived sources=14
指定五站 active=0, archived=5
```

修改范围：`v2/fetchers/browser_page.py`、`v2/tests/test_fetchers.py`、
`v2/AGENTS.md`、本审核报告及两项 Step 04 审核产物。未修改配置、缓存、
正式 TXT、BAT 或 V1。范围、架构、规则、语法、类型可用性、静态、测试、
覆盖率、安全、差异、数据和真实页面门禁全部通过。复审结论：PASS。

## 18. 2026-07-30 跨域 iframe 隔离复审

Step 08 实时证据显示，10 个 `CROSS_DOMAIN` 站点中的普通页面主 DOM 均与
Source 同源，且含正确栏目和历史；触发拒绝的是无关开奖或视频 iframe。
旧实现把任意跨域 Document 当成整站失败，导致可信主正文被无关组件拖垮。

先增加 RED：同源主 DOM 加跨域 frame 时应只返回主 DOM；原实现抛出
`CROSS_DOMAIN`。跨域主 DOM 的既有测试同时保持 GREEN。最小实现仅丢弃
`DocumentMethod.BROWSER_FRAME` 的跨域文档；DOM、OCR、script 等其他
跨域文档仍立即失败，跨域 frame 永不进入 Parser。

严格 TLS 真实复核后，岁岁欢愉、金榜题名、自在如风、且听凨吟、
百彩通啊啊、双世宠妃、庄家无命 210-201 结果与同步 V1 逐项一致；金瓯无缺
和蛇蝎美人不再被 frame 拖成全局跨域失败，按当前列表实际期号返回。
八步毛哥暴露的是独立 Parser 栏目边界，未在抓取层放宽。证据见
`reviews/step-04-frame-live.json`。

门禁结果：

```text
Fetcher tests=24/24 passed
V2 full tests=134/134 passed
Fetcher total coverage=85%
browser_page.py=86%
Ruff=PASS
compileall=PASS
Pyright=未安装
production V1 imports=0
core source-name branches=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：`v2/fetchers/browser_page.py`、`v2/tests/test_fetchers.py`、
`v2/AGENTS.md`、本报告及本次审核产物。未修改配置、缓存、正式 TXT、BAT
或 V1。全部门禁通过，复审结论：PASS。

## 19. 2026-07-30 列表最新详情历史模式复审

Step 08 证明滚动列表只保留最新及少量旧详情。V1 历史流程打开最新目标详情
一次，再从详情正文解析完整历史；V2 原实现按 210-201 分别寻找独立链接，
导致已从目录下架的 210-208 被误报缺失。

先增加 RED：historical 请求面对 211 和 207 链接时必须只打开最新 211
详情。旧 `FetchRequest` 不接受该语义。最小实现新增布尔
`history_mode`；`ListDetailFetcher` 在此模式选择最高期目标链接一次，
同一期多 URL 仍冲突、跨域仍拒绝。默认单期/多期精确链接行为不变。

严格 TLS 真实复核：金瓯无缺打开详情 714515、蛇蝎美人打开 714516，
两站 210-201 与同步 V1 合计 20/20 一致。证据见
`reviews/step-04-list-history-live.json`。

```text
Fetcher tests=25/25 passed
V2 full tests=137/137 passed
Fetcher total coverage=85%
list_detail.py=85%
registry.py=95%
Ruff=PASS
compileall=PASS
Pyright=未安装
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：`v2/fetchers/registry.py`、`v2/fetchers/list_detail.py`、
`v2/tests/test_fetchers.py`、`v2/AGENTS.md`、本报告及审核产物。未修改
配置、缓存、正式 TXT、BAT 或 V1。全部门禁通过，复审结论：PASS。
