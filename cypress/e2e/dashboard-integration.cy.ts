describe('Dashboard Integration', () => {
  beforeEach(() => {
    // Mock authentication
    cy.window().then((win) => {
      win.localStorage.setItem('clerk-session', 'mock-session')
    })
  })

  it('should display dashboard header correctly', () => {
    cy.visit('/dashboard')
    
    // Check header content (updated for new branding)
    cy.contains('WriterBloom').should('be.visible')
    cy.contains('Welcome back to your creative space').should('be.visible')
  })

  it('should show empty state when no projects exist', () => {
    // Mock empty projects response
    cy.intercept('GET', '/api/v2/projects', { body: { projects: [] } }).as('getProjects')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Check empty state content (updated for new branding)
    cy.contains('Ready to bloom? Start your first writing journey!').should('be.visible')
    cy.contains('Your story is waiting to bloom').should('be.visible')
    cy.contains('Begin a new journey').should('be.visible')
  })

  it('should display projects and chapter count when projects exist', () => {
    // Mock projects response with chapters
    const mockProjects = [
      {
        id: 'project-1',
        metadata: {
          title: 'Test Novel',
          owner_id: 'user-1',
          status: 'active'
        },
        settings: {
          genre: 'Fantasy',
          target_chapters: 25
        },
        progress: {
          chapters_completed: 3
        }
      }
    ]

    const mockChapters = [
      { chapter: 1, word_count: 3500, created_at: '2024-01-01' },
      { chapter: 2, word_count: 3800, created_at: '2024-01-02' },
      { chapter: 3, word_count: 4000, created_at: '2024-01-03' }
    ]

    cy.intercept('GET', '/api/v2/projects', { body: { projects: mockProjects } }).as('getProjects')
    cy.intercept('GET', '/api/chapters?project_id=project-1', { body: { chapters: mockChapters } }).as('getChapters')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    cy.wait('@getChapters')
    
    // Check project is displayed
    cy.contains('Test Novel').should('be.visible')
    cy.contains('Fantasy').should('be.visible')
    cy.contains('3 chapters written').should('be.visible')
    
    // Check chapter preview section
    cy.contains('Recent Chapters').should('be.visible')
    cy.contains('Chapter 1').should('be.visible')
    cy.contains('3,500 words').should('be.visible')
  })

  it('should open project creation modal', () => {
    cy.intercept('GET', '/api/v2/projects', { body: { projects: [] } }).as('getProjects')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Click create project button
    cy.contains('Create Your First Project').click()
    
    // Check modal opens
    cy.contains('Create New Project').should('be.visible')
    cy.contains('Upload Book Bible').should('be.visible')
    cy.contains('Start from Scratch').should('be.visible')
  })

  it('should handle project deletion flow', () => {
    const mockProjects = [
      {
        id: 'project-1',
        metadata: { title: 'Test Novel 1' }
      },
      {
        id: 'project-2', 
        metadata: { title: 'Test Novel 2' }
      }
    ]

    cy.intercept('GET', '/api/v2/projects', { body: { projects: mockProjects } }).as('getProjects')
          cy.intercept('DELETE', '/api/v2/projects/project-1', { body: { success: true } }).as('deleteProject')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Click delete button (should only show when multiple projects)
    cy.get('[title="Delete current project"]').click()
    
    // Check delete confirmation modal
    cy.contains('Delete Project').should('be.visible')
    cy.contains('Test Novel 1').should('be.visible')
    
    // Confirm deletion
    cy.contains('Delete Project').click()
    cy.wait('@deleteProject')
  })

  it('should navigate to writing interface', () => {
    const mockProjects = [
      {
        id: 'project-1',
        metadata: { title: 'Test Novel' }
      }
    ]

    cy.intercept('GET', '/api/v2/projects', { body: { projects: mockProjects } }).as('getProjects')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Click "Start Writing" button
    cy.contains('Start Writing').click()
    
    // Should navigate to chapters page
    cy.url().should('include', '/project/project-1/chapters')
  })

  it('should be accessible via keyboard navigation', () => {
    cy.intercept('GET', '/api/v2/projects', { body: { projects: [] } }).as('getProjects')
    
    cy.visit('/dashboard')
    cy.wait('@getProjects')
    
    // Tab through main elements
    cy.get('body').tab()
    cy.focused().should('contain', 'Create Your First Project')
    
    // Test modal accessibility
    cy.focused().type('{enter}')
    cy.contains('Create New Project').should('be.visible')
    
    // Test escape key
    cy.get('body').type('{esc}')
    cy.contains('Create New Project').should('not.exist')
  })
}) 