# -*- coding: utf-8 -*-
r"""由 audit/archive-tianchengfengpo-283/run_archive.py 生成本轮「美酒咖啡」封存脚本。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "audit" / "archive-tianchengfengpo-283" / "run_archive.py"
DST = ROOT / "audit" / "archive-meijiukafei-285" / "run_archive.py"

NEW_REASON = """REASONS = {
    "美酒咖啡": (
        "用户明确封存，不再抓取；285期抓取失败：站方侧论坛登录墙，游客不可见"
        "（browser_dom 正文仅 157 字符，为「属牛的女孩论坛」访客错误页："
        "「提示信息 » 您没有登录或者没有权限访问此页面，可能有如下几个原因: "
        "读取数据错误,原因：您要访问的链接无效,可能链接不完整,或数据已被删除! "
        "您还不是论坛会员,请先登录论坛」，含登录表单 document.login.pwuser；"
        "页内「美酒咖啡」「285」「九肖」命中均为 0；"
        "独立佐证：站点根域返回 HTTP 200、read.php?tid=54123 亦 HTTP 200（4092 B），"
        "站点存活但该帖对游客不可见）"
    ),
}
"""

target = (SRC).read_text(encoding="utf-8")
target = target.replace(
    'r"""封存 田乘风破（283 期失败：站方已删帖，AdminArticle 不存在）。',
    'r"""封存 美酒咖啡（285 期失败：站方论坛登录墙，游客不可见）。',
)
target = target.replace(
    "→ 缓存整条移除 → 283 失败TXT 清除该站记录（保留其他记录及其顺序）。",
    "→ 缓存整条移除 → 285 失败TXT 清除该站记录（保留其他记录及其顺序）。",
)
target = target.replace(
    'AUDIT = ROOT / "audit" / "archive-tianchengfengpo-283"',
    'AUDIT = ROOT / "audit" / "archive-meijiukafei-285"',
)
target = target.replace(
    'FAIL_TXT = BASE / "七类数据统一归纳失败" / "283期-生肖-失败.txt"',
    'FAIL_TXT = BASE / "七类数据统一归纳失败" / "285期-生肖-失败.txt"',
)
target = target.replace('TARGETS = ["田乘风破"]', 'TARGETS = ["美酒咖啡"]')
start = target.index("REASONS = {")
end = target.index("NAME_RE = ")
target = target[:start] + NEW_REASON + target[end:]
target = target.replace(
    'assert "田乘风破" not in after_fail and after_fail.strip()',
    'assert "美酒咖啡" not in after_fail and after_fail.strip()',
)
DST.write_text(target, encoding="utf-8")
print("written", DST)
print("TARGETS ok:", 'TARGETS = ["美酒咖啡"]' in target)
print("FAIL_TXT ok:", '285期-生肖-失败.txt' in target)
print("残留学号/旧名:", target.count("田乘风破"), target.count("283期"))
