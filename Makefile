# One command rebuilds everything from the sources: `make`.
.PHONY: all fetch extract validate build load test lint
all: fetch extract validate build
fetch:    ; uv run kwelec fetch
extract:  ; uv run kwelec extract
validate: ; uv run kwelec validate
build:    ; uv run kwelec build
load:     ; uv run kwelec load --migrate     # needs SUPABASE_PROJECT_REF and SUPABASE_ACCESS_TOKEN
test:     ; uv run pytest -q
lint:     ; uv run ruff check src tests
