# Production Deployment Checklist

This checklist ensures the book_writer_automated system deploys correctly on Railway and all v2 API routes function properly.

## ✅ Code Fixes Applied

### 1. Router Import Resilience
- [x] **backend/main.py**: Broadened exception handling to catch `(ModuleNotFoundError, ImportError)` for router imports
- [x] **backend/database_integration.py**: Added robust import fallback for `DatabaseAdapter`
- [x] **backend/firestore_client.py**: Added import fallback for `database_integration`
- [x] **backend/main.py**: Added fallbacks for `utils.paths` and other backend imports
- [x] **backend/routers/users_v2.py**: Fixed router prefix from `/users/v2` to `/v2/users`

### 2. Deployment Command Conflicts Resolved
- [x] **Procfile**: Deleted to eliminate conflicts with `railway.toml`
- [x] **railway.toml**: Now single source of truth with `startCommand = "./start.sh"`
- [x] **start.sh**: Made executable and verified permissions in git

### 3. Debug Capabilities Added
- [x] **backend/main.py**: Added `/debug/router-status` endpoint to verify router registration
- [x] **Logging**: Enhanced router import logging to show success/failure clearly

## 🔧 Railway Environment Variables

### Critical Variables (Must be set)
```bash
# Authentication (Required)
CLERK_PUBLISHABLE_KEY=pk_test_... # or pk_live_...
ENVIRONMENT=production

# Database (Optional - set USE_FIRESTORE=false to disable)
USE_FIRESTORE=false  # Set to true only when Firestore is properly configured
GOOGLE_CLOUD_PROJECT=your-project-id  # Only if USE_FIRESTORE=true
SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'  # Only if USE_FIRESTORE=true

# OpenAI (Optional - features degrade gracefully if missing)
OPENAI_API_KEY=sk-...

# Optional Settings
CORS_ORIGINS=https://your-frontend-domain.com
DISABLE_FILE_OPERATIONS=false  # Set true only if Railway blocks file writes
DEBUG=false  # Set true temporarily for troubleshooting
```

### How to Set Variables in Railway
1. Go to your Railway project dashboard
2. Click on your service
3. Navigate to "Variables" tab
4. Add variables using the form or "Raw Editor"
5. Click "Deploy" to apply changes

## 🚀 Deployment Process

### 1. Pre-Deployment Verification
```bash
# Verify executable permissions locally
git ls-files --stage | grep -E "(start\.sh|railway_start\.py)"
# Should show 100755 for both files

# Test import paths work from backend directory
cd backend && python3 -c "import main; print('✅ All imports working')"
```

### 2. Deploy to Railway
- Push changes to main branch (Railway auto-deploys)
- Watch deployment logs for:
  - `🚀 CUSTOM START SCRIPT EXECUTING` (confirms start.sh is used)
  - `✅ All v2 routers included successfully` (confirms router imports work)
  - No `❌ CRITICAL: Failed to include routers` errors

### 3. Post-Deployment Smoke Tests
```bash
# Base URL for your Railway deployment
export BASE_URL="https://silky-loss-production.up.railway.app"

# 1. Verify v2 routes exist (should return 401, not 404)
curl -i $BASE_URL/v2/projects/
curl -i $BASE_URL/v2/chapters/
curl -i $BASE_URL/v2/users/

# 2. Check OpenAPI includes v2 routes
curl -s $BASE_URL/openapi.json | jq '.paths | keys[]' | grep "/v2/"

# 3. Verify router registration
curl -s $BASE_URL/debug/router-status | jq '.found_v2_prefixes'
# Should return: ["/v2/projects", "/v2/chapters", "/v2/users"]

# 4. Check working directory and imports
curl -s $BASE_URL/debug/paths | jq '.current_working_directory'

# 5. Verify health endpoints
curl $BASE_URL/health
curl $BASE_URL/status
```

## 🔍 Troubleshooting Guide

### Issue: v2 routes return 404
**Symptoms**: `/v2/projects/` returns 404 instead of 401
**Solution**: 
1. Check `/debug/router-status` - if `v2_routes_count` is 0, routers failed to import
2. Check deployment logs for router import errors
3. Verify all environment variables are set correctly

### Issue: Import errors in logs
**Symptoms**: `❌ CRITICAL: Failed to include routers` in logs
**Solution**:
1. Check if specific modules are missing dependencies
2. Verify `backend/` directory structure is correct
3. Ensure all import fallbacks are in place

### Issue: Start script not executing
**Symptoms**: Logs don't show `🚀 CUSTOM START SCRIPT EXECUTING`
**Solution**:
1. Verify `start.sh` is executable: `git ls-files --stage start.sh`
2. Check `railway.toml` has correct `startCommand = "./start.sh"`
3. Ensure no conflicting `Procfile` exists

### Issue: Authentication failures
**Symptoms**: All endpoints return authentication errors
**Solution**:
1. Verify `CLERK_PUBLISHABLE_KEY` is set correctly
2. Check `ENVIRONMENT=production` is set
3. Test with `/debug/auth-config` endpoint

## 📋 Success Criteria

✅ **Router Registration**: `/debug/router-status` shows all 3 v2 prefixes  
✅ **Authentication**: v2 routes return 401 Unauthorized (not 404)  
✅ **OpenAPI**: `/openapi.json` includes `/v2/projects/`, `/v2/chapters/`, `/v2/users/`  
✅ **Health**: `/health` and `/status` return 200 OK  
✅ **Logs**: No critical import errors in deployment logs  

## 🎯 Next Steps After Successful Deployment

1. **Configure Firestore** (if needed):
   - Set up Google Cloud service account
   - Add `SERVICE_ACCOUNT_JSON` environment variable
   - Set `USE_FIRESTORE=true`

2. **Add OpenAI** (for content generation):
   - Obtain OpenAI API key
   - Set `OPENAI_API_KEY` environment variable

3. **Set up monitoring**:
   - Configure Railway health checks
   - Set up log aggregation if needed

4. **Frontend integration**:
   - Update frontend to use new Railway URL
   - Test authentication flow end-to-end

---

**Last Updated**: 2025-01-23  
**Status**: Ready for deployment ✅ 