# Step 06 严格审核报告

审核日期：2026-07-29  
审核对象：服务层、运行模式、V2 缓存、报告层与 CLI  
结论：PASS

## 1. 范围审核

本步骤新增：

- `v2/services/__init__.py`
- `v2/services/crawl.py`
- `v2/services/run_modes.py`
- `v2/services/onboarding.py`
- `v2/services/verification.py`
- `v2/services/shadow.py`
- `v2/services/duplicate.py`
- `v2/services/cache_sync.py`
- `v2/storage/cache.py`
- `v2/storage/reports.py`
- `v2/cli.py`
- `v2/tests/test_services.py`
- `v2/tests/test_run_modes_cli.py`
- `v2/reviews/.coverage-step-06`
- `v2/reviews/step-06-coverage.json`
- `v2/reviews/step-06-live.json`

没有修改 V1，没有迁移配置，没有切换 BAT，也没有实现 Step 07 之后的工作。

结论：PASS。

## 2. TDD 审核

第一轮 RED：

```text
ModuleNotFoundError: No module named 'v2.services'
Ran 1 test
FAILED (errors=1)
```

第二轮 RED：

```text
ModuleNotFoundError: No module named 'v2.cli'
Ran 1 test
FAILED (errors=1)
```

审核加硬 RED：

```text
缺站/乱序缓存批次未拒绝：2 项失败
onboard 少于 10 期或重复期号未拒绝：3 项失败
onboard 成功结果不足 10 期未拒绝：1 项失败
```

最小实现和加硬后：

```text
Step 06 service tests: 16 passed
Step 06 run-mode/CLI tests: 5 passed
V2 full tests: 83 passed
```

结论：PASS。

## 3. 服务职责审核

- CrawlService 只解析注册表、抓取文档、调用 Parser 和 Validator，不写文件。
- CrawlRunService 先在内存核对站点身份、顺序和期数，再允许报告或缓存写入。
- VerificationService 只有 CrawlService 依赖，不持有配置、缓存或报告仓库。
- OnboardingService 在真实近 10 期和判重完成前不写活跃配置。
- DuplicateChecker 按具体期号和九肖原始顺序比较；3 至 5 期进入人工复核，6 期及以上判重。
- ShadowComparator 按稳定站点身份和具体期号对齐，不按列表位置猜测。

结论：PASS。

## 4. 运行模式审核

- `crawl`：逐站结果身份、顺序和期数完整后写 TXT，并允许同步单期缓存。
- `crawl-range`：每期独立抓取，所有批次先完成校验，只写逐期 TXT 和汇总失败 TXT。
- 多期流程没有调用 CacheSyncService；测试中的缓存调用次数为 0。
- `verify` 返回独立 Result，不写正式配置、缓存或 TXT。
- `onboard` 只在近 10 期完整且 DuplicateState=CLEAR 时原子添加配置。
- `shadow` 和 `duplicate` 使用独立纯比较器，不接触正式缓存。

结论：PASS。

## 5. 缓存与报告审核

- 缓存以完整 Source 稳定身份对齐，并保持活跃站点顺序。
- 缺站、乱序或期号不一致的批次在读取和写入正式缓存前失败。
- 失败站点会删除该期旧九肖并记录稳定 ErrorCode，不能保留旧值冒充成功。
- 缓存只保留最近 10 个具体期号，JSON 通过同目录临时文件和原子替换写入。
- 中文错误只由 ReportRepository 根据 ErrorCode 渲染；业务判断不依赖中文文案。
- 本步骤全部配置和缓存写入测试均使用临时目录，V1 正式数据未被触碰。

结论：PASS。

## 6. CLI 审核

- CLI 覆盖 crawl、crawl-range、onboard、verify、shadow 和 duplicate 六个命令。
- CLI 只定义参数、执行基本参数类型检查并调用注入的服务处理器。
- CLI 不加载配置、不访问网络、不读写缓存、不包含站点名称规则。
- 实际依赖装配和 BAT 入口仍按执行契约留给 Step 07 与 Step 09。

结论：PASS。

## 7. 真实运行审核

使用正式单期模式 `history_mode=false`，通过真实 Playwright 上下文执行：

```text
霸王码特  current_issue=210  狗猴虎鸡龙牛蛇羊猪
女霸君主  current_issue=210  猴鸡龙马牛鼠兔羊猪
```

- 两站均使用 dynamic_article + split_line + Validator + CrawlService。
- 两站均为 success，结果与 Step 05 真实验收基准一致。
- TLS 校验未关闭，`ignore_https_errors=false`。
- 没有正式配置、缓存或 TXT 写入。
- 完整证据保存在 `v2/reviews/step-06-live.json`。

结论：PASS。

## 8. 语法、类型与静态审核

- `compileall`：PASS。
- Ruff：PASS，零错误。
- Pyright：当前环境未安装，已如实记录，未伪造通过结论。
- JSON 由 Python JSON 编码或测试读取；本步骤 JSON 产物结构有效。

结论：PASS。

## 9. 测试与覆盖率审核

```text
V2 tests: 83/83 passed
V2 total coverage: 94%
```

新增核心模块覆盖率：

- cli.py：97%
- services/crawl.py：97%
- services/run_modes.py：95%
- services/onboarding.py：97%
- services/verification.py：100%
- services/shadow.py：85%
- services/duplicate.py：96%
- services/cache_sync.py：90%
- storage/cache.py：88%
- storage/reports.py：100%

全部高于 80% 门禁，没有跳过或禁用测试。

结论：PASS。

## 10. 架构与安全审核

- V2 生产代码导入 V1 模块：0。
- 核心目录出现已知站点名称特例：0。
- Parser 或 Service 出现网络客户端依赖：0。
- 硬编码密钥、Bearer token 或私钥：0。
- 安全扫描唯一的 `password` 命中是 URL 认证信息拒绝逻辑。
- 正式写入只通过 storage 原子写入函数；没有 shell、eval、exec 或递归删除业务逻辑。

结论：PASS。

## 11. V1 回归与数据审核

```text
Ran 188 tests in 1.408s
OK
v1_hashes_verified=20
```

- V1 318 个活跃站点、14 个封存站点和 210-201 缓存基准未修改。
- V2 活跃和封存配置仍均为空，迁移工作没有提前进入 Step 06。
- V2 缓存测试只写 TemporaryDirectory。

结论：PASS。

## 12. 差异与临时文件审核

- 目标目录不是 Git 仓库，因此使用 Step 05 文件清单、当前 V2 文件清单和 V1 固化哈希交叉审核。
- 本步骤文件全部属于服务、缓存、报告、CLI、测试和审核证据范围。
- 运行产生的 10 个 `v2/**/__pycache__` 已在核对绝对路径后清理。
- 误生成在 V2 外的根目录 `.coverage` 已清理；正式覆盖率数据保存在 `v2/reviews/.coverage-step-06`。
- 没有删除或修改用户数据。

结论：PASS。

## 13. 最终结论

Step 06 的所有适用门禁均已通过，可以将 Step 06 标记为 `[x] 已完成`，并将 Step 07 标记为唯一的 `[>] 进行中`。

## 14. 2026-07-30 历史请求语义传递复审

Step 04 新增 `FetchRequest.history_mode` 后，先增加两条服务 RED：显式历史
`CrawlService` 和 `HistoricalAuditService` 都必须向 Fetcher 传 `True`。
旧实现两项实际均为 `False`。最小修改只传递现有服务参数；普通 crawl 仍为
`False`，多期运行仍逐期调用普通 crawl，不改变缓存边界。

通过正式 `HistoricalAuditService`、严格 TLS 真实运行金瓯无缺和蛇蝎美人，
两站 210-201 与同步 V1 合计 20/20 一致。证据见
`reviews/step-06-history-request-live.json`。

```text
Affected service tests=31/31 passed
V2 full tests=138/138 passed
Service coverage=98%
crawl.py=94%
history.py=100%
Ruff=PASS
compileall=PASS
Pyright=未安装
production V1 imports=0
core source-name branches=0
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
```

修改范围：`v2/services/crawl.py`、`v2/services/history.py`、两份服务测试、
`v2/AGENTS.md`、本报告及审核产物。未修改 V1、配置、缓存、正式 TXT 或
BAT。全部门禁通过，复审结论：PASS。
