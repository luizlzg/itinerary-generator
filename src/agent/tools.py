"""Tools for the itinerary document generation agent."""
import json
import os
from langchain_core.tools import tool
from src.mcp_client.tavily_client import SimplifiedTavilySearch
from src.mcp_client.docx_client import LocalDocxGenerator
from src.utils.logger import LOGGER
from typing import TypedDict, List, Optional, Dict, Any
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

class ImageInfo(TypedDict):
    id: str
    descricao: str
    url_regular: str

class IngressoInfo(TypedDict):
    titulo: str
    conteudo: str
    url: str

class LinkInfo(TypedDict):
    titulo: str
    url: str

class PasseioInfo(TypedDict):
    nome: str
    descricao: str
    imagens: List[ImageInfo]
    informacoes_ingresso: List[IngressoInfo]
    links_uteis: List[LinkInfo]
    custo_estimado: float
    dia_numero: int  # Which day this passeio belongs to


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


@tool(return_direct=True)
def gerar_documento_roteiro_por_dias(
    titulo_documento: str,
    passeios_dados: List[PasseioInfo],
) -> str:
    """
    Gera um documento formatado com o roteiro de viagem organizado por dias.

    IMPORTANTE: Este é o ÚLTIMO passo. Só chame esta função DEPOIS de ter pesquisado
    informações e imagens para TODOS os passeios.

    CRÍTICO: Esta função requer DOIS parâmetros OBRIGATÓRIOS:
    1. titulo_documento (string)
    2. passeios_dados (lista/array de objetos PasseioInfo)

    Args:
        titulo_documento: Título do roteiro (ex: "Roteiro de Viagem - Paris - 3 Dias")
        passeios_dados: OBRIGATÓRIO - Lista/array de PasseioInfo com todos os passeios compilados.
            Cada passeio DEVE ter o campo "dia_numero" preenchido (1, 2, 3, etc.)
            Exemplo:
            [
                {"nome": "Torre Eiffel", "descricao": "...", "imagens": [...], "dia_numero": 1, "custo_estimado": 26.10, ...},
                {"nome": "Louvre", "descricao": "...", "imagens": [...], "dia_numero": 1, "custo_estimado": 17.00, ...},
                {"nome": "Versalhes", "descricao": "...", "imagens": [...], "dia_numero": 2, "custo_estimado": 19.50, ...}
            ]

    Returns:
        JSON string com informações sobre o documento criado (caminho do arquivo)

    NUNCA ESQUEÇA: Você DEVE passar passeios_dados como segundo parâmetro!
    Chamada CORRETA:
        gerar_documento_roteiro_por_dias(
            titulo_documento="Roteiro Paris - 3 Dias",
            passeios_dados=[{...}, {...}, {...}]
        )

    Chamada ERRADA (vai falhar):
        gerar_documento_roteiro_por_dias(titulo_documento="Roteiro Paris - 3 Dias")
    """
    try:
        if not passeios_dados or len(passeios_dados) == 0:
            return json.dumps({
                "error": "Lista de passeios está vazia!",
                "sucesso": False
            }, ensure_ascii=False)

        LOGGER.info(f"Processing {len(passeios_dados)} passeios for document")

        # Group passeios by day
        passeios_por_dia = {}
        for passeio in passeios_dados:
            if not isinstance(passeio, dict):
                LOGGER.warning(f"Passeio is not a dict: {type(passeio).__name__}")
                continue

            dia_numero = passeio.get("dia_numero", 1)
            if dia_numero not in passeios_por_dia:
                passeios_por_dia[dia_numero] = []
            passeios_por_dia[dia_numero].append(passeio)

        # Prepare content blocks for document
        content_blocks = []
        custo_total = 0

        # Add each day
        for dia_numero in sorted(passeios_por_dia.keys()):
            passeios = passeios_por_dia[dia_numero]

            # Add day heading
            content_blocks.append({
                "type": "heading",
                "text": f"Dia {dia_numero}",
                "level": 1
            })

            # Add each passeio under this day
            for passeio in passeios:
                nome = passeio.get("nome", "Passeio sem nome")
                descricao = passeio.get("descricao", "")

                LOGGER.info(f"Processing passeio: {nome} (Dia {dia_numero})")

                # Add passeio as subheading
                content_blocks.append({
                    "type": "heading",
                    "text": nome,
                    "level": 2
                })

                # Add description
                if descricao:
                    content_blocks.append({
                        "type": "paragraph",
                        "text": descricao
                    })

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

                    content_blocks.append({
                        "type": "image",
                        "url": url,
                        "id": img.get("id", f"img_{idx}")
                    })

                # Add ticket/cost info
                info_ingresso = passeio.get("informacoes_ingresso", [])
                if not isinstance(info_ingresso, list):
                    info_ingresso = []

                if info_ingresso:
                    content_blocks.append({
                        "type": "heading",
                        "text": "Informações de Ingresso",
                        "level": 3
                    })

                    for info in info_ingresso:
                        if not isinstance(info, dict):
                            continue

                        conteudo = info.get('conteudo', '')
                        if conteudo:
                            content_blocks.append({
                                "type": "paragraph",
                                "text": f"• {conteudo}"
                            })

                        url = info.get("url")
                        if url:
                            content_blocks.append({
                                "type": "paragraph",
                                "text": f"Link: {url}"
                            })

                # Add useful links
                links = passeio.get("links_uteis", [])
                if not isinstance(links, list):
                    links = []

                if links:
                    content_blocks.append({
                        "type": "heading",
                        "text": "Links Úteis",
                        "level": 3
                    })

                    link_items = []
                    for link in links:
                        if isinstance(link, dict):
                            titulo = link.get('titulo', 'Link')
                            url = link.get('url', '')
                            if url:
                                link_items.append(f"{titulo}: {url}")

                    if link_items:
                        content_blocks.append({
                            "type": "bullet_list",
                            "items": link_items
                        })

                # Try to extract cost
                custo = passeio.get("custo_estimado", 0)
                if custo > 0:
                    custo_total += custo

            # Add spacing between days
            content_blocks.append({
                "type": "paragraph",
                "text": ""
            })

        # Add cost summary
        if custo_total > 0:
            content_blocks.append({
                "type": "heading",
                "text": "Resumo de Custos",
                "level": 1
            })
            content_blocks.append({
                "type": "paragraph",
                "text": f"Custo total estimado: €{custo_total:.2f}",
                "bold": True
            })

        LOGGER.info(f"Prepared {len(content_blocks)} content blocks for document")

        # Creating local DOCX
        LOGGER.info("Creating local DOCX document...")
        try:
            generator = get_docx_generator()
            LOGGER.info("DOCX generator initialized")

            LOGGER.info(f"Calling create_document with {len(content_blocks)} blocks")
            file_path = generator.create_document(
                title=titulo_documento,
                content_blocks=content_blocks
            )

            LOGGER.info(f"Document created successfully at: {file_path}")

            if not file_path or not os.path.exists(file_path):
                LOGGER.error(f"Document file does not exist: {file_path}")
                return json.dumps({
                    "error": f"Documento foi criado mas arquivo não foi encontrado: {file_path}",
                    "sucesso": False
                }, ensure_ascii=False)

            num_dias = len(passeios_por_dia)
            return json.dumps({
                "sucesso": True,
                "tipo": "docx_local",
                "caminho_arquivo": file_path,
                "mensagem": f"Documento DOCX criado localmente com {num_dias} dias: {file_path}"
            }, ensure_ascii=False, indent=2)

        except Exception as docx_error:
            LOGGER.error(f"DOCX creation failed: {docx_error}", exc_info=True)
            return json.dumps({
                "error": f"Erro ao criar DOCX: {str(docx_error)}",
                "sucesso": False,
                "detalhes": str(docx_error)
            }, ensure_ascii=False)

    except Exception as e:
        LOGGER.error(f"Document generation failed: {e}", exc_info=True) 
        return json.dumps({
            "error": f"Erro ao gerar documento: {str(e)}",
            "sucesso": False,
            "tipo_erro": type(e).__name__
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
        search_results = client.search(query, max_results=3)

        return json.dumps(search_results.get("results", []), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Erro ao pesquisar: {str(e)}",
        }, ensure_ascii=False)


@tool
def buscar_imagens_passeio(
    query: str,
    quantidade: int = 3
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
        # Search with images enabled
        search_data = client.search(query, max_results=3, include_images=True)

        images = search_data.get("images", [])

        result = {
            "quantidade_encontrada": len(images),
            "imagens": []
        }

        # Tavily returns image URLs as strings
        for image_url in images[:quantidade]:
            result["imagens"].append({
                "url_regular": image_url,
                "url_pequena": image_url,
                "descricao": f"Imagem relacionada a '{query}'",
            })

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Erro ao buscar imagens: {str(e)}",
        }, ensure_ascii=False)



# List of all tools for the itinerary agent
ITINERARY_TOOLS = [
    pesquisar_informacoes_passeio,
    buscar_imagens_passeio,
    calcular_distancia_entre_locais,
    gerar_documento_roteiro_por_dias,
]
