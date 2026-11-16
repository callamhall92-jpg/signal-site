// Remembers, for this visit only, where the visitor first arrived from, so a sign-up can say which channel brought it.
(function () {
  try {
    if (sessionStorage.getItem("nh_from")) return;
    var q = new URLSearchParams(location.search), ref = "";
    try { var h = new URL(document.referrer).hostname; if (h && h.replace(/^www\./, "") !== location.hostname.replace(/^www\./, "")) ref = h; } catch (e) {}
    var utm = [q.get("utm_source"), q.get("utm_medium"), q.get("utm_campaign")].filter(Boolean).join(" / ");
    sessionStorage.setItem("nh_from", JSON.stringify({ ref: ref, utm: utm }));
  } catch (e) {}
})();
