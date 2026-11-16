// Sends the sign-up form without leaving the page and shows the result underneath.
(function () {
  var form = document.getElementById("signup");
  if (!form) return;
  var msg = document.getElementById("signup-msg");
  var button = form.querySelector("button");
  var labels = { email: "a valid email address", region: "your region", work: "your main type of work" };
  function firstFrom() { try { return JSON.parse(sessionStorage.getItem("nh_from") || "{}"); } catch (e) { return {}; } }
  function say(text, ok) { msg.textContent = text; msg.className = "msg " + (ok ? "good" : "bad"); }
  // How many new tenders a week to expect, from the last four weeks, so nobody signs up expecting more than comes.
  var rates = {};
  try { rates = JSON.parse(form.dataset.rates || "{}"); } catch (e) { rates = {}; }
  var hint = document.getElementById("s-rate");
  function showRate() {
    var f = form.elements, key = f.region.value + "|" + f.work.value;
    if (!hint || !f.region.value || !f.work.value || !Object.keys(rates).length) { if (hint) hint.textContent = ""; return; }
    var n = rates[key] || 0;
    if (n >= 3) hint.textContent = "About " + Math.round(n) + " new tenders a week match this in " + f.region.value + ". The free plan sends the best three; paid plans send them all, scored.";
    else if (n >= 1) hint.textContent = "About " + (Math.round(n * 2) / 2) + " new tenders a week match this in " + f.region.value + ". When there are fewer than three, the free plan adds the best from neighbouring regions, marked as nearby.";
    else hint.textContent = (n > 0 ? "This type of work comes up rarely in " + f.region.value + " (about " + Math.max(1, Math.round(n * 4)) + " in the last four weeks)."
                                     : "None of this type of work came up in " + f.region.value + " in the last four weeks.") + " We add the best from neighbouring regions to make up three where we can, or you could choose a broader type of work, such as repairs and maintenance.";
  }
  form.elements.region.addEventListener("change", showRate);
  form.elements.work.addEventListener("change", showRate);
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = form.elements;
    if (!f.email.value.trim() || !f.region.value || !f.work.value) {
      say("Please enter your email and choose a region and type of work.", false);
      return;
    }
    button.disabled = true;
    say("Sending…", true);
    fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: f.email.value, company: f.company.value, region: f.region.value, work: f.work.value,
        partner_opt_in: f.partner_opt_in.checked, product_updates: f.product_updates.checked, website: f.website.value, page: location.pathname,
        referrer: firstFrom().ref, utm: firstFrom().utm
      })
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) { return { status: res.status, body: body }; });
    }).then(function (r) {
      if (r.status === 200) {
        form.reset();
        say("Check your inbox. We have sent a link to confirm your email address.", true);
      } else if (r.status === 422) {
        say("Please enter " + (labels[r.body.field] || "the missing details") + ".", false);
      } else {
        say("Sorry, that did not go through. Please try again in a few minutes.", false);
      }
    }).catch(function () {
      say("Sorry, that did not go through. Check your connection and try again.", false);
    }).then(function () { button.disabled = false; });
  });
})();
