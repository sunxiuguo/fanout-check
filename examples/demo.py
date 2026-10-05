"""Run from the checkout: python -m examples.demo. No API keys or files written."""
import asyncio
import time

from fanout_check import Recorder, check
from fanout_check.cli import render_text

CONTRACT = {"version": 1, "groups": [{
    "name": "research", "members": ["docs", "code", "tests"], "min_peak": 3,
}]}


async def run(blocking):
    recorder = Recorder()
    ready = asyncio.Event()
    entered = 0

    async def tool(name):
        nonlocal entered
        with recorder.span(name, group="research"):
            if blocking:
                # A blocking operation inside async code serializes the event loop.
                time.sleep(0.02)
            else:
                # The barrier makes this demonstration independent of scheduler speed.
                entered += 1
                if entered == 3:
                    ready.set()
                await ready.wait()
                await asyncio.sleep(0.02)

    await asyncio.gather(*(tool(name) for name in ("docs", "code", "tests")))
    return check(recorder.trace(), CONTRACT)


def main():
    broken = asyncio.run(run(blocking=True))
    fixed = asyncio.run(run(blocking=False))
    print("Blocking tool bodies, even though called with gather:")
    print(render_text(broken))
    print("\nCooperative tool bodies:")
    print(render_text(fixed))
    if broken["status"] != "fail" or fixed["status"] != "pass":
        raise SystemExit("Unexpected demo result")
    print("\nExpected failure and passing control verified. No model calls were made.")


if __name__ == "__main__":
    main()
