---
title: "[EKS] EKS GPU 트러블슈팅: 3. 장애 재현 - 3. 분산학습과 NCCL 통신 - 2. SG 차단 네트워크 장애 재현"
excerpt: "EKS node SG에서 ephemeral self-ref를 제거하면 분산학습이 어떻게 실패하는지 재현해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GPU
  - NCCL
  - Security-Group
  - Distributed-Training
  - PyTorch
  - Terraform
  - Troubleshooting
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-01-Distributed-Learning-Background %})에서 정리한 실험 설계(Pod 2개 + headless Service, torchrun 기반 2-node all_reduce)를 바탕으로, EKS node SG의 **ephemeral self-ref(1025-65535/tcp) 제거**로 분산학습 네트워크 장애를 재현한다.

- **장애 재현**: Terraform 토글 2개 플립 → SG rule 8개 제거(ephemeral self-ref + webhook 5개 + egress + aux VPC allow) → 2-node torchrun이 **120초 후 실패**
- **핵심 발견**: 실패 지점이 예상(NCCL)과 다르다. **NCCL이 아니라 PyTorch c10d TCPStore**에서 rendezvous timeout이 먼저 발생. `NCCL_DEBUG=INFO` 로그가 **한 줄도 출력되지 않는다**
- **진단 공식**: `NCCL_DEBUG=INFO` 로그가 비어 있고 Python traceback에 `socket.cpp`/`TCPStore`/`DistNetworkError`가 보이면 → NCCL이 아니라 c10d 층. SG/방화벽/`MASTER_PORT` 접근성을 먼저 확인
- **복구**: Terraform SG 원복(8 rule 재생성, 4초) → all_reduce 재성공(21초)
- **운영 함정**: "NCCL 이슈"라고 불리는 것의 상당수는 NCCL 바깥이다. EKS managed node SG의 recommended rule 덩어리는 한 묶음으로 움직인다

<br>

# 전제 환경

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-01-Distributed-Learning-Background %})에서 설계한 실험 환경을 그대로 이어받는다.

| 항목 | 값 |
| --- | --- |
| 클러스터 | myeks5w, K8s 1.35 |
| GPU 노드 | g5.xlarge × 2, AZ ap-northeast-2a, private subnet |
| GPU Operator | v26.3.1, ClusterPolicy `status.state: ready` |
| Device Plugin DS | 2/2/2 Ready |
| 컨테이너 이미지 | `nvcr.io/nvidia/pytorch:24.10-py3` (NCCL 2.22.3+cuda12.6 내장) |
| NCCL transport | NET/Socket (IB 없음, `NCCL_IB_DISABLE=1`) |
| 실험 구조 | Pod 2개 + headless Service, torchrun 기반 2-node all_reduce |

<br>

# Baseline 스냅샷

장애 주입 전, SG가 온전한 상태에서 2-node all_reduce가 정상 동작함을 먼저 증명한다. 이것이 있어야 "차단 후 실패"를 SG 때문이라고 귀속할 수 있다.

## SG rule 상태

| SG | ingress 수 | egress 수 | 핵심 rule |
| --- | --- | --- | --- |
| node SG | **10** | 1 (`0.0.0.0/0` all) | self-ref ephemeral `1025-65535/tcp`, cluster→node webhook 5개(4443/6443/8443/9443/10251), kubelet 10250, DNS 53/tcp+udp self, cluster→node 443 |
| aux SG | **1** (`192.168.0.0/16` all-traffic) | 1 (`0.0.0.0/0` all) | VPC 대역 전체 허용 |

## 2-node all_reduce 성공

정상 상태에서 torchrun 기반 2-node all_reduce를 실행한 결과, 핵심 로그를 발췌하면 다음과 같다.

```
NCCL INFO Bootstrap : Using eth0:192.168.xx.xx<0>
NCCL INFO NET/Socket : Using [0]eth0:192.168.xx.xx<0>
NCCL INFO Using network Socket
NCCL INFO ncclCommInitRank ... - Init COMPLETE
NCCL INFO Connected all rings
[rank 0] iter 0 sum-first=3.0
[rank 0] iter 1 sum-first=6.0
[rank 0] iter 2 sum-first=12.0
[rank 0] iter 3 sum-first=24.0
[rank 0] iter 4 sum-first=48.0
```

- NCCL 2.22.3+cuda12.6, NET/Socket transport(IB 없음)
- `Init COMPLETE` → `Connected all rings` → rank 0/1 양쪽 sum 일치(3→6→12→24→48)
- Pod 상태: 양쪽 `Completed`

<details markdown="1">
<summary><b>Master(rank 0) 전체 NCCL 로그</b></summary>

```
nccl-master-0:1:1 [0] NCCL INFO NCCL_SOCKET_IFNAME set by environment to eth0
nccl-master-0:1:1 [0] NCCL INFO Bootstrap : Using eth0:192.168.xx.xx<0>
nccl-master-0:1:1 [0] NCCL INFO cudaDriverVersion 13000
nccl-master-0:1:1 [0] NCCL INFO NCCL version 2.22.3+cuda12.6
nccl-master-0:1:84 [0] NCCL INFO Plugin Path : /opt/hpcx/nccl_rdma_sharp_plugin/lib/libnccl-net.so
nccl-master-0:1:84 [0] NCCL INFO P2P plugin v8 IBext_v8
nccl-master-0:1:84 [0] NCCL INFO NET/IB : No device found.          # ← IB 디바이스 탐색 실패 (우선순위 2 탈락)
nccl-master-0:1:84 [0] NCCL INFO NCCL_IB_DISABLE set by environment to 1.  # ← 환경변수로 IB 명시적 비활성화
nccl-master-0:1:84 [0] NCCL INFO NET/Socket : Using [0]eth0:192.168.xx.xx<0>  # ← TCP Socket으로 fallback (우선순위 3)
nccl-master-0:1:84 [0] NCCL INFO Using network Socket               # ← 최종 transport 확정: TCP Socket
nccl-master-0:1:84 [0] NCCL INFO ncclCommInitRank comm 0x56223d711810 rank 0 nranks 2 cudaDev 0 nvmlDev 0 busId 1e0 commId 0xef1a7a6ce2d1f588 - Init START
nccl-master-0:1:84 [0] NCCL INFO comm 0x56223d711810 rank 0 nRanks 2 nNodes 2 localRanks 1 localRank 0 MNNVL 0
nccl-master-0:1:84 [0] NCCL INFO Channel 00/02 :    0   1
nccl-master-0:1:84 [0] NCCL INFO Channel 01/02 :    0   1
nccl-master-0:1:84 [0] NCCL INFO Trees [0] 1/-1/-1->0->-1 [1] -1/-1/-1->0->1
nccl-master-0:1:84 [0] NCCL INFO ncclCommInitRank comm 0x56223d711810 rank 0 nranks 2 cudaDev 0 nvmlDev 0 busId 1e0 commId 0xef1a7a6ce2d1f588 - Init COMPLETE
nccl-master-0:1:87 [0] NCCL INFO Channel 00/0 : 1[0] -> 0[0] [receive] via NET/Socket/0
nccl-master-0:1:87 [0] NCCL INFO Channel 01/0 : 1[0] -> 0[0] [receive] via NET/Socket/0
nccl-master-0:1:87 [0] NCCL INFO Channel 00/0 : 0[0] -> 1[0] [send] via NET/Socket/0
nccl-master-0:1:87 [0] NCCL INFO Channel 01/0 : 0[0] -> 1[0] [send] via NET/Socket/0
nccl-master-0:1:87 [0] NCCL INFO Connected all rings
```

NCCL transport 선택 과정을 정리하면 다음과 같다. NCCL은 우선순위가 높은 transport부터 시도하여, 사용 가능한 첫 번째 경로를 선택한다.

| 우선순위 | transport | 이 실험에서 | 로그 |
| --- | --- | --- | --- |
| 1 | NVLink | 해당 없음 (노드 간 통신, 같은 서버 내 GPU 간만 가능) | - |
| 2 | GPUDirect RDMA / IB | g5.xlarge에 EFA/IB 없음 → `No device found` + `IB_DISABLE=1` | line 7-8 |
| 3 | **TCP Socket** | **선택됨** → `NET/Socket : Using [0]eth0` | line 9-10 |

g5.xlarge에는 NVLink도 EFA도 없으므로 **TCP Socket이 유일한 노드 간 NCCL 통신 경로**다. 이 TCP Socket 통신이 node SG의 ephemeral self-ref(1025-65535/tcp) rule을 통해 허용된다. 즉, 이 rule이 제거되면 NCCL의 유일한 통신 경로가 막힌다.

</details>

<br>

# 장애 주입

## Terraform SG rule 차단

Terraform 변수 2개를 `false`로 플립하여 SG rule 8개를 제거한다.

```bash
terraform plan \
  -var gpu_desired_size=2 \
  -var enable_aux_sg_vpc_allow=false \
  -var node_sg_enable_recommended_rules=false \
  -out=tfplan-c3-block
# Plan: 0 to add, 0 to change, 8 to destroy
```

## 제거되는 SG rule 8개

| # | rule | 의미 | 실험상 역할 |
| --- | --- | --- | --- |
| **1** | aux SG VPC `192.168.0.0/16` all-traffic ingress | 노드 간 숨은 허용 경로 | **분산학습 통신 차단 (핵심)** |
| **2** | node SG self-ref `1025-65535/tcp` ingress | 노드 간 ephemeral 포트 허용 | **분산학습 통신 차단 (핵심)** |
| 3 | node SG `egress 0.0.0.0/0` | 노드 outbound all | 부수 효과 (`aux_egress_all`이 보완) |
| 4 | cluster→node 4443/tcp | webhook | 부수 효과 |
| 5 | cluster→node 6443/tcp | webhook | 부수 효과 |
| 6 | cluster→node 8443/tcp | Karpenter webhook | 부수 효과 |
| 7 | cluster→node 9443/tcp | aws-lb-controller, cert-manager webhook | 부수 효과 |
| 8 | cluster→node 10251/tcp | webhook | 부수 효과 |

1번과 2번이 분산학습 통신의 실제 차단 대상이다. 3번(egress)은 `aux_egress_all`이 커버하고, 4~8번은 webhook 부수 효과다.

"1번과 2번만 골라서 제거하면 되지 않나?"라고 생각할 수 있지만, EKS Terraform 모듈의 `node_security_group_enable_recommended_rules`는 단일 boolean이다. 이 토글 하나로 ephemeral self-ref, webhook 5개, egress가 한 묶음으로 켜지거나 꺼진다. 개별 rule만 골라 빼는 옵션이 모듈에 없다. `aws ec2 revoke-security-group-ingress` CLI로 수동 제거할 수는 있지만, 실무에서 이 장애가 발생하는 경로는 "누군가 PR에서 토글을 `false`로 바꾸거나, 모듈 업그레이드 시 기본값이 바뀌면서 8개가 한꺼번에 내려가는 것"이다. 이 실험은 그 실무 사고 경로를 그대로 재현한다.

## 차단 후 SG 상태

| SG | baseline ingress | 차단 후 ingress | 남는 rule |
| --- | --- | --- | --- |
| node SG | 10 | **4** | kubelet 10250, DNS 53/tcp+udp self, cluster→node 443 |
| aux SG | 1 | **0** | (egress `0.0.0.0/0`만 유지) |

<br>

# 디버깅 경로

> 장애 원인을 **모르는 상태**에서 분산학습 실패를 만났다고 가정하고, 단계별로 원인을 좁혀간다.

## 1단계: Pod 상태 확인

차단 상태에서 2-node all_reduce를 실행하면, 약 2분 23초 후 양쪽 Pod가 `Error`로 전이한다.

```bash
kubectl get pods -o wide
```

```
NAME              READY   STATUS   RESTARTS   AGE     NODE
nccl-master-0     0/1     Error    0          2m23s   ip-192-168-aa-aa...
nccl-worker-0     0/1     Error    0          2m23s   ip-192-168-bb-bb...
```

`podAntiAffinity`에 의해 두 Pod가 서로 다른 GPU 노드에 분산되었다. 120초 PG timeout + container teardown 시간을 합치면 약 2분 23초다.

## 2단계: kubectl logs — 에러 메시지 확인

### Master (rank 0)

```
[init] host=nccl-master-0 rank=0 ws=2 master=nccl-master:29500
Traceback (most recent call last):
  File "/tmp/allreduce.py", line 4, in <module>
    dist.init_process_group(backend="nccl", timeout=datetime.timedelta(seconds=120))
  ...
torch.distributed.DistStoreError: Timed out after 121 seconds waiting for clients. 1/2 clients joined.
```

rank 0은 `MASTER_PORT`(29500)에서 TCP listen을 열고 나머지 rank가 접속하기를 기다렸지만, 121초가 지나도 1/2만 참가(자기 자신)했다.

### Worker (rank 1)

```
[init] host=nccl-worker-0 rank=1 ws=2 master=nccl-master:29500
[E419 13:27:42.301344821 socket.cpp:1011] [c10d] The client socket has timed out after 120000ms
  while trying to connect to (nccl-master, 29500).
torch.distributed.DistNetworkError: The client socket has timed out after 120000ms
  while trying to connect to (nccl-master, 29500).
```

rank 1은 `MASTER_ADDR:MASTER_PORT`(nccl-master:29500)에 TCP connect를 시도했지만, 120초 후 timeout이 발생했다.

<details markdown="1">
<summary><b>Worker(rank 1) 전체 traceback</b></summary>

```
[E419 13:27:42.301344821 socket.cpp:1011] [c10d] The client socket has timed out after 120000ms while trying to connect to (nccl-master, 29500).
[E419 13:27:42.317323202 TCPStore.cpp:390] [c10d] TCP client failed to connect/validate to host nccl-master:29500 - timed out (try=0, timeout=120000ms): The client socket has timed out after 120000ms while trying to connect to (nccl-master, 29500).
Exception raised from throwTimeoutError at /opt/pytorch/pytorch/torch/csrc/distributed/c10d/socket.cpp:1013 (most recent call first):
frame #0: c10::Error::Error(...) in libc10.so
frame #7: c10d::TCPStore::TCPStore(...) in libtorch_cpu.so
...
Traceback (most recent call last):
  File "/tmp/allreduce.py", line 4, in <module>
    dist.init_process_group(backend="nccl", timeout=datetime.timedelta(seconds=120))
  ...
torch.distributed.DistNetworkError: The client socket has timed out after 120000ms while trying to connect to (nccl-master, 29500).
```

</details>

### NCCL INFO 라인: 0줄

양쪽 로그 모두 **NCCL 관련 출력이 한 줄도 없다**. baseline 성공 시와 동일한 Pod 매니페스트, 동일한 `NCCL_DEBUG=INFO` 환경변수를 사용했는데도, baseline에서 출력되었던 `NCCL INFO Bootstrap`, `NCCL INFO NET/Socket`, `Init START` 등의 라인이 전혀 나타나지 않는다. 

같은 설정에서 한쪽은 NCCL 로그가 나오고 한쪽은 0줄이므로, 로그 레벨 설정 문제가 아니다. `NCCL_DEBUG=INFO`는 NCCL 코드가 한 줄이라도 실행되면 bootstrap·transport 선택·communicator init 로그를 반드시 출력하는 레벨이다. 0줄이라는 것은 **NCCL 코드 경로에 아예 진입하지 못했다**는 뜻이다.

## 3단계: 층 분석 — 왜 NCCL이 아닌가

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-01-Distributed-Learning-Background %})에서 정리한 초기화 시퀀스를 다시 보자.

```text
1. c10d TCPStore rendezvous   ← 여기서 실패 (120s timeout)
   rank 0: MASTER_PORT에 TCP listen
   rank 1: MASTER_ADDR:MASTER_PORT로 TCP connect
         → ephemeral 범위(1025-65535) 차단으로 connect 불가

2. NCCL bootstrap             ← 도달하지 못함
3. NCCL communicator 구성     ← 도달하지 못함
```

`init_process_group(backend="nccl")`이 내부적으로 c10d `TCPStore`를 먼저 생성한다. TCPStore는 `MASTER_ADDR:MASTER_PORT`(nccl-master:29500)에 대한 TCP 연결이다. 29500은 ephemeral 범위(1025-65535)에 속하므로, self-ref rule이 제거된 상태에서는 이 TCP connect가 차단된다.

c10d TCPStore 단계에서 먼저 죽기 때문에, **NCCL bootstrap 단계에 도달하지 못한다**. 그래서 `NCCL_DEBUG=INFO` 로그가 한 줄도 출력되지 않는 것이다.

## 4단계: SG rule 확인

차단 후 SG 상태를 조회하면, baseline 대비 정확히 8개 rule이 제거되었음을 확인할 수 있다.

```bash
aws ec2 describe-security-groups --group-ids <NODE_SG_ID> <AUX_SG_ID> \
  --region ap-northeast-2 --output json
```

- node SG: 10 → **4** ingress (ephemeral self-ref + webhook 5개 + egress 제거 확인)
- aux SG: 1 → **0** ingress (VPC all-traffic 제거 확인)

## 부수 효과 관찰

SG 차단 3분 48초 구간 동안 webhook/controller 상태를 관찰했다.

| 컴포넌트 | 상태 | 비고 |
| --- | --- | --- |
| cert-manager | Running 유지, 재시작 0회 | 차단 구간에 신규 Certificate 생성을 하면 9443 차단으로 실패했을 것 (미검증) |
| gpu-operator | Running 유지, 재시작 0회 | validator Job은 이미 Completed 상태라 webhook 재호출 없음 |
| ClusterPolicy `status.state` | `ready` 유지 | operator reconcile은 노드 내부 경로라 SG 영향 없음 |
| aws-lb-controller | N/A | 본 클러스터에 미설치 |

차단 구간이 짧고(3분 48초), 이 동안 신규 admission 호출이 없었기 때문에 부수 효과가 표면화되지 않았다. 운영 환경에서 이 시간이 길어지면 webhook 장애로 이어질 수 있다.

<br>

# 예상 vs 실측

| 항목 | 예상 | 실측 | 일치 |
| --- | --- | --- | --- |
| terraform plan | 8 destroy | **8 destroy** (정확 일치) | O |
| 차단 후 node SG ingress | recommended 외 rule만 남음 | **4개** (kubelet/DNS/443) | O |
| torchrun 실패 지점 | NCCL bootstrap 후 peer TCP connect hang | **c10d TCPStore rendezvous timeout** (NCCL 이전) | **X** (층이 다름) |
| `NCCL_DEBUG=INFO` 출력 | Bootstrap, NET/Socket 등 | **0줄** (NCCL 초기화 미도달) | **X** |
| Pod 상태 | Error | **Error** (2m23s) | O |
| webhook 영향 | 일시적 admission 실패 가능 | Running 유지 (호출 미발생) | △ |

핵심 불일치는 **실패 층**이다. NCCL이 아니라 그 앞의 c10d TCPStore에서 먼저 막혔다. 이 불일치 자체가 "NCCL 이슈인지 아닌지 판정하는 기준"을 제시하는 가장 강력한 실측 근거가 된다.

<br>

# 해결/복구

## Terraform SG 원복

```bash
# SG rule 8개 재생성 (기본값 true/true 복귀)
terraform plan -var gpu_desired_size=2 -out=tfplan-c3-restore
# Plan: 8 to add, 0 to change, 0 to destroy

terraform apply "tfplan-c3-restore"
# Apply complete! Resources: 8 added (4초 내)
```

## all_reduce 재성공

SG 원복 후 동일 매니페스트로 all_reduce를 재실행하면, 21초 내 양쪽 `Completed`로 전이한다.

```
NCCL INFO Bootstrap : Using eth0:192.168.xx.xx<0>
NCCL INFO NET/Socket : Using [0]eth0:192.168.xx.xx<0>
NCCL INFO ncclCommInitRank ... - Init COMPLETE
NCCL INFO Connected all rings
[rank 0] iter 0 sum-first=3.0
[rank 0] iter 1 sum-first=6.0
[rank 0] iter 2 sum-first=12.0
[rank 0] iter 3 sum-first=24.0
[rank 0] iter 4 sum-first=48.0
```

Baseline과 100% 동일한 출력이다.

## 복구 검증

| 항목 | baseline | 복구 후 | 일치 |
| --- | --- | --- | --- |
| node SG ingress 수 | 10 | **10** | O |
| aux SG ingress VPC allow | 존재 | **존재** | O |
| sum-first (iter 0~4) | 3.0/6.0/12.0/24.0/48.0 | **동일** | O |
| NCCL `Init COMPLETE` + `Connected all rings` | O | **O** | O |
| Pod phase | Completed | **Completed** (21s, 이미지 캐시) | O |

**차단→복구 사이클 닫힘 확인**: baseline 성공 → 차단 후 실패 → 복구 apply → 동일 매니페스트 재실행으로 baseline과 동일 값 재현.

<br>

# 정리

## 진단 공식

> `NCCL_DEBUG=INFO` 로그가 stdout에 아예 없고, Python traceback이 `torch.distributed.socket.cpp` / `TCPStore` / `DistNetworkError` 키워드를 포함하면 → NCCL이 아니라 **PyTorch c10d 층의 rendezvous 단계**(MASTER_ADDR:MASTER_PORT TCP connect)가 원인이다. SG/방화벽/`MASTER_PORT` 접근성을 먼저 확인한다.

이 공식은 NCCL communicator lazy init 디버깅([관련 글]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %}))과 함께 읽으면, "NCCL 로그가 비어 있을 때 어디를 봐야 하는가"에 대한 판단 근거가 된다.

## 디버깅 경로 비교

| | [03-01: Device Plugin 비활성화]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %}) | [03-02: vLLM 기동 실패]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-02-vLLM-TroubleShooting %}) | 03-03-02: SG 차단 (이번 글) |
| --- | --- | --- | --- |
| 장애 층 | **인프라 층** (GPU Operator) | **앱 층** (vLLM) | **네트워크 층** (SG/c10d) |
| Pod STATUS | Pending | CrashLoopBackOff | Error |
| 핵심 도구 | `kubectl get/describe` | `kubectl logs --previous` | `kubectl logs` + `aws ec2 describe-security-groups` |
| GPU 인프라 | 비정상 (Allocatable 0) | 정상 | 정상 |
| NCCL 관여 | 없음 | 없음 | 예상했으나 **c10d에서 먼저 실패** |

같은 "GPU 워크로드가 안 된다"는 증상이지만, Pod STATUS와 에러 메시지의 층위가 디버깅 경로의 분기점이 된다.

## 운영 함정 2가지

**1. "NCCL 이슈"라고 불리는 것의 상당수는 NCCL 바깥이다**

`NCCL_DEBUG=INFO`를 켰는데도 NCCL INFO 라인이 한 줄도 없다면, 원인은 그 아래 계층이다: PyTorch c10d TCPStore, Kubernetes Service DNS, 방화벽/SG, kube-proxy. NCCL 자체를 의심하기 전에 네트워크 연결성부터 확인해야 한다.

**2. EKS managed node SG의 "recommended rule 덩어리"는 한 묶음으로 움직인다**

`node_security_group_enable_recommended_rules=false` 토글 하나가 self-ref ephemeral(분산학습)과 webhook(4443/6443/8443/9443/10251)을 동시에 내린다. 분산학습만 끊기는 것이 아니라 admission webhook도 영향을 받을 수 있다. IaC 가드레일로 이 토글을 잠그는 것이 재발 방지의 핵심이다.

## 요약

| 항목 | 장애 상태 | 복구 상태 |
| --- | --- | --- |
| node SG ephemeral self-ref | **제거됨** | 존재 (1025-65535/tcp) |
| aux SG VPC allow | **제거됨** | 존재 (192.168.0.0/16) |
| c10d TCPStore rendezvous | **timeout 120s** | 성공 |
| NCCL `Init COMPLETE` | **미도달** (NCCL 로그 0줄) | Init COMPLETE |
| all_reduce sum | **실패** | 3.0/6.0/12.0/24.0/48.0 |
| Pod phase | **Error** (2m23s) | Completed (21s) |
| 차단→복구 총 소요 | — | **SG apply 4초 + all_reduce 21초** |

## 다음 단계

이번 글까지 인프라 층(Device Plugin), 앱 층(vLLM), 네트워크 층(SG 차단) 장애를 각각 재현했다. [다음 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-04-Error-Cases %})에서는 EKS 관리형 환경에서 재현할 수 없는 3개 주제(CUDA XID, Auto Mode, EFA)를 사례 탐구로 다룬다.

<br>
