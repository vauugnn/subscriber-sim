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
        logs clean clean-all parse modal-setup modal-deploy modal-serve

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
	@printf "  $(GREEN)make parse$(NC)          Parse raw chat exports → data/sessions.jsonl\n"
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
	./start_mlx_server.sh

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
	@printf "$(YELLOW)Parsing raw chat exports → data/sessions.jsonl…$(NC)\n"
	$(VENV_PY) scripts/parse_chats.py
	@printf "$(GREEN)✅ Done$(NC)\n"

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
