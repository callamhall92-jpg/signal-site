// The subcontract work board: the list, the posting form, the confirmation page and the review or remove page.
(function () {
  var main = document.getElementById("main");
  var LABELS = { new_build: "New build", refurbishment: "Refurbishment", repairs_maintenance: "Repairs and maintenance",
    roofing: "Roofing", mechanical_electrical: "Mechanical and electrical", groundworks_civils: "Groundworks and civils",
    design_professional: "Design and professional" };
  var BANDS = { under_10k: "Under £10,000", "10k_50k": "£10,000 to £50,000", "50k_250k": "£50,000 to £250,000", "250k_1m": "£250,000 to £1 million", over_1m: "Over £1 million" };
  var FIELDS = { email: "your email address", company: "your company name", company_number: "the company number (8 characters, or leave it blank)",
    title: "what the work is (at least 8 characters)", description: "the description (at least 40 characters, with no web links)",
    category: "the type of work", region: "the region", apply_by: "the date (between 2 days and 4 months from today)",
    how_to_apply: "how firms should reply (an email address or a link starting https://)", value_band: "the rough value", agree: "the tick box" };
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function nice(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }
  function post(api, body) { return fetch(api, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  function card(p) {
    var item = el("div", "mail-item work-item"), body = el("div");
    body.appendChild(el("strong", null, p.title));
    body.appendChild(el("p", null, p.company + (p.company_number ? " (company no. " + p.company_number + ")" : "")));
    body.appendChild(el("p", null, [p.town ? p.town + ", " + p.region : p.region, LABELS[p.category], BANDS[p.value_band], "prices by " + nice(p.apply_by)].filter(Boolean).join(" | ")));
    p.description.split(/\n+/).forEach(function (para) { if (para.trim()) body.appendChild(el("p", "why", para.trim())); });
    var how = el("p"), a = el("a", null, /^https:\/\//.test(p.how_to_apply) ? "Reply on the contractor's site" : p.how_to_apply);
    a.href = /^https:\/\//.test(p.how_to_apply) ? p.how_to_apply : "mailto:" + p.how_to_apply + "?subject=" + encodeURIComponent(p.title + " (seen on Noticehawk)");
    a.rel = "noopener nofollow";
    how.appendChild(el("strong", null, "Reply to: ")); how.appendChild(a); body.appendChild(how);
    item.appendChild(body);
    return item;
  }

  var list = document.getElementById("work-list");
  if (list) {
    fetch(main.dataset.api).then(function (r) { return r.json(); }).then(function (d) {
      var trade = document.getElementById("work-trade"), region = document.getElementById("work-region"), posts = d.posts || [];
      function draw() {
        list.textContent = "";
        if (!posts.length) { list.appendChild(el("p", null, "No work is posted right now. The board is new; if you have a package to price, be the first to post.")); return; }
        var shown = posts.filter(function (p) { return (!trade.value || p.category === trade.value) && (!region.value || p.region === region.value); });
        if (!shown.length) list.appendChild(el("p", null, "Nothing posted for that type of work and region right now."));
        shown.forEach(function (p) { list.appendChild(card(p)); });
      }
      trade.addEventListener("change", draw); region.addEventListener("change", draw);
      draw();
    }).catch(function () { list.textContent = "We could not load the board just now. Try again shortly."; });
  }

  var form = document.getElementById("work-form"), msg = document.getElementById("work-msg");
  if (form) {
    var by = form.apply_by, d = new Date(); d.setDate(d.getDate() + 2); by.min = d.toISOString().slice(0, 10);
    d.setDate(d.getDate() + 118); by.max = d.toISOString().slice(0, 10);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var button = form.querySelector("button"), body = { agree: form.agree.checked, website: form.website.value };
      ["company", "company_number", "email", "title", "category", "region", "town", "description", "value_band", "apply_by", "how_to_apply"].forEach(function (k) { body[k] = form[k].value.trim(); });
      button.disabled = true; msg.textContent = "";
      post(form.dataset.api, body).then(function (res) {
        if (res.status === 200) { form.hidden = true; msg.textContent = "Nearly done. We have sent a confirmation link to " + body.email + ". Click it and your post goes on the board straight away. Check your junk folder if it has not arrived in a few minutes."; return; }
        if (res.status === 422) return res.json().then(function (j) { msg.textContent = "Please check " + (FIELDS[j.field] || "the form") + "."; });
        msg.textContent = res.status === 503 ? "We are getting a lot of posts. Please try again in an hour." : "That did not work. Please try again.";
      }).catch(function () { msg.textContent = "We could not reach the server. Check your connection and try again."; })
        .then(function () { button.disabled = false; });
    });
  }

  var done = document.getElementById("done-p");
  if (done) {
    var status = new URLSearchParams(location.search).get("status");
    if (status === "unknown") { document.getElementById("done-h").textContent = "That link did not work"; done.textContent = "The link may be old or incomplete. Try the link in your email again, or post the work again."; }
    if (status === "error") { document.getElementById("done-h").textContent = "Something went wrong"; done.textContent = "Please try the link in your email again in a few minutes."; }
  }

  var manage = document.getElementById("manage");
  if (manage) {
    var q = new URLSearchParams(location.search), review = q.get("review"), own = q.get("post"), api = main.dataset.api;
    var STATUS = { unconfirmed: "Waiting for the email address to be confirmed.", pending: "Waiting to be checked. It is not on the board yet.",
      live: "On the board now.", rejected: "Taken down. It is not on the board.", removed: "Removed. It is no longer on the board." };
    function show(d) {
      manage.textContent = "";
      manage.appendChild(el("p", "lede dark", STATUS[d.status] || ""));
      manage.appendChild(card(d.post));
      var acts = el("div", "card-actions");
      function act(label, cls, body) {
        var b = el("button", cls, label); b.type = "button";
        b.addEventListener("click", function () {
          b.disabled = true;
          post(api, body).then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(show)
            .catch(function () { b.disabled = false; b.textContent = "That did not work. Try again"; });
        });
        acts.appendChild(b);
      }
      if (review && d.status === "pending") act("Approve and publish", "btn", { review: review, action: "approve" });
      if (review && (d.status === "pending" || d.status === "live")) act("Take this post down", d.status === "live" ? "btn" : "linkish", { review: review, action: "reject" });
      if (own && (d.status === "live" || d.status === "pending")) act("Remove this post", "btn", { manage: own, action: "remove" });
      manage.appendChild(acts);
    }
    if (review) document.getElementById("manage-h").textContent = "Review a post";
    post(api, review ? { review: review, action: "view" } : { manage: own || "", action: "view" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(show)
      .catch(function () { manage.textContent = "We could not find that post. The link may be old or incomplete."; });
  }
})();
