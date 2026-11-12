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
NOTICE_PREFIX = "https://www.find-tender.service.gov.uk/"

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
        if not url.startswith(NOTICE_PREFIX):
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


def chips(items: list[dict], labels: dict | None = None) -> str:
    return "\n".join(
        f'<li>{html.escape((labels or {}).get(i["name"], i["name"]))}<span>{int(i["n"])}</span></li>' for i in items)


def start_block(cfg: dict) -> str:
    email = html.escape(cfg["contact_email"])
    return (
        '<div><h2>Free accounts open shortly.</h2>'
        '<p>Three tenders a week for your region and your kind of work, free. '
        'Paid plans add the full scored list.</p></div>'
        f'<div class="card"><strong>Want to be first in?</strong>'
        f'<span>Email us with your region and the work you do, and we will set you up on day one.</span>'
        f'<a class="btn dark" style="text-align:center" href="mailto:{email}?subject=Noticehawk%20early%20access">Email {email}</a>'
        '<span style="font-size:13px;color:#6B7280">We never sell or share your details.</span></div>')


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
    home = Template((ROOT / "templates" / "home.html").read_text()).substitute(
        open_count=f'{int(stats["open_count"]):,}', value_total=money(stats["value_total"]),
        closing_14=f'{int(stats["closing_14"]):,}', updated=updated_text,
        sample_rows=sample_rows(stats.get("sample") or []),
        region_chips=chips(stats.get("regions") or []),
        category_chips=chips(stats.get("categories") or [], CATEGORY_LABELS),
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
                      "Your first alert arrives on Monday."), '<meta name="robots" content="noindex">'))
    (out / "404.html").write_text(page(
        base, cfg, "/404.html", "Page not found | Noticehawk", "That page does not exist.",
        simple.format(h="Page not found", p="That page does not exist or has moved."), '<meta name="robots" content="noindex">'))
    today = updated.strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{cfg['site_url']}{p}</loc><lastmod>{today}</lastmod></url>" for p in ("/", "/privacy/", "/terms/"))
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
