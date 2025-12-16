"""
LangGraph definition for the multi-agent itinerary generation system.

Graph flow:
  START → day_organizer_node → (invalid input?) → END
                             → (valid input?) → [attraction_researcher_node (parallel)] → build_document_node → END

Features:
- Two specialized agents (day organizer and attraction researcher)
- Map-reduce pattern using Send API for parallel day research
- Structured outputs using TypedDict
- Multi-language support
- Early exit for invalid/unrelated input
"""
from langgraph.graph import StateGraph, END
from src.agent.state import GraphState
from src.agent.agent_definition import day_organizer_node, attraction_researcher_node
from src.agent.other_nodes import assign_workers_node, build_document_node
from src.utils.logger import LOGGER


def build_graph() -> StateGraph:
    """
    Build and compile the multi-agent itinerary generation graph.

    Graph structure:
      START → day_organizer_node → (invalid?) → END
                                 → (valid?) → [attraction_researcher_node] → build_document_node → END

    The assign_workers_node checks for invalid input and either:
    - Routes to END if invalid
    - Creates Send() calls for parallel attraction research if valid

    Returns:
        Compiled StateGraph ready for execution
    """
    LOGGER.info("Building multi-agent itinerary generation graph...")

    # Create graph with state schema
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("day_organizer_node", day_organizer_node)
    workflow.add_node("attraction_researcher_node", attraction_researcher_node)
    workflow.add_node("build_document_node", build_document_node)

    # Set entry point
    workflow.set_entry_point("day_organizer_node")

    # Add conditional edges from day_organizer_node
    # assign_workers_node checks for invalid input:
    # - If invalid: returns END to terminate graph
    # - If valid: returns Send() calls to invoke attraction_researcher_node
    workflow.add_conditional_edges(
        "day_organizer_node",
        assign_workers_node,
        ["attraction_researcher_node", END],
    )

    # After all attraction_researcher_node calls complete, go to build_document_node
    workflow.add_edge("attraction_researcher_node", "build_document_node")

    # End after document is built
    workflow.add_edge("build_document_node", END)

    # Compile graph
    graph = workflow.compile()
    LOGGER.info("Graph compiled successfully")
    return graph
