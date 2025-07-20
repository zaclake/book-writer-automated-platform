# Reference Generation System Setup Guide

This guide covers setting up and customizing the AI-powered reference generation system.

## Prerequisites

1. **OpenAI API Key**: Required for AI content generation
2. **Python 3.11+**: Backend requirement
3. **Node.js 18+**: Frontend requirement

## Quick Setup

### 1. Environment Configuration

Add to your `backend/.env` file:

```env
# Required for AI generation
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional customization
DEFAULT_AI_MODEL=gpt-4o
DEFAULT_AI_TEMPERATURE=0.7
DEFAULT_AI_MAX_TOKENS=4000
REFERENCE_PROMPTS_DIR=./prompts/reference-generation
```

### 2. Install Dependencies

```bash
cd backend
pip install openai>=1.0.0 PyYAML>=6.0
```

### 3. Verify Setup

Start the backend and check the health endpoint:

```bash
curl http://localhost:8000/health/detailed
```

Look for `auth_configured: true` in the response.

## Customizing Prompts

### Prompt File Structure

Each reference type has a YAML prompt file in `prompts/reference-generation/`:

- `characters-prompt.yaml` - Character profiles and development
- `outline-prompt.yaml` - Story structure and chapter breakdown  
- `world-building-prompt.yaml` - Setting and environmental details
- `style-guide-prompt.yaml` - Writing voice and tone guidelines
- `plot-timeline-prompt.yaml` - Chronological and thematic tracking

### YAML Prompt Format

```yaml
name: "Descriptive Generator Name"
description: "What this prompt generates"
version: "1.0"

model_config:
  model: "gpt-4o"           # OpenAI model to use
  temperature: 0.7          # Creativity level (0.0-1.0)
  max_tokens: 4000          # Maximum response length
  top_p: 0.9               # Response diversity

system_prompt: |
  You are an expert [domain] consultant for fiction writers.
  Your task is to create [specific output type].
  
  Guidelines:
  - Be specific to the story's genre and themes
  - Create actionable, detailed content
  - Focus on practical writing guidance

user_prompt_template: |
  Based on the following book bible, create a comprehensive [filename]:
  
  ---
  BOOK BIBLE:
  {book_bible_content}
  ---
  
  Generate detailed content that includes:
  
  ## Section 1
  [Description of what should be in this section]
  
  ## Section 2  
  [Description of what should be in this section]

validation_rules:
  - "Must include at least 3 main sections"
  - "Content must be specific to the book's genre"
  - "Should provide actionable writing guidance"

output_format: "markdown"
expected_sections:
  - "Section 1"
  - "Section 2"
```

### Template Variables

Available in `user_prompt_template`:

- `{book_bible_content}` - The complete book bible text
- Additional variables can be passed via the API

### Customization Examples

#### Adjusting Creativity
```yaml
model_config:
  temperature: 0.3  # More focused, less creative
  # or
  temperature: 0.9  # More creative, less focused
```

#### Targeting Different Genres
```yaml
system_prompt: |
  You are an expert in [FANTASY/SCI-FI/ROMANCE] writing.
  Focus on genre-specific elements like [magic systems/technology/relationships].
```

#### Changing Output Length
```yaml
model_config:
  max_tokens: 2000  # Shorter content
  # or  
  max_tokens: 6000  # Longer, more detailed content
```

## Using the System

### Through the UI

1. **Upload Book Bible**: Use the Book Bible Upload component
2. **Generate References**: Click "Generate AI Content" in Reference Files section
3. **Individual Regeneration**: Click the sparkle icon next to any reference file
4. **Edit Content**: Click "Edit" to manually modify any generated file

### Through the API

#### Generate All References
```bash
curl -X POST http://localhost:8000/references/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "your-project-id"}'
```

#### Regenerate Specific File
```bash
curl -X POST http://localhost:8000/references/characters.md/regenerate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "your-project-id"}'
```

## Troubleshooting

### AI Generation Not Working

1. **Check API Key**: Verify `OPENAI_API_KEY` is set correctly
2. **Check Logs**: Look for OpenAI API errors in backend logs
3. **Test Connection**: Use a simple API test:

```python
from openai import OpenAI
client = OpenAI(api_key="your-key")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Test"}]
)
print(response.choices[0].message.content)
```

### Template Fallback Mode

If AI generation fails, the system automatically falls back to basic templates:

- Reference files are still created with structure
- You can manually edit and populate them
- AI generation can be retried later

### Common Issues

#### "OpenAI API key not configured"
- Solution: Add `OPENAI_API_KEY` to your `.env` file
- Restart the backend after adding the key

#### "Prompt file not found"
- Solution: Ensure all YAML files exist in `prompts/reference-generation/`
- Check file naming: `[type]-prompt.yaml`

#### "Generated content too short"
- Solution: Increase `max_tokens` in prompt config
- Check if your book bible has sufficient content

#### Rate Limiting
- OpenAI API has rate limits
- The system handles retries automatically
- For high volume, consider upgrading your OpenAI plan

## Advanced Configuration

### Custom Reference Types

To add a new reference type:

1. Create a new prompt file: `prompts/reference-generation/custom-prompt.yaml`
2. Update the filename mapping in `backend/utils/reference_content_generator.py`
3. Add the UI entry in `src/components/ReferenceFileManager.tsx`

### Integration with Existing Systems

The reference generation integrates with:

- **Book Bible Upload**: Auto-generation on upload
- **Project Management**: Files tied to project lifecycle  
- **Authentication**: Secure access to generation endpoints
- **Error Handling**: Graceful degradation and retry logic

### Performance Optimization

- **Parallel Generation**: Multiple files generated concurrently
- **Caching**: Consider caching frequently used prompts
- **Batch Processing**: API optimized for bulk operations

## Best Practices

1. **Start Simple**: Use default prompts, then customize gradually
2. **Test Iteratively**: Generate small sections to test prompt changes
3. **Monitor Costs**: AI generation uses OpenAI tokens - monitor usage
4. **Version Control**: Keep prompt files in version control
5. **Backup Important Content**: Generated content can be regenerated, but edits are valuable

## Support

- Check the main README for general setup issues
- Review backend logs for detailed error messages  
- Test individual components in isolation
- Use the health endpoints to verify system status 