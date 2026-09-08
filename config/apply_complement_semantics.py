from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2.storage.atomic import atomic_write_bytes


DATA_MARKER = "绝杀三肖"


def apply_complement_semantics(
    sources_path: Path,
    semantics_path: Path,
) -> tuple[str, ...]:
    sources_document = json.loads(sources_path.read_text(encoding="utf-8"))
    semantics_document = json.loads(
        semantics_path.read_text(encoding="utf-8")
    )
    if (
        not isinstance(semantics_document, dict)
        or set(semantics_document)
        != {"schema_version", "data_marker", "sources"}
        or semantics_document.get("schema_version") != 1
        or semantics_document.get("data_marker") != DATA_MARKER
        or not isinstance(semantics_document.get("sources"), list)
    ):
        raise ValueError("invalid complement source semantics")

    by_name = {
        str(item["name"]): item for item in sources_document["sources"]
    }
    changed: list[str] = []
    seen: set[str] = set()
    for raw_name in semantics_document["sources"]:
        name = str(raw_name).strip()
        if not name or name in seen or name not in by_name:
            raise ValueError(f"invalid complement source: {name}")
        seen.add(name)
        item = by_name[name]
        if item.get("parser") not in {"direct_nine", "complement_three"}:
            raise ValueError(f"unsupported complement parser: {name}")
        if item.get("group_map"):
            raise ValueError(f"complement source has group mapping: {name}")
        item["parser"] = "complement_three"
        item["data_marker"] = DATA_MARKER
        changed.append(name)

    payload = (
        json.dumps(sources_document, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(sources_path, payload)
    return tuple(changed)


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=root / "sources.json")
    parser.add_argument(
        "--semantics",
        type=Path,
        default=root / "complement_source_semantics.json",
    )
    args = parser.parse_args()
    changed = apply_complement_semantics(args.sources, args.semantics)
    print(f"complement_sources={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
