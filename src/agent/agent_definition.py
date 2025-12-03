"""
LangGraph ReAct agent for itinerary document generation.

Built with LangChain 1.0:
- Uses create_agent from langchain.agents
- Compatible with langchain>=1.0.0, langchain-core>=1.0.0
- Portuguese Brazilian language support
"""
import json
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain.agents import create_agent
from src.agent.tools import ITINERARY_TOOLS
from src.agent.prompts import ITINERARY_SYSTEM_PROMPT
from src.utils.logger import LOGGER, LOG_FILE


class ItineraryAgent:
    """
    ReAct agent for generating travel itinerary documents.

    Built with LangChain 1.0 and LangGraph:
    - Uses TypedDict state schema (v1.0 compliant)
    - Custom graph implementation
    - Portuguese Brazilian language support
    - Integrates with MCP servers for web search, images, and document generation
    """

    def __init__(self, model_provider: str = "anthropic", model_name: str = "claude-sonnet-4-20250514"):
        """
        Initialize the itinerary generation agent.

        Args:
            model_provider: LLM provider ('openai' or 'anthropic')
            model_name: Model name to use
        """
        self.model_provider = model_provider
        self.model_name = model_name
        self.llm = self._initialize_llm()
        self.agent = self._create_agent()

    def _initialize_llm(self):
        """Initialize the LLM based on provider."""
        if self.model_provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.model_name,
                temperature=0,
                streaming=True
            )
        elif self.model_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.model_name,
                temperature=0,
                streaming=True,
                max_tokens=32768
            )
        else:
            raise ValueError(f"Unsupported model provider: {self.model_provider}")

    def _create_agent(self):
        """Create the ReAct agent with tools and prompts."""
        # Use create_agent from LangChain 1.0
        return create_agent(
            model=self.llm,
            tools=ITINERARY_TOOLS,
            system_prompt=ITINERARY_SYSTEM_PROMPT
        )

    def generate_itinerary(
        self,
        passeios_input: str,
        numero_dias: int,
        thread_id: str = "default",
        verbose: bool = True
    ) -> str:
        """
        Generate a complete itinerary document organized by days.

        Args:
            passeios_input: User input with list of passeios (attractions) - any format accepted
            numero_dias: Number of days for the itinerary
            thread_id: Thread ID for conversation tracking
            verbose: If True, print progress messages

        """

        message = f"""Gere um roteiro de viagem completo ORGANIZADO POR DIAS baseado na seguinte entrada do usuário:

{passeios_input}

Número de dias: {numero_dias}

Por favor, siga este fluxo de trabalho:

1. **Para CADA passeio/atração mencionado**:
   - Pesquise informações detalhadas usando 'pesquisar_informacoes_passeio'
   - FOQUE em DESCREVER o que é cada passeio, o que se pode fazer lá, por que é interessante
   - Para custos: explique claramente se é GRÁTIS ou PAGO, e se pago, quanto custa e o que está incluso
   - Links são apenas para COMPRA DE INGRESSOS, não para descrições
   - Busque 2-3 imagens de alta qualidade usando 'buscar_imagens_passeio'

2. **Organize os passeios por dias** (VOCÊ decide a organização):
   - Se houver preferências do usuário: analise você mesmo e organize semanticamente
   - Se NÃO houver preferências: use 'calcular_distancia_entre_locais' para agrupar passeios próximos
   - IMPORTANTE: Ao compilar cada PasseioInfo, ADICIONE o campo "dia_numero" (1, 2, 3, etc.)

3. **Compile todos os dados** em uma lista de PasseioInfo com o campo "dia_numero" preenchido

4. **Gere o documento final**:
   - Use 'gerar_documento_roteiro_por_dias' passando:
     * O título do documento
     * A lista compilada de passeios (com dia_numero em cada um)
   - O documento terá estrutura de dias, com cada dia como heading principal e cada passeio como subheading

IMPORTANTE:
- Descreva bem cada atração ao invés de apenas colocar links. O usuário quer entender O QUE É cada lugar.
- VOCÊ é responsável por decidir qual passeio vai em qual dia
- O documento final deve ter {numero_dias} dias organizados
"""

        # Invoke the graph with increased recursion limit and debug output
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100  # Increased from default 25
        }

        if verbose:
            print(f"\n🔄 Iniciando processamento do roteiro...")
            print(f"📝 Log file: {LOG_FILE}")
            print("📍 Acompanhe o progresso abaixo:\n")

        step_count = 0
        logged_messages = []

        try:
            for event in self.agent.stream(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                stream_mode="values"
            ):
                step_count += 1

                if "messages" in event and event["messages"]:
                    # Log ALL new messages (when tools run in parallel, there will be multiple messages)
                    messages = event["messages"]

                    for msg in messages:
                        if msg not in logged_messages:
                            logged_messages.append(msg)
                            LOGGER.info(msg.pretty_repr())

                    # For console output, use the last message
                    last_message = messages[-1]

                    # Console output for user (verbose mode)
                    if verbose:
                        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                            for tool_call in last_message.tool_calls:
                                tool_name = tool_call.get('name', 'unknown')
                                tool_args = tool_call.get('args', {})

                                if tool_name == 'pesquisar_informacoes_passeio':
                                    print(f"  🔍 Pesquisando: {tool_args.get('query', '?')}")
                                elif tool_name == 'buscar_imagens_passeio':
                                    print(f"  📸 Buscando imagens: {tool_args.get('query', '?')}")
                                elif tool_name == 'gerar_documento_roteiro_por_dias':
                                    print(f"  📄 Gerando documento...")
                                elif tool_name == 'calcular_distancia_entre_locais':
                                    print(f"  📏 Calculando distâncias entre locais: '{tool_args.get('local1', '?')}' e '{tool_args.get('local2', '?')}'...")

                        elif isinstance(last_message, ToolMessage):
                            # Check for errors
                            try:
                                content_json = json.loads(last_message.content)
                                if "error" in content_json:
                                    print(f"  ⚠️  Erro na ferramenta: {content_json['error']}")
                            except:
                                pass

                        elif isinstance(last_message, AIMessage):
                            if hasattr(last_message, 'content') and last_message.content and not hasattr(last_message, 'tool_calls'):
                                preview = str(last_message.content)[:100]
                                if len(preview) > 0:
                                    print(f"  💭 Agente: {preview}...")

        except Exception as e:
            LOGGER.error(f"FATAL ERROR: {str(e)}", exc_info=True)
            if verbose:
                print(f"\n❌ Erro durante execução: {e}")
                print(f"📝 Veja detalhes completos em: {LOG_FILE}")
            raise

        LOGGER.info(f"\n{'='*60}")
        LOGGER.info(f"COMPLETED IN {step_count} STEPS")
        LOGGER.info(f"{'='*60}")

        if verbose:
            print(f"\n✅ Processamento concluído em {step_count} passos!")
            print(f"📝 Log completo salvo em: {LOG_FILE}\n")

