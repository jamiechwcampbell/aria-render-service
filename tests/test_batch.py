"""Offline tests for app/batch.py (stdlib only: python3 -m unittest tests.test_batch)."""
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from app import batch


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_renderer(tmp: Path, clock: Clock, sizes: dict, seconds: float = 60, fail: set = ()):
    def render_fn(fields):
        jid = fields["voiceover"]
        clock.t += seconds
        if jid in fail:
            raise RuntimeError(f"boom {jid}")
        p = tmp / f"{jid}.mp4"
        p.write_bytes(b"x" * sizes.get(jid, 1000))
        return {"outputs": {"full.mp4": {"path": str(p)}, "silent.mp4": {"path": str(p)}}, "qa": {"ok": True}}
    return render_fn


def job(jid, **kw):
    return {"job_id": jid, "video_url": "https://example.invalid/v.mp4", "voiceover": jid, **kw}


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmpd = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpd.name)
        self.clock = Clock()

    def tearDown(self):
        self.tmpd.cleanup()

    def test_validation(self):
        for bad in [{}, {"jobs": []}, {"jobs": [{"voiceover": "a"}]},
                    {"jobs": [job("a"), job("a")]},
                    {"jobs": [job("a", upload_url="http://plain")]},
                    {"jobs": [job(str(i)) for i in range(batch.MAX_JOBS + 1)]}]:
            with self.assertRaises(ValueError):
                batch.validate_batch(bad)

    def test_runs_all_jobs_and_strips_control_keys(self):
        seen = []
        base = make_renderer(self.tmp, self.clock, {})

        def render_fn(fields):
            seen.append(sorted(fields))
            return base(fields)
        out = batch.run_batch({"jobs": [job("a", est_seconds=5), job("b")]}, render_fn, clock=self.clock)
        self.assertEqual(out["counts"], {"succeeded": 2})
        self.assertTrue(all("job_id" not in f and "est_seconds" not in f for f in seen))
        a = out["jobs"][0]
        self.assertEqual(a["qa"], {"ok": True})
        self.assertIn("base64", a["outputs"]["full.mp4"])
        self.assertNotIn("base64", a["outputs"]["silent.mp4"])
        self.assertEqual(a["outputs"]["full.mp4"]["sha256"], hashlib.sha256(b"x" * 1000).hexdigest())

    def test_failure_is_isolated(self):
        r = make_renderer(self.tmp, self.clock, {}, fail={"b"})
        out = batch.run_batch({"jobs": [job("a"), job("b"), job("c")]}, r, clock=self.clock)
        self.assertEqual([j["status"] for j in out["jobs"]], ["succeeded", "failed", "succeeded"])
        self.assertIn("boom b", out["jobs"][1]["error"])

    def test_deadline_leaves_jobs_not_started(self):
        r = make_renderer(self.tmp, self.clock, {}, seconds=100)
        out = batch.run_batch({"deadline_s": 250, "jobs": [job("a", est_seconds=100), job("b", est_seconds=100),
                                                            job("c", est_seconds=100)]}, r, clock=self.clock)
        self.assertEqual([j["status"] for j in out["jobs"]], ["succeeded", "succeeded", "not_started"])

    def test_inline_cap_skips_base64_when_result_would_be_too_big(self):
        big = 6 * 1024 * 1024
        r = make_renderer(self.tmp, self.clock, {"a": big, "b": big})
        out = batch.run_batch({"jobs": [job("a"), job("b")]}, r, clock=self.clock)
        self.assertIn("base64", out["jobs"][0]["outputs"]["full.mp4"])
        self.assertIn("base64_skipped", out["jobs"][1]["outputs"]["full.mp4"])
        total_b64 = sum(len(j["outputs"]["full.mp4"].get("base64", "")) for j in out["jobs"])
        self.assertLess(total_b64, batch.RESULT_CAP_BYTES)

    def test_upload_url_uses_put_and_no_base64(self):
        calls = []

        def put(url, path, headers=None):
            calls.append((url, Path(path).name, headers))
            return 200
        r = make_renderer(self.tmp, self.clock, {})
        out = batch.run_batch({"jobs": [job("a", upload_url="https://up.invalid/a", upload_headers={"x": "1"})]},
                              r, put_fn=put, clock=self.clock)
        item = out["jobs"][0]["outputs"]["full.mp4"]
        self.assertTrue(item["uploaded"])
        self.assertNotIn("base64", item)
        self.assertEqual(calls, [("https://up.invalid/a", "a.mp4", {"x": "1"})])

    def test_upload_failure_marks_job_failed_infra(self):
        def put(url, path, headers=None):
            raise OSError("network down")
        r = make_renderer(self.tmp, self.clock, {})
        out = batch.run_batch({"jobs": [job("a", upload_url="https://up.invalid/a")]}, r, put_fn=put, clock=self.clock)
        self.assertEqual(out["jobs"][0]["status"], "failed")
        self.assertEqual(out["jobs"][0]["error_class"], "infra")

    def test_base64_roundtrip(self):
        r = make_renderer(self.tmp, self.clock, {"a": 10})
        out = batch.run_batch({"jobs": [job("a")]}, r, clock=self.clock)
        self.assertEqual(base64.b64decode(out["jobs"][0]["outputs"]["full.mp4"]["base64"]), b"x" * 10)


if __name__ == "__main__":
    unittest.main()
