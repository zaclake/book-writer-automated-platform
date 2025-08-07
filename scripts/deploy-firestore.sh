#!/bin/bash

# Deploy Firestore configuration for credits system
# This script deploys security rules and indexes to Firestore

set -e

echo "🚀 Deploying Firestore configuration for credits system..."

# Check if Firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI not found. Please install it first:"
    echo "   npm install -g firebase-tools"
    exit 1
fi

# Check if user is logged in
if ! firebase projects:list &> /dev/null; then
    echo "❌ Not logged in to Firebase. Please run:"
    echo "   firebase login"
    exit 1
fi

# Get current project
PROJECT=$(firebase use --alias default 2>/dev/null | grep "Now using alias" | awk '{print $4}' || echo "")
if [ -z "$PROJECT" ]; then
    echo "❌ No Firebase project configured. Please run:"
    echo "   firebase use --add"
    exit 1
fi

echo "📁 Using Firebase project: $PROJECT"

# Deploy Firestore rules
echo "🔒 Deploying Firestore security rules..."
if [ -f "firestore.rules" ]; then
    firebase deploy --only firestore:rules
    echo "✅ Security rules deployed"
else
    echo "❌ firestore.rules file not found"
    exit 1
fi

# Deploy Firestore indexes
echo "📊 Deploying Firestore indexes..."
if [ -f "firestore.indexes.json" ]; then
    firebase deploy --only firestore:indexes
    echo "✅ Indexes deployed"
else
    echo "❌ firestore.indexes.json file not found"
    exit 1
fi

echo ""
echo "🎉 Firestore configuration deployed successfully!"
echo ""
echo "Next steps:"
echo "1. Run the pricing data initialization script:"
echo "   cd backend && python scripts/init_pricing_data.py"
echo ""
echo "2. Set environment variables for your deployment:"
echo "   - ENABLE_CREDITS_SYSTEM=true"
echo "   - ENABLE_CREDITS_BILLING=true"
echo "   - ENABLE_BETA_CREDITS=true (for beta)"
echo "   - CREDITS_MARKUP=5.0"
echo ""
echo "3. Deploy your backend with the credits system enabled"