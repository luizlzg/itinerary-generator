"""
Main CLI entry point for the Itinerary Document Generator.

This is a multi-agent LangGraph system that creates travel itinerary documents
with images, costs, and ticket links in the user's preferred language.

Uses two specialized agents:
1. Day Organizer - organizes attractions by days using K-means clustering
2. Attraction Researcher - researches details for each attraction (parallel execution)
"""
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt, Confirm
from src.agent.graph import build_graph
from src.mcp_client.email_mcp_client import check_email_config, send_itinerary_email_sync
from src.utils.observability import setup_langsmith_tracing

# Load environment variables
load_dotenv()

# Setup LangSmith tracing (if configured)
tracing_enabled = setup_langsmith_tracing()

# Initialize Rich console
console = Console()

# Supported languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "pt-br": "Portuguese (Brazil)",
    "es": "Spanish",
    "fr": "French",
}


def check_environment():
    """Check if required environment variables are set."""
    issues = []

    # Check LLM API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        issues.append("No LLM API key configured (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    else:
        if os.getenv("ANTHROPIC_API_KEY"):
            console.print("Anthropic API configured", style="green")
        if os.getenv("OPENAI_API_KEY"):
            console.print("OpenAI API configured", style="green")

    # Check Tavily (required for web search AND images)
    if not os.getenv("TAVILY_API_KEY"):
        issues.append("TAVILY_API_KEY not configured (required for web search and images)")
    else:
        console.print("Tavily configured (web search + images)", style="green")

    # Check LangSmith tracing
    if tracing_enabled:
        project = os.getenv("LANGSMITH_PROJECT", "itinerary-generator")
        console.print(f"LangSmith tracing enabled (project: {project})", style="green")
    else:
        console.print("[dim]LangSmith tracing disabled (optional)[/dim]")

    if issues:
        console.print("\n[bold yellow]Configuration Warnings:[/bold yellow]")
        for issue in issues:
            console.print(f"  {issue}")

        console.print("\n[dim]Configure the keys in the .env file[/dim]")
        console.print("[dim]Example: TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx[/dim]\n")

        if any("No LLM API key" in issue for issue in issues):
            console.print("[bold red]Cannot continue without configuring at least one LLM.[/bold red]")
            return False

    return True


def get_attractions_input() -> str:
    """Get attractions list from user."""
    console.print("\n[bold cyan]List the attractions you want to visit:[/bold cyan]")
    console.print("[dim]You can list in any format.[/dim]")
    console.print()
    console.print("[dim]Example:[/dim]")
    console.print("[dim]   - Eiffel Tower and surroundings (climb, trocadero, photo streets)[/dim]")
    console.print("[dim]   - Louvre Museum[/dim]")
    console.print("[dim]   - Palace of Versailles[/dim]")
    console.print()
    console.print("[dim]Type 'END' on a separate line when finished.[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    return "\n".join(lines).strip()


def get_preferences_input() -> str:
    """Get user preferences including age, organization preferences, etc."""
    console.print("\n[bold cyan]Preferences (optional):[/bold cyan]")
    console.print("[dim]Can include: age, day organization preferences, etc.[/dim]")
    console.print()
    console.print("[dim]Example:[/dim]")
    console.print("[dim]   'I'm 25 years old. On the first day I prefer museums.'[/dim]")
    console.print()
    console.print("[dim]Type 'END' on a separate line when finished (or leave empty and type END).[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    return "\n".join(lines).strip()


def get_num_days() -> int:
    """Get number of days for the itinerary."""
    while True:
        try:
            days = Prompt.ask("\n[bold cyan]How many days for the itinerary?[/bold cyan]", default="3")
            number = int(days)
            if number > 0:
                return number
            else:
                console.print("[yellow]Please enter a positive number.[/yellow]")
        except ValueError:
            console.print("[yellow]Please enter a valid number.[/yellow]")


def get_language() -> str:
    """Get desired language for the output document."""
    console.print("\n[bold cyan]Select the output language for the document:[/bold cyan]")
    for code, name in SUPPORTED_LANGUAGES.items():
        console.print(f"  {code}: {name}")

    while True:
        lang = Prompt.ask(
            "\n[bold cyan]Language code[/bold cyan]",
            default="en",
            choices=list(SUPPORTED_LANGUAGES.keys())
        )
        if lang in SUPPORTED_LANGUAGES:
            console.print(f"[dim]Selected: {SUPPORTED_LANGUAGES[lang]}[/dim]")
            return lang
        console.print("[yellow]Please select a valid language code.[/yellow]")


def main():
    """Main CLI function."""

    # Check environment
    if not check_environment():
        sys.exit(1)

    console.print()

    # Initialize graph
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            console.print("[dim]Initializing multi-agent system with Claude Sonnet 4...[/dim]")
            graph = build_graph()
        elif os.getenv("OPENAI_API_KEY"):
            console.print("[dim]Initializing multi-agent system with GPT-4...[/dim]")
            graph = build_graph()
        else:
            console.print("[bold red]Error: No LLM configured![/bold red]")
            sys.exit(1)

        console.print("Multi-agent system initialized successfully!\n", style="green")
        console.print("[dim]  -> Agent 1: Day Organizer (uses geographic distance)[/dim]")
        console.print("[dim]  -> Agent 2: Attraction Researcher (parallel execution)[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]Error initializing system: {e}[/bold red]")
        sys.exit(1)

    # Main interaction loop
    while True:
        console.print("[bold]Choose an option:[/bold]")
        console.print("1. Generate travel itinerary")
        console.print("2. Exit")

        option = Prompt.ask("\nOption", choices=["1", "2"], default="1")

        if option == "2":
            console.print("\n[bold green]Goodbye! Have a great trip![/bold green]")
            break

        elif option == "1":
            # Generate itinerary mode
            console.print("\n" + "="*60)
            console.print("[bold bright_blue]Mode: Day-by-Day Itinerary Generation[/bold bright_blue]")
            console.print("="*60)

            # Get attractions list
            attractions_input = get_attractions_input()

            if not attractions_input.strip():
                console.print("[yellow]No information provided. Please try again.[/yellow]\n")
                continue

            # Get preferences (optional)
            preferences_input = get_preferences_input()

            # Get number of days
            num_days = get_num_days()

            # Get output language
            language = get_language()

            # Generate itinerary using graph
            console.print("\n[bold yellow]Generating itinerary with multi-agent system... This may take a few minutes.[/bold yellow]")
            console.print("[dim]Steps:[/dim]")
            console.print("[dim]  1. Agent 1: Organize attractions by day (based on preferences or distance)[/dim]")
            console.print("[dim]  2. Agent 2: Research each attraction in parallel (info + images)[/dim]")
            console.print("[dim]  3. Generate formatted DOCX document[/dim]\n")

            try:
                # Initialize graph state
                initial_state = {
                    "user_input": attractions_input,
                    "num_days": num_days,
                    "preferences_input": preferences_input,
                    "language": language,
                    "document_title": "",
                    "attractions_by_day": [],
                    "processed_attractions": [],
                    "clusters": [],
                    "attraction_coordinates": {},
                    "final_document_path": "",
                    "costs_by_currency": {},
                    "invalid_input": False,
                    "error_message": "",
                }

                config = {
                    "recursion_limit": 1000,
                }

                # Invoke graph
                console.print("[dim]Executing multi-agent workflow...[/dim]\n")
                final_state = graph.invoke(initial_state, config=config)

                # Display result
                console.print("\n" + "="*60)
                if final_state.get("invalid_input"):
                    # Input was invalid - show error message
                    error_message = final_state.get("error_message", "Invalid input.")
                    console.print("[bold yellow]Could not generate itinerary[/bold yellow]")
                    console.print("="*60)
                    console.print(f"\n{error_message}\n")
                elif final_state.get("final_document_path"):
                    document_path = final_state['final_document_path']
                    console.print(f"[bold green]{num_days}-day itinerary generated successfully![/bold green]")
                    console.print("="*60)
                    console.print(f"\n[bold]File:[/bold] {document_path}")

                    # Show cost summary if available
                    costs = final_state.get("costs_by_currency", {})
                    if costs:
                        console.print("\n[bold]Estimated costs (per person):[/bold]")
                        for currency, total in costs.items():
                            console.print(f"  {currency}: {total:.2f}")

                    # Offer to send via email
                    console.print()
                    send_email = Confirm.ask(
                        "[bold cyan]Would you like to send the itinerary via email?[/bold cyan]",
                        default=False
                    )

                    if send_email:
                        # Check email configuration
                        email_config = check_email_config()

                        if not email_config["configured"]:
                            console.print("\n[yellow]Email not configured.[/yellow]")
                            console.print(f"[dim]{email_config['message']}[/dim]")
                            if email_config.get("help"):
                                console.print(f"\n[dim]{email_config['help']}[/dim]")
                        else:
                            # Get recipient email(s)
                            console.print("[dim]Tip: Separate multiple emails with commas[/dim]")
                            recipient = Prompt.ask(
                                "\n[bold cyan]Recipient email address(es)[/bold cyan]",
                                default="",
                            )

                            # Validate at least one valid email
                            emails = [e.strip() for e in recipient.split(",") if e.strip() and "@" in e.strip()]
                            if emails:
                                # Extract destination from document title or user input
                                destination = final_state.get("document_title", "")
                                if not destination:
                                    destination = attractions_input.split("\n")[0][:30]

                                emails_str = ", ".join(emails)
                                console.print(f"\n[dim]Sending to {emails_str}...[/dim]")

                                result = send_itinerary_email_sync(
                                    document_path=document_path,
                                    to_emails=emails,
                                    destination=destination,
                                    num_days=num_days,
                                    language=language,
                                )

                                if result.get("success"):
                                    num_recipients = len(result.get("recipients", emails))
                                    if num_recipients > 1:
                                        console.print(f"[bold green]Email sent successfully to {num_recipients} recipients![/bold green]")
                                    else:
                                        console.print("[bold green]Email sent successfully![/bold green]")
                                else:
                                    console.print(f"[bold red]Failed to send email: {result.get('error')}[/bold red]")
                                    if result.get("help"):
                                        console.print(f"[dim]{result['help']}[/dim]")
                            else:
                                console.print("[yellow]No valid email address provided.[/yellow]")
                else:
                    console.print("[bold yellow]Itinerary processed but document was not generated[/bold yellow]")
                    console.print("="*60)
                console.print()

            except Exception as e:
                console.print(f"\n[bold red]Error generating itinerary: {e}[/bold red]\n")
                import traceback
                traceback.print_exc()

        else:
            console.print("[yellow]Invalid option. Please try again.[/yellow]\n")

        console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Program interrupted by user.[/bold yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error: {e}[/bold red]")
        sys.exit(1)
