---
title: "[Ubuntu] OS 자동 업데이트가 K8s GPU 노드를 두 번 깨뜨린 이야기"
excerpt: "unattended-upgrades가 NVIDIA 드라이버 버전 불일치와 kube-proxy IPVS 장애를 연쇄적으로 일으킨 과정과 교훈을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Ubuntu
  - unattended-upgrades
  - NVIDIA
  - GPU
  - Kubernetes
  - kube-proxy
  - IPVS
  - Troubleshooting
---

<br>

자정 무렵, 주기적으로 K8s GPU 클러스터 상태를 검토하다가 GPU 워커 노드 풀의 일부에서 `nvidia-smi`가 실패하는 것을 우연히 발견했다. 다행히 해당 노드에서 돌고 있던 GPU Pod가 없어서 실제 장애로 이어지지는 않았지만, 만약 학습 잡이 스케줄된 상태였다면 GPU 할당 실패로 이어졌을 상황이었다.

원인을 추적해 보니 Ubuntu의 `unattended-upgrades`가 새벽에 NVIDIA 드라이버와 Linux 커널을 동시에 자동 업그레이드한 것이 시작이었다. reboot 전에는 NVIDIA 드라이버 버전 불일치가, reboot 후에는 kube-proxy의 IPVS 모듈 로딩 실패가 발생하면서, 하나의 자동 업데이트가 두 단계의 연쇄 장애로 이어졌다. 업무 시간이 아니라 발견이 늦었을 뿐, 문제는 이미 잠복해 있었다.

이 글에서는 발견부터 해결까지의 과정을 따라가면서, 왜 K8s 프로덕션 노드(특히 GPU 노드)에서 OS 자동 업데이트를 통제해야 하는지 정리해 본다.

<br>

# TL;DR

- Ubuntu `unattended-upgrades`가 K8s GPU 노드에서 NVIDIA 드라이버(580.126 → 580.159) + Linux 커널(5.15.0-177 → 5.15.0-179)을 동시에 자동 업그레이드
- **reboot 전**: kernel module(580.126)과 userspace library(580.159) 버전 불일치 → `nvidia-smi` NVML 초기화 실패
- **reboot 후**: 새 커널에서 `ip_vs` 모듈 로딩 실패 → kube-proxy CrashLoopBackOff → K8s 시스템 파드 연쇄 장애
- **교훈**: K8s GPU 노드에서는 `unattended-upgrades`를 비활성화하고, `drain` → upgrade → reboot → `uncordon` 패턴으로 통제해야 한다

<br>

# 배경

## 환경

- K8s(RKE2 v1.34) GPU 워커 노드 풀
- Ubuntu 22.04 LTS
- NVIDIA driver 580 branch (`nvidia-driver-580-server-open`), RTX 5090 x 8
- `unattended-upgrades` 기본 설정 활성화 상태

## unattended-upgrades

Ubuntu의 `unattended-upgrades`는 보안 패치를 자동으로 설치하는 데몬이다. `/etc/apt/apt.conf.d/50unattended-upgrades`에 설정된 `Allowed-Origins`에 따라, cron 주기로 패키지를 자동 업그레이드한다. 일반 서버에서는 보안 패치를 자동으로 받아오는 편리한 도구지만, K8s 노드에서는 예상치 못한 부작용을 일으킬 수 있다. 이 글이 정확히 그 사례다.

## NVIDIA 드라이버의 userspace ↔ kernel module 구조

NVIDIA GPU를 사용하려면 두 계층이 협력해야 한다.

- **kernel module** (`nvidia.ko`): 커널 공간에서 GPU 하드웨어와 직접 통신. `modprobe nvidia`로 적재되며, reboot 시 자동 로드
- **userspace library** (`libnvidia-ml.so` 등): 사용자 공간에서 동작. `nvidia-smi` 같은 CLI 도구가 이 라이브러리를 동적 로딩하여 kernel module과 `ioctl()`로 통신

이 구조는 [Linux 디바이스 드라이버 3계층]({% post_url 2026-02-01-CS-Linux-Device-Driver %})에서 다룬 "유저 라이브러리(`.so`) → 장치 파일(`/dev/*`) → 커널 모듈(`.ko`)" 패턴 그대로다. [Linux 공유 라이브러리]({% post_url 2026-05-13-CS-Linux-Shared-Library %})에서 다룬 soname/ABI 계약도 여기에 적용된다. NVML은 초기화 시 kernel module의 ioctl 인터페이스 버전을 확인하는데, **userspace library 버전과 kernel module 버전이 다르면 초기화를 거부**한다.

핵심은 이것이다: `apt upgrade`로 userspace 패키지(`libnvidia-ml.so`, `nvidia-smi` 등)는 즉시 교체되지만, **kernel module은 이미 메모리에 로드되어 있어서 reboot(또는 명시적 unload/reload) 전까지 옛 버전이 그대로 살아있다.** 이 시간차가 1차 장애의 원인이다.

## Linux 커널 모듈 적재: depmod와 modprobe

kernel module(`.ko`)의 적재에는 두 도구가 핵심 역할을 한다.

- **`depmod`** — 모듈 의존성 지도를 만드는 도구. `/lib/modules/<커널 버전>/` 아래의 `.ko` 파일들을 스캔해서 다음 DB 파일들을 생성한다:
  - `modules.dep`(텍스트) / `modules.dep.bin`(바이너리): 모듈 간 의존성 매핑. "A를 로드하려면 B, C가 먼저 필요하다"는 관계를 기록
  - `modules.alias`(텍스트) / `modules.alias.bin`(바이너리): 하드웨어 ID(PCI, USB 등)와 모듈 간 매핑. 장치를 인식했을 때 어떤 드라이버를 로드할지 결정하는 인덱스
  - `modules.symbols`(텍스트) / `modules.symbols.bin`(바이너리): 모듈이 export하는 커널 심볼(함수/변수)의 위치 정보
- **`modprobe`** — `depmod`가 만든 DB를 참조해서 kernel module을 의존성과 함께 로드하는 도구. 예를 들어 `modprobe ip_vs`를 실행하면, `modules.dep`에서 `ip_vs`가 `nf_conntrack`에 의존한다는 것을 읽고 `nf_conntrack`을 먼저 로드한 뒤 `ip_vs`를 로드한다. `.ko` 파일 경로를 직접 지정해야 하는 `insmod`와 달리, 모듈 이름만으로 의존성까지 자동 처리한다

여기서 두 가지를 짚어 둔다.

**첫째, DB는 커널 버전별로 독립이다.** 각 커널 버전은 `/lib/modules/<버전>/`에 자기만의 `.ko` 파일과 DB 파일을 갖는다. `modprobe`는 현재 부팅된 커널의 `uname -r` 값으로 어떤 디렉토리를 참조할지 결정한다.

```
/lib/modules/
├── 5.15.0-177-generic/    ← 이전 커널 (DB 정상, ip_vs 잘 로드됨)
│   ├── modules.dep
│   ├── modules.dep.bin
│   └── kernel/...
└── 5.15.0-179-generic/    ← 새 커널 (DB가 불완전할 수 있음)
    ├── modules.dep
    ├── modules.dep.bin
    └── kernel/...
```

**둘째, `modprobe`는 텍스트 파일이 아니라 바이너리 캐시(`.bin`)를 우선 참조한다.** 성능을 위해 `modules.dep.bin`을 먼저 읽고, 이 파일이 아예 없을 때만 텍스트 `modules.dep`로 폴백한다. 문제는 바이너리 캐시가 **존재는 하지만 내용이 불완전한** 경우다. `modprobe`는 파일이 있으니 신뢰하고 읽지만 원하는 항목을 찾지 못해 실패하고, 텍스트 파일로 폴백하지도 않는다.

`depmod`는 데몬이 아니라 일회성 도구로, 보통 커널 패키지 설치 시 post-install hook으로 자동 실행된다. 전체 흐름을 정리하면 다음과 같다.

```
[새 Linux 커널 설치]
       │
       ▼
1. depmod 실행 ──▶ /lib/modules/<새 커널>/ 아래 모듈들을 스캔하여
                    의존성 지도(modules.dep + .bin 바이너리 캐시) 작성
       │
       ▼
[reboot → 새 커널로 부팅]
       │
       ▼
2. modprobe ip_vs 실행
       │
       ▼
3. modprobe가 modules.dep.bin 확인 ──▶ "ip_vs를 로드하려면 nf_conntrack이 먼저 필요"
       │
       ▼
4. nf_conntrack을 먼저 로드한 뒤, ip_vs를 로드
```

**`.ko` 파일이 디렉토리에 존재하더라도 바이너리 캐시가 최신화되지 않으면 `modprobe`는 모듈을 찾지 못한다.** 그리고 `depmod`는 주기적으로 실행되는 프로세스가 아니므로, 한번 stale 상태가 되면 누군가 명시적으로 `depmod -a`를 실행하지 않는 한 자동으로 복구되지 않는다. 이 메커니즘의 실전 사례가 2차 장애에서 등장한다. 지금은 여기까지만 알아두자.

> 더 파고 싶다면 [Linux 디바이스 드라이버]({% post_url 2026-02-01-CS-Linux-Device-Driver %})의 커널 모듈 적재 섹션과 `modprobe(8)`, `depmod(8)` 매뉴얼을 참고하면 된다.

<br>

# 1차 장애: NVIDIA 드라이버 버전 불일치

## 발견

클러스터 인벤토리 갱신 중 SSH로 각 노드의 `nvidia-smi`를 호출했더니, 4 2대에서 실패했다.

```bash
# 전체 GPU 워커 노드 driver 버전 매트릭스 수집
~$ for h in $GPU_WORKERS; do
    echo "=== $h ==="
    ssh $h "nvidia-smi --query-gpu=index,driver_version,name --format=csv,noheader 2>&1 | head -3"
  done

# 실행 결과 (발췌)
=== gpu-worker-1 ===
Failed to initialize NVML: Driver/library version mismatch
NVML library version: 580.159
=== gpu-worker-2 ===
0, 580.126.09, NVIDIA GeForce RTX 5090, 32607 MiB
=== gpu-worker-3 ===
Failed to initialize NVML: Driver/library version mismatch
NVML library version: 580.159
# ... 나머지 노드는 580.126.09로 정상
```

gpu-worker-1, gpu-worker-3만 `NVML library version: 580.159`로 시작에 실패했다. 나머지 노드는 580.126.09로 정상이었다. 같은 노드 풀인데 호스트 상태가 갈렸다.

K8s 측에서는 전체 노드가 `Ready`로 보이고, NFD(Node Feature Discovery) label도 `nvidia.com/gpu.present=true`, capacity도 `nvidia.com/gpu: 8`로 살아있었다. 즉, **K8s scheduler는 이 호스트 측 부정합을 전혀 감지하지 못하고** 있었다.

## 진단

### kernel module vs userspace library 버전 비교

`Driver/library version mismatch` 에러는 NVML이 초기화 시 kernel module과 ioctl 버전 매칭에 실패했다는 뜻이다. 에러 메시지에 `NVML library version: 580.159`(userspace 쪽)는 찍혀 있으므로, 비교 대상인 kernel module 쪽 버전을 먼저 확인해야 어느 쪽이 어긋났는지 알 수 있다.

```bash
# /proc/driver/nvidia/version: 현재 커널에 로드된 nvidia.ko 버전
~$ for h in $GPU_WORKERS; do
    echo "=== $h ==="
    ssh $h "cat /proc/driver/nvidia/version | head -1"
  done

# 실행 결과: 전체 노드 동일
=== gpu-worker-1 ===
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.126.09  Release Build ...
=== gpu-worker-2 ===
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.126.09  Release Build ...
=== gpu-worker-3 ===
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.126.09  Release Build ...
# ... 나머지 노드도 동일
```

전체 노드 kernel module은 **580.126.09 동일**. 그런데 gpu-worker-1, gpu-worker-3의 NVML(userspace)은 **580.159**. "userspace만 새 버전, kmod은 옛 버전" 패턴이 확정됐다.

### 누가 업그레이드했는가

`apt/history.log`의 `Commandline:` 필드로 호출 주체를 확인했다.

```bash
# gpu-worker-1의 apt history.log에서 해당 날짜 트랜잭션 확인
~$ ssh gpu-worker-1 "awk '/Start-Date: 2026-05-21/,/End-Date: 2026-05-21/' /var/log/apt/history.log | head -20"

# 실행 결과 (발췌)
Start-Date: 2026-05-21  06:52:45
Commandline: /usr/bin/unattended-upgrade
Install: nvidia-firmware-580-server-580.159.03:amd64 ...
Upgrade: libnvidia-common-580-server, nvidia-driver-580-server-open, nvidia-dkms-580-server-open,
         libnvidia-compute-580-server, nvidia-utils-580-server, libnvidia-gl-580-server ...
         (모두 580.126.09 → 580.159.03)
End-Date: 2026-05-21  06:55:58
Start-Date: 2026-05-21  06:56:07
Commandline: /usr/bin/unattended-upgrade
Install: linux-image-5.15.0-179-generic, linux-headers-5.15.0-179-generic ...
Upgrade: linux-generic (5.15.0.177.162 → 5.15.0.179.163)
End-Date: 2026-05-21  06:57:34
```

`Commandline: /usr/bin/unattended-upgrade` — **사용자가 아닌 `unattended-upgrade` 데몬**이 호출 주체였다. 인프라 팀에도 확인한 결과 "패키지 관련 작업 별도 없었음"이었다.

같은 cron 사이클에서 세 묶음이 동시에 올라갔다.

1. **NVIDIA driver userspace + dkms** 580.126.09 → 580.159.03 (15개 패키지)
2. **Linux kernel image** 5.15.0-177 → 5.15.0-179 (headers, modules 동반)
3. 기타 (`libgnutls30`, `rsync` 등)

나머지 노드에서는 같은 업그레이드 흔적이 없었다. `unattended-upgrades`의 cron이 노드별로 다른 시각에 실행되기 때문에, 이 노드들은 아직 자동 업그레이드가 트리거되지 않은 상태였을 뿐이다.

## 원인

배경에서 설명한 구조 그대로다.

| 계층 | 업그레이드 전 | 업그레이드 후 (reboot 전) |
|------|-------------|------------------------|
| userspace (`libnvidia-ml.so`, `nvidia-smi`) | 580.126.09 | **580.159.03** (apt가 즉시 교체) |
| kernel module (`nvidia.ko`) | 580.126.09 | **580.126.09** (메모리에 로드된 옛 버전 그대로) |

NVML은 초기화 첫 단계에서 kernel module과 ioctl 인터페이스 버전을 매칭한다. 불일치를 감지하면 `Failed to initialize NVML: Driver/library version mismatch`로 fail-fast한다.

여기서 중요한 한 가지: **NVIDIA driver만 올라간 게 아니라 Linux kernel image 자체도 5.15.0-177 → 5.15.0-179로 교체됐다.** DKMS(Dynamic Kernel Module Support)가 새 kernel용 `nvidia.ko` 580.159.03을 빌드해 두었으므로, reboot 하면 새 kernel + 새 driver 조합이 활성화된다. 이 사실이 2차 장애의 복선이다.

<br>

# 해결 1: cordon + reboot

## cordon

reboot 전에 K8s scheduler가 두 노드에 워크로드를 배치하지 않도록 차단했다.

```bash
# 학습 잡이 mismatch 노드에 스케줄되는 것을 방지
~$ kubectl cordon gpu-worker-1 gpu-worker-3
```

## reboot 및 사후 검증

인프라 팀에 reboot를 요청하고, 완료 후 사후 검증을 실행했다.

```bash
# kmod과 userspace lib 버전 일치 확인
~$ for h in gpu-worker-1 gpu-worker-3; do
    echo "=== $h ==="
    ssh $h "cat /proc/driver/nvidia/version | head -1"
    ssh $h "nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1"
    ssh $h "uname -r"
  done

# 실행 결과
=== gpu-worker-1 ===
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.159.03 ...
580.159.03
5.15.0-179-generic
=== gpu-worker-3 ===
NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.159.03 ...
580.159.03
5.15.0-179-generic
```

kernel module과 userspace library 모두 580.159.03으로 일치. GPU도 8장 전부 정상 인식. 호스트 측 정합성은 100% 회복됐다.

"끝난 줄 알았는데" — K8s 측 시스템 파드를 점검하니 또 다른 문제가 기다리고 있었다.

<br>

# 2차 장애: kube-proxy CrashLoopBackOff

## 발견

reboot 후 노드 STATUS는 `Ready,SchedulingDisabled`(cordon 유지)로 정상이었지만, 시스템 파드 상태가 문제였다.

```bash
# 시스템 파드 상태 확인
~$ kubectl get pods -A --field-selector spec.nodeName=gpu-worker-1 | grep -vE 'Completed|Succeeded'
```

| Namespace | Pod | STATUS | RESTARTS |
|-----------|-----|--------|----------|
| kube-system | kube-proxy-gpu-worker-1 | **CrashLoopBackOff** | 22회 (90분간) |
| kube-system | rke2-canal (CNI) | Unknown | 0 |
| gpu-operator | nvidia-device-plugin | Unknown | 0 |
| gpu-operator | gpu-feature-discovery | Unknown | 0 |
| gpu-operator | nvidia-container-toolkit | Unknown | 0 |
| gpu-operator | nvidia-dcgm-exporter | Unknown | 0 |
| metallb-system | metallb-speaker | CrashLoopBackOff | 37회 |
| monitoring | fluent-bit | Unknown | 0 |

gpu-worker-3도 동일한 패턴이었다. kube-proxy가 죽으니 같은 노드의 CNI, gpu-operator daemonset, metallb, monitoring
까지 줄줄이 Unknown / CrashLoopBackOff로 무너졌다.

> kube-proxy가 죽으면 왜 다른 파드까지 무너지는가? kube-proxy는 노드의 iptables/IPVS 규칙을 관리해서 K8s Service → Pod 트래픽을 라우팅한다. kube-proxy가 없으면 해당 노드에서 ClusterIP/NodePort 기반의 서비스 통신이 끊기고, 이에 의존하는 파드들이 liveness/readiness probe 실패나 API server 통신 장애로 Unknown 또는 CrashLoopBackOff에 빠진다. 이 노드에서는 CNI(rke2-canal), gpu-operator daemonset, metallb, monitoring까지 연쇄적으로 영향을 받았다.

## 로그 분석

```bash
~$ kubectl -n kube-system logs kube-proxy-gpu-worker-1 --tail=10

# 실행 결과 (핵심만 발췌)
time="2026-05-21T15:58:07Z" level=warning msg="Running modprobe ip_vs failed with message:
  `modprobe: WARNING: Module ip_vs not found in directory /lib/modules/5.15.0-179-generic`,
  error: exit status 1"
time="2026-05-21T15:58:07Z" level=error msg="Could not get ipvs family information from the kernel.
  It is possible that ipvs is not enabled in your kernel.
  Native loadbalancing will not work until this is fixed."
E0521 15:58:07.143666 server.go:135 "Error running ProxyServer"
  err="can't use the IPVS proxier: Ipvs not supported"
```

이 RKE2 클러스터의 kube-proxy는 IPVS(IP Virtual Server) mode로 동작한다. 시작 시 `modprobe ip_vs`를 실행하는데, 새 커널(5.15.0-179)에서 `ip_vs` 모듈을 찾지 못해 fail-fast로 종료한 것이다. 22회 CrashLoopBackOff의 근본 원인이다.

## 범위 확인

클러스터 전체 kube-proxy 상태를 대조해 보니, **새 커널 5.15.0-179 노드 2개만 fail**이었다.

```bash
~$ kubectl get pods -n kube-system | grep kube-proxy | grep -E 'gpu-worker'

# 실행 결과 (발췌)
kube-proxy-gpu-worker-1   0/1   CrashLoopBackOff   23   94m   # kernel 5.15.0-179
kube-proxy-gpu-worker-2   1/1   Running            0    66d   # kernel 5.15.0-171
kube-proxy-gpu-worker-3   0/1   CrashLoopBackOff   23   95m   # kernel 5.15.0-179
# ... 나머지 노드는 Running (kernel 5.15.0-171)
```

같은 RKE2 v1.34 + 같은 kube-proxy 이미지인데 새 커널 노드만 fail. 이미지 버그가 아니라 **kernel 5.15.0-179 환경에서의 모듈 로딩 문제**임이 확정됐다.

## 모순 상황

호스트에 직접 들어가 확인해 보니, 모듈 파일 자체는 정상이었다.

```bash
# ip_vs.ko 파일 존재 확인
~$ ssh gpu-worker-1 "ls /lib/modules/5.15.0-179-generic/kernel/net/netfilter/ipvs/ip_vs.ko"
/lib/modules/5.15.0-179-generic/kernel/net/netfilter/ipvs/ip_vs.ko

# 패키지 설치 확인
~$ ssh gpu-worker-1 "dpkg -l | grep linux-modules-extra-5.15.0-179"
ii  linux-modules-extra-5.15.0-179-generic  5.15.0-179.189  amd64

# modules.dep 텍스트 파일 확인
~$ ssh gpu-worker-1 "grep ip_vs /lib/modules/5.15.0-179-generic/modules.dep | head -1"
kernel/net/netfilter/ipvs/ip_vs.ko: kernel/net/netfilter/nf_conntrack.ko ...
```

`.ko` 파일 존재, 패키지 설치 정상, `modules.dep` **텍스트 파일**에도 등록 — 그런데 `modprobe`가 "Module not found"를 뱉는 모순적 상황이었다.

배경에서 설명했듯이 `modprobe`는 텍스트 파일(`modules.dep`)이 아니라 **바이너리 캐시(`modules.dep.bin`)를 우선 참조**한다. 텍스트 파일을 `grep`하면 항목이 보이지만, `modprobe`가 실제로 읽는 바이너리 캐시가 새 커널(5.15.0-179)에 맞게 완전히 생성되지 않았을 가능성이 높다.

혼동하지 말아야 할 것은, 이전 커널(5.15.0-177)에서는 `ip_vs`가 정상적으로 로드되어 kube-proxy가 IPVS mode로 잘 동작하고 있었다는 점이다. `ip_vs` 자체가 시스템에 없는 게 아니라, **새 커널 버전의 모듈 DB가 불완전한 것**이 문제였다. `unattended-upgrades`가 같은 cron 사이클에서 커널 패키지와 NVIDIA dkms를 연달아 설치하면서 여러 post-install hook의 `depmod` 호출이 겹친 것이 원인으로 추정된다.

<br>

# 해결 2: depmod + modprobe

배경에서 설명한 `depmod`와 `modprobe`를 직접 사용할 차례다. `depmod -a`는 텍스트 DB와 바이너리 캐시를 **모두** 재생성한다.

```bash
# 1) 새 커널의 모듈 DB 전체 재생성 (텍스트 + 바이너리 캐시)
~$ ssh gpu-worker-1 "sudo depmod -a 5.15.0-179-generic"

# 2) host kernel에 ip_vs 적재
~$ ssh gpu-worker-1 "sudo modprobe ip_vs && lsmod | grep ip_vs"

# 실행 결과
ip_vs                 176128  0
nf_conntrack          172032  3 xt_conntrack,nf_nat,ip_vs
nf_defrag_ipv6         24576  2 nf_conntrack,ip_vs
libcrc32c              16384  6 nf_conntrack,nf_nat,btrfs,nf_tables,raid456,ip_vs
```

host kernel에 `ip_vs`가 정상 적재됐다. 의존 모듈(`nf_conntrack`, `nf_defrag_ipv6`, `libcrc32c`)도 자동으로 잡혔다.

별도로 kube-proxy pod를 강제 restart하지 않았다. CrashLoopBackOff의 exponential backoff 타이머가 약 5분 후 다음 시도를 트리거했고, 이번에는 host kernel에 `ip_vs`가 이미 적재되어 있어 `modprobe`가 성공했다.

```bash
# kube-proxy 자동 회복 확인
~$ kubectl get pods -n kube-system | grep kube-proxy-gpu-worker-1
kube-proxy-gpu-worker-1    1/1   Running    25 (5m ago)   103m
```

25번째 재시작에서 정상 시작. kube-proxy가 살아나자 나머지 시스템 파드도 연쇄적으로 회복됐다.

gpu-worker-3에도 동일한 sequence를 적용한 후, 모든 시스템 파드가 Running으로 돌아온 것을 확인하고 uncordon했다.

```bash
# 두 노드 uncordon
~$ kubectl uncordon gpu-worker-1 gpu-worker-3

# 최종 상태 확인
~$ kubectl get nodes -o wide | grep gpu-worker
gpu-worker-1   Ready   ray   66d   v1.34.3+rke2r1   ...   5.15.0-179-generic   containerd://2.1.5
gpu-worker-2   Ready   ray   66d   v1.34.3+rke2r1   ...   5.15.0-171-generic   containerd://2.1.5
gpu-worker-3   Ready   ray   66d   v1.34.3+rke2r1   ...   5.15.0-179-generic   containerd://2.1.5
# ... 나머지 노드도 Ready (kernel 5.15.0-171)
```

두 노드 모두 `Ready`, 학습 잡 재개 가능 상태로 복귀했다.

<br>

# 교훈

## 왜 K8s 노드에서 OS 자동 업데이트를 통제해야 하는가

이번 사건은 하나의 `unattended-upgrades` cron 사이클에서 NVIDIA driver + Linux kernel이 동시에 자동 업그레이드된 것에서 시작했다. 결과적으로 **reboot 전에도, reboot 후에도** 장애가 발생했다.

K8s 노드에서 OS 자동 업데이트가 위험한 이유를 4가지로 정리할 수 있다.

### 1. 부분 upgrade 후 reboot 누락 시 상태 부정합

이번 사건의 1차 장애가 정확히 이 패턴이다. userspace library는 `apt`가 즉시 교체하지만, kernel module은 reboot 전까지 옛 버전이 메모리에 살아있다. 이 시간차 동안 NVML 같은 라이브러리는 kernel module과 버전 매칭에 실패한다.

K8s scheduler는 이런 호스트 측 부정합을 감지하지 못한다. 이 사건에서도 두 노드 모두 `Ready` + NFD label 정상 + GPU capacity 8이었다. 만약 cordon 없이 학습 잡이 먼저 스케줄됐다면, 학습이 GPU를 잡지 못하고 실패한 후에야 문제를 인지했을 것이다.

### 2. 검증 안 된 조합의 첫 활성화

reboot은 단순히 `nvidia.ko`를 재로드하는 게 아니다. 이 사건에서는 **Linux kernel 자체가 5.15.0-177 → 5.15.0-179로 바뀌었다.** reboot 후 새 kernel + 새 NVIDIA driver + 기존 kubelet + 기존 containerd + 기존 CNI 조합이 이 클러스터에서 **처음** 활성화된다.

2차 장애(kube-proxy의 `ip_vs` 모듈 로딩 실패)가 이 케이스다. kernel minor patch 수준에서 ABI가 크게 바뀌는 일은 드물지만, 모듈 로딩 보조 DB(`modules.alias` 등)의 상태나 모듈 적재 순서 같은 환경 의존적 문제는 새 kernel에서 처음 노출될 수 있다.

### 3. 타이밍 무통제로 노드 간 비대칭

`unattended-upgrades`의 cron은 노드별로 다른 시각에 실행된다(random sleep 포함). 이 사건에서도 풀의 일부 노드만 업그레이드가 트리거되고 나머지는 아직 실행되지 않았다.

결과적으로 같은 노드 풀 안에서 kernel/driver 버전이 비대칭이 된다(gpu-worker-1,3은 5.15.0-179/580.159, gpu-worker-2,4는 5.15.0-171/580.126). GPU 분산학습(multi-node training)에서는 노드 간 driver 차이가 NCCL 호환성 문제로 표면화될 수 있다.

### 4. 운영자가 변경을 모름

자동 업데이트는 `dpkg.log`나 `apt/history.log`를 봐야 사후에 인지할 수 있다. 이 사건도 인벤토리 갱신 중 우연히 발견한 것이다.

K8s Node object의 `.status.nodeInfo.kernelVersion`은 reboot 후에 갱신되므로 모니터링은 가능하지만, **reboot 전에는 userspace만 바뀌므로 K8s 측에서 감지할 수 없다.**

### 근거

이 권장은 "어딘가에 한 줄로 적혀 있어서"가 아니라, 여러 출처에서 수렴하는 커뮤니티 합의다.

- **kubeadm 업그레이드 문서**: K8s 패키지(kubeadm/kubelet/kubectl)에 `apt-mark hold`를 사용하고, `drain` → upgrade → `uncordon` 수동 패턴을 규정한다. OS 패키지에 대한 직접 언급은 없지만, K8s 컴포넌트도 자동 업그레이드를 안 하는데 kernel/driver는 더 위험하다
- **Safely Drain a Node**: "`kubectl drain`을 kernel upgrade, hardware maintenance 등 전에 사용하라"고 명시한다
- **AKS (Azure Kubernetes Service)**: SecurityPatch/NodeImage 채널에서 "Linux unattended upgrades are disabled by default"로 명시적 비활성화
- **kured (CNCF Sandbox)**: K8s 노드 reboot를 `drain` → reboot → `uncordon`으로 자동화하는 daemon. 존재 자체가 "노드 reboot는 통제되어야 한다"는 합의
- **NVIDIA GPU Operator**: driver upgrade controller가 `drain` → kmod unload → upgrade → reload 패턴을 자동화한다. host OS의 자동 driver 업그레이드는 위험하다는 전제가 설계에 내재되어 있다

## 어떻게 막을 수 있는가

강한 순서대로 정리하면 다음과 같다.

| # | 옵션 | 동작 | trade-off |
|---|------|------|-----------|
| 1 | `unattended-upgrades` 완전 비활성 | 자동 upgrade 0건 | 보안 패치도 안 들어옴. 별도 maintenance window 운영 필수 **(GPU 노드 권장)** |
| 2 | `Allowed-Origins`에서 nvidia/kernel 제외 | security만 허용, nvidia driver + kernel 자동 upgrade 차단 | 어떤 패키지가 reboot 필요한지 enumeration 필요. 누락 시 동일 사고 재발 |
| 3 | `apt-mark hold` | 특정 패키지만 자동 upgrade 차단 | hold가 단일 패키지 단위라 의존 lib가 단독 upgrade 될 수 있음 |
| 4 | `Automatic-Reboot "true"` + 시각 지정 | upgrade 직후 자동 reboot → mismatch 윈도우 닫힘 | in-flight 학습 강제 종료 가능. GPU 노드에는 위험 |
| 5 | 모니터링/alert만 추가 | mismatch 발생 시 자동 감지 | 사고 발생 자체는 못 막음. fail-fast 보조 수단 |

GPU 노드에는 **옵션 1 + 옵션 5 병행**이 가장 안전하다. 보안 패치는 정해진 maintenance window에 아래 패턴으로 일괄 처리한다.

## 권장 패턴: drain → upgrade → reboot → uncordon

```bash
# 1. drain: 워크로드를 다른 노드로 이동
~$ kubectl drain gpu-worker-1 --ignore-daemonsets --delete-emptydir-data

# 2. upgrade: OS 패키지 업그레이드
~$ ssh gpu-worker-1 "sudo apt update && sudo apt upgrade -y"

# 3. reboot: 새 kernel + 새 driver 활성화
~$ ssh gpu-worker-1 "sudo reboot"

# 4. 사후 검증
~$ ssh gpu-worker-1 "uname -r; nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1"

# 5. uncordon: 노드를 다시 스케줄 가능으로
~$ kubectl uncordon gpu-worker-1
```

`cordon`만으로는 기존 pod가 그대로 남는다. `drain`은 기존 pod까지 evict하므로, in-flight 워크로드 없이 안전하게 유지보수할 수 있다. PodDisruptionBudget을 설정해 두면 `drain` 시에도 서비스 가용성을 보장할 수 있다.

<br>

# 참고 링크

- [kubeadm 클러스터 업그레이드](https://kubernetes.io/ko/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/)
- [Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)
- [Node Shutdowns — unattended-upgrades 충돌 주의](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/)
- [kured — Kubernetes Reboot Daemon](https://kured.dev/)
- [NVIDIA GPU Operator — GPU Driver Upgrades](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-driver-upgrades.html)
- [AKS — Node OS Auto-upgrade](https://learn.microsoft.com/en-us/azure/aks/auto-upgrade-node-os-image)
- [Linux 디바이스 드라이버: 3계층 구조]({% post_url 2026-02-01-CS-Linux-Device-Driver %})
- [Linux 공유 라이브러리(.so)]({% post_url 2026-05-13-CS-Linux-Shared-Library %})

<br>
