.PHONY: help install index eval eval-api eval-smoke dev-api dev-app build deploy clean

help:
	@echo "Documesh — Make targets"
	@echo ""
	@echo "  make index          Re-crawl all vendors and rebuild the search index"
	@echo "  make build-index    Rebuild search index only (no crawl)"
	@echo "  make verify         Run structural audit (license/attribution on all chunks)"
	@echo "  make eval           Run API eval (5 errors → doc sections, gate ≥80%)"
	@echo "  make eval-smoke     Run webmcp-evals smoke against staging (needs Chrome + WebMCP flag)"
	@echo "  make dev-api        Start API server on :8787"
	@echo "  make dev-app        Start static server on :8788"
	@echo "  make deploy         Deploy to Cloudflare (staging)"
	@echo "  make deploy-prod    Deploy to Cloudflare (production)"
	@echo "  make clean          Remove build artifacts"

install:
	@echo "No npm dependencies needed — stdlib only."

index:
	python3 indexer/fetch_docs.py
	python3 indexer/enrich_docs.py
	python3 indexer/foundation_docs.py
	python3 indexer/foundation_docs_r2.py
	python3 indexer/build_index.py
	python3 indexer/verify.py

build-index:
	python3 indexer/build_index.py

verify:
	python3 indexer/verify.py

eval:
	node worker/eval.mjs

eval-smoke:
	npx webmcp-evals smoke \
		-u "https://documesh.selatan.org" \
		-e evals/documesh-smoke.json \
		--timeout 30000 \
		--chrome-channel chrome

dev-api:
	node worker/dev-server.mjs

dev-app:
	python3 -m http.server 8788 --directory app

build:
	python3 indexer/build_index.py

deploy:
	npx wrangler deploy --env staging

deploy-prod:
	npx wrangler deploy --env production

clean:
	rm -rf .wrangler node_modules dist
