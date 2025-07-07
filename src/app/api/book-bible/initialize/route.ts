import { NextRequest, NextResponse } from 'next/server'
import { writeFileSync, mkdirSync } from 'fs'
import path from 'path'
import { execSync } from 'child_process'

export async function POST(request: NextRequest) {
  try {
    const { filename, content, projectInfo } = await request.json()

    if (!filename || !content) {
      return NextResponse.json(
        { error: 'Filename and content are required' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    
    // Ensure directories exist
    mkdirSync(path.join(projectRoot, 'references'), { recursive: true })
    mkdirSync(path.join(projectRoot, 'chapters'), { recursive: true })
    mkdirSync(path.join(projectRoot, 'notes'), { recursive: true })
    mkdirSync(path.join(projectRoot, '.project-state'), { recursive: true })

    // Save the book bible file
    const bookBiblePath = path.join(projectRoot, 'book-bible.md')
    writeFileSync(bookBiblePath, content, 'utf8')

    // Parse book bible content and generate reference files
    const referenceFiles = await parseBookBibleContent(content, projectInfo)

    // Save reference files
    for (const [filename, fileContent] of Object.entries(referenceFiles)) {
      const filePath = path.join(projectRoot, 'references', filename)
      writeFileSync(filePath, fileContent, 'utf8')
    }

    // Initialize project state using Python system if available
    let stateInitialized = false
    try {
      const command = `cd "${projectRoot}" && python system/project-state-initialization-enhanced.py init`
      execSync(command, { encoding: 'utf8' })
      stateInitialized = true
    } catch (error) {
      console.warn('Python state initialization failed, using fallback:', error)
      // Fallback: create basic state files
      initializeBasicState(projectRoot)
      stateInitialized = true
    }

    // Save project metadata
    const metadataPath = path.join(projectRoot, '.project-meta.json')
    const metadata = {
      title: projectInfo?.title || 'Untitled Project',
      genre: projectInfo?.genre || 'Unknown',
      logline: projectInfo?.logline || '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      book_bible_uploaded: true,
      project_initialized: true,
      state_initialized: stateInitialized,
      reference_files: Object.keys(referenceFiles)
    }
    writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf8')

    return NextResponse.json({
      success: true,
      message: 'Project initialized successfully',
      referenceFiles: Object.keys(referenceFiles),
      stateInitialized: stateInitialized,
      projectInfo: projectInfo
    })

  } catch (error: any) {
    console.error('Project initialization error:', error)
    return NextResponse.json(
      { error: `Initialization failed: ${error.message}` },
      { status: 500 }
    )
  }
}

async function parseBookBibleContent(content: string, projectInfo: any): Promise<Record<string, string>> {
  const referenceFiles: Record<string, string> = {}
  
  // Extract sections from book bible
  const sections = extractSections(content)
  
  // Generate characters.md
  referenceFiles['characters.md'] = generateCharactersFile(sections, projectInfo)
  
  // Generate outline.md
  referenceFiles['outline.md'] = generateOutlineFile(sections, projectInfo)
  
  // Generate world-building.md
  referenceFiles['world-building.md'] = generateWorldBuildingFile(sections, projectInfo)
  
  // Generate style-guide.md
  referenceFiles['style-guide.md'] = generateStyleGuideFile(sections, projectInfo)
  
  // Generate plot-timeline.md
  referenceFiles['plot-timeline.md'] = generatePlotTimelineFile(sections, projectInfo)
  
  return referenceFiles
}

function extractSections(content: string): Record<string, string> {
  const sections: Record<string, string> = {}
  const lines = content.split('\n')
  let currentSection = ''
  let currentContent: string[] = []
  
  for (const line of lines) {
    if (line.startsWith('## ') || line.startsWith('# ')) {
      // Save previous section
      if (currentSection) {
        sections[currentSection] = currentContent.join('\n').trim()
      }
      // Start new section
      currentSection = line.replace(/^#+\s*/, '').toLowerCase()
      currentContent = []
    } else {
      currentContent.push(line)
    }
  }
  
  // Save last section
  if (currentSection) {
    sections[currentSection] = currentContent.join('\n').trim()
  }
  
  return sections
}

function generateCharactersFile(sections: Record<string, string>, projectInfo: any): string {
  let content = `# Characters Reference\n\n`
  content += `*Generated from Book Bible for: ${projectInfo?.title || 'Untitled Project'}*\n\n`
  
  // Look for character-related sections
  const characterSections = Object.keys(sections).filter(key => 
    key.includes('character') || key.includes('protagonist') || key.includes('antagonist')
  )
  
  if (characterSections.length > 0) {
    content += `## Main Characters\n\n`
    for (const section of characterSections) {
      content += `### ${section.charAt(0).toUpperCase() + section.slice(1)}\n\n`
      content += `${sections[section]}\n\n`
    }
  } else {
    content += `## Character Profiles\n\n`
    content += `*Character details to be extracted from book bible content*\n\n`
    content += `### Protagonist\n\n`
    content += `- **Name:** [To be determined]\n`
    content += `- **Age:** [To be determined]\n`
    content += `- **Goals:** [To be determined]\n`
    content += `- **Flaws:** [To be determined]\n\n`
  }
  
  return content
}

function generateOutlineFile(sections: Record<string, string>, projectInfo: any): string {
  let content = `# Story Outline\n\n`
  content += `*Generated from Book Bible for: ${projectInfo?.title || 'Untitled Project'}*\n\n`
  
  // Look for outline/plot sections
  const outlineSections = Object.keys(sections).filter(key => 
    key.includes('outline') || key.includes('plot') || key.includes('structure') || key.includes('chapter')
  )
  
  if (outlineSections.length > 0) {
    for (const section of outlineSections) {
      content += `## ${section.charAt(0).toUpperCase() + section.slice(1)}\n\n`
      content += `${sections[section]}\n\n`
    }
  } else {
    content += `## Story Structure\n\n`
    content += `*Plot outline to be extracted from book bible content*\n\n`
    content += `### Act I - Setup\n\n`
    content += `### Act II - Confrontation\n\n`
    content += `### Act III - Resolution\n\n`
  }
  
  return content
}

function generateWorldBuildingFile(sections: Record<string, string>, projectInfo: any): string {
  let content = `# World Building\n\n`
  content += `*Generated from Book Bible for: ${projectInfo?.title || 'Untitled Project'}*\n\n`
  
  // Look for world-building sections
  const worldSections = Object.keys(sections).filter(key => 
    key.includes('world') || key.includes('setting') || key.includes('location') || key.includes('environment')
  )
  
  if (worldSections.length > 0) {
    for (const section of worldSections) {
      content += `## ${section.charAt(0).toUpperCase() + section.slice(1)}\n\n`
      content += `${sections[section]}\n\n`
    }
  } else {
    content += `## Setting Details\n\n`
    content += `*World details to be extracted from book bible content*\n\n`
    content += `### Time Period\n\n`
    content += `### Location\n\n`
    content += `### Cultural Context\n\n`
  }
  
  return content
}

function generateStyleGuideFile(sections: Record<string, string>, projectInfo: any): string {
  let content = `# Style Guide\n\n`
  content += `*Generated from Book Bible for: ${projectInfo?.title || 'Untitled Project'}*\n\n`
  
  // Look for style-related sections
  const styleSections = Object.keys(sections).filter(key => 
    key.includes('style') || key.includes('tone') || key.includes('voice') || key.includes('writing')
  )
  
  content += `## Genre\n\n`
  content += `${projectInfo?.genre || 'To be determined'}\n\n`
  
  if (styleSections.length > 0) {
    for (const section of styleSections) {
      content += `## ${section.charAt(0).toUpperCase() + section.slice(1)}\n\n`
      content += `${sections[section]}\n\n`
    }
  } else {
    content += `## Writing Style\n\n`
    content += `*Style preferences to be extracted from book bible content*\n\n`
    content += `### Narrative Voice\n\n`
    content += `### Tone\n\n`
    content += `### Technical Preferences\n\n`
  }
  
  return content
}

function generatePlotTimelineFile(sections: Record<string, string>, projectInfo: any): string {
  let content = `# Plot Timeline\n\n`
  content += `*Generated from Book Bible for: ${projectInfo?.title || 'Untitled Project'}*\n\n`
  
  // Look for timeline/sequence sections
  const timelineSections = Object.keys(sections).filter(key => 
    key.includes('timeline') || key.includes('sequence') || key.includes('chronology')
  )
  
  if (timelineSections.length > 0) {
    for (const section of timelineSections) {
      content += `## ${section.charAt(0).toUpperCase() + section.slice(1)}\n\n`
      content += `${sections[section]}\n\n`
    }
  } else {
    content += `## Story Timeline\n\n`
    content += `*Timeline to be extracted from book bible content*\n\n`
    content += `### Beginning\n\n`
    content += `### Middle\n\n`
    content += `### End\n\n`
  }
  
  return content
}

function initializeBasicState(projectRoot: string): void {
  const stateDir = path.join(projectRoot, '.project-state')
  
  // Create basic state files
  const stateFiles = {
    'pattern-database.json': {},
    'quality-baselines.json': {},
    'chapter-progress.json': {},
    'session-history.json': []
  }
  
  for (const [filename, content] of Object.entries(stateFiles)) {
    const filePath = path.join(stateDir, filename)
    writeFileSync(filePath, JSON.stringify(content, null, 2), 'utf8')
  }
} 