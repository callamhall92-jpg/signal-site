// Sends the sign-up form without leaving the page and shows the result underneath.
(function () {
  var form = document.getElementById("signup");
  if (!form) return;
  var msg = document.getElementById("signup-msg");
  var button = form.querySelector("button");
  var labels = { email: "a valid email address", region: "your region", work: "your main type of work" };
  function say(text, ok) { msg.textContent = text; msg.className = "msg " + (ok ? "good" : "bad"); }
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
        partner_opt_in: f.partner_opt_in.checked, product_updates: f.product_updates.checked, website: f.website.value, page: location.pathname
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
