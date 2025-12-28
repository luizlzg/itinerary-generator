# Itinerary Generator

A multi-agent LangGraph system that transforms a list of tourist attractions into comprehensive day-by-day travel itineraries with geographic optimization, detailed research, and professional DOCX document generation.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![LangChain](https://img.shields.io/badge/langchain-1.0-purple)
![LangGraph](https://img.shields.io/badge/langgraph-1.0+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## Features

- **Intelligent Day Organization**: K-means clustering groups attractions by geographic proximity
- **Constrained Clustering**: Set min/max attractions per day while keeping the number of days fixed
- **User Approval Flow**: Review and adjust K-means organized itineraries before proceeding
- **Address-Based Geocoding**: Searches for official addresses before geocoding to ensure accuracy
- **Multilingual Output**: Preserves attraction names in user's original language on maps and documents
- **User Preference Handling**: Supports isolated days, specific day assignments, or flexible grouping
- **Parallel Research**: Multiple agent instances research attractions concurrently
- **Rich Attraction Details**: Descriptions, opening hours, costs, ticket links, and images
- **Professional DOCX Output**: Styled documents with visual route maps
- **Multi-Language Support**: English, Portuguese (BR), Spanish, French
- **Email Delivery**: Send generated itineraries via SMTP

## Architecture

The system uses LangGraph to orchestrate specialized agents in a pipeline:

```
User Input (attractions list)
         │
         ▼
┌─────────────────────────────┐
│  Day Organizer Agent        │
│  1. Search official address │  ← Uses web search for accurate geocoding
│  2. Build name→address map  │  ← Preserves user's language in keys
│  3. Extract coordinates     │
│  4. K-means clustering      │  ← Supports min/max constraints
│  5. Request user approval   │  ← Interactive review for flexible attractions
│  6. Respect user prefs      │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Attraction Researcher      │  Parallel instances (one per day)
│  Agents                     │  research details, images, costs
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Document Builder           │  Generates DOCX with maps, images,
│                             │  and cost summaries
└─────────────────────────────┘
         │
         ▼
    DOCX Output + Optional Email
```

## Tech Stack

- **LangChain 1.0** / **LangGraph** - Agent orchestration with TypedDict state schemas
- **Claude Sonnet 4.5** (Anthropic) or **GPT-4** (OpenAI) - LLM providers
- **Tavily MCP** - Web search and image retrieval
- **GeoPy** - Geocoding via Nominatim
- **scikit-learn** / **k-means-constrained** - K-means clustering with size constraints
- **GeoPandas / Matplotlib** - Route map visualization
- **python-docx** - Document generation

## Quick Start

```bash
# 1. Clone and install dependencies
git clone <repository-url>
cd itinerary-generator
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (see Configuration below)

# 3. Run the CLI
python main.py
```

## Configuration

Create a `.env` file with the following:

```bash
# LLM Provider (required - choose one)
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# Model settings
MODEL_PROVIDER=anthropic          # or "openai"
MODEL_NAME=claude-sonnet-4-5-20250929  # or "gpt-4o"

# Web Search (required for attraction research)
TAVILY_API_KEY=tvly-...

# Email delivery (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password

# Observability (optional)
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=itinerary-generator
```

## Usage

The CLI guides you through the itinerary creation process:

1. **Enter attractions** (one per line, end with "END"):
   ```
   Torre Eiffel
   Museu do Louvre
   Catedral de Notre-Dame
   Palácio de Versalhes
   END
   ```

2. **Add preferences** (optional):
   ```
   Versalhes precisa de um dia inteiro
   No máximo 3 atrações por dia
   ```

3. **Select options**:
   - Number of days
   - Output language (en, pt-br, es, fr)

4. **Review organization** (for flexible attractions):
   ```
   ============================================================
   PROPOSED ITINERARY ORGANIZATION
   ============================================================

   Day 1:
     • Torre Eiffel
     • Catedral de Notre-Dame

   Day 2:
     • Museu do Louvre

   Day 3:
     • Palácio de Versalhes

   ============================================================

   Is this organization okay?
   Type 'yes' to approve, or describe what changes you'd like.
   Examples: 'move Louvre to day 2', 'swap day 1 and day 3'

   Your response:
   ```

5. **Receive output**:
   - Generated DOCX saved to `.results/`
   - Cost summary by currency displayed
   - Option to send via email

## User Preference Types

The Day Organizer understands three types of user intent:

| Type | Example | Behavior |
|------|---------|----------|
| **Isolated** | "Disneyland needs a full day" | Attraction gets exclusive day |
| **Specific Day** | "Eiffel Tower on day 1" | Assigned to day, can share with others |
| **Flexible** | Just listing attractions | Grouped by geographic proximity |

### Clustering Constraints

You can specify min/max attractions per day:

| Constraint | Example | Behavior |
|------------|---------|----------|
| **Minimum** | "at least 2 per day" | Each day has >= 2 attractions |
| **Maximum** | "no more than 3 per day" | Each day has <= 3 attractions |
| **Both** | "between 2 and 4 per day" | Days have 2-4 attractions |

The number of days remains fixed; only cluster sizes are constrained using `k-means-constrained`.

## Multilingual Support

The system preserves attraction names in your language:

1. **Input**: You provide names in your language (e.g., "Torre Eiffel", "Museu do Louvre")
2. **Geocoding**: Agent finds English addresses for accurate coordinates
3. **Storage**: Your original names are used as keys
4. **Output**: Maps and documents display names in your language

Example mapping:
```python
{
    "Torre Eiffel": "Eiffel Tower, Champ de Mars, Paris, France",
    "Museu do Louvre": "Louvre Museum, Rue de Rivoli, Paris, France"
}
```

## Project Structure

```
itinerary-generator/
├── main.py                              # CLI entry point
├── requirements.txt                     # Dependencies
├── .env.example                         # Configuration template
│
├── src/
│   ├── agent/
│   │   ├── graph.py                    # LangGraph workflow definition
│   │   ├── state.py                    # TypedDict state schemas
│   │   ├── agent_definition.py         # Agent creation and node functions
│   │   ├── tools.py                    # Search, geocoding, clustering, approval tools
│   │   ├── prompts.py                  # System prompts for agents
│   │   └── other_nodes.py              # Helper nodes (assign_workers, build_document)
│   │
│   ├── processor/
│   │   ├── docx_processor.py           # DOCX document generation
│   │   └── email_processor.py          # SMTP email client
│   │
│   ├── mcp_client/
│   │   └── tavily_client.py            # Tavily MCP for web/image search
│   │
│   ├── middleware/
│   │   └── structured_output_validator.py  # Output validation with retry
│   │
│   └── utils/
│       ├── logger.py                   # Rich CLI logging
│       ├── observability.py            # LangSmith integration
│       └── utilities.py                # Geospatial plotting helpers
│
└── .results/                            # Generated DOCX files
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `search_attraction_info` | Web search for addresses and information |
| `extract_coordinates` | Geocode attractions (name→address mapping) |
| `organize_attractions_by_days` | K-means clustering with constraints |
| `request_itinerary_approval` | Pause for user review (uses LangGraph interrupt) |
| `update_itinerary_organization` | Apply user's requested changes |
| `return_invalid_input_error` | Handle invalid/unrelated input |

## Output Example

The generated DOCX includes:

- **Cover page** with itinerary title and dates
- **Day-by-day sections** with:
  - Attraction descriptions and tips
  - Opening hours and addresses
  - Embedded images with captions
  - Ticket purchase links
  - Estimated costs per person
- **Visual route map** with color-coded day markers (names in your language)
- **Cost summary** grouped by currency

## API Requirements

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| Anthropic/OpenAI | LLM reasoning | Pay per token |
| Tavily | Web search + images | 1,000 searches/month |

## Geocoding Accuracy

The agent searches for official addresses before geocoding to ensure accurate coordinates:

1. **Search**: Queries "[attraction] [city] [country] official address"
2. **Map**: Creates `{original_name: english_address}` dict
3. **Geocode**: Uses full address like "Colosseum, Piazza del Colosseo, Rome, Italy"
4. **Store**: Coordinates are saved with original name as key

This prevents errors with attractions that have namesakes in other cities and preserves your language in outputs.

## Troubleshooting

**Geocoding failures**: The agent will search for official addresses before geocoding. If issues persist, ensure attraction names include city and country.

**Rate limits**: The system includes exponential backoff retry. For high volume, consider adding delays between requests.

**Approval not requested**: The middleware validates that `request_itinerary_approval` is called when K-means clustering is used. If skipped, the agent will retry.

## License

MIT License - Free to use and modify
