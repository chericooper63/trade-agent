/* Trade Agent — paper operations dashboard.
 * Reads the existing /api/dashboard payload, triggers /api/run and /api/settings.
 * No live execution path exists; every action here is paper-only.
 */

const el = (id) => document.getElementById(id);

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);
const isNum = (value) => value !== null && value !== '' && Number.isFinite(Number(value));

const money = (value) => (isNum(value)
  ? new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value))
  : '—');
const dec = (value, digits = 2) => (isNum(value) ? Number(value).toFixed(digits) : '—');
const pct = (value, digits = 2) => (isNum(value) ? `${Number(value).toFixed(digits)}%` : '—');
const when = (iso) => {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};
const shortId = (id) => (id ? String(id).slice(0, 8) : '—');

const state = { payload: null };

async function request(path, init) {
  const response = await fetch(path, init);
  let body = null;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error((body && body.error) || `Request failed (${response.status})`);
  return body;
}

/* ---------------- status helpers ---------------- */

const OK_STATES = new Set(['completed', 'approved', 'filled', 'ready', 'paper_filled']);
const BAD_STATES = new Set(['rejected', 'failed', 'error']);
const WARN_STATES = new Set(['pending', 'awaiting', 'skipped']);

function chipClass(status) {
  const value = String(status ?? '').toLowerCase();
  if (OK_STATES.has(value)) return 'chip';
  if (BAD_STATES.has(value)) return 'chip chip-bad';
  if (WARN_STATES.has(value)) return 'chip chip-warn';
  return 'chip chip-muted';
}

const chip = (status, label = status) =>
  `<span class="${chipClass(status)}">${esc(label ?? 'none')}</span>`;

const boolChip = (flag) => chip(flag ? 'approved' : 'rejected', flag ? 'approved' : 'rejected');

/* ---------------- flags ---------------- */

function renderFlags(payload) {
  const conn = payload.connection || {};
  const market = payload.market_data || {};
  const flags = [
    `<span class="flag"><b>Mode</b> ${esc(conn.mode || 'paper')}</span>`,
    conn.allow_live
      ? '<span class="flag warn"><b>Live</b> allowed by env, blocked in UI</span>'
      : '<span class="flag off"><b>Live execution</b> disabled</span>',
    `<span class="flag ${conn.account_id_set ? '' : 'warn'}"><b>Broker</b> ${esc(conn.broker || 'none')} · ${
      conn.account_id_set ? 'account set' : 'no account'}</span>`,
    `<span class="flag ${conn.require_manual_approval ? '' : 'warn'}"><b>Manual approval</b> ${
      conn.require_manual_approval ? 'required' : 'off'}</span>`,
    conn.kill_switch
      ? '<span class="flag off"><b>Kill switch</b> active</span>'
      : '<span class="flag"><b>Kill switch</b> off</span>',
    `<span class="flag"><b>Market data</b> ${esc(market.symbol || '—')} · ${esc(market.rows ?? '—')} rows</span>`,
  ];
  el('flagStrip').innerHTML = flags.join('');
}

/* ---------------- KPI row ---------------- */

function renderKpis(payload, run) {
  const summary = (run && run.final_summary) || {};
  const portfolio = (run && run.portfolio) || {};
  const account = (run && run.account) || {};
  const trade = (run && run.trade) || {};
  const order = (run && run.order) || null;

  const cards = [
    { accent: 'var(--cyan)', label: 'Decision signal', value: summary.signal || '—', meta: `confidence ${dec(summary.confidence, 3)}` },
    { accent: 'var(--violet)', label: 'Cycle status', value: run ? (run.status || '—') : 'no cycle', meta: run ? when(run.completed_at) : 'run a paper cycle' },
    { accent: 'var(--amber)', label: 'Order', value: order ? `${order.side} ${order.quantity} ${order.symbol}` : 'none', meta: `execution ${trade.status || '—'}` },
    { accent: 'var(--green)', label: 'Paper equity', value: money(account.equity), meta: account.kind ? String(account.kind).replace(/_/g, ' ') : 'local virtual budget' },
    { accent: 'var(--red)', label: 'Risk budget used', value: pct(Number(portfolio.risk_budget_used) * 100), meta: `limit ${pct(Number(portfolio.risk_budget_limit) * 100)}` },
    { accent: 'var(--cyan)', label: 'Planned cash', value: money(portfolio.cash_remaining), meta: `allocated ${money(portfolio.total_cash_used)}` },
  ];

  el('kpiGrid').innerHTML = cards.map((card) => `
    <article class="kpi" style="--accent: ${card.accent}">
      <div class="kpi-label">${esc(card.label)}</div>
      <div class="kpi-value">${esc(card.value)}</div>
      <div class="kpi-meta">${esc(card.meta)}</div>
    </article>
  `).join('');
}

/* ---------------- panels ---------------- */

function renderDecision(run) {
  const chipEl = el('decisionChip');
  if (!run) {
    chipEl.className = 'chip chip-muted';
    chipEl.textContent = 'none';
    el('decisionBody').innerHTML = '<p class="empty">No decision cycle has run yet. Use “Run paper cycle”.</p>';
    return;
  }

  const summary = run.final_summary || {};
  const signal = summary.signal || 'HOLD';
  const confidence = Number(summary.confidence) || 0;
  const price = run.order?.price ?? run.market_scan?.candidates?.[0]?.price ?? null;
  const signalColor = signal === 'BUY' ? 'var(--green)' : signal === 'SELL' ? 'var(--red)' : 'var(--muted)';

  chipEl.className = chipClass(summary.status);
  chipEl.textContent = summary.status || 'unknown';

  el('decisionBody').innerHTML = `
    <div class="decision-hero">
      <span class="decision-signal" style="color: ${signalColor}">${esc(signal)}</span>
      <span class="decision-symbol">${esc(summary.symbol || '—')}</span>
    </div>
    <div class="meter"><i style="width: ${Math.max(0, Math.min(100, confidence * 100))}%"></i></div>
    <dl class="kv">
      <dt>Confidence</dt><dd>${dec(confidence, 3)}</dd>
      <dt>Signal reason</dt><dd>${esc(run.signal?.reason || '—')}</dd>
      <dt>Latest price</dt><dd>${money(price)}</dd>
      <dt>Completed</dt><dd>${esc(when(run.completed_at))}</dd>
      <dt>Run id</dt><dd class="mono">${esc(shortId(run.run_id))}</dd>
    </dl>
  `;
}

function renderGates(run) {
  if (!run) {
    el('gateList').innerHTML = '<li class="empty">Gates are evaluated during a paper cycle.</li>';
    return;
  }

  const portfolio = run.portfolio || {};
  const risk = run.risk || {};
  const audit = run.decision_audit || {};
  const trade = run.trade || {};
  const policyApproved = audit.policy_approved ?? run.execution_simulation?.policy_gate?.allowed ?? false;
  const filled = trade.status === 'filled';

  const gates = [
    {
      name: 'Portfolio budget',
      ok: Boolean(portfolio.approved),
      detail: portfolio.approved
        ? `${money(portfolio.total_cash_used)} allocated · ${money(portfolio.cash_remaining)} cash left`
        : (portfolio.rejection_reasons || []).join(', ') || 'rejected',
    },
    { name: 'Risk chief', ok: Boolean(risk.approved), detail: risk.reason || '—' },
    { name: 'Execution policy', ok: Boolean(policyApproved), detail: `audit status: ${audit.approval_status || '—'}` },
    { name: 'Execution steward', ok: filled, detail: trade.reason || (filled ? 'order filled in the local simulator' : '—') },
  ];

  el('gateList').innerHTML = gates.map((gate) => `
    <li class="gate">
      <div><div class="gate-name">${esc(gate.name)}</div><small>${esc(gate.detail)}</small></div>
      ${boolChip(gate.ok)}
    </li>
  `).join('');
}

function renderExecution(run) {
  if (!run) {
    el('executionBody').innerHTML = '<p class="empty">No order has been simulated.</p>';
    return;
  }

  const order = run.order;
  const trade = run.trade || {};
  const rows = order
    ? [
        ['Order id', `<span class="mono">${esc(order.order_id)}</span>`],
        ['Symbol', esc(order.symbol)],
        ['Side', esc(order.side)],
        ['Quantity', `${esc(order.quantity)} shares`],
        ['Price', money(order.price)],
        ['Route', esc(order.route || 'local_simulator')],
        ['Status', chip(trade.status)],
        ['Simulated', esc(trade.simulated ? 'yes' : 'no')],
      ]
    : [
        ['Status', chip(trade.status || 'skipped')],
        ['Reason code', esc(trade.reason_code || '—')],
        ['Simulated', esc(trade.simulated ? 'yes' : 'no')],
      ];

  el('executionBody').innerHTML = `
    <dl class="kv">${rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join('')}</dl>
    ${trade.reason ? `<div class="note">${esc(trade.reason)}</div>` : ''}
  `;
}

function renderResearch(run) {
  if (!run) {
    el('researchBody').innerHTML = '<p class="empty">No research evidence for this cycle.</p>';
    return;
  }

  const research = run.research || {};
  const candidates = run.market_scan?.candidates || [];
  const report = (research.reports || [])[0] || null;
  const metrics = (report && report.metrics) || run.metrics || null;

  const metricCards = metrics
    ? [
        ['Total return', `${dec(metrics.total_return)}%`],
        ['Net profit', money(metrics.net_profit)],
        ['Win rate', pct(Number(metrics.win_rate) * 100)],
        ['Profit factor', dec(metrics.profit_factor)],
        ['Max drawdown', `${dec(metrics.max_drawdown)}%`],
        ['Trades', dec(metrics.trades, 0)],
        ['Costs', money(metrics.costs)],
        ['Paper ready', metrics.paper_ready ? 'yes' : 'no'],
      ]
    : [];

  const candidateRows = candidates.length
    ? candidates.map((item) => `
        <tr>
          <td><strong>${esc(item.symbol)}</strong></td>
          <td>${chip(item.signal, item.signal)}</td>
          <td>${dec(item.confidence, 3)}</td>
          <td>${money(item.price)}</td>
          <td>${esc(item.source || '—')}</td>
        </tr>`).join('')
    : '<tr><td colspan="5" class="empty">No candidates scanned.</td></tr>';

  el('researchBody').innerHTML = `
    ${metricCards.length ? `<div class="metric-grid">${metricCards.map(([label, value]) => `
      <div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}</div>` : ''}
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Symbol</th><th>Signal</th><th>Confidence</th><th>Price</th><th>Source</th></tr></thead>
        <tbody>${candidateRows}</tbody>
      </table>
    </div>
    <div class="note">
      ${esc(research.qualified?.length || 0)} qualified candidate(s) from the research gate.
      ${report && report.research_passed === false ? ' Backtest did not pass the paper-ready thresholds.' : ''}
      Performance figures are simulated and are not a live-readiness claim.
    </div>
  `;
}

function renderAgents(run) {
  const agents = (run && run.agents) || [];
  el('agentCount').textContent = `${agents.length} agents`;

  if (!agents.length) {
    el('agentGrid').innerHTML = '<p class="empty">No agent results yet.</p>';
    return;
  }

  el('agentGrid').innerHTML = agents.map((agent) => `
    <article class="agent">
      <div class="agent-top">
        <span class="agent-avatar">${esc(String(agent.role || '?').slice(0, 2).toUpperCase())}</span>
        <div style="min-width: 0">
          <div class="agent-name">${esc(agent.role || 'agent')}</div>
          <div class="agent-id">${esc(agent.agent_name || '—')}</div>
        </div>
      </div>
      <div>${chip(agent.status)}</div>
      <p class="agent-reason">${esc(agent.reason || 'Stage completed with recorded evidence.')}</p>
      <div class="agent-foot"><span>conf ${dec(agent.confidence, 2)}</span><span>${esc(when(agent.timestamp))}</span></div>
    </article>
  `).join('');
}

function renderHistory(payload) {
  const history = [...(payload.run_history || [])].reverse();
  el('historyCount').textContent = `${history.length} run${history.length === 1 ? '' : 's'}`;

  const body = el('historyTable').querySelector('tbody');
  if (!history.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">No persisted runs yet.</td></tr>';
    return;
  }

  body.innerHTML = history.map((run) => `
    <tr>
      <td>${esc(when(run.completed_at))}</td>
      <td><strong>${esc(run.symbol || '—')}</strong></td>
      <td>${chip(run.signal, run.signal || '—')}</td>
      <td>${chip(run.status)}</td>
      <td>${chip(run.trade_status || 'skipped')}</td>
      <td>${run.portfolio_approved ? 'approved' : 'rejected'}</td>
      <td>${run.risk_approved ? 'approved' : 'rejected'}</td>
      <td class="mono">${esc(shortId(run.run_id))}</td>
    </tr>
  `).join('');
}

function renderSafety(payload) {
  const conn = payload.connection || {};
  const market = payload.market_data || {};

  const limits = [
    ['Account equity', money(conn.account_equity)],
    ['Proposal capital', money(conn.proposal_capital)],
    ['Max position size', pct(Number(conn.max_position_size) * 100)],
    ['Max daily loss', pct(Number(conn.max_daily_loss) * 100)],
    ['Broker', conn.broker || '—'],
    ['API key env', conn.api_key_env || '—'],
    ['Secret key env', conn.secret_key_env || '—'],
    ['Account id', conn.account_id_set ? 'configured' : 'not set'],
    ['Data provider', `${market.symbol || '—'} · ${market.rows ?? '—'} rows`],
  ];

  el('safetyBody').innerHTML = `
    <div class="safety">
      <div>
        <label class="switch-row">
          <span>
            <strong>Kill switch</strong>
            <small>${conn.kill_switch ? 'Engaged — paper cycles are blocked' : 'Off — paper cycles may run'}</small>
          </span>
          <span class="switch">
            <input type="checkbox" id="killSwitchToggle" ${conn.kill_switch ? 'checked' : ''} />
            <i></i>
          </span>
        </label>
        <div class="note">
          Live execution is unavailable in this build: no order adapter exists, and the dashboard
          only records simulated paper cycles against a local virtual budget.
        </div>
      </div>
      <dl class="kv">
        ${limits.map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')}
      </dl>
    </div>
  `;

  el('killSwitchToggle').addEventListener('change', (event) => {
    setKillSwitch(event.target.checked);
  });
}

/* ---------------- render + actions ---------------- */

function render(payload) {
  const run = payload.last_run || null;
  el('modePill').textContent = payload.mode || 'paper';
  el('cyclePill').textContent = run ? `cycle ${run.status || 'unknown'}` : 'no cycle yet';

  renderFlags(payload);
  renderKpis(payload, run);
  renderDecision(run);
  renderGates(run);
  renderExecution(run);
  renderResearch(run);
  renderAgents(run);
  renderHistory(payload);
  renderSafety(payload);
}

let toastTimer = null;
function toast(message, isError = false) {
  const node = el('toast');
  node.textContent = message;
  node.className = isError ? 'toast error' : 'toast';
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4200);
}

async function refresh() {
  state.payload = await request('/api/dashboard');
  render(state.payload);
}

async function runCycle() {
  const button = el('runButton');
  button.disabled = true;
  button.textContent = 'Running…';
  try {
    await request('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    await refresh();
    toast('Paper cycle recorded.');
  } catch (error) {
    toast(error.message, true);
    try { await refresh(); } catch { /* keep the previous view */ }
  } finally {
    button.disabled = false;
    button.textContent = 'Run paper cycle';
  }
}

async function setKillSwitch(engaged) {
  const conn = (state.payload && state.payload.connection) || {};
  try {
    await request('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'paper',
        require_manual_approval: Boolean(conn.require_manual_approval),
        kill_switch: engaged,
      }),
    });
    await refresh();
    toast(engaged ? 'Kill switch engaged — cycles are blocked.' : 'Kill switch released.');
  } catch (error) {
    toast(error.message, true);
    try { await refresh(); } catch { /* ignore */ }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  el('runButton').addEventListener('click', runCycle);
  el('refreshButton').addEventListener('click', () => {
    refresh().catch((error) => toast(error.message, true));
  });

  refresh().catch((error) => {
    toast(`Dashboard could not load: ${error.message}`, true);
    render({ mode: 'paper', connection: {}, market_data: {}, run_history: [] });
  });
});
