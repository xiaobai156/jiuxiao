from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from v2.domain.errors import ErrorCode
from v2.domain.models import Position, Source


SOURCE_FIELDS = {
    "name",
    "url",
    "position",
    "section_marker",
    "fetcher",
    "parser",
    "api_url",
    "group_map",
    "detail_link_keyword",
    "aliases",
    "data_marker",
    "source_policy",
}
REQUIRED_SOURCE_FIELDS = {"name", "url", "position", "fetcher", "parser"}


class ConfigValidationError(ValueError):
    code = ErrorCode.CONFIG_INVALID


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigValidationError(f"{field_name} 必须是字符串")
    return value.strip()


def source_from_dict(value: Any) -> Source:
    if not isinstance(value, Mapping):
        raise ConfigValidationError("source 必须是 JSON 对象")
    fields = set(value)
    missing = REQUIRED_SOURCE_FIELDS - fields
    unknown = fields - SOURCE_FIELDS
    if missing:
        raise ConfigValidationError(
            f"source 缺少字段: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ConfigValidationError(
            f"source 包含未知字段: {', '.join(sorted(unknown))}"
        )

    try:
        position = Position(value["position"])
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError("position 只接受 top 或 bottom") from exc

    raw_group_map = value.get("group_map", {})
    if not isinstance(raw_group_map, Mapping):
        raise ConfigValidationError("group_map 必须是 JSON 对象")
    group_map = tuple(
        (
            _required_string(key, "group_map key"),
            _required_string(item, "group_map value"),
        )
        for key, item in raw_group_map.items()
    )

    raw_aliases = value.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raise ConfigValidationError("aliases 必须是 JSON 数组")
    aliases = tuple(
        _required_string(alias, "alias") for alias in raw_aliases
    )
    raw_source_policy = value.get("source_policy", [])
    if not isinstance(raw_source_policy, list):
        raise ConfigValidationError("source_policy 必须是 JSON 数组")
    source_policy = tuple(
        _required_string(method, "source_policy method")
        for method in raw_source_policy
    )

    try:
        return Source(
            name=_required_string(value["name"], "name"),
            url=_required_string(value["url"], "url"),
            position=position,
            section_marker=_optional_string(
                value.get("section_marker", ""),
                "section_marker",
            ),
            fetcher=_required_string(value["fetcher"], "fetcher"),
            parser=_required_string(value["parser"], "parser"),
            api_url=_optional_string(value.get("api_url", ""), "api_url"),
            group_map=group_map,
            detail_link_keyword=_optional_string(
                value.get("detail_link_keyword", ""),
                "detail_link_keyword",
            ),
            aliases=aliases,
            data_marker=_optional_string(
                value.get("data_marker", ""),
                "data_marker",
            ),
            source_policy=source_policy,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(str(exc)) from exc


def source_to_dict(source: Source) -> dict[str, Any]:
    return {
        "name": source.name,
        "url": source.url,
        "position": source.position.value,
        "section_marker": source.section_marker,
        "fetcher": source.fetcher,
        "parser": source.parser,
        "api_url": source.api_url,
        "group_map": dict(source.group_map),
        "detail_link_keyword": source.detail_link_keyword,
        "aliases": list(source.aliases),
        "data_marker": source.data_marker,
        "source_policy": list(source.source_policy),
    }
