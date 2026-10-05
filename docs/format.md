# Format and semantics, version 1

## Trace

```json
{
  "version": 1,
  "clock": "monotonic",
  "spans": [
    {"id": "1", "name": "a", "group": "batch", "start_ns": 0, "end_ns": 10000000, "status": "ok"},
    {"id": "2", "name": "b", "group": "batch", "start_ns": 1000000, "end_ns": 9000000, "status": "ok"}
  ]
}
```

IDs are unique across the trace. Names need only be unique within each contracted group. Labels are nonempty strings of at most 200 characters with no Unicode control/format characters, surrogate code points, or line/paragraph separators. Timestamps are nonnegative integer nanoseconds up to `2**63 - 1`; booleans are not numbers. Use one recorder/clock origin per trace.

Statuses: `ok`, `error`, `cancelled`, or `running`. Only `running` has `end_ns: null`. All others require an end greater than or equal to the start. The recorder rethrows exceptions and cancellation; it never turns them into success. Unfinished selected spans make the report inconclusive. A process killed without exporting a final trace cannot be inspected by this recorder.

All fields are required and no additional fields are accepted. Convert existing telemetry explicitly; setting `clock` to `monotonic` does not correct clock skew.

## Contract

```json
{
  "version": 1,
  "allow_unlisted_groups": false,
  "groups": [
    {"name": "batch", "members": ["a", "b"], "min_peak": 2, "max_peak": 2, "min_overlap_ms": 4}
  ]
}
```

Group names and member names must be unique within their arrays. A group has at least two members and at least one limit. Missing/extra members suppress that group's timing metrics rather than calculating them on a favorable subset. Repeated names count as extra occurrences even if they are legitimate retries; assign attempts distinct names/groups deliberately.

Unknown fields are errors, including misspelled limit names. CLI fractional JSON bounds are parsed as exact decimals. Bounds may contain at most 100 significant digits and an exponent between -100 and 100; unsupported precision is rejected rather than rounded or underflowed. Python callers can use `decimal.Decimal` for exact decimal bounds; a supplied Python float means its shortest decimal representation. `allow_unlisted_groups` is optional and defaults to false. All groups in `groups` are required. Unlisted groups explicitly allowed by the contract are outside its timing/status guarantee.

## Interval arithmetic

Intervals are half-open: `[start_ns, end_ns)`. A call ending exactly when another starts does not overlap it. Zero-duration spans have no positive interval and never increase peak concurrency.

- `group_ms`: entire envelope from first start to last end
- `active_ms`: union of intervals with at least one call active
- `work_ms`: sum of individual durations, including waits inside measured blocks
- `all_overlap_ms`: intersection of all members' intervals
- `all_overlap_ratio`: intersection duration divided by shortest duration, or zero if any duration is zero
- `launch_skew_ms`: last start minus first start
- `average_active_concurrency`: summed durations divided by active union, or zero for an empty union
- `concurrency_ms`: duration at each observed concurrency level; key `"0"` means idle gaps inside the envelope

A sweep across grouped endpoint deltas handles ties independently of input order. Limit checks are exact nanosecond/rational comparisons; JSON metric display is floating point. This avoids rounding a failing sub-nanosecond threshold into a pass.

## Report

The report has `version`, `status`, `groups`, and `findings`. Each group has `name` and `metrics` (null if its exact membership or completion cannot be established).

Finding codes:

- `MEMBER_COUNT`: required member appeared zero or more than one time
- `UNEXPECTED_MEMBER`: unexpected name in a contracted group
- `UNLISTED_GROUP`: trace group has no contract and unlisted groups are not allowed
- `UNSUCCESSFUL_SPAN`: selected call ended with error or cancellation
- `UNFINISHED_SPAN`: selected call has not ended
- `LIMIT_VIOLATION`: observed metric is outside an inclusive bound

`path` is a JSON Pointer into the contract for `/groups/...` and into the trace for `/spans/...`. Text reports ASCII-escape Unicode, quotes, and backslashes in labels so redirected output does not depend on the terminal encoding. IDs and labels may appear in findings, but no tool payloads are accepted or printed. Exact Decimal bounds in `expected` are serialized as decimal strings so JSON output does not round them; integer and Python float bounds retain their numeric type.

The status is `inconclusive` if a selected span is unfinished, even if other findings already fail. Otherwise it is `fail` if any finding exists, and `pass` only with no findings. Invalid input raises `InputError` in Python; the CLI emits an `invalid` error object in JSON mode. Argument-parser errors such as missing flags retain normal argparse text output.
