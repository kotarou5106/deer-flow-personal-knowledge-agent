#!/usr/bin/env bash
#
# deploy.sh - Build, start, or stop DeerFlow production services
#
# Commands:
#   deploy.sh                    — build + start
#   deploy.sh build              — build all images (mode-agnostic)
#   deploy.sh start              — start from pre-built images
#   deploy.sh restart            — restart long-running services
#   deploy.sh status             — show long-running service status
#   deploy.sh down               — stop and remove containers
#   deploy.sh init-extensions-config — initialise extensions_config.json only
#
# Sandbox mode (local / aio / provisioner) is auto-detected from config.yaml.
#
# Examples:
#   deploy.sh                    # build + start
#   deploy.sh build              # build all images
#   deploy.sh start              # start pre-built images
#   deploy.sh restart            # restart long-running services
#   deploy.sh status             # show long-running service status
#   deploy.sh down               # stop and remove containers
#
# Must be run from the repo root directory.

set -e

case "${1:-}" in
    build|start|restart|status|down|init-extensions-config)
        CMD="$1"
        if [ -n "${2:-}" ]; then
            echo "Unknown argument: $2"
            echo "Usage: deploy.sh [build|start|restart|status|down|init-extensions-config]"
            exit 1
        fi
        ;;
    "")
        CMD=""
        ;;
    *)
        echo "Unknown argument: $1"
        echo "Usage: deploy.sh [build|start|restart|status|down|init-extensions-config]"
        exit 1
        ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOCKER_DIR="$REPO_ROOT/docker"
COMPOSE_CMD=(docker compose -p deer-flow -f "$DOCKER_DIR/docker-compose.yaml")

# ── Colors ────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

validate_json_file() {
    local path="$1"

    if command -v python3 > /dev/null 2>&1; then
        python3 - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    json.load(f)
PY
    elif command -v python > /dev/null 2>&1; then
        python - "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    json.load(f)
PY
    elif command -v node > /dev/null 2>&1; then
        node -e 'JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"))' "$path"
    else
        echo -e "${RED}✗ Cannot validate JSON: python3, python, and node are unavailable.${NC}" >&2
        return 1
    fi
}

init_extensions_config() {
    if [ -z "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
        export DEER_FLOW_EXTENSIONS_CONFIG_PATH="$REPO_ROOT/extensions_config.json"
    fi

    local target="$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
    local default_template="$REPO_ROOT/docker/extensions_config.default.json"
    local parent_dir
    local tmp_file

    if [ -d "$target" ]; then
        echo -e "${RED}✗ extensions_config.json path is a directory: $target${NC}" >&2
        echo "  Replace it with a JSON file before starting Docker Compose." >&2
        return 1
    fi

    if [ -f "$target" ]; then
        if ! validate_json_file "$target"; then
            echo -e "${RED}✗ extensions_config.json is not valid JSON: $target${NC}" >&2
            echo "  Existing configuration was left unchanged." >&2
            return 1
        fi
        echo -e "${GREEN}✓ extensions_config.json: $target${NC}"
        return 0
    fi

    if [ -e "$target" ]; then
        echo -e "${RED}✗ extensions_config.json path exists but is not a regular file: $target${NC}" >&2
        return 1
    fi

    if [ ! -f "$default_template" ]; then
        echo -e "${RED}✗ Missing default extensions config template: $default_template${NC}" >&2
        return 1
    fi

    if ! validate_json_file "$default_template"; then
        echo -e "${RED}✗ Default extensions config template is not valid JSON: $default_template${NC}" >&2
        return 1
    fi

    parent_dir="$(dirname "$target")"
    mkdir -p "$parent_dir"
    tmp_file="$parent_dir/.$(basename "$target").tmp.$$"
    cp "$default_template" "$tmp_file"
    chmod 600 "$tmp_file"
    mv "$tmp_file" "$target"
    echo -e "${GREEN}✓ Created safe default extensions_config.json at $target${NC}"
}

if [ "$CMD" = "init-extensions-config" ]; then
    init_extensions_config
    exit 0
fi

# ── DEER_FLOW_HOME ────────────────────────────────────────────────────────────

if [ -z "$DEER_FLOW_HOME" ]; then
    export DEER_FLOW_HOME="$REPO_ROOT/backend/.deer-flow"
fi
echo -e "${BLUE}DEER_FLOW_HOME=$DEER_FLOW_HOME${NC}"
mkdir -p "$DEER_FLOW_HOME"

# ── DEER_FLOW_REPO_ROOT (for skills host path in DooD) ───────────────────────

export DEER_FLOW_REPO_ROOT="$REPO_ROOT"

# ── config.yaml ───────────────────────────────────────────────────────────────

if [ -z "$DEER_FLOW_CONFIG_PATH" ]; then
    export DEER_FLOW_CONFIG_PATH="$REPO_ROOT/config.yaml"
fi

if  [ "$CMD" != "down" ] && [ ! -f "$DEER_FLOW_CONFIG_PATH" ]; then
    # Try to seed from repo (config.example.yaml is the canonical template)
    if [ -f "$REPO_ROOT/config.example.yaml" ]; then
        cp "$REPO_ROOT/config.example.yaml" "$DEER_FLOW_CONFIG_PATH"
        echo -e "${GREEN}✓ Seeded config.example.yaml → $DEER_FLOW_CONFIG_PATH${NC}"
        echo -e "${YELLOW}⚠ config.yaml was seeded from the example template.${NC}"
        echo "  Run 'make setup' to generate a minimal config, or edit $DEER_FLOW_CONFIG_PATH manually before use."
    else
        echo -e "${RED}✗ No config.yaml found.${NC}"
        echo "  Run 'make setup' from the repo root (recommended),"
        echo "  or 'make config' for the full template, then set the required model API keys."
        exit 1
    fi
else
    echo -e "${GREEN}✓ config.yaml: $DEER_FLOW_CONFIG_PATH${NC}"
fi

# ── extensions_config.json ───────────────────────────────────────────────────

if [ "$CMD" != "down" ]; then
    init_extensions_config
fi


# ── BETTER_AUTH_SECRET ───────────────────────────────────────────────────────
# Required by Next.js in production. Generated once and persisted so auth
# sessions survive container restarts.

_secret_file="$DEER_FLOW_HOME/.better-auth-secret"
if [ -z "$BETTER_AUTH_SECRET" ]; then
    if [ -f "$_secret_file" ]; then
        export BETTER_AUTH_SECRET
        BETTER_AUTH_SECRET="$(cat "$_secret_file")"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET loaded from $_secret_file${NC}"
    else
        export BETTER_AUTH_SECRET
        if command -v python3 > /dev/null 2>&1 && \
            BETTER_AUTH_SECRET="$(python3 -c 'import sys; sys.version_info >= (3, 6) or sys.exit(1); import secrets; print(secrets.token_hex(32))' 2>/dev/null)"; then
            true
        elif command -v python > /dev/null 2>&1 && \
            BETTER_AUTH_SECRET="$(python -c 'import sys; sys.version_info >= (3, 6) or sys.exit(1); import secrets; print(secrets.token_hex(32))' 2>/dev/null)"; then
            true
        elif command -v openssl > /dev/null 2>&1 && \
            BETTER_AUTH_SECRET="$(openssl rand -hex 32)"; then
            true
        else
            echo -e "${RED}✗ Cannot generate BETTER_AUTH_SECRET: python3, python, and openssl are all unavailable.${NC}" >&2
            echo -e "${RED}  Set BETTER_AUTH_SECRET manually before running make up.${NC}" >&2
            exit 1
        fi
        echo "$BETTER_AUTH_SECRET" > "$_secret_file"
        chmod 600 "$_secret_file"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET generated → $_secret_file${NC}"
    fi
fi

# ── DEER_FLOW_INTERNAL_AUTH_TOKEN ────────────────────────────────────────────
# Shared by all Gateway workers so channel workers can call internal Gateway
# APIs even when the request is handled by a different Uvicorn worker.

_internal_auth_token_file="$DEER_FLOW_HOME/.internal-auth-token"
if  [ "$CMD" != "down" ] && [ -z "$DEER_FLOW_INTERNAL_AUTH_TOKEN" ]; then
    if [ -f "$_internal_auth_token_file" ]; then
        export DEER_FLOW_INTERNAL_AUTH_TOKEN
        DEER_FLOW_INTERNAL_AUTH_TOKEN="$(cat "$_internal_auth_token_file")"
        echo -e "${GREEN}✓ DEER_FLOW_INTERNAL_AUTH_TOKEN loaded from $_internal_auth_token_file${NC}"
    else
        export DEER_FLOW_INTERNAL_AUTH_TOKEN
        if command -v python3 > /dev/null 2>&1 && \
            DEER_FLOW_INTERNAL_AUTH_TOKEN="$(python3 -c 'import sys; sys.version_info >= (3, 6) or sys.exit(1); import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null)"; then
            true
        elif command -v python > /dev/null 2>&1 && \
            DEER_FLOW_INTERNAL_AUTH_TOKEN="$(python -c 'import sys; sys.version_info >= (3, 6) or sys.exit(1); import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null)"; then
            true
        elif command -v openssl > /dev/null 2>&1 && \
            DEER_FLOW_INTERNAL_AUTH_TOKEN="$(openssl rand -hex 32)"; then
            true
        else
            echo -e "${RED}✗ Cannot generate DEER_FLOW_INTERNAL_AUTH_TOKEN: python3, python, and openssl are all unavailable.${NC}" >&2
            echo -e "${RED}  Set DEER_FLOW_INTERNAL_AUTH_TOKEN manually before running make up.${NC}" >&2
            exit 1
        fi
        echo "$DEER_FLOW_INTERNAL_AUTH_TOKEN" > "$_internal_auth_token_file"
        chmod 600 "$_internal_auth_token_file"
        echo -e "${GREEN}✓ DEER_FLOW_INTERNAL_AUTH_TOKEN generated → $_internal_auth_token_file${NC}"
    fi
fi

# ── detect_sandbox_mode ───────────────────────────────────────────────────────

detect_sandbox_mode() {
    local sandbox_use=""
    local provisioner_url=""

    [ -f "$DEER_FLOW_CONFIG_PATH" ] || { echo "local"; return; }

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*use:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

    if [[ "$sandbox_use" == *"deerflow.community.aio_sandbox:AioSandboxProvider"* ]]; then
        if [ -n "$provisioner_url" ]; then
            echo "provisioner"
        else
            echo "aio"
        fi
    else
        echo "local"
    fi
}

# ── down ──────────────────────────────────────────────────────────────────────

if [ "$CMD" = "down" ]; then
    # Set minimal env var defaults so docker compose can parse the file without
    # warning about unset variables that appear in volume specs.
    export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"
    export DEER_FLOW_CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-$DEER_FLOW_HOME/config.yaml}"
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-$DEER_FLOW_HOME/extensions_config.json}"
    export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$REPO_ROOT}"
    export BETTER_AUTH_SECRET="${BETTER_AUTH_SECRET:-placeholder}"
    export DEER_FLOW_INTERNAL_AUTH_TOKEN="${DEER_FLOW_INTERNAL_AUTH_TOKEN:-placeholder}"
    export POSTGRES_USER="${POSTGRES_USER:-placeholder}"
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-placeholder}"
    export POSTGRES_DB="${POSTGRES_DB:-placeholder}"
    export DATABASE_URL="${DATABASE_URL:-postgresql://placeholder:placeholder@postgres:5432/placeholder}"
    export KNOWLEDGE_DATABASE_URL="${KNOWLEDGE_DATABASE_URL:-postgresql://placeholder:placeholder@postgres:5432/placeholder}"
    "${COMPOSE_CMD[@]}" down
    exit 0
fi

# ── build ────────────────────────────────────────────────────────────────────
# Build produces mode-agnostic images. No --gateway or sandbox detection needed.

if [ "$CMD" = "build" ]; then
    echo "=========================================="
    echo "  DeerFlow — Building Images"
    echo "=========================================="
    echo ""

    "${COMPOSE_CMD[@]}" build

    echo ""
    echo "=========================================="
    echo "  ✓ Images built successfully"
    echo "=========================================="
    echo ""
    echo "  Next: deploy.sh start"
    echo ""
    exit 0
fi

# ── Banner ────────────────────────────────────────────────────────────────────

echo "=========================================="
echo "  DeerFlow Production Deployment"
echo "=========================================="
echo ""

# ── Detect runtime configuration ────────────────────────────────────────────
# Only needed for start / up — determines whether provisioner is launched.

sandbox_mode="$(detect_sandbox_mode)"
echo -e "${BLUE}Sandbox mode: $sandbox_mode${NC}"

echo -e "${BLUE}Runtime: Gateway embedded agent runtime${NC}"

long_services="postgres gateway knowledge-worker frontend nginx"
build_services="knowledge-migrate gateway knowledge-worker frontend"

if [ "$sandbox_mode" = "provisioner" ]; then
    long_services="$long_services provisioner"
    build_services="$build_services provisioner"
fi

# ── DEER_FLOW_DOCKER_SOCKET (aio / pure-DooD mode only) ──────────────────────
# Only aio mode (AioSandboxProvider without provisioner_url) needs the host
# Docker socket. It is mounted via the opt-in docker-compose.dood.yaml overlay,
# appended here, so the default (local) and provisioner modes never expose the
# host daemon. Mounting the socket = root-equivalent host control; see SECURITY.md.

if [ -z "$DEER_FLOW_DOCKER_SOCKET" ]; then
    export DEER_FLOW_DOCKER_SOCKET="/var/run/docker.sock"
fi

if [ "$sandbox_mode" = "aio" ]; then
    if [ ! -S "$DEER_FLOW_DOCKER_SOCKET" ]; then
        echo -e "${RED}⚠ Docker socket not found at $DEER_FLOW_DOCKER_SOCKET${NC}"
        echo "  AioSandboxProvider (DooD) will not work."
        exit 1
    fi
    echo -e "${GREEN}✓ Docker socket: $DEER_FLOW_DOCKER_SOCKET${NC}"
    echo -e "${YELLOW}  Mounting host Docker socket into gateway (DooD = host root-equivalent). See SECURITY.md.${NC}"
    COMPOSE_CMD+=(-f "$DOCKER_DIR/docker-compose.dood.yaml")
fi

echo ""

if [ "$CMD" = "status" ]; then
    # shellcheck disable=SC2086
    "${COMPOSE_CMD[@]}" ps $long_services
    exit 0
fi

if [ "$CMD" = "restart" ]; then
    # shellcheck disable=SC2086
    "${COMPOSE_CMD[@]}" restart $long_services
    exit 0
fi

# ── Start / Up ───────────────────────────────────────────────────────────────

if [ "$CMD" != "start" ]; then
    echo "Building images..."
    echo ""
    # shellcheck disable=SC2086
    "${COMPOSE_CMD[@]}" build $build_services
fi

echo "Starting PostgreSQL and waiting for health..."
echo ""
"${COMPOSE_CMD[@]}" up -d --wait postgres

echo ""
echo "Running Knowledge database migrations..."
echo ""
"${COMPOSE_CMD[@]}" run --rm knowledge-migrate

echo ""
echo "Starting long-running services..."
echo ""
# shellcheck disable=SC2086
"${COMPOSE_CMD[@]}" up -d --remove-orphans $long_services

echo ""
echo "=========================================="
echo "  DeerFlow is running!"
echo "=========================================="
echo ""
echo "  🌐 Application: http://localhost:${PORT:-2026}"
echo "  📡 API Gateway: http://localhost:${PORT:-2026}/api/*"
echo "  🤖 Runtime:     Gateway embedded"
echo "  API:            /api/langgraph/* → Gateway"
echo ""
echo "  Manage:"
echo "    make down        — stop and remove containers"
echo "    make docker-logs — view logs"
echo ""
