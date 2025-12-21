"""
Agent creation and execution functions for the multi-agent itinerary generation graph.

Built with LangChain 1.0:
- Uses ToolStrategy for TypedDict structured responses
- Two specialized agents: day organizer and attraction researcher
- Multi-language support
- Middleware-based structured output validation with retry logic
- Interrupt support for user approval of K-means organized itineraries
"""
from typing import Dict, Any
import uuid
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from src.agent.tools import DAY_ORGANIZER_TOOLS, ATTRACTION_RESEARCHER_TOOLS
from src.agent.prompts import DAY_ORGANIZER_PROMPT, ATTRACTION_RESEARCHER_PROMPT
from src.agent.state import GraphState, OrganizedItinerary, DayResearchResult
from src.utils.logger import LOGGER
from langchain.agents.structured_output import ToolStrategy
from src.middleware import (
    StructuredOutputValidatorMiddleware,
    StructuredOutputValidationError,
    ClusteringToolValidatorMiddleware,
    validate_organized_itinerary,
    validate_day_research_result,
)
import os
import anthropic
import time


def _initialize_llm(model_provider: str = "anthropic", model_name: str = "claude-sonnet-4-20250514"):
    """
    Initialize the LLM based on provider.

    Args:
        model_provider: LLM provider ('openai' or 'anthropic')
        model_name: Model name to use

    Returns:
        Initialized LLM instance
    """
    if model_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            temperature=0
        )
    elif model_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_name,
            temperature=0,
            max_tokens=32768
        )
    else:
        raise ValueError(f"Unsupported model provider: {model_provider}")


def create_day_organizer_agent(
    model_provider: str = "anthropic",
    model_name: str = "claude-sonnet-4-20250514",
    num_days: int = 3,
    checkpointer=None
):
    """
    Create the day organizer agent (first agent).

    This agent:
    - Receives user input with attractions list
    - Organizes attractions by days based on preferences or geographic proximity
    - Uses only the distance calculation tool
    - Returns structured output (OrganizedItinerary)
    - Uses middleware for structured output validation
    - Supports interrupt for user approval of K-means organized itineraries

    Args:
        model_provider: LLM provider ('openai' or 'anthropic')
        model_name: Model name to use
        num_days: Number of days for the itinerary (used in prompt)
        checkpointer: Checkpointer for state persistence (required for interrupt support)

    Returns:
        Agent configured with structured output and validation middleware
    """
    LOGGER.info(f"Creating day organizer agent with {model_provider}/{model_name}")

    # Initialize LLM
    llm = _initialize_llm(model_provider, model_name)

    # Format prompt with num_days
    formatted_prompt = DAY_ORGANIZER_PROMPT.replace("{num_days}", str(num_days))

    # Create validation middlewares
    validator_middleware = StructuredOutputValidatorMiddleware(
        expected_schema=OrganizedItinerary,
        validator_func=validate_organized_itinerary
    )

    clustering_validator_middleware = ClusteringToolValidatorMiddleware()

    # Create agent with tools, structured output, middlewares, and checkpointer
    agent = create_agent(
        model=llm,
        tools=DAY_ORGANIZER_TOOLS,
        system_prompt=formatted_prompt,
        state_schema=GraphState,
        response_format=ToolStrategy(OrganizedItinerary),
        middleware=[clustering_validator_middleware, validator_middleware],
        checkpointer=checkpointer
    )

    LOGGER.info("Day organizer agent created successfully with validation middleware and interrupt support")
    return agent


def create_attraction_researcher_agent(
    model_provider: str = "anthropic",
    model_name: str = "claude-sonnet-4-20250514",
    language: str = "en",
):
    """
    Create the attraction researcher agent (second agent).

    This agent:
    - Receives all attractions for a day
    - Researches detailed information and images for each
    - Uses search and image tools
    - Returns structured output (DayResearchResult)
    - Uses middleware for structured output validation

    Args:
        model_provider: LLM provider ('openai' or 'anthropic')
        model_name: Model name to use
        language: Output language for document content

    Returns:
        Agent configured with structured output and validation middleware
    """
    LOGGER.info(f"Creating attraction researcher agent with {model_provider}/{model_name}")

    # Initialize LLM
    llm = _initialize_llm(model_provider, model_name)

    # Format prompt with language
    formatted_prompt = ATTRACTION_RESEARCHER_PROMPT.replace("{language}", language)

    # Create validation middleware
    validator_middleware = StructuredOutputValidatorMiddleware(
        expected_schema=DayResearchResult,
        validator_func=validate_day_research_result
    )

    # Create agent with tools, structured output, and middleware
    agent = create_agent(
        model=llm,
        tools=ATTRACTION_RESEARCHER_TOOLS,
        system_prompt=formatted_prompt,
        state_schema=GraphState,
        response_format=ToolStrategy(DayResearchResult),
        middleware=[validator_middleware]
    )

    LOGGER.info("Attraction researcher agent created successfully with validation middleware")
    return agent


# ============================================================================
# Node Functions
# ============================================================================

def _display_itinerary_for_approval(itinerary: list) -> None:
    """Display the proposed itinerary for user approval."""
    print("\n" + "="*60)
    print("PROPOSED ITINERARY ORGANIZATION")
    print("="*60)

    for day_info in itinerary:
        day_num = day_info.get("day", "?")
        attractions = day_info.get("attractions", [])
        print(f"\nDay {day_num}:")
        for attraction in attractions:
            print(f"  • {attraction}")

    print("\n" + "="*60)


def _get_user_approval() -> str:
    """Get user approval or feedback for the proposed itinerary."""
    print("\nIs this organization okay?")
    print("Type 'yes' to approve, or describe what changes you'd like.")
    print("Examples: 'move Louvre to day 2', 'swap day 1 and day 3'\n")

    response = input("Your response: ").strip()
    return response


def day_organizer_node(state: GraphState) -> Dict[str, Any]:
    """
    Node that runs the day organizer agent (first agent).

    This agent:
    - Receives user input with attractions
    - Organizes attractions by days (using preferences or distance)
    - Returns OrganizedItinerary structure
    - Implements retry logic for validation failures
    - Handles interrupt for user approval of K-means organized itineraries

    Args:
        state: Graph state with user_input and num_days

    Returns:
        Updated state with attractions_by_day and document_title
    """
    LOGGER.info("="*60)
    LOGGER.info("RUNNING DAY ORGANIZER AGENT")
    LOGGER.info("="*60)

    user_input = state.get("user_input", "")
    num_days = state.get("num_days", 3)
    preferences_input = state.get("preferences_input", "")

    # Get model config from environment
    model_provider = os.getenv("MODEL_PROVIDER", "anthropic")
    model_name = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")
    max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))

    # Prepare initial input message
    full_input = f"{user_input}\n\nPreferences: {preferences_input}" if preferences_input else user_input
    messages = [HumanMessage(content=full_input)]

    # Create checkpointer and thread_id for interrupt support
    checkpointer = MemorySaver()
    thread_id = str(uuid.uuid4())
    agent_config = {"configurable": {"thread_id": thread_id}}

    # Retry loop
    retry_count = 0
    state["messages"] = messages

    while retry_count <= max_retries:
        try:
            # Create agent for this attempt (with checkpointer for interrupt support)
            agent = create_day_organizer_agent(
                model_provider=model_provider,
                model_name=model_name,
                num_days=num_days,
                checkpointer=checkpointer,
            )

            # Invoke agent with streaming to log all messages
            LOGGER.info(f"Invoking day organizer agent for {num_days} days (attempt {retry_count + 1}/{max_retries + 1})...")

            logged_messages = []
            result = None

            # Stream events to log all messages
            for event in agent.stream(state, config=agent_config, stream_mode="values"):
                if "messages" in event and event["messages"]:
                    event_messages = event["messages"]

                    # Log all new messages
                    for msg in event_messages:
                        if msg not in logged_messages:
                            logged_messages.append(msg)
                            LOGGER.info(msg.pretty_repr())

                    # Keep last result
                    result = event

            # Check for interrupt after streaming completes
            while True:
                if "__interrupt__" in result:
                    has_interrupt = True
                    interrupt_info = result["__interrupt__"][0].value
                else:
                    has_interrupt = False
                    interrupt_info = None

                if not has_interrupt:
                    break

                # Handle itinerary approval interrupt
                if isinstance(interrupt_info, dict) and interrupt_info.get("type") == "itinerary_approval":
                    itinerary = interrupt_info.get("itinerary", [])
                    _display_itinerary_for_approval(itinerary)
                    user_response = _get_user_approval()

                    LOGGER.info(f"User response: {user_response}")
                    print("\nProcessing your response...\n")

                    # Resume agent with user's response
                    for event in agent.stream(Command(resume=user_response), config=agent_config, stream_mode="values"):
                        if "messages" in event and event["messages"]:
                            event_messages = event["messages"]

                            for msg in event_messages:
                                if msg not in logged_messages:
                                    logged_messages.append(msg)
                                    LOGGER.info(msg.pretty_repr())

                            result = event
                else:
                    LOGGER.warning(f"Unknown interrupt type: {interrupt_info}")
                    break

            # Extract structured output from final result
            structured_response = result.get("structured_response", {})
            document_title = structured_response.get("document_title", "Travel Itinerary")
            attractions_by_day = structured_response.get("attractions_by_day", [])

            LOGGER.info(f"✅ Day organizer succeeded - {len(attractions_by_day)} days")
            LOGGER.info(f"Document title: {document_title}")
            LOGGER.info("="*60)

            return {
                "document_title": document_title,
                "attractions_by_day": attractions_by_day,
                "clusters": result.get("clusters", []),
                "attraction_coordinates": result.get("attraction_coordinates", {}),
                "invalid_input": result.get("invalid_input", False),
                "error_message": result.get("error_message", ""),
                "organized_days": result.get("organized_days", {}),
                "has_flexible_attractions": result.get("has_flexible_attractions", False),
                "itinerary_approved": result.get("itinerary_approved", False),
            }

        except StructuredOutputValidationError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"❌ Day organizer validation failed after {retry_count} attempts")
                LOGGER.error(f"Final error: {e}")
                LOGGER.info("="*60)
                return {
                    "document_title": f"Travel Itinerary - {num_days} Days",
                    "attractions_by_day": [],
                    "clusters": [],
                    "attraction_coordinates": {},
                    "invalid_input": False,
                    "error_message": ""
                }

            # Add error feedback message for retry
            LOGGER.warning(f"⚠️ Validation failed (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"Retrying with error feedback...")

            # Use all messages from the failed attempt (from middleware) + error feedback
            state = e.state
            messages = e.messages + [HumanMessage(content=e.error_feedback_message)]
            state["messages"] = messages

        except anthropic.RateLimitError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"❌ Day organizer rate limit exceeded after {retry_count} attempts")
                LOGGER.error(f"Final error: {e}")
                LOGGER.info("="*60)
                return {
                    "document_title": f"Travel Itinerary - {num_days} Days",
                    "attractions_by_day": [],
                    "clusters": [],
                    "attraction_coordinates": {},
                    "invalid_input": False,
                    "error_message": ""
                }

            wait_time = 10 * retry_count  # Exponential backoff
            LOGGER.warning(f"⚠️ Rate limit exceeded (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            messages = messages + [HumanMessage(content="You executed too many searches in a short time and hit the rate limit. This message indicates you should start over from scratch, making fewer searches per minute to avoid hitting the limit again. Start!")]
            state["messages"] = messages

        except Exception as e:
            LOGGER.error(f"❌ Day organizer failed with unexpected error: {e}", exc_info=True)
            LOGGER.info("="*60)
            return {
                "document_title": f"Travel Itinerary - {num_days} Days",
                "attractions_by_day": [],
                "clusters": [],
                "attraction_coordinates": {},
                "invalid_input": False,
                "error_message": ""
            }


def attraction_researcher_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Node that runs the attraction researcher agent (second agent).

    This node is called MULTIPLE times in parallel via Send API (one per day).
    Each invocation researches ALL attractions for ONE day.
    Implements retry logic for validation failures.

    Args:
        state: Minimal state with attractions (list), day_number, preferences_input, language

    Returns:
        State update with processed_attractions (list of AttractionResearchResult for this day)
    """
    attractions = state.get("attractions", [])
    day_number = state.get("day_number", 1)
    preferences_input = state.get("preferences_input", "")
    language = state.get("language", "en")

    # Create logging prefix for this worker
    log_prefix = f"RESEARCH WORKER - DAY {day_number} - ATTRACTIONS: [{', '.join(attractions)}]"

    # Get model config from environment
    model_provider = os.getenv("MODEL_PROVIDER", "anthropic")
    model_name = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")
    max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))

    # Prepare initial input message
    attractions_str = "\n".join([f"- {a}" for a in attractions])
    message_content = f"""Research complete information about ALL attractions for this day:

Day number: {day_number}

Attractions:
{attractions_str}

{f'User preferences: {preferences_input}' if preferences_input else ''}

Remember to:
1. For EACH attraction, identify if it's a simple or compound attraction (with sub-locations)
2. Research detailed information for EACH location/sub-location
3. Search for 2-3 images of EACH location/sub-location
4. Compile ALL attractions into a single structured response (DayResearchResult)
"""

    messages = [HumanMessage(content=message_content)]

    state["messages"] = messages

    # Retry loop
    retry_count = 0

    while retry_count <= max_retries:
        try:
            # Create agent for this attempt
            agent = create_attraction_researcher_agent(
                model_provider=model_provider,
                model_name=model_name,
                language=language,
            )

            # Invoke agent with streaming to log all messages
            LOGGER.info(f"{log_prefix} | Invoking agent (attempt {retry_count + 1}/{max_retries + 1})")

            logged_messages = []
            result = None

            # Stream events to log all messages
            for event in agent.stream(state, stream_mode="values"):
                if "messages" in event and event["messages"]:
                    event_messages = event["messages"]

                    # Log all new messages
                    for msg in event_messages:
                        if msg not in logged_messages:
                            logged_messages.append(msg)
                            LOGGER.info(f"{log_prefix} | {msg.pretty_repr()}")

                    # Keep last result
                    result = event

            # Extract structured output from final result
            attractions_results = result["structured_response"].get("attractions", [])

            LOGGER.info(f"{log_prefix} | ✅ Completed - {len(attractions_results)} attractions researched")

            # Return as list because processed_attractions uses operator.add reducer
            return {"processed_attractions": attractions_results}

        except StructuredOutputValidationError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"{log_prefix} | ❌ Validation failed after {retry_count} attempts")
                LOGGER.error(f"{log_prefix} | Error: {e}")
                # Return minimal fallback
                return {"processed_attractions": [
                    {
                        "name": a,
                        "day_number": day_number,
                        "description": "",
                        "images": [],
                        "ticket_info": [],
                        "useful_links": [],
                        "estimated_cost": 0.0,
                        "currency": "EUR",
                    }
                    for a in attractions
                ]}

            # Add error feedback message for retry
            LOGGER.warning(f"{log_prefix} | ⚠️ Validation failed (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"{log_prefix} | Retrying with error feedback")

            # Use all messages from the failed attempt (from middleware) + error feedback
            state = e.state
            messages = e.messages + [HumanMessage(content=e.error_feedback_message)]
            state["messages"] = messages

        except anthropic.RateLimitError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"{log_prefix} | ❌ Rate limit exceeded after {retry_count} attempts")
                LOGGER.error(f"{log_prefix} | Error: {e}")
                LOGGER.info("="*60)
                # Return minimal fallback
                return {"processed_attractions": [
                    {
                        "name": a,
                        "day_number": day_number,
                        "description": "",
                        "images": [],
                        "ticket_info": [],
                        "useful_links": [],
                        "estimated_cost": 0.0,
                        "currency": "EUR",
                    }
                    for a in attractions
                ]}

            wait_time = 10 * retry_count  # Exponential backoff
            LOGGER.warning(f"{log_prefix} | ⚠️ Rate limit exceeded (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            messages = messages + [HumanMessage(content="You executed too many searches in a short time and hit the rate limit. This message indicates you should start over from scratch, making fewer searches per minute to avoid hitting the limit again. Start!")]
            state["messages"] = messages

        except Exception as e:
            LOGGER.error(f"{log_prefix} | ❌ Unexpected error: {e}", exc_info=True)
            # Return minimal fallback
            return {"processed_attractions": [
                {
                    "name": a,
                    "day_number": day_number,
                    "description": "",
                    "images": [],
                    "ticket_info": [],
                    "useful_links": [],
                    "estimated_cost": 0.0,
                    "currency": "EUR",
                }
                for a in attractions
            ]}
