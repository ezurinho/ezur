"""One-shot refactor of the registry UI: simpler views, less duplication."""
import pathlib

p = pathlib.Path("app/ui/app.js")
s = p.read_text(encoding="utf-8")

RESUMEN = r'''function viewResumen() {
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
      <td class="mono faint">${esc(tfs)}</td>
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
      <p class="hint foot">Las calcula el runner sobre el histórico; el modelo solo puede citarlas.</p>
    </section>
    <section class="card">
      <header><h3>Validación</h3><span class="meta">${pipelineCount().done} de 12 pasos</span></header>
      ${pipelineBar()}
    </section>
  </div>

  <div class="section"><h2>Familias probadas</h2><span class="meta">${fint(d.project?.dataset?.rows)} barras 5m</span></div>
  <div class="card table-wrap">
    <table class="table">
      <thead><tr><th>Familia</th><th>TF</th><th class="num">Corridas</th><th class="num">Mejor PF</th><th>Veredicto</th></tr></thead>
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
  const wfaOk = cyc.wfa_min_trades >= 30;
  return [
    ["SPEC", "especificaciones válidas", "done"],
    ["DATOS", gaps === 0 ? "integridad verificada" : `${fint(gaps)} gaps`, gaps === 0 ? "done" : "fail"],
    ["COSTE", "fees + spread + funding en R", "done"],
    ["BACKTEST", `${d.runs.length} corridas`, "done"],
    ["PBO", `${fnum(cyc.pbo, 2)} vs 0,20`, cyc.pbo <= 0.2 ? "done" : "fail"],
    ["DSR", `${fnum(cyc.dsr, 2)} vs 0,95`, cyc.dsr >= 0.95 ? "done" : "fail"],
    ["ROBUSTEZ", "sin artefacto de perturbación", "missing"],
    ["MONTE CARLO", "bootstrap estacionario pendiente", "missing"],
    ["REGÍMENES", "sin segmentación registrada", "missing"],
    ["WFA", `${cyc.wfa_folds || 0} folds · ${cyc.wfa_total_trades || 0} trades OOS`, wfaOk ? "done" : "partial"],
    ["BENCHMARK", "alpha vs BTC pendiente", "missing"],
    ["DRY-RUN", "no iniciado", "missing"],
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
  const pending = steps.filter(([, , st]) => st === "missing").map(([, name]) => name);
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
  <p class="hint foot">${pending.length ? `Faltan: ${pending.join(", ")}.` : "Pipeline completo."}</p>`;
}

'''

CORRIDA = r'''function viewCorrida(id) {
  const r = S.data.runs.find((x) => x.id === id);
  if (!r) return `<div class="card empty-card">
    <p class="k">Corrida no registrada</p>
    <p class="muted">No existe ninguna corrida con id <b class="mono">${esc(id)}</b> en este registro.</p>
    <p><a class="btn small" href="#/corridas">Ver todas las corridas</a></p>
  </div>`;
  const s = strategyOf(r.strategy_id);
  const cyc = cycleOf(r.cycle_id);
  const m = r.metrics;
  const extras = [
    ["Sharpe", fnum(m.sharpe, 2)],
    ["Win rate", fpct(m.win)],
    ["Años", fnum(m.years, 2)],
    ["Stop mediano", fpct(m.stop_frac_median, 2)],
    ["Expectativa", `${fsigned(m.exp_net_r, 3)} R`],
    ["Con coste 2×", `${fsigned(m.exp_stress_r, 3)} R`],
  ];
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
    <p class="hint foot">Ciclo <b class="mono">${esc(r.cycle_id)}</b>: PBO ${fnum(cyc?.pbo, 2)} · DSR ${fnum(cyc?.dsr, 2)} · ${cyc?.verdict === "REJECTED" ? "aprobación bloqueada" : "ciclo válido"}.</p>
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

'''

ESTRATEGIAS = r'''function viewEstrategias() {
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

'''

CORRIDAS_ROWS = r'''  const rows = rs.map((r) => {
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

'''


def swap(src, start_marker, end_marker, new_text):
    a = src.index(start_marker)
    b = src.index(end_marker)
    return src[:a] + new_text + src[b:]


s = swap(s, "function viewResumen() {", "function runRow(r) {", RESUMEN)
s = swap(s, "function viewCorrida(id) {", "function viewLog() {", CORRIDA)
s = swap(s, "function viewEstrategias() {", "function viewEstrategia(id) {", ESTRATEGIAS)
s = swap(
    s,
    "  const rows = rs.map((r) => {\n    const m = r.metrics;",
    "function viewCorrida(id) {",
    CORRIDAS_ROWS,
)

s = s.replace(
    '''  <div class="section"><h2>Contrato para el runner</h2><span class="meta">POST /api/runs</span></div>
  <section class="card">
    <pre class="code">''',
    '''  <details class="fold">
    <summary>Contrato para el runner · POST /api/runs</summary>
    <pre class="code">''',
)
s = s.replace(
    '''    <p class="hint" style="margin-top:12px">El servidor recalcula las puertas y el veredicto: si el ciclo falla PBO/DSR, ninguna corrida puede quedar APROBADA. Duplicar un id devuelve 409: el registro es append-only.</p>
  </section>`;''',
    '''    <p class="hint">El servidor recalcula las puertas y el veredicto: si el ciclo falla PBO/DSR, ninguna corrida puede quedar APROBADA. Duplicar un id devuelve 409: el registro es append-only.</p>
  </details>`;''',
)
s = s.replace(
    '''    <thead><tr><th>Ruta</th><th class="num">Bytes</th><th>Modificado</th><th>sha256</th><th>Estado</th></tr></thead>
    <tbody>${files.map((f) => `<tr>
      <td class="id">${esc(f.path)}</td>
      <td class="num">${f.exists ? fint(f.bytes) : "—"}</td>
      <td class="mono faint">${esc(f.mtime || "—")}</td>
      <td class="mono faint">${esc(f.sha256 || "—")}</td>
      <td>${fileTag(f.exists)}</td>
    </tr>`).join("")}</tbody>''',
    '''    <thead><tr><th>Ruta</th><th class="num">Bytes</th><th>Modificado</th><th>Estado</th></tr></thead>
    <tbody>${files.map((f) => `<tr>
      <td class="id">${esc(f.path)}<div class="sub mono">${esc(f.sha256 || "—")}</div></td>
      <td class="num">${f.exists ? fint(f.bytes) : "—"}</td>
      <td class="mono faint">${esc(f.mtime || "—")}</td>
      <td>${fileTag(f.exists)}</td>
    </tr>`).join("")}</tbody>''',
)

p.write_text(s, encoding="utf-8")
print("app.js rewritten:", len(s.splitlines()), "lines")
