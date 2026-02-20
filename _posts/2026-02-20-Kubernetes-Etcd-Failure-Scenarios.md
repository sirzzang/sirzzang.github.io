---
title:  "[Kubernetes] etcd 비정상 시나리오별 대응"
excerpt: K3s 삼중화 클러스터에서 etcd 멤버가 비정상일 때의 대표 시나리오와 대응 방법을 정리한다.
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - K3s
  - etcd
  - trouble-shooting
---

<br>

# 배경

이 글은 [K3s 컨트롤 플레인 재조인 트러블슈팅]({% post_url 2026-02-19-Kubernetes-Split-Brain %}) 글에서 etcd 비정상 시나리오 부분을 분리한 것이다. K3s 삼중화 컨트롤 플레인(3멤버 etcd) 환경에서, 재조인 전 etcd 상태가 비정상일 때의 대표 시나리오와 대응 방법을 정리한다.

Split Brain의 원인과 해결 과정, K3s의 `k3s server` 부팅 동작 등에 대해서는 위 글을 참고한다.

<br>

# TL;DR

아래 표는 **Raft 멤버십/토폴로지 관점**의 주요 시나리오만 다룬다. 재조인 전 점검 맥락에서는 이 범위로 충분하지만, etcd 운영 전반의 모든 장애 케이스를 다루는 것은 아니다.

| 시나리오 | 증상 | 쓰기 가능 여부 | 핵심 대응 |
| --- | --- | --- | --- |
| 1. 멤버 1개 unhealthy | `endpoint health`에서 1개 `false` | O (quorum 2/3 유지) | 복구 시도 후, 불가 시 `member remove` → 빠르게 재조인 |
| 2. 3멤버 중 2개 unhealthy | quorum 미달, API Server 쓰기 실패 | X | 노드 복구 시도 → 불가 시 `--cluster-reset` 응급 조치 |
| 3. Split Brain | 분리된 노드가 독립 클러스터 운영 | O (원래 클러스터 2/3) | 분리 노드 제거 → 데이터 정리 → 재조인 |
| 4. member ID mismatch | 로그에 `member ID mismatch` | O (healthy) | revision + RAFT TERM 확인 → 스냅샷 복구 검토 |
| 복합 | Split Brain + quorum 상실 | X | quorum 먼저 확보 → 이후 Split Brain 대응 |

핵심 원칙: **"쓰기가 가능한 클러스터를 먼저 확보"**한다. Split Brain 복구(멤버 제거, 재조인)를 포함한 모든 클러스터 변경 작업은 etcd 쓰기를 필요로 하기 때문이다. 인프라/운영 레벨 장애(디스크 풀, 인증서 만료 등)는 [기타 케이스](#기타-케이스)를 참고한다.

<br>

# 배경 지식

## etcdctl endpoint health vs endpoint status

etcd 상태 진단에 사용하는 두 명령어는 목적이 다르다.

### `endpoint health`

각 엔드포인트에 경량 요청을 보내 **응답 가능 여부**(true/false)와 응답 시간을 확인한다. "이 멤버가 살아 있는가"를 빠르게 판단할 때 사용한다.

```bash
# ETCDCTL_API=3: etcd API v3 사용
# --endpoints: 접속할 etcd 서버 주소 (로컬 K3s etcd)
# --cacert: TLS 검증용 CA 인증서 (서버 인증서 검증)
# --cert: 클라이언트 인증용 인증서
# --key: 클라이언트 인증용 개인키
$ sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  endpoint health --cluster -w table
+----------------------------+--------+-------------+-------+
|          ENDPOINT          | HEALTH |    TOOK     | ERROR |
+----------------------------+--------+-------------+-------+
| https://x.x.x.x:2379      |   true | 10.399169ms |       |
| https://y.y.y.y:2379      |   true | 10.207552ms |       |
+----------------------------+--------+-------------+-------+
```

### `endpoint status`

각 엔드포인트의 **상세 상태 메타데이터**를 반환한다. DB 크기, 리더 여부, Raft index, **Raft term**, **revision** 등이 포함된다. 데이터 정합성이나 리더 선출 상태를 확인할 때 사용한다.

```bash
$ sudo ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt \
  --cert=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  --key=/var/lib/rancher/k3s/server/tls/etcd/server-client.key \
  endpoint status --cluster -w table
```

정리하면, `endpoint health`로 먼저 "살아 있는가"를 확인하고, 이상이 있으면 `endpoint status`로 "어떤 상태인가"를 확인하는 순서로 진단한다.

### etcd 쿼럼(quorum)

etcd는 Raft 합의 알고리즘을 사용하며, 쓰기(로그 복제)를 수행하려면 **쿼럼(quorum)**을 만족해야 한다.

- **기준이 되는 N**: 클러스터 **멤버 수 N**은 `etcdctl member list`에 등록된 멤버 수이다. unhealthy 멤버라도 `member remove`로 제거하기 전까지는 N에 포함된다. 즉, "지금 응답하는 멤버 수"가 아니라 "member list에 있는 멤버 수"가 N이다.
- **쿼럼 계산**: 쿼럼 = 과반수 = ⌈(N+1)/2⌉. 따라서 N=3이면 쿼럼 2, N=5이면 쿼럼 3이다.
- **시나리오 1과의 관계**: 3개 중 1개만 unhealthy인 경우, N=3·쿼럼=2이고, 정상 응답하는 멤버가 2개이므로 쿼럼 충족 → **쓰기 가능**하다. `member remove`를 실행해 비로소 해당 멤버가 list에서 빠지면 N=2가 되고, 쿼럼도 2가 되어 남은 멤버 중 1개만 장애나도 쓰기 불가가 된다.


**etcd 클러스터가 쿼럼을 잃으면** 쓰기가 불가능해진다.
- **쓰기 실패**: `kubectl apply`, `kubectl delete`, Pod 생성 등 etcd에 쓰기가 필요한 모든 작업이 타임아웃 또는 에러
- **읽기**: kube-apiserver의 **watch cache**에 남아 있는 데이터에 대해서는 `kubectl get nodes`, `kubectl get pods` 등이 응답할 수 있다. 다만 이는 캐시된 데이터이므로 최신 상태를 보장하지 않으며, API Server가 재시작되면 캐시도 사라진다.

<br>

## K3s etcd 스냅샷 백업

K3s는 기본적으로 etcd 스냅샷을 자동으로 생성한다.

- **기본 스냅샷 경로**: `/var/lib/rancher/k3s/server/db/snapshots/`
- **스냅샷 주기**: 기본 12시간 (`--etcd-snapshot-schedule-cron`으로 변경 가능)
- **보관 개수**: 기본 5개 (`--etcd-snapshot-retention`으로 변경 가능)

스냅샷 유무에 따라 복구 경로가 달라진다.

- **스냅샷 있음**: `k3s server --cluster-reset --cluster-reset-restore-path=<경로>`로 특정 시점의 데이터를 복원할 수 있다. 현재 데이터가 손상되었거나, 특정 시점으로 롤백해야 할 때 유용하다.
- **스냅샷 없음**: 현재 살아 있는 노드의 데이터만으로 복구해야 한다. `--cluster-reset`은 현재 데이터 기준으로 단일 노드 리셋만 가능하다.

재조인이나 복구 작업 전에 반드시 스냅샷 존재 여부를 확인하고, 가능하면 수동 스냅샷을 한 번 더 생성해 두는 것이 안전하다.

```bash
# 스냅샷 존재 여부 확인
$ ls /var/lib/rancher/k3s/server/db/snapshots/

# 수동 스냅샷 생성
$ sudo k3s etcd-snapshot save --name manual-backup
```

<br>

# 시나리오별 대응

아래 내용은 모두 K3s 삼중화 컨트롤 플레인(3멤버 etcd 클러스터)을 전제로 한다. etcdctl 명령어에는 매번 TLS 인증서 플래그가 필요하지만, 가독성을 위해 이하에서는 생략한다. 실제 실행 시에는 [위 배경 지식 섹션](#배경-지식)의 예시를 참고한다.

## 시나리오 1: 멤버 3개 중 1개 unhealthy

`member list`에는 3명이 보이지만, `endpoint health`에서 한 멤버만 `false`인 경우다. quorum(2/3)은 유지되므로 **쓰기는 가능**하다.

### 대응

먼저 해당 멤버의 복구를 시도한다. 복구가 불가능하다고 판단되면, 해당 멤버를 etcd 클러스터에서 제거한다.

### 복구 불가 판단 기준

아래 조건들에 해당하면, 해당 노드의 하드웨어/OS/디스크 수준 문제로 판단하고 `member remove`로 전환한다.

- etcd 로그에서 `failed to reach peer`, heartbeat timeout 등이 **반복적으로** 나타남
- K3s 서비스 재시작(`systemctl restart k3s`) 후에도 `endpoint health`가 계속 `false`
- `etcdctl defrag`(디스크 단편화 해소) 시도 실패
- 스냅샷 복원 시도 실패


```bash
# 기존 컨트롤 플레인에서 실행. unhealthy 멤버의 ID 사용
$ sudo etcdctl member remove <unhealthy멤버_ID>
```

제거 후에는 해당 노드에서 K3s 데이터를 정리한 뒤 `--server`를 지정해 재조인한다.

> **주의**: `member remove` 후 클러스터는 **2멤버 상태**가 된다. 이 상태에서는 quorum이 2이므로, 남은 멤버 중 **1개만 장애나도 즉시 클러스터 전체 장애**가 된다. 가능한 한 빠르게 삼중화를 복구해야 한다.

## 시나리오 2: 3멤버 클러스터에서 2멤버 unhealthy

원래 3멤버 etcd 클러스터에서, 2개 멤버가 unhealthy(`endpoint health`에서 응답 없음 또는 `false`)하여 1개만 살아 있는 상황이다. 3멤버 중 1개(살아 있는 노드)만 정상이므로 1/3으로 **quorum 미달**이 되고, 클러스터가 **쓰기 불가** 상태가 된다. 쿼럼 상실 시 동작(쓰기 실패·읽기/watch cache)은 [배경 지식의 etcd 쿼럼](#etcd-쿼럼quorum)을 참고한다.

### 죽은 노드 복구 시도 (우선)

먼저 죽어 있는 노드의 복구를 시도한다.

```bash
# 죽어 있는 노드에 접속해서
$ sudo systemctl restart k3s
# 또는 재부팅
$ sudo reboot
```

2-3회 재시작을 시도한 뒤에도 peer 연결이 회복되지 않으면(로그에서 `failed to dial`, `connection refused` 지속), 해당 노드의 복구가 불가능한 것으로 판단한다.

### 응급 조치 (복구 불가 시)

살아 있는 노드에서 `--cluster-reset`으로 단일 노드 클러스터로 재시작한다.

```bash
# 살아 있는 노드에서
$ sudo k3s server --cluster-reset
# 경고: etcd 클러스터가 단일 노드로 재초기화됨
```

`--cluster-reset`의 내부 동작:

1. 기존 etcd member list를 **모두 제거**하고, 자기 자신만 남긴다
2. 새로운 **Raft cluster ID**를 생성한다 (기존 클러스터와는 완전히 다른 합의 그룹이 됨)
3. 자기가 보유한 etcd 데이터는 보존하되, 단일 멤버로 재구성한다

이것은 시나리오 1의 `member remove` + 재조인과는 **근본적으로 다른 복구 경로**다. `member remove`는 기존 Raft 클러스터 내에서 멤버 하나를 제거하는 것이지만, `--cluster-reset`은 **기존 클러스터 자체를 버리고 새로운 클러스터를 만드는 것**이다. 따라서 이후 다른 노드들은 **반드시 etcd 데이터를 완전히 삭제한 뒤** `--server`를 지정해 재조인해야 한다. 기존 데이터를 가지고 합류하면 Raft cluster ID 불일치로 실패한다.

> **주의**: `--cluster-reset`은 **권장되지 않는 응급 조치**다. 데이터 손실 위험이 있으므로, 실행 전에 스냅샷을 확보하는 것이 좋다. 스냅샷이 있다면 `--cluster-reset-restore-path` 옵션으로 특정 시점의 데이터를 복원할 수도 있다.

## 시나리오 3: Split Brain

한 노드가 기존 클러스터와 별개의 etcd 클러스터로 부팅해, 원래 클러스터에는 2개 멤버만 보이고, 분리된 노드는 독립 클러스터로 동작하는 상황이다.

대응은 [Split Brain 트러블슈팅 글의 "해결" 섹션]({% post_url 2026-02-19-Kubernetes-Split-Brain %}#해결)과 동일하다. 원래 클러스터에서 해당 노드 제거 → 분리된 노드에서 K3s 완전 제거 → `--server` 지정 후 재조인.

### member list에서 분리된 노드가 이미 없는 경우

원래 클러스터의 `etcdctl member list`에서 분리된 노드가 이미 제거되어 있는 경우가 있을 수 있다. 이 경우 `member remove` 단계를 건너뛸 수 있다.

member list에 분리된 노드가 없을 수 있는 경우는 다음과 같다.

- **K3s의 force-new-cluster 경로**: K3s가 `--server` 없이 재기동될 때 내부적으로 force-new-cluster에 가까운 경로를 탄다. 이 과정에서 기존 etcd 멤버 정보를 정리하고 자기 자신만 남긴 단독 클러스터를 구성할 수 있다. 이 경우, 원래 클러스터 쪽에서도 해당 멤버가 자동으로 제거되었을 가능성이 있다.
- **이전에 수동으로 `member remove`를 실행한 경우**: 관리자가 이미 해당 노드를 etcd 멤버에서 제거했을 수 있다.

참고로, `kubectl delete node`는 Kubernetes 노드 오브젝트만 삭제하며, etcd 멤버 정보는 별도로 `etcdctl member remove`를 실행해야 제거된다. 따라서 `kubectl delete node`만으로는 member list에서 사라지지 않는다.

> 실제로 [Split Brain 트러블슈팅]({% post_url 2026-02-19-Kubernetes-Split-Brain %}) 글의 복구 과정에서도 member list에 분리된 노드가 보이지 않았다. 당시 정확한 확인이 남아 있지 않아 단정할 수는 없지만, K3s가 `--server` 없이 재기동될 때 force-new-cluster 경로를 타면서 기존 멤버 정보가 정리된 것으로 추정된다.

## 시나리오 4: member ID mismatch

`member list`는 정상이고 `endpoint health`도 `true`인데, etcd 로그에 `member ID mismatch` 등의 에러가 나오는 경우다.

### 발생 원인

- **데이터 미정리 강제 재조인**: 기존 etcd 데이터를 삭제하지 않고 `--server`로 재조인을 시도한 경우. 클러스터가 새 member ID를 부여했는데, 해당 노드의 etcd 데이터에는 여전히 이전 member ID가 남아 있어 불일치가 발생한다.
- **스냅샷 복원 시점 불일치**: 스냅샷 복원 시, 해당 스냅샷이 찍힌 시점 이후에 클러스터에서 member 변경(추가/제거)이 있었던 경우. 복원된 데이터의 멤버 구성이 현재 클러스터와 다르다.

### 대응

각 컨트롤 플레인 노드에서 `endpoint status`를 실행하여 데이터 정합성을 확인한다.

```bash
$ sudo etcdctl endpoint status --cluster -w table
```

출력에서 다음 두 값을 확인한다.

- **revision**: 모든 엔드포인트에서 동일해야 한다. 근소한 차이(수 단위)는 네트워크 지연에 의한 것일 수 있으며, 큰 차이가 있으면 데이터 분기를 의심한다.
- **RAFT TERM**: 모든 엔드포인트에서 **동일**해야 한다. term이 다르면 리더 선출이 비정상적으로 진행된 것으로, 단순한 지연과 구분된다.

revision과 RAFT TERM이 모두 일치하면, 데이터는 정상이고 member ID만 꼬인 상태일 수 있다. 이 경우 해당 노드를 `member remove` 후 데이터를 정리하고 재조인하면 해결된다. 불일치가 있으면 K3s/etcd 문서의 스냅샷 복원 절차를 검토한다.


## 복합 시나리오: Split Brain + 기존 클러스터 노드 하나가 죽어 있었다면

가장 까다로운 시나리오다. 마치 아래와 같은 상황이다.

- **원래 3중화**: cp-node-a, cp-node-b, cp-node-c
- **cp-node-c**: Split Brain으로 독립 클러스터 운영 중
- **cp-node-b**: 죽어 있음
- **cp-node-a**: 혼자 살아 있음

이때 **기존 클러스터(cp-node-a + cp-node-b) 쪽 etcd는 이미 quorum을 잃은 상태**다. cp-node-c가 독립 클러스터로 분리되었더라도, 원래 클러스터의 etcd member list에서는 자동으로 제거되지 않는다. 원래 클러스터 입장에서는 여전히 cp-node-a, cp-node-b, cp-node-c 세 멤버가 등록되어 있고, 그 중 cp-node-b와 cp-node-c가 응답하지 않는 상황이다. 3멤버 중 1개(cp-node-a)만 살아 있으므로 1/3으로 **quorum 미달** → 클러스터가 **쓰기 불가** 상태가 된다.

**우선순위는 반드시 다음 순서다.**

1. **먼저: 기존 클러스터의 quorum 복구**
   - cp-node-b 복구 시도: `systemctl restart k3s` 또는 재부팅
   - 2-3회 재시작을 시도한 뒤에도 peer 연결이 회복되지 않으면(로그에서 `failed to dial`, `connection refused` 지속), 해당 노드의 복구가 불가능한 것으로 판단한다.
   - cp-node-b 복구가 불가능하면: cp-node-a에서 `k3s server --cluster-reset`으로 단일 노드로 재시작하는 **응급 조치**를 검토한다.
   - **이유**: quorum이 없으면 etcd에 쓰기가 불가능하므로, Split Brain 노드를 멤버에서 제거하는 작업조차 할 수 없다.

2. **그 다음: Split Brain 노드 및 죽었던 노드 대응**
   - quorum이 확보된 뒤에야 `etcdctl member remove`로 cp-node-c를 제거할 수 있다 (member list에 남아 있는 경우).
   - cp-node-c에서 K3s 데이터를 정리한 뒤 `--server`를 지정해 재조인한다.

**`--cluster-reset` 응급 조치 이후의 전체 복구 절차**:

`--cluster-reset`으로 cp-node-a가 단독 클러스터로 재시작된 이후, 나머지 노드들의 재조인 절차는 다음과 같다.

1. **cp-node-b** (죽어 있던 노드, 복구된 경우):
   ```bash
   # cp-node-b에서
   $ sudo systemctl stop k3s
   $ sudo rm -rf /var/lib/rancher/k3s/server/db/
   $ sudo rm -rf /etc/rancher/k3s
   # --server를 지정하여 재조인
   $ curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="<기존버전>" \
     K3S_URL=https://<cp-node-a IP>:6443 \
     K3S_TOKEN=<TOKEN> \
     sh -s - server \
     --server https://<cp-node-a IP>:6443
   ```

2. **cp-node-c** (Split Brain으로 독립되어 있던 노드):
   ```bash
   # cp-node-c에서
   $ sudo /usr/local/bin/k3s-uninstall.sh
   $ sudo rm -rf /var/lib/rancher/k3s
   $ sudo rm -rf /etc/rancher/k3s
   # --server를 지정하여 재조인
   $ curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="<기존버전>" \
     K3S_URL=https://<cp-node-a IP>:6443 \
     K3S_TOKEN=<TOKEN> \
     sh -s - server \
     --server https://<cp-node-a IP>:6443
   ```

순서는 어느 쪽이든 상관없지만, cp-node-b를 먼저 합류시키면 quorum(2/3)을 빠르게 확보할 수 있으므로 일반적으로 권장된다.

정리하면, **"쓰기가 가능한 클러스터를 먼저 확보"**하는 것이 핵심이다. Split Brain 복구(멤버 제거, 재조인) 자체가 모두 etcd 쓰기를 필요로 하기 때문이다.

<br>

# 정리

etcd가 비정상일 때의 대응은 결국 하나의 원칙으로 수렴한다: **"쓰기가 가능한 클러스터를 먼저 확보"**하는 것이다.

모든 복구 작업(`member remove`, 재조인)은 etcd 쓰기를 필요로 한다. quorum이 확보되지 않으면 아무것도 할 수 없으므로, quorum 복구가 항상 최우선이다.

복구 작업 전 체크리스트:
1. `etcdctl endpoint health --cluster`로 각 멤버의 상태 확인
2. `etcdctl endpoint status --cluster`로 revision, RAFT TERM 확인
3. K3s 스냅샷 존재 여부 확인 (`ls /var/lib/rancher/k3s/server/db/snapshots/`)
4. 현재 상황에 맞는 시나리오 식별 후 대응

> 이 글은 [K3s 컨트롤 플레인 재조인 트러블슈팅]({% post_url 2026-02-19-Kubernetes-Split-Brain %}) 글에서 분리되었다.

<br>


# 참고: 기타 etcd 실패 케이스

최초에 다뤘던 표의 시나리오는 **Raft 멤버십/토폴로지** 관점만 다룬다. 아래는 멤버십과 무관한 **인프라·운영 레벨** 장애로, 별도 진단이 필요하다.

- **디스크 풀**: etcd는 write-ahead log를 디스크에 쓰므로, 디스크가 가득 차면 write가 실패한다. member는 healthy로 보이지만 쓰기가 안 되는 상황이라 진단이 까다롭다.
- **인증서 만료**: etcd peer/client TLS 인증서가 만료되면 멤버 간 통신이 끊겨 quorum 상실처럼 보이지만 원인이 다르다. K3s 장기 운영 클러스터에서 자주 발생하는 케이스다.
- **클럭 스큐**: 멤버 간 시간 차이가 크면 Raft heartbeat/election timeout 계산이 어긋나 leader election이 불안정해진다.
- **잦은 leader re-election**: 네트워크 불안정이나 리소스 부족으로 heartbeat가 간헐적으로 누락되면 election이 반복되며 write 가용성이 불안정해진다. `endpoint status`에서 `RAFT TERM`이 빠르게 증가하면 이 증상이다.
- **데이터 compaction/defrag 미수행**: etcd는 revision 기록을 누적하는데, compaction을 안 하면 메모리·디스크를 계속 소모해 결국 OOM이나 디스크 풀로 이어질 수 있다.
- **스냅샷 복원 실패**: 잘못된 스냅샷으로 복원 시 member list와 실제 데이터 간 불일치가 발생한다.
