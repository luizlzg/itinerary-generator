"""
Main CLI entry point for the Itinerary Document Generator.

This is a multi-agent LangGraph system that creates travel itinerary documents
with images, costs, and ticket links in Portuguese Brazilian.

Uses two specialized agents:
1. Day Organizer - organizes passeios by days
2. Passeio Researcher - researches details for each passeio (parallel execution)
"""
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt
from src.agent.graph import build_graph

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()


def check_environment():
    """Check if required environment variables are set."""
    issues = []

    # Check LLM API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        issues.append("❌ Nenhuma chave de API de LLM configurada (OPENAI_API_KEY ou ANTHROPIC_API_KEY)")
    else:
        if os.getenv("ANTHROPIC_API_KEY"):
            console.print("✅ Anthropic API configurada", style="green")
        if os.getenv("OPENAI_API_KEY"):
            console.print("✅ OpenAI API configurada", style="green")

    # Check Tavily (required for web search AND images)
    if not os.getenv("TAVILY_API_KEY"):
        issues.append("⚠️  TAVILY_API_KEY não configurada (necessária para pesquisa web e imagens)")
    else:
        console.print("✅ Tavily configurada (pesquisa web + imagens)", style="green")

    if issues:
        console.print("\n[bold yellow]Avisos de Configuração:[/bold yellow]")
        for issue in issues:
            console.print(f"  {issue}")

        console.print("\n[dim]Configure as chaves no arquivo .env[/dim]")
        console.print("[dim]Exemplo: TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx[/dim]\n")

        if any("❌" in issue for issue in issues):
            console.print("[bold red]Não é possível continuar sem configurar pelo menos um LLM.[/bold red]")
            return False

    return True


def get_roteiro_input() -> str:
    """Get passeios list from user."""
    console.print("\n[bold cyan]Liste os passeios/atrações que deseja visitar:[/bold cyan]")
    console.print("[dim]Você pode listar em qualquer formato.[/dim]")
    console.print()
    console.print("[dim]Exemplo:[/dim]")
    console.print("[dim]   - Torre Eiffel e arredores (entrar, trocadero, ruas para fotos)[/dim]")
    console.print("[dim]   - Museu do Louvre[/dim]")
    console.print("[dim]   - Palácio de Versalhes[/dim]")
    console.print()
    console.print("[dim]Digite 'FIM' em uma linha separada quando terminar.[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "FIM":
                break
            lines.append(line)
        except EOFError:
            break

    return "\n".join(lines).strip()


def get_preferences_input() -> str:
    """Get user preferences including age, organization preferences, etc."""
    console.print("\n[bold cyan]Preferências (opcional):[/bold cyan]")
    console.print("[dim]Pode incluir: idade, preferências de organização dos dias, etc.[/dim]")
    console.print()
    console.print("[dim]Exemplo:[/dim]")
    console.print("[dim]   'Tenho 25 anos. No primeiro dia prefiro museus.'[/dim]")
    console.print()
    console.print("[dim]Digite 'FIM' em uma linha separada quando terminar (ou deixe vazio e digite FIM).[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "FIM":
                break
            lines.append(line)
        except EOFError:
            break

    return "\n".join(lines).strip()


def get_numero_dias() -> int:
    """Get number of days for the itinerary."""
    while True:
        try:
            dias = Prompt.ask("\n[bold cyan]Quantos dias de roteiro?[/bold cyan]", default="3")
            numero = int(dias)
            if numero > 0:
                return numero
            else:
                console.print("[yellow]Por favor, entre com um número positivo.[/yellow]")
        except ValueError:
            console.print("[yellow]Por favor, entre com um número válido.[/yellow]")


def main():
    """Main CLI function."""

    # Check environment
    if not check_environment():
        sys.exit(1)

    console.print()

    # Initialize graph
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            console.print("[dim]Inicializando sistema multi-agente com Claude Sonnet 4...[/dim]")
            graph = build_graph()
        elif os.getenv("OPENAI_API_KEY"):
            console.print("[dim]Inicializando sistema multi-agente com GPT-4...[/dim]")
            graph = build_graph()
        else:
            console.print("[bold red]Erro: Nenhum LLM configurado![/bold red]")
            sys.exit(1)

        console.print("✅ Sistema multi-agente inicializado com sucesso!\n", style="green")
        console.print("[dim]  → Agente 1: Organizador de Dias (usa distância geográfica)[/dim]")
        console.print("[dim]  → Agente 2: Pesquisador de Passeios (execução paralela)[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]Erro ao inicializar sistema: {e}[/bold red]")
        sys.exit(1)

    # Main interaction loop
    while True:
        console.print("[bold]Escolha uma opção:[/bold]")
        console.print("1. Gerar roteiro de viagem")
        console.print("2. Sair")

        opcao = Prompt.ask("\nOpção", choices=["1", "2"], default="1")

        if opcao == "2":
            console.print("\n[bold green]Até logo! Boa viagem! 🌍✈️[/bold green]")
            break

        elif opcao == "1":
            # Generate itinerary mode
            console.print("\n" + "="*60)
            console.print("[bold bright_blue]Modo: Geração de Roteiro por Dias[/bold bright_blue]")
            console.print("="*60)

            # Get passeios list
            roteiro_input = get_roteiro_input()

            if not roteiro_input.strip():
                console.print("[yellow]Nenhuma informação fornecida. Tente novamente.[/yellow]\n")
                continue

            # Get preferences (optional)
            preferences_input = get_preferences_input()

            # Get number of days
            numero_dias = get_numero_dias()

            # Generate itinerary using graph
            console.print("\n[bold yellow]Gerando roteiro com sistema multi-agente... Isso pode levar alguns minutos.[/bold yellow]")
            console.print("[dim]Etapas:[/dim]")
            console.print("[dim]  1. Agente 1: Organizar passeios por dia (baseado em preferências ou distância)[/dim]")
            console.print("[dim]  2. Agente 2: Pesquisar cada passeio em paralelo (informações + imagens)[/dim]")
            console.print("[dim]  3. Gerar documento DOCX formatado[/dim]\n")

            try:
                # Initialize graph state
                initial_state = {
                    "user_input": roteiro_input,
                    "numero_dias": numero_dias,
                    "preferences_input": preferences_input,
                    "document_title": "",
                    "passeios_by_day": [],
                    "processed_passeios": [],
                    "total_cost": 0.0,
                    "final_document_path": "",
                }

                config = {
                    "recursion_limit": 1000,
                }

                # Invoke graph
                console.print("[dim]Executando workflow multi-agente...[/dim]\n")
                final_state = graph.invoke(initial_state, config=config)

                # Display result
                console.print("\n" + "="*60)
                if final_state.get("final_document_path"):
                    console.print(f"[bold green]✅ Roteiro de {numero_dias} dias gerado com sucesso![/bold green]")
                    console.print("="*60)
                    console.print(f"\n[bold]Arquivo:[/bold] {final_state['final_document_path']}")
                    console.print(f"[bold]Custo total estimado:[/bold] €{final_state.get('total_cost', 0.0):.2f}")
                else:
                    console.print("[bold yellow]⚠️  Roteiro processado mas documento não foi gerado[/bold yellow]")
                    console.print("="*60)
                console.print()

            except Exception as e:
                console.print(f"\n[bold red]Erro ao gerar roteiro: {e}[/bold red]\n")
                import traceback
                traceback.print_exc()

        else:
            console.print("[yellow]Opção inválida. Tente novamente.[/yellow]\n")

        console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Programa interrompido pelo usuário.[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Erro fatal: {e}[/bold red]")
        sys.exit(1)
