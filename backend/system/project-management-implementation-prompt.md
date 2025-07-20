# Project Management System Implementation Prompt

## CONTEXT: Automated Novel Writing System

I have built a comprehensive automated novel writing system that helps users create professional-quality novels through simple commands. The system currently works as follows:

### Current System Architecture:
1. **Book Bible Generator** (`tools/book-bible-generator.html`) - Visual form that emails users a complete book bible
2. **Project Initialization** - Command "Initialize my book project" reads book-bible.md and creates reference files
3. **Chapter Writing** - Commands like "Write chapter 1" generate professional chapters using AI
4. **Quality Control** - 8-layer quality framework with automatic revision and consistency tracking
5. **Pattern Prevention** - Cross-chapter tracking to prevent repetitive descriptions/metaphors

### Current File Structure:
```
book-project/
├── book-bible.md              ← User places this from email/download
├── chapters/                  ← AI creates chapters here
│   ├── chapter-01.md
│   ├── chapter-02.md
│   └── ...
├── references/                ← AI generates these from book bible
│   ├── characters.md
│   ├── outline.md
│   ├── world-building.md
│   ├── style-guide.md
│   └── plot-timeline.md
└── notes/                     ← Optional user workspace
```

### Current Commands Available:
- "Initialize my book project" - Sets up references from book-bible.md
- "Write chapter X" - Generates individual chapters
- "Reinitialize project" - Fixes corrupted projects
- "Restore to chapter X" - Rollback functionality
- Quality control commands (audit, check consistency, etc.)

### Key System Files (for context):
- `user-manual.md` - Complete user instructions
- `tools/book-bible-generator.html` - Visual form with EmailJS integration
- `frameworks/craft-excellence-framework.md` - Quality requirements
- `chapter-generation-protocol.md` - 5-stage chapter creation process
- `analysis/failure-mode-analysis.md` - Failure detection and recovery
- `docs/emailjs-setup-guide.md` - Email configuration instructions

## PROBLEM TO SOLVE

The current system has **NO project management capabilities**:

❌ **Missing Functionality:**
- No way to start a completely fresh project (clear everything)
- No way to manage multiple book projects simultaneously  
- No way to archive completed projects
- No way to switch between different book projects
- No way to list existing projects
- No clear separation between different books
- No project naming/organization system

❌ **Current Limitations:**
- System assumes one active project per directory
- Reference files get overwritten when reinitializing
- Pattern databases don't distinguish between different books
- Quality baselines mix data from different projects
- No backup/restore functionality for project states
- Users must manually manage directories and files

## REQUIREMENTS FOR NEW PROJECT MANAGEMENT SYSTEM

### 1. **Project Lifecycle Management**
Implement commands for complete project lifecycle:

**New Project Commands:**
- `"Start new project"` or `"Create new project 'project-name'"` - Complete fresh start
- `"Clear current project"` - Wipe current project clean while staying in same directory
- `"Archive current project"` - Move completed project to archive with metadata

**Project Switching:**
- `"List my projects"` - Show all available projects
- `"Switch to project 'name'"` - Change active project context
- `"Load project 'name'"` - Restore a specific project state

### 2. **Enhanced Directory Management**
**Option A: Directory-Based Projects (Recommended)**
- Each book project gets its own folder
- System auto-detects project based on current directory
- Commands work within the current directory context
- Simple for users to understand and manage

**Option B: Named Project System**
- Multiple projects can exist in same directory with naming
- System manages project separation internally
- More complex but allows project coexistence

### 3. **Project State Management**
**State Tracking:**
- Track which chapters are completed
- Save quality baselines per project
- Maintain separate pattern databases per project
- Store project metadata (creation date, status, word count, etc.)

**Backup/Restore:**
- `"Backup current project"` - Create snapshot
- `"Restore project to backup 'date'"` - Rollback entire project
- `"Export project"` - Create portable project archive
- `"Import project from 'archive'"` - Restore from backup

### 4. **Project Organization**
**Project Status:**
- Track project status: "Planning", "Writing", "Revising", "Complete"
- Show progress: chapters completed, word count, estimated completion
- Display last modified, creation date, etc.

**Project Metadata:**
- Project name, genre, status
- Target word count, current word count
- Character count, chapter count
- Quality score averages
- Last writing session date

### 5. **Enhanced Commands**
**Project Info:**
- `"Project status"` - Show current project details
- `"Project stats"` - Writing statistics and progress
- `"All projects summary"` - Overview of all projects

**Project Management:**
- `"Rename current project to 'new-name'"` - Change project name
- `"Duplicate project as 'new-name'"` - Copy project for variations
- `"Delete project 'name'"` - Remove project permanently (with confirmation)

### 6. **Integration with Existing System**
**Maintain Compatibility:**
- All existing commands must continue working
- Current file structure should be preserved for active projects
- Book bible generator workflow remains unchanged
- Quality control and chapter generation unchanged

**Enhanced Initialization:**
- `"Initialize my book project"` should detect if project already exists
- Option to reinitialize vs. create new vs. restore
- Smart handling of existing reference files

## IMPLEMENTATION PRIORITIES

### Phase 1: Basic Project Management (Essential)
1. **Clear/Reset Project** - `"Clear current project"` command
2. **New Project Setup** - `"Start new project"` command  
3. **Project Status** - `"Project status"` command
4. **Archive Completed** - `"Archive current project"` command

### Phase 2: Multi-Project Support (Important)
5. **List Projects** - `"List my projects"` command
6. **Project Switching** - Directory-based or named system
7. **Project State Separation** - Separate databases per project

### Phase 3: Advanced Features (Nice to Have)
8. **Backup/Restore** - Project snapshot functionality
9. **Project Statistics** - Progress tracking and analytics  
10. **Import/Export** - Portable project archives

## TECHNICAL CONSIDERATIONS

### File Structure Enhancements:
```
book-projects/                 ← Master projects directory (optional)
├── thriller-novel-1/          ← Individual project directories
│   ├── book-bible.md
│   ├── chapters/
│   ├── references/
│   ├── .project-meta.json     ← New: Project metadata
│   └── .project-state/        ← New: State tracking
└── romance-novel-2/
    ├── book-bible.md
    ├── chapters/
    ├── references/
    ├── .project-meta.json
    └── .project-state/
```

### State Management:
- Project metadata in JSON format
- Separate pattern databases per project
- Quality baselines stored per project
- Chapter progress tracking
- Session history and statistics

### Error Handling:
- Confirm destructive operations (clear, delete, archive)
- Validate project names and prevent conflicts
- Handle missing files gracefully
- Provide recovery options for corrupted projects

### User Experience:
- Clear status messages for all operations
- Progress indicators for long operations
- Helpful error messages with suggested fixes
- Consistent command patterns

## INTEGRATION POINTS

**Must integrate with:**
1. **Book Bible Generator** - Projects created from emailed book bibles
2. **Chapter Generation** - All existing chapter commands work within project context
3. **Quality Control** - Quality frameworks maintain separate baselines per project
4. **Pattern Tracking** - Separate pattern databases prevent cross-project contamination
5. **User Manual** - Update documentation to include project management commands

**Preserve existing:**
- All current commands and their functionality
- File formats and structures for active projects
- Quality control mechanisms and standards
- Chapter generation protocols and workflows

## SUCCESS CRITERIA

✅ **User can:**
- Start completely fresh projects without confusion
- Manage multiple books simultaneously without cross-contamination
- Archive completed projects cleanly
- Get clear status on all their projects
- Switch between projects seamlessly
- Recover from mistakes with backup/restore

✅ **System maintains:**
- All existing functionality unchanged
- Quality standards per project
- Pattern tracking separation
- File organization consistency
- User workflow simplicity

✅ **Technical implementation:**
- No breaking changes to existing commands
- Clean separation of project data
- Robust error handling and recovery
- Efficient state management
- Clear documentation and examples

## REQUEST

Please implement a comprehensive project management system that solves these problems while maintaining full compatibility with the existing automated novel writing system. Focus on user experience simplicity while providing robust project lifecycle management capabilities.

The solution should feel natural and obvious to users who are already comfortable with the current "Initialize my book project" → "Write chapter 1" workflow, while adding the missing project management layer they need.

Provide both the implementation code/commands and updated documentation showing the new workflow. 