UI_DIR := hubspace/ui

.PHONY: build-ui build test clean

# Build the web UI (hubspace/ui) into hubspace/static/. Requires Node + npm.
# Only needed by developers editing the UI, or by CI before packaging — plain
# `pip install .` from a published wheel/sdist already carries the built output.
build-ui:
	cd $(UI_DIR) && npm install --prefer-offline --no-audit --no-fund && npm run build

# Full package build: fresh UI first, then the stdlib-only Python wheel + sdist.
build: build-ui
	python3 -m build

test:
	python3 tests/run_tests.py

clean:
	rm -rf $(UI_DIR)/node_modules $(UI_DIR)/dist
	rm -f hubspace/static/hub.js hubspace/static/hub.css \
	      hubspace/static/draw.js hubspace/static/draw.css \
	      hubspace/static/chunk-*.js
