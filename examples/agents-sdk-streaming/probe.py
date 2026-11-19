"""Test a streamed tool batch and its trace with no live provider."""
import asyncio
import json
import sys
import time
from importlib.metadata import version

from fanout_check import Recorder, check

network_events = []

def reject_network(event, _args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                 "socket.sendto", "socket.bind"}:
        network_events.append(event)
        raise RuntimeError("Unexpected network access")


async def exercise(blocking: bool) -> dict:
    from agents import Agent, Runner, RunConfig, function_tool
    from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

    recorder = Recorder()

    @function_tool
    async def work(label: str) -> str:
        """Perform one synthetic unit of work."""
        with recorder.span(label, group="lookup"):
            if blocking:
                time.sleep(0.04)
            else:
                await asyncio.sleep(0.04)
        return label

    calls = [function_call(work.name, {"label": label}, call_id=f"call-{label}")
             for label in "abc"]
    model = ScriptedModel([ModelStep(output=calls, response_id="calls"),
                           ModelStep(output=[assistant_message("done")],
                                     response_id="reply")])
    result = Runner.run_streamed(Agent(name="test", model=model, tools=[work]),
                                "run the synthetic batch", max_turns=3,
                                run_config=RunConfig(tracing_disabled=True))
    seen = {"tool_called": 0, "tool_output": 0}
    deltas = []
    async for event in result.stream_events():
        if event.type == "run_item_stream_event" and event.name in seen:
            seen[event.name] += 1
        if event.type == "raw_response_event" and event.data.type == "response.output_text.delta":
            deltas.append(event.data.delta)
    model.assert_complete()
    assert len(model.calls) == 2 and all(call.streamed for call in model.calls)
    assert result.final_output == "done" and "".join(deltas) == "done"
    assert seen == {"tool_called": 3, "tool_output": 3}, seen
    outputs = sorted((i["call_id"], i["output"]) for i in model.calls[1].input
                     if isinstance(i, dict) and i.get("type") == "function_call_output")
    assert outputs == [(f"call-{label}", label) for label in "abc"], outputs
    report = check(recorder.trace(), {"version": 1, "groups": [
        {"name": "lookup", "members": list("abc"), "min_peak": 3}
    ]})
    info = dict(status=report["status"], peak=report["groups"][0]["metrics"]["peak"],
                codes=[item["code"] for item in report["findings"]], **seen)
    want = ("fail", 1, ["LIMIT_VIOLATION"]) if blocking else ("pass", 3, [])
    assert (info["status"], info["peak"], info["codes"]) == want, info
    return info


async def main():
    sdk = version("openai-agents")
    assert sdk == "0.25.0", sdk
    results = {mode: await asyncio.wait_for(exercise(blocking), 10)
               for mode, blocking in (("cooperative", False), ("blocking", True))}
    assert not network_events, network_events
    print(json.dumps(dict(sdk=sdk, results=results, network_events=network_events), indent=2))


if __name__ == "__main__":
    sys.addaudithook(reject_network)
    from agents import set_trace_provider
    from agents.tracing.provider import DefaultTraceProvider

    # Use no exporter; the SDK's default exporter can initialize an HTTP client.
    provider = DefaultTraceProvider()
    provider.set_disabled(True)
    set_trace_provider(provider)
    asyncio.run(main())
