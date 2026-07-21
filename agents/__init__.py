"""Agent orchestration layer for the Energy Supply-Chain Sentinel.

Five agents wired into one LangGraph chain that fires from a detected signal
to a costed, mapped procurement recommendation:

    Risk Intelligence -> Scenario Modeller -> Procurement -> Strategic Reserve
                      -> Supply-Chain Digital Twin

Reads the shared Postgres data layer in-process (agents/datasource.py); all
numbers are deterministic, the LLM (Cerebras by default) only narrates.

Quick use:
    from agents.orchestrator import Orchestrator
    result = Orchestrator().run("Strait of Hormuz")
    print(result.headline)
"""
from .orchestrator import Orchestrator  # noqa: F401
from .schemas import PipelineResult      # noqa: F401
