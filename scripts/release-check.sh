#!/usr/bin/env bash
# Local release proof: build the bundle and wheel, install the wheel in a throwaway HOME, smoke-test it.
# Publishes nothing and reads no real Claude data. Leaves dist/ (wheel + SHA256SUMS) for `uv publish`.
set -euo pipefail

cd "$(dirname "$0")/.."
root=$PWD
tmp=$(mktemp -d)
server_pid=""
cleanup() {
  [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true
  rm -rf "$tmp" "$root/frontend/node_modules" "$root/src/constellation/static"
}
trap cleanup EXIT

fail() { echo "release-check FAILED: $*" >&2; exit 1; }

[ -z "$(git status --porcelain)" ] || fail "working tree is dirty; commit or stash first"

echo "== frontend bundle"
npm --prefix frontend ci
npm --prefix frontend run build
[ -f src/constellation/static/index.html ] || fail "src/constellation/static/index.html missing after the frontend build"

echo "== wheel"
rm -rf dist
uv build
wheels=(dist/*.whl)
[ "${#wheels[@]}" -eq 1 ] || fail "expected exactly one wheel in dist/"
wheel=${wheels[0]}
listing=$(unzip -Z1 "$wheel")
for need in constellation/static/index.html constellation/demo/demo.json; do
  grep -qx "$need" <<<"$listing" || fail "wheel is missing $need"
done
if grep -E '(^|/)(tests/|\.env|constellation\.json$)|\.sqlite$' <<<"$listing"; then
  fail "wheel contains files that must never ship (listed above)"
fi

echo "== clean install in a temp HOME"
export HOME=$tmp UV_TOOL_DIR=$tmp/tools UV_TOOL_BIN_DIR=$tmp/bin XDG_CACHE_HOME=$tmp/cache
export PATH=$tmp/bin:$PATH
uv tool install "$root/$wheel"
constellation --help >/dev/null
constellation --version
# `doctor --env` arrives with a later slice (install-and-cli S4); add it here when it exists.

echo "== open demo smoke test"
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
constellation open demo --no-browser --port "$port" >"$tmp/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$port/" >/dev/null && ok=1 && break
  kill -0 "$server_pid" 2>/dev/null || { cat "$tmp/server.log" >&2; fail "demo server exited early"; }
  sleep 0.5
done
[ "${ok:-}" = 1 ] || { cat "$tmp/server.log" >&2; fail "demo server did not answer on port $port within 20s"; }
kill "$server_pid"; wait "$server_pid" 2>/dev/null || true; server_pid=""

echo "== checksums"
(cd dist && shasum -a 256 -- *.whl *.tar.gz > SHA256SUMS && cat SHA256SUMS)
echo "release-check OK"
