from __future__ import annotations

import re
from pathlib import Path

from v2.domain.errors import ErrorCode, Failure
from v2.domain.identity import source_identity
from v2.domain.models import Result
from v2.storage.atomic import atomic_write_many, atomic_write_text


ERROR_MESSAGES = {
    ErrorCode.CONFIG_INVALID: "站点配置无效",
    ErrorCode.DUPLICATE_SOURCE: "站点重复",
    ErrorCode.FETCH_FAILED: "页面抓取失败",
    ErrorCode.HTTP_ERROR: "页面返回 HTTP 错误",
    ErrorCode.API_RECORD_MISMATCH: "动态文章记录不匹配",
    ErrorCode.ANCHOR_MISSING: "未找到目录关键字",
    ErrorCode.DIRECTION_INVALID: "顶部或尾部方向无效",
    ErrorCode.ISSUE_MISSING: "没有找到目标期记录",
    ErrorCode.LOCKED_CONTENT: "目标内容已锁定",
    ErrorCode.INVALID_ZODIAC_COUNT: "九肖数量或内容无效",
    ErrorCode.GROUP_EVIDENCE_MISSING: "分组原文证据缺失",
    ErrorCode.CANDIDATE_CONFLICT: "同站同期存在冲突结果",
    ErrorCode.BLOCK_AMBIGUOUS: "目标栏目存在多个无法唯一确定的区块",
    ErrorCode.DOCUMENT_CONFLICT: "不同文档来源存在冲突结果",
    ErrorCode.SOURCE_UNTRUSTED: "来源证据不可信",
    ErrorCode.CROSS_DOMAIN: "页面发生跨域跳转",
    ErrorCode.WRITE_FAILED: "正式文件写入失败",
    ErrorCode.INTERNAL_ERROR: "站点任务发生未预期异常",
}


FAILURE_STAGES = {
    ErrorCode.CONFIG_INVALID: "配置校验",
    ErrorCode.DUPLICATE_SOURCE: "站点身份校验",
    ErrorCode.FETCH_FAILED: "网络抓取",
    ErrorCode.HTTP_ERROR: "网络抓取",
    ErrorCode.API_RECORD_MISMATCH: "动态文章身份校验",
    ErrorCode.ANCHOR_MISSING: "栏目锚点校验",
    ErrorCode.DIRECTION_INVALID: "方向校验",
    ErrorCode.ISSUE_MISSING: "指定期数校验",
    ErrorCode.LOCKED_CONTENT: "内容状态校验",
    ErrorCode.INVALID_ZODIAC_COUNT: "数据数量校验",
    ErrorCode.GROUP_EVIDENCE_MISSING: "分组证据校验",
    ErrorCode.CANDIDATE_CONFLICT: "同期冲突校验",
    ErrorCode.BLOCK_AMBIGUOUS: "区块边界校验",
    ErrorCode.DOCUMENT_CONFLICT: "来源冲突校验",
    ErrorCode.SOURCE_UNTRUSTED: "来源可信度校验",
    ErrorCode.CROSS_DOMAIN: "跨域校验",
    ErrorCode.WRITE_FAILED: "文件写入",
    ErrorCode.INTERNAL_ERROR: "站点任务隔离",
}


def render_failure(failure: Failure) -> str:
    message = ERROR_MESSAGES[failure.code]
    detail = f"；{failure.detail}" if failure.detail else ""
    return f"{failure.code.value}：{message}{detail}"


def _failure_reason(failure: Failure) -> str:
    detail = " ".join(failure.detail.split())
    return detail or ERROR_MESSAGES[failure.code]


def _failure_stage(failure: Failure) -> str:
    return FAILURE_STAGES.get(failure.code, "结果校验")


def _failure_entry(issue: int, result: Result) -> str:
    failure = result.failures[0] if result.failures else None
    if failure is None:
        failure = Failure(ErrorCode.ISSUE_MISSING)
    return (
        f"失败 {result.source.name} {result.source.url} "
        f"方向: {result.source.position.value} 期数: {issue} "
        f"阶段: {_failure_stage(failure)} 原因: {_failure_reason(failure)}"
    )


class ReportRepository:
    def __init__(
        self,
        output_dir: Path,
        *,
        failure_dir: Path | None = None,
        success_filename: str = "{issue}.txt",
        failure_filename: str = "{issue}-failures.txt",
        range_failure_dir: Path | None = None,
        range_failure_filename: str = "range-failures.txt",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.failure_dir = Path(failure_dir or output_dir)
        self.success_filename = success_filename
        self.failure_filename = failure_filename
        self.range_failure_dir = Path(range_failure_dir or self.failure_dir)
        self.range_failure_filename = range_failure_filename

    def _issue_paths(self, issue: int) -> tuple[Path, Path]:
        try:
            success_name = self.success_filename.format(issue=issue)
            failure_name = self.failure_filename.format(issue=issue)
        except (KeyError, ValueError) as exc:
            raise ValueError("报告文件名模板无效") from exc
        if not success_name or not failure_name:
            raise ValueError("报告文件名不能为空")
        return self.output_dir / success_name, self.failure_dir / failure_name

    def write_issue(
        self,
        issue: int,
        results: tuple[Result, ...],
    ) -> tuple[Path, Path]:
        output_path, failure_path = self._issue_paths(issue)
        success_lines: list[str] = []
        failure_lines: list[str] = []
        for result in results:
            records = result.history.records_for(issue)
            if result.successful and len(records) == 1:
                success_lines.append(f"{records[0].zodiac_text} {result.source.name}")
                continue
            failure_lines.append(_failure_entry(issue, result))
        atomic_write_text(
            output_path,
            "\n".join(success_lines) + ("\n" if success_lines else ""),
        )
        atomic_write_text(
            failure_path,
            "\n\n".join(failure_lines) + ("\n" if failure_lines else ""),
        )
        return output_path, failure_path

    def merge_issue(
        self,
        issue: int,
        results: tuple[Result, ...],
    ) -> tuple[Path, Path]:
        """Merge one selected source scope into an existing issue report."""
        output_path, failure_path = self._issue_paths(issue)
        names = [result.source.name for result in results]
        if len(names) != len(set(names)):
            raise ValueError("duplicate report source name")

        success_lines = self._read_lines(output_path)
        failure_entries = self._read_failure_entries(failure_path)
        for result in results:
            name = result.source.name
            success_lines = [
                line for line in success_lines if self._success_name(line) != name
            ]
            failure_entries = [
                entry
                for entry in failure_entries
                if self._failure_name(entry) != name
            ]
            if result.successful:
                records = result.history.records_for(issue)
                if len(records) != 1:
                    raise ValueError("successful result must contain one issue record")
                success_lines.append(f"{records[0].zodiac_text} {name}")
            else:
                failure_entries.append(_failure_entry(issue, result))

        success_text = "\n".join(success_lines) + ("\n" if success_lines else "")
        failure_text = "\n\n".join(failure_entries) + (
            "\n" if failure_entries else ""
        )
        if output_path.parent.resolve() == failure_path.parent.resolve():
            atomic_write_many(
                {
                    output_path: success_text.encode("utf-8"),
                    failure_path: failure_text.encode("utf-8"),
                },
                self.output_dir / ".report-transaction.json",
            )
        else:
            atomic_write_text(output_path, success_text)
            atomic_write_text(failure_path, failure_text)
        return output_path, failure_path

    @staticmethod
    def _read_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        return list(path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def _read_failure_entries(path: Path) -> list[str]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return [entry for entry in text.split("\n\n") if entry]

    def failed_sources(self, issue: int, sources: tuple) -> tuple:
        """Resolve failed URLs only when the active source match is unique."""
        _success, failure_path = self._issue_paths(issue)
        entries = self._read_failure_entries(failure_path)
        failed_urls = tuple(
            dict.fromkeys(
                match.group(1)
                for entry in entries
                if (
                    match := re.search(
                        r"\s(https?://\S+)",
                        entry.splitlines()[0],
                    )
                )
            )
        )
        selected = []
        for url in failed_urls:
            matches = tuple(source for source in sources if source.url == url)
            if len(matches) > 1:
                names = ", ".join(source.name for source in matches)
                raise ValueError(
                    f"失败TXT URL无法唯一匹配活跃站点: {url} ({names})"
                )
            if len(matches) == 1:
                selected.append(matches[0])
        selected_ids = {source_identity(source).key for source in selected}
        return tuple(
            source
            for source in sources
            if source_identity(source).key in selected_ids
        )

    @staticmethod
    def _success_name(line: str) -> str:
        return line.rsplit(" ", 1)[-1] if " " in line else ""

    @staticmethod
    def _failure_name(entry: str) -> str:
        first_line = entry.splitlines()[0]
        if first_line.startswith("失败 "):
            body = first_line.removeprefix("失败 ")
            url_match = re.search(r"\shttps?://\S+", body)
            if url_match:
                return body[: url_match.start()].strip()
        return first_line.split("\t", 1)[0]

    def write_range_failures(
        self,
        issue_results: tuple[tuple[int, tuple[Result, ...]], ...],
    ) -> Path:
        if not issue_results:
            raise ValueError("issue_results cannot be empty")
        try:
            filename = self.range_failure_filename.format(
                start_issue=issue_results[0][0],
                end_issue=issue_results[-1][0],
            )
        except (KeyError, ValueError) as exc:
            raise ValueError("多期失败文件名模板无效") from exc
        if not filename:
            raise ValueError("多期失败文件名不能为空")
        path = self.range_failure_dir / filename
        failed_in_every_issue: set[str] | None = None
        for _issue, results in issue_results:
            failed = {
                source_identity(result.source).key
                for result in results
                if not result.successful
            }
            failed_in_every_issue = (
                failed
                if failed_in_every_issue is None
                else failed_in_every_issue & failed
            )
        failed_in_every_issue = failed_in_every_issue or set()
        sections: list[str] = []
        for issue, results in issue_results:
            failures = tuple(
                result
                for result in results
                if source_identity(result.source).key in failed_in_every_issue
            )
            if not failures:
                continue
            lines = [f"{issue}期"]
            for result in failures:
                lines.append(_failure_entry(issue, result))
            sections.append("\n".join(lines))
        atomic_write_text(
            path,
            "\n\n".join(sections) + ("\n" if sections else ""),
        )
        return path
