// Asks for a sign-in link. The answer is the same whether or not the address belongs to a customer.
(function () {
  var form = document.getElementById("login"), msg = document.getElementById("login-msg");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var button = form.querySelector("button");
    button.disabled = true; msg.textContent = "";
    fetch(form.dataset.api, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.email.value.trim(), website: form.website.value }) })
      .then(function (res) {
        if (res.status === 200) { form.hidden = true; msg.textContent = "If that address has a paid Noticehawk plan, a sign-in link is on its way. It can take a minute or two; check your junk folder as well."; }
        else if (res.status === 429) msg.textContent = "We are getting a lot of requests. Please try again in a few minutes.";
        else msg.textContent = "That did not work. Check the address and try again.";
      })
      .catch(function () { msg.textContent = "We could not reach the server. Check your connection and try again."; })
      .then(function () { button.disabled = false; });
  });
})();
