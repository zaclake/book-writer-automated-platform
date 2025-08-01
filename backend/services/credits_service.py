#!/usr/bin/env python3
"""
Credits Service
Manages user credit balances with transaction-safe operations and provisional debiting.
"""

import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)

class TransactionType(Enum):
    """Credit transaction types."""
    CREDIT = "credit"
    DEBIT = "debit"
    PROVISIONAL_DEBIT = "provisional_debit"
    VOID = "void"
    REFUND = "refund"

class TransactionStatus(Enum):
    """Transaction status."""
    PENDING = "pending"
    COMPLETED = "completed"
    VOID = "void"
    FAILED = "failed"

@dataclass
class CreditTransaction:
    """Credit transaction record."""
    txn_id: str
    user_id: str
    amount: int
    type: TransactionType
    status: TransactionStatus
    reason: str
    meta: Dict[str, Any]
    balance_after: Optional[int] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dedupe_key: Optional[str] = None
    ref_id: Optional[str] = None
    price_snapshot: Optional[Dict[str, Any]] = None

@dataclass
class CreditBalance:
    """User credit balance information."""
    user_id: str
    balance: int
    last_updated: datetime
    pending_debits: int = 0

class InsufficientCreditsError(Exception):
    """Raised when user has insufficient credits for an operation."""
    def __init__(self, required: int, available: int, user_id: str):
        self.required = required
        self.available = available  
        self.user_id = user_id
        super().__init__(f"Insufficient credits for user {user_id}: required {required}, available {available}")

class CreditsService:
    """
    Service for managing user credit balances with transaction safety.
    Supports provisional debiting for long-running operations.
    """
    
    def __init__(self, firestore_service):
        """Initialize the credits service."""
        self.firestore_service = firestore_service
        self._available = firestore_service and firestore_service.available
        
        if not self._available:
            logger.warning("CreditsService initialized without Firestore - credits system disabled")
    
    def is_available(self) -> bool:
        """Check if credits service is available."""
        return self._available
    
    async def get_balance(self, user_id: str) -> Optional[CreditBalance]:
        """
        Get current credit balance for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            CreditBalance or None if user not found
        """
        if not self.is_available():
            return None
        
        try:
            # Get user document
            user_doc = await self.firestore_service.get_user(user_id)
            if not user_doc:
                logger.warning(f"User {user_id} not found when getting balance")
                return None
            
            credits_data = user_doc.get('credits', {})
            balance = credits_data.get('balance', 0)
            last_updated = credits_data.get('last_updated', datetime.now(timezone.utc))
            
            # Calculate pending debits
            pending_debits = await self._calculate_pending_debits(user_id)
            
            return CreditBalance(
                user_id=user_id,
                balance=balance,
                last_updated=last_updated,
                pending_debits=pending_debits
            )
            
        except Exception as e:
            logger.error(f"Failed to get balance for user {user_id}: {e}")
            return None
    
    async def _calculate_pending_debits(self, user_id: str) -> int:
        """Calculate total pending debit amount for a user."""
        try:
            # Query for pending provisional debits
            query = self.firestore_service.db.collection('users').document(user_id)\
                        .collection('credits_transactions')\
                        .where('type', '==', TransactionType.PROVISIONAL_DEBIT.value)\
                        .where('status', '==', TransactionStatus.PENDING.value)
            
            docs = await asyncio.get_event_loop().run_in_executor(None, lambda: list(query.stream()))
            
            total_pending = sum(doc.to_dict().get('amount', 0) for doc in docs)
            return total_pending
            
        except Exception as e:
            logger.error(f"Failed to calculate pending debits for user {user_id}: {e}")
            return 0
    
    async def add_credits(self, user_id: str, amount: int, reason: str, 
                         meta: Optional[Dict[str, Any]] = None,
                         dedupe_key: Optional[str] = None) -> Optional[CreditTransaction]:
        """
        Add credits to a user's balance.
        
        Args:
            user_id: User ID
            amount: Credits to add (positive integer)
            reason: Reason for credit addition
            meta: Optional metadata
            dedupe_key: Optional deduplication key
            
        Returns:
            CreditTransaction or None if failed
        """
        if not self.is_available():
            return None
        
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        
        try:
            txn_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Check for duplicate transaction
            if dedupe_key:
                existing = await self._find_transaction_by_dedupe_key(user_id, dedupe_key)
                if existing:
                    logger.warning(f"Duplicate credit transaction detected for user {user_id}, dedupe_key {dedupe_key}")
                    return existing
            
            # Use Firestore transaction for atomicity
            @self.firestore_service.db.transactional
            def add_credits_transaction(transaction):
                # Get current user document
                user_ref = self.firestore_service.db.collection('users').document(user_id)
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise ValueError(f"User {user_id} not found")
                
                user_data = user_doc.to_dict()
                credits_data = user_data.get('credits', {})
                current_balance = credits_data.get('balance', 0)
                new_balance = current_balance + amount
                
                # Update user balance
                transaction.update(user_ref, {
                    'credits.balance': new_balance,
                    'credits.last_updated': now
                })
                
                # Create transaction record
                txn_data = {
                    'txn_id': txn_id,
                    'user_id': user_id,
                    'amount': amount,
                    'type': TransactionType.CREDIT.value,
                    'status': TransactionStatus.COMPLETED.value,
                    'reason': reason,
                    'meta': meta or {},
                    'balance_after': new_balance,
                    'created_at': now,
                    'completed_at': now,
                    'dedupe_key': dedupe_key
                }
                
                txn_ref = user_ref.collection('credits_transactions').document(txn_id)
                transaction.set(txn_ref, txn_data)
                
                return CreditTransaction(
                    txn_id=txn_id,
                    user_id=user_id,
                    amount=amount,
                    type=TransactionType.CREDIT,
                    status=TransactionStatus.COMPLETED,
                    reason=reason,
                    meta=meta or {},
                    balance_after=new_balance,
                    created_at=now,
                    completed_at=now,
                    dedupe_key=dedupe_key
                )
            
            # Execute transaction
            db_transaction = self.firestore_service.db.transaction()
            result = add_credits_transaction(db_transaction)
            
            logger.info(f"Added {amount} credits to user {user_id}, new balance: {result.balance_after}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to add credits for user {user_id}: {e}")
            return None
    
    async def deduct_credits(self, user_id: str, amount: int, reason: str,
                           meta: Optional[Dict[str, Any]] = None,
                           dedupe_key: Optional[str] = None,
                           allow_overdraft: bool = False) -> Optional[CreditTransaction]:
        """
        Deduct credits from a user's balance.
        
        Args:
            user_id: User ID
            amount: Credits to deduct (positive integer)
            reason: Reason for deduction
            meta: Optional metadata
            dedupe_key: Optional deduplication key
            allow_overdraft: Whether to allow balance to go negative
            
        Returns:
            CreditTransaction or None if failed
            
        Raises:
            InsufficientCreditsError: If user has insufficient credits
        """
        if not self.is_available():
            return None
        
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        
        try:
            txn_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Check for duplicate transaction
            if dedupe_key:
                existing = await self._find_transaction_by_dedupe_key(user_id, dedupe_key)
                if existing:
                    logger.warning(f"Duplicate debit transaction detected for user {user_id}, dedupe_key {dedupe_key}")
                    return existing
            
            # Use Firestore transaction for atomicity
            @self.firestore_service.db.transactional
            def deduct_credits_transaction(transaction):
                # Get current user document
                user_ref = self.firestore_service.db.collection('users').document(user_id)
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise ValueError(f"User {user_id} not found")
                
                user_data = user_doc.to_dict()
                credits_data = user_data.get('credits', {})
                current_balance = credits_data.get('balance', 0)
                
                # Check for sufficient credits
                if not allow_overdraft and current_balance < amount:
                    raise InsufficientCreditsError(amount, current_balance, user_id)
                
                new_balance = current_balance - amount
                
                # Update user balance
                transaction.update(user_ref, {
                    'credits.balance': new_balance,
                    'credits.last_updated': now
                })
                
                # Create transaction record
                txn_data = {
                    'txn_id': txn_id,
                    'user_id': user_id,
                    'amount': amount,
                    'type': TransactionType.DEBIT.value,
                    'status': TransactionStatus.COMPLETED.value,
                    'reason': reason,
                    'meta': meta or {},
                    'balance_after': new_balance,
                    'created_at': now,
                    'completed_at': now,
                    'dedupe_key': dedupe_key
                }
                
                txn_ref = user_ref.collection('credits_transactions').document(txn_id)
                transaction.set(txn_ref, txn_data)
                
                return CreditTransaction(
                    txn_id=txn_id,
                    user_id=user_id,
                    amount=amount,
                    type=TransactionType.DEBIT,
                    status=TransactionStatus.COMPLETED,
                    reason=reason,
                    meta=meta or {},
                    balance_after=new_balance,
                    created_at=now,
                    completed_at=now,
                    dedupe_key=dedupe_key
                )
            
            # Execute transaction
            db_transaction = self.firestore_service.db.transaction()
            result = deduct_credits_transaction(db_transaction)
            
            logger.info(f"Deducted {amount} credits from user {user_id}, new balance: {result.balance_after}")
            return result
            
        except InsufficientCreditsError:
            raise  # Re-raise insufficient credits error
        except Exception as e:
            logger.error(f"Failed to deduct credits for user {user_id}: {e}")
            return None
    
    async def provisional_debit(self, user_id: str, amount: int, reason: str,
                              meta: Optional[Dict[str, Any]] = None,
                              dedupe_key: Optional[str] = None) -> Optional[CreditTransaction]:
        """
        Create a provisional debit (hold) on credits without immediately deducting them.
        Used for long-running operations that may fail.
        
        Args:
            user_id: User ID
            amount: Credits to hold (positive integer)
            reason: Reason for provisional debit
            meta: Optional metadata
            dedupe_key: Optional deduplication key
            
        Returns:
            CreditTransaction or None if failed
            
        Raises:
            InsufficientCreditsError: If user has insufficient credits
        """
        if not self.is_available():
            return None
        
        if amount <= 0:
            raise ValueError("Provisional debit amount must be positive")
        
        try:
            txn_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Check for duplicate transaction
            if dedupe_key:
                existing = await self._find_transaction_by_dedupe_key(user_id, dedupe_key)
                if existing:
                    logger.warning(f"Duplicate provisional debit detected for user {user_id}, dedupe_key {dedupe_key}")
                    return existing
            
            # Use Firestore transaction for atomicity
            @self.firestore_service.db.transactional
            def provisional_debit_transaction(transaction):
                # Get current user document
                user_ref = self.firestore_service.db.collection('users').document(user_id)
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise ValueError(f"User {user_id} not found")
                
                user_data = user_doc.to_dict()
                credits_data = user_data.get('credits', {})
                current_balance = credits_data.get('balance', 0)
                
                # Check for sufficient credits (including existing pending debits)
                # Note: This is a simplified check - in production you might want to
                # calculate pending debits within the transaction for perfect accuracy
                if current_balance < amount:
                    raise InsufficientCreditsError(amount, current_balance, user_id)
                
                # Create transaction record (no balance change yet)
                txn_data = {
                    'txn_id': txn_id,
                    'user_id': user_id,
                    'amount': amount,
                    'type': TransactionType.PROVISIONAL_DEBIT.value,
                    'status': TransactionStatus.PENDING.value,
                    'reason': reason,
                    'meta': meta or {},
                    'balance_after': None,  # No balance change yet
                    'created_at': now,
                    'completed_at': None,
                    'dedupe_key': dedupe_key
                }
                
                txn_ref = user_ref.collection('credits_transactions').document(txn_id)
                transaction.set(txn_ref, txn_data)
                
                return CreditTransaction(
                    txn_id=txn_id,
                    user_id=user_id,
                    amount=amount,
                    type=TransactionType.PROVISIONAL_DEBIT,
                    status=TransactionStatus.PENDING,
                    reason=reason,
                    meta=meta or {},
                    balance_after=None,
                    created_at=now,
                    completed_at=None,
                    dedupe_key=dedupe_key
                )
            
            # Execute transaction
            db_transaction = self.firestore_service.db.transaction()
            result = provisional_debit_transaction(db_transaction)
            
            logger.info(f"Created provisional debit of {amount} credits for user {user_id}, txn_id: {txn_id}")
            return result
            
        except InsufficientCreditsError:
            raise  # Re-raise insufficient credits error
        except Exception as e:
            logger.error(f"Failed to create provisional debit for user {user_id}: {e}")
            return None
    
    async def finalize_provisional_debit(self, user_id: str, txn_id: str,
                                       final_amount: Optional[int] = None) -> bool:
        """
        Finalize a provisional debit by actually deducting credits.
        
        Args:
            user_id: User ID
            txn_id: Transaction ID of the provisional debit
            final_amount: Final amount to deduct (if different from provisional amount)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            # Use Firestore transaction for atomicity
            @self.firestore_service.db.transactional
            def finalize_transaction(transaction):
                # Get provisional debit transaction
                user_ref = self.firestore_service.db.collection('users').document(user_id)
                txn_ref = user_ref.collection('credits_transactions').document(txn_id)
                txn_doc = txn_ref.get(transaction=transaction)
                
                if not txn_doc.exists:
                    raise ValueError(f"Transaction {txn_id} not found")
                
                txn_data = txn_doc.to_dict()
                
                # Verify this is a pending provisional debit
                if (txn_data.get('type') != TransactionType.PROVISIONAL_DEBIT.value or 
                    txn_data.get('status') != TransactionStatus.PENDING.value):
                    raise ValueError(f"Transaction {txn_id} is not a pending provisional debit")
                
                provisional_amount = txn_data.get('amount', 0)
                amount_to_deduct = final_amount if final_amount is not None else provisional_amount
                
                # Get current user balance
                user_doc = user_ref.get(transaction=transaction)
                if not user_doc.exists:
                    raise ValueError(f"User {user_id} not found")
                
                user_data = user_doc.to_dict()
                credits_data = user_data.get('credits', {})
                current_balance = credits_data.get('balance', 0)
                
                # Check for sufficient credits
                if current_balance < amount_to_deduct:
                    raise InsufficientCreditsError(amount_to_deduct, current_balance, user_id)
                
                new_balance = current_balance - amount_to_deduct
                now = datetime.now(timezone.utc)
                
                # Update user balance
                transaction.update(user_ref, {
                    'credits.balance': new_balance,
                    'credits.last_updated': now
                })
                
                # Update transaction record
                transaction.update(txn_ref, {
                    'status': TransactionStatus.COMPLETED.value,
                    'completed_at': now,
                    'balance_after': new_balance,
                    'amount': amount_to_deduct,  # Update with final amount
                    'meta.finalized_at': now.isoformat(),
                    'meta.original_provisional_amount': provisional_amount
                })
                
                return True
            
            # Execute transaction
            db_transaction = self.firestore_service.db.transaction()
            success = finalize_transaction(db_transaction)
            
            if success:
                logger.info(f"Finalized provisional debit {txn_id} for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to finalize provisional debit {txn_id} for user {user_id}: {e}")
            return False
    
    async def void_provisional_debit(self, user_id: str, txn_id: str, reason: str = "voided") -> bool:
        """
        Void a provisional debit without deducting credits.
        
        Args:
            user_id: User ID
            txn_id: Transaction ID of the provisional debit
            reason: Reason for voiding
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            # Use Firestore transaction for atomicity
            @self.firestore_service.db.transactional
            def void_transaction(transaction):
                # Get provisional debit transaction
                user_ref = self.firestore_service.db.collection('users').document(user_id)
                txn_ref = user_ref.collection('credits_transactions').document(txn_id)
                txn_doc = txn_ref.get(transaction=transaction)
                
                if not txn_doc.exists:
                    raise ValueError(f"Transaction {txn_id} not found")
                
                txn_data = txn_doc.to_dict()
                
                # Verify this is a pending provisional debit
                if (txn_data.get('type') != TransactionType.PROVISIONAL_DEBIT.value or 
                    txn_data.get('status') != TransactionStatus.PENDING.value):
                    raise ValueError(f"Transaction {txn_id} is not a pending provisional debit")
                
                now = datetime.now(timezone.utc)
                
                # Update transaction record to void status
                transaction.update(txn_ref, {
                    'status': TransactionStatus.VOID.value,
                    'completed_at': now,
                    'meta.void_reason': reason,
                    'meta.voided_at': now.isoformat()
                })
                
                return True
            
            # Execute transaction
            db_transaction = self.firestore_service.db.transaction()
            success = void_transaction(db_transaction)
            
            if success:
                logger.info(f"Voided provisional debit {txn_id} for user {user_id}: {reason}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to void provisional debit {txn_id} for user {user_id}: {e}")
            return False
    
    async def get_transactions(self, user_id: str, limit: int = 25, 
                              start_after: Optional[str] = None) -> List[CreditTransaction]:
        """
        Get transaction history for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of transactions to return
            start_after: Transaction ID to start after (for pagination)
            
        Returns:
            List of CreditTransaction objects
        """
        if not self.is_available():
            return []
        
        try:
            # Build query
            query = self.firestore_service.db.collection('users').document(user_id)\
                        .collection('credits_transactions')\
                        .order_by('created_at', direction='DESCENDING')\
                        .limit(limit)
            
            # Handle pagination
            if start_after:
                # Get the start_after document for cursor
                start_doc_ref = self.firestore_service.db.collection('users').document(user_id)\
                                    .collection('credits_transactions').document(start_after)
                start_doc = await asyncio.get_event_loop().run_in_executor(None, start_doc_ref.get)
                if start_doc.exists:
                    query = query.start_after(start_doc)
            
            # Execute query
            docs = await asyncio.get_event_loop().run_in_executor(None, lambda: list(query.stream()))
            
            # Convert to CreditTransaction objects
            transactions = []
            for doc in docs:
                data = doc.to_dict()
                transactions.append(CreditTransaction(
                    txn_id=data.get('txn_id'),
                    user_id=data.get('user_id'),
                    amount=data.get('amount'),
                    type=TransactionType(data.get('type')),
                    status=TransactionStatus(data.get('status')),
                    reason=data.get('reason'),
                    meta=data.get('meta', {}),
                    balance_after=data.get('balance_after'),
                    created_at=data.get('created_at'),
                    completed_at=data.get('completed_at'),
                    dedupe_key=data.get('dedupe_key'),
                    ref_id=data.get('ref_id'),
                    price_snapshot=data.get('price_snapshot')
                ))
            
            return transactions
            
        except Exception as e:
            logger.error(f"Failed to get transactions for user {user_id}: {e}")
            return []
    
    async def _find_transaction_by_dedupe_key(self, user_id: str, dedupe_key: str) -> Optional[CreditTransaction]:
        """Find existing transaction by deduplication key."""
        try:
            query = self.firestore_service.db.collection('users').document(user_id)\
                        .collection('credits_transactions')\
                        .where('dedupe_key', '==', dedupe_key)\
                        .limit(1)
            
            docs = await asyncio.get_event_loop().run_in_executor(None, lambda: list(query.stream()))
            
            if docs:
                data = docs[0].to_dict()
                return CreditTransaction(
                    txn_id=data.get('txn_id'),
                    user_id=data.get('user_id'),
                    amount=data.get('amount'),
                    type=TransactionType(data.get('type')),
                    status=TransactionStatus(data.get('status')),
                    reason=data.get('reason'),
                    meta=data.get('meta', {}),
                    balance_after=data.get('balance_after'),
                    created_at=data.get('created_at'),
                    completed_at=data.get('completed_at'),
                    dedupe_key=data.get('dedupe_key'),
                    ref_id=data.get('ref_id'),
                    price_snapshot=data.get('price_snapshot')
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find transaction by dedupe key {dedupe_key} for user {user_id}: {e}")
            return None
    
    async def initialize_user_credits(self, user_id: str, initial_balance: int = 0, 
                                    reason: str = "account_creation") -> bool:
        """
        Initialize credits for a new user.
        
        Args:
            user_id: User ID
            initial_balance: Initial credit balance
            reason: Reason for credit initialization
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            now = datetime.now(timezone.utc)
            
            # Update user document with credits structure
            user_ref = self.firestore_service.db.collection('users').document(user_id)
            await asyncio.get_event_loop().run_in_executor(None, user_ref.update, {
                'credits.balance': initial_balance,
                'credits.last_updated': now,
                'credits.created_at': now
            })
            
            # If initial balance > 0, create a credit transaction
            if initial_balance > 0:
                await self.add_credits(
                    user_id=user_id,
                    amount=initial_balance,
                    reason=reason,
                    meta={'initialization': True}
                )
            
            logger.info(f"Initialized credits for user {user_id} with balance {initial_balance}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize credits for user {user_id}: {e}")
            return False

# Global instance
_credits_service: Optional[CreditsService] = None

def get_credits_service(firestore_service=None) -> CreditsService:
    """Get or create the global credits service instance."""
    global _credits_service
    
    if _credits_service is None and firestore_service:
        _credits_service = CreditsService(firestore_service)
    
    return _credits_service

def initialize_credits_service(firestore_service):
    """Initialize the global credits service."""
    global _credits_service
    _credits_service = CreditsService(firestore_service)
    return _credits_service