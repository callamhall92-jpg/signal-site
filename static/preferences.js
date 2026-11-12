// Loads a customer's choices with the private token in the link, enforces their plan's limits and saves.
(function () {
  var form = document.getElementById("prefs");
  var intro = document.getElementById("pref-intro");
  var msg = document.getElementById("pref-msg");
  var token = new URLSearchParams(location.search).get("token");
  var limits = { regions: 1, trades: 1 };
  function say(text, ok) { msg.textContent = text; msg.className = "msg " + (ok ? "good" : "bad"); }
  function boxes(name) { return Array.prototype.slice.call(form.querySelectorAll('input[name="' + name + '"]')); }
  function chosen(name) { return boxes(name).filter(function (b) { return b.checked; }).map(function (b) { return b.value; }); }
  function enforce(name) {
    var full = chosen(name).length >= limits[name];
    boxes(name).forEach(function (b) { b.disabled = full && !b.checked; });
  }
  function limitText(n, all, noun) {
    return n >= all ? "(choose any, or none for all " + noun + ")" : "(choose up to " + n + ")";
  }
  if (!token) { intro.textContent = "This link is incomplete. Open the link from one of our emails again."; return; }
  fetch(form.dataset.api + "?token=" + encodeURIComponent(token)).then(function (res) {
    if (!res.ok) throw new Error("not found");
    return res.json();
  }).then(function (p) {
    limits = { regions: p.max_regions, trades: p.max_trades };
    intro.textContent = "You are on the " + p.plan + " plan. Choose what you want tenders for; changes apply from your next alert.";
    document.getElementById("region-limit").textContent = limitText(p.max_regions, 12, "regions");
    document.getElementById("trade-limit").textContent = limitText(p.max_trades, 7, "types of work");
    boxes("regions").forEach(function (b) { b.checked = p.regions.indexOf(b.value) !== -1; });
    boxes("trades").forEach(function (b) { b.checked = p.trades.indexOf(b.value) !== -1; });
    ["regions", "trades"].forEach(function (name) {
      enforce(name);
      boxes(name).forEach(function (b) { b.addEventListener("change", function () { enforce(name); }); });
    });
    form.hidden = false;
  }).catch(function () {
    intro.textContent = "We could not find your account from this link. Open the link from your most recent email, or write to hello@noticehawk.co.uk.";
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var button = form.querySelector("button");
    button.disabled = true;
    say("Saving…", true);
    fetch(form.dataset.api, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token, regions: chosen("regions"), trades: chosen("trades") })
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (b) { return { status: res.status, body: b }; });
    }).then(function (r) {
      if (r.status === 200) say("Saved. Your next alert will use these choices.", true);
      else if (r.body.error === "too_few") say("Choose at least one region and one type of work.", false);
      else if (r.body.error === "too_many") say("That is more than your plan includes. Untick one, or upgrade from the pricing page.", false);
      else say("That did not save. Please try again in a few minutes.", false);
    }).catch(function () { say("That did not save. Check your connection and try again.", false); })
      .then(function () { button.disabled = false; });
  });
})();
