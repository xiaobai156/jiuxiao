from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.domain.errors import Failure, ErrorCode
from v2.domain.models import Evidence, History, Position, Record, Result, Source
from v2.services.cache_sync import CacheSyncService
from v2.storage.cache import CacheRepository
from v2.storage.reports import ReportRepository


def source(name: str, position: Position = Position.TOP) -> Source:
    return Source(
        name=name,
        url=f"https://example.test/{name}",
        position=position,
        section_marker=name,
        fetcher="browser_page",
        parser="direct_nine",
    )


def result(item: Source, issue: int, zodiac: str) -> Result:
    record = Record(
        issue=issue,
        zodiacs=tuple(zodiac),
        evidence=Evidence(
            method="test",
            source_line=f"{issue}期 九肖【{zodiac}】",
            directory_anchor=item.name,
            document_label="test",
            document_url=item.url,
            document_method="browser_dom",
            actual_anchor_line=item.name,
            anchor_index=0,
            anchor_occurrence=1,
            block_id="test-block",
            block_start=0,
            block_end=1,
            candidate_index_in_block=0,
            parser_id=item.parser,
            raw_issue_line=f"{issue}期",
            raw_zodiac_line=zodiac,
            data_marker="九肖",
            metadata=(
                ("document_index", "0"),
                ("line_index", "0"),
            ),
        ),
    )
    return Result.succeeded(item, (issue,), History((record,), issue))


class ScopedStorageTests(unittest.TestCase):
    def test_report_write_uses_split_dynamic_output_contract(self) -> None:
        first = source("甲")
        second = source("乙", Position.BOTTOM)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            success_dir = root / "success"
            failure_dir = root / "failure"
            repository = ReportRepository(
                success_dir,
                failure_dir=failure_dir,
                success_filename="{issue}期-生肖.txt",
                failure_filename="{issue}期-生肖-失败.txt",
            )

            output_path, failure_path = repository.write_issue(
                213,
                (
                    result(first, 213, "鼠牛虎兔龙蛇马羊猴"),
                    Result.failed(
                        second,
                        (213,),
                        Failure(
                            ErrorCode.ISSUE_MISSING,
                            detail="213期不是最后一条专属历史边界行",
                        ),
                    ),
                ),
            )

            self.assertEqual(
                output_path,
                success_dir / "213期-生肖.txt",
            )
            self.assertEqual(
                failure_path,
                failure_dir / "213期-生肖-失败.txt",
            )
            self.assertIn("鼠牛虎兔龙蛇马羊猴 甲", output_path.read_text("utf-8"))
            self.assertEqual(
                failure_path.read_text("utf-8"),
                "失败 乙 https://example.test/乙 方向: bottom 期数: 213 "
                "阶段: 指定期数校验 原因: 213期不是最后一条专属历史边界行\n",
            )
            self.assertFalse((root / "outputs").exists())

    def test_report_merge_preserves_unselected_sources(self) -> None:
        first = source("甲")
        second = source("乙")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "213.txt"
            failures = root / "213-failures.txt"
            output.write_text("旧数据 丙\n旧数据 甲\n", encoding="utf-8")
            failures.write_text(
                "乙\thttps://example.test/乙\tISSUE_MISSING：没有找到目标期记录\n",
                encoding="utf-8",
            )

            ReportRepository(root).merge_issue(
                213,
                (
                    result(first, 213, "鼠牛虎兔龙蛇马羊猴"),
                    Result.failed(
                        second,
                        (213,),
                        Failure(ErrorCode.ANCHOR_MISSING),
                    ),
                ),
            )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "旧数据 丙\n鼠牛虎兔龙蛇马羊猴 甲\n",
            )
            failure_text = failures.read_text(encoding="utf-8")
            self.assertIn(
                "失败 乙 https://example.test/乙 方向: top 期数: 213 "
                "阶段: 栏目锚点校验 原因: 未找到目录关键字",
                failure_text,
            )
            self.assertNotIn("甲\t", failure_text)

    def test_cache_selected_sync_preserves_unselected_sources(self) -> None:
        first = source("甲")
        second = source("乙")
        third = source("丙")
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = CacheRepository(Path(temp_dir) / "cache.json")
            service = CacheSyncService(repository)
            service.sync_single(
                (first, second, third),
                tuple(
                    result(item, 212, "鼠牛虎兔龙蛇马羊猴")
                    for item in (first, second, third)
                ),
                212,
            )

            snapshot = service.sync_selected_single(
                (first,),
                (result(first, 213, "牛虎兔龙蛇马羊猴鸡"),),
                213,
            )

            by_name = {item.source.name: item for item in snapshot.sources}
            self.assertEqual(
                dict(by_name["甲"].records)[213],
                "牛虎兔龙蛇马羊猴鸡",
            )
            self.assertEqual(
                dict(by_name["乙"].records)[212],
                "鼠牛虎兔龙蛇马羊猴",
            )
            self.assertEqual(
                dict(by_name["丙"].records)[212],
                "鼠牛虎兔龙蛇马羊猴",
            )


if __name__ == "__main__":
    unittest.main()
