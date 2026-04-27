.PHONY: help install lint test

help:
	@echo "ohMyStock — available make targets:"
	@echo "  make install   Install / sync dependencies via uv"
	@echo "  make lint      Run linter (not configured yet)"
	@echo "  make test      Run pytest via uv"
	@echo "  make help      Show this message"

install:
	uv sync

lint:
	@echo "lint not configured yet"

test:
	uv run pytest
