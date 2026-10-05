import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_core import contract, span, trace


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.c = self.directory / "contract.json"
        self.c.write_text(json.dumps(contract()), encoding="utf-8")

    def run_cli(self, data, *args):
        return subprocess.run([sys.executable, "-m", "fanout_check", "-", "--contract", str(self.c), *args], input=data, text=True, capture_output=True)

    def test_pass(self):
        p = self.run_cli(json.dumps(trace(span("a"), span("b"))), "--format", "json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"], "pass")

    def test_fail(self):
        p = self.run_cli(json.dumps(trace(span("a", 0, 10), span("b", 10, 20))))
        self.assertEqual(p.returncode, 1)
        self.assertIn("LIMIT_VIOLATION", p.stdout)

    def test_inconclusive(self):
        p = self.run_cli(json.dumps(trace(span("a", end=None, status="running"), span("b"))), "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["status"], "inconclusive")

    def test_malformed_json(self):
        p = self.run_cli('{secret broken', "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("secret", p.stdout)

    def test_duplicate_keys_rejected(self):
        p = self.run_cli('{"version":1,"version":1}', "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("duplicate JSON field", p.stdout)

    def test_nonfinite_rejected(self):
        p = self.run_cli('{"x":NaN}', "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("non-finite", p.stdout)

    def test_tiny_positive_limit_never_underflows_to_pass(self):
        self.c.write_text('{"version":1,"groups":[{"name":"batch","members":["a","b"],"min_overlap_ms":1e-400}]}', encoding="utf-8")
        p = self.run_cli(json.dumps(trace(span("a", 0, 10), span("b", 10, 20))), "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["status"], "invalid")
        self.assertIn("precision", p.stdout)

    def test_cli_exact_decimal_comparison(self):
        self.c.write_text('{"version":1,"groups":[{"name":"batch","members":["a","b"],"min_overlap_ratio":0.3333333333333333334}]}', encoding="utf-8")
        p = self.run_cli(json.dumps(trace(span("a", 0, 3), span("b", 2, 5))), "--format", "json")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["findings"][0]["expected"], "0.3333333333333333334")

    def test_unsupported_unicode_labels_are_invalid_in_both_formats(self):
        for character in ("\ud800", "\udfff", "\u0085", "\u202e", "\u2028"):
            t = trace(span("a"), span("b"))
            t["spans"][0]["group"] = "batch" + character
            for format in ("text", "json"):
                p = self.run_cli(json.dumps(t), "--format", format)
                self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
                self.assertNotIn("Traceback", p.stderr)

    def test_text_report_survives_ascii_stdout(self):
        c = contract()
        c["groups"][0]["name"] = "batch猫"
        c["groups"][0]["members"] = ["猫", "b"]
        self.c.write_text(json.dumps(c), encoding="utf-8")
        t = trace(span("猫", group="batch猫"))
        p = subprocess.run([sys.executable, "-m", "fanout_check", "-", "--contract", str(self.c)], input=json.dumps(t), text=True, capture_output=True, env={**os.environ, "PYTHONIOENCODING": "ascii"})
        self.assertEqual(p.returncode, 1)
        self.assertIn("batch\\u732b", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_help_never_reads_or_writes_files(self):
        p = subprocess.run([sys.executable, "-m", "fanout_check", "nonexistent", "--contract", "nonexistent", "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("No model calls or file writes", " ".join(p.stdout.split()))

    def test_two_stdin_inputs(self):
        p = subprocess.run([sys.executable, "-m", "fanout_check", "-", "--contract", "-", "--format", "json"], input="", text=True, capture_output=True)
        self.assertEqual(p.returncode, 2)

    def test_input_unchanged(self):
        source = self.directory / "trace.json"
        source.write_text(json.dumps(trace(span("a"), span("b"))), encoding="utf-8")
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        p = subprocess.run([sys.executable, "-m", "fanout_check", str(source), "--contract", str(self.c)], capture_output=True)
        self.assertEqual(p.returncode, 0)
        after = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        self.assertEqual(before, after)

    def test_oversize_input(self):
        p = self.run_cli(" " * (10 * 1024 * 1024 + 1), "--format", "json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("10 MiB", p.stdout)
