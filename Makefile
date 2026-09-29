# Versions pinned in one place; CI reads them from here.
KPS_CHART_VERSION ?= 75.0.0
PROMETHEUS_VERSION ?= 3.1.0
KUBECONFORM_VERSION ?= 0.6.7
TRIVY_VERSION ?= 0.74.0
K8S_VERSION ?= 1.31.0
CLUSTER ?= sre-lab
IMAGE ?= orders-api:local

SHELL := /bin/bash
.SHELLFLAGS := -eo pipefail -c

CRD_SCHEMAS := https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json
RULES_OUT := observability/tests/generated/orders-api.rules.yml

.PHONY: help test test-rules lint-k8s tf-check scan-image scan-config up build deploy load e2e down print-%

help: ## Show targets
	@grep -E '^[a-zA-Z_%-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

test: ## Unit tests and lint for the app
	cd app && ruff check . && ruff format --check . && pytest -q

test-rules: ## promtool check + unit test the SLO alert rules
	python3 scripts/extract_rules.py k8s/base/prometheusrule.yaml $(RULES_OUT)
	promtool check rules $(RULES_OUT)
	promtool test rules observability/tests/slo_alerts_test.yml

lint-k8s: ## Render kustomize and validate against Kubernetes + CRD schemas
	kubectl kustomize k8s/overlays/local | kubeconform -strict -summary \
	  -kubernetes-version $(K8S_VERSION) -schema-location default -schema-location '$(CRD_SCHEMAS)'
	kubectl kustomize k8s/alert-sink | kubeconform -strict -summary -kubernetes-version $(K8S_VERSION)
	kubeconform -strict -summary -kubernetes-version $(K8S_VERSION) k8s/tools/

scan-image: ## Trivy: fail on fixable CRITICAL/HIGH CVEs in the app image
	trivy image --ignore-unfixed --severity CRITICAL,HIGH --exit-code 1 --no-progress $(IMAGE)

scan-config: ## Trivy: fail on HIGH/CRITICAL misconfigurations in Kubernetes manifests
	trivy config --severity CRITICAL,HIGH --exit-code 1 --no-progress k8s
	@echo "--- terraform (advisory) ---"
	trivy config --severity CRITICAL,HIGH --exit-code 0 --no-progress terraform

tf-check: ## terraform fmt + validate every environment
	terraform fmt -check -recursive terraform
	for env in local aws; do \
	  terraform -chdir=terraform/envs/$$env init -backend=false -input=false >/dev/null && \
	  terraform -chdir=terraform/envs/$$env validate || exit 1; \
	done

up: ## Create the kind cluster and monitoring stack with Terraform
	terraform -chdir=terraform/envs/local init -input=false
	terraform -chdir=terraform/envs/local apply -auto-approve

build: ## Build the app image and load it into kind
	docker build -t $(IMAGE) --build-arg APP_VERSION=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) app
	kind load docker-image $(IMAGE) --name $(CLUSTER)

deploy: ## Deploy orders-api, dashboard, SLO rules and the alert-sink webhook receiver
	kubectl apply -k k8s/alert-sink
	kubectl apply -k k8s/overlays/local
	kubectl -n monitoring rollout status deployment/alert-sink --timeout=180s
	kubectl -n orders rollout status deployment/orders-api --timeout=180s

load: ## Start synthetic traffic
	kubectl apply -f k8s/tools/loadgen-job.yaml

e2e: ## Run end to end checks, including the game day alert check
	python3 scripts/e2e_check.py

down: ## Delete the kind cluster
	terraform -chdir=terraform/envs/local destroy -auto-approve

print-%: ## Print a variable (used by CI)
	@echo $($*)
