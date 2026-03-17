#!/bin/bash

# sync-todos.sh - Sync GitHub issues to TODO.md
# Usage: ./scripts/sync-todos.sh
# Requirements: gh (GitHub CLI) installed and authenticated

set -e

REPO="Inventiv-PH/subscriber-sim"
TODO_FILE="TODO.md"
GITHUB_URL="https://github.com/$REPO/issues"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📋 GitHub Issues → TODO.md Sync${NC}"
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

# Fetch issues by priority
echo "Fetching issues from $REPO..."

# High priority issues
HIGH_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:high" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")

# Medium priority issues
MEDIUM_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:medium" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")

# Low priority issues
LOW_PRIORITY=$(gh issue list --repo "$REPO" --label "priority:low" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")

# In progress issues
IN_PROGRESS=$(gh issue list --repo "$REPO" --label "status:in-progress" --state open --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null || echo "")

# Completed issues (closed)
COMPLETED=$(gh issue list --repo "$REPO" --state closed --json title,number,body --template '{{range .}}{{.number}}: {{.title}}\n{{end}}' 2>/dev/null | head -10 || echo "")

echo -e "${GREEN}✓ Issues fetched${NC}"
echo ""

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

# Generate TODO.md with new issues
TOTAL=$((HIGH_COUNT + MEDIUM_COUNT + LOW_COUNT + IN_PROG_COUNT + COMP_COUNT))
COMPLETION=$((COMP_COUNT * 100 / TOTAL))

echo "💾 Updated $TODO_FILE"
echo ""
echo -e "${GREEN}Sync complete!${NC}"
echo ""
echo "📝 Next steps:"
echo "  1. Review updated tasks in $TODO_FILE"
echo "  2. Adjust priorities if needed"
echo "  3. Mark tasks as in-progress/done"
echo "  4. Commit changes: git add TODO.md && git commit -m 'chore: sync todos from GitHub issues'"
echo ""
echo "🔗 View all issues: $GITHUB_URL"
