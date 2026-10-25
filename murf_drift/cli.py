"""murf-drift: does the Murf Python SDK still cover the published API?"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import diff, docs_check, sdk_scan, spec

EXIT_OK, EXIT_DRIFT, EXIT_USAGE = 0, 1, 2


def run(openapi: str, asyncapi: str | None, sdk_path: str | None,
        docs_index: str | None = None) -> tuple[list[diff.Finding], dict]:
    if sdk_path:
        root, version = Path(sdk_path), None
        if not root.is_dir():
            raise FileNotFoundError(f"--sdk {sdk_path}: not a directory")
    else:
        root, version = sdk_scan.locate_installed("murf")
    surface = sdk_scan.scan(root, version)
    findings = diff.diff_rest(spec.rest_operations(spec.load(openapi)), surface)
    n_channels = 0
    if asyncapi:
        channels, resolver = spec.ws_channels(spec.load(asyncapi))
        n_channels = len(channels)
        findings += diff.diff_ws(channels, resolver, surface)
    docs_stats = None
    if docs_index:
        docs_findings, docs_stats = docs_check.check_docs(root, docs_index)
        findings += docs_findings
    meta = {
        "sdk_root": str(root),
        "sdk_version": version,
        "openapi": openapi,
        "asyncapi": asyncapi,
        "sdk_operations": len(surface.calls),
        "ws_channels": n_channels,
        "docs": docs_stats,
    }
    return findings, meta


def render_text(findings: list[diff.Finding], meta: dict) -> str:
    lines = [f"murf-drift: SDK {meta['sdk_version'] or meta['sdk_root']} vs {meta['openapi']}"]
    if meta["asyncapi"]:
        lines.append(f"            and {meta['asyncapi']}")
    counts = Counter(f.severity for f in findings)
    for sev in ("error", "warn", "info"):
        group = [f for f in findings if f.severity == sev]
        if not group:
            continue
        lines.append("")
        lines.append(f"{sev.upper()} ({len(group)})")
        for f in group:
            lines.append(f"  [{f.kind}] {f.where}: {f.detail}")
    lines.append("")
    if meta.get("docs"):
        d = meta["docs"]
        lines.append(f"docs: {d['pages']} pages, {d['python_blocks']} python blocks, "
                     f"{d['sdk_calls_checked']} SDK calls checked")
    lines.append(f"{counts['error']} error(s), {counts['warn']} warning(s), {counts['info']} info")
    return "\n".join(lines)


def render_markdown(findings: list[diff.Finding], meta: dict) -> str:
    out = [f"### SDK drift: murf {meta['sdk_version'] or '(local checkout)'} vs published spec", "",
           "| Severity | Kind | Where | Detail |", "|---|---|---|---|"]
    for f in findings:
        out.append(f"| {f.severity} | {f.kind} | `{f.where}` | {f.detail} |")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="murf-drift", description=__doc__)
    p.add_argument("--openapi", default=spec.OPENAPI_URL, help="OpenAPI JSON URL or file (default: live Murf spec)")
    p.add_argument("--asyncapi", default=spec.ASYNCAPI_URL, help="AsyncAPI JSON URL or file; pass '' to skip WebSocket checks")
    p.add_argument("--sdk", default=None, help="path to the `murf` package dir (default: the installed one)")
    p.add_argument("--docs", nargs="?", const=docs_check.DOCS_INDEX, default=None, metavar="LLMS_TXT",
                   help="also check every Python example in the docs (default index: murf.ai/api/docs/llms.txt)")
    p.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    p.add_argument("--fail-on", choices=["error", "warn", "never"], default="error",
                   help="exit 1 when a finding at this severity or worse exists (default: error)")
    args = p.parse_args(argv)
    try:
        findings, meta = run(args.openapi, args.asyncapi or None, args.sdk, args.docs)
    except (FileNotFoundError, OSError, ValueError) as e:
        print(f"murf-drift: {e}", file=sys.stderr)
        return EXIT_USAGE

    if args.format == "json":
        print(json.dumps({"meta": meta, "findings": [f.to_dict() for f in findings]}, indent=2))
    elif args.format == "markdown":
        print(render_markdown(findings, meta))
    else:
        print(render_text(findings, meta))

    if args.fail_on == "never":
        return EXIT_OK
    threshold = diff.SEVERITY_ORDER[args.fail_on]
    return EXIT_DRIFT if any(diff.SEVERITY_ORDER[f.severity] >= threshold for f in findings) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
