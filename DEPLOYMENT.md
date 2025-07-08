# 🚀 Book Writer Automated - Deployment Guide

This project uses a multi-platform deployment strategy with automated scripts to handle all components.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │  Authentication │
│   (Vercel)      │◄──►│   (Railway)     │◄──►│    (Clerk)      │
│                 │    │                 │    │                 │
│ • Next.js 14    │    │ • FastAPI       │    │ • User Auth     │
│ • React         │    │ • Python 3.11   │    │ • JWT Tokens    │
│ • Tailwind CSS  │    │ • Gunicorn      │    │ • Custom Domain │
│ • TypeScript    │    │ • SQLite        │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Quick Start

### 1. Full Deployment (All Platforms)
```bash
npm run deploy
```

### 2. Frontend Only (Vercel)
```bash
npm run deploy:frontend
```

### 3. Backend Only (Railway)
```bash
npm run deploy:backend
```

### 4. Quick Deploy (Skip Tests)
```bash
npm run deploy:quick
```

## Manual Deployment

### Prerequisites
```bash
# Install required CLIs
npm install -g @railway/cli
npm install -g vercel

# Login to services
railway login
npx vercel login
```

### Step-by-Step Deployment

#### 1. Frontend (Next.js → Vercel)
```bash
# Build and test locally
npm install
npm run build
npm run type-check

# Deploy to Vercel
npx vercel --prod
```

#### 2. Backend (FastAPI → Railway)
```bash
# Navigate to backend
cd backend

# Deploy to Railway
railway up

# Verify deployment
curl https://silky-loss-production.up.railway.app/health
```

#### 3. Authentication (Clerk)
- No deployment required (service-based)
- Configure in [Clerk Dashboard](https://dashboard.clerk.com)
- Environment variables already set

## Environment Variables

### Frontend (.env.local)
```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_BACKEND_URL=https://silky-loss-production.up.railway.app
```

### Backend (Railway)
```env
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
OPENAI_API_KEY=sk-proj-...
```

## Deployment Script Features

### ✅ **Automated Checks**
- Dependency verification (git, npm, Railway CLI)
- Git status and uncommitted changes
- TypeScript type checking
- Production build testing

### ✅ **Multi-Platform Support**
- **GitHub**: Source code repository
- **Vercel**: Frontend hosting with custom domain
- **Railway**: Backend API hosting
- **Clerk**: Authentication service

### ✅ **Flexible Options**
- Deploy all platforms or specific ones
- Skip tests for quick deployments
- Interactive commit prompts
- Deployment verification

### ✅ **Error Handling**
- Exit on any error
- Colored output for clarity
- Detailed logging
- Rollback-safe operations

## Deployment Verification

After deployment, the script automatically verifies:

### Frontend (Vercel)
- ✅ **URL**: https://www.writerbloom.com
- ✅ **Status**: 200 OK response
- ✅ **Features**: Clerk authentication, API proxying

### Backend (Railway)
- ✅ **URL**: https://silky-loss-production.up.railway.app
- ✅ **Status**: API endpoints responding
- ✅ **Features**: FastAPI, authentication middleware

## Troubleshooting

### Common Issues

#### 1. TypeScript Errors
```bash
# Check types manually
npm run type-check

# Fix common issues
npm run lint --fix
```

#### 2. Railway Connection
```bash
# Login to Railway
railway login

# Check connection
railway status
```

#### 3. Vercel Build Failures
```bash
# Test build locally
npm run build

# Check environment variables
npx vercel env ls
```

#### 4. Authentication Issues
- Verify Clerk environment variables
- Check custom domain settings
- Ensure API keys match between platforms

### Rollback Strategy

#### Frontend (Vercel)
```bash
# List deployments
npx vercel ls

# Promote specific deployment
npx vercel promote [deployment-url]
```

#### Backend (Railway)
```bash
# Railway handles rollbacks through dashboard
# Visit: https://railway.app/project/[project-id]
```

## Platform URLs

- 🌐 **Production**: https://www.writerbloom.com
- 🔧 **API**: https://silky-loss-production.up.railway.app
- 📚 **GitHub**: https://github.com/zaclake/book-writer-automated-platform
- 🔐 **Clerk Dashboard**: https://dashboard.clerk.com

## Monitoring

### Frontend (Vercel)
- Build logs: Vercel Dashboard
- Runtime logs: Browser Network tab
- Performance: Vercel Analytics

### Backend (Railway)
- Application logs: `railway logs`
- Metrics: Railway Dashboard
- Health check: `/health` endpoint

### Authentication (Clerk)
- User activity: Clerk Dashboard
- Auth logs: Clerk Logs section
- API usage: Clerk Analytics

---

**Need Help?** Check the deployment script output for detailed error messages and suggestions. 