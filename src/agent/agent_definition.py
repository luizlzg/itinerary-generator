"""
Agent creation and execution functions for the multi-agent itinerary generation graph.

Built with LangChain 1.0:
- Uses ToolStrategy for TypedDict structured responses
- Two specialized agents: day organizer and passeio researcher
- Portuguese Brazilian language support
- Middleware-based structured output validation with retry logic
"""
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from src.agent.tools import DAY_ORGANIZER_TOOLS, PASSEIO_RESEARCHER_TOOLS
from src.agent.prompts import DAY_ORGANIZER_PROMPT, PASSEIO_RESEARCHER_PROMPT
from src.agent.state import GraphState, OrganizedItinerary, DayResearchResult
from src.utils.logger import LOGGER
from langchain.agents.structured_output import ToolStrategy
from src.middleware import (
    StructuredOutputValidatorMiddleware,
    StructuredOutputValidationError,
    KMeansUsageValidatorMiddleware,
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
    numero_dias: int = 3
):
    """
    Create the day organizer agent (first agent).

    This agent:
    - Receives user input with passeios list
    - Organizes passeios by days based on preferences or geographic proximity
    - Uses only the distance calculation tool
    - Returns structured output (OrganizedItinerary)
    - Uses middleware for structured output validation

    Args:
        model_provider: LLM provider ('openai' or 'anthropic')
        model_name: Model name to use
        numero_dias: Number of days for the itinerary (used in prompt)

    Returns:
        Agent configured with structured output and validation middleware
    """
    LOGGER.info(f"Creating day organizer agent with {model_provider}/{model_name}")

    # Initialize LLM
    llm = _initialize_llm(model_provider, model_name)

    # Format prompt with numero_dias
    formatted_prompt = DAY_ORGANIZER_PROMPT.replace("{numero_dias}", str(numero_dias))

    # Create validation middlewares
    validator_middleware = StructuredOutputValidatorMiddleware(
        expected_schema=OrganizedItinerary,
        validator_func=validate_organized_itinerary
    )

    kmeans_usage_middleware = KMeansUsageValidatorMiddleware()

    # Create agent with tools, structured output, and middlewares
    agent = create_agent(
        model=llm,
        tools=DAY_ORGANIZER_TOOLS,
        system_prompt=formatted_prompt,
        state_schema=GraphState,
        response_format=ToolStrategy(OrganizedItinerary),
        middleware=[kmeans_usage_middleware, validator_middleware]
    )

    LOGGER.info("Day organizer agent created successfully with validation middleware")
    return agent


def create_passeio_researcher_agent(
    model_provider: str = "anthropic",
    model_name: str = "claude-sonnet-4-20250514",
):
    """
    Create the passeio researcher agent (second agent).

    This agent:
    - Receives all passeios for a day
    - Researches detailed information and images for each
    - Uses search and image tools
    - Returns structured output (DayResearchResult)
    - Uses middleware for structured output validation

    Args:
        model_provider: LLM provider ('openai' or 'anthropic')
        model_name: Model name to use

    Returns:
        Agent configured with structured output and validation middleware
    """
    LOGGER.info(f"Creating passeio researcher agent with {model_provider}/{model_name}")

    # Initialize LLM
    llm = _initialize_llm(model_provider, model_name)

    # Create validation middleware
    validator_middleware = StructuredOutputValidatorMiddleware(
        expected_schema=DayResearchResult,
        validator_func=validate_day_research_result
    )

    # Create agent with tools, structured output, and middleware
    agent = create_agent(
        model=llm,
        tools=PASSEIO_RESEARCHER_TOOLS,
        system_prompt=PASSEIO_RESEARCHER_PROMPT,
        state_schema=GraphState,
        response_format=ToolStrategy(DayResearchResult),
        middleware=[validator_middleware]
    )

    LOGGER.info("Passeio researcher agent created successfully with validation middleware")
    return agent


# ============================================================================
# Node Functions
# ============================================================================

def day_organizer_node(state: GraphState) -> Dict[str, Any]:
    """
    Node that runs the day organizer agent (first agent).

    This agent:
    - Receives user input with passeios
    - Organizes passeios by days (using preferences or distance)
    - Returns OrganizedItinerary structure
    - Implements retry logic for validation failures

    Args:
        state: Graph state with user_input and numero_dias

    Returns:
        Updated state with passeios_by_day and document_title
    """
    LOGGER.info("="*60)
    LOGGER.info("RUNNING DAY ORGANIZER AGENT")
    LOGGER.info("="*60)

    user_input = state.get("user_input", "")
    numero_dias = state.get("numero_dias", 3)
    preferences_input = state.get("preferences_input", "")

    # Get model config from environment
    model_provider = os.getenv("MODEL_PROVIDER", "anthropic")
    model_name = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")
    max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))

    # Prepare initial input message
    full_input = f"{user_input}\n\nPreferências: {preferences_input}" if preferences_input else user_input
    messages = [HumanMessage(content=full_input)]

    # Retry loop
    retry_count = 0
    state["messages"] = messages

    while retry_count <= max_retries:
        try:
            # Create agent for this attempt
            agent = create_day_organizer_agent(
                model_provider=model_provider,
                model_name=model_name,
                numero_dias=numero_dias,
            )

            # Invoke agent with streaming to log all messages
            LOGGER.info(f"Invoking day organizer agent for {numero_dias} dias (attempt {retry_count + 1}/{max_retries + 1})...")

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
                            LOGGER.info(msg.pretty_repr())

                    # Keep last result
                    result = event

            # Extract structured output from final result
            structured_response = result.get("structured_response", {})
            document_title = structured_response.get("document_title", "Roteiro de Viagem")
            passeios_by_day = structured_response.get("passeios_by_day", [])

            LOGGER.info(f"✅ Day organizer succeeded - {len(passeios_by_day)} days")
            LOGGER.info(f"Document title: {document_title}")
            LOGGER.info("="*60)

            return {
                "document_title": document_title,
                "passeios_by_day": passeios_by_day,
                "clusters": result.get("clusters", []),
                "coordenadas_atracoes": result.get("coordenadas_atracoes", {}),
            }

        except StructuredOutputValidationError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"❌ Day organizer validation failed after {retry_count} attempts")
                LOGGER.error(f"Final error: {e}")
                LOGGER.info("="*60)
                return {
                    "document_title": f"Roteiro de Viagem - {numero_dias} Dias",
                    "passeios_by_day": [],
                    "clusters": [],
                    "coordenadas_atracoes": {},
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
                    "document_title": f"Roteiro de Viagem - {numero_dias} Dias",
                    "passeios_by_day": [],
                    "clusters": [],
                    "coordenadas_atracoes": {},
                }

            wait_time = 10 * retry_count  # Exponential backoff
            LOGGER.warning(f"⚠️ Rate limit exceeded (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            messages = messages + [HumanMessage(content="Você executou muitas pesquisas em pouco tempo e acabou atingindo o limite de taxa. Essa mensagem indica que você deve começar novamente do zero, realizando menos pesquisas por minuto para evitar atingir o limite novamente. Inicie!")]
            state["messages"] = messages

        except Exception as e:
            LOGGER.error(f"❌ Day organizer failed with unexpected error: {e}", exc_info=True)
            LOGGER.info("="*60)
            return {
                "document_title": f"Roteiro de Viagem - {numero_dias} Dias",
                "passeios_by_day": [],
                "clusters": [],
                "coordenadas_atracoes": {},
            }


def passeio_researcher_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Node that runs the passeio researcher agent (second agent).

    This node is called MULTIPLE times in parallel via Send API (one per day).
    Each invocation researches ALL passeios for ONE day.
    Implements retry logic for validation failures.

    Args:
        state: Minimal state with passeios (list), dia_numero, preferences_input

    Returns:
        State update with processed_passeios (list of PasseioResearchResult for this day)
    """
    passeios = state.get("passeios", [])
    dia_numero = state.get("dia_numero", 1)
    preferences_input = state.get("preferences_input", "")

    # Create logging prefix for this worker
    log_prefix = f"RESEARCH WORKER - DAY {dia_numero} - PASSEIOS: [{', '.join(passeios)}]"

    # Get model config from environment
    model_provider = os.getenv("MODEL_PROVIDER", "anthropic")
    model_name = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")
    max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))

    # Prepare initial input message
    passeios_str = "\n".join([f"- {p}" for p in passeios])
    message_content = f"""Pesquise informações completas sobre TODOS os passeios deste dia:

Dia do roteiro: {dia_numero}

Passeios:
{passeios_str}

{f'Preferências do usuário: {preferences_input}' if preferences_input else ''}

Lembre-se de:
1. Para CADA passeio, identificar se é passeio simples ou composto (com sub-locais)
2. Pesquisar informações detalhadas de CADA local/sub-local
3. Buscar 2-3 imagens de CADA local/sub-local
4. Compilar TODOS os passeios em uma única resposta estruturada (DayResearchResult)
"""

    messages = [HumanMessage(content=message_content)]

    state["messages"] = messages

    # Retry loop
    retry_count = 0

    while retry_count <= max_retries:
        try:
            # Create agent for this attempt
            agent = create_passeio_researcher_agent(
                model_provider=model_provider,
                model_name=model_name,
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
            passeios_results = result["structured_response"].get("passeios", [])

            LOGGER.info(f"{log_prefix} | ✅ Completed - {len(passeios_results)} passeios researched")

            # Return as list because processed_passeios uses operator.add reducer
            return {"processed_passeios": passeios_results}

        except StructuredOutputValidationError as e:
            retry_count += 1

            if retry_count > max_retries:
                LOGGER.error(f"{log_prefix} | ❌ Validation failed after {retry_count} attempts")
                LOGGER.error(f"{log_prefix} | Error: {e}")
                # Return minimal fallback
                return {"processed_passeios": [
                    {
                        "nome": p,
                        "dia_numero": dia_numero,
                        "descricao": "",
                        "imagens": [],
                        "informacoes_ingresso": [],
                        "links_uteis": [],
                        "custo_estimado": 0.0,
                    }
                    for p in passeios
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
                return {"processed_passeios": [
                    {
                        "nome": p,
                        "dia_numero": dia_numero,
                        "descricao": "",
                        "imagens": [],
                        "informacoes_ingresso": [],
                        "links_uteis": [],
                        "custo_estimado": 0.0,
                    }
                    for p in passeios
                ]}

            wait_time = 10 * retry_count  # Exponential backoff
            LOGGER.warning(f"{log_prefix} | ⚠️ Rate limit exceeded (attempt {retry_count}/{max_retries + 1}): {e}")
            LOGGER.info(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            messages = messages + [HumanMessage(content="Você executou muitas pesquisas em pouco tempo e acabou atingindo o limite de taxa. Essa mensagem indica que você deve começar novamente do zero, realizando menos pesquisas por minuto para evitar atingir o limite novamente. Inicie!")]
            state["messages"] = messages

        except Exception as e:
            LOGGER.error(f"{log_prefix} | ❌ Unexpected error: {e}", exc_info=True)
            # Return minimal fallback
            return {"processed_passeios": [
                {
                    "nome": p,
                    "dia_numero": dia_numero,
                    "descricao": "",
                    "imagens": [],
                    "informacoes_ingresso": [],
                    "links_uteis": [],
                    "custo_estimado": 0.0,
                }
                for p in passeios
            ]}
