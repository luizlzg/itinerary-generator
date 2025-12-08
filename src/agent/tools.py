"""Tools for the multi-agent itinerary generation graph."""
import json
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from typing_extensions import Annotated
from langgraph.types import Command
from src.mcp_client.tavily_client import SimplifiedTavilySearch
from src.mcp_client.docx_client import LocalDocxGenerator
from src.utils.logger import LOGGER
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from sklearn.cluster import KMeans
import numpy as np


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
def pesquisar_informacoes_passeio(
    query: str,
) -> str:
    """
    Ferramenta de busca na web para pesquisar informações.
    Use esta ferramenta quando precisar buscar informações online.

    Args:
        query: requisição de pesquisa

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
            include_raw_content=False,
            chunks_per_source=1
        )

        tool_output = search_results.get("results", [])
        tool_output = [{"url": res["url"], "title": res["title"], "content": res.get("content", "")} for res in tool_output]

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

@tool
def extrair_coordenadas(
    nomes_atracoes: list[str],
    runtime: ToolRuntime,
) -> Command:
    """
    Extrai coordenadas geográficas de uma lista de atrações usando Nominatim.

    IMPORTANTE: Esta ferramenta atualiza o estado do grafo com as coordenadas obtidas.
    Os nomes que você fornecer serão usados EXATAMENTE como estão na API de geocoding.
    Se alguns nomes falharem, a ferramenta retornará quais falharam para você tentar novamente.

    Args:
        nomes_atracoes: Lista com os nomes das atrações (ex: ["Torre Eiffel, Paris", "Museu do Louvre, Paris"])

    Returns:
        Command object that updates state with coordinates and returns success/failure info
    """
    geolocator = get_geolocator()

    # Get current coordinates from state
    current_coordenadas = runtime.state.get("coordenadas_atracoes", {})

    # Process new coordinates
    new_coordenadas = {}
    falhas = []

    for nome in nomes_atracoes:
        try:
            LOGGER.info(f"Geocoding: {nome}")
            location = geolocator.geocode(nome, timeout=10)

            if location:
                new_coordenadas[nome] = {
                    "lat": location.latitude,
                    "lon": location.longitude
                }
                LOGGER.info(f"✓ Sucesso: {nome} -> ({location.latitude}, {location.longitude})")
            else:
                falhas.append(nome)
                LOGGER.warning(f"✗ Falha: Não foi possível encontrar coordenadas para '{nome}'")

        except Exception as e:
            falhas.append(nome)
            LOGGER.error(f"✗ Erro ao geocodificar '{nome}': {e}")

    # Merge new coordinates with existing ones
    coordenadas_atracoes = {**current_coordenadas, **new_coordenadas}

    # Check if all coordinates are obtained (no failures)
    all_coordenadas_obtidas = len(falhas) == 0

    # Create message for the agent
    message_content = json.dumps({
        "falhas": falhas,
        "total_sucesso": len(new_coordenadas),
        "total_falhas": len(falhas),
    }, ensure_ascii=False, indent=2)

    # Return Command to update state
    return Command(
        update={
            "coordenadas_atracoes": coordenadas_atracoes,
            "all_coordenadas_obtidas": all_coordenadas_obtidas,
            "messages": [ToolMessage(content=message_content, tool_call_id=runtime.tool_call_id)]
        }
    )


@tool
def agrupar_atracoes_kmeans(
    runtime: ToolRuntime,
) -> str:
    """
    Agrupa atrações por dia usando algoritmo K-means baseado em proximidade geográfica.
    Calcula as distâncias entre membros de cada cluster.

    IMPORTANTE: Esta ferramenta lê o número de dias e as coordenadas diretamente do estado do grafo.
    Certifique-se de que todas as coordenadas foram obtidas antes de chamar esta ferramenta.

    Returns:
        JSON string com:
        - grupos: dict com {dia: [lista de atrações]}
        - distancias_intra_cluster: dict com distâncias entre membros de cada cluster
    """
    try:
        # Get numero_dias and coordenadas from state
        numero_dias = runtime.state.get("numero_dias")
        coordenadas = runtime.state.get("coordenadas_atracoes", {})
        todas_as_coordenadas_obtidas = runtime.state.get("all_coordenadas_obtidas", False)

        if not todas_as_coordenadas_obtidas:
            return json.dumps({
                "error": "Nem todas as coordenadas foram obtidas. Chame extrair_coordenadas primeiro."
            }, ensure_ascii=False)

        if not numero_dias:
            return json.dumps({
                "error": "Número de dias não encontrado no estado do grafo"
            }, ensure_ascii=False)

        if not coordenadas:
            return json.dumps({
                "error": "Coordenadas não encontradas no estado do grafo. Chame extrair_coordenadas primeiro."
            }, ensure_ascii=False)

        # Preparar dados para K-means
        nomes = list(coordenadas.keys())
        coords_array = np.array([[coords["lat"], coords["lon"]] for coords in coordenadas.values()])

        # Aplicar K-means
        kmeans = KMeans(n_clusters=numero_dias, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(coords_array)

        # Organizar resultados por dia
        grupos = {i: [] for i in range(numero_dias)}
        for idx, cluster_id in enumerate(clusters):
            grupos[cluster_id].append(nomes[idx])

        # Calcular distâncias intra-cluster
        distancias_intra_cluster = {}
        for dia in range(numero_dias):
            atracoes_dia = grupos[dia]
            distancias_dia = {}

            for i, atracao1 in enumerate(atracoes_dia):
                distancias_dia[atracao1] = {}
                coords1 = (coordenadas[atracao1]["lat"], coordenadas[atracao1]["lon"])

                for j, atracao2 in enumerate(atracoes_dia):
                    if i != j:
                        coords2 = (coordenadas[atracao2]["lat"], coordenadas[atracao2]["lon"])
                        dist = geodesic(coords1, coords2).kilometers
                        distancias_dia[atracao1][atracao2] = round(dist, 2)

            distancias_intra_cluster[f"dia_{dia + 1}"] = distancias_dia

        # Formatar grupos com dia começando em 1
        grupos_formatados = {f"dia_{i + 1}": atracoes for i, atracoes in grupos.items()}

        return Command(
            update={
                "clusters": clusters,
                "messages": [ToolMessage(json.dumps({
                    "grupos": grupos_formatados,
                    "distancias_intra_cluster": distancias_intra_cluster,
                }, ensure_ascii=False, indent=2), tool_call_id=runtime.tool_call_id)]
            }
        )

    except Exception as e:
        LOGGER.error(f"Erro ao agrupar atrações: {e}", exc_info=True)
        return json.dumps({
            "error": f"Erro ao agrupar atrações: {str(e)}"
        }, ensure_ascii=False)


# ============================================================================
# Tool Lists for Each Agent
# ============================================================================

# First agent (day organizer) - needs search, coordinate extraction, and K-means clustering
DAY_ORGANIZER_TOOLS = [
    pesquisar_informacoes_passeio,
    extrair_coordenadas,
    agrupar_atracoes_kmeans,
]

# Second agent (passeio researcher) - needs search and images
PASSEIO_RESEARCHER_TOOLS = [
    pesquisar_informacoes_passeio,
    buscar_imagens_passeio,
]
