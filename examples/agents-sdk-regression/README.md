# Check an actual SDK tool boundary

This optional, synthetic example invokes real OpenAI Agents SDK `FunctionTool`
callbacks under `asyncio.gather`. It shows what an application's timing contract
can catch. It does not use a model, API key, `Runner`, hosted service or real data,
and does not add dependencies to fanout-check itself.

The motivating [SDK issue #2386](https://github.com/openai/openai-agents-python/issues/2386)
is already fixed by [PR #2387](https://github.com/openai/openai-agents-python/pull/2387),
which includes native regression tests. This is historical/component evidence,
not a new SDK bug, upstream contribution or evidence of external adoption.

## Run the three explicit comparisons

Verified on Linux with Python 3.12.14 on 9 October 2026. From the repository root,
create disposable environments for these examples only. Do not downgrade an
application's environment to the historical versions.

```sh
python3.12 -m venv .venv-agents-070
.venv-agents-070/bin/python -m pip install --only-binary=:all: \
  -c examples/agents-sdk-regression/constraints-historical.txt openai-agents==0.7.0
env -i PATH=/usr/bin:/bin HOME=/tmp OPENAI_AGENTS_DISABLE_TRACING=1 \
  .venv-agents-070/bin/python examples/agents-sdk-regression/probe.py > result-070.json

python3.12 -m venv .venv-agents-080
.venv-agents-080/bin/python -m pip install --only-binary=:all: \
  -c examples/agents-sdk-regression/constraints-historical.txt openai-agents==0.8.0
env -i PATH=/usr/bin:/bin HOME=/tmp OPENAI_AGENTS_DISABLE_TRACING=1 \
  .venv-agents-080/bin/python examples/agents-sdk-regression/probe.py > result-080.json

python3.12 -m venv .venv-agents-0231
.venv-agents-0231/bin/python -m pip install --only-binary=:all: \
  -c examples/agents-sdk-regression/constraints-0.23.1.txt openai-agents==0.23.1
env -i PATH=/usr/bin:/bin HOME=/tmp OPENAI_AGENTS_DISABLE_TRACING=1 \
  .venv-agents-0231/bin/python examples/agents-sdk-regression/probe.py > result-0231.json
```

Installation needs registry access; the probe does not. Each run prints every
synthetic interval, contract and report, repeats five cases three times, and
exits zero only when all expected outcomes match. An expected checker failure is
a successful negative-control assertion. Unknown SDK versions are rejected.

These constraints reproduce the tested dependency versions; they are not a
security endorsement or a cross-platform lockfile. The two historical environments
have identical dependencies except `openai-agents`. An unconstrained historical
installation selected `openai==2.54.0` and failed before tool execution because
`InputTokensDetails(cached_tokens=0)` lacked `cache_write_tokens`. The historical
constraints therefore pin `openai==2.16.0` within the SDK's declared range. Do not
interpret that setup failure as a fanout finding. Release 0.23.1 uses its separate
tested constraints, including OpenAI 3.27.0.

## Observed controls

| Case | SDK 0.7.0 | SDK 0.8.0 | SDK 0.23.1 |
|---|---|---|---|
| Synchronous body, gathered calls | fail, peak 1 | pass, peak 3 | pass, peak 3 |
| Cooperative async body, gathered calls | pass, peak 3 | pass, peak 3 | pass, peak 3 |
| Cooperative async body, sequential calls | fail, peak 1 | fail, peak 1 | fail, peak 1 |
| Blocking sleep inside async body | fail, peak 1 | fail, peak 1 | fail, peak 1 |
| Semaphore cap 2, spans inside semaphore | pass, peak 2 | pass, peak 2 | pass, peak 2 |

The unchanged checker at `4f9a3db0f8d5d7f11a410a2f94d3ff969a3e533f`
produced these outcomes in 45 cases; an independent clean-environment repeat
reproduced all 45. The first repetition's 15 exported trace/contract pairs also
matched the actual CLI's JSON and exit statuses.

The corrected SDK moves synchronous functions to a thread. It cannot automatically
fix an application's blocking code inside an async function, or a caller invoking
tools sequentially. Record inside admission controls to measure admitted work.
The cap case intentionally checks peak 2 rather than requiring all three members
to overlap. A small native test assertion may be sufficient for your application;
this example does not establish a need for another dependency.

## Boundaries and safety

The probe invokes `function_tool(...).on_invoke_tool` directly with a `ToolContext`.
Full `Runner` orchestration, model choices, approval policies, actual external tools,
production performance and non-Linux platforms were not tested. Sleeping work
demonstrates interval overlap, not useful CPU parallelism or speedup. Under heavy
load, observed timing may differ; there is no tight latency budget in these checks.

Tracing is explicitly disabled. The clean launch environment omits credentials,
and an audit hook denies socket connect, DNS lookup, sendto and bind operations;
zero attempts were observed. This is an application-level check, not OS-enforced
network isolation or a security sandbox. No real payload is captured. SDK license
and dependencies remain theirs; no SDK implementation is vendored here. AI
assistance was used to prepare and review this example.
