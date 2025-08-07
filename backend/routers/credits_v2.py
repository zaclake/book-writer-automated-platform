#!/usr/bin/env python3
"""
Credits API Router (v2)
Handles credit balance, transactions, and purchases for the credit system.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, Field
from auth_middleware import verify_token

# Import credit services
try:
    from backend.services.credits_service import get_credits_service, CreditTransaction, TransactionType
    from backend.services.pricing_registry import get_pricing_registry
    from backend.services.billable_client import estimate_credits_for_chat, estimate_credits_for_image
    from backend.database_integration import get_database_adapter
except ImportError:
    from services.credits_service import get_credits_service, CreditTransaction, TransactionType
    from services.pricing_registry import get_pricing_registry
    from services.billable_client import estimate_credits_for_chat, estimate_credits_for_image
    from database_integration import get_database_adapter

logger = logging.getLogger(__name__)

# Simple in-memory cache for balance requests (15-second TTL)
_balance_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 15

def get_cached_balance(user_id: str) -> Optional[Dict[str, Any]]:
    """Get cached balance if it exists and is fresh."""
    if user_id in _balance_cache:
        cache_entry = _balance_cache[user_id]
        if time.time() - cache_entry['timestamp'] < CACHE_TTL_SECONDS:
            logger.debug(f"Using cached balance for user {user_id}")
            return cache_entry['data']
        else:
            # Cache expired, remove it
            del _balance_cache[user_id]
    return None

def cache_balance(user_id: str, balance_data: Dict[str, Any]) -> None:
    """Cache balance data for the user."""
    _balance_cache[user_id] = {
        'data': balance_data,
        'timestamp': time.time()
    }
    logger.debug(f"Cached balance for user {user_id}")

# Initialize router
router = APIRouter(
    prefix="/v2/credits",
    tags=["credits"],
    responses={404: {"description": "Not found"}},
)

# Response models
class BalanceResponse(BaseModel):
    """Credit balance response."""
    balance: int
    pending_debits: int = 0
    available_balance: int
    last_updated: datetime
    
class TransactionResponse(BaseModel):
    """Credit transaction response."""
    txn_id: str
    amount: int
    type: str
    status: str
    reason: str
    balance_after: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    meta: Dict[str, Any] = {}

class TransactionListResponse(BaseModel):
    """Transaction list response."""
    transactions: List[TransactionResponse]
    has_more: bool = False
    next_cursor: Optional[str] = None

class EstimateResponse(BaseModel):
    """Credit estimate response."""
    estimated_credits: int
    estimated_cost_usd: float
    markup_applied: float
    calculation_details: Dict[str, Any]

# Request models
class GrantCreditsRequest(BaseModel):
    """Request to grant credits to a user."""
    amount: int = Field(..., gt=0, description="Credits to grant (positive integer)")
    reason: str = Field(..., min_length=1, max_length=200, description="Reason for granting credits")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata")

class EstimateRequest(BaseModel):
    """Request to estimate credits for an operation."""
    operation_type: str = Field(..., description="Type of operation (chat, image)")
    model: str = Field(..., description="Model name")
    prompt_text: Optional[str] = Field(None, description="Prompt text for chat operations")
    max_tokens: Optional[int] = Field(4000, description="Max tokens for chat operations")
    image_count: Optional[int] = Field(1, description="Number of images for image operations")

class PurchaseRequest(BaseModel):
    """Request to purchase credits (stub for Stripe integration)."""
    package: str = Field(..., description="Credit package (1k, 5k, 10k)")
    payment_method_id: Optional[str] = Field(None, description="Stripe payment method ID")

# Helper functions
def get_credits_service_instance():
    """Get credits service instance."""
    db_adapter = get_database_adapter()
    if db_adapter and hasattr(db_adapter, 'firestore'):
        return get_credits_service(db_adapter.firestore)
    return None

def get_pricing_registry_instance():
    """Get pricing registry instance."""
    db_adapter = get_database_adapter()
    if db_adapter and hasattr(db_adapter, 'firestore'):
        return get_pricing_registry(db_adapter.firestore)
    return None

def check_credits_feature_enabled():
    """Check if credits feature is enabled."""
    enabled = os.getenv('ENABLE_CREDITS_SYSTEM', 'false').lower() == 'true'
    if not enabled:
        raise HTTPException(
            status_code=501,
            detail="Credits system is not enabled on this server"
        )

def check_admin_permissions(user_info: Dict[str, str]):
    """Check if user has admin permissions."""
    # This is a simplified check - in production you'd check roles/permissions
    is_admin = user_info.get('email', '').endswith('@yourdomain.com')  # Replace with actual admin check
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Administrator permissions required"
        )

# API Endpoints

@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    request: Request,
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Get current credit balance for the authenticated user.
    """
    check_credits_feature_enabled()
    
    try:
        user_id = user_info['user_id']
        
        # Check cache first
        cached_data = get_cached_balance(user_id)
        if cached_data:
            return BalanceResponse(**cached_data)
        
        # Get credits service
        credits_service = get_credits_service_instance()
        if not credits_service or not credits_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Credits service temporarily unavailable"
            )
        
        # Get balance from service
        balance_info = await credits_service.get_balance(user_id)
        if not balance_info:
            # Initialize credits for new user
            await credits_service.initialize_user_credits(user_id, 0, "account_creation")
            balance_info = await credits_service.get_balance(user_id)
            
            if not balance_info:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to retrieve user balance"
                )
        
        available_balance = balance_info.balance - balance_info.pending_debits
        
        response_data = {
            "balance": balance_info.balance,
            "pending_debits": balance_info.pending_debits,
            "available_balance": max(0, available_balance),
            "last_updated": balance_info.last_updated
        }
        
        # Cache the response
        cache_balance(user_id, response_data)
        
        return BalanceResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get balance for user {user_info.get('user_id')}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve balance"
        )

@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    request: Request,
    limit: int = 25,
    cursor: Optional[str] = None,
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Get transaction history for the authenticated user.
    """
    check_credits_feature_enabled()
    
    try:
        user_id = user_info['user_id']
        
        # Validate limit
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 100"
            )
        
        # Get credits service
        credits_service = get_credits_service_instance()
        if not credits_service or not credits_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Credits service temporarily unavailable"
            )
        
        # Get transactions
        transactions = await credits_service.get_transactions(
            user_id=user_id,
            limit=limit + 1,  # Get one extra to check if there are more
            start_after=cursor
        )
        
        # Check if there are more results
        has_more = len(transactions) > limit
        if has_more:
            transactions = transactions[:limit]
        
        # Convert to response format
        transaction_responses = []
        for txn in transactions:
            transaction_responses.append(TransactionResponse(
                txn_id=txn.txn_id,
                amount=txn.amount,
                type=txn.type.value,
                status=txn.status.value,
                reason=txn.reason,
                balance_after=txn.balance_after,
                created_at=txn.created_at,
                completed_at=txn.completed_at,
                meta=txn.meta
            ))
        
        # Get next cursor
        next_cursor = transactions[-1].txn_id if has_more and transactions else None
        
        return TransactionListResponse(
            transactions=transaction_responses,
            has_more=has_more,
            next_cursor=next_cursor
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get transactions for user {user_info.get('user_id')}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve transactions"
        )

@router.post("/estimate", response_model=EstimateResponse)
async def estimate_credits(request: EstimateRequest):
    """
    Estimate credits required for an operation.
    """
    check_credits_feature_enabled()
    
    try:
        # Get pricing registry
        pricing_registry = get_pricing_registry_instance()
        if not pricing_registry or not pricing_registry.is_available():
            raise HTTPException(
                status_code=503,
                detail="Pricing service temporarily unavailable"
            )
        
        # Estimate credits based on operation type
        if request.operation_type == 'chat':
            if not request.prompt_text:
                raise HTTPException(
                    status_code=400,
                    detail="prompt_text is required for chat operations"
                )
            
            estimate = await estimate_credits_for_chat(
                user_id="anonymous",  # Public estimation doesn't require specific user
                model=request.model,
                prompt_text=request.prompt_text,
                max_tokens=request.max_tokens or 4000
            )
            
        elif request.operation_type == 'image':
            estimate = await estimate_credits_for_image(
                user_id="anonymous",  # Public estimation doesn't require specific user
                model=request.model,
                count=request.image_count or 1
            )
            
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported operation_type. Use 'chat' or 'image'"
            )
        
        if 'error' in estimate:
            raise HTTPException(
                status_code=503,
                detail=estimate['error']
            )
        
        return EstimateResponse(
            estimated_credits=estimate['estimated_credits'],
            estimated_cost_usd=estimate['estimated_cost_usd'],
            markup_applied=estimate['markup_applied'],
            calculation_details=estimate['calculation_details']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to estimate credits: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to estimate credits"
        )

@router.post("/admin/users/{target_user_id}/grant")
async def grant_credits(
    target_user_id: str,
    request: GrantCreditsRequest,
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Grant credits to a user (admin only).
    """
    check_credits_feature_enabled()
    check_admin_permissions(user_info)
    
    try:
        admin_user_id = user_info['user_id']
        
        # Get credits service
        credits_service = get_credits_service_instance()
        if not credits_service or not credits_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Credits service temporarily unavailable"
            )
        
        # Add metadata about who granted the credits
        meta = request.meta.copy()
        meta.update({
            'granted_by': admin_user_id,
            'granted_by_email': user_info.get('email'),
            'admin_action': True
        })
        
        # Grant credits
        transaction = await credits_service.add_credits(
            user_id=target_user_id,
            amount=request.amount,
            reason=request.reason,
            meta=meta
        )
        
        if not transaction:
            raise HTTPException(
                status_code=500,
                detail="Failed to grant credits"
            )
        
        logger.info(f"Admin {admin_user_id} granted {request.amount} credits to user {target_user_id}")
        
        return {
            "success": True,
            "transaction_id": transaction.txn_id,
            "amount_granted": request.amount,
            "new_balance": transaction.balance_after,
            "message": f"Successfully granted {request.amount} credits"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to grant credits: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to grant credits"
        )

@router.post("/purchase")
async def purchase_credits(
    request: PurchaseRequest,
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Purchase credits (stub for future Stripe integration).
    """
    check_credits_feature_enabled()
    
    # This is a stub endpoint for future Stripe integration
    raise HTTPException(
        status_code=501,
        detail={
            "error": "FEATURE_NOT_IMPLEMENTED",
            "message": "Credit purchasing is not yet available",
            "coming_soon": True,
            "contact_support": "Please contact support for credit top-ups"
        }
    )

@router.get("/admin/pricing")
async def get_pricing_info(
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Get current pricing information (admin only).
    """
    check_credits_feature_enabled()
    check_admin_permissions(user_info)
    
    try:
        # Get pricing registry
        pricing_registry = get_pricing_registry_instance()
        if not pricing_registry or not pricing_registry.is_available():
            raise HTTPException(
                status_code=503,
                detail="Pricing service temporarily unavailable"
            )
        
        # Get current pricing for common models
        models = [
            ('openai', 'gpt-4o'),
            ('openai', 'gpt-4o-mini'),
            ('openai', 'dall-e-3'),
            ('replicate', 'stable-diffusion-3')
        ]
        
        pricing_info = {}
        for provider, model in models:
            model_pricing = pricing_registry.get_model_pricing(provider, model)
            markup = pricing_registry.get_markup_multiplier(provider)
            
            if model_pricing:
                pricing_info[f"{provider}:{model}"] = {
                    'provider': provider,
                    'model': model,
                    'input_usd_per_1k': model_pricing.input_usd_per_1k,
                    'output_usd_per_1k': model_pricing.output_usd_per_1k,
                    'job_usd': model_pricing.job_usd,
                    'markup_multiplier': markup,
                    'last_updated': model_pricing.last_updated.isoformat() if model_pricing.last_updated else None
                }
        
        return {
            'pricing': pricing_info,
            'credit_conversion_rate': 100,  # 100 credits per dollar
            'retrieved_at': datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pricing info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve pricing information"
        )

@router.post("/admin/beta-credits/initialize")
async def initialize_beta_credits(
    user_info: Dict[str, str] = Depends(verify_token)
):
    """
    Initialize beta credits for the authenticated user (controlled by ENABLE_BETA_CREDITS env).
    """
    check_credits_feature_enabled()
    
    try:
        user_id = user_info['user_id']
        
        # Check if beta credits are enabled
        beta_enabled = os.getenv('ENABLE_BETA_CREDITS', 'false').lower() == 'true'
        if not beta_enabled:
            raise HTTPException(
                status_code=403,
                detail="Beta credits are not enabled on this server"
            )
        
        # Get credits service
        credits_service = get_credits_service_instance()
        if not credits_service or not credits_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Credits service temporarily unavailable"
            )
        
        # Check if user already has beta credits
        balance_info = await credits_service.get_balance(user_id)
        if balance_info and balance_info.balance > 0:
            return {
                "already_initialized": True,
                "current_balance": balance_info.balance,
                "message": "User already has credits"
            }
        
        # Initialize user credits if needed
        if not balance_info:
            await credits_service.initialize_user_credits(user_id, 0, "account_creation")
        
        # Grant beta credits (2,000 credits = $20 value at 5x markup)
        beta_amount = 2000
        transaction = await credits_service.add_credits(
            user_id=user_id,
            amount=beta_amount,
            reason="beta_grant",
            meta={
                'source': 'beta_initialization',
                'granted_by_email': user_info.get('email'),
                'beta_program': True,
                'value_usd': 20.0  # $20 value to user
            }
        )
        
        if not transaction:
            raise HTTPException(
                status_code=500,
                detail="Failed to grant beta credits"
            )
        
        logger.info(f"Granted {beta_amount} beta credits to user {user_id} ({user_info.get('email')})")
        
        return {
            "success": True,
            "credits_granted": beta_amount,
            "new_balance": transaction.balance_after,
            "transaction_id": transaction.txn_id,
            "value_usd": 20.0,
            "message": f"Successfully granted {beta_amount} beta credits ($20 value)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize beta credits for user {user_info.get('user_id')}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize beta credits"
        )

@router.get("/health")
async def credits_health_check():
    """
    Health check for credits system.
    """
    try:
        # Check if feature is enabled
        enabled = os.getenv('ENABLE_CREDITS_SYSTEM', 'false').lower() == 'true'
        if not enabled:
            return {
                "status": "disabled",
                "message": "Credits system is disabled"
            }
        
        # Check services
        credits_service = get_credits_service_instance()
        pricing_registry = get_pricing_registry_instance()
        
        credits_available = credits_service and credits_service.is_available()
        pricing_available = pricing_registry and pricing_registry.is_available()
        
        status = "healthy" if credits_available and pricing_available else "degraded"
        
        return {
            "status": status,
            "credits_service": "available" if credits_available else "unavailable",
            "pricing_registry": "available" if pricing_available else "unavailable",
            "feature_enabled": enabled,
            "billing_enabled": os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true',
            "beta_credits_enabled": os.getenv('ENABLE_BETA_CREDITS', 'false').lower() == 'true'
        }
        
    except Exception as e:
        logger.error(f"Credits health check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }