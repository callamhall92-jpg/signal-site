// Remembers, for this visit only, where the visitor first arrived from, so a sign-up can say which channel brought it.
(function () {
  try {
    var q = new URLSearchParams(location.search), ref = "", team = false;
    // Our own devices: ?team=on stops this device being counted in visits and clicks, ?team=off counts it again.
    try {
      if (q.get("team") === "on") localStorage.setItem("nh_team", "1");
      if (q.get("team") === "off") localStorage.removeItem("nh_team");
      team = localStorage.getItem("nh_team") === "1";
      if (q.get("team") === "on" || q.get("team") === "off") {
        var n = document.createElement("div");
        n.textContent = team ? "This device is no longer counted in visits or clicks." : "This device is counted again.";
        n.setAttribute("role", "status");
        n.style.cssText = "position:fixed;left:12px;right:12px;bottom:12px;z-index:99;padding:12px 16px;background:#14213d;color:#fff;border-radius:8px;text-align:center";
        document.body.appendChild(n);
      }
    } catch (e) {}
    if (sessionStorage.getItem("nh_from")) return;
    try { var h = new URL(document.referrer).hostname; if (h && h.replace(/^www\./, "") !== location.hostname.replace(/^www\./, "")) ref = h; } catch (e) {}
    var utm = [q.get("utm_source"), q.get("utm_medium"), q.get("utm_campaign")].filter(Boolean).join(" / ");
    sessionStorage.setItem("nh_from", JSON.stringify({ ref: ref, utm: utm }));
    // Count the arrival against the post or email that brought it: the tag, this page and the day, nothing about the visitor.
    if (q.get("utm_source") && !team && navigator.sendBeacon) {
      navigator.sendBeacon("https://wboavagwignktkodqvwa.supabase.co/functions/v1/hit",
        JSON.stringify({ s: q.get("utm_source"), m: q.get("utm_medium") || "", c: q.get("utm_campaign") || "", p: location.pathname }));
    }
  } catch (e) {}
})();
