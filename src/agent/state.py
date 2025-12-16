"""State schema and TypedDict models for the multi-agent itinerary graph."""
from typing import TypedDict, Annotated, List, Dict, Any
import operator
import numpy
from src.utils.utilities import merge_dicts, replace_value


# ============================================================================
# TypedDict Models for Structured Outputs
# ============================================================================

class DayOrganization(TypedDict):
    """Organization of attractions for a single day."""
    day: int  # Day number (1, 2, 3, etc.)
    attractions: List[str]  # List of attraction names for this day


class OrganizedItinerary(TypedDict):
    """Complete itinerary organized by days - output from first agent."""
    document_title: str  # Creative title for the document
    attractions_by_day: List[DayOrganization]


class ImageInfo(TypedDict):
    """Image information for an attraction."""
    id: str
    url_regular: str
    caption: str  # Agent-provided caption describing what this image shows


class TicketInfo(TypedDict):
    """Ticket/entrance information for an attraction."""
    title: str
    content: str
    url: str


class LinkInfo(TypedDict):
    """Useful link for an attraction."""
    title: str
    url: str


class AttractionResearchResult(TypedDict):
    """Complete research result for a single attraction - output from second agent."""
    name: str  # Attraction name
    day_number: int  # Day number this attraction belongs to
    description: str  # Detailed description
    images: List[ImageInfo]  # Images of the attraction
    ticket_info: List[TicketInfo]  # Ticket info (empty if free/no ticket)
    useful_links: List[LinkInfo]  # Useful links
    estimated_cost: float  # Estimated cost per person
    currency: str  # Currency code (e.g., "EUR", "USD", "BRL", "GBP")


class DayResearchResult(TypedDict):
    """Research results for all attractions in a day - output from second agent."""
    day_number: int  # Day number
    attractions: List[AttractionResearchResult]  # All researched attractions for this day


# ============================================================================
# Graph State
# ============================================================================

class GraphState(TypedDict):
    """State for the multi-agent itinerary generation graph."""

    # Input from user
    user_input: str
    num_days: int
    preferences_input: str  # User preferences including age, organization preferences, etc.
    language: str  # Output language for document generation (e.g., "pt-br", "en", "es", "fr")

    # First agent - coordinate extraction state
    # Using merge_dicts to properly merge coordinate updates from multiple extract_coordinates calls
    attraction_coordinates: Annotated[Dict[str, Dict[str, float]], merge_dicts]  # {attraction_name: {lat: float, lon: float}}
    all_coordinates_obtained: Annotated[bool, replace_value]  # True when all attractions have coordinates
    clusters: numpy.ndarray  # Cluster labels for each attraction

    # First agent output (day organizer)
    document_title: str  # Generated document title
    attractions_by_day: List[Dict[str, Any]]  # List of {"day": int, "attractions": List[str]}

    # Second agent outputs (accumulated from parallel executions - one per day)
    # Using Annotated with operator.add to accumulate results from parallel Send() calls
    processed_attractions: Annotated[List[Dict[str, Any]], operator.add]

    # Invalid input handling
    invalid_input: bool  # True if input is invalid/unrelated
    error_message: str  # Error message explaining why input is invalid

    # Final outputs
    costs_by_currency: Dict[str, float]  # {currency_code: total_cost} e.g. {"EUR": 150.0, "USD": 50.0}
    final_document_path: str
