"""Tells Bing (and through it ChatGPT search, Copilot and DuckDuckGo) about new and changed pages, straight after a deploy.
IndexNow: https://www.indexnow.org. Google does not take part; it finds pages from the sitemap."""
import datetime
import json
import re
import sys
import urllib.request

KEY = "54cb9e6277872f6b25f087f5af11c2de"
HOST = "noticehawk.co.uk"
DAILY = re.compile(r"^https://noticehawk\.co\.uk/(|this-week/|tenders/.*|subcontract-work/|frameworks/)$")


def urls(sitemap: str, everything: bool) -> list[str]:
    found = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    return [u for u in found if everything or DAILY.match(u)]


def main(argv: list[str]) -> int:
    everything = "--all" in argv or datetime.date.today().weekday() == 0     # every page on Mondays, listings daily
    batch = urls(open("dist/sitemap.xml").read(), everything)[:10000]
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": batch}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            print(json.dumps({"submitted": len(batch), "status": res.status}))
    except Exception as exc:  # noqa: BLE001 - search engines being slow must never fail the site deploy
        print(json.dumps({"submitted": 0, "error": str(exc)[:200]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
