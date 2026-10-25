"""Read Murf's published OpenAPI (REST) and AsyncAPI (WebSocket) specs.

Only what the drift check needs is extracted: for each REST operation the
wire names a client can send, and for each WebSocket channel the message
schemas (and their nested object fields).
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

OPENAPI_URL = "https://murf.ai/api/docs/openapi.json"
ASYNCAPI_URL = "https://murf.ai/api/docs/asyncapi.json"

# Sent by the SDK's client wrapper on every request, never per-method.
AUTH_HEADERS = {"api-key"}


def load(source: str) -> dict:
    """Load a JSON spec from an http(s) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "murf-sdk-drift"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def norm_path(path: str) -> str:
    """`/v1/a/{voiceId}/b` and `v1/a/{x}/b` both become `/v1/a/{}/b`."""
    path = "/" + path.lstrip("/")
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/") or "/"


class Resolver:
    def __init__(self, doc: dict):
        self.doc = doc

    def deref(self, schema: dict | None, _depth: int = 0) -> dict:
        """Follow local $refs and flatten allOf / nullable anyOf into one object schema."""
        if not isinstance(schema, dict) or _depth > 20:
            return {}
        if "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                return {}
            node = self.doc
            for part in ref[2:].split("/"):
                node = node.get(part, {}) if isinstance(node, dict) else {}
            return self.deref(node, _depth + 1)
        if "allOf" in schema:
            merged: dict = {"type": "object", "properties": {}, "required": []}
            for sub in schema["allOf"]:
                s = self.deref(sub, _depth + 1)
                merged["properties"].update(s.get("properties", {}))
                merged["required"] += s.get("required", [])
            return merged
        for key in ("anyOf", "oneOf"):
            # `anyOf: [X, {type: null}]` is how optional nested objects are written.
            members = [m for m in schema.get(key, []) if m.get("type") != "null"]
            if key in schema and len(members) == 1:
                return self.deref(members[0], _depth + 1)
        return schema

    def follow(self, schema: dict) -> dict:
        """Follow $refs only. Unlike deref, a one-member oneOf stays a union."""
        seen = 0
        while isinstance(schema, dict) and "$ref" in schema and seen < 20:
            node = self.doc
            for part in schema["$ref"][2:].split("/"):
                node = node.get(part, {}) if isinstance(node, dict) else {}
            schema, seen = node, seen + 1
        return schema if isinstance(schema, dict) else {}

    def object_fields(self, schema: dict | None) -> dict[str, dict]:
        """Properties of an object schema; for maps and arrays, of the value/item schema."""
        s = self.deref(schema)
        if s.get("properties"):
            return s["properties"]
        for inner in (s.get("additionalProperties"), s.get("items")):
            if isinstance(inner, dict):
                inner_s = self.deref(inner)
                if inner_s.get("properties"):
                    return inner_s["properties"]
        return {}


@dataclass
class Operation:
    method: str
    path: str  # as written in the spec
    body: set[str] = field(default_factory=set)
    query: set[str] = field(default_factory=set)
    headers: set[str] = field(default_factory=set)
    required: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, str]:
        return (self.method.upper(), norm_path(self.path))


def rest_operations(doc: dict) -> list[Operation]:
    r = Resolver(doc)
    ops: list[Operation] = []
    for path, item in doc.get("paths", {}).items():
        for method, op in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            o = Operation(method=method.upper(), path=path)
            for p in op.get("parameters", []):
                p = r.deref(p)
                where, name = p.get("in"), p.get("name")
                if where == "query":
                    o.query.add(name)
                elif where == "header" and name.lower() not in AUTH_HEADERS:
                    o.headers.add(name)
            for content in op.get("requestBody", {}).get("content", {}).values():
                s = r.deref(content.get("schema"))
                o.body |= set(s.get("properties", {}))
                o.required |= set(s.get("required", []))
            ops.append(o)
    return ops


@dataclass
class Message:
    channel: str
    name: str
    schema: dict


@dataclass
class Channel:
    name: str
    query: set[str]
    messages: list[Message]


def ws_channels(doc: dict) -> tuple[list[Channel], Resolver]:
    r = Resolver(doc)
    out: list[Channel] = []
    for cname, ch in doc.get("channels", {}).items():
        msgs: list[Message] = []
        for direction in ("publish", "subscribe"):
            payload = ch.get(direction, {}).get("message", {}).get("payload", {})
            payload_s = r.follow(payload)
            members = payload_s.get("oneOf") or payload_s.get("anyOf") or [payload]
            for m in members:
                name = m["$ref"].rsplit("/", 1)[-1] if "$ref" in m else r.deref(m).get("title", "?")
                msgs.append(Message(channel=cname, name=name, schema=m))
        query = set(ch.get("bindings", {}).get("ws", {}).get("query", {}).get("properties", {}))
        query.discard("api_key")
        out.append(Channel(name=cname, query=query, messages=msgs))
    return out, r
