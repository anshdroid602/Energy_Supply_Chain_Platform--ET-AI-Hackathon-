"""The five agent nodes. Each is a factory `make_*_node(ds, llm, params)`
returning a `node(state) -> dict` callable the orchestrator wires into the
LangGraph. Numbers are deterministic; the LLM only narrates."""
