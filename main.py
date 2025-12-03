"""
Main CLI entry point for the Itinerary Document Generator Agent.

This is a LangGraph ReAct agent that creates travel itinerary documents
with images, costs, and ticket links in Portuguese Brazilian.
"""
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt
from src.agent.agent_definition import ItineraryAgent

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
    """Get complete itinerary input from user (passeios, age, preferences - all in one)."""
    console.print("\n[bold cyan]Descreva seu roteiro de viagem:[/bold cyan]")
    console.print("[dim]Você pode incluir tudo em um único texto:[/dim]")
    console.print("[dim]  - Lista de passeios/atrações[/dim]")
    console.print("[dim]  - Sua idade (para recomendações de ingresso)[/dim]")
    console.print("[dim]  - Preferências de organização (opcional)[/dim]")
    console.print()
    console.print("[dim]Exemplo:[/dim]")
    console.print("[dim]  'Tenho 25 anos. Quero visitar:[/dim]")
    console.print("[dim]   - Torre Eiffel e arredores (entrar, trocadero, ruas para fotos)[/dim]")
    console.print("[dim]   - Museu do Louvre[/dim]")
    console.print("[dim]   - Versalhes[/dim]")
    console.print("[dim]   No primeiro dia prefiro museus'[/dim]")
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

    # Initialize agent
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            console.print("[dim]Inicializando agente com Claude Sonnet 4...[/dim]")
            agent = ItineraryAgent(
                model_provider="anthropic",
                model_name="claude-sonnet-4-5-20250929"
            )
        elif os.getenv("OPENAI_API_KEY"):
            console.print("[dim]Inicializando agente com GPT-4...[/dim]")
            agent = ItineraryAgent(
                model_provider="openai",
                model_name="gpt-5.1"
            )
        else:
            console.print("[bold red]Erro: Nenhum LLM configurado![/bold red]")
            sys.exit(1)

        console.print("✅ Agente inicializado com sucesso!\n", style="green")

    except Exception as e:
        console.print(f"[bold red]Erro ao inicializar agente: {e}[/bold red]")
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

            # Get complete input (passeios, age, preferences - all in one)
            roteiro_input = get_roteiro_input()

            if not roteiro_input.strip():
                console.print("[yellow]Nenhuma informação fornecida. Tente novamente.[/yellow]\n")
                continue

            # Get number of days
            numero_dias = get_numero_dias()

            # Generate itinerary
            console.print("\n[bold yellow]Gerando roteiro organizado por dias... Isso pode levar alguns minutos.[/bold yellow]")
            console.print("[dim]O agente vai:[/dim]")
            console.print("[dim]  1. Analisar sua idade e preferências[/dim]")
            console.print("[dim]  2. Pesquisar informações e imagens para cada passeio[/dim]")
            console.print("[dim]  3. Calcular distâncias e organizar os {0} dias[/dim]".format(numero_dias))
            console.print("[dim]  4. Gerar o documento formatado[/dim]\n")

            try:
                # Call with verbose=True to see progress
                _ = agent.generate_itinerary(
                    passeios_input=roteiro_input,
                    numero_dias=numero_dias,
                    verbose=True  # Show progress
                )

                # Display result
                console.print("\n" + "="*60)
                console.print(f"[bold green]✅ Roteiro de {numero_dias} dias gerado com sucesso![/bold green]")
                console.print("="*60)
                console.print()

            except Exception as e:
                console.print(f"\n[bold red]Erro ao gerar roteiro: {e}[/bold red]\n")

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
