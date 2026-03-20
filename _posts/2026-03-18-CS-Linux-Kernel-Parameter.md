---
title:  "[CS] 리눅스 커널 파라미터와 sysctl"
excerpt: "리눅스 커널 파라미터의 개념, sysctl을 이용한 조회·설정, /etc/sysctl.d/ 파일 체계에 대해 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - sysctl
  - 커널파라미터
---

<br>

Kubernetes를 학습하다 보면 커널 파라미터가 끊임없이 등장한다. 클러스터를 구성할 때마다 `net.bridge.bridge-nf-call-iptables`, `net.ipv4.ip_forward`를 설정해야 하고, 컨테이너 환경에서 `vm.swappiness`를 조정해야 한다는 이야기도 심심치 않게 들린다. `/etc/sysctl.d/`를 들여다보니 번호가 붙은 설정 파일들이 여러 개 있고, 누가 어떤 순서로 적용하는지도 궁금해졌다. 간단하게라도 정리해 본다.

<br>

# TL;DR

- **커널 파라미터**: 리눅스 커널의 동작을 런타임에 조정하는 설정 값이다. `net.*`, `vm.*`, `fs.*`, `kernel.*` 등의 네임스페이스로 분류된다.
- **sysctl**: 커널 파라미터를 조회·변경하는 인터페이스로, 모든 Linux 배포판에서 동일하게 동작한다.
- **커널 파라미터 설정값**: `/etc/sysctl.d/`의 `.conf` 파일들은 **번호 → 알파벳 순서**로 로드되며, 같은 파라미터가 여러 파일에 있으면 **나중에 읽힌 값이 이긴다**.
- **컨테이너 환경에서의 커널 파라미터**: VM과 달리 컨테이너는 자체 커널 없이 호스트 커널을 공유하므로, 커널 파라미터 설정이 모든 컨테이너에 직접 영향을 미친다. Kubernetes 환경에서 IP 포워딩, 브릿지, 메모리 오버커밋 등의 설정이 필수적인 이유다.

<br>

# 리눅스 커널 파라미터

## 커널 파라미터란

리눅스 커널은 OS의 핵심으로, 하드웨어·네트워크·메모리·프로세스 등을 관리한다. **커널 파라미터**는 이러한 커널의 동작 방식을 런타임에 조정할 수 있는 설정 값이다. 커널을 다시 컴파일하거나 재부팅하지 않고도 동작을 바꿀 수 있다.

> 대부분의 커널 파라미터는 런타임에 변경 가능하지만, 일부 파라미터는 부팅 시에만 설정되거나 read-only로 노출되어 `sysctl -w`로 변경할 수 없는 경우도 있다. 변경 시 `sysctl: setting key "...": Invalid argument` 등의 에러가 발생하면 해당 파라미터의 변경 가능 여부를 확인해야 한다.

예를 들어:
- `net.ipv4.ip_forward = 1` → IP 패킷 포워딩 활성화 (라우터·컨테이너 환경 필수)
- `vm.overcommit_memory = 1` → 메모리 오버커밋 정책 제어
- `fs.file-max = 1048576` → 시스템 전체 최대 열린 파일 수 제한

## /proc/sys/와 procfs

커널 파라미터는 `/proc/sys/` 디렉토리를 통해 노출된다. `/proc/`는 **procfs(proc filesystem)**라는 가상 파일시스템으로, 디스크에 실제 파일이 저장되어 있는 것이 아니라 **커널이 메모리 상의 내부 데이터를 파일처럼 보여주는** 인터페이스다. 파일을 읽으면 커널이 그 시점의 값을 동적으로 생성해서 반환하고, 파일에 쓰면 커널이 해당 값을 즉시 변경한다.

`/proc/` 전체가 커널 정보를 노출하는 가상 파일시스템이고, 그 중 `/proc/sys/` 하위가 **런타임에 변경 가능한 커널 파라미터**를 담당한다. 후술할 `sysctl` 명령어는 결국 이 `/proc/sys/` 하위 파일을 읽고 쓰는 래퍼(wrapper)다.

```bash
# procfs 마운트 확인
mount | grep proc
# proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)

# /proc/sys/ 하위의 최상위 디렉토리 = 네임스페이스
ls /proc/sys/
# abi  crypto  debug  dev  fs  kernel  net  sunrpc  user  vm
```

## 네임스페이스

커널 파라미터는 관리 영역별 **네임스페이스**로 분류되며, `/proc/sys/` 하위 디렉토리 구조가 이 네임스페이스를 그대로 반영한다.

| 네임스페이스 | /proc/sys/ 경로 | 관리 영역 | 대표 파라미터 |
| --- | --- | --- | --- |
| **kernel** | `/proc/sys/kernel/` | 프로세스, 스케줄링, 패닉 | `kernel.panic`, `kernel.pid_max` |
| **vm** | `/proc/sys/vm/` | 가상 메모리, 스왑, 페이지 캐시 | `vm.swappiness`, `vm.overcommit_memory` |
| **net** | `/proc/sys/net/` | 네트워크 스택 (IPv4, IPv6, bridge 등) | `net.ipv4.ip_forward`, `net.bridge.bridge-nf-call-iptables` |
| **fs** | `/proc/sys/fs/` | 파일시스템, 파일 디스크립터 | `fs.file-max`, `fs.inotify.max_user_watches` |
| **dev** | `/proc/sys/dev/` | 디바이스 드라이버 | `dev.cdrom.autoclose` |

```bash
# 네임스페이스별 파라미터 수 확인
sysctl -a 2>/dev/null | grep -c ^kernel   # kernel.*
sysctl -a 2>/dev/null | grep -c ^vm       # vm.*
sysctl -a 2>/dev/null | grep -c ^net      # net.*
sysctl -a 2>/dev/null | grep -c ^fs       # fs.*
```

<br>

# sysctl

## sysctl이란

`sysctl`은 커널 파라미터를 **런타임에 조회·변경**하는 인터페이스다. 내부적으로 `/proc/sys/` 디렉토리의 가상 파일을 읽고 쓴다.

```bash
# 조회
sysctl net.ipv4.ip_forward
# net.ipv4.ip_forward = 1

# 같은 값을 /proc/sys/로 직접 조회
cat /proc/sys/net/ipv4/ip_forward
# 1
```

`sysctl` 명령어의 파라미터 이름에서 `.`은 `/proc/sys/` 하위의 디렉토리 구분자(`/`)에 대응한다.

| sysctl 파라미터 | /proc/sys/ 경로 |
| --- | --- |
| `net.ipv4.ip_forward` | `/proc/sys/net/ipv4/ip_forward` |
| `vm.overcommit_memory` | `/proc/sys/vm/overcommit_memory` |
| `kernel.panic` | `/proc/sys/kernel/panic` |
| `fs.file-max` | `/proc/sys/fs/file-max` |

## 배포판 호환성

`sysctl`은 Linux 커널이 제공하는 `/proc/sys/` 인터페이스를 사용하므로, **Ubuntu, RHEL, Rocky, Amazon Linux, Debian, SUSE 등 모든 Linux 배포판에서 동일하게 동작**한다. `procps` 패키지(또는 `procps-ng`)에 포함되어 있으며 사실상 모든 배포판에 기본 설치된다.

다만 배포판마다 다를 수 있는 것들이 있다:
- **기본값**: 배포판에 따라 다를 수 있음 (예: `vm.dirty_ratio` 등)
- **커널 버전에 따른 파라미터 차이**: 새 커널에서 파라미터가 추가되거나 동작이 변경될 수 있음
- **설정 파일 경로 관례**: `/etc/sysctl.conf`만 사용하는 구형 배포판 vs `/etc/sysctl.d/`를 지원하는 최신 배포판

> BSD 계열(macOS, FreeBSD)에도 `sysctl` 명령어가 있지만 파라미터 체계가 다르다. 이 글에서 다루는 내용은 Linux `sysctl`에 한정한다.

<br>

# 설정 파일 체계와 로드 순서

커널 파라미터를 변경하는 방법을 이해하려면, 먼저 설정 파일이 어디에 있고 어떤 순서로 읽히는지를 알아야 한다.

## 설정 파일 디렉토리

커널 파라미터의 영구 설정은 여러 디렉토리에 분산될 수 있다. `sysctl --system` 실행 시(또는 부팅 시) 아래 디렉토리들에서 `.conf` 파일을 수집한다.

| 경로 | 용도 |
| --- | --- |
| `/usr/lib/sysctl.d/` | 패키지·배포판 기본값 (패키지 관리자가 관리, 직접 수정 비권장) |
| `/run/sysctl.d/` | 런타임 생성 설정 (임시, 재부팅 시 사라짐) |
| `/etc/sysctl.d/` | **관리자 커스텀 설정** (가장 많이 사용) |
| `/etc/sysctl.conf` | 전통적 설정 파일 (항상 마지막에 적용되는 특수 케이스) |

관리자가 커스텀 설정을 넣을 때는 `/etc/sysctl.d/`에 파일을 추가하는 것이 권장된다.

## 로드 순서: 파일명 기준 머지

핵심 규칙은 **디렉토리 순서가 아니라 파일명 순서**다. 모든 디렉토리의 `.conf` 파일을 한데 모은 뒤, **파일명의 문자열(lexicographic) 정렬 순서대로** 적용한다. 같은 파라미터가 여러 파일에 있으면 나중에 적용된 파일의 값이 덮어쓴다. `/etc/sysctl.conf`만 예외로 항상 마지막에 적용된다.

예를 들어 `/etc/sysctl.d/00-defaults.conf`와 `/usr/lib/sysctl.d/10-default-yama-scope.conf`가 있으면, `/etc/sysctl.d/`가 "나중" 디렉토리임에도 파일명 `00-*`이 `10-*`보다 앞이므로 `00-defaults.conf`가 먼저 적용된다.

**같은 파일명이 여러 디렉토리에 존재**하는 경우에만 디렉토리 우선순위가 적용된다. `/etc/sysctl.d/`가 `/run/sysctl.d/`를, `/run/sysctl.d/`가 `/usr/lib/sysctl.d/`를 이긴다. 우선순위가 낮은 쪽의 동명 파일은 무시된다.

## 파일명 규칙

파일명에 대해 systemd가 강제하는 형식 제한은 없다. `100-custom.conf`, `999-override.conf` 같은 세 자리 이상의 숫자도 유효하고, 숫자 없이 `custom.conf`처럼 문자로 시작하는 파일명도 정상적으로 로드된다. 문자열 정렬에서 숫자(`0`-`9`)가 알파벳(`a`-`z`)보다 앞이므로, 숫자로 시작하는 파일이 먼저 로드되고 문자로 시작하는 파일이 그 뒤에 온다.

다만, 정렬이 숫자 크기가 아닌 **문자열 기준**이라는 점이 중요하다. 두 자리 숫자(00-99) 범위에서는 문자열 순서와 숫자 순서가 일치하지만, 세 자리 이상을 섞으면 의도와 다르게 동작할 수 있다.

```
# 문자열 정렬 순서 (숫자 크기 순서가 아님)
100-custom.conf      # "1" < "2"이므로 20보다 앞
20-defaults.conf
50-default.conf
99-amazon.conf
custom.conf          # 문자로 시작 → 숫자 뒤에 정렬
```

위 예시에서 `100-custom.conf`는 숫자상 100이지만, 문자열 `"1"` < `"2"`이므로 `20-defaults.conf`보다 **앞에** 로드된다.

## 번호 대역 관례

실무에서는 관례적으로 **00-99 두 자리 숫자**를 사용한다.
- 대부분의 배포판과 패키지가 두 자리 컨벤션을 따름
- 두 자리 범위에서는 문자열 순서와 숫자 순서가 일치하므로 직관적
- 세 자리 이상이 필요할 만큼 파일이 많아지면, 설정 관리 자체를 재고해야 할 신호

번호 대역 별 용도도 관례적으로 정해져 있다. 

| 번호 대역 | 관례적 용도 |
| --- | --- |
| **00-09** | 시스템 최초 기본값 |
| **10-29** | 배포판 기본값, 보안 정책 |
| **50** | 시스템 기본 설정 |
| **70-89** | 서비스별 설정 (Kubernetes, Docker 등) |
| **99** | **최종 오버라이드** — 여기 설정이 최종 승리 |

핵심은 **나중에 읽힌 값이 이긴다**는 것이다. 최종적으로 적용하고 싶은 설정은 99번대에 넣는다.

## 같은 번호 내 알파벳 순서

같은 번호의 파일이 여러 개 있으면 **파일명 알파벳 순서**대로 로드된다.

```bash
# 예: EKS 워커 노드의 /etc/sysctl.d/
tree /etc/sysctl.d
# /etc/sysctl.d
# ├── 00-defaults.conf
# ├── 99-amazon.conf
# ├── 99-kubernetes-cri.conf
# └── 99-sysctl.conf -> ../sysctl.conf
```

이 경우 99번대 파일의 로드 순서는 `99-amazon.conf` → `99-kubernetes-cri.conf` → `99-sysctl.conf`(알파벳: a < k < s)이다.

## 파라미터 충돌 시 동작

같은 파라미터가 여러 파일에 있어도 **에러가 발생하지 않는다**. 나중에 읽힌 값이 조용히 덮어쓸 뿐이다.

```bash
# 99-amazon.conf
vm.overcommit_memory = 1

# 99-sysctl.conf (= /etc/sysctl.conf)
vm.overcommit_memory = 0
```

위 경우 `99-sysctl.conf`가 알파벳 순서상 나중이므로(s > a) 최종 적용값은 `0`이 된다.

이 동작은 의도적인 오버라이드에 활용할 수 있지만, 같은 번호 내에서 알파벳 순서를 인지하지 못하면 **의도치 않은 덮어쓰기**가 발생할 수 있다. 같은 번호대에 여러 파일이 있을 때는 파라미터가 겹치지 않도록 관리하거나, 겹칠 경우 알파벳 순서를 명확히 인지해야 한다.

## 실제 로드 순서 확인: sysctl --system 출력

`sysctl --system`을 실행하면 어떤 파일을 어떤 순서로 로드했는지 출력되므로, 위에서 설명한 규칙이 실제로 어떻게 적용되는지 직접 확인할 수 있다. 아래는 EKS 워커 노드(Amazon Linux 2023)에서의 실제 출력 예시다.

```bash
[root@ip-192-168-2-21 ~]# sysctl --system
* Applying /etc/sysctl.d/00-defaults.conf ... # 00번대
kernel.printk = 8 4 1 7
kernel.panic = 5
net.ipv4.neigh.default.gc_thresh1 = 0
...
* Applying /usr/lib/sysctl.d/10-default-yama-scope.conf ... # 10번대
kernel.yama.ptrace_scope = 0
* Applying /usr/lib/sysctl.d/50-coredump.conf ...
kernel.core_pattern = |/usr/lib/systemd/systemd-coredump %P %u %g %s %t %c %h
...
* Applying /usr/lib/sysctl.d/50-default.conf ... # 50번대
kernel.sysrq = 16
kernel.core_uses_pid = 1
net.ipv4.conf.default.rp_filter = 2
sysctl: setting key "net.ipv4.conf.all.rp_filter": Invalid argument
...
* Applying /usr/lib/sysctl.d/60-amazon-linux-coredump.conf ... # 60번대
fs.suid_dumpable = 0
* Applying /etc/sysctl.d/99-amazon.conf ... # 99번대
vm.overcommit_memory = 1
kernel.panic = 10
kernel.panic_on_oops = 1
* Applying /etc/sysctl.d/99-kubernetes-cri.conf ...
net.ipv4.ip_forward = 1
* Applying /etc/sysctl.d/99-sysctl.conf ...
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 8192
vm.max_map_count = 524288
kernel.pid_max = 4194304
* Applying /etc/sysctl.conf ... # sysctl.conf
fs.inotify.max_user_watches = 524288
...
```

출력에서 확인할 수 있는 것들을 살펴 보자.
- **파일명 기준 머지**: `/etc/sysctl.d/00-defaults.conf`가 `/usr/lib/sysctl.d/10-*`보다 먼저 적용된다. 디렉토리가 다르지만 파일명 `00-*`이 `10-*`보다 앞이기 때문이다. 이후 `50-*`, `60-*`, `99-*` 순으로 모든 디렉토리의 파일이 파일명 순서대로 적용되고, `/etc/sysctl.conf`가 마지막에 온다.
- **파라미터 덮어쓰기**: `kernel.panic`이 `00-defaults.conf`에서 `5`로 설정된 후 `99-amazon.conf`에서 `10`으로 덮어쓰인다.
- **에러 처리**: `50-default.conf` 로드 시 `sysctl: setting key "net.ipv4.conf.all.rp_filter": Invalid argument` 에러가 출력되지만, 해당 설정만 무시되고 다음 파라미터로 계속 진행된다. 아래에서 이 에러가 왜 발생하는지 자세히 다룬다.

## 설정 파일에 지원되지 않는 파라미터가 포함된 이유

위 출력에서 `50-default.conf` 로드 시 `Invalid argument` 에러가 발생한 것을 볼 수 있다. `/usr/lib/sysctl.d/50-default.conf`는 **systemd 패키지**가 설치될 때 함께 배포하는 파일로, systemd 메인테이너들이 "대부분의 리눅스 시스템에서 합리적인 기본값"이라고 판단한 커널 파라미터 세트를 담고 있다. 특정 커널 빌드에 맞춰 생성된 것이 아니라 범용적으로 배포되는 설정이다.

문제는 **설정 파일을 만드는 주체(systemd)와 그 설정을 소비하는 주체(커널)가 서로 다르다**는 점이다. systemd는 다양한 커널 버전과 빌드 옵션 조합 위에서 동작해야 하므로, 불가피하게 디커플링이 발생한다.

- **커널 빌드 옵션 차이**: `net.ipv4.conf.all.rp_filter = 2`(loose mode)는 커널이 `CONFIG_IP_MULTIPLE_TABLES` 같은 옵션을 켜고 컴파일되어야 동작한다. 커널 빌드 설정에 따라 특정 값이 거부될 수 있다.
- **커널 버전 차이**: 특정 버전 이후에 추가되거나, 허용 값 범위가 변경된 파라미터가 있다. systemd 패키지는 이를 버전별로 분기 처리하지 않는다.
- **모듈 로딩 타이밍**: 해당 파라미터를 노출하는 커널 모듈이 `sysctl --system` 시점에 아직 로드되지 않았을 수 있다.

`sysctl --system`이 에러를 만나도 **중단하지 않고 다음 설정을 계속 적용**하는 것은 의도된 동작이다. 이런 디커플링이 전제되어 있기 때문에, systemd 쪽에서도 "일단 범용 설정을 다 넣어두고, 현재 커널에서 안 되는 것은 무시하면 된다"는 전략을 취한다. 에러 메시지가 출력되더라도 시스템 동작에는 영향이 없다.

<br>

# 조회·변경 방법

설정 파일 체계를 이해했으니, 실제로 커널 파라미터를 조회하고 변경하는 방법을 알아보자.

## 조회

설정 파일이 여러 곳에 분산되어 있어도, **실제로 커널에 적용된 최종값**은 `sysctl` 명령어로 한 번에 확인할 수 있다.

```bash
# 전체 파라미터 조회
sysctl -a

# 특정 파라미터 확인
sysctl net.bridge.bridge-nf-call-iptables
# net.bridge.bridge-nf-call-iptables = 1

# 네임스페이스별 필터링
sysctl -a | grep ^net.bridge
sysctl -a | grep ^vm
sysctl -a | grep ^kernel
```

> `/proc/sys/` 파일을 직접 읽어도 같은 값을 확인할 수 있다.
>
> ```bash
> cat /proc/sys/net/bridge/bridge-nf-call-iptables
> ```

## 런타임(임시) 변경

`sysctl -w` 또는 `/proc/sys/` 파일에 직접 쓰면 즉시 반영되지만, **재부팅하면 사라진다**.

```bash
# sysctl -w로 변경
sysctl -w net.ipv4.ip_forward=1

# /proc/sys/에 직접 쓰기 (동일한 효과)
echo 1 > /proc/sys/net/ipv4/ip_forward
```

## 영구 변경

설정 파일에 기록하면 **부팅 시 자동 적용**된다. 앞서 설명한 디렉토리 중 관리자가 커스텀 설정을 넣는 곳은 `/etc/sysctl.d/`이며, 전통적인 `/etc/sysctl.conf`도 사용할 수 있다.

```bash
# /etc/sysctl.d/에 설정 파일 생성
cat <<EOF | tee /etc/sysctl.d/99-k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
EOF

# 모든 설정 파일 다시 로드 (재부팅 없이 즉시 적용)
sysctl --system
```

| 명령어 | 동작 |
| --- | --- |
| `sysctl --system` | 모든 디렉토리의 설정 파일을 로드 순서대로 다시 적용 |
| `sysctl -p <파일>` | 특정 파일 하나만 로드 |

<br>

# 컨테이너·Kubernetes 환경에서의 중요성

## 왜 커널 파라미터가 중요한가

컨테이너는 VM과 달리 **호스트 커널을 공유**한다. 컨테이너 내부에서 별도 커널을 실행하는 것이 아니라, 호스트의 커널 파라미터가 모든 컨테이너의 동작에 직접 영향을 미친다.

Kubernetes 환경에서는 Pod 간 네트워킹, 브릿지 트래픽 처리, IP 포워딩 등이 커널 수준에서 동작하기 때문에 커널 파라미터 설정이 필수적이다. 설정이 누락되면 Pod 간 통신 실패, Service 접근 불가 등의 문제가 발생한다.

## Kubernetes에서 자주 설정하는 파라미터

| 파라미터 | 값 | 이유 |
| --- | --- | --- |
| `net.ipv4.ip_forward` | 1 | Pod 간 패킷 라우팅에 필수. 커널 기본값은 0(포워딩 비활성) |
| `net.bridge.bridge-nf-call-iptables` | 1 | 브릿지 트래픽이 iptables 규칙을 거치도록 함. Service ClusterIP 라우팅에 필수 |
| `net.bridge.bridge-nf-call-ip6tables` | 1 | IPv6 브릿지 트래픽에 ip6tables 적용 |
| `vm.overcommit_memory` | 1 | kubelet(Go 런타임)의 대규모 가상 메모리 예약이 거부되지 않도록 함 |
| `kernel.panic` | 10 | 커널 패닉 시 10초 후 자동 재부팅으로 노드 복구 |
| `vm.panic_on_oom` | 0 | OOM 시 커널 패닉 대신 OOM Killer가 처리 |

각 파라미터의 상세 설명은 Kubernetes 시리즈 글에서 다루고 있다:
- `vm.overcommit_memory`: [kubeadm 클러스터 구성 - 노드 정보 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %})
- `vm.swappiness`, `vm.overcommit_memory` 등 메모리 파라미터: [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %})

## kubelet의 커널 파라미터 자동 설정

kubelet은 시작 시 `kernel.panic`, `vm.overcommit_memory` 등을 자동으로 설정한다(`--protect-kernel-defaults=false`일 때). 이 설정은 `sysctl -w`로 런타임에 적용하는 것이므로 `/etc/sysctl.d/`의 파일 체계와 별개로 동작한다. 재부팅 후에도 값이 유지되는 것은 kubelet이 매번 시작할 때마다 다시 설정하기 때문이다.

반면 Kubespray 같은 배포 도구는 `/etc/sysctl.d/99-sysctl.conf`에 파라미터를 영구 기록한다. 이 경우 kubelet이 아닌 systemd가 부팅 시 적용하므로, kubelet 시작 전에도 값이 설정되어 있다.

## Pod 수준 sysctl

호스트 커널을 공유한다고 해서 Pod에서 커널 파라미터를 전혀 조정할 수 없는 것은 아니다. Pod의 `securityContext.sysctls`를 통해 일부 파라미터를 Pod 단위로 설정할 수 있다. 다만 모든 파라미터가 가능한 것은 아니며, **어떤 파라미터를 설정할 수 있는지**는 두 가지 축으로 결정된다.

```
모든 커널 파라미터
├── Non-namespaced (호스트 전역) → Pod securityContext.sysctls로 설정 불가
└── Namespaced (네임스페이스 격리)
    ├── Safe   → 기본 허용, 부작용 없음
    └── Unsafe → 격리는 되지만 간접 부작용 가능, kubelet 허용 필요
```

### 축 1: Namespaced vs Non-namespaced

첫 번째 축은 커널 파라미터가 **Linux namespace로 격리되는지 여부**다.

| 구분 | 설명 | 예시 |
| --- | --- | --- |
| **Namespaced** | Pod(컨테이너)마다 독립된 값을 가질 수 있음 | `net.*` 대부분, `kernel.shm_rmid_forced` 등 IPC 관련 일부 |
| **Non-namespaced** | 호스트 커널 전역에서 하나의 값을 공유 | `vm.*`, `kernel.pid_max`, `fs.file-max` 등 |

Non-namespaced 파라미터는 값을 격리할 수 있는 namespace 자체가 없으므로, **Pod의 `securityContext.sysctls`로 설정하는 것 자체가 불가능**하다. 앞서 다룬 `net.ipv4.ip_forward`, `vm.overcommit_memory` 같은 파라미터가 여기에 해당하며, 반드시 호스트(노드) 수준에서 설정해야 한다.

### 축 2: Safe vs Unsafe (namespaced 파라미터의 세분류)

두 번째 축은 namespaced 파라미터 내에서의 구분이다. Kubernetes는 namespaced sysctl을 다시 **safe**과 **unsafe**로 나눈다.

| 구분 | 설명 | 예시 |
| --- | --- | --- |
| **Safe** | namespace 격리가 되고, 다른 Pod·노드에 부작용이 없다고 Kubernetes가 검증한 파라미터. 기본 허용 | `kernel.shm_rmid_forced`, `net.ipv4.ping_group_range`, `net.ipv4.ip_local_port_range` |
| **Unsafe** | namespace 격리는 되지만, **간접적인 부작용 가능성**이 있는 파라미터. kubelet에서 명시적 허용 필요 | `net.core.somaxconn`, `kernel.msgmax` |

Kubernetes가 safe로 인정한 전체 목록은 다음과 같다 ([공식 문서](https://kubernetes.io/docs/tasks/administer-cluster/sysctl-cluster/) 기준).

- `kernel.shm_rmid_forced`
- `net.ipv4.ip_local_port_range`
- `net.ipv4.tcp_syncookies`
- `net.ipv4.ping_group_range` (1.18+)
- `net.ipv4.ip_unprivileged_port_start` (1.22+)
- `net.ipv4.ip_local_reserved_ports` (1.27+, 커널 3.16+)
- `net.ipv4.tcp_keepalive_time` (1.29+, 커널 4.5+)
- `net.ipv4.tcp_fin_timeout` (1.29+, 커널 4.6+)
- `net.ipv4.tcp_keepalive_intvl` (1.29+, 커널 4.5+)
- `net.ipv4.tcp_keepalive_probes` (1.29+, 커널 4.5+)
- `net.ipv4.tcp_rmem` (1.32+, 커널 4.15+)
- `net.ipv4.tcp_wmem` (1.32+, 커널 4.15+)

> 버전이 올라가면서 safe 목록은 계속 확장되고 있다. `net.ipv4.ip_local_port_range`도 초기에는 unsafe였다가 이후 safe로 승격된 케이스다.

여기서 핵심은 unsafe sysctl도 **namespace 격리 자체는 된다**는 점이다. 파라미터 값이 직접 호스트나 다른 Pod에 전파되는 것이 아니다. "영향을 미칠 수 있다"는 것은 간접적인 의미다. 예를 들어 `net.core.somaxconn`을 극단적으로 높게 설정하면 해당 Pod의 network namespace 안에서만 적용되지만, 커널 메모리를 과도하게 소비하여 노드 전체의 안정성에 영향을 줄 수 있다. Kubernetes가 unsafe로 분류하는 이유는 이런 간접적 부작용 때문이지, 격리가 안 되기 때문이 아니다.

### 설정 방법

safe sysctl은 별도 설정 없이 Pod spec에서 바로 사용할 수 있다.

```yaml
apiVersion: v1
kind: Pod
spec:
  securityContext:
    sysctls:
    - name: net.ipv4.ping_group_range
      value: "0 65535"
```

unsafe sysctl을 사용하려면 kubelet 설정에서 해당 파라미터를 명시적으로 허용해야 한다.

```bash
--allowed-unsafe-sysctls="net.core.somaxconn,kernel.msgmax"
```

kubelet이 허용하지 않은 unsafe sysctl을 Pod spec에 지정하면, Pod 생성 자체가 거부된다.

### Pod 종료 시 원복 여부

Pod이 종료되면 해당 network/IPC namespace 자체가 사라진다. namespace에 속한 커널 파라미터 값도 함께 소멸하므로, 호스트나 다른 Pod에 대한 "원복"이라는 개념 자체가 필요 없다. 처음부터 격리된 공간에서만 존재했던 값이기 때문이다.

unsafe sysctl의 간접 부작용(예: 커널 메모리 과다 소비)도 Pod이 종료되면서 해당 리소스가 해제되므로 자연스럽게 해소된다.

### Pod 단위로 sysctl을 설정하는 이유

굳이 Pod에서 커널 파라미터를 변경하는 이유는 호스트에서 파라미터를 변경하면 **그 노드 위의 모든 Pod에 영향**을 주기 때문이다. 특정 워크로드 하나를 위해 노드 전체 설정을 바꾸는 것은 과한 경우가 많다.

그렇다면, 언제 이렇게 Pod에서 호스트 커널 파라미터를 변경해야 할까. 실제로 Pod 단위 sysctl이 필요한 사례는 아래와 같다: 
- **nginx/envoy 같은 리버스 프록시 Pod**: 동시 연결이 많아 `net.core.somaxconn`을 높여야 하지만, 같은 노드의 다른 Pod들은 그럴 필요가 없다.
- **non-root로 낮은 포트를 바인딩해야 하는 경우**: `net.ipv4.ip_unprivileged_port_start`를 낮추면 80, 443 같은 포트를 non-root 프로세스가 바인딩할 수 있다. 호스트 전체에 적용하면 보안 정책이 느슨해진다.
- **멀티테넌트 클러스터**: 테넌트 A의 워크로드는 `net.ipv4.ip_local_port_range`를 넓게, 테넌트 B는 기본값으로 유지하고 싶을 때. 호스트 수준에서는 이런 분리가 불가능하다.

"호스트에서 바꾸면 되지 않나"라는 생각은 단일 워크로드 환경에서는 맞다. 그러나 Kubernetes를 쓴다는 것은 한 노드에 여러 성격의 Pod이 올라간다는 뜻이므로, **워크로드별로 네트워크 튜닝을 다르게 가져가야 할 때** Pod 단위 sysctl이 의미를 가진다.

## /etc/sysctl.d/ 파일 체계를 이해해야 하는 이유

컨테이너·Kubernetes 환경에서 `/etc/sysctl.d/`의 로드 순서를 이해하는 것이 운영·트러블슈팅에서 중요하다.

- **배포판 기본값, 클라우드 벤더 설정, CRI 설정, 사용자 커스텀 설정이 여러 파일에 분산**됨
- 어떤 파일이 어떤 순서로 로드되어 최종 값을 결정하는지 알아야 문제를 추적할 수 있음
- 예: EKS에서 `99-amazon.conf`와 `99-kubernetes-cri.conf`가 공존할 때, 파라미터 충돌 여부와 최종 적용값을 판단하려면 알파벳 순서 규칙을 알아야 함

<br>

# 자주 나오는 트러블슈팅 사례

## 파일 디스크립터 부족 (Too many open files)

프로세스가 열 수 있는 파일 수 제한에 걸리면 `Too many open files` 에러가 발생한다. 고부하 서버, 많은 Pod를 실행하는 Kubernetes 노드에서 흔히 발생한다.

관련 파라미터는 **커널 계층**(sysctl)과 **사용자 공간 계층**(ulimit)으로 나뉜다:

| 계층 | 파라미터 | 기본값 | 설명 |
| --- | --- | --- | --- |
| **커널(시스템 전체)** | `fs.file-max` | 커널·메모리 크기에 따라 자동 계산 | 시스템 전체에서 열 수 있는 최대 파일 디스크립터 수 |
| **커널(프로세스당)** | `fs.nr_open` | 일반적으로 1048576 | 단일 프로세스가 열 수 있는 파일 디스크립터 수의 상한 |
| **사용자 공간** | `ulimit -n` | 배포판·설정에 따라 다름 | 셸·프로세스별 실제 제한 (`/etc/security/limits.conf` 또는 systemd `LimitNOFILE`로 설정) |

`fs.file-max`은 `sysctl`로, `ulimit -n`은 `limits.conf`나 systemd 유닛 파일의 `LimitNOFILE`로 설정한다.

```bash
# 시스템 전체 제한 확인
sysctl fs.file-max
# fs.file-max = 9223372036854775807

# 프로세스당 상한 확인
sysctl fs.nr_open
# fs.nr_open = 1048576

# 현재 열린 파일 수 확인
cat /proc/sys/fs/file-nr
# 3520    0    9223372036854775807
# (사용 중 / 할당 후 미사용 / 최대)
```

Kubernetes 노드에서 수백 개의 Pod가 실행되면 파일 디스크립터 소비가 급격히 늘어나므로, `fs.file-max`과 `LimitNOFILE`을 충분히 높여두어야 한다.

## inotify watch 부족

많은 파일을 감시(watch)하는 워크로드에서 `inotify_add_watch: no space left on device` 에러가 발생할 수 있다. IDE, 파일 동기화 도구, Kubernetes의 ConfigMap/Secret 마운트 등이 inotify를 사용한다.

```bash
# 현재 제한 확인
sysctl fs.inotify.max_user_watches
# fs.inotify.max_user_watches = 8192

# 늘리기 (런타임)
sysctl -w fs.inotify.max_user_watches=524288

# 영구 설정
echo "fs.inotify.max_user_watches=524288" | tee /etc/sysctl.d/99-inotify.conf
```

## conntrack 테이블 가득 참

Kubernetes Service(ClusterIP, NodePort)는 커널의 conntrack(연결 추적) 모듈을 사용한다. 트래픽이 많은 클러스터에서 conntrack 테이블이 가득 차면 패킷이 drop되며, `dmesg`에 다음과 같은 로그가 남는다.

```
nf_conntrack: table full, dropping packet
```

```bash
# conntrack 최대 크기 확인
sysctl net.netfilter.nf_conntrack_max
# net.netfilter.nf_conntrack_max = 131072

# 현재 사용량 확인
sysctl net.netfilter.nf_conntrack_count

# dmesg에서 conntrack 관련 로그 확인
dmesg | grep conntrack
```

`nf_conntrack_max`의 기본값은 커널이 시스템 메모리 크기에 비례하여 자동 계산한다. 트래픽이 많은 환경에서는 이 값을 늘리고, `nf_conntrack_tcp_timeout_established` 등 타임아웃 값을 조정하여 오래된 연결이 빨리 정리되도록 한다.

## 브릿지·IP 포워딩 미설정

Kubernetes 노드 사전 설정에서 가장 흔한 실수다. `net.bridge.bridge-nf-call-iptables`나 `net.ipv4.ip_forward`가 0이면 Pod 간 통신이나 Service 접근이 실패한다.

```bash
# 확인
sysctl net.bridge.bridge-nf-call-iptables
sysctl net.ipv4.ip_forward

# 둘 다 1이어야 함
```

특히 `net.bridge.bridge-nf-call-iptables`는 **`br_netfilter` 커널 모듈이 로드되어 있어야** 파라미터 자체가 존재한다. 모듈 미로드가 이 파라미터 설정 실패의 가장 흔한 원인이다.

```bash
# br_netfilter 모듈 로드 확인
lsmod | grep br_netfilter

# 모듈이 없으면 로드
modprobe br_netfilter

# 재부팅 후에도 자동 로드되도록 설정
echo "br_netfilter" | tee /etc/modules-load.d/br_netfilter.conf
```

<br>

# 결론

커널 파라미터는 결국 **리눅스 커널의 튜닝 노브**다. 어떤 파라미터가 있고, 어떻게 조회·설정하며, 설정 파일이 어떤 순서로 로드되는지를 알면 대부분의 상황에 대응할 수 있다.

특히 컨테이너·Kubernetes 환경에서는 호스트 커널 하나를 모든 컨테이너가 공유하므로, 커널 파라미터 하나가 노드 전체에 영향을 미친다. 클러스터를 구성할 때마다 반복적으로 등장하는 `ip_forward`, `bridge-nf-call-iptables`, `vm.overcommit_memory` 같은 설정들이 **왜** 필요한지, 그리고 `/etc/sysctl.d/`에 여러 파일이 공존할 때 **최종적으로 어떤 값이 적용되는지**를 이해하면, 설정 누락이나 의도치 않은 덮어쓰기로 인한 트러블슈팅 시간을 크게 줄일 수 있다.

<br>

# 참고 자료

추후 필요할 때 아래 자료를 참고하면 좋다.

- [man sysctl(8)](https://man7.org/linux/man-pages/man8/sysctl.8.html) - sysctl 명령어 매뉴얼
- [man sysctl.d(5)](https://man7.org/linux/man-pages/man5/sysctl.d.5.html) - /etc/sysctl.d/ 설정 파일 형식 및 로드 순서
- [Linux Kernel Documentation - sysctl](https://www.kernel.org/doc/Documentation/sysctl/) - 커널 파라미터 네임스페이스별 문서
- [Linux Kernel Documentation - vm.txt](https://www.kernel.org/doc/Documentation/sysctl/vm.txt) - 메모리 관련 커널 파라미터
- [Linux Kernel Documentation - fs.txt](https://www.kernel.org/doc/Documentation/sysctl/fs.txt) - 파일시스템 관련 커널 파라미터
- [Linux Kernel Documentation - net.txt](https://www.kernel.org/doc/Documentation/sysctl/net.txt) - 네트워크 관련 커널 파라미터
- [Using sysctls in a Kubernetes Cluster](https://kubernetes.io/docs/tasks/administer-cluster/sysctl-cluster/) - Kubernetes 공식 문서: Pod 수준 sysctl 설정, safe/unsafe 분류, namespaced sysctl 목록

<br>
