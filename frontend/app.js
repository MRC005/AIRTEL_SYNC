// Accel Business OneSitting - customer app (advisor -> quote -> KYC -> tracker) and sales view.
const $ = (s) => document.querySelector(s);
const state = { sid: null, rec: null, selected: {}, consentId: null, kyc: null, orderId: null, lang: "en", started: false };
const CONNECTIVITY = ["P01", "P02", "P03", "P04", "P05", "P06"];
const SPEECH_LANG = { en: "en-IN", hi: "hi-IN", ta: "ta-IN", kn: "kn-IN", mr: "mr-IN", bn: "bn-IN" };
const rupees = (n) => "₹" + Number(n).toLocaleString("en-IN");
// "per user" x 18 -> "18 users"; "per site" x 1 -> "1 site"
const units = (qty, unit) => { const u = unit.replace(/^per /, ""); return `${qty} ${qty === 1 ? u : u + "s"}`; };

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "Something went wrong");
  return body;
}
const postJSON = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

function show(view) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== view));
  const order = ["advisor", "quote", "kyc", "track"];
  document.querySelectorAll(".steps span").forEach((s) => {
    const i = order.indexOf(s.dataset.step), cur = order.indexOf(view);
    s.classList.toggle("on", i === cur);
    s.classList.toggle("done", cur > -1 && i < cur);
  });
  $(".steps").hidden = view === "backoffice";
  window.scrollTo(0, 0);
}

// ---------- 1. Advisor ----------
function bubble(text, who) {
  const b = document.createElement("div");
  b.className = `bubble ${who}`;
  b.textContent = text;
  $("#chat").appendChild(b);
  $("#chat").scrollTop = $("#chat").scrollHeight;
  return b;
}

function renderChips(chips, multi) {
  const box = $("#chips");
  box.innerHTML = "";
  const picked = new Set();
  chips.forEach((c) => {
    const btn = document.createElement("button");
    btn.textContent = c;
    btn.onclick = () => {
      if (!multi) return send(c);
      picked.has(c) ? picked.delete(c) : picked.add(c);
      btn.classList.toggle("on");
    };
    box.appendChild(btn);
  });
  if (multi) {
    const done = document.createElement("button");
    done.textContent = "Done ✓";
    done.onclick = () => picked.size && send([...picked].join(", "));
    box.appendChild(done);
  }
}

async function send(text) {
  if (text) bubble(text, "me");
  $("#msg").value = "";
  $("#chips").innerHTML = "";
  const typing = bubble("…", "bot typing");
  try {
    const r = await postJSON("/api/advisor/chat", { session_id: state.sid, message: text || "" });
    typing.remove();
    state.sid = r.session_id;
    bubble(r.reply, "bot");
    renderChips(r.quick_replies || [], r.multi);
    $("#mode").textContent = r.mode === "gemini" ? "AI advisor (Gemini) · replies in your language" : "Guided mode (AI key not set)";
    if (r.ready && r.recommendation) {
      state.rec = r.recommendation;
      setTimeout(() => { renderQuote(true); show("quote"); }, 900);
    }
  } catch (e) {
    typing.textContent = e.message;
  }
}

$("#composer").onsubmit = (e) => { e.preventDefault(); const t = $("#msg").value.trim(); if (t) send(t); };
$("#langs").onclick = (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  document.querySelectorAll("#langs button").forEach((x) => x.classList.toggle("on", x === b));
  state.lang = b.dataset.lang;
  send(b.dataset.hello);
};

// Voice input (Chrome / Android) - a stretch goal from the brief.
const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!Speech) $("#mic").hidden = true;
$("#mic").onclick = () => {
  const rec = new Speech();
  rec.lang = SPEECH_LANG[state.lang] || "en-IN";
  $("#mic").classList.add("live");
  rec.onresult = (e) => send(e.results[0][0].transcript);
  rec.onend = () => $("#mic").classList.remove("live");
  rec.start();
};

// ---------- 2. Quote ----------
function renderQuote(reset) {
  const r = state.rec;
  if (reset) {
    state.selected = {};
    r.items.forEach((i) => (state.selected[i.product_id] = { qty: i.qty, on: true }));
    r.add_ons.forEach((a) => (state.selected[a.product_id] = { qty: a.qty, on: false }));
  }
  $("#segName").textContent = `Recommended for your ${r.segment_name.toLowerCase()}`;
  $("#explain").textContent = r.explanation || "";
  $("#items").innerHTML = "";
  $("#addons").innerHTML = "";
  r.items.forEach((i) => $("#items").appendChild(itemRow(i, true)));
  r.add_ons.forEach((a) => $("#addons").appendChild(itemRow(a, false)));
  const ul = $("#notEligible ul");
  ul.innerHTML = "";
  (r.not_eligible || []).forEach((n) => { const li = document.createElement("li"); li.textContent = n.reason; ul.appendChild(li); });
  $("#notEligible").hidden = !(r.not_eligible || []).length;
  requote();
}

function itemRow(i, inBundle) {
  const sel = state.selected[i.product_id];
  const row = document.createElement("div");
  row.className = "item" + (sel.on ? "" : " off");
  const locked = CONNECTIVITY.includes(i.product_id);
  row.innerHTML = `
    <div><div class="name">${i.name}</div>
      <div class="qty"><button data-d="-1" aria-label="Fewer">−</button><span>${units(sel.qty, i.unit)}</span><button data-d="1" aria-label="More">+</button></div></div>
    <div class="amt">${rupees(i.unit_price * sel.qty)}<br>${locked ? '<small class="muted">core</small>' : '<input type="checkbox" class="toggle" aria-label="Include">'}</div>
    <div class="why">${i.reason}${i.setup ? ` · one-time setup ${rupees(i.setup / i.qty * sel.qty)}` : ""}</div>`;
  const tog = row.querySelector(".toggle");
  if (tog) {
    tog.checked = sel.on;
    tog.onchange = () => { sel.on = tog.checked; row.classList.toggle("off", !sel.on); requote(); };
  }
  row.querySelectorAll(".qty button").forEach((b) => (b.onclick = () => {
    sel.qty = Math.max(1, sel.qty + Number(b.dataset.d));
    row.querySelector(".qty span").textContent = units(sel.qty, i.unit);
    row.querySelector(".amt").firstChild.textContent = rupees(i.unit_price * sel.qty);
    requote();
  }));
  return row;
}

function selection() {
  return Object.entries(state.selected).filter(([, s]) => s.on).map(([product_id, s]) => ({ product_id, qty: s.qty }));
}

async function requote() {
  try {
    const q = await postJSON("/api/quote", { session_id: state.sid, selected: selection() });
    $("#total").textContent = q.monthly_total.toLocaleString("en-IN");
    $("#priceMeta").textContent = `${rupees(q.monthly_total_with_gst)} incl. GST · one-time setup ${rupees(q.setup_total)} · ${q.contract_months}-month plan · live in about ${q.activation_days} days`;
    $("#budget").hidden = true;
    $("#toKyc").disabled = false;
  } catch (e) {
    $("#budget").textContent = e.message;
    $("#budget").hidden = false;
    $("#toKyc").disabled = true;
  }
}

$("#toKyc").onclick = async () => {
  show("kyc");
  const n = await api("/api/consent/notice");
  $("#notice").innerHTML = `
    <dt>Why we need this</dt><dd>${n.purpose}</dd>
    <dt>What we collect</dt><dd>${n.data_collected.join(", ")}</dd>
    <dt>How it is used</dt><dd>${n.how_used}</dd>
    <dt>How long we keep it</dt><dd>${n.retention}</dd>
    <dt>Your rights</dt><dd>${n.your_rights} (${n.law})</dd>`;
};

// ---------- 3. Smart KYC ----------
$("#agree").onchange = () => ($("#giveConsent").disabled = !$("#agree").checked);
$("#giveConsent").onclick = async () => {
  const c = await postJSON("/api/consent", { session_id: state.sid, accepted: true });
  state.consentId = c.consent_id;
  $("#consentCard").hidden = true;
  $("#uploadCard").hidden = false;
};

const DECISION_TEXT = {
  APPROVED: ["Verified in seconds", "Your documents match the GST and Udyam registries. Installation can be booked now."],
  ACTION_NEEDED: ["One thing to fix", "Fix the items marked below and upload again. Your quote is saved."],
  MANUAL_REVIEW: ["Sent for a quick check", "A specialist will confirm within 4 working hours. You can still place the order."],
  REJECTED: ["GSTIN is not active", "We updated your bundle to products you can buy without an active GSTIN."],
};

$("#verify").onclick = async () => {
  const out = $("#kycResult");
  out.innerHTML = '<p class="muted">Reading documents and checking registries…</p>';
  const fd = new FormData();
  fd.append("session_id", state.sid);
  fd.append("consent_id", state.consentId);
  let path = "/api/kyc/verify";
  if ($("#sample").value) { fd.append("applicant", $("#sample").value); path = "/api/kyc/sample"; }
  else if ($("#files").files.length) [...$("#files").files].forEach((f) => fd.append("files", f));
  else { out.innerHTML = '<p class="warn">Choose your document photos or a sample applicant.</p>'; return; }
  try {
    const r = await api(path, { method: "POST", body: fd });
    state.kyc = r.decision;
    const [title, sub] = DECISION_TEXT[r.decision];
    const checks = r.checks.map((c) => `<li class="${c.status}"><b>${c.check}</b>${c.message}</li>`).join("");
    const g = r.extracted.gst_certificate?.fields || {};
    out.innerHTML = `
      <div class="decision ${r.decision}">${title}<small>${sub}</small></div>
      <ul class="checks">${checks}</ul>
      ${g.gstin ? `<p class="fields">Read from GST certificate: ${g.trade_name || ""} · GSTIN ${g.gstin} (masked)</p>` : ""}
      ${r.decision === "ACTION_NEEDED" ? "" : '<button class="primary" id="placeOrder">Place order</button>'}`;
    if (r.revised_recommendation) { state.rec = r.revised_recommendation; renderQuote(true); }
    $("#placeOrder")?.addEventListener("click", placeOrder);
  } catch (e) {
    out.innerHTML = `<p class="warn">${e.message}</p>`;
  }
};

// ---------- 4. Tracker ----------
async function placeOrder() {
  const o = await postJSON("/api/orders", { session_id: state.sid, selected: selection(), kyc_decision: state.kyc });
  state.orderId = o.order_id;
  renderOrder(o);
  show("track");
}

function renderOrder(o) {
  $("#orderId").textContent = o.order_id;
  $("#orderMeta").textContent = `${rupees(o.monthly_total)}/month · one bill · one support number`;
  $("#timeline").innerHTML = o.stages.map((s) =>
    `<li class="${s.done ? "done" : ""} ${s.current ? "current" : ""}"><span class="dot"></span><b>${s.stage}</b><small>${s.done ? "Done" : "Expected " + s.expected} · ${s.description}</small></li>`).join("");
  $("#orderItems").innerHTML = o.products.map((p) =>
    `<div class="item"><div class="name">${p.name} × ${p.qty}</div><div class="amt">${p.live ? "Live ✓" : "By " + p.live_by}</div></div>`).join("");
  const cur = o.stages.find((s) => s.current);
  $("#wa").textContent = cur
    ? `Hi! Your Accel order ${o.order_id}: next step "${cur.stage}" on ${cur.expected}. Reply HELP for support. No need to call.`
    : `All set! Your Accel services are live. One bill on the 1st of every month.`;
}
$("#advance").onclick = async () => renderOrder(await postJSON(`/api/orders/${state.orderId}/advance?days=1`, {}));

// ---------- Sales / partner view ----------
$("#toBackoffice").onclick = async () => {
  show("backoffice");
  const b = await api("/api/backoffice");
  $("#modelMeta").textContent = `Propensity model: AUC ${b.model.auc}. Calling the top 20% of leads reaches ${Math.round(b.model.top20_capture * 100)}% of all activations (${Math.round(b.model.top20_rate * 100)}% conversion vs ${Math.round(b.model.base_rate * 100)}% average).`;
  $("#callList tbody").innerHTML = b.call_list.map((l) =>
    `<tr><td class="score">${l.score}</td><td><b>${l.business_name}</b><br><small class="muted">${l.business_type}</small></td><td>${l.city} · ${l.preferred_language}</td><td>${l.lead_source}</td><td>${l.drop_reason}</td></tr>`).join("");
  $("#drivers").innerHTML = b.drivers.map((d) =>
    `<div class="driver"><span>${d.feature.replaceAll("_", " ")}</span><span class="${d.weight > 0 ? "up" : "down"}">${d.weight > 0 ? "▲" : "▼"} ${Math.abs(d.weight)}</span></div>`).join("");
  $("#unclosed").innerHTML = b.advisor_unclosed.length
    ? b.advisor_unclosed.map((u) => `<div class="item"><div class="name">${u.business_type || "Unknown business"} · ${u.city || "—"}</div><div class="amt">${u.status}</div><div class="why">Language: ${u.language}. Hand to the nearest channel partner for a call.</div></div>`).join("")
    : '<p class="muted">None right now.</p>';
};
$("#backToApp").onclick = () => show(state.orderId ? "track" : state.rec ? "quote" : "advisor");

send("");
