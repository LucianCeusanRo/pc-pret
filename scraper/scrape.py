#!/usr/bin/env python3
"""PC Preț snapshot scraper.

Fetches PUBLIC listing pages politely (one request at a time, a pause between
requests, an identifying User-Agent, only paths allowed by each site's robots.txt)
and writes site/data/snapshot.json.

Every observed price comes from a real listing URL. When a model has fewer than
MIN_N used listings, we still publish a used-market reference by estimating from:
  1. any observed used listings (even 1–2), blended with
  2. current shop (new) price × a documented depreciation factor by generation, or
  3. the closest neighbour model in the same tier.
Estimated values are flagged with method= in the snapshot; the sell UI shows a
price (not "no data") and the methodology page explains how.

Standard library only.
"""
import json, re, sys, time, statistics, datetime, urllib.request, urllib.error, urllib.parse, urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / "scraper" / "catalog.json").read_text(encoding="utf8"))
OUT = ROOT / "site" / "data" / "snapshot.json"
UA = "Mozilla/5.0 (compatible; pc-pret-bot/1.0; +https://github.com/LucianCeusanRo/pc-pret)"
DELAY = 2.2  # seconds between requests to the same site
MIN_N = 3  # listings needed for a pure observed median (no estimate blend)
OLX_MAX_PAGES = 5
OLX_TARGET = 25  # stop paging a query once we have this many matching ads
EVO_MAX_PAGES = {"gpu": 12, "cpu": 8, "ram": 10, "ssd": 10, "mb": 10}

# Used ≈ new × factor. Calibrated as honest mid-market ask ratios, not invented
# sold prices. Documented on the site methodology page / README.
DEPRECIATION = {
    "gpu": {"16": 0.40, "20": 0.42, "30": 0.52, "40": 0.62, "50": 0.78,
            "rx500": 0.35, "rx6000": 0.50, "rx7000": 0.60, "rx9000": 0.75, "_default": 0.55},
    "cpu": {"zen2": 0.40, "zen3": 0.50, "zen4": 0.60, "zen5": 0.72,
            "cml": 0.40, "adl": 0.50, "rpl": 0.55, "_default": 0.50},
    "ram": {"ddr4": 0.45, "ddr5": 0.55, "_default": 0.50},
    "ssd": {"nvme": 0.50, "_default": 0.50},
    "mb":  {"am4": 0.45, "am5": 0.55, "lga1700": 0.50, "_default": 0.50},
}

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
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch("*", url)

def fetch(url):
    if not allowed(url):
        return ("robots", "")
    host = urllib.parse.urlsplit(url).netloc
    wait = DELAY - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ro-RO,ro;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return (r.status, r.read().decode("utf8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(60)
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
    if re.search(r"\b(cumpar|cumpăr|caut|schimb|defect|defecta|nefunctional|nefuncțional|pentru piese|dezmembr|bench)\b", t):
        return False
    # component price must not come from a whole PC, kit, bundle or accessory
    if re.search(r"\b(pc\b|sistem|calculator|desktop|laptop|notebook|bundle|combo|configuratie|configurație|"
                 r"unitate|gaming setup|kit\b|waterblock|backplate|bracket|riser|cooler|ventilator|"
                 r"cablu|suport|pasta termica|pastă termică)\b|\+", t):
        return False
    # titles that name 2+ component types are usually whole PCs, not a single part
    kinds_hit = sum(bool(re.search(pat, t)) for pat in (
        r"\b(rtx|gtx|rx\s*\d{3,4}|radeon)\b",
        r"\b(ryzen|i[3579][\s\-]*\d{4}|intel\s*core|core\s*i[3579])\b",
        r"\b(ddr[45]|\bram\b|memorii)\b",
        r"\b(nvme|\bssd\b|\bhdd\b)\b",
    ))
    if kinds_hit >= 2:
        return False
    return True

def dedupe(listings):
    seen, out = set(), []
    for l in listings:
        key = l.get("url") or (l.get("source"), l.get("title"), l.get("price"))
        if key in seen:
            continue
        seen.add(key)
        out.append(l)
    return out

# ---------------- OLX (used market) ----------------
OLX_CAT = {"gpu": "placi-video", "cpu": "procesoare", "ram": "memorii-ram", "ssd": "hard-disk-uri", "mb": "placi-de-baza"}

def olx_state(html):
    i = html.find("__PRERENDERED_STATE__")
    if i < 0:
        return None
    i = html.find('"', i)
    raw, _ = json.JSONDecoder().raw_decode(html, i)
    return json.loads(raw)

def olx_queries(item):
    qs = [item["q"]] + list(item.get("q_alt") or [])
    # de-dupe preserving order
    seen, out = set(), []
    for q in qs:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k); out.append(q.strip())
    return out

def scrape_olx_page(kind, query, item, status, page):
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
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
            "city": (a.get("location") or {}).get("cityName"),
            "posted": a.get("lastRefreshTime") or a.get("createdTime"),
            "fetched": fetched, "query": query,
        })
    return out, more

def scrape_olx(kind, item, status):
    out = []
    for query in olx_queries(item):
        for page in range(1, OLX_MAX_PAGES + 1):
            got, more = scrape_olx_page(kind, query, item, status, page)
            out = dedupe(out + got)
            if not more or len(out) >= OLX_TARGET:
                break
        if len(out) >= OLX_TARGET:
            break
    return out

# ---------------- evoMAG (new, shop) ----------------
EVO_CAT = {"gpu": "componente-pc-gaming-placi-video", "cpu": "componente-pc-gaming-procesoare",
           "ram": "componente-pc-gaming-memorii", "ssd": "componente-pc-gaming-solid-state-drive-ssd",
           "mb": "componente-pc-gaming-placi-de-baza"}

def scrape_evomag(kind, status):
    products = []
    for page in range(1, EVO_MAX_PAGES[kind] + 1):
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
    "vinted": "https://www.vinted.ro/catalog?search_text=rtx%203060",
    "lajumate": "https://lajumate.ro/anunturi_placute-video.html",
    "okazii": "https://www.okazii.ro/cautare/rtx+3060.html",
    "publi24": "https://www.publi24.ro/",
}

PROBE_NOTES = {
    "vinted": "HTML is a heavy SPA without usable embedded listings for us; public JSON API returned 404. Not integrated.",
    "lajumate": "robots.txt disallows search URLs (/search?*q= and filtered category search). Category pages alone have no query results.",
    "okazii": "robots allow search, but listing markup is opaque (no stable price JSON); mostly accessories mixed in. Not integrated yet.",
    "publi24": "robots.txt disallows /Search/ and /anunturi/? — cannot scrape search politely.",
    "ebay": "Needs a free eBay developer key from the owner. Optional; not scraped.",
}

def probe(url):
    code, html = fetch(url)
    blocked = code != 200 or "captcha" in html[:5000].lower()
    return {"http": code, "blocked": blocked}

def summarize(prices, min_n=MIN_N):
    if not prices:
        return None
    s = sorted(prices)
    med = statistics.median(s)
    s = [p for p in s if med * 0.4 <= p <= med * 2.5]
    if len(s) < min_n:
        return None
    if len(s) >= 4:
        q = statistics.quantiles(s, n=4)
        p25, p75 = q[0], q[-1]
    else:
        p25, p75 = s[0], s[-1]
    return {"median": round(statistics.median(s)), "p25": round(p25), "p75": round(p75), "n": len(s)}

def depreciation_factor(kind, item):
    table = DEPRECIATION.get(kind) or DEPRECIATION.get("gpu")
    return table.get(item.get("gen"), table.get("_default", 0.5))

def soft_used(prices):
    """Median from any number of cleaned prices (including 1)."""
    return summarize(prices, min_n=1)

def apply_estimates(models, catalog_by_id):
    """Fill models[id]['used'] via estimate when observed used listings < MIN_N.

    Two passes: first new/OLX-based estimates, then neighbour fallbacks so
    neighbours already have a used reference when we look them up.
    """
    pending = []
    for mid, m in models.items():
        item = catalog_by_id[mid]
        used_prices = [l["price"] for l in m["listings"] if l["source"] == "olx" and l.get("condition") == "used"]
        observed = soft_used(used_prices)
        pure = summarize(used_prices, min_n=MIN_N)
        if pure:
            m["used"] = {**pure, "method": "olx_median"}
            m["estimate"] = None
            continue

        new = m.get("new")
        factor = depreciation_factor(m["kind"], item)
        est = method = None
        if new and new.get("median"):
            from_new = round(new["median"] * factor)
            if observed:
                blend = statistics.median(used_prices + [from_new, from_new])
                est, method = round(blend), f"blend_olx_n{len(used_prices)}_new_x_{factor}"
            else:
                est, method = from_new, f"new_x_{factor}"
        elif observed:
            est, method = observed["median"], f"olx_scarce_n{observed['n']}"

        if est and est > 0:
            n_obs = observed["n"] if observed else 0
            m["used"] = {"median": est, "p25": round(est * 0.9), "p75": round(est * 1.1),
                         "n": n_obs, "method": method, "estimated": True}
            m["estimate"] = {"median": est, "method": method,
                             "factor": factor if method.startswith(("new", "blend")) else None,
                             "new_median": (new or {}).get("median"), "observed_n": n_obs}
        else:
            m["used"] = None
            m["estimate"] = None
            pending.append(mid)

    # Pass 2: neighbours
    for mid in pending:
        m = models[mid]
        item = catalog_by_id[mid]
        for nid in item.get("neighbors") or []:
            nb = models.get(nid)
            if not nb or not nb.get("used"):
                continue
            est = nb["used"]["median"]
            method = f"neighbor:{nid}"
            m["used"] = {"median": est, "p25": round(est * 0.9), "p75": round(est * 1.1),
                         "n": 0, "method": method, "estimated": True}
            m["estimate"] = {"median": est, "method": method, "factor": None,
                             "new_median": None, "observed_n": 0}
            break

def main():
    started = now_iso()
    sources = {
        "olx": {"label": "OLX.ro (anunțuri second-hand)", "requests": 0, "errors": [], "items": 0},
        "evomag": {"label": "evoMAG.ro (magazin, produse noi)", "requests": 0, "errors": [], "items": 0},
    }
    catalog_by_id = {}
    models = {}
    for kind, items in CATALOG.items():
        if kind.startswith("_"):
            continue
        for item in items:
            catalog_by_id[item["id"]] = {**item, "kind": kind}

        print(f"[evomag] {kind}", file=sys.stderr)
        shop = scrape_evomag(kind, sources["evomag"])
        for item in items:
            print(f"[olx] {item['id']}", file=sys.stderr)
            used = scrape_olx(kind, item, sources["olx"])
            new = [p for p in shop if matches(item, p["title"])]
            sources["olx"]["items"] += len(used)
            sources["evomag"]["items"] += len(new)
            models[item["id"]] = {
                "kind": kind, "name": item["name"], "gen": item.get("gen"),
                "used": summarize([p["price"] for p in used if p.get("condition") == "used"]),
                "new": summarize([p["price"] for p in new], min_n=1),  # even 1–2 shop SKUs are useful for estimates
                "listings": sorted(used, key=lambda x: x["price"]) + sorted(new, key=lambda x: x["price"]),
            }

    # If a source failed this run, keep its listings from the previous snapshot.
    try:
        prev = json.loads(OUT.read_text(encoding="utf8"))
    except Exception:
        prev = None
    for src in ("olx", "evomag"):
        prev_items = (prev or {}).get("sources", {}).get(src, {}).get("items", 0)
        if prev and sources[src]["items"] < 0.5 * max(prev_items, 1) and prev_items > 0:
            sources[src]["stale_since"] = prev["sources"][src].get("stale_since") or prev["generated"]
            sources[src]["items_this_run"] = sources[src]["items"]
            sources[src]["items"] = 0
            for mid, m in models.items():
                pm = prev["models"].get(mid)
                old = [l for l in (pm or {}).get("listings", []) if l["source"] == src]
                m["listings"] = [l for l in m["listings"] if l["source"] != src] + old
                sources[src]["items"] += len(old)
            for mid, m in models.items():
                item = catalog_by_id[mid]
                m["used"] = summarize([l["price"] for l in m["listings"] if l["source"] == "olx" and l.get("condition") == "used"])
                m["new"] = summarize([l["price"] for l in m["listings"] if l["source"] == "evomag"], min_n=1)

    # Estimates so mainstream parts always get a used reference
    apply_estimates(models, catalog_by_id)

    probes = {}
    for k, u in PROBES.items():
        probes[k] = probe(u)
        if k in PROBE_NOTES:
            probes[k]["note"] = PROBE_NOTES[k]
    probes["ebay"] = {"http": None, "blocked": True, "note": PROBE_NOTES["ebay"]}

    for k, v in sources.items():
        v["ok"] = v["items"] > 0
        v["errors"] = v["errors"][:10]

    n_est = sum(1 for m in models.values() if (m.get("used") or {}).get("estimated"))
    n_obs = sum(1 for m in models.values() if m.get("used") and not m["used"].get("estimated"))
    n_none = sum(1 for m in models.values() if not m.get("used"))

    snap = {
        "generated": now_iso(), "started": started,
        "sources": sources, "probes": probes, "models": models,
        "methodology": {
            "min_listings_for_observed_median": MIN_N,
            "depreciation": DEPRECIATION,
            "estimate_order": [
                "OLX used median when n >= 3 (after outlier drop)",
                "Blend scarce OLX asks with shop_new × generation depreciation",
                "Shop_new × generation depreciation alone",
                "Scarce OLX asks alone (n = 1 or 2)",
                "Nearest neighbour model in the same tier",
            ],
            "counts": {"observed": n_obs, "estimated": n_est, "none": n_none},
        },
    }
    if not any(v["ok"] for v in sources.values()):
        sys.exit("no source returned data; keeping the previous snapshot")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"wrote {OUT} models={len(models)} olx={sources['olx']['items']} evomag={sources['evomag']['items']} "
          f"observed={n_obs} estimated={n_est} none={n_none}", file=sys.stderr)

if __name__ == "__main__":
    main()
