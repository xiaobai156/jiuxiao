# Step 09 影子运行、切换与回滚工具审核

审核日期：2026-07-30  
状态：PASS，已完成

## 1. 完成内容

- 增加可执行 V2 入口 `python -m v2`，支持单期、多期、影子、预检、切换和回滚。
- 增加独立单期、多期 V2 BAT；只调用 V2 模块，输出和缓存只写入 `v2`。
- 影子运行通过两个独立 Python/浏览器进程执行 V1、V2，V1 仅由 test/golden 工作进程调用。
- 影子报告按站点身份和具体期号原子写入 `v2/reviews`，运行前后校验全部 V1 基准文件字节未变。
- 切换预检固定检查 Step 08 批准、318/14 配置数量、20 个 V1 哈希、V2 入口和事务残留。
- 两个正式 BAT 的切换和回滚使用事务日志、同目录临时文件和原子替换；V1 备份带 SHA-256 校验。
- 提供一键回滚 BAT。Step 09 只在临时目录测试切换/回滚，未调用正式切换。

## 2. TDD 证据

- 先建立 `step-09-user-journeys.md`，定义四条用户旅程、输入输出、失败条件和正式 BAT 边界。
- RED：首次运行新测试因 `ShadowRunService` 不存在失败；入口测试因 `v2.__main__`、V2 BAT 和单期 worker 参数不存在失败。
- GREEN：第 09 步专项测试 21/21 通过。
- 覆盖影子只读保护、错误引擎/期号、子进程失败、预检五项硬门禁、路径逃逸、损坏备份、原子写入失败、切换和精确回滚。

## 3. 真实影子审核

```text
issue=210
V1 sources=318
V2 sources=318
differences=7
VALUE_MISMATCH=0
ERROR_MISMATCH=1
EVIDENCE_MISMATCH=6
```

7 条均不是九肖数据错误：

- 势不可挡、橘色日落、物微志信：V2 按规则多保存分组类型和分组原文，九肖值与顺序相同。
- 大摇大摆、飘香岁月、入骨思念：两次独立抓取间页面的 `开0000/开马49` 状态变化，九肖值与顺序相同。
- 经书澳彩：双方都失败；V1 为 `ISSUE_MISSING`，V2 为更准确的 `ANCHOR_MISSING`。

真实报告：`shadow-210-v1.json`、`shadow-210-v2.json`、`shadow-210-diff.json`。

结论：数据正确，没有九肖值或顺序错误。

## 4. 严格门禁

```text
Step 09 focused tests=21/21 passed
V2 tests=159/159 passed
V2 total coverage=88%
Step 09 core coverage=93%
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
Ruff=PASS
compileall=PASS
Python 3.10 V2 entrypoint=PASS
Pyright=未安装
V2 JSON=62 checked, 0 invalid
production V1 imports=0
active sources=318
archived sources=14
transaction residue=0
```

五个指定封存站心灵乐园、葡京肖王、福星攻略、白手起家、妞逼特肖全部只在封存配置，活跃配置中为 0。

## 5. 安全与差异审核

- 新增：`v2/__main__.py`、`v2/runtime.py`、`v2/services/switching.py`、`v2/storage/switching.py`、第 09 步测试和四个独立 BAT。
- 修改：影子服务及两个 test/golden worker，使影子运行可选择一个具体期号。
- 未修改：两个正式 BAT、V1 Python、V1 配置、V1 缓存、V1 输出和 V2 活跃/封存配置。
- 子进程使用固定模块名和参数数组，不通过 shell 拼接；清单路径逃逸、缺失文件、哈希变化和事务残留全部失败关闭。
- 未发现硬编码密钥、跨域放宽、补位、方向互换或非原子正式写入。

## 6. 最终结论

Step 09 全部门禁通过，可以标记 `[x] 已完成`。V2 工具已经具备影子运行、切换前检查、双 BAT 原子切换和一键精确回滚能力。

Step 10 仍必须等待连续 10 个新期真实影子验收和用户最终切换确认；本步没有提前修改正式 BAT。
