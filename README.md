# Subscriber Sim 🤖

A Streamlit-based chatbot simulator that trains and deploys a LoRA fine-tuned Jasmin model to interact with subscriber archetypes in real-time.

## What It Does

1. **Interactive Chat Simulation** — A Streamlit app where you interact with a fine-tuned Jasmin model that responds to different subscriber archetypes (horny, cheapskate, casual, troll, whale, cold, simp). Chat history is persisted in a SQLite database.
2. **Model Inference** — Local LLM inference using MLX (Apple Silicon optimized) or cloud GPU backends. Fine-tuned LoRA adapters loaded dynamically.
3. **Data Persistence** — SQLite database stores conversations, session metadata, and interaction logs for analytics and training data collection.
4. **Archetype Management** — 7 predefined subscriber personas with distinct personality traits, spending patterns, and communication styles.

## Stack

**Frontend & App:**
- [Streamlit](https://streamlit.io/) — Interactive web UI for chat simulation
- [Material Symbols](https://fonts.google.com/icons) — Icon library

**Model & Inference:**
- [Llama 3.1 8B](https://huggingface.co/meta-llama/Llama-2-7b-hf) — Base model (4-bit quantized)
- [Unsloth](https://github.com/unslothai/unsloth) — Efficient LoRA training
- [MLX](https://ml-explore.github.io/mlx/build/html/index.html) — Apple Silicon optimized inference (macOS)
- [Transformers](https://huggingface.co/transformers/) — Model loading & tokenization

**Data & Storage:**
- [SQLite](https://www.sqlite.org/) — Lightweight database for chat history & metadata
- JSONL files — Training data format

**Infrastructure:**
- Docker & Docker Compose — Containerized deployment
- Modal / Streamlit Cloud — Cloud deployment targets

## Quick Start

### Local Development

```bash
# 1. Clone and setup
git clone https://github.com/Inventiv-PH/subscriber-sim.git
cd subscriber-sim

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app/main.py
```

### Using Make (recommended)

```bash
make setup      # Setup venv and dependencies
make server     # Start MLX inference server
make app        # Start Streamlit app in another terminal
```

### Docker

```bash
docker-compose up --build
```

**Full setup guide**: See [docs/QUICK_START.md](docs/QUICK_START.md)

## Documentation

- **[docs/README.md](docs/README.md)** — Documentation index and navigation
- **[docs/QUICK_START.md](docs/QUICK_START.md)** — Setup and deployment options
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System design and components
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** — Code patterns, contributing guidelines
- **[TODO.md](TODO.md)** — Roadmap and task tracking

## Project Structure

```
subscriber-sim/
├── app/                          # Streamlit application
│   ├── main.py                   # Entry point, UI layout
│   ├── archetypes.py             # Subscriber personality definitions
│   ├── inference.py              # LLM inference logic
│   └── database.py               # SQLite operations
├── data/                         # Training data & chat logs
├── models/                       # Fine-tuned LoRA adapters
├── docs/                         # Documentation
├── scripts/                      # Utility scripts
├── Dockerfile                    # Container definition
├── docker-compose.yml            # Multi-container setup
├── requirements.txt              # Python dependencies
├── TODO.md                       # Roadmap and tasks
└── README.md                     # This file
```

## Contributing

We welcome contributions! See [DEVELOPMENT.md](docs/DEVELOPMENT.md#contributing) for guidelines.

## Task Tracking

This project uses GitHub issues for tracking. To sync GitHub issues to local tracking:

```bash
# Make sync script executable (one time)
chmod +x scripts/sync-todos.sh

# Sync issues to TODO.md
./scripts/sync-todos.sh
```

For manual tracking, edit [TODO.md](TODO.md) directly.

## License

This project is proprietary. See LICENSE file for details.
