// Polls a run that is still going and reloads the page when it has finished. It writes only text it was sent as JSON (textContent), never markup.
(function () {
  var holder = document.getElementById("run");
  if (!holder || holder.dataset.final === "true") { return; }
  var state = document.getElementById("state");
  var failures = 0;
  function poll() {
    fetch("/runs/" + encodeURIComponent(holder.dataset.runId), { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (answer) { if (!answer.ok) { throw new Error("status"); } return answer.json(); })
      .then(function (body) {
        failures = 0;
        if (body.state === "exported" || body.state === "failed") { window.location.reload(); return; }
        state.textContent = body.state + (body.deadline_passed ? " (past the time limit; stopping)" : "");
        window.setTimeout(poll, 2000);
      })
      .catch(function () {
        failures += 1;
        if (failures >= 3) { state.textContent = "the status could not be read; reload the page"; return; }
        window.setTimeout(poll, 4000);
      });
  }
  window.setTimeout(poll, 1500);
})();
