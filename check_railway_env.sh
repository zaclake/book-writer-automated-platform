#!/bin/bash

echo "🔍 Railway Environment Variable Checker"
echo "========================================"

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install it first:"
    echo "npm install -g @railway/cli"
    exit 1
fi

echo "✅ Railway CLI found"

# Check Railway login status
if ! railway status &> /dev/null; then
    echo "❌ Not logged in to Railway. Please run: railway login"
    exit 1
fi

echo "✅ Logged in to Railway"

echo ""
echo "📋 Current Environment Variables:"
echo "================================="

# List current environment variables
railway variables

echo ""
echo "🎯 CRITICAL VARIABLES NEEDED FOR FIRESTORE:"
echo "==========================================="
echo "✅ USE_FIRESTORE=true"
echo "✅ GOOGLE_CLOUD_PROJECT=writer-bloom"
echo "✅ SERVICE_ACCOUNT_JSON={...json content...}"
echo "✅ ENVIRONMENT=production"

echo ""
echo "🔧 To set missing variables, run:"
echo "railway variables set USE_FIRESTORE=true"
echo "railway variables set GOOGLE_CLOUD_PROJECT=writer-bloom"
echo "railway variables set ENVIRONMENT=production"
echo "railway variables set SERVICE_ACCOUNT_JSON='your-json-here'"

