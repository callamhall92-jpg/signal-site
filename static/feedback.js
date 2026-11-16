// "Not for me": records why a tender was wrong for this subscriber, from the link in their weekly email.
(function () {
  var main = document.getElementById("main"), msg = document.getElementById("fb-msg"), box = document.getElementById("fb-reasons");
  var q = new URLSearchParams(location.search), token = q.get("t"), record = q.get("r");
  function say(text, ok) { msg.textContent = text; msg.className = "msg " + (ok ? "good" : "bad"); }
  if (!token || !record) { box.hidden = true; say("This link is incomplete. Open it again from your weekly email.", false); return; }
  box.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-reason]");
    if (!b) return;
    Array.prototype.forEach.call(box.querySelectorAll("button"), function (x) { x.disabled = true; });
    fetch(main.dataset.api, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token, record: record, reason: b.dataset.reason }) })
      .then(function (r) {
        if (r.ok) { box.hidden = true; say("Thanks. We have noted that and hidden the tender from your account page.", true); }
        else { Array.prototype.forEach.call(box.querySelectorAll("button"), function (x) { x.disabled = false; }); say("That did not save. Please try again.", false); }
      })
      .catch(function () { Array.prototype.forEach.call(box.querySelectorAll("button"), function (x) { x.disabled = false; }); say("That did not save. Check your connection and try again.", false); });
  });
})();
