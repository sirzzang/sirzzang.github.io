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
last_modified_at: 2026-10-01
---

<br>

# TL;DR

- 쿠버네티스 스케줄링이란, `kube-scheduler`가 파드를 적합한 노드에 배치하는 프로세스다. 스케줄러는 노드가 결정되지 않은 파드를 감지하여, 스케줄링 요구 사항에 맞는 노드를 필터링하고 스코어링으로 최적 노드를 선택한다.
- `kube-scheduler`는 컨트롤 플레인에서 실행되며(Static Pod, systemd 서비스, 프로세스 내장 등 배포 방식은 다양), 교체하거나 여러 스케줄러를 동시에 운영할 수 있다. 파드는 `spec.schedulerName`으로 사용할 스케줄러를 지정하며, 각 스케줄러는 자신의 이름과 일치하는 파드만 처리한다(경쟁 없음).
- 스케줄러의 판단 기준은 오직 `spec.nodeName`이다. `status.phase: Pending`은 판단 기준이 아니다.
- 스케줄러를 거치지 않는 수동 스케줄링은 파드 생성 시 `spec.nodeName`을 직접 지정하거나, 이미 생성된 파드에 대해 Binding 오브젝트를 생성하는 방식으로 가능하다. 수동 스케줄링이 실제로 활용된 대표 사례인 DaemonSet은 `ScheduleDaemonSetPods` Feature Gate가 기본 활성화된 v1.12부터 NodeAffinity(`matchFields`) 기반으로 전환되어 `kube-scheduler`에 위임되며, v1.17에 GA가 되었다.
- 수동 스케줄링은 Filter 단계를 건너뛰지만 kubelet이 일부 조건을 다시 검사한다. cordon, `NoSchedule` taint, InterPodAffinity, PodTopologySpread는 아무도 검사하지 않는다.
- 스케줄러는 3개의 큐(Active / Backoff / Unschedulable)로 파드를 관리하며, Active Queue에 있는 파드만 스케줄링을 시도한다.

<br>

# 들어가며

쿠버네티스를 운영하다 보면, 파드가 Pending 상태에 빠져 있는 상황을 마주하게 된다.  왜 이 파드는 특정 노드에 배치되지 않는지, 왜 리소스가 충분해 보이는데도 스케줄링에 실패하는지, 혹은 Deployment를 업데이트했는데 새 파드가 영원히 뜨지 않는 상황이 왜 발생했는지를 이해하려면, 스케줄링의 동작 방식을 알아야 한다.

이 글에서는 아래 다섯 가지를 다룬다.

1. **스케줄링의 기본 개념**: 스케줄링이란 무엇이고, 무엇이 아닌지
2. **스케줄러**: `kube-scheduler`의 실행 방식, 교체 가능 여부, 다중 스케줄러 운영과 파드 매칭 방식
3. **스케줄링 대상**: 스케줄러의 유일한 판단 기준 (`spec.nodeName`)과 판단 기준이 아닌 것 (`Pending`, `PodScheduled`)
4. **수동 스케줄링**: 스케줄러를 거치지 않는 노드 배치 방법 (`spec.nodeName` 직접 지정, Binding 오브젝트)과 대표 사례인 DaemonSet의 스케줄러 위임 전환
5. **스케줄러 큐 구조**: 3개 큐(Active / Backoff / Unschedulable)의 역할과 파드 이동 메커니즘

앞의 두 질문은 [2편]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %})의 Filter·Score와 [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})의 제어 설정이 다루고, 세 번째 질문은 [2편 - 프로세스 결과와 큐 이동 요약]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#프로세스-결과와-큐-이동-요약)의 실전 사례가 다룬다. 실제 파드에서 실패 지점과 큐를 확인하는 절차는 [5편 - 스케줄링 실패 진단]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#스케줄링-실패-진단)에 있다.

이 시리즈는 파드가 **처음 노드에 배치되는 시점**의 결정만 다룬다. 배치된 뒤의 재배치(Descheduler), 축출(Eviction과 `PodDisruptionBudget`), 노드 증설(Cluster Autoscaler)은 스케줄링 결과에 영향을 주지만 `kube-scheduler`의 책임이 아니므로 범위 밖으로 둔다. 본문에 이 이름들이 나올 때는 스케줄링 결정과 맞닿는 지점만 짚는다.

본문 기준 버전은 v1.32이며, 그보다 최신 기능(PodGroup 스케줄링 등)은 등장 지점에 버전을 따로 표기한다.

<br>

# 스케줄링

## 개념

Kubernetes 스케줄링이란, **Kubernetes 스케줄러가 파드를 적합한 노드에 배치하는 프로세스**를 의미한다. 스케줄러의 핵심 역할은 **파드가 배포될 적합한 노드를 결정**하는 것이다. 스케줄러가 다루는 대상은 구체적으로 다음과 같다.

- **새로 생성되는 파드 중 노드가 결정되지 않은 경우**: 파드가 API Server에 등록되었지만 아직 `spec.nodeName`이 설정되지 않은 상태
- **생성되었지만 적합한 노드를 아직 찾지 못한 경우**: 이전 스케줄링 시도에서 실패하여 큐에서 대기 중인 파드

스케줄러가 이러한 파드를 감지하면, 파드에 정의된 스케줄링 요구 사항(리소스 요청은 [2편 - Filter]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#filter)의 `NodeResourcesFit`에서, nodeSelector·affinity는 [3편]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %})에서 후술)에 맞는 노드를 **필터링**하고, 스코어링 과정을 통해 배포에 **적합한 노드 순서를 정렬**한 뒤, 최적의 노드를 선택하여 바인딩한다. 전체 흐름을 요약하면 다음과 같다.

1. `kube-scheduler`가 스케줄링이 필요한 파드를 감지
2. 필터링으로 파드의 스케줄링 요구 사항에 맞는 노드를 걸러냄
3. 스코어링으로 적합한 노드에 순위를 매김 (필요 시 선점)
4. 최고 점수 노드에 파드를 바인딩

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

또한, 당연히 스케줄링은 **파드**에 적용되는 개념이다. Deployment, StatefulSet 등과 같은 리소스 컨트롤러에 적용되는 개념이 아니라는 의미다.

<br>

## 스케줄러

### kube-scheduler

스케줄링을 수행하는 컴포넌트가 `kube-scheduler`다. 컨트롤 플레인에서 실행되며, 배포 방식은 클러스터 프로비저닝 도구에 따라 다르다. 어떤 방식이든 스케줄러의 동작 원리는 동일하다.

| 배포 방식 | 대표 도구 | 설명 |
| --- | --- | --- |
| **Static Pod** | kubeadm, kubespray, RKE2 | kubelet이 `/etc/kubernetes/manifests/kube-scheduler.yaml` 매니페스트를 읽어 실행. 가장 일반적인 방식 |
| **systemd 서비스** | [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) | kube-scheduler 바이너리를 직접 실행하여 systemd unit으로 등록. 컨트롤 플레인에 kubelet이 필요 없음 |
| **프로세스 내장** | K3s | 단일 바이너리(`k3s server`)에 스케줄러가 포함되어 별도 프로세스 없이 동작 |

kubeadm 기반 클러스터에서는 Static Pod으로 실행되므로, `kube-system` 네임스페이스에서 파드로 확인할 수 있다.

```bash
kubectl get pods -n kube-system -l component=kube-scheduler
```

```
NAME                           READY   STATUS    RESTARTS   AGE
kube-scheduler-control-plane   1/1     Running   0          3d
```

반면 systemd 서비스로 구동하는 환경(예: [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}))에서는 컨트롤 플레인 노드에 kubelet 자체가 없으므로, 스케줄러가 파드 목록에 나타나지 않는다. 대신 `systemctl status kube-scheduler`로 상태를 확인한다.

<br>

### 커스텀 스케줄러와 다중 스케줄러

`kube-scheduler`는 기본 스케줄러(default-scheduler)이지만, 반드시 이것만 사용해야 하는 것은 아니다. 쿠버네티스는 다음을 지원한다.

- **기본 스케줄러 교체**: `kube-scheduler`의 설정 파일(`KubeSchedulerConfiguration` — [4편 - KubeSchedulerConfiguration]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#kubeschedulerconfiguration)에서 후술)을 수정하여 플러그인([2편 - 기본 플러그인과 Extension Point 매핑]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#기본-플러그인과-extension-point-매핑)에서 후술)을 활성화/비활성화하거나, 커스텀 스케줄러 바이너리로 교체할 수 있다.
- **다중 스케줄러 운영**: 기본 스케줄러와 별도의 커스텀 스케줄러를 동시에 실행할 수 있다. 각 스케줄러는 고유한 이름을 가지며, 파드는 `spec.schedulerName` 필드로 어떤 스케줄러를 사용할지 지정한다.

<br>

#### schedulerName 지정

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

`spec.schedulerName`을 지정하지 않으면 기본값인 `default-scheduler`가 사용된다. 이 기본값은 kube-apiserver가 파드 생성 시 자동으로 설정해 준다. 다중 스케줄러 환경에서 반드시 `schedulerName`을 명시해야 하는 것은 아니지만, **명시하지 않으면 항상 `default-scheduler`가 해당 파드를 처리한다.** 커스텀 스케줄러로 처리하고 싶은 파드에만 `schedulerName`을 명시하면 된다.

지정된 이름의 스케줄러가 클러스터에 없으면, 해당 파드는 아무도 스케줄링하지 않으므로 Pending 상태에 영구히 남게 된다. 시스템 파드까지 이 상황에 빠지는 경우는 [5편 - default-scheduler 부재 시나리오]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#default-scheduler-부재-시나리오)에서 다룬다.

이 동작은 뒤에서 다룰 [Binding 오브젝트](#이미-생성된-파드에-대한-수동-스케줄링-binding-오브젝트)를 쓸 때도 그대로 활용된다. 존재하지 않는 스케줄러 이름을 지정해 두면 `default-scheduler`가 그 파드를 Watch하지 않으므로, 파드가 Pending으로 남아 있는 동안 여유롭게 Binding을 생성할 수 있다.

<br>

#### 다중 스케줄러 구현 방식

다중 스케줄러를 구현하는 방식은 크게 두 가지다.

**1. 단일 kube-scheduler에서 다중 프로필 운영**

`KubeSchedulerConfiguration`에서 여러 프로필을 정의할 수 있다. 각 프로필은 고유한 `schedulerName`을 가지고, 서로 다른 플러그인 구성을 적용할 수 있다.

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler     # 기본 프로필
  - schedulerName: no-scoring-scheduler  # 같은 프로세스 안의 두 번째 프로필
```

하나의 프로세스에서 여러 프로필을 운영하므로 리소스 경쟁 문제가 적다. 프로필별로 플러그인을 켜고 끄는 문법과, 기본 플러그인을 전부 끈 뒤 순서를 재배치하는 `*` 패턴은 [4편 - `*` 패턴: 전체 비활성화와 순서 재배치]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#-패턴-전체-비활성화와-순서-재배치)에서 다룬다. 프로필별로 바꿀 수 없는 설정도 있다([4편 - 멀티 프로필의 제약]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#멀티-프로필의-제약)).

**2. 별도의 스케줄러 프로세스 운영**

완전히 독립적인 스케줄러 바이너리를 Deployment 등으로 배포한다. [Volcano](https://volcano.sh/), [Kueue](https://kueue.sigs.k8s.io/) 등이 이 방식에 해당한다.

> Profile만으로 충분한 경우와 별도 바이너리가 필요한 경우의 판단 기준, Volcano와 Kueue의 아키텍처 비교는 [5편 - 멀티 스케줄러 심화]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#멀티-스케줄러-심화)에서 자세히 다룬다.

<br>

#### 파드와 스케줄러의 매칭: 경쟁은 없다

하나의 파드를 놓고 여러 스케줄러가 "경쟁"하는 상황은 설계상 발생하지 않는다. 각 스케줄러는 **`spec.schedulerName`이 자신의 이름과 일치하는 파드만** Watch하고 처리한다. 즉, `schedulerName: default-scheduler`인 파드는 기본 스케줄러만, `schedulerName: my-custom-scheduler`인 파드는 커스텀 스케줄러만 처리한다. 랜덤으로 스케줄러가 파드를 가져가는 것이 아니라, **`schedulerName` 필드에 의해 1:1로 매칭**되는 구조다.

단, 서로 다른 스케줄러 프로세스가 같은 `schedulerName`을 쓰는 것을 쿠버네티스가 막아 주지는 않는다. 이 경우에는 두 스케줄러가 같은 파드를 처리하려 시도한다([5편 - schedulerName 고유성 메커니즘]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#schedulername-고유성-메커니즘)).

그리고 서로 다른 스케줄러가 처리한 파드들이 **같은 노드의 리소스를 놓고 충돌**하는 문제는 발생할 수 있다. 각 스케줄러가 독립적으로 리소스 상태를 계산하기 때문에, 스케줄러 A가 노드의 잔여 리소스를 보고 파드를 배치하는 사이에 스케줄러 B가 같은 노드에 다른 파드를 배치하면 리소스 과할당이 발생한다. 선점이 얽히면 루프가 생길 수도 있다. 스케줄러 A가 스케줄러 B의 낮은 우선순위 파드를 선점하면, B의 컨트롤러가 해당 파드를 재생성하고, B가 다시 같은 노드에 스케줄링하고, A가 다시 선점하는 반복이 가능하다.

이 때문에 다중 스케줄러를 운영할 때는 **노드 풀을 분리**하거나, **스케줄러 간 리소스 경쟁이 없도록 설계**하는 것이 일반적이다. 충돌이 구체적으로 어떤 메커니즘으로 발생하는지와 운영 권고는 [5편 - 자원 뷰 충돌]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#자원-뷰-충돌)에서 다룬다.

<br>

#### 다중 스케줄러 활용 사례

| 사례 | 설명 |
| --- | --- |
| GPU 워크로드 전용 스케줄러 | GPU 토폴로지를 인식하는 커스텀 스케줄러로 GPU 파드만 스케줄링. 프로필 분리로 해결되는 경우는 [4편 - 워크로드 성격에 따른 프로필 분리]({% post_url 2025-11-05-Kubernetes-Scheduling-04 %}#워크로드-성격에-따른-프로필-분리) 참고 |
| 배치 작업 스케줄러 | [Volcano](https://volcano.sh/), [Kueue](https://kueue.sigs.k8s.io/) 등 배치/ML 워크로드에 특화된 스케줄러 |
| 테스트/실험 | 새 스케줄링 정책을 테스트하면서 기존 워크로드에는 영향을 주지 않음 |
| 스코어링 비활성화 | 특정 워크로드에 대해 Score 단계를 건너뛰어 스케줄링 속도를 높임 |

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
    message: "0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector."
```

`message`는 스케줄링이 실패한 이유를 노드 수로 집계한 문자열이다. 읽는 방법은 다음과 같다.

- `0/10`: 평가한 노드 중 **적합 판정을 받은 노드 수 / 평가 대상 노드 수**. 앞 숫자가 0이면 Filter를 통과한 노드가 하나도 없다는 뜻이다
- `1 Insufficient nvidia.com/gpu`: **그 이유로 탈락한 노드 수**가 1개. 탈락 사유는 Filter 플러그인이 반환한 것이다
- 사유가 여럿이면 쉼표로 이어 붙는다. 위 예시는 1개 노드가 GPU 부족으로, 9개 노드가 nodeSelector 불일치로 탈락한 상황이다

각 사유가 어떤 플러그인에서 나오는지와, 이 메시지로 실패 단계를 좁히는 절차는 [5편 - Events 메시지 읽기]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#events-메시지-읽기)에서 다룬다.

이 기준에 따라, Pending 상태의 파드들을 스케줄링 관점에서 세 가지로 분류할 수 있다.

| 분류 | `spec.nodeName` | 스케줄러 관여 | 위치 |
| --- | --- | --- | --- |
| 스케줄링 대상 | 비어 있음 | O | Active / Backoff / Unschedulable Queue |
| 수동 지정 | 수동 설정됨 | X | 큐에 없음 |
| 스케줄링 완료 | 스케줄러가 설정함 | 완료 | 큐에 없음 (컨테이너 시작 대기 중) |

첫 번째 분류의 파드가 세 큐 중 어디에 있는지는 API로 직접 노출되지 않는다. Events와 메트릭으로 추정하는 방법은 [5편 - 파드가 어느 큐에 있는지 판별]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#파드가-어느-큐에-있는지-판별)에서 다룬다.

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

`status.conditions`의 `PodScheduled`는 **스케줄링 결과를 기록하는 지표**다. 스케줄러가 이 값을 읽어서 판단하는 것이 아니라, 스케줄링 시도의 결과로 기록된다. 성공과 실패를 기록하는 주체가 다르다.

동작 흐름은 아래와 같다.

1. 파드 생성(`nodeName` 비어 있음) → `conditions`는 아직 비어 있음
2. 스케줄러가 `nodeName`이 비어 있는 파드를 감지하고 스케줄링 시도
3. 성공 시 → Binding 처리 과정에서 **API Server**가 `PodScheduled: True`를 기록
4. 실패 시 → **스케줄러**가 직접 `PodScheduled: False`(`reason: Unschedulable`, 실패 사유 `message`)를 patch

즉, 위 예시 YAML에서 본 `reason`과 `message`는 스케줄러가 남긴 것이고, `True` 조건은 API Server가 남긴 것이다.

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

다만, 스케줄러를 거치지 않으므로 **Filter 단계가 실행되지 않는다**. 존재하지 않는 노드명을 지정하면 파드는 Pending 상태에 영구히 남게 된다.

<br>

스케줄러의 Filter를 건너뛴다고 해서 아무 검증도 없는 것은 아니다. kubelet은 자신의 노드에 배정된 파드를 실행하기 전에 admission 검사를 수행하며, 여기서 리소스 충분 여부와 `nodeSelector`, `NoExecute` taint 등은 다시 판정한다. 그러나 **배치 정책에 해당하는 것 — cordon, `NoSchedule` taint, 파드 간 affinity, 토폴로지 분산 — 은 스케줄러도 kubelet도 검사하지 않는다.**

그래서 cordon된 노드에 `spec.nodeName`을 직접 지정하면 파드가 그대로 뜬다. cordon이 Filter 단계에서만 평가되고 kubelet은 `NoSchedule` taint를 보지 않기 때문이다(구조는 [3편 - cordon의 기술적 의미]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#cordon의-기술적-의미)). 버그가 아니라 설계된 경로이고, GPU 장애 노드를 cordon해 둔 채 검증용 probe만 밀어 넣는 식으로 활용할 여지도 있다.

kubelet이 다시 검사하는 항목과 하지 않는 항목의 전체 대조, cordon 우회의 주의점은 [5편 - 수동 배치의 제약]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#수동-배치의-제약)에서 다룬다.

<br>

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

Binding 오브젝트가 생성되면 API Server가 해당 파드의 `spec.nodeName`을 `worker-1`으로 설정하고 `PodScheduled: True` 조건을 기록하며, 해당 노드의 kubelet이 파드를 실행한다. `spec.nodeName` 직접 지정과 마찬가지로 스케줄러의 Filter는 실행되지 않고, [kubelet의 admission 검사만]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#kubelet이-다시-검사하는-것과-하지-않는-것) 적용된다.

Binding 오브젝트의 핵심 특성은 다음과 같다.

- **1회성**: 하나의 파드에 대해 한 번만 성공한다. 이미 `spec.nodeName`이 설정된 파드에 다시 Binding을 생성하면 실패한다.
- **스케줄러 내부 동작과 동일**: 스케줄러가 노드를 선택한 후 Bind 단계에서 수행하는 작업이 바로 이 Binding 오브젝트 생성이다. 수동 스케줄링은 스케줄러의 Filter/Score 단계를 건너뛰고 Bind 단계만 직접 실행하는 것과 같다.
- **`kubectl`에 전용 서브커맨드가 없다**: `kubectl bind` 같은 명령은 없다. `kind: Binding` 매니페스트를 `kubectl create -f`로 POST하거나, 위와 같이 API Server에 직접 요청을 보낸다. `kubectl patch`로 `spec.nodeName`을 고치는 방식은 앞에서 본 것처럼 거부된다.

<br>

이 1회성이라는 성질에는 중요한 따름정리가 있다. **스케줄링이 완료된 파드의 배치는 바꿀 수 없다.** 쿠버네티스에는 실행 중인 파드를 다른 노드로 옮기는 마이그레이션 기능이 없으므로, 배치를 바꾸려면 삭제 후 재생성이 유일한 경로다. 선점과 축출도 이 원칙의 예외가 아니다 — victim의 `nodeName`을 고치는 것이 아니라 삭제하고, 컨트롤러가 만든 새 파드가 스케줄링을 처음부터 다시 받는다.

Binding이 거부되는 세 가지 조건, 스케줄러와 경쟁하지 않고 Binding을 쓰는 방법, 변경 가능한 `spec` 필드 목록은 [5편 - 수동 배치의 제약]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#수동-배치의-제약)에서 다룬다.

<br>

### 수동 스케줄링 방식 비교

| 방식 | 시점 | 방법 | Filter 실행 | 비고 |
| --- | --- | --- | --- | --- |
| `spec.nodeName` 직접 지정 | 파드 생성 시 | YAML에 `nodeName` 명시 | 안 함 | 가장 단순. 존재하지 않는 노드 지정 시 영구 Pending |
| Binding 오브젝트 | 파드 생성 후 | Binding 오브젝트 POST | 안 함 | 스케줄러 내부 동작과 동일한 메커니즘. `schedulerName`을 바꿔 두면 경쟁 없이 사용 가능 |

두 방식 모두 스케줄러를 우회하므로, cordon 여부와 `NoSchedule` taint, 배치 규칙은 사전에 직접 확인해야 한다.

### 사례: DaemonSet의 수동 → 스케줄러 위임 전환

DaemonSet은 클러스터의 모든(또는 특정) 노드에 파드를 하나씩 배치하는 워크로드 리소스로, **수동 스케줄링이 실제로 활용되었던 대표 사례**이자 거기서 벗어나 `kube-scheduler`에 위임하게 된 전환의 대표 케이스다. DaemonSet의 스케줄링 방식은 Kubernetes 버전에 따라 크게 변화했다.

**과거 (v1.12 이전): DaemonSet Controller가 직접 배치**

`ScheduleDaemonSetPods`는 DaemonSet 파드의 스케줄링을 DaemonSet Controller가 아닌 `kube-scheduler`에 위임하도록 전환하는 [Feature Gate](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/)다. 전환 이력은 다음과 같다.

| 버전 | 상태 |
| --- | --- |
| v1.11 | alpha (기본 비활성화) |
| v1.12 | **beta (기본 활성화)** — 이 시점부터 기본 동작이 스케줄러 위임으로 바뀐다 |
| v1.17 | GA (항상 활성화, 비활성화 불가) |
| v1.18 | 게이트 자체 제거 |

기본 활성화 시점이 v1.12이므로, 실제 동작이 전환된 것은 v1.12다. v1.12부터 v1.16까지는 게이트를 명시적으로 꺼서 과거 동작으로 되돌릴 수 있었고, v1.17 GA부터는 그것도 불가능해졌다.

이 기능이 도입되기 전, DaemonSet Controller는 파드를 생성하면서 직접 `spec.nodeName`을 설정해 노드에 배치했다. 앞에서 살펴본 두 가지 수동 스케줄링 방식 중 첫 번째([`spec.nodeName` 직접 지정](#파드-생성-시-specnodename-지정))와 동일한 메커니즘이다.

- DaemonSet Controller가 각 노드에 대해 파드를 생성하면서 `spec.nodeName`을 직접 지정
- `kube-scheduler`를 거치지 않으므로 taint/toleration, affinity 등 스케줄러의 필터 검증이 적용되지 않음
- DaemonSet Controller가 자체적으로 taint/toleration 등을 확인해야 했는데, 이로 인해 스케줄러와 DaemonSet Controller의 로직이 중복되고, 동작이 불일치하는 문제가 있었음

**현재 (v1.12 기본 활성화, v1.17 GA): kube-scheduler에 위임**

`ScheduleDaemonSetPods`가 활성화되면서, DaemonSet Controller는 `spec.nodeName`을 직접 설정하지 않는다. 대신 파드의 `spec.affinity.nodeAffinity`에 `matchFields`로 특정 노드를 지정하여 `kube-scheduler`에 위임한다. 그 결과 DaemonSet 파드도 스케줄러의 모든 필터 검증(taint/toleration, 리소스 확인 등)을 거치게 되었고, 스케줄러와 DaemonSet Controller 사이의 로직 불일치 문제가 해소되었다.

이 경로는 스케줄러 내부에서 추가 최적화를 받는다. `NodeAffinity` 플러그인은 `matchFields`로 노드 이름이 고정된 경우 PreFilter 단계에서 해당 노드만 후보로 반환하므로, 전체 노드를 순회하지 않는다([5편 - Extension Point 결정권 분류]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#extension-point-결정권-분류)).

NodeAffinity와 `matchFields`의 구체적인 YAML과 동작은 [3편 - 사례: DaemonSet의 NodeAffinity 위임]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#사례-daemonset의-nodeaffinity-위임)에서 다룬다.

<br>

## 스케줄러 큐

스케줄러는 내부적으로 3개의 큐를 운영하며, **Active Queue에 있는 파드만 꺼내서 스케줄링을 시도**한다. 큐 관리 자체도 스케줄러가 담당한다. 스케줄러 내부의 Scheduling Queue 컴포넌트가 새 파드 감지(Watch), 타이머 기반 Backoff Queue 확인, 클러스터 이벤트에 따른 Unschedulable Queue 처리, 스케줄링 실패 시 적절한 큐로의 이동 등을 모두 수행한다.

![kubernetes-scheduling-queues]({{site.url}}/assets/images/kubernetes-scheduling-queues.png){: .align-center}
<center><sup>파드가 3개의 큐 사이를 이동하는 흐름. 출처: <a href="https://github.com/kubernetes/community/blob/master/contributors/devel/sig-scheduling/scheduler_queues.md">kubernetes/community - Scheduling queue in kube-scheduler</a></sup></center>

| 큐 | 자료구조 | 역할 | 주로 관측되는 실패 | Active Queue 복귀 조건 |
| --- | --- | --- | --- | --- |
| **Active Queue** | Heap (우선순위 순) | 즉시 스케줄링을 시도할 파드 | - | - |
| **Backoff Queue** | Heap (백오프 만료 시각 순) | 짧은 간격으로 재시도할 파드 | 바인딩 실패, 내부 오류, 백오프가 남은 상태에서의 이벤트 복귀 | 지수 백오프 타이머 만료 시 (1초 → 2초 → 4초 → ... 최대 10초) |
| **Unschedulable Queue** | Map | 클러스터 상태가 바뀌어야 스케줄링 가능한 파드 | Filter 탈락 전반 (리소스 부족, nodeSelector 불일치, taint/toleration 불일치, PV 미존재, GPU 타입 없음) | 클러스터 이벤트 발생 시 (노드 추가/변경, PV/PVC 생성, 파드 삭제, 리소스 증가) |

> 위 "주로 관측되는 실패" 열은 결과를 기준으로 묶은 것이다. 스케줄러 내부의 실제 분기 기준은 실패의 성질이 아니라 ① 플러그인이 reject한 것인지 내부 오류인지 ② 스케줄링 도중 도착한 이벤트에 대한 QueueingHint 판정이다. 리소스 부족처럼 "일시적"으로 보이는 실패도 기본적으로는 Unschedulable Queue로 간다. 이 판정 메커니즘은 [2편 - EnqueueExtension과 QueueingHint]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#enqueueextension과-queueinghint)에서 다룬다.

Active Queue에서 파드를 꺼내는 순서는 **우선순위 기반**이며, 동일한 우선순위의 경우 큐에 들어온 순서(FIFO)를 따른다. Backoff Queue는 백오프 만료 시각이 가장 빠른 파드가 맨 위에 온다.

> Unschedulable Queue는 업스트림 코드에서 `unschedulablePods`라는 맵으로 구현되어 있어 풀(pool)이라고도 불린다. 이 시리즈에서는 큐로 통일해 부른다.

Unschedulable Queue의 복귀 조건이 "클러스터 이벤트"라는 것은, **파드 쪽 설정을 고쳐서는 풀리지 않는 상태가 있다**는 뜻이다. 노드 디스크가 차서 `disk-pressure` taint가 붙은 경우가 그렇다. 디스크를 비워 taint가 걷히는 노드 변경이 일어나야 복귀하므로, 그때까지는 재시도가 전부 실패한다([3편 - 노드 압박과 스케줄링]({% post_url 2025-11-05-Kubernetes-Scheduling-03 %}#노드-압박과-스케줄링), 실제 사례는 [MinIO 트러블슈팅]({% post_url 2026-02-24-Dev-Minio-Custom-PVC-Troubleshooting %}#왜-재스케줄링이-안-됐나-추론)).

<br>

### Active Queue 진입 경로

파드가 Active Queue에 들어오는 경로는 세 가지다.

1. **신규 파드**: API Server에 대한 Watch를 통해 `spec.nodeName`이 비어 있는 파드를 감지
2. **Backoff Queue에서 복귀**: 지수 백오프 타이머가 만료된 파드. 즉시 재시도하면 스케줄러에 불필요한 부하가 걸리므로, 실패를 반복할수록 재시도 간격을 늘린다(값은 위 표 참고).
3. **Unschedulable Queue에서 복귀**: 클러스터 이벤트가 발생하여 스케줄링 조건이 달라진 경우. 노드 추가/변경, PV/PVC 생성, 파드 삭제 등이 이에 해당한다.

<br>

### 백그라운드 고루틴과 Move Request

큐 간 파드 이동은 두 가지 백그라운드 고루틴과 Move Request 메커니즘에 의해 이루어진다.

<br>
 
**백그라운드 고루틴** (주기 고정, 설정 불가)

| 고루틴 | 실행 주기 | 역할 |
| --- | --- | --- |
| `flushBackoffQCompleted` | 1초 | 백오프 타이머가 만료된 파드를 Backoff Queue → Active Queue로 이동 |
| `flushUnschedulablePodsLeftover` | 30초 | Unschedulable Queue에 `podMaxInUnschedulablePodsDuration`(기본 **5분**)보다 오래 머문 파드를 Active Queue 또는 Backoff Queue로 이동 (이벤트에 의해 이동되지 못한 잔류 파드 처리) |

여기서 **30초는 검사 주기이고, 이동 대상을 판정하는 체류 기준은 5분**이다. 두 값을 혼동하지 않아야 한다.

`flushUnschedulablePodsLeftover`는 안전망 역할이다. 정상적으로는 클러스터 이벤트에 의한 Move Request가 Unschedulable Queue의 파드를 이동시키지만, 이벤트를 놓치거나 매칭되지 않은 파드가 영원히 갇히는 것을 방지한다. 최악의 경우 파드가 약 5분 30초(5분 초과 체류 + 다음 검사 주기 30초)까지 Unschedulable Queue에 머물 수 있다.

<br>

**Move Request**

클러스터 이벤트(노드 추가/변경, 파드 삭제, PV/PVC 생성, Service 변경 등)가 발생하면 스케줄러가 Move Request를 발행하여 Unschedulable Queue의 파드를 Active Queue 또는 Backoff Queue로 이동시킨다. 스케줄링이 실패한 시점과 Move Request 발행 시점이 같은 스케줄링 사이클이면, 해당 파드는 Unschedulable Queue가 아닌 Backoff Queue로 직접 이동하여 더 빠르게 재시도된다.

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

스케줄링 프로세스의 구체적인 단계(Filter, Score, PostFilter)와 실패 유형별 큐 이동 규칙은 [2편 - 프로세스 결과와 큐 이동 요약]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}#프로세스-결과와-큐-이동-요약)에서 다룬다.



<br>

# 정리

이 글에서 다룬 핵심 내용을 정리한다.

1. **스케줄링은 배치 작업이다.** 파드 생성, 파드 실행, 리소스 할당은 스케줄링이 아니다. 스케줄러는 노드가 결정되지 않은 파드를 감지하여, 스케줄링 요구 사항에 맞는 노드를 필터링하고 스코어링하여 "어느 노드에서 실행할지"를 결정한다.
2. **`kube-scheduler`는 교체 가능하고 다중 운영이 가능하다.** 단일 kube-scheduler에서 다중 프로필을 운영하거나, 별도 스케줄러 프로세스를 배포할 수 있다. 각 스케줄러는 `spec.schedulerName`이 자신의 이름과 일치하는 파드만 처리하며, 하나의 파드를 두고 여러 스케줄러가 경쟁하는 일은 없다.
3. **스케줄러의 판단 기준은 `spec.nodeName`이다.** `status.phase: Pending`이나 `PodScheduled` 조건이 아니다. `spec.nodeName`이 비어 있는 파드만 스케줄링 대상이 된다.
4. **수동 스케줄링은 두 가지 방법이 있다.** 파드 생성 시 `spec.nodeName`을 직접 지정하거나, 이미 생성된 파드에 Binding 오브젝트를 생성한다. 두 방식 모두 스케줄러의 Filter를 건너뛰지만, kubelet이 리소스·nodeSelector·`NoExecute` taint는 다시 검사한다. cordon과 `NoSchedule` taint, 파드 간 배치 규칙은 아무도 검사하지 않는다. DaemonSet은 v1.12부터 NodeAffinity(`matchFields`) 기반으로 전환되어 `kube-scheduler`에 위임되며(v1.17 GA), 이 덕분에 스케줄러의 필터 검증과 일관된 스케줄링 동작이 보장된다.
5. **이미 스케줄링된 파드는 옮길 수 없다.** `spec.nodeName`은 변경 불가 필드이고 쿠버네티스에 마이그레이션 기능이 없으므로, 배치를 바꾸려면 삭제 후 재생성이 유일한 경로다. 선점과 축출도 예외가 아니라 "삭제 후 재생성"이다.
6. **스케줄러는 3개의 큐로 파드를 관리한다.** Active Queue에서만 스케줄링을 시도하고, 실패 시 Backoff Queue 또는 Unschedulable Queue로 분류한 뒤, 조건 충족 시 Active Queue로 복귀시킨다.

파드가 Pending 상태에 빠졌을 때는 먼저 `spec.nodeName`이 비어 있는지 확인하여 스케줄링 문제인지 아닌지를 구분한다. 스케줄링 문제라면 어느 큐에 있는지를 좁혀 나가는데, Events 메시지와 메트릭으로 큐를 판별하는 구체적인 절차는 [5편 - 스케줄링 실패 진단]({% post_url 2025-11-05-Kubernetes-Scheduling-05 %}#스케줄링-실패-진단)에서 다룬다.

<br>

# 참고 링크

- [kube-scheduler - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)
- [Assigning Pods to Nodes - Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Configure Multiple Schedulers - Kubernetes 공식 문서](https://kubernetes.io/docs/tasks/extend-kubernetes/configure-multiple-schedulers/)
- [Feature Gates - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/)
- [Well-Known Labels, Annotations and Taints - Kubernetes 공식 문서](https://kubernetes.io/docs/reference/labels-annotations-taints/)
- [Scheduling queue in kube-scheduler - kubernetes/community](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-scheduling/scheduler_queues.md)
- [KEP-548: Graduate ScheduleDaemonSetPods to GA](https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/548-schedule-daemonset-pods)

<br>
