(() => {
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const LANGS = ["ro", "en", "bg", "hu"];
let lang = localStorage.getItem("pcp_lang") || "ro";
if (!LANGS.includes(lang)) lang = "ro";
let SNAP = null, CFG = null, sb = null, user = null, lastEstimate = null;

const t = (k, vars = {}) => {
  let s = (I18N[lang] && I18N[lang][k]) || I18N.ro[k] || k;
  for (const [a, b] of Object.entries(vars)) s = s.replaceAll(`{${a}}`, b);
  return s;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const locale = () => ({ ro: "ro-RO", en: "en-GB", bg: "bg-BG", hu: "hu-HU" }[lang]);
const ron = (n) => new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(n) + " lei";
const fmtDate = (iso) => new Intl.DateTimeFormat(locale(), { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Bucharest" }).format(new Date(iso));
const fmtDay = (iso) => new Intl.DateTimeFormat(locale(), { dateStyle: "short", timeZone: "Europe/Bucharest" }).format(new Date(iso));

function applyI18n() {
  document.documentElement.lang = lang;
  $$("[data-i]").forEach((el) => (el.textContent = t(el.dataset.i)));
  $$("[data-ph]").forEach((el) => (el.placeholder = t(el.dataset.ph)));
  $("#lang").value = lang;
  if (SNAP) {
    const n = Object.values(SNAP.models).reduce((a, m) => a + m.listings.length, 0);
    $("#datafrom").textContent = t("data_from", { date: fmtDate(SNAP.generated), n });
    fillSelects(); renderSources();
  }
  renderAccount();
  if (lastEstimate) renderEstimate(lastEstimate);
  if ($("#q").value) runSearch();
}

// ---------- tabs ----------
function showTab(id) {
  $$(".tab").forEach((s) => (s.hidden = s.id !== id));
  $$("nav [data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  history.replaceState(null, "", "#" + id);
}

// ---------- sell form ----------
const KINDS = { cpu: "f_cpu", gpu: "f_gpu", ram: "f_ram", ssd: "f_ssd", mb: "f_mb" };
function fillSelects() {
  for (const kind of Object.keys(KINDS)) {
    const sel = $("#s_" + kind), keep = sel.value;
    const opts = Object.entries(SNAP.models).filter(([, m]) => m.kind === kind)
      .map(([id, m]) => `<option value="${id}">${esc(m.name)}${m.used ? "" : " (" + t("no_data") + ")"}</option>`);
    sel.innerHTML = `<option value="">${esc(t("opt_none"))}</option>` + opts.join("");
    sel.value = keep;
  }
}

function readForm() {
  const parts = {};
  for (const k of Object.keys(KINDS)) parts[k] = $("#s_" + k).value || null;
  return { type: $("input[name=type]:checked").value, parts, condition: $("#s_cond").value, country: $("#s_country").value };
}

function estimate(conf) {
  const rows = [], missing = [];
  let ref = 0;
  for (const [kind, id] of Object.entries(conf.parts)) {
    if (!id) continue;
    const m = SNAP.models[id];
    rows.push({ kind, id, m });
    if (m.used) ref += m.used.median; else missing.push(m.name);
  }
  const cf = CFG.condition_factor[conf.condition] ?? 1;
  const pb = conf.type === "prebuilt" ? CFG.prebuilt_factor : 1;
  const courier = CFG.courier_cost_ron[conf.country] ?? CFG.courier_cost_ron.RO;
  let offer = ref * cf * pb * (1 - CFG.margin) - courier;
  offer = Math.max(0, Math.floor(offer / CFG.round_to) * CFG.round_to);
  return { conf, rows, missing, ref: Math.round(ref), offer, pawnLow: Math.round(ref * CFG.pawn_range.low), pawnHigh: Math.round(ref * CFG.pawn_range.high), snapshot: SNAP.generated };
}

function renderEstimate(e) {
  const box = $("#result");
  const pawnCmp = e.offer > e.pawnHigh ? "us_vs_pawn_above" : e.offer >= e.pawnLow ? "us_vs_pawn_within" : "us_vs_pawn_below";
  box.innerHTML = `
    <h2>${esc(t("res_title"))}</h2>
    <div class="offer"><span class="big">${e.offer ? ron(e.offer) : "—"}</span><span class="pill">🚚 ${esc(t("free_shipping"))}</span></div>
    <p class="muted">${esc(t("disclaimer"))}</p>
    <h3>${esc(t("parts_title"))}</h3>
    <ul class="partlist">${e.rows.map(({ kind, m }) => `<li><b>${esc(t(KINDS[kind]))}:</b> ${esc(m.name)}${m.used ? "" : ` <i class="warn">(${esc(t("no_data"))})</i>`}</li>`).join("")}</ul>
    ${e.missing.length ? `<p class="warn">${esc(t("missing_note", { list: e.missing.join(", ") }))}</p>` : ""}
    <details><summary>${esc(t("how_title"))}</summary><p>${esc(t("how_text"))}</p></details>
    <h3>${esc(t("cmp_title"))}</h3>
    <div class="cmp">
      <div class="card"><h4>${esc(t("cmp_pawn"))}</h4><div class="amt">${ron(e.pawnLow)} – ${ron(e.pawnHigh)}</div><p>${esc(t("pawn_text"))} <a href="${CFG.pawn_range.source}" target="_blank" rel="noopener">${esc(t("pawn_source"))}</a></p></div>
      <div class="card us"><h4>${esc(t("cmp_us"))}</h4><div class="amt">${ron(e.offer)}</div><p>${esc(t("us_text"))}</p></div>
    </div>
    <p><b>${esc(t(pawnCmp))}</b></p>
    <h3>${esc(t("benefits_title"))}</h3>
    <ul class="benefits"><li>🚚 ${esc(t("b1"))}</li><li>⚡ ${esc(t("b2"))}</li><li>🤝 ${esc(t("b3"))}</li><li>🏠 ${esc(t("b4"))}</li></ul>
    <p class="muted">${esc(t("data_from", { date: fmtDate(e.snapshot), n: e.rows.reduce((a, r) => a + (r.m.used ? r.m.used.n : 0), 0) }))}</p>
    <div class="actions"><button id="b_save">${esc(t("btn_save"))}</button><button id="b_sell" class="primary">${esc(t("btn_sell"))}</button><button id="b_contact">${esc(t("btn_contact"))}</button></div>
    <div id="reqform"></div><p id="actmsg" class="msg"></p>`;
  $("#b_save").onclick = saveOffer;
  $("#b_sell").onclick = () => openRequest("sell");
  $("#b_contact").onclick = () => openRequest("contact");
}

function onEstimate(ev) {
  ev.preventDefault();
  const err = $("#formerr"); err.textContent = "";
  if (!$("#s_works").checked) return (err.textContent = t("err_works"));
  const conf = readForm();
  if (!conf.parts.cpu && !conf.parts.gpu) return (err.textContent = t("err_pick"));
  lastEstimate = estimate(conf);
  renderEstimate(lastEstimate);
  $("#result").hidden = false;
  $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- accounts (Supabase) ----------
function requireLogin() {
  if (user) return true;
  $("#actmsg").textContent = t("need_login");
  setTimeout(() => showTab("account"), 900);
  return false;
}
async function saveOffer() {
  if (!requireLogin()) return;
  const e = lastEstimate;
  const { error } = await sb.from("offers").insert({ config: e.conf, estimate_ron: e.offer, snapshot_date: e.snapshot });
  $("#actmsg").textContent = error ? error.message : t("saved_ok");
  if (!error) loadMine();
}
function openRequest(kind) {
  if (!requireLogin()) return;
  const country = lastEstimate.conf.country;
  const couriers = COURIERS[country] || [];
  $("#reqform").innerHTML = `<form id="rf" class="panel">
    <h3>${esc(t(kind === "sell" ? "sell_title" : "contact_title"))}</h3>
    <p class="muted">${esc(t(kind === "sell" ? "courier_note" : "contact_note"))}</p>
    <label>${esc(t("f_name"))}<input name="name" required maxlength="100" autocomplete="name"></label>
    <label>${esc(t("f_phone"))}<input name="phone" required maxlength="30" type="tel" autocomplete="tel"></label>
    ${kind === "sell" ? `
    <label>${esc(t("f_city"))}<input name="city" required maxlength="80"></label>
    <label>${esc(t("f_address"))}<input name="address" required maxlength="300" autocomplete="street-address"></label>
    <fieldset><legend>${esc(t("f_courier"))}</legend>${couriers.map((c, i) => `<label class="inline"><input type="radio" name="courier" value="${c.id}" ${i ? "" : "checked"}> ${esc(c.name)}</label>`).join("")}</fieldset>`
    : `<label>${esc(t("f_when"))}<input name="call_when" maxlength="100"></label>`}
    <label>${esc(t("f_notes"))}<textarea name="notes" maxlength="500" rows="2"></textarea></label>
    <div class="actions"><button class="primary">${esc(t("btn_submit"))}</button><button type="button" id="rf_x">${esc(t("btn_cancel"))}</button></div></form>`;
  $("#rf_x").onclick = () => ($("#reqform").innerHTML = "");
  $("#rf").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = Object.fromEntries(new FormData(ev.target));
    const e = lastEstimate;
    const row = { kind, config: e.conf, estimate_ron: e.offer, snapshot_date: e.snapshot, country, ...f };
    if (kind === "sell") {
      const c = couriers.find((x) => x.id === f.courier);
      const booking = await c.bookPickup(row); // manual today; see couriers.js
      row.courier = c.id;
      if (!booking.ok) return ($("#actmsg").textContent = "Courier error");
    }
    const { error } = await sb.from("sell_requests").insert(row);
    $("#actmsg").textContent = error ? error.message : t("sent_ok");
    if (!error) { $("#reqform").innerHTML = ""; loadMine(); }
  };
}

function renderAccount() {
  const box = $("#acc");
  if (!sb) { box.innerHTML = `<p class="warn">${esc(t("auth_off"))}</p>`; return; }
  if (!user) {
    box.innerHTML = `<form id="af" class="panel">
      <label>${esc(t("email"))}<input name="email" type="email" required autocomplete="email"></label>
      <label>${esc(t("password"))}<input name="password" type="password" minlength="8" required autocomplete="current-password"></label>
      <div class="actions"><button class="primary" value="in">${esc(t("login"))}</button><button value="up">${esc(t("signup"))}</button></div>
      <p id="amsg" class="msg"></p></form>`;
    $("#af").onsubmit = async (ev) => {
      ev.preventDefault();
      const { email, password } = Object.fromEntries(new FormData(ev.target));
      const up = ev.submitter && ev.submitter.value === "up";
      const r = up ? await sb.auth.signUp({ email, password, options: { emailRedirectTo: location.origin + location.pathname + "#account" } })
                   : await sb.auth.signInWithPassword({ email, password });
      $("#amsg").textContent = r.error ? r.error.message : up && !r.data.session ? t("check_email") : "";
    };
    return;
  }
  box.innerHTML = `<p>${esc(t("logged_as", { email: user.email }))} <button id="lo">${esc(t("logout"))}</button></p>
    <h3>${esc(t("my_requests"))}</h3><div id="mreq" class="muted">…</div>
    <h3>${esc(t("my_offers"))}</h3><div id="moff" class="muted">…</div>
    <p><button id="del" class="danger">${esc(t("delete_data"))}</button></p>`;
  $("#lo").onclick = () => sb.auth.signOut();
  $("#del").onclick = async () => {
    if (!confirm(t("delete_confirm"))) return;
    await sb.from("sell_requests").delete().eq("user_id", user.id);
    await sb.from("offers").delete().eq("user_id", user.id);
    alert(t("deleted")); loadMine();
  };
  loadMine();
}
const partsLabel = (c) => Object.values(c.parts || {}).filter(Boolean).map((id) => SNAP?.models[id]?.name || id).join(" · ");
async function loadMine() {
  if (!sb || !user || !$("#mreq")) return;
  const [r, o] = await Promise.all([
    sb.from("sell_requests").select("*").order("created_at", { ascending: false }),
    sb.from("offers").select("*").order("created_at", { ascending: false }),
  ]);
  $("#mreq").innerHTML = r.data?.length ? `<ul>${r.data.map((x) => `<li><b>${esc(t("st_" + x.status))}</b> · ${fmtDay(x.created_at)} · ${x.estimate_ron ? ron(x.estimate_ron) : ""} · ${esc(partsLabel(x.config))}${x.courier ? " · " + esc(x.courier) : ""}</li>`).join("")}</ul>` : esc(t("empty"));
  $("#moff").innerHTML = o.data?.length ? `<ul>${o.data.map((x) => `<li>${fmtDay(x.created_at)} · ${ron(x.estimate_ron)} · ${esc(partsLabel(x.config))}</li>`).join("")}</ul>` : esc(t("empty"));
}

// ---------- search ----------
function runSearch(onlyModel) {
  const q = $("#q").value.trim().toLowerCase();
  const out = $("#sres");
  if (!q && !onlyModel) { out.innerHTML = ""; return; }
  const toks = q.split(/\s+/).filter(Boolean);
  const hit = (s) => toks.every((k) => s.toLowerCase().includes(k));
  const groups = [];
  for (const [id, m] of Object.entries(SNAP.models)) {
    if (onlyModel && id !== onlyModel) continue;
    const ls = onlyModel || hit(m.name) ? m.listings : m.listings.filter((l) => hit(l.title));
    if (ls.length) groups.push({ id, m, ls });
  }
  if (!groups.length) { out.innerHTML = `<p>${esc(t("no_results"))}</p>`; return; }
  out.innerHTML = groups.slice(0, 12).map(({ m, ls }) => {
    const refFor = (l) => (l.condition === "new" ? m.new : m.used);
    const rows = ls.map((l) => {
      const ref = refFor(l);
      const pct = ref ? Math.round((1 - l.price / ref.median) * 100) : 0;
      const deal = ref && l.price <= ref.median * CFG.deal_threshold && l.price >= ref.median * 0.4;
      return `<tr class="${deal ? "deal" : ""}"><td class="num">${ron(l.price)}${deal ? `<br><span class="badge">${esc(t("deal", { p: pct }))}</span>` : ""}</td>
        <td><a href="${esc(l.url)}" target="_blank" rel="noopener nofollow">${esc(l.title)}</a>${l.city ? `<br><small>${esc(l.city)}</small>` : ""}</td>
        <td>${l.source === "olx" ? "OLX" : "evoMAG"}</td><td>${esc(t(l.condition === "new" ? "cond_new" : "cond_used"))}</td><td><small>${fmtDay(l.fetched)}</small></td></tr>`;
    }).join("");
    return `<section class="group"><h3>${esc(m.name)}</h3>
      <p>${esc(t("ref_used"))}: <b>${m.used ? ron(m.used.median) : "—"}</b> ${m.used ? `<small>(n=${m.used.n})</small>` : ""} · ${esc(t("ref_new"))}: <b>${m.new ? ron(m.new.median) : "—"}</b> ${m.new ? `<small>(n=${m.new.n})</small>` : ""}</p>
      <div class="scroll"><table><thead><tr><th>${esc(t("col_price"))}</th><th>${esc(t("col_title"))}</th><th>${esc(t("col_source"))}</th><th>${esc(t("col_cond"))}</th><th>${esc(t("col_date"))}</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }).join("");
}

function renderSources() {
  const s = SNAP.sources, p = SNAP.probes;
  const li = (name, ok, extra = "") => `<li><b>${esc(name)}</b>: ${ok}${extra}</li>`;
  $("#sources").innerHTML = `<ul>
    ${Object.values(s).map((v) => li(v.label, v.stale_since ? `⚠️ ${t("src_stale", { date: fmtDate(v.stale_since) })}` : v.ok ? `✅ ${t("src_ok")}` : `❌ ${t("src_blocked")}`, ` · ${v.items}`)).join("")}
    ${Object.entries(p).map(([k, v]) => li({ emag: "eMAG.ro", altex: "Altex.ro", flanco: "Flanco.ro", pcgarage: "PC Garage" }[k] || k, v.blocked ? `❌ ${t("src_blocked")} (HTTP ${v.http})` : `⚠️ ${t("src_reach")}`)).join("")}
  </ul><p class="muted">${esc(fmtDate(SNAP.generated))}</p>`;
}

// ---------- boot ----------
async function boot() {
  $("#lang").innerHTML = LANGS.map((l) => `<option value="${l}">${I18N[l].lang_name}</option>`).join("");
  $("#lang").onchange = (e) => { lang = e.target.value; localStorage.setItem("pcp_lang", lang); applyI18n(); };
  $$("nav [data-tab]").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  $("#sellform").onsubmit = onEstimate;
  $("#sform").onsubmit = (e) => { e.preventDefault(); runSearch(); };
  const tab = location.hash.slice(1);
  showTab(["sell", "search", "account", "about"].includes(tab) ? tab : "sell");
  [SNAP, CFG] = await Promise.all([fetch("data/snapshot.json").then((r) => r.json()), fetch("config.json").then((r) => r.json())]);
  const pc = window.PCP_CONFIG || {};
  if (pc.SUPABASE_URL && pc.SUPABASE_ANON_KEY && window.supabase) {
    sb = window.supabase.createClient(pc.SUPABASE_URL, pc.SUPABASE_ANON_KEY);
    user = (await sb.auth.getSession()).data.session?.user || null;
    sb.auth.onAuthStateChange((_e, session) => { user = session?.user || null; renderAccount(); });
  }
  applyI18n();
  const q = new URLSearchParams(location.search).get("q");
  if (q) { $("#q").value = q; showTab("search"); runSearch(); }
}
boot();
})();
