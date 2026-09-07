# Recipe Enhancement Platform

Automatically enhances recipes by analyzing and applying community-tested modifications from AllRecipes.com. Uses LLM processing to extract meaningful recipe tweaks and apply them with full citation tracking.

## Installation

This project uses [`uv`](https://docs.astral.sh/uv/) for fast, reliable Python package management.

### Prerequisites

- Python 3.13+
- `uv` package manager

## Setup

```bash
# Install dependencies
uv venv
source .venv/bin/activate
uv pip sync pyproject.toml
```

### Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your-openai-api-key-here
```

## Usage

### 1. Scrape Recipes (Optional - data already provided)

```bash
uv run python src/scraper_v2.py
```

### 2. Run Recipe Enhancement Pipeline

```bash
cd src

# Test single recipe (chocolate chip cookies)
uv run python test_pipeline.py single

# Process all recipes
uv run python test_pipeline.py all
```

## Output

### Enhanced Recipes

Enhanced recipes are saved in `src/data/enhanced/`:

- `enhanced_[recipe_id]_[recipe-name].json` - Individual enhanced recipes with modifications applied
- `pipeline_summary_report.json` - Summary of all processing results

### Data Structure

Original scraped recipes in `data/` directory contain reviews with `has_modification: true` flags. Enhanced recipes include:

```json
{
  "recipe_id": "10813_enhanced",
  "title": "Best Chocolate Chip Cookies (Community Enhanced)",
  "ingredients": ["1 cup butter", "1 additional egg yolk", ...],
  "modifications_applied": [
    {
      "source_review": {
        "text": "I added an extra egg yolk for chewier texture",
        "rating": 5
      },
      "modification_type": "addition",
      "reasoning": "Improves texture and chewiness",
      "changes_made": [...]
    }
  ],
  "enhancement_summary": {
    "total_changes": 1,
    "change_types": ["addition"],
    "expected_impact": "Chewier texture and improved consistency"
  }
}
```

## How It Works

The LLM Analysis Pipeline processes recipes in 3 steps:

1. **Tweak Extraction**: Selects one random review with modifications and uses GPT-4o-mini to extract structured changes
2. **Recipe Modification**: Applies changes to the original recipe using fuzzy string matching
3. **Enhanced Recipe Generation**: Creates enhanced version with full citation tracking back to source review

Each run produces one enhanced recipe per original recipe, with complete attribution showing exactly what changed and why.

## Development

```bash
# Add dependencies
uv add <package_name>

# Run tests
cd src && uv run python test_pipeline.py single
```
