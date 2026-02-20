---
title:  "[Kubernetes] Split Brain: K3s 컨트롤 플레인 재조인 트러블슈팅"
excerpt: K3s 컨트롤 플레인 노드를 제거 후 재설치하는 과정에서 발생한 Split Brain 문제의 원인과 해결 과정을 정리한다.
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - K3s
  - k3s
  - etcd
  - split-Brain
  - trouble-shooting
---

<br>

# 배경

삼중화 컨트롤 플레인으로 운영 중인 K3s 클러스터에서, 컨트롤 플레인 노드 하나의 하드웨어에 문제가 생겨 클러스터에서 제거한 상황이 있었다. 하드웨어 수리를 위해 해당 노드의 K3s systemd 서비스를 중단해 두었고, 수리 후 `k3s server` 명령어로 해당 노드를 다시 클러스터에 합류시키려고 했는데, 의도한 대로 동작하지 않았다.

운영 초기에 벌어졌던 정말 미숙한 실수이지만, 이번 글에서는 해당 상황에 대해 복기하고, 원인과 해결에 대해 자세히 정리해 보고자 한다.

<br>

# TL;DR

1. 문제와 해결
   - 컨트롤 플레인 노드 제거 후 재설치 시, `k3s server`를 `--server` 플래그 없이 실행하여 Split Brain 발생
   - 분리된 노드의 K3s 데이터를 완전 제거한 뒤, `--server` 플래그를 지정하여 기존 클러스터에 재조인

2. 원인
   - K3s는 `--server` 플래그 없이 실행하면, 로컬 etcd 데이터를 기반으로 단독 클러스터를 부트스트랩
   - 기존 etcd 데이터가 남아 있는 상태에서 `--server` 플래그 없이 `k3s server` 실행 시, 기존 클러스터와 독립적인 새 클러스터가 생성됨

3. 교훈
   - 컨트롤 플레인 노드 제거 시, 반드시 K3s 데이터를 완전히 정리한 뒤 재설치
   - 재조인 시 반드시 `--server` 플래그를 명시해야 함
   - 워커 노드와 달리, 컨트롤 플레인 노드는 etcd 데이터를 보유하므로 제거/재조인 절차에 더 주의해야 함

<br>

# 문제

기존 클러스터의 컨트롤 플레인에서 확인했을 때, 해당 노드가 `NotReady` 상태로 표시된다.

```bash
$ kubectl get nodes
NAME        STATUS     ROLES                       AGE    VERSION
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
NAME       STATUS   ROLES                  AGE   VERSION
cp-node-c Ready    control-plane,master   19h   v1.27.9+k3s1
```

정리하면 다음과 같은 상황이다.

```
원래 클러스터 (cp-node-a에서 확인)                 분리된 클러스터 (cp-node-c에서 확인)
├─ cp-node-a (control-plane)                  cp-node-c (19h) ← 독립
├─ cp-node-b (control-plane)                  └─ 단일 노드: 자기만 보임
└─ cp-node-c (77d, NotReady) ← Split Brain!
```

하나의 클러스터였던 것이 둘로 분리되어, 각각이 자신이 정상이라고 판단하며 독립적으로 동작하고 있다. 이른바 **Split Brain** 상태다.

<br>

# 배경 지식: etcd와 Split Brain

## etcd 클러스터와 Raft 합의 알고리즘

Kubernetes 클러스터의 모든 상태 데이터는 etcd에 저장된다. 컨트롤 플레인이 삼중화되어 있으면, 각 컨트롤 플레인 노드가 etcd 멤버가 되어 동일한 데이터의 복제본을 유지한다. etcd는 Raft 합의 알고리즘을 사용하는데, 이 알고리즘의 핵심 개념이 **quorum**이다.

- 3개 멤버 클러스터에서 quorum은 2다. 즉, 2개 이상의 멤버가 동의해야 쓰기 작업이 가능하다.
- 1개가 장애나도 나머지 2개가 quorum을 유지하므로, 클러스터가 정상 동작한다.
- 2개가 장애나면 1/3으로 quorum 미달이 되어, 클러스터 전체가 읽기 전용 또는 동작 불가 상태가 된다.

## Split Brain

### 정의

Split Brain은 **하나의 클러스터였던 것이 둘 이상의 독립적인 클러스터로 분리되어, 각각이 자기 내부에서는 정상이라고 판단하며 독립적으로 동작하는 상태**를 가리킨다. 엄밀히 말하면, **전통적으로 양쪽 모두 쓰기 작업을 수행하며 데이터가 분기되는 상황**을 의미한다.

### 원인

Split Brain이 발생하는 원인은 다양하다. 네트워크 파티션, 합의 알고리즘 버그(quorum 오판), HA 환경에서의 펜싱 실패(양쪽이 상대를 죽은 것으로 판단), 혹은 **노드 재초기화** 같은 운영 실수 등으로 인해 `서로 독립된 두 클러스터가 각각 쓰는 현상`이 발생하곤 한다. **가장 흔히 거론되는 원인**이 네트워크 파티션이다.

### Raft/quorum의 보호 메커니즘

그런데 **Raft 알고리즘을 사용하는 etcd 기반 시스템에서는**, 컨트롤 플레인(etcd 멤버)을 홀수(3, 5, 7…)로 구성할 때 네트워크 파티션에 의한 Split Brain이 발생하지 않도록 보장된다. 홀수로 두면 2 vs 1, 3 vs 2처럼 한쪽만 과반을 갖는 분할만 가능하고, 2 vs 2처럼 양쪽이 똑같이 나뉘는 경우는 없다. 

예컨대 3노드 클러스터에서 네트워크가 2 vs 1로만 분리되더라도 항상 한쪽은 다수다.

- 다수 쪽(2/3): quorum 확보, 정상 쓰기 가능
- 소수 쪽(1/3): quorum 미달, 쓰기 불가, 읽기 전용

quorum을 **과반(절반 초과)**으로 두기 때문에, 한 번에 하나의 파티션만 quorum을 가질 수 있어 네트워크 파티션만으로는 "양쪽 모두 쓰기"가 불가능하다. Raft가 정확히 이 문제를 방지하기 위해 설계된 알고리즘이며, 그래서 etcd/Kubernetes 컨트롤 플레인도 홀수 대수 구성을 권장하는 것이다. 2멤버 구성이 비권장인 이유, 순차 파티션(1:1:1), Raft safety 한계 등은 글 말미의 [추가 궁금증](#추가-궁금증)을 참고한다.

### 시스템 설계별 차이

정리하면, Split Brain(양쪽 모두 쓰기·데이터 분기)이 발생하는지 여부는 시스템 설계에 따라 다르다.

- **quorum 기반이 아닌 시스템**: MySQL Master-Master 복제나 합의 없이 동작하는 일부 NoSQL처럼, quorum이 없는 구성에서는 네트워크 파티션 시 **양쪽에서 동시 쓰기가 가능**해 진짜 Split Brain이 발생할 수 있다.
- **짝수 멤버인 quorum 기반 시스템**: 예를 들어 2노드 etcd에서 네트워크 파티션이 나면 양쪽 모두 1/2로 quorum을 잡지 못해 **양쪽 다 쓰기 불가**가 된다. Split Brain이 아니라 **전체 장애**에 가깝다.
- **수동 재초기화**: etcd가 자체적으로 새 클러스터를 부트스트랩하면, 기존 클러스터와 무관한 **별개의 합의 그룹**이 된다. 각각이 자기 내부에서는 quorum을 만족하므로 **독립적으로 쓰기를 수행**하게 되고, 결과적으로 Split Brain이 된다.

## 이번 케이스 적용

이번에 겪은 상황이 개념적으로 Split Brain이라고 볼 수 있는 이유는 다음과 같다.

- **원래 클러스터**(cp-node-a, cp-node-b 쪽)는 cp-node-c를 여전히 etcd 멤버로 등록하고 있지만, 해당 노드를 **NotReady**로만 인식한다.
- **cp-node-c**는 자기 자신만 있는 **새로운 독립 클러스터**를 구성하고 **Ready** 상태로 동작한다.

즉, 동일한 etcd 데이터에서 출발한 두 클러스터가 각각 독립적으로 운영되고 있는 것이다. 둘 다 자기 관점에서는 정상이므로, 정의에 부합하는 Split Brain 상태라 할 수 있다.

이번 케이스는 위 세 가지 중 **수동 재초기화**에 해당한다. `k3s server`를 이용한 **노드 재초기화**로 인해 Raft의 보호 메커니즘을 우회해서 Split Brain이 발생한 것이다. 전통적인 의미에서 가장 흔히 거론되는 네트워크 파티션과는 발생 원인이 다르고, 그래서 엄밀한 의미에서의 Split Brain 상황은 아닐 수도 있지만, 실무에서는 이런 상황도 Split Brain 혹은 isolated cluster라 통칭하기도 한다.


<br>

# 원인

이번 사례의 원인은 명확하다. 하드웨어 수리가 끝난 cp-node-c 노드에서, **기존 K3s 데이터를 정리하지 않은 채 `k3s server`를 `--server` 플래그 없이 실행**한 것이다. K3s는 `--server` 플래그가 없으면 이 노드가 클러스터의 시작점이라고 해석하고, 로컬에 남아 있던 etcd 데이터를 그대로 가지고 단독 클러스터로 부팅해 버렸다.

유사한 증상이 나올 수 있는 경우는 여러 가지가 있다.

- **노드 재조인 과정에서 기존 데이터를 정리하지 않고 K3s를 다시 기동한 경우**: 이번 사례에서 원인으로 확인된 경우다.
- **etcd 데이터 손상·분리**로 인해 일부 멤버만 독립적인 클러스터를 이루는 경우
- **네트워크 파티션**으로 일부 노드가 완전히 격리된 경우 (다만 홀수 quorum 구성이면 한쪽만 쓰기 가능해, 재초기화와는 다른 양상이다)


## K3s의 `k3s server` 부팅 동작

이번 상황은 워커 노드가 아니라 **컨트롤 플레인** 노드 재조인이었다. 워커였다면 `k3s agent --server <URL> --token <TOKEN>`를 쓰기 때문에 `--server`를 명시하는 것이 당연했을 테지만, 컨트롤 플레인이라 `k3s server`를 쓰다 보니 플래그를 빼고 실행하는 실수가 생긴 것이다.

컨트롤 플레인 노드 실행 시 `k3s server`를 이용한 부팅을 사용해야 하는 것은 명확하다. 다만, K3s는 `k3s server` 실행 시 `--server` 플래그의 유무에 따라 동작이 크게 달라진다.

### `k3s server` (플래그 없이)

`--server` 플래그를 주지 않으면 K3s는 이 노드를 **클러스터의 시작점**으로 해석한다.

- **etcd 데이터가 없는 경우**: 새 단일 노드 클러스터를 생성한다. 기존 멤버가 없으므로 Split Brain 위험은 없다.
- **etcd 데이터가 있는 경우**: 그 데이터를 가지고 **단독 클러스터로 부팅**한다. 이번 사례가 여기 해당한다.

K3s가 기존 etcd 데이터를 그대로 쓰는 것은 설계상 의도된 동작이다. 정상 시나리오는 **노드 재부팅 후 K3s 서비스가 자동 기동**될 때다. 컨트롤 플레인 노드 재부팅 후 systemd가 기존에 등록된 K3s 서비스를 그대로 기동하는데, 그 유닛에는 처음 클러스터에 합류했을 때 썼던 `--server`가 이미 들어 있으므로, 기존 etcd 데이터로 이전 상태를 복구한 뒤 다른 멤버와 재합류하는 것이 기대 동작이다. 매번 스냅샷을 수동으로 복원하는 부담을 줄이기 위해, K3s는 “기존 데이터가 있으면 이어가기”를 기본으로 둔 것이다.

문제는 **노드 재조인** 시다. 기존 etcd 데이터가 남은 상태에서 `--server` 없이 `k3s server`만 실행하면, K3s는 “재부팅 후 복귀”와 “이 노드가 클러스터의 시작점”을 구분하지 못한다. `--server`가 없으면 K3s는 **조인할 대상을 두지 않고**, 로컬 데이터만으로 단일 클러스터를 부트스트랩하는 쪽으로 간다. 즉, 다른 멤버의 peer URL로 연결을 시도하다 실패한 뒤 단독으로 돌아선 것이 아니라, **처음부터 “나 혼자 시작”으로 분기**된다. K3s가 etcd를 기동할 때 `--server`가 없으면 단일 멤버로 재구성(force-new-cluster에 가까운 경로)하는 로직을 타기 때문에, 기존 멤버 목록이 있어도 무시되고 자기 자신만 멤버인 새 클러스터로 부팅한다.

**이번에 겪은 상황**이 바로 위에서 설명한 문제 상황이다. 하드웨어 수리로 인해 systemd 서비스를 중단해 둔 상태였고, 수리 후 다시 기동할 때 `--server` 플래그 없이 `k3s server`를 실행했다. 결과적으로 K3s가 이 노드를 "클러스터의 시작점"으로 인식해 단독 클러스터로 부팅해 버린 것이다.

### `k3s server --server <URL> --token <TOKEN>`

기존 클러스터에 **조인**하는 모드다. 지정한 서버로 접속해 클러스터에 합류를 시도한다. 조인에 실패하면 에러를 내고 재시도 루프를 돌 뿐, 혼자 새 클러스터를 만들지 않는다. 다만 기존 etcd 데이터가 남아 있으면 member ID 불일치 등으로 조인이 실패하는 경우가 많아, 데이터를 정리한 뒤 다시 조인하는 것이 일반적이다.

### `k3s server --cluster-init`

**새 HA 클러스터의 첫 번째 노드**로 기동할 때 쓰는 옵션이다. **기존 etcd 데이터가 있으면 이 플래그는 완전히 무시되고**, 해당 노드는 기존 멤버로서 정상 기동한다. etcd 데이터가 없을 때만 새 클러스터를 초기화한다.
- [K3s Discussion #4395](https://github.com/k3s-io/k3s/discussions/4395#discussioncomment-1590317)
- [K3s Discussion #9788](https://github.com/k3s-io/k3s/discussions/9788#discussioncomment-8920420)

따라서 이미 클러스터에 조인한 노드의 systemd unit에 `--cluster-init`이 계속 남아 있어도 안전하며, 실제로 K3s 설치 스크립트가 생성하는 서비스 파일이 이 형태다.

### 정리

etcd 데이터 디렉토리 존재 여부와 실행 플래그 조합에 따른 동작은 다음과 같다.

| 조건 | etcd 데이터 있음 | etcd 데이터 없음 |
| --- | --- | --- |
| `k3s server` (플래그 없음) | 기존 데이터로 단독 클러스터 부팅 (Split Brain 위험) | 새로운 단일 노드 클러스터 생성 |
| `k3s server --server <URL> --token <TOKEN>` | 대부분 조인 실패 (etcd member ID mismatch). 데이터 정리 후 재시도 필요 | 해당 클러스터에 정상 조인 |
| `k3s server --cluster-init` | 플래그가 무시되고 기존 멤버로서 정상 기동 (Split Brain 위험 없음) | 새로운 HA 클러스터의 첫 번째 노드로 초기화 |
| `k3s server --cluster-reset` | etcd 클러스터를 단일 멤버로 리셋. 다른 멤버 정보 제거, 자기 데이터만 보존 | 의미 없음 |

핵심은 `--server` 플래그다.

- `--server`가 **있으면**: 조인 실패 시 에러와 재시도만 반복하고, 단독 클러스터를 만들지 않는다.
- `--server`가 **없으면**: 로컬 데이터만으로 단독 부팅을 시도하므로, 기존 데이터가 있을 때 Split Brain 위험이 있다.

<br>

# K3s vs kubeadm: 설계 철학의 차이

앞 절에서 본 것처럼, `--server` 없이 기존 etcd 데이터가 남은 상태에서 실행하면 K3s는 "재부팅 후 복귀"와 "클러스터 시작점"을 구분하지 못하고 단독 클러스터로 부팅해 버린다. kubeadm의 경우, 이런 상황에 대한 안전 장치가 더 엄격하다. `kubeadm init` 시 기존 etcd 데이터(`/var/lib/etcd/member`)가 존재하면 에러를 내고 중단하고, `kubeadm join` 시 반드시 토큰과 discovery 정보를 명시해야 한다.

| 비교 | K3s | kubeadm |
| --- | --- | --- |
| 기존 etcd 데이터 + 재시작 | 단독 부팅 허용 | 에러 + 중단 |
| 조인 vs 초기화 구분 | `--server` 유무로만 | `init` / `join` 명령 자체가 다름 |
| 안전장치 | 최소한 | 검증·안전장치 다수 |
| 설계 철학 | 단순성, 자동 복구 | 명시성, 안전성 |

K3s는 단순성을 최우선으로 설계된 경량 배포판이기 때문에, 이런 검증을 생략한 대가로 Split Brain 위험을 안고 있다. kubeadm이었다면 기존 etcd 데이터가 있는 상태에서 `kubeadm init`을 시도하면 에러로 중단되었을 것이다.

<br>

# Split Brain 시 데이터는 어떻게 되는가

cp-node-c이 독립 클러스터로 재시작될 때, 기존 etcd 데이터를 버리는 것이 아니라 그 위에서 다시 시작한다. 흐름을 정리하면 다음과 같다.

1. **이전 상태**: cp-node-c은 삼중화 etcd 멤버였으므로, `/var/lib/rancher/k3s/server/db/` 안에 전체 클러스터 상태의 복제본이 있었다 (노드 목록, Pod, Service, ConfigMap 등 전부).
2. **`k3s server` 재시작 시**: K3s가 기존 etcd 데이터를 발견하고, `--server` 플래그가 없으므로 단일 멤버 클러스터로 부트스트랩한다.
3. **분기(fork) 발생**: 이 시점부터 양쪽이 각자의 방향으로 데이터를 쌓아 나간다.
    - 원래 클러스터(cp-node-a, cp-node-b): 새로운 Pod 스케줄링, Deployment 업데이트 등 계속 진행
    - cp-node-c 독립 클러스터: 혼자서 자기 노드에 대한 상태만 업데이트

분기점 이전의 데이터는 동일하지만, 이후부터 양쪽이 완전히 갈라진다. etcd(Raft 기반)에는 분기된 데이터를 자동으로 합치는 메커니즘이 없으므로, 한쪽을 버려야 한다. 실무적으로는 quorum이 유지된 다수 쪽을 정본으로 선택하는 것이 일반적이다.


<br>

# 해결

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

> 데이터를 남긴 채 재조인하는 것도, 비권장이지만 가능은 한 방법이다.

## 실제 복구 과정

이미 Split Brain이 발생한 상태에서 복구한 과정을 정리한다.

### 1단계: 원래 클러스터에서 분리된 노드 제거

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

etcd 멤버 2개, 장애 없이 유지되고 있다. 원래 삼중화였으므로 cp-node-c의 멤버 정보가 있어야 하는데, 이미 목록에서 사라져 있다. 

아쉽게도 당시 상황에 대한 정확한 확인이 남아 있지 않아 단정할 수는 없지만, K3s가 `--server` 없이 재기동될 때 내부적으로 force-new-cluster에 가까운 경로를 타면서, 기존 etcd 멤버 정보를 정리하고 자기 자신만 남긴 단독 클러스터를 구성한 것으로 추정된다. 이에 대한 일반론은 [etcd 비정상 시나리오별 대응]({% post_url 2026-02-20-Kubernetes-Etcd-Failure-Scenarios %})의 시나리오 3을 참고한다.

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

K3s가 CA 인증서를 가져오기 위해 기존 컨트롤 플레인에 접속을 시도하는데, 호스트명을 IP로 해석하지 못해 실패하는 것이다. 이 경우 `--server` 플래그가 있기 때문에, 혼자 클러스터를 만들지 않고 계속 재시도 루프를 반복한다. 이것이 `--server` 플래그의 안전 장치가 작동하는 모습이다.

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

# 추가 궁금증

## 2멤버 etcd 클러스터는 가능한가

기술적으로는 가능하다. `--initial-cluster`에 2개 멤버만 지정하면 된다.

quorum 계산은 ⌈(2+1)/2⌉ = 2이므로, **두 멤버가 모두 살아 있어야 쓰기가 가능**하다. 하나라도 죽으면 즉시 quorum 상실이다.

문제는 단일 노드(N=1, quorum=1)보다 오히려 나쁠 수 있다는 점이다.

| 구성 | quorum | 1개 장애 시 |
| --- | --- | --- |
| 1멤버 | 1/1 | 클러스터 전체 장애 |
| 2멤버 | 2/2 | 클러스터 전체 장애 (동일, 복잡도만 증가) |
| 3멤버 | 2/3 | 1개 장애 허용 |

2멤버는 단일 노드 대비 장애 허용이 전혀 늘어나지 않으면서 복잡도만 높아진다. etcd 공식 문서에서 2멤버 구성을 명시적으로 권장하지 않는 이유가 이것이다. Kubernetes 컨트롤 플레인을 짝수(2, 4)로 구성하지 말라는 권고도 같은 맥락이다. 굳이 2멤버로 구성할 수는 있지만, 장애 허용 측면에서 이점이 없어 의미 있는 선택지는 아니다.

## 1:1:1로 나뉘는 게 가능한가

"홀수면 한쪽만 과반"은 **2-way 파티션**(2 vs 1, 3 vs 2)을 전제한다. 그렇다면 순차적으로 파티션이 발생해 **3-way 분할**(1:1:1)이 되면 어떻게 될까?

예를 들어 3멤버 클러스터(A, B, C)에서:

1. **1단계**: A-B vs C로 파티션 → A-B 쪽이 quorum(2/3) 확보, 리더 선출. C는 quorum 미달.
2. **2단계**: A-B 사이에서도 파티션 발생 → A, B, C 각각 1/3, 모두 quorum 미달.

결과는 **전체 쓰기 불가이지, Split Brain이 아니다**. 기존 리더(B였다면)도 quorum의 ACK를 얻지 못해 write를 commit할 수 없고, 나머지 노드들도 candidate가 되지만 vote를 과반 얻지 못해 리더 선출이 안 된다.

즉, Raft는 어떤 파티션 패턴에서도 "양쪽이 동시에 write를 commit하는" Split Brain이 발생하지 않는다. vote와 write commit 모두 과반 ACK를 요구하고, 과반은 중복될 수 없기 때문이다. 다만, 1:1:1 상황에서는 **가용성(availability)을 포기**하게 된다. Raft는 CAP 이론에서 CP(Consistency + Partition tolerance)를 선택하는 설계이므로, 파티션 상황에서 consistency를 지키기 위해 availability를 희생하는 것이 의도된 동작이다.

| 파티션 패턴 | 결과 |
| --- | --- |
| 2 vs 1 | 2쪽만 쓰기, 1쪽은 읽기 전용 |
| 1 vs 1 vs 1 (순차 파티션) | 전체 쓰기 불가, Split Brain 없음 |
| 수동 재초기화 (이번 케이스) | Raft 우회, Split Brain 발생 가능 |

다만, Raft의 safety guarantee가 완벽한 것은 아니다. 리더가 파티션으로 분리된 사실을 감지하지 못하는 짧은 구간에서 stale read나 lost write가 발생할 수 있고, 알고리즘 자체가 아닌 구현체의 버그로 safety가 깨질 수도 있다. 이들은 Split Brain과는 다른 문제이므로 여기서는 다루지 않는다.

## 원래 클러스터에서 Split Brain을 감지할 수 있는가

감지할 수 없다. 원래 클러스터 관점에서 보면, 해당 노드는 단순히 `NotReady` 상태일 뿐이다. 노드가 꺼졌든, 네트워크가 끊겼든, 독립 클러스터를 구성했든, 원래 클러스터 입장에서는 그저 통신이 안 되는 노드일 뿐이다.

## Split Brain 데이터를 합칠 수 있는가

자동으로 합쳐지지 않는다. etcd(Raft 기반)에는 분기된 데이터를 merge하는 메커니즘이 없다. 한쪽을 버려야 한다. 실무적으로는 quorum이 유지된 다수 쪽을 정본(source of truth)으로 선택한다. 만약 양쪽 모두에서 중요한 변경이 있었다면, 한쪽을 정본으로 잡은 뒤 다른 쪽의 변경사항을 kubectl로 하나씩 다시 적용해야 한다.

실제로 이번 상황에서도 Split Brain으로 동작한 소수 쪽 cp-node-c의 데이터를 버렸다. 다행히 이번 상황에서는 cp-node-c가 19시간 동안 혼자 돌았을 뿐, 실제 워크로드 변경이 거의 없었기 때문에 소수 쪽 데이터를 그냥 버려도 문제가 없었다.

## 재조인 시 다른 컨트롤 플레인 노드를 지정해도 되는가

된다. 삼중화된 컨트롤 플레인 중 어느 노드를 `--server`로 지정해도, etcd 데이터를 공유하고 있기 때문에 결국 같은 클러스터에 조인하게 된다.

다만, 실무에서는 로드 밸런서 URL을 사용하거나, 관행적으로 클러스터를 처음 초기화한 노드를 지정하는 경우가 많다.

## 분리된 노드에서 서비스가 돌고 있었다면

바로 제거하면 서비스 중단이 발생할 수 있다. 이 경우 독립 클러스터에서 실행 중인 워크로드를 먼저 확인하고(`kubectl get pods -A`), 원래 클러스터에 없는 워크로드가 있다면 매니페스트를 백업한 뒤 제거를 진행해야 한다.

다만, Split Brain 상태의 소수 쪽 노드에서 돌던 워크로드는 원래 클러스터의 스케줄러가 관리하지 않는 상태이므로, 대부분 원래 클러스터에 이미 같은 워크로드가 재스케줄링되어 있다.

## 잔여 데이터를 삭제하지 않고 재조인하면

대부분 조인에 실패한다. 기존 etcd 데이터의 member ID가 현재 클러스터와 맞지 않기 때문이다.

```
FATAL etcd member add failed: etcdserver: re-configuration failed due to not enough started members
```

운이 좋으면 재조인이 되는 경우도 있지만, 데이터 정합성 문제가 발생할 위험이 있으므로 권장하지 않는다. 반드시 `k3s-uninstall.sh` 실행과 데이터 디렉토리 삭제 후 재조인하는 것이 안전하다.

## etcd 상태가 비정상일 때

재조인 전에 `member list`, `endpoint health` 등으로 etcd 상태를 확인해야 한다. etcd가 비정상일 때의 대표 시나리오(멤버 unhealthy, quorum 상실, Split Brain, member ID mismatch)와 복합 케이스에 대한 대응은 별도 글로 정리하였다.

- [etcd 비정상 시나리오별 대응]({% post_url 2026-02-20-Kubernetes-Etcd-Failure-Scenarios %})

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

> 컨트롤 플레인을 세심(?)하게 다루지 않고, 무작정 `k3s server`로 초기화해버리면, 이 글에서와 같은 문제를 겪게 된다. 

## 교훈

이번 사례를 복기하며 얻은 교훈은 다음과 같다.

1. **제거 시 반드시 K3s 데이터를 완전히 정리한다.** `k3s-uninstall.sh` 실행 후 `/var/lib/rancher/k3s`와 `/etc/rancher/k3s` 디렉토리가 남아 있지 않은지 확인한다.
2. **재조인 시 반드시 `--server` 플래그를 명시한다.** 이 플래그가 없으면 K3s는 단독 클러스터를 부트스트랩할 수 있어 Split Brain 위험이 있다.
3. **재조인 전 etcd 상태를 확인한다.** etcd 멤버 목록과 헬스 상태를 점검한 뒤, 문제가 있으면 [etcd 비정상 시나리오별 대응]({% post_url 2026-02-20-Kubernetes-Etcd-Failure-Scenarios %})을 참고하여 해당 시나리오에 맞게 대응한 후에 재조인을 진행한다.
4. **컨트롤 플레인은 etcd 데이터를 보유하므로**, 제거·재조인 절차를 워커 노드와 동일하게 취급하면 안 된다.
