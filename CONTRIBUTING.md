# Contributing

Keep this a small, offline timing-contract tool. Before adding an SDK adapter, open an issue with a public or synthetic trace shape and the application-level check it enables. Do not upload private prompts, customer data, API keys, or production traces without sanitizing them.

Run `python -m unittest discover -s tests -v`, `python -m examples.demo`, and `python -m compileall -q fanout_check` before proposing changes. New checks need a failing case and a nearby passing control. Endpoint ties, zero-duration calls, missing members, cancellation, and incomplete traces deserve explicit tests.

A timing assertion must not imply semantic correctness or causal independence. Keep every collection feature opt-in and payload-free. The package has no runtime dependencies; preserve that unless a demonstrated need justifies changing it.
