# Step 08 历史黄金差异与全量审核

审核日期：2026-07-30  
状态：PASS，已完成

## 1. 比较范围

- 318 个活跃站点，210-201 共 3180 个站点期号。
- 按 Source 身份、具体期号、九肖原始顺序、错误类别和证据比较。
- V1/V2 独立进程并行真实抓取，V1 只读，V2 严格 TLS。
- 正式候选文件：`step-08-v1-golden.json`、`step-08-v2-golden.json`、
  `step-08-diff.json`。

## 2. 审核中修复并复审的缺口

- SPA 非空外壳提前返回：增加正文就绪重试。
- `#/users/` 多帖子混读：增加 `profile_history`，16 站 160/160 一致。
- 跨域开奖/视频 iframe 拖垮同源正文：丢弃不可信 frame，跨域主 DOM 仍拒绝。
- 八步毛哥同页多栏目混读：增加精确 `named_section`，10/10 一致。
- 列表历史逐期找已下架链接：historical 模式改为最新详情一次读取历史，
  金瓯无缺和蛇蝎美人 20/20 一致。

每项均按 RED、最小实现、真实页面、覆盖率、V1 回归和独立复审执行；对应
Step 04/05/06/07 报告均为 PASS。

## 3. 最新差异

```text
total=52
VALUE_MISMATCH=0
ERROR_MISMATCH=20
EVIDENCE_MISMATCH=32
```

没有九肖值或顺序差异。52 条分为：

- 27 条 V2 强制分组证据：势不可挡 10、橘色日落 10、物微志信 7。
  网页原行和九肖完全一致，V2 按不可变规则额外保存 group_type/group_text；
  V1 证据不完整。
- 10 条经书澳彩失败分类：真实页面为未登录/无权限页。V1 为
  ISSUE_MISSING，V2 为 ANCHOR_MISSING；双方均失败，V2 分类更准确。
- 10 条停止武术 V1 单轮暂时缺失：本轮 V1 为 ISSUE_MISSING、V2 成功；
  前两轮 V1 与 V2 的 210-201 全部值一致，证明不是 V2 越界补数。
- 5 条开奖状态实时更新：大摇大摆、花天酒地、九肖美味、飘香岁月、
  入骨思念各 1 条。九肖值不变，仅 source_line 的开0000/开马49在两个独立
  抓取时刻不同；比较器没有忽略该变化。

逐项结构化证据见 `step-08-approval-required.json`。

## 4. 最终门禁

```text
V2 tests=138/138 passed
V2 total line coverage=90%
V1 tests=188/188 passed
V1 hashes=20 checked, 0 mismatches
Ruff=PASS
compileall=PASS
Pyright=未安装
V2 JSON=60 checked, 0 invalid
production V1 imports=0
active sources=318
archived sources=14
VALUE_MISMATCH=0
```

指定五站心灵乐园、葡京肖王、福星攻略、白手起家、妞逼特肖仍全部只在封存
配置，不进入活跃加载器。缓存、正式 TXT、正式 BAT 和 V1 文件均未修改。

## 5. 最终结论

实现、测试、覆盖率、静态、安全、数据和真实页面门禁已通过。用户已于
2026-07-30 明确确认：V2 数据正确，52 条属于非数据错误差异，允许 Step 08
完成。

当前没有发现会写错期数或九肖值的路径；不满足锚点、方向窗口、唯一候选和
九肖数量规则时会进入失败，不会写错成功。

Step 08 审核结论：PASS。可以标记 `[x]` 并进入 Step 09。
