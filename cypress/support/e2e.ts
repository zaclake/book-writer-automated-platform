// Import commands.js using ES2015 syntax:
import './commands'

// Alternatively you can use CommonJS syntax:
// require('./commands')

declare global {
  namespace Cypress {
    interface Chainable {
      tab(): Chainable<Element>
    }
  }
}

// Add custom tab command for accessibility testing
Cypress.Commands.add('tab', { prevSubject: 'optional' }, (subject) => {
  cy.focused().then(($el) => {
    if ($el.length) {
      cy.wrap($el).trigger('keydown', { key: 'Tab' })
    } else {
      cy.get('body').trigger('keydown', { key: 'Tab' })
    }
  })
}) 