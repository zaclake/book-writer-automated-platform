# Writerbloom Credit System Documentation

## Overview

The Writerbloom Credit System is a consumption-based billing system that automatically charges users for AI model usage. Credits provide a unified currency for all AI operations including text generation, image creation, and reference file generation.

## Credit Formula

### Base Formula
```
credits = ceil((openai_cost_usd × CREDITS_MARKUP) × 100)
```

### Configuration
- **CREDITS_MARKUP**: 5.0 (default, 5× markup)
- **Credit Value**: 1 credit = $0.01 of user-facing value
- **Conversion Rate**: 100 credits per $1 of user value

### Example Calculations
```
OpenAI Cost: $0.0123
Raw Cost × Markup: $0.0123 × 5 = $0.0615
Credits: ceil($0.0615 × 100) = 7 credits

Target Novel Generation (~2M tokens):
Raw OpenAI Cost: ~$30
Credits Required: ceil($30 × 5 × 100) = 15,000 credits
User Value: $150
```

## Auto-Complete Book Generation Credit Estimation

### Overview
The auto-complete system now provides credit-based cost estimation instead of dollar amounts. This gives users clear visibility into credit consumption before starting large book generation projects.

### Estimation Components

#### Credit Calculation Factors
1. **Base Token Estimation**: 1.3 tokens per word (input + output)
2. **Quality Multipliers**: Higher quality thresholds require more AI processing
   - Quality 9.0+: 2.5× multiplier (extremely high quality)
   - Quality 8.0+: 2.0× multiplier (high quality)  
   - Quality 7.0+: 1.7× multiplier (good quality)
   - Quality 6.0+: 1.4× multiplier (standard quality)
   - Below 6.0: 1.2× multiplier (basic quality)

3. **Retry Multipliers**: Account for quality gate failures requiring regeneration
   - Quality 9.0+: 1.8× retry factor
   - Quality 8.0+: 1.5× retry factor
   - Quality 7.0+: 1.3× retry factor
   - Below 7.0: 1.1× retry factor

4. **Overhead**: 5% overhead for job setup and finalization

#### Estimation API Response
```json
{
  "success": true,
  "estimation": {
    "total_chapters": 20,
    "words_per_chapter": 4000,
    "total_words": 80000,
    "quality_threshold": 7.0,
    "estimated_total_credits": 3500,
    "credits_per_chapter": 175,
    "estimation_method": "credits_service"
  }
}
```

#### UI Display
The estimation interface shows:
- **Total Chapters**: Number of chapters to generate
- **Total Words**: Estimated total word count
- **Estimated Credits**: Total credits required (prominently displayed)
- **Quality Threshold**: Selected quality level (0-10 scale displayed as percentage)

#### Confirmation Modal
Before starting auto-completion, users see:
- **Credit Summary**: Clear breakdown of credit requirement
- **Safety Features**: Quality gates, pause/resume, chapter-by-chapter generation
- **Confirmation Button**: Shows exact credit amount (e.g., "Confirm & Start (3,500 credits)")

### Technical Implementation

#### Backend Changes
- New endpoint: `POST /auto-complete/estimate` returns credit-based estimation
- Credit calculation via `backend/auto_complete/estimate_utils.py`
- Integration with existing `PricingRegistry` for dynamic markup application
- Fallback calculations if pricing service unavailable

#### Frontend Changes
- Updated `AutoCompleteEstimate` TypeScript interface
- Credit-focused UI components (removed dollar signs, tokens, bullet details)
- Status messages use credit terminology
- Error handling for insufficient credits (402 responses)

### Example Credit Estimation
```
Book Configuration:
- 20 chapters × 4,000 words = 80,000 total words
- Quality threshold: 7.0 (good quality)
- Model: GPT-4o

Calculation:
- Base tokens per chapter: 4,000 × 1.3 = 5,200 tokens
- Quality multiplier: 1.7× = 8,840 tokens
- Retry multiplier: 1.3× = 11,492 tokens
- Cost per chapter: ~175 credits
- Total base: 175 × 20 = 3,500 credits
- With overhead: 3,500 × 1.05 = 3,675 credits
```

### Long-Running Process Guidance

#### Expected Duration
Auto-complete book generation is a **long-running process** that typically takes:
- **30-45 minutes** for a standard 20-chapter book (80,000 words)
- **Time varies** based on quality threshold, chapter count, and AI model response times
- **Real-time progress tracking** via browser interface with live chapter completion updates

#### User Experience Features
1. **Safe Navigation**: Users can safely close their browser or navigate away during generation
2. **Progress Persistence**: Job continues running on the server regardless of browser state
3. **Automatic Reconnection**: Upon returning, the interface automatically reconnects to show current progress
4. **Progress Indicators**: Live progress bar showing chapter completion, time estimates, and status messages
5. **Browser Notifications**: Toast notifications inform users they can safely leave and return later

#### Technical Implementation
- **localStorage Persistence**: Running job IDs stored locally for recovery after page refresh
- **Server-Sent Events (SSE)**: Real-time progress streaming with automatic reconnection
- **Polling Fallback**: If SSE fails, system falls back to periodic status polling
- **Background Processing**: Chapter generation runs in background tasks, not tied to user sessions

#### Recommended User Workflow
1. **Start Generation**: Click "Start Auto-Completion" and see confirmation with time estimate
2. **Monitor Initial Progress**: Watch first few chapters complete to ensure process is working
3. **Navigate Away**: Feel free to close browser, work on other tasks, or check other projects
4. **Return Later**: Come back in 30-45 minutes to review completed chapters
5. **Quality Review**: Use built-in quality gates and chapter review tools for final polishing

## Model Pricing

### Current Supported Models

#### OpenAI Models
- **GPT-4o**: $0.005/1K input, $0.015/1K output tokens
- **GPT-4o-mini**: $0.00015/1K input, $0.0006/1K output tokens  
- **DALL-E 3**: $0.04 per image (standard quality)

#### Replicate Models
- **Stable Diffusion 3**: $0.02 per image

### Pricing Configuration
Model pricing is stored in Firestore at `system/model_pricing` and can be updated without code deployment:

```json
{
  "schema_version": "1.0",
  "models": {
    "openai": {
      "gpt-4o": {
        "input_usd_per_1k": 0.005,
        "output_usd_per_1k": 0.015
      }
    }
  }
}
```

## Architecture

### Core Components

1. **PricingRegistry**: Manages model costs and markup rules with automatic caching
2. **CreditsService**: Handles all credit transactions with Firestore atomicity
3. **BillableClient**: Wraps AI SDKs to automatically deduct credits
4. **Credits API**: REST endpoints for balance, transactions, and admin operations

### Transaction Types

- **CREDIT**: Add credits to user balance
- **DEBIT**: Immediate credit deduction
- **PROVISIONAL_DEBIT**: Hold credits for long-running operations
- **VOID**: Cancel a provisional debit
- **REFUND**: Return credits to user

### Provisional Billing Workflow

For long-running operations (like chapter generation):

1. **Estimate**: Calculate expected credits needed
2. **Provisional Debit**: Hold credits without deducting
3. **Execute**: Run the AI operation
4. **Finalize**: Deduct actual credits used, release hold
5. **Void** (if failed): Release held credits

```python
# Example usage
txn_id = await credits_service.provisional_debit(user_id, estimated_credits, "chapter_generation")

try:
    result = await ai_operation()
    await credits_service.finalize_provisional_debit(user_id, txn_id, actual_credits)
except Exception:
    await credits_service.void_provisional_debit(user_id, txn_id, "operation_failed")
```

## API Endpoints

### User Endpoints

#### GET /v2/credits/balance
Get current credit balance and pending debits.

**Response:**
```json
{
  "balance": 2000,
  "pending_debits": 50,
  "available_balance": 1950,
  "last_updated": "2025-01-15T10:30:00Z"
}
```

#### GET /v2/credits/transactions
Get transaction history with pagination.

**Parameters:**
- `limit`: 1-100 (default: 25)
- `cursor`: Transaction ID for pagination

#### POST /v2/credits/estimate
Estimate credits for an operation.

**Request:**
```json
{
  "operation_type": "chat",
  "model": "gpt-4o",
  "prompt_text": "Write a chapter...",
  "max_tokens": 4000
}
```

#### POST /v2/credits/admin/beta-credits/initialize
Initialize beta credits for authenticated user (if ENABLE_BETA_CREDITS=true).

### Admin Endpoints

#### POST /admin/users/{user_id}/credits/grant
Grant credits to a user (admin only).

**Request:**
```json
{
  "amount": 1000,
  "reason": "customer_support_credit",
  "meta": {"ticket_id": "12345"}
}
```

#### GET /admin/pricing
Get current pricing information (admin only).

## Environment Configuration

### Required Variables
```bash
# Core system
ENABLE_CREDITS_SYSTEM=true
ENABLE_CREDITS_BILLING=true

# Pricing
CREDITS_MARKUP=5.0

# Beta program
ENABLE_BETA_CREDITS=true

# Database
USE_FIRESTORE=true
SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

### Firestore Schema

#### User Document Structure
```
users/{user_id}
├── credits/
│   ├── balance: number
│   ├── last_updated: timestamp
│   └── created_at: timestamp
└── credits_transactions/{txn_id}
    ├── txn_id: string
    ├── amount: number
    ├── type: "credit"|"debit"|"provisional_debit"|"void"|"refund"
    ├── status: "pending"|"completed"|"void"|"failed"
    ├── reason: string
    ├── meta: object
    ├── balance_after: number
    ├── created_at: timestamp
    ├── completed_at: timestamp
    └── dedupe_key: string (optional)
```

## Beta Credit Program

### Default Grant
- **Amount**: 2,000 credits
- **Value**: $20 user value ($4 raw OpenAI cost at 5× markup)
- **Trigger**: User calls `/v2/credits/admin/beta-credits/initialize`
- **Control**: ENABLE_BETA_CREDITS environment variable

### Usage Estimates
```
Novel chapter (3,000 words): ~100-200 credits
Reference file generation: ~50-100 credits
Cover art generation: ~200 credits
Full novel (25 chapters): ~3,000-5,000 credits
```

## Error Handling

### HTTP 402 Payment Required
Returned when user has insufficient credits:

```json
{
  "error": "INSUFFICIENT_CREDITS",
  "required": 120,
  "available": 25,
  "message": "Insufficient credits for this operation"
}
```

### Frontend Integration
The frontend should:
1. Show global "Buy Credits" modal on 402 errors
2. Disable generate buttons when credits insufficient
3. Display real-time balance in sidebar
4. Provide credit transaction history

## Troubleshooting

### Common Issues

#### Credits Not Deducting
1. Check `ENABLE_CREDITS_BILLING=true`
2. Verify Firestore connectivity
3. Check user authentication
4. Review billable client initialization

#### Rate Limiting
```bash
# Check Firestore logs
kubectl logs deployment/backend | grep "rate_limit"

# Monitor pricing registry cache
curl /v2/credits/health
```

#### Transaction Failures
```bash
# Check for failed transactions
db.collection('users/{user_id}/credits_transactions')
  .where('status', '==', 'failed')
  .get()
```

### Refund Process

#### Manual Refund (Admin)
```python
# Grant refund credits
await credits_service.add_credits(
    user_id="user123",
    amount=500,
    reason="refund_chapter_generation_failure",
    meta={
        "original_txn_id": "txn_456",
        "refund_type": "manual",
        "admin_user": "admin@example.com"
    }
)
```

#### Automatic Refund (System)
Provisional debits are automatically voided if operations fail.

### Replaying Transactions

#### Find Original Transaction
```python
txn = await credits_service.get_transaction(user_id, txn_id)
```

#### Replay Failed Operation
```python
# Void failed provisional debit
await credits_service.void_provisional_debit(user_id, txn_id, "replay_attempt")

# Start new operation
new_txn = await credits_service.provisional_debit(user_id, amount, "retry_operation")
```

## Monitoring and Analytics

### Key Metrics
- Daily credit consumption by user
- Average credits per operation type
- Conversion rate (credits → revenue)
- Failed transaction rate

### Alerts
- User balance goes negative
- Daily margin below threshold
- High transaction failure rate
- Unusual spending patterns

### Structured Logging
All credit operations emit structured logs for BigQuery analysis:

```json
{
  "event": "credit_debit",
  "user_id": "user123",
  "amount": 150,
  "operation": "chapter_generation",
  "model": "gpt-4o",
  "raw_cost_usd": 0.0312,
  "markup_applied": 5.0,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

## Future Enhancements

### Stripe Integration
- Credit purchase packages (1K, 5K, 10K)
- Subscription plans with included credits
- Auto-reload when balance low

### Advanced Features
- Team credit pools
- Usage-based pricing tiers
- Promotional credit campaigns
- Credit gifting between users

## Support

### Customer Questions

**Q: How do I check my credit balance?**
A: Visit your profile page or check the sidebar credit display.

**Q: What happens if I run out of credits?**
A: Operations will be blocked with a "Buy Credits" prompt. Beta users can contact support.

**Q: Can I get a refund for unused credits?**
A: Contact support for refund requests on a case-by-case basis.

**Q: How much do operations cost?**
A: Use the cost estimator before generating content, or check your transaction history.

### Developer Support

For technical issues:
1. Check `/v2/credits/health` endpoint
2. Review application logs
3. Verify environment configuration
4. Test with minimal API calls

Contact: [technical documentation contact]