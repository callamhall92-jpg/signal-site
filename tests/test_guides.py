import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = json.loads((ROOT / "guides.json").read_text())["guides"]


def test_every_guide_is_complete_and_unique():
    slugs = [g["slug"] for g in GUIDES]
    assert len(slugs) == len(set(slugs))
    for g in GUIDES:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", g["slug"]) and len(g["slug"]) <= 80
        assert 20 <= len(g["title"]) <= 90 and 60 <= len(g["description"]) <= 260
        assert date.fromisoformat(g["date"]) <= date.today()
        assert g.get("hook") is None or 80 <= len(g["hook"]) <= 700
        page = (ROOT / "templates" / "guides" / f"{g['slug']}.html").read_text()
        assert page.lstrip().startswith("$header") and "$cta" in page, g["slug"]
        assert page.count("<h1>") == 1 and "<script" not in page.lower() and "<iframe" not in page.lower()
        assert "Checked against" in page or "as published on" in page, g["slug"]   # every guide says when its facts were checked


def test_no_orphan_guide_pages():
    on_disk = {p.stem for p in (ROOT / "templates" / "guides").glob("*.html")}
    assert on_disk == {g["slug"] for g in GUIDES}
