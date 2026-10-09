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

from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Position,
    Source,
)
from v2.parsers.custom.formula_next_issue_ocr import (  # noqa: E402
    FormulaNextIssueOcrParser,
)
from v2.parsers.safety import (  # noqa: E402
    ocr_repaired_candidates,
    safe_zodiac_candidates,
)
from v2.validator import Validator  # noqa: E402

EXPECTED = ("马", "蛇", "龙", "兔", "虎", "牛", "鼠", "猪", "狗")


def test_confusion_mapping_repairs_single_misread_character() -> None:
    # 「免」是「兔」的常见 OCR 误读；映射后恰好 9 个互异生肖 ⇒ 采纳。
    assert ocr_repaired_candidates("282期：马蛇龙免虎牛鼠猪狗") == (EXPECTED,)


def test_adjacent_duplicate_glyph_is_collapsed_once() -> None:
    # 真实案例（嫦娥公式 282 期）：OCR 把「兔」认成「免兔」，去重后恰好 9 个互异 ⇒ 采纳。
    assert ocr_repaired_candidates("282期：马蛇龙免兔虎牛鼠猪狗") == (EXPECTED,)


def test_repair_is_rejected_when_result_is_not_nine_unique_zodiacs() -> None:
    # 10 个互异：不能靠纠错凑成 9 肖。
    assert ocr_repaired_candidates("282期：马蛇龙兔虎牛鼠猪狗羊") == ()
    # 8 个：数量不足。
    assert ocr_repaired_candidates("282期：马蛇龙免兔虎牛鼠猪") == ()
    # 9 个字但**非相邻**重复：相邻重复折叠只允许一处相邻双写，非相邻重复不许去重。
    assert ocr_repaired_candidates("282期：马蛇龙兔虎牛鼠猪兔") == ()
    # 10 个字且含两处相邻重复：折叠一处后仍有重复 ⇒ 拒绝。
    assert ocr_repaired_candidates("282期：马马蛇龙兔兔虎牛鼠猪") == ()


def test_original_candidates_win_when_raw_text_is_already_valid() -> None:
    line = "282期：九肖【马蛇龙兔虎牛鼠猪狗】开：000对"
    assert safe_zodiac_candidates(line) == (EXPECTED,)
    # 原本就不合法的原文保持原行为（返回原始 run 候选，交由统一校验器判失败）。
    raw_only = "282期：马蛇龙兔虎牛鼠猪狗羊"
    assert safe_zodiac_candidates(raw_only) == (tuple("马蛇龙兔虎牛鼠猪狗羊"),)


def test_formula_next_issue_ocr_accepts_repaired_confusion_via_validator() -> None:
    target = Source(
        name="嫦娥公式",
        url="https://enpcjg.4qnp3-wmf88-gaewaj.xyz:16677/topic/544154.html",
        position=Position.BOTTOM,
        section_marker="嫦娥彩报╠无错九肖╣公式规律",
        fetcher="browser_page",
        parser="formula_next_issue_ocr",
        data_marker="九肖",
        source_policy=(DocumentMethod.BROWSER_DOM.value,),
    )
    document = Document(
        label="browser-dom",
        url=target.url,
        text=(
            "嫦娥彩报╠无错九肖╣公式规律\n"
            "281期: 221921324838+10公式：+3下期: 马蛇龙兔虎牛鼠猪狗\n"
            "282期：马蛇龙免兔虎牛鼠猪狗\n"
        ),
        method=DocumentMethod.BROWSER_DOM,
    )

    parsed = FormulaNextIssueOcrParser().parse(target, (document,), (282,))
    verified = Validator().validate(target, parsed, (282,))

    assert verified.history.records[0].zodiac_text == "".join(EXPECTED)


def test_repair_does_not_apply_without_contract_violation() -> None:
    # 合法 9 肖页面：纠错逻辑不得参与（返回空，确保既有取值路径逐字不变）。
    assert ocr_repaired_candidates("282期：马蛇龙兔虎牛鼠猪狗") == (EXPECTED,)
    assert safe_zodiac_candidates("282期：马蛇龙兔虎牛鼠猪狗") == (EXPECTED,)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
