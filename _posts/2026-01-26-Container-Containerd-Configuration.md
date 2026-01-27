---
title:  "[Container] containerd 설정 파일 톺아 보기"
excerpt: "containerd의 config.toml 설정 파일 구조와 주요 옵션을 살펴보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Container
  - containerd
  - Docker
  - Kubernetes
  - CRI
  - Configuration
---

<br>

containerd에 대해 알아야 할 일이 점점 늘어나는데, 매번 설정할 때마다 "이게 뭐였더라" 하며 검색하는 스스로를 발견했다. 더 이상 미루지 말고 제대로 알아봐야겠다고 다짐하며 containerd 설정 파일에 대해 알아 보았다.

<br>

# TL;DR

- **설정 파일 위치**: `/etc/containerd/config.toml` (기본값)
- **설정 버전**: containerd 2.x는 `version = 3`, containerd 1.x는 `version = 2` 권장
- **TOML 형식**: 사람이 읽기 쉽고, 계층적 설정에 적합한 설정 파일 포맷
- **주요 섹션**: 글로벌 설정, `[grpc]`, `[plugins]`, `[plugins."io.containerd.grpc.v1.cri"]`
- **플러그인 구조**: containerd는 플러그인 아키텍처로, CRI, snapshotter(이미지 레이어 관리 모듈), runtime 등이 모두 플러그인
- **Kubernetes 연동**: CRI 플러그인(`io.containerd.grpc.v1.cri`) 설정이 핵심

<br>

# 개요

containerd는 Docker와 Kubernetes에서 사용하는 컨테이너 런타임이다. 이 글에서는 containerd의 설정 파일인 `config.toml`의 구조와 주요 옵션을 살펴본다.



<br>

# 설정 파일 형식: TOML

containerd의 설정 파일(`config.toml`)은 **TOML** 형식으로 작성된다. 

## TOML이란

**TOML(Tom's Obvious, Minimal Language)**은 설정 파일을 위한 파일 형식이다. INI 파일과 유사하지만 더 명확한 문법을 가지며, JSON이나 YAML보다 사람이 읽고 쓰기 쉽다.

```toml
# 주석은 #으로 시작
key = "value"
number = 42
boolean = true

[section]
  nested_key = "nested_value"

[section.subsection]
  deep_key = "deep_value"
```

## containerd가 TOML을 사용하는 이유

containerd의 설정은 **계층적이고 복잡한 구조**를 가진다. 특히 플러그인 설정이 중첩되어 있어 이를 표현하기에 TOML이 적합하다.

| 형식 | 장점 | 단점 |
|-----|------|------|
| **TOML** | 읽기 쉬움, 계층 구조 명확, 타입 명시적 | 덜 알려짐 |
| JSON | 널리 사용, 파싱 쉬움 | 표준 JSON은 주석 불가, 가독성 떨어짐 |
| YAML | 간결, 널리 사용 | 들여쓰기 민감, 암묵적 타입 변환 |
| INI | 단순 | 중첩 구조 제한적 |

containerd, Docker, Cargo(Rust), Hugo 등 많은 Go 기반 프로젝트에서 TOML을 채택하고 있다.

## TOML 테이블(섹션) 문법

containerd 설정 파일을 읽다 보면 `[grpc]`, `[plugins."io.containerd.gc.v1.scheduler"]` 같은 대괄호 표현이 나온다. 이것은 TOML의 **테이블(Table)** 문법으로, 설정을 계층적으로 구조화하기 위한 것이다.

```toml
# 최상위 필드 (테이블 없이)
version = 3
root = "/var/lib/containerd"

# 테이블(섹션) 선언
[grpc]
  address = "/run/containerd/containerd.sock"
  uid = 0

# 중첩 테이블
[plugins."io.containerd.gc.v1.scheduler"]
  pause_threshold = 0.02
```

테이블을 사용하면 같은 설정을 더 읽기 쉽게 표현할 수 있다:

```toml
# 테이블 없이 (읽기 어려움)
plugins."io.containerd.gc.v1.scheduler".pause_threshold = 0.02
plugins."io.containerd.gc.v1.scheduler".deletion_threshold = 0
plugins."io.containerd.gc.v1.scheduler".mutation_threshold = 100

# 테이블 사용 (읽기 쉬움)
[plugins."io.containerd.gc.v1.scheduler"]
  pause_threshold = 0.02
  deletion_threshold = 0
  mutation_threshold = 100
```

### 따옴표로 감싼 키: timeouts의 특수성

containerd 공식 문서를 보면 `[grpc]`, `[plugins."..."]` 같은 섹션은 대괄호로 표현되는데, timeouts는 일반 키로 소개하고 있다. 글로벌 설정처럼 보이지만, 실제 설정을 확인해 보면, `[timeouts]`와 같이 대괄호로 표현된다. 혼란스러울 수 있지만, 하지만 timeouts도 [timeouts] 테이블이며, 다른 섹션들과 구조가 다르다.
- `[grpc]`, `[plugins."..."]` 등의 섹션: 중첩 테이블 구조로, **구조체 타입**(필드가 있음)
- `[timeouts]`: 테이블 구조이지만, **맵 타입**(키-값만 있음)

```toml
# 구조체 타입 - 필드가 있음
[grpc]
  address = "/run/containerd/containerd.sock"
  uid = 0

# 맵 타입 - 키-값만 있음 (확장성을 위한 설계)
[timeouts]
  'io.containerd.timeout.shim.cleanup' = '5s'   # 전체가 하나의 키 이름
  'io.containerd.timeout.shim.load' = '5s'
```

TOML에서 점(`.`)이 포함된 키는 따옴표로 감싸야 한다. `'io.containerd.timeout.shim.cleanup'`은 중첩 테이블이 아니라 **하나의 키 이름**이다.

> 참고: **맵 타입 섹션의 확장성**
>
> 혼란스러울 수 있음에도 이렇게 설계한 이유는 **확장성** 때문이다. 만약 중첩 테이블로 했다면 새로운 타임아웃을 추가할 때마다 깊이가 달라진다:
>
> ```toml
> # 만약 중첩 테이블로 했다면 (복잡함)
> [timeouts.io.containerd.timeout.shim]
>   cleanup = '5s'
>   load = '5s'
>
> [timeouts.io.containerd.timeout.task]
>   state = '2s'
>
> # 맵 방식 (현재, 단순함)
> [timeouts]
>   'io.containerd.timeout.shim.cleanup' = '5s'
>   'io.containerd.timeout.new.feature' = '10s'  # 쉽게 추가 가능
> ```
>
> 이렇게 설계했기 때문에, 깊은 중첩 없이 새로운 타임아웃을 쉽게 추가할 수 있다.

<br>

# 설정 파일 개요

## 위치 및 우선순위

containerd는 다음 우선순위로 설정을 적용한다:

1. **`--config` 옵션**으로 지정된 경로 (최우선)
2. **기본 경로** (`/etc/containerd/config.toml`)
3. **내장된 기본값** (설정 파일이 없을 때)

### `--config` 옵션

containerd 데몬 시작 시 `--config` 옵션으로 설정 파일 경로를 직접 지정할 수 있다.

```bash
containerd --config /path/to/custom-config.toml
```

이 옵션이 지정되면 기본 경로는 무시된다.

### 기본 경로

`--config` 옵션이 없으면 `/etc/containerd/config.toml`에서 설정을 읽는다.

```bash
/etc/containerd/config.toml
```

### 내장된 기본값

설정 파일이 없거나 `--config` 옵션이 제공되지 않으면, containerd는 **내장된 기본값**을 사용한다.

```bash
# 기본 설정 출력
containerd config default

# 현재 적용된 설정 출력
containerd config dump
```

## 설정 파일 버전

containerd 설정 파일에는 `version` 필드가 있다. 버전을 명시하지 않으면 **version 1로 간주**되는데, 이는 하위 호환성을 위한 것이다.

| 설정 버전 | 최소 containerd 버전 | 상태 |
|----------|---------------------|------|
| **1** | v1.0.0 | deprecated, v2.0에서 제거됨 |
| **2** | v1.3.0 | containerd 1.x 권장 |
| **3** | v2.0.0 | containerd 2.x 권장 (현재 최신) |

### 버전별 주요 변경점

- **Version 1 → 2**: 플러그인 ID에 `io.containerd.` 접두사 추가
- **Version 2 → 3**: 일부 플러그인 ID 변경, CRI 플러그인 구조 개선

### 자동 마이그레이션

containerd는 **시작할 때마다 설정을 최신 버전으로 자동 마이그레이션**한다. 이 과정에서:

- 원본 설정 파일(`config.toml`)은 **변경되지 않음**
- 메모리 상에서 최신 버전으로 변환하여 사용
- 약간의 시작 시간 오버헤드 발생

마이그레이션을 피하고 시작 시간을 최적화하려면 아래와 같이 `containerd config migrate`를 이용해 미리 변환해 둘 수 있다:

```bash
# 설정 파일을 최신 버전으로 마이그레이션하여 출력
containerd config migrate /etc/containerd/config.toml

# 결과를 파일로 저장
containerd config migrate /etc/containerd/config.toml > /etc/containerd/config.toml.new
```

> **주의**: 마이그레이션된 설정 파일은 이전 버전의 containerd에서 호환되지 않을 수 있다. 롤백이 필요 없는 것이 확실할 때만 마이그레이션을 적용하자.

<br>

# 주요 설정 항목


containerd 설정 파일의 전체 구조는 다음과 같다:

```
config.toml
├── (글로벌 설정)          # version, root, state, imports 등
├── [grpc]                 # gRPC 서버 설정 (kubelet 통신)
├── [ttrpc]                # ttrpc 서버 설정 (shim 통신)
├── [debug]                # 디버깅 설정
├── [metrics]              # Prometheus 메트릭 설정
├── [plugins]              # 플러그인 설정
│   ├── [plugins."io.containerd.cri.v1.images"]      # CRI 이미지 관련
│   │   └── pinned_images, registry 등
│   ├── [plugins."io.containerd.cri.v1.runtime"]     # CRI 런타임 관련
│   │   └── containerd.runtimes, cni 등
│   ├── [plugins."io.containerd.grpc.v1.cri"]        # (v2) 통합 CRI 플러그인
│   └── ...
├── [cgroup]               # cgroup 설정
├── [timeouts]             # 타임아웃 설정
└── [stream_processors]    # 스트림 처리 설정
```

설정 파일에 명시되지 않은 옵션은 **기본값**이 적용된다. `containerd config default` 명령으로 전체 기본값을 확인할 수 있다.

<details markdown="1">
<summary>설정 파일 구조 상세 예시 (클릭하여 펼치기)</summary>

```toml
# ========================================
# 1. 최상위 필드 (Top-level fields)
# ========================================
version = 3
root = "/var/lib/containerd"
state = "/run/containerd"

# ========================================
# 2. 최상위 섹션 (Top-level sections)
# ========================================

[grpc]
address = "/run/containerd/containerd.sock"
uid = 0

[debug]
address = "/run/containerd/debug.sock"
level = "info"

# ========================================
# 3. Timeouts - 특수 케이스 (따옴표로 감싼 키)
# ========================================
[timeouts]
  # 이것들은 중첩 테이블이 아니라 단일 키
  'io.containerd.timeout.shim.cleanup' = '5s'
  'io.containerd.timeout.shim.load' = '5s'
  'io.containerd.timeout.task.state' = '2s'

# ========================================
# 4. 플러그인 섹션 (Plugins section)
# ========================================

[plugins]
  # 플러그인 루트 - 아무것도 없음

  # GC Scheduler 플러그인
  [plugins."io.containerd.gc.v1.scheduler"]
    pause_threshold = 0.02
    deletion_threshold = 0
    mutation_threshold = 100
    schedule_delay = "0s"
    startup_delay = "100ms"

  # Diff Service 플러그인
  [plugins."io.containerd.service.v1.diff-service"]
    default = ["walking"]

  # Monitor (cgroups) 플러그인
  [plugins."io.containerd.monitor.v1.cgroups"]
    no_prometheus = false

  # Task 플러그인
  [plugins."io.containerd.runtime.v2.task"]
    platforms = ["linux/amd64"]
    sched_core = false

  # Tasks Service 플러그인
  [plugins."io.containerd.service.v1.tasks-service"]
    rdt_config_file = ""
    blockio_config_file = ""

  # CRI Runtime 플러그인 (중첩이 깊음)
  [plugins."io.containerd.cri.v1.runtime"]
    enable_selinux = false
    max_container_log_line_size = 16384

    [plugins."io.containerd.cri.v1.runtime".containerd]
      snapshotter = "overlayfs"
      default_runtime_name = "runc"

      # Runc 런타임 설정
      [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc]
        runtime_type = "io.containerd.runc.v2"

        # Runc 옵션
        [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc.options]
          SystemdCgroup = true
          BinaryName = "/usr/bin/runc"

# ========================================
# 구조 요약:
# ========================================
# 
# version, root         → 최상위 필드
# [grpc]                → 최상위 섹션
# [timeouts]            → 특수 케이스 (플랫 맵)
# [plugins."..."]       → 플러그인 (깊은 중첩 가능)
#
# 플러그인 ID 형식:
# io.containerd.<type>.<api_version>.<name>
#
# 예시:
# - io.containerd.gc.v1.scheduler        → GC 스케줄러
# - io.containerd.service.v1.diff        → Diff 서비스
# - io.containerd.runtime.v2.task        → Runtime task
# - io.containerd.cri.v1.runtime         → CRI 런타임
```

</details>

<br>

## 글로벌 설정

설정 파일의 최상위 레벨에 위치하는 글로벌 설정이다.

| 항목 | 기본값 | 설명 |
|-----|-------|------|
| `version` | 1 (미지정 시) | 설정 파일 버전. 2 또는 3을 명시적으로 지정 권장 |
| `root` | `/var/lib/containerd` | containerd 데이터 저장 디렉토리 (이미지, 컨테이너 메타데이터 등) |
| `state` | `/run/containerd` | 런타임 상태 저장 디렉토리 (소켓, PID 파일, 컨테이너 상태 등) |
| `temp` | `""` | 임시 파일 디렉토리. 비어있으면 시스템 기본값 사용 |
| `plugin_dir` | `""` | 동적 플러그인 저장 디렉토리 |
| `disabled_plugins` | `[]` | 비활성화할 플러그인 ID 목록. 지정된 플러그인은 초기화되지 않음 |
| `required_plugins` | `[]` | 필수 플러그인 ID 목록. 초기화 실패 시 containerd 종료 |
| `oom_score` | 0 | OOM Killer 점수 조정 (-1000 ~ 1000) |
| `imports` | `[]` | 추가로 포함할 설정 파일 경로 (glob 패턴 지원) |

### root vs state

- **root** (`/var/lib/containerd`): 영구 데이터 저장. 재부팅 후에도 유지되어야 하는 데이터 (이미지 레이어, 컨테이너 메타데이터)
- **state** (`/run/containerd`): 런타임 상태 저장. 재부팅 시 초기화되어도 되는 데이터 (소켓, PID 파일, 실행 중인 컨테이너 상태). 보통 tmpfs(`/run`)에 위치

### imports

`imports` 필드를 사용하면 nginx의 `conf.d`처럼 설정을 여러 파일로 분산할 수 있다.

- **glob 패턴 지원**: `*.toml`처럼 와일드카드 사용 가능
- **다중 파일 지정**: 배열로 여러 경로 지정 가능
- **우선순위**: 뒤에 import된 파일이 앞의 설정을 덮어씀
- **Version 3 기본값**: `/etc/containerd/conf.d/*.toml`

systemd 설정과 유사하게 `/etc/containerd/conf.d/` 디렉토리에 파일을 두어 모듈화할 수 있다:

활용 예시:
- `/etc/containerd/conf.d/99-nvidia.toml`: GPU 런타임 설정
- `/etc/containerd/conf.d/50-registry.toml`: 프라이빗 레지스트리 설정

<br>

## [grpc] 섹션

**kubelet 등 외부 클라이언트와의 gRPC 통신 설정**이다.

containerd는 gRPC를 통해 클라이언트와 통신한다. Kubernetes의 CRI(Container Runtime Interface) 스펙 자체가 gRPC 기반으로 정의되어 있기 때문이다.

| 항목 | 기본값 | 설명 |
|-----|-------|------|
| `address` | `/run/containerd/containerd.sock` | Unix 소켓 경로 |
| `tcp_address` | `""` | TCP 주소 (원격 접속용, 보통 비활성화) |
| `tcp_tls_cert` | `""` | TLS 인증서 경로 |
| `tcp_tls_key` | `""` | TLS 키 경로 |
| `tcp_tls_ca` | `""` | TLS CA 인증서 경로 |
| `uid` | 0 | 소켓 소유자 UID (0 = root) |
| `gid` | 0 | 소켓 소유자 GID (0 = root) |
| `max_recv_message_size` | 16777216 | 최대 수신 메시지 크기 (16MB) |
| `max_send_message_size` | 16777216 | 최대 전송 메시지 크기 (16MB) |

> **참고**: `uid`와 `gid`가 0인 것은 root 사용자/그룹을 의미한다. 보안상 [rootless containerd](https://github.com/containerd/containerd/blob/main/docs/rootless.md)를 사용하거나, 특정 그룹(예: `docker`)에만 접근을 허용하려면 이 값을 조정한다.

### gRPC를 사용하는 이유

Kubernetes는 컨테이너 런타임과 통신하기 위해 **CRI(Container Runtime Interface)**를 정의했다. CRI는 [Protocol Buffers](https://github.com/kubernetes/cri-api/blob/master/pkg/apis/runtime/v1/api.proto)로 정의된 gRPC 서비스다.

```
kubelet  ←──gRPC(CRI)──→  containerd (CRI 플러그인)
                              │
                              ├──→ runc (OCI 런타임)
                              ├──→ nvidia-container-runtime
                              └──→ 기타 OCI 런타임
```

따라서 containerd뿐 아니라 CRI-O 등 Kubernetes와 연동하는 모든 컨테이너 런타임은 gRPC를 사용한다.

<br>

## [ttrpc] 섹션

**containerd-shim과의 경량 RPC 통신 설정**이다.

TTRPC(Tiny TLS RPC)는 containerd에서 개발한 경량 RPC 프로토콜이다. gRPC보다 오버헤드가 적어 shim(containerd와 실제 컨테이너 프로세스 사이의 중간 계층)과의 통신에 사용된다.

| 항목 | 기본값 | 설명 |
|-----|-------|------|
| `address` | `""` | TTRPC 소켓 경로 (비어있으면 비활성화) |
| `uid` | 0 | 소켓 소유자 UID |
| `gid` | 0 | 소켓 소유자 GID |

<br>

## [debug] 섹션

디버그 및 로깅 설정이다.

| 항목 | 기본값 | 설명 |
|-----|-------|------|
| `address` | `/run/containerd/debug.sock` | 디버그 소켓 경로 |
| `uid` | 0 | 소켓 소유자 UID |
| `gid` | 0 | 소켓 소유자 GID |
| `level` | `info` | 로그 레벨 (`trace`, `debug`, `info`, `warn`, `error`, `fatal`, `panic`) |
| `format` | `text` | 로그 포맷 (`text`, `json`) |

<br>

## [metrics] 섹션

**메트릭 리스너 활성화 및 설정**이다.

기본적으로 메트릭 엔드포인트는 **비활성화**되어 있다. 활성화하면 Prometheus 형식(OpenMetrics)으로 메트릭을 노출하며, Prometheus 외에도 OpenMetrics를 지원하는 다양한 모니터링 도구에서 수집할 수 있다.

| 항목 | 기본값 | 설명 |
|-----|-------|------|
| `address` | `""` | 메트릭 엔드포인트 주소. 비어있으면 비활성화 |
| `grpc_histogram` | `false` | gRPC 히스토그램 메트릭 활성화 여부 |

메트릭을 활성화하려면:

```toml
[metrics]
  address = "127.0.0.1:1338"
```

<br>

## [plugins] 섹션

**설치된 플러그인의 설정 옵션**이다.

containerd는 **플러그인 아키텍처**로 설계되어 있다. 거의 모든 기능이 플러그인으로 구현되며, 각 플러그인은 `[plugins."<plugin-id>"]` 형태로 설정한다. 아래 나열된 플러그인들은 **기본적으로 활성화**되어 있으며, 기본 활성화되지 않은 플러그인은 별도 문서를 참고해야 한다.

### 기본 플러그인 요약

| 플러그인 ID | 역할 |
|------------|------|
| `io.containerd.grpc.v1.cri` | **CRI 플러그인** - Kubernetes 연동의 핵심 |
| `io.containerd.runtime.v2.task` | 런타임 task 관리 |
| `io.containerd.gc.v1.scheduler` | 가비지 컬렉션 스케줄러 |
| `io.containerd.service.v1.tasks-service` | 태스크 서비스 (RDT, BlockIO) |
| `io.containerd.service.v1.diff-service` | 이미지 레이어 diff 서비스 |
| `io.containerd.monitor.v1.cgroups` | cgroup 메트릭 모니터링 |
| `io.containerd.snapshotter.v1.overlayfs` | OverlayFS 스냅샷터 |
| `io.containerd.metadata.v1.bolt` | 메타데이터 저장 (BoltDB) |
| `io.containerd.nri.v1.nri` | NRI (Node Resource Interface) |

### 플러그인 상세 설명

#### io.containerd.grpc.v1.cri (CRI 플러그인)

Kubernetes 연동의 핵심 플러그인이다. kubelet이 containerd와 통신할 때 이 플러그인을 통해 컨테이너를 생성하고 관리한다. 자세한 설정은 [CRI 플러그인 설정](#cri-플러그인-설정) 섹션에서 다룬다.

#### io.containerd.runtime.v2.task

컨테이너 런타임 task의 플랫폼 및 스케줄링을 설정한다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `platforms` | `["linux/amd64"]` | 지원 플랫폼 목록 |
| `sched_core` | `false` | Linux Core Scheduling 활성화 여부 |

#### io.containerd.gc.v1.scheduler (GC 스케줄러)

사용하지 않는 이미지, 컨테이너, 스냅샷 등을 정리하는 가비지 컬렉션 스케줄러다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `pause_threshold` | `0.02` | GC 일시 중지 임계값 |
| `deletion_threshold` | `0` | 삭제 작업 후 GC 트리거 임계값 |
| `mutation_threshold` | `100` | DB 변경 후 GC 트리거 임계값 |
| `schedule_delay` | `0s` | GC 스케줄 지연 시간 |
| `startup_delay` | `100ms` | containerd 시작 후 첫 GC까지 대기 시간 |

#### io.containerd.service.v1.tasks-service

고급 리소스 관리 기능(RDT, BlockIO)을 제공하는 태스크 서비스다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `rdt_config_file` | `""` | Intel RDT(Resource Director Technology) 설정 파일 경로 |
| `blockio_config_file` | `""` | Block I/O 설정 파일 경로 |

#### io.containerd.service.v1.diff-service

이미지 레이어 간 차이를 계산하는 서비스다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `default` | `["walking"]` | diff 계산 방식 (배열로 우선순위 지정) |

**differ 종류**:
- `walking`: 기본값. 파일시스템을 순회하며 두 스냅샷을 비교
- 스냅샷터별 네이티브 differ: 스냅샷터가 자체 diff 기능을 제공하면 사용 가능 (예: `overlayfs`가 자체 diff를 지원하면 더 효율적)

대부분의 환경에서는 `walking`만 사용하며, 특별한 최적화가 필요한 경우에만 다른 differ를 고려한다.

#### io.containerd.monitor.v1.cgroups

cgroup 메트릭을 모니터링하고 Prometheus로 노출한다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `no_prometheus` | `false` | `true`로 설정하면 Prometheus 메트릭 비활성화 |

#### io.containerd.snapshotter.v1.overlayfs

OverlayFS 기반 스냅샷터로, 컨테이너 이미지 레이어를 관리한다. 대부분의 Linux 시스템에서 기본 스냅샷터로 사용된다.

#### io.containerd.metadata.v1.bolt

BoltDB를 사용하여 containerd의 메타데이터를 저장한다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `content_sharing_policy` | `shared` | 콘텐츠 공유 정책 (`shared` 또는 `isolated`) |

#### io.containerd.nri.v1.nri

NRI(Node Resource Interface)는 컨테이너 생성/삭제 시 외부 플러그인이 개입할 수 있게 하는 인터페이스다. 리소스 할당, 디바이스 주입 등의 커스텀 로직을 구현할 수 있다.

| 옵션 | 기본값 | 설명 |
|-----|-------|------|
| `disable` | `true` (v2) / `false` (v3) | NRI 비활성화 여부 |
| `socket_path` | `/var/run/nri/nri.sock` | NRI 소켓 경로 |
| `plugin_path` | `/opt/nri/plugins` | NRI 플러그인 경로 |
| `plugin_config_path` | `/etc/nri/conf.d` | 플러그인 설정 경로 |
| `plugin_registration_timeout` | `5s` | 플러그인 등록 타임아웃 |
| `plugin_request_timeout` | `2s` | 플러그인 요청 타임아웃 |

### 플러그인 설정 키 구조

플러그인 설정은 `[plugins."<plugin-id>"]` 형태로 시작하며, 하위 설정은 점(`.`)으로 구분하여 중첩한다:

```toml
[plugins."io.containerd.grpc.v1.cri"]
  sandbox_image = "registry.k8s.io/pause:3.8"

[plugins."io.containerd.grpc.v1.cri".containerd]
  default_runtime_name = "runc"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  BinaryName = "/usr/bin/runc"
  SystemdCgroup = true
```

<br>

## CRI 플러그인 설정

Kubernetes와 연동할 때 가장 중요한 설정이다. 플러그인 ID가 버전에 따라 다르다:

- **Version 2**: `[plugins."io.containerd.grpc.v1.cri"]`
- **Version 3**: `[plugins."io.containerd.cri.v1.runtime"]`, `[plugins."io.containerd.cri.v1.images"]`

### 주요 CRI 설정 (Version 2 기준)

| 경로 | 항목 | 기본값 | 설명 |
|-----|------|-------|------|
| `[plugins."io.containerd.grpc.v1.cri"]` | `sandbox_image` | `registry.k8s.io/pause:3.8` | Pod sandbox 이미지 |
| | `max_concurrent_downloads` | 3 | 동시 이미지 다운로드 수 |
| | `max_container_log_line_size` | 16384 | 컨테이너 로그 라인 최대 크기 |
| | `enable_selinux` | false | SELinux 지원 활성화 |
| | `enable_cdi` | false | CDI (Container Device Interface) 활성화 |
| | `systemd_cgroup` | false | systemd cgroup 드라이버 사용 |
| `.containerd` | `snapshotter` | `overlayfs` | 스냅샷터 종류 |
| | `default_runtime_name` | `runc` | 기본 런타임 이름 |
| `.cni` | `bin_dir` | `/opt/cni/bin` | CNI 플러그인 바이너리 경로 |
| | `conf_dir` | `/etc/cni/net.d` | CNI 설정 파일 경로 |
| `.registry` | `config_path` | `""` | 레지스트리 설정 경로 |

### 런타임 설정

런타임 설정은 중첩된 키 구조를 따른다:

```
[plugins."...cri".containerd.runtimes]           # 런타임 목록의 상위
  └─ [....runtimes.<runtime>]                    # 특정 런타임 (예: runc, crun, kata)
       └─ [....runtimes.<runtime>.options]       # 해당 런타임의 옵션
```

#### 런타임 레벨 설정 (`runtimes.<runtime>`)

| 항목 | 기본값 | 설명 |
|------|-------|------|
| `runtime_type` | `io.containerd.runc.v2` | 런타임 shim 타입 |
| `runtime_path` | `""` | 런타임 경로 (비어있으면 PATH에서 검색) |
| `privileged_without_host_devices` | `false` | 특권 컨테이너에서 호스트 디바이스 제외 |
| `base_runtime_spec` | `""` | 기본 OCI 스펙 파일 경로 |
| `cni_conf_dir` | `""` | 런타임별 CNI 설정 경로 (비어있으면 전역 설정 사용) |
| `cni_max_conf_num` | `0` | 런타임별 최대 CNI 설정 파일 수 |
| `sandboxer` | `podsandbox` | 샌드박스 컨트롤러 타입 |

#### 런타임 옵션 (`runtimes.<runtime>.options`)

runc 기반 런타임의 주요 옵션:

| 항목 | 기본값 | 설명 |
|------|-------|------|
| `BinaryName` | `""` | OCI 런타임 바이너리 경로. 빈 문자열이면 `$PATH`에서 런타임 이름(예: `runc`)을 검색. 명시적 경로(예: `/usr/bin/runc`)를 지정하면 해당 바이너리를 직접 사용 |
| `SystemdCgroup` | `false` | systemd cgroup 드라이버 사용 여부 |
| `NoPivotRoot` | `false` | pivot_root 대신 chroot 사용 |
| `NoNewKeyring` | `false` | 새 세션 키링 생성 비활성화 |
| `Root` | `""` | runc root 디렉토리 |
| `CriuPath` | `""` | CRIU 바이너리 경로 (체크포인트/복원용) |
| `CriuImagePath` | `""` | CRIU 이미지 경로 |
| `CriuWorkPath` | `""` | CRIU 작업 경로 |

#### 설정 예시

```toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"
  
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
    SystemdCgroup = true         # systemd cgroup 사용
    BinaryName = "/usr/bin/runc" # OCI 런타임 바이너리 경로
```

> **참고**: Kubernetes와 함께 사용할 때는 `SystemdCgroup = true`로 설정하고, kubelet의 `cgroupDriver: "systemd"`와 일치시켜야 한다. systemd 기반 시스템에서는 cgroup의 "single-writer" 규칙을 준수해야 하기 때문이다. 특히 cgroup v2 환경(최신 Linux 배포판 기본값)에서는 systemd가 cgroup 트리를 독점 관리하므로 `systemd` 드라이버 사용이 필수에 가깝다. 자세한 내용은 [CRI Plugin Config Guide](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)를 참고한다.

<br>

# 전체 설정 예시

containerd 설정 파일은 버전에 따라 구조와 옵션이 다르다. 주요 차이점은 다음과 같다.

| 항목 | Version 2 (containerd 1.x) | Version 3 (containerd 2.x) |
|-----|---------------------------|---------------------------|
| **CRI 플러그인 ID** | `io.containerd.grpc.v1.cri` (통합) | `io.containerd.cri.v1.images`, `io.containerd.cri.v1.runtime` (분리) |
| **sandbox 이미지** | `[plugins."...cri"].sandbox_image` | `[plugins."...images".pinned_images].sandbox` |
| **CDI 기본값** | `enable_cdi = false` | `enable_cdi = true` |
| **NRI 기본값** | `disable = true` | `disable = false` |
| **imports 기본값** | `[]` | `['/etc/containerd/conf.d/*.toml']` |
| **레지스트리 설정** | `registry.mirrors`, `registry.configs` | `registry.config_path` (hosts.toml 방식 권장) |
| **deprecated 플러그인** | `io.containerd.runtime.v1.linux` 존재 | 제거됨 |
| **systemd_cgroup 위치** | 최상위 + runtimes.options | runtimes.options만 |

> **참고**: Version 3는 CRI 플러그인을 이미지 관련(`cri.v1.images`)과 런타임 관련(`cri.v1.runtime`)으로 분리했다. 이는 책임 분리 원칙에 따라 이미지 풀링/저장과 컨테이너 실행을 독립적으로 관리하고, 설정 구조를 더 명확하게 하기 위함이다.

## Version 3 기본 설정

containerd 2.x의 기본 설정이다. `containerd config default`로 생성할 수 있다.

<details markdown="1">
<summary>Version 3 전체 설정 (클릭하여 펼치기)</summary>

```toml
# containerd 2.x 기본 설정 (version = 3)
version = 3

# 글로벌 설정
root = '/var/lib/containerd'           # 영구 데이터 저장 경로
state = '/run/containerd'              # 런타임 상태 저장 경로
temp = ''                              # 임시 파일 경로 (비어있으면 시스템 기본값)
disabled_plugins = []                  # 비활성화할 플러그인 목록
required_plugins = []                  # 필수 플러그인 목록 (없으면 종료)
oom_score = 0                          # OOM Killer 점수 조정
imports = ['/etc/containerd/conf.d/*.toml']  # 추가 설정 파일 import

# gRPC 설정 (kubelet 등 클라이언트와의 통신)
[grpc]
  address = '/run/containerd/containerd.sock'  # Unix 소켓 경로
  tcp_address = ''                             # TCP 주소 (원격 접속, 보통 비활성화)
  tcp_tls_ca = ''
  tcp_tls_cert = ''
  tcp_tls_key = ''
  uid = 0                                      # 소켓 소유자 UID (0 = root)
  gid = 0                                      # 소켓 소유자 GID (0 = root)
  max_recv_message_size = 16777216             # 최대 수신 크기 (16MB)
  max_send_message_size = 16777216             # 최대 전송 크기 (16MB)
  tcp_tls_common_name = ''

# TTRPC 설정 (shim과의 경량 통신)
[ttrpc]
  address = ''
  uid = 0
  gid = 0

# 디버그 설정
[debug]
  address = ''
  uid = 0
  gid = 0
  level = ''      # 로그 레벨: trace, debug, info, warn, error, fatal, panic
  format = ''     # 로그 포맷: text, json

# 메트릭 설정 (Prometheus)
[metrics]
  address = ''                # 비어있으면 비활성화
  grpc_histogram = false      # gRPC 히스토그램 메트릭

# 플러그인 설정
[plugins]
  # CRI 이미지 관련 설정 (version 3에서 분리됨)
  [plugins.'io.containerd.cri.v1.images']
    snapshotter = 'overlayfs'
    disable_snapshot_annotations = true
    discard_unpacked_layers = false
    max_concurrent_downloads = 3
    image_pull_progress_timeout = '5m0s'

    # sandbox 이미지 설정
    [plugins.'io.containerd.cri.v1.images'.pinned_images]
      sandbox = 'registry.k8s.io/pause:3.10.1'

    # 레지스트리 설정
    [plugins.'io.containerd.cri.v1.images'.registry]
      config_path = '/etc/containerd/certs.d:/etc/docker/certs.d'

  # CRI 런타임 관련 설정 (version 3에서 분리됨)
  [plugins.'io.containerd.cri.v1.runtime']
    enable_selinux = false
    max_container_log_line_size = 16384
    disable_apparmor = false
    enable_cdi = true                    # CDI 활성화 (GPU 등 디바이스)
    cdi_spec_dirs = ['/etc/cdi', '/var/run/cdi']

    [plugins.'io.containerd.cri.v1.runtime'.containerd]
      default_runtime_name = 'runc'      # 기본 런타임

      # runc 런타임 설정
      [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes]
        [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc]
          runtime_type = 'io.containerd.runc.v2'
          sandboxer = 'podsandbox'

          [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc.options]
            SystemdCgroup = false        # systemd cgroup 사용 여부

    # CNI 설정
    [plugins.'io.containerd.cri.v1.runtime'.cni]
      bin_dirs = ['/opt/cni/bin']        # CNI 플러그인 바이너리 경로
      conf_dir = '/etc/cni/net.d'        # CNI 설정 파일 경로

  # 가비지 컬렉션 스케줄러
  [plugins.'io.containerd.gc.v1.scheduler']
    pause_threshold = 0.02
    deletion_threshold = 0
    mutation_threshold = 100
    schedule_delay = '0s'
    startup_delay = '100ms'

  # CRI gRPC 서비스 설정
  [plugins.'io.containerd.grpc.v1.cri']
    disable_tcp_service = true
    stream_server_address = '127.0.0.1'
    stream_server_port = '0'
    stream_idle_timeout = '4h0m0s'

  # 메타데이터 저장 (BoltDB)
  [plugins.'io.containerd.metadata.v1.bolt']
    content_sharing_policy = 'shared'

  # 스냅샷터 설정
  [plugins.'io.containerd.snapshotter.v1.overlayfs']
    root_path = ''
    mount_options = []

# cgroup 설정
[cgroup]
  path = ''

# 타임아웃 설정
[timeouts]
  'io.containerd.timeout.bolt.open' = '0s'
  'io.containerd.timeout.shim.cleanup' = '5s'
  'io.containerd.timeout.shim.load' = '5s'
  'io.containerd.timeout.shim.shutdown' = '3s'
  'io.containerd.timeout.task.state' = '2s'

# 스트림 프로세서 (이미지 암호화 등)
[stream_processors]
  [stream_processors.'io.containerd.ocicrypt.decoder.v1.tar']
    accepts = ['application/vnd.oci.image.layer.v1.tar+encrypted']
    returns = 'application/vnd.oci.image.layer.v1.tar'
    path = 'ctd-decoder'
    args = ['--decryption-keys-path', '/etc/containerd/ocicrypt/keys']
```

</details>

<br>

## Version 2 기본 설정

containerd 1.x의 기본 설정이다.

<details markdown="1">
<summary>Version 2 전체 설정 (클릭하여 펼치기)</summary>

```toml
# containerd 1.x 기본 설정 (version = 2)
disabled_plugins = []
imports = []
oom_score = 0
plugin_dir = ""
required_plugins = []
root = "/var/lib/containerd"
state = "/run/containerd"
temp = ""
version = 2

[cgroup]
  path = ""

[debug]
  address = ""
  format = ""
  gid = 0
  level = ""
  uid = 0

[grpc]
  address = "/run/containerd/containerd.sock"
  gid = 0
  max_recv_message_size = 16777216
  max_send_message_size = 16777216
  tcp_address = ""
  tcp_tls_ca = ""
  tcp_tls_cert = ""
  tcp_tls_key = ""
  uid = 0

[metrics]
  address = ""
  grpc_histogram = false

[plugins]
  # 가비지 컬렉션 스케줄러
  [plugins."io.containerd.gc.v1.scheduler"]
    deletion_threshold = 0
    mutation_threshold = 100
    pause_threshold = 0.02
    schedule_delay = "0s"
    startup_delay = "100ms"

  # CRI 플러그인 (Kubernetes 연동 핵심)
  [plugins."io.containerd.grpc.v1.cri"]
    cdi_spec_dirs = ["/etc/cdi", "/var/run/cdi"]
    device_ownership_from_security_context = false
    disable_apparmor = false
    disable_cgroup = false
    disable_hugetlb_controller = true
    disable_proc_mount = false
    disable_tcp_service = true
    drain_exec_sync_io_timeout = "0s"
    enable_cdi = false                              # CDI 비활성화 (기본값)
    enable_selinux = false
    enable_tls_streaming = false
    enable_unprivileged_icmp = false
    enable_unprivileged_ports = false
    ignore_image_defined_volumes = false
    image_pull_progress_timeout = "5m0s"
    max_concurrent_downloads = 3
    max_container_log_line_size = 16384
    restrict_oom_score_adj = false
    sandbox_image = "registry.k8s.io/pause:3.8"     # Pod sandbox 이미지
    selinux_category_range = 1024
    stats_collect_period = 10
    stream_idle_timeout = "4h0m0s"
    stream_server_address = "127.0.0.1"
    stream_server_port = "0"
    systemd_cgroup = false                          # systemd cgroup (Kubernetes 권장)

    # CNI 설정
    [plugins."io.containerd.grpc.v1.cri".cni]
      bin_dir = "/opt/cni/bin"
      conf_dir = "/etc/cni/net.d"
      max_conf_num = 1

    # containerd 코어 설정
    [plugins."io.containerd.grpc.v1.cri".containerd]
      default_runtime_name = "runc"                 # 기본 런타임
      snapshotter = "overlayfs"                     # 스냅샷터

      # 기본 런타임 설정 (deprecated, runtimes 사용 권장)
      [plugins."io.containerd.grpc.v1.cri".containerd.default_runtime]
        runtime_type = ""

      # 런타임 설정
      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes]
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
          runtime_type = "io.containerd.runc.v2"    # shim 타입
          sandbox_mode = "podsandbox"

          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
            BinaryName = ""                         # OCI 런타임 바이너리 (빈값 = runc)
            SystemdCgroup = false                   # systemd cgroup 사용

    # 레지스트리 설정
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = ""

      [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
      [plugins."io.containerd.grpc.v1.cri".registry.configs]

  # 기타 플러그인
  [plugins."io.containerd.internal.v1.opt"]
    path = "/opt/containerd"

  [plugins."io.containerd.internal.v1.restart"]
    interval = "10s"

  [plugins."io.containerd.metadata.v1.bolt"]
    content_sharing_policy = "shared"

  [plugins."io.containerd.runtime.v2.task"]
    platforms = ["linux/amd64"]

  [plugins."io.containerd.snapshotter.v1.overlayfs"]
    root_path = ""
    mount_options = []

[proxy_plugins]

[stream_processors]
  [stream_processors."io.containerd.ocicrypt.decoder.v1.tar"]
    accepts = ["application/vnd.oci.image.layer.v1.tar+encrypted"]
    args = ["--decryption-keys-path", "/etc/containerd/ocicrypt/keys"]
    path = "ctd-decoder"
    returns = "application/vnd.oci.image.layer.v1.tar"

[timeouts]
  "io.containerd.timeout.bolt.open" = "0s"
  "io.containerd.timeout.shim.cleanup" = "5s"
  "io.containerd.timeout.shim.load" = "5s"
  "io.containerd.timeout.shim.shutdown" = "3s"
  "io.containerd.timeout.task.state" = "2s"

[ttrpc]
  address = ""
  gid = 0
  uid = 0
```

</details>

<br>

## 다중 런타임 설정

하나의 containerd에서 여러 OCI 런타임(예: runc, nvidia-container-runtime)을 사용하려면 `runtimes` 섹션에 여러 런타임을 정의한다.

```toml
# Version 2 (containerd 1.x)
[plugins."io.containerd.grpc.v1.cri".containerd]
  default_runtime_name = "runc"      # 기본 런타임

  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes]
    # 기본 runc 런타임
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
      runtime_type = "io.containerd.runc.v2"

      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
        BinaryName = "/usr/bin/runc"
        SystemdCgroup = true

    # NVIDIA GPU 런타임
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
      runtime_type = "io.containerd.runc.v2"

      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
        BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime"
        SystemdCgroup = true

    # gVisor (샌드박스 런타임): https://gvisor.dev/
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.gvisor]
      runtime_type = "io.containerd.runsc.v1"

    # Kata Containers (VM 기반 런타임): https://katacontainers.io/
    # [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata]
    #   runtime_type = "io.containerd.kata.v2"
```

### Kubernetes에서 런타임 선택

Kubernetes Pod에서 특정 런타임을 사용하려면 **RuntimeClass**를 사용한다. RuntimeClass의 `handler`에 사용되는 런타임 이름 값은 containerd 설정의 `[plugins."...".containerd.runtimes.<runtime>]`에서 `<runtime>` 부분과 일치해야 한다. 

```yaml
# RuntimeClass 정의
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia    # containerd 설정의 런타임 이름과 일치해야 함
---
# Pod에서 사용
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  runtimeClassName: nvidia    # RuntimeClass의 metadata.name 참조
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.0-base
```


위 예시에서는 런타임 이름(`nvidia`)과 containerd 설정의 `[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]`에서 명시된 것과 일치한다.


<br>

# 실무 사용 예

## 호스트 containerd vs K3s 내장 containerd

하나의 노드에서 **호스트에 직접 설치된 containerd**와 **K3s에 내장된 containerd**가 공존할 수 있다. 이 경우 설정 파일 위치와 소켓 경로가 다르다.

| 구분 | 호스트 containerd | K3s 내장 containerd |
|-----|------------------|-------------------|
| **바이너리** | `/usr/bin/containerd` | K3s에 내장 |
| **설정 파일** | `/etc/containerd/config.toml` | `/var/lib/rancher/k3s/agent/etc/containerd/config.toml` |
| **소켓** | `/run/containerd/containerd.sock` | `/run/k3s/containerd/containerd.sock` |
| **용도** | 호스트에서 직접 컨테이너 실행 | K3s 클러스터의 Pod 실행 |

```bash
# 호스트 containerd 버전 확인
containerd --version
# containerd containerd.io 1.7.19 2bf793ef6dc9...

# K3s 내장 containerd 버전 확인
k3s crictl version
# RuntimeVersion:  v1.7.11-k3s2.27
```

<br>

## 실제 노드 설정 예시

### 호스트 containerd 설정 (GPU 노드)

NVIDIA GPU가 있는 노드에서 호스트 containerd 설정 예시다. GPU 런타임을 기본으로 설정하고, CDI를 활성화했다.

<details markdown="1">
<summary>호스트 containerd 설정 (클릭하여 펼치기)</summary>

```toml
# /etc/containerd/config.toml
# containerd 1.7.19, configuration version 2

disabled_plugins = []
imports = ["/etc/containerd/config.toml", "/etc/containerd/conf.d/99-nvidia.toml"]  # 추가 설정 파일 import
oom_score = 0
plugin_dir = ""
required_plugins = []
root = "/var/lib/containerd"
state = "/run/containerd"
temp = ""
version = 2

[grpc]
  address = "/run/containerd/containerd.sock"
  # ...

[plugins]
  [plugins."io.containerd.grpc.v1.cri"]
    enable_cdi = true                    # CDI 활성화 (GPU 지원)
    sandbox_image = "registry.k8s.io/pause:3.8"
    # ...

    [plugins."io.containerd.grpc.v1.cri".containerd]
      default_runtime_name = "nvidia"    # GPU 런타임을 기본으로 설정
      snapshotter = "overlayfs"

      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes]
        # NVIDIA 런타임 (기본)
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
          runtime_type = "io.containerd.runc.v2"
          sandbox_mode = "podsandbox"

          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
            BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime"
            SystemdCgroup = false

        # NVIDIA CDI 런타임
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia-cdi]
          runtime_type = "io.containerd.runc.v2"

          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia-cdi.options]
            BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime.cdi"

        # NVIDIA Legacy 런타임
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia-legacy]
          runtime_type = "io.containerd.runc.v2"

          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia-legacy.options]
            BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime.legacy"

        # 표준 runc 런타임 (fallback)
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
          runtime_type = "io.containerd.runc.v2"

          [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
            BinaryName = ""              # 기본 runc 사용
            SystemdCgroup = false
```

</details>

<br>

### K3s 내장 containerd 설정

K3s가 생성하는 containerd 설정이다. K3s 전용 경로와 레지스트리 미러가 설정되어 있다.

호스트 containerd의 전체 설정과 비교하면 항목이 훨씬 적다. **설정 파일에 명시되지 않은 항목은 containerd의 내장 기본값을 따르기 때문에**, 변경이 필요한 항목만 설정하면 된다. K3s는 이 방식으로 필요한 항목(K3s 전용 경로, sandbox 이미지, 레지스트리 미러 등)만 오버라이드한다.

> **주의**: K3s의 containerd 설정 파일 상단에 `# File generated by k3s. DO NOT EDIT. Use config.toml.tmpl instead.`라는 주석이 있다. 직접 수정하면 K3s가 덮어쓰므로, 커스터마이징이 필요하면 `config.toml.tmpl` 파일을 사용해야 한다.

<details markdown="1">
<summary>K3s containerd 설정 (클릭하여 펼치기)</summary>

```toml
# /var/lib/rancher/k3s/agent/etc/containerd/config.toml
# File generated by k3s. DO NOT EDIT. Use config.toml.tmpl instead.

version = 2

[plugins."io.containerd.internal.v1.opt"]
  path = "/var/lib/rancher/k3s/agent/containerd"

[plugins."io.containerd.grpc.v1.cri"]
  stream_server_address = "127.0.0.1"
  stream_server_port = "10010"
  enable_selinux = false
  enable_unprivileged_ports = true
  enable_unprivileged_icmp = true
  sandbox_image = "rancher/mirrored-pause:3.6"      # K3s 전용 sandbox 이미지

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "overlayfs"
  disable_snapshot_annotations = true

[plugins."io.containerd.grpc.v1.cri".cni]
  # K3s 전용 CNI 경로
  bin_dir = "/var/lib/rancher/k3s/data/.../bin"
  conf_dir = "/var/lib/rancher/k3s/agent/etc/cni/net.d"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true                              # K3s는 systemd cgroup 사용

# 레지스트리 미러 설정
[plugins."io.containerd.grpc.v1.cri".registry.mirrors]

[plugins."io.containerd.grpc.v1.cri".registry.mirrors."172.20.10.218"]
  endpoint = ["http://172.20.10.218"]

[plugins."io.containerd.grpc.v1.cri".registry.mirrors."inno.registry.com:5000"]
  endpoint = ["http://inno.registry.com:5000"]

# 레지스트리 인증 및 TLS 설정
[plugins."io.containerd.grpc.v1.cri".registry.configs."172.20.10.218".auth]
  username = "admin"
  password = "Harbor12345"

[plugins."io.containerd.grpc.v1.cri".registry.configs."172.20.10.218".tls]
  insecure_skip_verify = true

# GPU 런타임 추가
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes."nvidia"]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes."nvidia".options]
  BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime"
  SystemdCgroup = true
```

</details>

<br>

## K3s containerd 커스터마이징

K3s의 containerd 설정 파일(`config.toml`)은 **K3s가 시작할 때마다 자동 생성**된다. 파일 상단의 `# File generated by k3s. DO NOT EDIT.` 주석이 이를 알려준다. 직접 `config.toml`을 수정해도 K3s 재시작 시 덮어쓰이므로, **K3s가 권장하는 방법은 템플릿 파일을 사용하는 것**이다.

### 동작 방식

1. K3s는 시작 시 `config.toml.tmpl` 파일이 있는지 확인
2. 템플릿 파일이 있으면 이를 기반으로 `config.toml` 생성
3. 템플릿 파일이 없으면 K3s 내장 기본 설정으로 `config.toml` 생성

### 설정 파일 위치

```bash
# 템플릿 파일 (사용자가 생성/수정)
/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl

# 생성된 설정 파일 (K3s가 관리, 직접 수정해도 재시작 시 덮어쓰일 수 있음)
/var/lib/rancher/k3s/agent/etc/containerd/config.toml

# 레지스트리 설정 (k3s에서는 이 파일을 사용해야 함)
/etc/rancher/k3s/registries.yaml
```

### 템플릿 파일 작성 예시

템플릿 파일은 Go 템플릿 문법을 지원하지만, 일반 TOML로 작성해도 된다:

```toml
# /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl
version = 2

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia.options]
  BinaryName = "/usr/local/nvidia/toolkit/nvidia-container-runtime"
  SystemdCgroup = true
```

Go 템플릿 문법을 사용하면 아래와 같이 작성한다:

```toml
# /var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl
version = 2

# K3s의 기본 설정을 포함
{{ template "base" . }}

# 추가 런타임 설정
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.nvidia]
  runtime_type = "io.containerd.runc.v2"
```

`{{ template "base" . }}`는 K3s의 기본 containerd 설정을 포함한다. 이를 통해 기본 설정을 유지하면서 필요한 부분만 추가할 수 있다.

> **팁**: 레지스트리 미러나 인증 설정만 변경하려면 `registries.yaml`을 사용하는 것이 더 간편하다.

자세한 내용은 [K3s containerd 설정 문서](https://docs.k3s.io/advanced#configuring-containerd)를 참고하자.

<br>

# 정리

| 항목 | 설명 |
|-----|------|
| **설정 파일 위치** | `/etc/containerd/config.toml` (기본), K3s는 `/var/lib/rancher/k3s/agent/etc/containerd/` |
| **설정 파일 형식** | TOML (사람이 읽기 쉽고, 계층 구조에 적합) |
| **설정 버전** | containerd 2.x는 `version = 3`, containerd 1.x는 `version = 2` |
| **자동 마이그레이션** | 시작할 때마다 최신 버전으로 자동 변환 (원본 파일은 유지) |
| **플러그인 구조** | 거의 모든 기능이 플러그인으로 구현됨 |
| **CRI 플러그인** | Kubernetes 연동의 핵심 (`io.containerd.grpc.v1.cri`) |
| **gRPC 사용 이유** | Kubernetes CRI 스펙이 gRPC 기반으로 정의됨 |
| **다중 런타임** | `runtimes` 섹션에 여러 런타임 정의 후 RuntimeClass로 선택 |

<br>

# 참고 자료

- [containerd 공식 GitHub](https://github.com/containerd/containerd)
- [containerd-config.toml.5.md](https://github.com/containerd/containerd/blob/main/docs/man/containerd-config.toml.5.md) - 전체 설정 옵션 레퍼런스
- [CRI plugin config.md](https://github.com/containerd/containerd/blob/main/docs/cri/config.md) - CRI 플러그인 설정
- [PLUGINS.md](https://github.com/containerd/containerd/blob/main/docs/PLUGINS.md) - 플러그인 시스템 설명
- [RELEASES.md - Daemon Configuration](https://github.com/containerd/containerd/blob/main/RELEASES.md#daemon-configuration) - 버전별 설정 호환성
- [TOML 공식 사이트](https://toml.io/) - TOML 형식 문서

<br>

