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
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 测试包")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)

from v2.config.repository import SourceRepository  # noqa: E402
from v2.domain.errors import ErrorCode  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.registry import zodiac_candidates  # noqa: E402
from v2.parsers.split_line import SplitLineParser  # noqa: E402
from v2.validator import ValidationError, Validator  # noqa: E402


FENGFENG_SOURCE = Source(
    "风度翩翩",
    "https://jusbfyu.mkdwi-xa2ua-rsovan.work:29422/article/manager/"
    "6a3236bff21d7a093399eec3?url=hjc",
    Position.BOTTOM,
    "风度翩翩",
    "dynamic_article",
    "split_line",
)

FENGFENG_263 = "猴虎龙马蛇鼠兔羊猪"


def fengfeng_document(line_263: str) -> Document:
    return Document(
        "api:$",
        FENGFENG_SOURCE.url,
        "\n".join(
            (
                "263期：【九肖中特】〓 期期实战",
                "风度翩翩",
                "261期: 〖风度翩翩〗 🐁 九肖中特 🐁开: 羊24 准",
                "【狗.猴.虎.龙.牛.蛇.兔.羊.猪】",
                "262期: 〖风度翩翩〗 🐁 九肖中特 🐁开: 牛30 错",
                "【狗.猴.虎.龙.马.蛇.鼠.羊.猪】",
                f"263期: 〖风度翩翩〗 🐁 九肖中特 🐁开:00准\n{line_263}",
                "重金",
            )
        ),
        DocumentMethod.DYNAMIC_API,
    )


def test_unterminated_payload_bracket_still_yields_the_original_zodiacs() -> None:
    document = fengfeng_document("【猴.虎.龙.马.蛇.鼠.兔.羊.猪")

    parsed = SplitLineParser().parse(FENGFENG_SOURCE, (document,), (263,))
    verified = Validator().validate(FENGFENG_SOURCE, parsed, (263,))

    record = verified.history.records_for(263)[0]
    assert record.zodiac_text == FENGFENG_263
    assert record.evidence.direction_window == (263, 262, 261)
    assert verified.history.current_issue == 263
    assert record.evidence.raw_zodiac_line == "【猴.虎.龙.马.蛇.鼠.兔.羊.猪"


def test_terminated_payload_bracket_keeps_a_single_candidate() -> None:
    document = fengfeng_document("【猴.虎.龙.马.蛇.鼠.兔.羊.猪】")

    parsed = SplitLineParser().parse(FENGFENG_SOURCE, (document,), (263,))
    verified = Validator().validate(FENGFENG_SOURCE, parsed, (263,))

    assert verified.history.records_for(263)[0].zodiac_text == FENGFENG_263


@pytest.mark.parametrize(
    ("issue", "expected"),
    ((262, "狗猴虎龙马蛇鼠羊猪"), (261, "狗猴虎龙牛蛇兔羊猪")),
)
def test_unterminated_payload_keeps_adjacent_issues_intact(
    issue: int,
    expected: str,
) -> None:
    document = fengfeng_document("【猴.虎.龙.马.蛇.鼠.兔.羊.猪")

    parsed = SplitLineParser().parse(FENGFENG_SOURCE, (document,), (issue,))
    verified = Validator().validate(FENGFENG_SOURCE, parsed, (issue,))

    assert verified.history.records_for(issue)[0].zodiac_text == expected


def test_unterminated_payload_still_reports_a_missing_issue() -> None:
    document = fengfeng_document("【猴.虎.龙.马.蛇.鼠.兔.羊.猪")

    parsed = SplitLineParser().parse(FENGFENG_SOURCE, (document,), (999,))

    with pytest.raises(ValidationError) as missing:
        Validator().validate(FENGFENG_SOURCE, parsed, (999,))
    assert missing.value.failure.code is ErrorCode.ISSUE_MISSING


@pytest.mark.parametrize(
    ("line", "expected"),
    (
        ("【猴.虎.龙.马.蛇.鼠.兔.羊.猪", (tuple(FENGFENG_263),)),
        ("【猴.虎.龙.马.蛇.鼠.兔.羊.猪】", (tuple(FENGFENG_263),)),
        ("【书画棋琴】→资料已公開！", ()),
        ("【请充值后查看", ()),
        ("【01.02.03.05.06.07.08.09", ()),
        ("鼠牛虎兔龙蛇马羊猴", (tuple("鼠牛虎兔龙蛇马羊猴"),)),
    ),
)
def test_zodiac_candidates_only_accept_real_zodiac_brackets(
    line: str,
    expected: tuple[tuple[str, ...], ...],
) -> None:
    assert zodiac_candidates(line) == expected


def test_formal_263_column_keeps_its_registered_parser() -> None:
    repository = SourceRepository(
        PROJECT_ROOT / "config" / "sources.json",
        PROJECT_ROOT / "config" / "archived_sources.json",
    )
    sources = {source.name: source for source in repository.load_active()}

    assert sources["土豪劣绅"].parser == "topic_cyclic_grouped"

    archived = {
        entry.source.name: entry.source for entry in repository.load_archived()
    }
    # 风度翩翩 已在 273 期封存（文章已换成五肖中特）；263 的绑定随封存条目保留。
    assert "风度翩翩" not in sources
    assert archived["风度翩翩"].parser == "split_line"
    assert archived["风度翩翩"].position is Position.BOTTOM

    # 尽心竭力 已在 269 期封存（站点删除该文章）；263 的绑定随封存条目保留。
    assert "尽心竭力" not in sources
    assert archived["尽心竭力"].parser == "split_line"
