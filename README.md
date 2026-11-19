# PC Preț 🖥️

**Live:** https://lucianceusanro.github.io/pc-pret/

*[Română mai jos](#română)*

## English

### What it is
A small Romanian website with two tools:

1. **Sell your PC** – pick your CPU, graphics card, RAM, SSD, motherboard, condition and whether it's a prebuilt. You get an instant estimated offer in lei, calculated from current second-hand market data (OLX listings). The sell page shows only the offer, a pawn shop comparison and the benefits (free courier pickup, fast, no haggling, no meetups); it does not display the underlying market prices.
2. **Find a deal** – type something like `4070` and see the current OLX and shop listings, a reference price (median of the listings) and which ones are below it.

Every price on the site comes from a real listing fetched by the scraper, with its link and the date it was fetched. Nothing is made up.

### Why
People who stopped gaming often have a PC sitting unused and no idea what it's worth. Pawn shops pay little, and selling on OLX takes time, haggling and meeting strangers. Buyers have the opposite problem: it's hard to tell if a listing is a good price. This tool helps both sides with real numbers. It's meant to help buyers and sellers, not to work against shops.

### Who it helps
- People with an unused gaming PC who want a fast, fair-ish number before deciding.
- Buyers looking for a used GPU/CPU who want to know what "normal" costs right now.

### How it works
```
GitHub Actions (daily cron)
   └─ scraper/scrape.py  → fetches public listing pages slowly (2.5 s between requests,
                            robots.txt checked, identifying User-Agent)
   └─ writes site/data/snapshot.json and commits it
   └─ deploys site/ to GitHub Pages (static: HTML + JS, no server)
Browser
   └─ loads snapshot.json + config.json and does all math locally
   └─ optional accounts and sell requests via Supabase (free tier, Row Level Security)
```

**Sources (status is re-checked on every run and shown on the site):**

| Source | Used for | Status at first snapshot |
|---|---|---|
| OLX.ro search pages (category + query variants, "used" filter, up to 5 pages) | second-hand prices | ✅ works |
| evoMAG.ro category pages (JSON-LD product list) | new prices | ✅ works |
| eMAG.ro | – | ❌ blocked (captcha, HTTP 511), not used |
| Altex.ro | – | ❌ no response (timeout), not used |
| Flanco.ro | – | ❌ blocked (HTTP 403), not used |
| PC Garage | – | ❌ blocked (HTTP 403), not used |

The OLX JSON API is disallowed in OLX's robots.txt, so the scraper reads the normal public search pages instead. evoMAG's own search (`?sn.q=`) is disallowed too, so it reads category pages.

**Offer formula.** Market value = sum of the used references of the chosen parts (OLX median when n ≥ 3 after outlier drop; otherwise a documented estimate from shop-new × depreciation or a neighbour). Offer = market value × condition factor × prebuilt factor × (1 − margin) − courier cost, rounded down. All factors live in [`site/config.json`](site/config.json). Shipping is free for the seller; the courier cost is ours.

**Pawn shop range.** 40–70% of the used market value, taken from MAGNOR's public guide ([source](https://magnor.ro/blog/post/amanet-electronice-ghid-2026)). It's a typical range, not a quote.

### Step-by-step tutorial
1. Open the site. In **Vinde PC-ul**, pick your parts. Choose "— nu am / nu știu —" for anything you don't know.
2. Pick the condition and the pickup country, tick that the PC works, press **Calculează oferta**.
3. See your offer and your setup. Parts without enough data are marked.
4. Compare with the typical pawn shop range and decide.
5. Optional: create an account to save the offer, send a sell request (pick a courier), or ask to be called.
6. In **Caută ofertă**, type a model (e.g. `3060`, `b550`, `ddr4 32gb`). Green rows are below the reference price.

### Run it yourself
```bash
git clone https://github.com/LucianCeusanRo/pc-pret && cd pc-pret
python3 scraper/scrape.py          # ~6 minutes, standard library only
python3 -m http.server -d site 8000 # open http://localhost:8000
```

### Accounts (optional, Supabase free tier)
1. Create a free project at supabase.com (no card needed).
2. SQL Editor → run [`supabase/schema.sql`](supabase/schema.sql) (tables + Row Level Security).
3. Authentication → URL configuration: add the site URL as a redirect URL.
4. In the GitHub repo: Settings → Secrets and variables → Actions → **Variables**: `SUPABASE_URL` and `SUPABASE_ANON_KEY`. The anon key is public by design and only works within the RLS policies. Never put the `service_role` key anywhere in this repo.
5. Re-run the workflow. Request status (`trimis` → `contactat` → `ridicat`) is changed by the owner in the Supabase table editor.

Without these variables the site still works; the account tab just says accounts aren't active yet.

### Courier adapters
Couriers are listed per country in [`site/js/couriers.js`](site/js/couriers.js): RO Fan Courier, Sameday, Cargus; BG Speedy, Econt; HU GLS, MPL. Today all use a **manual** adapter: the request is saved and we contact the seller to arrange pickup. No courier API is called, because booking pickups needs a business contract and API keys.

To add a real integration later, implement `bookPickup(request) → { ok, awb, trackingUrl }` for that courier **on a server** (e.g. a Supabase Edge Function or Vercel Function holding the API key), and have the browser adapter call that endpoint.

### Limitations
- Listing prices are asking prices, not sold prices.
- Model matching uses the listing title and can be wrong sometimes; outliers are dropped but not all noise.
- Only one shop (evoMAG) for new prices; stock is not checked.
- OLX is paginated (up to 5 pages and alternate queries per model). When a part still has fewer than 3 used listings, we **estimate** a used reference from the shop new price × a documented generation depreciation factor, or from a neighbouring model — we do **not** show "not enough data" for mainstream parts. The method is stored in the snapshot and explained on the About page. Truly unknown items show "cannot estimate".
- Vinted, Lajumate, Publi24 and Okazii were probed: search is blocked by robots, needs a login/API, or has no stable public price markup. eBay needs the owner's free developer key (optional, not scraped).
- PSU and case are not valued.
- Data is from the Romanian market, in lei, even for BG/HU pickup.
- The estimate is not a binding offer; the final amount is set after checking the PC.
- evoMAG rate-limits GitHub Actions servers (HTTP 429). When a source fails, the scraper keeps that source's listings from the last good run with their original fetch dates, and the site marks it "temporarily blocked" with the date. Running the scraper from a home connection (`python3 scraper/scrape.py` then commit) refreshes it.

### About
Built by Lucian Ceușan with AI-assisted coding. I'm a beginner and still learning programming; feedback and issues are welcome.

---

## Română

### Ce este
Un site mic, în română (și engleză, bulgară, maghiară), cu două unelte:

1. **Vinde PC-ul** – alegi procesorul, placa video, RAM-ul, SSD-ul, placa de bază, starea și dacă e PC de firmă sau asamblat. Primești pe loc o ofertă estimată în lei, calculată din datele actuale din piața second-hand (anunțuri OLX). Pagina de vânzare arată doar oferta, comparația cu amanetul și avantajele (ridicare gratuită prin curier, rapid, fără negocieri, fără întâlniri); nu afișează prețurile de piață din spate.
2. **Caută ofertă** – scrii de exemplu `4070` și vezi anunțurile actuale de pe OLX și din magazin, un preț de referință (mediana) și care sunt sub el.

Fiecare preț de pe site vine dintr-un anunț real preluat de script, cu linkul și data preluării. Nu inventăm nimic.

### De ce
Mulți care nu se mai joacă au un PC care stă degeaba și nu știu cât valorează. Amanetul dă puțin, iar vânzarea pe OLX cere timp, negocieri și întâlniri cu străini. Cumpărătorii au problema inversă: e greu de știut dacă un preț e bun. Unealta ajută ambele părți cu cifre reale. Nu e făcută împotriva magazinelor.

### Pe cine ajută
- Pe cei cu un PC de gaming nefolosit care vor o cifră rapidă înainte să decidă.
- Pe cei care caută o placă video sau un procesor second-hand și vor să știe cât e „normal” acum.

### Cum funcționează
Un script (`scraper/scrape.py`) rulează zilnic pe GitHub Actions, citește încet pagini publice de anunțuri (pauză de 2,5 s, verifică robots.txt), salvează `site/data/snapshot.json` și publică site-ul pe GitHub Pages. Tot calculul se face în browser. Conturile și cererile de vânzare folosesc Supabase (gratuit, cu Row Level Security).

Surse: OLX.ro (second-hand) și evoMAG.ro (nou) funcționează. eMAG, Altex, Flanco și PC Garage blochează accesul automat, așa că nu le folosim, iar site-ul arată asta.

Oferta = valoarea de piață (suma medianelor OLX) × stare × factor PC de firmă × (1 − marjă) − cost curier, rotunjit în jos. Setările sunt în `site/config.json`. Transportul e gratuit pentru vânzător.

Intervalul de amanet (40–70% din valoarea second-hand) vine din ghidul public MAGNOR.

### Tutorial pas cu pas
1. Deschide site-ul, tab-ul **Vinde PC-ul**, și alege componentele („— nu am / nu știu —” dacă nu știi).
2. Alege starea și țara, bifează că PC-ul funcționează, apasă **Calculează oferta**.
3. Vezi oferta și configurația ta. Componentele fără date suficiente sunt marcate.
4. Compară cu intervalul tipic de amanet și decide.
5. Opțional: fă-ți cont ca să salvezi oferta, să trimiți o cerere de vânzare (alegi curierul) sau să ceri să fii sunat.
6. În **Caută ofertă** scrii un model (ex. `3060`, `b550`, `ddr4 32gb`). Rândurile verzi sunt sub prețul de referință.

### Curieri
Fan Courier, Sameday, Cargus (RO), Speedy, Econt (BG), GLS, MPL (HU). Deocamdată nu rezervăm automat: salvăm cererea și te contactăm. Codul are o interfață (`bookPickup`) pregătită pentru API-urile curierilor, care trebuie apelate de pe un server, nu din browser.

### Limitări
Prețurile din anunțuri sunt prețuri cerute, nu prețuri de vânzare. Potrivirea după titlu poate greși. Un singur magazin pentru prețuri noi, fără verificare de stoc. Sursa și carcasa nu intră în calcul. Sub 3 anunțuri OLX folosim o estimare documentată (preț nou × amortizare / model apropiat), nu „fără date suficiente”. Vinted/Lajumate/Publi24/Okazii nu sunt integrate (robots / markup / API). eBay opțional cu cheie de dezvoltator. Estimarea nu e o ofertă fermă.

### Despre
Făcut de Lucian Ceușan cu ajutorul programării asistate de AI. Sunt începător și încă învăț programare; orice feedback e binevenit.
