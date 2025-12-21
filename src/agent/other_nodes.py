"""
Helper nodes for the multi-agent itinerary generation graph.

Contains:
- assign_workers_node: Creates Send() calls to distribute work to attraction researcher agents
- build_document_node: Final node that generates the DOCX document
"""
import os
from typing import Dict, Any, List, Union, Literal
from langgraph.types import Send
from langgraph.graph import END
from src.agent.state import GraphState
from src.processor.docx_processor import LocalDocxGenerator
from src.utils.logger import LOGGER

_docx_generator = None

def get_docx_generator():
    """Get or create local DOCX generator."""
    global _docx_generator
    if _docx_generator is None:
        _docx_generator = LocalDocxGenerator()
    return _docx_generator


def assign_workers_node(state: GraphState) -> Union[List[Send], Literal["__end__"]]:
    """
    Create Send() calls to assign each DAY to the researcher agent.

    This node implements the map-reduce pattern by:
    1. Taking the organized attractions by day from first agent
    2. Creating a Send() call for EACH DAY to the attraction_researcher_node
    3. Each Send() runs in parallel (one per day)

    If invalid_input is True, returns END to terminate the graph.

    Args:
        state: Graph state containing attractions_by_day from day organizer

    Returns:
        END if input is invalid, otherwise list of Send() calls
    """
    # Check if input was marked as invalid by the day organizer
    if state.get("invalid_input", False):
        LOGGER.warning("Input marked as invalid - routing to END")
        return END

    LOGGER.info("Assigning workers for attraction research...")

    attractions_by_day = state.get("attractions_by_day", [])
    preferences_input = state.get("preferences_input", "")
    language = state.get("language", "en")

    if not attractions_by_day:
        LOGGER.warning("No attractions found in state to assign")
        return []

    # Create Send() calls for each DAY (not each attraction)
    sends = []

    for day_data in attractions_by_day:
        day_number = day_data.get("day", 1)
        attractions = day_data.get("attractions", [])

        LOGGER.info(f"Creating worker for Day {day_number} with {len(attractions)} attractions")

        # Each Send() will invoke attraction_researcher_node with ALL attractions for this day
        sends.append(
            Send(
                "attraction_researcher_node",
                {
                    "attractions": attractions,  # List of all attraction names for this day
                    "day_number": day_number,
                    "preferences_input": preferences_input,
                    "language": language,
                },
            )
        )

    LOGGER.info(f"Created {len(sends)} workers for parallel day research")
    return sends


def build_document_node(state: GraphState) -> Dict[str, Any]:
    """
    Build the final DOCX document from all processed attractions.

    This node:
    1. Takes all processed_attractions from state (accumulated from parallel executions)
    2. Groups them by day
    3. Generates DOCX document with proper structure
    4. Calculates costs grouped by currency
    5. Returns final document path

    Note: This node is only called when input is valid (invalid input routes to END).

    Args:
        state: Graph state containing processed_attractions

    Returns:
        Updated state with final_document_path and costs_by_currency
    """
    LOGGER.info("Building final document...")

    processed_attractions = state.get("processed_attractions", [])
    num_days = state.get("num_days", 3)
    document_title = state.get("document_title", f"Travel Itinerary - {num_days} Days")
    language = state.get("language", "en")

    if not processed_attractions:
        LOGGER.error("No processed attractions found in state")
        return {
            "final_document_path": "",
            "costs_by_currency": {},
        }

    LOGGER.info(f"Processing {len(processed_attractions)} attractions for document")

    # Group attractions by day
    attractions_by_day = {}
    for attraction in processed_attractions:
        if not isinstance(attraction, dict):
            LOGGER.warning(f"Attraction is not a dict: {type(attraction).__name__}")
            continue

        day_number = attraction.get("day_number", 1)
        if day_number not in attractions_by_day:
            attractions_by_day[day_number] = []
        attractions_by_day[day_number].append(attraction)

    # Prepare content blocks for document
    content_blocks = []
    costs_by_currency = {}  # {currency: total_cost}

    # Language-specific labels
    labels = _get_language_labels(language)

    # Add each day
    for day_number in sorted(attractions_by_day.keys()):
        attractions = attractions_by_day[day_number]

        # Add day heading
        content_blocks.append({"type": "heading", "text": f"{labels['day']} {day_number}", "level": 1})

        # Add each attraction under this day
        for attraction in attractions:
            name = attraction.get("name", labels["unnamed_attraction"])
            description = attraction.get("description", "")

            LOGGER.info(f"Processing attraction: {name} (Day {day_number})")

            # Add attraction as subheading
            content_blocks.append({"type": "heading", "text": name, "level": 2})

            # Add description - parse bullet points
            if description:
                lines = description.split('\n')
                bullet_points = []

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Check if this is a bullet point
                    if line.startswith('- '):
                        bullet_points.append(line[2:])  # Remove "- " prefix

                    # Regular text (paragraph)
                    else:
                        # If we have accumulated bullet points, add them first
                        if bullet_points:
                            content_blocks.append({"type": "bullet_list", "items": bullet_points})
                            bullet_points = []

                        content_blocks.append({"type": "paragraph", "text": line})

                # Add any remaining bullet points
                if bullet_points:
                    content_blocks.append({"type": "bullet_list", "items": bullet_points})

            # Add images
            images = attraction.get("images", [])
            if not isinstance(images, list):
                images = []

            for idx, img in enumerate(images):
                if not isinstance(img, dict):
                    continue

                url = img.get("url_regular")
                if not url:
                    continue

                content_blocks.append(
                    {"type": "image", "url": url, "id": img.get("id", f"img_{idx}"), "caption": img.get("caption", "")}
                )

            # Add ticket/cost info
            ticket_info = attraction.get("ticket_info", [])
            if not isinstance(ticket_info, list):
                ticket_info = []

            if ticket_info:
                content_blocks.append(
                    {"type": "heading", "text": labels["ticket_info"], "level": 3}
                )

                for info in ticket_info:
                    if not isinstance(info, dict):
                        continue

                    content = info.get("content", "")
                    if content:
                        content_blocks.append({"type": "paragraph", "text": f"• {content}"})

                    url = info.get("url")
                    if url:
                        content_blocks.append({"type": "paragraph", "text": f"Link: {url}"})

            # Add useful links
            links = attraction.get("useful_links", [])
            if not isinstance(links, list):
                links = []

            if links:
                content_blocks.append({"type": "heading", "text": labels["useful_links"], "level": 3})

                link_items = []
                for link in links:
                    if isinstance(link, dict):
                        title = link.get("title", "Link")
                        url = link.get("url", "")
                        if url:
                            link_items.append(f"{title}: {url}")

                if link_items:
                    content_blocks.append({"type": "bullet_list", "items": link_items})

            # Try to extract cost and currency
            cost = attraction.get("estimated_cost", 0.0)
            currency = attraction.get("currency", "EUR")  # Default to EUR if not specified
            if cost > 0:
                if currency not in costs_by_currency:
                    costs_by_currency[currency] = 0.0
                costs_by_currency[currency] += cost

            # Add page break after each attraction
            content_blocks.append({"type": "page_break"})

        # Add spacing between days
        content_blocks.append({"type": "paragraph", "text": ""})

    # Add cost summary grouped by currency
    if costs_by_currency:
        content_blocks.append({"type": "heading", "text": labels["cost_summary"], "level": 1})

        # Currency symbols for common currencies
        currency_symbols = {
            "EUR": "€",
            "USD": "$",
            "GBP": "£",
            "BRL": "R$",
            "JPY": "¥",
            "CHF": "CHF",
            "AUD": "A$",
            "CAD": "C$",
        }

        cost_items = []
        for currency, total in sorted(costs_by_currency.items()):
            symbol = currency_symbols.get(currency, currency)
            cost_items.append(f"{symbol} {total:.2f} ({currency})")

        content_blocks.append({"type": "bullet_list", "items": cost_items})
        content_blocks.append(
            {
                "type": "paragraph",
                "text": labels["estimated_per_person"],
                "bold": False,
            }
        )

    content_blocks.append({"type": "final_image", "title": state.get("document_title", ""), "clusters": state.get("clusters", []), "attraction_coordinates": state.get("attraction_coordinates", {})})

    LOGGER.info(f"Prepared {len(content_blocks)} content blocks for document")

    # Create DOCX document
    try:
        generator = get_docx_generator()
        LOGGER.info("DOCX generator initialized")

        LOGGER.info(f"Using document title: {document_title}")
        LOGGER.info(f"Calling create_document with {len(content_blocks)} blocks (language: {language})")
        file_path = generator.create_document(
            title=document_title, content_blocks=content_blocks, language=language
        )

        LOGGER.info(f"Document created successfully at: {file_path}")

        if not file_path or not os.path.exists(file_path):
            LOGGER.error(f"Document file does not exist: {file_path}")
            return {
                "final_document_path": "",
                "costs_by_currency": costs_by_currency,
            }

        return {
            "final_document_path": file_path,
            "costs_by_currency": costs_by_currency,
        }

    except Exception as e:
        LOGGER.error(f"Document generation failed: {e}", exc_info=True)
        return {
            "final_document_path": "",
            "costs_by_currency": costs_by_currency,
        }


def _get_language_labels(language: str) -> Dict[str, str]:
    """Get language-specific labels for document generation."""
    labels = {
        "en": {
            "day": "Day",
            "unnamed_attraction": "Unnamed attraction",
            "ticket_info": "Ticket Information",
            "useful_links": "Useful Links",
            "cost_summary": "Cost Summary",
            "estimated_per_person": "* Estimated values per person",
        },
        "pt-br": {
            "day": "Dia",
            "unnamed_attraction": "Atração sem nome",
            "ticket_info": "Informações de Ingresso",
            "useful_links": "Links Úteis",
            "cost_summary": "Resumo de Custos",
            "estimated_per_person": "* Valores estimados por pessoa",
        },
        "es": {
            "day": "Día",
            "unnamed_attraction": "Atracción sin nombre",
            "ticket_info": "Información de Entrada",
            "useful_links": "Enlaces Útiles",
            "cost_summary": "Resumen de Costos",
            "estimated_per_person": "* Valores estimados por persona",
        },
        "fr": {
            "day": "Jour",
            "unnamed_attraction": "Attraction sans nom",
            "ticket_info": "Informations sur les Billets",
            "useful_links": "Liens Utiles",
            "cost_summary": "Résumé des Coûts",
            "estimated_per_person": "* Valeurs estimées par personne",
        },
    }
    return labels.get(language, labels["en"])
