# Step 05 严格审核报告

审核日期：2026-07-29  
审核对象：解析器注册表与统一 Validator  
结论：PASS

## 1. 范围审核

本步骤新增：

- `v2/parsers/__init__.py`
- `v2/parsers/custom/__init__.py`
- `v2/parsers/registry.py`
- `v2/parsers/direct_nine.py`
- `v2/parsers/grouped.py`
- `v2/parsers/split_line.py`
- `v2/parsers/image_ocr.py`
- `v2/validator.py`
- `v2/tests/test_parsers.py`
- `v2/reviews/.coverage-step-05`
- `v2/reviews/step-05-coverage.json`
- `v2/reviews/step-05-live.json`

没有修改 V1，没有实现服务、缓存同步或 CLI。

结论：PASS。

## 2. TDD 审核

初始 RED：

```text
ModuleNotFoundError: No module named 'v2.parsers'
Ran 1 test
FAILED (errors=1)
```

第一轮 GREEN：

```text
Parser tests: 11 passed
```

规则审核发现 Record 未继承 Document 的 article_id、record_path 和 api_url。补测试后 RED：

```text
KeyError: 'article_id'
Ran 12 tests
FAILED (errors=1)
```

贯通 Document provenance 后：

```text
Parser tests: 12 passed
V2 full tests: 62 passed
```

结论：PASS。

## 3. 解析器职责审核

- Parser 只接收 Source、Document 和期数，不访问网络或文件。
- direct_nine 只解析同行锚点和括号候选，不跨行猜测。
- split_line 只绑定期数行与立即下一行。
- grouped 只使用 Source 明确配置的 group_map。
- image_ocr 只接受 IMAGE_OCR Document。
- ParserRegistry 只按配置键解析实现。
- custom 目录用于隔离后续特殊站点。

```text
forbidden_imports=0
source_name_branches=0
io_matches=0
```

结论：PASS。

## 4. 锚点、锁定和边界审核

- 文档完全缺少站名、别名或 `section_marker` 时返回 ANCHOR_MISSING。
- 期数行必须包含当前站点锚点，不能因整页出现站名就扫描其他栏目。
- 目标期行出现购买、锁定或隐藏标记时返回 LOCKED_CONTENT。
- HTML 只做结构化文本归一化，不改变生肖原始顺序。
- 相同文档正文去重由抓取层完成，解析器保留不同候选供 Validator 判断。

结论：PASS。

## 5. 分组与跨行审核

- grouped 缺少 source.group_map 时返回 GROUP_EVIDENCE_MISSING。
- 分组字、分组类型和转换结果进入 Evidence。
- 转换严格按网页分组顺序拼接。
- split_line 只读取立即下一行，不能跨广告或任意扩大窗口。
- Record 证据包含原始两行、文档标签、文档/行号及上游来源 metadata。

结论：PASS。

## 6. Validator 审核

- 九肖必须恰好 9 个、互不重复且全部属于十二生肖。
- Evidence 的目录锚点必须属于 Source 的栏目名、站名或别名。
- 同站同期不同九肖返回 CANDIDATE_CONFLICT。
- top 使用前 3 条有效记录，bottom 使用后 3 条有效记录。
- 单期/近两期模式严格执行方向三条窗口。
- history_mode 允许按明确期号验证近十期，但不改变 current_issue 的方向定义。
- 输出记录顺序严格跟随 requested_issues。

结论：PASS。

## 7. 真实解析审核

首次真实审核使用 direct_nine，Validator 返回 ISSUE_MISSING，未生成 PASS 报告。诊断证据：

```text
documents=1
records=0
```

真实 API 正文将期数/站名与九肖括号分为相邻两行。没有放宽 direct_nine，而是按专属结构选择 split_line。

重新验证结果：

- 霸王码特：44 条历史候选；current_issue=210；210=狗猴虎鸡龙牛蛇羊猪；209=狗猴虎龙马蛇兔羊猪。
- 女霸君主：19 条历史候选；current_issue=210；210=猴鸡龙马牛鼠兔羊猪；209=狗猴虎鸡龙马蛇兔猪。
- 两站均使用 dynamic_article + split_line + strict Validator。
- ignore_https_errors=false。
- 每条 Record 均保存 source_line、directory_anchor、document_label、article_id、record_path 和 api_url。
- 结果与 V1 已验收基准一致。

完整证据保存在 `v2/reviews/step-05-live.json`。

结论：PASS。

## 8. 语法、类型与静态审核

- `py_compile`：PASS。
- Ruff：PASS，零错误。
- Pyright：当前环境未安装，未伪造通过结论。
- V2 全量测试：62/62 通过。

结论：PASS。

## 9. 覆盖率审核

```text
Parser + Validator coverage: 92.80%
Required: 80%
```

- direct_nine：100%。
- image_ocr：100%。
- grouped、split_line、registry、validator 均高于 80%。

结论：PASS。

## 10. 架构与安全审核

- 解析层没有导入 V1、Fetcher 或 Storage。
- 没有站点名称条件分支。
- 没有网络、浏览器或文件 I/O。
- 没有密钥或密码。
- 错误判断只依赖 ErrorCode，不依赖中文报告文案。

结论：PASS。

## 11. V1 回归与数据审核

```text
Ran 188 tests in 1.451s
OK
v1_hashes_verified=20
```

- V1 测试继续通过。
- Step 01 固化的 20 个 V1 文件哈希全部一致。
- 正式 V1 配置、缓存和输出未改动。

结论：PASS。

## 12. 差异与临时文件审核

- 审核前 V2 共 56 个持久文件。
- Step 05 新增 12 个持久文件；本报告为第 13 个。
- 编译生成的 3 个 `__pycache__` 目录已在确认路径属于 `v2` 后删除。
- 没有 V2 目录外意外变化。

结论：PASS。

## 13. 最终结论

Step 05 的所有门禁均已通过，可以将 Step 05 标记为 `[x] 已完成`，并将 Step 06 标记为唯一的 `[>] 进行中`。

## 14. 2026-07-29 书名括号复审

Step 07 真实审核月影舞华时发现网页使用 `《九肖》`，原通用
BRACKET_PATTERN 只接受 `【】`、`[]` 和 `〖〗`。按执行契约暂停
Step 07，并重新打开 Step 05。

先增加真实结构 RED 测试，修正测试夹具后得到有效证据：

```text
IndexError: tuple index out of range
records=0
```

最小修复只为通用括号字符集增加 `《》`，没有放宽锚点、期数、方向、
候选冲突或九肖数量校验。

复审结果：

```text
Parser/custom tests: 17/17 passed
Parser + Validator coverage: 88%
V2 full tests: 94/94 passed
V1 tests: 188/188 passed
v1_hashes_verified=20
Ruff: PASS
compileall: PASS
Pyright: 未安装
```

真实页面复审：

```text
月影舞华  state=success  current_issue=210
210期九肖中特《羊狗猪牛鸡蛇龙猴兔》开0000准
```

- 修改范围仅为 `v2/parsers/registry.py` 和对应测试。
- 新增覆盖证据 `v2/reviews/.coverage-step-05-rereview` 与
  `v2/reviews/step-05-rereview-coverage.json`。
- V2 生产代码未导入 V1，未增加站点名称分支或 I/O。
- V1 配置、缓存、测试和 BAT 哈希未变化。

复审结论：PASS。Step 05 可以重新标记为 `[x] 已完成`，恢复 Step 07。

## 16. 2026-07-30 历史黄金差异复审

Step 08 首轮 318 站、210-201 期真实黄金导出暴露通用解析回归：V1
有 2993 条成功历史记录，原 V2 只有 307 条。按执行契约暂停 Step 08，
重新打开 Step 05。本节结论取代本报告第 3 至 6 节中“期数行必须重复
锚点”和“direct_nine 不跨行”的旧限制；锚点、栏目边界、方向与候选冲突
门禁没有放宽。

### 16.1 TDD 证据

按真实页面逐批建立 RED：

```text
标题锚点与数据行分离、绝杀三肖、自动分组、相邻栏目隔离：5 项失败
尾部分组、带期号目录入口、方向镜像区块：3 项失败
历史逐期验证共享完整窗口：1 项失败
跨行九肖、固定版权提示、===分组===：2 项失败
相同期重复占用窗口、无效期污染其他期：2 项失败
```

每批只做最小实现后转 GREEN。最终新增回归覆盖：

- 标题/作者锚点与连续历史行绑定，遇到无关栏目立即停止。
- 绝杀三肖按固定十二生肖顺序计算九肖补集。
- 琴棋书画、梅兰菊竹、东南西北、春夏秋冬、风雨雷电保存原分组证据。
- 支持书名号、方括号、圆括号、尖括号、尾部分组和等号包裹分组。
- 期号行与紧邻九肖行绑定；只跳过已明确识别的站内版权提示。
- top/bottom 先按方向选择不同期号窗口，再做同期冲突判断。
- 同值重复不占用期号窗口；不同值重复仍返回 CANDIDATE_CONFLICT。
- 历史审计逐期隔离数量、锚点和冲突错误，不让一个坏期拖垮其他期。

结论：PASS。

### 16.2 修改范围

本次修改：

- `v2/parsers/registry.py`
- `v2/parsers/direct_nine.py`
- `v2/parsers/grouped.py`
- `v2/validator.py`
- `v2/services/history.py`
- `v2/tests/test_parsers.py`
- `v2/tests/test_golden.py`
- `v2/AGENTS.md`

本次生成或更新：

- `v2/reviews/.coverage-step-05-history-rereview`
- `v2/reviews/step-05-history-rereview-coverage.json`
- `v2/reviews/step-08-v2-golden.json`

没有修改配置、缓存、正式 TXT、V1 Python/JSON/BAT，也没有顺手重构其他
生产模块。结论：PASS。

### 16.3 真实页面审核

修复后使用 TLS 校验开启、独立 V2 运行时和低并发 6 完成 318 个活跃站点
的 210-201 期真实导出：

```text
sources=318
unique_identities=318
entries=3180
success=2805
structured_errors=375
```

相较首次 V2 导出的 307 条成功记录，通用解析已恢复 2498 条。抽样真实页面
覆盖动态 API、普通论坛、SPA 用户页、分组、绝杀、跨行、页面上下镜像和
同页多栏目。`寻根问底` 的 207 期原文为重复分组“琴琴棋”，只失败 207，
210-208 和 206-201 不再被污染。

剩余差异没有在本步骤隐瞒：列表详情遇单期缺失会整批失败、部分 SPA 返回
空壳、跨域跳转被抓取器拒绝、OCR 实时识别漂移、页面已从 210 更新到 211，
以及 V1/V2 导出时刻不同。这些分别属于 Step 04 抓取器或 Step 08 同步黄金
基准，不以放宽 Parser 规则处理。

结论：PASS；Step 08 仍未通过。

### 16.4 测试、覆盖率与静态审核

```text
V2 tests: 119/119 passed
Affected Parser/Validator/History coverage: 91%
DirectNineParser: 100%
Parser registry: 94%
Validator: 91%
HistoricalAuditService: 100%
Ruff: PASS
compileall: PASS
Pyright: 未安装
```

首次覆盖率审核发现 `services/history.py` 只有 78%，门禁未通过；补充批量
并发和未知注册键测试后达到 100%，没有通过降低阈值规避。

结论：PASS。

### 16.5 架构、安全、数据与 V1 审核

```text
V2 production forbidden V1 imports=0
core source.name branches=0
Parser network/browser/file I/O matches=0
V2 JSON files=29, invalid=0
V1 tests=188/188 passed
V1 baseline hashes=20 checked, 0 mismatches
```

V1 导出器在 `v2/tests/golden` 中的独立进程导入属于 Step 08 明确许可，V2
生产目录没有 V1 依赖。未发现硬编码密钥、危险删除、缓存写入或正式入口
切换。结论：PASS。

### 16.6 复审结论

Step 05 本次重新打开后的范围、规则、语法、静态、测试、覆盖率、架构、
安全、数据、真实页面和 V1 回归门禁全部通过，可以重新标记为 `[x] 已完成`，
并恢复 Step 08 为唯一 `[>] 进行中`。

## 17. 2026-07-30 相邻括号栏目边界复审

Step 08 在 `青藤之凉` 发现 4 条 CANDIDATE_CONFLICT。真实正文显示目标
`青藤之凉（春夏秋冬）` 历史后紧接 `戳你的肺（琴棋书画）`；原续行判断
只因下一行含括号就把新栏目并入目标区块。

先增加“括号栏目标题必须截断”的 RED 测试，原实现多解析第二个 210 期。
最小修复把续行限定为：上一期号行本身尚不可解析，且与紧邻下一行合并后
才能形成有效候选。完整期号行之后的括号标题、映射说明或广告都不再续接。

真实复核结果与同步 V1 完全一致：

```text
success issues=210,209,206,204,203,201
missing issues=208,207,205,202
candidate conflicts=0
```

复审门禁：V2 127/127，受影响 Parser/Validator/History 覆盖率 91%，
`registry.py` 95%，Ruff 和 compileall 通过，Pyright 未安装；V1 188/188，
20 个哈希无变化；生产 V1 导入、站点名称分支和 Parser I/O 均为 0。

修改范围仅为 `v2/parsers/registry.py`、`v2/tests/test_parsers.py`、
`v2/AGENTS.md` 及对应覆盖率/审核产物。复审结论：PASS；恢复 Step 08。

## 18. 2026-07-30 用户主页帖子隔离复审

Step 08 黄金审核发现 `#/users/` 用户主页会同时渲染多个帖子。通用整页解析
在尾部方向会落到页面末端的其他帖子，使丰利骨头、盐卤香灯的目标历史退出
方向窗口。按契约暂停 Step 08、重开 Step 05。

先增加 RED，固定三条边界：作者名或别名必须精确匹配；栏目必须与作者位于
同一发帖时间区块；其他作者的同一期九肖必须完全排除。新增
`ProfileHistoryParser` 只负责按作者、时间和栏目切出帖子，再委托已审核的
`DirectNineParser`，没有复制九肖规则，也没有网络或文件 I/O。

在生产配置不变的前提下，将全部 16 个 `#/users/` Source 临时指向新插件，
严格 TLS 真实抓取 210-201 期，并与同步 V1 黄金逐站逐期比较：160/160 一致，
0 错值、0 错期、0 错误类别差异。证据见
`reviews/step-05-profile-live.json`。

门禁结果：

```text
Custom parser tests=6/6 passed
Affected parser/golden tests=48/48 passed
V2 full tests=133/133 passed
Affected coverage=91%
profile_history.py=100%
direct_nine.py=100%
validator.py=91%
history.py=100%
Ruff=PASS
compileall=PASS
Pyright=未安装
Parser network/browser/file I/O matches=0
Parser source-name branches=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：新增 `v2/parsers/custom/profile_history.py`，修改
`v2/parsers/factory.py`、`v2/tests/test_custom_parsers.py`、`v2/AGENTS.md`，
并新增本次覆盖率和真实审核产物。未修改 V1、生产配置、缓存、正式 TXT 或
BAT。范围、架构、规则、语法、类型可用性、静态、测试、覆盖率、安全、
差异、数据和真实页面门禁全部通过。复审结论：PASS。

## 19. 2026-07-30 精确命名栏目边界复审

跨域 frame 修复后，八步毛哥的同源主 DOM 可正常读取，但通用 Parser 因
`source.name` 同时匹配同页几十个其他栏目，错误收集“春夏秋冬”等历史。
目标 `八步毛哥【绝杀三肖】` 当前只存在 210 期，不能扩大通用规则接受其他
栏目。

先增加 RED，要求精确 `section_marker` 起始，并在下一个同站 `【栏目】`
标题前截断；前后栏目中的 209 期都不得进入候选。新增 `NamedSectionParser`
只切分区块并委托 `DirectNineParser`，缺少精确栏目时返回
`ANCHOR_MISSING`，不访问网络或文件。

真实页面严格 TLS 复核 210-201：210 为
`鼠兔龙蛇马羊猴鸡猪`，209-201 全部 `ISSUE_MISSING`，与同步 V1 10/10
一致。证据见 `reviews/step-05-section-live.json`。

门禁结果：

```text
Custom parser tests=8/8 passed
Affected parser/golden tests=50/50 passed
V2 full tests=136/136 passed
Affected coverage=91%
named_section.py=90%
direct_nine.py=100%
validator.py=91%
Ruff=PASS
compileall=PASS
Pyright=未安装
Parser I/O matches=0
Parser source-name branches=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：新增 `v2/parsers/custom/named_section.py`，修改 Parser 工厂、
custom parser 测试、`v2/AGENTS.md`、本报告及审核产物。未修改 V1、配置、
缓存、正式 TXT 或 BAT。全部门禁通过，复审结论：PASS。

## 15. 2026-07-29 OCR 证据绑定复审

Step 04 补齐 IMAGE_OCR Document 后，真实页面显示栏目身份位于 DOM，
OCR 图片只包含无括号历史记录。原 ImageOcrParser 只把 OCR Document
交给 DirectNineParser，返回 ANCHOR_MISSING。按执行契约再次暂停 Step 07，
重新打开 Step 05。

先增加真实组合 RED 测试：DOM 含栏目别名、OCR 含
`210期：连续九肖`，原实现稳定失败为 ANCHOR_MISSING。最小修复：

- 用全部 Document 验证 Source 栏目、站名或别名锚点。
- 只从 IMAGE_OCR Document 提取记录。
- 同时接受已有括号九肖和边界明确的连续九个生肖字。
- 保留 OCR 原始行、document label、行号和 image_index。
- Parser 仍不访问网络、不截图、不读写文件。

复审结果：

```text
Parser tests: 14/14 passed
ImageOcrParser coverage: 93%
V2 full tests: 97/97 passed
V1 tests: 188/188 passed
v1_hashes_verified=20
Ruff: PASS
compileall: PASS
Pyright: 未安装
```

真实页面结果：

- 嫦娥公式 210期：羊马蛇龙兔虎牛鼠猪。
- 嫦娥奔月 210期：马蛇龙兔虎牛鼠猪狗。
- 两项均为 image_ocr 证据、图片索引 3，与 V1 缓存一致。
- 证据保存在 `v2/reviews/step-05-ocr-live.json`。

架构扫描：Parser 网络/浏览器/文件 I/O 为 0，站点名称条件分支为 0。
V1 文件、配置、缓存和 BAT 哈希未变化。

复审结论：PASS。Step 05 可以重新标记为 `[x] 已完成`，恢复 Step 07。
