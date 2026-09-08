from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2.storage.atomic import atomic_write_bytes


GROUP_MAPS = {
    "琴棋书画": {
        "琴": "兔蛇鸡",
        "棋": "鼠牛狗",
        "书": "虎龙马",
        "画": "羊猴猪",
    },
    "春夏秋冬": {
        "春": "虎兔龙",
        "夏": "蛇马羊",
        "秋": "猴鸡狗",
        "冬": "鼠牛猪",
    },
    "风雨雷电": {
        "风": "虎兔龙",
        "雨": "蛇羊马",
        "雷": "猴狗鸡",
        "电": "鼠牛猪",
    },
    "梅兰菊竹": {
        "梅": "鼠龙猴",
        "兰": "兔羊猪",
        "菊": "牛蛇鸡",
        "竹": "虎马狗",
    },
    "东南西北": {
        "东": "兔虎龙",
        "南": "马蛇羊",
        "西": "鸡猴狗",
        "北": "鼠猪牛",
    },
}
ZODIACS = set("鼠牛虎兔龙蛇马羊猴鸡狗猪")


def apply_grouped_semantics(
    sources_path: Path,
    semantics_path: Path,
) -> tuple[str, ...]:
    sources_document = json.loads(sources_path.read_text(encoding="utf-8"))
    semantics_document = json.loads(
        semantics_path.read_text(encoding="utf-8")
    )
    if (
        semantics_document.get("schema_version") != 1
        or set(semantics_document)
        != {"schema_version", "categories", "mapping_overrides"}
        or set(semantics_document.get("categories", {})) != set(GROUP_MAPS)
        or not isinstance(semantics_document.get("mapping_overrides"), dict)
    ):
        raise ValueError("invalid grouped source semantics")
    mapping_overrides = semantics_document["mapping_overrides"]
    by_name = {
        str(item["name"]): item for item in sources_document["sources"]
    }
    changed: list[str] = []
    seen: set[str] = set()
    for category, names in semantics_document["categories"].items():
        if not isinstance(names, list):
            raise ValueError("grouped source names must be arrays")
        for raw_name in names:
            name = str(raw_name).strip()
            if not name or name in seen or name not in by_name:
                raise ValueError(f"invalid grouped source: {name}")
            seen.add(name)
            item = by_name[name]
            parser = str(item.get("parser", ""))
            if parser == "profile_history":
                pass
            elif parser in {"direct_nine", "grouped"}:
                item["parser"] = "grouped"
            elif parser in {"topic_cyclic_nine", "dynamic_article_grouped"}:
                pass
            else:
                raise ValueError(f"unsupported grouped parser: {name}")
            mapping = mapping_overrides.get(name, GROUP_MAPS[category])
            if (
                not isinstance(mapping, dict)
                or tuple(mapping) != tuple(category)
                or any(
                    not isinstance(value, str) or len(value) != 3
                    for value in mapping.values()
                )
                or set("".join(mapping.values())) != ZODIACS
            ):
                raise ValueError(f"invalid grouped source mapping: {name}")
            item["group_map"] = mapping
            item["data_marker"] = category
            changed.append(name)
    if set(mapping_overrides) - seen:
        raise ValueError("group mapping override is not a grouped source")
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
        default=root / "grouped_source_semantics.json",
    )
    args = parser.parse_args()
    changed = apply_grouped_semantics(args.sources, args.semantics)
    print(f"grouped_sources={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
