# Firebase Setup Guide for Collaborative Projects Fix

## Issue Fixed
The error "Missing or insufficient permissions" was caused by missing Firebase Authentication integration. The Firestore security rules were correct, but Firebase Auth was not configured.

## What Was Done

### 1. Updated Firestore Security Rules
- Added `allow list` permissions for project queries
- Updated both `firestore.rules` and `backend/firestore.rules`
- Deployed the rules to Firebase

### 2. Added Firebase Auth Integration  
- Created `/api/firebase-auth/route.ts` endpoint for custom token generation
- Updated `src/lib/firestore-client.ts` to include Firebase Auth
- Updated `src/hooks/useFirestore.ts` to authenticate before subscriptions

### 3. Required Environment Variables

You need to add these to your `.env.local` file:

```bash
# Firebase Client Configuration (get from Firebase Console > Project Settings > Your apps)
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key-here
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=writer-bloom.firebaseapp.com  
NEXT_PUBLIC_FIREBASE_PROJECT_ID=writer-bloom
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=writer-bloom.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=681297692294
NEXT_PUBLIC_FIREBASE_APP_ID=1:681297692294:web:6bebc5668ea47c037cb307

# Firebase Admin SDK (for generating custom tokens)
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"writer-bloom",...entire JSON here...}
```

## Setup Steps

### Step 1: Get Firebase Web App Config
1. Visit: https://console.firebase.google.com/project/writer-bloom/settings/general
2. Scroll to "Your apps" section  
3. Click on the "writer-bloom" web app
4. Copy the config values

### Step 2: Get Service Account Key
1. Visit: https://console.firebase.google.com/project/writer-bloom/settings/serviceaccounts/adminsdk
2. Click "Generate new private key"
3. Download the JSON file
4. Copy the entire JSON content to `FIREBASE_SERVICE_ACCOUNT_KEY`

### Step 3: Update Environment Variables
Create/update `.env.local` with the values from steps 1 and 2.

## How It Works

1. **User signs in with Clerk** (existing auth system)
2. **Frontend calls `/api/firebase-auth`** to get Firebase custom token
3. **Firebase Auth signs in** with the custom token  
4. **Firestore security rules** now recognize the authenticated user
5. **Real-time subscriptions work** for both owned and collaborative projects

## Testing the Fix

After setting up the environment variables:

1. Restart the dev server: `npm run dev`
2. Sign in to the app
3. Check browser console - should see "✅ Successfully authenticated with Firebase"  
4. No more "Missing or insufficient permissions" errors
5. Collaborative projects should load properly

## Fallback

If Firebase Auth fails, the app will show a clear error message instead of infinite loading. You can always fall back to the API-based project loading by removing the Firebase Auth calls temporarily. 