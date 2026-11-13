#!/usr/bin/env bash
# kind 클러스터 + KFP standalone 2.17.3 구성.
# 사용: KUBECONFIG=<새 파일> SHARED_DIR=<공유 디렉터리> bash setup.sh
#   KUBECONFIG  — 반드시 새 파일을 지정한다. 기존 컨텍스트를 건드리지 않는다.
#   SHARED_DIR  — 노드의 /shared 로 붙일 호스트 디렉터리. NFS 같은 공유 스토리지 대용.
set -euo pipefail
: "${KUBECONFIG:?새 kubeconfig 파일 경로를 지정한다}"
: "${SHARED_DIR:?공유 디렉터리 경로를 지정한다}"
export KUBECONFIG
CLUSTER=mlpe-w4
KFP=2.17.3
mkdir -p "$SHARED_DIR"

cat > /tmp/kind-$CLUSTER.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraMounts:
  - hostPath: $SHARED_DIR   # 호스트에서 파일을 바꾸면 노드의 /shared 에 바로 보인다
    containerPath: /shared
  extraPortMappings:
  - containerPort: 30008    # KFP UI·API (ml-pipeline-ui NodePort)
    hostPort: 30008
EOF
kind create cluster --name "$CLUSTER" --config /tmp/kind-$CLUSTER.yaml --kubeconfig "$KUBECONFIG"

# TLS를 중간에서 재서명하는 프록시가 있는 네트워크라면, 그 CA를 노드 containerd에도 믿게 한다.
# 호스트 Docker는 OS 인증서 저장소를 따르지만 kind 노드는 따로 갖고 있다.
if [ -n "${EXTRA_CA:-}" ]; then
  docker cp "$EXTRA_CA" "$CLUSTER-control-plane:/usr/local/share/ca-certificates/extra-ca.crt"
  docker exec "$CLUSTER-control-plane" sh -c 'update-ca-certificates && systemctl restart containerd'
fi

kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$KFP"
kubectl wait --for condition=established --timeout=120s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/platform-agnostic?ref=$KFP"

# metadata-writer 이미지에는 arm64 항목이 없다 → amd64 digest로 고정해 Rosetta로 실행
DIGEST=$(docker manifest inspect ghcr.io/kubeflow/kfp-metadata-writer:$KFP \
  | python3 -c 'import json,sys; m=json.load(sys.stdin)["manifests"]; print(next(x["digest"] for x in m if x["platform"]["architecture"]=="amd64"))')
C=$(kubectl -n kubeflow get deploy metadata-writer -o jsonpath='{.spec.template.spec.containers[0].name}')
kubectl -n kubeflow set image deploy/metadata-writer "$C=ghcr.io/kubeflow/kfp-metadata-writer@$DIGEST"

# UI·API를 NodePort 30008로 연다(위 extraPortMappings와 짝)
kubectl -n kubeflow patch svc ml-pipeline-ui --type merge \
  -p '{"spec":{"type":"NodePort","ports":[{"port":80,"targetPort":3000,"nodePort":30008}]}}'

kubectl -n kubeflow wait --for condition=available --timeout=900s deploy --all
kubectl -n kubeflow get deploy
