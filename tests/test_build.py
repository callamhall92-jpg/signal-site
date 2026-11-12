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
