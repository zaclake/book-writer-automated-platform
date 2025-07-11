# Auto-Complete Book Backend

FastAPI backend for the Auto-Complete Book Writing System. Provides API endpoints for sequential chapter generation with quality gates, context continuity, and real-time progress tracking.

## Features

- **Sequential Chapter Generation**: Auto-complete entire books with quality gates between chapters
- **Real-time Progress**: Server-Sent Events (SSE) for live progress updates
- **Context Continuity**: Maintains story consistency across chapters
- **Quality Assessment**: Automated quality scoring and validation
- **Job Management**: Pause, resume, and cancel auto-completion jobs
- **User Authentication**: JWT-based authentication with Clerk integration
- **Containerized**: Docker support for easy deployment

## Quick Start

### Development Setup

1. **Clone and navigate to backend directory**:
```bash
cd backend
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**:
```bash
cp env.example .env
# Edit .env with your configuration
```

5. **Run the development server**:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Development

1. **Build and run with Docker Compose**:
```bash
docker-compose up --build
```

This will start:
- Backend API on `http://localhost:8000`
- Redis on `localhost:6379`
- Portainer (optional) on `http://localhost:9000`

## API Endpoints

### Auto-Complete Endpoints

- `POST /auto-complete/start` - Start auto-complete job
- `GET /auto-complete/{job_id}/status` - Get job status
- `POST /auto-complete/{job_id}/control` - Control job (pause/resume/cancel)
- `GET /auto-complete/{job_id}/progress` - Real-time progress stream (SSE)
- `GET /auto-complete/jobs` - List user's jobs

### Chapter Generation

- `POST /chapters/generate` - Generate single chapter
- `POST /quality/assess` - Assess chapter quality

### System

- `GET /` - API info
- `GET /health` - Health check

## Configuration

### Environment Variables

Copy `env.example` to `.env` and configure:

```env
# Required
OPENAI_API_KEY=your_openai_api_key
CLERK_SECRET_KEY=your_clerk_secret_key

# Optional
PORT=8000
ENVIRONMENT=development
REDIS_URL=redis://localhost:6379
```

### Quality Gates

Configure quality thresholds in your environment:

```env
DEFAULT_QUALITY_THRESHOLD=7.0
MAX_RETRIES_PER_CHAPTER=3
AUTO_PAUSE_ON_FAILURE=true
```

## Deployment

### Railway Deployment

1. **Connect your GitHub repository to Railway**
2. **Set environment variables in Railway dashboard**
3. **Deploy automatically on push to main branch**

The `railway.json` file contains deployment configuration.

### Manual Docker Deployment

1. **Build the image**:
```bash
docker build -t auto-complete-backend .
```

2. **Run the container**:
```bash
docker run -p 8000:8000 --env-file .env auto-complete-backend
```

### Production Considerations

- Use Redis for job storage instead of in-memory
- Set up proper logging and monitoring
- Configure CORS origins for your frontend domain
- Use environment-specific configuration
- Set up SSL/TLS certificates
- Configure auto-scaling based on job queue length

## API Usage Examples

### Start Auto-Complete Job

```bash
curl -X POST "http://localhost:8000/auto-complete/start" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "my-novel-project",
    "book_bible": "Complete book bible content...",
    "target_chapters": 20,
    "quality_threshold": 7.5,
    "words_per_chapter": 3800
  }'
```

### Monitor Progress

```bash
curl -N "http://localhost:8000/auto-complete/JOB_ID/progress" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Control Job

```bash
curl -X POST "http://localhost:8000/auto-complete/JOB_ID/control" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "pause"}'
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │  Job Processor  │    │  Orchestrator   │
│                 │    │                 │    │                 │
│ • Authentication│    │ • Async Jobs    │    │ • Chapter Gen   │
│ • API Endpoints │────│ • Progress      │────│ • Quality Gates │
│ • SSE Streaming │    │ • Job Control   │    │ • Context Mgmt  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Key Components

1. **main.py**: FastAPI application with endpoints
2. **auto_complete_book_orchestrator.py**: Sequential chapter generation
3. **background_job_processor.py**: Async job management
4. **chapter_context_manager.py**: Story continuity tracking

## Testing

Run tests with:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=. --cov-report=html
```

## Development

### Code Style

The project uses:
- **Black** for code formatting
- **Flake8** for linting
- **pytest** for testing

Format code:
```bash
black .
flake8 .
```

### Adding New Features

1. Create feature branch
2. Add tests for new functionality
3. Update documentation
4. Submit pull request

## Monitoring

### Health Checks

The `/health` endpoint provides system status:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": {
    "job_processor": true
  }
}
```

### Logging

Logs are written to:
- Console (development)
- Files in `./logs/` directory
- Structured JSON format in production

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `PYTHONPATH=/app` is set
2. **Permission Errors**: Check file permissions in Docker
3. **Port Conflicts**: Change `PORT` environment variable
4. **Memory Issues**: Increase Docker memory limits

### Debug Mode

Enable debug logging:
```env
LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License. # Force redeploy Fri Jul 11 13:06:21 EDT 2025
