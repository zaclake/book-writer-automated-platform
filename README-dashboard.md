# Book Writer Dashboard

AI-powered chapter generation dashboard with automated quality assessment.

## Features

- **Real-time Chapter Generation**: Generate chapters using OpenAI GPT-4o
- **Quality Assessment**: Automated scoring using brutal assessment system
- **Cost Tracking**: Monitor API costs and budget usage
- **System Status**: Real-time health monitoring
- **Chapter Management**: View, edit, and delete generated chapters

## Quick Start

### Local Development

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up environment**:
   ```bash
   cp env.example .env.local
   # Edit .env.local with your OpenAI API key
   ```

3. **Run development server**:
   ```bash
   npm run dev
   ```

4. **Open dashboard**: http://localhost:3000

### Vercel Deployment

1. **Connect repository** to Vercel
2. **Set environment variables**:
   - `OPENAI_API_KEY`: Your OpenAI API key
3. **Deploy**: Vercel will automatically deploy on push to main

## API Endpoints

- `POST /api/generate` - Generate a new chapter
- `POST /api/estimate` - Estimate generation cost
- `GET /api/chapters` - List all chapters
- `GET /api/chapters/[id]` - Get specific chapter
- `DELETE /api/chapters/[id]` - Delete chapter
- `GET /api/metrics` - Get analytics and metrics
- `GET /api/status` - System health check

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `DASHBOARD_PASSWORD` | Simple auth password | No |
| `NODE_ENV` | Environment (development/production) | No |

## Architecture

- **Frontend**: Next.js 14 with TypeScript
- **Styling**: Tailwind CSS
- **Charts**: Recharts
- **Icons**: Heroicons
- **Backend**: Python LLM orchestrator
- **Deployment**: Vercel

## Cost Estimation

- Standard chapter (~4000 words): ~$0.02
- 5-stage premium: ~$0.08
- Full novel (100 chapters): ~$2-8

## Quality Gates

Chapters are automatically assessed on:
- Plot progression
- Character development
- Dialogue quality
- Pacing
- Grammar
- Series consistency

## Support

For issues or questions, check the main project documentation or create an issue in the repository. 