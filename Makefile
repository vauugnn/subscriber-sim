# ── Jasmin Subscriber Sim ─────────────────────────────────────────────────────
# Usage: make <target>   (run `make` or `make help` to see all commands)

PYTHON     := python3
VENV       := venv
VENV_PY    := $(VENV)/bin/python3
VENV_PIP   := $(VENV)/bin/pip
VENV_MLX   := $(VENV)/bin/mlx_lm.server
VENV_ST    := $(VENV)/bin/streamlit
STAMP      := $(VENV)/.installed

PEFT_DIR   := models/lora-adapter
MLX_DIR    := models/lora-adapter-mlx
APP_DB     := data/chat.db

GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
BOLD   := \033[1m
NC     := \033[0m

.DEFAULT_GOAL := help
.PHONY: help setup convert server app docker-build docker-up docker-down \
        logs clean clean-all parse augment split modal-setup modal-deploy modal-serve \
        todos-sync todos-list todos-status

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@printf "$(BOLD)Jasmin Subscriber Sim$(NC)\n\n"
	@printf "$(CYAN)Local MLX setup (two-terminal workflow)$(NC)\n"
	@printf "  $(GREEN)make setup$(NC)          Create venv, install mlx-lm + app deps\n"
	@printf "  $(GREEN)make convert$(NC)        Convert LoRA adapter → MLX format (one-time)\n"
	@printf "  $(GREEN)make server$(NC)         Start MLX inference server on localhost:8080\n"
	@printf "  $(GREEN)make app$(NC)            Start Streamlit app natively on localhost:8501\n"
	@printf "\n$(CYAN)Local Docker workflow$(NC)\n"
	@printf "  $(GREEN)make docker-up$(NC)      Build + start app via Docker on :8501\n"
	@printf "  $(GREEN)make docker-build$(NC)   Build the Docker image only\n"
	@printf "  $(GREEN)make docker-down$(NC)    Stop Docker Compose\n"
	@printf "  $(GREEN)make logs$(NC)           Tail Docker container logs\n"
	@printf "\n$(CYAN)Modal (cloud GPU, production)$(NC)\n"
	@printf "  $(GREEN)make modal-setup$(NC)    Install modal + authenticate\n"
	@printf "  $(GREEN)make modal-deploy$(NC)   Deploy inference server to Modal cloud\n"
	@printf "  $(GREEN)make modal-serve$(NC)    Run Modal server locally for testing\n"
	@printf "\n$(CYAN)Data$(NC)\n"
	@printf "  $(GREEN)make augment$(NC)        Create general conversation templates (chat_data/general_*.txt)\n"
	@printf "  $(GREEN)make parse$(NC)          Parse ALL chat exports → data/<archetype>.jsonl\n"
	@printf "  $(GREEN)make split$(NC)          Balance archetypes → data/mlx/train.jsonl + valid.jsonl\n"
	@printf "\n$(CYAN)Todo Sync (GitHub Issues)$(NC)\n"
	@printf "  $(GREEN)make todos-sync$(NC)      Sync GitHub issues ↔ TODO.md (bidirectional)\n"
	@printf "  $(GREEN)make todos-push$(NC)      Push local TODO.md changes → GitHub issues\n"
	@printf "  $(GREEN)make todos-pull$(NC)      Pull GitHub issues → TODO.md\n"
	@printf "  $(GREEN)make todos-list$(NC)      List all open GitHub issues\n"
	@printf "  $(GREEN)make todos-status$(NC)    Show sync status\n"
	@printf "\n$(CYAN)Clean$(NC)\n"
	@printf "  $(GREEN)make clean$(NC)          Remove converted MLX adapter + chat DB\n"
	@printf "  $(GREEN)make clean-all$(NC)      Remove venv + all generated files\n"

# ── Setup ─────────────────────────────────────────────────────────────────────
$(STAMP):
	@printf "$(YELLOW)Creating venv…$(NC)\n"
	$(PYTHON) -m venv --upgrade-deps $(VENV)
	$(VENV_PY) -m pip install --quiet --upgrade pip
	@printf "$(YELLOW)Installing mlx-lm (inference server)…$(NC)\n"
	$(VENV_PY) -m pip install --quiet mlx-lm
	@printf "$(YELLOW)Installing Streamlit app deps…$(NC)\n"
	$(VENV_PY) -m pip install --quiet -r requirements.txt
	@touch $(STAMP)
	@printf "$(GREEN)✅ Setup complete$(NC)\n"

setup: $(STAMP)

# ── Convert PEFT adapter → MLX ────────────────────────────────────────────────
$(MLX_DIR)/adapters.safetensors: $(PEFT_DIR)/adapter_model.safetensors | $(STAMP)
	@printf "$(YELLOW)Converting LoRA adapter → MLX format…$(NC)\n"
	$(VENV_PY) scripts/convert_adapter_to_mlx.py \
		--input  $(PEFT_DIR) \
		--output $(MLX_DIR)
	@printf "$(GREEN)✅ MLX adapter ready at $(MLX_DIR)$(NC)\n"

convert: $(MLX_DIR)/adapters.safetensors

# ── MLX Inference server (Terminal 1) ────────────────────────────────────────
server: convert
	@printf "$(GREEN)Starting MLX inference server on localhost:8080…$(NC)\n"
	@printf "$(YELLOW)Keep this terminal open. Run 'make app' or 'make docker-up' in another.$(NC)\n\n"
	$(VENV_MLX) \
		--model        mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \
		--adapter-path $(MLX_DIR) \
		--host         0.0.0.0 \
		--port         8080

# ── Streamlit app — native (Terminal 2) ──────────────────────────────────────
app: $(STAMP)
	@printf "$(GREEN)Starting Streamlit app → http://localhost:8501$(NC)\n"
	@printf "$(YELLOW)MLX server must be running (make server).$(NC)\n\n"
	INFERENCE_BACKEND=mlx MLX_SERVER_URL=http://localhost:8080 \
		$(VENV_ST) run app/main.py

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	@printf "$(YELLOW)Building Docker image…$(NC)\n"
	docker build -t jasmin-chat .
	@printf "$(GREEN)✅ Image built$(NC)\n"

docker-up:
	@printf "$(GREEN)Starting Streamlit container → http://localhost:8501$(NC)\n"
	@printf "$(YELLOW)MLX server must be running (make server).$(NC)\n\n"
	docker compose up --build

docker-down:
	docker compose down
	@printf "$(GREEN)✅ Stopped$(NC)\n"

logs:
	docker compose logs -f chat

# ── Modal ─────────────────────────────────────────────────────────────────────
modal-setup: $(STAMP)
	$(VENV_PY) -m pip install --quiet modal
	$(VENV)/bin/modal setup
	@printf "$(GREEN)✅ Modal ready. Run 'make modal-deploy' to deploy.$(NC)\n"

modal-deploy:
	@printf "$(YELLOW)Deploying Jasmin inference server to Modal…$(NC)\n"
	$(VENV)/bin/modal deploy scripts/modal_server.py
	@printf "$(GREEN)✅ Deployed$(NC)\n"

modal-serve:
	@printf "$(YELLOW)Running Modal server locally (hot-reload)…$(NC)\n"
	$(VENV)/bin/modal serve scripts/modal_server.py

# ── Data ──────────────────────────────────────────────────────────────────────
parse: $(STAMP)
	@printf "$(YELLOW)Parsing raw chat exports → data/<archetype>.jsonl…$(NC)\n"
	$(VENV_PY) scripts/parse_chats.py
	@printf "$(GREEN)✅ Done — data/<archetype>.jsonl written with strong system prompts$(NC)\n"

augment: $(STAMP)
	@printf "$(YELLOW)Creating general conversation templates…$(NC)\n"
	$(VENV_PY) scripts/augment_data.py
	@printf "$(GREEN)✅ Done — chat_data/general_*.txt files created$(NC)\n"

split: $(STAMP)
	@printf "$(YELLOW)Balancing archetypes + writing train/valid split…$(NC)\n"
	$(VENV_PY) scripts/prepare_split.py
	@printf "$(GREEN)✅ Done — data/mlx/train.jsonl and data/mlx/valid.jsonl written$(NC)\n"

# ── Todo Sync ─────────────────────────────────────────────────────────────────
todos-sync:
	@if [ ! -f scripts/sync-todos.sh ]; then \
		printf "$(CYAN)Creating sync script…$(NC)\n"; \
		mkdir -p scripts; \
		chmod +x scripts/sync-todos.sh; \
	fi
	@printf "$(YELLOW)Syncing GitHub issues ↔ TODO.md…$(NC)\n"
	@bash scripts/sync-todos.sh
	@printf "$(GREEN)✅ Sync complete$(NC)\n"

todos-pull:
	@printf "$(YELLOW)Pulling GitHub issues → TODO.md…$(NC)\n"
	@bash scripts/sync-todos.sh --pull-only
	@printf "$(GREEN)✅ Pull complete$(NC)\n"

todos-push:
	@printf "$(YELLOW)Pushing TODO.md changes → GitHub issues…$(NC)\n"
	@bash scripts/sync-todos.sh --push-only
	@printf "$(GREEN)✅ Push complete$(NC)\n"

todos-list:
	@printf "$(CYAN)Open GitHub Issues:$(NC)\n"
	@gh issue list --state open --limit 20
	@printf "\n$(CYAN)Closed GitHub Issues (last 10):$(NC)\n"
	@gh issue list --state closed --limit 10

todos-status:
	@printf "$(CYAN)TODO.md Sync Status$(NC)\n"
	@if [ -f TODO.md ]; then \
		printf "$(GREEN)✓$(NC) TODO.md exists\n"; \
		grep -E "Last Updated|Sync Status" TODO.md || echo "  (No timestamp found)"; \
	else \
		printf "$(YELLOW)✗ TODO.md not found$(NC)\n"; \
	fi
	@printf "\n$(CYAN)GitHub Issue Summary:$(NC)\n"
	@gh issue list --state open --limit 1 2>/dev/null | wc -l | xargs -I {} printf "  Open issues: {}\n" || echo "  (gh CLI not configured)"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	@printf "$(YELLOW)Removing converted MLX adapter and chat DB…$(NC)\n"
	rm -rf $(MLX_DIR)
	rm -f $(APP_DB)
	@printf "$(GREEN)✅ Clean$(NC)\n"

clean-all: clean docker-down
	@printf "$(YELLOW)Removing venv…$(NC)\n"
	rm -rf $(VENV)
	@printf "$(GREEN)✅ Full clean done$(NC)\n"
