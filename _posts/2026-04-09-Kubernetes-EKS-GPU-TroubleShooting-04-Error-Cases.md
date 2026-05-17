---
title: "[EKS] EKS GPU 트러블슈팅: 4. 사례 탐구 - CUDA XID, Auto Mode, EFA"
excerpt: "EKS 관리형 환경에서 재현할 수 없는 GPU 주제 3가지를, 문서 탐구와 실무 경험 매핑으로 정리해 보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GPU
  - NVIDIA
  - XID
  - EFA
  - GPU-Operator
  - Auto-Mode
  - NCCL
  - Troubleshooting
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %})까지는 실제 EKS 클러스터에서 장애를 직접 재현했다. 이번에는 스터디 체크리스트에 포함되어 있었지만 **EKS 관리형 환경에서 재현할 수 없는** 3개 주제를, 문서 탐구와 실무 경험 매핑으로 다룬다.

- **CUDA XID 에러**: NVIDIA 커널 드라이버가 남기는 GPU 비정상 이벤트. EKS에서는 HW 계열 XID(48/74/79 등)를 인위적으로 유발할 수 없다. 플랫폼 엔지니어의 관심사는 재현이 아니라 **감지 → 자동 격리 → 인스턴스 교체** 파이프라인이 되어야 한다
- **GPU 스택 소유권 (Auto Mode vs 수동 구성)**: Auto Mode를 켜면 드라이버와 Device Plugin 소유권이 AWS로 넘어간다. GPU Operator가 사라지는 게 아니라, **담당 범위가 관측 레이어로 좁아지는** 것이다. 핵심 원칙은 "한 레이어의 소유자는 하나"
- **EFA와 InfiniBand**: "NCCL이냐 EFA냐"는 잘못된 질문이다. NCCL은 GPU 간 통신 라이브러리이고, EFA는 **그 라이브러리가 데이터를 실어 나르는 AWS 전용 네트워크**다. 온프레미스 IB와 비교하면, NCCL 튜닝 개념은 공유되지만 물리 진단 영역은 AWS가 가져간다

<br>

# 배경

## 재현 시나리오와 사례 탐구

이 시리즈의 [장애 재현 편]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에서는 Device Plugin 비활성화, vLLM 기동 실패, SG 차단 네트워크 장애를 실제로 유발하고 디버깅했다. 이 글에서 다루는 3개 주제는 접근이 다르다.

정영준님의 5주차 스터디 슬라이드는 XID 에러 코드, EKS Auto Mode, EFA/InfiniBand 차이를 체크포인트로 다뤘다. 그런데 이 주제들은 g5.xlarge 기반 실습 환경에서 재현할 수 없다.

- **XID**: HW 결함(XID 48), NVLink 에러(XID 74), PCIe 링크 드롭(XID 79) 등은 인위 유발이 불가능하거나 AWS 관리 경계에 들어간다
- **Auto Mode**: 별도 클러스터가 필요해 비용 부담이 크다
- **EFA**: g5.xlarge는 EFA를 지원하지 않고, EFA 활성 인스턴스(p4d/p5)는 고가다

그래서 문서 기반 이론 탐구와, 실무에서 겪었던 경험을 EKS 맥락에 매핑하는 방식으로 접근했다. 3개 주제는 각각 다른 축을 커버한다.

| 주제 | 축 | 실무 경험 연결 |
|---|---|---|
| CUDA XID | HW 감지 | 온프레미스에서 PCIe 연결 불량으로 GPU 교체한 경험 |
| Auto Mode | 아키텍처 선택 | 인프라팀이 device plugin을 선설치한 환경에서의 소유권 딜레마 |
| EFA | 네트워크 확장 | 온프레미스 InfiniBand와의 개념 비교, 차이점 정리 |

이 세 주제를 관통하는 메시지가 하나 있다. **"관리형 인프라 = 덜 배워도 된다"가 아니라 "다르게 배워야 한다"**는 것이다.

<br>

# CUDA XID 에러

## XID란

XID(eXception ID)는 NVIDIA 커널 드라이버가 커널 링버퍼(`dmesg`)에 남기는 **GPU 비정상 이벤트 ID**다. `dmesg | grep -i xid`로 확인할 수 있다.

```text
NVRM: Xid (PCI:0000:1e:00): 79, GPU has fallen off the bus.
NVRM: Xid (PCI:0000:af:00): 74, Channel ... GPU-side NVLink
NVRM: Xid (PCI:0000:1e:00): 31, Ch 00000060, engmask 00000101, intr 10000000
```

각 필드의 의미는 다음과 같다.

- `PCI:0000:<bus>:<dev>` → 어느 GPU에서 발생한 이벤트인지 식별
- `<code>` → XID 번호
- 나머지 → 이벤트별 컨텍스트(채널, engine mask, fault address 등)

## 주요 XID 코드와 EKS 재현 가능성

스터디 체크리스트에서 다뤄진 주요 XID 코드를 기반으로, EKS 관리형 환경(g5 인스턴스)에서의 재현 가능성을 정리하면 다음과 같다.

| XID | 의미 | EKS에서 유발 가능? |
|---|---|---|
| 31 | Invalid or corrupted push buffer stream → illegal memory access | 이론적으로 가능. CUDA OOB 커널을 작성하면 유발되지만, 정상 운영에서는 발생하면 안 되는 상황 |
| 48 | Double Bit ECC error → HW fault | 불가. ECC 비트 플립 필요 |
| 74 | NVLink 에러 | 불가. g5에는 NVLink이 없음 (A100/H100에서만 해당) |
| 79 | GPU has fallen off the bus (PCIe 링크 드롭) | 불가. PCIe 링크 이상 = 인스턴스 retire 대상 |
| 61 | PMU 통신 장애 | 불가 |
| 64 / 92 | ECC 에러 (단일/이중 비트) | 불가 |

AWS가 EC2 인스턴스 하드웨어 전 층(PCIe, ECC, NVLink HCA)을 소유한다. 고객이 건드릴 수 있는 층은 CUDA 커널 레벨뿐인데, 이것도 정상적인 상황이라면 유발되어서는 안 된다(XID 31이 뜬다면 애플리케이션 버그다). `StatusCheckFailed_System` / `StatusCheckFailed_Instance`가 HW 이상 시 발화하고, AWS가 자동으로 인스턴스를 retire 대상으로 표시한다. EC2를 stop → start하면 다른 물리 하드웨어로 재배치된다.

유발 가능한 XID 31(CUDA OOB)은 애플리케이션 버그 시나리오에 가깝다. 플랫폼 엔지니어가 실제로 관심 가지는 XID 48/64/74/79 같은 하드웨어 신호는 관리형 환경에서 시뮬레이션 없이 **감지 파이프라인 자체를 검증**해야 한다.

## 온프레미스 경험 매핑

예전 회사에서 PCIe 연결이 안 되어 GPU를 교체한 적이 있었다. 이걸 XID 에러와 연관지어 보면, 가장 가까운 매핑은 다음과 같다.

- **XID 79** (GPU has fallen off the bus): GPU와 메인보드를 연결하는 PCIe 버스가 완전히 끊어져서, OS 커널이 GPU를 인식하지 못하는 상황이다. 온프레미스에서는 1) GPU를 PCIe 슬롯에서 뺐다가 다시 꽂기, 2) 라이저 카드(GPU와 메인보드 사이의 연결 보드) 교체, 3) 메인보드나 GPU 카드 자체 교체 순으로 진단한다
- **XID 61** (PMU interface fault): GPU 내부에 있는 관리용 프로세서(PMU)와의 통신이 끊긴 상황이다. GPU 하드웨어가 서서히 열화되고 있다는 징후에 해당한다

PCIe 링크 속도가 Gen4에서 Gen1으로 떨어지는 현상(`LnkSta: Speed 2.5GT/s (downgraded)`)은 XID는 아니지만 전조 증상이 될 수 있다. GPU가 놀고 있을 때(idle) 절전 모드(ASPM)로 속도가 낮아지는 건 정상이다. 하지만 GPU에 부하가 걸린 상태에서도 속도가 올라가지 않는다면 HW 이상 징후다.

온프레미스에서는 `dmesg` 패턴 읽기, `lspci -vv`로 링크 속도 확인, 라이저/슬롯 물리 진단 같은 역량을 기른다. EKS에서는 이걸 직접 쓸 일이 거의 없다. 대신 동일한 XID를 놓고 다른 질문을 해야 한다.

- XID 이벤트를 모니터링 스택에 **어떻게 실어 올릴지** (DCGM → Prometheus → Alertmanager)
- 노드 Condition이 **어떻게 변하는지** (NPD → Node Problem → taint)
- 그 taint가 **Karpenter/ASG의 replace 결정에 어떻게 연결되는지**

온프레미스에서는 손으로 GPU를 뽑는 행위가, EKS에서는 선언적 자동화로 번역된다.

## 감지 파이프라인 설계

XID를 감지하는 수단은 계층별로 나뉜다.

| 계층 | 도구 | 감지 대상 |
|---|---|---|
| 커널 | `dmesg` / `/dev/kmsg` | 원본 XID 이벤트 |
| Node agent | NVIDIA node-problem-detector plugin | dmesg 후킹 → Node Condition(`GPUXidError=True`) 변경 |
| Cluster metric | dcgm-exporter `DCGM_FI_DEV_XID_ERRORS` | XID 카운터를 Prometheus 시계열로 |
| Cluster API | EC2 `describe-instance-status` | `StatusCheckFailed_System` 등 AWS 관점의 HW 상태 |
| 애플리케이션 | PyTorch/CUDA runtime 예외 | `cudaErrorLaunchFailure` 등 (내부 원인이 XID일 수 있음) |

MLOps/플랫폼 관점의 최소 셋은 **dcgm-exporter(Cluster metric 계층) + NPD(Node agent 계층) + 알림 라우팅(Prometheus → Alertmanager)**이다.

### Prometheus alert rule

```yaml
groups:
  - name: gpu-xid
    rules:
      # 모든 XID 이벤트 감지
      - alert: GpuXidError
        expr: increase(DCGM_FI_DEV_XID_ERRORS[5m]) > 0
        for: 0m
        labels: { severity: critical, team: mlops }
        annotations:
          summary: "GPU XID on {{ $labels.node }} / {{ $labels.gpu }}"
      # HW/PCIe/ECC/NVLink 계열은 즉시 cordon 트리거
      - alert: GpuXidErrorFatalPattern
        expr: increase(DCGM_FI_DEV_XID_ERRORS{xid=~"48|63|64|74|79|92"}[1m]) > 0
        labels: { severity: pager }
```

### 자동 격리 → 인스턴스 교체 흐름

전체 대응 파이프라인은 다음과 같다.

1. **NPD**의 custom plugin이 `dmesg`에서 `NVRM: Xid` 패턴을 후킹 → `Node.Status.Conditions["GPUXidError"]=True` 설정
2. `taint: gpu-xid=true:NoSchedule` 자동 부여 → 신규 GPU Pod은 이 노드로 스케줄되지 않음. 기존 Pod은 유지(in-flight 학습 중단 방지)
3. taint가 붙은 노드는 Karpenter disruption 또는 Managed Node Group scale 정책으로 교체
4. 교체 트리거 시 내부적으로 EC2 stop → start이 일어나며 다른 물리 HW로 재배치

### 증적 수집

장애 노드가 사라지기 전에 증적을 수집해야 한다. HW 교체 없이 인스턴스가 사라지면 증거가 함께 사라진다.

```bash
# NPD 이벤트 기반 trigger로 실행
kubectl debug node/<node> -- dmesg | grep -B1 -A5 -i xid > /s3/gpu-xid/<ts>-<node>.log
kubectl exec -n gpu-operator <dcgm-pod> -- dcgmi diag -r 3
aws ec2 describe-instance-status --instance-id <id> --include-all-instances
```

### 관리형 환경의 한계

실제 HW XID를 유발할 수 없는 관리형 환경에서는, 파이프라인 검증을 어떻게 할 수 있을까? 문서를 조사하면서 찾은 접근은 합성 테스트다. NPD의 테스트 모드로 가짜 Node Condition을 쏴서 cordon → 교체 흐름이 끝까지 도는지 확인하는 방식이다. 또한 `lspci -vv`나 SMBUS 레벨 진단은 관리형 환경에서 접근이 제한되고 AWS Support 케이스에 의존하게 되므로, 증적 자동 수집 DaemonSet을 미리 구성해 두는 것이 현실적인 대안으로 보인다.

한 가지 더 고려할 점이 있다. 장기 학습 중인 Pod이 taint로 cordon된 노드에 있으면, 기존 학습은 계속되지만 새 학습은 이 노드로 스케줄되지 않는다. 자동 교체가 진행 중인 학습을 망가뜨리지 않으려면, 체크포인트 주기와 재시작 가능한 설계가 함께 갖춰져야 할 것이다.

<br>

# GPU 스택 소유권: Auto Mode vs 수동 구성

## Auto Mode가 가져가는 것

EKS Auto Mode는 AWS가 노드 provisioning, OS 패치, 일부 애드온 라이프사이클을 가져가는 관리형 모드다. GPU 관점에서 핵심은 Karpenter 기반 노드 자동 provisioning + 자체 NVIDIA 드라이버 preinstall이다.

이 시리즈에서 구성한 수동 환경(managed Node Group + GPU Operator 자가 설치)과 비교하면 다음과 같다.

| 레이어 | 수동 구성 (이 시리즈) | Auto Mode |
|---|---|---|
| 노드 Provisioning | Terraform managed node group + 수동 관리 | Karpenter 기반 자동 (NodePool/NodeClass 선언) |
| OS / AMI 관리 | AL2023 NVIDIA AMI 핀 유지 + 수동 업데이트 | AWS 관리 |
| **NVIDIA driver** | GPU Operator `driver` DaemonSet | **AWS preinstall, 관리** |
| **Device Plugin** | GPU Operator `devicePlugin` DaemonSet | **AWS 관리 (클러스터에 DaemonSet으로 보이지 않음)** |
| NFD | GPU Operator 번들 또는 별도 설치 | 문서에 명시 없음 (확인 필요) |
| CUDA Toolkit | GPU Operator `toolkit` DaemonSet | 문서에 명시 없음 (확인 필요) |
| DCGM exporter | 사용자 설치 | 일부 자료에서 Auto Mode 포함 언급 (확인 필요) |
| GPU 장애 감지/복구 | NPD + 사용자 구성 | Node Monitoring Agent(NMA) + 자동 복구 (10분 이내) |
| Validator | GPU Operator validator Job | AWS 기본 검증 |

AWS 공식 문서에 따르면, Auto Mode는 **드라이버 + Device Plugin + 장애 자동 복구(NMA)**를 가져간다. Device Plugin은 DaemonSet 형태로 클러스터에 노출되지 않고 AWS가 내부적으로 관리한다. 다만 NFD, CUDA Toolkit, DCGM exporter의 Auto Mode 포함 여부는 문서에 명확히 기술되지 않은 부분이 있어, 실제 전환 시 확인이 필요하다.

## 충돌 지점과 공존 원칙

충돌 지점은 **드라이버**와 **Device Plugin** 2개다.

- 한 노드에 두 개의 NVIDIA driver DaemonSet이 동시에 있으면 커널 모듈 로드 경합이 일어나 기동 실패 또는 불안정 상태가 될 수 있다. 참고로 `driver.enabled=false`만으로 부족한 경우도 보고되어 있어서, `nvidiaDriverCRD.enabled=false`까지 함께 설정해야 할 수 있다
- Device Plugin이 중복 등록되면 어느 쪽이 유효한지 예측하기 어렵다

따라서 Auto Mode + GPU Operator 조합 시, 이 두 컴포넌트는 반드시 비활성화해야 한다.

```yaml
# Helm values (gpu-operator)
driver:       { enabled: false }
devicePlugin: { enabled: false }
```

공존 가능한 레이어는 관측/검증 중심이다.

- **DCGM exporter**: 메트릭 수집 전용. 드라이버 소유권과 무관하게 공존 가능. 다만 Auto Mode가 DCGM을 포함할 수 있으므로 중복 여부는 확인이 필요하다
- **CUDA Toolkit**: 충돌 가능성은 낮지만, Auto Mode에서의 Toolkit 포함 여부가 불분명해 전환 시 확인 필요
- **NFD**: label key namespace가 겹칠 수 있다. 실제로 다른 Operator(KAITO 등)와 NFD CRD가 충돌한 사례가 보고된 바 있어, 단일 소유자를 권장한다
- **Validator**: AWS 기본 검증과 중복될 수 있으므로 필요 시 별도로 켜는 식

핵심 원칙을 한 줄로 요약하면 이렇다.

> 한 레이어의 소유자는 하나여야 한다. GPU Operator values의 각 component 키는 "내가 이 레이어의 소유자인가"에 대한 선언이다.

## 실무 매핑: 인프라팀 선설치 상황

실무에서 GPU 노드를 편입할 때 인프라팀이 호스트에 NVIDIA 드라이버를 미리 깔아 둔 경우, GPU Operator로 통일할지 `driver.enabled=false`로 공존할지 고민했던 적이 있다.

Auto Mode에서 "AWS가 드라이버와 Device Plugin을 선설치한 상황"은 이 고민과 구조가 같다. 당시 정리했던 판단 기준은 다음과 같다.

1. **관리 책임 경계 확인**: 드라이버/Device Plugin을 누가 소유하는가? 인프라팀(Auto Mode에서는 AWS)인가, MLOps팀(GPU Operator)인가?
2. **경계가 인프라 쪽**: GPU Operator의 `driver.enabled=false`, `devicePlugin.enabled=false`. Auto Mode 공식 권장 경로도 이것
3. **경계가 MLOps 쪽**: 인프라 선설치분을 제거 후 GPU Operator 풀셋 사용 (Auto Mode에서는 선택 불가)
4. **애매한 경우**: "전부 우리가" vs "아무것도 안 함"이 아니라, **컴포넌트 단위로 true/false**를 합의하는 게 실질적인 답

## 수동 구성을 통해 얻은 것

이 시리즈에서 수동 경로를 선택한 것은 의미가 있었다. [환경 구성]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-02-01-Installation %})에서 `block_device_mappings` 함정을 발견하고, [Device Plugin 비활성화 재현]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에서 `absent()` 대신 `== 0` 기반 alert이 필요하다는 점을 실측했다. Auto Mode를 먼저 썼다면 이 지식 구멍이 생긴 채로 "그냥 되더라"에 머물렀을 것이다. 내재화 관점에서는 **수동 한 번 → Auto 전환** 순서가 권장된다.

### Auto Mode 전환 시 Helm values 예시

전환을 실행하지는 않았지만, 실행하게 될 때의 values를 남겨둔다.

```yaml
# values-autoMode.yaml
driver:       { enabled: false }   # AWS 소유
devicePlugin: { enabled: false }   # AWS 소유
dra:          { enabled: false }   # AWS 관리
nfd:          { enabled: false }   # AWS 관리
toolkit:      { enabled: false }   # AWS 관리 (확인 필요)
validator:    { enabled: true }    # 사용자 검증 원하면 유지
dcgmExporter: { enabled: true }    # 관측 — 사용자 소유
```

이 시리즈 실습에서 발견한 함정을 기반으로 전환 직후 돌려야 하는 리그레션 테스트도 있다.

- Allocatable `nvidia.com/gpu` 값이 각 노드에서 정상인지 (Device Plugin 비활성화 재현에서 발견한 `== 0` 함정)
- DCGM exporter metric 수집 정상 여부
- NCCL 2-node all_reduce smoke test (SG 차단 재현에서 사용한 baseline yaml 재활용)
- vLLM Deployment 기동 (driver/toolkit 경로 정상 여부)

<br>

# EFA와 InfiniBand

## EFA란, 그리고 InfiniBand와 뭐가 다른가

스터디 체크리스트에 "EFA / InfiniBand 차이"가 짧게 언급되어 있었는데, 둘 다 써 본 적이 없어서 문서부터 찾아봤다. 핵심만 정리하면 이렇다.

**InfiniBand(IB)**는 온프레미스 HPC에서 쓰는 고속 네트워크 표준이다. 전용 네트워크 카드(HCA), 전용 스위치, 네트워크를 관리하는 SubnetManager까지 별도 인프라가 필요하다. 대신 지연이 1~5μs로 매우 낮다.

**EFA(Elastic Fabric Adapter)**는 AWS가 만든 고속 네트워크 인터페이스다. IB처럼 별도 스위치나 관리 소프트웨어가 필요 없고, 기존 EC2 NIC(ENA)을 확장한 형태다. 일반 VPC 네트워크(TCP/IP)보다 훨씬 낮은 지연(15~50μs vs 100μs 이상)으로 노드 간 통신을 할 수 있다. p4d/p5/p5e/g5.48xlarge 등 제한된 인스턴스 타입에서만 활성화된다.

둘 다 빠른 이유는 공통적으로 **OS bypass** 때문이다. 일반 네트워크 통신은 애플리케이션 → OS 커널 → NIC 순서로 거치는데, IB와 EFA는 커널을 건너뛰고 애플리케이션이 NIC에 직접 데이터를 쓴다.

차이점을 표로 비교하면 다음과 같다.

| 축 | InfiniBand | EFA | 일반 VPC 네트워크 |
|---|---|---|---|
| 어디서 쓰나 | 온프레미스 HPC | AWS EC2 (일부 인스턴스) | AWS EC2 (모든 인스턴스) |
| 별도 HW/SW | 전용 카드(HCA) + 전용 스위치 + SubnetManager | 불필요 (ENA 확장) | 불필요 |
| 프로토콜 | IB 자체 프로토콜 | SRD (AWS 자체 설계) | TCP/IP |
| 지연 | 1~5 μs | 15~50 μs | 100+ μs |
| OS bypass | 있음 | 있음 | 없음 |

IB 경험이 있다면 EFA로 어느 정도 이전할 수 있을까? 문서를 조사하면서 정리한 범위는 다음과 같다.

- **개념이 공유되는 영역**: NCCL env 튜닝(`NCCL_PROTO`, `NCCL_BUFFSIZE` 등), topology 인식(NVLink vs network hop), buffer sizing. IB든 EFA든 NCCL 위에서 동작하므로, 튜닝 파라미터의 의미와 영향은 동일하다
- **개념은 같지만 도구가 다른 영역**: OS bypass / RDMA 개념은 동일하나, IB의 제어면(SubnetManager, IB fabric 도구들)은 EFA에 없다. AWS가 내부적으로 처리한다
- **EFA에 대응점이 없는 영역**: IB 스위치 / HCA 물리 진단(`opensmd`, `ibstat`, `ibdiagnet` 등). EFA에서는 AWS Support에 의존하게 된다

솔직히 IB나 RDMA를 직접 운영해 본 적은 아직 없다. 이번에 EFA 문서를 파면서 IB 쪽도 같이 읽게 됐는데, 언젠가 온프레미스 HPC 환경에서 IB를 직접 만져볼 기회가 오면 좋겠다는 생각이 들었다. HW 수준의 네트워크 진단 경험은 클라우드만으로는 쌓기 어려운 영역이라, EFA를 쓰더라도 그 밑단을 이해하는 데 분명 도움이 될 것이다.

이 시리즈에서 사용한 g5.xlarge는 EFA를 지원하지 않는다. [분산학습 재현]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %})에서 보낸 NCCL AllReduce는 일반 VPC 네트워크(TCP/IP) 위에서 동작했고, 소규모 실습에는 충분했다.

## NCCL은 데이터를 어떻게 보내나

NCCL이 GPU 간 데이터를 보낼 때, 어떤 네트워크를 쓸지는 환경에 따라 자동으로 결정된다. 우선순위가 높은 것부터 순서대로 시도한다.

1. **NVLink** → 같은 노드 안에서 GPU끼리 직접 연결. 가장 빠르다
2. **외부 플러그인** → NCCL이 별도로 설치된 네트워크 플러그인을 통해 데이터를 보내는 경로. AWS에서는 `aws-ofi-nccl`이라는 플러그인이 EFA에 접근하는 역할을 한다
3. **NCCL 내장 IB** → 플러그인 없이 NCCL이 직접 InfiniBand 카드(HCA)를 사용하는 경로. 온프레미스에 IB가 있으면 별도 설치 없이 동작한다
4. **Socket fallback** → 위 경로가 모두 없으면, 일반 TCP/IP 소켓으로 보낸다. OS 커널을 거치므로 가장 느리다

이 시리즈의 g5.xlarge 환경에서는 EFA도 없고 IB도 없으니, 실제로는 4번 Socket fallback이 사용됐다. [분산학습 배경]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-01-Distributed-Learning-Background %})에서 NCCL 로그에 `NET/Socket : Using [0]eth0:<ip>`가 찍힌 것이 이것이다. EFA를 지원하는 p5 같은 인스턴스라면 2번 경로를 타게 된다.

여기서 중요한 건, **EFA는 NCCL을 대체하는 게 아니라는 점**이다. NCCL은 "GPU 간에 데이터를 주고받는 라이브러리"이고, EFA는 "그 데이터를 실제로 실어 나르는 네트워크"다. NCCL 로그를 보면 g5에서 `NET/Socket`이라고 뜨는 자리에, p5에서는 `NET/AWS Libfabric` 같은 표기가 뜨는 식으로 transport만 바뀐다.

## 언제 EFA가 필요한가

| 워크로드 | EFA 필요? | 근거 |
|---|---|---|
| 단일 노드 8-GPU 학습 (NVLink only) | 불필요 | 노드 간 통신 없음 |
| 2-노드 데모 규모 all_reduce | 불필요 | VPC CNI로 충분 |
| Foundation 모델 학습 (수십~수백 노드) | 필요 | Gradient sync가 대역폭 병목 → SRD 필수 |
| 대규모 파인튜닝 (LoRA 외 full fine-tune) | 필요 | 동일 |
| vLLM 추론 (단일 노드 또는 TP intra-node) | 불필요 | 추론 워크로드는 노드 간 통신 미미 |
| 분산 추론 Ray + TP 2+ 노드 | 상황에 따라 | 토큰 통신량 측정 후 결정 |

판단 기준은, iteration 시간에서 노드 간 통신이 차지하는 비율이다. 프로파일링으로 통신 대기 비율을 측정해서, 네트워크가 병목이라면 EFA 도입을 검토하는 식이다.

EFA는 "선택지가 늦게 나타나는 의사결정"이기도 하다. g5.xlarge로 학습 실험을 하다가 "이제 scale-out이 필요"해지면 p5.48xlarge + EFA가 드러난다. 그 사이에 통신 병목 측정, Placement Group 설계, 컨테이너 이미지 리빌드(aws-ofi-nccl 포함), 인스턴스 쿼터/비용 승인 같은 지식 축이 쌓여야 한다.

## EKS에서 EFA를 쓰려면

EFA가 필요하다고 판단했다면, EKS에서 구성해야 할 요소는 3가지다.

1. **EFA 활성 인스턴스 타입** (p4d/p5/g5.48xlarge 등)
2. **EFA Device Plugin** (리소스 이름 `vpc.amazonaws.com/efa`)
3. 컨테이너 이미지에 **aws-ofi-nccl + libfabric** 포함 + NCCL env 세팅

Pod spec 예시는 다음과 같다.

```yaml
resources:
  limits:
    nvidia.com/gpu: 8
    vpc.amazonaws.com/efa: 4      # EFA device 수 (인스턴스별 상이)
env:
  - { name: FI_PROVIDER,            value: "efa" }
  - { name: FI_EFA_USE_DEVICE_RDMA, value: "1" }
  - { name: NCCL_PROTO,             value: "simple" }
  - { name: NCCL_IB_DISABLE,        value: "1" }
```

추가로 신경 써야 할 부분도 있다.

- **인스턴스 배치**: 동일 Placement Group(cluster strategy) 내에서 최적 성능. Launch template으로 placement group 지정
- **MTU**: EFA는 9001(jumbo frame). 일반 ENA 기본값과 다름
- **컨테이너 이미지**: NVIDIA DLAMI 기반이 가장 편함. 커스텀 이미지는 aws-ofi-nccl + libfabric 별도 빌드 필요
- **검증**: NCCL 로그에 `NET/AWS Libfabric`(또는 해당 plugin 명)이 노출되는지 확인. Socket fallback이 일어나면 성능 열화로만 나타나 발견이 어려움

NCCL 버전 × aws-ofi-nccl 버전 × libfabric 버전 매트릭스가 좁다는 점도 주의 사항이다. 잘못된 조합에서 silent fallback → Socket이 일어날 수 있어, 검증 단계에서 NCCL 로그의 transport 라인을 반드시 확인해야 한다.

<br>

# 정리

3개 사례 탐구의 공통 교훈은 **"관리형 환경에서는 다르게 배워야 한다"**는 것이다.

| 온프레미스 역량 | EKS 번역 |
|---|---|
| `dmesg` 패턴 읽기, `lspci -vv` 링크 속도 확인, GPU 물리 교체 | DCGM → Prometheus → NPD → Karpenter 자동 교체 파이프라인 |
| GPU Operator 풀셋 설치, 드라이버/Device Plugin 직접 관리 | Auto Mode 소유권 분리 + 레이어별 `enabled: true/false` 선언 |
| IB 스위치 구성, HCA 물리 진단 (온프레 HPC) | aws-ofi-nccl + EFA Device Plugin + NCCL transport 로그 검증 (클라우드) |

온프레미스 역량이 무의미해지는 게 아니다. 같은 근본 문제가 다른 도구로 해결될 뿐이다. 양쪽을 모두 이해하면 추상화의 비용과 이득이 선명해진다. 지금은 EKS 쪽에서 시작하고 있지만, 온프레미스 GPU/HPC 영역도 기회가 되면 직접 경험해 보고 싶다.

<br>


# 참고 링크

- [NVIDIA XID Errors Reference](https://docs.nvidia.com/deploy/xid-errors/)
- [AWS NVIDIA GPU 문제 해결](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshoot-gpu.html)
- [Kubernetes node-problem-detector](https://github.com/kubernetes/node-problem-detector)
- [EKS Auto Mode 가이드](https://docs.aws.amazon.com/eks/latest/userguide/automode.html)
- [NVIDIA gpu-operator Helm values reference](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/)
- [AWS EFA 개요](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa.html)
- [aws-ofi-nccl](https://github.com/aws/aws-ofi-nccl)
- [Kubernetes 환경에서 NVIDIA GPU 사용하기]({% post_url 2024-07-19-Dev-Kubernetes-GPU-Setting %})
- [NVIDIA Container Runtime]({% post_url 2024-07-21-Dev-Nvidia-Container-Runtime %})
- [NVIDIA Device Plugin 동작 원리]({% post_url 2024-07-23-Dev-Kubernetes-NVIDIA-GPU-Mechanism %})

<br>