/// <reference types="cypress" />

// Custom commands for authentication mocking
Cypress.Commands.add('mockAuth', (user = { id: 'user-1', name: 'Test User' }) => {
  cy.window().then((win) => {
    win.localStorage.setItem('clerk-session', JSON.stringify(user))
  })
})

// Custom command to wait for API calls with retry
Cypress.Commands.add('waitForApiCall', (alias: string, timeout = 10000) => {
  cy.wait(alias, { timeout })
})

declare global {
  namespace Cypress {
    interface Chainable {
      mockAuth(user?: { id: string; name: string }): Chainable<void>
      waitForApiCall(alias: string, timeout?: number): Chainable<null>
    }
  }
} 