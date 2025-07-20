# Deployment Guide - Auto-Complete Book Writing System

This guide covers deploying both the frontend (Next.js) and backend (FastAPI) components of the Auto-Complete Book Writing System.

## 🏗️ Architecture Overview

- **Frontend**: Next.js application deployed on Vercel
- **Backend**: FastAPI application deployed on Railway
- **Authentication**: Clerk for user management
- **Storage**: Firestore for metadata, local filesystem for generated content

## 📋 Prerequisites

### Required Accounts
- [Vercel](https://vercel.com) account for frontend deployment
- [Railway](https://railway.app) account for backend deployment  
- [Clerk](https://clerk.dev) account for authentication
- [OpenAI](https://openai.com) API key for LLM functionality

### Required Tools
- Node.js 18+ 
- Python 3.11+
- Railway CLI: `npm install -g @railway/cli`
- Vercel CLI: `npm install -g vercel`

## 🔧 Environment Configuration

### Backend Environment Variables
Create these environment variables in Railway:

```bash
# Core Application
ENVIRONMENT=production
PORT=8000
HOST=0.0.0.0

# AI Services
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here  # Optional

# Authentication (Clerk)
CLERK_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxx
CLERK_SECRET_KEY=sk_live_xxxxxxxxxxxx

# CORS Configuration
CORS_ORIGINS=https://your-frontend-domain.vercel.app,https://www.your-domain.com

# Optional: File Operations
DISABLE_FILE_OPERATIONS=false  # Set to 'true' for read-only filesystems
```

### Frontend Environment Variables
Create these environment variables in Vercel:

```bash
# Authentication (Clerk)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxx
CLERK_SECRET_KEY=sk_live_xxxxxxxxxxxx

# Backend API
NEXT_PUBLIC_BACKEND_URL=https://your-backend.up.railway.app
```

## 🚀 Deployment Process

### Pre-Deployment Verification

Before deploying, run the verification script:

```bash
cd backend
python verify-build.py
```

This checks for:
- All required files and directories
- Proper Docker build context
- Environment configuration documentation
- Critical system/ directory for LLM orchestrator

### Backend Deployment (Railway)

1. **Initial Setup**
   ```bash
   cd backend
   railway login
   railway init  # Create new project or link existing
   ```

2. **Configure Environment Variables**
   - Go to Railway dashboard → Your project → Variables
   - Add all required environment variables listed above

3. **Deploy**
   ```bash
   railway up
   ```

4. **Verify Deployment**
   - Check logs: `railway logs`
   - Test health endpoint: `curl https://your-backend.up.railway.app/health`

### Frontend Deployment (Vercel)

1. **Initial Setup**
   ```bash
   cd /project-root  # Not in backend/ directory
   vercel login
   vercel --prod
   ```

2. **Configure Environment Variables**
   - Go to Vercel dashboard → Your project → Settings → Environment Variables
   - Add all required environment variables listed above

3. **Deploy**
   ```bash
   vercel --prod
   ```

4. **Verify Deployment**
   - Test the application in browser
   - Check authentication flow
   - Test API connectivity

## 🔍 Critical Files for Deployment

### Required Directory Structure
```
project-root/
├── backend/
│   ├── main.py                    # FastAPI application
│   ├── Dockerfile                 # Container configuration
│   ├── requirements.txt           # Python dependencies
│   ├── auth_middleware.py         # Authentication logic
│   ├── firestore_client.py        # Database client
│   ├── utils/                     # Utility functions
│   └── verify-build.py            # Pre-deployment verification
├── system/                        # ⚠️  CRITICAL: LLM orchestrator
│   ├── __init__.py                # Python package marker
│   ├── llm_orchestrator.py        # Core LLM logic
│   └── auto_complete_book_orchestrator.py
├── src/                           # Frontend components
│   ├── components/
│   ├── app/
│   └── lib/
└── package.json                   # Frontend dependencies
```

### ⚠️ Common Deployment Issues

1. **"No module named 'system'" Error**
   - **Cause**: system/ directory not in Docker build context
   - **Fix**: Ensure `COPY . .` in Dockerfile and system/ exists at project root

2. **422 "missing fields" Error**
   - **Cause**: Frontend sending incorrect request body format  
   - **Fix**: Ensure frontend sends `project_id`, `chapter_number` (not `chapter`)

3. **CORS Errors**
   - **Cause**: Frontend domain not in CORS_ORIGINS
   - **Fix**: Add frontend URL to CORS_ORIGINS environment variable

4. **Authentication Failures**
   - **Cause**: Mismatched Clerk keys between frontend/backend
   - **Fix**: Verify CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY match

## 🧪 Post-Deployment Testing

### Manual Testing Checklist

1. **Authentication**
   - [ ] User can sign up/sign in
   - [ ] JWT tokens are generated correctly
   - [ ] Protected routes require authentication

2. **Core Functionality**  
   - [ ] Book Bible upload works
   - [ ] Project creation succeeds
   - [ ] Chapter cost estimation returns valid results
   - [ ] Chapter generation produces content
   - [ ] Generated chapters are saved and retrievable

3. **Error Handling**
   - [ ] Clear error messages for missing project
   - [ ] Proper validation errors (422) with helpful details
   - [ ] Auth errors (401) display correctly

### API Health Checks

```bash
# Basic health
curl https://your-backend.up.railway.app/health

# Authentication configuration  
curl https://your-backend.up.railway.app/debug/auth-status
```

## 📊 Monitoring & Logs

### Railway (Backend)
- View logs: `railway logs` or Railway dashboard
- Monitor resource usage in Railway dashboard
- Set up alerts for high error rates

### Vercel (Frontend)  
- View function logs in Vercel dashboard
- Monitor build and deployment status
- Check performance metrics

## 🔄 Update Process

### Backend Updates
```bash
cd backend
python verify-build.py  # Pre-deployment check
railway up               # Deploy if verification passes
```

### Frontend Updates  
```bash
vercel --prod           # Deploy latest changes
```

### Rolling Back
- **Railway**: Use dashboard to revert to previous deployment
- **Vercel**: Use dashboard or `vercel rollback` command

## 🆘 Troubleshooting

### Build Failures
1. Check `verify-build.py` output for missing files
2. Verify all environment variables are set
3. Check Docker build logs in Railway
4. Ensure system/ directory is at project root

### Runtime Errors
1. Check Railway logs for backend errors
2. Use browser dev tools for frontend issues  
3. Test API endpoints individually with curl
4. Verify CORS configuration

### Performance Issues
1. Monitor Railway resource usage
2. Check Vercel function execution times
3. Optimize large file uploads
4. Consider caching strategies

## 📞 Support

For deployment issues:
1. Check this guide first
2. Run `python backend/verify-build.py` 
3. Review logs in Railway/Vercel dashboards
4. Test individual components in isolation

---

**Last Updated**: January 2025  
**Version**: 1.0.0 