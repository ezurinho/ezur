/* BTC Quant — research registry dashboard (vanilla, no build step) */

const S = {
  data: null,
  results: null,
  error: null,
  filters: { corridor: "", verdict: "", q: "" },
  logFilter: "all",
};

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fnum = (v, d = 2) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: true }));
const fint = (v) => (v === null || v === undefined ? "—" : Math.round(Number(v)).toLocaleString("es-ES", { useGrouping: true }));
const fpct = (v, d = 1) => (v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(d).replace(".", ",")}%`);
const fsigned = (v, d = 2) => (v === null || v === undefined ? "—" : `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(d).replace(".", ",")}`);

const VERDICT_ES = { APPROVED: "APROBADO", INCONCLUSIVE: "INCONCLUSIVO", REJECTED: "RECHAZADO" };
const PORT = { donchian_breakout: "Donchian", ema_state: "EMA", zscore_fade: "Reversión", orb_session: "ORB" };
const VERDICT_TAG = { APPROVED: "Aprobada", INCONCLUSIVE: "Inconclusa", REJECTED: "Rechazada" };

const GATE_LABEL = {
  pf_net: "PF neto", pf_ci_low: "IC95% PF (inferior)", t_stat: "t-stat", trades: "Trades",
  cost_stress_2x: "Coste 2×", mdd_budget: "MDD vs presupuesto", funding: "Funding",
  pbo: "PBO", dsr: "DSR", minbtl: "MinBTL", wfa: "Trades por fold",
  benchmark_alpha: "Alpha vs B&H", plateau: "Plateau ±20%",
};
const OP_DEFAULT = { pbo: "≤", dsr: "≥", minbtl: "≤", wfa: "≥", mdd_budget: "≥", trades: "≥", t_stat: "≥", pf_net: ">", pf_ci_low: ">", cost_stress_2x: ">" };

const PAGE = {
  resumen: ["Resumen", "Estado del ciclo, veredictos y huecos del pipeline"],
  estrategias: ["Estrategias", "Hipótesis, reglas y versiones registradas"],
  corridas: ["Corridas", "Registro append-only de backtests con sus puertas"],
  runner: ["Runner", "Artefactos deterministas: spec → result.json, sin números inventados"],
  log: ["Eventos", "Log auditable: se anexa, no se edita"],
  proyecto: ["Proyecto", "Dataset, artefactos y contrato de la API"],
};

/* ------------------------------------------------------------------ helpers */
function strategyOf(id) { return (S.data?.strategies || []).find((s) => s.id === id); }
function cycleOf(id) { return (S.data?.cycles || []).find((c) => c.id === id); }
function runsOf(sid) { return (S.data?.runs || []).filter((r) => r.strategy_id === sid); }
function bestRun(sid) { return runsOf(sid).slice().sort((a, b) => b.metrics.pf_net - a.metrics.pf_net)[0]; }

function counts() {
  const c = { APPROVED: 0, INCONCLUSIVE: 0, REJECTED: 0 };
  (S.data?.runs || []).forEach((r) => { c[r.verdict] = (c[r.verdict] || 0) + 1; });
  return c;
}

function verdictOfStrategy(sid) {
  const rs = runsOf(sid);
  if (!rs.length) return "INCONCLUSIVE";
  if (rs.some((r) => r.verdict === "APPROVED")) return "APPROVED";
  if (rs.every((r) => r.verdict === "REJECTED")) return "REJECTED";
  return "INCONCLUSIVE";
}

function vtag(v) {
  return `<span class="vtag ${esc(v)}"><span class="dot"></span>${esc(VERDICT_TAG[v] || v)}</span>`;
}
function fileTag(ok) {
  return `<span class="vtag ${ok ? "APPROVED" : "REJECTED"}"><span class="dot"></span>${ok ? "Verificado" : "Falta"}</span>`;
}
function pill(v) {
  return `<span class="pill ${esc(v)}"><span class="dot"></span>${esc(VERDICT_ES[v] || v)}</span>`;
}

function gateFormat(key, g) {
  const isPct = key === "mdd_budget" || key === "benchmark_alpha";
  const isInt = key === "trades" || key === "wfa";
  const isYears = key === "minbtl";
  const fmt = (v) => (isPct ? `${v < 0 ? "−" : ""}${fpct(Math.abs(v))}` : isInt ? fint(v) : isYears ? `${fnum(v, 1)} años` : fnum(v, 2));
  if (typeof g.value !== "number") {
    const THRESH = { required: "oblig.", "±20%": "±20%" };
    const VAL = {
      included: "Incluido", excluded: "Ausente", pending: "Pendiente",
      "n/a (intradía)": "no aplica", "n/a (intraday)": "no aplica",
      "plano": "plano", "pico aislado": "pico aislado",
    };
    const known = VAL[String(g.value)];
    const val = known || esc(g.value);
    const lim = THRESH[String(g.threshold)] || (known ? "oblig." : esc(g.threshold));
    return { val, lim };
  }
  const op = g.op === ">=" ? "≥" : g.op === ">" ? ">" : g.op === "≤" ? "≤" : (OP_DEFAULT[key] || "=");
  const limVal = key === "mdd_budget" ? `−${fpct(Math.abs(g.threshold))}` : fmt(g.threshold);
  return { val: fmt(g.value), lim: `${op} ${limVal}` };
}

function gateRow(key, g) {
  if (!g) return "";
  const { val, lim } = gateFormat(key, g);
  const state = g.pass ? "pass" : "fail";
  return `<div class="gate ${state}">
    <span class="name">${esc(GATE_LABEL[key] || key)}</span>
    <span class="val">${val}</span>
    <span class="lim">${lim}</span>
    <span class="mark" aria-label="${g.pass ? "pasa" : "falla"}"></span>
  </div>`;
}

function gatesBlock(gates, keys) {
  if (!gates) return `<div class="empty">Sin puertas registradas</div>`;
  const k = keys || Object.keys(gates);
  return `<div class="gates">
    <div class="gate head"><span class="name">Puerta</span><span class="val">Valor</span><span class="lim">Umbral</span><span></span></div>
    ${k.map((key) => gateRow(key, gates[key])).join("")}
  </div>`;
}

function failPhrase(key, g) {
  const v = fnum(g.value, 2);
  const t = fnum(g.threshold, 2);
  if (key === "pbo") return `PBO ${v} > ${t}`;
  if (key === "dsr") return `DSR ${v} < ${t}`;
  if (key === "minbtl") return `MinBTL ${fnum(g.value, 2)} años > ${fnum(g.threshold, 2)} disponibles`;
  if (key === "wfa") return `${fnum(g.value, 1)} trades por fold < ${fint(g.threshold)}`;
  return `${GATE_LABEL[key] || key} ${v}`;
}

/* ------------------------------------------------------------------- chart */
let chartSeq = 0;
function niceStep(span, target = 4) {
  if (!(span > 0)) return 1;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return mult * mag;
}

function equityChart(vals, color, label) {
  if (!vals || vals.length < 2) return `<div class="empty">Sin serie de capital</div>`;
  const gid = `grad${++chartSeq}`;
  const narrow = window.innerWidth < 760;
  const W = narrow ? 380 : 720, H = narrow ? 168 : 220;
  const m = narrow ? { l: 42, r: 12, t: 12, b: 26 } : { l: 48, r: 16, t: 14, b: 24 };
  const fs = narrow ? 11.5 : 9.5;
  const min = Math.min(...vals), max = Math.max(...vals);
  const logScale = min > 0 && max / min > 6;
  const tf = (v) => (logScale ? Math.log10(v) : v);
  const inv = (v) => (logScale ? 10 ** v : v);
  const lo0 = logScale ? min : min - (max - min) * 0.15;
  const hi0 = logScale ? max : max + (max - min) * 0.1;
  const lo = logScale ? tf(lo0) : lo0, hi = logScale ? tf(hi0) : hi0;
  const pad = (hi - lo) * 0.06 || 0.01;
  const y = (v) => H - m.b - ((tf(v) - lo + pad) / (hi - lo + 2 * pad)) * (H - m.t - m.b);
  const x = (i) => m.l + (i / (vals.length - 1)) * (W - m.l - m.r);
  const span = inv(hi + pad) - inv(lo - pad);
  const step = niceStep(span, 5);
  const ticks = [];
  for (let t = Math.ceil(inv(lo - pad) / step) * step; t <= inv(hi + pad) + 1e-9 && ticks.length < 7; t += step) ticks.push(t);

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label || "curva de capital")}" preserveAspectRatio="none">
  <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="${color}" stop-opacity=".26"/>
    <stop offset="72%" stop-color="${color}" stop-opacity=".06"/>
    <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
  </linearGradient></defs>`;
  ticks.forEach((t) => {
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}" stroke="var(--line-2)" stroke-width="1" stroke-dasharray="2 4" vector-effect="non-scaling-stroke"/>`;
    svg += `<text x="${m.l - 6}" y="${(y(t) + 3).toFixed(1)}" text-anchor="end" font-size="${fs}" fill="var(--faint)" font-family="Cascadia Mono, Consolas, monospace">${fnum(t, step < 0.01 ? 3 : 2)}×</text>`;
  });
  if (lo - pad <= 1 && hi + pad >= 1) {
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(1).toFixed(1)}" y2="${y(1).toFixed(1)}" stroke="var(--faint)" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke" opacity=".7"/>`;
  }
  for (let i = 0; i < vals.length; i += 12) {
    svg += `<text x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="middle" font-size="${fs}" fill="var(--faint)" font-family="Cascadia Mono, Consolas, monospace">${2020 + Math.floor(i / 12)}</text>`;
  }
  const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  svg += `<path d="${d}L${x(vals.length - 1).toFixed(1)},${H - m.b}L${x(0).toFixed(1)},${H - m.b}Z" fill="url(#${gid})" stroke="none"/>`;
  svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
  svg += `<circle cx="${x(vals.length - 1).toFixed(1)}" cy="${y(vals[vals.length - 1]).toFixed(1)}" r="6" fill="${color}" opacity=".16"/>`;
  svg += `<circle cx="${x(vals.length - 1).toFixed(1)}" cy="${y(vals[vals.length - 1]).toFixed(1)}" r="2.6" fill="${color}"/>`;
  svg += `</svg>`;
  return `<div class="chart">${svg}</div>`;
}

/* -------------------------------------------------------------------- views */
function viewResumen() {
  const d = S.data;
  const c = counts();
  const cycle = d.cycles[0] || {};
  const gates = Object.entries(cycle.gates || {});
  const failing = gates.filter(([, g]) => g.pass === false);
  const rows = d.runs.slice(0, 6);
  const fams = [...new Set(d.strategies.map((s) => s.family))];
  const cycleName = cycle.name && !/^ciclo/i.test(cycle.name) ? ` · ${cycle.name}` : "";

  const why = !gates.length
    ? "Sin puertas registradas para este ciclo."
    : !failing.length
      ? `Las ${gates.length} puertas del ciclo pasan.`
      : failing.length === gates.length
        ? `Ninguna de las ${gates.length} puertas del ciclo pasa.`
        : `${failing.length} de ${gates.length} puertas fallan: ${failing.map(([k]) => GATE_LABEL[k] || k).join(", ")}.`;
  const whyNote = failing.length && cycle.wfa_total_trades
    ? `Walk-forward: ${cycle.wfa_total_trades} trades OOS en ${cycle.wfa_folds} folds. Sin potencia estadística.`
    : "";

  const famRow = (fam) => {
    const sts = d.strategies.filter((s) => s.family === fam);
    const rs = d.runs.filter((r) => sts.some((s) => s.id === r.strategy_id));
    const best = rs.slice().sort((a, b) => b.metrics.pf_net - a.metrics.pf_net)[0];
    const tfs = [...new Set(sts.map((s) => s.timeframe))].join("/");
    return `<tr class="click" data-strategy="${esc(sts[0]?.id || "")}">
      <td><span class="strong">${esc(fam)}</span></td>
      <td class="tf mono faint">${esc(tfs)}</td>
      <td class="num">${rs.length}</td>
      <td class="num">${fnum(best?.metrics.pf_net, 3)}</td>
      <td>${vtag(best ? best.verdict : "INCONCLUSIVE")}</td>
    </tr>`;
  };

  return `
  <section class="band ${esc(cycle.verdict || "INCONCLUSIVE")}">
    <div class="band-main">
      <div class="kicker">Ciclo <b>${esc(cycle.id || "—")}</b>${esc(cycleName)}</div>
      <div class="state"><span class="dot"></span>${esc(VERDICT_ES[cycle.verdict] || "SIN CICLO")}</div>
      <p class="why">${why}${whyNote ? `<span class="why-note">${esc(whyNote)}</span>` : ""}</p>
    </div>
    <dl class="band-stats">
      <div><dt class="k">Corridas</dt><dd class="v">${fint(d.runs.length)}</dd><dd class="n">${d.strategies.length} estrategias</dd></div>
      <div><dt class="k">Aprobadas</dt><dd class="v ${c.APPROVED ? "ok" : ""}">${fint(c.APPROVED)}</dd><dd class="n">de ${d.runs.length}</dd></div>
      <div><dt class="k">Inconclusas</dt><dd class="v mid">${fint(c.INCONCLUSIVE)}</dd><dd class="n">sin potencia</dd></div>
      <div><dt class="k">Rechazadas</dt><dd class="v bad">${fint(c.REJECTED)}</dd><dd class="n">PF, coste o MDD</dd></div>
    </dl>
  </section>

  <div class="duo even fit" style="margin-top:14px">
    <section class="card">
      <header><h3>Puertas del ciclo</h3><span class="meta">PROMPT_V4 §6</span></header>
      <div class="chips-gates">${gates.map(([k, g]) => gateChip(k, g)).join("")}</div>
      <p class="foot-note">Las calcula el runner sobre el histórico; el modelo solo puede citarlas.</p>
    </section>
    <section class="card">
      <header><h3>Validación</h3><span class="meta">${pipelineCount().done} de ${pipelineSteps().length} pasos</span></header>
      ${pipelineBar()}
    </section>
  </div>

  <div class="section"><h2>Familias probadas</h2><span class="meta">${fint(d.project?.dataset?.rows)} barras 5m</span></div>
  <div class="card table-wrap">
    <table class="table">
      <thead><tr><th>Familia</th><th class="tf">TF</th><th class="num">Corridas</th><th class="num">Mejor PF</th><th>Veredicto</th></tr></thead>
      <tbody>${fams.map(famRow).join("")}</tbody>
    </table>
  </div>

  <div class="section"><h2>Últimas corridas</h2><a href="#/corridas" class="meta">Ver todas</a></div>
  <div class="card table-wrap">
    <table class="table">
      <thead><tr><th>Corrida</th><th class="num">Trades</th><th class="num">PF neto</th><th class="num">t-stat</th><th>Veredicto</th></tr></thead>
      <tbody>${rows.map(runRow).join("")}</tbody>
    </table>
  </div>`;
}

/* Gates as compact chips: one line instead of a table header plus four rows. */
function gateChip(key, g) {
  const { val, lim } = gateFormat(key, g);
  return `<span class="gchip ${g.pass ? "pass" : "fail"}" title="${esc(GATE_LABEL[key] || key)}: ${g.pass ? "pasa" : "falla"}">
    <i></i><b>${esc(GATE_LABEL[key] || key)}</b><span class="num">${val}</span><em>${lim}</em>
  </span>`;
}

/* Validation pipeline as twelve segments instead of twelve rows. */
function pipelineSteps() {
  const d = S.data;
  const cyc = d.cycles[0] || {};
  const gaps = d.project?.dataset?.gaps;
  const wfaOk = (cyc.wfa_min_trades || 0) >= 30;
  const results = S.results?.results || [];
  const r0 = results.slice().sort((a, b) => (b.metrics?.all?.pf_net || 0) - (a.metrics?.all?.pf_net || 0))[0] || {};
  const val = S.results?.validation || {};
  const ver = S.results?.verification || {};
  const plateau = r0.robustness?.perturbation;
  const reg = r0.robustness?.regimes;
  const bench = r0.benchmark || {};
  const hasBootstrap = !!r0.metrics?.all?.pf_ci95;
  const benchOk = bench.alpha_annual != null && bench.ci95 && bench.ci95[0] > 0;
  return [
    ["SPEC", `${results.length} specs contra schema`, results.length ? "done" : "missing"],
    ["DATOS", gaps === 0 ? "integridad verificada" : `${fint(gaps)} gaps`, gaps === 0 ? "done" : "fail"],
    ["COSTE", "fees + spread + funding en R", "done"],
    ["BACKTEST", ver && !ver.failures ? `${d.runs.length} corridas · ${ver.checked}/${ver.checked} reproducen`
      : `${d.runs.length} corridas`, "done"],
    ["PBO", `${fnum(cyc.pbo, 3)} vs 0,20`, cyc.pbo <= 0.2 ? "done" : "fail"],
    ["DSR", `${fnum(cyc.dsr, 3)} vs 0,95`, cyc.dsr >= 0.95 ? "done" : "fail"],
    ["ROBUSTEZ", plateau ? "plateau ±10% / ±20%" : "sin artefacto de perturbación",
     plateau ? (plateau.pass ? "done" : "fail") : "missing"],
    ["MONTE CARLO", hasBootstrap ? "bootstrap por bloques del PF" : "bootstrap estacionario pendiente",
     hasBootstrap ? "done" : "missing"],
    ["REGÍMENES", reg ? (reg.concentrated ? "edge solo en algunos tramos" : "edge en todos los tramos")
      : "sin segmentación registrada",
     reg ? (reg.concentrated ? "fail" : "done") : "missing"],
    ["WFA", `${cyc.wfa_folds || 0} folds · ${cyc.wfa_total_trades || 0} trades OOS`,
     wfaOk ? "done" : (cyc.wfa_folds ? "fail" : "missing")],
    ["BENCHMARK", bench.alpha_annual == null ? "alpha vs BTC pendiente"
      : `alpha ${fsigned(bench.alpha_annual * 100, 1)}% vs BTC`,
     bench.alpha_annual == null ? "missing" : (benchOk ? "done" : "fail")],
    ["DRY-RUN", results.length ? "spec validada y coste admitido" : "no iniciado",
     results.length ? "done" : "missing"],
  ];
}

function pipelineCount() {
  const n = { done: 0, fail: 0, partial: 0, missing: 0 };
  pipelineSteps().forEach(([, , st]) => n[st]++);
  return n;
}

function pipelineBar() {
  const steps = pipelineSteps();
  const n = pipelineCount();
  const pending = steps.filter(([, , st]) => st === "missing").map(([name]) => name);
  return `
  <div class="segments" role="img" aria-label="${n.done} de ${steps.length} pasos hechos, ${n.fail} fallan, ${n.missing} pendientes">
    ${steps.map(([name, note, st]) => `<span class="seg ${st}" title="${esc(name)} · ${esc(note)}"></span>`).join("")}
  </div>
  <div class="seg-legend">
    <span class="ok"><i></i>${n.done} hechos</span>
    ${n.fail ? `<span class="bad"><i></i>${n.fail} fallan</span>` : ""}
    ${n.partial ? `<span class="mid"><i></i>${n.partial} parcial</span>` : ""}
    ${n.missing ? `<span class="none"><i></i>${n.missing} pendientes</span>` : ""}
  </div>
  <p class="foot-note">${pending.length ? `Faltan: ${pending.join(", ")}.` : "Pipeline completo."}</p>`;
}

function runRow(r) {
  const m = r.metrics || {};
  return `<tr class="click" data-run="${esc(r.id)}">
    <td class="id"><span class="row-link">${esc(r.label)}</span><div class="sub">${esc(r.strategy_id)}<span class="sub-tf"> · ${esc(r.params?.bar || "")}</span></div></td>
    <td class="num">${fint(m.n)}</td>
    <td class="num">${fnum(m.pf_net, 3)}</td>
    <td class="num">${fsigned(m.t_stat, 2)}</td>
    <td>${vtag(r.verdict)}</td>
  </tr>`;
}

function viewEstrategias() {
  const rows = S.data.strategies.map((s) => {
    const rs = runsOf(s.id);
    const b = bestRun(s.id);
    return `<tr class="click" data-strategy="${esc(s.id)}">
      <td><span class="row-link strong">${esc(s.name)}</span><div class="sub">${esc(s.id)} · ${rs.length} corridas</div></td>
      <td><span class="chip">${esc(s.family)}</span> <span class="chip strong">${esc(s.timeframe)}</span></td>
      <td class="num">${fnum(b?.metrics.pf_net, 3)}</td>
      <td>${vtag(verdictOfStrategy(s.id))}</td>
    </tr>`;
  }).join("");
  return `<div class="card table-wrap"><table class="table">
    <thead><tr><th>Estrategia</th><th>Clase</th><th class="num">Mejor PF</th><th>Veredicto</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function viewEstrategia(id) {
  const s = strategyOf(id);
  if (!s) return `<div class="empty">Estrategia no registrada</div>`;
  const rs = runsOf(id);
  return `
  <div class="detail-head">
    <div><h2>${esc(s.name)}</h2><div class="meta">${esc(s.id)} · creada ${esc((s.created_at || "").slice(0, 10))}</div></div>
    <div>${pill(verdictOfStrategy(id))}</div>
  </div>
  <div class="duo even" style="margin-top:16px">
    <section class="card prose">
      <div class="k">Hipótesis económica</div><p>${esc(s.hypothesis)}</p>
      <div class="k">Reglas</div><p>${esc(s.rules)}</p>
    </section>
    <section class="card prose">
      <div class="k">Riesgos residuales</div><p>${esc(s.risks)}</p>
      <div class="k">Versiones registradas</div><p class="muted">${esc(verdictSummary(rs))}</p>
    </section>
  </div>
  <div class="section"><h2>Corridas de esta estrategia</h2><span class="meta">${rs.length}</span></div>
  <div class="card table-wrap"><table class="table">
    <thead><tr><th>Corrida</th><th class="tf">TF</th><th class="num">Trades</th><th class="num">PF neto · IC95%</th><th class="num tstat">t-stat</th><th>Veredicto</th></tr></thead>
    <tbody>${rs.map((r) => `<tr class="click" data-run="${esc(r.id)}">
      <td class="id"><span class="row-link">${esc(r.label)}</span></td><td class="mono faint tf">${esc(r.params.bar)}</td>
      <td class="num">${fint(r.metrics.n)}</td>
      <td class="num">${fnum(r.metrics.pf_net, 3)}<div class="sub">${fnum(r.metrics.pf_ci95[0], 2)} – ${fnum(r.metrics.pf_ci95[1], 2)}</div></td>
      <td class="num tstat">${fsigned(r.metrics.t_stat, 2)}</td><td>${vtag(r.verdict)}</td></tr>`).join("")}</tbody>
  </table></div>`;
}

function viewCorridas() {
  const f = S.filters;
  let rs = S.data.runs.slice();
  if (f.corridor) rs = rs.filter((r) => r.strategy_id === f.corridor);
  if (f.verdict) rs = rs.filter((r) => r.verdict === f.verdict);
  if (f.q) {
    const q = f.q.toLowerCase();
    rs = rs.filter((r) => `${r.id} ${r.label} ${r.strategy_id}`.toLowerCase().includes(q));
  }
  const opts = S.data.strategies.map((s) => `<option value="${esc(s.id)}" ${f.corridor === s.id ? "selected" : ""}>${esc(s.id)}</option>`).join("");
  const rows = rs.map((r) => {
    const m = r.metrics;
    return `<tr class="click" data-run="${esc(r.id)}">
      <td class="id"><span class="row-link">${esc(r.label)}</span><div class="sub">${esc(r.strategy_id)} · ${esc(r.params.bar)} · N=${esc(r.params.N ?? r.params.fast ?? r.params.range_bars ?? "—")}</div></td>
      <td class="num">${fnum(m.pf_net, 3)}<div class="sub">${fnum(m.pf_ci95[0], 2)} – ${fnum(m.pf_ci95[1], 2)}</div></td>
      <td class="num">${fsigned(m.t_stat, 2)}</td>
      <td class="num">${fpct(m.mdd)}</td>
      <td>${vtag(r.verdict)}</td>
    </tr>`;
  }).join("");
  return `
  <div class="toolbar">
    <select id="f-strategy" aria-label="Estrategia"><option value="">Todas las estrategias</option>${opts}</select>
    <select id="f-verdict" aria-label="Veredicto">
      <option value="">Todos los veredictos</option>
      ${["APPROVED", "INCONCLUSIVE", "REJECTED"].map((v) => `<option value="${v}" ${f.verdict === v ? "selected" : ""}>${VERDICT_TAG[v]}</option>`).join("")}
    </select>
    <input type="text" id="f-q" placeholder="Buscar" value="${esc(f.q)}" aria-label="Buscar">
    <span class="count">${rs.length} de ${S.data.runs.length}</span>
  </div>
  <div class="card table-wrap"><table class="table">
    <thead><tr><th>Corrida</th><th class="num">PF neto · IC95%</th><th class="num">t-stat</th><th class="num">MDD</th><th>Veredicto</th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5" class="empty">Sin corridas con ese filtro</td></tr>`}</tbody>
  </table></div>`;
}

function viewCorrida(id) {
  const r = S.data.runs.find((x) => x.id === id);
  if (!r) return `<div class="card empty-card">
    <p class="k">Corrida no registrada</p>
    <p class="muted">No existe ninguna corrida con id <b class="mono">${esc(id)}</b> en este registro.</p>
    <p><a class="btn small" href="#/corridas">Ver todas las corridas</a></p>
  </div>`;
  const s = strategyOf(r.strategy_id);
  const cyc = cycleOf(r.cycle_id);
  // The registry row is the source of truth; the runner artefact fills in metrics
  // the row does not carry (time_in_market arrived after the row was written).
  const art = (S.results?.results || []).find(
    (a) => a.spec_id === r.strategy_id && a.version === r.version);
  const m = { ...(art?.metrics?.all || {}), ...r.metrics };
  const extras = [
    ["Sharpe", fnum(m.sharpe, 2)],
    ["Aciertos", fpct(m.win)],
    ["Años", fnum(m.years, 2)],
    // Exposición: qué fracción del tiempo el libro estuvo dentro. Un PF alto con
    // 5% de exposición deja el capital ocioso, y sin este dato no se ve.
    ["Tiempo invertido", m.time_in_market == null ? "—" : fpct(m.time_in_market)],
    ["Trades por año", fnum(m.trades_per_year, 1)],
    ["R por año", `${fsigned(m.r_per_year, 2)} R`],
    ["Stop mediano", fpct(m.stop_frac_median, 2)],
    ["Expectativa", `${fsigned(m.exp_net_r, 3)} R`],
    ["Con coste 2×", `${fsigned(m.exp_stress_r, 3)} R`],
  ].filter(([, v]) => v != null && v !== "—" && !/NaN|undefined/.test(v));
  return `
  <div class="detail-head">
    <div><h2>${esc(r.label)}</h2><div class="meta">${esc(r.id)} · v${esc(r.version)} · ${esc((r.created_at || "").replace("T", " ").replace("Z", " UTC"))}</div></div>
    <div>${pill(r.verdict)}</div>
  </div>
  <div class="detail-tools">
    <a class="btn small ghost" href="#/estrategias/${esc(r.strategy_id)}">← ${esc(s?.name || r.strategy_id)}</a>
    <a class="btn small ghost" href="#/corridas">Todas las corridas</a>
    <span class="spacer"></span>
    <span class="chip">${esc(r.params.bar)}</span>
    <span class="chip">${esc(s?.family || "")}</span>
  </div>

  <section class="card">
    <header><h3>Resultado</h3><span class="meta">${esc(r.params.bar)} · ${fnum(r.costs?.rt_bps, 2)} pb RT</span></header>
    ${gatesBlock(r.gates, ["pf_net", "pf_ci_low", "t_stat", "trades", "cost_stress_2x", "mdd_budget", "funding"])}
    <div class="extras">
      ${extras.map(([k, v]) => `<span><b>${esc(k)}</b> ${esc(v)}</span>`).join("")}
    </div>
    <p class="foot-note">Ciclo <b class="mono">${esc(r.cycle_id)}</b>: PBO ${fnum(cyc?.pbo, 2)} · DSR ${fnum(cyc?.dsr, 2)} · ${cyc?.verdict === "REJECTED" ? "aprobación bloqueada" : "ciclo válido"}.</p>
  </section>

  <div class="section"><h2>Curva de capital</h2><span class="meta">mensual · riesgo 0,5% por trade</span></div>
  <section class="card">
    ${equityChart(r.equity, "var(--c1)", r.id)}
    <div class="chart-legend">
      <span><i style="background:var(--c1)"></i>capital (×)</span>
      <span>Funding ${m.funding_r ? `${fnum(m.funding_r, 3)} R/trade` : "no incluido"}</span>
    </div>
  </section>

  <details class="fold">
    <summary>Parámetros, costes y artefactos</summary>
    <div class="trio">
      <section><h4>Parámetros</h4><pre class="code">${esc(JSON.stringify(r.params, null, 2))}</pre></section>
      <section><h4>Costes</h4><pre class="code">${esc(JSON.stringify(r.costs, null, 2))}</pre></section>
      <section><h4>Artefactos</h4><pre class="code">${esc(JSON.stringify(r.artifacts, null, 2))}</pre></section>
    </div>
    ${r.notes ? `<p class="hint">${esc(r.notes)}</p>` : ""}
  </details>`;
}

function viewLog() {
  const f = S.logFilter;
  const ev = S.data.events.filter((e) => f === "all" || e.type === f);
  const types = ["all", ...new Set(S.data.events.map((e) => e.type))];
  return `
  <div class="toolbar">
    ${types.map((t) => `<button class="btn small ghost ${f === t ? "on" : ""}" data-log="${esc(t)}">${t === "all" ? "Todo" : esc(t)}</button>`).join("")}
    <span class="count">${ev.length} eventos</span>
  </div>
  <div class="card">
    ${ev.length ? ev.map((e, i) => {
      const stamp = String(e.ts).replace("T", " ").replace("Z", "");
      const day = stamp.slice(0, 10), clock = stamp.slice(11);
      const prev = i ? String(ev[i - 1].ts).replace("T", " ").replace("Z", "").slice(0, 10) : null;
      const when = day === prev ? esc(clock.slice(0, 5)) : esc(stamp);
      return `<div class="logrow${e.run_id ? " link" : ""}"${e.run_id ? ` data-run="${esc(e.run_id)}" role="link" tabindex="0"` : ""}>
      <div class="ts${day === prev ? " hms" : ""}">${when}</div>
      <div class="actor">${esc(e.actor)}</div>
      <div class="msg${e.message.length > 160 ? " clamp" : ""}"${e.message.length > 160 ? ` title="${esc(e.message)}"` : ""}>${esc(e.message)}</div>
    </div>`;
    }).join("") : `<div class="empty">Sin eventos</div>`}
  </div>`;
}

function viewProyecto() {
  const p = S.data.project || {};
  const ds = p.dataset || {};
  const files = S.data.files || [];
  return `
  <div class="duo even fit">
    <section class="card">
      <header><h3>Dataset</h3><span class="mono faint" style="font-size:11px">${esc(ds.instrument)}</span></header>
      <div class="stack">
        <div><div class="k">Fuente</div><div class="v">${esc(ds.source)}</div></div>
        <div><div class="k">Cobertura</div><div class="v">${esc((ds.start || "").slice(0, 10))} → ${esc((ds.end || "").slice(0, 10))} · ${fint(ds.rows)} barras 5m</div></div>
        <div><div class="k">Integridad</div><div class="v">${fint(ds.gaps)} gaps · ${fint(ds.duplicates)} duplicados · ${fint(ds.funding_events)} eventos de funding</div></div>
        <div><div class="k">Hash normalizado</div><div class="v hash" title="${esc(ds.sha256 || "")}">${esc(ds.sha256 || "—")}</div></div>
      </div>
    </section>
    <section class="card">
      <header><h3>Gobernanza</h3><span class="mono faint" style="font-size:11px">v${esc(p.engine_version)}</span></header>
      <div class="grid-specs">
        <div><div class="k">Riesgo por trade</div><div class="v">${fpct(p.risk_per_trade, 2)}</div></div>
        <div><div class="k">MDD máximo</div><div class="v">${fpct(p.budget?.max_mdd, 0)}</div></div>
        <div><div class="k">Vol objetivo</div><div class="v">${fpct(p.budget?.target_vol_annual, 0)} anual</div></div>
        <div><div class="k">Money management</div><div class="v">${esc(p.pm)}</div></div>
      </div>
      <p class="hint foot">Las corridas se insertan con id único y nunca se actualizan. Los eventos solo se anexan. El veredicto final es humano.</p>
    </section>
  </div>

  <div class="section"><h2>Artefactos del proyecto</h2><span class="meta">${files.filter((f) => f.exists).length}/${files.length} verificados</span></div>
  <div class="card table-wrap"><table class="table files">
    <thead><tr><th>Ruta</th><th class="num bytes">Bytes</th><th>Modificado</th><th>Estado</th></tr></thead>
    <tbody>${files.map((f) => `<tr>
      <td class="id"><span class="fname" title="${esc(f.path)}">${esc(f.path)}</span><div class="sub mono" title="${esc(f.sha256 || "")}">${esc(f.sha256 || "—")}</div></td>
      <td class="num bytes">${f.exists ? fint(f.bytes) : "—"}</td>
      <td class="mono faint">${esc(f.mtime || "—")}</td>
      <td>${fileTag(f.exists)}</td>
    </tr>`).join("")}</tbody>
  </table></div>

  <details class="fold">
    <summary>Contrato para el runner · POST /api/runs</summary>
    <pre class="code">curl -X POST http://127.0.0.1:8787/api/runs -H "Content-Type: application/json" -d @run.json

{
  "strategy_id": "BTC-ORB-5M",
  "label": "orb_45min",
  "version": "1.0.1",
  "cycle_id": "CYCLE-2026-11",
  "params": { "bar": "5m", "range_bars": 9 },
  "costs": { "rt_bps": 10.14, "funding": false, "cost_r": 0.2 },
  "metrics": {
    "n": 4200, "pf_net": 0.71, "pf_stress": 0.49,
    "pf_ci95": [0.66, 0.76], "t_stat": -2.1, "mdd": -0.62,
    "sharpe": -1.2, "win": 0.36, "exp_net_r": -0.22
  },
  "artifacts": { "data_hash": "…", "seed": 7 }
}</pre>
    <p class="hint">El servidor recalcula las puertas y el veredicto: si el ciclo falla PBO/DSR, ninguna corrida puede quedar APROBADA. Duplicar un id devuelve 409: el registro es append-only.</p>
  </details>`;
}

function verdictSummary(rs) {
  const c = rs.reduce((a, r) => ({ ...a, [r.verdict]: (a[r.verdict] || 0) + 1 }), {});
  return ["APPROVED", "INCONCLUSIVE", "REJECTED"].filter((v) => c[v]).map((v) => `${c[v]} ${VERDICT_TAG[v].toLowerCase()}`).join(" · ") || "sin corridas";
}

/* -------------------------------------------------------------------- modal */
let modalOpener = null;

function modal(html) {
  modalOpener = document.activeElement;
  $("#modal-root").innerHTML = `<div class="modal-bg"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <button class="modal-x" id="modal-x" type="button" aria-label="Cerrar">×</button>${html}</div></div>`;
  $("#modal-root").querySelector(".modal-bg").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-bg")) closeModal();
  });
  $("#modal-x").onclick = closeModal;
  document.addEventListener("keydown", escClose);
}
function escClose(e) {
  if (e.key === "Escape") { e.preventDefault(); closeModal(); return; }
  if (e.key !== "Tab") return;
  const box = $("#modal-root").querySelector(".modal");
  if (!box) return;
  const f = [...box.querySelectorAll('button, [href], textarea, input, select, [tabindex]:not([tabindex="-1"])')]
    .filter((n) => !n.disabled && n.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function closeModal() {
  if (!$("#modal-root").innerHTML) return;
  $("#modal-root").innerHTML = "";
  document.removeEventListener("keydown", escClose);
  if (modalOpener && document.contains(modalOpener)) modalOpener.focus();
  modalOpener = null;
}

function newRunModal() {
  const sid = S.data.strategies[0]?.id || "BTC-ORB-5M";
  const cid = S.data.cycles[0]?.id || "CYCLE-2026-11";
  const tpl = `{
  "strategy_id": "${sid}", "label": "nueva_config", "version": "1.0.1",
  "cycle_id": "${cid}",
  "params": { "bar": "5m", "N": 96 },
  "costs":  { "rt_bps": 10.14, "funding": false, "cost_r": 0.2 },
  "metrics": {
    "n": 1200, "pf_net": 1.02, "pf_stress": 0.91, "pf_ci95": [0.92, 1.13],
    "t_stat": 1.1, "mdd": -0.18, "sharpe": 0.4, "win": 0.42, "exp_net_r": 0.01
  },
  "artifacts": { "data_hash": "…", "seed": 7 }
}`;
  modal(`<h3 id="modal-title">Registrar corrida</h3>
    <p class="hint">Pega el JSON que produce el runner. El servidor recalcula puertas y veredicto; no se aceptan métricas sin IC.</p>
    <textarea class="code" id="m-json" spellcheck="false" aria-label="JSON de la corrida">${esc(tpl)}</textarea>
    <div class="row"><span class="muted" id="m-msg"></span><span class="spacer"></span><button class="btn ghost" id="m-cancel">Cancelar</button><button class="btn primary" id="m-send">Registrar</button></div>`);
  $("#m-cancel").onclick = closeModal;
  $("#m-send").onclick = async () => {
    const msg = $("#m-msg");
    let body;
    try { body = JSON.parse($("#m-json").value); } catch (e) { msg.textContent = `JSON inválido: ${e.message}`; msg.className = "bad"; return; }
    msg.textContent = "Enviando…"; msg.className = "muted";
    try {
      const res = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const out = await res.json();
      if (!res.ok) { msg.textContent = out.error || `HTTP ${res.status}`; msg.className = "bad"; return; }
      closeModal();
      banner(`Corrida ${out.id} registrada · ${VERDICT_TAG[out.verdict]}${out.reason ? ` (${out.reason})` : ""}`, out.verdict === "REJECTED" ? "bad" : out.verdict === "INCONCLUSIVE" ? "mid" : "ok");
      await refresh();
      route();
    } catch (e) { msg.textContent = e.message; msg.className = "bad"; }
  };
  $("#m-json").focus();
}

function noteModal() {
  modal(`<h3 id="modal-title">Registrar nota</h3>
    <p class="hint">Se anexa al log con timestamp y actor. No se puede editar después.</p>
    <textarea class="code" id="m-note" style="min-height:140px" placeholder="Decisión, cambio de criterio, incidencia operativa…"></textarea>
    <div class="row">
      <select id="m-actor" aria-label="Actor"><option value="human">human</option><option value="agent">agent</option><option value="runner">runner</option></select>
      <span class="muted" id="m-msg"></span><span class="spacer"></span>
      <button class="btn ghost" id="m-cancel">Cancelar</button>
      <button class="btn primary" id="m-send">Anotar</button>
    </div>`);
  $("#m-cancel").onclick = closeModal;
  $("#m-send").onclick = async () => {
    const message = $("#m-note").value.trim();
    if (!message) { $("#m-msg").textContent = "Escribe una nota antes de guardar."; $("#m-msg").className = "bad"; return; }
    const res = await fetch("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, actor: $("#m-actor").value, type: "note" }),
    });
    if (res.ok) {
      closeModal();
      await refresh();
      location.hash = "#/log";
      route();
    } else {
      $("#m-msg").textContent = `HTTP ${res.status}`;
      $("#m-msg").className = "bad";
    }
  };
  $("#m-note").focus();
}

/* -------------------------------------------------------------------- runner */
const RUNNER_GATES = [
  ["data_integrity", "Integridad"], ["pbo", "PBO"], ["dsr", "DSR"],
  ["oos_t_stat", "t OOS"], ["oos_pf_ci_low", "IC95% PF"], ["trades", "Trades"],
  ["wfa_min_trades", "Trades/fold"], ["cost_stress_2x", "Coste 2×"],
  ["funding_included", "Funding"], ["plateau", "Plateau"],
  ["benchmark_alpha", "Alpha"], ["mdd_budget", "MDD"],
];

const GATE_WORDS = { included: "Incluido", none: "Ausente", excluded: "Ausente", required: "oblig." };

function runGateValue(key, g) {
  if (g.value === null || g.value === undefined) return "—";
  if (typeof g.value === "boolean") return g.value ? "sí" : "no";
  if (typeof g.value === "string") return GATE_WORDS[g.value] || g.value;
  if (key === "data_integrity") return `${fint(g.value)} gaps`;
  if (key === "mdd_budget") return `-${fpct(Math.abs(g.value))}`;
  if (key === "trades" || key === "wfa_min_trades") return fint(g.value);
  if (key === "benchmark_alpha") return `${fsigned(g.value * 100, 1)}%`;
  return fnum(g.value, 2);
}

function runGateLimit(key, g) {
  if (g.threshold === true || g.threshold === null || g.threshold === undefined) return "";
  if (typeof g.threshold !== "number") return esc(GATE_WORDS[g.threshold] || String(g.threshold));
  if (key === "data_integrity") return "";
  const raw = typeof g.op === "string" ? g.op : "";
  const op = /^[<>]=?$/.test(raw) ? (raw === ">=" ? "≥" : raw === ">" ? ">" : raw === "<=" ? "≤" : raw) : "=";
  const thr = key === "benchmark_alpha" ? `${fsigned(g.threshold * 100, 1)}%` : fnum(g.threshold, 2);
  return `${op} ${thr}`;
}

function runGateChip(key, label, g) {
  if (!g) return "";
  const unknown = g.pass === null || g.pass === undefined;
  const cls = unknown ? "unk" : g.pass ? "pass" : "fail";
  const aria = unknown ? "sin dato" : g.pass ? "pasa" : "falla";
  const val = runGateValue(key, g);
  const lim = runGateLimit(key, g);
  return `<div class="gchip ${cls}" role="group" aria-label="${esc(label)}: ${aria}" title="${esc(`${label} · ${aria}`)}"><i></i><b>${esc(label)}</b><span class="num">${esc(val)}</span>${lim ? `<em>${lim}</em>` : ""}</div>`;
}

function splitRows(r) {
  const rows = [
    ["Todos", r.metrics?.all, "el registro completo, sin split"],
    ["IS", r.metrics?.is, `primeros ${fpct(parseFloat(r.validation?.split?.split("/")[0]) || 0.6, 0)}`],
    ["OOS", r.metrics?.oos, "tramo reservado, se toca una vez"],
    ["Reserva", r.metrics?.reserve, "no usado para elegir parámetros"],
  ].filter(([, m]) => m && m.n);
  return `<div class="card table-wrap"><table class="table split">
    <thead><tr><th>Tramo</th><th class="num">Trades</th><th class="num">PF neto</th><th class="num">IC95% PF</th><th class="num col-aux">t</th><th class="num col-aux">MDD</th></tr></thead>
    <tbody>${rows.map(([name, m, note]) => `<tr>
      <td class="id"><span>${esc(name)}</span><div class="sub">${esc(note)}</div></td>
      <td class="num">${fint(m.n)}</td>
      <td class="num"><b>${fnum(m.pf_net, 3)}</b></td>
      <td class="num mono faint">${m.pf_ci95?.[0] == null ? "—" : `${fnum(m.pf_ci95[0], 2)}–${fnum(m.pf_ci95[1], 2)}`}</td>
      <td class="num col-aux ${m.t_stat >= 3 ? "ok" : "bad"}">${fsigned(m.t_stat, 2)}</td>
      <td class="num col-aux">${fpct(m.mdd, 1)}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function runnerCard(r, spec) {
  if (r.error) return `<div class="banner bad">${esc(r.error)}</div>`;
  const a = r.artifacts || {};
  const st = r.stress || {};
  const pl = r.robustness?.perturbation || {};
  const bm = r.benchmark || {};
  const fails = Object.entries(r.gates || {}).filter(([, g]) => g.pass === false).length;
  const unknowns = Object.entries(r.gates || {}).filter(([, g]) => g.pass === null || g.pass === undefined).length;
  const eq = r.equity || [];
  const drawable = eq.length > 4 && Math.min(...eq) > 0.1;
  const regId = spec?.label ? `${r.spec_id}-v${r.version}-${spec.label}` : null;
  const reg = regId ? (S.data?.runs || []).find((x) => x.id === regId) : null;
  const clash = reg && reg.verdict !== r.verdict;
  return `
  <section class="card runner-card">
    <header>
      <h3>${esc(r.spec_id)} <span class="faint mono" style="font-size:11px">v${esc(r.version)}</span></h3>
      ${vtag(r.verdict)}
    </header>
    <div class="card-body">
      ${clash ? `<div class="banner mid"><b>Veredictos discrepantes.</b> Este artefacto dicta ${esc(VERDICT_ES[r.verdict] || r.verdict)} con ${Object.keys(r.gates || {}).length} puertas; el registro guardó ${esc(VERDICT_ES[reg.verdict] || reg.verdict)} para la misma corrida. Las corridas anteriores al runner no reevalúan alpha ni plateau: el registro es append-only.</div>` : ""}
      <div class="grid-specs four">
        <div><div class="k">Familia</div><div class="v">${esc(r.family)} · ${esc(r.data?.timeframe_signal)}</div></div>
        <div><div class="k">Barras de señal</div><div class="v">${fint(r.data?.bars_signal)}</div></div>
        <div><div class="k">Seed / entorno</div><div class="v" title="${esc(a.env || "")}">${fint(a.seed)}</div></div>
        <div><div class="k">Generado</div><div class="v mono">${esc(String(r.generated_at || "").replace("T", " ").replace("Z", "").slice(0, 16))}</div></div>
      </div>

      <div class="chips-gates">${RUNNER_GATES.map(([k, label]) => runGateChip(k, label, (r.gates || {})[k])).join("")}</div>
      <p class="hint foot">${fails} fallan · ${unknowns} sin dato · ${12 - fails - unknowns} pasan.${unknowns ? " Las puertas sin dato requieren el ciclo de selección." : " Las 12 puertas evaluadas con datos reales."}</p>

      ${splitRows(r)}

      <div class="grid-specs">
        <div><div class="k">Coste aplicado</div><div class="v">${fnum(st.applied_rt_bps, 2)} pb RT</div></div>
        <div><div class="k">Break-even</div><div class="v">${st.breakeven_rt_bps == null ? "—" : `${fnum(st.breakeven_rt_bps, 1)} pb RT`}</div></div>
        <div><div class="k">Coste 2× → PF</div><div class="v">${fnum(st.cost_2x?.pf, 3)}</div></div>
        <div><div class="k">Alpha anual</div><div class="v">${bm.alpha_annual == null ? "—" : fsigned(bm.alpha_annual * 100, 1) + "%"}</div></div>
        <div><div class="k">IC95% alpha</div><div class="v mono" style="font-size:11.5px">${bm.ci95?.[0] == null ? "—" : `${fnum(bm.ci95[0] * 100, 1)}% … ${fnum(bm.ci95[1] * 100, 1)}%`}</div></div>
        <div><div class="k">Plateau ±20%</div><div class="v">${pl.pass == null ? "pendiente" : pl.pass ? "plano" : "pico aislado"}</div></div>
      </div>

      ${drawable ? `<div class="runner-chart">${equityChart(eq, r.verdict === "APPROVED" ? "var(--ok)" : r.verdict === "INCONCLUSIVE" ? "var(--mid)" : "var(--bad)", `${r.spec_id} · ${r.data?.timeframe_signal}`)}</div>` : ""}

      ${regimeBlock(r.robustness?.regimes)}

      ${(r.reasoning || []).length ? `<ul class="prose reasons">${r.reasoning.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${(r.missing_artifacts || []).length ? `<p class="missing">Faltan artefactos del ciclo: <span class="mono">${esc(r.missing_artifacts.join(", "))}</span></p>` : ""}
      <p class="hash-line" title="${esc(a.spec_hash || "")} · ${esc(a.data_hash || "")} · ${esc(a.code_sha || "")}"><span>spec ${esc((a.spec_hash || "").replace("sha256:", "").slice(0, 16))}</span><span>data ${esc((a.data_hash || "").replace("sha256:", "").slice(0, 16))}</span><span>code ${esc((a.code_sha || "").replace("sha256:", "").slice(0, 8))}</span></p>
      ${reg ? `<p class="reg-link"><a href="#/corridas/${encodeURIComponent(reg.id)}">Ver la corrida registrada ${esc(reg.id)}</a> · ${esc(VERDICT_ES[reg.verdict] || reg.verdict)}</p>` : `<p class="reg-link faint">Esta spec aún no tiene corrida en el registro.</p>`}
    </div>
  </section>`;
}

/* ------------------------------------------------------- selection cycle card */
function verifyCard(v) {
  if (!v || v.error) return "";
  const ok = !v.failures;
  const fam = {};
  for (const r of v.runs || []) fam[r.family] = (fam[r.family] || 0) + 1;
  const famText = Object.entries(fam).map(([k, n]) => `${PORT[k] || k} ${n}`).join(" · ");
  const rows = (v.runs || []).map(r => {
    const same = Math.abs(Number(r.registry_pf_net) - Number(r.engine_pf_net)) <= 1.5e-3;
    const pfCell = same ? fnum(r.registry_pf_net, 3)
      : `${fnum(r.registry_pf_net, 3)} → ${fnum(r.engine_pf_net, 3)}`;
    const label = String(r.id || "").split(/-v[\d.]+-/).pop();
    // A defective row has no diffs (nothing was compared) and no verdict: a
    // missing field must not take the whole view down with it.
    const diffs = (r.diffs || []).join(" · ");
    const status = r.ok === true ? "reproduce" : r.ok === false ? "discrepa" : "omite";
    return `
    <tr${r.ok === false ? ' class="bad"' : r.ok === null ? ' class="muted"' : ""}>
      <td class="mono nowrap" title="${esc(r.id)}">${esc(label)}</td>
      <td class="num">${fint(r.trades)}</td>
      <td class="num mono">${pfCell}</td>
      <td title="${esc(diffs || (r.ok === null ? "registro defectuoso documentado" : ""))}">${status}</td>
    </tr>`;
  }).join("");
  const bench = v.benchmark || {};
  const vm = bench.vol_matched || {};
  const bRows = (v.runs || []).slice()
    .sort((a, b) => (b.alpha_annual ?? -9) - (a.alpha_annual ?? -9))
    .map(r => {
      const a = r.alpha_annual;
      const ci = r.alpha_ci95 || [null, null];
      const vmRow = r.vol_matched || {};
      const vTag = { bate: "bate", indistinguible: "sin concluir", pierde: "pierde" }[r.alpha_verdict] || "—";
      return `
    <tr>
      <td class="mono nowrap" title="${esc(r.id)}">${esc(r.id.split(/-v[\d.]+-/).pop())}</td>
      <td class="num mono ${a >= 0 ? "pos" : "neg"}" title="IC95 [${fnum(ci[0] * 100, 0)}%, ${fnum(ci[1] * 100, 0)}%]">${fsigned(a * 100, 1)}%</td>
      <td class="num mono faint col-aux">[${fnum(ci[0] * 100, 0)}, ${fnum(ci[1] * 100, 0)}]</td>
      <td class="num mono ${(vmRow.alpha_annual ?? -1) >= 0 ? "pos" : "neg"}">${vmRow.alpha_annual == null ? "—" : fsigned(vmRow.alpha_annual * 100, 1) + "%"}</td>
      <td>${vTag}</td>
    </tr>`;
    }).join("");
  return `
  <div class="card runner-card verify-card">
    <div class="card-head">
      <div><h3>Registro verificado</h3><div class="meta">Cada corrida se reconstruye desde sus <span class="mono">params</span> y se re-ejecuta en el motor</div></div>
      <span class="pill ${ok ? "ok" : "bad"}">${ok ? `${v.checked}/${v.checked} reproducen` : `${v.failures} sin reproducir`}</span>
    </div>
    <div class="card-body">
      <div class="grid-specs four">
        <div><div class="k">Corridas</div><div class="v">${fint(v.checked)}</div></div>
        <div><div class="k">Discrepancias</div><div class="v">${fint(v.failures || 0)}</div></div>
        <div><div class="k">Familias</div><div class="v" style="font-size:11.5px">${esc(famText)}</div></div>
        <div><div class="k">Tolerancia</div><div class="v" style="font-size:11.5px">n exacto · PF ±0,0015</div></div>
      </div>
      <p class="hint">Motor y registro son independientes: el primero ejecuta, el segundo almacena. Si un número registrado no sale de re-ejecutar sus propios parámetros, el registro no vale como fuente de verdad.</p>
      <details class="disc"><summary>Corrida por corrida</summary>
        <table class="table split">
          <thead><tr><th>Config</th><th class="num">Trades</th><th class="num">PF neto</th><th>Resultado</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>
      ${bench.bate != null ? `<div class="bench-line">
        <span>Alpha vs comprar y mantener</span>
        <b>${fint(bench.bate)} baten</b><i>·</i><b>${fint(bench.indistinguible)} sin concluir</b><i>·</i><b class="neg">${fint(bench.pierde)} pierden</b>
        <em>a igual riesgo: ${fint(vm.bate)} / ${fint(vm.indistinguible)} / ${fint(vm.pierde)}</em>
      </div>` : ""}
      <details class="disc"><summary>Alpha por configuración</summary>
        <table class="table split">
          <thead><tr><th>Config</th><th class="num"><span class="lc">α</span> anual</th><th class="num col-aux">IC95 %</th><th class="num"><span class="lc">α</span> igual</th><th>Veredicto</th></tr></thead>
          <tbody>${bRows}</tbody>
        </table>
        <p class="hint">El tramo comparado es el fuera de muestra (60–80% del intervalo). <b>α igualado</b> escala los retornos diarios de la estrategia por σ(B&H)/σ(estrategia): responde a si la regla bate al activo <em>al mismo riesgo</em>, no con el tamaño de posición que impone el 0,5% por operación. La medición está anexada al registro como evento <span class="mono">audit</span> por corrida, no reescrita en la fila original.</p>
      </details>
      <p class="hash-line"><span>datos ${esc(v.data_hash || "")}</span><span>${esc(v._file || "")}</span><span>${esc(v._mtime || "")}</span></p>
    </div>
  </div>`;
}

function sensCard(v, canon) {
  if (!v || v.error || !canon) return "";
  const g = v.dsr_by_group || {};
  const rows = Object.entries(g)
    .sort((a, b) => (b[1].dsr || 0) - (a[1].dsr || 0))
    .map(([sid, d]) => `
    <tr>
      <td class="mono nowrap">${esc(sid.replace("BTC-", ""))}</td>
      <td class="num">${fint(d.trials)}</td>
      <td class="num mono ${d.dsr >= 0.95 ? "pos" : "neg"}">${fnum(d.dsr, 3)}</td>
      <td class="num mono">${fnum(d.sharpe_annual, 2)} vs ${fnum(d.sr0_annual, 2)}</td>
    </tr>`).join("");
  const cmp = (label, a, b, fmt) => `<tr><td>${label}</td><td class="num mono">${fmt(a)}</td><td class="num mono">${fmt(b)}</td></tr>`;
  const n3 = x => fnum(x, 3);
  return `
  <div class="card runner-card sens-card">
    <div class="card-head">
      <div><h3>Sensibilidad del universo</h3><div class="meta">Las mismas puertas sobre las 19 configuraciones registradas, no sobre vecindades</div></div>
      <span class="pill mid">prueba, no canónico</span>
    </div>
    <div class="card-body">
      <table class="table split">
        <thead><tr><th>Puerta</th><th class="num">Canónico (15)</th><th class="num">Registro (19)</th></tr></thead>
        <tbody>
          ${cmp("PBO", canon.pbo?.pbo, v.pbo?.pbo, n3)}
          ${cmp("DSR", canon.dsr?.dsr, v.dsr?.dsr, n3)}
          ${cmp("SR₀ anual", canon.dsr?.sr0_annual, v.dsr?.sr0_annual, x => fnum(x, 2))}
          ${cmp("MinBTL (años)", canon.minbtl?.minbtl_years, v.minbtl?.minbtl_years, x => fnum(x, 1))}
          ${cmp("Trades/fold", canon.wfa?.min_trades_per_fold, v.wfa?.min_trades_per_fold, fint)}
        </tbody>
      </table>
      <p class="hint"><b>El PBO de 0,000 no es robustez.</b> Nueve de las 19 configuraciones pierden en todos los bloques, así que la ganadora in-sample siempre gana también fuera: el CSCV no tiene nada que discriminar. El PBO solo informa dentro de un espacio homogéneo, y por eso el ciclo canónico mantiene vecindades paramétricas.</p>
      <details class="disc"><summary>DSR por grupo de hipótesis</summary>
        <table class="table split">
          <thead><tr><th>Familia</th><th class="num">Trials</th><th class="num">DSR</th><th class="num">SR anual vs SR₀</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="hint">Agrupado por familia, el DSR ordena los marcos temporales: el 1d es el único que se acerca al umbral; todo lo de 5m queda en 0,000 porque ninguna de sus variantes supera el ruido de su propio espacio de búsqueda.</p>
      </details>
      <p class="hash-line"><span>${esc(v._file || "")}</span><span>${fint(v.inputs?.universe_size)} configuraciones</span></p>
    </div>
  </div>`;
}

function crossCheck(pbo, cp, dsr, psr) {
  const p = pbo && pbo.pbo;
  const c = cp && cp.share_below_median;
  if (p == null && c == null) return "";
  const d = dsr && dsr.dsr;
  const q = psr && psr.psr;
  const disagree = p != null && c != null && ((p <= 0.2) !== (c <= 0.2));
  const rows = [];
  if (p != null) rows.push(`<div class="cc-row"><span class="cc-k">PBO · CSCV</span><span class="cc-v mono">${fnum(p, 3)}</span><span class="cc-n">${p <= 0.2 ? "pasa" : "falla"} · ${fint((pbo.n_splits) || 0)} particiones simétricas</span></div>`);
  if (c != null) rows.push(`<div class="cc-row"><span class="cc-k">PBO · CPCV</span><span class="cc-v mono">${fnum(c, 3)}</span><span class="cc-n">${c <= 0.2 ? "pasa" : "falla"} · ${fint(cp.paths)} caminos con purga de ${fint(cp.purge_blocks)} bloque</span></div>`);
  if (d != null) rows.push(`<div class="cc-row"><span class="cc-k">DSR</span><span class="cc-v mono">${fnum(d, 3)}</span><span class="cc-n">${d >= 0.95 ? "pasa" : "falla"} · ${fint(dsr.trials)} pruebas, SR₀ ${fnum(dsr.sr0_annual, 2)}</span></div>`);
  if (q != null) rows.push(`<div class="cc-row"><span class="cc-k">PSR</span><span class="cc-v mono">${fnum(q, 3)}</span><span class="cc-n">${q >= 0.95 ? "pasa" : "falla"} · contra cero, sin deflactar</span></div>`);
  return `<div class="cc-box">
    <div class="cc-head">Cuatro formas de la misma pregunta</div>
    ${rows.join("")}
    ${disagree ? `<p class="cc-warn">El PBO depende del método: CSCV da ${fnum(p, 3)} y CPCV ${fnum(c, 3)}, y el umbral de 0,20 cae en medio. La puerta se evalúa con CSCV por ser el método declarado, pero afirmar que «falla el PBO» con esta diferencia sería más de lo que el dato sostiene.</p>` : ""}
    ${q != null && d != null && q >= 0.95 && d < 0.95 ? `<p class="cc-warn">El PSR de ${fnum(q, 3)} dice que hay señal frente a cero; el DSR de ${fnum(d, 3)} dice que no sobrevive a ${fint(dsr.trials)} pruebas. Ambas cosas son ciertas: hay algo, y no basta para atribuirlo a la regla.</p>` : ""}
  </div>`;
}

function cycleCard(v) {
  if (!v || v.error) return "";
  const pbo = v.pbo || {};
  const dsr = v.dsr || {};
  const mb = v.minbtl || {};
  const w = v.wfa || {};
  const inp = v.inputs || {};
  const chip = (label, val, lim, ok) =>
    `<div class="gchip ${ok ? "pass" : "fail"}"><i></i><span>${esc(label)}</span><b>${val}</b><em>${esc(lim)}</em></div>`;
  const empty = pbo.pbo == null;
  const okCycle = pbo.pbo != null && pbo.pbo <= 0.2 && dsr.dsr != null && dsr.dsr >= 0.95;
  return `
  <section class="card cycle-card">
    <header>
      <h3>Ciclo de selección</h3>
      ${empty ? `<span class="vtag INCONCLUSIVE"><span class="dot"></span>Sin datos</span>`
        : `<span class="vtag ${okCycle ? "APPROVED" : "REJECTED"}"><span class="dot"></span>${okCycle ? "Pasa" : "Rechazado"}</span>`}
    </header>
    <div class="card-body">
      <div class="grid-specs four">
        <div><div class="k">Universo</div><div class="v">${fint(inp.universe_size)} configuraciones</div></div>
        <div><div class="k">Muestra</div><div class="v">${fint(inp.daily_observations)} días · ${fnum(inp.coverage_years, 1)} años</div></div>
        <div><div class="k">Particiones CSCV</div><div class="v">${fint(pbo.n_splits)} · ${fint(pbo.blocks)} bloques</div></div>
        <div><div class="k">Ciclo</div><div class="v mono" style="font-size:11.5px">${esc(v.cycle_id || "—")}</div><div class="sub">${esc(String(v.generated_at || "").replace("T", " ").replace("Z", "").slice(0, 16))}</div></div>
      </div>
      <div class="chips-gates">
        ${chip("PBO", fnum(pbo.pbo, 3), "≤ 0,20", pbo.pbo != null && pbo.pbo <= 0.2)}
        ${chip("DSR", fnum(dsr.dsr, 3), "≥ 0,95", dsr.dsr != null && dsr.dsr >= 0.95)}
        ${chip("MinBTL", mb.minbtl_years == null ? "—" : `${fnum(mb.minbtl_years, 1)} años`, `≤ ${fnum(inp.coverage_years, 1)} años`, mb.minbtl_years != null && mb.minbtl_years <= (inp.coverage_years || 0))}
        ${chip("Trades/fold", w.min_trades_per_fold == null ? "—" : fint(w.min_trades_per_fold), "≥ 30", (w.min_trades_per_fold || 0) >= 30)}
      </div>
      ${crossCheck(pbo, v.cpcv, dsr, v.psr)}
      <div class="grid-specs">
        <div><div class="k">Sharpe anual vs SR₀</div><div class="v mono">${fnum(dsr.sharpe_annual, 2)} vs ${fnum(dsr.sr0_annual, 2)}</div><div class="sub">${fint(dsr.trials)} trials · ${esc(dsr.source || "")}</div></div>
        <div><div class="k">WFA fuera de muestra</div><div class="v mono">${fint(w.total_oos_trades)} trades · PF ${fnum(w.oos_pf_aggregate, 3)}</div><div class="sub">${fint(w.evaluated_folds)} folds evaluados de ${fint(w.folds_requested)}</div></div>
        <div><div class="k">Config ganadora</div><div class="v mono">${esc(v.dsr_config || "—")}</div><div class="sub">mejor Sharpe del universo</div></div>
        <div><div class="k">Artefacto</div><div class="v mono hash" title="${esc(v._file || "")}">${esc((v._file || "").split("/").pop())}</div><div class="sub">${fint(v._bytes)} B · specs ${esc((inp.specs_hash || "").slice(7, 15))}</div></div>
      </div>
      <details class="fold">
        <summary>Walk-forward por fold</summary>
        <div class="table-wrap">
          <table class="table split">
            <thead><tr><th>Fold</th><th>OOS</th><th>Config</th><th class="num">Trades</th><th class="num">PF</th></tr></thead>
            <tbody>${(w.folds || []).map((f) => `<tr>
              <td class="id">${fint(f.fold)}</td>
              <td class="mono" style="font-size:11px">${esc((f.oos || []).join(" → "))}</td>
              <td class="mono" style="font-size:11px">${esc(f.chosen || "—")}</td>
              <td class="num">${fint(f.oos_trades)}</td>
              <td class="num">${fnum(f.oos_pf, 3)}</td>
            </tr>`).join("")}</tbody>
          </table>
        </div>
      </details>
      ${(v.caveats || []).length ? `<ul class="prose reasons">${v.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
    </div>
  </section>`;
}

/* --------------------------------------------------------------- regimes */
function regimeBlock(reg) {
  if (!reg || !reg.volatility) return "";
  const all = [...Object.values(reg.volatility.buckets || {}), ...Object.values(reg.trend?.buckets || {})]
    .filter((b) => b.pf != null);
  const allLose = all.length > 0 && all.every((b) => b.pf < 1.0);
  const axis = (name, block) => {
    const rows = Object.entries(block.buckets || {});
    return `<div class="reg-axis">
      <div class="k">${esc(name)}</div>
      <div class="reg-bars">${rows.map(([lab, b]) => {
        const bad = b.pf != null && b.pf < 1.0;
        return `<div class="reg-bar${bad ? " bad" : ""}" title="${esc(lab)}: ${fint(b.n)} trades · PF ${fnum(b.pf, 3)} · ${fnum((b.exp_r || 0), 3)} R">
          <span class="lab">${esc(lab)}</span>
          <span class="track"><span class="fill" style="width:${Math.max(2, Math.min(100, ((b.pf || 0) / 3) * 100))}%"></span></span>
          <span class="val">${fnum(b.pf, 2)}</span>
        </div>`;
      }).join("")}</div>
    </div>`;
  };
  return `<div class="regimes">
    <div class="reg-head">
      <span class="k">Régimen de mercado al entrar</span>
      <span class="reg-flag ${reg.concentrated ? "bad" : (allLose ? "bad" : "ok")}">${allLose ? "sin edge en ningún tramo" : reg.concentrated ? `concentrado: pierde en ${esc(Object.values(reg.losing_buckets || {}).flat().join(", "))}` : "el edge aparece en todos los tramos"}</span>
    </div>
    ${axis("Volatilidad ATR/close", reg.volatility)}
    ${axis("Tendencia 20 barras", reg.trend)}
  </div>`;
}

function universeCard(u) {
  if (!u || !u.aggregate) return "";
  const a = u.aggregate, c = u.correlation || {};
  const rows = (u.by_symbol || []).map((s) => `<tr>
    <td class="nowrap"><b>${esc(s.symbol.replace("USDT", ""))}</b></td>
    <td class="nowrap">${fint(s.n)}</td>
    <td class="nowrap ${s.pf_net >= 1 ? "pos" : "neg"}">${fnum(s.pf_net, 3)}</td>
    <td class="nowrap">${fnum(s.sharpe, 2)}</td>
    <td class="nowrap">${fnum(s.t_stat, 2)}</td>
    <td class="nowrap col-aux">${fpct(s.mdd)}</td></tr>`).join("");
  return `<div class="card">
    <header><h3>Universo multi-activo</h3><span class="pill mid">${esc(u.label)}</span></header>
    <div class="card-body">
      <p class="prose">La misma regla sobre ${(u.aggregate.symbols || []).length} perpetuos. El t bruto sube porque hay más trades, pero los activos se mueven juntos: el ajuste por correlación lo devuelve al punto de partida.</p>
      <table class="table compact"><thead><tr><th>Activo</th><th>Trades</th><th>PF</th><th>Sharpe</th><th>t</th><th class="col-aux">MDD</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="cc-box wide">
        <div class="cc-head">El t agregado y su corrección</div>
        <div class="cc-row"><span class="cc-k">Agregado, activos independientes</span><span class="cc-v">${fnum(a.t_stat, 2)}</span><span class="cc-n">${fint(a.n)} trades · PF ${fnum(a.pf_net, 3)}</span></div>
        <div class="cc-row"><span class="cc-k">Correlación de la estrategia</span><span class="cc-v">${fnum(c.mean_rho, 3)}</span><span class="cc-n">baja porque no opera todos los días</span></div>
        <div class="cc-row"><span class="cc-k">Correlación condicional</span><span class="cc-v">${fnum(c.mean_rho_conditional, 3)}</span><span class="cc-n">cuando ambos libros están dentro</span></div>
        <div class="cc-row"><span class="cc-k">Correlación de mercado</span><span class="cc-v">${fnum(c.mean_rho_market, 3)}</span><span class="cc-n">la dependencia real entre activos</span></div>
        <div class="cc-row"><span class="cc-k">t ajustado (correlación ${fnum(c.rho_used, 3)})</span><span class="cc-v">${fnum(a.t_stat_adjusted, 2)}</span><span class="cc-n">umbral 3,0 · no pasa</span></div>
        <div class="cc-warn">Cuadruplicar los activos no compró potencia: ${fnum(a.t_stat_adjusted, 2)} frente al ${fnum(a.t_stat, 2)} bruto. Contar el mismo movimiento cuatro veces no lo convierte en cuatro observaciones.</div>
      </div>
      <p class="muted">MDD ${fpct(a.mdd)} con el riesgo dividido entre los activos que operan · stress 2× PF ${fnum(a.pf_stress, 3)} · ${fnum(a.years, 2)} años.</p>
    </div>
  </div>`;
}

function viewRunner() {
  if (!S.results) {
    return `<div class="card"><header><h3>Sin artefactos del runner</h3></header><div class="card-body"><p class="prose">No se pudo leer <code>/api/results</code>. Ejecuta el runner y recarga.</p>
    <pre class="code">python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json</pre></div></div>`;
  }
  const results = S.results.results || [];
  const specs = S.results.specs || [];
  if (!results.length) {
    return `<div class="card"><header><h3>Sin resultados</h3><span class="mono faint" style="font-size:11px">${specs.length} specs</span></header><div class="card-body">
      <p class="prose">Hay ${specs.length} specs declaradas y ningún <code>result.json</code>. El runner es la única vía legítima para producir métricas.</p>
      <pre class="code">python runner/run_strategy.py --spec runner/specs/&lt;spec&gt;.json</pre></div></div>`;
  }
  return `
    <div class="section"><h2>Resultados del runner</h2><span class="meta">${results.length} artefactos · ${specs.length} specs declaradas</span></div>
    ${cycleCard(S.results.validation)}
    ${verifyCard(S.results.verification)}
    ${sensCard(S.results.sensitivity, S.results.validation)}
    ${(S.results.universe || []).map(universeCard).join("")}
    ${results.map((r) => runnerCard(r, specs.find((s) => s.id === r.spec_id && s.version === r.version))).join("")}
    <details class="fold">
      <summary>Contrato del runner · spec → result.json</summary>
      <pre class="code">python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json \\
    --register http://127.0.0.1:8787

# 1. valida la spec contra runner/strategy_spec.schema.json
# 2. aplica el modelo de ejecución de PROMPT_V4 §3 (fill open[t+1], stop-first, gap al open)
# 3. calcula métricas, IC por bootstrap de bloques, stress 2x, break-even, plateau y alpha
# 4. evalúa las 12 puertas de §6; las que necesitan el ciclo quedan en null, no se inventan
# 5. escribe runner/out/&lt;id&gt;-v&lt;version&gt;.json y, con --register, POST /api/runs</pre>
    </details>`;
}

/* ------------------------------------------------------------------- router */
function banner(text, cls = "ok") {
  $("#banner").innerHTML = text ? `<div class="banner ${esc(cls)}">${esc(text)}</div>` : "";
}

function renderFoot() {
  const d = S.data;
  const ds = d.project?.dataset || {};
  const ts = String(d.generated_at || "").replace("T", " ").replace("Z", "").slice(0, 16);
  const hash = (ds.sha256 || "").slice(0, 12);
  $("#pagefoot").innerHTML = `
    <span>estado leído <b>${esc(ts || "—")}</b></span>
    <span class="sep"></span>
    <span>dataset sha <b>${esc(hash || "—")}</b></span>
    <span class="sep"></span>
    <span>motor <b>v${esc(d.project?.engine_version || "4.0.0")}</b></span>
    <span class="sep"></span>
    <span>${fint(d.runs.length)} corridas · ${fint(d.events.length)} eventos</span>`;
}

function renderContext() {
  const d = S.data;
  const ds = d.project?.dataset || {};
  const cyc = d.cycles[0];
  $("#context").innerHTML = `
    <span class="ctx"><b>${esc(ds.instrument || "—")}</b> perpetuo</span>
    <span class="sep"></span>
    <span class="ctx">${fint(ds.rows)} barras 5m</span>
    <span class="sep"></span>
    <span class="ctx">${esc((ds.start || "").slice(0, 10))} → ${esc((ds.end || "").slice(0, 10))}</span>
    <span class="sep"></span>
    <span class="ctx">${fint(ds.gaps)} gaps · ${fint(ds.duplicates)} duplicados</span>
    <span class="right">${cyc ? `${vtag(cyc.verdict)}<span class="sep"></span><span class="ctx mono">${esc(cyc.id)}</span>` : ""}</span>`;
}

function route(scroll = true) {
  if (!S.data) return;
  const hash = (location.hash || "#/resumen").replace(/^#\/?/, "");
  const [view, ...rest] = hash.split("/");
  const id = decodeURIComponent(rest.join("/"));
  const name = ["resumen", "estrategias", "corridas", "runner", "log", "proyecto"].includes(view) ? view : "resumen";

  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === name));
  const navEl = $("#nav");
  const activeLink = navEl && navEl.querySelector("a.active");
  if (navEl && activeLink) {
    let sc = navEl;
    while (sc && sc !== document.body && sc.scrollWidth <= sc.clientWidth + 1) sc = sc.parentElement;
    if (sc && sc !== document.body) {
      const sr = sc.getBoundingClientRect();
      const ar = activeLink.getBoundingClientRect();
      sc.scrollLeft += ar.left - sr.left - (sr.width - ar.width) / 2;
    }
  }
  $("#page-title").textContent = PAGE[name][0];
  $("#page-sub").textContent = PAGE[name][1];

  let html = "";
  if (name === "resumen") html = viewResumen();
  else if (name === "estrategias") html = id ? viewEstrategia(id) : viewEstrategias();
  else if (name === "corridas") html = id ? viewCorrida(id) : viewCorridas();
  else if (name === "runner") html = viewRunner();
  else if (name === "log") html = viewLog();
  else html = viewProyecto();
  $("#view").innerHTML = html;

  const detail = id && (name === "corridas" || name === "estrategias") ? ` · ${id.split("-v")[0]}` : "";
  document.title = `${PAGE[name][0]}${detail} — BTC Quant`;
  if (scroll) window.scrollTo({ top: 0, behavior: "instant" });
}

async function loadResults() {
  try {
    const res = await fetch("/api/results", { cache: "no-store" });
    S.results = res.ok ? await res.json() : null;
  } catch {
    S.results = null;
  }
  const n = (S.results?.specs || []).length;
  const el = $("#nav-specs");
  if (el) el.textContent = n || "";
}

/* ------------------------------------------------------------------- wiring */
async function refresh() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    S.data = await res.json();
    S.error = null;
    const c = counts();
    $("#nav-runs").textContent = S.data.runs.length;
    $("#nav-strategies").textContent = S.data.strategies.length;
    $("#health-dot").className = "dot ok";
    $("#health-text").textContent = "registro local";
    $("#engine").textContent = `v${S.data.project?.engine_version || "4.0.0"}`;
    renderContext();
    renderFoot();
    banner("");
    await loadResults();
  } catch (e) {
    S.error = e.message;
    $("#health-dot").className = "dot";
    $("#health-text").textContent = "sin conexión";
    banner(`No se pudo leer /api/state: ${e.message}`, "bad");
  }
}

document.addEventListener("click", (e) => {
  const themeBtn = e.target.closest("#theme-btn");
  if (themeBtn) { toggleTheme(); return; }
  const runEl = e.target.closest("[data-run]");  if (runEl) { location.hash = `#/corridas/${encodeURIComponent(runEl.dataset.run)}`; return; }
  const stEl = e.target.closest("[data-strategy]");
  if (stEl) { location.hash = `#/estrategias/${encodeURIComponent(stEl.dataset.strategy)}`; return; }
  const logBtn = e.target.closest("[data-log]");
  if (logBtn) { S.logFilter = logBtn.dataset.log; route(); }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const el = e.target.closest("[data-run][role='link'], [data-strategy][role='link']");
  if (!el) return;
  e.preventDefault();
  if (el.dataset.run) location.hash = `#/corridas/${encodeURIComponent(el.dataset.run)}`;
  else location.hash = `#/estrategias/${encodeURIComponent(el.dataset.strategy)}`;
});

document.addEventListener("change", (e) => {
  if (e.target.id === "f-strategy") { S.filters.corridor = e.target.value; route(); }
  if (e.target.id === "f-verdict") { S.filters.verdict = e.target.value; route(); }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "f-q") {
    S.filters.q = e.target.value;
    const pos = e.target.selectionStart;
    route(false);
    const el = $("#f-q");
    if (el) { el.focus(); el.setSelectionRange(pos, pos); }
  }
});

$("#btn-new").onclick = () => newRunModal();
$("#btn-note").onclick = () => noteModal();

let lastNarrow = window.innerWidth < 760;
window.addEventListener("resize", () => {
  const n = window.innerWidth < 760;
  if (n === lastNarrow) return;
  lastNarrow = n;
  route(false);
});

/* ------------------------------------------------------------------- theme */
// "auto" follows the OS; "dark" forces it. Only dark needs forcing, so there is
// no light override to get out of sync with the prefers-color-scheme blocks.
const THEME_KEY = "btcquant.theme";

function applyTheme(mode) {
  const osDark = matchMedia("(prefers-color-scheme: dark)").matches;
  // `forced` decides the attribute; `dark` is the resulting appearance, which is
  // what the button must report even when the OS is the one making it dark.
  const forced = mode === "dark";
  const dark = forced || osDark;
  if (forced) document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
  const btn = $("#theme-btn");
  if (btn) {
    const label = !dark ? "Oscuro" : forced ? "Oscuro activo" : "Oscuro del sistema";
    btn.setAttribute("aria-pressed", String(dark));
    btn.title = forced ? "Volver a seguir el tema del sistema" : "Forzar tema oscuro";
    btn.querySelector(".tl").textContent = label;
  }
}

function toggleTheme() {
  const nowDark = document.documentElement.dataset.theme === "dark";
  const next = nowDark ? "auto" : "dark";
  try { localStorage.setItem(THEME_KEY, next); } catch { /* private mode */ }
  applyTheme(next);
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch { /* private mode */ }
  const mode = saved === "dark" ? "dark" : "auto";
  applyTheme(mode);
  if (mode === "auto") {
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme("auto"));
  }
}

(async function boot() {
  initTheme();
  await refresh();
  if (S.data) route();
  window.addEventListener("hashchange", route);
})();
