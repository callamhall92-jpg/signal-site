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
    build.build(STATS, CFG, tmp_path / "dist")
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
    assert "/tenders/roofing/south-east/" in site and site.count("<url>") == 7 + 8
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
    assert "Competitor watch" in (tmp_path / "dist" / "index.html").read_text()


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
