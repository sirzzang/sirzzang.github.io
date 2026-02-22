---
title:  "[Kubernetes] 쿠버네티스 스케줄링 - 1. 개념"
excerpt: "Kubernetes에서의 파드 스케줄링 개념에 대해 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Scheduler
  - Scheduling
  - Pod
---

<br>

# TL;DR

- 쿠버네티스 스케줄링이란, `kube-scheduler`가 파드를 적합한 노드에 배치하는 프로세스다.
- `kube-scheduler`는 컨트롤 플레인의 static pod으로 실행되며, 교체하거나 여러 스케줄러를 동시에 운영할 수 있다. 파드는 `spec.schedulerName`으로 사용할 스케줄러를 지정한다.
- 스케줄러의 판단 기준은 오직 `spec.nodeName`이다. `status.phase: Pending`은 판단 기준이 아니다.
- 스케줄러를 거치지 않는 수동 스케줄링은 파드 생성 시 `spec.nodeName`을 직접 지정하거나, 이미 생성된 파드에 대해 Binding 오브젝트를 생성하는 방식으로 가능하다.
- 스케줄러는 3개의 큐(Active / Backoff / Unschedulable)로 파드를 관리하며, Active Queue에 있는 파드만 스케줄링을 시도한다.

<br>

# 들어가며

쿠버네티스를 운영하다 보면, 파드가 Pending 상태에 빠져 있는 상황을 마주하게 된다. 왜 이 파드는 특정 노드에 배치되지 않는지, 왜 리소스가 충분한데도 스케줄링에 실패하는지, 혹은 Deployment를 업데이트했는데 새 파드가 영원히 뜨지 않는 상황을 이해하려면, 스케줄링의 동작 방식을 알아야 한다.

이 글에서는 아래 다섯 가지를 다룬다.

1. **스케줄링의 기본 개념**: 스케줄링이란 무엇이고, 무엇이 아닌지
2. **스케줄러**: `kube-scheduler`의 실행 방식, 교체 가능 여부, 다중 스케줄러 운영
3. **스케줄링 대상**: 스케줄러의 유일한 판단 기준 (`spec.nodeName`)과 판단 기준이 아닌 것 (`Pending`, `PodScheduled`)
4. **수동 스케줄링**: 스케줄러를 거치지 않는 노드 배치 방법 (`spec.nodeName` 직접 지정, Binding 오브젝트)
5. **스케줄러 큐 구조**: 3개 큐(Active / Backoff / Unschedulable)의 역할과 파드 이동 메커니즘

[다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서는 구체적인 스케줄링 프로세스(Filter, Score, PostFilter)와 선점 메커니즘을 다룬다.

<br>

# 스케줄링

## 개념

Kubernetes 스케줄링이란, **Kubernetes 스케줄러가 파드를 적합한 노드에 배치하는 프로세스**를 의미한다. 조금 더 정확하게는, 생성된 파드를 클러스터 내 어느 노드에서 실행할지 결정하고 할당하는 과정이다. 구체적으로는 다음과 같다.

1. `kube-scheduler`가 스케줄링이 필요한 파드를 감지
2. 필터링과 스코어링(필요 시 선점)을 통해 최적의 노드를 선택
3. 해당 노드에 파드를 바인딩

### 공식 문서 살펴 보기

[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)는 아래와 같이 정의한다.

> In Kubernetes, scheduling refers to making sure that Pods are matched to nodes so that Kubelet can run them.

Kubelet이 실행할 수 있도록, 파드가 노드에 매치되게 하는 작업이라고 한다. 정의에서도 확인할 수 있지만, 스케줄링은 **배치** 작업일 뿐이다. 아래와 같은 작업은, 스케줄링이 아니다.

- 파드 생성 그 자체: 리소스 컨트롤러가 API server에 요청하면, API server가 etcd에 저장
  - Deployment의 경우: Deployment Controller → ReplicaSet Controller → API Server
- 파드 실행: Kubelet 담당. Kubelet이 Container Runtime을 통해 실행. Scheduler는 어디서 실행할지만 결정
- 리소스 할당: Linux cgroups/namespaces가 담당

그리고 이와 같은 스케줄링에 포함될 수 있는 작업의 범위는 다음과 같다:

- 노드 선택: Filter + Score를 통한 최적 노드 결정
- 파드와 노드 연결(바인딩): `spec.nodeName` 설정
- (필요 시) 선점: 낮은 우선순위 파드(victim) 선택 및 종료 요청

또한, 당연히 스케줄링은 **파드**에 적용되는 개념이다. Deployment, Statefulset 등과 같은 리소스 컨트롤러에 적용되는 개념이 아니라는 의미다.

<br>

## 스케줄러

### kube-scheduler

스케줄링을 수행하는 컴포넌트가 `kube-scheduler`다. kubeadm 기반 클러스터에서는 컨트롤 플레인 노드의 **static pod**으로 실행된다. kubelet이 `/etc/kubernetes/manifests/kube-scheduler.yaml` 매니페스트를 읽어 직접 실행하는 방식이다.

```bash
kubectl get pods -n kube-system -l component=kube-scheduler
```

```
NAME                           READY   STATUS    RESTARTS   AGE
kube-scheduler-control-plane   1/1     Running   0          3d
```

K3s의 경우에는 `kube-scheduler`가 별도의 파드로 실행되지 않고 `k3s server` 프로세스에 내장되어 있다. kubeadm과 K3s의 차이는 배포 방식일 뿐, 스케줄러의 동작 원리는 동일하다.

<br>

### 커스텀 스케줄러와 다중 스케줄러

`kube-scheduler`는 기본 스케줄러(default-scheduler)이지만, 반드시 이것만 사용해야 하는 것은 아니다. 쿠버네티스는 다음을 지원한다.

- **기본 스케줄러 교체**: `kube-scheduler`의 설정 파일(`KubeSchedulerConfiguration`)을 수정하여 플러그인을 활성화/비활성화하거나, 커스텀 스케줄러 바이너리로 교체할 수 있다.
- **다중 스케줄러 운영**: 기본 스케줄러와 별도의 커스텀 스케줄러를 동시에 실행할 수 있다. 각 스케줄러는 고유한 이름을 가지며, 파드는 `spec.schedulerName` 필드로 어떤 스케줄러를 사용할지 지정한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  schedulerName: my-custom-scheduler  # 기본값: default-scheduler
  containers:
  - name: nginx
    image: nginx
```

`spec.schedulerName`을 지정하지 않으면 기본값인 `default-scheduler`가 사용된다. 지정된 이름의 스케줄러가 클러스터에 없으면, 해당 파드는 아무도 스케줄링하지 않으므로 Pending 상태에 영구히 남게 된다.

다중 스케줄러가 유용한 대표적인 사례는 다음과 같다.

| 사례 | 설명 |
| --- | --- |
| GPU 워크로드 전용 스케줄러 | GPU 토폴로지를 인식하는 커스텀 스케줄러로 GPU 파드만 스케줄링 |
| 배치 작업 스케줄러 | [Volcano](https://volcano.sh/), [Kueue](https://kueue.sigs.k8s.io/) 등 배치/ML 워크로드에 특화된 스케줄러 |
| 테스트/실험 | 새 스케줄링 정책을 테스트하면서 기존 워크로드에는 영향을 주지 않음 |

다중 스케줄러 운영 시 주의할 점은, **서로 다른 스케줄러가 같은 노드의 리소스를 놓고 경쟁할 수 있다**는 것이다. 스케줄러 A가 노드의 잔여 리소스를 기준으로 파드를 배치하려는 순간, 스케줄러 B가 같은 노드에 다른 파드를 배치하면 리소스 충돌이 발생할 수 있다. 이 때문에 다중 스케줄러를 운영할 때는 노드 풀을 분리하거나, 스케줄러 간 리소스 경쟁이 없도록 설계하는 것이 일반적이다.

<br>

## 스케줄링 대상

스케줄러는 정확히 어떤 파드를 스케줄링 대상으로 인식하는가.

### 판단 기준: spec.nodeName

스케줄러의 판단 기준은 단 하나, **`spec.nodeName`이 비어 있는지 여부**다. 이 필드가 비어 있으면 스케줄링 대상이고, 값이 설정되어 있으면 스케줄러는 해당 파드를 무시한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  nodeName: "" # 비어 있음 → 스케줄링 대상
status:
  phase: Pending
  conditions:
  - type: PodScheduled 
    status: "False"  
    reason: Unschedulable
    message: "0/10 nodes available: 1 Insufficient gpu"
```

이 기준에 따라, Pending 상태의 파드들을 스케줄링 관점에서 세 가지로 분류할 수 있다.

| 분류 | `spec.nodeName` | 스케줄러 관여 | 위치 |
| --- | --- | --- | --- |
| 스케줄링 대상 | 비어 있음 | O | Active / Backoff / Unschedulable Queue |
| 수동 지정 | 수동 설정됨 | X | 큐에 없음 |
| 스케줄링 완료 | 스케줄러가 설정함 | 완료 | 큐에 없음 (컨테이너 시작 대기 중) |

<details markdown="1">
<summary>분류별 YAML 예시</summary>

**1. 스케줄링 대상** — `spec.nodeName`이 비어 있음

```yaml
spec:
  nodeName: ""  # 비어 있음 → 스케줄링 대상
status:
  phase: Pending
  conditions:
  - type: PodScheduled
    status: "False"
```

- 스케줄러가 감지하고 스케줄링을 시도하는 파드
- 스케줄링 큐(Active Queue, Backoff Queue, Unschedulable Queue)에 포함됨

**2. 스케줄링 비대상** — `spec.nodeName`이 수동 지정됨

```yaml
spec:
  nodeName: "worker-1"  # 수동 지정됨 → 스케줄러 개입하지 않음
status:
  phase: Pending  # 아직 Pending이지만 스케줄러가 처리하지 않음
  conditions:
  - type: PodScheduled
    status: "False"
```

- 수동으로 노드가 지정된 파드. 스케줄러가 관여하지 않음
- Pending 상태일 수 있지만(예: 이미지 pull 중, 컨테이너 시작 대기 중), 스케줄링과는 무관

**3. 스케줄링 완료** — `spec.nodeName`이 스케줄러에 의해 설정됨

```yaml
spec:
  nodeName: "worker-1"  # 스케줄러가 설정함
status:
  phase: Pending  # 컨테이너 시작 전까지는 여전히 Pending
  conditions:
  - type: PodScheduled
    status: "True"  # 스케줄링 완료
```

- 스케줄러가 이미 노드를 할당한 파드
- 컨테이너가 시작되기 전까지는 Pending 상태를 유지할 수 있음

</details>

<br>

### 판단 기준이 아닌 것

`spec.nodeName` 외에 스케줄링과 관련 있어 보이는 필드가 두 가지 더 있다. `status.phase: Pending`과 `status.conditions[PodScheduled]`다. 둘 다 스케줄러의 판단 기준이 **아니다**.

<br>

#### status.phase: Pending

`Pending`은 파드의 광범위한 상태를 나타낸다. 파드가 Pending이 되는 원인은 스케줄링 대기 외에도 다양하다.

- 스케줄링 완료 후 이미지 pull 중
- init container 실행 대기 중
- 스케줄링 완료 후 컨테이너 시작 대기 중

즉, **Pending 상태라고 해서 반드시 스케줄링 문제인 것은 아니다**. `spec.nodeName`이 이미 설정된 파드도 컨테이너가 시작되기 전까지는 Pending 상태를 유지한다. 파드가 Pending 상태에 빠졌을 때, 먼저 `spec.nodeName`이 비어 있는지 확인하여 스케줄링 문제인지 아닌지를 구분하는 것이 진단의 첫 단계다.

<br>

#### status.conditions: PodScheduled

`status.conditions`의 `PodScheduled`는 **스케줄링 결과를 기록하는 지표**다. 스케줄러가 이 값을 읽어서 판단하는 것이 아니라, 스케줄링이 완료된 후 API Server가 이 값을 업데이트한다.

동작 흐름은 아래와 같다.

1. 파드 생성(`nodeName` 비어 있음) → `PodScheduled: False`
2. 스케줄러가 `nodeName`이 비어 있는 파드를 감지하고 스케줄링 시도
3. 성공 시 `nodeName` 설정 → `PodScheduled: True`로 자동 업데이트
4. 실패 시 `nodeName` 여전히 비어 있음 → `PodScheduled: False` 유지

정리하면, **`spec.nodeName`이 원인(입력)**이고, **`Pending`과 `PodScheduled`는 결과(출력)**다. 스케줄러는 오직 `spec.nodeName`만 보고 스케줄링 대상 여부를 결정한다.

<br>

## 수동 스케줄링

스케줄러를 거치지 않고 파드를 특정 노드에 직접 배치하는 방법이다. 테스트, 디버깅, 또는 DaemonSet과 같이 스케줄러 개입 없이 노드에 파드를 배치해야 하는 상황에서 사용한다.

### 파드 생성 시 spec.nodeName 지정

가장 단순한 방법은 파드 생성 시 `spec.nodeName`을 직접 지정하는 것이다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: manual-pod
spec:
  nodeName: worker-1  # 스케줄러를 거치지 않고 worker-1에 직접 배치
  containers:
  - name: nginx
    image: nginx
```

이 경우 스케줄러는 해당 파드를 완전히 무시한다. `spec.nodeName`이 이미 설정되어 있으므로 스케줄링 대상이 아니다. kubelet이 자신의 노드에 할당된 파드를 감지하고 직접 실행한다.

다만, 스케줄러를 거치지 않으므로 **Filter 단계의 검증이 생략**된다는 점에 유의해야 한다. 리소스 부족, taint/toleration 불일치 등 스케줄러가 확인하는 조건을 무시하고 배치되기 때문에, 노드의 상태를 사전에 확인하지 않으면 파드가 실행에 실패할 수 있다. 또한, 존재하지 않는 노드명을 지정하면 파드는 Pending 상태에 영구히 남게 된다.

### 이미 생성된 파드에 대한 수동 스케줄링: Binding 오브젝트

`spec.nodeName`은 파드가 생성된 이후에는 직접 수정할 수 없다. API Server가 이 필드의 업데이트를 거부하기 때문이다.

```bash
# 이미 생성된 파드의 nodeName을 변경하려고 하면 실패한다
kubectl patch pod my-pod -p '{"spec":{"nodeName":"worker-1"}}'
# The Pod "my-pod" is invalid: spec: Forbidden: pod updates may not change fields other than ...
```

이미 생성되어 `spec.nodeName`이 비어 있는 파드를 수동으로 노드에 배치하려면, **Binding 오브젝트**를 생성해야 한다. 이것은 실제로 스케줄러가 내부적으로 파드를 노드에 바인딩할 때 사용하는 것과 동일한 메커니즘이다.

```bash
# Binding 오브젝트를 API Server에 POST
curl -X POST http://<API_SERVER>/api/v1/namespaces/default/pods/my-pod/binding \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "Binding",
    "metadata": {
      "name": "my-pod"
    },
    "target": {
      "apiVersion": "v1",
      "kind": "Node",
      "name": "worker-1"
    }
  }'
```

Binding 오브젝트가 생성되면 API Server가 해당 파드의 `spec.nodeName`을 `worker-1`으로 설정하고, 해당 노드의 kubelet이 파드를 실행한다. `spec.nodeName` 직접 지정과 마찬가지로 스케줄러의 Filter 검증을 거치지 않는다.

Binding 오브젝트의 핵심 특성은 다음과 같다.

- **1회성**: 하나의 파드에 대해 한 번만 생성할 수 있다. 이미 바인딩된 파드에 대해 다시 Binding을 생성하면 실패한다.
- **스케줄러 내부 동작과 동일**: 스케줄러가 노드를 선택한 후 Bind 단계에서 수행하는 작업이 바로 이 Binding 오브젝트 생성이다. 수동 스케줄링은 스케줄러의 Filter/Score 단계를 건너뛰고 Bind 단계만 직접 실행하는 것과 같다.
- **`kubectl`로는 직접 생성 불가**: Binding 오브젝트는 `kubectl create`로 생성할 수 없으며, API Server에 직접 HTTP 요청을 보내야 한다.


### 수동 스케줄링 방식 비교

| 방식 | 시점 | 방법 | Filter 검증 | 비고 |
| --- | --- | --- | --- | --- |
| `spec.nodeName` 직접 지정 | 파드 생성 시 | YAML에 `nodeName` 명시 | 생략됨 | 가장 단순. 존재하지 않는 노드 지정 시 영구 Pending |
| Binding 오브젝트 | 파드 생성 후 | API Server에 POST 요청 | 생략됨 | 스케줄러 내부 동작과 동일한 메커니즘 |

두 방식 모두 스케줄러를 우회하므로, 노드의 리소스 상태나 taint/toleration 등을 사전에 확인해야 한다.

<br>

## 스케줄러 큐

스케줄러는 내부적으로 3개의 큐를 운영하며, **Active Queue에 있는 파드만 꺼내서 스케줄링을 시도**한다. 큐 관리 자체도 스케줄러가 담당한다. 스케줄러 내부의 Scheduling Queue 컴포넌트가 새 파드 감지(Watch), 타이머 기반 Backoff Queue 확인, 클러스터 이벤트에 따른 Unschedulable Queue 처리, 스케줄링 실패 시 적절한 큐로의 이동 등을 모두 수행한다.

| 큐 | 역할 | 실패 유형 | Active Queue 복귀 조건 |
| --- | --- | --- | --- |
| **Active Queue** | 즉시 스케줄링을 시도할 파드 | - | - |
| **Backoff Queue** | 일시적으로 스케줄링에 실패한 파드 | 일시적 실패 (리소스 약간 부족, 노드 일시적 NotReady, 다른 파드가 먼저 리소스 선점) | 지수 백오프 타이머 만료 시 (1초 → 2초 → 4초 → ... 최대 10초) |
| **Unschedulable Queue** | 클러스터 구조상 스케줄링 불가능한 파드 | 구조적 실패 (nodeSelector 불일치, taint/toleration 불일치, PV 미존재, GPU 타입 없음) | 클러스터 이벤트 발생 시 (노드 추가/변경, PV/PVC 생성, 파드 삭제, 리소스 증가) |

Active Queue에서 파드를 꺼내는 순서는 **우선순위 기반**이며, 동일한 우선순위의 경우 큐에 들어온 순서(FIFO)를 따른다.

<br>

### Active Queue 진입 경로

파드가 Active Queue에 들어오는 경로는 세 가지다.

1. **신규 파드**: API Server에 대한 Watch를 통해 `spec.nodeName`이 비어 있는 파드를 감지
2. **Backoff Queue에서 복귀**: 지수 백오프 타이머가 만료된 파드. 즉시 재시도하면 스케줄러에 불필요한 부하가 걸리므로, 초기에는 빠르게(1초), 계속 실패하면 간격을 늘려(2초 → 4초 → ... 최대 10초) 재시도한다.
3. **Unschedulable Queue에서 복귀**: 클러스터 이벤트가 발생하여 스케줄링 조건이 달라진 경우. 노드 추가/변경, PV/PVC 생성, 파드 삭제 등이 이에 해당한다.

<br>

### 스케줄링 루프

이 구조에 의해, 클러스터 내에서는 다음과 같은 스케줄링 루프가 반복된다.

```
Active Queue에서 파드 꺼냄
    ↓
스케줄링 시도
    ├─ 성공 → Bind (큐에서 제거)
    └─ 실패 → 실패 유형에 따라 Backoff Queue 또는 Unschedulable Queue로 이동
                  ↓
              조건 충족 시 Active Queue로 복귀
                  ↓
              (반복)
```

스케줄링 프로세스의 구체적인 단계(Filter, Score, PostFilter)와 실패 유형별 큐 이동 규칙은 [다음 글]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})에서 다룬다.



<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **스케줄링은 배치 작업이다.** 파드 생성, 파드 실행, 리소스 할당은 스케줄링이 아니다. 스케줄러는 "어느 노드에서 실행할지"만 결정한다.
2. **`kube-scheduler`는 교체 가능하고 다중 운영이 가능하다.** 파드는 `spec.schedulerName`으로 사용할 스케줄러를 지정하며, 기본값은 `default-scheduler`다.
3. **스케줄러의 판단 기준은 `spec.nodeName`이다.** `status.phase: Pending`이나 `PodScheduled` 조건이 아니다. `spec.nodeName`이 비어 있는 파드만 스케줄링 대상이 된다.
4. **수동 스케줄링은 두 가지 방법이 있다.** 파드 생성 시 `spec.nodeName`을 직접 지정하거나, 이미 생성된 파드에 Binding 오브젝트를 생성한다. 두 방식 모두 스케줄러의 Filter 검증을 우회한다.
5. **스케줄러는 3개의 큐로 파드를 관리한다.** Active Queue에서만 스케줄링을 시도하고, 실패 유형(일시적/구조적)에 따라 Backoff Queue 또는 Unschedulable Queue로 분류한 뒤, 조건 충족 시 Active Queue로 복귀시킨다.

파드가 Pending 상태에 빠졌을 때, 먼저 `spec.nodeName`이 비어 있는지 확인하여 스케줄링 문제인지 아닌지를 구분하고, 스케줄링 문제라면 파드가 어느 큐에 있는지(Events 메시지 등)를 확인하여 원인을 좁혀 나가는 것이 효과적이다.
