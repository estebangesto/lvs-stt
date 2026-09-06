PYTHON ?= python3
SERVICE_DIR ?= $(HOME)/.config/systemd/user
SRC_DIR ?= $(CURDIR)

.PHONY: help lint install enable start stop status benchmark

help:
	@echo "Targets:"
	@echo "  lint      - compile-check the Python files"
	@echo "  install   - copy systemd units into ~/.config/systemd/user"
	@echo "  enable    - enable the socket unit"
	@echo "  start     - start the socket unit"
	@echo "  stop      - stop socket and service"
	@echo "  status    - show systemd status"
	@echo "  benchmark - run the benchmark helper"

lint:
	$(PYTHON) -m py_compile $(SRC_DIR)/transcribe_whisper_fast.py $(SRC_DIR)/stt_benchmark.py $(SRC_DIR)/stt_socket_client.py

install:
	mkdir -p $(SERVICE_DIR)
	cp $(SRC_DIR)/lvs-stt.service $(SERVICE_DIR)/lvs-stt.service
	cp $(SRC_DIR)/lvs-stt.socket $(SERVICE_DIR)/lvs-stt.socket

enable:
	@systemctl --user daemon-reload
	@systemctl --user enable lvs-stt.socket

start:
	@systemctl --user start lvs-stt.socket

stop:
	@systemctl --user stop lvs-stt.service lvs-stt.socket

status:
	@systemctl --user status lvs-stt.socket lvs-stt.service --no-pager || true

benchmark:
	$(PYTHON) $(SRC_DIR)/stt_benchmark.py
