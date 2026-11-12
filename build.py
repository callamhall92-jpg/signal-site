"""Builds the static site into dist/ from the templates and the live public figures."""
from __future__ import annotations

import html
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from string import Template

ROOT = Path(__file__).parent
CATEGORY_LABELS = {
    "new_build": "New build", "refurbishment": "Refurbishment",
    "repairs_maintenance": "Repairs and maintenance", "mechanical_electrical": "Mechanical and electrical",
    "roofing": "Roofing", "groundworks_civils": "Groundworks and civils",
    "design_professional": "Design and professional services", "other": "Other",
}
NOTICE_PREFIXES = ("https://www.find-tender.service.gov.uk/", "https://www.contractsfinder.service.gov.uk/")

FAQ = [
    ("What is Noticehawk?",
     "A weekly email of UK public-sector tenders for construction and building maintenance firms, "
     "filtered to your regions and type of work and scored out of 100 for how well each suits a smaller firm."),
    ("Where do the tenders come from?",
     "From Find a Tender, the UK government's official service for public contract notices. "
     "We check it every day and link each alert to the official notice."),
    ("How is the score worked out?",
     "A fixed points table: how closely the work matches construction and maintenance, the contract value, "
     "the days left to bid, and whether the buyer has split it into lots or marked it suitable for smaller firms. "
     "Every tender is scored the same way."),
    ("What kinds of work are covered?",
     "New build, refurbishment, repairs and maintenance, mechanical and electrical, roofing, "
     "groundworks and civils, and design and professional services."),
    ("Does Noticehawk submit bids for me?",
     "No. Each alert links to the official notice, and you bid through the buyer's own portal."),
    ("What does it cost?",
     "The Free plan sends three tenders a week for one region and one type of work. "
     "Paid plans start at £29 a month and can be cancelled at any time."),
]


def money(value) -> str:
    if value is None:
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
            f'<td class="num">{money(r.get("value"))}</td>'
            f'<td class="num">{days} day{"" if days == 1 else "s"}</td></tr>')
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


def start_block(cfg: dict) -> str:
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
    work = "".join(f'<option value="{w}">{html.escape(CATEGORY_LABELS[w])}</option>' for w in WORK_TYPES)
    return (
        '<div><h2>Start with three tenders a week, free.</h2>'
        '<p>Pick your region and the work you do. Upgrade any time for the full scored list.</p></div>'
        f'<form class="card" id="signup" action="{html.escape(cfg["signup_url"], quote=True)}" method="post" novalidate>'
        '<label for="s-email">Work email</label>'
        '<input id="s-email" name="email" type="email" autocomplete="email" required>'
        '<label for="s-company">Company name or number <span class="fine">(optional)</span></label>'
        '<input id="s-company" name="company" type="text" autocomplete="organization" maxlength="160">'
        '<div class="pair">'
        f'<div><label for="s-region">Region</label><select id="s-region" name="region" required><option value="">Choose</option>{regions}</select></div>'
        f'<div><label for="s-work">Main type of work</label><select id="s-work" name="work" required><option value="">Choose</option>{work}</select></div>'
        '</div>'
        '<div class="trap" aria-hidden="true"><label for="s-website">Leave this empty</label>'
        '<input id="s-website" name="website" type="text" tabindex="-1" autocomplete="off"></div>'
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
          '<nav class="main" aria-label="Main"><a href="/tenders/">Browse tenders</a><a href="/#pricing">Pricing</a>'
          '<a class="btn small" href="/#start">Start free</a></nav></div></header></div>')


def listing_pages(stats: dict) -> list[dict]:
    """One page per work type, per region and per pairing that has at least one open tender."""
    rows = [r for r in (stats.get("listings") or [])
            if (r.get("url") or "").startswith(NOTICE_PREFIXES) and r.get("category") in CATEGORY_LABELS and r.get("region") in REGIONS]
    rows.sort(key=lambda r: (int(r["days"]), r["title"]))      # soonest deadline first
    pages = []
    for cat in WORK_TYPES:
        hits = [r for r in rows if r["category"] == cat]
        if hits:
            pages.append({"path": f"/tenders/{category_slug(cat)}/", "category": cat, "region": None, "rows": hits})
    for region in REGIONS:
        hits = [r for r in rows if r["region"] == region]
        if hits:
            pages.append({"path": f"/tenders/{slug(region)}/", "category": None, "region": region, "rows": hits})
        for cat in WORK_TYPES:
            both = [r for r in hits if r["category"] == cat]
            if both:
                pages.append({"path": f"/tenders/{category_slug(cat)}/{slug(region)}/", "category": cat, "region": region, "rows": both})
    return pages


def place_phrase(region: str) -> str:
    return f"in {region}" if region in ("London", "Wales", "Scotland", "Northern Ireland", "Yorkshire and the Humber") else f"in the {region}"


def listing_title(page: dict) -> str:
    work = CATEGORY_LABELS[page["category"]] if page["category"] else "Construction"
    return f"{work} tenders" + (f" {place_phrase(page['region'])}" if page["region"] else " in the UK")


def render_listing(page: dict, pages: list[dict], cfg: dict, updated_text: str) -> tuple[str, str]:
    rows, title = page["rows"], listing_title(page)
    shown = rows[:12]
    body_rows = "\n".join(
        f'<tr><td><a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
        f'<small>{html.escape(" · ".join(x for x in (None if page["region"] else r["region"], None if page["category"] else CATEGORY_LABELS[r["category"]]) if x))}</small></td>'
        f'<td class="muted">{html.escape(r.get("buyer") or "Not stated")}</td>'
        f'<td class="num">{money(r.get("value"))}</td>'
        f'<td class="num">{int(r["days"])} day{"" if int(r["days"]) == 1 else "s"}</td></tr>' for r in shown)
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
            '<div class="tablebox light"><table><thead><tr><th scope="col">Tender</th><th scope="col">Buyer</th>'
            f'<th scope="col">Value</th><th scope="col">Closes</th></tr></thead><tbody>{body_rows}</tbody></table></div>'
            f'{more}<div class="cta-box"><div><strong>Get these by email every Monday.</strong>'
            '<span>Three a week free, or every matching tender with a score out of 100 from £29 a month.</span></div>'
            '<a class="btn" href="/#start">Start free</a></div>'
            f'{rel}</main>')
    return body, head


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


def page(base: str, cfg: dict, path: str, title: str, description: str, body: str, head_extra: str = "") -> str:
    return Template(base).substitute(
        title=html.escape(title), description=html.escape(description, quote=True),
        canonical=cfg["site_url"] + path, head_extra=head_extra, body=body, email=html.escape(cfg["contact_email"]))


def build(stats: dict, cfg: dict, out: Path) -> None:
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
        start_block=start_block(cfg),
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
        '<fieldset id="watch" hidden><legend>Watchlists <span class="fine">(Premium)</span></legend>'
        '<label for="keywords">Keywords to watch, one per line <span class="fine" id="keyword-limit"></span></label>'
        '<textarea id="keywords" rows="4" placeholder="asbestos&#10;fire doors"></textarea>'
        '<p class="fine">We flag any open tender that mentions one, whatever the type of work.</p>'
        '<label for="competitors">Competitors to watch, one per line <span class="fine" id="competitor-limit"></span></label>'
        '<textarea id="competitors" rows="3" placeholder="Part of the company name is enough"></textarea>'
        '<p class="fine">We tell you when a firm with that name wins a public contract.</p></fieldset>'
        '<button class="btn dark" type="submit">Save my choices</button>'
        '<p class="msg" id="pref-msg" role="status" aria-live="polite"></p></form></main>'
        '<script src="/preferences.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "shortlist").mkdir()
    (out / "shortlist" / "index.html").write_text(page(
        base, cfg, "/shortlist/", "Your shortlist | Noticehawk", "Deadline reminders for a tender on your shortlist.",
        HEADER + f'<main id="main" class="doc" data-api="{html.escape(cfg["shortlist_url"], quote=True)}">'
        '<h1 id="sl-title">One moment…</h1><p id="sl-text"></p>'
        '<p id="sl-actions" hidden><a class="btn dark" id="sl-notice" href="#" rel="noopener">Open the official notice</a> '
        '<a class="btn outline" id="sl-cal" href="#" download="tender-deadline.ics">Add the deadline to my calendar</a></p>'
        '<p id="sl-undo-wrap" hidden><button class="linkish" id="sl-undo" type="button">Take it off my shortlist</button></p>'
        '</main><script src="/shortlist.js" defer></script>', '<meta name="robots" content="noindex">'))
    (out / "unsubscribe").mkdir()
    (out / "unsubscribe" / "index.html").write_text(page(
        base, cfg, "/unsubscribe/", "Unsubscribe | Noticehawk", "Stop Noticehawk emails.",
        '<div class="night"><header><div class="wrap"><a class="brand" href="/"><i aria-hidden="true"></i>Noticehawk</a>'
        '</div></header></div><main id="main" class="doc"><h1>Unsubscribe</h1>'
        '<div id="ask"><p>Stop all Noticehawk emails to this address. A paid plan is not cancelled by this; '
        'use the billing link in any alert to do that.</p>'
        '<p><button class="btn dark" id="go" type="button">Unsubscribe me</button></p></div>'
        '<p class="msg" id="out" role="status" aria-live="polite"></p>'
        f'<p>Trouble with this page? Email <a href="mailto:{html.escape(cfg["contact_email"])}">{html.escape(cfg["contact_email"])}</a> and we will do it for you.</p></main>'
        f'<script>(function(){{var t=new URLSearchParams(location.search).get("token"),o=document.getElementById("out"),a=document.getElementById("ask");'
        'function say(m,ok){o.textContent=m;o.className="msg "+(ok?"good":"bad")}'
        'if(!t){a.hidden=true;say("This link is incomplete. Open the unsubscribe link from one of our emails again.",false);return}'
        'document.getElementById("go").addEventListener("click",function(){this.disabled=true;'
        f'fetch({json.dumps(cfg["unsubscribe_url"])}+"?token="+encodeURIComponent(t),{{method:"POST"}})'
        '.then(function(r){if(r.ok){a.hidden=true;say("Done. You will not get any more emails from us.",true)}'
        'else{say("That did not work. Please try again, or email us.",false)}})'
        '.catch(function(){say("That did not work. Check your connection and try again.",false)})})})();</script>',
        '<meta name="robots" content="noindex">'))
    (out / "404.html").write_text(page(
        base, cfg, "/404.html", "Page not found | Noticehawk", "That page does not exist.",
        simple.format(h="Page not found", p="That page does not exist or has moved."), '<meta name="robots" content="noindex">'))
    today = updated.strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{cfg['site_url']}{p}</loc><lastmod>{today}</lastmod></url>"
                   for p in ["/", "/tenders/"] + [p["path"] for p in pages] + ["/privacy/", "/terms/"])
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
        "> Weekly email alerts of UK public-sector tenders for construction and building maintenance firms, "
        "filtered by region and type of work and scored out of 100 for how well each suits a smaller firm.\n\n"
        f"- Open tenders tracked on {updated_text}: {int(stats['open_count']):,}\n"
        f"- By region: {regions}\n- By type of work: {cats}\n"
        "- Source: Find a Tender, the official UK notice service, checked daily. Open Government Licence v3.0.\n"
        "- Plans: Free (3 tenders a week), Basic £29 a month, Professional £79 a month, Premium £149 a month. Cancel any time.\n"
        f"- Contact: {cfg['contact_email']}\n\n"
        "## Pages\n\n"
        f"- [Home]({cfg['site_url']}/): what the service does, live tender counts, plans and common questions\n"
        f"- [Browse tenders]({cfg['site_url']}/tenders/): open tenders by region and type of work, {len(pages)} pages\n"
        f"- [Privacy notice]({cfg['site_url']}/privacy/)\n- [Terms of service]({cfg['site_url']}/terms/)\n")


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
