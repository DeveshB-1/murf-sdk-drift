"""Read what the Fern-generated Murf Python SDK can actually send.

The SDK is parsed with `ast`, never imported, so this works on an installed
wheel or on a source checkout of murf-ai/murf-python-sdk, without pydantic or
an API key. Fern writes every request as

    self._client_wrapper.httpx_client.request(
        "v1/speech/generate", method="POST", json={"voiceId": voice_id, ...})

so the wire names are string literals we can read directly.
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from .spec import norm_path

IGNORED_HEADERS = {"content-type", "accept", "api-key"}
REQUEST_FUNCS = {"request", "stream"}
PAYLOAD_KWARGS = ("json", "data", "files")


@dataclass
class SdkCall:
    method: str
    path: str
    body: set[str] = field(default_factory=set)
    query: set[str] = field(default_factory=set)
    headers: set[str] = field(default_factory=set)
    opaque_body: bool = False  # body passed as a variable, keys unknown
    files: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, str]:
        return (self.method.upper(), norm_path(self.path))


@dataclass
class SdkModel:
    name: str
    fields: dict[str, str]  # wire name -> annotation source
    file: str


@dataclass
class SdkSurface:
    root: Path
    version: str | None
    calls: dict[tuple[str, str], SdkCall]
    models: dict[str, SdkModel]
    has_ws_client: bool


def locate_installed(package: str = "murf") -> tuple[Path, str | None]:
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise FileNotFoundError(f"package {package!r} is not installed; pass --sdk PATH")
    try:
        version = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return Path(next(iter(spec.submodule_search_locations))), version


def _path_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def _dict_keys(node: ast.AST) -> set[str] | None:
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return None


def _scan_calls(tree: ast.AST, calls: dict[tuple[str, str], SdkCall]) -> None:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in REQUEST_FUNCS or not node.args:
            continue
        path = _path_literal(node.args[0])
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        method_node = kw.get("method")
        if not path or not isinstance(method_node, ast.Constant):
            continue
        call = SdkCall(method=str(method_node.value).upper(), path=path)
        call = calls.setdefault(call.key, call)  # sync + async clients merge
        for name in PAYLOAD_KWARGS:
            if name not in kw or (isinstance(kw[name], ast.Constant) and kw[name].value is None):
                continue
            keys = _dict_keys(kw[name])
            if keys is None:
                call.opaque_body = True
            elif name == "files":
                call.files |= keys
                call.body |= keys
            else:
                call.body |= keys
        if "params" in kw:
            call.query |= _dict_keys(kw["params"]) or set()
        if "headers" in kw:
            call.headers |= {h for h in (_dict_keys(kw["headers"]) or set()) if h.lower() not in IGNORED_HEADERS}


def _alias(ann: ast.AST, value: ast.AST | None) -> str | None:
    """Fern spells aliases two ways: FieldMetadata(alias=) inside Annotated, or Field(alias=)."""
    for node in [ann] + ([value] if value is not None else []):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fname = sub.func.attr if isinstance(sub.func, ast.Attribute) else getattr(sub.func, "id", "")
                if fname in {"FieldMetadata", "Field"}:
                    for k in sub.keywords:
                        if k.arg == "alias" and isinstance(k.value, ast.Constant):
                            return str(k.value.value)
    return None


def _scan_models(tree: ast.AST, file: str, models: dict[str, SdkModel]) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [ast.unparse(b) for b in node.bases]
        if not any("BaseModel" in b for b in bases):
            continue
        fields: dict[str, str] = {}
        for stmt in node.body:  # direct body only: skips `model_config` inside `if IS_PYDANTIC_V2`
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                ann_src = ast.unparse(stmt.annotation)
                if "ClassVar" in ann_src:
                    continue
                wire = _alias(stmt.annotation, stmt.value) or stmt.target.id
                fields[wire] = ann_src
        models[node.name] = SdkModel(name=node.name, fields=fields, file=file)


def _imports_websocket(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        if any(n.split(".")[0] in {"websockets", "websocket", "httpx_ws", "aiohttp"} for n in names):
            return True
    return False


def scan(root: Path, version: str | None = None) -> SdkSurface:
    calls: dict[tuple[str, str], SdkCall] = {}
    models: dict[str, SdkModel] = {}
    has_ws = False
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if rel.startswith("core/"):
            continue  # http plumbing, not API surface
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        _scan_calls(tree, calls)
        _scan_models(tree, rel, models)
        has_ws = has_ws or _imports_websocket(tree)
    return SdkSurface(root=root, version=version, calls=calls, models=models, has_ws_client=has_ws)
