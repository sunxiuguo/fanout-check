"""Read-only CLI. Exit 0: pass, 1: contract failure, 2: invalid/incomplete."""
import argparse
from decimal import Decimal, InvalidOperation
import json
import sys

from . import __version__
from .core import InputError, check

MAX_INPUT_BYTES = 10 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("", "duplicate JSON field")
        result[key] = value
    return result


def load_json(path):
    if path == "-":
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with open(path, "rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise InputError("", "input exceeds 10 MiB")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_float=Decimal,
                      parse_constant=lambda _: (_ for _ in ()).throw(InputError("", "non-finite JSON number")))


def _text_label(value):
    return json.dumps(value, ensure_ascii=True)[1:-1]


def render_text(report):
    lines = [f"fanout-check: {report['status'].upper()}"]
    for group in report["groups"]:
        m = group["metrics"]
        if m is None:
            lines.append(f"  {_text_label(group['name'])}: metrics unavailable (membership or unfinished spans)")
        else:
            lines.append(f"  {_text_label(group['name'])}: peak={m['peak']}  overlap={m['all_overlap_ms']:.3f} ms  launch-skew={m['launch_skew_ms']:.3f} ms")
    for finding in report["findings"]:
        detail = ""
        if finding["code"] == "LIMIT_VIOLATION":
            detail = f" {finding['metric']}={finding['actual']} ({finding['comparison']} {finding['expected']})"
        elif "member" in finding:
            detail = f" {_text_label(finding['member'])} count={finding['actual']}"
        lines.append(f"  {finding['code']} [{_text_label(finding['group'])}]{detail}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check actual overlap in explicitly grouped tool/agent spans. No model calls or file writes.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("trace", help="version-1 monotonic trace JSON, or - for stdin")
    parser.add_argument("--contract", required=True, help="timing contract JSON")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        if args.trace == "-" and args.contract == "-":
            raise InputError("", "only one input may use stdin")
        trace = load_json(args.trace)
        contract = load_json(args.contract)
        report = check(trace, contract)
    except (InputError, OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError, InvalidOperation) as exc:
        error = {"version": 1, "status": "invalid", "error": {
            "path": exc.path if isinstance(exc, InputError) else "",
            "message": exc.message if isinstance(exc, InputError) else "cannot read valid UTF-8 JSON input",
        }}
        if args.format == "json":
            print(json.dumps(error, ensure_ascii=True))
        else:
            print("fanout-check: INVALID\n  " + error["error"]["message"], file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True) if args.format == "json" else render_text(report))
    return {"pass": 0, "fail": 1, "inconclusive": 2}[report["status"]]
