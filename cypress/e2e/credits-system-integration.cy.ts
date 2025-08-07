describe('Credits System Integration', () => {
  let testUserId: string;
  let testProjectId: string;

  beforeEach(() => {
    // Setup test user and project
    testUserId = 'cypress_test_user_' + Date.now();
    testProjectId = 'cypress_test_project_' + Date.now();
    
    // Mock authentication
    cy.window().then((win) => {
      win.localStorage.setItem('auth_token', `mock_token_${testUserId}`);
    });
    
    // Visit dashboard
    cy.visit('/dashboard');
  });

  describe('Credit Balance Display', () => {
    it('should display current credit balance in sidebar', () => {
      // Mock API response for user balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 1500,
          pending_debits: 25,
          last_updated: new Date().toISOString()
        }
      }).as('getBalance');

      // Verify balance appears in sidebar
      cy.get('[data-testid="credit-balance-sidebar"]').should('be.visible');
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '1,500');
      cy.get('[data-testid="credit-balance-pending"]').should('contain', '25 pending');
    });

    it('should display credit balance in mobile top nav', () => {
      // Mock mobile viewport
      cy.viewport('iphone-x');
      
      // Mock API response
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 750,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getBalance');

      // Verify mobile balance display
      cy.get('[data-testid="credit-balance-mobile"]').should('be.visible');
      cy.get('[data-testid="credit-balance-mobile"]').should('contain', '750');
    });

    it('should show low balance warning when credits < 100', () => {
      // Mock low balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 25,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getLowBalance');

      // Should show warning indicator
      cy.get('[data-testid="low-balance-warning"]').should('be.visible');
      cy.get('[data-testid="low-balance-warning"]').should('have.class', 'text-yellow-500');
    });
  });

  describe('Chapter Generation Billing Flow', () => {
    beforeEach(() => {
      // Navigate to chapter generation
      cy.visit(`/project/${testProjectId}/chapters`);
    });

    it('should deduct credits and update balance after chapter generation', () => {
      // Mock initial balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 500,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getInitialBalance');

      // Mock successful chapter generation with billing
      cy.intercept('POST', `/v2/chapters/${testProjectId}/generate`, {
        statusCode: 200,
        body: {
          content: 'Generated chapter content...',
          word_count: 1200,
          credits_charged: 25,
          transaction_id: 'txn_cypress_123',
          chapter_number: 1
        }
      }).as('generateChapter');

      // Mock updated balance after generation
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 475, // 500 - 25 = 475
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getUpdatedBalance');

      // Verify initial balance
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '500');

      // Generate chapter
      cy.get('[data-testid="generate-chapter-btn"]').click();
      cy.get('[data-testid="chapter-context-input"]').type('Test chapter context');
      cy.get('[data-testid="confirm-generate-btn"]').click();

      // Wait for generation to complete
      cy.wait('@generateChapter');

      // Verify balance updated in real-time
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '475');

      // Verify success message includes billing info
      cy.get('[data-testid="generation-success-message"]')
        .should('contain', '25 credits charged');
    });

    it('should show insufficient credits modal when balance too low', () => {
      // Mock low balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 10,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getLowBalance');

      // Mock 402 Payment Required error
      cy.intercept('POST', `/v2/chapters/${testProjectId}/generate`, {
        statusCode: 402,
        body: {
          detail: {
            error: 'INSUFFICIENT_CREDITS',
            message: 'Insufficient credits for this operation',
            required: 25,
            available: 10,
            user_id: testUserId
          }
        }
      }).as('insufficientCredits');

      // Attempt chapter generation
      cy.get('[data-testid="generate-chapter-btn"]').click();
      cy.get('[data-testid="chapter-context-input"]').type('Test chapter context');
      cy.get('[data-testid="confirm-generate-btn"]').click();

      // Wait for error response
      cy.wait('@insufficientCredits');

      // Verify "Buy Credits" modal appears
      cy.get('[data-testid="buy-credits-modal"]').should('be.visible');
      cy.get('[data-testid="buy-credits-modal"]')
        .should('contain', 'Insufficient Credits');
      cy.get('[data-testid="credits-required"]').should('contain', '25');
      cy.get('[data-testid="credits-available"]').should('contain', '10');
    });

    it('should handle network errors gracefully without charging credits', () => {
      // Mock network error during generation
      cy.intercept('POST', `/v2/chapters/${testProjectId}/generate`, {
        statusCode: 500,
        body: { error: 'OpenAI API timeout' }
      }).as('networkError');

      // Mock balance remains unchanged
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 500,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getUnchangedBalance');

      // Attempt chapter generation
      cy.get('[data-testid="generate-chapter-btn"]').click();
      cy.get('[data-testid="chapter-context-input"]').type('Test chapter context');
      cy.get('[data-testid="confirm-generate-btn"]').click();

      // Wait for error
      cy.wait('@networkError');

      // Verify error message shown
      cy.get('[data-testid="error-message"]')
        .should('be.visible')
        .should('contain', 'Generation failed');

      // Verify balance unchanged (no credits charged on failure)
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '500');
    });
  });

  describe('Buy Credits Modal', () => {
    it('should allow claiming beta credits for new users', () => {
      // Mock beta credits eligibility
      cy.intercept('POST', '/api/v2/credits/admin/beta-credits/initialize', {
        statusCode: 200,
        body: {
          eligible: true,
          amount: 2000,
          reason: 'new_user_beta'
        }
      }).as('getBetaEligibility');

      // Mock successful beta credit claim
      cy.intercept('POST', '/api/v2/credits/admin/beta-credits/initialize', {
        statusCode: 200,
        body: {
          success: true,
          credits_granted: 2000,
          new_balance: 2000,
          transaction_id: 'beta_claim_123'
        }
      }).as('claimBetaCredits');

      // Trigger insufficient credits modal
      cy.get('[data-testid="credit-balance-sidebar"]').click();
      cy.get('[data-testid="buy-credits-btn"]').click();

      // Verify modal appears with beta option
      cy.get('[data-testid="buy-credits-modal"]').should('be.visible');
      cy.get('[data-testid="claim-beta-credits-btn"]').should('be.visible');
      cy.get('[data-testid="beta-credits-amount"]').should('contain', '2,000');

      // Claim beta credits
      cy.get('[data-testid="claim-beta-credits-btn"]').click();

      // Wait for claim to process
      cy.wait('@claimBetaCredits');

      // Verify success and modal closes
      cy.get('[data-testid="beta-claim-success"]')
        .should('be.visible')
        .should('contain', '2,000 credits added');
      
      cy.get('[data-testid="buy-credits-modal"]').should('not.exist');

      // Verify balance updated
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '2,000');
    });

    it('should show Stripe payment options when beta credits unavailable', () => {
      // Mock no beta eligibility
      cy.intercept('POST', '/api/v2/credits/admin/beta-credits/initialize', {
        statusCode: 200,
        body: {
          eligible: false,
          reason: 'already_claimed'
        }
      }).as('getNoBetaEligibility');

      // Open buy credits modal
      cy.get('[data-testid="credit-balance-sidebar"]').click();
      cy.get('[data-testid="buy-credits-btn"]').click();

      // Verify payment options shown
      cy.get('[data-testid="buy-credits-modal"]').should('be.visible');
      cy.get('[data-testid="payment-options"]').should('be.visible');
      cy.get('[data-testid="credits-package-1000"]').should('contain', '1,000 credits');
      cy.get('[data-testid="credits-package-5000"]').should('contain', '5,000 credits');
      cy.get('[data-testid="credits-package-10000"]').should('contain', '10,000 credits');

      // Verify beta option not shown
      cy.get('[data-testid="claim-beta-credits-btn"]').should('not.exist');
    });
  });

  describe('Credits Page Transaction History', () => {
    beforeEach(() => {
      cy.visit('/profile');
      cy.get('[data-testid="credits-tab"]').click();
    });

    it('should display transaction history with pagination', () => {
      // Mock transaction history
      const mockTransactions = [
        {
          txn_id: 'txn_1',
          amount: 25,
          type: 'debit',
          status: 'completed',
          reason: 'openai_chat_completion',
          created_at: new Date().toISOString(),
          balance_after: 475,
          meta: {
            operation: 'chapter_generation',
            model: 'gpt-4o'
          }
        },
        {
          txn_id: 'txn_2',
          amount: 2000,
          type: 'credit',
          status: 'completed',
          reason: 'beta_credits_claim',
          created_at: new Date(Date.now() - 86400000).toISOString(),
          balance_after: 500,
          meta: {
            initialization: true
          }
        }
      ];

      cy.intercept('GET', '/api/v2/credits/transactions*', {
        statusCode: 200,
        body: {
          transactions: mockTransactions,
          has_more: false,
          total_count: 2
        }
      }).as('getTransactions');

      // Verify transaction table
      cy.get('[data-testid="transaction-history-table"]').should('be.visible');
      cy.get('[data-testid="transaction-row"]').should('have.length', 2);

      // Verify transaction details
      cy.get('[data-testid="transaction-row"]').first()
        .should('contain', '-25 credits')
        .should('contain', 'Chapter Generation')
        .should('contain', 'Completed');

      cy.get('[data-testid="transaction-row"]').last()
        .should('contain', '+2,000 credits')
        .should('contain', 'Beta Credits')
        .should('contain', 'Completed');
    });

    it('should load more transactions on pagination', () => {
      // Mock initial page
      cy.intercept('GET', '/api/v2/credits/transactions?limit=25', {
        statusCode: 200,
        body: {
          transactions: Array(25).fill(null).map((_, i) => ({
            txn_id: `txn_${i}`,
            amount: 10,
            type: 'debit',
            status: 'completed',
            reason: 'test_transaction',
            created_at: new Date().toISOString(),
            balance_after: 500 - (i * 10)
          })),
          has_more: true,
          total_count: 50
        }
      }).as('getFirstPage');

      // Mock second page
      cy.intercept('GET', '/api/v2/credits/transactions?limit=25&start_after=*', {
        statusCode: 200,
        body: {
          transactions: Array(25).fill(null).map((_, i) => ({
            txn_id: `txn_${i + 25}`,
            amount: 10,
            type: 'debit',
            status: 'completed',
            reason: 'test_transaction',
            created_at: new Date().toISOString(),
            balance_after: 250 - (i * 10)
          })),
          has_more: false,
          total_count: 50
        }
      }).as('getSecondPage');

      // Verify initial load
      cy.get('[data-testid="transaction-row"]').should('have.length', 25);

      // Load more transactions
      cy.get('[data-testid="load-more-btn"]').click();
      cy.wait('@getSecondPage');

      // Verify additional transactions loaded
      cy.get('[data-testid="transaction-row"]').should('have.length', 50);
      cy.get('[data-testid="load-more-btn"]').should('not.exist');
    });
  });

  describe('Real-time Balance Updates', () => {
    it('should update balance immediately after any credit-consuming operation', () => {
      // Setup WebSocket mock for real-time updates
      cy.window().then((win) => {
        // Mock WebSocket connection
        const mockWS = {
          send: cy.stub(),
          close: cy.stub(),
          readyState: 1 // OPEN
        };
        
        win.WebSocket = cy.stub().returns(mockWS);
      });

      // Mock initial balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 1000,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getInitialBalance');

      // Navigate to reference generation
      cy.visit(`/project/${testProjectId}/book-bible`);
      
      // Verify initial balance
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '1,000');

      // Mock reference generation with credit deduction
      cy.intercept('POST', '/references/characters', {
        statusCode: 200,
        body: {
          characters: [{ name: 'Test Character', description: 'Test description' }],
          credits_charged: 15,
          transaction_id: 'ref_txn_123'
        }
      }).as('generateCharacters');

      // Mock updated balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 985, // 1000 - 15
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getUpdatedBalance');

      // Generate characters
      cy.get('[data-testid="generate-characters-btn"]').click();
      cy.wait('@generateCharacters');

      // Verify balance updated immediately
      cy.get('[data-testid="credit-balance-amount"]').should('contain', '985');
    });
  });

  describe('Auto-Complete Credit Estimation', () => {
    beforeEach(() => {
      // Navigate to auto-complete page
      cy.visit(`/project/${testProjectId}/auto-complete`);
    });

    it('should display credit-based estimation instead of dollar costs', () => {
      // Mock auto-complete estimation response
      cy.intercept('POST', '/api/auto-complete/estimate', {
        statusCode: 200,
        body: {
          success: true,
          estimation: {
            total_chapters: 20,
            words_per_chapter: 4000,
            total_words: 80000,
            quality_threshold: 7.0,
            estimated_total_credits: 3500,
            credits_per_chapter: 175,
            estimation_method: 'credits_service'
          }
        }
      }).as('getEstimation');

      // Click estimate button
      cy.get('[data-testid="estimate-credits-btn"]', { timeout: 10000 })
        .should('be.visible')
        .click();

      // Wait for estimation
      cy.wait('@getEstimation');

      // Verify credit-based UI elements
      cy.get('[data-testid="estimation-display"]').should('be.visible');
      cy.get('[data-testid="estimation-total-credits"]')
        .should('contain', '3,500');
      cy.get('[data-testid="estimation-total-chapters"]')
        .should('contain', '20');
      cy.get('[data-testid="estimation-total-words"]')
        .should('contain', '80,000');
      cy.get('[data-testid="estimation-quality-threshold"]')
        .should('contain', '7%');

      // Verify no dollar signs or token references
      cy.get('[data-testid="estimation-display"]')
        .should('not.contain', '$')
        .should('not.contain', 'tokens')
        .should('not.contain', 'cost');

      // Verify status message uses credits
      cy.get('[data-testid="status-message"]')
        .should('contain', 'credits')
        .should('contain', '3,500')
        .should('not.contain', '$');
    });

    it('should show credit-based confirmation modal before starting', () => {
      // First get estimation
      cy.intercept('POST', '/api/auto-complete/estimate', {
        statusCode: 200,
        body: {
          success: true,
          estimation: {
            total_chapters: 15,
            words_per_chapter: 3000,
            total_words: 45000,
            quality_threshold: 8.0,
            estimated_total_credits: 2800,
            credits_per_chapter: 187,
            estimation_method: 'credits_service'
          }
        }
      }).as('getEstimation');

      // Get estimation
      cy.get('[data-testid="estimate-credits-btn"]').click();
      cy.wait('@getEstimation');

      // Click start auto-completion
      cy.get('[data-testid="start-auto-completion-btn"]').click();

      // Verify confirmation modal uses credits
      cy.get('[data-testid="confirm-modal"]').should('be.visible');
      cy.get('[data-testid="confirm-modal-title"]')
        .should('contain', 'Confirm Auto-Completion');
      
      // Verify credit summary
      cy.get('[data-testid="credit-summary"]')
        .should('contain', 'AI Generation Credits')
        .should('contain', '2,800')
        .should('not.contain', '$')
        .should('not.contain', 'cost');

      // Verify credit breakdown
      cy.get('[data-testid="credit-breakdown"]')
        .should('contain', 'Credit Breakdown')
        .should('contain', '187')  // credits per chapter
        .should('not.contain', 'tokens');

      // Verify button shows credits
      cy.get('[data-testid="confirm-start-btn"]')
        .should('contain', '2,800 credits')
        .should('not.contain', '$');
    });

    it('should handle insufficient credits error properly', () => {
      // Mock estimation with high credit requirement
      cy.intercept('POST', '/api/auto-complete/estimate', {
        statusCode: 200,
        body: {
          success: true,
          estimation: {
            total_chapters: 30,
            words_per_chapter: 5000,
            total_words: 150000,
            quality_threshold: 9.0,
            estimated_total_credits: 8500,
            credits_per_chapter: 283,
            estimation_method: 'credits_service'
          }
        }
      }).as('getHighEstimation');

      // Mock user with low balance
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 200,
        body: {
          balance: 1000,
          pending_debits: 0,
          last_updated: new Date().toISOString()
        }
      }).as('getLowBalance');

      // Mock insufficient credits response
      cy.intercept('POST', '/api/auto-complete/start', {
        statusCode: 402,
        body: {
          detail: {
            error: 'INSUFFICIENT_CREDITS',
            message: 'Insufficient credits for this operation',
            estimated_credits: 8500,
            remaining_credits: 1000
          }
        }
      }).as('insufficientCreditsStart');

      // Get estimation
      cy.get('[data-testid="estimate-credits-btn"]').click();
      cy.wait('@getHighEstimation');

      // Try to start auto-completion
      cy.get('[data-testid="start-auto-completion-btn"]').click();
      cy.get('[data-testid="confirm-input"]').type('CONFIRM');
      cy.get('[data-testid="confirm-start-btn"]').click();
      cy.wait('@insufficientCreditsStart');

      // Verify error message uses credits terminology
      cy.get('[data-testid="error-message"]')
        .should('contain', 'Insufficient credits')
        .should('contain', '8,500')
        .should('contain', '1,000')
        .should('not.contain', '$');
    });
  });

  describe('Error Handling and Recovery', () => {
    it('should handle credits service downtime gracefully', () => {
      // Mock credits service unavailable
      cy.intercept('GET', '/api/v2/credits/balance', {
        statusCode: 503,
        body: { error: 'Credits service temporarily unavailable' }
      }).as('getBalanceError');

      // Visit dashboard
      cy.visit('/dashboard');

      // Verify graceful fallback
      cy.get('[data-testid="credit-balance-error"]')
        .should('be.visible')
        .should('contain', 'Balance unavailable');

      // Verify app still functional
      cy.get('[data-testid="dashboard-content"]').should('be.visible');
    });

    it('should retry failed balance updates', () => {
      let callCount = 0;

      // Mock first call fails, second succeeds
      cy.intercept('GET', '/api/v2/credits/balance', (req) => {
        callCount++;
        if (callCount === 1) {
          req.reply({
            statusCode: 500,
            body: { error: 'Temporary server error' }
          });
        } else {
          req.reply({
            statusCode: 200,
            body: {
              balance: 750,
              pending_debits: 0,
              last_updated: new Date().toISOString()
            }
          });
        }
      }).as('getBalanceWithRetry');

      cy.visit('/dashboard');

      // Should eventually show balance after retry
      cy.get('[data-testid="credit-balance-amount"]', { timeout: 10000 })
        .should('contain', '750');
    });
  });
});