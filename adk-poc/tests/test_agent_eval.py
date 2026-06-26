"""
Agent-level evaluation tests — uses ADK's AgentEvaluator to check that the
agent calls the right tools with the right args.

Requires GOOGLE_API_KEY set (the LLM runs to produce responses).

Run: pytest adk-poc/tests/test_agent_eval.py -v
"""

import pytest
from pathlib import Path

from google.adk.evaluation.agent_evaluator import AgentEvaluator

EVALS_DIR = Path(__file__).parent / "evals"


@pytest.mark.asyncio
async def test_access_management():
    """Evaluate access management — tool trajectory + response match."""
    await AgentEvaluator.evaluate(
        agent_module="adk_poc",
        eval_dataset_file_path_or_dir=str(EVALS_DIR / "access-management.test.json"),
    )


@pytest.mark.asyncio
async def test_skill_creator():
    """Evaluate skill creation — interview trigger + code rejection."""
    await AgentEvaluator.evaluate(
        agent_module="adk_poc",
        eval_dataset_file_path_or_dir=str(EVALS_DIR / "skill-creator.test.json"),
    )
