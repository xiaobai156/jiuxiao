from __future__ import annotations

import argparse
from pathlib import Path

from v2.services.golden import GoldenComparator
from v2.storage.golden import GoldenReportRepository, GoldenRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _review_path(project_root: Path, path: Path) -> Path:
    reviews = (project_root / "v2" / "reviews").resolve()
    resolved = path.resolve()
    if resolved.parent != reviews:
        raise ValueError("golden files must be directly inside v2/reviews")
    return resolved


def main() -> None:
    args = parse_args()
    root = args.project_root.resolve()
    expected_path = _review_path(root, args.expected)
    actual_path = _review_path(root, args.actual)
    output_path = _review_path(root, args.output)
    expected = GoldenRepository(expected_path).load()
    actual = GoldenRepository(actual_path).load()
    report = GoldenComparator().compare(expected, actual)
    GoldenReportRepository(output_path).write(report)
    print(f"differences={len(report.differences)}")


if __name__ == "__main__":
    main()
