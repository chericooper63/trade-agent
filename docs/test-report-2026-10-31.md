# Test & readiness report — 31 Oct 2026

Scope: the whole `trade_agent` package (`trade_agent/*.py`), the stdlib dashboard server and
frontend, the CLI, and the composition of both existing suites (`tests/test_trade_agent.py`,
`tests/test_integration.py`).

Environment: `docker compose -f docker-compose.base44.yml`, service `dashboard` (container port
8000 → host 3000), bind-mounted source, `watchfiles` reload, `BASE44_PREVIEW_MODE` unset for
behaviour checks unless noted.

## 1. How it was exercised

| Check | Command / endpoint | Result |
| --- | --- | --- |
| Unit + integration suite (pytest) | `python -m pytest tests -q` | **63 passed, 7 failed**, 3 subtests passed, 5.0 s |
| Same suite as CI runs it (unittest) | `python -m unittest discover -s tests` | **Ran 70 tests, FAILED (failures=7)** |
| Byte-compile | `python -m compileall -q trade_agent tests` | OK |
| Liveness / readiness | `GET /api/health` | `200 {"status":"ready"}`, storage `ready`, 66 history entries |
| Dashboard payload | `GET /api/dashboard` | `200`, `status=ready`, `mode=paper`, 20 run summaries |
| Dashboard page (preview browser) | `http://localhost:3000/` at 1071 px | Renders, no console errors, no horizontal overflow |
| CLI (isolated data dir) | `TRADE_AGENT_DATA_DIR=/tmp/... python -m trade_agent.cli --mode paper` | Exits 0, emits a run — but the cycle is **rejected** |

## 2. Pass/fail by area

| Area | Passing | Failing |
| --- | --- | --- |
| Data providers & market data | 5 | 0 |
| Strategy, research, scanner, backtest | 7 | 0 |
| Portfolio, risk, intelligence | 8 | 0 |
| Execution, orders, broker adapters (paper paths) | 9 | 0 |
| Policy, config, environment contract | 11 | 0 |
| Orchestration / specialist agents | 3 | 1 |
| Learning, review, team, storage | 8 | 0 |
| Monitoring, events, knowledge graph, report | 6 | 0 |
| Dashboard server, startup, health | 3 | 0 |
| End-to-end integration | 3 | 1 |
| CLI | 0 | 1 |
| Dashboard API (settings) | 0 | 1 |
| Live decision audit | 0 | 1 |
| Live policy / readiness gate | 0 | 1 |
| Live broker adapter | 0 | 1 |
| **Total** | **63** | **7** |

Working, verified by green tests: market-data generation and CSV/source contracts, technical signal
generation, research scoring and scanner ranking, backtest metrics and cost handling, portfolio
sizing and risk budgets, risk approval, paper execution simulation with policy/risk gates, execution
service approval/duplicate/fingerprint rules, the paper Alpaca adapter contract (no network), order
book matching, policy and config validation (including conflicting approval flags), environment
parsing, learning journal/review feedback loops, knowledge graph, performance and report services,
audit persistence across restart, dashboard HTTP serving, health endpoint, startup retry logic, and
the kill-switch, multi-cycle accumulation and audit-trail integration tests.

## 3. The 7 failures

### Group A — one real product regression (2 tests)

1. `test_integration.py::FullCycleIntegrationTest::test_full_trade_cycle_completes_and_persists_to_run_history`
   — expected run `status="completed"` and a filled trade, got `"rejected"`.
2. `test_trade_agent.py::TradeAgentTests::test_multi_layer_agent_run_returns_documented_layers`
   — expected `execution_simulation["simulated"] is True`, got `False`. Same root cause.

**Root cause** (introduced by commit `2040f3c`, the live-execution change). `orchestration.py` now
passes `manual_approval=self.agent.config.manual_approval_required` (default `True`) into
`MonitoringService.build_decision_audit`. That method returns `approval_status="pending"` whenever
manual approval is requested, regardless of mode. The orchestrator then only calls
`approve_decision()` when `mode == "live"`, so in paper mode the audit stays `pending`,
`is_approved_for_execution()` returns `False`, `can_execute` is `False`, and every cycle is recorded
as rejected.

**Evidence**

- Orchestrator replay: `portfolio approved: True`, `risk approved: True`, `audit status: pending`,
  `trade: {"status": "rejected", "reason_code": "risk_approved", "reason": "Execution approval is missing."}`.
- CLI (`--mode paper`): `status: rejected`, `simulated: False`.
- Live dashboard: header reads *cycle rejected*; governance panel shows *Execution policy: audit
  status: pending / APPROVED* and *Execution steward: Execution approval is missing. / REJECTED*;
  the persisted run history's newest entries are all `trade_status: rejected`.

**Impact:** the product's core loop is broken — paper cycles never fill, so no simulated order,
no fills and no "completed" run appear in the dashboard. The compounding-uptrend demo data is
working as designed; the approval logic is what blocks it.

### Group B — 5 stale tests that assert live execution is unavailable

The live path was implemented in `2040f3c`, but these tests still encode the old "live is
unimplemented" contract.

3. `test_live_policy_requires_per_action_account_approval_and_nonblank_credentials`
   — expects `LiveBrokerAdapter.place()` to raise `"not implemented"`; it now calls the **real**
   Alpaca endpoint and fails with `Alpaca live API request failed: HTTP Error 401: Unauthorized`.
   The credential/approval assertions before that point pass. Side effect: this test makes an
   outbound HTTPS request, so the suite is not hermetic.
4. `test_live_decision_audit_requires_explicit_manual_approval`
   — expects `ExecutionService.execute()` to reject a live-audited route with `"paper-only"`; live
   routes are now accepted by design.
5. `test_cli_refuses_live_and_unimplemented_modes`
   — expects `"Live execution is not implemented"`; the CLI now raises
   `"Live mode requires an explicit account_id (TRADE_AGENT_ACCOUNT_ID)."` first, and would attempt
   live submission once configured.
6. `test_dashboard_never_switches_workflow_to_live`
   — expects `DashboardAPI.update_settings({"mode": "live", ...})` to raise; it now switches the
   orchestrator to the live policy and live execution agent (the UI itself still only ever posts
   `mode: "paper"`).
7. `test_production_readiness_gate_requires_explicit_live_action_context`
   — expects `status="live_policy_validated_execution_unavailable"` and
   `live_execution_available=False`; the gate now returns `"live_ready"` / `True`.

## 4. Gaps found that no test covers

1. **Live mode bypasses the human approval gate.** `AgentOrchestrator.run()` calls
   `monitor.approve_decision(..., approver="orchestrator")` unconditionally when `mode == "live"`,
   so `TRADE_AGENT_REQUIRE_MANUAL_APPROVAL=true` never requires a person. Live orders are submitted
   with a self-issued approval.
2. **Live equity is not read from the broker.** The run result reports
   `equity_source: "alpaca_live_account"` while `equity` is the configured local paper budget
   (`TRADE_AGENT_ACCOUNT_EQUITY`). Sizing decisions in live mode would use a fabricated balance.
3. **No hermetic live-path test.** Nothing exercises `AlpacaLiveBrokerAdapter` /
   `LiveExecutionAgent` against a stubbed transport, so live order payloads, error mapping and
   partial fills are unverified.
4. **Live credentials are not declared or present.** `.base44/environment.json` has
   `"secrets": []`; the container has no `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` or
   `TRADE_AGENT_ACCOUNT_ID`. Live mode cannot be configured from the dashboard today.
5. **Docs contradict the code.** `AGENTS.md` ("no live order adapter exists", "All 70 tests pass"),
   `README.md` (lines ~283, ~284, ~305) and `.env.example` ("No live order adapter is
   implemented") all still describe live execution as unavailable.
6. **Not hermetic in general.** The suite reaches `api.alpaca.markets` (failure 3) and one test
   writes `tmp_missing_symbol.csv` into the process working directory (cleaned up in `finally`).
7. **Dashboard history noise.** `LearningAgent.review_cycle` stores each learning entry into
   `runs/history.json`, so `run_history` alternates real summaries with entries that have no
   `run_id`/`completed_at`; the UI renders them as rows with `—` and `none` (visible in the
   current dashboard).

## 5. Checklist to fix the failing tests

Ordered; step 1 unblocks the run, step 2 keeps the suite honest, the rest hardens live mode.

- [ ] **1. Restore the paper cycle (Group A, real bug).**
  - Make paper decisions executable without a human approval step: either build the paper audit
    with `manual_approval=False` (leaving live on `manual_approval_required`) or auto-approve paper
    audits in the orchestrator with `approver="paper_policy"` as before `2040f3c`.
  - Keep live behaviour unchanged: live must still require `manual_approval is True` and a recorded
    approver.
  - Also give the "not executable" branch a truthful `reason_code` (today it reports
    `"risk_approved"`, the flag *name*, instead of a reason such as `approval_pending`).
  - Accept when: both Group A tests pass; `python -m trade_agent.cli --mode paper` reports
    `status: completed`, `trade.status: filled`, `simulated: true`; the dashboard's *Run paper cycle*
    shows a filled trade; `test_kill_switch_blocks_cycle_and_records_failure` and
    `test_multiple_cycles_accumulate_in_run_history` stay green.
- [ ] **2. Re-baseline the live-contract tests (Group B) to the implemented behaviour.**
  - `test_live_policy_...`: replace the `"not implemented"` expectation with a stubbed transport
    (subclass `AlpacaLiveBrokerAdapter` overriding `_request`, as
    `test_alpaca_paper_adapter_uses_paper_contract_without_network` already does) and assert the
    order payload, `route`/`mode` fields and history entry. No network.
  - `test_live_decision_audit_...`: assert a live-audited route is accepted only with an approved,
    manually approved audit, and that a `paper_broker` route still works for paper audits.
  - `test_cli_refuses_live_and_unimplemented_modes`: keep the `backtest` assertion; rename/replace
    the live half with the current contract (missing `account_id` → the account-id error) plus a
    separate test proving `--mode live` without credentials fails closed.
  - `test_dashboard_never_switches_workflow_to_live`: decide the public contract. Recommended:
    keep the dashboard API paper-only (raise unless an explicit live-confirmation flag is passed)
    and restore the assertion; otherwise rename the test to assert the live switch is allowed and
    correctly wired.
  - `test_production_readiness_gate_...`: expect `"live_ready"` / `live_execution_available: True`.
  - Accept when: 70/70 pass under both `pytest` and `unittest discover`, with no outbound network.
- [ ] **3. Close the manual-approval hole in live mode.**
  - Require a human approval token/`approved_by` supplied per live action; the orchestrator must not
    self-approve. Add a test asserting a live run cannot execute when no human approval is supplied.
- [ ] **4. Source live equity from the broker.** Fetch `GET /account` (buying power/equity) through
    the adapter before sizing in live mode, or relabel `equity_source` to the configured budget.
    Test with a stubbed adapter.
- [ ] **5. Declare and wire the live credentials.** Add `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and
    `TRADE_AGENT_ACCOUNT_ID` to `.base44/environment.json` `secrets` (and keep
    `/run/base44/app.env` as the last `env_file:`), then verify presence in the container without
    printing values.
- [ ] **6. Update documentation to match the code**: `AGENTS.md` (live adapter exists; current test
    count), `README.md` safety section, `.env.example` comments.
- [ ] **7. Tidy the dashboard run history**: keep learning entries out of `run_history` (filter on
    `final_summary`/`run_id`) so the table shows runs only.
- [ ] **8. Make the suite hermetic**: mock every broker call, and write scratch files via
    `tempfile` instead of the working directory.

## 6. Status summary

**Completed / working today**

- Dev environment: compose stack healthy, health and dashboard endpoints 200, live reload, persisted
  state volume.
- Paper simulation, strategy, research, risk, portfolio, execution gates, storage, learning loop,
  team messaging, knowledge graph, reporting, startup retries, kill switch — 63 green tests.
- Paper Alpaca contract, live policy/credential validation, config/env safety rules — green.
- Live adapters (`AlpacaLiveBrokerAdapter`, `LiveBrokerAdapter`, `LiveExecutionAgent`) implemented
  and reachable from orchestrator, CLI and dashboard API.

**Still needed**

- The paper approval regression (Group A) — highest priority: it breaks the main demo loop and the
  dashboard's visible result.
- Five stale live-contract tests + a hermetic stub for the live adapter (Group B).
- Human-in-the-loop approval for live orders, broker-sourced live equity, declared live credentials,
  and documentation that matches the implemented live path.
- Dashboard history filtering and test-suite hermeticity (lower priority).

**Not automatically verified**

- Any real Alpaca submission (no credentials in the container; calls would reach the live provider).
- Clicking *Run paper cycle* in the dashboard UI (avoided writing new run records; the same code path
  was exercised directly through the orchestrator and the CLI).
- Non-desktop breakpoints (not part of this request).
