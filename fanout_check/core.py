"""Strict, payload-free timing contracts for explicitly grouped calls."""
from collections import Counter, defaultdict
from fractions import Fraction
from decimal import Decimal
import unicodedata

MAX_SPANS = 10_000
MAX_NS = 2**63 - 1
LIMITS = {
    "min_peak", "max_peak", "min_overlap_ms", "min_overlap_ratio",
    "max_launch_skew_ms", "max_group_ms",
}


class InputError(ValueError):
    def __init__(self, path, message):
        self.path = path
        self.message = message
        super().__init__(f"{path or '/'}: {message}")


def _object(value, required, optional, path):
    if not isinstance(value, dict):
        raise InputError(path, "expected an object")
    if set(value) - required - optional:
        raise InputError(path, "unrecognized field")
    if required - set(value):
        raise InputError(path, "missing required field")


def _label(value, path):
    if (not isinstance(value, str) or not value.strip() or len(value) > 200
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value)):
        raise InputError(path, "expected a nonempty label of at most 200 characters, without Unicode controls, format characters, surrogates, or line separators")


def _integer(value, path):
    if type(value) is not int or not 0 <= value <= MAX_NS:
        raise InputError(path, "expected a nonnegative 63-bit integer")


def _limit_fraction(value, path):
    if type(value) not in (int, float, Decimal):
        raise InputError(path, "expected a finite nonnegative limit")
    number = value if isinstance(value, Decimal) else Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    if not number.is_finite() or number < 0 or number > Decimal(MAX_NS) / 1_000_000:
        raise InputError(path, "expected a finite nonnegative limit")
    digits = number.as_tuple()
    if len(digits.digits) > 100 or abs(digits.exponent) > 100:
        raise InputError(path, "limit exceeds supported decimal precision (100 digits/places)")
    return Fraction(number)


def validate_trace(trace):
    _object(trace, {"version", "clock", "spans"}, set(), "")
    if type(trace["version"]) is not int or trace["version"] != 1:
        raise InputError("/version", "only version 1 is supported")
    if trace["clock"] != "monotonic":
        raise InputError("/clock", "one shared monotonic clock is required")
    spans = trace["spans"]
    if not isinstance(spans, list) or len(spans) > MAX_SPANS:
        raise InputError("/spans", f"expected an array with at most {MAX_SPANS} spans")
    seen = set()
    for i, span in enumerate(spans):
        p = f"/spans/{i}"
        _object(span, {"id", "name", "group", "start_ns", "end_ns", "status"}, set(), p)
        for field in ("id", "name", "group"):
            _label(span[field], f"{p}/{field}")
        if span["id"] in seen:
            raise InputError(f"{p}/id", "duplicate span id")
        seen.add(span["id"])
        _integer(span["start_ns"], f"{p}/start_ns")
        if span["status"] not in ("ok", "error", "cancelled", "running"):
            raise InputError(f"{p}/status", "expected ok, error, cancelled, or running")
        if span["status"] == "running":
            if span["end_ns"] is not None:
                raise InputError(f"{p}/end_ns", "running spans must have a null end")
        else:
            _integer(span["end_ns"], f"{p}/end_ns")
            if span["end_ns"] < span["start_ns"]:
                raise InputError(f"{p}/end_ns", "end precedes start")
    return trace


def validate_contract(contract):
    _object(contract, {"version", "groups"}, {"allow_unlisted_groups"}, "")
    if type(contract["version"]) is not int or contract["version"] != 1:
        raise InputError("/version", "only version 1 is supported")
    if type(contract.get("allow_unlisted_groups", False)) is not bool:
        raise InputError("/allow_unlisted_groups", "expected a boolean")
    groups = contract["groups"]
    if not isinstance(groups, list) or not 1 <= len(groups) <= 1000:
        raise InputError("/groups", "expected 1 to 1000 group contracts")
    seen = set()
    for i, group in enumerate(groups):
        p = f"/groups/{i}"
        _object(group, {"name", "members"}, LIMITS, p)
        _label(group["name"], f"{p}/name")
        if group["name"] in seen:
            raise InputError(f"{p}/name", "duplicate group name")
        seen.add(group["name"])
        members = group["members"]
        if not isinstance(members, list) or not 2 <= len(members) <= MAX_SPANS:
            raise InputError(f"{p}/members", "expected 2 to 10000 unique member names")
        for j, member in enumerate(members):
            _label(member, f"{p}/members/{j}")
        if len(set(members)) != len(members):
            raise InputError(f"{p}/members", "duplicate member name")
        if not LIMITS.intersection(group):
            raise InputError(p, "at least one timing or concurrency limit is required")
        for key in LIMITS.intersection(group):
            value = group[key]
            if key in ("min_peak", "max_peak"):
                if type(value) is not int or not 1 <= value <= len(members):
                    raise InputError(f"{p}/{key}", "expected an integer from 1 to member count")
            else:
                _limit_fraction(value, f"{p}/{key}")
            if key == "min_overlap_ratio" and value > 1:
                raise InputError(f"{p}/{key}", "ratio must be between 0 and 1")
        if group.get("min_peak", 1) > group.get("max_peak", len(members)):
            raise InputError(p, "min_peak exceeds max_peak")
    return contract


def interval_metrics(spans):
    """Compute exact nanosecond metrics on validated, finished spans."""
    if not spans or any(s["end_ns"] is None for s in spans):
        raise ValueError("metrics require at least one finished span")
    events = defaultdict(int)
    durations = []
    for span in spans:
        start, end = span["start_ns"], span["end_ns"]
        durations.append(end - start)
        events[start] += 1
        events[end] -= 1
    bins = defaultdict(int)
    active, previous = 0, min(events)
    for timestamp in sorted(events):
        if timestamp > previous:
            bins[active] += timestamp - previous
        active += events[timestamp]
        previous = timestamp
    overlap = max(0, min(s["end_ns"] for s in spans) - max(s["start_ns"] for s in spans))
    shortest = min(durations)
    return {
        "calls": len(spans),
        "peak": max((n for n, ns in bins.items() if ns > 0), default=0),
        "group_ns": max(s["end_ns"] for s in spans) - min(s["start_ns"] for s in spans),
        "active_ns": sum(ns for n, ns in bins.items() if n > 0),
        "work_ns": sum(durations),
        "all_overlap_ns": overlap,
        "shortest_ns": shortest,
        "launch_skew_ns": max(s["start_ns"] for s in spans) - min(s["start_ns"] for s in spans),
        "concurrency_ns": dict(sorted(bins.items())),
    }


def _display_metrics(m):
    active = m["active_ns"]
    return {
        "calls": m["calls"], "peak": m["peak"],
        "group_ms": m["group_ns"] / 1_000_000,
        "active_ms": active / 1_000_000,
        "work_ms": m["work_ns"] / 1_000_000,
        "all_overlap_ms": m["all_overlap_ns"] / 1_000_000,
        "all_overlap_ratio": m["all_overlap_ns"] / m["shortest_ns"] if m["shortest_ns"] else 0,
        "launch_skew_ms": m["launch_skew_ns"] / 1_000_000,
        "average_active_concurrency": m["work_ns"] / active if active else 0,
        "concurrency_ms": {str(n): ns / 1_000_000 for n, ns in m["concurrency_ns"].items()},
    }


def check(trace, contract):
    """Return a JSON-serializable report, without modifying either input."""
    validate_trace(trace)
    validate_contract(contract)
    by_group = defaultdict(list)
    for i, span in enumerate(trace["spans"]):
        by_group[span["group"]].append((i, span))
    findings, reports = [], []
    inconclusive = False

    def finding(code, group, path, **detail):
        findings.append({"code": code, "group": group, "path": path, **detail})

    listed = {g["name"] for g in contract["groups"]}
    if not contract.get("allow_unlisted_groups", False):
        for name in sorted(set(by_group) - listed):
            finding("UNLISTED_GROUP", name, f"/spans/{by_group[name][0][0]}/group")
    for gi, group in enumerate(contract["groups"]):
        name = group["name"]
        rows = by_group.get(name, [])
        cp = f"/groups/{gi}"
        counts = Counter(s["name"] for _, s in rows)
        valid_members = True
        for member in group["members"]:
            if counts[member] != 1:
                finding("MEMBER_COUNT", name, cp + "/members", member=member, expected=1, actual=counts[member])
                valid_members = False
        for member in sorted(set(counts) - set(group["members"])):
            finding("UNEXPECTED_MEMBER", name, cp + "/members", member=member, actual=counts[member])
            valid_members = False
        unfinished = False
        for i, span in rows:
            if span["status"] == "running":
                finding("UNFINISHED_SPAN", name, f"/spans/{i}/end_ns", span_id=span["id"])
                unfinished = inconclusive = True
            elif span["status"] != "ok":
                finding("UNSUCCESSFUL_SPAN", name, f"/spans/{i}/status", span_id=span["id"], actual=span["status"])
        if not valid_members or unfinished:
            reports.append({"name": name, "metrics": None})
            continue
        m = interval_metrics([s for _, s in rows])
        metrics = _display_metrics(m)
        reports.append({"name": name, "metrics": metrics})
        limits = {
            "min_peak": (m["peak"], "minimum", "peak"),
            "max_peak": (m["peak"], "maximum", "peak"),
            "min_overlap_ms": (Fraction(m["all_overlap_ns"], 1_000_000), "minimum", "all_overlap_ms"),
            "min_overlap_ratio": (Fraction(m["all_overlap_ns"], m["shortest_ns"]) if m["shortest_ns"] else Fraction(0), "minimum", "all_overlap_ratio"),
            "max_launch_skew_ms": (Fraction(m["launch_skew_ns"], 1_000_000), "maximum", "launch_skew_ms"),
            "max_group_ms": (Fraction(m["group_ns"], 1_000_000), "maximum", "group_ms"),
        }
        for key in sorted(LIMITS.intersection(group)):
            actual, direction, metric = limits[key]
            limit = _limit_fraction(group[key], cp + "/" + key)
            if (direction == "minimum" and actual < limit) or (direction == "maximum" and actual > limit):
                finding("LIMIT_VIOLATION", name, cp + "/" + key, metric=metric, comparison=direction, expected=str(group[key]) if isinstance(group[key], Decimal) else group[key], actual=metrics[metric])
    return {"version": 1, "status": "inconclusive" if inconclusive else "fail" if findings else "pass", "groups": reports, "findings": findings}
