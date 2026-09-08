from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from v2.domain.models import Position, Source


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    name: str
    normalized_url: str
    position: Position
    section_marker: str
    config_fingerprint: str

    @property
    def key(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "url": self.normalized_url,
                "position": self.position.value,
                "section_marker": self.section_marker,
                "config_fingerprint": self.config_fingerprint,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def normalize_url(value: str) -> str:
    raw = str(value).strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL 必须是有效的 HTTP(S) 地址")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL 不允许包含认证信息")

    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(parse_qsl(parsed.query, keep_blank_values=True)),
        doseq=True,
    )
    fragment = parsed.fragment.strip()
    route_fragment = (
        fragment.rstrip("/")
        if fragment.startswith(("/", "!/"))
        else ""
    )
    return urlunsplit((scheme, netloc, path, query, route_fragment))


def source_identity(source: Source) -> SourceIdentity:
    configuration = json.dumps(
        {
            "fetcher": source.fetcher,
            "parser": source.parser,
            "api_url": source.api_url,
            "group_map": source.group_map,
            "detail_link_keyword": source.detail_link_keyword,
            "aliases": source.aliases,
            "data_marker": source.data_marker,
            "source_policy": source.source_policy,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return SourceIdentity(
        name=source.name.strip(),
        normalized_url=normalize_url(source.url),
        position=source.position,
        section_marker=source.section_marker.strip(),
        config_fingerprint=hashlib.sha256(configuration).hexdigest(),
    )
