/**
 * UI Strings Library - Warm Mentor Tone
 * 
 * Brand Voice: Uplifting, warm, creative, mentor-like
 * Metaphors: journey, blooming, creative growth
 */

export const UI_STRINGS = {
  // Navigation & Layout
  navigation: {
    dashboard: 'Dashboard',
    library: 'Library',
    community: 'Community', 
    forum: 'Forum',
    profile: 'Profile',
    backToDashboard: '← Back to Dashboard',
  },

  // Project/Journey Management
  projects: {
    // Visible labels (UI only - backend still uses "projects")
    singular: 'Journey',
    plural: 'Journeys', 
    create: 'Begin a new journey',
    continue: 'Continue Journey',
    noProjects: "Ready to bloom? Start your first writing journey!",
    progress: {
      notStarted: "Let's get the first words flowing",
      quarter: "Great start! Your story is taking shape",
      half: "Halfway there—keep writing!",
      threeQuarter: "So close! Your journey is almost complete",
      complete: "🌱 Your creativity has bloomed!"
    }
  },

  // Chapters & Writing
  chapters: {
    generate: 'Start your next chapter',
    edit: 'Polish your chapter',
    create: 'Begin a new chapter',
    continue: 'Continue writing',
  },

  // Actions & Buttons
  actions: {
    save: 'Save progress',
    delete: 'Move to archive',
    export: 'Share your work',
    publish: 'Release into the world',
    getStarted: 'Get Started Free',
    takeTour: 'Take a Tour',
  },

  // Status & Feedback
  status: {
    saving: 'Saving your progress...',
    saved: 'All set! 🌱 Your creativity is blooming',
    error: "Looks like we hit a snag—let's try again!",
    success: 'Beautiful work! ✨',
    loading: 'Working our magic...',
  },

  // Landing Page
  landing: {
    tagline: 'From idea to publication—your writing journey starts here.',
    subtitle: 'Transform your stories into published books with AI-powered guidance, gentle encouragement, and professional tools.',
    howItWorks: {
      title: 'Your Creative Journey, Simplified',
      steps: [
        {
          title: 'Plant Your Idea',
          description: 'Share your story concept and watch it take root with our AI-powered planning tools.'
        },
        {
          title: 'Nurture Your Draft', 
          description: 'Write chapter by chapter with intelligent suggestions and gentle guidance along the way.'
        },
        {
          title: 'Bloom Into Publication',
          description: 'Polish, format, and publish your finished work with professional-grade tools.'
        }
      ]
    },
    testimonials: {
      title: 'Stories from Fellow Writers',
      quotes: [
        {
          text: "WriterBloom helped me finish my first novel. The encouragement made all the difference.",
          author: "Sarah M., Author"
        },
        {
          text: "Finally, a writing tool that feels like having a supportive mentor by your side.",
          author: "James R., Novelist"  
        }
      ]
    }
  },

  // Encouragement & Nudges
  encouragement: {
    dailyNudges: [
      "Every word you write is a step forward on your journey.",
      "Your story matters. Keep blooming.",
      "Great writers aren't born, they're grown. Keep writing.",
      "Your creativity is a gift to the world—nurture it today.",
      "Even small progress is still progress. You've got this!"
    ],
    milestones: {
      firstChapter: "🎉 Your first chapter is complete! The journey has begun.",
      halfway: "🌱 You're halfway through your journey—your dedication is inspiring!",
      nearEnd: "🌸 The finish line is in sight! Your persistence is paying off.",
      completed: "🌟 Your journey is complete! Time to share your beautiful work with the world."
    }
  }
} as const

// Helper function to get random daily nudge
export const getRandomNudge = (): string => {
  const nudges = UI_STRINGS.encouragement.dailyNudges
  return nudges[Math.floor(Math.random() * nudges.length)]
} 