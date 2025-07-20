# 📚 Auto-Complete Book Writing Platform

An intelligent book writing platform that automatically generates complete books with sequential chapter generation, quality gates, and real-time progress tracking.

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ 
- Python 3.11+
- OpenAI API Key
- Clerk Account (for authentication)

### Local Development

1. **Clone and install dependencies:**
```bash
git clone <repository-url>
cd book_writer_automated

# Install frontend dependencies
npm install

# Install backend dependencies
cd backend
pip install -r requirements.txt
```

2. **Environment setup:**
```bash
# Frontend - Copy and configure
cp env.example .env.local

# Backend - Copy and configure  
cd backend
cp env.example .env
```

3. **Run the development servers:**
```bash
# Terminal 1: Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
npm run dev
```

4. **Visit http://localhost:3000**

## 🛠️ **Recent Critical Bug Fixes**

### ✅ Issue 1: Estimate Function "python: command not found" Error
**Problem:** The estimate API was trying to execute Python scripts directly in the Vercel environment, causing failures.

**Root Cause:** 
- Frontend API route (`/api/estimate`) was using `execSync()` to run Python locally
- Vercel's Node.js runtime doesn't include Python
- Architectural mismatch between frontend execution and backend services

**Solution Applied:**
- Replaced direct Python execution with proper backend API calls
- Updated `/api/estimate` to call `/v1/estimate` backend endpoint
- Implemented comprehensive cost estimation in backend with fallback logic
- Added proper error handling and logging

**Files Modified:**
- `src/app/api/estimate/route.ts` - Removed Python execution, added backend API call
- `backend/main.py` - Added `/v1/estimate` endpoint with LLM orchestrator integration

### ✅ Issue 2: Chapter Generation Success but No Visible Chapters
**Problem:** Chapter generation reported success but chapters weren't visible in the UI.

**Root Cause:**
- Backend chapter generation was returning mock data instead of real chapters
- Frontend was reading from local filesystem instead of backend storage
- Storage architecture mismatch between generation and retrieval systems
- Missing project ID context in chapter API calls

**Solution Applied:**
- Replaced mock chapter generation with real LLM orchestrator implementation
- Added proper chapter storage in backend project workspaces
- Created comprehensive chapter retrieval API endpoints (`/v1/chapters`)
- Updated frontend to fetch chapters from backend instead of local files
- Added project ID context to all chapter operations

**Files Modified:**
- `backend/main.py` - Real chapter generation + storage endpoints
- `src/app/api/chapters/route.ts` - Backend API integration
- `src/app/api/chapters/[chapter]/route.ts` - Individual chapter backend calls
- `src/app/page.tsx` - Project ID context for chapter fetching
- `src/components/ChapterList.tsx` - Backend integration for chapter operations

## 🧪 Testing the Fixes

### Test Estimate Function:
1. Navigate to "Generate New Chapter" section
2. Enter chapter number (1), word count (3800), select stage
3. Click "Estimate Cost"
4. **Expected:** Cost estimate appears without "python: command not found" error
5. **Previously:** Would fail with Python execution error

### Test Chapter Generation:
1. Ensure you have a Book Bible uploaded (creates project ID)
2. Use chapter generation form
3. Click "Generate Chapter"
4. **Expected:** Chapter appears in the chapters list below
5. **Previously:** Would show success but no chapter visible

### Test Chapter Viewing:
1. Click on any generated chapter in the list
2. **Expected:** Chapter content appears in modal/viewer
3. Chapter shows proper word count and metadata

## 🏗️ Architecture Overview

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Next.js Frontend  │    │   FastAPI Backend   │    │  Python Modules    │
│                     │    │                     │    │                     │
│ • Cost Estimation   │────│ • /v1/estimate      │────│ • LLM Orchestrator │
│ • Chapter Display   │────│ • /v1/chapters/*    │────│ • Chapter Storage  │
│ • Project Mgmt      │────│ • Project Workspace │────│ • Quality Gates    │
│ • Authentication    │    │ • File Management   │    │ • Context Manager  │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

## 🎯 Core Features

- **📖 Auto-Complete Book Generation**: Generate entire books chapter by chapter
- **💰 Cost Estimation**: Accurate token and cost estimation before generation  
- **📊 Real-time Progress**: Live progress tracking with Server-Sent Events
- **🎯 Quality Gates**: Automated quality assessment between chapters
- **🔄 Chapter Management**: View, edit, and delete generated chapters
- **🔐 Secure Authentication**: Clerk-based user management
- **📁 Project Workspaces**: Isolated storage for each book project
- **⚡ Rate Limiting**: API protection and resource management

## 📦 Deployment

### Frontend (Vercel)
```bash
# Deploy to Vercel
vercel --prod

# Required environment variables:
NEXT_PUBLIC_BACKEND_URL=https://your-backend-url.railway.app
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

### Backend (Railway)
```bash
cd backend

# Deploy to Railway
railway up

# Required environment variables:
OPENAI_API_KEY=sk-...
CLERK_SECRET_KEY=sk_test_...
ENVIRONMENT=production
```

## 📋 Environment Variables

### Frontend (.env.local)
```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

### Backend (.env)
```env
OPENAI_API_KEY=sk-...
CLERK_SECRET_KEY=sk_test_...
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
ENVIRONMENT=development

# AI Content Generation
DEFAULT_AI_MODEL=gpt-4o
DEFAULT_AI_TEMPERATURE=0.7
DEFAULT_AI_MAX_TOKENS=4000
REFERENCE_PROMPTS_DIR=./prompts/reference-generation
```

## 🔧 API Endpoints

### Core Endpoints
- `POST /v1/estimate` - Cost estimation for chapter generation
- `POST /v1/chapters/generate` - Generate single chapter
- `GET /v1/chapters` - List project chapters  
- `GET /v1/chapters/{id}` - Get specific chapter
- `DELETE /v1/chapters/{id}` - Delete chapter
- `POST /book-bible/initialize` - Initialize project with book bible

### Auto-Complete Endpoints
- `POST /auto-complete/start` - Start auto-complete job
- `GET /auto-complete/{job_id}/status` - Get job status
- `POST /auto-complete/{job_id}/control` - Control job (pause/resume/cancel)
- `GET /auto-complete/{job_id}/progress` - Real-time progress stream (SSE)

## 🐛 Troubleshooting

### Common Issues

#### "Backend URL not configured" Error
**Cause:** Missing `NEXT_PUBLIC_BACKEND_URL` environment variable
**Solution:** Set the backend URL in your environment variables

#### "python: command not found" Error (Fixed)
**Cause:** Old version trying to execute Python locally
**Solution:** Update to latest version with backend API integration

#### Chapters Not Appearing (Fixed)  
**Cause:** Storage architecture mismatch
**Solution:** Update to latest version with proper backend storage

#### Authentication Issues
**Cause:** Missing or incorrect Clerk configuration
**Solution:** Verify Clerk keys are properly set in environment variables

### Health Checks
- Backend health: `GET /health`
- API documentation: `GET /docs` (FastAPI auto-generated)
- Frontend status: Check browser console for error messages

## 🏗️ Project Structure

```
book-writer-automated-platform/
├── src/                          # Next.js frontend
│   ├── app/                      # App Router pages
│   │   ├── api/                  # API routes (proxy to backend)
│   │   ├── layout.tsx            # Root layout
│   │   └── page.tsx              # Home page
│   ├── components/               # React components
│   └── lib/                      # Utilities
├── backend/                      # FastAPI backend
│   ├── main.py                   # Main application
│   ├── auth_middleware.py        # Authentication
│   ├── firestore_client.py       # Database client
│   ├── system/                   # Core generation logic
│   │   ├── llm_orchestrator.py   # Chapter generation
│   │   └── auto_complete_book_orchestrator.py
│   ├── requirements.txt          # Python dependencies
│   ├── Dockerfile               # Container config
│   └── tests/                   # Test suite
├── .github/workflows/           # CI/CD pipelines
├── docs/                        # Documentation
└── README.md                    # This file
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- 📧 Email: [support@bookwriter.ai](mailto:support@bookwriter.ai)
- 📖 Documentation: [docs.bookwriter.ai](https://docs.bookwriter.ai)
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/book-writer-automated/issues)

---

**Built with ❤️ for writers everywhere** 📚✨ 