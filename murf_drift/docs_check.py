"""Check the Python SDK examples in Murf's docs against the SDK's real signatures.

Every ```python block on every docs page is parsed with `ast` (never run).
Calls shaped like `client.<resource>.<method>(kw=...)` and `Murf(kw=...)` are
compared with the parameters the installed SDK accepts. A keyword the SDK
doesn't accept means the copy-pasted example raises TypeError before any
request is sent.
"""

from __future__ import annotations

import ast
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .diff import Finding

DOCS_INDEX = "https://murf.ai/api/docs/llms.txt"
CONSTRUCTORS = {"Murf", "AsyncMurf"}
FENCE = re.compile(r"```(?:python|py)\b[^\n]*\n(.*?)```", re.DOTALL)


@dataclass
class Signature:
    params: set[str]
    var_kw: bool


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "murf-sdk-drift"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature:
    a = fn.args
    names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs} - {"self"}
    return Signature(params=names, var_kw=a.kwarg is not None)


def sdk_signatures(root: Path) -> dict[tuple[str, str], Signature]:
    """(resource, method) -> Signature. resource is the dotted package path, e.g. 'dubbing.jobs'."""
    sigs: dict[tuple[str, str], Signature] = {}
    for py in sorted(root.rglob("client.py")):
        rel = py.relative_to(root)
        resource = ".".join(rel.parts[:-1])
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            if resource == "" and cls.name in CONSTRUCTORS:
                init = next((f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"), None)
                if init:
                    sigs[("", cls.name)] = _sig(init)
                continue
            if not cls.name.endswith("Client") or cls.name.startswith(("Async", "Raw")) or resource == "":
                continue
            for fn in cls.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and not fn.name.startswith("_"):
                    sigs[(resource, fn.name)] = _sig(fn)
    return sigs


def _chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def check_source(src: str, where: str, sigs: dict[tuple[str, str], Signature]) -> tuple[list[Finding], int]:
    """Return findings and the number of SDK calls checked in one code block."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [], 0
    resources = {r for r, _ in sigs if r}
    out: list[Finding] = []
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _chain(node.func)
        if not chain:
            continue
        if len(chain) == 1 and chain[0] in CONSTRUCTORS:
            key, label = ("", chain[0]), chain[0]
        elif len(chain) >= 3 and ".".join(chain[1:-1]) in resources:
            key, label = (".".join(chain[1:-1]), chain[-1]), ".".join(chain[1:])
        else:
            continue
        checked += 1
        sig = sigs.get(key)
        if sig is None:
            out.append(Finding("error", "docs-unknown-method", where, f"`{label}()` is not a method in this SDK"))
            continue
        for kw in node.keywords:
            if kw.arg and kw.arg not in sig.params and not sig.var_kw:
                out.append(Finding("error", "docs-unknown-kwarg", where,
                                   f"`{label}({kw.arg}=...)` raises TypeError: the SDK has no `{kw.arg}` parameter"))
    return out, checked


def page_urls(index_text: str) -> list[str]:
    urls = re.findall(r"\((https://murf\.ai/api/docs/[^)\s]+\.md)\)", index_text)
    return list(dict.fromkeys(urls))


def check_docs(root: Path, index_url: str = DOCS_INDEX, fetch=_fetch) -> tuple[list[Finding], dict]:
    sigs = sdk_signatures(root)
    urls = page_urls(fetch(index_url))
    findings: list[Finding] = []
    stats = {"pages": 0, "python_blocks": 0, "sdk_calls_checked": 0, "fetch_errors": 0}
    for url in urls:
        try:
            text = fetch(url)
        except OSError:
            stats["fetch_errors"] += 1
            continue
        stats["pages"] += 1
        for block in FENCE.findall(text):
            stats["python_blocks"] += 1
            f, n = check_source(block, url, sigs)
            findings += f
            stats["sdk_calls_checked"] += n
    # one row per (page, problem): the same snippet often repeats in tabs
    return list(dict.fromkeys(findings)), stats
