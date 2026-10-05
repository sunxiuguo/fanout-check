# Problem evidence and scope

Checked 5 October 2026. This is a product hypothesis, not evidence of adoption.

## Primary reports

- [openai/openai-agents-python #2386](https://github.com/openai/openai-agents-python/issues/2386): a user reported sync tool bodies blocking the event loop and serializing fan-out. Opened 31 January 2026, closed/completed 3 February 2026. Historical regression class, not an unresolved SDK bug
- [openai/openai-agents-python #1859](https://github.com/openai/openai-agents-python/issues/1859): a separate user requested a maximum parallel-tool-call count. Closed/completed 6 May 2026. A cap is a behavior worth testing, not an absent feature we claim to supply
- [langfuse/langfuse #7200](https://github.com/langfuse/langfuse/issues/7200) and [#11941](https://github.com/langfuse/langfuse/issues/11941): reports about graph visualization of parallel branches and parent-child spans. These motivate making grouping explicit. This tool neither reproduces nor fixes those UI defects

The runnable demonstration is original synthetic asyncio code, inspired by the general blocking-I/O failure class. It does not run an affected SDK version or copy a user's private trace.

## Existing tools and rejected directions

- [skill-overlay](https://github.com/luw2007/skill-overlay) already covers offline three-way updates for customized skills. An update-merger project was rejected as duplicative
- [drskill](https://github.com/dbreunig/drskill) covers skill auditing, activation evidence, and installed-skill checks. A generic skills doctor was rejected
- [evalstats](https://github.com/ianarawjo/promptstats) and [clavis-systems/evalstats](https://github.com/clavis-systems/evalstats) cover statistical evaluation comparisons. A new paired-score evaluator was rejected
- [Tracetest](https://github.com/kubeshop/tracetest), [Perfetto](https://perfetto.dev/), and trace observability platforms are much broader solutions. Prefer them when you need collection, exploration, full trace assertions, distributed-clock analysis, or visualization
- [trace2test](https://github.com/felmonon/trace2test) and [agentprdiff](https://agentprdiff.dev/) cover broader agent behavior regression workflows

The small niche here is explicit, same-clock sibling-call timing contracts in a local test: membership, overlap, launch skew, completion, and caps. A search cannot establish that no competitor implements these checks. There is no claim of a novel interval algorithm.

## Experiment boundary

Initial effort is capped at this dependency-free library, strict CLI, original demo, and independently reviewed tests. No provider integrations, hosted backend, paid service, or promotional outreach is bundled into this release.

After publication, look for independent usage reports and concrete requests from people instrumenting real fan-outs. Within 30 days, two independent reports of a caught regression or a maintained test integration would justify further adapters. Absent useful evidence, keep the small project available but do not expand into a general trace platform. Stars are observable interest, not proof of value, and no growth outcome is promised.

## Clock reference

[Python time documentation](https://docs.python.org/3/library/time.html#time.perf_counter_ns) documents the monotonic performance-counter clock and integer-nanosecond variant. [Python asyncio documentation](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread) explains blocking I/O and thread offloading. Measurement instrumentation remains the application's responsibility.
