#!/usr/bin/env python3
"""PC Preț snapshot scraper.

Fetches PUBLIC listing pages politely (one request at a time, a pause between
requests, an identifying User-Agent, only paths allowed by each site's robots.txt)
and writes site/data/snapshot.json. No prices are invented: every price in the
snapshot comes from a listing that was fetched in this run, with its URL.

Standard library only, so it runs anywhere (GitHub Actions, a laptop).
"""
import json, re, sys, time, statistics, datetime, urllib.request, urllib.error, urllib.parse, urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / "scraper" / "catalog.json").read_text(encoding="utf8"))
OUT = ROOT / "site" / "data" / "snapshot.json"
UA = "Mozilla/5.0 (compatible; pc-pret-bot/1.0; +https://github.com/LucianCeusanRo/pc-pret)"
DELAY = 2.5  # seconds between requests to the same site
MIN_N = 3  # minimum listings for a reference price
MAX_PAGES = {"gpu": 12, "cpu": 6, "ram": 10, "ssd": 10, "mb": 10}

_robots = {}
_last = {}

def allowed(url):
    host = urllib.parse.urlsplit(url)
    base = f"{host.scheme}://{host.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                rp.parse(r.read().decode("utf8", "replace").splitlines())
        except Exception:
            rp = None  # robots unreachable -> treat as allowed for plain listing pages
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch("*", url)

def fetch(url):
    """Returns (status, text). Respects robots.txt and a per-host delay."""
    if not allowed(url):
        return ("robots", "")
    host = urllib.parse.urlsplit(url).netloc
    wait = DELAY - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ro-RO,ro;q=0.9"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return (r.status, r.read().decode("utf8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(60)  # rate limited: back off once, then give up
                continue
            return (e.code, "")
        except Exception as e:
            return ("error:" + type(e).__name__, "")
    return ("error", "")

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

def matches(item, title):
    t = title.lower()
    if not re.search(item["match"], t, re.I):
        return False
    if item.get("exclude") and re.search(item["exclude"], t, re.I):
        return False
    # skip wanted-to-buy / swap / broken ads
    if re.search(r"\b(cumpar|cumpăr|caut|schimb|defect|defecta|nefunctional|pentru piese|dezmembr)", t):
        return False
    # a component price must not come from a whole PC, a bundle or an accessory
    if re.search(r"\b(pc|sistem|calculator|desktop|laptop|notebook|bundle|combo|configuratie|unitate|gaming setup|"
                 r"waterblock|backplate|bracket|riser|cooler|ventilator|cablu|suport)\b|\+", t):
        return False
    return True

# ---------------- OLX (used market) ----------------
OLX_CAT = {"gpu": "placi-video", "cpu": "procesoare", "ram": "memorii-ram", "ssd": "hard-disk-uri", "mb": "placi-de-baza"}

def olx_state(html):
    i = html.find("__PRERENDERED_STATE__")
    if i < 0:
        return None
    i = html.find('"', i)
    raw, _ = json.JSONDecoder().raw_decode(html, i)
    return json.loads(raw)

def scrape_olx(kind, item, status):
    out = []
    for page in (1, 2):
        got, more = scrape_olx_page(kind, item, status, page)
        out += got
        if not more or len(out) >= 15:
            break
    return out

def scrape_olx_page(kind, item, status, page):
    slug = re.sub(r"[^a-z0-9]+", "-", item["q"].lower()).strip("-")
    url = (f"https://www.olx.ro/electronice-si-electrocasnice/componente-laptop-pc/{OLX_CAT[kind]}/q-{slug}/"
           "?search%5Bfilter_enum_state%5D%5B0%5D=used" + (f"&page={page}" if page > 1 else ""))
    code, html = fetch(url)
    status["requests"] += 1
    if code != 200:
        status["errors"].append(f"{code} {url}")
        return [], False
    try:
        listing = olx_state(html)["listing"]["listing"]
        ads = listing["ads"]
        more = listing.get("totalPages", 1) > page
    except Exception as e:
        status["errors"].append(f"parse {url}: {e}")
        return [], False
    out = []
    fetched = now_iso()
    for a in ads:
        p = (a.get("price") or {}).get("regularPrice") or {}
        if p.get("currencyCode") != "RON" or not p.get("value"):
            continue
        if not matches(item, a.get("title", "")):
            continue
        cond = None
        for prm in a.get("params") or []:
            if prm.get("key") == "state":
                cond = prm.get("normalizedValue")
        out.append({
            "source": "olx", "title": a["title"][:140], "price": round(float(p["value"])),
            "url": a["url"], "condition": cond or "used", "business": bool(a.get("isBusiness")),
            "city": (a.get("location") or {}).get("cityName"), "posted": a.get("lastRefreshTime") or a.get("createdTime"),
            "fetched": fetched,
        })
    return out, more

# ---------------- evoMAG (new, shop) ----------------
EVO_CAT = {"gpu": "componente-pc-gaming-placi-video", "cpu": "componente-pc-gaming-procesoare",
           "ram": "componente-pc-gaming-memorii", "ssd": "componente-pc-gaming-solid-state-drive-ssd",
           "mb": "componente-pc-gaming-placi-de-baza"}

def scrape_evomag(kind, status):
    products = []
    for page in range(1, MAX_PAGES[kind] + 1):
        url = f"https://www.evomag.ro/{EVO_CAT[kind]}/" + ("" if page == 1 else f"filtru/pagina:{page}")
        code, html = fetch(url)
        status["requests"] += 1
        if code != 200:
            status["errors"].append(f"{code} {url}")
            break
        fetched = now_iso()
        found = 0
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            if d.get("@type") != "ItemList":
                continue
            for el in d.get("itemListElement", []):
                it = el.get("item") or {}
                off = it.get("offers") or {}
                if off.get("priceCurrency") != "RON" or not off.get("price"):
                    continue
                products.append({"source": "evomag", "title": it.get("name", "")[:140],
                                 "price": round(float(off["price"])), "url": it.get("url"),
                                 "condition": "new", "business": True, "fetched": fetched})
                found += 1
        if found == 0:
            break
    return products

# ---------------- shops we only probe ----------------
PROBES = {
    "emag": "https://www.emag.ro/placi_video/c",
    "altex": "https://altex.ro/placi-video/cpl/",
    "flanco": "https://www.flanco.ro/laptop-it-tablete/componente-pc.html",
    "pcgarage": "https://www.pcgarage.ro/placi-video/",
}

def probe(url):
    code, html = fetch(url)
    blocked = code != 200 or "captcha" in html[:5000].lower()
    return {"http": code, "blocked": blocked}

def summarize(prices):
    if not prices:
        return None
    s = sorted(prices)
    med = statistics.median(s)
    # drop obvious outliers (typos, bundles, accessories) then recompute
    s = [p for p in s if med * 0.4 <= p <= med * 2.5]
    if len(s) < MIN_N:
        return None  # not enough listings for an honest reference
    q = statistics.quantiles(s, n=4) if len(s) >= 4 else [s[0], statistics.median(s), s[-1]]
    return {"median": round(statistics.median(s)), "p25": round(q[0]), "p75": round(q[-1]), "n": len(s)}

def main():
    started = now_iso()
    sources = {
        "olx": {"label": "OLX.ro (anunțuri second-hand)", "requests": 0, "errors": [], "items": 0},
        "evomag": {"label": "evoMAG.ro (magazin, produse noi)", "requests": 0, "errors": [], "items": 0},
    }
    models = {}
    for kind, items in CATALOG.items():
        if kind.startswith("_"):
            continue
        print(f"[evomag] {kind}", file=sys.stderr)
        shop = scrape_evomag(kind, sources["evomag"])
        for item in items:
            print(f"[olx] {item['id']}", file=sys.stderr)
            used = scrape_olx(kind, item, sources["olx"])
            new = [p for p in shop if matches(item, p["title"])]
            sources["olx"]["items"] += len(used)
            sources["evomag"]["items"] += len(new)
            models[item["id"]] = {
                "kind": kind, "name": item["name"],
                "used": summarize([p["price"] for p in used if p["condition"] == "used"]),
                "new": summarize([p["price"] for p in new]),
                "listings": sorted(used, key=lambda x: x["price"]) + sorted(new, key=lambda x: x["price"]),
            }
    # If a source failed this run (blocked / rate limited), keep its listings from the
    # previous snapshot instead of showing nothing. Those listings keep their ORIGINAL
    # fetch date, and the source is marked stale on the site.
    try:
        prev = json.loads(OUT.read_text(encoding="utf8"))
    except Exception:
        prev = None
    for src in ("olx", "evomag"):
        prev_items = (prev or {}).get("sources", {}).get(src, {}).get("items", 0)
        if prev and sources[src]["items"] < 0.5 * prev_items:
            sources[src]["stale_since"] = prev["sources"][src].get("stale_since") or prev["generated"]
            sources[src]["items_this_run"] = sources[src]["items"]
            sources[src]["items"] = 0
            for mid, m in models.items():
                pm = prev["models"].get(mid)
                old = [l for l in (pm or {}).get("listings", []) if l["source"] == src]
                m["listings"] = [l for l in m["listings"] if l["source"] != src] + old
                sources[src]["items"] += len(old)
            for m in models.values():
                m["used"] = summarize([l["price"] for l in m["listings"] if l["source"] == "olx" and l["condition"] == "used"])
                m["new"] = summarize([l["price"] for l in m["listings"] if l["source"] == "evomag"])
    probes = {k: probe(u) for k, u in PROBES.items()}
    for k, v in sources.items():
        v["ok"] = v["items"] > 0
        v["errors"] = v["errors"][:10]
    snap = {"generated": now_iso(), "started": started, "sources": sources, "probes": probes, "models": models}
    if not any(v["ok"] for v in sources.values()):
        sys.exit("no source returned data; keeping the previous snapshot")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"wrote {OUT} models={len(models)} olx={sources['olx']['items']} evomag={sources['evomag']['items']}", file=sys.stderr)

if __name__ == "__main__":
    main()
