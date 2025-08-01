import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException

from backend.services.billable_client import (
    BillableOpenAIClient,
    BillableResponse,
    InsufficientCreditsError,
    estimate_credits_for_chat,
    estimate_credits_for_image
)
from backend.services.credits_service import CreditTransaction, TransactionType, TransactionStatus
from backend.services.pricing_registry import CreditCalculation


@pytest.fixture
def mock_pricing_registry():
    """Mock pricing registry for testing."""
    registry = Mock()
    registry.is_available.return_value = True
    return registry


@pytest.fixture
def mock_credits_service():
    """Mock credits service for testing."""
    service = Mock()
    service.is_available.return_value = True
    return service


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for chat completion."""
    response = Mock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150
    response.choices = [Mock()]
    response.choices[0].message.content = "Test response"
    return response


@pytest.fixture
def mock_openai_image_response():
    """Mock OpenAI API response for image generation."""
    response = Mock()
    response.data = [Mock()]
    response.data[0].url = "https://example.com/image.png"
    return response


@pytest.mark.asyncio
async def test_chat_completion_billing_flow(mock_pricing_registry, mock_credits_service, mock_openai_response):
    """Test complete chat completion billing flow."""
    user_id = "test_user_123"
    
    # Mock credit calculation
    calc = CreditCalculation(
        credits=10,
        raw_cost_usd=0.002,
        markup_applied=5.0,
        calculation_details={"test": "data"}
    )
    mock_pricing_registry.calculate_credits.return_value = calc
    
    # Mock successful credit deduction
    mock_transaction = CreditTransaction(
        txn_id="txn_123",
        user_id=user_id,
        amount=10,
        type=TransactionType.DEBIT,
        status=TransactionStatus.COMPLETED,
        reason="openai_chat_completion",
        meta={}
    )
    mock_credits_service.deduct_credits = AsyncMock(return_value=mock_transaction)
    
    # Create billable client with mocked dependencies
    with patch('backend.services.billable_client.OpenAI') as mock_openai_class:
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai_instance
        
        client = BillableOpenAIClient(
            user_id=user_id,
            api_key="test_key",
            pricing_registry=mock_pricing_registry,
            credits_service=mock_credits_service,
            enable_billing=True
        )
        
        # Make chat completion call
        result = await client.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}]
        )
        
        # Verify billing was called correctly
        mock_pricing_registry.calculate_credits.assert_called_once_with(
            'openai', 'gpt-4o', 
            {
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'total_tokens': 150
            }
        )
        
        mock_credits_service.deduct_credits.assert_called_once()
        deduct_call = mock_credits_service.deduct_credits.call_args
        assert deduct_call[1]['user_id'] == user_id
        assert deduct_call[1]['amount'] == 10
        assert deduct_call[1]['reason'] == "openai_chat_completion"
        
        # Verify response structure
        assert isinstance(result, BillableResponse)
        assert result.response == mock_openai_response
        assert result.credits_charged == 10
        assert result.raw_cost_usd == 0.002
        assert result.transaction_id == "txn_123"
        assert result.provider == "openai"
        assert result.model == "gpt-4o"


@pytest.mark.asyncio
async def test_insufficient_credits_raises_http_402(mock_pricing_registry, mock_credits_service):
    """Test that insufficient credits raises HTTPException with 402 status."""
    user_id = "test_user_123"
    
    # Mock credit calculation
    calc = CreditCalculation(
        credits=100,
        raw_cost_usd=0.02,
        markup_applied=5.0,
        calculation_details={}
    )
    mock_pricing_registry.calculate_credits.return_value = calc
    
    # Mock insufficient credits error
    mock_credits_service.deduct_credits = AsyncMock(
        side_effect=InsufficientCreditsError(required=100, available=50, user_id=user_id)
    )
    
    with patch('backend.services.billable_client.OpenAI') as mock_openai_class:
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = Mock()
        mock_openai_class.return_value = mock_openai_instance
        
        client = BillableOpenAIClient(
            user_id=user_id,
            api_key="test_key",
            pricing_registry=mock_pricing_registry,
            credits_service=mock_credits_service,
            enable_billing=True
        )
        
        # Should raise HTTPException with 402 status
        with pytest.raises(HTTPException) as exc_info:
            await client.chat_completions_create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Test"}]
            )
        
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["error"] == "INSUFFICIENT_CREDITS"
        assert exc_info.value.detail["user_id"] == user_id


@pytest.mark.asyncio
async def test_image_generation_billing(mock_pricing_registry, mock_credits_service, mock_openai_image_response):
    """Test image generation billing with job-based pricing."""
    user_id = "test_user_123"
    
    # Mock credit calculation for job-based pricing
    calc = CreditCalculation(
        credits=20,  # DALL-E 3 typically costs more
        raw_cost_usd=0.04,
        markup_applied=5.0,
        calculation_details={"job_based": True}
    )
    mock_pricing_registry.calculate_credits.return_value = calc
    
    # Mock successful credit deduction
    mock_transaction = CreditTransaction(
        txn_id="img_txn_123",
        user_id=user_id,
        amount=20,
        type=TransactionType.DEBIT,
        status=TransactionStatus.COMPLETED,
        reason="openai_image_generation",
        meta={}
    )
    mock_credits_service.deduct_credits = AsyncMock(return_value=mock_transaction)
    
    with patch('backend.services.billable_client.OpenAI') as mock_openai_class:
        mock_openai_instance = Mock()
        mock_openai_instance.images.generate.return_value = mock_openai_image_response
        mock_openai_class.return_value = mock_openai_instance
        
        client = BillableOpenAIClient(
            user_id=user_id,
            api_key="test_key",
            pricing_registry=mock_pricing_registry,
            credits_service=mock_credits_service,
            enable_billing=True
        )
        
        # Make image generation call
        result = await client.images_generate(
            model="dall-e-3",
            prompt="A test image",
            n=1,
            size="1024x1024"
        )
        
        # Verify billing was called correctly
        mock_pricing_registry.calculate_credits.assert_called_once_with(
            'openai', 'dall-e-3',
            {
                'job_count': 1,
                'model': 'dall-e-3',
                'size': '1024x1024',
                'quality': 'standard'
            }
        )
        
        # Verify response
        assert isinstance(result, BillableResponse)
        assert result.credits_charged == 20
        assert result.provider == "openai"
        assert result.model == "dall-e-3"


@pytest.mark.asyncio
async def test_billing_disabled_returns_zero_credits(mock_pricing_registry, mock_credits_service, mock_openai_response):
    """Test that billing disabled returns zero credits charged."""
    user_id = "test_user_123"
    
    with patch('backend.services.billable_client.OpenAI') as mock_openai_class:
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai_instance
        
        client = BillableOpenAIClient(
            user_id=user_id,
            api_key="test_key",
            pricing_registry=mock_pricing_registry,
            credits_service=mock_credits_service,
            enable_billing=False  # Billing disabled
        )
        
        result = await client.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}]
        )
        
        # Should not call pricing or credits services
        mock_pricing_registry.calculate_credits.assert_not_called()
        mock_credits_service.deduct_credits.assert_not_called()
        
        # Should return zero credits charged
        assert result.credits_charged == 0
        assert result.transaction_id is None


@pytest.mark.asyncio
async def test_token_counting_accuracy():
    """Test token counting estimation accuracy."""
    user_id = "test_user_123"
    model = "gpt-4o"
    prompt_text = "This is a test prompt with several words to estimate token count"
    max_tokens = 100
    
    # Mock pricing registry
    mock_registry = Mock()
    mock_registry.estimate_credits.return_value = CreditCalculation(
        credits=5,
        raw_cost_usd=0.001,
        markup_applied=5.0,
        calculation_details={}
    )
    
    with patch('backend.services.billable_client.get_pricing_registry', return_value=mock_registry):
        result = await estimate_credits_for_chat(user_id, model, prompt_text, max_tokens)
        
        # Verify token estimation was called
        mock_registry.estimate_credits.assert_called_once()
        call_args = mock_registry.estimate_credits.call_args
        
        assert call_args[0][0] == 'openai'  # provider
        assert call_args[0][1] == model
        
        # Check estimated usage structure
        estimated_usage = call_args[0][2]
        assert 'prompt_tokens' in estimated_usage
        assert 'completion_tokens' in estimated_usage
        assert 'total_tokens' in estimated_usage
        assert estimated_usage['completion_tokens'] == max_tokens
        
        # Verify result structure
        assert result['estimated_credits'] == 5
        assert 'estimated_cost_usd' in result
        assert 'markup_applied' in result


@pytest.mark.asyncio
async def test_image_estimation():
    """Test image generation credit estimation."""
    user_id = "test_user_123"
    model = "dall-e-3"
    count = 2
    
    # Mock pricing registry
    mock_registry = Mock()
    mock_registry.estimate_credits.return_value = CreditCalculation(
        credits=40,  # 2 images × 20 credits each
        raw_cost_usd=0.08,
        markup_applied=5.0,
        calculation_details={}
    )
    
    with patch('backend.services.billable_client.get_pricing_registry', return_value=mock_registry):
        result = await estimate_credits_for_image(user_id, model, count)
        
        # Verify estimation was called correctly
        mock_registry.estimate_credits.assert_called_once()
        call_args = mock_registry.estimate_credits.call_args
        
        assert call_args[0][0] == 'openai'
        assert call_args[0][1] == model
        
        estimated_usage = call_args[0][2]
        assert estimated_usage['job_count'] == count
        assert estimated_usage['model'] == model
        
        # Verify result
        assert result['estimated_credits'] == 40


def test_billable_client_initialization_requires_api_key():
    """Test that BillableOpenAIClient requires API key."""
    with pytest.raises(ValueError, match="OpenAI API key not found"):
        BillableOpenAIClient(
            user_id="test_user",
            api_key=None,  # No API key provided
            enable_billing=False
        )


@pytest.mark.asyncio
async def test_zero_credits_calculated_does_not_deduct():
    """Test that zero credit calculations don't trigger deduction."""
    user_id = "test_user_123"
    
    # Mock zero credit calculation
    calc = CreditCalculation(
        credits=0,
        raw_cost_usd=0.0,
        markup_applied=5.0,
        calculation_details={}
    )
    mock_pricing_registry = Mock()
    mock_pricing_registry.is_available.return_value = True
    mock_pricing_registry.calculate_credits.return_value = calc
    
    mock_credits_service = Mock()
    mock_credits_service.is_available.return_value = True
    
    with patch('backend.services.billable_client.OpenAI') as mock_openai_class:
        mock_openai_instance = Mock()
        mock_openai_response = Mock()
        mock_openai_response.usage.prompt_tokens = 0
        mock_openai_response.usage.completion_tokens = 0
        mock_openai_response.usage.total_tokens = 0
        mock_openai_instance.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_openai_instance
        
        client = BillableOpenAIClient(
            user_id=user_id,
            api_key="test_key",
            pricing_registry=mock_pricing_registry,
            credits_service=mock_credits_service,
            enable_billing=True
        )
        
        result = await client.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": ""}]
        )
        
        # Should not deduct credits when calculation is zero
        mock_credits_service.deduct_credits.assert_not_called()
        assert result.credits_charged == 0