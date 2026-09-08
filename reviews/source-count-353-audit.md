# 353 站点补齐审核

审核日期：2026-07-30  
状态：`[x] 已完成`

## 目标

修正 V2 只运行 318 个固定站点的问题，使每日 V2 与 V1 一样运行：

- `[x]` 主列表动态站：34 个
- `[x]` 六爱趣专用接口站：1 个
- `[x]` 固定活跃站：318 个
- `[x]` 每日总数：353 个

## 实现与保护

- `[x]` V2 每日运行时从主列表读取站点；20 个 V1 原本排除的标题仍排除。
- `[x]` 每个主列表站必须有已登记的固定顶部/尾部方向；新站没有方向会停止，不猜方向。
- `[x]` 六爱趣仅 POST `type=3` 到专用接口；接口异常、栏目类型不对、缺期或同期期数据冲突均失败，不使用页面凑数。
- `[x]` 运行前拒绝重复站名或重复站点身份。
- `[x]` V2 运行时不导入 `crawler.py`；V1 正式 BAT 和 V1 文件未修改。

## 自动审核

```text
V2 tests=175/175 passed
Ruff=PASS
compileall=PASS
V1 hashes=20 checked, 0 mismatches
```

## 真实 211 期审核

```text
V2 console total=353
V2 result=344 success, 9 failure
V2 cache sources=353
main-list + 六爱趣=35 success, 0 failure
V1/V2 35-source read-only comparison=35 compared, 0 mismatch
```

9 个失败均为固定站自身未更新、目录锚点缺失或九肖不合格；没有把其他站数据写入成功结果。

## 与 Step 10 的关系

本次只证明漏掉的 35 个站已补齐且 211 期数据与 V1 一致。连续 10 个新期影子验收仍是 `0/10`，不因本次审核增加进度，也未切换正式 V1 BAT。
