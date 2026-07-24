PYTHON ?= python3
SERVICE_DIR ?= $(HOME)/.config/systemd/user
SRC_DIR := /opt/lucia-stt

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
	cp $(SRC_DIR)/lucia-stt.service $(SERVICE_DIR)/lucia-stt.service
	cp $(SRC_DIR)/lucia-stt.socket $(SERVICE_DIR)/lucia-stt.socket

enable:
	@systemctl --user daemon-reload
	@systemctl --user enable lucia-stt.socket

start:
	@systemctl --user start lucia-stt.socket

stop:
	@systemctl --user stop lucia-stt.service lucia-stt.socket

status:
	@systemctl --user status lucia-stt.socket lucia-stt.service --no-pager || true

benchmark:
	$(PYTHON) $(SRC_DIR)/stt_benchmark.py
