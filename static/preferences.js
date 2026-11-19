// Loads a customer's choices with the private token in the link, enforces their plan's limits and saves.
(function () {
  var form = document.getElementById("prefs");
  var intro = document.getElementById("pref-intro");
  var msg = document.getElementById("pref-msg");
  var token = new URLSearchParams(location.search).get("token");
  var limits = { regions: 1, trades: 1 };
  var watch = false, fit = false, profile = false, copyOn = false;
  function lines(id) {
    return document.getElementById(id).value.split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
  }
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
  if (!token) {
    intro.textContent = "This link is incomplete. Open the link from one of our emails again, or ";
    var a = document.createElement("a"); a.href = "/login/"; a.textContent = "sign in with your email address";
    intro.appendChild(a); intro.appendChild(document.createTextNode(" and change your choices from your account page."));
    return;
  }
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
    if (p.fit) {
      fit = true;
      document.getElementById("fit").hidden = false;
      ["min_value", "max_value"].forEach(function (id) {
        var el = document.getElementById(id), v = p[id] === null || p[id] === undefined ? "" : String(Math.round(Number(p[id])));
        if (v && !Array.prototype.some.call(el.options, function (o) { return o.value === v; })) el.add(new Option("£" + Number(v).toLocaleString("en-GB"), v));
        el.value = v;
      });
    }
    if (p.fit && p.profile) {
      profile = true;
      document.getElementById("profile").hidden = false;
      document.getElementById("base_postcode").value = p.profile.base_postcode || "";
      var miles = document.getElementById("max_miles"), m = p.profile.max_miles ? String(p.profile.max_miles) : "";
      if (m && !Array.prototype.some.call(miles.options, function (o) { return o.value === m; })) miles.add(new Option(m + " miles", m));
      miles.value = m;
      document.getElementById("specialisms").value = (p.profile.specialisms || []).join("\n");
      document.getElementById("avoid").value = (p.profile.avoid || []).join("\n");
      document.getElementById("skip_frameworks").checked = !!p.profile.skip_frameworks;
    }
    if (p.max_keywords > 0 || p.max_competitors > 0) {
      watch = true;
      document.getElementById("watch").hidden = false;
      document.getElementById("keyword-limit").textContent = "(up to " + p.max_keywords + ")";
      document.getElementById("competitor-limit").textContent = "(up to " + p.max_competitors + ")";
      document.getElementById("keywords").value = (p.keywords || []).join("\n");
      document.getElementById("competitors").value = (p.competitors || []).join("\n");
      document.getElementById("buyer-limit").textContent = "(up to " + (p.max_buyers || 0) + ")";
      document.getElementById("buyers").value = (p.buyers || []).join("\n");
    }
    if (p.fit) {
      copyOn = true;
      document.getElementById("copy").hidden = false;
      copyState(p.copy);
    }
    form.hidden = false;
  }).catch(function () {
    intro.textContent = "We could not find your account from this link. Open the link from your most recent email, or write to hello@noticehawk.co.uk.";
  });
  function copyState(c) {
    document.getElementById("copy_email").value = c && c.email ? c.email : "";
    document.getElementById("copy-state").textContent = !c || !c.email ? "" :
      c.confirmed ? "Confirmed. They get a copy of every alert." : "Waiting for them to confirm from the email we sent.";
  }
  function payload() {
    var body = { token: token, regions: chosen("regions"), trades: chosen("trades") };
    if (watch) { body.keywords = lines("keywords"); body.competitors = lines("competitors"); body.buyers = lines("buyers"); }
    if (fit) {
      body.min_value = document.getElementById("min_value").value || null;
      body.max_value = document.getElementById("max_value").value || null;
    }
    if (profile) {
      body.profile = { base_postcode: document.getElementById("base_postcode").value.trim(),
        max_miles: document.getElementById("max_miles").value ? Number(document.getElementById("max_miles").value) : null,
        specialisms: lines("specialisms"), avoid: lines("avoid"), skip_frameworks: document.getElementById("skip_frameworks").checked };
    }
    if (copyOn) body.copy_email = document.getElementById("copy_email").value.trim();
    return body;
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var button = form.querySelector("button");
    button.disabled = true;
    say("Saving…", true);
    fetch(form.dataset.api, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload())
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (b) { return { status: res.status, body: b }; });
    }).then(function (r) {
      if (r.status === 200) {
        if (r.body.copy === "asked") { say("Saved. We have emailed the second address to ask them to confirm.", true); document.getElementById("copy-state").textContent = "Waiting for them to confirm from the email we sent."; }
        else if (r.body.copy === "not_sent") say("Saved, but the email to the second address did not send. Save again to retry.", false);
        else { if (r.body.copy === "cleared") document.getElementById("copy-state").textContent = ""; say("Saved. Your next alert will use these choices.", true); }
      }
      else if (r.body.error === "copy_bad_email") say("The second email address does not look right. Check it and save again.", false);
      else if (r.body.error === "copy_same") say("The second address is the one your alerts already go to. Enter a different one or leave it blank.", false);
      else if (r.body.error === "copy_suppressed") say("That address has asked not to receive our emails, so we cannot add it.", false);
      else if (r.body.error === "too_few") say("Choose at least one region and one type of work.", false);
      else if (r.body.error === "watch_too_many") say("That is more keywords, competitors or buyers than your plan includes. Remove some and save again.", false);
      else if (r.body.error === "profile_bad_postcode") say("We could not find that postcode. Check it and save again, or leave it blank.", false);
      else if (r.body.error === "profile_too_many") say("Up to 8 specialisms and 8 things to leave out. Remove some and save again.", false);
      else if (r.body.error === "profile_bad_length") say("Each specialism or thing to leave out needs to be between 3 and 40 characters.", false);
      else if (r.body.error === "fit_bad_range") say("The smallest contract needs to be less than the largest.", false);
      else if (r.body.error === "watch_bad_length") say("Each keyword or name needs to be between 3 and 60 characters.", false);
      else if (r.body.error === "too_many") say("That is more than your plan includes. Untick one, or upgrade from the pricing page.", false);
      else say("That did not save. Please try again in a few minutes.", false);
    }).catch(function () { say("That did not save. Check your connection and try again.", false); })
      .then(function () { button.disabled = false; });
  });
})();
