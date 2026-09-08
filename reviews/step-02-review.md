# Step 02 严格审核报告

审核日期：2026-07-29  
审核对象：领域模型、错误契约与站点身份  
结论：PASS

## 1. 范围审核

本步骤新增：

- `v2/domain/__init__.py`
- `v2/domain/errors.py`
- `v2/domain/models.py`
- `v2/domain/identity.py`
- `v2/tests/test_domain.py`
- `v2/reviews/.coverage-step-02`
- `v2/reviews/step-02-coverage.json`

没有修改 V1，没有实现配置、网络、解析、缓存或 CLI。

结论：PASS。

## 2. TDD 审核

RED：

```text
python -m unittest discover -s .\v2\tests -p 'test_domain.py' -v
ModuleNotFoundError: No module named 'v2.domain'
Ran 1 test
FAILED (errors=1)
```

GREEN：

```text
Ran 12 tests
OK
```

V2 全量：

```text
Ran 18 tests
OK
```

结论：PASS。

## 3. 领域契约审核

- Source、Document、Evidence、Record、History、Result 和 Failure 均为冻结且启用 `slots` 的数据类。
- 嵌套配置、元数据、生肖、记录和失败集合均转换为元组。
- Record 保留原始生肖顺序，不在模型层排序。
- History 允许保留同站同期不同候选，留给 Validator 判定冲突。
- Result 明确区分 success、failure 和 partial 状态。
- SourceIdentity 绑定名称、标准化 URL、方向和 `section_marker`。
- 身份键使用规范 JSON 的 SHA-256，长度固定为 64。

执行证据：

```text
frozen_slot_models=7
error_codes=15
source_identity_key_length=64
step_02_domain_contract_audit=PASS
```

结论：PASS。

## 4. 错误契约审核

- 15 个 ErrorCode 均为稳定 ASCII 大写标识。
- 业务判断不依赖中文错误文案。
- Failure 使用错误码、技术详情和不可变上下文。
- 空上下文键、非法模型值、无 failure 的失败结果均关闭失败。

结论：PASS。

## 5. 身份与 URL 审核

- HTTP/HTTPS scheme 和主机名规范为小写。
- 默认 80/443 端口被规范化。
- 根路径、尾部斜杠、查询参数顺序和 fragment 得到稳定处理。
- URL 中的名称、方向或栏目锚点变化都会改变身份键。
- 非 HTTP(S) URL 关闭失败。

结论：PASS。

## 6. 语法、类型与静态审核

- `py_compile`：PASS。
- Ruff：PASS，零错误。
- Pyright：当前环境未安装，未伪造通过结论。
- 领域模块可由 Python 3.11.15 正常导入和执行。

结论：PASS。

## 7. 覆盖率审核

```text
Statements: 233
Missing: 25
Branches: 60
Coverage: 82.59%
Required: 80%
```

覆盖率证据保存在 `v2/reviews/step-02-coverage.json`。

结论：PASS。

## 8. 架构与安全审核

```text
v1_runtime_imports=0
source_name_branches=0
secret_matches=0
step_02_architecture_security=PASS
```

- V2 领域层没有导入 V1。
- 没有站点名称条件分支。
- 没有密钥或密码。
- 模型层不访问网络、不写文件。

结论：PASS。

## 9. V1 回归与数据审核

```text
Ran 188 tests in 1.469s
OK
v1_hashes_verified=20
```

- V1 全量测试继续通过。
- Step 01 固化的 20 个 V1 文件哈希全部一致。
- 本步骤没有修改活跃、封存或缓存数据。

结论：PASS。

## 10. 差异与临时文件审核

- Step 02 新增 7 个持久文件；本报告为第 8 个。
- Python 执行生成的 `__pycache__` 均在确认路径属于 `v2` 后删除。
- 覆盖率原始数据和 JSON 保留为审核证据。
- 没有 V2 目录外意外变化。

结论：PASS。

## 11. 真实审核适用性

本步骤只定义纯领域对象和身份规范，不访问网页，因此真实页面审核不适用。真实抓取审核从 Step 04 开始。

结论：PASS。

## 12. 最终结论

Step 02 的所有适用门禁均已通过，可以将 Step 02 标记为 `[x] 已完成`，并将 Step 03 标记为唯一的 `[>] 进行中`。

## 13. 2026-07-29 哈希路由身份复审

Step 07 自动迁移真实 318 个活跃站点时，RED 测试发现多个
`https://host/#/users/<id>` 地址被原归一化逻辑错误合并。按执行契约，
Step 07 暂停，Step 02 重新标记为进行中。

复审先增加失败测试，证据为两个不同 `#/users` 路由生成相同身份 key。
最小修复只保留以 `/` 或 `!/` 开头的 SPA 路由 fragment；普通
`#page-heading` 文档锚点仍被忽略。

复审范围：

- 修改 `v2/domain/identity.py`。
- 修改 `v2/tests/test_domain.py`。
- 新增 `v2/reviews/.coverage-step-02-rereview`。
- 新增 `v2/reviews/step-02-rereview-coverage.json`。

复审结果：

```text
Domain tests: 13/13 passed
Config/storage regression: 17/17 passed
V2 full tests: 89/89 passed
Identity module coverage: 92%
V1 tests: 188/188 passed
v1_hashes_verified=20
Ruff: PASS
compileall: PASS
Pyright: 未安装
```

- 普通 URL 等价归一化行为未改变。
- SPA 作者页现在按完整哈希路由形成不同身份。
- V2 生产代码仍未导入 V1，未增加站点名称分支。
- 未修改 V1 文件、配置、缓存或 BAT。
- 真实 318/14 自动迁移的原身份冲突已解除。

复审结论：PASS。Step 02 可以重新标记为 `[x] 已完成`，恢复 Step 07。
