// A paying customer's account page: live matches with filters, planned procurements and renewals.
(function () {
  var main = document.getElementById("main");
  var token = new URLSearchParams(location.search).get("token") || "";
  var state = { data: null, tab: "tenders" };
  var LABELS = { new_build: "New build", refurbishment: "Refurbishment", repairs_maintenance: "Repairs and maintenance",
    roofing: "Roofing", mechanical_electrical: "Mechanical and electrical", groundworks_civils: "Groundworks and civils",
    design_professional: "Design and professional" };
  var PARTS = [["fit", "Fit with your work"], ["value", "Contract size"], ["time", "Time to bid"], ["sme", "Suits smaller firms"], ["detail", "Detail in the notice"]];
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function money(v) {
    if (v === null || v === undefined) return "Value not stated";
    v = Number(v);
    if (v >= 1e6) return "£" + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "m";
    if (v >= 1e3) return "£" + Math.round(v / 1e3) + "k";
    return "£" + Math.round(v);
  }
  function nice(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }
  function monthYear(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }); }
  function safeUrl(u) { return /^https:\/\/www\.(find-tender|contractsfinder)\.service\.gov\.uk\//.test(u || "") ? u : null; }

  // The same adjustment the weekly email makes for the contract sizes a customer says they take on.
  function sizePoints(value, low, high, full) {
    if (high !== null && value > high) {
      var over = value / high;
      return [Math.round(full * (over <= 1.5 ? 0.6 : over <= 3 ? 0.3 : 0.1)), "Bigger than the largest contract you said you take on"];
    }
    if (low !== null && value < low) return [Math.round(full * (value >= low * 0.5 ? 0.6 : 0.2)), "Smaller than the contracts you said are worth bidding for"];
    return [full, null];
  }
  function personalise(list, low, high) {
    if (low === null && high === null) return list;
    return list.map(function (t) {
      if (t.value === null || !t.parts || !t.parts.value) return t;
      var p = sizePoints(Number(t.value), low, high, t.parts.value[1]);
      var parts = Object.assign({}, t.parts, { value: [p[0], t.parts.value[1]] });
      return Object.assign({}, t, { score: Math.max(0, Math.min(100, t.score - t.parts.value[0] + p[0])), parts: parts, fitNote: p[1] });
    }).sort(function (a, b) { return b.score - a.score || a.days - b.days; });
  }

  function intelLines(i) {
    var out = [];
    if (!i) return out;
    if (i.previous) {
      out.push(["Last time", "A similar contract, “" + i.previous.title.slice(0, 90) + "”, went to " + i.previous.winners.slice(0, 2).join(" and ") +
        (i.previous.value ? " for " + money(i.previous.value) : "") + " in " + monthYear(i.previous.awarded_on) + "."]);
    }
    var b = i.buyer;
    if (b) {
      var kind = b.same_type ? "contracts of this type" : "construction contracts", firms = b.winners + " different firm" + (b.winners === 1 ? "" : "s"), text;
      if (b.pattern === "one_firm") text = b.top_winner + " won " + b.top_wins + " of this buyer's last " + b.awards + " " + kind + ". A hard field to break into";
      else if (b.pattern === "regulars") text = Math.round(b.repeat_share * 100) + "% of this buyer's last " + b.awards + " " + kind + " went to firms it had used before (" + firms + " in all). It favours its regulars";
      else if (b.pattern === "open") text = "This buyer's last " + b.awards + " " + kind + " went to " + firms + ". An open field";
      else text = b.awards + " recent " + kind + ", awarded to " + firms;
      if (b.typical_value) text += ". Typical value " + money(b.typical_value);
      out.push(["This buyer", text + "."]);
    }
    if (i.area && i.area.leaders && i.area.leaders.length) {
      out.push(["Who wins locally", "Across " + i.area.buyers + " buyers in this region, " + i.area.awards + " recent contracts of this type went to " +
        i.area.winners + " firms. Most wins: " + i.area.leaders.map(function (l) { return l[0] + " (" + l[1] + ")"; }).join(", ") + "."]);
    }
    return out;
  }

  function line(parent, label, text, cls) {
    var p = el("p", cls || "why");
    var s = el("strong", null, label + ": "); p.appendChild(s); p.appendChild(document.createTextNode(text)); parent.appendChild(p);
  }
  function card(t) {
    var item = el("div", "mail-item"), body = el("div");
    item.appendChild(el("span", "score " + (t.score >= 80 ? "high" : t.score >= 60 ? "mid" : "low"), String(t.score)));
    var url = safeUrl(t.url), a = el(url ? "a" : "span", null, t.title);
    if (url) { a.href = url; a.rel = "noopener"; a.target = "_blank"; }
    body.appendChild(a);
    body.appendChild(el("p", null, t.buyer || "Buyer not stated"));
    body.appendChild(el("p", null, [t.region, LABELS[t.category], money(t.value), "closes " + nice(t.deadline) + " (" + t.days + " day" + (t.days === 1 ? "" : "s") + ")"].filter(Boolean).join(" | ")));
    if (t.note) line(body, "Our read", t.note, "read");
    intelLines(t.intel).forEach(function (l) { line(body, l[0], l[1]); });
    if (t.fitNote) line(body, "Check first", t.fitNote + ".", "check");
    if (t.parts) body.appendChild(el("p", "why", PARTS.filter(function (p) { return t.parts[p[0]]; }).map(function (p) { return p[1] + " " + t.parts[p[0]][0] + "/" + t.parts[p[0]][1]; }).join(" · ")));
    var b = el("button", "linkish", t.shortlisted ? "On your shortlist. Remove" : "Remind me before this closes");
    b.type = "button";
    b.addEventListener("click", function () {
      b.disabled = true;
      fetch(main.dataset.shortlist, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token, record: t.id, action: t.shortlisted ? "remove" : "add" }) })
        .then(function (r) { if (r.ok) { t.shortlisted = !t.shortlisted; render(); } else { b.disabled = false; b.textContent = "That did not save. Try again"; } })
        .catch(function () { b.disabled = false; b.textContent = "That did not save. Try again"; });
    });
    body.appendChild(b);
    item.appendChild(body);
    return item;
  }
  function simpleCard(title, url, lines) {
    var item = el("div", "mail-item"), body = el("div"), u = safeUrl(url), a = el(u ? "a" : "span", null, title);
    if (u) { a.href = u; a.rel = "noopener"; a.target = "_blank"; }
    body.appendChild(a);
    lines.filter(Boolean).forEach(function (l) { body.appendChild(el("p", null, l)); });
    item.appendChild(body);
    return item;
  }

  function filtered() {
    var d = state.data, region = $("f-region").value, type = $("f-type").value, days = Number($("f-days").value) || 0;
    var min = Number($("f-score").value) || 0, size = $("f-size").value, text = $("f-text").value.trim().toLowerCase(), only = $("f-short").checked;
    return d.tenders.filter(function (t) {
      if (region && t.region !== region) return false;
      if (type && t.category !== type) return false;
      if (days && t.days > days) return false;
      if (t.score < min) return false;
      if (only && !t.shortlisted) return false;
      if (size) {
        var v = t.value === null ? null : Number(t.value), parts = size.split("-");
        if (v === null || v < Number(parts[0]) || (parts[1] && v >= Number(parts[1]))) return false;
      }
      if (text && ((t.title || "") + " " + (t.buyer || "")).toLowerCase().indexOf(text) === -1) return false;
      return true;
    });
  }
  function csv(rows) {
    function q(v) { v = v === null || v === undefined ? "" : String(v); return /^[=+\-@]/.test(v) ? "\"'" + v.replace(/"/g, '""') + "\"" : "\"" + v.replace(/"/g, '""') + "\""; }
    var out = [["Score", "Title", "Buyer", "Region", "Type of work", "Value", "Closes", "Notice"].map(q).join(",")];
    rows.forEach(function (t) { out.push([t.score, t.title, t.buyer, t.region, LABELS[t.category] || "", t.value, t.deadline, t.url].map(q).join(",")); });
    return URL.createObjectURL(new Blob(["﻿" + out.join("\r\n")], { type: "text/csv" }));
  }
  function render() {
    var d = state.data, list = $("list"), rows;
    list.textContent = "";
    ["tenders", "coming", "renewals"].forEach(function (k) { var b = $("tab-" + k); if (b) b.setAttribute("aria-selected", String(state.tab === k)); });
    $("filters").hidden = state.tab !== "tenders";
    if (state.tab === "tenders") {
      rows = filtered();
      $("count").textContent = rows.length + " of " + d.tenders.length + " open tender" + (d.tenders.length === 1 ? "" : "s");
      rows.slice(0, 150).forEach(function (t) { list.appendChild(card(t)); });
      if (!rows.length) list.appendChild(el("p", "empty", d.tenders.length ? "Nothing matches those filters." : "No open tenders match your regions and type of work right now."));
      if (rows.length > 150) list.appendChild(el("p", "empty", "Showing the best 150. Narrow the filters to see the rest."));
      var dl = $("download");
      if (dl) { dl.hidden = !d.csv || !rows.length; if (d.csv && rows.length) { dl.href = csv(rows); dl.download = "noticehawk-tenders.csv"; } }
    } else if (state.tab === "coming") {
      $("count").textContent = d.coming.length + " planned";
      d.coming.forEach(function (c) { list.appendChild(simpleCard(c.title, c.url, [c.buyer || "Buyer not stated", [c.region, LABELS[c.category], money(c.value), c.expected ? "tender expected " + monthYear(c.expected) : "tender date not yet stated"].filter(Boolean).join(" | ")])); });
      if (!d.coming.length) list.appendChild(el("p", "empty", "No planned procurements for your regions and type of work right now."));
    } else {
      $("count").textContent = d.renewals.length + " ending in 3 to 15 months";
      d.renewals.forEach(function (r) { list.appendChild(simpleCard(r.title, r.url, [r.buyer || "Buyer not stated", ["Ends " + monthYear(r.ends), "held by " + ((r.winners || []).slice(0, 2).join(" and ") || "not stated"), money(r.value)].join(" | ")])); });
      if (!d.renewals.length) list.appendChild(el("p", "empty", "No contracts ending soon for your regions and type of work."));
    }
  }
  function fill(select, values, labels) {
    values.forEach(function (v) { select.add(new Option(labels ? labels[v] || v : v, v)); });
  }
  function start(d) {
    var low = d.min_value === null ? null : Number(d.min_value), high = d.max_value === null ? null : Number(d.max_value);
    d.tenders = personalise(d.tenders || [], low, high);
    state.data = d;
    $("plan").textContent = d.plan + " plan" + (d.updated ? " · checked " + nice(String(d.updated).slice(0, 10)) : "");
    $("prefs").href = "/preferences/?token=" + encodeURIComponent(token);
    function uniq(key) { var s = {}; d.tenders.forEach(function (t) { if (t[key]) s[t[key]] = 1; }); return Object.keys(s).sort(); }
    fill($("f-region"), uniq("region")); fill($("f-type"), uniq("category"), LABELS);
    ["coming", "renewals"].forEach(function (k) { if (d[k] === null || d[k] === undefined) { $("tab-" + k).hidden = true; d[k] = []; } });
    if (d.needs_setup) $("setup").hidden = false;
    ["f-region", "f-type", "f-days", "f-score", "f-size", "f-text", "f-short"].forEach(function (id) { $(id).addEventListener("input", render); });
    ["tenders", "coming", "renewals"].forEach(function (k) { $("tab-" + k).addEventListener("click", function () { state.tab = k; render(); }); });
    $("loading").hidden = true; $("app").hidden = false;
    render();
  }
  function fail(title, text) { $("loading").hidden = true; $("problem").hidden = false; $("problem-title").textContent = title; $("problem-text").textContent = text; }

  if (!/^[0-9a-f-]{36}$/i.test(token)) { fail("Sign in to see your account", "Ask for a new sign-in link below."); return; }
  fetch(main.dataset.api + "?token=" + encodeURIComponent(token)).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (b) {
      if (res.status === 200 && b.ok) start(b);
      else if (res.status === 403 && b.error === "free_plan") fail("The account page is for paid plans", "Your free weekly alert carries on as it is. Paid plans start at £29 a month.");
      else if (res.status === 403) fail("There is no live plan on this account", "If you think that is wrong, email hello@noticehawk.co.uk.");
      else if (res.status === 404) fail("That link is not recognised", "Ask for a new sign-in link below.");
      else fail("Something went wrong", "Please try again in a few minutes.");
    });
  }).catch(function () { fail("We could not reach the server", "Check your connection and try again."); });
})();
