# Portable replay of this Agents SDK example

This optional handoff carries exact synthetic inputs, pinned wheel dependencies
and independently recorded expected results into a subsequent clean workspace.
It reuses the existing probe and CLI. The core package remains dependency-free;
there is no service, backup system or dashboard.

## Build from a reviewed repository checkout

From the repository root, with Python 3.10+ and Git available:

```sh
python -I -B examples/agents-sdk-regression/replay/build.py
```

This standard-library command performs no dependency installation, probe run,
network request or expectation capture. It reads the selected committed source
from the checkout's **current HEAD**, checks that those working files match HEAD,
and captures the reviewed replay files. Commit or restore selected source edits
before building. Pending changes to these replay files can be built for review.
No historical source checkout or duplicated source tree is maintained here.
The archive's `source/` contains the core modules, probe, original constraints,
root README, license and project metadata; it is a selected runnable source set.

The command writes `dist/agents-sdk-replay/fanout-check-replay.tar.gz` and prints
its exact SHA-256, size and source commit. `--output PATH.tar.gz` chooses another
destination. Identical selected source and replay files produce identical archive
bytes: member order, ownership, modes and timestamps are normalized. Standard
CRLF checkout text is restored to LF; committed source blobs stay exact. Custom
Git clean/smudge filter transformations are unsupported and never invoked. Generated
archives are ignored by Git. No .git, caches, environments, logs, credentials,
assistant configuration or user data is selected.

Send the printed digest through a separately trusted channel with the archive.
The digest inside the archive does not authenticate it. This package is unsigned.
A trusted checkout and reviewed builder are prerequisites; Git IDs are not
independently verified publisher/build provenance.

## One command in a clean replay workspace

Before extracting or executing, compare the archive SHA-256 to the exact digest
obtained separately from the sender. If absent or different, do not execute it.
Inspect the generated replay code. Extract into a private fresh directory,
rejecting absolute paths, `..`, links, duplicates and noncanonical member names.
Enter `fanout-check-replay` and run:

```sh
python3.12 -I replay.py
```

Supported: Linux x86_64 **CPython 3.12.14**, standard venv/ensurepip, working
SSL/CA support, public PyPI access and roughly 500 MiB free space. Normal proxy
and CA settings may be required. The interpreter and dependencies are not bundled.
No SDK installation, pip cache, Git checkout, API key, model or real data is needed.

Before installation, replay rejects an incompatible runtime, changed manifest
or protected file, undeclared import/input files, symbolic/hard links and unsafe
inventory paths. Its manifest digest is fixed in the generated script; replacing
that script can replace its digest. This establishes consistency under trust in
the reviewed script, not authenticity of an attacker-replaced whole bundle.
Supplemental evidence cannot supply commands or imports. Checks do not prevent
concurrent hostile filesystem changes; use a private workspace.

The fixed command sequence creates three new environments, installs pinned
hash-checked wheels only, checks versions, and runs the unchanged probe. Every
child Python uses `-I -B`; the CLI imports only selected verified source.
Manifest fields and package instructions are never interpreted as commands.
Pip uses a fixed HTTPS public index, isolated settings, no source builds,
additional dependency resolution or cache. Install steps time out after 300
seconds, other run steps after 120, and metadata checks after 30.

Success exits 0 with `VERIFIED: 45/45 live cases; 15/15 exact frozen CLI reports`
and the actual source commit. Failures exit 2, with setup logs in `.replay/`;
no verified `output/` is published. Repeated runs require fresh extraction:
existing `.replay/` or `output/` is refused.

## Useful expected outputs

| Synthetic control | SDK 0.7.0 | SDK 0.8.0 | SDK 0.23.1 |
|---|---|---|---|
| Sync body, gathered calls | fail / peak 1 | pass / peak 3 | pass / peak 3 |
| Cooperative async, gathered | pass / peak 3 | pass / peak 3 | pass / peak 3 |
| Cooperative async, sequential | fail / peak 1 | fail / peak 1 | fail / peak 1 |
| Blocking sleep inside async | fail / peak 1 | fail / peak 1 | fail / peak 1 |
| Semaphore cap 2, spans inside admission | pass / peak 2 | pass / peak 2 | pass / peak 2 |

Each runs three times: 45 live assertions, including intentional failing controls.
`output/summary.json` equals the recorded oracle bytes. Three `result-*.json`
files retain newly observed intervals/contracts/reports. `output/frozen-reports/`
contains 15 complete deterministic CLI reports and `verification.json` records
counts, timing, runtime and the actual selected source commit. Live timestamps,
UUIDs and wall times vary; the semantic comparison excludes them.

The 30 input files and 16 expected files are unchanged original baseline records
from source commit `e03b9cf6eeb701505f2e714b4ac943ff3c67bf19`, captured before the
first replay implementation. The qualitative oracle was separately written from
the original README control table. Its historical `source_commit` field records
oracle provenance, while the manifest and verification receipt identify the
current source being tested. Summary SHA-256:

```text
d6a69f24cb10af3c6c28a7696a8b1630ad50e4a60e8e78dc9505e8c035363794
```

Build checks the original fixture-set fingerprint and never refreshes expected
outputs. A source change that alters recorded behavior must fail replay until
the new behavior and a separately recorded baseline are explicitly reviewed.
The frozen reports test library/CLI agreement; a separate fresh reviewer also
recomputed all 60 reports directly from intervals without importing the checker.

## Maintenance, evidence and limits

Run the repository's normal `python -m unittest discover -s tests -v` before
building; packaging tests run without SDK installs or registry access. Replay
itself is the optional integration test. For deliberate dependency updates,
retain the existing constraints and review their changes; use standard uv
`pip compile --only-binary :all: --generate-hashes --python-version 3.12.14`
on each `requirements/{070,080,0231}.in`, writing the corresponding `.txt`.
uv 0.12.19 generated the initial locks; uv is not needed to build or replay.
Do not capture expected results from the command under test. Historical pins
are for disposable example environments, not a security endorsement.

The original README baseline already worked: nine commands, 48.537 seconds,
zero interventions, 45/45 matches and no missing dependency. The handoff adds
one documented user command, complete locks and automatic exact-input/result
verification; no speedup was demonstrated. Preparation cost and original baseline
evidence remain preserved outside the repository patch rather than being bundled
as captured task logs. A prior reviewed handoff reproduced 45/15 matches in a
separate downloaded Python prefix and Debian 12 container userspace. Those runs
share the host/kernel and normal proxy/CA infrastructure; another physical host,
OS, architecture or Python version is not claimed.

Installing/importing dependencies, including wheel startup `.pth` code, executes
trusted package code. Hashes identify bytes, not safe publishers or verified
build provenance. Python/pip bootstrap, the reviewed project and pinned wheels
remain trusted. A venv and the probe's socket audit hook are not hostile-code
sandboxes or OS network isolation. This probes direct FunctionTool callbacks
with synthetic sleep work, without a model or full Runner. It establishes neither
CPU parallelism, application correctness, production speedup, external adoption
nor willingness to pay. Registry availability and compatible Python/wheels remain
external prerequisites.
