"""
Helper nodes for the multi-agent itinerary generation graph.

Contains:
- assign_workers_node: Creates Send() calls to distribute work to passeio researcher agents
- build_document_node: Final node that generates the DOCX document
"""
import os
from typing import Dict, Any, List
from langgraph.types import Send
from src.agent.state import GraphState
from src.agent.tools import get_docx_generator
from src.utils.logger import LOGGER


def assign_workers_node(state: GraphState) -> List[Send]:
    """
    Create Send() calls to assign each DAY to the researcher agent.

    This node implements the map-reduce pattern by:
    1. Taking the organized passeios by day from first agent
    2. Creating a Send() call for EACH DAY to the passeio_researcher_node
    3. Each Send() runs in parallel (one per day)

    Args:
        state: Graph state containing passeios_by_day from day organizer

    Returns:
        List of Send() calls to passeio_researcher_node (one per day)
    """
    LOGGER.info("Assigning workers for passeio research...")

    passeios_by_day = state.get("passeios_by_day", [])
    preferences_input = state.get("preferences_input", "")

    if not passeios_by_day:
        LOGGER.warning("No passeios found in state to assign")
        return []

    # Create Send() calls for each DAY (not each passeio)
    sends = []

    for day_data in passeios_by_day:
        dia_numero = day_data.get("dia", 1)
        passeios = day_data.get("passeios", [])

        LOGGER.info(f"Creating worker for Dia {dia_numero} with {len(passeios)} passeios")

        # Each Send() will invoke passeio_researcher_node with ALL passeios for this day
        sends.append(
            Send(
                "passeio_researcher_node",
                {
                    "passeios": passeios,  # List of all passeio names for this day
                    "dia_numero": dia_numero,
                    "preferences_input": preferences_input,
                },
            )
        )

    LOGGER.info(f"Created {len(sends)} workers for parallel day research")
    return sends


def build_document_node(state: GraphState) -> Dict[str, Any]:
    """
    Build the final DOCX document from all processed passeios.

    This node:
    1. Takes all processed_passeios from state (accumulated from parallel executions)
    2. Groups them by day
    3. Generates DOCX document with proper structure
    4. Calculates total cost
    5. Returns final document path

    Args:
        state: Graph state containing processed_passeios

    Returns:
        Updated state with final_document_path and total_cost
    """
    LOGGER.info("Building final document...")

    processed_passeios = state.get("processed_passeios", [])
    numero_dias = state.get("numero_dias", 3)
    document_title = state.get("document_title", f"Roteiro de Viagem - {numero_dias} Dias")

    if not processed_passeios:
        LOGGER.error("No processed passeios found in state")
        return {
            "final_document_path": "",
            "total_cost": 0.0,
        }

    LOGGER.info(f"Processing {len(processed_passeios)} passeios for document")

    # Group passeios by day
    passeios_por_dia = {}
    for passeio in processed_passeios:
        if not isinstance(passeio, dict):
            LOGGER.warning(f"Passeio is not a dict: {type(passeio).__name__}")
            continue

        dia_numero = passeio.get("dia_numero", 1)
        if dia_numero not in passeios_por_dia:
            passeios_por_dia[dia_numero] = []
        passeios_por_dia[dia_numero].append(passeio)

    # Prepare content blocks for document
    content_blocks = []
    custo_total = 0.0

    # Add each day
    for dia_numero in sorted(passeios_por_dia.keys()):
        passeios = passeios_por_dia[dia_numero]

        # Add day heading
        content_blocks.append({"type": "heading", "text": f"Dia {dia_numero}", "level": 1})

        # Add each passeio under this day
        for passeio in passeios:
            nome = passeio.get("nome", "Passeio sem nome")
            descricao = passeio.get("descricao", "")

            LOGGER.info(f"Processing passeio: {nome} (Dia {dia_numero})")

            # Add passeio as subheading
            content_blocks.append({"type": "heading", "text": nome, "level": 2})

            # Add description - parse bullet points
            if descricao:
                lines = descricao.split('\n')
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
            imagens = passeio.get("imagens", [])
            if not isinstance(imagens, list):
                imagens = []

            for idx, img in enumerate(imagens):
                if not isinstance(img, dict):
                    continue

                url = img.get("url_regular")
                if not url:
                    continue

                content_blocks.append(
                    {"type": "image", "url": url, "id": img.get("id", f"img_{idx}")}
                )

            # Add ticket/cost info
            info_ingresso = passeio.get("informacoes_ingresso", [])
            if not isinstance(info_ingresso, list):
                info_ingresso = []

            if info_ingresso:
                content_blocks.append(
                    {"type": "heading", "text": "Informações de Ingresso", "level": 3}
                )

                for info in info_ingresso:
                    if not isinstance(info, dict):
                        continue

                    conteudo = info.get("conteudo", "")
                    if conteudo:
                        content_blocks.append({"type": "paragraph", "text": f"• {conteudo}"})

                    url = info.get("url")
                    if url:
                        content_blocks.append({"type": "paragraph", "text": f"Link: {url}"})

            # Add useful links
            links = passeio.get("links_uteis", [])
            if not isinstance(links, list):
                links = []

            if links:
                content_blocks.append({"type": "heading", "text": "Links Úteis", "level": 3})

                link_items = []
                for link in links:
                    if isinstance(link, dict):
                        titulo = link.get("titulo", "Link")
                        url = link.get("url", "")
                        if url:
                            link_items.append(f"{titulo}: {url}")

                if link_items:
                    content_blocks.append({"type": "bullet_list", "items": link_items})

            # Try to extract cost
            custo = passeio.get("custo_estimado", 0.0)
            if custo > 0:
                custo_total += custo

        # Add spacing between days
        content_blocks.append({"type": "paragraph", "text": ""})

    # Add cost summary
    if custo_total > 0:
        content_blocks.append({"type": "heading", "text": "Resumo de Custos", "level": 1})
        content_blocks.append(
            {
                "type": "paragraph",
                "text": f"Custo total estimado: €{custo_total:.2f}",
                "bold": True,
            }
        )

    LOGGER.info(f"Prepared {len(content_blocks)} content blocks for document")

    # Create DOCX document
    try:
        generator = get_docx_generator()
        LOGGER.info("DOCX generator initialized")

        LOGGER.info(f"Using document title: {document_title}")
        LOGGER.info(f"Calling create_document with {len(content_blocks)} blocks")
        file_path = generator.create_document(
            title=document_title, content_blocks=content_blocks
        )

        LOGGER.info(f"Document created successfully at: {file_path}")

        if not file_path or not os.path.exists(file_path):
            LOGGER.error(f"Document file does not exist: {file_path}")
            return {
                "final_document_path": "",
                "total_cost": custo_total,
            }

        return {
            "final_document_path": file_path,
            "total_cost": custo_total,
        }

    except Exception as e:
        LOGGER.error(f"Document generation failed: {e}", exc_info=True)
        return {
            "final_document_path": "",
            "total_cost": custo_total,
        }
