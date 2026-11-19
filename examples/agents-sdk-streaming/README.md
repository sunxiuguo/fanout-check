# Check the concurrency of streamed tool calls

A stream can show three successful tool results even when those tools ran
serially. This example checks both the output of the stream and the
concurrency contract for a batch of three tools.

From the Fanout Check checkout, in a fresh Python 3.12 virtual environment:

```sh
python -m pip install . "openai-agents==0.25.0"
python examples/agents-sdk-streaming/probe.py
```

The probe uses the SDK's scripted model, not a live provider. It needs no API
key and blocks audited socket operations during the run. Both cases must
emit three tool-call events, three tool-output events and the final text
`done`. The probe also verifies that the SDK sends the three expected tool
outputs back to the model with the right call IDs.

| Tool body | Contract status | Peak overlap |
| --- | --- | --- |
| Cooperative await | Pass | 3 |
| Blocking sleep in an async function | Fail (`LIMIT_VIOLATION`) | 1 |

The command exits successfully only if both controls produce the expected
results. This is not a latency benchmark or a test of a live provider,
stream cancellation, or a rendered UI. No SDK dependency is added to the
Fanout Check package.
