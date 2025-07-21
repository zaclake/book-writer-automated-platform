# 📚 WriterBloom - AI-Powered Book Writing Platform

An intelligent book writing platform that streamlines the entire book creation process from concept to completed manuscript. Create professional-quality novels through a clean, distraction-free writing experience with AI assistance.

## ✨ **New Streamlined Workflow**

**One Simple Flow**: Setup Wizard → Book Bible Creation → Reference Review → Clean Mode Writing

1. **Choose Your Setup** (QuickStart, Guided Wizard, or Paste-In)
2. **Book Bible + References Generated Automatically** ✨ *NEW: No separate steps!*
3. **Review & Approve References** in beautiful tabbed interface
4. **Start Writing** in distraction-free Clean Mode editor

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ 
- Python 3.11+
- OpenAI API Key (required for AI-powered content generation)
- Clerk Account (for authentication)
- Firebase/Firestore project (for data storage)

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

**Required Environment Variables:**

**Frontend (.env.local):**
```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
ENABLE_OPENAI_EXPANSION=true  # Toggle AI features

# Clerk Authentication
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your-key
CLERK_SECRET_KEY=sk_test_your-key

# Backend URL
NEXT_PUBLIC_BACKEND_URL=https://your-backend-url.railway.app
```

**Backend (.env):**
```bash
# API Keys
OPENAI_API_KEY=your_openai_api_key_here
ENABLE_OPENAI_EXPANSION=true  # Enable/disable AI expansion

# Clerk Authentication
CLERK_SECRET_KEY=your_clerk_secret_key_here
CLERK_JWT_ISSUER=your_clerk_jwt_issuer_here

# Firestore Configuration
USE_FIRESTORE=true
GOOGLE_CLOUD_PROJECT=your-project-id
SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# AI Content Generation
DEFAULT_AI_MODEL=gpt-4o
DEFAULT_AI_TEMPERATURE=0.7
DEFAULT_AI_MAX_TOKENS=4000
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

---

## 🎨 **Writing Experience Overview**

### **Clean Mode Writing Interface**

When it's time to write, the UI disappears. Experience a beautiful, minimalist writing studio with:

- **Elegant Typography**: Literata serif font optimized for long-form writing
- **Optimal Reading Width**: 60-70 character line length for perfect readability  
- **Distraction-Free Editor**: Full-screen inline editing with no UI clutter
- **Floating Action Bar**: Save, Rewrite, and Approve actions stay accessible but unobtrusive
- **Smart Sidebar**: Collapsible reference access without breaking focus

### **Reference Review System**

Before writing, review AI-generated reference materials in a clean tabbed interface:

- **📖 Characters**: Character profiles, relationships, and development arcs
- **📋 Plot Outline**: Story structure, chapter breakdown, and key plot points  
- **🌍 World/Glossary**: Setting details, world rules, and location descriptions
- **✍️ Style & Tone**: Writing voice, narrative preferences, and style guidelines
- **⭐ Must-Includes**: Timeline, key events, and essential story elements

Each reference can be edited and approved individually. Progress tracking shows completion status with a sticky "Finish Review & Start Writing" button.

---

## 📖 **Book Bible Creation System**

### **🚀 QuickStart Mode (5-10 minutes)**
Perfect for writers with a basic story concept:
- Title & Genre
- Brief Premise (one sentence)
- Main Character description
- Setting (time and place)
- Central Conflict

**AI Enhancement**: Expands your basic inputs into comprehensive reference materials automatically.

### **🧙‍♂️ Guided Wizard Mode (15-20 minutes)**
Comprehensive step-by-step guidance for detailed planning:
- Detailed character development
- World-building assistance  
- Plot structure breakdown
- Theme and tone guidance
- Target audience definition

**AI Enhancement**: Creates detailed reference files with rich backstories, world details, and plot development.

### **📋 Paste-In Mode (2-5 minutes)**
For writers who already have detailed notes:
- Paste existing book bible content
- AI organizes and structures your material
- Automatically generates missing reference types
- Maintains your original vision while filling gaps

**All modes now include automatic reference generation - no extra steps required!** 