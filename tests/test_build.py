import json
from pathlib import Path

import build

ROOT = Path(__file__).parent.parent
STATS = json.loads((ROOT / "tests" / "sample_stats.json").read_text())
CFG = json.loads((ROOT / "config.json").read_text())


def test_money():
    assert build.money(180000) == "£180k"
    assert build.money(1200000) == "£1.2m"
    assert build.money(1234567890) == "£1.2bn"
    assert build.money(950) == "£950"
    assert build.money(None) == "Not stated"


def test_build_writes_every_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    out = tmp_path / "dist"
    for f in ("index.html", "privacy/index.html", "terms/index.html", "welcome/index.html", "404.html",
              "robots.txt", "sitemap.xml", "llms.txt", "site.css", "favicon.svg"):
        assert (out / f).exists(), f
    home = (out / "index.html").read_text()
    assert "486" in home and "£1.2bn" in home and "141" in home
    assert "12 November 2026" in home
    assert "London<span>71</span>" in home and "Repairs and maintenance<span>145</span>" in home
    assert "$" not in home.replace("£", "")          # no unfilled placeholders
    assert "application/ld+json" in home and "FAQPage" in home
    assert 'rel="canonical" href="https://noticehawk.co.uk/"' in home


def test_untrusted_text_is_escaped_and_bad_links_dropped(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    home = (tmp_path / "dist" / "index.html").read_text()
    assert "Roof &lt;b&gt;survey&lt;/b&gt;" in home and "<b>survey</b>" not in home
    assert "A &amp; B Trust" in home
    assert "javascript:" not in home and "Bad link" not in home
    assert "1 day<" in home


def test_signups_closed_shows_no_form(tmp_path):
    build.build(STATS, dict(CFG, signup_open=False), tmp_path / "dist")
    home = (tmp_path / "dist" / "index.html").read_text()
    assert "<form" not in home and "<input" not in home
    assert "mailto:hello@noticehawk.co.uk" in home


def test_robots_and_llms(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    robots = (tmp_path / "dist" / "robots.txt").read_text()
    assert "OAI-SearchBot" in robots and "Sitemap: https://noticehawk.co.uk/sitemap.xml" in robots
    assert "Basic £29 a month" in (tmp_path / "dist" / "llms.txt").read_text()


def test_signups_open_shows_the_form(tmp_path):
    build.build(STATS, dict(CFG, signup_open=True), tmp_path / "dist")
    home = (tmp_path / "dist" / "index.html").read_text()
    assert '<form class="card" id="signup"' in home and "functions/v1/lead-form" in home
    assert home.count("<option>") == 12 and 'value="roofing"' in home
    assert 'name="website"' in home and "/signup.js" in home
    assert "open shortly" not in home and "No card needed." in home
    assert (tmp_path / "dist" / "signup.js").exists()


def test_confirmed_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "confirmed" / "index.html").read_text()
    assert "You're confirmed." in page and "noindex" in page


def test_unsubscribe_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "unsubscribe" / "index.html").read_text()
    assert "Unsubscribe me" in page and "functions/v1/unsubscribe" in page and 'method:"POST"' in page


def test_listing_pages(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    out = tmp_path / "dist"
    for path in ("tenders/index.html", "tenders/roofing/index.html", "tenders/south-east/index.html",
                 "tenders/roofing/south-east/index.html", "tenders/roofing/scotland/index.html",
                 "tenders/refurbishment/east-of-england/index.html"):
        assert (out / path).exists(), path
    assert not (out / "tenders" / "roofing" / "london").exists()                # no page without a tender
    page = (out / "tenders" / "roofing" / "index.html").read_text()
    assert "<h1>Roofing tenders in the UK</h1>" in page and "2 open public-sector tenders" in page
    assert "Roof repairs &amp; minor &lt;works&gt;" in page and "evil.example" not in page and "Bad link row" not in page
    assert page.index("Roof repairs") < page.index("Flat roof replacement")       # soonest deadline first
    assert "BreadcrumbList" in page and "ItemList" in page
    both = (out / "tenders" / "roofing" / "south-east" / "index.html").read_text()
    assert "<h1>Roofing tenders in the South East</h1>" in both and "/tenders/roofing/scotland/" in both
    assert "Roofing tenders in Scotland" in (out / "tenders" / "roofing" / "scotland" / "index.html").read_text()
    site = (out / "sitemap.xml").read_text()
    assert "/tenders/roofing/south-east/" in site and site.count("<url>") == 7 + 8 + 5 + 3 + 3 + (len(build.GUIDES) - 7)  # fixed pages, plus one for each guide added since the first seven
    assert 'id="work-form"' in (out / "post-work" / "index.html").read_text() and "/subcontract-work/" in site
    assert 'noindex' in (out / "post-work" / "manage" / "index.html").read_text()
    home = (out / "index.html").read_text()
    assert '<a href="/tenders/south-east/">South East<span>59</span></a>' in home


def test_preferences_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "preferences" / "index.html").read_text()
    assert page.count('name="regions"') == 12 and page.count('name="trades"') == 7
    assert "functions/v1/preferences" in page and "noindex" in page and (tmp_path / "dist" / "preferences.js").exists()


def test_shortlist_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "shortlist" / "index.html").read_text()
    assert "functions/v1/shortlist" in page and "noindex" in page and "Add the deadline to my calendar" in page
    assert (tmp_path / "dist" / "shortlist.js").exists()
    assert "Shortlist with deadline reminders" in (tmp_path / "dist" / "index.html").read_text()


def test_preferences_page_has_watchlists(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "preferences" / "index.html").read_text()
    assert 'id="watch" hidden' in page and 'id="keywords"' in page and 'id="competitors"' in page
    assert "5 competitors" in (tmp_path / "dist" / "index.html").read_text()


def test_analytics_on_public_pages_only(tmp_path):
    import build
    cfg = {**json.loads((build.ROOT / "config.json").read_text()), "analytics_token": "abc123"}
    stats = json.loads((build.ROOT / "tests" / "sample_stats.json").read_text())
    build.build(stats, cfg, tmp_path)
    assert "cloudflareinsights.com/beacon.min.js" in (tmp_path / "index.html").read_text()
    assert "abc123" in (tmp_path / "privacy" / "index.html").read_text()
    for private in ("preferences", "shortlist", "unsubscribe", "welcome", "confirmed"):
        assert "cloudflareinsights" not in (tmp_path / private / "index.html").read_text(), private
    build.build(stats, {**cfg, "analytics_token": ""}, tmp_path)
    assert "cloudflareinsights" not in (tmp_path / "index.html").read_text()


def test_how_it_works_example_alert_and_weekly_digest(tmp_path):
    import build
    cfg = json.loads((build.ROOT / "config.json").read_text())
    stats = json.loads((build.ROOT / "tests" / "sample_stats.json").read_text())
    build.build(stats, cfg, tmp_path)
    how = (tmp_path / "how-it-works" / "index.html").read_text()
    assert "Contracts Finder" in how and "up to 30 points" in how and "does not write or submit bids" in how.replace("It does", "does")
    alert = (tmp_path / "example-alert" / "index.html").read_text()
    assert "Fit with your work 30/30" in alert and "Not stated in the notice: where the work is" in alert
    week = (tmp_path / "this-week" / "index.html").read_text()
    assert "Flat roof replacement, sports hall" in week and "javascript:" not in week and "Injected" not in week
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert all(f"/{p}/</loc>" in sitemap for p in ("this-week", "how-it-works", "example-alert"))
    build.build({**stats, "digest": [], "sample": []}, cfg, tmp_path)
    assert "being put together" in (tmp_path / "this-week" / "index.html").read_text()
    assert "being refreshed" in (tmp_path / "example-alert" / "index.html").read_text()


def test_homepage_menu_links_to_the_new_pages(tmp_path):
    import build
    cfg = json.loads((build.ROOT / "config.json").read_text())
    build.build(json.loads((build.ROOT / "tests" / "sample_stats.json").read_text()), cfg, tmp_path)
    home = (tmp_path / "index.html").read_text()
    assert all(f'href="/{p}/"' in home for p in ("this-week", "how-it-works", "example-alert"))


def test_sign_up_form_offers_the_plan_news_opt_out(tmp_path):
    import build
    cfg = {**json.loads((build.ROOT / "config.json").read_text()), "signup_open": True}
    build.build(json.loads((build.ROOT / "tests" / "sample_stats.json").read_text()), cfg, tmp_path)
    home = (tmp_path / "index.html").read_text()
    assert 'name="product_updates" type="checkbox" checked' in home and "Untick if you would rather not" in home
    assert "product_updates: f.product_updates.checked" in (tmp_path / "signup.js").read_text()
    assert "up to two short emails" in (tmp_path / "privacy" / "index.html").read_text()


def test_preferences_page_offers_followed_buyers(tmp_path):
    import build
    cfg = json.loads((build.ROOT / "config.json").read_text())
    build.build(json.loads((build.ROOT / "tests" / "sample_stats.json").read_text()), cfg, tmp_path)
    assert 'id="buyers"' in (tmp_path / "preferences" / "index.html").read_text()
    assert 'body.buyers = lines("buyers")' in (tmp_path / "preferences.js").read_text()


def test_preferences_page_offers_contract_size(tmp_path):
    import build
    cfg = json.loads((build.ROOT / "config.json").read_text())
    build.build(json.loads((build.ROOT / "tests" / "sample_stats.json").read_text()), cfg, tmp_path)
    page = (tmp_path / "preferences" / "index.html").read_text()
    assert 'id="fit" hidden' in page and '<option value="250000">£250,000</option>' in page
    script = (tmp_path / "preferences.js").read_text()
    assert "body.max_value" in script and "fit_bad_range" in script


def test_login_and_account_pages(tmp_path):
    import build
    cfg = json.loads((build.ROOT / "config.json").read_text())
    build.build(json.loads((build.ROOT / "tests" / "sample_stats.json").read_text()), cfg, tmp_path)
    login = (tmp_path / "login" / "index.html").read_text()
    account = (tmp_path / "account" / "index.html").read_text()
    assert 'data-api="https://wboavagwignktkodqvwa.supabase.co/functions/v1/login"' in login and "noindex" in login
    assert 'id="f-region"' in account and "noindex" in account and "cloudflareinsights" not in account
    assert "/account/</loc>" not in (tmp_path / "sitemap.xml").read_text()
    assert 'href="/login/"' in (tmp_path / "index.html").read_text()
    assert (tmp_path / "account.js").exists() and (tmp_path / "login.js").exists()


def test_guides_are_built_and_listed(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    for slug in ("finding-public-sector-construction-tenders", "procurement-act-2023-construction",
                 "frameworks-and-call-offs", "tender-alert-services-compared"):
        page = (tmp_path / "dist" / "guides" / slug / "index.html").read_text()
        assert "$" not in page.split("<main", 1)[1].split("</main>", 1)[0].replace("£", "")
        assert f"/guides/{slug}/" in (tmp_path / "dist" / "sitemap.xml").read_text()
    assert "/guides/" in (tmp_path / "dist" / "index.html").read_text()


def test_signup_form_carries_weekly_rates(tmp_path):
    cfg = dict(CFG, signup_open=True)
    build.build(dict(STATS, rates=[{"region": "South East", "category": "roofing", "per_week": 0.5}]), cfg, tmp_path / "dist")
    page = (tmp_path / "dist" / "index.html").read_text()
    assert 'data-rates="{&quot;South East|roofing&quot;: 0.5}"' in page and 'id="s-rate"' in page


def test_feedback_page(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    page = (tmp_path / "dist" / "feedback" / "index.html").read_text()
    assert 'data-reason="wrong_area"' in page and "noindex" in page and "/feedback.js" in page
    assert 'data-feedback="https://' in (tmp_path / "dist" / "account" / "index.html").read_text()


def test_plan_buttons_go_to_stripe_only_when_open(tmp_path):
    links = {"construction_basic": "https://buy.stripe.com/b", "construction_pro": "https://buy.stripe.com/p",
             "construction_premium": "https://buy.stripe.com/x"}
    build.build(STATS, dict(CFG, signup_open=True, payment_links=links), tmp_path / "open")
    home = (tmp_path / "open" / "index.html").read_text()
    for url in links.values():
        assert f'href="{url}"' in home
    build.build(STATS, dict(CFG, signup_open=False, payment_links=links), tmp_path / "shut")
    assert "buy.stripe.com" not in (tmp_path / "shut" / "index.html").read_text()


def _content_stats():
    rows = [dict(r) for r in STATS["listings"]]
    region = rows[0]["region"]
    mine = [r for r in rows if r["region"] == region]
    extra = [{**mine[0], "title": f"Extra works package {i}", "url": f"https://www.find-tender.service.gov.uk/Notice/00{i}-2026",
              "buyer": "KENT COUNTY COUNCIL"} for i in range(3)]
    month = {"month": "2026-10-01", "region": None, "awards": 1122, "prev": 1229, "firms": 1347, "median": 256000,
             "with_value": 975, "under_500k": 575,
             "categories": [{"name": "roofing", "n": 85, "median": 313435.9}, {"name": "refurbishment", "n": 192, "median": 241312.5}],
             "regions": [{"name": region, "n": 109}, {"name": "Wales", "n": 102}],
             "buyers": [{"name": "KENT COUNTY COUNCIL", "n": 35}], "winners": [{"name": "ABCA SYSTEMS LIMITED", "n": 19}],
             "largest": [{"title": "CA123 - Highways resurfacing", "buyer": "Sefton Council", "value": 8000000,
                          "url": "https://www.find-tender.service.gov.uk/Notice/096120-2026", "category": "groundworks_civils"}]}
    return {**STATS, "listings": rows + extra, "new_week": [r["url"] for r in extra],
            "market": [month, {**month, "month": "2026-09-01", "awards": 150}],     # September is too thin to publish
            "market_regions": [{**month, "region": region, "awards": 109, "regions": []}],
            "buyers": [{"name": "KENT COUNTY COUNCIL", "region": region, "awards": 40, "median": 55677, "ending_12m": 3,
                        "categories": [{"name": "roofing", "n": 30}], "winners": [{"name": "ROCON CONTRACTORS LIMITED", "n": 9}],
                        "recent": [{"title": "School roof", "date": "2026-11-12", "value": 96883.5, "category": "roofing",
                                    "url": "https://www.contractsfinder.service.gov.uk/Notice/abc"}]}]}, region


def test_market_reports_buyers_and_weekly_round_ups(tmp_path):
    stats, region = _content_stats()
    out = tmp_path / "dist"
    build.build(stats, CFG, out)
    rslug = build.slug(region)
    report = (out / "insights" / "2026-10" / "index.html").read_text()
    assert "UK construction contracts awarded: October 2026" in report and "1,122 construction" in report
    assert 'href="/buyers/kent-county-council/">Kent County Council</a>' in report and "Abca Systems Limited" in report
    assert "CA123" not in report and "Highways resurfacing" in report
    assert not (out / "insights" / "2026-09").exists()
    assert (out / "insights" / "2026-10" / rslug / "index.html").exists()
    assert "October 2026" in (out / "insights" / "index.html").read_text()
    buyer = (out / "buyers" / "kent-county-council" / "index.html").read_text()
    assert "Rocon Contractors Limited" in buyer and "Extra works package 0" in buyer and "3 of these contracts are due to end" in buyer
    week = (out / "this-week" / rslug / "index.html").read_text()
    assert "3 public-sector construction" in week and "Extra works package 2" in week
    assert f"/this-week/{rslug}/" in (out / "this-week" / "index.html").read_text()
    site = (out / "sitemap.xml").read_text()
    for path in ("/insights/2026-10/", f"/insights/2026-10/{rslug}/", "/buyers/kent-county-council/", f"/this-week/{rslug}/"):
        assert path in site
    assert "/buyers/" in (out / "llms.txt").read_text()


def test_no_content_pages_without_data(tmp_path):
    build.build(STATS, CFG, tmp_path / "dist")
    assert not (tmp_path / "dist" / "buyers").exists() and not (tmp_path / "dist" / "insights").exists()
