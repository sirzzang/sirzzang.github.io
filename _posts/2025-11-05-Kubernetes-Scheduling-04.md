---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 4. 스케줄러 설정과 최적화"
excerpt: "NodeResourcesFit 전략, 리소스 단편화 문제, 스케줄러 성능 튜닝, 멀티 프로필 구성을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - KubeSchedulerConfiguration
  - NodeResourcesFit
  - Bin Packing
  - GPU
  - Fragmentation
last_modified_at: 2026-10-01
---

<br>

# TL;DR

- 스케줄러 설정은 **프로세스 1개 : Configuration 1개 : Profile N개** 계층 구조를 가진다. Configuration은 글로벌 설정과 Profile 목록을 포함하며, 각 Profile이 extension point별 플러그인 구성을 담당한다.
- `KubeSchedulerConfiguration`을 통해 스케줄러의 플러그인 구성, 스코어링 전략, 성능 파라미터를 세밀하게 설정할 수 있다. `multiPoint` 필드로 플러그인을 모든 extension point에 일괄 등록하고, `*` 패턴으로 기본 플러그인을 전부 비활성화한 뒤 순서를 재배치할 수 있다.
- 설정 파일만 고쳐도 스케줄러는 다시 읽지 않는다. Static Pod 환경에서는 프로세스를 재시작시켜야 하고, 설정에 오류가 있으면 스케줄러가 기동하지 못해 신규 파드가 모두 Pending에 빠진다.
- `NodeResourcesFit` 플러그인은 세 가지 스코어링 전략을 제공한다: `LeastAllocated`(기본, 리소스 분산), `MostAllocated`(bin packing, 노드 채우기), `RequestedToCapacityRatio`(커스텀 곡선).
- GPU 등 희소 리소스는 `LeastAllocated` 전략에서 **단편화(fragmentation)** 문제가 발생하기 쉽다. 여러 노드에 GPU가 분산 배치되어, 단일 노드에서 충분한 GPU를 확보하지 못하는 상황이다. `MostAllocated` 전략으로 완화할 수 있다.
- `percentageOfNodesToScore`로 대규모 클러스터에서의 스케줄링 지연을 줄일 수 있으며, 단일 kube-scheduler에서 여러 프로필을 운영하여 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.

<br>

# 들어가며

[1편]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}), [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}), [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서 스케줄링의 개념, 프레임워크, 스케줄링 제어 설정까지 다뤘다. 이번 글에서는 **스케줄러 자체의 설정과 최적화**를 다룬다. 기준 버전은 앞 편들과 같은 v1.32다.

1. **KubeSchedulerConfiguration**: 설정 계층 구조(Configuration → Profile), 설정 전달과 적용 방법, 설정 파일 구조, 플러그인 활성화/비활성화 패턴(`multiPoint`, `*` 패턴)
2. **NodeResourcesFit 스코어링 전략**: LeastAllocated, MostAllocated, RequestedToCapacityRatio 세 전략의 동작 원리와 사용 시나리오
3. **리소스 단편화 문제**: 특히 GPU 환경에서 발생하는 단편화와 해결 방안
4. **스케줄러 성능 튜닝**: `percentageOfNodesToScore`와 대규모 클러스터 최적화
5. **멀티 프로필**: 워크로드 성격에 따라 서로 다른 스케줄링 정책을 적용하는 구성

> Extension Point의 결정권 분류, PreScore 역할, PodGroup 스케줄링 등 프레임워크 내부 동작은 [5편]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %})에서 자세히 다룬다.

<br>

# KubeSchedulerConfiguration

## 설정 계층 구조

스케줄러 설정을 이해하려면 먼저 **스케줄러 프로세스, Configuration, Profile** 세 개념의 계층 관계를 잡아야 한다.

```
Scheduler 프로세스 (kube-scheduler 바이너리)
  └── Configuration (1개)
        ├── 글로벌 설정 (leaderElection, clientConnection, parallelism 등)
        └── Profiles[] (1개 이상)
              ├── Profile "default-scheduler"
              │     └── Extension Points
              │           ├── filter: [Plugin A, Plugin B, ...]
              │           ├── score: [Plugin C (weight:2), ...]
              │           └── ...
              └── Profile "gpu-scheduler"
                    └── Extension Points
                          ├── filter: [Plugin A, Plugin E, ...]
                          └── ...
```

| 개념 | 범위 | 뭘 설정하나 |
| --- | --- | --- |
| **Configuration** | 스케줄러 프로세스 전체 | 글로벌 설정 + Profile 목록 |
| **Profile** | 하나의 `schedulerName` 단위 | 어떤 extension point에 어떤 plugin을 켜고/끄고/weight를 줄지 |

하나의 스케줄러 프로세스는 하나의 Configuration을 가지며, 그 안에 여러 Profile을 포함할 수 있다. 파드의 `spec.schedulerName`이 Profile의 `schedulerName`과 매칭되어, 같은 프로세스 안에서 서로 다른 플러그인 구성으로 스케줄링할 수 있다([1편 - 다중 스케줄러 구현 방식]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#다중-스케줄러-구현-방식) 참고).

<br>

## 설정 전달 방법

`kube-scheduler`는 별도의 바이너리로, `--config` CLI 인자를 통해 `KubeSchedulerConfiguration` 파일을 전달받는다. 실행 방식은 클러스터 구성에 따라 다르다.

| 클러스터 유형 | kube-scheduler 실행 방식 | 설정 전달 |
| --- | --- | --- |
| **kubeadm** (가장 일반적) | Static Pod (`/etc/kubernetes/manifests/kube-scheduler.yaml`) | Pod spec의 command에 `--config` 지정, hostPath로 마운트 |
| **RKE2** | Static Pod 또는 자체 관리 | `/var/lib/rancher/rke2/` 하위 경로에서 관리 |
| **systemd** | systemd unit file | `ExecStart=kube-scheduler --config ...` |

kubeadm 기준으로 Static Pod manifest는 다음과 같은 구조다.

```yaml
# /etc/kubernetes/manifests/kube-scheduler.yaml (Static Pod)
apiVersion: v1
kind: Pod
metadata:
  name: kube-scheduler
  namespace: kube-system
spec:
  containers:
  - command:
    - kube-scheduler
    - --config=/etc/kubernetes/scheduler-config.yaml  # KubeSchedulerConfiguration 파일 경로
    image: registry.k8s.io/kube-scheduler:v1.32.0
    volumeMounts:
    - mountPath: /etc/kubernetes/scheduler-config.yaml  # 컨테이너 내부 경로
      name: scheduler-config
      readOnly: true
  volumes:
  - hostPath:
      path: /etc/kubernetes/scheduler-config.yaml  # 호스트(control plane 노드) 경로
    name: scheduler-config
```

`--config`로 참조하는 파일이 바로 [아래에서 다룰](#설정-파일-구조) `KubeSchedulerConfiguration`이다.

<br>

## 설정 적용과 롤백

설정 파일을 고치는 것과 그 설정이 적용되는 것은 별개다. **`kube-scheduler`는 설정 파일을 런타임에 다시 읽지 않는다.** 프로세스를 재시작해야 반영된다.

Static Pod 환경에서는 재시작시키는 방법을 고를 때 주의할 점이 있다. **kubelet이 Static Pod을 식별하는 UID는 매니페스트 파일의 mtime이 아니라 파드 오브젝트 내용의 해시**다. 소스에서 UID를 만드는 부분이 그대로 보여 준다.

```go
// pkg/kubelet/config/common.go — applyDefaults()
hasher := md5.New()
hash.DeepHashObject(hasher, pod)   // 파드 오브젝트 내용으로 해시
fmt.Fprintf(hasher, "host:%s", nodeName)
fmt.Fprintf(hasher, "file:%s", source)
pod.UID = types.UID(hex.EncodeToString(hasher.Sum(nil)[0:]))
```

따라서 `touch`로 매니페스트의 타임스탬프만 바꾸면 kubelet이 파일 이벤트는 감지하지만 재파싱 결과가 이전과 같아 **파드가 재생성되지 않는다.** 더구나 여기서 바꾸는 것은 매니페스트가 아니라 hostPath로 마운트된 별도 설정 파일(`scheduler-config.yaml`)이므로, 매니페스트 내용은 애초에 변하지 않는다.

내용 해시를 실제로 바꾸거나 파일 자체를 없앴다 되돌리는 방법을 써야 한다.

```shell
# 방법 1: 매니페스트를 디렉토리 밖으로 옮겼다 되돌린다 (삭제 → 생성 이벤트)
~# mv /etc/kubernetes/manifests/kube-scheduler.yaml /root/
~$ kubectl get pods -n kube-system -l component=kube-scheduler   # 사라졌는지 확인
~# mv /root/kube-scheduler.yaml /etc/kubernetes/manifests/

# 방법 2: 매니페스트 내용을 바꿔 해시를 바꾼다 (annotation 추가 등)
~# sed -i 's|^  name: kube-scheduler$|  name: kube-scheduler\n  annotations:\n    reload: "'"$(date +%s)"'"|' \
     /etc/kubernetes/manifests/kube-scheduler.yaml

# 방법 3: 컨테이너를 직접 죽인다 (kubelet이 다시 띄우며 새 설정 파일을 읽는다)
~# crictl ps --name kube-scheduler -q | xargs crictl stop
```

재시작 후에는 기동 여부를 반드시 확인한다. **파드가 `Running`이라는 것만으로는 새 설정이 적용됐다는 보장이 되지 않으므로**, 컨테이너가 실제로 재시작됐는지(`RESTARTS` 또는 `started at`)를 함께 본다.

```shell
# 파드 상태와 재시작 여부를 함께 확인
~$ kubectl get pods -n kube-system -l component=kube-scheduler

# 컨테이너가 실제로 언제 시작됐는지 확인
~$ kubectl get pod -n kube-system kube-scheduler-<control-plane-node> \
    -o jsonpath='{.status.containerStatuses[0].state.running.startedAt}'

# 기동 로그 확인 (설정 파싱 오류가 있으면 여기에 나온다)
~$ kubectl logs -n kube-system kube-scheduler-<control-plane-node> --tail=50
```

설정 YAML에 오타가 있거나 존재하지 않는 플러그인 이름이 들어 있으면 **스케줄러가 기동하지 못한다.** 이때 클러스터에서 벌어지는 일은 다음과 같다.

- 이미 실행 중인 파드는 영향을 받지 않는다. 스케줄링은 배치 시점의 작업이므로, 배치가 끝난 파드는 kubelet이 계속 관리한다
- **신규 파드는 전부 Pending에 머문다.** 아무도 `spec.nodeName`을 채워 주지 않는다
- 파드가 죽고 재생성되는 워크로드도 새 파드가 뜨지 않는다

그래서 롤백 경로를 먼저 확보해 두는 편이 적절하다.

```shell
# 매니페스트 디렉토리 "밖"에 백업을 둔다
~# cp /etc/kubernetes/manifests/kube-scheduler.yaml /root/kube-scheduler.yaml.bak
~# cp /etc/kubernetes/scheduler-config.yaml /root/scheduler-config.yaml.bak

# 문제가 생기면 되돌린다
~# cp /root/kube-scheduler.yaml.bak /etc/kubernetes/manifests/kube-scheduler.yaml
```

백업 파일을 `/etc/kubernetes/manifests/` **안에** 두면 안 된다. kubelet은 그 디렉토리의 매니페스트를 전부 읽으므로, `kube-scheduler.yaml.bak`도 파드로 띄우려 시도한다. 백업은 반드시 디렉토리 밖에 둔다.

컨트롤 플레인 구성에 따라 위험도가 다르다.

| 구성 | 설정 변경 시 |
| --- | --- |
| 컨트롤 플레인 1대 | 스케줄러가 기동에 실패하면 클러스터 전체의 스케줄링이 멈춘다 |
| 컨트롤 플레인 HA (3대) | leader election으로 한 대만 활성 상태다. 한 대씩 순차 적용하면 나머지 중 하나가 리더가 되어 스케줄링이 계속된다 |

HA 환경에서는 모든 노드에 같은 설정을 적용하는 편이 적절하다. 노드별로 설정이 다르면 리더가 바뀔 때마다 스케줄링 동작이 달라진다.

> 위 절차는 kubeadm 기준 Static Pod 환경을 전제로 정리한 것이다. 관리형 컨트롤 플레인(EKS, GKE 등)은 사용자가 `kube-scheduler` 설정에 접근할 수 없는 경우가 많고, 이때는 별도 스케줄러를 배포하는 방향([5편 - 멀티 스케줄러 심화]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#멀티-스케줄러-심화))으로 가야 한다.

<br>

## 설정 파일 구조

설정 파일은 `KubeSchedulerConfiguration` API 오브젝트로, 스케줄러의 동작을 세밀하게 제어한다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration        # Configuration (전체 설정)
clientConnection:
  kubeconfig: /etc/srv/kubernetes/kube-scheduler/kubeconfig  # 글로벌 설정
profiles:                                # Profile 목록
  - schedulerName: default-scheduler     # Profile 이름 (Pod의 spec.schedulerName과 매칭)
    pluginConfig:                         # 플러그인별 상세 설정
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: LeastAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
```

주요 설정 영역은 다음과 같다.

| 영역 | 설명 |
| --- | --- |
| `profiles` | 스케줄러 프로필 목록. 각 프로필은 고유한 `schedulerName`과 플러그인 구성을 가짐 |
| `profiles[].plugins` | extension point별 플러그인 활성화/비활성화 |
| `profiles[].pluginConfig` | 플러그인별 상세 설정 (스코어링 전략, 가중치 등) |
| `percentageOfNodesToScore` | 대규모 클러스터 성능 최적화 파라미터 |

## 플러그인 활성화/비활성화

각 extension point에서 기본 플러그인을 비활성화하거나 커스텀 플러그인을 활성화할 수 있다.

```yaml
profiles:
  - schedulerName: default-scheduler
    plugins:
      score:
        disabled:
          - name: PodTopologySpread   # 기본 플러그인 하나를 끈다
        enabled:
          - name: MyCustomPlugin      # 커스텀 플러그인을 추가한다
            weight: 2
```

`enabled`로 추가한 플러그인은 기본 플러그인 **뒤에** 붙는다. 기본 플러그인 간의 순서를 바꾸거나, 커스텀 플러그인을 기본 플러그인 사이에 끼워넣으려면 [아래의 `*` 패턴](#-패턴-전체-비활성화와-순서-재배치)을 사용해야 한다.

<br>

### multiPoint

하나의 플러그인이 여러 extension point를 구현하는 경우가 많다(예: `NodeResourcesFit`은 PreFilter, Filter, PreScore, Score 네 곳에 등록된다). `multiPoint` 필드를 사용하면 해당 플러그인이 구현하는 **모든 extension point에 한 번에** 등록할 수 있다.

```yaml
profiles:
  - schedulerName: default-scheduler
    plugins:
      multiPoint:
        enabled:
          - name: NodeResourcesFit
            weight: 2
```

위 한 줄이 NodeResourcesFit을 PreFilter, Filter, PreScore, Score 네 곳에 동시에 등록한다. 플러그인이 어떤 인터페이스를 구현했는지는 스케줄러가 초기화 시점에 Go의 type assertion으로 자동 판별한다. 플러그인 구조체가 `FilterPlugin`, `ScorePlugin` 등의 인터페이스 메서드를 가지고 있으면, 해당 extension point에 자동 등록되는 구조다.

비활성화도 동일하게 동작한다.

```yaml
plugins:
  multiPoint:
    disabled:
      - name: TaintToleration  # Filter + PreScore + Score 전부에서 제거
```

K8s 기본 스케줄러 프로파일도 내부적으로 이 방식을 사용한다. v1.32 기준 18개의 기본 플러그인이 `multiPoint`로 등록되어, extension point별로 일일이 나열하지 않고도 관리된다. 전체 목록은 [2편 - 기본 플러그인과 Extension Point 매핑]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)에 있다.

<br>

### multiPoint와 개별 설정의 우선순위

`multiPoint`로 전체를 등록한 뒤, 특정 extension point에서만 오버라이드할 수 있다. **개별 extension point 설정이 multiPoint보다 우선**한다.

```yaml
plugins:
  multiPoint:
    enabled:
      - name: MyPlugin    # MyPlugin이 구현하는 모든 곳에 등록
  score:
    disabled:
      - name: MyPlugin    # 단, Score에서만은 제외
```

<br>

### `*` 패턴: 전체 비활성화와 순서 재배치

`*`를 사용하면 해당 extension point의 모든 기본 플러그인을 한꺼번에 비활성화할 수 있다.

```yaml
profiles:
  - schedulerName: no-scoring-scheduler
    plugins:
      preScore:
        disabled:
        - name: '*'      # PreScore 기본 플러그인 전부 제거
      score:
        disabled:
        - name: '*'      # Score 기본 플러그인 전부 제거 → 스코어링 생략
```

| 패턴 | 의미 |
| --- | --- |
| `disabled: [{name: '*'}]` 만 | 해당 extension point의 기본 플러그인 전부 OFF |
| `disabled: [{name: '*'}]` + `enabled: [...]` | 기본 플러그인을 전부 제거한 뒤 원하는 플러그인만 원하는 순서로 등록 |
| `enabled: [...]` 만 | 기본 플러그인은 그대로 유지하고, 그 뒤에 추가 |

**플러그인 호출 순서를 완전히 제어**하고 싶을 때, `*`로 전부 끄고 `enabled`에서 원하는 순서로 다시 나열하면 된다.

```yaml
score:
  disabled:
    - name: '*'           # 기본 플러그인 전부 제거
  enabled:                # 원하는 순서로 다시 등록
    - name: MyCustomScorer
      weight: 5
    - name: NodeResourcesFit
      weight: 2
    - name: NodeAffinity
      weight: 1
    # TaintToleration 등은 아예 안 넣음 → 비활성화
```

이 패턴은 "기본 플러그인 중 일부만 선택적으로 쓰면서 순서도 바꾸고 싶다"는 요구에 유용하다.

<br>

# NodeResourcesFit 전략과 리소스 단편화

## NodeResourcesFit 스코어링 전략

[2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-score-플러그인)에서 `NodeResourcesFit`은 Filter와 Score 양쪽에 등록되는 플러그인이라고 했다. 이 Score 단계의 동작을 결정하는 것이 **스코어링 전략(scoringStrategy)**이다. 플러그인이 각 extension point에서 무엇을 하는지는 [5편 - NodeResourcesFit]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#noderesourcesfit)에서 분해한다.

세 가지 전략이 있고, 선택 기준은 다음과 같다.

- 노드마다 여유를 남겨 부하 급증을 흡수해야 한다 → **`LeastAllocated`**(기본)
- 노드 수를 줄여 비용을 낮추거나 GPU 단편화를 막아야 한다 → **`MostAllocated`**
- 리소스별로 가중치를 다르게 주거나 사용률 구간별 선호를 따로 둬야 한다 → **`RequestedToCapacityRatio`**

| 전략 | 방향 | 점수 기준 | 주요 시나리오 |
| --- | --- | --- | --- |
| LeastAllocated | 분산 | 여유 많은 노드 선호 | 웹 서비스, 고가용성 |
| MostAllocated | 집중 (bin packing) | 사용률 높은 노드 선호 | 비용 최적화, 배치 작업 |
| RequestedToCapacityRatio | 커스텀 | 사용률-점수 곡선 정의 | GPU 워크로드, 세밀 제어 |

각 전략의 점수 공식과 계산 예시는 아래에서 다룬다.

### LeastAllocated (기본)

리소스 사용률이 **낮은** 노드에 높은 점수를 부여한다. 파드를 클러스터 전체에 **분산**시키는 방향이다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: LeastAllocated
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
```

노드별 점수는 아래 공식으로 계산된다. 노드의 전체 할당 가능 리소스(`allocatable`) 대비 배치 후 남는 여유 비율이 클수록 높은 점수를 받는다.

```
score = (allocatable - requested) / allocatable * MaxScore
```

여유가 많은 노드일수록 점수가 높다. 리소스가 여러 종류(CPU, Memory 등)인 경우, 각 리소스별 점수를 설정된 가중치로 가중 평균하여 최종 점수를 산출한다.

<details markdown="1">
<summary><b>계산 예시</b></summary>

cpu weight: 1, memory weight: 1인 상태에서 새 파드가 cpu 2, memory 256Mi를 요청한다고 가정한다.

**Node A** (여유 많음)

```
Allocatable: cpu 8, memory 16Gi
Requested:   cpu 1, memory 2Gi

cpu score   = (8 - (1+2)) / 8 * 100 = 62.5
memory score = (16Gi - (2Gi+256Mi)) / 16Gi * 100 ≈ 85.9
final score = (62.5 * 1 + 85.9 * 1) / (1 + 1) = 74.2
```

**Node B** (여유 적음)

```
Allocatable: cpu 8, memory 16Gi
Requested:   cpu 5, memory 12Gi

cpu score   = (8 - (5+2)) / 8 * 100 = 12.5
memory score = (16Gi - (12Gi+256Mi)) / 16Gi * 100 ≈ 23.4
final score = (12.5 * 1 + 23.4 * 1) / (1 + 1) = 18.0
```

Node A(74.2) > Node B(18.0)이므로, **여유가 많은 Node A가 선택**된다. 파드가 분산 배치되는 방향이다.

여기서 `Allocatable`은 노드가 파드에 할당할 수 있는 총량이고, `Requested`는 그 노드에 이미 배치된 파드들의 `requests` 합이다. 공식의 분모는 항상 `allocatable`이다.

> `requests`를 지정하지 않은 컨테이너에는 **Score 단계에 한해** 기본값(CPU 100m, memory 200Mi)이 적용된다. Filter 단계는 실제 `requests`를 그대로 쓰므로 비워 두면 0으로 계산된다. 점수 계산에서만 0이 아닌 값으로 보정된다는 뜻이다.

</details>

부하가 예측 불가능하고 급증할 수 있는 서비스(웹 서버, API 서버), 각 노드에 여유를 남겨 스파이크를 흡수해야 하는 환경, 노드 장애 시 다른 노드가 부하를 분담해야 하는 고가용성 환경에 적합하다.

다만, 모든 노드가 비슷하게 부분 점유되므로 "비어 있는 노드"가 줄어든다. Cluster Autoscaler와 함께 사용할 때 스케일 다운 대상 노드를 만들기 어렵고, GPU 등 희소 리소스에서는 단편화 문제가 발생할 수 있다.

<br>

### MostAllocated

리소스 사용률이 **높은** 노드에 높은 점수를 부여한다. 파드를 가능한 한 적은 수의 노드에 **집중 배치하는**(bin packing) 방향이다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: MostAllocated
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
```

노드별 점수는 아래 공식으로 계산된다. 배치 후 노드의 사용률(`requested / allocatable`)이 높을수록 높은 점수를 받는다. LeastAllocated와 정확히 반대 방향이다.

```
score = requested / allocatable * MaxScore
```

LeastAllocated와 마찬가지로, 리소스가 여러 종류인 경우 각 리소스별 점수를 가중 평균하여 최종 점수를 산출한다.

<details markdown="1">
<summary><b>계산 예시</b></summary>

cpu weight: 1, memory weight: 1인 상태에서 새 파드가 cpu 2, memory 256Mi를 요청한다고 가정한다. 위 LeastAllocated 예시와 동일한 노드다.

**Node A** (여유 많음)

```
Allocatable: cpu 8, memory 16Gi
Requested:   cpu 1, memory 2Gi

cpu score   = (1+2) / 8 * 100 = 37.5
memory score = (2Gi+256Mi) / 16Gi * 100 ≈ 14.1
final score = (37.5 * 1 + 14.1 * 1) / (1 + 1) = 25.8
```

**Node B** (여유 적음)

```
Allocatable: cpu 8, memory 16Gi
Requested:   cpu 5, memory 12Gi

cpu score   = (5+2) / 8 * 100 = 87.5
memory score = (12Gi+256Mi) / 16Gi * 100 ≈ 76.6
final score = (87.5 * 1 + 76.6 * 1) / (1 + 1) = 82.0
```

Node B(82.0) > Node A(25.8)이므로, **이미 많이 사용된 Node B가 선택**된다. 파드가 한 노드에 집중 배치되는 bin packing 방향이다.

</details>

노드 수에 따라 비용이 발생하는 클라우드 환경에서 비용 최적화에 유리하며, Cluster Autoscaler와 함께 사용할 때 빈 노드를 만들어 스케일 다운을 유도할 수도 있다. 배치 작업이나 ML 학습 등 일시적 워크로드, GPU 등 희소 리소스의 단편화 방지에도 적합하다.

다만, 특정 노드에 부하가 집중되므로 해당 노드 장애 시 영향 범위가 커지고, 리소스 경합(CPU throttling, OOM 등)이 발생할 가능성이 높아진다.

<br>

### RequestedToCapacityRatio

가장 세밀한 제어가 가능한 전략이다. `shape` 파라미터로 **사용률-점수 매핑 곡선**을 직접 정의한다.

```yaml
pluginConfig:
  - name: NodeResourcesFit
    args:
      scoringStrategy:
        type: RequestedToCapacityRatio
        resources:
          - name: cpu
            weight: 1
          - name: memory
            weight: 1
          - name: nvidia.com/gpu
            weight: 5
        requestedToCapacityRatio:
          shape:
            - utilization: 0
              score: 0
            - utilization: 100
              score: 10
```

`shape`의 두 점을 선형 보간하여 점수를 계산한다. 위 예시는 사용률이 높을수록 점수가 높은 bin packing 동작이다. 반대로 설정하면 LeastAllocated와 유사하게 동작한다.

```yaml
# LeastAllocated와 유사한 동작
shape:
  - utilization: 0
    score: 10
  - utilization: 100
    score: 0
```

**핵심 활용: 리소스별 가중치 차등 적용**

`RequestedToCapacityRatio`의 가장 큰 장점은 **리소스별로 가중치를 차등** 적용할 수 있다는 것이다. 예를 들어 GPU 리소스에 높은 가중치를 주어, GPU를 최우선으로 bin packing하면서 CPU/Memory는 상대적으로 덜 중요하게 취급할 수 있다.

```yaml
resources:
  - name: nvidia.com/gpu
    weight: 10
  - name: cpu
    weight: 1
  - name: memory
    weight: 1
```

<br>

## 리소스 단편화 문제

### 단편화란

리소스 단편화(fragmentation)란 클러스터 전체로 보면 리소스 여유가 있지만, 개별 노드에서는 파드의 요구를 충족하지 못하는 상태를 말한다.

예를 들어, 4-GPU 노드 3대가 있는 클러스터에서:

```
Node A: 4 GPU 중 2 GPU 사용 중 (2 여유)
Node B: 4 GPU 중 2 GPU 사용 중 (2 여유)
Node C: 4 GPU 중 2 GPU 사용 중 (2 여유)
```

클러스터 전체로는 6 GPU가 여유지만, **4 GPU를 요청하는 파드**는 스케줄링할 수 없다. 어떤 노드에도 4 GPU 여유가 없기 때문이다.

### 현재 상태 확인하기

단편화가 실제로 일어나고 있는지는 노드별 할당 현황을 봐야 알 수 있다.

```shell
# 노드 하나의 할당 현황 상세
~$ kubectl describe node <node>
```

```
# 실행 결과 (발췌)
Capacity:
  cpu:                64
  memory:             264120152Ki
  nvidia.com/gpu:     4
Allocatable:
  cpu:                63500m
  memory:             259925Mi
  nvidia.com/gpu:     4
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                12500m (19%)  24 (37%)
  memory             48Gi (18%)    96Gi (37%)
  nvidia.com/gpu     2             2
```

`Capacity`는 노드의 물리적 총량이고, `Allocatable`은 그중 파드에 할당할 수 있는 양이다. kubelet과 시스템 데몬을 위한 예약분(`--kube-reserved`, `--system-reserved`)이 빠져 있어 `Capacity`보다 작다. **스케줄러의 점수 계산에 쓰이는 분모는 `Allocatable`이다.**

`Allocated resources`의 `Requests`가 이미 배치된 파드들의 `requests` 합이다. `Allocatable - Requests`가 그 노드의 실제 여유다. 위 노드는 GPU 4개 중 2개가 할당되어 2개 여유다.

클러스터 전체의 GPU 분포를 한 번에 보려면 다음과 같이 확인한다.

```shell
# 노드별 GPU 용량 한눈에 보기
~$ kubectl get nodes -o custom-columns=\
'NAME:.metadata.name,GPU_ALLOC:.status.allocatable.nvidia\.com/gpu'
```

```
# 실행 결과
NAME       GPU_ALLOC
node-1     4
node-2     4
node-3     4
```

노드별로 몇 개가 **쓰이고 있는지**는 `allocatable`에 나오지 않는다. `kubectl describe node`의 `Allocated resources`를 노드마다 확인하거나, 파드의 GPU 요청을 노드별로 합산해야 한다.

### GPU 리소스에서 단편화가 심한 이유

CPU나 Memory와 달리, GPU는 다음과 같은 특성 때문에 단편화에 취약하다.

| 특성 | CPU/Memory | GPU |
| --- | --- | --- |
| 노드당 수량 | 수십~수백 코어, GB 단위 | 보통 2~8개 |
| 단위 크기 | 작음 (1 밀리코어, 1 MiB) | 큼 (1 GPU 단위) |
| 파드당 요청량 | 전체 대비 작은 비율 | 전체 대비 큰 비율 (1~8 GPU) |
| 분할 가능성 | 자유롭게 분할 | 정수 단위만 허용 |
| overcommit | 가능 (request < limit) | **불가** ([request == limit 강제]({% post_url 2024-07-23-Dev-Kubernetes-NVIDIA-GPU-Mechanism %}#extended-resource로서의-gpu)) |

GPU가 4개인 노드에서 GPU 1개짜리 파드 2개가 다른 노드에 분산 배치되면, GPU 4개짜리 파드는 어디에도 들어갈 수 없게 된다. **기본 전략인 `LeastAllocated`가 정확히 이 상황을 만든다**. 리소스를 고르게 분산시키므로, 모든 노드가 "부분 점유" 상태가 된다.

### 해결: MostAllocated 또는 RequestedToCapacityRatio

GPU 단편화를 줄이려면, 스코어링 전략을 bin packing 방향으로 전환하여 GPU 파드를 가능한 한 적은 수의 노드에 집중시켜야 한다. [위에서 다룬](#noderesourcesfit-스코어링-전략) 두 전략을 활용한다.

**MostAllocated로 GPU를 집중시키는 설정**

`resources`에 `nvidia.com/gpu`를 추가하고 가중치를 CPU/Memory보다 높게 설정한다. 기본 프로필의 전략만 바꾸는 경우 전체 설정은 다음과 같다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated
            resources:
              - name: nvidia.com/gpu   # GPU에 높은 가중치 → GPU bin packing 우선
                weight: 5
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
```

이 설정은 **클러스터 전체의 기본 배치 전략을 바꾼다.** GPU를 쓰지 않는 일반 워크로드도 bin packing 방향으로 배치되므로, 일반 서비스까지 특정 노드에 몰릴 수 있다. GPU 워크로드에만 적용하려면 [멀티 프로필](#멀티-프로필)로 분리하는 편이 적절하다.

**RequestedToCapacityRatio로 더 세밀하게 제어**

GPU 가중치를 CPU/Memory보다 크게(예: 10) 주고, `shape`를 사용률이 높을수록 점수가 높은 곡선으로 설정한다. 점수 계산에서 GPU가 지배적이 되어, GPU 사용률이 높은 노드를 강하게 선호한다. 사용률 구간별로 선호도를 다르게 두고 싶을 때 유리하다.

핵심은 공통적으로 **GPU 리소스의 가중치를 CPU/Memory보다 높게 설정**하여, 점수 계산에서 GPU bin packing이 우선되도록 하는 것이다.

### 단편화 방지 설계 가이드

단편화를 방지하기 위한 설계 포인트를 정리한다.

| 방법 | 설명 |
| --- | --- |
| bin packing 전략 | `MostAllocated` 또는 `RequestedToCapacityRatio`로 GPU를 집중 배치 |
| 노드 풀 분리 | GPU 노드와 일반 노드를 [taint/toleration]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#taints-and-tolerations)으로 분리하여, GPU 노드에는 GPU 워크로드만 배치 |
| 멀티 프로필 | GPU 워크로드 전용 프로필에만 bin packing 적용, 일반 워크로드는 LeastAllocated 유지 |
| 전용 스케줄러 | Volcano, Kueue 등 GPU 토폴로지 인식 스케줄러 사용 ([5편 - Volcano vs Kueue]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#volcano-vs-kueue-접근-방식의-차이)) |

이 표의 방법들은 모두 **개별 파드 하나가** 필요한 GPU를 한 노드에서 확보하게 만드는 쪽이다. 여러 파드가 **동시에** 확보되어야 작업이 시작되는 그룹 워크로드(분산 학습 등)는 문제 구조가 다르고, bin packing만으로는 해결되지 않는다. 그 경우의 스케줄링은 [5편 - PodGroup-level Extension Points]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#podgroup-level-extension-points)에서 다룬다.

주의할 점이 하나 있다. 프로필은 **배치 전략만** 바꾼다. 어떤 파드가 어떤 파드를 밀어낼 수 있는지는 프로필과 무관하게 `PriorityClass`가 결정한다([2편 - 선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#선점)). GPU 전용 프로필을 만들어도 선점 동작은 달라지지 않는다.

<br>

# 스케줄러 성능 튜닝

## percentageOfNodesToScore

대규모 클러스터에서 스케줄링 지연을 줄이기 위한 파라미터다. [2편 - Filter]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#filter)에서 설명했듯, 스케줄러는 모든 노드를 평가하지 않고 충분한 수의 적합 노드를 찾으면 Score 단계로 넘어간다. 이 "충분한 수"를 결정하는 것이 `percentageOfNodesToScore`다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
percentageOfNodesToScore: 50
```

### 기본값

명시하지 않으면 클러스터 규모에 따라 자동 계산된다. 계산식은 다음과 같다.

```
비율(%) = 50 - (전체 노드 수 / 125)     # 하한 5%
평가 노드 수 = max(전체 노드 수 * 비율, 100)
```

두 가지 하한이 동시에 걸린다. 비율은 5% 아래로 내려가지 않고, 평가 노드 수는 100개 아래로 내려가지 않는다.

| 전체 노드 수 | 계산된 비율 | 실제 평가 노드 수 |
| --- | --- | --- |
| 100 노드 이하 | — | 전체 (100노드 하한에 걸려 사실상 전량 평가) |
| 1,000 노드 | 약 42% | 약 420 |
| 5,000 노드 | 약 10% | 약 500 |
| 10,000 노드 | 5% (하한) | 약 500 |

노드 100개 이하 클러스터에서는 하한 때문에 어차피 전체 노드를 평가하므로, 이 값을 설정할 필요가 없다.

### 트레이드오프

| 값 | 스케줄링 속도 | 스케줄링 품질 |
| --- | --- | --- |
| 높음 (100%) | 느림 | 최적 (모든 노드 비교) |
| 낮음 (10~30%) | 빠름 | 차선 (일부 노드만 비교) |

공식 문서는 구체적인 권장값을 제시하지 않지만, **10% 아래로 낮추는 것은 피하라**고 명시한다. 스케줄러 throughput이 결정적으로 중요하고 노드 점수가 거의 중요하지 않은 경우가 아니라면, 배치 품질 손실이 커진다는 것이다.

적정값은 노드 수, 파드 생성 빈도, 배치 제약의 강도에 따라 달라지므로 직접 측정해 정하는 편이 적절하다. 이 글에서 값을 측정해 검증한 범위는 아니다.

### 프로필별 설정 (v1.26+)

v1.26부터는 글로벌 설정뿐만 아니라 프로필별로도 `percentageOfNodesToScore`를 설정할 수 있다. 프로필 블록 안에 같은 이름의 필드를 두면 글로벌 값을 덮어쓴다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
percentageOfNodesToScore: 50          # 글로벌 기본값
profiles:
  - schedulerName: default-scheduler
    # 글로벌 값(50)을 그대로 사용

  - schedulerName: batch-scheduler
    percentageOfNodesToScore: 10      # 이 프로필만 10%로 낮춰 처리량 우선
```

배치 워크로드처럼 처리량이 배치 품질보다 중요한 프로필에 낮은 값을 주는 식으로 활용할 수 있다.

<br>

# 멀티 프로필

[1편 - 다중 스케줄러 구현 방식]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#다중-스케줄러-구현-방식)에서 단일 kube-scheduler에서 여러 프로필을 운영할 수 있다고 했다. 여기서는 이를 활용한 구체적인 구성 예시를 다룬다.

## 워크로드 성격에 따른 프로필 분리

일반 서비스와 GPU/배치 워크로드에 서로 다른 스코어링 전략을 적용하는 예시다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  # 프로필 1: 일반 워크로드 (리소스 분산)
  - schedulerName: default-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: LeastAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1

  # 프로필 2: GPU 워크로드 (bin packing)
  - schedulerName: gpu-binpack-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
              - name: nvidia.com/gpu
                weight: 5
```

파드 배포 시 `spec.schedulerName`으로 프로필을 선택한다.

```yaml
# 일반 서비스: default-scheduler 사용 (기본값)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-service
spec:
  template:
    spec:
      containers:
        - name: web
          image: nginx
          resources:
            requests:
              cpu: 500m
              memory: 256Mi
---
# GPU 워크로드: gpu-binpack-scheduler 사용
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-training
spec:
  template:
    spec:
      schedulerName: gpu-binpack-scheduler  # 프로필 선택
      containers:
        - name: trainer
          image: ml-trainer:latest
          resources:
            requests:
              nvidia.com/gpu: 2
            limits:
              nvidia.com/gpu: 2
```

## 멀티 프로필의 제약

- 모든 프로필이 **동일한 `queueSort` 플러그인**을 사용해야 한다. 스케줄러 내부적으로 Pending 파드 큐는 하나이기 때문이다. 서로 다른 `queueSort`를 지정하면 스케줄러가 기동 시 validation 오류로 거부한다.
- 프로필별로 `schedulerName`이 **고유**해야 한다. 같은 프로세스 안에서 중복되면 기동 시 거부된다.
- `schedulerName`을 지정하지 않은 파드는 kube-apiserver가 `default-scheduler`로 채우므로, 그 이름의 프로필이 처리한다([1편 - schedulerName 지정]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %}#schedulername-지정)).

## 프로필과 Event 추적

멀티 프로필 환경에서 "어떤 프로필이 이 파드를 처리했는가"를 확인하려면 Kubernetes Event의 `reportingController` 필드를 보면 된다. 스케줄러는 이벤트 종류에 따라 다른 값을 `reportingController`에 넣는다.

| 이벤트 종류 | `reportingController` 값 | 이유 |
| --- | --- | --- |
| **파드 스케줄링** | 해당 파드의 `spec.schedulerName` | 어떤 profile이 처리했는지 추적 |
| **Leader election** | `profiles[0].schedulerName` | 프로세스 전체 대표값 필요 → 첫 번째 profile 사용 |

파드 스케줄링 이벤트의 경우, 해당 파드의 `schedulerName`이 그대로 `reportingController`에 들어간다.

```yaml
# schedulerName: gpu-scheduler인 Pod의 스케줄링 Event
apiVersion: events.k8s.io/v1
kind: Event
reportingController: gpu-scheduler   # Pod의 schedulerName이 그대로 들어감
reason: Scheduled
note: "Successfully assigned default/my-pod to node-3"
```

Leader election 이벤트는 프로세스 전체 단위의 동작이므로 특정 profile에 귀속되지 않는다. 프로세스를 대표하는 별도 이름이 없기 때문에, 관례적으로 `profiles` 배열의 **첫 번째** profile 이름을 사용한다.

디버깅 시 필드 선택자로 이벤트를 필터링하면, 어떤 프로필이 어떤 파드를 처리했는지 빠르게 확인할 수 있다. 여기서 주의할 점이 있다. **필드 선택자의 이름은 `reportingController`가 아니라 `reportingComponent`다.**

```shell
# 필드 선택자 이름은 reportingComponent (core/v1 필드명을 따른다)
~$ kubectl get events -A --field-selector reportingComponent=gpu-binpack-scheduler
```

```
# 실행 결과
NAMESPACE   LAST SEEN   TYPE     REASON      OBJECT                        MESSAGE
default     30s         Normal   Scheduled   pod/ml-training-7d4b8c-xk2p9  Successfully assigned default/ml-training-7d4b8c-xk2p9 to node-3
```

`reportingController`로 필터하면 `field label not supported: reportingController` 에러가 난다. Event 오브젝트 안의 필드 이름(`reportingController`)과, API Server가 필드 선택자로 노출하는 이름(`reportingComponent`)이 다르기 때문이다.

<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **스케줄러 설정은 프로세스 → Configuration → Profile 계층 구조다.** 하나의 스케줄러 프로세스가 하나의 Configuration을 가지고, 그 안에 여러 Profile을 포함한다. `kube-scheduler`는 `--config` 플래그로 Configuration 파일을 전달받으며, 클러스터 유형에 따라 Static Pod, systemd 등 방식이 다르다.
2. **설정 파일을 고치는 것과 적용되는 것은 별개다.** 스케줄러는 설정을 런타임에 다시 읽지 않으므로 프로세스를 재시작해야 하고, 설정 오류로 기동에 실패하면 신규 파드가 전부 Pending에 빠진다. 백업은 매니페스트 디렉토리 밖에 두고, HA 환경에서는 한 대씩 순차 적용한다.
3. **`multiPoint`로 플러그인을 일괄 등록하고, `*` 패턴으로 순서를 재배치할 수 있다.** `multiPoint`는 플러그인이 구현하는 모든 extension point에 자동 등록하며, 개별 extension point 설정이 `multiPoint`보다 우선한다. `*` disable 후 `enabled`로 재등록하면 플러그인 호출 순서를 완전히 제어할 수 있다.
4. **`NodeResourcesFit`은 세 가지 스코어링 전략을 제공한다.** `LeastAllocated`(기본)는 리소스를 분산, `MostAllocated`는 노드를 채우는 bin packing, `RequestedToCapacityRatio`는 리소스별 가중치와 사용률-점수 곡선을 커스텀으로 정의한다. 점수 공식의 분모는 항상 `allocatable`이다.
5. **GPU 리소스는 단편화에 취약하다.** 노드당 수량이 적고 단위가 크기 때문에, `LeastAllocated` 전략에서 모든 노드가 부분 점유되어 큰 GPU 요청을 수용하지 못하는 문제가 발생한다. `MostAllocated`로 전환하거나, GPU 가중치를 높인 `RequestedToCapacityRatio`를 사용하여 bin packing을 적용한다. 다만 기본 프로필의 전략을 바꾸면 일반 워크로드까지 영향을 받으므로, 멀티 프로필로 분리하는 편이 적절하다.
6. **`percentageOfNodesToScore`로 대규모 클러스터의 스케줄링 속도를 개선할 수 있다.** 기본값은 클러스터 규모에 따라 자동 계산되며 비율 5%·노드 수 100개의 두 하한이 걸린다. 100노드 이하에서는 따로 설정할 필요가 없고, 공식 문서는 10% 아래로 낮추는 것을 권하지 않는다.
7. **멀티 프로필로 워크로드 성격에 맞는 스케줄링 정책을 적용할 수 있다.** 일반 워크로드에는 `LeastAllocated`, GPU 워크로드에는 `MostAllocated`를 적용하는 식으로 프로필을 분리한다. 어떤 프로필이 처리했는지는 Event의 `reportingComponent` 필드 선택자로 확인한다.

[5편]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %})에서는 지금까지 한 줄로 지나간 프레임워크 내부 동작(Extension Point 결정권, PreScore 역할, 기본 플러그인 해부)과 PodGroup 스케줄링, 멀티 스케줄러 아키텍처를 다룬다.

<br>

# 참고 링크

- [Scheduler Configuration - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/scheduling/config/)
- [Resource Bin Packing - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/resource-bin-packing/)
- [Scheduler Performance Tuning - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduler-perf-tuning/)
- [kube-scheduler Configuration (v1) API Reference](https://kubernetes.io/docs/reference/config-api/kube-scheduler-config.v1/)
- [Reserve Compute Resources for System Daemons - Kubernetes 공식 문서](https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/)
- [Practical Tips for Preventing GPU Fragmentation - NVIDIA Technical Blog](https://developer.nvidia.com/blog/practical-tips-for-preventing-gpu-fragmentation-for-volcano-scheduler/)

<br>
