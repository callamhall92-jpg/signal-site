// Remembers, for this visit only, where the visitor first arrived from, so a sign-up can say which channel brought it.
(function () {
  try {
    if (sessionStorage.getItem("nh_from")) return;
    var q = new URLSearchParams(location.search), ref = "";
    try { var h = new URL(document.referrer).hostname; if (h && h.replace(/^www\./, "") !== location.hostname.replace(/^www\./, "")) ref = h; } catch (e) {}
    var utm = [q.get("utm_source"), q.get("utm_medium"), q.get("utm_campaign")].filter(Boolean).join(" / ");
    sessionStorage.setItem("nh_from", JSON.stringify({ ref: ref, utm: utm }));
    // Count the arrival against the post or email that brought it: the tag, this page and the day, nothing about the visitor.
    if (q.get("utm_source") && navigator.sendBeacon) {
      navigator.sendBeacon("https://wboavagwignktkodqvwa.supabase.co/functions/v1/hit",
        JSON.stringify({ s: q.get("utm_source"), m: q.get("utm_medium") || "", c: q.get("utm_campaign") || "", p: location.pathname }));
    }
  } catch (e) {}
})();
