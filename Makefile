# ── Jasmin Subscriber Sim ─────────────────────────────────────────────────────
# Usage: make <target>   (run `make` or `make help` to see all commands)

PYTHON     := python3
VENV       := venv
VENV_PY    := $(VENV)/bin/python3
VENV_PIP   := $(VENV)/bin/pip
VENV_MLX   := $(VENV)/bin/mlx_lm.server
VENV_ST    := $(VENV)/bin/streamlit
STAMP      := $(VENV)/.installed

PEFT_DIR   := models/finetuned
MLX_DIR    := models/finetuned-mlx
APP_DB     := data/chat.db

GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
BOLD   := \033[1m
NC     := \033[0m

.DEFAULT_GOAL := help
.PHONY: help setup convert server app docker-build docker-up docker-down \
        logs clean clean-all parse modal-setup modal-deploy modal-serve hf-deploy

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@printf "$(BOLD)Jasmin Subscriber Sim$(NC)\n\n"
	@printf "$(CYAN)Setup$(NC)\n"
	@printf "  $(GREEN)make setup$(NC)          Create venv, install mlx-lm + app deps\n"
	@printf "  $(GREEN)make convert$(NC)        Convert PEFT LoRA adapter → MLX format\n"
	@printf "\n$(CYAN)Run (two-terminal workflow)$(NC)\n"
	@printf "  $(GREEN)make server$(NC)         Start MLX inference server on localhost:8080\n"
	@printf "  $(GREEN)make docker-up$(NC)      Build + start Streamlit app via Docker on :8501\n"
	@printf "\n$(CYAN)Run (native, no Docker)$(NC)\n"
	@printf "  $(GREEN)make app$(NC)            Start Streamlit app natively on localhost:8501\n"
	@printf "\n$(CYAN)Docker$(NC)\n"
	@printf "  $(GREEN)make docker-build$(NC)   Build the Docker image only\n"
	@printf "  $(GREEN)make docker-down$(NC)    Stop Docker Compose\n"
	@printf "  $(GREEN)make logs$(NC)           Tail Docker container logs\n"
	@printf "\n$(CYAN)HuggingFace Spaces deployment$(NC)\n"
	@printf "  $(GREEN)make hf-deploy$(NC)      Push hf_space/ to a HuggingFace Space\n"
	@printf "\n$(CYAN)Modal (cloud GPU deployment)$(NC)\n"
	@printf "  $(GREEN)make modal-setup$(NC)    Install modal + authenticate\n"
	@printf "  $(GREEN)make modal-deploy$(NC)   Deploy inference server to Modal cloud\n"
	@printf "  $(GREEN)make modal-serve$(NC)    Run Modal server locally for testing\n"
	@printf "\n$(CYAN)Data$(NC)\n"
	@printf "  $(GREEN)make parse$(NC)          Parse raw chat exports → data/sessions.jsonl\n"
	@printf "\n$(CYAN)Clean$(NC)\n"
	@printf "  $(GREEN)make clean$(NC)          Remove MLX adapter cache + chat DB\n"
	@printf "  $(GREEN)make clean-all$(NC)      Remove venv + all generated files\n"

# ── Setup ─────────────────────────────────────────────────────────────────────
# Uses a stamp file so pip only runs once; touch the stamp to re-run.
$(STAMP):
	@printf "$(YELLOW)Creating venv…$(NC)\n"
	$(PYTHON) -m venv --upgrade-deps $(VENV)
	@printf "$(YELLOW)Installing mlx-lm (inference server)…$(NC)\n"
	$(VENV_PY) -m pip install --quiet --upgrade pip
	$(VENV_PY) -m pip install --quiet mlx-lm
	@printf "$(YELLOW)Installing Streamlit app deps…$(NC)\n"
	$(VENV_PY) -m pip install --quiet -r app_requirements.txt
	@touch $(STAMP)
	@printf "$(GREEN)✅ Setup complete$(NC)\n"

setup: $(STAMP)

# ── Convert PEFT adapter → MLX ────────────────────────────────────────────────
$(MLX_DIR)/adapters.safetensors: $(PEFT_DIR)/adapter_model.safetensors | $(STAMP)
	@printf "$(YELLOW)Converting PEFT adapter → MLX format…$(NC)\n"
	$(VENV_PY) scripts/convert_adapter_to_mlx.py \
		--input  $(PEFT_DIR) \
		--output $(MLX_DIR)
	@printf "$(GREEN)✅ Adapter ready at $(MLX_DIR)$(NC)\n"

convert: $(MLX_DIR)/adapters.safetensors

# ── Inference server (run in Terminal 1) ─────────────────────────────────────
server: convert
	@printf "$(GREEN)Starting MLX server on localhost:8080…$(NC)\n"
	@printf "$(YELLOW)Keep this terminal open. Start the app in another terminal.$(NC)\n\n"
	./start_mlx_server.sh

# ── Streamlit app — native (run in Terminal 2) ───────────────────────────────
app: $(STAMP)
	@printf "$(GREEN)Starting Streamlit app on http://localhost:8501$(NC)\n"
	@printf "$(YELLOW)Make sure MLX server is running (make server in another terminal).$(NC)\n\n"
	$(VENV_ST) run app/main.py

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	@printf "$(YELLOW)Building Docker image…$(NC)\n"
	docker build -t jasmin-chat .
	@printf "$(GREEN)✅ Image built$(NC)\n"

docker-up: convert
	@printf "$(GREEN)Starting Streamlit app via Docker on http://localhost:8501$(NC)\n"
	@printf "$(YELLOW)Make sure MLX server is running (make server in another terminal).$(NC)\n\n"
	docker compose up --build

docker-down:
	docker compose down
	@printf "$(GREEN)✅ Stopped$(NC)\n"

logs:
	docker compose logs -f chat

# ── HuggingFace Spaces ────────────────────────────────────────────────────────
hf-deploy:
	@if [ -z "$(HF_SPACE)" ]; then \
		printf "$(YELLOW)Usage: make hf-deploy HF_SPACE=yourname/jasmin-chat$(NC)\n"; exit 1; \
	fi
	@printf "$(YELLOW)Pushing hf_space/ to https://huggingface.co/spaces/$(HF_SPACE)…$(NC)\n"
	cd hf_space && git init && git remote add space https://huggingface.co/spaces/$(HF_SPACE) 2>/dev/null || true
	cd hf_space && git add -A && git commit -m "deploy" --allow-empty
	cd hf_space && git push space main --force
	@printf "$(GREEN)✅ Deployed → https://huggingface.co/spaces/$(HF_SPACE)$(NC)\n"

# ── Modal ─────────────────────────────────────────────────────────────────────
modal-setup: $(STAMP)
	$(VENV_PY) -m pip install --quiet modal
	$(VENV)/bin/modal setup
	@printf "$(GREEN)✅ Modal ready. Run 'make modal-deploy' to deploy.$(NC)\n"

modal-deploy:
	@printf "$(YELLOW)Deploying Jasmin inference server to Modal…$(NC)\n"
	$(VENV)/bin/modal deploy scripts/modal_server.py
	@printf "$(GREEN)✅ Deployed. Copy the endpoint URL into docker-compose.yml → MLX_SERVER_URL$(NC)\n"

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
	@printf "$(YELLOW)Removing MLX adapter cache and chat DB…$(NC)\n"
	rm -f $(MLX_DIR)/adapters.safetensors
	rm -f $(APP_DB)
	@printf "$(GREEN)✅ Clean$(NC)\n"

clean-all: clean docker-down
	@printf "$(YELLOW)Removing venv…$(NC)\n"
	rm -rf $(VENV)
	@printf "$(GREEN)✅ Full clean done$(NC)\n"
