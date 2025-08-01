import pytest
import uuid
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime, timezone

from backend.services.credits_service import (
    CreditsService, 
    CreditTransaction, 
    CreditBalance,
    TransactionType, 
    TransactionStatus,
    InsufficientCreditsError
)


@pytest.fixture
def mock_firestore_service():
    """Mock Firestore service for testing."""
    service = Mock()
    service.available = True
    service.db = Mock()
    return service


@pytest.fixture
def credits_service(mock_firestore_service):
    """Return CreditsService instance with mocked Firestore."""
    return CreditsService(mock_firestore_service)


@pytest.mark.asyncio
async def test_get_balance_returns_correct_balance(credits_service, mock_firestore_service):
    """Test that get_balance returns correct balance from Firestore."""
    user_id = "test_user_123"
    
    # Mock user document with credits data
    mock_user_doc = {
        "credits": {
            "balance": 1500,
            "last_updated": datetime.now(timezone.utc)
        }
    }
    mock_firestore_service.get_user = AsyncMock(return_value=mock_user_doc)
    
    # Mock pending debits calculation
    credits_service._calculate_pending_debits = AsyncMock(return_value=25)
    
    balance = await credits_service.get_balance(user_id)
    
    assert balance is not None
    assert balance.user_id == user_id
    assert balance.balance == 1500
    assert balance.pending_debits == 25


@pytest.mark.asyncio
async def test_get_balance_user_not_found(credits_service, mock_firestore_service):
    """Test get_balance when user doesn't exist."""
    user_id = "nonexistent_user"
    
    # Mock user not found
    mock_firestore_service.get_user = AsyncMock(return_value=None)
    
    balance = await credits_service.get_balance(user_id)
    
    assert balance is None


@pytest.mark.asyncio
async def test_add_credits_atomic_transaction(credits_service, mock_firestore_service):
    """Test that add_credits performs atomic Firestore transaction."""
    user_id = "test_user_123"
    amount = 100
    reason = "test_credit_addition"
    
    # Mock Firestore transaction behavior
    mock_transaction = Mock()
    mock_firestore_service.db.transaction.return_value = mock_transaction
    
    # Mock user document
    mock_user_ref = Mock()
    mock_user_doc = Mock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "credits": {"balance": 500}
    }
    
    mock_firestore_service.db.collection.return_value.document.return_value = mock_user_ref
    mock_user_ref.get.return_value = mock_user_doc
    
    # Mock transaction decorator behavior
    def mock_transactional(func):
        def wrapper(transaction):
            return func(transaction)
        return wrapper
    
    mock_firestore_service.db.transactional = mock_transactional
    
    # Mock transaction operations
    mock_user_ref.collection.return_value.document.return_value = Mock()
    
    result = await credits_service.add_credits(user_id, amount, reason)
    
    # Verify transaction was called to update user balance
    mock_transaction.update.assert_called()
    mock_transaction.set.assert_called()
    
    assert result is not None
    assert result.amount == amount
    assert result.type == TransactionType.CREDIT
    assert result.status == TransactionStatus.COMPLETED
    assert result.balance_after == 600  # 500 + 100


@pytest.mark.asyncio
async def test_deduct_credits_insufficient_balance_raises_error(credits_service, mock_firestore_service):
    """Test that deduct_credits raises InsufficientCreditsError when balance too low."""
    user_id = "test_user_123"
    amount = 1000  # More than available balance
    reason = "test_deduction"
    
    # Mock Firestore transaction behavior
    mock_transaction = Mock()
    mock_firestore_service.db.transaction.return_value = mock_transaction
    
    # Mock user document with insufficient balance
    mock_user_ref = Mock()
    mock_user_doc = Mock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "credits": {"balance": 100}  # Only 100 credits available
    }
    
    mock_firestore_service.db.collection.return_value.document.return_value = mock_user_ref
    mock_user_ref.get.return_value = mock_user_doc
    
    # Mock transaction decorator
    def mock_transactional(func):
        def wrapper(transaction):
            return func(transaction)
        return wrapper
    
    mock_firestore_service.db.transactional = mock_transactional
    
    # Should raise InsufficientCreditsError
    with pytest.raises(InsufficientCreditsError) as exc_info:
        await credits_service.deduct_credits(user_id, amount, reason)
    
    assert exc_info.value.required == amount
    assert exc_info.value.available == 100
    assert exc_info.value.user_id == user_id


@pytest.mark.asyncio
async def test_provisional_debit_workflow(credits_service, mock_firestore_service):
    """Test complete provisional debit workflow: create → finalize."""
    user_id = "test_user_123"
    amount = 50
    reason = "test_provisional"
    
    # Mock Firestore transaction behavior
    mock_transaction = Mock()
    mock_firestore_service.db.transaction.return_value = mock_transaction
    
    # Mock user document
    mock_user_ref = Mock()
    mock_user_doc = Mock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "credits": {"balance": 200}
    }
    
    mock_firestore_service.db.collection.return_value.document.return_value = mock_user_ref
    mock_user_ref.get.return_value = mock_user_doc
    mock_user_ref.collection.return_value.document.return_value = Mock()
    
    # Mock transaction decorator
    def mock_transactional(func):
        def wrapper(transaction):
            return func(transaction)
        return wrapper
    
    mock_firestore_service.db.transactional = mock_transactional
    
    # Step 1: Create provisional debit
    provisional_txn = await credits_service.provisional_debit(user_id, amount, reason)
    
    assert provisional_txn is not None
    assert provisional_txn.type == TransactionType.PROVISIONAL_DEBIT
    assert provisional_txn.status == TransactionStatus.PENDING
    assert provisional_txn.amount == amount
    assert provisional_txn.balance_after is None  # No balance change yet
    
    # Step 2: Mock finalize transaction
    txn_id = provisional_txn.txn_id
    
    # Mock transaction document for finalization
    mock_txn_ref = Mock()
    mock_txn_doc = Mock()
    mock_txn_doc.exists = True
    mock_txn_doc.to_dict.return_value = {
        "type": TransactionType.PROVISIONAL_DEBIT.value,
        "status": TransactionStatus.PENDING.value,
        "amount": amount
    }
    
    mock_user_ref.collection.return_value.document.return_value = mock_txn_ref
    mock_txn_ref.get.return_value = mock_txn_doc
    
    # Finalize the provisional debit
    success = await credits_service.finalize_provisional_debit(user_id, txn_id, final_amount=45)
    
    assert success is True
    
    # Verify transaction was updated to completed
    mock_transaction.update.assert_called()


@pytest.mark.asyncio
async def test_void_provisional_debit(credits_service, mock_firestore_service):
    """Test voiding a provisional debit without charging credits."""
    user_id = "test_user_123"
    txn_id = str(uuid.uuid4())
    void_reason = "operation_failed"
    
    # Mock Firestore transaction behavior
    mock_transaction = Mock()
    mock_firestore_service.db.transaction.return_value = mock_transaction
    
    # Mock transaction document
    mock_user_ref = Mock()
    mock_txn_ref = Mock()
    mock_txn_doc = Mock()
    mock_txn_doc.exists = True
    mock_txn_doc.to_dict.return_value = {
        "type": TransactionType.PROVISIONAL_DEBIT.value,
        "status": TransactionStatus.PENDING.value,
        "amount": 50
    }
    
    mock_firestore_service.db.collection.return_value.document.return_value = mock_user_ref
    mock_user_ref.collection.return_value.document.return_value = mock_txn_ref
    mock_txn_ref.get.return_value = mock_txn_doc
    
    # Mock transaction decorator
    def mock_transactional(func):
        def wrapper(transaction):
            return func(transaction)
        return wrapper
    
    mock_firestore_service.db.transactional = mock_transactional
    
    # Void the provisional debit
    success = await credits_service.void_provisional_debit(user_id, txn_id, void_reason)
    
    assert success is True
    
    # Verify transaction was updated to void status
    mock_transaction.update.assert_called()
    update_call_args = mock_transaction.update.call_args[0]
    update_data = update_call_args[1]
    
    assert update_data["status"] == TransactionStatus.VOID.value
    assert update_data["meta.void_reason"] == void_reason


@pytest.mark.asyncio
async def test_dedupe_key_prevents_duplicate_transactions(credits_service, mock_firestore_service):
    """Test that dedupe_key prevents duplicate credit transactions."""
    user_id = "test_user_123"
    amount = 100
    reason = "test_credit"
    dedupe_key = "unique_operation_123"
    
    # Mock existing transaction with same dedupe key
    existing_txn = CreditTransaction(
        txn_id="existing_txn_id",
        user_id=user_id,
        amount=amount,
        type=TransactionType.CREDIT,
        status=TransactionStatus.COMPLETED,
        reason=reason,
        meta={},
        dedupe_key=dedupe_key
    )
    
    credits_service._find_transaction_by_dedupe_key = AsyncMock(return_value=existing_txn)
    
    # Attempt to add credits with same dedupe key
    result = await credits_service.add_credits(user_id, amount, reason, dedupe_key=dedupe_key)
    
    # Should return existing transaction, not create new one
    assert result == existing_txn
    assert result.txn_id == "existing_txn_id"


@pytest.mark.asyncio
async def test_credits_service_unavailable_when_firestore_down(mock_firestore_service):
    """Test that CreditsService gracefully handles Firestore unavailability."""
    mock_firestore_service.available = False
    
    service = CreditsService(mock_firestore_service)
    
    assert service.is_available() is False
    
    # All operations should return None/empty when service unavailable
    balance = await service.get_balance("user_123")
    assert balance is None
    
    txn = await service.add_credits("user_123", 100, "test")
    assert txn is None
    
    txn = await service.deduct_credits("user_123", 50, "test")
    assert txn is None


def test_credit_amount_validation(credits_service):
    """Test that credit operations validate positive amounts."""
    user_id = "test_user_123"
    
    # Test zero amount
    with pytest.raises(ValueError, match="Credit amount must be positive"):
        credits_service.add_credits(user_id, 0, "test")
    
    # Test negative amount
    with pytest.raises(ValueError, match="Credit amount must be positive"):
        credits_service.add_credits(user_id, -100, "test")
    
    # Test debit validation
    with pytest.raises(ValueError, match="Debit amount must be positive"):
        credits_service.deduct_credits(user_id, 0, "test")