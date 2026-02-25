---
title:  "[Kubernetes] K3s Split Brain 트러블슈팅 - 1. 상황 복기"
excerpt: K3s 컨트롤 플레인 노드를 재조인하는 과정에서 발생한 Split Brain 문제의 발견과 당시 해결 과정을 복기한다.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - K3s
  - etcd
  - split-brain
  - trouble-shooting
---

<br>

K3s 컨트롤 플레인 노드의 하드웨어를 수리한 뒤, 클러스터에 다시 합류시키려다 Split Brain이 발생했다. `k3s server`를 `--server` 플래그 없이 실행한 것이 원인이었는데, 당시에는 정확히 무엇이 잘못된 건지 몰랐다. 이 글에서는 당시 상황을 복기하고, 어떻게 발견하고 해결했는지를 정리한다.

<br>

# TL;DR

이번 글의 목표는 **K3s Split Brain 발생 상황의 복기와 해결 과정 정리**다.

- **상황**: K3s 삼중화 컨트롤 플레인에서 노드 하나를 수리 후 `--server` 플래그 없이 `k3s server`를 실행
- **문제**: 해당 노드가 기존 클러스터에 복귀하지 않고, 독립된 단독 클러스터를 생성하여 Split Brain 발생
- **해결**: K3s 데이터를 완전히 제거한 뒤, `--server` 플래그를 명시하여 재조인
- **후속**: 정확한 원인(etcd 데이터 소실 → SQLite 폴백)은 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 소스 코드 분석과 재현 실험으로 확인

<br>

# 배경

## 클러스터 전환 이력

원래 단일 서버(embedded SQLite)로 운영하던 K3s 클러스터를, `--cluster-init`을 통해 embedded etcd 기반 삼중화 컨트롤 플레인으로 전환하여 운영하고 있었다. 다만 전환 시점의 정확한 절차가 남아 있지 않아, 당시 systemd unit 파일 구성이나 사용된 플래그 등은 확인할 수 없는 상태였다.

## 하드웨어 장애와 재조인 시도

이 클러스터에서, 컨트롤 플레인 노드 하나(cp-node-c)의 하드웨어에 문제가 생겼다. 하드웨어 수리를 위해 해당 노드의 K3s systemd 서비스를 중단해 두었고, 수리 후 해당 노드를 다시 클러스터에 합류시키려 했다. 이때 systemd 서비스를 재시작하는 대신, 직접 커맨드 라인에서 `k3s server`를 실행했는데, 의도한 대로 동작하지 않았다.

운영 초기에 벌어졌던 정말 미숙한 실수이지만, 이번 글에서는 해당 상황을 복기하고 당시 어떻게 해결했는지 정리한다. 정확한 원인 분석은 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 소스 코드 분석과 재현 실험을 통해 다룬다.

<br>

# 문제: 두 개의 클러스터

## 증상 발견

기존 클러스터의 컨트롤 플레인(cp-node-a)에서 확인했을 때, cp-node-c가 `NotReady` 상태로 표시된다.

```bash
$ kubectl get nodes
NAME       STATUS     ROLES                       AGE    VERSION
cp-node-a  Ready      control-plane,etcd,master   490d   v1.27.9+k3s1
cp-node-b  Ready      control-plane,etcd,master   75d    v1.27.9+k3s1
cp-node-c  NotReady   control-plane,etcd,master   77d    v1.27.9+k3s1
worker-01  Ready      <none>                      340d   v1.27.9+k3s1
worker-02  Ready      <none>                      313d   v1.27.9+k3s1
...
```

그런데 해당 노드(cp-node-c)에서 직접 확인하면, 자기 자신만 `Ready` 상태로 보인다.

```bash
$ kubectl get nodes
NAME      STATUS   ROLES                  AGE   VERSION
cp-node-c Ready    control-plane,master   19h   v1.27.9+k3s1
```

## 상황 정리

```
원래 클러스터 (cp-node-a에서 확인)                 분리된 클러스터 (cp-node-c에서 확인)
├─ cp-node-a (control-plane,etcd,master)      cp-node-c (control-plane,master, 19h)
├─ cp-node-b (control-plane,etcd,master)      └─ 단일 노드: 자기만 보임
└─ cp-node-c (77d, NotReady)
```

하나의 클러스터였던 것이 둘로 분리되어, 각각이 자신이 정상이라고 판단하며 독립적으로 동작하고 있다. 이른바 **Split Brain** 상태다.

## 당시 놓쳤던 의문점

당시에는 "Split Brain이 발생했다"는 사실 자체에 집중하여 빠르게 복구하는 데 초점을 맞췄다. 하지만 복기해 보면, 위 출력에 몇 가지 의문스러운 점이 있다.

- **AGE 19h**: 원래 클러스터에서 cp-node-c의 AGE는 77d인데, 분리된 클러스터에서는 19h다. 기존 데이터를 그대로 가지고 부팅했다면 AGE도 77d여야 하지 않은가?
- **ROLES의 차이**: 원래 클러스터에서는 `control-plane,etcd,master`인데, 분리된 클러스터에서는 `control-plane,master`로 `etcd` 역할이 빠져 있다.
- **다른 노드 부재**: 기존 etcd 데이터를 가지고 부팅했다면, 다른 노드들(cp-node-a, cp-node-b, worker 등)도 NotReady 상태로라도 보여야 하지 않은가?

이 의문점들은 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 분석한다.

<br>

# 배경지식

## K3s 데이터스토어와 다중화

Kubernetes 클러스터의 모든 상태 데이터는 데이터스토어에 저장된다. K3s 단일 서버에서는 embedded SQLite가 기본 데이터스토어다. SQLite는 단일 파일 기반 임베디드 데이터베이스로, 복제 메커니즘이 없어 다중 노드 간 데이터 동기화가 불가능하다. 따라서 컨트롤 플레인을 삼중화하려면 분산 합의가 가능한 데이터스토어가 필요하며, K3s에서는 `--cluster-init` 옵션으로 embedded etcd로 전환하여 이를 지원한다.

## etcd 클러스터와 Raft 합의 알고리즘

etcd를 사용하면 각 컨트롤 플레인 노드가 etcd 멤버가 되어 동일한 데이터의 복제본을 유지한다. etcd는 Raft 합의 알고리즘을 사용하는데, 이 알고리즘의 핵심 개념이 **quorum**이다.

Raft에서 quorum은 **과반수**이며, 공식은 **quorum = ⌊N/2⌋ + 1** (N: 클러스터 멤버 수)이다. N=3이면 2, N=5이면 3이 된다.

- 3개 멤버 클러스터에서 quorum은 2다. 즉, 2개 이상의 멤버가 동의해야 쓰기 작업이 가능하다.
- 1개가 장애나도 나머지 2개가 quorum을 유지하므로, 클러스터가 정상 동작한다.
- 2개가 장애나면 1/3으로 quorum 미달이 되어, 클러스터 전체가 읽기 전용 또는 동작 불가 상태가 된다.

멤버 수에 따른 quorum과 장애 허용 범위를 정리하면 다음과 같다.

| 구성 | quorum | 1개 장애 시 |
| --- | --- | --- |
| 1멤버 | 1/1 | 클러스터 전체 장애 |
| 2멤버 | 2/2 | 클러스터 전체 장애 (동일, 복잡도만 증가) |
| 3멤버 | 2/3 | 1개 장애 허용 |

2멤버는 단일 노드 대비 장애 허용이 전혀 늘어나지 않으면서 복잡도만 높아진다. etcd 공식 문서에서도 2멤버 구성을 권장하지 않는다. 따라서 컨트롤 플레인 다중화 시 최소 3멤버(홀수) 구성이 기본이다. etcd 클러스터 구성 후 서비스 상태·멤버 목록·엔드포인트 상태 확인 등 검증 방법은 [내 손으로 클러스터 구성하기 - Bootstrapping the etcd Cluster]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}#검증)의 검증 섹션을 참고하면 된다. quorum 미달, unhealthy 멤버, Split Brain 등 비정상 시나리오별 진단(`endpoint health` vs `endpoint status`)과 대응은 [etcd 비정상 시나리오별 대응]({% post_url 2026-02-20-Dev-Kubernetes-Etcd-Failure-Scenarios %})을 참고하면 된다.

여기서 중요한 점은, **quorum의 분모는 "현재 응답하는 멤버 수"가 아니라 "클러스터에 등록된 전체 멤버 수"**라는 것이다. 멤버가 장애 등으로 응답하지 않더라도 멤버 리스트에서 자동으로 빠지지 않는다. 멤버 수를 줄이려면 `etcdctl member remove` 같은 명시적인 관리 작업이 필요하다.

## Split Brain

### 정의

Split Brain은 **하나의 클러스터였던 것이 둘 이상의 독립적인 클러스터로 분리되어, 각각이 자기 내부에서는 정상이라고 판단하며 독립적으로 동작하는 상태**를 가리킨다. 엄밀히 말하면, **양쪽 모두 쓰기 작업을 수행하며 데이터가 분기되는 상황**을 의미한다.

### 원인

Split Brain이 발생하는 원인은 다양하다. 네트워크 파티션, 합의 알고리즘 버그(quorum 오판), HA 환경에서의 펜싱 실패(양쪽이 상대를 죽은 것으로 판단), 혹은 **노드 재초기화** 같은 운영 실수 등이 있다. 가장 흔히 거론되는 원인이 네트워크 파티션이다.

### Raft/quorum의 네트워크 파티션 보호 메커니즘

네트워크 파티션이란 네트워크 장애로 인해 클러스터 멤버들이 서로 통신할 수 없는 둘 이상의 그룹으로 나뉘는 것이다. Raft에서 리더는 팔로워들에게 주기적으로 하트비트를 보내고, 팔로워는 리더의 하트비트를 기다린다. 하트비트 응답이 일정 시간 이상 없으면 해당 멤버에 도달할 수 없는 것으로 판단한다.

**Raft 알고리즘을 사용하는 etcd 기반 시스템에서는** 컨트롤 플레인(etcd 멤버)을 홀수(3, 5, 7…)로 구성할 때 네트워크 파티션에 의한 Split Brain이 발생하지 않도록 보장된다. 앞서 설명한 대로 quorum의 분모는 전체 등록 멤버 수이므로, 네트워크 파티션이 발생해도 분모는 변하지 않고 분자(응답하는 멤버 수)만 줄어든다. 홀수로 두면 2 vs 1, 3 vs 2처럼 한쪽만 과반을 갖는 분할만 가능하고, 2 vs 2처럼 양쪽이 똑같이 나뉘는 경우는 없다.

예컨대 3멤버 클러스터에서 네트워크가 2 vs 1로 분리되더라도 항상 한쪽은 다수다.

- 다수 쪽(2/3): quorum 확보, 정상 쓰기 가능
- 소수 쪽(1/3): quorum 미달, 쓰기 불가, 읽기 전용

quorum을 **과반(절반 초과)**으로 두기 때문에, 한 번에 하나의 파티션만 quorum을 가질 수 있어 네트워크 파티션만으로는 "양쪽 모두 쓰기"가 불가능하다.

그렇다면 순차적으로 파티션이 발생해 **3-way 분할**(1:1:1)이 되면 어떻게 될까? 예를 들어 3멤버 클러스터(A, B, C)에서 A-B vs C로 파티션이 발생한 뒤, A-B 사이에서도 파티션이 발생하면 A, B, C 각각 1/3이 되어 모두 quorum 미달이다. 결과는 **전체 쓰기 불가이지, Split Brain이 아니다**. quorum을 만족하는 쪽이 어디에도 없기 때문에, 세 노드 모두 쓰기가 불가능하다. 이것은 "양쪽이 동시에 쓰기를 해서 데이터가 분기되는" Split Brain이 아니다.

Raft는 어떤 파티션 패턴에서도 양쪽이 동시에 write를 commit하는 Split Brain이 발생하지 않도록 보장한다. 다만, 1:1:1처럼 어느 쪽도 quorum을 확보하지 못하면 클러스터 전체가 쓰기 불가 상태가 되어 사실상 서비스가 중단된다. 데이터가 분기되는 것은 막았지만, **가용성(availability)은 포기**한 것이다. 이는 Raft가 CAP 이론에서 CP(Consistency + Partition tolerance)를 선택한 설계이기 때문으로, 파티션 상황에서 일관성을 지키기 위해 가용성을 희생하는 것이 의도된 동작이다.

### 보호가 우회되는 경우: 수동 재초기화 — 이번 케이스

위의 보호는 **같은 Raft 합의 그룹 안에서의 네트워크 파티션**에 대한 것이다. 이번 케이스처럼 **완전히 새로운 독립 클러스터**가 생성되면 상황이 근본적으로 달라진다. 두 시나리오를 비교하면 차이가 명확하다.

<br>

**네트워크 파티션 (같은 Raft 합의 그룹):**

```
하나의 Raft 클러스터
[cp-node-a] ←→ [cp-node-b]    |    [cp-node-c]
         quorum 2/3           |    quorum 미달 1/3
         쓰기 가능              |    쓰기 불가, 읽기 전용
```

양쪽 모두 **같은 Raft 합의 그룹**의 멤버다. 소수 쪽은 quorum을 확보하지 못해 쓰기가 불가능하므로, 양쪽이 동시에 쓰는 **Split Brain이 아니다**.

<br>

**수동 재초기화 (별개의 Raft 합의 그룹) — 이번 케이스:**

```
Raft 클러스터 A (원래)                   Raft 클러스터 B (신규)
[cp-node-a] ←→ [cp-node-b]           [cp-node-c]
         멤버 리스트: {A, B, C}           멤버 리스트: {C}
         quorum 2/3                    quorum 1/1
         쓰기 가능                       쓰기 가능
```

cp-node-c가 **완전히 새로운 독립 Raft 클러스터**를 구성한 것이다. 두 클러스터는 **서로 다른 Raft 합의 그룹**이고, 각자의 합의 그룹 안에서 quorum을 만족한다. 따라서 **양쪽 모두 쓰기가 가능**하며, 이것이 진짜 Split Brain이다.

> 참고: 원래 클러스터(A)의 quorum이 2/3인 이유
> 
> Split Brain이 발생한 시점에 원래 클러스터의 etcd 멤버 리스트에는 여전히 cp-node-c가 남아 있다. cp-node-c가 새 클러스터를 만들었다고 해서 원래 클러스터의 멤버 리스트가 자동으로 줄어들지는 않기 때문이다. `kubectl delete node`나 `etcdctl member remove`로 명시적으로 제거해야 비로소 2/2가 된다. 다만, 2/3이든 2/2이든 quorum(2)을 충족하므로 쓰기가 가능하고, 반대쪽 독립 클러스터도 1/1로 쓰기가 가능하니 **Split Brain이라는 결론은 동일**하다.

| | 네트워크 파티션 | 수동 재초기화 (이번 케이스) |
| --- | --- | --- |
| Raft 클러스터 수 | 1개 (분리되었지만 같은 그룹) | 2개 (완전히 독립) |
| 소수 쪽 쓰기 | 불가 (quorum 미달) | **가능** (자기 클러스터에서 quorum 충족, 1/1) |
| Raft 보호 | 작동 | **우회됨** |
| Split Brain | 아님 | **맞음** |


### 시스템 설계별 차이

지금까지 etcd(Raft 기반) 시스템에서의 네트워크 파티션과 수동 재초기화를 살펴봤다. 좀 더 넓은 시각에서 보면, 네트워크 파티션 시 Split Brain(양쪽 모두 쓰기·데이터 분기)이 발생하는지 여부는 분산 시스템의 설계에 따라 다르다. etcd가 속하는 홀수 멤버 quorum 기반 시스템을 포함해 정리하면 다음과 같다.

- **quorum 기반이 아닌 시스템**: MySQL Master-Master 복제나 합의 없이 동작하는 일부 NoSQL처럼, quorum이 없는 구성에서는 네트워크 파티션 시 **양쪽에서 동시 쓰기가 가능**해 진짜 Split Brain이 발생할 수 있다.
- **홀수 멤버인 quorum 기반 시스템**: etcd(Raft), ZooKeeper(ZAB) 등이 여기에 해당한다. 네트워크 파티션 시 과반을 확보한 쪽만 쓰기가 가능하므로, **양쪽 동시 쓰기에 의한 Split Brain이 발생하지 않는다**.
- **짝수 멤버인 quorum 기반 시스템**: 예를 들어 2노드 etcd에서 네트워크 파티션이 나면 양쪽 모두 1/2로 quorum을 잡지 못해 **양쪽 다 쓰기 불가**가 된다. Split Brain이 아니라 **전체 장애**에 가깝다.
- **수동 재초기화**: 위의 어떤 설계든, 기존 클러스터와 무관한 **별개의 합의 그룹**이 생성되면 각각이 자기 내부에서 quorum을 만족하므로 **독립적으로 쓰기를 수행**하게 되고, 결과적으로 Split Brain이 된다.

<br>

# 추정한 원인

복기를 통해 다음과 같이 원인을 추정했다.

> 하드웨어 수리가 끝난 cp-node-c에서, 기존 K3s 데이터를 정리하지 않은 채 `k3s server`를 `--server` 플래그 없이 실행한 것이 원인이다. K3s가 이 노드를 클러스터의 시작점으로 해석하여, 로컬에 남아 있던 etcd 데이터를 가지고 단독 클러스터로 부팅해 버린 것이다.

이 추정에는 맞는 부분과 재검증이 필요한 부분이 있다. 정확한 원인은 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 K3s 소스 코드 분석과 재현 실험을 통해 확인한다.

<br>

# 해결

Split Brain이 발생하면, 분기된 데이터를 자동으로 합칠 수 없다. etcd(Raft 기반)에는 분기된 데이터를 merge하는 메커니즘이 없기 때문이다. 한쪽을 버려야 한다. 실무적으로는 quorum이 유지된 다수 쪽을 정본(source of truth)으로 선택한다. 이번 복구에서도 소수 쪽(cp-node-c)의 데이터를 버리고, 다수 쪽(cp-node-a, cp-node-b)을 기준으로 복구했다.

## 올바른 제거/재조인 절차

원래 아래와 같이 했어야 한다.

```bash
# 1. Kubernetes 노드 오브젝트 제거 (기존 컨트롤 플레인에서 실행)
kubectl delete node cp-node-c

# 2. etcd 멤버 목록에서도 제거 (기존 컨트롤 플레인에서 실행)
# kubectl delete node는 Kubernetes 오브젝트만 삭제하고 etcd 멤버 정보는 남긴다.
# member list로 cp-node-c의 ID를 확인한 뒤 제거한다.
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  member list -w table

# 위 결과에서 cp-node-c의 ID를 확인한 뒤:
sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  member remove <cp-node-c의_멤버_ID>

# 3. 해당 노드에서 K3s 완전 제거 (cp-node-c에서 실행)
sudo /usr/local/bin/k3s-uninstall.sh
sudo rm -rf /var/lib/rancher/k3s
sudo rm -rf /etc/rancher/k3s

# 4. 데이터가 정리되었는지 확인
ls /var/lib/rancher/k3s/  # 디렉토리 자체가 없어야 정상

# 5. 올바른 플래그로 재조인
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.27.9+k3s1" \
  K3S_URL=https://<컨트롤플레인IP>:6443 \
  K3S_TOKEN=<TOKEN> \
  sh -s - server \
  --server https://<컨트롤플레인IP>:6443
```

`--server`에 지정하는 컨트롤 플레인 노드는 삼중화된 노드 중 어느 것이든 상관없다. etcd 데이터를 공유하고 있기 때문에 결국 같은 클러스터에 조인하게 된다. 실무에서는 로드 밸런서 URL을 사용하거나, 관행적으로 클러스터를 처음 초기화한 노드를 지정하는 경우가 많다.

## 실제 복구 과정

이미 Split Brain이 발생한 상태에서 복구한 과정을 정리한다.

### 1단계: 원래 클러스터에서 분리된 노드 제거

> 분리된 노드에서 서비스가 돌고 있었다면, 바로 제거하면 서비스 중단이 발생할 수 있다. 독립 클러스터에서 실행 중인 워크로드를 먼저 확인하고(`kubectl get pods -A`), 원래 클러스터에 없는 워크로드가 있다면 매니페스트를 백업한 뒤 제거를 진행해야 한다. 다만, Split Brain 상태의 소수 쪽 노드에서 돌던 워크로드는 대부분 원래 클러스터에 이미 재스케줄링되어 있다.

기존 컨트롤 플레인(cp-node-a)에서 실행한다.

```bash
$ kubectl delete node cp-node-c
node "cp-node-c" deleted
```

### 2단계: 분리된 노드에서 K3s 완전 제거

cp-node-c에서 실행한다.

```bash
$ sudo /usr/local/bin/k3s-uninstall.sh
$ sudo rm -rf /var/lib/rancher/k3s/
$ sudo rm -rf /etc/rancher/k3s
```

### 3단계: 클러스터 상태 확인

재조인 전에 기존 클러스터의 etcd 상태를 확인한다. 진단 없이 재조인부터 하면 상황이 더 꼬일 수 있다.

```bash
# 노드 상태 확인 (cp-node-a에서 실행)
$ kubectl get nodes
NAME        STATUS   ROLES                       AGE    VERSION
cp-node-a   Ready    control-plane,etcd,master   490d   v1.27.9+k3s1
cp-node-b   Ready    control-plane,etcd,master   75d    v1.27.9+k3s1
worker-01   Ready    <none>                      340d   v1.27.9+k3s1
...
```

```bash
# etcd 멤버 목록 확인
$ sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  member list -w table
+------------------+---------+------------+----------------------------+----------------------------+
|        ID        | STATUS  |    NAME    |         PEER ADDRS         |        CLIENT ADDRS        |
+------------------+---------+------------+----------------------------+----------------------------+
| aaaaaaaaaaaaaaaa | started | cp-node-b  | https://x.x.x.x:2380      | https://x.x.x.x:2379      |
| bbbbbbbbbbbbbbbb | started | cp-node-a  | https://y.y.y.y:2380      | https://y.y.y.y:2379      |
+------------------+---------+------------+----------------------------+----------------------------+
```

```bash
# etcd 헬스 체크
$ sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  endpoint health --cluster -w table
+----------------------------+--------+-------------+-------+
|          ENDPOINT          | HEALTH |    TOOK     | ERROR |
+----------------------------+--------+-------------+-------+
| https://x.x.x.x:2379       |  true  | 10.399169ms |       |
| https://y.y.y.y:2379       |  true  | 10.207552ms |       |
+----------------------------+--------+-------------+-------+
```

etcd 멤버 2개, 장애 없이 유지되고 있다. 원래 삼중화였으므로 cp-node-c의 멤버 정보가 있어야 하는데, 이미 목록에서 사라져 있다. 이 현상의 원인에 대해서는 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 K3s 소스 코드(`member_controller.go`)를 분석하며 확인한다.

다만, 이 상태에서는 1개만 장애가 나도 quorum을 상실하여 클러스터 전체에 문제가 생기므로, 빠르게 삼중화를 복구해야 한다.

### 4단계: 클러스터 재조인

기존 컨트롤 플레인에서 토큰을 확인한 뒤, cp-node-c에서 재조인한다. 반드시 동일한 K3s 버전으로 설치해야 하며, `--server` 플래그를 명시해야 한다.

```bash
# cp-node-a에서 토큰 확인
$ sudo cat /var/lib/rancher/k3s/server/node-token
K10xxxxx...::server:yyyyyy...

# cp-node-c에서 재조인
$ curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.27.9+k3s1" \
  K3S_URL=https://<cp-node-a IP>:6443 \
  K3S_TOKEN=<TOKEN> \
  sh -s - server \
  --server https://<cp-node-a IP>:6443
```

재조인 후 확인하면, 삼중화 컨트롤 플레인이 정상적으로 복구된 것을 볼 수 있다.

```bash
$ kubectl get nodes
NAME        STATUS   ROLES                       AGE    VERSION
cp-node-a  Ready    control-plane,etcd,master   490d   v1.27.9+k3s1
cp-node-b  Ready    control-plane,etcd,master   75d    v1.27.9+k3s1
cp-node-c  Ready    control-plane,etcd,master   119s   v1.27.9+k3s1
worker-01  Ready    <none>                      340d   v1.27.9+k3s1
...
```

<br>

# 트러블슈팅

재조인 과정이 한 번에 깔끔하게 되지는 않았다. 발생한 이슈들을 정리한다.

## K3s 버전 불일치

`INSTALL_K3S_VERSION`을 지정하지 않으면, 설치 스크립트가 최신 stable 버전을 받아 온다. 기존 클러스터와 버전이 다르면 조인에 실패한다.

```bash
$ curl -sfL https://get.k3s.io | K3S_URL=https://<IP>:6443 \
  K3S_TOKEN=<TOKEN> \
  sh -s - server --server https://<IP>:6443
[INFO]  Finding release for channel stable
[INFO]  Using v1.33.6+k3s1 as release    # 기존 클러스터는 v1.27.9+k3s1
...
Job for k3s.service failed because the control process exited with error code.
```

반드시 기존 클러스터와 동일한 버전을 명시해야 한다.

```bash
INSTALL_K3S_VERSION="v1.27.9+k3s1"
```

## 호스트명으로 조인 시 DNS 실패

`--server` 값에 IP 대신 호스트명을 사용하면, 해당 호스트명의 DNS 해석이 안 될 경우 조인에 실패한다.

```bash
# 로그 확인
$ sudo journalctl -u k3s -n 100 --no-pager
...
level=fatal msg="starting kubernetes: preparing server: failed to get CA certs:
  Get \"https://cp-node-a:6443/cacerts\": dial tcp: lookup cp-node-a: Try again"
```

K3s가 CA 인증서를 가져오기 위해 기존 컨트롤 플레인에 접속을 시도하는데, 호스트명을 IP로 해석하지 못해 실패하는 것이다. 이 경우 `--server` 플래그가 있기 때문에, 혼자 클러스터를 만들지 않고 계속 재시도 루프를 반복한다.

해결은 두 가지다. 호스트명 대신 IP 주소를 직접 쓰거나, 해당 노드의 `/etc/hosts`에 기존 컨트롤 플레인 호스트명과 IP를 등록해 두면 된다.

```bash
# 방법 1: --server에 IP 직접 지정
--server https://<IP주소>:6443

# 방법 2: /etc/hosts에 호스트명 등록 후 기존대로 호스트명 사용
# (재조인 대상 노드에서) /etc/hosts 예시:
# <기존컨트롤플레인_IP>  cp-node-a
```

## 재조인 후 kubectl 인증 에러

재조인 후 cp-node-c에서 `kubectl` 명령을 실행하면, 인증서 에러가 발생할 수 있다.

```bash
$ kubectl get nodes
Unable to connect to the server: tls: failed to verify certificate:
  x509: certificate signed by unknown authority
```

이전 Split Brain 상태에서 사용하던 kubeconfig의 CA 인증서와 현재 클러스터의 CA 인증서가 다르기 때문이다. 재조인 후 새로 생성된 kubeconfig를 복사하면 해결된다.

```bash
$ mv ~/.kube/config ~/.kube/config.old 2>/dev/null
$ mkdir -p ~/.kube
$ sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
$ sudo chown $(id -u):$(id -g) ~/.kube/config
$ kubectl get nodes   # 정상 동작 확인
```

## Private Registry 이미지 풀 실패

기존 클러스터에서 사내 private registry를 사용하고 있었다면, 재조인 후 해당 노드에서 이미지를 가져오지 못할 수 있다. K3s를 완전히 제거하고 재설치했기 때문에, registry 설정이 초기화되었기 때문이다.

```bash
$ kubectl get pods -A --field-selector spec.nodeName=cp-node-c
NAMESPACE    NAME                          READY   STATUS              ...
gpu-operator gpu-feature-discovery-xxxxx   0/2     Init:ImagePullBackOff
...
```

K3s의 private registry 설정은 `/etc/rancher/k3s/registries.yaml`에서 관리한다. 기존 컨트롤 플레인의 설정을 참고하여, 재조인한 노드에도 동일하게 설정한 뒤 K3s를 재시작하면 된다.

```yaml
# /etc/rancher/k3s/registries.yaml
mirrors:
  "docker.io":
    endpoint:
      - "http://<registry주소>:<포트>"
  "<registry주소>:<포트>":
    endpoint:
      - "http://<registry주소>:<포트>"

configs:
  "<registry주소>:<포트>":
    tls:
      insecure_skip_verify: true
```

```bash
$ sudo systemctl restart k3s
```

설정 후 ImagePullBackOff 상태의 Pod가 없는지 확인한다.

```bash
$ kubectl get pods -A | grep -E "ImagePull|ErrImage"
# 출력 없으면 정상
```

<br>

# 남은 의문

당시에는 빠른 복구에 집중했지만, 복기하면서 몇 가지 의문이 남는다.

1. **정확히 어떤 메커니즘으로 독립 클러스터가 생성되었는가?** `k3s server`를 플래그 없이 실행했을 때 K3s 내부에서 어떤 코드 경로를 타는지, etcd 데이터 유무에 따라 동작이 어떻게 달라지는지 확인이 필요하다.

2. **etcd 데이터가 보존된 것인가, 사라진 것인가?** 분리된 클러스터에서 AGE가 19h이고, `etcd` 역할이 없고, 다른 노드가 안 보인다. 이는 기존 etcd 데이터 위에서 부팅한 것이 아니라, 새로운 빈 클러스터를 생성한 것처럼 보인다. 하드웨어 수리 과정에서 데이터가 사라진 것은 아닌지 확인이 필요하다.

3. **etcd 멤버가 자동으로 제거된 것인가, `kubectl delete node`에 의해 제거된 것인가?** 3단계에서 etcd 멤버가 2개만 보인 원인이 K3s의 자동 제거인지, 1단계의 `kubectl delete node`가 트리거한 것인지 확인이 필요하다.

4. **단독 → 삼중화 전환 후 systemd unit에 플래그가 남아 있었는가?** 전환 이력이 남아 있지 않아, 각 컨트롤 플레인의 systemd unit에 `--cluster-init`이나 `--server` 플래그가 있었는지 확인할 수 없다. 플래그가 빠져 있었다면 그 자체가 이번 문제의 원인 중 하나일 수 있다.

이 의문점들을 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 K3s v1.27.9 소스 코드 분석과 재현 실험을 통해 확인한다.

<br>

# 정리

컨트롤 플레인 노드의 제거와 재조인은, 워커 노드에 비해 훨씬 주의가 필요하다.

| 구분 | 워커 노드 | 컨트롤 플레인 노드 |
| --- | --- | --- |
| etcd 멤버 | X | O |
| 상태 데이터 | 없음 | etcd 데이터베이스 |
| 제거 영향 | 없음 | quorum 영향 가능 |
| Split Brain 위험 | 없음 | 있음 |
| 재조인 | 언제든지 가능 | 데이터 정리 필수 |

## 당시의 교훈

이번 사례를 복기하며 당시 얻은 교훈은 다음과 같다. 정확한 원인 분석 후에 보완이 필요한 부분은 [Part 2]({% post_url 2026-02-19-Dev-Kubernetes-Split-Brain-02 %})에서 추가한다.

1. **제거 시 반드시 K3s 데이터를 완전히 정리한다.** `k3s-uninstall.sh` 실행 후 `/var/lib/rancher/k3s`와 `/etc/rancher/k3s` 디렉토리가 남아 있지 않은지 확인한다.
2. **재조인 시 반드시 `--server` 플래그를 명시한다.** 이 플래그가 없으면 K3s는 독립 클러스터를 생성할 수 있다.
3. **재조인 전 etcd 상태를 확인한다.** etcd 멤버 목록과 헬스 상태를 점검한 뒤, 문제가 있으면 [etcd 비정상 시나리오별 대응]({% post_url 2026-02-20-Dev-Kubernetes-Etcd-Failure-Scenarios %})을 참고하여 대응한 후에 재조인을 진행한다.
4. **컨트롤 플레인은 etcd 데이터를 보유하므로**, 제거·재조인 절차를 워커 노드와 동일하게 취급하면 안 된다.
5. **Split Brain은 원래 클러스터에서 감지할 수 없다.** 분리된 노드는 단순히 `NotReady`로만 보인다. 하드웨어 수리 등으로 노드를 재투입할 때는 반드시 `kubectl get nodes`와 `etcdctl member list`를 양쪽에서 확인하여 클러스터 상태가 일치하는지 검증해야 한다.
