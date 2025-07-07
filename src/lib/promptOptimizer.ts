interface ReferenceFile {
  filename: string
  content: string
}

interface PromptContext {
  chapter: number
  stage: string
  targetWords: number
  genre: string
  characters?: string[]
  sceneType?: string
  themes?: string[]
}

interface OptimizedPrompt {
  systemPrompt: string
  userPrompt: string
  tokenEstimate: number
  includedReferences: string[]
}

export class PromptOptimizer {
  private static readonly MAX_CONTEXT_TOKENS = 8000 // Reserve tokens for generation
  private static readonly TOKEN_PER_WORD_ESTIMATE = 1.3

  static optimizePrompts(
    baseSystemPrompt: string,
    baseUserPrompt: string,
    references: ReferenceFile[],
    context: PromptContext
  ): OptimizedPrompt {
    // Estimate base prompt tokens
    const baseTokens = this.estimateTokens(baseSystemPrompt + baseUserPrompt)
    const availableTokens = this.MAX_CONTEXT_TOKENS - baseTokens

    // Prioritize and select relevant reference content
    const relevantContent = this.selectRelevantContent(references, context, availableTokens)

    // Inject optimized content into prompts
    const optimizedSystemPrompt = this.injectSystemContext(baseSystemPrompt, relevantContent, context)
    const optimizedUserPrompt = this.injectUserContext(baseUserPrompt, relevantContent, context)

    return {
      systemPrompt: optimizedSystemPrompt,
      userPrompt: optimizedUserPrompt,
      tokenEstimate: this.estimateTokens(optimizedSystemPrompt + optimizedUserPrompt),
      includedReferences: relevantContent.map(c => c.source)
    }
  }

  private static selectRelevantContent(
    references: ReferenceFile[],
    context: PromptContext,
    availableTokens: number
  ): Array<{ source: string; content: string; priority: number; tokens: number }> {
    const relevantContent: Array<{ source: string; content: string; priority: number; tokens: number }> = []

    for (const ref of references) {
      const sections = this.extractRelevantSections(ref, context)
      
      for (const section of sections) {
        const tokens = this.estimateTokens(section.content)
        relevantContent.push({
          source: `${ref.filename}:${section.title}`,
          content: section.content,
          priority: section.priority,
          tokens
        })
      }
    }

    // Sort by priority (higher first)
    relevantContent.sort((a, b) => b.priority - a.priority)

    // Select content that fits within token budget
    const selected: typeof relevantContent = []
    let usedTokens = 0

    for (const content of relevantContent) {
      if (usedTokens + content.tokens <= availableTokens) {
        selected.push(content)
        usedTokens += content.tokens
      }
    }

    return selected
  }

  private static extractRelevantSections(
    ref: ReferenceFile,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []

    if (ref.filename === 'characters.md') {
      sections.push(...this.extractCharacterSections(ref.content, context))
    } else if (ref.filename === 'style-guide.md') {
      sections.push(...this.extractStyleSections(ref.content, context))
    } else if (ref.filename === 'world-building.md') {
      sections.push(...this.extractWorldSections(ref.content, context))
    } else if (ref.filename === 'outline.md') {
      sections.push(...this.extractOutlineSections(ref.content, context))
    } else if (ref.filename === 'plot-timeline.md') {
      sections.push(...this.extractTimelineSections(ref.content, context))
    }

    return sections
  }

  private static extractCharacterSections(
    content: string,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []
    const lines = content.split('\n')
    
    let currentSection = ''
    let currentContent: string[] = []
    
    for (const line of lines) {
      if (line.startsWith('##') || line.startsWith('###')) {
        // Save previous section
        if (currentSection && currentContent.length > 0) {
          const sectionText = currentContent.join('\n').trim()
          const priority = this.calculateCharacterPriority(currentSection, sectionText, context)
          
          if (priority > 0) {
            sections.push({
              title: currentSection,
              content: sectionText,
              priority
            })
          }
        }
        
        // Start new section
        currentSection = line.replace(/^#+\s*/, '')
        currentContent = []
      } else {
        currentContent.push(line)
      }
    }
    
    // Save last section
    if (currentSection && currentContent.length > 0) {
      const sectionText = currentContent.join('\n').trim()
      const priority = this.calculateCharacterPriority(currentSection, sectionText, context)
      
      if (priority > 0) {
        sections.push({
          title: currentSection,
          content: sectionText,
          priority
        })
      }
    }

    return sections
  }

  private static calculateCharacterPriority(
    sectionTitle: string,
    content: string,
    context: PromptContext
  ): number {
    let priority = 1 // Base priority

    // Higher priority for main characters
    if (sectionTitle.toLowerCase().includes('protagonist') || 
        sectionTitle.toLowerCase().includes('main character')) {
      priority += 5
    }

    // Higher priority for characters mentioned in context
    if (context.characters) {
      for (const char of context.characters) {
        if (sectionTitle.toLowerCase().includes(char.toLowerCase()) ||
            content.toLowerCase().includes(char.toLowerCase())) {
          priority += 3
          break
        }
      }
    }

    // Higher priority for dialogue and voice information
    if (content.toLowerCase().includes('voice') || 
        content.toLowerCase().includes('dialogue') ||
        content.toLowerCase().includes('speaking style')) {
      priority += 2
    }

    return priority
  }

  private static extractStyleSections(
    content: string,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []
    
    // Style guide is always high priority for consistency
    const lines = content.split('\n')
    let currentSection = ''
    let currentContent: string[] = []
    
    for (const line of lines) {
      if (line.startsWith('##') || line.startsWith('###')) {
        if (currentSection && currentContent.length > 0) {
          sections.push({
            title: currentSection,
            content: currentContent.join('\n').trim(),
            priority: 4 // High priority for style consistency
          })
        }
        
        currentSection = line.replace(/^#+\s*/, '')
        currentContent = []
      } else {
        currentContent.push(line)
      }
    }
    
    if (currentSection && currentContent.length > 0) {
      sections.push({
        title: currentSection,
        content: currentContent.join('\n').trim(),
        priority: 4
      })
    }

    return sections
  }

  private static extractWorldSections(
    content: string,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []
    
    // Extract sections and prioritize based on scene type
    const lines = content.split('\n')
    let currentSection = ''
    let currentContent: string[] = []
    
    for (const line of lines) {
      if (line.startsWith('##') || line.startsWith('###')) {
        if (currentSection && currentContent.length > 0) {
          const priority = this.calculateWorldPriority(currentSection, currentContent.join('\n'), context)
          
          if (priority > 0) {
            sections.push({
              title: currentSection,
              content: currentContent.join('\n').trim(),
              priority
            })
          }
        }
        
        currentSection = line.replace(/^#+\s*/, '')
        currentContent = []
      } else {
        currentContent.push(line)
      }
    }
    
    if (currentSection && currentContent.length > 0) {
      const priority = this.calculateWorldPriority(currentSection, currentContent.join('\n'), context)
      
      if (priority > 0) {
        sections.push({
          title: currentSection,
          content: currentContent.join('\n').trim(),
          priority
        })
      }
    }

    return sections
  }

  private static calculateWorldPriority(
    sectionTitle: string,
    content: string,
    context: PromptContext
  ): number {
    let priority = 2 // Base priority

    // Higher priority for scene-relevant locations
    if (context.sceneType) {
      if (sectionTitle.toLowerCase().includes(context.sceneType.toLowerCase()) ||
          content.toLowerCase().includes(context.sceneType.toLowerCase())) {
        priority += 3
      }
    }

    // Higher priority for general world rules
    if (sectionTitle.toLowerCase().includes('rules') ||
        sectionTitle.toLowerCase().includes('culture') ||
        sectionTitle.toLowerCase().includes('society')) {
      priority += 2
    }

    return priority
  }

  private static extractOutlineSections(
    content: string,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []
    
    // Look for chapter-specific outline information
    const lines = content.split('\n')
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      
      // Look for chapter references
      if (line.toLowerCase().includes(`chapter ${context.chapter}`) ||
          line.toLowerCase().includes(`ch ${context.chapter}`) ||
          line.toLowerCase().includes(`${context.chapter}.`)) {
        
        // Extract surrounding context
        const start = Math.max(0, i - 2)
        const end = Math.min(lines.length, i + 5)
        const contextLines = lines.slice(start, end)
        
        sections.push({
          title: `Chapter ${context.chapter} Outline`,
          content: contextLines.join('\n').trim(),
          priority: 5 // Very high priority for current chapter
        })
      }
    }

    return sections
  }

  private static extractTimelineSections(
    content: string,
    context: PromptContext
  ): Array<{ title: string; content: string; priority: number }> {
    const sections: Array<{ title: string; content: string; priority: number }> = []
    
    // Timeline is generally lower priority unless specifically relevant
    const lines = content.split('\n')
    let relevantFound = false
    
    for (const line of lines) {
      if (line.toLowerCase().includes(`chapter ${context.chapter}`) ||
          line.toLowerCase().includes('current') ||
          line.toLowerCase().includes('now')) {
        relevantFound = true
        break
      }
    }

    if (relevantFound) {
      sections.push({
        title: 'Relevant Timeline',
        content: content.substring(0, 500), // Limit timeline content
        priority: 2
      })
    }

    return sections
  }

  private static injectSystemContext(
    basePrompt: string,
    relevantContent: Array<{ source: string; content: string; priority: number; tokens: number }>,
    context: PromptContext
  ): string {
    if (relevantContent.length === 0) return basePrompt

    let contextSection = '\n\n## STORY CONTEXT\n\n'
    
    // Add genre-specific instructions
    contextSection += `**Genre:** ${context.genre}\n`
    contextSection += `**Chapter:** ${context.chapter}\n`
    contextSection += `**Stage:** ${context.stage}\n\n`

    // Add relevant reference content
    for (const content of relevantContent) {
      contextSection += `**${content.source}:**\n${content.content}\n\n`
    }

    contextSection += '## INSTRUCTIONS\n\n'
    contextSection += 'Use the above context to maintain consistency with established characters, world rules, and style guidelines. '
    contextSection += 'Reference specific details when relevant, but do not repeat information unnecessarily.\n\n'

    return basePrompt + contextSection
  }

  private static injectUserContext(
    basePrompt: string,
    relevantContent: Array<{ source: string; content: string; priority: number; tokens: number }>,
    context: PromptContext
  ): string {
    // User prompt gets minimal context injection to avoid confusion
    let contextNote = ''
    
    if (relevantContent.length > 0) {
      contextNote = `\n\nIMPORTANT: Reference the provided story context for character consistency, world rules, and style guidelines. `
      contextNote += `Focus on Chapter ${context.chapter} requirements.`
    }

    return basePrompt + contextNote
  }

  private static estimateTokens(text: string): number {
    // Rough estimation: 1.3 tokens per word on average
    const words = text.split(/\s+/).length
    return Math.ceil(words * this.TOKEN_PER_WORD_ESTIMATE)
  }
}

export default PromptOptimizer 