"""LangGraph StateGraph construction with fan-out/fan-in."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.orchestrator import nodes
from src.agents.orchestrator.state import PRReviewState
from src.core.logging import get_logger

logger = get_logger(__name__)


def build_graph() -> StateGraph:
    """Construct and return the review pipeline graph."""
    graph = StateGraph(PRReviewState)

    # Add all nodes.
    graph.add_node("initialize", nodes.initialize)
    graph.add_node("fetch_pr", nodes.fetch_pr)
    graph.add_node("check_success", nodes.check_success)
    graph.add_node("analyze_security", nodes.analyze_security)
    graph.add_node("analyze_bug", nodes.analyze_bug)
    graph.add_node("analyze_style", nodes.analyze_style)
    graph.add_node("analyze_performance", nodes.analyze_performance)
    graph.add_node("aggregate_findings", nodes.aggregate_findings)
    graph.add_node("apply_fixes", nodes.apply_fixes)
    graph.add_node("finalize", nodes.finalize)

    # Linear edges.
    graph.add_edge("initialize", "fetch_pr")
    graph.add_edge("fetch_pr", "check_success")

    # Parallel fan-out from check_success to 4 agents.
    graph.add_edge("check_success", "analyze_security")
    graph.add_edge("check_success", "analyze_bug")
    graph.add_edge("check_success", "analyze_style")
    graph.add_edge("check_success", "analyze_performance")

    # Fan-in: all agents -> aggregate.
    graph.add_edge("analyze_security", "aggregate_findings")
    graph.add_edge("analyze_bug", "aggregate_findings")
    graph.add_edge("analyze_style", "aggregate_findings")
    graph.add_edge("analyze_performance", "aggregate_findings")

    # Conditional: fixes or skip.
    graph.add_conditional_edges(
        "aggregate_findings",
        nodes.should_apply_fixes,
        {
            "apply_fixes": "apply_fixes",
            "skip_fixes": "finalize",
        },
    )

    # apply_fixes -> finalize -> END
    graph.add_edge("apply_fixes", "finalize")
    graph.add_edge("finalize", END)

    # Set entry point.
    graph.set_entry_point("initialize")

    logger.info("graph_built", nodes=10, edges=17)
    return graph


# Singleton compiled graph.
_graph_instance = None


def get_graph() -> StateGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph().compile()
    return _graph_instance
