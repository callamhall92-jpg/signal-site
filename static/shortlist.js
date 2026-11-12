// Opened from "Remind me before this closes" in an alert, or "Stop reminders" in a reminder.
(function () {
  var main = document.getElementById("main");
  var q = new URLSearchParams(location.search);
  var token = q.get("t"), record = q.get("r"), action = q.get("do") === "remove" ? "remove" : "add";
  var title = document.getElementById("sl-title"), text = document.getElementById("sl-text");
  var actions = document.getElementById("sl-actions"), undoWrap = document.getElementById("sl-undo-wrap");
  function show(h, p) { title.textContent = h; text.textContent = p; }
  function nice(iso) {
    var d = new Date(iso + "T12:00:00Z");
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  }
  function calendar(name, iso, url) {
    function esc(s) { return String(s).replace(/\\/g, "\\\\").replace(/([,;])/g, "\\$1").replace(/\r?\n/g, " "); }
    var day = iso.replace(/-/g, "");
    var next = new Date(iso + "T00:00:00Z"); next.setUTCDate(next.getUTCDate() + 1);
    var end = next.toISOString().slice(0, 10).replace(/-/g, "");
    var ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Noticehawk//Shortlist//EN", "BEGIN:VEVENT",
      "UID:" + record + "@noticehawk.co.uk", "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z",
      "DTSTART;VALUE=DATE:" + day, "DTEND;VALUE=DATE:" + end, "SUMMARY:" + esc("Tender closes: " + name),
      "DESCRIPTION:" + esc("Check the official notice for the exact closing time. " + url), "URL:" + url,
      "BEGIN:VALARM", "TRIGGER:-P2D", "ACTION:DISPLAY", "DESCRIPTION:" + esc("Tender closes in 2 days: " + name), "END:VALARM",
      "END:VEVENT", "END:VCALENDAR"].join("\r\n");
    return URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
  }
  function call(what) {
    return fetch(main.dataset.api, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token, record: record, action: what })
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (b) { return { status: res.status, body: b }; });
    });
  }
  function run(what) {
    actions.hidden = true; undoWrap.hidden = true;
    call(what).then(function (r) {
      var b = r.body;
      if (r.status === 200 && b.result === "added") {
        if (!b.open || !b.deadline) {
          show("That tender has closed", "“" + b.title + "” is no longer open, so there is nothing to remind you about.");
          return;
        }
        show("On your shortlist", "“" + b.title + "” closes on " + nice(b.deadline) +
          ". We will email you seven days and two days before.");
        document.getElementById("sl-notice").href = b.url;
        document.getElementById("sl-cal").href = calendar(b.title, b.deadline, b.url);
        actions.hidden = false; undoWrap.hidden = false;
      } else if (r.status === 200) {
        show("Removed", "“" + b.title + "” is off your shortlist. You will get no more reminders about it.");
      } else if (r.status === 403) {
        show("Reminders are part of the paid plans", "Upgrade from the pricing page to shortlist tenders and get deadline reminders.");
      } else {
        show("That link did not work", "Open it again from your most recent email, or write to hello@noticehawk.co.uk.");
      }
    }).catch(function () { show("That did not go through", "Check your connection and open the link again."); });
  }
  if (!token || !record) { show("This link is incomplete", "Open it again from one of our emails."); return; }
  document.getElementById("sl-undo").addEventListener("click", function () { run("remove"); });
  run(action);
})();
