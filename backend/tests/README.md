# Credits System Test Suite

This directory contains comprehensive tests for the WriterBloom credits system, covering all critical business logic, security boundaries, and user experience flows.

## Test Organization

### Unit Tests

#### `test_pricing_registry.py`
Tests core mathematical and business logic for credit pricing:
- ✅ USD → Credits conversion accuracy with 5x markup
- ✅ Token-based pricing (GPT-4o: $0.005/$0.015 per 1k tokens)
- ✅ Job-based pricing (DALL-E 3: $0.04 per image)
- ✅ Unknown model handling (returns 0 cost/credits)
- ✅ 1 credit = $0.01 user value validation

#### `test_credits_service.py`
Tests transaction safety and balance management:
- ✅ Atomic Firestore transactions for balance updates
- ✅ Provisional debit workflow (create → finalize/void)
- ✅ Insufficient credits error handling
- ✅ Deduplication key enforcement
- ✅ Concurrent transaction safety
- ✅ Service availability graceful degradation

#### `test_billable_client.py`
Tests AI SDK wrappers and billing integration:
- ✅ OpenAI chat completion billing flow
- ✅ Token counting accuracy validation
- ✅ HTTP 402 error handling for insufficient credits
- ✅ Image generation billing (DALL-E 3)
- ✅ Billing disabled fallback behavior
- ✅ Zero credit calculations (no deduction)

### Integration Tests

#### `test_chapter_billing_integration.py`
Tests end-to-end billing workflows:
- ✅ Chapter generation successful billing flow
- ✅ HTTP 402 response for insufficient credits
- ✅ OpenAI API failure rollback (no credit deduction)
- ✅ Reference generation billing integration
- ✅ Cover art generation billing integration
- ✅ Credits system disabled fallback behavior

### Frontend E2E Tests

#### `cypress/e2e/credits-system-integration.cy.ts`
Tests user interface and real-time behavior:
- ✅ Credit balance display (sidebar + mobile)
- ✅ Low balance warning indicators (< 100 credits)
- ✅ Real-time balance updates after operations
- ✅ Insufficient credits modal flow
- ✅ Beta credit claiming workflow
- ✅ Transaction history pagination
- ✅ Error handling and retry behavior

## Running Tests

### Unit Tests
```bash
cd backend
python -m pytest tests/test_pricing_registry.py -v
python -m pytest tests/test_credits_service.py -v
python -m pytest tests/test_billable_client.py -v
```

### Integration Tests
```bash
cd backend
python -m pytest tests/test_chapter_billing_integration.py -v
```

### Cypress E2E Tests
```bash
npm run cypress:open
# or headless:
npm run cypress:run --spec "cypress/e2e/credits-system-integration.cy.ts"
```

## Test Environment Setup

### Required Environment Variables
```bash
# Enable credits system for testing
ENABLE_CREDITS_SYSTEM=true
ENABLE_CREDITS_BILLING=true
ENABLE_BETA_CREDITS=true
CREDITS_MARKUP=5.0

# Mock service configurations
OPENAI_API_KEY=test_key_mock
REPLICATE_API_TOKEN=test_token_mock
```

### Mock Data Initialization
```bash
# Initialize test pricing data
python backend/scripts/init_pricing_data.py

# Deploy test Firestore rules
./scripts/deploy-firestore.sh
```

## Test Coverage Goals

### Critical Paths (100% Coverage Required)
- [ ] Credit calculation math (USD → credits)
- [ ] Transaction atomicity (balance updates)
- [ ] Insufficient credits error handling
- [ ] Security boundaries (user isolation)

### Business Logic (95% Coverage Required)
- [ ] Provisional debit workflow
- [ ] Billing integration with AI services
- [ ] Error recovery and rollback
- [ ] Feature flag behavior

### User Experience (90% Coverage Required)
- [ ] Real-time UI updates
- [ ] Modal flows and error messages
- [ ] Beta credit onboarding
- [ ] Transaction history display

## Security Test Checklist

### Access Control
- [ ] Users can only read their own credit balance
- [ ] Users cannot write to credits collections directly
- [ ] Admin endpoints require proper authentication
- [ ] Service account-only credit mutations

### Data Integrity
- [ ] Concurrent operations maintain consistency
- [ ] Transaction deduplication prevents double-charging
- [ ] Provisional debits automatically void on timeout
- [ ] Balance calculations match transaction history

### Business Rules
- [ ] No overdrafts allowed (hard stop at 0 credits)
- [ ] 5x markup consistently applied across all models
- [ ] Credit costs accurately reflect OpenAI usage
- [ ] Beta credits limited to eligible users only

## Performance Benchmarks

### Response Time Targets
- Credit balance query: < 100ms
- Credit deduction: < 200ms
- Transaction history: < 300ms
- Balance UI update: < 50ms

### Load Testing Scenarios
- 100 concurrent chapter generations
- 1000 balance queries per second
- 50 simultaneous provisional debits per user
- Transaction history with 10,000+ records

## Monitoring and Alerts

### Key Metrics to Track
- Credit calculation accuracy vs. actual OpenAI costs
- Transaction failure rates
- Provisional debit void rates
- User balance distribution

### Alert Conditions
- Credit calculation errors > 0.1%
- Transaction failures > 1%
- Balance discrepancies detected
- Negative balances (should never happen)

## Known Issues and Limitations

### Current Test Limitations
- Firestore emulator not used (relies on mocks)
- Real OpenAI API calls not tested in CI
- WebSocket real-time updates mocked in Cypress
- Performance tests require manual execution

### Future Test Enhancements
- Integration with Firestore Test Suite
- Contract testing with OpenAI API schemas
- Load testing automation in CI
- Advanced error injection scenarios

## Contributing to Tests

### Adding New Tests
1. Follow existing naming conventions
2. Include both positive and negative test cases
3. Mock external dependencies consistently
4. Document test purpose and expected behavior

### Test Data Management
- Use deterministic test data (no random values)
- Clean up test data after each test
- Isolate tests from each other
- Use descriptive test user/project IDs

### Debugging Failed Tests
- Check environment variable configuration
- Verify mock service responses
- Review test isolation and cleanup
- Check Firestore security rules in test mode