"""The page's one script, run under Node against a stand-in page (PRD FR-017 criterion 3, SEC-16; Phase 6 step 4).

The script polls a run that is going and reloads the page when it has ended. Node is only a test tool here (skipped when it is not installed);
nothing in the service needs it.
"""

import json
import shutil
import subprocess

import pytest

from credit_intel.api.pages import STATIC

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")

HARNESS = r"""
const fs = require("fs");
const scenario = JSON.parse(process.argv[2]);
const log = { fetches: [], timers: [], reloads: 0, text: [], unsafe: [] };
const stateEl = {};
Object.defineProperty(stateEl, "textContent", { set(v) { log.text.push(v); }, get() { return ""; } });
for (const name of ["innerHTML", "outerHTML"]) Object.defineProperty(stateEl, name, { set(v) { log.unsafe.push(name); } });
const holder = { dataset: { runId: scenario.runId, final: scenario.final } };
global.document = { getElementById: (id) => (id === "run" && !scenario.noHolder ? holder : id === "state" ? stateEl : null) };
const replies = scenario.replies.slice();
global.fetch = (url, options) => {
  log.fetches.push({ url, accept: options.headers.Accept, cache: options.cache });
  const next = replies.shift();
  if (next === "reject") return Promise.reject(new Error("network"));
  return Promise.resolve({ ok: next.ok, json: () => Promise.resolve(next.body) });
};
const pending = [];
global.window = { setTimeout: (fn, ms) => { pending.push({ fn, ms }); log.timers.push(ms); return pending.length; }, location: { reload() { log.reloads += 1; } } };
eval(fs.readFileSync(process.argv[3], "utf8"));
(async () => {
  for (let i = 0; i < 12 && pending.length; i++) {
    pending.shift().fn();
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(JSON.stringify({ ...log, left: pending.length }));
})();
"""


def run(tmp_path, *, replies, final="false", run_id="20261030T101530.123456Z-abcdef12", no_holder=False):
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    scenario = json.dumps({"replies": replies, "final": final, "runId": run_id, "noHolder": no_holder})
    done = subprocess.run(["node", str(harness), scenario, str(STATIC / "app.js")], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(done.stdout)


def test_a_finished_page_does_nothing(tmp_path):
    out = run(tmp_path, replies=[], final="true")
    assert out["fetches"] == [] and out["timers"] == [] and out["reloads"] == 0


def test_a_page_with_no_run_on_it_does_nothing(tmp_path):
    out = run(tmp_path, replies=[], no_holder=True)
    assert out["fetches"] == [] and out["timers"] == []


def test_a_run_going_is_polled_at_its_own_address_and_its_state_shown_as_text_until_it_ends(tmp_path):
    ok = lambda state, **extra: {"ok": True, "body": {"state": state, **extra}}  # noqa: E731
    out = run(tmp_path, replies=[ok("received"), ok("fields_extracted"), ok("exported")], run_id="a b/c")
    assert [f["url"] for f in out["fetches"]] == ["/runs/a%20b%2Fc"] * 3  # the ID is encoded, and only this service is called
    assert {f["accept"] for f in out["fetches"]} == {"application/json"} and {f["cache"] for f in out["fetches"]} == {"no-store"}
    assert out["text"] == ["received", "fields_extracted"] and out["reloads"] == 1 and out["unsafe"] == []
    assert out["timers"] == [1500, 2000, 2000] and out["left"] == 0  # a first wait, then every two seconds, and nothing after the reload


def test_a_failed_run_also_reloads_the_page(tmp_path):
    out = run(tmp_path, replies=[{"ok": True, "body": {"state": "failed"}}])
    assert out["reloads"] == 1 and out["text"] == [] and out["left"] == 0


def test_a_run_past_its_time_limit_says_so_in_text(tmp_path):
    out = run(tmp_path, replies=[{"ok": True, "body": {"state": "text_extracted", "deadline_passed": True}}, {"ok": True, "body": {"state": "failed"}}])
    assert out["text"] == ["text_extracted (past the time limit; stopping)"] and out["unsafe"] == []


def test_markup_in_a_state_is_written_as_text_and_never_as_html(tmp_path):
    out = run(tmp_path, replies=[{"ok": True, "body": {"state": "<img src=x onerror=alert(1)>"}}, "reject", "reject", "reject"])
    assert out["text"][0] == "<img src=x onerror=alert(1)>" and out["unsafe"] == []


@pytest.mark.parametrize("bad", ["reject", {"ok": False, "body": {}}])
def test_three_failures_in_a_row_stop_the_polling_and_say_to_reload_and_a_success_resets_the_count(tmp_path, bad):
    out = run(tmp_path, replies=[bad, bad, bad, bad, bad])
    assert out["text"] == ["the status could not be read; reload the page"] and len(out["fetches"]) == 3 and out["left"] == 0
    ok = {"ok": True, "body": {"state": "validated"}}
    again = run(tmp_path, replies=[bad, bad, ok, bad, bad, ok, "reject", "reject", "reject"])
    assert again["text"] == ["validated", "validated", "the status could not be read; reload the page"] and len(again["fetches"]) == 9
