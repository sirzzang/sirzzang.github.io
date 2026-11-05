#!/usr/bin/env bash
# kind 클러스터에 Coder를 올린다. KUBECONFIG로 실험 클러스터를 지정한다.
set -euo pipefail
cd "$(dirname "$0")"
kubectl create namespace coder
kubectl -n coder apply -f postgres.yaml
kubectl -n coder rollout status deploy/postgres --timeout=180s
helm install coder coder --repo https://helm.coder.com/v2 --version 2.36.0 \
  --namespace coder --values values.yaml --wait --timeout 5m
kubectl -n coder get pods
