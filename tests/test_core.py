import copy
from decimal import Decimal
import json
import random
import unittest

from fanout_check import InputError, check
from fanout_check.core import MAX_NS, interval_metrics


def span(name, start=0, end=10, group="batch", status="ok", id=None):
    return dict(id=id or name, name=name, group=group, start_ns=start, end_ns=end, status=status)


def trace(*spans):
    return dict(version=1, clock="monotonic", spans=list(spans))


def contract(**limits):
    return dict(version=1, groups=[dict(name="batch", members=["a", "b"], **(limits or {"min_peak": 2}))])


class MetricsTests(unittest.TestCase):
    def test_fully_parallel(self):
        r = check(trace(span("a"), span("b")), contract(min_peak=2, min_overlap_ratio=1))
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["groups"][0]["metrics"]["average_active_concurrency"], 2)

    def test_sequential_fails(self):
        r = check(trace(span("a", 0, 10), span("b", 10, 20)), contract())
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["findings"][0]["actual"], 1)

    def test_adjacent_endpoints_never_overlap(self):
        m = interval_metrics([span("a", 0, 10), span("b", 10, 20)])
        self.assertEqual(m["peak"], 1)
        self.assertEqual(m["all_overlap_ns"], 0)
        self.assertEqual(m["concurrency_ns"], {1: 20})

    def test_partial_overlap(self):
        m = interval_metrics([span("a", 0, 10), span("b", 5, 15)])
        self.assertEqual(m["concurrency_ns"], {1: 10, 2: 5})
        self.assertEqual(m["work_ns"], 20)
        self.assertEqual(m["active_ns"], 15)

    def test_idle_gap(self):
        m = interval_metrics([span("a", 0, 5), span("b", 10, 15)])
        self.assertEqual(m["concurrency_ns"], {0: 5, 1: 10})
        self.assertEqual(m["group_ns"], 15)

    def test_zero_duration(self):
        r = check(trace(span("a", 0, 0), span("b", 0, 0)), contract())
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["groups"][0]["metrics"]["peak"], 0)

    def test_zero_does_not_inflate_peak(self):
        m = interval_metrics([span("a", 0, 10), span("b", 5, 5)])
        self.assertEqual(m["peak"], 1)
        self.assertEqual(m["all_overlap_ns"], 0)

    def test_large_timestamps_keep_nanosecond_difference(self):
        r = check(trace(span("a", MAX_NS-4, MAX_NS), span("b", MAX_NS-3, MAX_NS)), contract(min_overlap_ms=0.000003))
        self.assertEqual(r["status"], "pass")
        r = check(trace(span("a", MAX_NS-4, MAX_NS), span("b", MAX_NS-3, MAX_NS)), contract(min_overlap_ms=0.0000031))
        self.assertEqual(r["status"], "fail")

    def test_ratio_exact_boundary(self):
        t = trace(span("a", 0, 10), span("b", 7, 17))
        self.assertEqual(check(t, contract(min_overlap_ratio=.3))["status"], "pass")
        self.assertEqual(check(t, contract(min_overlap_ratio=.30000000000000004))["status"], "fail")

    def test_decimal_ratio_exact_boundary(self):
        t = trace(span("a", 0, 3), span("b", 2, 5))
        self.assertEqual(check(t, contract(min_overlap_ratio=Decimal("0.3333333333333333333")))["status"], "pass")
        r = check(t, contract(min_overlap_ratio=Decimal("0.3333333333333333334")))
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["findings"][0]["expected"], "0.3333333333333333334")
        json.dumps(r)

    def test_maximums(self):
        t = trace(span("a", 0, 10_000_000), span("b", 5_000_000, 15_000_000))
        r = check(t, contract(max_peak=1, max_launch_skew_ms=4, max_group_ms=14))
        self.assertEqual(len(r["findings"]), 3)
        self.assertEqual(check(t, contract(max_peak=2, max_launch_skew_ms=5, max_group_ms=15))["status"], "pass")

    def test_no_mutation(self):
        t, c = trace(span("a"), span("b")), contract()
        before = copy.deepcopy((t, c))
        check(t, c)
        self.assertEqual((t, c), before)

    def test_order_invariant_metrics(self):
        t = [span("a", 0, 10), span("b", 2, 5), span("c", 5, 15)]
        self.assertEqual(interval_metrics(t), interval_metrics(list(reversed(t))))

    def test_exhaustive_small_interval_pairs(self):
        intervals = [(a, b) for a in range(6) for b in range(a, 7)]
        for first in intervals:
            for second in intervals:
                spans = [span("a", *first), span("b", *second)]
                m = interval_metrics(spans)
                counts = [sum(a <= t < b for a, b in (first, second)) for t in range(min(first[0], second[0]), max(first[1], second[1]))]
                self.assertEqual(m["peak"], max(counts, default=0))
                self.assertEqual(m["work_ns"], sum(counts))
                self.assertEqual(m["active_ns"], sum(n > 0 for n in counts))
                self.assertEqual(m["all_overlap_ns"], sum(n == 2 for n in counts))

    def test_seeded_interval_oracle(self):
        rng = random.Random(20261005)
        for _ in range(300):
            spans = []
            for i in range(rng.randint(2, 10)):
                start = rng.randrange(20)
                spans.append(span(str(i), start, rng.randrange(start, 25)))
            m = interval_metrics(spans)
            counts = [sum(s["start_ns"] <= t < s["end_ns"] for s in spans) for t in range(25)]
            self.assertEqual(m["peak"], max(counts))
            self.assertEqual(m["active_ns"], sum(n > 0 for n in counts))
            self.assertEqual(m["all_overlap_ns"], sum(n == len(spans) for n in counts))


class MembershipTests(unittest.TestCase):
    def test_empty_trace_is_failure(self):
        self.assertEqual(check(trace(), contract())["status"], "fail")

    def test_missing_member(self):
        r = check(trace(span("a")), contract())
        self.assertEqual(r["findings"][0]["code"], "MEMBER_COUNT")
        self.assertIsNone(r["groups"][0]["metrics"])

    def test_retries_are_not_silently_combined(self):
        r = check(trace(span("a"), span("a", id="retry"), span("b")), contract())
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["findings"][0]["actual"], 2)

    def test_unexpected_member(self):
        r = check(trace(span("a"), span("b"), span("c")), contract())
        self.assertEqual(r["findings"][0]["code"], "UNEXPECTED_MEMBER")

    def test_unlisted_group(self):
        r = check(trace(span("a"), span("b"), span("c", group="other")), contract())
        self.assertEqual(r["findings"][0]["code"], "UNLISTED_GROUP")

    def test_allow_unlisted_is_explicit(self):
        c = contract()
        c["allow_unlisted_groups"] = True
        r = check(trace(span("a"), span("b"), span("c", group="other")), c)
        self.assertEqual(r["status"], "pass")

    def test_group_isolation(self):
        c = contract()
        c["groups"].append(dict(name="other", members=["a", "b"], min_peak=2))
        r = check(trace(span("a", 0, 10), span("b", 0, 10), span("a", 20, 30, "other", id="x"), span("b", 30, 40, "other", id="y")), c)
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["findings"][0]["group"], "other")

    def test_error_is_failure_even_when_overlapping(self):
        r = check(trace(span("a", status="error"), span("b")), contract())
        self.assertEqual(r["findings"][0]["code"], "UNSUCCESSFUL_SPAN")
        self.assertEqual(r["status"], "fail")

    def test_cancelled_is_failure(self):
        self.assertEqual(check(trace(span("a", status="cancelled"), span("b")), contract())["status"], "fail")

    def test_running_is_inconclusive(self):
        r = check(trace(span("a", end=None, status="running"), span("b")), contract())
        self.assertEqual(r["status"], "inconclusive")
        self.assertIsNone(r["groups"][0]["metrics"])

    def test_finished_member_does_not_hide_incomplete_group(self):
        r = check(trace(span("a", end=None, status="running")), contract())
        self.assertEqual(r["status"], "inconclusive")
        self.assertEqual({f["code"] for f in r["findings"]}, {"MEMBER_COUNT", "UNFINISHED_SPAN"})


class ValidationTests(unittest.TestCase):
    def test_bad_trace_fields(self):
        mutations = [
            lambda t: t.update(version=True), lambda t: t.update(clock="unix"),
            lambda t: t.update(payload="secret"), lambda t: t.update(spans={}),
            lambda t: t["spans"][0].update(start_ns=True),
            lambda t: t["spans"][0].update(start_ns=-1),
            lambda t: t["spans"][0].update(start_ns=1.1),
            lambda t: t["spans"][0].update(end_ns=MAX_NS+1),
            lambda t: t["spans"][0].update(end_ns=-1),
            lambda t: t["spans"][0].update(end_ns=None),
            lambda t: t["spans"][0].update(name="\x1b[31m"),
            lambda t: t["spans"][0].update(name=""),
            lambda t: t["spans"][0].update(name="\ud800"),
            lambda t: t["spans"][0].update(name="\u202e"),
            lambda t: t["spans"][0].update(name="\u0085"),
            lambda t: t["spans"][0].update(name="\u2028"),
            lambda t: t["spans"][0].update(status="unknown"),
            lambda t: t["spans"][0].update(status="running"),
            lambda t: t["spans"][0].update(arguments="secret"),
            lambda t: t["spans"][1].update(id="a"),
        ]
        for mutate in mutations:
            t = trace(span("a"), span("b"))
            mutate(t)
            with self.subTest(trace=t), self.assertRaises(InputError):
                check(t, contract())

    def test_invalid_contract_limits(self):
        for key, value in [("min_peak", 0), ("min_peak", 3), ("min_peak", True), ("max_peak", 1.5), ("min_overlap_ratio", 1.1), ("min_overlap_ms", -1), ("min_overlap_ms", float("nan")), ("max_group_ms", float("inf")), ("max_group_ms", 10**1000), ("max_launch_skew_ms", "3"), ("min_overlap_ms", False)]:
            with self.subTest(key=key, value=value), self.assertRaises(InputError):
                check(trace(span("a"), span("b")), contract(**{key: value}))

    def test_invalid_contract_shape(self):
        bad = [None, {}, dict(version=True, groups=[]), dict(version=1, groups=[]), dict(version=1, groups=[dict(name="batch", members=["a", "a"], min_peak=2)]), dict(version=1, groups=[dict(name="batch", members=["a", "b"])]), contract(min_peek=2), contract(min_peak=2, max_peak=1)]
        for c in bad:
            with self.subTest(contract=c), self.assertRaises(InputError):
                check(trace(span("a"), span("b")), c)

    def test_duplicate_group(self):
        c = contract()
        c["groups"].append(copy.deepcopy(c["groups"][0]))
        with self.assertRaises(InputError):
            check(trace(), c)

    def test_oversize_span_count(self):
        with self.assertRaises(InputError):
            check(trace(*([span("a")] * 10_001)), contract())

    def test_json_serializable_report(self):
        r = check(trace(span("a"), span("b")), contract())
        self.assertEqual(json.loads(json.dumps(r)), r)


if __name__ == "__main__":
    unittest.main()
