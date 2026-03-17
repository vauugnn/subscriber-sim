# 📋 TODO & Roadmap

**Last Updated**: 2026-03-17  
**Sync Status**: Manual (use `scripts/sync-todos.sh` to sync with GitHub issues)

---

## 🔴 High Priority (Current Sprint)

### Core Features
- [ ] **Refine inference pipeline** — Optimize LLM response generation with streaming output
- [ ] **Enhance database queries** — Add indexing and caching for frequently accessed conversations
- [ ] **Improve UI/UX** — Better sidebar navigation and session management in Streamlit

### Infrastructure
- [ ] **Docker optimization** — Reduce image size and startup time
- [ ] **Error handling** — Comprehensive error pages and logging in production

---

## 🟡 Medium Priority (Next Sprint)

### Features
- [ ] **Add prompt templates** — Allow customizable prompts for different conversation types
- [ ] **Export conversations** — Bulk export chat data for analysis and training
- [ ] **Session analytics** — Dashboard showing conversation statistics and metrics
- [ ] **Archetype customization** — UI to adjust archetype traits without code changes

### Documentation
- [ ] **API documentation** — OpenAPI spec for inference endpoints
- [ ] **Video tutorials** — Setup and usage walkthroughs
- [ ] **Contributing guide** — Detailed steps for new contributors

---

## 🟢 Low Priority (Backlog)

### Enhancements
- [ ] **Multi-model support** — Allow switching between different base models
- [ ] **Fine-tuning UI** — Web interface for training custom LoRA adapters
- [ ] **User accounts** — Track individual subscribers and personalized data
- [ ] **Real-time analytics** — WebSocket-based live chat statistics
- [ ] **Mobile app** — React Native companion app for on-the-go chat

### DevOps
- [ ] **CI/CD pipeline** — GitHub Actions for automated testing and deployment
- [ ] **Monitoring** — Prometheus metrics and Grafana dashboards
- [ ] **Load testing** — Performance benchmarks under concurrent users

---

## 📌 In Progress

> Tasks currently being worked on by the team

---

## ✅ Completed

- [x] Initial Streamlit app setup
- [x] SQLite database integration
- [x] Archetype system implementation
- [x] Basic inference pipeline
- [x] Docker containerization
- [x] Documentation structure

---

## 🔄 Sync with GitHub Issues

To automatically sync tasks from GitHub issues to this file:

```bash
# Make the script executable
chmod +x scripts/sync-todos.sh

# Run the sync script
./scripts/sync-todos.sh

# This will:
# 1. Fetch all open issues from GitHub
# 2. Extract task titles and descriptions
# 3. Update the sections above with new tasks
# 4. Preserve manual edits (prioritization, status)
```

### Manual Sync Process

If you prefer to manually track GitHub issues:

1. Create an issue on GitHub: https://github.com/Inventiv-PH/subscriber-sim/issues
2. Label it with:
   - `priority: high` / `priority: medium` / `priority: low`
   - `type: feature` / `type: bug` / `type: docs`
   - `status: backlog` / `status: in-progress` / `status: done`
3. Add an issue link in the relevant TODO.md section:

   ```
   - [ ] **Issue title** — Description
         [GitHub Issue #123](https://github.com/Inventiv-PH/subscriber-sim/issues/123)
   ```

---

## 📊 Metrics

| Metric | Count |
|--------|-------|
| **High Priority** | 3 items |
| **Medium Priority** | 7 items |
| **Low Priority** | 8 items |
| **In Progress** | 0 items |
| **Completed** | 6 items |
| **Total** | 24 items |

**Completion Rate**: 25% ✓

---

## 🎯 Next Steps

1. **Review priorities** — Adjust based on current needs
2. **Assign tasks** — Pick items from High Priority to start
3. **Update status** — Use checkboxes and "In Progress" section as work progresses
4. **Sync with GitHub** — Run `sync-todos.sh` regularly to stay in sync

---

## 📞 Questions?

- See [DEVELOPMENT.md](./docs/DEVELOPMENT.md) for contribution guidelines
- Open an issue on [GitHub](https://github.com/Inventiv-PH/subscriber-sim/issues)
- Check [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for technical context
