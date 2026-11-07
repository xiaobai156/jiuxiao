"""区块边界（邻栏吸行）与升序页截断的回归测试（2026-11-06 审核修复）。

修复前的两条真实路径：

1. 邻栏吸行：区块只由首个锚点定位，之后凡是「NNN期」行一律继续收。
   本站 310/309 之后若跟着别栏的「288期 云中白鹤【精华九肖】」+ 九肖行，
   288 会被当成本站记录并**通过**校验（实测 SUCCESS）。
   修法：区块已学到本栏标题后，再遇到带期号、带其它栏目标题且不含本栏
   锚点的行，即结束区块，让指定期取不到（失败），而不是取到他栏值。
2. 升序页截断：区块内「期号变大」曾被一律当作 001/365 循环断点。
   升序页 264→265→266 因此只剩 264，266 收不到。
   修法：只有 (1,365) / (365,1) 才是循环断点。

两个断言都落在「解析结果 + 校验失败码」上，不依赖内部函数调用次数。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if "v2" not in sys.modules:
    specification = importlib.util.spec_from_file_location(
        "v2",
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert specification is not None and specification.loader is not None
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.direct_nine import DirectNineParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


def _source(name: str, marker: str, position: Position) -> Source:
    return Source(
        name=name,
        url="https://example.test/read.php?tid=1",
        position=position,
        section_marker=marker,
        fetcher="browser_page",
        parser="direct_nine",
    )


def _document(text: str) -> Document:
    return Document(
        label="browser-dom",
        url="https://example.test/read.php?tid=1",
        text=text,
        method=DocumentMethod.BROWSER_DOM,
    )


# 本栏 310/309，随后是别栏（云中白鹤）的 288 期与它的九肖行。
_NEIGHBOUR_COLUMN_PAGE = (
    "【吉祥意见】\n"
    "310期:【吉祥意见】九肖中特【鼠鸡蛇狗龙猪虎兔羊】开:狗21中\n"
    "309期:【吉祥意见】九肖中特【猴牛鸡羊马猪蛇鼠龙】开:马49中\n"
    "288期 云中白鹤【精华九肖】\n"
    "【猪狗猴羊马蛇龙兔虎】开:？00中\n"
)


def test_neighbour_column_issue_line_ends_block_instead_of_being_absorbed() -> None:
    target = _source("吉祥意见", "九肖中特", Position.TOP)

    parsed = DirectNineParser().parse(
        target,
        (_document(_NEIGHBOUR_COLUMN_PAGE),),
        (311,),
    )

    assert 288 not in {record.issue for record in parsed.records}, (
        "别栏的 288 期不得并入本栏区块"
    )
    assert parsed.blocks[0].block_end == 3, "区块必须停在别栏标题行之前"
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (311,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_boundary_fix_keeps_own_history_readable() -> None:
    target = _source("吉祥意见", "九肖中特", Position.TOP)

    parsed = DirectNineParser().parse(
        target,
        (_document(_NEIGHBOUR_COLUMN_PAGE),),
        (310,),
    )

    assert {record.issue for record in parsed.records} == {310, 309}
    verified = Validator().validate(target, parsed, (310,))
    assert verified.history.records[0].zodiac_text == "鼠鸡蛇狗龙猪虎兔羊"


def test_first_data_row_merges_its_title_even_when_anchor_has_one() -> None:
    """锚点行带标题、数据行带的是另一个标题时，不得把本栏数据判成他栏。"""
    target = _source("出言不逊", "出言不逊", Position.TOP)
    page = (
        "【出言不逊九肖】\n"
        "310期【九肖中特】鼠鸡蛇狗龙猪虎兔羊\n"
        "309期【九肖中特】猴牛鸡羊马猪蛇鼠龙\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (309,))

    assert parsed.blocks[0].observed_issues == (310, 309)
    verified = Validator().validate(target, parsed, (309,))
    assert verified.history.records[0].zodiac_text == "猴牛鸡羊马猪蛇鼠龙"


def test_same_column_title_change_still_reads_older_history() -> None:
    """同栏换了标题写法（新记录【九肖中特】、旧记录【精华九肖】）不算他栏。"""
    target = _source("出言不逊", "出言不逊", Position.TOP)
    page = (
        "【出言不逊】\n"
        "310期【九肖中特】鼠鸡蛇狗龙猪虎兔羊\n"
        "309期【精华九肖】猴牛鸡羊马猪蛇鼠龙\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (309,))

    assert parsed.blocks[0].observed_issues == (310, 309)
    verified = Validator().validate(target, parsed, (309,))
    assert verified.history.records[0].zodiac_text == "猴牛鸡羊马猪蛇鼠龙"


def test_same_column_title_change_on_ascending_page() -> None:
    """升序页同样：期号顺着本块历史方向前进，换了标题也仍是本栏。"""
    target = _source("出言不逊", "出言不逊", Position.BOTTOM)
    page = (
        "【出言不逊】\n"
        "309期【九肖中特】猴牛鸡羊马猪蛇鼠龙\n"
        "310期【精华九肖】鼠鸡蛇狗龙猪虎兔羊\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (310,))

    assert parsed.blocks[0].observed_issues == (309, 310)
    verified = Validator().validate(target, parsed, (310,))
    record = verified.history.records[0]
    assert record.zodiac_text == "鼠鸡蛇狗龙猪虎兔羊"
    assert record.evidence.direction_window == (310, 309)


def test_neighbour_older_issue_with_other_author_is_cut() -> None:
    """别栏期号比本栏更旧时，靠「他站作者名」切断（288 期在正文同一行）。"""
    target = _source("出言不逊", "九肖中特", Position.TOP)
    page = (
        "九肖中特\n"
        "310期【出言不逊】九肖【鼠鸡蛇狗龙猪虎兔羊】\n"
        "309期【出言不逊】九肖【猴牛鸡羊马猪蛇鼠龙】\n"
        "288期 云中白鹤【精华九肖】\n"
        "鼠牛虎兔龙蛇马羊猴\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (288,))

    assert 288 not in {record.issue for record in parsed.records}
    assert parsed.blocks[0].block_end == 3
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (288,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING


def test_same_issue_header_line_does_not_cut_the_data_line() -> None:
    """页头「311期: 站名【趣目】」与数据行「311期 数据」同号，不能当逆方向切断。"""
    target = _source("测试站", "测试站【经典必中九肖】", Position.TOP)
    page = (
        "311期: 测试站【经典必中九肖】←※已免费公开\n"
        "发表时间：2018-11-30 16:25:54\n"
        "311期 {测试站九肖} :【狗羊马猴猪蛇龙鸡牛】 开 ?? 准\n"
        "310期 {测试站九肖} :【羊牛狗兔猪蛇鸡鼠龙】 开 46,鸡 准\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (311,))

    assert parsed.records, "同号的数据行不得被切断"
    verified = Validator().validate(target, parsed, (311,))
    record = verified.history.records[0]
    assert record.zodiac_text == "狗羊马猴猪蛇龙鸡牛"
    assert record.evidence.direction_window == (311, 310)


# 升序页：旧期在前、新期在文末，中间夹一行纯域名广告。
_ASCENDING_PAGE = (
    "【出言不逊】\n"
    "264期:【出言不逊】九肖中特【鼠鸡蛇狗龙猪虎兔羊】开:狗21中\n"
    "922308.com 七星好料\n"
    "265期:【出言不逊】九肖中特【猴牛鸡羊马猪蛇鼠龙】开:马49中\n"
    "266期:【出言不逊】九肖中特【马牛龙羊虎狗蛇兔猴】开:？00中\n"
)


def test_ascending_history_is_not_truncated_by_issue_increase() -> None:
    target = _source("出言不逊", "出言不逊", Position.BOTTOM)

    parsed = DirectNineParser().parse(target, (_document(_ASCENDING_PAGE),), (266,))

    assert parsed.blocks[0].observed_issues == (264, 265, 266)
    verified = Validator().validate(target, parsed, (266,))
    record = verified.history.records[0]
    assert record.zodiac_text == "马牛龙羊虎狗蛇兔猴"
    assert record.evidence.direction_window == (266, 265, 264)


def test_new_year_seam_still_ends_block_at_issue_001() -> None:
    target = _source("出言不逊", "出言不逊", Position.TOP)
    page = (
        "【出言不逊】\n"
        "001期:【出言不逊】九肖中特【鼠鸡蛇狗龙猪虎兔羊】开:狗21中\n"
        "365期:【出言不逊】九肖中特【猪狗猴羊马蛇龙兔虎】开:马49中\n"
    )

    parsed = DirectNineParser().parse(target, (_document(page),), (365,))

    assert 365 not in {record.issue for record in parsed.records}, (
        "001→365 是跨轮历史，365 不得当作本栏当期"
    )
    with pytest.raises(ValidationError) as captured:
        Validator().validate(target, parsed, (365,))
    assert captured.value.failure.code is ErrorCode.ISSUE_MISSING
