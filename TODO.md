
# 📋 TODO & Roadmap

**Last Updated**: 2026-03-17  
**Sync Status**: Manual (use `scripts/sync-todos.sh` to sync with GitHub issues)

---

## 🔴 High Priority (Current Sprint)

### 🐛 Inference Issue Diagnosis & Fix
**Status**: Starting 2026-03-18  
**Goal**: Root cause analysis and fixes for response repetition (Colab) and context drift (Streamlit)  
**Owner**: @jaimeemanuellucero  
**Tracking**: [Inference Diagnosis Epic](https://github.com/Inventiv-PH/subscriber-sim/issues)

**Phase 1: Root Cause Diagnosis**
- [ ] **[PRIORITY] Export Colab conversation logs** — Capture full prompts, raw outputs, filtered outputs. Document repetition pattern after 5-8 turns. Add debug logging to subscriber_sim.ipynb Cell 9.
- [ ] **Analyze generation parameters** — Compare Colab (working) vs Streamlit params. Check temperature, top_p, rep_pen, max_tokens. Hypothesis: low rep_pen causes repetition.
- [ ] **Inspect prompt construction** — Compare Colab vs Streamlit prompt formats. Verify system prompts, mid-conversation reminders, stop tokens.
- [ ] **Analyze response filtering** — Check if _filter_response() is too aggressive. Test disabling filters to isolate their impact.
- [ ] **Test context window size** — Current: 16 messages. Test 16 vs 24 vs 32. Measure character consistency and context retention.
- [ ] **Compare LoRA adapter formats** — PEFT (HuggingFace) vs MLX (exported). Investigate convert_adapter_to_mlx.py for lossy transformation.
- [ ] **Verify parameter parity** — Run Colab with Streamlit params. Run Streamlit with Colab params. Document what changes behavior.
- [ ] **Isolate backend vs adapter** — Test MLX with small context. Test Modal backend. Determine if issue is backend or adapter-specific.

**Phase 2: Implementation** (depends on Phase 1 findings)
- [ ] Implement fixes based on root cause findings
- [ ] A/B test all 7 archetypes with both backends
- [ ] Document before/after examples

### Core Features
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
| **High Priority** | 17 items |
| **Medium Priority** | 7 items |
| **Low Priority** | 8 items |
| **In Progress** | 0 items |
| **Completed** | 6 items |
| **Total** | 38 items |

**Completion Rate**: 16% ✓  
**Current Focus**: Inference Issue Diagnosis (8 investigation tasks)

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
