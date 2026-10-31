"""Integration test: full trade cycle from orchestrator to run history.

Exercises the complete agent pipeline end to end — data collection, strategy
signal, research scan, portfolio sizing, risk evaluation, policy gate, paper
execution, and learning review — then verifies that the result is correctly
persisted to the run history and audit trail.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from trade_agent.agent import MultiLayerTradeAgent
from trade_agent.config import AgentConfig
from trade_agent.orchestration import AgentOrchestrator
from trade_agent.storage import RunStorage


class FullCycleIntegrationTest(unittest.TestCase):
    """Run a complete paper cycle through the orchestrator and verify persistence."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.storage = RunStorage(directory=self._tmpdir.name)
        config = AgentConfig.from_env()
        agent = MultiLayerTradeAgent(config=config)
        self.orchestrator = AgentOrchestrator(agent=agent, storage=self.storage)

    # ------------------------------------------------------------------ #
    #  Full-cycle persistence                                            #
    # ------------------------------------------------------------------ #

    def test_full_trade_cycle_completes_and_persists_to_run_history(self):
        """A single orchestrator run produces a filled paper trade and lands in history."""
        result = self.orchestrator.run()

        # Top-level shape
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["mode"], "paper")

        # Every documented agent layer ran
        agent_names = {a["agent_name"] for a in result["agents"]}
        expected_agents = {
            "data_curator",
            "strategy_architect",
            "alpha_researcher",
            "portfolio_manager",
            "risk_chief",
            "policy_guard",
            "execution_steward",
            "learning_reviewer",
        }
        self.assertTrue(expected_agents.issubset(agent_names),
                        f"Missing agents: {expected_agents - agent_names}")

        # Compounding uptrend should produce a tradeable BUY that fills
        self.assertEqual(result["trade"]["status"], "filled")
        self.assertTrue(result["trade"]["simulated"])
        self.assertFalse(result["trade"]["allow_live"])

        # Risk and portfolio both approved
        self.assertTrue(result["portfolio"]["approved"])
        self.assertTrue(result["risk"]["approved"])

        # Review / learning entries present
        self.assertIn("learning_entries", result["review"])
        self.assertGreaterEqual(len(result["review"]["learning_entries"]), 1)

        # Team handoffs happened
        self.assertTrue(result["team_messages"])

        # Final summary is self-consistent
        summary = result["final_summary"]
        self.assertEqual(summary["run_id"], result["run_id"])
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["trade_status"], "filled")
        self.assertTrue(summary["portfolio_approved"])
        self.assertTrue(summary["risk_approved"])

        # Persisted to run history — the learning agent stores a learning entry
        # during review_cycle, then the orchestrator stores the full result,
        # so a single cycle produces two history entries.
        history = self.storage.load_history()
        self.assertEqual(len(history), 2)
        final_entry = history[-1]
        self.assertEqual(final_entry["run_id"], result["run_id"])
        self.assertEqual(final_entry["status"], "completed")

        # latest_run.json written
        self.assertTrue(self.storage.latest_path.exists())
        latest = json.loads(self.storage.latest_path.read_text(encoding="utf-8"))
        self.assertEqual(latest["run_id"], result["run_id"])

    def test_audit_trail_captures_full_event_sequence(self):
        """The audit log records the run lifecycle from start to final summary."""
        result = self.orchestrator.run()
        audit = self.storage.load_audit_history()
        event_types = [e["event_type"] for e in audit]

        self.assertIn("run_started", event_types)
        self.assertIn("agent_result", event_types)
        self.assertIn("agent_handoff", event_types)
        self.assertIn("final_summary", event_types)

        # The run_started event references the same run_id
        started = next(e for e in audit if e["event_type"] == "run_started")
        self.assertEqual(started["run_id"], result["run_id"])
        self.assertEqual(started["mode"], "paper")

        # final_summary is the last event
        self.assertEqual(audit[-1]["event_type"], "final_summary")
        self.assertEqual(audit[-1]["run_id"], result["run_id"])

    def test_multiple_cycles_accumulate_in_run_history(self):
        """Successive cycles append to the history without overwriting prior runs."""
        run1 = self.orchestrator.run()
        run2 = self.orchestrator.run()

        # Each cycle produces two history entries (learning + final result),
        # so two cycles yield four entries total.
        history = self.storage.load_history()
        self.assertEqual(len(history), 4)
        run_ids = [entry["run_id"] for entry in history if "run_id" in entry]
        self.assertIn(run1["run_id"], run_ids)
        self.assertIn(run2["run_id"], run_ids)
        self.assertNotEqual(run1["run_id"], run2["run_id"])

        # latest_run.json reflects the most recent cycle
        latest = json.loads(self.storage.latest_path.read_text(encoding="utf-8"))
        self.assertEqual(latest["run_id"], run2["run_id"])

    def test_kill_switch_blocks_cycle_and_records_failure(self):
        """An active kill switch prevents the cycle and records a run_failed audit event."""
        self.orchestrator.agent.config.kill_switch = True
        with self.assertRaises(ValueError):
            self.orchestrator.run()

        audit = self.storage.load_audit_history()
        run_failed = [e for e in audit if e["event_type"] == "run_failed"]
        self.assertEqual(len(run_failed), 1)
        self.assertIn("kill switch", run_failed[0]["reason"].lower())

        # Nothing should have been persisted to the run history
        self.assertEqual(len(self.storage.load_history()), 0)


if __name__ == "__main__":
    unittest.main()
