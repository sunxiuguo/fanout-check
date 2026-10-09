# fanout-check

**Catch “parallel” agent workflows that quietly run one call at a time.**

A small, offline Python library and CLI for testing **observed overlap** in explicitly grouped tool or subagent calls. No API keys, model calls, telemetry, or runtime dependencies.

```text
Blocking tool bodies, even though called with gather:
fanout-check: FAIL
  research: peak=1  overlap=0.000 ms
  LIMIT_VIOLATION [research] peak=1 (minimum 3)

Cooperative tool bodies:
fanout-check: PASS
  research: peak=3
```

Excerpt from the runnable demo. Exact times depend on your machine.

## Try it in a checkout

Requires Python 3.10 or newer. No install is needed for the demo or tests.

```sh
git clone https://github.com/sunxiuguo/fanout-check.git
cd fanout-check
python -m examples.demo
python -m unittest discover -s tests -v
```

The demo actually runs three blocking tasks and three cooperative tasks, records their intervals, and checks the expected failure and passing control. It uses synthetic work and no agent SDK.

For an actual SDK component comparison, see the optional
[Agents SDK regression example](examples/agents-sdk-regression/). It compares
historical and fixed releases without a model or Runner; the core has no new dependencies.

Run a deterministic fixture:

```sh
python -m fanout_check examples/parallel.json --contract examples/contract.json
python -m fanout_check examples/sequential.json --contract examples/contract.json --format json
# The second command intentionally exits 1.
```

Optional installation from this checkout:

```sh
python -m pip install .
fanout-check examples/parallel.json --contract examples/contract.json
```

This project is not currently published to PyPI. The source-install build uses setuptools; the installed package has no runtime dependencies.

## Put a contract around your fan-out

```python
import asyncio
from fanout_check import Recorder, check

recorder = Recorder()

async def tool(name):
    with recorder.span(name, group="research"):
        await asyncio.sleep(0.05)  # replace with your actual awaited tool call

async def run():
    await asyncio.gather(tool("docs"), tool("code"), tool("tests"))

asyncio.run(run())

report = check(recorder.trace(), {
    "version": 1,
    "groups": [{
        "name": "research",
        "members": ["docs", "code", "tests"],
        "min_peak": 3,
        "min_overlap_ratio": 0.8,
    }],
})
assert report["status"] == "pass", report["findings"]
```

Each member must occur **exactly once** in that group. Missing calls, extra calls, retries with the same member name, errors, and cancellations cannot quietly pass. Use a new group name for each batch or retry attempt.

### Available limits

- `min_peak`: at least this many selected calls were simultaneously in progress for a positive interval
- `max_peak`: no more than this many selected calls were simultaneously in progress
- `min_overlap_ms`: all members overlapped for at least this long
- `min_overlap_ratio`: all-member overlap divided by the shortest member's duration, from 0 to 1
- `max_launch_skew_ms`: latest start minus earliest start
- `max_group_ms`: latest end minus earliest start, including gaps

Every contract needs at least one limit. Bounds are inclusive. Comparisons use exact integer/rational arithmetic; displayed values use milliseconds.

For a concurrency-limited batch, use `min_peak` and `max_peak`. Do not require all-member overlap when the cap is smaller than the member count.

## What a pass means

It means the supplied intervals meet the supplied contract. **Overlap is not proof of useful CPU parallelism, safe independence, correct outputs, or a faster end-to-end run.** Sleeping, queueing, nested wrappers, or blocking on a lock can overlap too.

Instrument the operation you want to measure. In particular, place the span **inside** a semaphore to measure admitted work:

```python
async with semaphore:
    with recorder.span("lookup-a", group="batch-1"):
        await lookup()
```

Only group sibling operations that you already know may run concurrently. The tool never decides which actions are safe to parallelize. Do not use it to parallelize approval-dependent or otherwise ordered actions.

## Files, statuses, and CI

The read-only CLI accepts a trace file or stdin plus a contract file:

```sh
python -m fanout_check - --contract examples/contract.json --format json < examples/parallel.json
```

- Exit `0`: all configured groups passed
- Exit `1`: a contract failed, including missing/extra/failed/cancelled calls
- Exit `2`: invalid input or an unfinished selected span (`inconclusive`)

Unlisted groups fail unless the contract explicitly sets `"allow_unlisted_groups": true`. Invalid spans anywhere in a trace are rejected even when their group is unlisted. A trace with no calls cannot satisfy a nonempty contract.

The recorder uses a single process's monotonic clock. Exported data uses integer nanoseconds relative to the recorder's origin. [The format](docs/format.md) is small enough to emit from another language. Do not combine clocks from different machines or recorder instances. This version does not import OTel, Langfuse, or vendor transcripts.

CI example after producing `run.json` in your application test:

```sh
python -m fanout_check run.json --contract fanout-contract.json --format json
```

Keep timing budgets realistic for your CI runner. The shipped tests use deterministic interval fixtures and an exhaustive small-interval oracle; they do not gate on tight wall-time benchmarks.

## Why a separate tool?

A historical [Agents SDK report](https://github.com/openai/openai-agents-python/issues/2386) describes synchronous tool bodies serializing an otherwise parallel execution path. [Another request](https://github.com/openai/openai-agents-python/issues/1859) asks for a concurrency cap. **Both issues are closed/completed**; this project does not claim to fix current SDK bugs. These failure classes can still recur in application code and wrapper changes.

Trace platforms and viewers remain the right tools for collection, visualization, and diagnosis. `fanout-check` is deliberately a small timing-contract gate for an application test, with explicit groups and no hosted service. [Research and alternatives](docs/research.md) records the evidence and limits of the product hypothesis.

## Privacy and limits

- The recorder collects caller-supplied labels, IDs, timestamps, and status only. It does not capture prompts, tool inputs, outputs, exception messages, or secrets
- Labels are still your data: use stable operation names, not customer text or credentials
- No network access or automatic execution/replay of recorded operations
- The CLI reads files and stdout/stderr only; it does not write reports to disk. Python may create its normal bytecode cache unless disabled
- Strict version-1 input: unknown fields, duplicate JSON keys, duplicate IDs, malformed times, and unsupported clocks fail closed
- CLI limits: 10 MiB per input, 10,000 spans per trace, 1,000 group contracts
- Not a security boundary, trusted attestation, profiler, scheduler, or statistical benchmark

## Development

```sh
python -m unittest discover -s tests -v
python -m examples.demo
python -m compileall -q fanout_check
```

[Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
