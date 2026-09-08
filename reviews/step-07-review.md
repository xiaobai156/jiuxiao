# Step 07 严格审核报告

审核日期：2026-07-29  
审核对象：V1 配置自动迁移、特殊规则配置与 custom parser  
结论：PASS

## 1. 范围审核

本步骤新增或生成：

- `v2/config/migrate_v1.py`
- `v2/config/migration_overrides.json`
- `v2/parsers/factory.py`
- `v2/parsers/custom/common.py`
- `v2/parsers/custom/white_tiger.py`
- `v2/parsers/custom/yueying.py`
- `v2/parsers/custom/color_info_grouped.py`
- `v2/parsers/custom/single_season_complement.py`
- `v2/tests/test_migration.py`
- `v2/tests/test_custom_parsers.py`
- `v2/reviews/.coverage-step-07`
- `v2/reviews/step-07-coverage.json`
- `v2/reviews/step-07-migration.json`
- `v2/reviews/step-07-live.json`

本步骤由迁移器原子替换：

- `v2/config/sources.json`
- `v2/config/archived_sources.json`

迁移真实数据时发现的三个基础缺口严格按契约重新打开并复审：

- Step 02：SPA 哈希路由身份，复审 PASS。
- Step 04：配置驱动的内存 OCR Document，复审 PASS。
- Step 05：书名括号和 DOM/OCR 证据绑定，复审 PASS。

没有修改 V1，没有切换 BAT，没有进入历史全量差异或正式入口工作。

结论：PASS。

## 2. TDD 审核

初始迁移 RED：

```text
ModuleNotFoundError: No module named 'v2.config.migrate_v1'
```

真实 318/14 首次转换触发 SPA 身份冲突，随后按 Step 02 RED-GREEN-复审流程修复。

custom parser RED：

```text
ModuleNotFoundError: No module named 'v2.parsers.custom.color_info_grouped'
```

真实页面审核又先后得到并修复：

- 月影舞华 ISSUE_MISSING：真实页面使用 `《》`。
- 风神九肖 INVALID_ZODIAC_COUNT：同一期包含三/五/七/九肖行。
- 彩资讯网 ISSUE_MISSING：组字位于无括号行尾。
- OCR SOURCE_UNTRUSTED/ANCHOR_MISSING：图片懒加载且栏目身份在 DOM。

每项均先固化失败测试，再做最小实现，相关重新审核报告均为 PASS。

结论：PASS。

## 3. 自动迁移审核

- 318 个活跃站点和 14 个封存站点全部直接读取 V1 JSON 转换，没有手工重录主体数据。
- 活跃和封存的名称、URL、数量及顺序与 V1 原文件一致。
- V2 已落盘配置与 build_migration 重新生成的 bundle 完全相等。
- 中文顶部/尾部转为 top/bottom；URL、栏目、API、分组映射和列表关键字全部保留。
- fetcher 由 URL 和 detail_link_keyword 推导。
- 无法从 URL 推导的别名、有效方向和特殊 parser 只存于 migration_overrides.json。
- 两个配置文件通过同目录事务日志和原子替换同时提交。
- 非空目标拒绝再次迁移，防止覆盖后续人工配置。

证据保存在 `v2/reviews/step-07-migration.json`。

结论：PASS。

## 4. 数量、顺序与封存审核

```text
active_exact=True
archived_exact=True
active_count=318
archived_count=14
```

- 心灵乐园、妞逼特肖、葡京肖王、福星攻略、白手起家只存在于 archived_sources.json。
- SourceRepository.load_active() 只返回 318 个活跃站点，不加载 14 个封存站点。
- 共享 URL 只有不同非空 section_marker 时才通过配置仓库校验。
- `#/users/<id>` SPA 路由保留在标准化身份中，不再互相碰撞。

结论：PASS。

## 5. 配置策略审核

332 个来源的抓取器分布：

```text
browser_page=237
dynamic_article=93
list_detail=2
```

解析器分布：

```text
direct_nine=286
grouped=37
split_line=2
image_ocr=2
white_tiger=1
yueying=1
color_info_grouped=1
single_season_complement=2
```

- 霸王码特和女霸君主固定为 dynamic_article + split_line。
- 分组型缺省映射从 V1 zodiac_spec_groups.json 自动选择对应四组。
- OCR、月影、白虎、彩资讯和绝杀一季通过配置选择专属纯解析器。
- ParserRegistry 工厂可解析每个实际配置中的 parser key。

结论：PASS。

## 6. custom parser 审核

- white_tiger 只读取白虎可见区段，并只接收九肖行。
- yueying 将网页最旧到最新顺序转换为 top 方向顺序，同时保留原始行号证据。
- color_info_grouped 只读取指定栏目，支持括号组字和真实无括号行尾三组字。
- single_season_complement 根据明确的春夏秋冬映射生成被杀一季的九肖补集。
- 所有 custom parser 不访问网络、不读写文件、不判断 source.name。

结论：PASS。

## 7. 真实页面审核

使用正式单期模式、`history_mode=false`、TLS 校验开启，九个现存特殊站点全部 success：

```text
月影舞华  羊狗猪牛鸡蛇龙猴兔
风神九肖  鸡马羊虎蛇牛兔猪猴
嫦娥公式  羊马蛇龙兔虎牛鼠猪
嫦娥奔月  马蛇龙兔虎牛鼠猪狗
彩资讯网  羊猴猪兔蛇鸡鼠牛狗
橘色日落  虎兔龙蛇马羊猴鸡狗
物微志信  虎兔龙蛇马羊猴鸡狗
霸王码特  狗猴虎鸡龙牛蛇羊猪
女霸君主  猴鸡龙马牛鼠兔羊猪
```

全部与 V1 210 期缓存一致。证据保存在 `v2/reviews/step-07-live.json`。

结论：PASS。

## 8. 测试与覆盖率审核

```text
V2 tests: 97/97 passed
V2 total coverage: 93%
```

- migrate_v1.py：86%。
- custom parser：最低 87%。
- parser factory：100%。
- browser_page.py：80%。
- image_ocr.py：93%。
- 所有新增或受影响核心模块均达到 80% 门禁。

结论：PASS。

## 9. 语法、类型与静态审核

- Python compileall：PASS。
- Ruff：PASS，零错误。
- sources、archived_sources、migration_overrides、覆盖率和真实证据 JSON 均可由标准 JSON 解析器读取。
- Pyright：当前环境未安装，已如实记录。

结论：PASS。

## 10. 架构与安全审核

- V2 生产代码导入 crawler、detect_duplicates 或 verify_failed_sites：0。
- domain/fetchers/parsers/services/storage/cli 按 source.name 条件分支：0。
- 站点名称和迁移差异只出现在 JSON 配置、custom 插件测试与审核证据中。
- OCR 截图只使用内存 bytes，V2 目录 PNG 文件为 0。
- 硬编码密钥、Bearer token、私钥、eval、exec、shell 和递归删除业务逻辑：0。

结论：PASS。

## 11. V1 回归与数据审核

```text
Ran 188 tests in 1.529s
OK
v1_hashes_verified=20
```

- V1 关键代码、318/14 配置、210-201 缓存和 BAT 均未修改。
- V2 配置、测试、证据和覆盖数据全部留在 v2 内。
- Step 07 不写 V1 缓存或正式输出。

结论：PASS。

## 12. 差异与临时文件审核

- 目标目录不是 Git 仓库，使用生成 bundle 等值比较、文件哈希和明确文件清单审核差异。
- 本步骤中间 coverage pre 文件已清理，最终覆盖数据保存在 reviews。
- 所有 v2/**/__pycache__ 已在绝对路径核对后清理。
- V2 内没有 OCR PNG 或遗留事务日志。
- 未删除或修改用户数据。

结论：PASS。

## 13. 最终结论

Step 07 的全部门禁已通过，可以标记为 `[x] 已完成`，并将 Step 08 标记为唯一的 `[>] 进行中`。

## 14. 2026-07-30 用户主页策略自动迁移复审

Step 05 已证明 `#/users/` 必须使用帖子隔离插件。Step 07 重新打开后，先在
真实 V1 迁移测试中增加 RED：全部 16 个此类 URL 必须自动得到
`profile_history`，旧迁移器实际返回 `direct_nine`。最小实现仅依据 URL
结构推导 parser，没有增加站点名称分支或 16 条手工覆盖项。

正式配置通过现有 `build_migration` 从 V1 重新生成，提交前逐字段断言：只允许
16 个活跃 Source 的 `parser` 从 `direct_nine` 改为 `profile_history`；数量、
顺序、身份及所有其他字段必须相同；封存配置必须完全相同。两份 V2 配置随后
通过同目录原子事务提交，未留下事务文件。

迁移后数据审核：

```text
active=318
archived=14
active_exact_generated_bundle=True
archived_exact_generated_bundle=True
profile_history=16
direct_nine=270
configured live checks=160/160 matched
指定五站 active=0, archived=5
```

正式配置中的 16 站在严格 TLS 下重新抓取 210-201，并与同步 V1 黄金比较，
160/160 一致。证据见 `reviews/step-07-profile-live.json`；更新后的配置哈希和
策略分布见 `reviews/step-07-migration.json`。

门禁结果：

```text
Migration tests=5/5 passed
V2 full tests=133/133 passed
migrate_v1.py coverage=80%
Ruff=PASS
compileall=PASS
Pyright=未安装
V2 JSON=37 checked, 0 invalid
production V1 imports=0
core source-name branches=0
transaction artifacts=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：`v2/config/migrate_v1.py`、`v2/config/sources.json`、
`v2/config/archived_sources.json`（内容不变但参与原子事务）、
`v2/tests/test_migration.py`、`v2/AGENTS.md`、本审核报告和对应审核产物。
未修改 V1、缓存、正式 TXT 或 BAT。全部门禁通过，复审结论：PASS。

## 15. 2026-07-30 精确栏目策略配置复审

Step 05 新增 `named_section` 后，先增加迁移 RED，要求八步毛哥自动配置该
parser；旧 bundle 返回 `direct_nine`。最小修改只在
`migration_overrides.json` 增加一条 parser 配置，Python 核心无站名分支。

正式 V2 配置通过自动 bundle 重建，提交前逐字段断言只允许八步毛哥的
`parser` 从 `direct_nine` 改为 `named_section`，封存配置必须完全一致；
两份配置原子提交，无事务残留。正式 Source 再次真实验证 210-201，与同步
V1 10/10 一致。证据见 `reviews/step-07-section-live.json`。

```text
Migration tests=5/5 passed
V2 full tests=136/136 passed
migrate_v1.py=80%
active=318, archived=14
active_exact_generated_bundle=True
archived_exact_generated_bundle=True
Ruff=PASS
compileall=PASS
Pyright=未安装
transaction artifacts=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：`v2/config/migration_overrides.json`、两份 V2 配置（封存内容不变）、
迁移测试、`v2/AGENTS.md`、本报告及审核产物。未修改 V1、缓存、正式 TXT
或 BAT。全部门禁通过，复审结论：PASS。
