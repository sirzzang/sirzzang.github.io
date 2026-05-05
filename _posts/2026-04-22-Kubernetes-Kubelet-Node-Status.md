---
title:  "[Kubernetes] kubelet의 노드 상태 보고 구조"
excerpt: "kubelet이 노드 상태를 API server에 보고하는 원리에 대해 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - kubelet
  - Node
  - NodeStatus
  - Lease
  - Node Controller
---

<br>

# 개요

`kubectl get nodes`를 실행하면 각 노드의 `STATUS`가 `Ready`인지, CPU와 메모리는 얼마나 있는지, 어떤 컨테이너 이미지가 캐시되어 있는지 등을 확인할 수 있다. 이 정보는 어디에서 오는 걸까?

답은 **kubelet**이다. 각 노드에서 실행되는 kubelet은 자신의 노드 상태를 수집하여 **API server에 직접 PATCH**한다. kubelet이 API server에 접근할 때는 [kubeconfig]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %})를 사용한다. Node Controller나 Scheduler는 이 데이터를 **읽기만** 할 뿐, 보고를 받는 주체가 아니다.

```text
kubelet  →  API server (Node .status PATCH)  →  etcd 저장
                                                    ↑ (읽기)
                                    Node Controller (health 판단)
                                    Scheduler (스케줄링 결정)
```

이 글에서는 kubelet이 노드 상태를 보고하는 구조를 살펴본다. Node `.status`의 구조, 상태 수집과 보고 흐름, Node Controller와의 관계, 보고 관련 설정, 그리고 Lease 기반 최적화까지 다룬다.

<br>

# Node `.status` 구조

## `spec` vs `status` 패턴

Kubernetes 리소스의 `.spec`과 `.status`는 각각 다른 역할을 한다.

- **`.spec`**: **desired state**. 사용자나 상위 컨트롤러가 "이렇게 되길 원한다"고 선언하는 부분이다.
- **`.status`**: **observed state**. 에이전트나 컨트롤러가 "지금 실제로 이렇게 보인다"고 보고하는 부분이다.

이 **spec / status 분리**는 Pod, Deployment, Service 등 대부분의 Kubernetes 리소스에 동일하게 적용된다.

## Node에서의 적용

Node 리소스에도 같은 패턴이 적용된다. Node는 `core/v1` API(`apiVersion: v1`, `kind: Node`)에 속하고, `.spec`과 `.status`는 각각 다른 Go 타입으로 정의된다.

| 부분 | 누가 작성 | 정의 타입 |
|------|-----------|-----------|
| `.spec` | 사용자, 컨트롤러 (taints, `podCIDR`, `unschedulable` 등) | `NodeSpec` |
| `.status` | **kubelet** (이 필드의 유일한 writer) | `NodeStatus` |

Node가 다른 리소스와 다른 점은 **`.status`의 writer가 클러스터 안의 컨트롤러가 아니라, 해당 노드에서 돌아가는 kubelet**이라는 것이다.

## `NodeStatus` 스키마

`.status`는 Kubernetes가 정의한 `NodeStatus` 타입을 따른다. 핵심 필드를 발췌하면 다음과 같다.

```go
// k8s.io/api/core/v1/types.go (발췌)
type NodeStatus struct {
    Capacity        ResourceList
    Allocatable     ResourceList
    Conditions      []NodeCondition
    Addresses       []NodeAddress
    DaemonEndpoints NodeDaemonEndpoints
    NodeInfo        NodeSystemInfo
    Images          []ContainerImage
    // ...
}

type ContainerImage struct {
    Names     []string
    SizeBytes int64
}
```

`kubectl get node <이름> -o json`으로 보이는 `.status` 트리가 곧 이 스키마의 직렬화(serialization) 결과이고, kubelet은 이 형태에 맞춰 채운 뒤 API server에 PATCH한다.

## 주요 필드 요약

| 필드 | 내용 |
|------|------|
| `.status.conditions` | Ready, MemoryPressure, DiskPressure, PIDPressure 등 [노드 상태 조건](https://kubernetes.io/docs/reference/node/node-status/#condition) |
| `.status.capacity` / `.allocatable` | CPU, 메모리, GPU 등 스케줄링에 쓰이는 리소스 |
| `.status.images[]` | 노드에 캐시된 컨테이너 이미지 목록 |
| `.status.nodeInfo` | OS, 커널 버전, kubelet 버전, container runtime 버전 |
| `.status.addresses` | InternalIP, Hostname 등 |
| `.status.daemonEndpoints` | kubelet이 노출하는 포트 등 |

`.status.conditions`의 JSON 예시를 보면 다음과 같다.

```json
{
  "conditions": [
    {
      "type": "Ready",
      "status": "True",
      "lastHeartbeatTime": "2026-04-21T00:00:00Z",
      "lastTransitionTime": "2026-04-20T12:00:00Z",
      "reason": "KubeletReady",
      "message": "kubelet is posting ready status."
    },
    {
      "type": "MemoryPressure",
      "status": "False",
      "reason": "KubeletHasSufficientMemory",
      "message": "kubelet has sufficient memory available."
    }
  ]
}
```

각 condition에는 `lastHeartbeatTime`(마지막으로 해당 조건이 갱신된 시각)과 `lastTransitionTime`(상태가 마지막으로 변경된 시각)이 기록된다. Node Controller는 이 시각 정보를 보고 노드의 health를 판단한다.

<br>

# 상태 수집과 보고 흐름

## kubelet은 stateless에 가깝다

kubelet은 `.status`를 **로컬 디스크에 별도로 영속화하지 않는다**. 설정된 주기마다(기본 10초) 그때그때 수집하여 메모리에 조립한 뒤, API server에 PATCH로 반영한다. 장기 저장은 etcd(API server 경유)가 담당하고, kubelet 쪽은 stateless에 가깝다.

## 한 주기 안에서의 흐름

kubelet의 상태 보고는 한 주기 안에서 다음 세 단계로 이루어진다.

**1단계: 각 setter/gatherer가 정보를 수집한다.**

| 수집 대상 | 정보 소스 | 수집 방식 |
|-----------|-----------|-----------|
| images | CRI(Container Runtime Interface) 런타임 (containerd 등) | `ListImages` 등 CRI RPC로 캐시된 이미지 메타데이터 수집 |
| conditions | 시스템 메트릭 | cgroup, `/proc` 등에서 메모리/디스크/PID 압박(pressure) 여부 판단 |
| capacity / allocatable | 하드웨어 정보 | cgroup, sysfs 등에서 CPU, 메모리, 확장 리소스(GPU 등) 읽기 |
| nodeInfo | OS 정보 | `/etc/os-release`, `uname` 등으로 OS, 커널, kubelet, 런타임 버전 수집 |

**2단계: `.status` 구조체를 메모리에 조립한다.**

수집된 정보를 Node 오브젝트의 `.status`에 대응하는 `NodeStatus` 구조체로 조립한다.

**3단계: 변경이 있으면 API server에 PATCH한다.**

직전에 API server에 보고한 값(또는 직전 주기의 스냅샷)과 비교하여, 의미 있는 변경이 있을 때만 PATCH를 보낸다. 변경이 없으면 PATCH를 생략할 수 있다(Lease 기반 최적화, 강제 보고 주기는 뒤에서 다룬다).

정리하면 **매번 fresh 수집 → in-memory 조립 → (필요 시) PATCH**다.

<br>

# Node Controller와의 관계

kubelet과 Node Controller는 **보고하는 쪽**과 **감시하는 쪽**으로 역할이 분리되어 있다. 이 구도를 먼저 이해해야 이후의 설정과 Lease 최적화를 잘 이해할 수 있다.

| 역할 | 주체 | 동작 |
|------|------|------|
| 상태 보고 | kubelet | 자기 노드의 `.status`를 API server에 직접 PATCH |
| 상태 감시 | Node Controller | 모든 노드의 `.status`(또는 Lease)를 읽어서 health 판단 |
| NotReady 판정 | Node Controller | grace period(기본 40초) 초과 시 condition 변경 |
| Taint 추가 | Node Controller | NotReady → `node.kubernetes.io/not-ready` taint (NoSchedule/NoExecute) |
| Pod eviction(축출) | Node Controller | NoExecute taint로 인한 Pod 축출 |

kubelet은 **자기 자신만 보고**하고, Node Controller는 **전체 노드를 감시**한다. 이 분리 덕분에 kubelet이 죽더라도 Node Controller가 heartbeat 갱신이 멈춘 것을 감지하여 NotReady를 판정할 수 있다. kubelet이 스스로 "나 죽었다"고 보고하지 않아도 되는 구조다.

<br>

# 보고 관련 설정

## 보고 주기

kubelet과 kube-controller-manager에는 노드 상태 보고와 관련된 네 가지 핵심 설정이 있다. 설정 파일에서는 `KubeletConfiguration` / `KubeControllerManagerConfiguration`의 **camelCase 필드명**으로, 커맨드라인에서는 대응하는 **`--kebab-case` 플래그**로 지정한다.

위 두 개는 **보고하는 쪽(kubelet)**의 설정이고, 아래 두 개는 **감시하는 쪽(Node Controller)**의 설정이다.

| 설정 파일 필드 | 대응 플래그 | 적용 위치 | 기본값 | 의미 |
|---------------|-------------|-----------|--------|------|
| `nodeStatusUpdateFrequency` | `--node-status-update-frequency` | kubelet | **10초** | kubelet이 `.status`를 API server에 PATCH하는 주기 |
| `nodeStatusReportFrequency` | `--node-status-report-frequency` | kubelet | **5분** | 변경이 없어도 강제 보고하는 주기 |
| `nodeMonitorPeriod` | `--node-monitor-period` | kube-controller-manager | **5초** | Node Controller가 노드 상태를 확인(polling)하는 주기 |
| `nodeMonitorGracePeriod` | `--node-monitor-grace-period` | kube-controller-manager | **40초** | 이 시간 동안 보고가 없으면 NotReady 판정 |

이 설정들이 어떻게 맞물려 동작하는지 보면 다음과 같다.

1. kubelet은 **10초마다** 노드 상태를 수집하고, 변경이 있으면 API server에 PATCH
2. 변경이 없으면 PATCH를 스킵하되, **5분마다** 강제로 한 번 보고 (stale 방지)
3. Node Controller는 **5초마다** 각 노드의 마지막 보고 시각을 확인
4. **40초** 동안 보고가 없으면 → NotReady condition 설정

크기 순으로 보면 `nodeMonitorPeriod`(5s) < `nodeStatusUpdateFrequency`(10s) < `nodeMonitorGracePeriod`(40s) < `nodeStatusReportFrequency`(5m)이다. Node Controller가 가장 자주 체크하고(5초), kubelet이 그 다음으로 자주 보고하며(10초), 40초 무응답이면 NotReady가 되는 구조다.

동일한 설정을 파일과 플래그에 동시에 지정하면, 일반적으로 **플래그가 파일 값을 덮어쓴다**. 실제 유효값을 확인하려면 둘 다 확인해야 한다.

## 이미지 보고

kubelet이 `.status.images[]`에 보고하는 이미지 목록과 관련된 설정도 있다.

| 설정 파일 필드 | 대응 플래그 | 기본값 | 의미 |
|---------------|-------------|--------|------|
| `nodeStatusMaxImages` | `--node-status-max-images` | **50** | 보고할 최대 이미지 수. 초과 시 크기가 큰 순으로 우선. **-1**이면 무제한 |
| `imageGCHighThresholdPercent` | `--image-gc-high-threshold` | 85 | 디스크 사용률이 이 값 이상이면 이미지 GC 시작 |
| `imageGCLowThresholdPercent` | `--image-gc-low-threshold` | 80 | GC 후 이 수준까지 정리 |
| `imageMinimumGCAge` | `--image-minimum-gc-age` | 2분 | 이 시간 이상 미사용된 이미지만 GC 대상 |

`nodeStatusMaxImages`의 기본값이 50이므로, 노드에 50개가 넘는 이미지가 있으면 `kubectl`로 조회할 때 일부가 누락된다. 이미지가 많은 환경에서는 50을 쉽게 초과할 수 있다. 정확한 전수 조회가 필요하면 이 값을 `-1`(무제한) 또는 충분히 큰 값으로 변경해야 한다.

## 설정 확인 방법

kubelet의 보고 주기나 이미지 설정이 실제로 어떤 값으로 동작하는지 확인하는 방법은 여러 가지가 있다.

| 방법 | 명령어 | 특징 |
|------|--------|------|
| 프로세스 인자 확인 | `ps aux \| grep kubelet` | 노드 SSH 필요. 플래그 값만 보임, config 파일 값은 따로 확인 |
| config 파일 직접 확인 | `cat /var/lib/kubelet/config.yaml` | 노드 SSH 필요. 배포 도구마다 경로가 다름 |
| ConfigMap 확인 | `kubectl get cm kubelet-config -n kube-system` | kubeadm 기반에서만 존재. RKE2, k3s 등에서는 없을 수 있음 |
| configz API | `curl .../nodes/<노드>/proxy/configz` | **가장 확실**. 현재 유효값을 반환. `kubectl proxy` 필요 |

kubelet config 파일의 위치는 배포 도구에 따라 다르다.

| 배포 도구 | config 경로 |
|-----------|-------------|
| kubeadm | `/var/lib/kubelet/config.yaml` |
| RKE2 | `--config-dir` 디렉토리 아래 조각 파일 (예: `/var/lib/rancher/rke2/agent/etc/kubelet.conf.d/`) |
| k3s | `/var/lib/rancher/k3s/agent/etc/kubelet.conf` |

`ps`에서 kubelet의 `--config` 또는 `--config-dir` 플래그를 확인한 뒤 해당 경로를 따라가면 된다.

이 중 **configz API가 가장 확실**하다. configz는 kubelet이 API server의 node proxy로 노출하는 **현재 유효 설정(effective configuration)**이다. config 파일과 플래그가 동시에 존재할 때, 플래그가 파일 값을 덮어쓰는 경우가 있는데, configz는 이런 우선순위가 모두 적용된 최종 결과를 보여준다.

```bash
# configz API 호출 (kubectl proxy 필요)
kubectl proxy --port=18001 &
curl http://127.0.0.1:18001/api/v1/nodes/<노드명>/proxy/configz | jq .
```

<details markdown="1">
<summary><b>configz 출력 예시 (보고 관련 필드 발췌)</b></summary>

```json
{
  "kubeletconfig": {
    "nodeStatusUpdateFrequency": "10s",
    "nodeStatusReportFrequency": "5m0s",
    "nodeLeaseDurationSeconds": 40,
    "nodeStatusMaxImages": 50,
    "imageGCHighThresholdPercent": 85,
    "imageGCLowThresholdPercent": 80,
    "imageMinimumGCAge": "2m0s",
    "syncFrequency": "30s",
    "fileCheckFrequency": "5s"
  }
}
```

</details>

예를 들어, config 파일에 `syncFrequency: 1m0s`라고 적혀 있더라도 프로세스 인자로 `--sync-frequency=30s`가 지정되어 있으면, configz에는 `30s`가 나온다. 이처럼 **configz가 "실제 유효값"을 보여주므로**, 배포 도구와 관계없이 가장 확실한 확인 방법이다.

<br>

# Lease 기반 최적화

## 기존 방식의 문제

Kubernetes 1.14 이전에는 kubelet이 **10초마다 Node `.status` 전체를 PATCH**했다. `.status`에는 conditions, images 배열(이미지 50개 x names + sizeBytes), capacity, allocatable, nodeInfo, addresses 등이 모두 포함되어 있어 **한 번의 PATCH가 수 KB에서 이미지가 많으면 수십 KB**에 달한다. 노드 수가 수백~수천 대인 클러스터에서는 이 PATCH가 **etcd write throughput과 API server 처리량에 직접적인 부담**이 된다.

## Lease란

Lease는 Kubernetes의 `coordination.k8s.io/v1` API 그룹에 속하는 리소스로, 본래 분산 시스템의 **리스(lease) / 잠금(lock)** 메커니즘을 위해 설계되었다. 노드 heartbeat 용도에서는 각 노드마다 `kube-node-lease` 네임스페이스에 Lease 오브젝트가 하나씩 존재하며, kubelet이 이 오브젝트의 `renewTime` 필드를 주기적으로 갱신한다.

```yaml
# kubectl get lease -n kube-node-lease <노드명> -o yaml
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: worker-node-01
  namespace: kube-node-lease
spec:
  holderIdentity: worker-node-01
  leaseDurationSeconds: 40
  renewTime: "2026-04-22T10:00:00.000000Z"  # kubelet이 갱신하는 유일한 필드
```

Lease 오브젝트 전체가 **수백 바이트**에 불과하다. 갱신할 때도 `renewTime` 타임스탬프 하나만 바뀌므로, etcd에 쓰는 데이터양이 Node `.status` PATCH와 비교하면 극히 작다.

## 핵심: 빈도가 아니라 크기 분리

Lease 최적화는 heartbeat **빈도를 줄이는 것이 아니다**. 10초마다 한 번이라는 빈도는 동일하다. 핵심은 **"자주 쓰는 것은 가볍게, 무거운 것은 드물게"** 분리한 것이다.

| 무엇을 | 어떻게 | 주기 | 관련 설정 | 크기 |
|--------|--------|------|-----------|------|
| liveness (살아 있는가) | Lease `renewTime` 갱신 | 10초 | `nodeStatusUpdateFrequency` | **수백 바이트** |
| status (상태가 변했는가) | Node `.status` 전체 PATCH | 변경 시, 또는 5분마다 강제 | `nodeStatusReportFrequency` | **수 KB ~ 수십 KB** |
| health 판단 | Node Controller가 Lease 갱신 시각 확인 | 5초 | `nodeMonitorPeriod` | (읽기) |
| NotReady 판정 | Lease 갱신이 멈춘 지 40초 경과 | - | `nodeMonitorGracePeriod` | - |

1.14 이전과 비교하면 다음과 같다.

| 구분 | 1.14 이전 | 1.14 이후 (Lease) |
|------|-----------|-------------------|
| 10초마다 하는 일 | Node `.status` 전체 PATCH (수 KB~수십 KB) | Lease `renewTime` 갱신 (수백 바이트) |
| Node `.status` PATCH | 10초마다 매번 | 변경 시 + 5분마다 강제만 |
| Node Controller의 liveness 판단 기준 | `.status.conditions[].lastHeartbeatTime` | Lease `renewTime` |

노드 1,000대 클러스터를 기준으로 단순 계산하면, 10초마다 etcd에 쓰는 양이 **~10KB x 1,000 = ~10MB** (이전)에서 **~0.3KB x 1,000 = ~300KB** (Lease)로 줄어든다. 무거운 `.status` PATCH는 5분에 한 번으로 빈도가 낮아지므로, 전체적인 etcd/API server 부하가 크게 감소한다.

이 최적화의 설계 배경은 KEP(Kubernetes Enhancement Proposal) [KEP-589: Efficient Node Heartbeats](https://github.com/kubernetes/enhancements/tree/master/keps/sig-node/589-efficient-node-heartbeats)에서 확인할 수 있다. 이전 자료에서는 **KEP-0009**로 인용되기도 한다.

<br>

# 정리

kubelet의 노드 상태 보고 구조를 요약하면 다음과 같다.

1. kubelet은 자기 노드의 `.status`를 **API server에 직접 PATCH**한다(보고). Node Controller는 이 데이터를 읽어서 health를 판단한다(감시).
2. Node `.status`는 `NodeStatus` 스키마를 따르며, conditions, capacity/allocatable, images, nodeInfo 등을 포함한다.
3. kubelet은 매 주기(기본 10초) **fresh 수집 → in-memory 조립 → 변경 시 PATCH**하는 stateless 구조다.
4. 보고 관련 설정은 보고 주기(4개), 이미지 보고(`nodeStatusMaxImages` 등)로 나뉘며, configz API로 실제 유효값을 확인할 수 있다.
5. Kubernetes 1.14+부터 **Lease 기반 최적화**로, 자주 쓰는 heartbeat는 경량 Lease로, 무거운 `.status` PATCH는 변경 시 + 5분 강제로 분리했다.
6. kubelet이 죽으면 Lease 갱신이 멈추고, Node Controller가 grace period(40초) 후 **NotReady**를 판정한다.

<br>

# 참고 링크

- [Node Status - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/node/node-status/)
- [Node Heartbeats - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/node/node-status/#heartbeats)
- [Node Controller - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/architecture/nodes/#node-controller)
- [Kubelet Configuration (v1beta1) - Kubernetes API Reference](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/)
- [Container Image Garbage Collection - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/architecture/garbage-collection/#container-image-garbage-collection)
- [KEP-589: Efficient Node Heartbeats](https://github.com/kubernetes/enhancements/tree/master/keps/sig-node/589-efficient-node-heartbeats)

<br>
