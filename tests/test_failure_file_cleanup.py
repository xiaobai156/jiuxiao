"""失败清单清空后必须删除文件本身（不留 0 字节空壳）。

用户 2026-10-28 明确要求：失败清理干净了，要把失败 txt 删掉。
此前 `write_issue` / `merge_issue` 在失败条目为空时仍会写出空文件，
导致失败目录里留一堆 0 字节 txt。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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

from v2.domain.errors import ErrorCode, Failure  # noqa: E402
from v2.domain.models import (  # noqa: E402
    Document,
    DocumentMethod,
    Evidence,
    History,
    Position,
    Record,
    Result,
    Source,
)
from v2.storage.reports import ReportRepository  # noqa: E402

ISSUE = 301


def _source(name: str) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{name}",
        position=Position.TOP,
        section_marker=name,
        fetcher="browser_page",
        parser="direct_nine",
    )


def _evidence(name: str) -> Evidence:
    return Evidence(
        method="direct",
        source_line=f"{ISSUE}期【鼠牛虎兔龙蛇马羊猴】",
        directory_anchor=name,
        document_label="test",
        document_url=f"https://example.test/{name}",
        document_method=DocumentMethod.BROWSER_DOM.value,
        raw_issue_line=f"{ISSUE}期",
        raw_zodiac_line="鼠牛虎兔龙蛇马羊猴",
    )


def _success(name: str) -> Result:
    source = _source(name)
    record = Record(
        issue=ISSUE,
        zodiacs=tuple("鼠牛虎兔龙蛇马羊猴"),
        evidence=_evidence(name),
    )
    return Result.succeeded(
        source, (ISSUE,), History(records=(record,), current_issue=ISSUE)
    )


def _failure(name: str) -> Result:
    return Result.failed(
        _source(name),
        (ISSUE,),
        Failure(ErrorCode.ISSUE_MISSING, detail="测试"),
    )


def _repo(tmp_path: Path) -> ReportRepository:
    return ReportRepository(
        tmp_path / "success",
        failure_dir=tmp_path / "failure",
        success_filename="{issue}期-生肖.txt",
        failure_filename="{issue}期-生肖-失败.txt",
    )


def test_write_issue_creates_failure_file_when_entries_exist(tmp_path) -> None:
    repo = _repo(tmp_path)
    _success_path, failure_path = repo.write_issue(
        ISSUE, (_success("成功站"), _failure("失败站"))
    )

    assert failure_path.exists()
    assert "失败站" in failure_path.read_text(encoding="utf-8")


def test_write_issue_removes_failure_file_when_all_succeed(tmp_path) -> None:
    repo = _repo(tmp_path)
    _success_path, failure_path = repo.write_issue(
        ISSUE, (_success("甲"), _success("乙"))
    )

    assert not failure_path.exists(), "失败清单为空时必须删除文件，不留空壳"


def test_merge_issue_removes_failure_file_when_last_entry_cleared(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.write_issue(ISSUE, (_success("成功站"), _failure("失败站")))
    _success_path, failure_path = repo._issue_paths(ISSUE)
    assert failure_path.exists()

    # 该站被救回后再合并一次：失败条目清零，文件必须消失
    repo.merge_issue(ISSUE, (_success("失败站"),))

    assert not failure_path.exists(), "最后一条失败清掉后必须删除文件"


def test_merge_issue_keeps_failure_file_when_entries_remain(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.write_issue(ISSUE, (_success("成功站"), _failure("甲"), _failure("乙")))
    _success_path, failure_path = repo._issue_paths(ISSUE)

    repo.merge_issue(ISSUE, (_success("甲"),))

    assert failure_path.exists()
    text = failure_path.read_text(encoding="utf-8")
    assert "乙" in text
    assert "甲" not in text


def test_merge_issue_does_not_create_empty_file(tmp_path) -> None:
    repo = _repo(tmp_path)
    _success_path, failure_path = repo._issue_paths(ISSUE)
    assert not failure_path.exists()

    repo.merge_issue(ISSUE, (_success("甲"),))

    assert not failure_path.exists(), "合并成功时不得凭空创建空失败文件"


def test_document_import_is_available() -> None:
    """占位断言：确保测试模块能正常加载 domain 模型。"""
    assert Document is not None
