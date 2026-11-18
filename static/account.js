// A paying customer's account page: live matches with filters, planned procurements and renewals.
(function () {
  var main = document.getElementById("main");
  var token = new URLSearchParams(location.search).get("token") || "";
  var state = { data: null, tab: "tenders", base: null, work: null, assist: new URLSearchParams(location.search).get("assist") };
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
  function safeUrl(u) { return /^https:\/\/www\.((find-tender|contractsfinder)\.service\.gov\.uk|publiccontractsscotland\.gov\.uk)\//.test(u || "") ? u : null; }

  // The same adjustment the weekly email makes for the contract sizes a customer says they take on.
  function sizePoints(value, low, high, full) {
    if (high !== null && value > high) {
      var over = value / high;
      return [Math.round(full * (over <= 1.5 ? 0.6 : over <= 3 ? 0.3 : 0.1)), "Bigger than the largest contract you said you take on"];
    }
    if (low !== null && value < low) return [Math.round(full * (value >= low * 0.5 ? 0.6 : 0.2)), "Smaller than the contracts you said are worth bidding for"];
    return [full, null];
  }
  // The same rules as the alert emails: the subscriber's business profile, then their contract sizes.
  function personalise(list, low, high) {
    var sized = low !== null || high !== null, any = false;
    var out = list.filter(function (t) { return !(t.profile && t.profile.drop); }).map(function (t) {
      var prof = t.profile || {}, notes = (prof.notes || []).slice(), score = t.score + (prof.delta || 0), parts = t.parts;
      if (t.profile) any = true;
      if (sized && t.value !== null && parts && parts.value) {
        var p = sizePoints(Number(t.value), low, high, parts.value[1]);
        score = score - parts.value[0] + p[0];
        parts = Object.assign({}, parts, { value: [p[0], parts.value[1]] });
        if (p[1]) notes.push(p[1]);
      }
      if (!notes.length && score === t.score) return t;
      return Object.assign({}, t, { score: Math.max(0, Math.min(100, score)), parts: parts, fitNote: notes.join(". ") || null });
    });
    return sized || any ? out.sort(function (a, b) { return b.score - a.score || a.days - b.days; }) : out;
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
      if (b.pattern === "framework") text = b.top_winner + " won " + b.top_wins + " of this buyer's last " + b.awards + " " + kind + ", mostly as call-offs from a framework. New work here usually needs a place on that framework";
      else if (b.pattern === "one_firm") text = b.top_winner + " won " + b.top_wins + " of this buyer's last " + b.awards + " " + kind + ". A hard field to break into";
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

  // AI assist: what a bid for this tender is likely to need, drawn from the notice, any published documents and our read of them.
  var HAVE_KEY = "nh-have";
  function have() { try { return JSON.parse(localStorage.getItem(HAVE_KEY) || "{}"); } catch (e) { return {}; } }
  function setHave(id, on) { try { var h = have(); if (on) h[id] = 1; else delete h[id]; localStorage.setItem(HAVE_KEY, JSON.stringify(h)); } catch (e) { /* private browsing */ } }
  function slug(text) { return text.toLowerCase().replace(/£[\d.,]+[mk]?/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function addDays(iso, n) { var d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function assistData(t) {
    var f = t.facts || {}, df = t.doc_facts || {}, today = new Date().toISOString().slice(0, 10);
    var stated = [], items = [], marks = [], ask = [], dates = [];
    var mentions = (f.mentions || []).concat(df.mentions || []).filter(function (m, i, a) { return a.indexOf(m) === i; });
    var insurance = mentions.filter(function (m) { return /insurance/.test(m); });
    var schemes = mentions.filter(function (m) { return !/insurance|turnover|site visit/.test(m); });

    dates.push(["Bids close", nice(t.deadline) + " (" + t.days + " day" + (t.days === 1 ? "" : "s") + ")"]);
    if (f.questions_by && f.questions_by >= today) dates.push(["Questions to the buyer by", nice(f.questions_by)]);
    else if (t.days > 7) dates.push(["Send questions by about", nice(addDays(t.deadline, -7)) + " (the notice gives no date; buyers usually stop answering a week before)"]);
    if (t.days > 4) dates.push(["Have your price finished by", nice(addDays(t.deadline, -3))]);
    dates.push(["Upload by", (t.days > 1 ? nice(addDays(t.deadline, -1)) : "today") + ". Portals reject late bids, even by a minute"]);

    if (f.judged) stated.push("Scored " + f.judged.quality + "% on quality and " + f.judged.price + "% on price.");
    if (f.months) stated.push("Contract length: " + f.months + " months" + (f.extension_months ? ", with up to " + f.extension_months + " more" : f.extension_option ? ", with an option to extend" : "") + ".");
    if (f.framework) stated.push("This is a framework: a place on it does not guarantee any work.");
    if (f.dps) stated.push("This is a dynamic purchasing system: you can usually apply at any time while it is open.");
    if (f.lots) stated.push("Split into " + f.lots + " lots. You can normally bid for one or several.");
    if (df.contract) stated.push("Form of contract: " + df.contract + ".");
    if (df.turnover) stated.push("Minimum turnover: " + df.turnover + ".");
    else if (mentions.indexOf("a minimum turnover") !== -1) stated.push("A minimum turnover is asked for. The figure is in the tender pack.");
    if (df.site_visit_mandatory) stated.push("A site visit is mandatory. Book it straight away; missing it usually rules you out.");
    else if (mentions.indexOf("a site visit") !== -1) stated.push("A site visit is mentioned. Check whether it is compulsory and when.");
    if (df.social_value_pct) stated.push("Social value is " + df.social_value_pct + "% of the score.");
    insurance.forEach(function (m) { stated.push("Asks for " + m + "."); });
    if (schemes.length) stated.push("Names " + schemes.join(", ") + ".");
    if (t.doc_note) stated.push("From the documents: " + t.doc_note);

    function item(id, text, flagged) { items.push({ id: id, text: text, flagged: !!flagged }); }
    schemes.forEach(function (m) { item("s-" + slug(m), m + " (named in this tender)", true); });
    insurance.forEach(function (m) { item("i-" + slug(m) + "-" + (m.match(/£[\d.,]+[mk]?/) || [""])[0], m.charAt(0).toUpperCase() + m.slice(1) + " certificate (level asked for here)", true); });
    if (!insurance.some(function (m) { return /public/.test(m); })) item("pl", "Public liability insurance certificate");
    if (!insurance.some(function (m) { return /employer/.test(m); })) item("el", "Employer's liability insurance certificate");
    item("co", "Company details: registered name, number, VAT number, address");
    item("acc", "Last two years' accounts" + (df.turnover ? " showing turnover of " + df.turnover + " or more" : ""), !!df.turnover);
    if (!schemes.length) item("hs", "Health and safety policy, and a safety accreditation if you hold one (CHAS, SafeContractor or similar)");
    else item("hsp", "Health and safety policy");
    item("refs", "Three references for similar work in the last three years, with contact names who will answer");
    item("pol", "Standard policies: equality, environmental, modern slavery, safeguarding if working near the public");
    item("method", "Method statement: how you will do this job, who will do it and how you will keep the site safe");
    item("prog", "Programme of work with start and finish dates");
    item("price", "Priced schedule or form of tender, filled in exactly as the buyer laid it out");
    if (df.social_value_pct || (f.judged && f.judged.quality >= 30)) item("sv", "Social value answer: local jobs, apprentices, local suppliers, with numbers you will be held to", !!df.social_value_pct);
    if (t.docs_portal || f.portal) item("portal-" + slug(t.docs_portal || "site"), "Supplier account on " + (t.docs_portal || "the buyer's portal") + ", needed to download the pack and to submit", true);

    if (f.judged) {
      if (f.judged.quality >= 50) marks.push("Most of the marks are for quality. A cheap price will not win this on its own: put your time into the written answers and back each claim with a job you have done.");
      else if (f.judged.price >= 70) marks.push("This is mostly decided on price. Keep the written answers short and correct, and spend your time on the pricing.");
      else marks.push("Price and quality both matter. Answer every question fully, then sharpen the price.");
    } else marks.push("The notice does not say how bids are scored. The tender pack will. Read the scoring table before you write anything, and give the most words to the questions with the most marks.");
    if (df.social_value_pct >= 10) marks.push("Social value carries " + df.social_value_pct + "%. That is often the gap between first and second place, so give it a proper answer.");
    if (t.parts && t.parts.sme && t.parts.sme[0] >= t.parts.sme[1] * 0.7) marks.push("The buyer has marked this as suitable for smaller firms.");

    if (!t.value) ask.push("What is the budget or estimated value?");
    if (!f.judged) ask.push("How will bids be scored, and what are the weightings?");
    if (!f.months) ask.push("When does the work start and how long does it run?");
    if (f.framework) ask.push("How much work went through this framework last time, and how is it shared out?");
    if (f.lots) ask.push("Is there a limit on how many lots one firm can win?");
    if (mentions.indexOf("a site visit") !== -1 && !df.site_visit_mandatory) ask.push("Is the site visit compulsory, and what dates are offered?");
    ask.push("Is there an incumbent contractor, and do TUPE staff transfers apply?");
    return { dates: dates, stated: stated, items: items, marks: marks, ask: ask };
  }
  function assistText(t, a) {
    var out = ["AI assist: " + t.title, t.buyer || "", t.url || "", "", "KEY DATES"];
    a.dates.forEach(function (d) { out.push("- " + d[0] + ": " + d[1]); });
    if (a.stated.length) { out.push("", "WHAT THE BUYER STATES"); a.stated.forEach(function (s) { out.push("- " + s); }); }
    out.push("", "HAVE READY"); a.items.forEach(function (i) { out.push("[ ] " + i.text); });
    out.push("", "WHERE THE MARKS ARE"); a.marks.forEach(function (m) { out.push("- " + m); });
    out.push("", "QUESTIONS WORTH ASKING THE BUYER"); a.ask.forEach(function (q) { out.push("- " + q); });
    out.push("", "From Noticehawk. Drawn from the notice and any published documents. Check the tender pack before you rely on it.");
    return out.join("\n");
  }
  // Draft check: runs in the browser. The draft is not sent to us or stored.
  var CHECKS = [
    ["pl", /public liability/i], ["el", /employer'?s'? liability/i], ["acc", /accounts|turnover/i], ["hs", /health and safety|chas|safecontractor|ssip/i],
    ["hsp", /health and safety/i], ["refs", /reference|referee|case stud/i], ["pol", /equality|environmental|modern slavery|safeguarding/i],
    ["method", /method statement|methodology|we will (carry out|deliver|undertake)|sequence of work/i], ["prog", /programme|start date|completion|week \d|weeks/i],
    ["price", /£\s?\d|price|rates|schedule of rates/i], ["sv", /social value|apprentice|local (labour|jobs|supplier|employment)/i], ["co", /company (number|registration)|registered (office|in)|vat (number|no)/i]
  ];
  function draftCheck(a, text) {
    var words = (text.match(/\S+/g) || []).length, out = { found: [], missing: [], flags: [], words: words };
    a.items.forEach(function (i) {
      var rule = null;
      CHECKS.forEach(function (c) { if (i.id === c[0] || i.id.indexOf(c[0] + "-") === 0) rule = c[1]; });
      if (!rule && /^[si]-/.test(i.id)) {           // a scheme or insurance named in this tender: look for its own words
        var key = i.text.replace(/\s*\(.*$/, "").replace(/ certificate$/i, "");
        var amount = key.match(/£[\d.,]+\s?[mk]?/i), name = key.replace(/£[\d.,]+\s?[mk]?/i, "").trim().split(/\s+/).slice(0, 2).join(" ");
        rule = new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
        if (rule.test(text) && amount && text.replace(/[\s,]/g, "").toLowerCase().indexOf(amount[0].replace(/[\s,]/g, "").toLowerCase()) === -1)
          out.flags.push("You mention " + name.toLowerCase() + " but not the " + amount[0] + " level this tender asks for.");
      }
      if (!rule) return;
      (rule.test(text) ? out.found : out.missing).push(i.text);
    });
    var figures = (text.match(/\d[\d,.]*\s?(%|per cent|days?|hours?|weeks?|years?|staff|operatives|m2|sqm)|£\s?\d/gi) || []).length;
    if (words >= 150 && figures < 3) out.flags.push("Few figures. Evaluators mark evidence: add numbers such as response times, contract values, staff, percentages.");
    var soft = (text.match(/\b(we believe|we strive|we aim to|we pride ourselves|passionate|world[- ]class|best[- ]in[- ]class|second to none)\b/gi) || []).length;
    if (soft >= 2) out.flags.push("Claims without proof (" + soft + " phrases such as “we pride ourselves”, “we aim to”). Replace each with what you did, for whom, and the result.");
    if (words >= 150 && !/\b(20\d\d|for (the )?[A-Z][a-z]+ (Council|Borough|Housing|School|NHS|Trust|University)|contract for)\b/.test(text)) out.flags.push("No past job named. Name a similar contract, the client and the year.");
    if (words > 0 && words < 150) out.flags.push("Only " + words + " words. If this is the whole answer it is probably too thin to score well.");
    if (/\b(tbc|xxx|insert|lorem|\[.*?\])\b/i.test(text)) out.flags.push("Looks like a placeholder is still in the text (TBC, XXX, [brackets] or “insert”).");
    var total = out.found.length + out.missing.length;
    out.score = Math.max(0, Math.min(100, Math.round((total ? out.found.length / total : 0) * 80 + 20 - out.flags.length * 5)));
    return out;
  }
  function draftBox(t, a) {
    var wrap = el("div", "draft"), ta = el("textarea"), go = el("button", "btn small", "Check my draft"), res = el("div", "draft-result");
    wrap.appendChild(el("h4", null, "Check your draft before you send it"));
    wrap.appendChild(el("p", "assist-note", "Paste your written answers below. The check runs on your device: your draft is not sent to us or saved."));
    ta.rows = 7; ta.placeholder = "Paste your draft answers here"; ta.setAttribute("aria-label", "Your draft answers");
    go.type = "button";
    go.addEventListener("click", function () {
      var text = ta.value.trim(); res.textContent = "";
      if (!text) { res.appendChild(el("p", "assist-note", "Paste your draft first.")); return; }
      var r = draftCheck(a, text);
      res.appendChild(el("p", "draft-score", "Completeness: " + r.score + " out of 100 (" + r.words.toLocaleString("en-GB") + " words)"));
      function list(title, arr, cls) { if (!arr.length) return; res.appendChild(el("h4", null, title)); var ul = el("ul", cls); arr.forEach(function (x) { ul.appendChild(el("li", null, x)); }); res.appendChild(ul); }
      list("Not found in your draft", r.missing, "miss");
      list("Worth fixing", r.flags, "miss");
      list("Covered", r.found, "ok");
      res.appendChild(el("p", "assist-note", "Coming soon on Professional and Premium: a full AI review that reads your answers against the buyer's questions and scoring, and gives the bid a score."));
      res.appendChild(el("p", "assist-note", "This checks what is there against the checklist above. It cannot judge quality or tell you how a buyer will mark it, and some items belong in attachments, not in the written answers."));
    });
    wrap.appendChild(ta); wrap.appendChild(go); wrap.appendChild(res);
    return wrap;
  }
  function assistPanel(t) {
    var a = assistData(t), box = el("div", "assist"), held = have();
    function section(title) { box.appendChild(el("h4", null, title)); var ul = el("ul"); box.appendChild(ul); return ul; }
    var ul = section("Key dates");
    a.dates.forEach(function (d) { var li = el("li"); li.appendChild(el("strong", null, d[0] + ": ")); li.appendChild(document.createTextNode(d[1])); ul.appendChild(li); });
    if (a.stated.length) { ul = section("What the buyer states"); a.stated.forEach(function (s) { ul.appendChild(el("li", null, s)); }); }
    else if (state.data.plan === "Basic") box.appendChild(el("p", "assist-note", "Professional adds the requirements pulled from each notice and its documents: insurance levels, accreditations, turnover, scoring and contract terms."));
    box.appendChild(el("h4", null, "Have ready"));
    box.appendChild(el("p", "assist-note", "Tick what you already hold. It is remembered on this device, so the next tender shows only what is missing."));
    var list = el("div", "assist-ticks");
    a.items.forEach(function (i) {
      var lab = el("label", i.flagged ? "flag" : null), c = el("input");
      c.type = "checkbox"; c.checked = !!held[i.id];
      c.addEventListener("change", function () { setHave(i.id, c.checked); });
      lab.appendChild(c); lab.appendChild(document.createTextNode(" " + i.text)); list.appendChild(lab);
    });
    box.appendChild(list);
    ul = section("Where the marks are"); a.marks.forEach(function (m) { ul.appendChild(el("li", null, m)); });
    ul = section("Questions worth asking the buyer"); a.ask.forEach(function (q) { ul.appendChild(el("li", null, q)); });
    var foot = el("div", "card-actions"), copy = el("button", "linkish", "Copy this as a checklist");
    copy.type = "button";
    copy.addEventListener("click", function () {
      var text = assistText(t, a);
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { copy.textContent = "Copied"; })
        .catch(function () { var ta = el("textarea", "assist-copy"); ta.value = text; ta.rows = 12; box.appendChild(ta); ta.select(); copy.hidden = true; });
    });
    foot.appendChild(copy);
    var g1 = el("a", null, "Paperwork checklist"); g1.href = "/guides/tender-paperwork-checklist/";
    var g2 = el("a", null, "Writing answers that score"); g2.href = "/guides/writing-a-tender-response-that-scores-well/";
    foot.appendChild(g1); foot.appendChild(g2);
    box.appendChild(foot);
    box.appendChild(draftBox(t, a));
    box.appendChild(el("p", "assist-note", "Drawn from the notice, any published documents and our read of them. It is a starting point, not the full requirement: check the tender pack before you rely on it."));
    return box;
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
    var dist = distanceOf(t);
    body.appendChild(el("p", null, [t.council ? t.council + (t.where === "buyer" ? " (buyer's address)" : "") : t.region,
      dist === null ? null : Math.round(dist) + " miles away", workLabel(t), money(t.value), "closes " + nice(t.deadline) + " (" + t.days + " day" + (t.days === 1 ? "" : "s") + ")"].filter(Boolean).join(" | ")));
    if (t.note) line(body, "Our read", t.note, "read");
    intelLines(t.intel).forEach(function (l) { line(body, l[0], l[1]); });
    var docs = docsLine(t);
    if (docs) line(body, docs[0], docs[1]);
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
    var actions = el("div", "card-actions");
    var help = el("button", "linkish assist-open", "AI assist: what this bid needs"), panel = null;
    help.type = "button";
    help.setAttribute("aria-expanded", "false");
    function toggleAssist() {
      if (panel) { panel.remove(); panel = null; } else { panel = assistPanel(t); body.appendChild(panel); }
      help.setAttribute("aria-expanded", String(!!panel));
      help.textContent = panel ? "Hide AI assist" : "AI assist: what this bid needs";
    }
    help.addEventListener("click", toggleAssist);
    if (state.assist === t.id) { state.assist = null; setTimeout(function () { toggleAssist(); item.scrollIntoView({ block: "start" }); }, 0); }
    actions.appendChild(help);
    actions.appendChild(b);
    var nope = el("button", "linkish", "Not for me");
    nope.type = "button";
    nope.addEventListener("click", function () {
      nope.disabled = true;
      fetch(main.dataset.feedback, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token, record: t.id, reason: "not_my_work" }) })
        .then(function (r) {
          if (!r.ok) { nope.disabled = false; nope.textContent = "That did not save. Try again"; return; }
          state.data.tenders = state.data.tenders.filter(function (x) { return x.id !== t.id; });
          state.hidden = t;
          render();
        })
        .catch(function () { nope.disabled = false; nope.textContent = "That did not save. Try again"; });
    });
    actions.appendChild(nope);
    body.appendChild(actions);
    item.appendChild(body);
    return item;
  }
  function undoBar() {
    var t = state.hidden;
    if (!t) return null;
    var bar = el("p", "msg good", "Hidden “" + t.title + "”. ");
    var u = el("button", "linkish", "Undo");
    u.type = "button";
    u.addEventListener("click", function () {
      fetch(main.dataset.feedback, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token, record: t.id, reason: "undo" }) })
        .then(function (r) { if (r.ok) { state.data.tenders.push(t); state.hidden = null; render(); } });
    });
    bar.appendChild(u);
    return bar;
  }
  function simpleCard(title, url, lines) {
    var item = el("div", "mail-item"), body = el("div"), u = safeUrl(url), a = el(u ? "a" : "span", null, title);
    if (u) { a.href = u; a.rel = "noopener"; a.target = "_blank"; }
    body.appendChild(a);
    lines.filter(Boolean).forEach(function (l) { body.appendChild(el("p", null, l)); });
    item.appendChild(body);
    return item;
  }

  function workLabel(t) {
    var main = LABELS[t.category], mine = (t.also || []).filter(function (a) { return a !== t.category && LABELS[a] && (state.data.trades || []).indexOf(a) !== -1; });
    return main && mine.length ? main + ", includes " + LABELS[mine[0]].toLowerCase() : main;
  }
  var YEAR = "(?!(?:19|20)\\d\\d(?:[-/]\\d{2,4})?\\s)";
  var MARKER = /^\s*(\(?\s*(itt|rfq|rfp|itq|eoi|pin|tender)\s*\)?\s*[-:\u2013\u2014]\s*|\(\s*(itt|rfq|rfp|itq)\s*\)\s*)/i;
  var CODE_SEP = new RegExp("^\\s*" + YEAR + "[A-Za-z]*[A-Za-z0-9/._-]*\\d[A-Za-z0-9/._-]*\\s*[-:\u2013\u2014]\\s+");
  var CODE_LONG = new RegExp("^\\s*" + YEAR + "[A-Za-z0-9/._-]*\\d{4,}[A-Za-z0-9/._-]*\\s+");
  var TRAIL = /\s*\(\s*[A-Z0-9][A-Z0-9 \/._-]*\d[A-Z0-9 \/._-]*\)\s*$/;
  function tidy(title) {
    if (!title) return title || "";
    var out = title.trim();
    for (var i = 0; i < 3; i++) {
      var before = out;
      out = out.replace(MARKER, "").replace(CODE_SEP, "").replace(CODE_LONG, "");
      if (out === before) break;
    }
    out = out.replace(TRAIL, "").replace(/^[\s\-\u2013\u2014:]+|[\s\-\u2013\u2014:]+$/g, "");
    return out.length >= 8 ? out : title.trim();
  }
  function dedupe(list) {
    var seen = {};
    return list.filter(function (t) {
      var key = (t.title || "").toLowerCase().replace(/[^a-z0-9]/g, "") + "|" + (t.deadline || "");
      if (seen[key]) return false;
      seen[key] = 1;
      return true;
    });
  }
  function docsLine(t) {
    if (t.doc_note) return ["From the tender documents", t.doc_note];
    var f = t.doc_facts || {}, bits = [];
    if (f.turnover) bits.push("minimum turnover " + f.turnover);
    (f.mentions || []).forEach(function (m) { if (m !== "a minimum turnover" && m !== "a site visit") bits.push(m); });
    if (f.contract) bits.push(f.contract + " contract");
    if (f.social_value_pct) bits.push("social value " + f.social_value_pct + "% of the score");
    if (f.site_visit_mandatory) bits.push("mandatory site visit");
    if (bits.length) return ["From the tender documents", bits.slice(0, 7).join("; ") + "."];
    if (t.docs_portal) return ["Tender documents", "On " + t.docs_portal + ", where you register as a supplier to download them."];
    return null;
  }
  function area(t) { return t.county || t.council || null; }
  function miles(a, b) {
    var r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 3958.8 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }
  function distanceOf(t) {
    if (!state.base || t.lat === null || t.lat === undefined) return null;
    return miles(state.base, { lat: Number(t.lat), lon: Number(t.lon) });
  }
  function baseNote(text) { var n = $("base-note"); n.hidden = !text; n.textContent = text || ""; }
  function setBase(raw) {
    var pc = (raw || "").toUpperCase().replace(/\s+/g, "");
    if (!pc) { state.base = null; baseNote(""); try { localStorage.removeItem("nh_base"); } catch (e) {} render(); return; }
    if (!/^[A-Z]{1,2}[0-9][0-9A-Z]?[0-9][A-Z]{2}$/.test(pc)) { state.base = null; baseNote("Enter a full UK postcode to filter by distance."); render(); return; }
    fetch("https://api.postcodes.io/postcodes/" + encodeURIComponent(pc)).then(function (r) { return r.json(); }).then(function (b) {
      if (!b || !b.result) { state.base = null; baseNote("We could not find that postcode."); render(); return; }
      state.base = { lat: b.result.latitude, lon: b.result.longitude };
      try { localStorage.setItem("nh_base", pc); } catch (e) {}
      baseNote("Distances are measured in a straight line from " + b.result.postcode + " to the work site, or to the buyer's address where the notice gives no site.");
      render();
    }).catch(function () { state.base = null; baseNote("We could not look up that postcode just now. Try again shortly."); render(); });
  }
  function emptyText(d) {
    var other = [];
    if (d.coming && d.coming.length) other.push(d.coming.length + " planned in Coming soon");
    if (d.renewals && d.renewals.length) other.push(d.renewals.length + " ending soon in Renewals");
    return "No tenders are open for your regions and type of work today. New ones are added every day" +
      (other.length ? ", and there are " + other.join(" and ") : "") +
      ". To see more, add a region or type of work with the link at the top of the page.";
  }
  function filtered() {
    var d = state.data, region = $("f-region").value, type = $("f-type").value, days = Number($("f-days").value) || 0;
    var county = $("f-county").value, council = $("f-council").value, within = Number($("f-miles").value) || 0;
    var min = Number($("f-score").value) || 0, size = $("f-size").value, text = $("f-text").value.trim().toLowerCase(), only = $("f-short").checked;
    return d.tenders.filter(function (t) {
      if (region && t.region !== region) return false;
      if (county && area(t) !== county) return false;
      if (council && t.council !== council) return false;
      if (within && state.base) { var m = distanceOf(t); if (m === null || m > within) return false; }
      if (type && t.category !== type && (t.also || []).indexOf(type) === -1) return false;
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
    var out = [["Score", "Title", "Buyer", "Region", "Council", "County", "Type of work", "Value", "Closes", "Notice"].map(q).join(",")];
    rows.forEach(function (t) { out.push([t.score, t.title, t.buyer, t.region, t.council || "", area(t) || "", LABELS[t.category] || "", t.value, t.deadline, t.url].map(q).join(",")); });
    return URL.createObjectURL(new Blob(["﻿" + out.join("\r\n")], { type: "text/csv" }));
  }
  function render() {
    var d = state.data, list = $("list"), rows;
    list.textContent = "";
    ["tenders", "coming", "renewals", "work"].forEach(function (k) { var b = $("tab-" + k); if (b) b.setAttribute("aria-selected", String(state.tab === k)); });
    $("filters").hidden = state.tab !== "tenders";
    if (state.tab === "tenders") {
      rows = filtered();
      var undo = undoBar();
      if (undo) list.appendChild(undo);
      $("count").textContent = rows.length + " of " + d.tenders.length + " open tender" + (d.tenders.length === 1 ? "" : "s");
      rows.slice(0, 150).forEach(function (t) { list.appendChild(card(t)); });
      if (!rows.length) list.appendChild(el("p", "empty", d.tenders.length ? "Nothing matches those filters." : emptyText(d)));
      if (rows.length > 150) list.appendChild(el("p", "empty", "Showing the best 150. Narrow the filters to see the rest."));
      var dl = $("download");
      if (dl) { dl.hidden = !d.csv || !rows.length; if (d.csv && rows.length) { dl.href = csv(rows); dl.download = "noticehawk-tenders.csv"; } }
    } else if (state.tab === "coming") {
      $("count").textContent = d.coming.length + " planned";
      d.coming.forEach(function (c) { list.appendChild(simpleCard(c.title, c.url, [c.buyer || "Buyer not stated", [c.region, LABELS[c.category], money(c.value), c.expected ? "tender expected " + monthYear(c.expected) : "tender date not yet stated"].filter(Boolean).join(" | ")])); });
      if (!d.coming.length) list.appendChild(el("p", "empty", "No planned procurements for your regions and type of work right now."));
    } else if (state.tab === "work") {
      // Work packages posted by contractors on the board, for the subscriber's regions.
      var BANDS = { under_10k: "under £10,000", "10k_50k": "£10,000 to £50,000", "50k_250k": "£50,000 to £250,000", "250k_1m": "£250,000 to £1 million", over_1m: "over £1 million" };
      var posts = (state.work || []).filter(function (p) { return d.national || (d.regions || []).indexOf(p.region) !== -1; });
      $("count").textContent = state.work === null ? "Loading" : posts.length + " posted by contractors";
      posts.forEach(function (p) {
        var reply = /^https:\/\//.test(p.how_to_apply) ? p.how_to_apply : "mailto:" + p.how_to_apply + "?subject=" + encodeURIComponent(p.title + " (seen on Noticehawk)");
        list.appendChild(simpleCard(p.title, reply, [p.company, [p.town ? p.town + ", " + p.region : p.region, LABELS[p.category], BANDS[p.value_band], "prices by " + nice(p.apply_by)].filter(Boolean).join(" | "), p.description,
          "Reply to: " + p.how_to_apply]));
      });
      if (state.work !== null && !posts.length) list.appendChild(el("p", "empty", "No work is posted for your regions right now. The board is new; anything posted will also be in your alerts."));
      var more = el("p", "empty"), a1 = el("a", null, "See the whole board"), a2 = el("a", null, "post work free");
      a1.href = "/subcontract-work/"; a2.href = "/post-work/";
      more.appendChild(a1); more.appendChild(document.createTextNode(" or ")); more.appendChild(a2); more.appendChild(document.createTextNode("."));
      list.appendChild(more);
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
    ["tenders", "coming", "renewals"].forEach(function (k) { (d[k] || []).forEach(function (t) { t.title = tidy(t.title); }); });
    d.tenders = dedupe(d.tenders || []);
    var low = d.min_value === null ? null : Number(d.min_value), high = d.max_value === null ? null : Number(d.max_value);
    d.tenders = personalise(d.tenders || [], low, high);
    state.data = d;
    $("plan").textContent = d.plan + " plan" + (d.updated ? " · checked " + nice(String(d.updated).slice(0, 10)) : "");
    $("prefs").href = "/preferences/?token=" + encodeURIComponent(token);
    function uniq(key) { var s = {}; d.tenders.forEach(function (t) { if (t[key]) s[t[key]] = 1; }); return Object.keys(s).sort(); }
    fill($("f-region"), uniq("region")); var types = {}; d.tenders.forEach(function (t) { if (t.category) types[t.category] = 1; (t.also || []).forEach(function (a) { if (LABELS[a]) types[a] = 1; }); });
    fill($("f-type"), Object.keys(types).sort(), LABELS);
    var areas = {}; d.tenders.forEach(function (t) { if (area(t)) areas[area(t)] = 1; }); fill($("f-county"), Object.keys(areas).sort());
    fill($("f-council"), uniq("council"));
    $("f-county").addEventListener("input", function () {
      var c = $("f-county").value, sel = $("f-council"), keep = {};
      d.tenders.forEach(function (t) { if (t.council && (!c || area(t) === c)) keep[t.council] = 1; });
      while (sel.options.length > 1) sel.remove(1);
      fill(sel, Object.keys(keep).sort());
    });
    $("f-base").addEventListener("change", function () { setBase($("f-base").value); });
    try { var saved = localStorage.getItem("nh_base"); if (saved) { $("f-base").value = saved; setBase(saved); } } catch (e) {}
    ["coming", "renewals"].forEach(function (k) { if (d[k] === null || d[k] === undefined) { $("tab-" + k).hidden = true; d[k] = []; } });
    if (d.needs_setup) $("setup").hidden = false;
    ["f-region", "f-county", "f-council", "f-miles", "f-type", "f-days", "f-score", "f-size", "f-text", "f-short"].forEach(function (id) { $(id).addEventListener("input", render); });
    ["tenders", "coming", "renewals", "work"].forEach(function (k) { $("tab-" + k).addEventListener("click", function () { state.tab = k; render(); }); });
    $("loading").hidden = true; $("app").hidden = false;
    render();
    fetch(main.dataset.work).then(function (r) { return r.json(); }).then(function (w) { state.work = w.posts || []; })
      .catch(function () { state.work = []; }).then(function () { if (state.tab === "work") render(); });
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
