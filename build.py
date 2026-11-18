"""Builds the static site into dist/ from the templates and the live public figures."""
from __future__ import annotations

import hashlib
import html
from types import SimpleNamespace
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from string import Template

import content

ROOT = Path(__file__).parent
CATEGORY_LABELS = {
    "new_build": "New build", "refurbishment": "Refurbishment",
    "repairs_maintenance": "Repairs and maintenance", "mechanical_electrical": "Mechanical and electrical",
    "roofing": "Roofing", "groundworks_civils": "Groundworks and civils",
    "design_professional": "Design and professional services", "other": "Other",
}
NOTICE_PREFIXES = ("https://www.find-tender.service.gov.uk/", "https://www.contractsfinder.service.gov.uk/",
                   "https://www.publiccontractsscotland.gov.uk/")

FAQ = [
    ("What is Noticehawk?",
     "Email alerts of UK public-sector tenders for construction and building maintenance firms, "
     "filtered to your regions and type of work and scored out of 100 for how well each suits a smaller firm. "
     "The free plan sends three every Monday; paid plans send every match, with new ones each weekday."),
    ("Where do the tenders come from?",
     "From the official notice services: Find a Tender, Contracts Finder and Public Contracts Scotland. "
     "We check them every day and link each alert to the official notice."),
    ("How is the score worked out?",
     "A fixed points table: how closely the work matches construction and maintenance, the contract value, "
     "the days left to bid, and whether the buyer has split it into lots or marked it suitable for smaller firms. "
     "Every tender is scored the same way."),
    ("What kinds of work are covered?",
     "New build, refurbishment, repairs and maintenance, mechanical and electrical, roofing, "
     "groundworks and civils, and design and professional services."),
    ("Does Noticehawk help with the bid?",
     "Yes, on paid plans. AI assist reads each notice and any documents the buyer has published, and gives you the key dates, "
     "what the buyer asks for (insurance, accreditations, turnover, how bids are scored) and a checklist of what to have ready. "
     "It does not write or submit the bid: you bid through the buyer's own portal."),
    ("What is in each plan?",
     "The table under the plans on this page lists every feature against every plan, from Free to Premium."),
    ("Can I post work for subcontractors?",
     "Yes, free. Contractors can post a package of work on the subcontract board and firms reply to them directly. "
     "There is no fee and no commission."),
    ("What does it cost?",
     "The Free plan sends three tenders a week for one region and one type of work. "
     "Paid plans start at £29 a month and can be cancelled at any time."),
]


# Every feature against every plan. Y and N render as a tick and a dash. Kept in step with the plan
# entitlements in the database and with the welcome emails.
PLAN_NAMES = ["Free", "Basic", "Professional", "Premium"]
Y, N = True, False
PLAN_MATRIX = [
    ("Price a month", ["£0", "£29", "£79", "£149"]),
    ("Regions", ["1", "1", "3", "All"]),
    ("Types of work", ["1", "1", "3", "All"]),
    ("Matching tenders in the Monday alert", ["3", "All", "All", "All"]),
    ("New matches by email each weekday", [N, Y, Y, Y]),
    ("Score out of 100, the reasons, and our short read", [N, Y, Y, Y]),
    ("Your tenders online, filtered by county, council or distance", [N, Y, Y, Y]),
    ("Scores tuned to the contract sizes you want", [N, Y, Y, Y]),
    ("Shortlist with deadline reminders", [N, Y, Y, Y]),
    ("Contracts coming up for renewal", [N, Y, Y, Y]),
    ("AI assist: key dates and a checklist for each bid", [N, Y, Y, Y]),
    ("AI assist: the buyer's stated requirements (insurance, accreditations, turnover, scoring)", [N, N, Y, Y]),
    ("What the tender documents say", [N, N, Y, Y]),
    ("Who each buyer usually awards to, and who wins locally", [N, N, Y, Y]),
    ("Planned tenders before they are advertised", [N, N, Y, Y]),
    ("New awards near you, for subcontract work", [N, N, Y, Y]),
    ("Spreadsheet download", [N, N, Y, Y]),
    ("Follow buyers wherever they tender", [N, N, N, "10"]),
    ("Keyword watch list", [N, N, N, "10"]),
    ("Competitor watch list", [N, N, N, "5"]),
    ("Monthly market report for your area", [N, N, N, Y]),
    ("Guides by email, and the subcontract work board", [Y, Y, Y, Y]),
    ("Cancel any time, no contract", [Y, Y, Y, Y]),
]


def compare_table() -> str:
    def cell(v) -> str:
        if v is True:
            return '<td class="yes"><span aria-hidden="true">✓</span><span class="sr">Included</span></td>'
        if v is False:
            return '<td class="no"><span aria-hidden="true">–</span><span class="sr">Not included</span></td>'
        return f"<td>{html.escape(v)}</td>"
    short = {"Professional": "Pro", "Premium": "Prem"}
    head = "".join(f'<th scope="col"><span class="long">{p}</span><span class="short" aria-hidden="true">{short.get(p, p)}</span></th>' for p in PLAN_NAMES)
    rows = "".join(f'<tr><th scope="row">{html.escape(label)}</th>{"".join(cell(v) for v in values)}</tr>' for label, values in PLAN_MATRIX)
    return (f'<div class="compare-box"><table class="compare"><thead><tr><th scope="col">What you get</th>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def money(value) -> str:
    if value is None or float(value) < 500:      # buyers sometimes enter £0 or £1 as a placeholder
        return "Not stated"
    value = float(value)
    for limit, div, unit in ((1e9, 1e9, "bn"), (1e6, 1e6, "m"), (1e3, 1e3, "k")):
        if value >= limit:
            n = value / div
            return f"£{n:.1f}".rstrip("0").rstrip(".") + unit if n < 100 else f"£{n:.0f}{unit}"
    return f"£{value:.0f}"


def sample_rows(rows: list[dict]) -> str:
    out = []
    for r in rows[:5]:
        url = r.get("url") or ""
        if not url.startswith(NOTICE_PREFIXES):
            continue
        score = int(r["score"])
        note = (r.get("reason") or "").split(";")[-1].strip().capitalize()
        place = " · ".join(x for x in (r.get("region"), CATEGORY_LABELS.get(r.get("category"), "")) if x)
        days = int(r["days"])
        out.append(
            f'<tr><td><span class="score{" high" if score >= 80 else ""}">{score}</span></td>'
            f'<td><a href="{html.escape(url, quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
            f'<small>{html.escape(place)}</small></td>'
            f'<td class="muted">{html.escape(r.get("buyer") or "")}</td>'
            f'<td class="num" data-label="Value">{money(r.get("value"))}</td>'
            f'<td class="num" data-label="Closes in">{days} day{"" if days == 1 else "s"}</td></tr>')
    if not out:
        out.append('<tr><td colspan="5" class="muted">This week\'s examples are being refreshed.</td></tr>')
    return "\n".join(out)


def chips(items: list[dict], labels: dict | None = None, links: dict | None = None) -> str:
    out = []
    for i in items:
        text = f'{html.escape((labels or {}).get(i["name"], i["name"]))}<span>{int(i["n"])}</span>'
        href = (links or {}).get(i["name"])
        out.append(f'<li><a href="{href}">{text}</a></li>' if href else f"<li>{text}</li>")
    return "\n".join(out)


REGIONS = ["East Midlands", "East of England", "London", "North East", "North West", "Northern Ireland",
           "Scotland", "South East", "South West", "Wales", "West Midlands", "Yorkshire and the Humber"]
WORK_TYPES = ["repairs_maintenance", "refurbishment", "new_build", "mechanical_electrical", "roofing",
              "groundworks_civils", "design_professional"]


def pay_links(cfg: dict) -> dict:
    """Plan buttons go to Stripe checkout once sign-ups are open; before that, to the early-access box."""
    links = cfg.get("payment_links") or {}
    out = {}
    for key, product in (("pay_basic", "construction_basic"), ("pay_pro", "construction_pro"),
                         ("pay_premium", "construction_premium")):
        url = links.get(product) if cfg.get("signup_open") else None
        out[key] = html.escape(url, quote=True) if url else "#start"
    return out


def start_block(cfg: dict, rates: list | None = None) -> str:
    email = html.escape(cfg["contact_email"])
    if not cfg.get("signup_open"):
        return (
            '<div><h2>Free accounts open shortly.</h2>'
            '<p>Three tenders a week for your region and your kind of work, free. '
            'Paid plans add the full scored list.</p></div>'
            f'<div class="card"><strong>Want to be first in?</strong>'
            f'<span>Email us with your region and the work you do, and we will set you up on day one.</span>'
            f'<a class="btn dark" style="text-align:center" href="mailto:{email}?subject=Noticehawk%20early%20access">Email {email}</a>'
            '<span class="fine">We never sell or share your details.</span></div>')
    regions = "".join(f"<option>{html.escape(r)}</option>" for r in REGIONS)
    rates_attr = html.escape(json.dumps({r["region"] + "|" + r["category"]: float(r["per_week"]) for r in (rates or [])}), quote=True)
    work = "".join(f'<option value="{w}">{html.escape(CATEGORY_LABELS[w])}</option>' for w in WORK_TYPES)
    return (
        '<div><h2>Start with three tenders a week, free.</h2>'
        '<p>Pick your region and the work you do. Upgrade any time for the full scored list.</p></div>'
        f'<form class="card" id="signup" action="{html.escape(cfg["signup_url"], quote=True)}" method="post" novalidate '
        f'data-rates="{rates_attr}">'
        '<label for="s-email">Work email</label>'
        '<input id="s-email" name="email" type="email" autocomplete="email" required>'
        '<label for="s-company">Company name or number <span class="fine">(optional)</span></label>'
        '<input id="s-company" name="company" type="text" autocomplete="organization" maxlength="160">'
        '<div class="pair">'
        f'<div><label for="s-region">Region</label><select id="s-region" name="region" required><option value="">Choose</option>{regions}</select></div>'
        f'<div><label for="s-work">Main type of work</label><select id="s-work" name="work" required><option value="">Choose</option>{work}</select></div>'
        '</div>'
        '<p class="fine" id="s-rate" aria-live="polite"></p>'
        '<div class="trap" aria-hidden="true"><label for="s-website">Leave this empty</label>'
        '<input id="s-website" name="website" type="text" tabindex="-1" autocomplete="off"></div>'
        '<label class="check"><input name="product_updates" type="checkbox" checked>'
        '<span>Send me a helpful guide every couple of weeks, and the odd note about paid plans. Untick if you would rather not.</span></label>'
        '<label class="check"><input name="partner_opt_in" type="checkbox">'
        '<span>Send me offers from selected partners, such as bid writers and insurers. Optional.</span></label>'
        '<button class="btn dark" type="submit">Start free</button>'
        '<p class="msg" id="signup-msg" role="status" aria-live="polite"></p>'
        '<span class="fine">We never sell or share your details. See the <a href="/privacy/">privacy notice</a>.</span>'
        '</form><script src="/signup.js" defer></script>')


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-").replace("--", "-")


def category_slug(category: str) -> str:
    return slug(CATEGORY_LABELS[category])


HEADER = ('<div class="night"><header><div class="wrap"><a class="brand" href="/"><i aria-hidden="true"></i>Noticehawk</a>'
          '<nav class="main" aria-label="Main"><a href="/this-week/">This week</a><a href="/tenders/">Browse tenders</a><a href="/guides/">Guides</a><a href="/how-it-works/">How it works</a><a href="/#pricing">Pricing</a><a href="/login/">Sign in</a>'
          '<a class="btn small" href="/#start">Start free</a></nav></div></header></div>')


def listing_pages(stats: dict) -> list[dict]:
    """One page per work type, per region and per pairing that has at least one open tender."""
    rows = [r for r in (stats.get("listings") or [])
            if (r.get("url") or "").startswith(NOTICE_PREFIXES) and r.get("category") in CATEGORY_LABELS and r.get("region") in REGIONS]
    rows.sort(key=lambda r: (int(r["days"]), r["title"]))      # soonest deadline first
    pages = []
    for cat in WORK_TYPES:
        hits = [r for r in rows if r["category"] == cat or cat in (r.get("also") or [])]
        if hits:
            pages.append({"path": f"/tenders/{category_slug(cat)}/", "category": cat, "region": None, "rows": hits})
    for region in REGIONS:
        hits = [r for r in rows if r["region"] == region]
        if hits:
            pages.append({"path": f"/tenders/{slug(region)}/", "category": None, "region": region, "rows": hits})
        for cat in WORK_TYPES:
            both = [r for r in hits if r["category"] == cat or cat in (r.get("also") or [])]
            if both:
                pages.append({"path": f"/tenders/{category_slug(cat)}/{slug(region)}/", "category": cat, "region": region, "rows": both})
    return pages


def place_phrase(region: str) -> str:
    return f"in {region}" if region in ("London", "Wales", "Scotland", "Northern Ireland", "Yorkshire and the Humber") else f"in the {region}"


def listing_title(page: dict) -> str:
    work = CATEGORY_LABELS[page["category"]] if page["category"] else "Construction"
    return f"{work} tenders" + (f" {place_phrase(page['region'])}" if page["region"] else " in the UK")


def work_note(r: dict, page_category: str | None) -> str | None:
    """On an all-work page, the tender's type of work; on a type-of-work page, only when it is there as an extra."""
    if not page_category:
        return CATEGORY_LABELS.get(r["category"])
    if r["category"] != page_category and r["category"] in CATEGORY_LABELS:
        return f'{CATEGORY_LABELS[r["category"]]}, includes {CATEGORY_LABELS[page_category].lower()}'
    return None


def render_listing(page: dict, pages: list[dict], cfg: dict, updated_text: str) -> tuple[str, str]:
    rows, title = page["rows"], listing_title(page)
    shown = rows[:12]
    body_rows = "\n".join(
        f'<tr><td><a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
        f'<small>{html.escape(" · ".join(x for x in (None if page["region"] else r["region"], work_note(r, page["category"])) if x))}</small></td>'
        f'<td class="muted">{html.escape(r.get("buyer") or "Not stated")}</td>'
        f'<td class="num" data-label="Value">{money(r.get("value"))}</td>'
        f'<td class="num" data-label="Closes in">{int(r["days"])} day{"" if int(r["days"]) == 1 else "s"}</td></tr>' for r in shown)
    n = len(rows)
    more = (f'<p class="more">Showing the {len(shown)} closing soonest of {n}. Subscribers get every one, scored for a firm their size.</p>'
            if n > len(shown) else "")
    def related(label, items):
        links = "".join(f'<li><a href="{p["path"]}">{html.escape(text)}<span>{len(p["rows"])}</span></a></li>' for text, p in items)
        return f'<h2 class="sub">{label}</h2><ul class="chips links">{links}</ul>' if links else ""
    if page["category"] and page["region"]:
        rel = related(f"{CATEGORY_LABELS[page['category']]} tenders in other regions",
                      [(p["region"], p) for p in pages if p["category"] == page["category"] and p["region"] and p is not page])
        rel += related(f"Other work {place_phrase(page['region'])}",
                       [(CATEGORY_LABELS[p["category"]], p) for p in pages if p["region"] == page["region"] and p["category"] and p is not page])
    elif page["category"]:
        rel = related("By region", [(p["region"], p) for p in pages if p["category"] == page["category"] and p["region"]])
    else:
        rel = related("By type of work", [(CATEGORY_LABELS[p["category"]], p) for p in pages if p["region"] == page["region"] and p["category"]])
    crumbs = [("Home", "/"), ("Tenders", "/tenders/")]
    if page["category"] and page["region"]:
        crumbs.append((CATEGORY_LABELS[page["category"]], f"/tenders/{category_slug(page['category'])}/"))
    crumbs.append((title, page["path"]))
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": cfg["site_url"] + path} for i, (name, path) in enumerate(crumbs)]},
        {"@type": "ItemList", "name": title, "numberOfItems": n, "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["title"], "url": r["url"]} for i, r in enumerate(shown)]}]}
    head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    trail = " › ".join(f'<a href="{path}">{html.escape(name)}</a>' for name, path in crumbs[:-1])
    body = (HEADER + '<main id="main" class="doc wide">'
            f'<p class="trail">{trail}</p><h1>{html.escape(title)}</h1>'
            f'<p class="lede dark">{n} open public-sector tender{"" if n == 1 else "s"} on {updated_text}, '
            f'checked daily against the official notice services. The next closes in {int(rows[0]["days"])} days.</p>'
            '<div class="tablebox light"><table class="rows"><thead><tr><th scope="col">Tender</th><th scope="col">Buyer</th>'
            f'<th scope="col">Value</th><th scope="col">Closes</th></tr></thead><tbody>{body_rows}</tbody></table></div>'
            f'{more}<div class="cta-box"><div><strong>Get these by email every Monday.</strong>'
            '<span>Three a week free, or every matching tender with a score out of 100 from £29 a month.</span></div>'
            '<a class="btn" href="/#start">Start free</a></div>'
            f'{rel}</main>')
    return body, head


PART_LABELS = [("fit", "Fit with your work"), ("value", "Contract size"), ("time", "Time to bid"),
               ("sme", "Suits smaller firms"), ("detail", "Detail in the notice")]


def closing_text(days: int) -> str:
    return f"closes in {days} day{'' if days == 1 else 's'}"


def example_alert(stats: dict, updated_text: str) -> str:
    """A subscriber email laid out as it arrives, using this week's live sample tenders."""
    cards = []
    for r in (stats.get("sample") or [])[:4]:
        url = r.get("url") or ""
        if not url.startswith(NOTICE_PREFIXES):
            continue
        parts = r.get("parts") or {}
        line = " · ".join(f"{label} {parts[k][0]}/{parts[k][1]}" for k, label in PART_LABELS if k in parts)
        missing = parts.get("missing") or []
        meta = " | ".join(x for x in (r.get("region"), CATEGORY_LABELS.get(r.get("category"), ""), money(r.get("value")),
                                      closing_text(int(r["days"]))) if x)
        cards.append(
            '<div class="mail-item"><span class="score high">' + str(int(r["score"])) + '</span><div>'
            f'<a href="{html.escape(url, quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
            f'<p>{html.escape(r.get("buyer") or "Buyer not stated")}</p><p>{html.escape(meta)}</p>'
            f'<p class="why">{html.escape(r.get("reason") or "")}</p>'
            + (f'<p class="why">{html.escape(line)}</p>' if line else "")
            + (f'<p class="check"><strong>Check first:</strong> Not stated in the notice: {html.escape(", ".join(missing))}.</p>' if missing else "")
            + '<p class="remind">AI assist: what this bid needs · Remind me before this closes</p></div></div>')
    if not cards:
        cards.append('<p>This week\'s example is being refreshed.</p>')
    return (HEADER + '<main id="main" class="doc"><h1>What a Noticehawk alert looks like</h1>'
            f'<p class="lede dark">This is the Monday email a paying subscriber receives, filled with real tenders open on {updated_text}. '
            'Yours contains only your regions and your type of work.</p>'
            '<div class="mail"><div class="mail-head"><strong>Noticehawk</strong>'
            f'<span>{len(cards)} tenders for you this week</span></div>' + "".join(cards)
            + '<div class="mail-foot">You are on the Professional plan. Change your regions and work types, or unsubscribe, from any email.</div></div>'
            '<h2>What each part means</h2><ul>'
            '<li><strong>The score</strong> is out of 100. <a href="/how-it-works/">How it is worked out</a>.</li>'
            '<li><strong>The points line</strong> shows where the score came from, so you can see at a glance why a tender ranks where it does.</li>'
            '<li><strong>Check first</strong> flags anything the notice leaves out and anything that should give you pause, such as a short deadline.</li>'
            '<li><strong>Remind me</strong> adds the tender to your shortlist. You get a reminder seven days and two days before it closes.</li>'
            '</ul><p>Free accounts get three tenders a week without the scores. Paid alerts also list contracts coming up for renewal, '
            'and Professional and Premium add newly awarded contracts near you.</p>'
            '<div class="cta-box"><div><strong>Get this for your region.</strong><span>Three tenders a week free, no card needed.</span></div>'
            '<a class="btn" href="/#start">Start free</a></div></main>')


def weekly_digest(stats: dict, updated_text: str, cfg: dict) -> tuple[str, str]:
    """The ten most interesting tenders published in the last week, with links to the official notices."""
    rows = [r for r in (stats.get("digest") or []) if (r.get("url") or "").startswith(NOTICE_PREFIXES)][:10]
    body_rows = "\n".join(
        f'<tr><td><a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
        f'<small>{html.escape(" · ".join(x for x in (r.get("region"), CATEGORY_LABELS.get(r.get("category"), "")) if x))}</small></td>'
        f'<td class="muted">{html.escape(r.get("buyer") or "Not stated")}</td>'
        f'<td class="num" data-label="Value">{money(r.get("value"))}</td>'
        f'<td class="num" data-label="Closes in">{int(r["days"])} days</td></tr>' for r in rows)
    if not rows:
        body_rows = '<tr><td colspan="4" class="muted">This week\'s list is being put together.</td></tr>'
    ld = {"@context": "https://schema.org", "@type": "ItemList", "name": "Construction tenders worth a look this week",
          "numberOfItems": len(rows), "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": r["title"], "url": r["url"]} for i, r in enumerate(rows)]}
    head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    body = (HEADER + '<main id="main" class="doc wide"><h1>Construction tenders worth a look this week</h1>'
            f'<p class="lede dark">The {len(rows) or "ten"} highest-scoring UK public-sector construction and building maintenance tenders '
            f'published in the last week, as of {updated_text}. Each links to its official notice.</p>'
            '<div class="tablebox light"><table class="rows"><thead><tr><th scope="col">Tender</th><th scope="col">Buyer</th>'
            f'<th scope="col">Value</th><th scope="col">Closes in</th></tr></thead><tbody>{body_rows}</tbody></table></div>'
            '<p class="more">This list is the same for everyone. Subscribers get the tenders for their own regions and type of work, with a score for each. '
            '<a href="/example-alert/">See an example alert</a>.</p>'
            '<div class="cta-box"><div><strong>Get your own list every Monday.</strong>'
            '<span>Three a week free, or every matching tender with a score out of 100 from £29 a month.</span></div>'
            '<a class="btn" href="/#start">Start free</a></div>'
            '<p><a href="/tenders/">Browse all open tenders by region and type of work</a></p></main>')
    return body, head


GUIDES = [
    ("finding-public-sector-construction-tenders", "How to find UK public-sector construction tenders",
     "Where UK public bodies publish construction tenders: Find a Tender, Contracts Finder, Public Contracts Scotland, Sell2Wales and eTendersNI, with the thresholds that decide which."),
    ("procurement-act-2023-construction", "The Procurement Act 2023: what changed for construction firms",
     "What the Procurement Act 2023 changed for construction and maintenance firms: one place for notices, VAT-inclusive thresholds, open frameworks and local reservations."),
    ("frameworks-and-call-offs", "Frameworks and call-offs explained for construction firms",
     "How public-sector frameworks and call-off contracts work under the Procurement Act 2023, how long they last, and what they mean for smaller construction firms."),
    ("tender-alert-services-compared", "UK tender alert services compared",
     "Free official tender sites and paid UK tender alert services side by side: free options, published prices and what each focuses on."),
    ("winning-public-sector-work-small-construction-firms", "How small construction firms win public-sector work",
     "How smaller UK construction and maintenance firms win public-sector contracts: choosing tenders, registering, bid decisions, scoring and feedback under the Procurement Act 2023."),
    ("tender-paperwork-checklist", "The paperwork buyers ask for: a checklist for construction tenders",
     "The insurance, health and safety, financial and policy documents UK public buyers usually ask construction firms for, and when each is needed."),
    ("writing-a-tender-response-that-scores-well", "Writing a tender response that scores well",
     "How public-sector construction tenders are marked, and how to answer quality, price and social value questions so your bid scores well."),
]
GUIDE_DATES = {"winning-public-sector-work-small-construction-firms": "2026-11-17", "tender-paperwork-checklist": "2026-11-17",
               "writing-a-tender-response-that-scores-well": "2026-11-17"}
GUIDE_CTA = ('<div class="cta-box"><div><strong>Get the tenders for your region and type of work every Monday.</strong>'
             '<span>Three a week free, or every matching tender scored out of 100, with AI assist to show what each bid needs, from £29 a month. <a href="/#compare">What each plan includes</a>.</span></div>'
             '<a class="btn" href="/#start">Start free</a></div>')


HOME_GUIDES = [
    ("winning-public-sector-work-small-construction-firms", "How small construction firms win public-sector work",
     "Choosing tenders you can win, what to have ready, and how to use buyers' feedback."),
    ("tender-paperwork-checklist", "The paperwork buyers ask for",
     "The insurance, health and safety and financial documents to have ready before a tender lands."),
    ("writing-a-tender-response-that-scores-well", "Writing a tender response that scores well",
     "How tenders are marked, and how to answer quality, price and social value questions."),
]


def guide_cards() -> str:
    return "\n".join(f'<a class="guide-card" href="/guides/{s_}/"><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p>'
                     '<span>Read the guide</span></a>' for s_, t, d in HOME_GUIDES)


def write_guides(base: str, cfg: dict, out: Path, insight: bool) -> list[str]:
    paths = []
    (out / "guides").mkdir()
    for slug_, title, desc in GUIDES:
        body = Template((ROOT / "templates" / "guides" / f"{slug_}.html").read_text()).substitute(header=HEADER, cta=GUIDE_CTA)
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": title, "description": desc,
              "dateModified": GUIDE_DATES.get(slug_, "2026-11-16"), "author": {"@type": "Organization", "name": "Noticehawk"},
              "publisher": {"@type": "Organization", "name": "Noticehawk"}}
        head = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>"
        (out / "guides" / slug_).mkdir()
        (out / "guides" / slug_ / "index.html").write_text(page(base, cfg, f"/guides/{slug_}/", f"{title} | Noticehawk", desc, body, head))
        paths.append(f"/guides/{slug_}/")
    items = "".join(f'<li><a href="/guides/{s_}/">{html.escape(t)}</a><br><span class="muted">{html.escape(d)}</span></li>' for s_, t, d in GUIDES)
    if insight:
        items = ('<li><a href="/insights/">Monthly market reports</a><br>'
                 '<span class="muted">Construction contracts awarded by public bodies each month: values, types of work, buyers and winners.</span></li>'
                 '<li><a href="/buyers/">Public buyers</a><br>'
                 '<span class="muted">What each busy public buyer awards, the firms that win most often, and what is open now.</span></li>') + items
    body = (HEADER + '<main id="main" class="doc"><h1>Guides for construction firms bidding for public work</h1>'
            f'<ul class="guides">{items}</ul>{GUIDE_CTA}</main>')
    (out / "guides" / "index.html").write_text(page(base, cfg, "/guides/", "Guides to public-sector construction tenders | Noticehawk",
                                                    "Plain-English guides to finding and winning UK public-sector construction and maintenance tenders.", body))
    return ["/guides/"] + paths


def json_ld(cfg: dict) -> str:
    site = cfg["site_url"]
    graph = [
        {"@type": "Organization", "@id": f"{site}/#org", "name": "Noticehawk", "url": site,
         "email": cfg["contact_email"], "logo": f"{site}/favicon.svg",
         "description": "Tender alerts for UK construction and building maintenance firms."},
        {"@type": "WebSite", "@id": f"{site}/#site", "url": site, "name": "Noticehawk",
         "publisher": {"@id": f"{site}/#org"}, "inLanguage": "en-GB"},
        {"@type": "Service", "name": "Noticehawk tender alerts", "provider": {"@id": f"{site}/#org"},
         "areaServed": "GB", "serviceType": "Public-sector tender alerts for construction and building maintenance",
         "offers": [{"@type": "Offer", "name": n, "price": p, "priceCurrency": "GBP"}
                    for n, p in (("Free", "0"), ("Basic", "29"), ("Professional", "79"), ("Premium", "149"))]},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]},
    ]
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{data}</script>'


def analytics(cfg: dict, head_extra: str) -> str:
    """Cookie-free visit counting on public pages only.

    Account pages (marked noindex) carry a personal link in their address, so they are never measured.
    """
    token = cfg.get("analytics_token")
    if not token or "noindex" in head_extra:
        return ""
    beacon = html.escape(json.dumps({"token": token}), quote=True)
    return f'<script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon="{beacon}"></script>'


_ASSET = re.compile(r'(href|src)="/([a-z]+\.(?:css|js))"')
_ASSET_VERSIONS: dict[str, str] = {}


def _versioned(match) -> str:
    """Add a short fingerprint to our own stylesheet and scripts, so browsers and Cloudflare
    fetch the new file as soon as it changes instead of showing a cached old one."""
    name = match.group(2)
    if name not in _ASSET_VERSIONS:
        f = ROOT / "static" / name
        _ASSET_VERSIONS[name] = hashlib.sha256(f.read_bytes()).hexdigest()[:10] if f.exists() else ""
    v = _ASSET_VERSIONS[name]
    return f'{match.group(1)}="/{name}{"?v=" + v if v else ""}"'


def page(base: str, cfg: dict, path: str, title: str, description: str, body: str, head_extra: str = "") -> str:
    out = Template(base).substitute(
        title=html.escape(title), description=html.escape(description, quote=True),
        canonical=cfg["site_url"] + path, head_extra=head_extra, body=body, email=html.escape(cfg["contact_email"]),
        analytics=analytics(cfg, head_extra))
    return _ASSET.sub(_versioned, out)


# Readable titles: the buyer's reference codes and procedure markers dropped (same rules as the alert emails).
_MARKER = re.compile(r"^\s*(\(?\s*(itt|rfq|rfp|itq|eoi|pin|tender)\s*\)?\s*[-:–—]\s*|\(\s*(itt|rfq|rfp|itq)\s*\)\s*)", re.I)
# A leading code: one token with a digit, then a separator; or a token with four or more digits, then a space.
_CODE_SEP = re.compile(r"^\s*(?!(?:19|20)\d\d(?:[-/]\d{2,4})?\s)[A-Za-z]*[A-Za-z0-9/._-]*\d[A-Za-z0-9/._-]*\s*[-:–—]\s+")
_CODE_LONG = re.compile(r"^\s*(?!(?:19|20)\d\d(?:[-/]\d{2,4})?\s)[A-Za-z0-9/._-]*\d{4,}[A-Za-z0-9/._-]*\s+")
_TRAIL = re.compile(r"\s*\(\s*[A-Z0-9][A-Z0-9 /._-]*\d[A-Z0-9 /._-]*\)\s*$")


def tidy_title(title: str | None) -> str:
    if not title:
        return title or ""
    out = title.strip()
    for _ in range(3):
        before = out
        out = _MARKER.sub("", out)
        out = _CODE_SEP.sub("", out)
        out = _CODE_LONG.sub("", out)
        if out == before:
            break
    out = _TRAIL.sub("", out).strip(" -–—:")
    return out if len(out) >= 8 else title.strip()


def build(stats: dict, cfg: dict, out: Path) -> None:
    stats = {**stats, **{k: [{**r, "title": tidy_title(r.get("title"))} for r in (stats.get(k) or [])] for k in ("sample", "listings", "digest")}}
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out)
    base = (ROOT / "templates" / "base.html").read_text()
    updated = datetime.fromisoformat(stats["generated_at"]).astimezone(timezone.utc)
    updated_text = f"{updated.day} {updated:%B %Y}"
    pages = listing_pages(stats)
    home = Template((ROOT / "templates" / "home.html").read_text()).substitute(
        open_count=f'{int(stats["open_count"]):,}', value_total=money(stats["value_total"]),
        closing_14=f'{int(stats["closing_14"]):,}', updated=updated_text,
        sample_rows=sample_rows(stats.get("sample") or []),
        region_chips=chips(stats.get("regions") or [], None, {p["region"]: p["path"] for p in pages if p["region"] and not p["category"]}),
        category_chips=chips(stats.get("categories") or [], CATEGORY_LABELS, {p["category"]: p["path"] for p in pages if p["category"] and not p["region"]}),
        start_block=start_block(cfg, stats.get("rates")),
        **pay_links(cfg),
        guide_cards=guide_cards(), compare_table=compare_table(),
        hero_note=("Three tenders a week for your region, free. No card needed." if cfg.get("signup_open")
                   else "Free accounts open shortly: three tenders a week for your region, no card needed."),
        faq_html="\n".join(f"<div><h3>{html.escape(q)}</h3><p>{html.escape(a)}</p></div>" for q, a in FAQ))
    (out / "index.html").write_text(page(
        base, cfg, "/", "Noticehawk | Construction and building maintenance tender alerts",
        f"{int(stats['open_count']):,} open UK public-sector construction tenders, scored for smaller firms "
        "and sent by email each week. Free for three tenders a week.",
        home, json_ld(cfg)))
    for name, title, description in (
            ("privacy", "Privacy notice | Noticehawk", "How Noticehawk collects, uses and protects personal data."),
            ("terms", "Terms of service | Noticehawk", "The terms that apply to the Noticehawk tender alert service.")):
        body = Template((ROOT / "templates" / f"{name}.html").read_text()).substitute(email=html.escape(cfg["contact_email"]))
        (out / name).mkdir()
        (out / name / "index.html").write_text(page(base, cfg, f"/{name}/", title, description, body))
    how = Template((ROOT / "templates" / "how-it-works.html").read_text()).substitute(
        header=HEADER, email=html.escape(cfg["contact_email"]))
    (out / "how-it-works").mkdir()
    (out / "how-it-works" / "index.html").write_text(page(
        base, cfg, "/how-it-works/", "How Noticehawk works: sources, checks and scoring | Noticehawk",
        "Where Noticehawk's tenders come from, how often they are checked, how changed and withdrawn notices are handled, and how each score out of 100 is worked out.", how))
    (out / "example-alert").mkdir()
    (out / "example-alert" / "index.html").write_text(page(
        base, cfg, "/example-alert/", "Example tender alert email | Noticehawk",
        "See the weekly email a Noticehawk subscriber receives: scored construction tenders with the points behind each score and what to check first.",
        example_alert(stats, updated_text)))
    helpers = SimpleNamespace(HEADER=HEADER, CATEGORY_LABELS=CATEGORY_LABELS, NOTICE_PREFIXES=NOTICE_PREFIXES, money=money,
                              slug=slug, tidy_title=tidy_title, page=page)
    made = content.write(helpers, base, cfg, out, stats, pages, updated_text)
    insight = made["insights"]
    digest_body, digest_head = weekly_digest(stats, updated_text, cfg)
    if made["weekly"]:
        digest_body = digest_body.replace(
            '<p><a href="/tenders/">Browse all open tenders by region and type of work</a></p>',
            '<h2 class="sub">New this week by region</h2><ul class="chips links">'
            + "".join(f'<li><a href="{p}">{html.escape(t)}</a></li>' for t, p in made["weekly"])
            + '</ul><p><a href="/tenders/">Browse all open tenders by region and type of work</a></p>')
    (out / "this-week").mkdir(exist_ok=True)
    (out / "this-week" / "index.html").write_text(page(
        base, cfg, "/this-week/", "Construction tenders worth a look this week | Noticehawk",
        f"The highest-scoring UK public-sector construction and building maintenance tenders published in the last week, updated {updated_text}.",
        digest_body, digest_head))
    guide_paths = write_guides(base, cfg, out, bool(insight))
    simple = ('<div class="night"><header><div class="wrap"><a class="brand" href="/"><i aria-hidden="true"></i>Noticehawk</a>'
              '</div></header></div><main id="main" class="doc"><h1>{h}</h1><p>{p}</p><p><a class="btn dark" href="/">Back to the homepage</a></p></main>')
    (out / "welcome").mkdir()
    (out / "welcome" / "index.html").write_text(page(
        base, cfg, "/welcome/", "Welcome | Noticehawk", "Your Noticehawk subscription is set up.",
        simple.format(h="You're in.", p="Thank you. Your subscription is set up and a receipt is on its way from Stripe. "
                      "If you have not chosen your regions and type of work yet, we will email you a link to do it. "
                      "Your first alert arrives on the Monday after that."), '<meta name="robots" content="noindex">'))
    (out / "confirmed").mkdir()
    (out / "confirmed" / "index.html").write_text(page(
        base, cfg, "/confirmed/", "Email confirmed | Noticehawk", "Your Noticehawk email address is confirmed.",
        '<div class="night"><header><div class="wrap"><a class="brand" href="/"><i aria-hidden="true"></i>Noticehawk</a>'
        '</div></header></div><main id="main" class="doc">'
        '<div id="ok"><h1>You\'re confirmed.</h1><p>Your free tender alerts are switched on. '
        'The first one arrives on Monday, with three tenders for your region and type of work.</p></div>'
        '<div id="bad" hidden><h1>That link did not work.</h1><p>It may have been copied incompletely. '
        f'Sign up again from the homepage, or email <a href="mailto:{html.escape(cfg["contact_email"])}">{html.escape(cfg["contact_email"])}</a> and we will sort it out.</p></div>'
        '<p><a class="btn dark" href="/">Back to the homepage</a></p></main>'
        '<script>if(new URLSearchParams(location.search).get("status")){document.getElementById("ok").hidden=true;'
        'document.getElementById("bad").hidden=false}</script>', '<meta name="robots" content="noindex">'))
    for p in pages:
        body, head = render_listing(p, pages, cfg, updated_text)
        target = out / p["path"].strip("/")
        target.mkdir(parents=True, exist_ok=True)
        title = listing_title(p)
        (target / "index.html").write_text(page(
            base, cfg, p["path"], f"{title} | Noticehawk",
            f"{len(p['rows'])} open {title[0].lower() + title[1:]}, updated {updated_text}. Buyer, value and closing date for each, with a link to the official notice.",
            body, head))
    index_body = (HEADER + '<main id="main" class="doc wide"><h1>Browse open construction tenders</h1>'
                  f'<p class="lede dark">UK public-sector tenders for construction and building maintenance work, counted on {updated_text}.</p>'
                  '<h2 class="sub">By type of work</h2><ul class="chips links">'
                  + "".join(f'<li><a href="{p["path"]}">{html.escape(CATEGORY_LABELS[p["category"]])}<span>{len(p["rows"])}</span></a></li>' for p in pages if p["category"] and not p["region"])
                  + '</ul><h2 class="sub">By region</h2><ul class="chips links">'
                  + "".join(f'<li><a href="{p["path"]}">{html.escape(p["region"])}<span>{len(p["rows"])}</span></a></li>' for p in pages if p["region"] and not p["category"])
                  + '</ul><div class="cta-box"><div><strong>Get your tenders by email every Monday.</strong>'
                  '<span>Three a week free, or every matching tender with a score out of 100 from £29 a month.</span></div>'
                  '<a class="btn" href="/#start">Start free</a></div></main>')
    (out / "tenders").mkdir(exist_ok=True)
    (out / "tenders" / "index.html").write_text(page(
        base, cfg, "/tenders/", "Browse open construction tenders | Noticehawk",
        "Open UK public-sector construction and building maintenance tenders by region and type of work, updated daily.", index_body))
    (out / "preferences").mkdir()
    (out / "preferences" / "index.html").write_text(page(
        base, cfg, "/preferences/", "Your regions and work types | Noticehawk", "Choose the tenders Noticehawk sends you.",
        HEADER + '<main id="main" class="doc"><h1>Your regions and work types</h1>'
        '<p id="pref-intro">Loading your choices…</p>'
        f'<form id="prefs" hidden data-api="{html.escape(cfg["preferences_url"], quote=True)}">'
        '<fieldset><legend>Regions <span class="fine" id="region-limit"></span></legend><div class="ticks" id="regions">'
        + "".join(f'<label><input type="checkbox" name="regions" value="{html.escape(r)}"><span>{html.escape(r)}</span></label>' for r in REGIONS)
        + '</div></fieldset><fieldset><legend>Types of work <span class="fine" id="trade-limit"></span></legend><div class="ticks" id="trades">'
        + "".join(f'<label><input type="checkbox" name="trades" value="{w}"><span>{html.escape(CATEGORY_LABELS[w])}</span></label>' for w in WORK_TYPES)
        + '</div></fieldset>'
        '<fieldset id="fit" hidden><legend>Contract size</legend>'
        '<p class="fine">Tell us what you take on and your scores will reflect your firm, not a typical small one.</p>'
        '<label for="min_value">Smallest contract worth bidding for</label>'
        '<select id="min_value"><option value="">Any size</option><option value="10000">£10,000</option><option value="25000">£25,000</option><option value="50000">£50,000</option><option value="100000">£100,000</option><option value="250000">£250,000</option></select>'
        '<label for="max_value">Largest contract you would take on</label>'
        '<select id="max_value"><option value="">Any size</option><option value="100000">£100,000</option><option value="250000">£250,000</option><option value="500000">£500,000</option><option value="1000000">£1 million</option><option value="2000000">£2 million</option><option value="5000000">£5 million</option></select></fieldset>'
        '<fieldset id="watch" hidden><legend>Watchlists <span class="fine">(Premium)</span></legend>'
        '<label for="keywords">Keywords to watch, one per line <span class="fine" id="keyword-limit"></span></label>'
        '<textarea id="keywords" rows="4" placeholder="asbestos&#10;fire doors"></textarea>'
        '<p class="fine">We flag any open tender that mentions one, whatever the type of work.</p>'
        '<label for="competitors">Competitors to watch, one per line <span class="fine" id="competitor-limit"></span></label>'
        '<textarea id="competitors" rows="3" placeholder="Part of the company name is enough"></textarea>'
        '<p class="fine">We tell you when a firm with that name wins a public contract.</p>'
        '<label for="buyers">Buyers to follow, one per line <span class="fine" id="buyer-limit"></span></label>'
        '<textarea id="buyers" rows="3" placeholder="Kent County Council&#10;Medway"></textarea>'
        '<p class="fine">We send every open tender from a buyer with that name, wherever it is and whatever the type of work.</p></fieldset>'
        '<button class="btn dark" type="submit">Save my choices</button>'
        '<p class="msg" id="pref-msg" role="status" aria-live="polite"></p></form></main>'
        '<script src="/preferences.js" defer></script>', '<meta name="robots" content="noindex">'))
    login_form = (
        f'<form id="login" class="doc-form" data-api="{html.escape(cfg["login_url"], quote=True)}">'
        '<label for="login-email">Email address</label>'
        '<input id="login-email" name="email" type="email" autocomplete="email" required>'
        '<input name="website" type="text" tabindex="-1" autocomplete="off" hidden>'
        '<button class="btn" type="submit">Email me a sign-in link</button></form>'
        '<p id="login-msg" role="status"></p>')
    (out / "login").mkdir()
    (out / "login" / "index.html").write_text(page(
        base, cfg, "/login/", "Sign in | Noticehawk", "Sign in to your Noticehawk account with a link sent to your email.",
        HEADER + '<main id="main" class="doc"><h1>Sign in</h1>'
        '<p class="lede dark">For customers on a paid plan. Enter the email address you subscribed with and we will send you a sign-in link. There is no password to remember.</p>'
        + login_form + '<p class="fine">On the free plan? Your alerts arrive by email every Monday; there is nothing to sign in to.</p>'
        '</main><script src="/login.js" defer></script>', '<meta name="robots" content="noindex">'))
    # Subcontract work board: contractors post work free; published after email confirmation and approval.
    work_api = html.escape(cfg["work_url"], quote=True)
    regions_opts = "".join(f'<option>{html.escape(r)}</option>' for r in REGIONS)
    work_opts = "".join(f'<option value="{w}">{html.escape(CATEGORY_LABELS[w])}</option>' for w in WORK_TYPES)
    (out / "subcontract-work").mkdir()
    (out / "subcontract-work" / "index.html").write_text(page(
        base, cfg, "/subcontract-work/", "Subcontract work for construction firms | Noticehawk",
        "Work packages posted by main contractors and builders who want prices from construction and maintenance firms. Free to read and free to post.",
        HEADER + f'<main id="main" class="doc wide" data-api="{work_api}"><h1>Subcontract work</h1>'
        '<p class="lede dark">Work packages posted by contractors who want prices. Reply to the contractor directly; we take no fee and no commission.</p>'
        '<p><a class="btn" href="/post-work/">Post work free</a></p>'
        '<div id="work-list" class="mail" aria-live="polite"><p>Loading the board.</p></div>'
        '<h2>How it works</h2><ul>'
        '<li>A contractor posts the work, where it is, and the date they want prices by.</li>'
        '<li>A post appears once the contractor has confirmed their email address. We review every post and take down anything that is not genuine construction or maintenance work.</li>'
        '<li>You contact the contractor using the details in the post. Noticehawk is not a party to any agreement between you.</li>'
        '<li>Posts come down on their closing date, or sooner if the contractor removes them.</li></ul>'
        '<p class="fine">Posts are written by the contractors named. We review each one, but we do not vet the contractor or the terms. Make your own checks before you price or start work.</p>'
        '</main><script src="/work.js" defer></script>'))
    (out / "post-work").mkdir()
    (out / "post-work" / "index.html").write_text(page(
        base, cfg, "/post-work/", "Post subcontract work free | Noticehawk",
        "Contractors: post a work package free and get prices from construction and maintenance firms in your region.",
        HEADER + '<main id="main" class="doc"><h1>Post work free</h1>'
        '<p class="lede dark">For main contractors and builders who want prices for a package of work. It costs nothing, and firms reply to you directly.</p>'
        f'<form id="work-form" class="doc-form work-form" data-api="{work_api}" novalidate>'
        '<label for="w-company">Your company name</label><input id="w-company" name="company" type="text" autocomplete="organization" maxlength="120" required>'
        '<label for="w-number">Company number <span class="opt">(optional)</span></label><input id="w-number" name="company_number" type="text" maxlength="8" inputmode="text">'
        '<label for="w-email">Your email address</label><input id="w-email" name="email" type="email" autocomplete="email" required>'
        '<p class="hint">We send a confirmation link here. It is not shown on the post.</p>'
        '<label for="w-title">What is the work?</label><input id="w-title" name="title" type="text" maxlength="120" placeholder="Roofing package, school extension" required>'
        f'<label for="w-category">Type of work</label><select id="w-category" name="category" required><option value="">Choose</option>{work_opts}</select>'
        f'<label for="w-region">Region</label><select id="w-region" name="region" required><option value="">Choose</option>{regions_opts}</select>'
        '<label for="w-town">Town or area <span class="opt">(optional)</span></label><input id="w-town" name="town" type="text" maxlength="60">'
        '<label for="w-desc">Describe the work</label><textarea id="w-desc" name="description" rows="6" maxlength="2000" required></textarea>'
        '<p class="hint">What needs doing, roughly how much, and when it starts. At least a couple of sentences. No web links.</p>'
        '<label for="w-band">Rough value <span class="opt">(optional)</span></label><select id="w-band" name="value_band"><option value="">Not stated</option>'
        '<option value="under_10k">Under £10,000</option><option value="10k_50k">£10,000 to £50,000</option><option value="50k_250k">£50,000 to £250,000</option>'
        '<option value="250k_1m">£250,000 to £1 million</option><option value="over_1m">Over £1 million</option></select>'
        '<label for="w-by">Prices wanted by</label><input id="w-by" name="apply_by" type="date" required>'
        '<label for="w-apply">How should firms reply?</label><input id="w-apply" name="how_to_apply" type="text" maxlength="254" placeholder="estimating@yourfirm.co.uk" required>'
        '<p class="hint">An email address, or a link starting https://. This is shown on the post.</p>'
        '<input name="website" type="text" tabindex="-1" autocomplete="off" hidden>'
        '<label class="check"><input id="w-agree" name="agree" type="checkbox" required><span>I am posting on behalf of this company, the work is real, and I agree to the post and the reply details being published. <a href="/terms/">Terms</a> and <a href="/privacy/">privacy</a>.</span></label>'
        '<button class="btn" type="submit">Post this work</button></form>'
        '<p id="work-msg" role="status"></p>'
        '<p class="fine">Your post goes on the board as soon as you confirm your email address. You can take it down at any time from the link we email you.</p>'
        '</main><script src="/work.js" defer></script>'))
    (out / "post-work" / "done").mkdir()
    (out / "post-work" / "done" / "index.html").write_text(page(
        base, cfg, "/post-work/done/", "Post confirmed | Noticehawk", "Your post has been received.",
        HEADER + '<main id="main" class="doc"><h1 id="done-h">Thank you</h1><p id="done-p" class="lede dark">Your email address is confirmed and your post is on the board. We have emailed you a link to see or remove it.</p>'
        '<p><a href="/subcontract-work/">See the board</a></p></main><script src="/work.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "post-work" / "manage").mkdir()
    (out / "post-work" / "manage" / "index.html").write_text(page(
        base, cfg, "/post-work/manage/", "Manage a post | Noticehawk", "Review or remove a post.",
        HEADER + f'<main id="main" class="doc" data-api="{work_api}"><h1 id="manage-h">Your post</h1><div id="manage" aria-live="polite"><p>Loading.</p></div>'
        '</main><script src="/work.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "account").mkdir()
    (out / "account" / "index.html").write_text(page(
        base, cfg, "/account/", "Your account | Noticehawk", "Your live tender matches.",
        HEADER + f'<main id="main" class="doc wide" data-api="{html.escape(cfg["account_url"], quote=True)}" '
        f'data-shortlist="{html.escape(cfg["shortlist_url"], quote=True)}" data-feedback="{html.escape(cfg["feedback_url"], quote=True)}">'
        '<p id="loading">Loading your tenders…</p>'
        '<div id="problem" hidden><h1 id="problem-title"></h1><p id="problem-text"></p>' + login_form + '</div>'
        '<div id="app" hidden><h1>My tenders</h1>'
        '<p class="fine"><span id="plan"></span> · <a id="prefs" href="/preferences/">Change regions, type of work or contract size</a></p>'
        '<p id="setup" class="check" hidden>You have not chosen your regions and type of work yet, so there is nothing to show. Use the link above to choose them.</p>'
        '<div class="tabs" role="tablist"><button type="button" role="tab" id="tab-tenders">Open tenders</button>'
        '<button type="button" role="tab" id="tab-coming">Coming soon</button>'
        '<button type="button" role="tab" id="tab-renewals">Renewals</button></div>'
        '<div id="filters" class="filters">'
        '<label>Region<select id="f-region"><option value="">All yours</option></select></label>'
        '<label>County<select id="f-county"><option value="">All</option></select></label>'
        '<label>Council<select id="f-council"><option value="">All</option></select></label>'
        '<label>Your base postcode<input id="f-base" type="text" autocomplete="postal-code" placeholder="e.g. TN9 1AA" maxlength="8"></label>'
        '<label>Distance<select id="f-miles"><option value="">Any</option><option value="10">Within 10 miles</option>'
        '<option value="25">Within 25 miles</option><option value="50">Within 50 miles</option><option value="100">Within 100 miles</option></select></label>'
        '<label>Type of work<select id="f-type"><option value="">All yours</option></select></label>'
        '<label>Closing<select id="f-days"><option value="">Any time</option><option value="7">Within 7 days</option>'
        '<option value="14">Within 14 days</option><option value="30">Within 30 days</option></select></label>'
        '<label>Score<select id="f-score"><option value="0">Any</option><option value="60">60 and over</option>'
        '<option value="75">75 and over</option><option value="90">90 and over</option></select></label>'
        '<label>Value<select id="f-size"><option value="">Any</option><option value="0-50000">Under £50k</option>'
        '<option value="50000-250000">£50k to £250k</option><option value="250000-1000000">£250k to £1m</option>'
        '<option value="1000000-">Over £1m</option></select></label>'
        '<label>Buyer or keyword<input id="f-text" type="search" placeholder="e.g. Kent County Council"></label>'
        '<label class="check"><input id="f-short" type="checkbox"><span>My shortlist only</span></label></div>'
        '<p class="fine" id="base-note" hidden></p>'
        '<p class="fine"><span id="count"></span> <a id="download" hidden>Download as a spreadsheet</a></p>'
        '<div id="list" class="mail"></div>'
        '<p class="fine">Scores and notes are a guide drawn from the published notice. Always check the official notice and the buyer\'s documents before you bid.</p>'
        '</div></main><script src="/account.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "shortlist").mkdir()
    (out / "shortlist" / "index.html").write_text(page(
        base, cfg, "/shortlist/", "Your shortlist | Noticehawk", "Deadline reminders for a tender on your shortlist.",
        HEADER + f'<main id="main" class="doc" data-api="{html.escape(cfg["shortlist_url"], quote=True)}">'
        '<h1 id="sl-title">One moment…</h1><p id="sl-text"></p>'
        '<p id="sl-actions" hidden><a class="btn dark" id="sl-notice" href="#" rel="noopener">Open the official notice</a> '
        '<a class="btn outline" id="sl-cal" href="#" download="tender-deadline.ics">Add the deadline to my calendar</a></p>'
        '<p id="sl-undo-wrap" hidden><button class="linkish" id="sl-undo" type="button">Take it off my shortlist</button></p>'
        '</main><script src="/shortlist.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "feedback").mkdir()
    (out / "feedback" / "index.html").write_text(page(
        base, cfg, "/feedback/", "Not for me | Noticehawk", "Tell us why a tender was not right for you.",
        HEADER + f'<main id="main" class="doc" data-api="{html.escape(cfg["feedback_url"], quote=True)}">'
        '<h1>Not for me</h1><p id="fb-text">Tell us why, and we will use it to send you better matches. It also hides the tender from your account page.</p>'
        '<div id="fb-reasons" class="reasons">'
        '<button class="btn outline" type="button" data-reason="not_my_work">Not my type of work</button>'
        '<button class="btn outline" type="button" data-reason="wrong_area">Wrong area</button>'
        '<button class="btn outline" type="button" data-reason="too_big">Too big for us</button>'
        '<button class="btn outline" type="button" data-reason="too_small">Too small to be worth it</button>'
        '<button class="btn outline" type="button" data-reason="not_construction">Not construction work at all</button></div>'
        '<p class="msg" id="fb-msg" role="status" aria-live="polite"></p>'
        '<p><a href="/login/">Go to my account</a></p></main><script src="/feedback.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "unsubscribe").mkdir()
    (out / "unsubscribe" / "index.html").write_text(page(
        base, cfg, "/unsubscribe/", "Unsubscribe | Noticehawk", "Stop Noticehawk emails.",
        '<div class="night"><header><div class="wrap"><a class="brand" href="/"><i aria-hidden="true"></i>Noticehawk</a>'
        '</div></header></div><main id="main" class="doc"><h1>Unsubscribe</h1>'
        '<div id="ask"><p id="what">Stop all Noticehawk emails to this address. A paid plan is not cancelled by this; '
        'use the billing link in any alert to do that.</p>'
        '<p><button class="btn dark" id="go" type="button">Unsubscribe me</button></p></div>'
        '<p class="msg" id="out" role="status" aria-live="polite"></p>'
        f'<p>Trouble with this page? Email <a href="mailto:{html.escape(cfg["contact_email"])}">{html.escape(cfg["contact_email"])}</a> and we will do it for you.</p></main>'
        f'<script>(function(){{var q=new URLSearchParams(location.search),t=q.get("token"),g=q.get("who")==="g",w=q.get("who")==="p"?"&who=p":g?"&who=g":"",o=document.getElementById("out"),a=document.getElementById("ask");'
        'if(g){document.getElementById("what").textContent="Stop the guide emails to this address. Your tender alerts carry on as they are.";document.getElementById("go").textContent="Stop the guides"}'
        'function say(m,ok){o.textContent=m;o.className="msg "+(ok?"good":"bad")}'
        'if(!t){a.hidden=true;say("This link is incomplete. Open the unsubscribe link from one of our emails again.",false);return}'
        'document.getElementById("go").addEventListener("click",function(){this.disabled=true;'
        f'fetch({json.dumps(cfg["unsubscribe_url"])}+"?token="+encodeURIComponent(t)+w,{{method:"POST"}})'
        '.then(function(r){if(r.ok){a.hidden=true;say(g?"Done. No more guide emails. Your tender alerts carry on.":"Done. You will not get any more emails from us.",true)}'
        'else{say("That did not work. Please try again, or email us.",false)}})'
        '.catch(function(){say("That did not work. Check your connection and try again.",false)})})})();</script>',
        '<meta name="robots" content="noindex">'))
    (out / "404.html").write_text(page(
        base, cfg, "/404.html", "Page not found | Noticehawk", "That page does not exist.",
        simple.format(h="Page not found", p="That page does not exist or has moved."), '<meta name="robots" content="noindex">'))
    today = updated.strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{cfg['site_url']}{p}</loc><lastmod>{today}</lastmod></url>"
                   for p in ["/", "/this-week/", "/tenders/"] + [p["path"] for p in pages]
                   + ["/how-it-works/", "/example-alert/", "/subcontract-work/", "/post-work/", "/privacy/", "/terms/"] + made["paths"] + guide_paths)
    (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    (out / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        + "".join(f"User-agent: {bot}\nAllow: /\n\n" for bot in
                  ("OAI-SearchBot", "ChatGPT-User", "GPTBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended"))
        + f"Sitemap: {cfg['site_url']}/sitemap.xml\n")
    regions = ", ".join(f"{r['name']} ({r['n']})" for r in stats.get("regions") or [])
    cats = ", ".join(f"{CATEGORY_LABELS.get(c['name'], c['name'])} ({c['n']})" for c in stats.get("categories") or [])
    (out / "llms.txt").write_text(
        "# Noticehawk\n\n"
        "> Email alerts of UK public-sector tenders for construction and building maintenance firms, "
        "filtered by region and type of work and scored out of 100 for how well each suits a smaller firm.\n\n"
        f"- Open tenders tracked on {updated_text}: {int(stats['open_count']):,}\n"
        f"- By region: {regions}\n- By type of work: {cats}\n"
        "- Sources: Find a Tender, Contracts Finder and Public Contracts Scotland, the official UK notice services, checked daily. Open Government Licence v3.0.\n"
        "- Plans: Free (3 tenders a week), Basic £29 a month, Professional £79 a month, Premium £149 a month. Cancel any time.\n"
        "- Paid plans: every matching tender scored, new matches emailed each weekday, contracts coming up for renewal, deadline reminders, "
        "and AI assist, which lists the key dates, the buyer's stated requirements and a checklist of what each bid needs. "
        "Professional adds buyer award history, planned tenders, new awards for subcontract work and a spreadsheet download. "
        "Premium adds buyer, keyword and competitor watch lists and a monthly market report.\n"
        "- Subcontract work board: contractors post work they want priced, free of charge; firms reply directly. No fee or commission.\n"
        f"- Contact: {cfg['contact_email']}\n\n"
        "## Pages\n\n"
        f"- [Home]({cfg['site_url']}/): what the service does, live tender counts, plans and common questions\n"
        f"- [This week's tenders]({cfg['site_url']}/this-week/): the ten highest-scoring tenders published in the last week\n"
        f"- [Browse tenders]({cfg['site_url']}/tenders/): open tenders by region and type of work, {len(pages)} pages\n"
        f"- [How it works]({cfg['site_url']}/how-it-works/): data sources, daily checks, handling of changed and withdrawn notices, the scoring table, limits\n"
        f"- [Example alert]({cfg['site_url']}/example-alert/): the weekly subscriber email with live tenders\n"
        f"- [Subcontract work board]({cfg['site_url']}/subcontract-work/): work packages posted by contractors who want prices\n"
        f"- [Post work free]({cfg['site_url']}/post-work/): form for contractors to post a work package\n"
        + "".join(f"- [{t}]({cfg['site_url']}/guides/{s_}/): {d}\n" for s_, t, d in GUIDES)
        + (f"- [Monthly market reports]({cfg['site_url']}/insights/): construction contracts awarded by UK public bodies each month, nationally and by region: counts, typical values, types of work, busiest buyers and most frequent winners\n" if insight else "")
        + (f"- [Public buyers]({cfg['site_url']}/buyers/): {made['buyers']} pages, one per public body, with what it awards, who wins and open tenders\n" if made["buyers"] else "")
        + "".join(f"- [New tenders in {t} this week]({cfg['site_url']}{p})\n" for t, p in made["weekly"])
        + f"- [Privacy notice]({cfg['site_url']}/privacy/)\n- [Terms of service]({cfg['site_url']}/terms/)\n")


def main() -> int:
    cfg = json.loads((ROOT / "config.json").read_text())
    if len(sys.argv) > 1:
        stats = json.loads(Path(sys.argv[1]).read_text())
    else:
        req = urllib.request.Request(cfg["stats_url"], headers={"User-Agent": "noticehawk-site-build"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            stats = json.loads(resp.read())
    if int(stats["open_count"]) < 20:
        print(f"Refusing to publish: only {stats['open_count']} open tenders, which suggests a data fault.")
        return 1
    build(stats, cfg, ROOT / "dist")
    print(f"Built with {stats['open_count']} open tenders, {len(stats.get('sample') or [])} sample rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
