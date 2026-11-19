// The second person on an account: shows that they are confirmed, or lets them stop their copies of the alerts.
(function () {
  var q = new URLSearchParams(location.search), main = document.getElementById("main");
  function show(id) { ["c-ok", "c-stop", "c-done", "c-bad"].forEach(function (x) { document.getElementById(x).hidden = x !== id; }); }
  var stop = q.get("stop");
  if (!stop) { show(q.get("status") === "confirmed" ? "c-ok" : "c-bad"); return; }
  show("c-stop");
  document.getElementById("c-go").addEventListener("click", function () {
    this.disabled = true;
    fetch(main.dataset.api + "?copy_stop=" + encodeURIComponent(stop), { method: "POST" })
      .then(function (r) { return r.json(); }).then(function (b) { show(b.ok ? "c-done" : "c-bad"); })
      .catch(function () { show("c-bad"); });
  });
})();
