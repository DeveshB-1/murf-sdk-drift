"""Compare the published specs with the SDK surface and emit findings."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .sdk_scan import SdkModel, SdkSurface
from .spec import Channel, Operation, Resolver

SEVERITY_ORDER = {"error": 2, "warn": 1, "info": 0}


@dataclass(frozen=True)
class Finding:
    severity: str  # error: spec has it, SDK can't send/parse it. warn: SDK has something the spec dropped.
    kind: str
    where: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _canon(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def diff_rest(ops: list[Operation], sdk: SdkSurface) -> list[Finding]:
    out: list[Finding] = []
    spec_keys = set()
    for op in ops:
        spec_keys.add(op.key)
        where = f"{op.method} {op.path}"
        out += _casing_finding(where, op.body)
        call = sdk.calls.get(op.key)
        if call is None:
            out.append(Finding("error", "missing-operation", where, "in the spec, no SDK method calls it"))
            continue
        if call.opaque_body:
            out.append(Finding("info", "opaque-body", where, "SDK passes the body as a variable; fields not checked"))
        else:
            for f in sorted(op.body - call.body):
                out.append(Finding("error", "missing-field", where, f"body field `{f}` is in the spec, SDK never sends it"))
            for f in sorted(call.body - op.body):
                out.append(Finding("warn", "stale-field", where, f"SDK sends body field `{f}`, spec does not list it"))
        for q in sorted(op.query - call.query):
            out.append(Finding("error", "missing-field", where, f"query param `{q}` is in the spec, SDK never sends it"))
        for q in sorted(call.query - op.query):
            out.append(Finding("warn", "stale-field", where, f"SDK sends query param `{q}`, spec does not list it"))
        for h in sorted(op.headers - call.headers):
            out.append(Finding("error", "missing-field", where, f"header `{h}` is in the spec, SDK never sends it"))
    for key, call in sorted(sdk.calls.items()):
        if key not in spec_keys:
            out.append(Finding("warn", "stale-operation", f"{call.method} /{call.path.lstrip('/')}",
                               "SDK calls it, spec does not list it"))
    return out


def _referenced_models(annotation: str, models: dict[str, SdkModel]) -> list[SdkModel]:
    return [models[n] for n in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", annotation) if n in models]


def mixed_casing(names) -> tuple[list[str], list[str]]:
    """Split names into snake_case and camelCase; both non-empty means one object mixes conventions."""
    snake = sorted(n for n in names if "_" in n)
    camel = sorted(n for n in names if "_" not in n and re.search(r"[a-z][A-Z]", n))
    return snake, camel


def _casing_finding(where: str, names) -> list[Finding]:
    snake, camel = mixed_casing(names)
    if snake and camel:
        return [Finding("info", "spec-mixed-casing", where,
                        f"spec mixes camelCase ({', '.join(camel)}) with snake_case ({', '.join(snake[:3])}...) in one object")]
    return []


def _diff_model(where: str, spec_fields: dict, model: SdkModel, sdk: SdkSurface, r: Resolver,
                depth: int = 0) -> list[Finding]:
    out: list[Finding] = _casing_finding(where, spec_fields)
    for f in sorted(set(spec_fields) - set(model.fields)):
        out.append(Finding("error", "ws-missing-field", f"{where}", f"field `{f}` is in the spec, missing from SDK model {model.name}"))
    for f in sorted(set(model.fields) - set(spec_fields)):
        out.append(Finding("warn", "ws-stale-field", f"{where}", f"SDK model {model.name} has `{f}`, spec does not list it"))
    if depth >= 4:
        return out
    for f in sorted(set(spec_fields) & set(model.fields)):
        sub_spec = r.object_fields(spec_fields[f])
        subs = _referenced_models(model.fields[f], sdk.models)
        if sub_spec and subs:
            out += _diff_model(f"{where}.{f}", sub_spec, subs[0], sdk, r, depth + 1)
    return out


def diff_ws(channels: list[Channel], r: Resolver, sdk: SdkSurface) -> list[Finding]:
    out: list[Finding] = []
    by_canon = {_canon(n): m for n, m in sdk.models.items()}
    for ch in channels:
        matched = [(msg, by_canon.get(_canon(msg.name))) for msg in ch.messages]
        if not any(m for _, m in matched):
            names = ", ".join(msg.name for msg in ch.messages)
            out.append(Finding("error", "ws-missing-channel", ch.name, f"no SDK types for any message on this channel ({names})"))
            continue
        for msg, model in matched:
            where = f"WS {ch.name} {msg.name}"
            if model is None:
                out.append(Finding("error", "ws-missing-message", where, "message type is in the spec, SDK has no model for it"))
                continue
            out += _diff_model(where, r.object_fields(msg.schema), model, sdk, r)
    if channels and not sdk.has_ws_client:
        q = "; ".join(f"{c.name}: {', '.join(sorted(c.query)) or '-'}" for c in channels)
        out.append(Finding("warn", "ws-no-client", "SDK", "SDK ships WebSocket message types but no connect helper, "
                           f"so callers hand-build URLs and query params ({q})"))
    return out


def worst(findings: list[Finding]) -> str | None:
    if not findings:
        return None
    return max(findings, key=lambda f: SEVERITY_ORDER[f.severity]).severity
