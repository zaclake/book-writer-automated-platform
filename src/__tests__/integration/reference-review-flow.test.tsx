/**
 * Integration tests for References page (project tabs).
 *
 * These tests validate basic render + tab switching using the current
 * `src/app/project/[projectId]/references/page.tsx` UX.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { jest } from '@jest/globals'
import ReferenceReviewPage from '@/app/project/[projectId]/references/page'

const mockParams = { projectId: 'test-project-123' }

jest.mock('@/lib/auth', () => ({
  useAuthToken: () => ({
    getAuthHeaders: jest.fn().mockResolvedValue({
      Authorization: 'Bearer mock-token',
    }),
    isSignedIn: true,
    isLoaded: true,
  }),
}))

global.fetch = jest.fn()

const mockReferenceFiles: Record<string, { name: string; content: string; lastModified: string }> = {
  'characters.md': {
    name: 'characters.md',
    content:
      '# Characters\n\n## Protagonist\n**Alex Stone** - A 16-year-old student with hidden magical abilities.\n\n## Antagonist\n**Dark Lord Malachar** - Ancient evil seeking to return to power.',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'outline.md': {
    name: 'outline.md',
    content:
      '# Plot Outline\n\n## Act I: Discovery\nChapters 1-8: Alex discovers magical powers and enters academy.',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'world-building.md': {
    name: 'world-building.md',
    content: '# World Building\n\n## Setting\nModern-day magical academy hidden from regular world.',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'style-guide.md': {
    name: 'style-guide.md',
    content: '# Style Guide\n\n## Tone\nAdventurous with moments of humor and wonder.',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'plot-timeline.md': {
    name: 'plot-timeline.md',
    content: '# Must-Includes\n\n- Magic discovery scene\n- First spell casting',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'director-guide.md': {
    name: 'director-guide.md',
    content: '# Director Guide\n\n## First Draft\nWrite fast and keep momentum.',
    lastModified: '2024-01-15T10:30:00Z',
  },
  'canon-log.md': {
    name: 'canon-log.md',
    content: '# Canon Log\n\n- Entry 1',
    lastModified: '2024-01-15T10:30:00Z',
  },
}

function jsonResponse(data: any, init?: { ok?: boolean; status?: number }) {
  const ok = init?.ok ?? true
  const status = init?.status ?? (ok ? 200 : 400)
  return Promise.resolve({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: async () => data,
    text: async () => JSON.stringify(data),
  })
}

describe('References page - integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    const navigation = require('next/navigation')
    navigation.useParams.mockReturnValue(mockParams)

    ;(global.fetch as jest.Mock).mockImplementation((url: string, init?: any) => {
      // List files
      if (url.includes(`/api/v2/projects/${mockParams.projectId}/references`) && !url.includes('/references/')) {
        return jsonResponse({
          files: Object.keys(mockReferenceFiles).map((filename) => ({ filename })),
        })
      }

      // Load individual reference file
      if (url.includes(`/api/v2/projects/${mockParams.projectId}/references/`)) {
        const filename = decodeURIComponent(url.split('/').pop() || '')
        const file = mockReferenceFiles[filename]
        if (!file) return jsonResponse({ error: 'not found' }, { ok: false, status: 404 })
        return jsonResponse(file)
      }

      // Book bible
      if (url.includes(`/api/book-bible/${mockParams.projectId}`)) {
        return jsonResponse({
          book_bible: {
            content: 'Book bible content',
            last_modified: '2024-01-01T00:00:00Z',
          },
        })
      }

      // Canon log
      if (url.includes(`/api/v2/projects/${mockParams.projectId}/canon-log`)) {
        return jsonResponse({ entries: [] })
      }

      // Default
      return jsonResponse({ error: 'unhandled' }, { ok: false, status: 404 })
    })
  })

  it('renders and shows core tabs', async () => {
    render(<ReferenceReviewPage />)

    await waitFor(() => {
      expect(screen.getByText('Reference Materials')).toBeInTheDocument()
    })

    expect(screen.getByText('Characters')).toBeInTheDocument()
    expect(screen.getByText('Plot Outline')).toBeInTheDocument()
    expect(screen.getByText('World/Glossary')).toBeInTheDocument()
    expect(screen.getByText('Style & Tone')).toBeInTheDocument()
    expect(screen.getByText('Director Guide')).toBeInTheDocument()
    expect(screen.getByText('Must-Includes')).toBeInTheDocument()
  })

  it('loads characters content and can switch tabs', async () => {
    render(<ReferenceReviewPage />)

    await waitFor(() => {
      expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Plot Outline'))

    await waitFor(() => {
      expect(screen.getByText(/Act I/)).toBeInTheDocument()
    })
  })

  it('shows Generate References CTA', async () => {
    render(<ReferenceReviewPage />)

    await waitFor(() => {
      expect(screen.getByText('Generate References')).toBeInTheDocument()
    })
  })
})

