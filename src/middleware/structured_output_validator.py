"""
Structured Output Validator Middleware for LangChain 1.0

This middleware validates structured outputs from agents and retries with error feedback if validation fails.

Based on LangChain 1.0 middleware architecture:
- https://blog.langchain.com/agent-middleware/
- https://docs.langchain.com/oss/python/langchain/middleware/built-in
"""
import os
from typing import Any, Dict, Optional, Callable
from langchain.agents.middleware import AgentMiddleware
from src.utils.logger import LOGGER


class StructuredOutputValidationError(Exception):
    """Exception raised when structured output validation fails."""

    def __init__(self, message: str, error_feedback_message: str, messages: list, state: Dict[str, Any]):
        """
        Initialize the exception.

        Args:
            message: Error message for logging
            error_feedback_message: Message to send back to the agent
            messages: All messages from the conversation so far
        """
        super().__init__(message)
        self.error_feedback_message = error_feedback_message
        self.messages = messages
        self.state = state


class StructuredOutputValidatorMiddleware(AgentMiddleware):
    """
    Middleware that validates structured output from agents.

    If validation fails:
    - Raises StructuredOutputValidationError with error message
    - Agent definition level handles retry logic

    Configuration:
    - MAX_RETRIES: Set via STRUCTURED_OUTPUT_MAX_RETRIES env var (default: 3)
    """

    def __init__(
        self,
        expected_schema: Dict[str, Any],
        validator_func: Optional[Callable[[Dict[str, Any]], tuple[bool, str]]] = None,
    ):
        """
        Initialize the middleware.

        Args:
            expected_schema: Dict describing the expected output schema (TypedDict structure)
            validator_func: Optional custom validation function that returns (is_valid, error_message)
        """
        self.expected_schema = expected_schema
        self.validator_func = validator_func or self._default_validator
        self.max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))
        LOGGER.info(
            f"Initialized StructuredOutputValidatorMiddleware (max_retries={self.max_retries} at agent level)"
        )

    def _default_validator(
        self, output: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Default validation function - checks if all required keys are present.

        Args:
            output: The structured output to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(output, dict):
            return False, f"Output is not a dict, got {type(output).__name__}"

        missing_keys = []
        for key in self.expected_schema.keys():
            if key not in output:
                missing_keys.append(key)

        if missing_keys:
            return (
                False,
                f"Missing required fields: {', '.join(missing_keys)}. "
                f"Expected schema: {list(self.expected_schema.keys())}",
            )

        # Check for empty required fields
        empty_fields = []
        for key, value in output.items():
            if key in self.expected_schema:
                # Check if required list/string fields are empty
                if isinstance(value, (list, str)) and not value:
                    empty_fields.append(key)

        if empty_fields:
            return (
                False,
                f"Required fields are empty: {', '.join(empty_fields)}. "
                f"Please provide values for all required fields.",
            )

        return True, ""

    def after_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook that runs after model call - validates structured output.

        This is the main middleware hook for LangChain 1.0.

        Args:
            state: Current agent state containing messages and output

        Returns:
            Updated state if validation passes

        Raises:
            StructuredOutputValidationError: If validation fails (includes messages from state)
        """
        LOGGER.info("Running StructuredOutputValidatorMiddleware.after_model")

        # Extract structured output from state
        structured_output = state.get("structured_response")
        if not structured_output:
            LOGGER.warning("No structured_response found in state")
            return state

        # Validate the output
        is_valid, error_message = self.validator_func(structured_output)

        if is_valid:
            LOGGER.info("✅ Structured output validation passed")
            return state

        # Validation failed - raise error with feedback message
        LOGGER.warning(f"⚠️ Structured output validation failed: {error_message}")

        # Get messages from state
        messages = state.get("messages", [])

        # Create error feedback message for the agent
        error_feedback_message = f"""
ATENÇÃO: A resposta anterior não estava no formato correto.

Erro encontrado: {error_message}

Por favor, forneça a resposta NOVAMENTE no formato estruturado correto.
Certifique-se de incluir TODOS os campos obrigatórios: {list(self.expected_schema.keys())}

IMPORTANTE: Retorne a estrutura completa e corretamente preenchida.
"""

        # Raise error with messages - agent definition will handle retry
        raise StructuredOutputValidationError(
            f"Structured output validation failed: {error_message}",
            error_feedback_message,
            messages,
            state
        )


# Validation functions for specific schemas

def validate_organized_itinerary(output: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate OrganizedItinerary schema.

    Expected:
    - document_title (str)
    - passeios_by_day (list of dicts with "dia" and "passeios")
    """
    if not isinstance(output, dict):
        return False, f"Output must be a dict, got {type(output).__name__}"

    # Check document_title
    if "document_title" not in output:
        return False, "Missing 'document_title' field"

    if not output["document_title"] or not isinstance(output["document_title"], str):
        return False, "'document_title' must be a non-empty string"

    # Check passeios_by_day
    if "passeios_by_day" not in output:
        return False, "Missing 'passeios_by_day' field"

    passeios_by_day = output["passeios_by_day"]
    if not isinstance(passeios_by_day, list):
        return False, "'passeios_by_day' must be a list"

    if not passeios_by_day:
        return False, "'passeios_by_day' cannot be empty"

    # Validate each day
    for idx, day in enumerate(passeios_by_day):
        if not isinstance(day, dict):
            return False, f"Day at index {idx} must be a dict"

        if "dia" not in day:
            return False, f"Day at index {idx} missing 'dia' field"

        if "passeios" not in day:
            return False, f"Day at index {idx} missing 'passeios' field"

        if not isinstance(day["passeios"], list):
            return False, f"Day {day.get('dia')} 'passeios' must be a list"

        if not day["passeios"]:
            return False, f"Day {day.get('dia')} 'passeios' cannot be empty"

    return True, ""


def validate_day_research_result(output: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate DayResearchResult schema.

    Expected:
    - dia_numero (int)
    - passeios (list of PasseioResearchResult dicts)
    """
    if not isinstance(output, dict):
        return False, f"Output must be a dict, got {type(output).__name__}"

    # Check dia_numero
    if "dia_numero" not in output:
        return False, "Missing 'dia_numero' field"

    if not isinstance(output["dia_numero"], int):
        return False, "'dia_numero' must be an integer"

    # Check passeios
    if "passeios" not in output:
        return False, "Missing 'passeios' field"

    passeios = output["passeios"]
    if not isinstance(passeios, list):
        return False, "'passeios' must be a list"

    if not passeios:
        return False, "'passeios' cannot be empty - must research all passeios for this day"

    # Validate each passeio
    required_fields = ["nome", "dia_numero", "descricao", "imagens", "custo_estimado"]
    for idx, passeio in enumerate(passeios):
        if not isinstance(passeio, dict):
            return False, f"Passeio at index {idx} must be a dict"

        for field in required_fields:
            if field not in passeio:
                return False, f"Passeio at index {idx} missing '{field}' field"

        # Check nome is not empty
        if not passeio["nome"]:
            return False, f"Passeio at index {idx} 'nome' cannot be empty"

    return True, ""


class KMeansUsageValidatorMiddleware(AgentMiddleware):
    """
    Middleware that validates that the K-means clustering tool was called before the agent finishes.

    This middleware ensures the day organizer agent follows the correct workflow:
    1. Extract coordinates using extrair_coordenadas
    2. Group attractions using agrupar_atracoes_kmeans
    3. Return structured output

    If the K-means tool was not called, raises an error asking the agent to use it.
    """

    def __init__(self):
        """Initialize the middleware."""
        self.max_retries = int(os.getenv("STRUCTURED_OUTPUT_MAX_RETRIES", "3"))
        LOGGER.info(
            f"Initialized KMeansUsageValidatorMiddleware (max_retries={self.max_retries} at agent level)"
        )

    def after_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook that runs after agent completes - validates K-means tool was called.

        Args:
            state: Current agent state containing messages

        Returns:
            Updated state if validation passes

        Raises:
            StructuredOutputValidationError: If K-means tool was not called
        """
        LOGGER.info("Running KMeansUsageValidatorMiddleware.after_agent")

        # Get messages from state
        messages = state.get("messages", [])

        # Check if agrupar_atracoes_kmeans was called by looking for tool calls
        kmeans_called = False
        for msg in messages:
            # Check if this is an AIMessage with tool_calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if tool_call.get("name") == "agrupar_atracoes_kmeans":
                        kmeans_called = True
                        LOGGER.info("✅ K-means clustering tool was called")
                        break

            if kmeans_called:
                break

        if kmeans_called:
            return state

        # K-means was not called - raise error
        LOGGER.warning("⚠️ K-means clustering tool was NOT called")

        error_feedback_message = """
ATENÇÃO: Você não utilizou a ferramenta 'agrupar_atracoes_kmeans' no seu processo.

Para organizar o roteiro por dias, você DEVE seguir este fluxo:

1. Extrair coordenadas de todas as atrações usando 'extrair_coordenadas'
2. Agrupar as atrações por dia usando 'agrupar_atracoes_kmeans'
3. Organizar a ordem das atrações dentro de cada dia por proximidade
4. Retornar a estrutura final

Você PRECISA chamar 'agrupar_atracoes_kmeans' para agrupar as atrações por dia.

Por favor, complete o fluxo corretamente chamando a ferramenta K-means.
"""

        raise StructuredOutputValidationError(
            "K-means clustering tool was not called",
            error_feedback_message,
            messages,
            state
        )
