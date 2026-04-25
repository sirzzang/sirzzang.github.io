---
title: "[Kubernetes] Container Runtime CLI 없는 노드에서 이미지 조회하기"
excerpt: "워커 노드에 docker/crictl/ctr이 없어도 kubectl API로 이미지를 조회할 수 있다. kubelet의 노드 상태 보고를 활용하는 방법을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - kubectl
  - kubelet
  - containerd
  - container-runtime
  - on-premise
  - jq
---

<br>

# TL;DR

- 워커 노드에는 docker, crictl, ctr 같은 컨테이너 런타임 CLI가 없을 수 있다. kubelet + containerd만으로 노드는 정상 동작하므로, CLI 미설치는 비정상이 아니라 최소 구성이다
- kubelet이 API server에 보고하는 Node `.status.images[]`를 `kubectl get node -o json`으로 조회하면 추가 설치 없이 노드의 이미지 목록을 확인할 수 있다
- 출력이 docker images / crictl images와 달리 읽기 어렵지만, jq 후처리로 가독성을 확보할 수 있다
- `kubectl debug node` + chroot로 상세 조회도 가능하지만, 일상적 용도에는 과하다

<br>

# 배경

온프레미스 Kubernetes 클러스터를 운영하다 보면, 워커 노드에 컨테이너 런타임 CLI(Command Line Interface) 도구가 하나도 설치되어 있지 않은 상황을 만날 수 있다.

```bash
# 워커 노드에 SSH 접속 후 확인
$ which docker
$ docker
command not found: docker
$ which crictl
$ crictl
command not found: crictl
$ which ctr
$ ctr
command not found: ctr
```

docker, crictl, ctr 어느 것도 없다. 처음 보면 뭔가 빠진 것 같지만, 사실 이것은 비정상이 아니다. 워커 노드는 kubelet + containerd만 있으면 정상 동작하므로, 런타임 CLI가 없는 것은 최소 구성의 자연스러운 결과다.

## 왜 CLI가 없어도 되는가

워커 노드가 동작하는 데 필요한 바이너리는 다음이 전부다.

| 필수 바이너리 | 역할 |
|-------------|------|
| kubelet | CRI를 통해 containerd와 통신 |
| containerd + shims | 컨테이너 런타임 |
| runc | OCI 런타임 |
| CNI plugins | Pod 네트워킹 |

docker, crictl, ctr은 모두 **운영자 편의 도구**이지, 노드 동작에 필요한 컴포넌트가 아니다. 각각이 없는 이유를 정리하면 다음과 같다.

1. **docker**: Kubernetes 1.24 이후 dockershim이 제거되었다. containerd를 CRI(Container Runtime Interface) 런타임으로 직접 사용하므로 Docker Engine 자체가 불필요하다.
2. **crictl**: cri-tools 별도 패키지이다. kubeadm이나 kubespray 같은 프로비저닝 도구가 기본 설치하지만, 벤더가 노드 동작에 필요한 최소한만 설치하면 빠진다.
3. **ctr**: containerd 공식 릴리스 tarball에 포함되지만, 벤더가 containerd + shim만 추출해서 배포하면 ctr 바이너리가 아예 없을 수 있다.

여기에 보안 강화 관점에서 공격 표면(attack surface)을 줄이기 위해 디버깅 도구를 의도적으로 넣지 않는 경우도 있다.

## 일반적인 클러스터 구성과의 차이

| 클러스터 유형 | 런타임 CLI 상태 |
|-------------|----------------|
| kubeadm / kubespray 구축 | crictl 기본 설치 |
| 매니지드 K8s (EKS, GKE 등) | 노드 접속 자체가 제한적, kubectl API가 표준 |
| 온프레미스 벤더 구축 | 벤더 재량에 따라 CLI 미설치 가능 |

대부분의 환경에서는 최소한 crictl 정도는 있다. 하지만 벤더 구축 클러스터에서는 이런 보장이 없으므로, 런타임 CLI 없이도 노드 이미지를 확인할 수 있는 방법을 알아 두면 유용하다.

<br>

# 방법 비교

노드에 캐시된 컨테이너 이미지를 확인하는 방법은 크게 4가지가 있다.

| 방법 | 노드 CLI 필요 | 노드 접속 필요 | 장점 | 단점 |
|------|:---:|:---:|------|------|
| kubectl get node -o json | X | X | 즉시 사용 가능 | 상세 레이어 정보 없음, kubelet 보고 주기에 의존 |
| kubectl debug node + chroot | △ | X | 실시간 정확, 상세 정보 | 디버그 Pod 생성/삭제 필요, 호스트에 ctr 필요 |
| SSH + ctr | O | O | 가장 상세 (레이어, 언팩 상태) | ctr 미설치 시 불가 |
| SSH 소켓 포워딩 | X | O | 로컬 도구 활용 가능 | 설정 번거로움, 로컬에도 ctr 필요 |

## 선택: kubectl get node -o json

런타임 CLI가 없는 환경에서는 `kubectl get node -o json`이 가장 실용적이다.

- SSH 기반 방법(ctr, 소켓 포워딩)은 **노드 접속**이 필요하고, ctr이 없으면 불가하다
- `kubectl debug node`는 호스트에 ctr이 있어야 하고, 매번 디버그 Pod을 생성/삭제해야 하므로 **일상적 조회에 부적합**하다
- `kubectl get node -o json`은 노드 접속도 CLI도 필요 없이 **즉시 사용 가능**하다

이 방법은 kubelet이 API server에 보고하는 Node 리소스의 `.status` 필드를 그대로 읽는 것이다. 원리를 좀 더 살펴보자.

<br>

# 핵심 원리: kubelet의 노드 상태 보고

kubelet은 자신이 관리하는 노드의 상태를 주기적으로 API server의 `Node` 리소스 `.status`에 PATCH로 보고한다. 이 보고에는 노드에 캐시된 컨테이너 이미지 목록(`.status.images[]`)이 포함된다. 보고 구조와 주기, Lease 최적화 등 상세한 내용은 [kubelet의 노드 상태 보고 구조]({% post_url 2026-04-22-Kubernetes-Kubelet-Node-Status %})를 참고하자.

```text
containerd ←(ListImages)── kubelet ──(PATCH)→ API server (Node .status.images[])
```

런타임 CLI 없이도 이 보고 경로를 따라 `kubectl`로 이미지 목록을 조회할 수 있다.

## 출력 형식의 차이

그런데 이 방법은 docker images나 crictl images와 출력 형식이 상당히 다르다.

```bash
# docker images / crictl images의 출력
# → containerd 메타데이터(content store + metadata DB)를 직접 파싱
# → REPOSITORY, TAG, IMAGE ID, SIZE를 별도 컬럼으로 분리
REPOSITORY                                TAG       IMAGE ID     SIZE
harbor.example.com/my-project/training    a2a8e35   d4f7b2c1e9   10.1GB
```

```json
// kubelet .status.images[]의 보고 형식
// → containerd에 이미지 목록만 질의하고, reference 문자열을 그대로 전달
// → 태그/digest/repo 파싱 없이 names 배열 + sizeBytes만 제공
{
  "names": [
    "harbor.example.com/my-project/training@sha256:7a3e9f01bc...",
    "harbor.example.com/my-project/training:a2a8e35"
  ],
  "sizeBytes": 10789750931
}
```

왜 이런 차이가 나는지 정리하면 다음과 같다.

| 도구 | 데이터 소스 | 파싱 수준 |
|------|------------|-----------|
| docker images | Docker daemon → containerd content store | 완전 파싱 (repo/tag/digest/ID 분리, 레이어 집계) |
| crictl images | CRI API → containerd | 부분 파싱 (repo/tag/digest/size 분리) |
| kubelet status | containerd ListImages() → API server | 최소 보고 (reference 문자열 목록 + size만) |

kubelet은 이미지 관리 도구가 아니라, "이 노드에 뭐가 있는지"를 API server에 보고하는 역할이다. 사람이 읽기 좋은 형식으로 가공하지 않는다. 이건 구조적 한계다.

## 보고 특성과 주의사항

kubelet의 이미지 보고에는 몇 가지 알아둘 특성이 있다.

- **`.status.images[].names`**: 이미지 reference 문자열 목록이다. 태그가 있으면 tag reference와 digest reference가 둘 다 포함된다.
- **`.status.images[].sizeBytes`**: 디스크 사용량이다.
- **`--node-status-max-images`**: kubelet 플래그로 보고 개수를 제한할 수 있다. **기본값이 50**이므로, 이미지가 50개를 초과하면 일부만 보고된다. `-1`로 설정하면 제한 없이 전체를 보고한다.
- **태그 이동**: 새 push로 태그가 옮겨간 이미지는 digest만 남는다. 이런 이미지는 untagged로 분류된다.

특히 `--node-status-max-images` 기본값 50은 실무에서 놓치기 쉬운 부분이다. GPU 워커 노드처럼 대형 이미지가 많은 환경에서는 이미지가 누락될 수 있으므로, kubelet 설정을 확인해 두는 것이 좋다. 실제 유효값을 확인하는 방법(configz API 등)은 [kubelet의 노드 상태 보고 구조 - 이미지 보고 설정]({% post_url 2026-04-22-Kubernetes-Kubelet-Node-Status %}#이미지-보고-설정)을 참고하자.

<br>

# 사용법

## 기본: 원라이너

가장 간단한 형태는 `kubectl get node`에 jq를 붙이는 것이다.

```bash
# 특정 노드의 전체 이미지 목록 조회
kubectl get node gpu-worker-01 -o json | jq '.status.images[]'
```

필터링이 필요하면 jq의 `select`와 `test`를 조합한다.

```bash
# "training" 문자열이 포함된 이미지만 필터링
kubectl get node gpu-worker-01 -o json | \
  jq '.status.images[] | select(.names[] | test("training"))'
```

하지만 이 상태로는 names 배열과 sizeBytes가 날것 그대로 나온다. 운영 환경에서 반복적으로 쓰기에는 가독성이 부족하다.

## 개선: jq 후처리로 가독성 확보

jq(JSON 처리 CLI 도구)를 활용해 docker images 수준의 가독성에 근사하게 만들 수 있다. 핵심 아이디어는 다음과 같다.

- names 배열에서 `@sha256:` 포함 여부로 digest reference와 tag reference를 분류한다
- digest를 8자 short hash로 축약한다
- tagged 이미지와 untagged(digest-only) 이미지를 분리해서 표시한다
- 크기를 GB 단위로 변환하고, 크기 내림차순으로 정렬한다

다음은 이 로직의 핵심 부분을 발췌한 것이다. names 배열을 순회하면서 `@sha256:` 포함 여부로 tagged/untagged를 분류하고, repo/tag/digest/size를 추출한다.

```bash
# jq 유틸리티 함수: names 배열에서 tag와 digest를 분류
kubectl get node gpu-worker-01 -o json | jq -r '
  def short_digest:
    if test("@sha256:") then split("@sha256:")[1][0:8]
    else "" end;
  def repo_name:
    if test("@sha256:") then split("@sha256:")[0]
    elif test(":") then split(":")[0]
    else . end;
  def extract_tag:
    if test("@") then null
    elif test(":") then split(":")[-1]
    else null end;

  [.status.images[] |
    (.names | map(select(test("@") | not)) | first // null) as $tagged |
    (.names | map(select(test("@sha256:"))) | first // null) as $digested |
    {
      repo: (($tagged // $digested) | repo_name),
      tag: ($tagged | if . then extract_tag else null end),
      digest: ($digested | if . then short_digest else "--------" end),
      size: (.sizeBytes / 1073741824 * 100 | round / 100 | tostring + "GB"),
      sizeBytes: .sizeBytes
    }
  ] | sort_by(-.sizeBytes) | .[] |
  "\(.repo):\(.tag // "---")  \(.digest)  \(.size)"
'
```

<details markdown="1">
<summary><b>전체 jq 스크립트 (tagged/untagged 분리 출력 포함)</b></summary>

```bash
# jq로 kubelet 보고 데이터를 가독성 좋은 형태로 변환
kubectl get node gpu-worker-01 -o json | jq -r '
  def short_digest:
    if test("@sha256:") then split("@sha256:")[1][0:8]
    else "" end;
  def repo_name:
    if test("@sha256:") then split("@sha256:")[0]
    elif test(":") then split(":")[0]
    else . end;
  def extract_tag:
    if test("@") then null
    elif test(":") then split(":")[-1]
    else null end;
  def size_gb:
    . / 1073741824 * 100 | round / 100;

  def format_image:
    . as $img |
    ($img.names | map(select(test("@") | not)) | first // null) as $tagged |
    ($img.names | map(select(test("@sha256:"))) | first // null) as $digested |
    (($tagged // $digested) | repo_name) as $repo |
    ($tagged | if . then extract_tag else null end) as $tag |
    ($digested | if . then short_digest else "--------" end) as $short |
    ($img.sizeBytes | size_gb | tostring + "GB") as $size |
    {repo: $repo, tag: ($tag // null), digest: $short, size: $size, sizeBytes: $img.sizeBytes};

  [.status.images[] | format_image] | sort_by(-.sizeBytes) |
  (map(select(.tag != null))) as $tagged |
  (map(select(.tag == null))) as $untagged |
  (if ($tagged | length) > 0 then
    ["[tagged]"] +
    ($tagged | map("  \(.repo):\(.tag)  \(.digest)  \(.size)"))
  else [] end) +
  (if ($untagged | length) > 0 then
    (if ($tagged | length) > 0 then [""] else [] end) +
    ["[untagged]"] +
    ($untagged | map("  \(.repo)  \(.digest)  \(.size)"))
  else [] end) |
  .[]
'
```

</details>

실행하면 다음과 같은 출력을 얻을 수 있다.

```text
=== gpu-worker-01 (filter: training) ===
[tagged]
  harbor.example.com/my-project/training:a2a8e35  5379300c  10.05GB
  harbor.example.com/my-project/training:latest   e79bf6ea  10.05GB

[untagged]
  harbor.example.com/my-project/training  2f5c3f88  4.24GB
  harbor.example.com/my-project/training  1c757e3c  4.24GB
```

docker images의 "REPOSITORY TAG DIGEST SIZE" 레이아웃에 가장 가깝게 근사한 결과다. IMAGE ID와 digest가 정확히 동일하지는 않지만(IMAGE ID는 content-addressable manifest hash이므로), 운영 목적으로 "어떤 이미지가 어떤 태그로 얼마 크기로 있는지"를 파악하기에는 충분하다.

## 특정 이미지 빠른 검색

정규식(regular expression) 패턴으로 이미지를 검색하는 함수도 유용하다.

```bash
# zsh 함수: 정규식 패턴으로 노드 이미지 검색
node-image-find() {
  local pattern="${1:?Usage: node-image-find <pattern> [node]}"
  local node="${2:-gpu-worker-01}"
  kubectl get node "$node" -o json | \
    jq -r --arg p "$pattern" '
      .status.images[] |
      select(.names[] | test($p; "i")) |
      (.names | join(", ")) + "  (" +
        ((.sizeBytes / 1048576 | . * 10 | round / 10 | tostring) + "MB") +
      ")"
    '
}
```

```bash
# 사용 예시
node-image-find "training"                      # training 이미지 검색
node-image-find "training:(latest|a2a8e35)"     # 특정 태그 조합
node-image-find "training:a2a8e35" gpu-worker-02 # 다른 노드에서 검색
```

## 대안: kubectl debug node + chroot

상세 레이어 정보가 필요한 경우에는 `kubectl debug node`를 사용할 수 있다. 디버그 Pod을 띄운 뒤 `chroot /host`로 호스트 파일시스템에 진입하면, 호스트에 설치된 도구를 그대로 사용할 수 있다.

```bash
# 노드에 디버그 Pod(busybox 이미지)을 띄워서 호스트의 ctr로 이미지 조회
node-debug-images() {
  local node="${1:?Usage: node-debug-images <node> [filter]}"
  local filter="${2:-}"
  local cmd="ctr -n k8s.io images ls"
  [[ -n "$filter" ]] && cmd="ctr -n k8s.io images ls | grep $filter"
  kubectl debug "node/$node" -it --image=busybox \
    -- chroot /host sh -c "$cmd"
}
```

```bash
# 사용 예시
node-debug-images gpu-worker-01              # 전체 이미지 조회
node-debug-images gpu-worker-01 training     # 필터 포함
```

`kubectl debug node`는 호스트 파일시스템을 `/host`에 마운트한다. 디버그 컨테이너 자체는 `--image`로 지정한 이미지(여기서는 busybox)의 파일시스템을 루트로 사용하므로, 컨테이너 안에서 `ctr`을 직접 실행하면 바이너리도 없고 containerd 소켓(`/run/containerd/containerd.sock`)도 찾을 수 없다. `chroot /host`로 루트를 호스트 파일시스템으로 전환하면, 호스트의 바이너리와 소켓 경로를 그대로 사용할 수 있다. 호스트에 ctr이 있다면(PATH에 없더라도 바이너리가 존재하면) 이 방법으로 조회할 수 있다. 다만 디버그 Pod 생성/삭제 오버헤드가 있고, 호스트에 ctr조차 없으면 사용할 수 없으므로 일상적 조회보다는 **상세 정보가 필요할 때만** 사용하는 것이 좋다.

<br>

# 정리

## 방법별 추천 상황

| 상황 | 추천 방법 |
|------|----------|
| 일상적 이미지 확인 (태그, 크기) | `kubectl get node -o json` + jq |
| 특정 이미지 존재 여부 빠른 확인 | `kubectl get node -o json` + jq `select` |
| 상세 레이어 정보, 이미지 inspect | `kubectl debug node` + chroot |
| 노드 간 이미지 동기화 상태 비교 | `kubectl get node -o json` + diff |
| 디스크 압박 시 대형 이미지 파악 | `kubectl get node -o json` + jq (sizeBytes 필터) |

## 한계와 보완

이 방법으로 대부분의 일상적 이미지 조회를 커버할 수 있지만, 한계도 있다.

- **실시간성**: kubelet의 보고 주기에 의존하므로, 방금 pull된 이미지가 바로 보이지 않을 수 있다.
- **보고 개수 제한**: `--node-status-max-images` 기본값 50을 넘는 이미지는 누락된다. kubelet 설정을 확인하고 필요 시 조정을 요청해야 한다.
- **상세 정보 부족**: 레이어 정보, 이미지 config, manifest 상세 등은 얻을 수 없다. 이런 정보가 필요하면 `kubectl debug node` + chroot를 사용하거나, 팀에 cri-tools 설치를 요청하는 것을 검토해 볼 수 있다.

결국 런타임 CLI가 없는 환경에서도, kubelet이 API server에 보고하는 데이터를 활용하면 **추가 설치 없이** 충분히 실용적인 이미지 조회가 가능하다. 완벽하지는 않지만, "일단 돌아가는" 수준의 가시성(visibility)을 확보하는 데는 충분하다.

<br>