"""
Observability configuration for LangSmith tracing.

LangSmith provides:
- Token usage tracking per LLM call
- Execution time for each node/agent
- Cost estimation
- Full trace visualization
- Error tracking

Setup:
1. Create account at https://smith.langchain.com
2. Get API key from Settings
3. Set environment variables in .env:
   - LANGSMITH_API_KEY=your-api-key
   - LANGSMITH_TRACING=true
   - LANGSMITH_PROJECT=itinerary-generator (optional)
"""
import os
from typing import Optional
from src.utils.logger import LOGGER


def setup_langsmith_tracing(
    project_name: Optional[str] = None,
    enable: Optional[bool] = None
) -> bool:
    """
    Configure LangSmith tracing for the application.

    Args:
        project_name: Optional project name for organizing traces.
                      Defaults to LANGSMITH_PROJECT env var or "itinerary-generator".
        enable: Force enable/disable tracing. If None, uses LANGSMITH_TRACING env var.

    Returns:
        True if tracing is enabled, False otherwise.
    """
    # Check if API key is available
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        LOGGER.info("LangSmith API key not configured. Tracing disabled.")
        LOGGER.info("To enable: set LANGSMITH_API_KEY in .env file")
        return False

    # Determine if tracing should be enabled
    if enable is None:
        tracing_env = os.getenv("LANGSMITH_TRACING", "").lower()
        enable = tracing_env in ("true", "1", "yes")

    if not enable:
        LOGGER.info("LangSmith tracing disabled (LANGSMITH_TRACING != true)")
        return False

    # Set up environment variables for LangSmith
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key

    # Set endpoint (default to LangSmith cloud)
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ["LANGSMITH_ENDPOINT"] = endpoint

    # Set project name
    project = project_name or os.getenv("LANGSMITH_PROJECT", "itinerary-generator")
    os.environ["LANGSMITH_PROJECT"] = project

    LOGGER.info(f"LangSmith tracing enabled for project: {project}")
    LOGGER.info(f"View traces at: https://smith.langchain.com/o/default/projects/p/{project}")

    return True


def get_tracing_status() -> dict:
    """
    Get current tracing configuration status.

    Returns:
        Dictionary with tracing configuration details.
    """
    return {
        "enabled": os.getenv("LANGSMITH_TRACING", "").lower() == "true",
        "api_key_set": bool(os.getenv("LANGSMITH_API_KEY")),
        "project": os.getenv("LANGSMITH_PROJECT", "default"),
        "endpoint": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
    }


def print_tracing_summary():
    """Print a summary of tracing configuration."""
    status = get_tracing_status()

    if status["enabled"] and status["api_key_set"]:
        LOGGER.info("=" * 50)
        LOGGER.info("LANGSMITH TRACING ACTIVE")
        LOGGER.info(f"  Project: {status['project']}")
        LOGGER.info(f"  Dashboard: https://smith.langchain.com")
        LOGGER.info("=" * 50)
    else:
        LOGGER.info("LangSmith tracing: DISABLED")
