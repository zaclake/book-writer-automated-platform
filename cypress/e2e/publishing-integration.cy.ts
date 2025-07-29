describe('Publishing Integration', () => {
  beforeEach(() => {
    // Mock authentication
    cy.window().then((win) => {
      win.localStorage.setItem('auth_token', 'mock-token')
    })
    
    // Intercept API calls
    cy.intercept('GET', '/api/v2/projects', {
      fixture: 'projects-with-chapters.json'
    }).as('getProjects')
    
    cy.intercept('GET', '/api/v2/projects/*', {
      fixture: 'project-with-chapters.json'
    }).as('getProject')
  })

  it('should complete the full publishing flow', () => {
    // Visit dashboard and start publishing
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Click publish book button
    cy.get('[data-cy=publish-book-button]').click()
    
    // Project picker should open
    cy.get('[data-cy=project-picker-dialog]').should('be.visible')
    
    // Select a project with chapters
    cy.get('[data-cy=project-card]').first().click()
    cy.get('[data-cy=project-selected-badge]').should('be.visible')
    
    // Continue to publish page
    cy.get('[data-cy=continue-to-publish]').click()
    
    // Should navigate to publish page
    cy.url().should('include', '/publish')
    cy.wait('@getProject')
    
    // Fill out publishing form
    cy.get('input[name="title"]').should('have.value', 'Test Book')
    cy.get('input[name="author"]').clear().type('Test Author')
    
    // Add optional content
    cy.get('[data-cy=tab-sections]').click()
    cy.get('textarea[name="dedication"]').type('To my test readers')
    cy.get('textarea[name="acknowledgments"]').type('Thanks to the testing team')
    
    // Configure settings
    cy.get('[data-cy=tab-settings]').click()
    cy.get('input[name="formats"][value="epub"]').should('be.checked')
    cy.get('input[name="formats"][value="pdf"]').should('be.checked')
    
    // Mock the publish job start
    cy.intercept('POST', '/api/v2/publish/project/*', {
      statusCode: 200,
      body: {
        job_id: 'test-job-123',
        status: 'submitted',
        message: 'Publishing job started for 2 format(s)'
      }
    }).as('startPublishJob')
    
    // Mock job status polling
    cy.intercept('GET', '/api/v2/publish/test-job-123', {
      statusCode: 200,
      body: {
        job_id: 'test-job-123',
        status: 'running',
        progress: {
          current_step: 'Generating EPUB',
          progress_percentage: 45,
          last_update: new Date().toISOString()
        },
        created_at: new Date().toISOString()
      }
    }).as('getJobStatus')
    
    // Submit the form
    cy.get('[data-cy=publish-button]').click()
    cy.wait('@startPublishJob')
    
    // Should show progress
    cy.get('[data-cy=publishing-progress]').should('be.visible')
    cy.get('[data-cy=creative-loader]').should('be.visible')
    cy.wait('@getJobStatus')
    
    // Mock job completion
    cy.intercept('GET', '/api/v2/publish/test-job-123', {
      statusCode: 200,
      body: {
        job_id: 'test-job-123',
        status: 'completed',
        progress: {
          current_step: 'Completed',
          progress_percentage: 100,
          last_update: new Date().toISOString()
        },
        result: {
          epub_url: 'https://storage.example.com/book.epub',
          pdf_url: 'https://storage.example.com/book.pdf',
          file_sizes: {
            epub: 1024000,
            pdf: 2048000
          },
          word_count: 50000,
          page_count: 200
        },
        created_at: new Date().toISOString(),
        completed_at: new Date().toISOString()
      }
    }).as('getCompletedJobStatus')
    
    // Wait for completion
    cy.wait('@getCompletedJobStatus')
    
    // Should show success message and download links
    cy.get('[data-cy=publish-success]').should('be.visible')
    cy.get('[data-cy=download-epub]').should('be.visible')
    cy.get('[data-cy=download-pdf]').should('be.visible')
    
    // Test download links
    cy.get('[data-cy=download-epub]').should('have.attr', 'href', 'https://storage.example.com/book.epub')
    cy.get('[data-cy=download-pdf]').should('have.attr', 'href', 'https://storage.example.com/book.pdf')
    
    // Should be able to publish another version
    cy.get('[data-cy=publish-another]').should('be.visible')
  })

  it('should handle publishing errors gracefully', () => {
    cy.visit('/project/test-project/publish')
    cy.wait('@getProject')
    
    // Mock a failed publish job
    cy.intercept('POST', '/api/v2/publish/project/*', {
      statusCode: 500,
      body: {
        detail: 'Publishing service temporarily unavailable'
      }
    }).as('failedPublishJob')
    
    // Submit form with minimal data
    cy.get('[data-cy=publish-button]').click()
    cy.wait('@failedPublishJob')
    
    // Should show error message
    cy.get('[data-cy=publish-error]').should('be.visible')
    cy.get('[data-cy=publish-error]').should('contain', 'Publishing service temporarily unavailable')
    
    // Should have option to try again
    cy.get('[data-cy=try-again-button]').should('be.visible')
  })

  it('should validate required fields', () => {
    cy.visit('/project/test-project/publish')
    cy.wait('@getProject')
    
    // Clear required fields
    cy.get('input[name="title"]').clear()
    cy.get('input[name="author"]').clear()
    
    // Try to submit
    cy.get('[data-cy=publish-button]').click()
    
    // Should show validation errors
    cy.get('[data-cy=field-error]').should('have.length.at.least', 2)
    
    // Button should be disabled or form shouldn't submit
    cy.get('[data-cy=publishing-progress]').should('not.exist')
  })

  it('should handle projects without chapters', () => {
    // Mock project without chapters
    cy.intercept('GET', '/api/v2/projects', {
      body: [
        {
          id: 'empty-project',
          title: 'Empty Project',
          description: 'Project with no chapters',
          chapters: [],
          updated_at: new Date().toISOString()
        }
      ]
    }).as('getEmptyProjects')
    
    cy.visit('/dashboard')
    cy.wait('@getEmptyProjects')
    
    // Click publish book button
    cy.get('[data-cy=publish-book-button]').click()
    
    // Should show no publishable projects message
    cy.get('[data-cy=no-publishable-projects]').should('be.visible')
    cy.get('[data-cy=no-publishable-projects]').should('contain', 'No projects with chapters found')
  })

  it('should preserve form data when switching tabs', () => {
    cy.visit('/project/test-project/publish')
    cy.wait('@getProject')
    
    // Fill in book details
    cy.get('input[name="title"]').clear().type('My Custom Title')
    cy.get('input[name="author"]').clear().type('Custom Author')
    
    // Switch to sections tab and fill content
    cy.get('[data-cy=tab-sections]').click()
    cy.get('textarea[name="dedication"]').type('Custom dedication text')
    
    // Switch to engagement tab
    cy.get('[data-cy=tab-engagement]').click()
    cy.get('textarea[name="call_to_action"]').type('Please review my book!')
    
    // Switch back to details tab
    cy.get('[data-cy=tab-details]').click()
    
    // Data should be preserved
    cy.get('input[name="title"]').should('have.value', 'My Custom Title')
    cy.get('input[name="author"]').should('have.value', 'Custom Author')
    
    // Check other tabs still have data
    cy.get('[data-cy=tab-sections]').click()
    cy.get('textarea[name="dedication"]').should('have.value', 'Custom dedication text')
    
    cy.get('[data-cy=tab-engagement]').click()
    cy.get('textarea[name="call_to_action"]').should('have.value', 'Please review my book!')
  })

  it('should show project statistics correctly', () => {
    cy.visit('/project/test-project/publish')
    cy.wait('@getProject')
    
    // Should display project overview with stats
    cy.get('[data-cy=project-overview]').should('be.visible')
    cy.get('[data-cy=chapter-count]').should('contain', '5') // Based on fixture
    cy.get('[data-cy=word-count]').should('be.visible')
    cy.get('[data-cy=page-count]').should('be.visible')
    
    // Should show cover art badge if available
    cy.get('[data-cy=cover-art-badge]').should('be.visible')
  })
}) 