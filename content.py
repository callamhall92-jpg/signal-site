"""Pages built from published award notices and this week's new tenders:

- /insights/ and /insights/YYYY-MM/[region/]: monthly market reports, kept as an archive
- /buyers/ and /buyers/<buyer>/: what each busy public buyer awards, and to whom
- /this-week/<region>/: new tenders in each region this week

Every page is made from real figures. A page is only written when there is enough to say.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

CTA = ('<div class="cta-box"><div><strong>Get the tenders for your region and type of work every Monday.</strong>'
       '<span>Three a week free, or every matching tender with a score out of 100 from £29 a month.</span></div>'
       '<a class="btn" href="/#start">Start free</a></div>')
METHOD = ('<h2>How these figures are made</h2><p>We count contract award notices published on Find a Tender and Contracts Finder '
          'that we classify as construction or building maintenance work from the notice\'s description and codes. '
          'Each is dated by the award date in the notice. Buyers often publish award notices some weeks after the award, '
          'so the most recent months grow as late notices arrive. Values are the figures stated in the notices; many are estimates. '
          'The typical value is the median: half of the valued awards were below it and half above. A framework notice gives one '
          'total for the whole framework and repeats it against every firm appointed, so we count those appointments as awards '
          'but leave their values out of the median, along with any single figure of £100 million or more, which is almost always '
          'a framework or programme total. Firms are named only where the notice identifies a company. '
          'Contains public sector information licensed under the Open Government Licence v3.0.</p>')
_SMALL = {"and", "of", "the", "for", "in", "on", "at", "to", "de", "y"}
_UPPER = {"nhs", "uk", "llp", "plc", "gb", "hm", "bbc", "nhsbt", "ii", "iii"}
_THE = {"North East", "North West", "East Midlands", "West Midlands", "East of England", "South East", "South West"}


def friendly(name: str | None) -> str:
    """Names shouted in capitals become ordinary title case: "NATIONAL GRID UK LIMITED" -> "National Grid UK Limited"."""
    out = (name or "").strip()
    if out != out.upper() or not any(ch.isalpha() for ch in out):
        return out
    words = []
    for i, w in enumerate(out.split()):
        low = w.lower()
        core = low.strip("()[],.")
        if core in _UPPER or "&" in w:
            words.append(w)
        elif i > 0 and low in _SMALL:
            words.append(low)
        else:
            lead = low[:len(low) - len(low.lstrip("([\""))]
            rest = low[len(lead):]
            words.append(lead + "-".join("'".join(x[:1].upper() + x[1:] if (j == 0 or len(x) > 1) else x
                                                  for j, x in enumerate(part.split("'"))) for part in rest.split("-")))
    return " ".join(words)


def buyer_key(name: str) -> str:
    """Same rule as the database: "X Ltd" and "X Limited" are one buyer."""
    return re.sub(r"\s+", " ", re.sub(r"[\s,.]*\b(limited|ltd)\b\.?\s*$", "", (name or "").strip().lower()))


def in_region(region: str) -> str:
    return f"in the {region}" if region in _THE else f"in {region}"


def month_name(m: str) -> str:
    return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%B %Y")


def month_slug(m: str) -> str:
    return m[:7]


def ld_script(ld: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def crumbs_ld(cfg: dict, crumbs: list[tuple[str, str]]) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": cfg["site_url"] + path} for i, (name, path) in enumerate(crumbs)]}


def trail(crumbs: list[tuple[str, str]]) -> str:
    return '<p class="trail">' + " › ".join(f'<a href="{p}">{html.escape(n)}</a>' for n, p in crumbs[:-1]) + "</p>"


def table(head: list[str], rows: list[list[str]], nums: tuple[int, ...] = ()) -> str:
    th = "".join(f'<th scope="col">{html.escape(h)}</th>' for h in head)
    num = ' class="num"'
    body = "".join("<tr>" + "".join(f"<td{num if i in nums else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tablebox light"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


# ---------- monthly market reports ----------

def market_facts(b, m: dict) -> list[str]:
    n, where = int(m["awards"]), (f" {in_region(m['region'])}" if m.get("region") else "")
    month = month_name(m["month"])
    facts = [f"{n:,} construction and building maintenance contracts were reported as awarded by public buyers{where} in {month}."]
    if int(m.get("firms") or 0):
        facts.append(f"They went to {int(m['firms']):,} different companies; a framework award often names several.")
    cats = sorted((c for c in m.get("categories") or [] if c["name"] in b.CATEGORY_LABELS), key=lambda c: -int(c["n"]))
    if cats:
        facts.append(f"The most common type of work was {b.CATEGORY_LABELS[cats[0]['name']].lower()}, with {int(cats[0]['n'])} awards.")
    wv, under = int(m.get("with_value") or 0), int(m.get("under_500k") or 0)
    if wv >= 10:
        facts.append(f"Of the awards that gave a value, {round(under / wv * 100)}% were under £500,000, the range where smaller firms usually compete best.")
    if m.get("median"):
        facts.append(f"The typical (median) stated value was {b.money(m['median'])}.")
    if not m.get("region") and m.get("regions"):
        facts.append(f"{m['regions'][0]['name']} had the most awards ({int(m['regions'][0]['n'])}).")
    return facts


def market_page(b, cfg: dict, m: dict, buyer_paths: dict, regional: list[dict], months: list[dict]) -> tuple[str, str, str, str]:
    """One month's report, national or for one region. Returns (path, title, description, body+head)."""
    month, region = month_name(m["month"]), m.get("region")
    ms = month_slug(m["month"])
    path = f"/insights/{ms}/" + (f"{b.slug(region)}/" if region else "")
    title = (f"Construction contracts awarded {in_region(region)}: {month}" if region
             else f"UK construction contracts awarded: {month}")
    facts = market_facts(b, m)
    cats = sorted((c for c in m.get("categories") or [] if c["name"] in b.CATEGORY_LABELS), key=lambda c: -int(c["n"]))
    parts = ['<h2>Key figures</h2><ul>' + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"]
    parts.append("<h2>By type of work</h2>" + table(
        ["Type of work", "Awards", "Median value"],
        [[html.escape(b.CATEGORY_LABELS[c["name"]]), str(int(c["n"])), b.money(c.get("median"))] for c in cats], nums=(1, 2)))
    if not region and m.get("regions"):
        mine = {r["region"]: r for r in regional if r["month"] == m["month"]}
        parts.append("<h2>By region</h2>" + table(
            ["Region", "Awards"],
            [[(f'<a href="/insights/{ms}/{b.slug(r["name"])}/">{html.escape(r["name"])}</a>' if r["name"] in mine else html.escape(r["name"])),
              str(int(r["n"]))] for r in m["regions"]], nums=(1,)))

    def buyer_cell(name: str) -> str:
        p = buyer_paths.get(buyer_key(name))
        return f'<a href="{p}">{html.escape(friendly(name))}</a>' if p else html.escape(friendly(name))
    if m.get("buyers"):
        parts.append("<h2>Buyers that awarded most</h2>" + table(
            ["Buyer", "Awards"], [[buyer_cell(x["name"]), str(int(x["n"]))] for x in m["buyers"]], nums=(1,)))
    if m.get("winners"):
        parts.append("<h2>Firms that won most often</h2>" + table(
            ["Firm", "Awards"], [[html.escape(friendly(x["name"])), str(int(x["n"]))] for x in m["winners"]], nums=(1,)))
    largest = [x for x in m.get("largest") or [] if (x.get("url") or "").startswith(b.NOTICE_PREFIXES)]
    if largest:
        parts.append("<h2>Largest single contracts</h2>" + table(
            ["Contract", "Buyer", "Value"],
            [[f'<a href="{html.escape(x["url"], quote=True)}" rel="noopener">{html.escape(b.tidy_title(x["title"]))}</a>',
              buyer_cell(x["buyer"]), b.money(x["value"])] for x in largest], nums=(2,)))
    other = [x for x in months if x["month"] != m["month"]][:6]
    if region:
        links = [(f"{month}: whole UK", f"/insights/{ms}/")] + [
            (f"{r['region']}", f"/insights/{ms}/{b.slug(r['region'])}/") for r in regional if r["month"] == m["month"] and r["region"] != region]
    else:
        links = [(month_name(x["month"]), f"/insights/{month_slug(x['month'])}/") for x in other]
    if links:
        parts.append(f'<h2 class="sub">{"Other regions and the UK" if region else "Other months"}</h2><ul class="chips links">'
                     + "".join(f'<li><a href="{p}">{html.escape(t)}</a></li>' for t, p in links) + "</ul>")
    crumbs = [("Home", "/"), ("Market reports", "/insights/")] + ([(month, f"/insights/{ms}/")] if region else []) + [(title, path)]
    ld = {"@context": "https://schema.org", "@graph": [
        crumbs_ld(cfg, crumbs),
        {"@type": "Article", "headline": title, "description": facts[0], "datePublished": m["month"][:10],
         "author": {"@type": "Organization", "name": "Noticehawk"}, "publisher": {"@type": "Organization", "name": "Noticehawk"}}]}
    body = (b.HEADER + '<main id="main" class="doc wide">' + trail(crumbs) + f"<h1>{html.escape(title)}</h1>"
            f'<p class="lede dark">{html.escape(" ".join(facts[:2]))}</p>' + "".join(parts) + METHOD + CTA + "</main>")
    return path, title, facts[0], body + "\x00" + ld_script(ld)


def insights_index(b, cfg: dict, months: list[dict], regional: list[dict]) -> tuple[str, str]:
    latest = months[0]
    facts = market_facts(b, latest)
    rows = []
    for m in months:
        ms = month_slug(m["month"])
        regs = " · ".join(f'<a href="/insights/{ms}/{b.slug(r["region"])}/">{html.escape(r["region"])}</a>'
                          for r in regional if r["month"] == m["month"])
        rows.append([f'<a href="/insights/{ms}/">{month_name(m["month"])}</a>' + (f"<small>{regs}</small>" if regs else ""),
                     f'{int(m["awards"]):,}', b.money(m.get("median"))])
    body = (b.HEADER + '<main id="main" class="doc wide"><h1>Construction contract awards: monthly market reports</h1>'
            f'<p class="lede dark">What UK public buyers awarded in construction and building maintenance, month by month: '
            'how many contracts, typical values, the types of work, the buyers awarding most and the firms winning most.</p>'
            f'<h2>Latest: {month_name(latest["month"])}</h2><ul>' + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"
            f'<p><a href="/insights/{month_slug(latest["month"])}/">Read the full report for {month_name(latest["month"])}</a></p>'
            "<h2>All reports</h2>" + table(["Month", "Awards", "Median value"], rows, nums=(1, 2))
            + '<p class="more">Looking for one buyer? See <a href="/buyers/">what each public buyer awards, and to whom</a>.</p>'
            + METHOD + CTA + "</main>")
    return body, facts[0]


# ---------- buyers ----------

def buyer_slugs(b, buyers: list[dict]) -> dict:
    """Lower-cased buyer name -> page path. Slugs are made unique."""
    seen, out = set(), {}
    for x in buyers:
        s = base = b.slug(friendly(x["name"]))[:70].strip("-") or "buyer"
        i = 2
        while s in seen:
            s, i = f"{base}-{i}", i + 1
        seen.add(s)
        out[buyer_key(x["name"])] = f"/buyers/{s}/"
    return out


def buyer_page(b, cfg: dict, x: dict, path: str, open_rows: list[dict], region_paths: dict) -> tuple[str, str, str]:
    name = friendly(x["name"])
    n = int(x["awards"])
    cats = sorted((c for c in x.get("categories") or [] if c["name"] in b.CATEGORY_LABELS), key=lambda c: -int(c["n"]))
    title = f"{name}: construction and maintenance contracts"
    lede = (f"{name} has reported {n} construction and building maintenance contract awards in the last two years"
            + (f", with a typical (median) value of {b.money(x['median'])}." if x.get("median") else "."))
    if cats:
        lede += f" Most are for {b.CATEGORY_LABELS[cats[0]['name']].lower()}."
    parts = []
    if open_rows:
        parts.append(f"<h2>Open tenders from {html.escape(name)}</h2>" + table(
            ["Tender", "Value", "Closes in"],
            [[f'<a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
              f'<small>{html.escape(b.CATEGORY_LABELS.get(r["category"], ""))}</small>',
              b.money(r.get("value")), f'{int(r["days"])} days'] for r in open_rows[:8]], nums=(1, 2)))
    else:
        parts.append(f"<h2>Open tenders from {html.escape(name)}</h2><p>None open today that we classify as construction or building "
                     "maintenance. Subscribers are told when the next one is published.</p>")
    parts.append("<h2>What they buy</h2>" + table(
        ["Type of work", "Awards in two years"], [[html.escape(b.CATEGORY_LABELS[c["name"]]), str(int(c["n"]))] for c in cats], nums=(1,)))
    if x.get("winners"):
        parts.append("<h2>Firms that win most often</h2>" + table(
            ["Firm", "Awards"], [[html.escape(friendly(w["name"])), str(int(w["n"]))] for w in x["winners"]], nums=(1,)))
    recent = [r for r in x.get("recent") or [] if (r.get("url") or "").startswith(b.NOTICE_PREFIXES)]
    if recent:
        parts.append("<h2>Recent awards</h2>" + table(
            ["Contract", "Awarded", "Value"],
            [[f'<a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(b.tidy_title(r["title"]))}</a>'
              f'<small>{html.escape(b.CATEGORY_LABELS.get(r["category"], ""))}</small>',
              datetime.strptime(r["date"][:10], "%Y-%m-%d").strftime("%-d %b %Y"), b.money(r.get("value"))] for r in recent], nums=(2,)))
    if int(x.get("ending_12m") or 0):
        e = int(x["ending_12m"])
        parts.append(f"<h2>Coming up</h2><p>{e} of these contract{'s are' if e != 1 else ' is'} due to end in the next 12 months, "
                     "so the work may be tendered again. The Professional plan lists contracts coming up for renewal in your region.</p>")
    region = x.get("region")
    if region and region in region_paths:
        parts.append(f'<p class="more"><a href="{region_paths[region]}">All open construction tenders {in_region(region)}</a> · '
                     '<a href="/buyers/">All buyers</a></p>')
    crumbs = [("Home", "/"), ("Buyers", "/buyers/"), (name, path)]
    ld = {"@context": "https://schema.org", "@graph": [crumbs_ld(cfg, crumbs)]}
    body = (b.HEADER + '<main id="main" class="doc wide">' + trail(crumbs) + f"<h1>{html.escape(title)}</h1>"
            f'<p class="lede dark">{html.escape(lede)}</p>' + "".join(parts)
            + '<h2>About these figures</h2><p>Counted from contract award notices this buyer published on Find a Tender and Contracts Finder '
            'in the last two years that we classify as construction or building maintenance. Values are as stated in the notices. '
            'Firms are named only where the notice identifies a company. Contains public sector information licensed under the Open Government Licence v3.0.</p>'
            + CTA + "</main>")
    return title, lede, body + "\x00" + ld_script(ld)


def buyers_index(b, buyers: list[dict], paths: dict) -> str:
    rows = [[f'<a href="{paths[buyer_key(x["name"])]}">{html.escape(friendly(x["name"]))}</a>',
             html.escape(x.get("region") or ""), str(int(x["awards"])), b.money(x.get("median"))] for x in buyers]
    return (b.HEADER + '<main id="main" class="doc wide"><h1>Public buyers of construction and maintenance work</h1>'
            f'<p class="lede dark">The {len(buyers)} UK public buyers, including councils, NHS bodies, housing providers and utilities, that reported the most construction and building maintenance '
            'contract awards in the last two years. Each page shows what the buyer awards, the firms that win most often, '
            'recent contracts and any open tenders.</p>'
            + table(["Buyer", "Region", "Awards in two years", "Median value"], rows, nums=(2, 3)) + CTA + "</main>")


# ---------- weekly round-up by region ----------

def weekly_region(b, cfg: dict, region: str, new: list[dict], all_open: list[dict], updated_text: str,
                  listing_path: str | None, report_path: str | None, others: list[tuple[str, str]]) -> tuple[str, str, str, str]:
    path = f"/this-week/{b.slug(region)}/"
    title = f"New construction tenders {in_region(region)} this week"
    closing = sum(1 for r in all_open if int(r["days"]) <= 14)
    valued = [r for r in new if r.get("value") and float(r["value"]) >= 500]
    lede = (f"{len(new)} public-sector construction and building maintenance tenders were published {in_region(region)} "
            f"in the last seven days, as of {updated_text}. {len(all_open)} are open in the region in all, and {closing} of those close within 14 days.")
    extra = ""
    if valued:
        top = max(valued, key=lambda r: float(r["value"]))
        extra = (f'<p>The largest new tender by stated value is "{html.escape(top["title"])}" from '
                 f'{html.escape(friendly(top.get("buyer") or "a buyer not named"))}, at {b.money(top["value"])}.</p>')
    rows = sorted(new, key=lambda r: int(r["days"]))[:15]
    tbl = table(["Tender", "Buyer", "Value", "Closes in"],
                [[f'<a href="{html.escape(r["url"], quote=True)}" rel="noopener">{html.escape(r["title"])}</a>'
                  f'<small>{html.escape(b.CATEGORY_LABELS.get(r["category"], ""))}</small>',
                  html.escape(friendly(r.get("buyer") or "Not stated")), b.money(r.get("value")), f'{int(r["days"])} days'] for r in rows], nums=(2, 3))
    more = (f'<p class="more">Showing the {len(rows)} closing soonest of {len(new)} new this week. Subscribers get every one, scored for a firm their size.</p>'
            if len(new) > len(rows) else "")
    links = []
    if listing_path:
        links.append(f'<a href="{listing_path}">All {len(all_open)} open tenders {in_region(region)}</a>')
    if report_path:
        links.append(f'<a href="{report_path}">Latest market report for the region</a>')
    links.append('<a href="/this-week/">The best of the week across the UK</a>')
    rel = ('<h2 class="sub">Other regions this week</h2><ul class="chips links">'
           + "".join(f'<li><a href="{p}">{html.escape(t)}</a></li>' for t, p in others) + "</ul>") if others else ""
    crumbs = [("Home", "/"), ("This week", "/this-week/"), (title, path)]
    ld = {"@context": "https://schema.org", "@graph": [crumbs_ld(cfg, crumbs), {
        "@type": "ItemList", "name": title, "numberOfItems": len(new), "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": r["title"], "url": r["url"]} for i, r in enumerate(rows)]}]}
    body = (b.HEADER + '<main id="main" class="doc wide">' + trail(crumbs) + f"<h1>{html.escape(title)}</h1>"
            f'<p class="lede dark">{html.escape(lede)}</p>{extra}{tbl}{more}'
            f'<p class="more">{" · ".join(links)}</p>' + CTA + rel + "</main>")
    return path, title, lede, body + "\x00" + ld_script(ld)


# ---------- write everything ----------

def write(b, base: str, cfg: dict, out: Path, stats: dict, pages: list[dict], updated_text: str) -> dict:
    """Writes the pages and returns {"paths": [...], "insights": bool, "buyers": int, "weekly": [(region, path)]}."""
    paths: list[str] = []

    def put(path: str, title: str, desc: str, body_head: str) -> None:
        body, _, head = body_head.partition("\x00")
        d = out / path.strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(b.page(base, cfg, path, f"{title} | Noticehawk", desc[:300], body, head))
        paths.append(path)

    region_paths = {p["region"]: p["path"] for p in pages if p["region"] and not p["category"]}
    buyers = [x for x in stats.get("buyers") or [] if x.get("name") and int(x.get("awards") or 0) >= 8]
    bpaths = buyer_slugs(b, buyers)
    listings = stats.get("listings") or []
    if buyers:
        by_buyer: dict[str, list] = {}
        for r in listings:
            by_buyer.setdefault(buyer_key(r.get("buyer") or ""), []).append(r)
        put("/buyers/", "Public buyers of construction and maintenance work",
            "The UK public bodies that award the most construction and building maintenance contracts: what they buy, who wins and what is open now.",
            buyers_index(b, buyers, bpaths))
        for x in buyers:
            p = bpaths[buyer_key(x["name"])]
            title, lede, bh = buyer_page(b, cfg, x, p, by_buyer.get(buyer_key(x["name"]), []), region_paths)
            put(p, title, lede, bh)

    months = [m for m in stats.get("market") or [] if int(m.get("awards") or 0) >= 200]
    regional = [m for m in stats.get("market_regions") or [] if int(m.get("awards") or 0) >= 30 and m.get("region")]
    latest_regional: dict[str, str] = {}
    if months:
        body, desc = insights_index(b, cfg, months, regional)
        put("/insights/", "Construction contract awards: monthly market reports", desc, body)
        for m in months:
            path, title, desc, bh = market_page(b, cfg, m, bpaths, regional, months)
            put(path, title, desc, bh)
        for m in regional:
            if not any(x["month"] == m["month"] for x in months):
                continue
            path, title, desc, bh = market_page(b, cfg, m, bpaths, regional, months)
            put(path, title, desc, bh)
            latest_regional.setdefault(m["region"], path)   # regional comes newest month first

    new_urls = set(stats.get("new_week") or [])
    by_region: dict[str, list] = {}
    for r in listings:
        by_region.setdefault(r["region"], []).append(r)
    weekly = [(region, [r for r in rows if r["url"] in new_urls]) for region, rows in sorted(by_region.items())]
    weekly = [(region, new) for region, new in weekly if len(new) >= 3]
    weekly_links = [(region, f"/this-week/{b.slug(region)}/") for region, _ in weekly]
    for region, new in weekly:
        path, title, desc, bh = weekly_region(
            b, cfg, region, new, by_region[region], updated_text, region_paths.get(region), latest_regional.get(region),
            [(t, p) for t, p in weekly_links if t != region])
        put(path, title, desc, bh)
    return {"paths": paths, "insights": bool(months), "buyers": len(buyers), "weekly": weekly_links}
