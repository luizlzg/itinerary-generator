"""Tools for the multi-agent itinerary generation graph."""
import json
from langchain_core.tools import tool
from src.mcp_client.tavily_client import SimplifiedTavilySearch
from src.mcp_client.docx_client import LocalDocxGenerator
from src.utils.logger import LOGGER
from geopy.geocoders import Nominatim
from geopy.distance import geodesic


# Global clients (initialized on first use)
_tavily_client = None
_docx_generator = None
_geolocator = None


def get_geolocator():
    """Get or create geolocator for distance calculations."""
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="itinerary_generator")
    return _geolocator


def get_tavily_client():
    """Get or create Tavily search client (simplified version)."""
    global _tavily_client
    if _tavily_client is None:
        try:
            _tavily_client = SimplifiedTavilySearch()
        except ValueError as e:
            LOGGER.warning(f"Warning: Tavily not configured: {e}")
            _tavily_client = None
    return _tavily_client


def get_docx_generator():
    """Get or create local DOCX generator."""
    global _docx_generator
    if _docx_generator is None:
        _docx_generator = LocalDocxGenerator()
    return _docx_generator


@tool
def calcular_distancia_entre_locais(
    local1: str,
    local2: str,
) -> str:
    """
    Calcula a distância geográfica entre dois locais (passeios/atrações).
    Use esta ferramenta para agrupar passeios por proximidade geográfica.

    Args:
        local1: Nome completo do primeiro local (ex: "Torre Eiffel, Paris, França")
        local2: Nome completo do segundo local (ex: "Museu do Louvre, Paris, França")

    Returns:
        JSON string com a distância em quilômetros ou erro
    """
    geolocator = get_geolocator()

    try:
        # Geocode both locations
        LOGGER.info(f"Geocoding local1: {local1}")
        location1 = geolocator.geocode(local1, timeout=10)

        if not location1:
            return json.dumps({
                "error": f"Não foi possível encontrar as coordenadas de: {local1}",
                "distancia_km": None
            }, ensure_ascii=False)

        LOGGER.info(f"Geocoding local2: {local2}")
        location2 = geolocator.geocode(local2, timeout=10)

        if not location2:
            return json.dumps({
                "error": f"Não foi possível encontrar as coordenadas de: {local2}",
                "distancia_km": None
            }, ensure_ascii=False)

        # Calculate distance
        coords1 = (location1.latitude, location1.longitude)
        coords2 = (location2.latitude, location2.longitude)
        distance = geodesic(coords1, coords2).kilometers

        LOGGER.info(f"Distance between {local1} and {local2}: {distance:.2f} km")

        return json.dumps({
            "local1": local1,
            "local2": local2,
            "distancia_km": round(distance, 2),
            "coords1": {"lat": location1.latitude, "lon": location1.longitude},
            "coords2": {"lat": location2.latitude, "lon": location2.longitude}
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        LOGGER.error(f"Error calculating distance: {e}", exc_info=True)
        return json.dumps({
            "error": f"Erro ao calcular distância: {str(e)}",
            "distancia_km": None
        }, ensure_ascii=False)


@tool
def pesquisar_informacoes_passeio(
    query: str,
) -> str:
    """
    Ferramenta para pesquisar informações turísticas sobre um passeio.
    Você é obrigatório usar esta ferramenta para obter detalhes sobre o passeio,
    como descrição, horários, preços de ingressos, dicas úteis, etc.

    Args:
        query: requisição de pesquisa (nome do passeio, cidade, custo, ingresso, etc.)

    Returns:
        JSON string com os resultados da pesquisa
    """
    client = get_tavily_client()
    if not client:
        return json.dumps({
            "error": "Tavily não configurado. Configure TAVILY_API_KEY no arquivo .env",
        }, ensure_ascii=False)

    try:
        # Use advanced search with more comprehensive results and raw content
        search_results = client.search(
            query,
            max_results=5,
            search_depth="advanced",
            include_raw_content=True,
            chunks_per_source=1
        )

        tool_output = search_results.get("results", [])
        tool_output = [{"url": res["url"], "title": res["title"], "content": res.get("raw_content", "")} for res in tool_output]

        return json.dumps(tool_output, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Erro ao pesquisar: {str(e)}",
        }, ensure_ascii=False)


@tool
def buscar_imagens_passeio(
    query: str,
    quantidade: int = 5
) -> str:
    """
    Busca imagens de alta qualidade de um passeio turístico usando Tavily.

    Args:
        query: requisição de pesquisa (nome do passeio, cidade, etc.)
        quantidade: Número de imagens a buscar (padrão: 3, mas Tavily retorna o que tiver disponível)

    Returns:
        JSON string com URLs das imagens encontradas
    """
    client = get_tavily_client()
    if not client:
        return json.dumps({
            "error": "Tavily não configurado. Configure TAVILY_API_KEY no arquivo .env",
        }, ensure_ascii=False)

    try:
        # Search with images enabled and get full context for descriptions
        search_data = client.search(
            query,
            max_results=5,
            search_depth="advanced",
            include_images=True,
            include_image_descriptions=True
        )

        images = search_data.get("images", [])

        result = {
            "quantidade_encontrada": len(images),
            "imagens": []
        }


        # Tavily returns image URLs as strings
        for img_object in images[:quantidade]:

            result["imagens"].append({
                "url_regular": img_object["url"],
                "descricao": img_object["description"],
            })

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Erro ao buscar imagens: {str(e)}",
        }, ensure_ascii=False)



# ============================================================================
# Tool Lists for Each Agent
# ============================================================================

# First agent (day organizer) - only needs distance calculation
DAY_ORGANIZER_TOOLS = [
    calcular_distancia_entre_locais,
]

# Second agent (passeio researcher) - needs search and images
PASSEIO_RESEARCHER_TOOLS = [
    pesquisar_informacoes_passeio,
    buscar_imagens_passeio,
]
