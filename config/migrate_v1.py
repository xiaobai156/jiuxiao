from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from v2.config.repository import ArchivedSource
from v2.config.schema import source_to_dict
from v2.domain.identity import source_identity
from v2.domain.models import Position, Source
from v2.storage.atomic import atomic_write_many


DEFAULT_OVERRIDES_PATH = Path(__file__).with_name("migration_overrides.json")
DEFAULT_GROUPED_SEMANTICS_PATH = Path(__file__).with_name(
    "grouped_source_semantics.json"
)
DEFAULT_COMPLEMENT_SEMANTICS_PATH = Path(__file__).with_name(
    "complement_source_semantics.json"
)
GROUP_CATEGORIES = (
    "琴棋书画",
    "梅兰菊竹",
    "东南西北",
    "春夏秋冬",
    "风雨雷电",
)


@dataclass(frozen=True, slots=True)
class MigrationBundle:
    active: tuple[Source, ...]
    archived: tuple[ArchivedSource, ...]


@dataclass(frozen=True, slots=True)
class SourceOverride:
    parser: str = ""
    position: Position | None = None
    group_category: str = ""
    section_marker: str = ""
    data_marker: str = ""


@dataclass(frozen=True, slots=True)
class MigrationOverrides:
    aliases: dict[str, tuple[str, ...]]
    sources: dict[str, SourceOverride]


def build_migration(
    active_path: Path,
    archived_path: Path,
    groups_path: Path,
    overrides_path: Path = DEFAULT_OVERRIDES_PATH,
) -> MigrationBundle:
    active_document = _load_json(active_path)
    archived_document = _load_json(archived_path)
    groups_document = _load_json(groups_path)
    overrides = _load_overrides(overrides_path)
    if not isinstance(active_document, list):
        raise ValueError("V1 active sources must be a JSON array")
    if not isinstance(archived_document, dict) or set(archived_document) != {
        "schema_version",
        "archived_at",
        "reason",
        "sources",
    }:
        raise ValueError("V1 archived source document is invalid")
    if archived_document["schema_version"] != 1:
        raise ValueError("V1 archived schema must be 1")
    raw_archived = archived_document["sources"]
    if not isinstance(raw_archived, list):
        raise ValueError("V1 archived sources must be a JSON array")
    groups = _group_mapping(groups_document)
    grouped_categories, grouped_mapping_overrides = _load_grouped_semantics(
        DEFAULT_GROUPED_SEMANTICS_PATH
    )
    complement_sources = _load_complement_semantics(
        DEFAULT_COMPLEMENT_SEMANTICS_PATH
    )
    if set(grouped_categories) & complement_sources:
        raise ValueError("source cannot use grouped and complement semantics")

    active = tuple(
        _migrate_source(
            item,
            groups,
            overrides,
            grouped_categories,
            grouped_mapping_overrides,
            complement_sources,
        )
        for item in active_document
    )
    archived_at = _required_text(
        archived_document["archived_at"],
        "archived_at",
    )
    reason = _required_text(archived_document["reason"], "reason")
    archived = tuple(
        ArchivedSource(
            source=_migrate_source(
                item,
                groups,
                overrides,
                grouped_categories,
                grouped_mapping_overrides,
                complement_sources,
            ),
            archived_at=archived_at,
            reason=reason,
        )
        for item in raw_archived
    )
    bundle = MigrationBundle(active, archived)
    _validate_bundle(bundle)
    return bundle


def migrate_files(
    bundle: MigrationBundle,
    active_path: Path,
    archived_path: Path,
) -> None:
    active_path = Path(active_path)
    archived_path = Path(archived_path)
    if active_path.parent.resolve() != archived_path.parent.resolve():
        raise ValueError("migration targets must share one directory")
    _validate_bundle(bundle)
    _assert_empty_or_missing(active_path, archived_path)
    payloads = {
        active_path: _encode(
            {
                "schema_version": 2,
                "sources": [source_to_dict(source) for source in bundle.active],
            }
        ),
        archived_path: _encode(
            {
                "schema_version": 2,
                "sources": [
                    {
                        "source": source_to_dict(entry.source),
                        "archived_at": entry.archived_at,
                        "reason": entry.reason,
                    }
                    for entry in bundle.archived
                ],
            }
        ),
    }
    atomic_write_many(
        payloads,
        active_path.parent / ".v1-migration-transaction.json",
    )


def _migrate_source(
    value: Any,
    groups: dict[str, str],
    overrides: MigrationOverrides,
    grouped_categories: dict[str, str],
    grouped_mapping_overrides: dict[str, dict[str, str]],
    complement_sources: set[str],
) -> Source:
    allowed = {
        "name",
        "url",
        "position",
        "section_marker",
        "api_url",
        "group_map",
        "detail_link_keyword",
    }
    if not isinstance(value, dict) or not {"name", "url", "position"} <= set(
        value
    ):
        raise ValueError("V1 source is invalid")
    if set(value) - allowed:
        raise ValueError("V1 source contains unknown fields")
    name = _required_text(value["name"], "name")
    url = _required_text(value["url"], "url")
    override = overrides.sources.get(name, SourceOverride())
    grouped_category = grouped_categories.get(name, "")
    position = override.position or _position(value["position"])
    section_marker = override.section_marker or _optional_text(
        value.get("section_marker", "")
    )
    group_map = _source_group_map(
        value.get("group_map", {}),
        section_marker,
        override.group_category or grouped_category,
        groups,
        grouped_mapping_overrides.get(name, {}),
    )
    fetcher = _fetcher_for(url, value.get("detail_link_keyword", ""))
    parser = override.parser or (
        "profile_history"
        if "#/users/" in url
        else "grouped"
        if group_map
        else "complement_three"
        if name in complement_sources
        else "direct_nine"
    )
    if name in complement_sources and parser != "complement_three":
        raise ValueError(f"complement source parser conflict: {name}")
    return Source(
        name=name,
        url=url,
        position=position,
        section_marker=section_marker,
        fetcher=fetcher,
        parser=parser,
        api_url=_optional_text(value.get("api_url", "")),
        group_map=tuple(group_map.items()),
        detail_link_keyword=_optional_text(
            value.get("detail_link_keyword", "")
        ),
        aliases=overrides.aliases.get(name, ()),
        data_marker=(
            override.data_marker
            or override.group_category
            or grouped_category
            or ("绝杀三肖" if name in complement_sources else "")
        ),
    )


def _load_grouped_semantics(
    path: Path,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    document = _load_json(path)
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or set(document)
        != {"schema_version", "categories", "mapping_overrides"}
        or not isinstance(document["categories"], dict)
        or not isinstance(document["mapping_overrides"], dict)
    ):
        raise ValueError("grouped source semantics are invalid")
    result: dict[str, str] = {}
    for category, raw_names in document["categories"].items():
        if category not in GROUP_CATEGORIES or not isinstance(raw_names, list):
            raise ValueError("grouped source category is invalid")
        for raw_name in raw_names:
            name = _required_text(raw_name, "grouped source")
            if name in result:
                raise ValueError(f"duplicate grouped source: {name}")
            result[name] = category
    mapping_overrides: dict[str, dict[str, str]] = {}
    for raw_name, raw_mapping in document["mapping_overrides"].items():
        name = _required_text(raw_name, "group mapping source")
        category = result.get(name, "")
        if (
            not category
            or not isinstance(raw_mapping, dict)
            or tuple(raw_mapping) != tuple(category)
        ):
            raise ValueError(f"invalid grouped source mapping: {name}")
        mapping_overrides[name] = {
            _required_text(key, "group key"): _required_text(
                value,
                "group value",
            )
            for key, value in raw_mapping.items()
        }
    return result, mapping_overrides


def _load_complement_semantics(path: Path) -> set[str]:
    document = _load_json(path)
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "data_marker", "sources"}
        or document.get("schema_version") != 1
        or document.get("data_marker") != "绝杀三肖"
        or not isinstance(document.get("sources"), list)
    ):
        raise ValueError("complement source semantics are invalid")
    result: set[str] = set()
    for raw_name in document["sources"]:
        name = _required_text(raw_name, "complement source")
        if name in result:
            raise ValueError(f"duplicate complement source: {name}")
        result.add(name)
    return result


def _fetcher_for(url: str, detail_link_keyword: Any) -> str:
    if _optional_text(detail_link_keyword):
        return "list_detail"
    if any(
        marker in url
        for marker in (
            "/article/admin/",
            "/article/manager/",
            "/article/lottery/",
        )
    ):
        return "dynamic_article"
    return "browser_page"


def _source_group_map(
    raw_mapping: Any,
    section_marker: str,
    override_category: str,
    groups: dict[str, str],
    mapping_override: dict[str, str],
) -> dict[str, str]:
    if not isinstance(raw_mapping, dict):
        raise ValueError("V1 group_map must be an object")
    if raw_mapping:
        raw_result = {
            _required_text(key, "group key"): _required_text(value, "group value")
            for key, value in raw_mapping.items()
        }
        if mapping_override and raw_result != mapping_override:
            raise ValueError("V1 group map conflicts with grouped semantics")
        return raw_result
    if mapping_override:
        return dict(mapping_override)
    category = override_category or next(
        (
            candidate
            for candidate in GROUP_CATEGORIES
            if candidate in section_marker
        ),
        "",
    )
    if not category:
        return {}
    if any(character not in groups for character in category):
        raise ValueError(f"group category is incomplete: {category}")
    return {character: groups[character] for character in category}


def _load_overrides(path: Path) -> MigrationOverrides:
    document = _load_json(path)
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "aliases",
        "sources",
    }:
        raise ValueError("migration overrides are invalid")
    if document["schema_version"] != 1:
        raise ValueError("migration override schema must be 1")
    raw_aliases = document["aliases"]
    raw_sources = document["sources"]
    if not isinstance(raw_aliases, dict) or not isinstance(raw_sources, dict):
        raise ValueError("migration override mappings are invalid")
    aliases: dict[str, tuple[str, ...]] = {}
    for name, values in raw_aliases.items():
        if not isinstance(values, list):
            raise ValueError("migration aliases must be arrays")
        aliases[_required_text(name, "alias source")] = tuple(
            _required_text(value, "alias") for value in values
        )
    sources: dict[str, SourceOverride] = {}
    for name, value in raw_sources.items():
        if not isinstance(value, dict) or set(value) - {
            "parser",
            "position",
            "group_category",
            "section_marker",
            "data_marker",
        }:
            raise ValueError("migration source override is invalid")
        raw_position = value.get("position")
        sources[_required_text(name, "override source")] = SourceOverride(
            parser=_optional_text(value.get("parser", "")),
            position=(Position(raw_position) if raw_position is not None else None),
            group_category=_optional_text(value.get("group_category", "")),
            section_marker=_optional_text(value.get("section_marker", "")),
            data_marker=_optional_text(value.get("data_marker", "")),
        )
    return MigrationOverrides(aliases, sources)


def _validate_bundle(bundle: MigrationBundle) -> None:
    sources = (
        *bundle.active,
        *(entry.source for entry in bundle.archived),
    )
    names: set[str] = set()
    identities: set[str] = set()
    by_url: dict[str, list[Source]] = {}
    for source in sources:
        identity = source_identity(source)
        if source.name in names or identity.key in identities:
            raise ValueError(f"duplicate migrated source: {source.name}")
        for existing in by_url.get(identity.normalized_url, []):
            if (
                not source.section_marker
                or not existing.section_marker
                or source.section_marker == existing.section_marker
            ):
                raise ValueError(f"ambiguous shared URL: {source.name}")
        names.add(source.name)
        identities.add(identity.key)
        by_url.setdefault(identity.normalized_url, []).append(source)


def _assert_empty_or_missing(active_path: Path, archived_path: Path) -> None:
    if active_path.exists() != archived_path.exists():
        raise FileExistsError("migration targets must both exist or both be missing")
    if not active_path.exists():
        return
    for path in (active_path, archived_path):
        document = _load_json(path)
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 2
            or document.get("sources") != []
            or set(document) != {"schema_version", "sources"}
        ):
            raise FileExistsError(f"migration target is not empty: {path.name}")


def _group_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("V1 zodiac groups must be an object")
    return {
        _required_text(key, "group key"): _required_text(item, "group value")
        for key, item in value.items()
    }


def _position(value: Any) -> Position:
    mapping = {"顶部": Position.TOP, "尾部": Position.BOTTOM}
    if value not in mapping:
        raise ValueError(f"invalid V1 position: {value}")
    return mapping[value]


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _optional_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("optional value must be text")
    return value.strip()


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _encode(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
