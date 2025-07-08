#!/bin/bash

# 🚀 Book Writer Automated - Full Deployment Script
# This script handles deployment to all platforms: GitHub, Vercel, and Railway

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "\n${BLUE}🚀 $1${NC}"
}

# Check if required tools are installed
check_dependencies() {
    log_step "Checking dependencies..."
    
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed"
        exit 1
    fi
    
    if ! command -v npx &> /dev/null; then
        log_error "npx is not installed"
        exit 1
    fi
    
    if ! command -v railway &> /dev/null; then
        log_warning "Railway CLI not found. Backend deployment will be skipped."
        log_info "Install with: npm install -g @railway/cli"
        RAILWAY_AVAILABLE=false
    else
        RAILWAY_AVAILABLE=true
    fi
    
    log_success "Dependencies checked"
}

# Check git status
check_git_status() {
    log_step "Checking git status..."
    
    if [[ $(git status --porcelain) ]]; then
        log_warning "You have uncommitted changes:"
        git status --short
        read -p "Do you want to commit these changes? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            commit_changes
        else
            log_error "Please commit or stash your changes before deploying"
            exit 1
        fi
    else
        log_success "Working directory is clean"
    fi
}

# Commit changes
commit_changes() {
    log_step "Committing changes..."
    
    # Add all files except those in .gitignore
    git add .
    
    # Get commit message from user
    read -p "Enter commit message: " COMMIT_MESSAGE
    if [[ -z "$COMMIT_MESSAGE" ]]; then
        COMMIT_MESSAGE="Deploy: $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    
    git commit -m "$COMMIT_MESSAGE"
    log_success "Changes committed"
}

# Run frontend tests and build
test_frontend() {
    log_step "Testing frontend build..."
    
    # Install dependencies
    log_info "Installing frontend dependencies..."
    npm install
    
    # Run type checking
    log_info "Running TypeScript type check..."
    npx tsc --noEmit
    
    # Test build
    log_info "Testing production build..."
    npm run build
    
    log_success "Frontend build successful"
}

# Deploy to GitHub
deploy_github() {
    log_step "Deploying to GitHub..."
    
    # Get current branch
    CURRENT_BRANCH=$(git branch --show-current)
    
    # Push to origin
    git push origin $CURRENT_BRANCH
    
    log_success "Pushed to GitHub ($CURRENT_BRANCH)"
}

# Deploy to Vercel
deploy_vercel() {
    log_step "Deploying to Vercel..."
    
    # Deploy to production
    log_info "Triggering Vercel production deployment..."
    npx vercel --prod --yes
    
    log_success "Deployed to Vercel"
}

# Deploy to Railway
deploy_railway() {
    if [[ "$RAILWAY_AVAILABLE" == false ]]; then
        log_warning "Skipping Railway deployment (CLI not available)"
        return
    fi
    
    log_step "Deploying to Railway..."
    
    # Change to backend directory
    cd backend
    
    # Check Railway connection
    log_info "Checking Railway connection..."
    if ! railway status &> /dev/null; then
        log_error "Not connected to Railway. Please run: railway login"
        cd ..
        return 1
    fi
    
    # Deploy backend
    log_info "Deploying backend to Railway..."
    railway up
    
    # Return to root directory
    cd ..
    
    log_success "Deployed to Railway"
}

# Verify deployments
verify_deployments() {
    log_step "Verifying deployments..."
    
    # Check Vercel deployment
    log_info "Checking Vercel deployment..."
    if curl -s -I https://www.writerbloom.com | grep -q "200 OK\|200"; then
        log_success "Vercel deployment verified (https://www.writerbloom.com)"
    else
        log_warning "Vercel deployment may still be building"
    fi
    
    # Check Railway deployment
    if [[ "$RAILWAY_AVAILABLE" == true ]]; then
        log_info "Checking Railway deployment..."
        if curl -s -I https://silky-loss-production.up.railway.app | grep -q "200\|404"; then
            log_success "Railway deployment verified (https://silky-loss-production.up.railway.app)"
        else
            log_warning "Railway deployment may still be building"
        fi
    fi
}

# Main deployment function
main() {
    echo -e "${BLUE}"
    echo "🚀 Book Writer Automated - Deployment Script"
    echo "=============================================="
    echo -e "${NC}"
    
    # Parse command line arguments
    SKIP_TESTS=false
    DEPLOY_TARGET="all"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --frontend-only)
                DEPLOY_TARGET="frontend"
                shift
                ;;
            --backend-only)
                DEPLOY_TARGET="backend"
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --skip-tests      Skip frontend build tests"
                echo "  --frontend-only   Deploy only frontend (Vercel)"
                echo "  --backend-only    Deploy only backend (Railway)"
                echo "  --help           Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Run deployment steps
    check_dependencies
    check_git_status
    
    if [[ "$SKIP_TESTS" == false && ("$DEPLOY_TARGET" == "all" || "$DEPLOY_TARGET" == "frontend") ]]; then
        test_frontend
    fi
    
    deploy_github
    
    if [[ "$DEPLOY_TARGET" == "all" || "$DEPLOY_TARGET" == "frontend" ]]; then
        deploy_vercel
    fi
    
    if [[ "$DEPLOY_TARGET" == "all" || "$DEPLOY_TARGET" == "backend" ]]; then
        deploy_railway
    fi
    
    verify_deployments
    
    echo -e "\n${GREEN}🎉 Deployment completed successfully!${NC}"
    echo -e "${BLUE}📱 Frontend: https://www.writerbloom.com${NC}"
    echo -e "${BLUE}🔧 Backend: https://silky-loss-production.up.railway.app${NC}"
    echo -e "${BLUE}📚 GitHub: https://github.com/zaclake/book-writer-automated-platform${NC}"
}

# Run main function
main "$@" 