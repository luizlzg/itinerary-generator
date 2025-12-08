"""State schema and TypedDict models for the multi-agent itinerary graph."""
from typing import TypedDict, Annotated, List, Dict, Any
import operator
import numpy
from src.utils.utilities import merge_dicts, replace_value


# ============================================================================
# TypedDict Models for Structured Outputs
# ============================================================================

class DayOrganization(TypedDict):
    """Organization of passeios for a single day."""
    dia: int  # Day number (1, 2, 3, etc.)
    passeios: List[str]  # List of passeio names for this day


class OrganizedItinerary(TypedDict):
    """Complete itinerary organized by days - output from first agent."""
    document_title: str  # Creative title for the document
    passeios_by_day: List[DayOrganization]


class ImageInfo(TypedDict):
    """Image information for a passeio."""
    id: str
    url_regular: str
    caption: str  # Agent-provided caption describing what this image shows


class IngressoInfo(TypedDict):
    """Ticket/entrance information for a passeio."""
    titulo: str
    conteudo: str
    url: str


class LinkInfo(TypedDict):
    """Useful link for a passeio."""
    titulo: str
    url: str


class PasseioResearchResult(TypedDict):
    """Complete research result for a single passeio - output from second agent."""
    nome: str  # Passeio name
    dia_numero: int  # Day number this passeio belongs to
    descricao: str  # Detailed description
    imagens: List[ImageInfo]  # Images of the passeio
    informacoes_ingresso: List[IngressoInfo]  # Ticket info (empty if free/no ticket)
    links_uteis: List[LinkInfo]  # Useful links
    custo_estimado: float  # Estimated cost in EUR


class DayResearchResult(TypedDict):
    """Research results for all passeios in a day - output from second agent."""
    dia_numero: int  # Day number
    passeios: List[PasseioResearchResult]  # All researched passeios for this day


# ============================================================================
# Graph State
# ============================================================================

class GraphState(TypedDict):
    """State for the multi-agent itinerary generation graph."""

    # Input from user
    user_input: str
    numero_dias: int
    preferences_input: str  # User preferences including age, organization preferences, etc.

    # First agent - coordinate extraction state
    # Using merge_dicts to properly merge coordinate updates from multiple extrair_coordenadas calls
    coordenadas_atracoes: Annotated[Dict[str, Dict[str, float]], merge_dicts]  # {nome_atracao: {lat: float, lon: float}}
    all_coordenadas_obtidas: Annotated[bool, replace_value]  # True when all attractions have coordinates
    clusters: numpy.ndarray  # Cluster labels for each attraction

    # First agent output (day organizer)
    document_title: str  # Generated document title
    passeios_by_day: List[Dict[str, Any]]  # List of {"dia": int, "passeios": List[str]}

    # Second agent outputs (accumulated from parallel executions - one per day)
    # Using Annotated with operator.add to accumulate results from parallel Send() calls
    processed_passeios: Annotated[List[Dict[str, Any]], operator.add]

    # Final outputs
    total_cost: float
    final_document_path: str
