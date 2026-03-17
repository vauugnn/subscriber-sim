#!/bin/bash

# sync-todos.sh - Sync GitHub issues ↔ TODO.md
# Usage: ./scripts/sync-todos.sh [--pull-only|--push-only]
# Requirements: gh (GitHub CLI) installed and authenticated

set -e

REPO="Inventiv-PH/subscriber-sim"
TODO_FILE="TODO.md"
GITHUB_URL="https://github.com/$REPO/issues"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
SYNC_MODE="bidirectional"
if [ "$1" == "--pull-only" ]; then
    SYNC_MODE="pull"
elif [ "$1" == "--push-only" ]; then
    SYNC_MODE="push"
fi

echo -e "${BLUE}📋 GitHub Issues ↔ TODO.md Sync${NC}"
echo "=================================="

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}✗ GitHub CLI (gh) not found${NC}"
    echo "  Install it: https://cli.github.com"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}✗ Not authenticated with GitHub${NC}"
    echo "  Run: gh auth login"
    exit 1
fi

echo -e "${GREEN}✓ GitHub CLI authenticated${NC}"
echo ""

# Function to push TODO.md tasks to GitHub
push_todos_to_github() {
    echo "Pushing TODO.md tasks → GitHub..."
    echo ""
    
    local created=0
    local current_priority="medium"
    
    # Parse TODO.md line by line
    while IFS= read -r line; do
        # Update current priority based on section headers
        if [[ $line =~ "## 🔴 High Priority" ]]; then
            current_priority="high"
        elif [[ $line =~ "## 🟡 Medium Priority" ]]; then
            current_priority="medium"
        elif [[ $line =~ "## 🟢 Low Priority" ]]; then
            current_priority="low"
        fi
        
        # Match task lines: - [ ] **TITLE** — Description
        if [[ $line =~ ^-\ \[\ \]\ \*\*(.+)\*\*\ —\ (.*)$ ]]; then
            title="${BASH_REMATCH[1]}"
            description="${BASH_REMATCH[2]}"
            
            # Skip if title is empty or looks malformed
            if [ -z "$title" ] || [[ "$title" == "[PRIORITY]"* ]]; then
                continue
            fi
            
            # Remove markdown link brackets if present
            title=$(echo "$title" | sed 's/^\[\([^]]*\)\].*/\1/')
            
            # Skip header text
            if [[ "$title" =~ "Phase" ]] || [[ "$title" =~ "High Priority" ]]; then
                continue
            fi
            
            # Trim whitespace
            title=$(echo "$title" | xargs)
            description=$(echo "$description" | xargs)
            
            if [ -z "$title" ] || [ ${#title} -lt 3 ]; then
                continue
            fi
            
            # Check if issue already exists
            existing=$(gh issue list --repo "$REPO" --search "in:title \"$title\"" --state any --limit 1 2>/dev/null | wc -l)
            
            if [ "$existing" -eq 0 ]; then
                # Create the issue (body includes priority info)
                body="**Priority**: $current_priority"$'\n'"$description"
                
                echo -n "  Creating: $title... "
                if gh issue create --repo "$REPO" \
                    --title "$title" \
                    --body "$body" \
                    < /dev/null \
                    >/dev/null 2>&1; then
                    created=$((created + 1))
                    echo -e "${GREEN}✓${NC}"
                else
                    echo -e "${RED}✗${NC}"
                fi
            fi
        fi
    done < "$TODO_FILE"
    
    echo ""
    if [ "$created" -gt 0 ]; then
        echo -e "${GREEN}✓ Created $created new issues${NC}"
    else
        echo -e "${YELLOW}ℹ No new tasks to create (issues may already exist)${NC}"
    fi
}

# Function to pull GitHub issues to TODO.md
pull_github_to_todos() {
    echo "Pulling GitHub issues → TODO.md..."
    echo ""
    
    # Fetch issues by priority
    HIGH_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:high" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")
    MEDIUM_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:medium" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")
    LOW_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:low" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")
    IN_PROGRESS=$(gh issue list --repo "$REPO" --label "status:in-progress" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")
    COMPLETED=$(gh issue list --repo "$REPO" --state closed --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null | head -10 || echo "")
    
    # Count issues
    HIGH_COUNT=$(echo "$HIGH_PRIORITY" | grep -c "^[0-9]" || true)
    MEDIUM_COUNT=$(echo "$MEDIUM_PRIORITY" | grep -c "^[0-9]" || true)
    LOW_COUNT=$(echo "$LOW_PRIORITY" | grep -c "^[0-9]" || true)
    IN_PROG_COUNT=$(echo "$IN_PROGRESS" | grep -c "^[0-9]" || true)
    COMP_COUNT=$(echo "$COMPLETED" | grep -c "^[0-9]" || true)
    
    echo "Summary:"
    echo "  🔴 High Priority: $HIGH_COUNT"
    echo "  🟡 Medium Priority: $MEDIUM_COUNT"
    echo "  🟢 Low Priority: $LOW_COUNT"
    echo "  ⚙️  In Progress: $IN_PROG_COUNT"
    echo "  ✅ Completed: $COMP_COUNT"
    echo ""
    
    if [ "$HIGH_COUNT" -eq 0 ] && [ "$MEDIUM_COUNT" -eq 0 ] && [ "$LOW_COUNT" -eq 0 ]; then
        echo -e "${YELLOW}ℹ No GitHub issues found with priority labels${NC}"
        return
    fi
    
    echo -e "${GREEN}✓ Issues pulled${NC}"
}

# Execute based on sync mode
case $SYNC_MODE in
    pull)
        pull_github_to_todos
        ;;
    push)
        push_todos_to_github
        ;;
    bidirectional)
        push_todos_to_github
        echo ""
        pull_github_to_todos
        ;;
esac

echo ""
echo "💾 Sync complete!"
echo ""
echo "📝 Next steps:"
echo "  1. View all issues: $GITHUB_URL"
echo "  2. Update TODO.md and run 'make todos-push' to sync changes"
echo ""


