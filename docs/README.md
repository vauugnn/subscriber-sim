# 📚 Subscriber Sim Documentation

Welcome to the Subscriber Sim documentation! Find guides for understanding, using, and developing a Streamlit-based chatbot simulator that trains and deploys fine-tuned Jasmin models to interact with subscriber archetypes.

---

## 📚 Documentation Structure

### **1. [ARCHITECTURE.md](./ARCHITECTURE.md)** — System Design & Technical Overview
**For**: Architects, tech leads, contributors who need deep understanding

**Covers**:
- Complete system architecture with diagrams
- Component breakdown (app, inference, database, deployment)
- Data flow and training pipeline
- Technology stack and configuration
- Performance characteristics
- Security considerations
- Future enhancements

**When to read**:
- Understanding how the system works end-to-end
- Planning new features or integrations
- Debugging complex issues
- System optimization

---

### **2. [QUICK_START.md](./QUICK_START.md)** — Get Running in 5 Minutes
**For**: Users who want to try the app immediately

**Covers**:
- Three deployment options:
  - Option 1: Local MLX server + Streamlit (recommended for dev)
  - Option 2: Docker container
  - Option 3: Cloud deployment to Modal GPU
- Step-by-step setup for each option
- Quick command reference
- Troubleshooting common issues
- Performance tips

**When to read**:
- First time setup
- Deploying to different environments
- Troubleshooting runtime issues
- Quick command lookup

---

### **3. [DEVELOPMENT.md](./DEVELOPMENT.md)** — Contributing & Internal Details
**For**: Developers contributing to the project

**Covers**:
- Code organization and module structure
- Design patterns used in the codebase
- Data structures and schemas
- Workflow descriptions (initialization, message exchange, inference)
- Prompt engineering details
- Extension points for adding features
- Testing and validation strategies
- Debugging techniques
- Performance optimization tips
- Deployment checklist
- Common pitfalls and how to avoid them

**When to read**:
- Adding new features
- Understanding code organization
- Making architectural decisions
- Optimizing performance
- Contributing to the project

---

## 🚀 Quick Navigation

### I want to...

| Goal | Document | Section |
|------|----------|---------|
| **Get started immediately** | [QUICK_START.md](./QUICK_START.md) | Option 1: Run Locally |
| **Understand the architecture** | [ARCHITECTURE.md](./ARCHITECTURE.md) | Section 1-3: Overview & Components |
| **Deploy to production** | [QUICK_START.md](./QUICK_START.md) | Option 3: Deploy to Modal |
| **Run via Docker** | [QUICK_START.md](./QUICK_START.md) | Option 2: Run via Docker |
| **Add a new archetype** | [DEVELOPMENT.md](./DEVELOPMENT.md) | Section 6: Extension Points |
| **Add a new inference backend** | [DEVELOPMENT.md](./DEVELOPMENT.md) | Section 6: Extension Points |
| **Fix a bug** | [DEVELOPMENT.md](./DEVELOPMENT.md) | Section 8: Debugging |
| **Optimize performance** | [DEVELOPMENT.md](./DEVELOPMENT.md) | Section 9: Performance Optimization |
| **Understand the data flow** | [ARCHITECTURE.md](./ARCHITECTURE.md) | Section 3: Data Flow |
| **Learn the tech stack** | [ARCHITECTURE.md](./ARCHITECTURE.md) | Section 4: Key Technologies |
| **Process new chat data** | [QUICK_START.md](./QUICK_START.md) | Quick Commands: Data Processing |
| **Troubleshoot issues** | [QUICK_START.md](./QUICK_START.md) | Troubleshooting |

---

## 📋 Project at a Glance

**What is Subscriber Sim?**
A system that trains a fine-tuned Llama 3.1 chatbot to authentically respond as a content creator ("Jasmin") to various subscriber archetypes. It combines data collection via interactive simulation with LoRA fine-tuning and production inference.

**Tech Stack**:
- **Model**: Llama 3.1 8B (4-bit quantized)
- **Fine-tuning**: Unsloth + trl (SFTTrainer)
- **Inference**: MLX (local) or Modal GPU (cloud)
- **UI**: Streamlit (interactive chat)
- **Database**: SQLite3
- **Containerization**: Docker + Compose
- **Deployment**: Local, Docker, Modal, HuggingFace Spaces

**Key Components**:
```
Raw Chat Data → Parse → Training JSONL → Fine-tune → LoRA Adapter
                                              ↓
                                      MLX / Modal
                                        Inference
                                            ↓
                                      Streamlit Chat UI
                                            ↓
                                      SQLite Database
```

---

## 🎯 Common Workflows

### **For Data Scientists / ML Engineers**

1. **Train a new model**
   - See: [ARCHITECTURE.md](./ARCHITECTURE.md) Section 2.2 (Data & Training)
   - Process raw chats: `make parse`
   - Run `subscriber_sim_v2.ipynb` in Google Colab

2. **Fine-tune on new data**
   - Collect sessions via the Streamlit UI
   - Export to training format
   - Re-train in Colab with updated `sessions.jsonl`

3. **Add a new archetype**
   - See: [DEVELOPMENT.md](./DEVELOPMENT.md) Section 6
   - Edit `app/archetypes.py`
   - Define system prompt, parameters, and UI metadata

### **For DevOps / Backend Engineers**

1. **Deploy to production**
   - See: [QUICK_START.md](./QUICK_START.md) Option 3
   - Run: `make modal-setup && make modal-deploy`
   - Update Docker config with Modal endpoint

2. **Monitor & debug**
   - See: [DEVELOPMENT.md](./DEVELOPMENT.md) Section 8
   - Enable logging: `DEBUG=true`
   - Inspect database: `sqlite3 data/chat.db`

3. **Optimize for scale**
   - See: [ARCHITECTURE.md](./ARCHITECTURE.md) Section 8 (Error Handling)
   - Use Modal for auto-scaling
   - Enable WAL mode on SQLite (already enabled)

### **For Frontend / Product Developers**

1. **Add UI features**
   - See: [DEVELOPMENT.md](./DEVELOPMENT.md) Section 2.4 (Streamlit State Management)
   - Understand reactive state model
   - Leverage session_state for persistence

2. **Modify chat UI**
   - Edit `app/main.py` CSS and layout
   - Reference Streamlit component docs
   - Test locally: `make app`

3. **Add conversation export**
   - See: [DEVELOPMENT.md](./DEVELOPMENT.md) Section 6 (Extension Points)
   - Implement in `app/main.py` or new module
   - Use existing database layer

---

## 🔗 External Resources

### Essential Reading
- [Llama 2 Chat Format](https://huggingface.co/meta-llama/Llama-2-7b-chat)
- [LoRA Fine-Tuning](https://huggingface.co/docs/peft/en/developer_guides/lora)
- [Unsloth Docs](https://github.com/unslothai/unsloth)
- [MLX Documentation](https://ml-explore.github.io/mlx/)
- [Modal Platform](https://modal.com/docs)

### Related Projects
- Training notebook: `subscriber_sim_v2.ipynb` (Google Colab)
- Prototype notebook: `subscriber_sim.ipynb`
- Repository README: `/README.md`

---

## 💡 Pro Tips

1. **Always run two terminals for local dev**:
   - Terminal 1: `make server` (MLX inference)
   - Terminal 2: `make app` (Streamlit UI)

2. **Enable debug logging when troubleshooting**:
   ```bash
   export DEBUG=true
   make app
   ```

3. **Use Docker for consistency**:
   ```bash
   make docker-up  # One command, reproducible environment
   ```

4. **Backup chat database regularly**:
   ```bash
   cp data/chat.db data/chat.db.backup
   ```

5. **Test new archetypes with manual prompts first**:
   - Edit system prompt in `archetypes.py`
   - Start chat and try different inputs
   - Iterate on prompt before committing

---

## 🆘 Getting Help

### I found a bug
→ Check [DEVELOPMENT.md](./DEVELOPMENT.md) Section 8 (Debugging)

### Inference is slow
→ Check [QUICK_START.md](./QUICK_START.md) Performance Tips

### Can't get the app running
→ Check [QUICK_START.md](./QUICK_START.md) Troubleshooting

### Want to understand the system
→ Start with [ARCHITECTURE.md](./ARCHITECTURE.md) Section 1-2

### Adding a new feature
→ Check [DEVELOPMENT.md](./DEVELOPMENT.md) Section 6 (Extension Points)

### Deploying to production
→ Check [QUICK_START.md](./QUICK_START.md) Option 3 + Deployment Checklist in [DEVELOPMENT.md](./DEVELOPMENT.md)

---

## 📝 Document Versions

| Document | Last Updated | Applies To |
|----------|--------------|-----------|
| ARCHITECTURE.md | 2026-03-10 | v1.0+ |
| QUICK_START.md | 2026-03-10 | v1.0+ |
| DEVELOPMENT.md | 2026-03-10 | v1.0+ |

---

## 🎓 Learning Path

### Beginner (Just trying it out)
1. Read [QUICK_START.md](./QUICK_START.md) Option 1
2. Run `make setup && make server` in one terminal
3. Run `make app` in another terminal
4. Play around with the UI
5. Check chat.db with: `sqlite3 data/chat.db "SELECT * FROM conversations;"`

### Intermediate (Want to understand the system)
1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) Sections 1-3
2. Explore code: `app/*.py`
3. Try modifying archetype parameters in `app/archetypes.py`
4. Review `Makefile` targets
5. Deploy to Modal: `make modal-setup && make modal-deploy`

### Advanced (Building on this system)
1. Read entire [DEVELOPMENT.md](./DEVELOPMENT.md)
2. Study [ARCHITECTURE.md](./ARCHITECTURE.md) Sections 4-7 (Technologies & Workflows)
3. Review all files in `app/` and `scripts/`
4. Implement a feature from Section 6 (Extension Points)
5. Set up CI/CD pipeline

---

## 🚀 Next Steps

1. **Choose your path**:
   - Just try it? → [QUICK_START.md](./QUICK_START.md)
   - Understand it? → [ARCHITECTURE.md](./ARCHITECTURE.md)
   - Develop it? → [DEVELOPMENT.md](./DEVELOPMENT.md)

2. **Get set up**: `make setup`

3. **Start the app**: See [QUICK_START.md](./QUICK_START.md) Option 1

4. **Explore the code**: Review files listed in [DEVELOPMENT.md](./DEVELOPMENT.md) Section 1

5. **Make a change**: Try adding a new archetype (Section 6)

---

**Happy building! 🎯**
