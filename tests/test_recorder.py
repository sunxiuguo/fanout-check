import asyncio
from concurrent.futures import ThreadPoolExecutor
import unittest

from fanout_check import Recorder, check


class RecorderTests(unittest.TestCase):
    def test_records_success_without_payload(self):
        r = Recorder()
        with r.span("a", group="test"):
            inside = r.trace()
        self.assertEqual(inside["spans"][0]["status"], "running")
        self.assertIsNone(inside["spans"][0]["end_ns"])
        after = r.trace()
        self.assertEqual(after["spans"][0]["status"], "ok")
        self.assertGreaterEqual(after["spans"][0]["end_ns"], after["spans"][0]["start_ns"])
        after["spans"][0]["status"] = "error"
        self.assertEqual(r.trace()["spans"][0]["status"], "ok")

    def test_exception_is_rethrown_without_recording_message(self):
        r = Recorder()
        with self.assertRaisesRegex(RuntimeError, "private payload"):
            with r.span("a", group="test"):
                raise RuntimeError("private payload")
        self.assertEqual(r.trace()["spans"][0]["status"], "error")
        self.assertNotIn("private payload", str(r.trace()))

    def test_cancellation_is_rethrown(self):
        r = Recorder()
        async def run():
            with r.span("a", group="test"):
                raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(run())
        self.assertEqual(r.trace()["spans"][0]["status"], "cancelled")

    def test_thread_safe_ids(self):
        r = Recorder()
        def work(i):
            with r.span(str(i), group="threads"):
                pass
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(100)))
        spans = r.trace()["spans"]
        self.assertEqual(len({s["id"] for s in spans}), 100)
        self.assertTrue(all(s["status"] == "ok" for s in spans))

    def test_async_overlap(self):
        r = Recorder()
        async def run():
            ready = asyncio.Event()
            entered = 0
            async def work(name):
                nonlocal entered
                with r.span(name, group="batch"):
                    entered += 1
                    if entered == 2:
                        ready.set()
                    await ready.wait()
                    await asyncio.sleep(0)
            await asyncio.gather(work("a"), work("b"))
        asyncio.run(run())
        c = dict(version=1, groups=[dict(name="batch", members=["a", "b"], min_peak=2)])
        self.assertEqual(check(r.trace(), c)["status"], "pass")
