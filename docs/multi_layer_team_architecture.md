# Multi-Layer Trading Team

## UAEP and ORACLE framing

This repository is best understood as an institutional-grade reference implementation of the ORACLE operating pattern under the broader UAEP architecture.

UAEP provides the general operating model for AI systems: objective definition, context gathering, expert assembly, reasoning, planning, decision, execution, validation, improvement, and delivery. ORACLE applies that model to a high-level trading workflow where account scope, risk governance, auditability, and execution safety matter as much as signal generation.

The project therefore models a system that is not just a single trading bot. It is a structured operating layer for intelligence, risk, planning, and execution within a single account boundary.

## End state

The system is organized as a team of accountable main agents. Each main agent owns one professional role, keeps its own operating memory, and passes structured work products to the next role. No agent can place an order by itself: execution requires the existing account, risk, approval, and broker gates.

## Main roles

- **Market Scanner**: scans the configured stock and crypto universe and produces ranked candidates.
- **Alpha Researcher**: validates signals with historical evidence, feature checks, and alpha hypotheses.
- **Regime Analyst**: assesses the broader market regime and adjusts signal quality based on macro context.
- **Risk Chief**: checks account limits, liquidity, drawdown, daily loss, and concentration.
- **Portfolio Manager**: allocates approved risk across symbols and accounts.
- **Execution Steward**: routes only approved, account-bound orders and records the audit trail.
- **Performance Reviewer**: compares decisions with realized outcomes and writes learning records.

Each role has a persona and mandate for operating clarity. Persona is not authority: permissions come from the role contract and policy gates.

## Delegation model

A main agent may create private child agents for focused work. A child can communicate with its creator and report upward, but cannot directly message another main agent. Main-agent handoffs are explicit structured messages. This keeps ownership, provenance, and failure analysis visible.

## Learning loop

Every completed decision should produce:

1. The original market evidence and assumptions.
2. The decision and authorization context.
3. The realized fill, exit, P&L, and costs.
4. A written lesson from the responsible reviewer.
5. A later research review before any strategy or policy changes.

Learning records are evidence, not automatic permission to change live behavior. Model and risk changes must continue through paper validation and approval.

## Build sequence

1. Connect scanner candidates to per-asset research and walk-forward metrics.
2. Add portfolio-level exposure, liquidity, and daily loss controls.
3. Persist team messages, decisions, outcomes, and lessons with stable IDs.
4. Add paper trading operations, reconciliation, and monitoring.
5. Add broker adapters only after paper evidence and explicit account configuration are complete.
