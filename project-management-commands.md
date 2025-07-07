# Project Management Commands - Quick Reference

*Essential commands for managing multiple novel projects*

---

## 🔧 **ESSENTIAL PROJECT COMMANDS**

### **📋 Project Information**
```
"List my projects"              → Overview of all projects and their status
"Project status"                → Detailed info about current project  
"Project stats"                 → Writing statistics and progress analytics
"All projects summary"          → Workspace overview with totals
```

### **🆕 Starting New Projects**
```
"Start new project"             → Clear current directory, fresh start
"Start new project 'Title'"     → Create new project in subdirectory (recommended)
"Clear current project"         → Wipe current project, keep book-bible.md
"Create project workspace 'Name'" → Set up new project structure
```

### **🔄 Project Navigation**
```
"Switch to project 'Title'"     → Change to different project
"Load project 'Title'"          → Same as switch to project
```

### **💾 Project Completion**
```
"Archive current project"       → Complete and archive finished novel
"Backup current project"        → Create manual backup snapshot
```

---

## 📁 **PROJECT STRUCTURE**

### **Recommended Directory Layout**
```
writing-workspace/
├── .projects-registry.json         ← Auto-created project registry
├── mystery-novel/                  ← Individual project directories  
│   ├── book-bible.md
│   ├── .project-meta.json         ← Project metadata
│   ├── .project-state/            ← State tracking
│   ├── chapters/
│   ├── references/
│   └── notes/
├── romance-novel/
├── sci-fi-thriller/
└── archived-projects/              ← Completed novels
    ├── fantasy-epic-completed/
    └── thriller-novel-completed/
```

---

## 🚀 **COMMON WORKFLOWS**

### **Workflow 1: Starting Your First Project**
```bash
"Start new project 'Mystery Novel'"
# Fill out book-bible.md in ./mystery-novel/
"Initialize my book project"
"Write chapter 1"
```

### **Workflow 2: Multiple Projects**
```bash
# Working on Mystery Novel (Chapter 8)
"Start new project 'Romance Novel'"     # Create second project
# Fill out romance book bible, initialize
"Write chapter 1"                       # Write romance chapter 1
"Switch to project 'Mystery Novel'"     # Back to mystery
"Write chapter 9"                       # Continue mystery
"List my projects"                      # See both projects
```

### **Workflow 3: Completing a Novel**
```bash
"Write chapter 25"                      # Final chapter
"Project status"                        # Check completion stats
"Archive current project"               # Professional archiving
"Start new project 'Next Novel'"       # Begin next book
```

---

## 🎯 **ENHANCED EXISTING COMMANDS**

### **All Original Commands Still Work**
- `"Initialize my book project"` - Now detects existing projects
- `"Write chapter X"` - Uses current project context automatically
- `"Rewrite chapter X"` - Maintains project-specific quality standards
- All quality control commands work within current project

### **What's New with Existing Commands**
- **Perfect project isolation:** Characters, patterns, quality tracking all separate
- **Smart initialization:** Detects existing vs. new projects  
- **Automatic context loading:** Each project remembers its state
- **Project-aware backups:** All operations preserve project integrity

---

## 🔍 **PROJECT STATUS INFORMATION**

### **"Project status" shows:**
- ✅ Progress (chapters completed, word count, target)
- ✅ Writing quality scores and trends
- ✅ Project details (created, genre, inspiration)
- ✅ Next actions and story momentum
- ✅ System recommendations

### **"List my projects" shows:**
- ✅ All projects with status (Active, Paused, Complete)
- ✅ Progress percentages and quality averages
- ✅ Last session dates for each project
- ✅ Workspace totals and statistics
- ✅ Quick action suggestions

---

## 🛠️ **BACKUP & RECOVERY**

### **Automatic Backups**
- Before any destructive operation (clear, archive)
- After each chapter completion
- Daily if project was worked on
- Before switching projects

### **Manual Backup**
```
"Backup current project"            → Create named backup
"Restore from backup"               → Show available backups to restore
```

### **Recovery Options**
```
"Restore project to backup 'date'"  → Specific backup restoration
"Repair project database"           → Fix corrupted project data
"Reinitialize references"           → Regenerate from book-bible.md
```

---

## ⚠️ **IMPORTANT NOTES**

### **Project Isolation**
- ✅ **Character voices separate:** Each project maintains distinct character personalities
- ✅ **Pattern tracking separate:** No cross-contamination of descriptions/metaphors
- ✅ **Quality baselines separate:** Each project develops its own standards
- ✅ **Plot continuity separate:** Story threads tracked per project

### **Compatibility**
- ✅ **Zero breaking changes:** All existing commands work exactly the same
- ✅ **Existing projects:** Continue working without modification
- ✅ **File structure:** Current structure preserved and enhanced
- ✅ **Learning curve:** If you know current system, you know new system

### **Best Practices**
- 🎯 **Use subdirectories:** `"Start new project 'Title'"` creates cleaner organization
- 🎯 **Regular backups:** System auto-backs up, but manual backups for peace of mind
- 🎯 **Clear naming:** Use descriptive project names for easy identification
- 🎯 **Archive completed:** Use `"Archive current project"` for professional completion

---

## 📞 **QUICK HELP**

### **Most Common Commands:**
```bash
"List my projects"              # See all your novels
"Project status"                # Current project details  
"Start new project 'Title'"     # Begin new novel
"Switch to project 'Title'"     # Change projects
"Write chapter X"               # Normal chapter writing
```

### **If Something Goes Wrong:**
```bash
"Restore from backup"           # Roll back to previous state
"Reinitialize references"       # Fix missing reference files
"Project status"                # Check project health
"Repair project database"       # Fix corrupted tracking
```

---

*For complete details, see the full Project Management System documentation in `system/system/project-manager.md` and updated User Manual.* 