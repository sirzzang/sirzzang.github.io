---
title: "[NCCL] GPU 호환성 게이트: 빌드 타임과 배포 타임에서 NCCL 커널 미스매치 차단하기"
excerpt: "cuobjdump로 NCCL 바이너리의 SASS/PTX 아키텍처를 분석하고, CI와 init container에서 GPU 호환성을 자동 검증하는 패턴을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - NCCL
  - CUDA
  - cuobjdump
  - GPU
  - MLOps
  - Kubernetes
  - CI-CD
  - Init-Container
---

<br>

# TL;DR

- NCCL `.so` 바이너리 안에는 GPU 아키텍처별로 미리 컴파일된 SASS 커널과 forward compatibility용 PTX가 fatbin으로 묶여 있다. `cuobjdump`로 이 목록을 추출하면 "이 NCCL이 어떤 GPU를 지원하는가"를 정적으로 판정할 수 있다
- **CI 게이트**(빌드 타임): 이미지 빌드 후, push 전에 `docker run` + `cuobjdump`로 SASS/PTX 아키텍처를 대조한다. GPU 없이도 검증 가능하고, 호환되지 않는 이미지가 레지스트리에 올라가는 것 자체를 차단한다
- **런타임 게이트**(배포 타임): K8s init container로 실제 GPU의 compute capability에서 SM 표기를 도출하고, NCCL fatbin의 SASS 목록과 대조한 뒤, 동적으로 NCCL init까지 확인한다. 학습 컨테이너 진입 전에 초 단위로 판정한다
- 두 게이트 모두 ML 엔지니어의 학습 코드를 수정하지 않는다. 빌드 타임은 "배포 전 차단", 배포 타임은 "실제 GPU 기반 정밀 감지"로 역할이 다르다

<br>

# 들어가며

[이전 글]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})에서 NCCL communicator의 lazy init이 디버깅을 어떻게 어렵게 만드는지 분석하고, 마지막에 "플랫폼 레벨에서 GPU↔NCCL 호환성을 사전 검증하는 대안"을 세 가지 제시했다. 빌드 타임 CI/CD 체크, K8s init container, 환경변수 + 타임아웃.

이 글은 그중 앞의 두 가지를 실제로 구현한 결과물이다. 구현하면서 "어떤 원리로 호환성을 판정하는가"가 핵심이라는 걸 느꼈는데, 그 원리는 CUDA fatbin의 구조와 `cuobjdump`라는 도구에 있다. 이걸 먼저 정리하고, 그 위에서 CI 게이트와 런타임 게이트가 어떤 패턴으로 동작하는지 풀어 보겠다.

<br>

# 배경 지식: GPU 바이너리의 구조

> 이 글에서 다루는 NCCL은 NVIDIA GPU 전용 라이브러리이므로, 이하 GPU 바이너리 설명은 모두 NVIDIA CUDA 생태계 기준이다.

## GPU 아키텍처와 Compute Capability

NVIDIA는 GPU를 세대별로 **아키텍처**(microarchitecture)로 분류한다. Ampere, Hopper, Blackwell 같은 이름이 아키텍처명이다. 각 아키텍처 안에서도 칩 구성(SM 수, 메모리 대역 등)이 다른 변종이 있으므로, 이를 구분하기 위해 **compute capability**라는 숫자를 부여한다.

| 아키텍처 | 대표 GPU | Compute Capability | SM 표기 |
| --- | --- | --- | --- |
| Ampere | A100, RTX 3090 | 8.0, 8.6 | sm_80, sm_86 |
| Hopper | H100 | 9.0 | sm_90 |
| Blackwell | B200, RTX 5090 | 10.0, 12.0 | sm_100, sm_120 |

Compute capability는 `X.Y`(major.minor) 형식이고, SM 표기는 이를 합쳐서 `sm_(X*10+Y)`로 쓴다. 예를 들어 compute capability 12.0은 sm_120, 8.6은 sm_86이다. major는 아키텍처 세대, minor는 같은 세대 내 변종을 나타낸다. 이 번호는 단순한 "기능 레벨 표기"가 아니라, **해당 GPU에서 실행 가능한 기계어의 종류를 결정하는 식별자**다. sm_80용으로 컴파일된 바이너리와 sm_90용으로 컴파일된 바이너리는 서로 다른 명령어를 사용한다.

## Fat binary: GPU 바이너리가 "뚱뚱한" 이유

CPU 바이너리는 대체로 하위 호환성이 잘 유지된다. x86-64 바이너리 하나를 빌드하면 10년 전 CPU에서도, 최신 CPU에서도 그냥 돌아간다. ISA(명령어 집합)가 확장은 되어도 기존 명령어를 제거하지 않기 때문이다. 그래서 CPU 라이브러리는 "하나 빌드해서 어디서든 돌린다"가 기본 전제다.

GPU는 사정이 다르다. 같은 NVIDIA라도 major가 바뀌면 기계어(machine code) 자체가 크게 달라진다. sm_80(Ampere)용으로 컴파일된 커널은 sm_120(Blackwell)에서 직접 실행할 수 없고, 그 반대도 마찬가지다. GPU 아키텍처마다 레지스터 파일 구조, warp 스케줄링, 메모리 계층이 재설계되기 때문이다.

그래서 NVIDIA GPU 라이브러리들은 **fat binary(fatbin)** 전략을 쓴다. 하나의 `.so` 안에 여러 아키텍처용 바이너리를 함께 묶어 놓고, 런타임에 현재 GPU에 맞는 것을 골라 실행하는 구조다. "여러 벌을 다 넣어야 한다"는 것은 바이너리 크기가 커진다는 뜻이지만, 그 대가로 두 가지를 얻는다.

- **즉시 실행**: 현재 GPU에 맞는 native 기계어가 이미 들어 있으면 JIT 컴파일 없이 바로 실행한다. NCCL처럼 통신 latency에 민감한 라이브러리에서는 첫 호출에서 발생하는 JIT 지연을 피할 수 있다는 점이 중요하다
- **아키텍처별 최적화**: 같은 allreduce 커널이라도 sm_80과 sm_90에서 최적의 구현이 다르다. 레지스터 수, shared memory 크기, warp 내 동기화 primitive가 달라지기 때문이다. fat binary에 각 아키텍처 전용 native binary(SASS — 아래에서 자세히 다룬다)를 넣어 두면 해당 GPU에서 최적 성능을 낼 수 있다

바이너리 크기 비용은 감수할 만하다. NCCL `.so`의 경우 7개 아키텍처 x 약 19개 커널 = 132개 cubin(개별 GPU 바이너리)이 들어 있어도 전체 크기는 수십 MB 수준이다. 학습 이미지가 수 GB인 환경에서 유의미한 오버헤드가 아니다.

fat binary 안에 들어가는 GPU 코드는 아래서 살펴 볼 SASS, PTX 두 종류로 나뉜다.

## SASS와 PTX

NVIDIA GPU 라이브러리의 `.so` 파일 안에는 두 종류의 GPU 코드가 들어 있다.

| 구분 | 설명 | 실행 방식 |
| --- | --- | --- |
| **SASS**(cubin) | 특정 GPU 아키텍처용으로 미리 컴파일된 native binary | 즉시 실행. JIT 불필요 |
| **PTX** | 가상 ISA(Intermediate Representation) | 로딩 시점에 GPU driver가 JIT 컴파일해서 SASS로 변환 |

SASS는 빠르지만 특정 아키텍처에 종속된다. PTX는 느리지만(첫 로드 시 JIT 지연) 상위 호환(forward compatibility)을 제공한다. cubin이라는 이름은 SASS 쪽에만 붙는다 — cubin은 "CUDA binary"의 줄임말로, 이미 특정 SM을 타깃으로 최종 컴파일된 native 기계어 파일(`.cubin`)을 뜻한다. PTX는 아직 기계어가 아닌 중간 표현이므로 cubin이 아니다. fatbin 안에서도 SASS는 ELF 섹션(`.cubin`)으로, PTX는 텍스트 섹션(`.ptx`)으로 구분되어 들어가며, 후술할 `cuobjdump`의 `-lelf` / `-lptx` 옵션이 이 구분을 그대로 반영한다.

### SASS 호환성

SASS(cubin)는 **같은 major 안에서 minor가 올라가는 방향**으로 호환된다.

> A cubin for a certain compute capability is supported to run on any GPU with the same major revision and same or higher minor revision of compute capability.
> — [CUDA C++ Programming Guide, Compute Capability](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#compute-capabilities)

| cubin 타깃 | 동작하는 GPU | 동작하지 않는 GPU |
| --- | --- | --- |
| sm_80 (major 8, minor 0) | sm_80, sm_86, sm_87, sm_89 | sm_70, sm_90 (다른 major) |
| sm_86 (major 8, minor 6) | sm_86, sm_87, sm_89 | sm_80 (minor가 더 낮음) |

이 규칙 덕분에 라이브러리 빌더는 한 family 안에서 **base(가장 낮은 minor) 하나만** 빌드해 넣으면 상위 variant들을 모두 커버할 수 있다.

### PTX forward compatibility

PTX는 SASS와 다른 방향의 호환성을 제공한다. 위에서 봤듯이 PTX는 native 기계어가 아닌 가상 ISA이므로, driver가 JIT 컴파일할 수만 있다면 특정 아키텍처에 묶이지 않는다.

PTX의 호환 방향은 **상위 한 방향**이다. sm_120 PTX는 sm_120 이상의 GPU에서만 JIT 가능하다. driver가 "sm_120 이상의 명령어 집합을 알고 있을 때"만 변환할 수 있기 때문이다. sm_86 같은 하위 아키텍처에서는 sm_120 PTX를 JIT할 수 없다 — 더 새로운 세대의 명령어를 더 오래된 하드웨어로 변환하는 것은 불가능하다.

이 성질 덕분에 PTX는 "미래의 아직 나오지 않은 GPU"를 위한 보험 역할을 한다. 라이브러리 빌드 시점에는 존재하지 않았던 GPU가 나와도, driver가 업데이트되면 PTX를 JIT해서 동작시킬 수 있다. 다만 JIT 컴파일에는 첫 로드 시 수 초에서 수십 초까지 지연이 발생할 수 있고(라이브러리 크기와 GPU에 따라 다르다), 아키텍처 전용 최적화를 활용하지 못하므로 성능은 native SASS보다 떨어진다.

### SASS vs PTX 비교

두 메커니즘의 차이를 정리하면 다음과 같다.

| | PTX fallback | SASS minor 호환 |
| --- | --- | --- |
| 동작 방식 | 로드 시 driver JIT 컴파일 | 미리 컴파일된 binary 직접 실행 |
| 방향 | 동일/상위 모든 아키텍처 (major 경계 넘음) | 같은 major 안에서만, minor 상승 방향 |
| 비용 | 첫 로드 시 JIT 지연 | 0 |
| 성능 | 아키텍처 전용 최적화 미적용 | native 최적 성능 |
| 용도 | 미래 GPU를 위한 보험 | 현재 지원 GPU의 주 실행 경로 |

## NVIDIA 라이브러리의 fatbin 구성 전략

실제 NVIDIA 라이브러리들은 위의 SASS minor 호환성과 PTX forward compatibility를 조합해서, fat binary를 효율적으로 구성한다.

### SASS 구성 원칙

모든 SM 변종을 다 넣지 않는다. 각 아키텍처 family에서 **base(가장 낮은 minor)** 하나만 포함하면, minor 호환성에 의해 같은 family의 상위 변종이 자동으로 커버된다.

| family base SASS | 커버하는 GPU (minor 호환) |
| --- | --- |
| sm_60 (Pascal) | sm_60, sm_61 |
| sm_70 (Volta) | sm_70, sm_75 (Turing) |
| sm_80 (Ampere) | sm_80, sm_86, sm_87, sm_89 |
| sm_90 (Hopper) | sm_90 |
| sm_100, sm_120 (Blackwell) | sm_100, sm_120 |

예를 들어 sm_86(RTX 3090)은 NCCL SASS에 전용 커널이 없다. 한 번도 포함된 적이 없다. 하지만 sm_80 SASS가 있으면 minor 호환에 의해 문제 없이 동작한다. 호환성 게이트를 만들 때 **exact match가 아닌 major 호환성 체크**가 필요한 이유가 여기에 있다.

### PTX 구성 원칙

빌드 시점의 최신 아키텍처 하나만 포함한다. 옛 아키텍처는 SASS에 다 들어 있으니 PTX가 불필요하고, 미래 아키텍처를 위한 fallback 용도로는 최신 하나면 충분하다. 예를 들어 NCCL 2.29.7은 sm_120 PTX만 포함하고 있으므로, 향후 sm_120 이상의 새 GPU가 나와도 driver JIT으로 동작할 수 있다.

### 세대 교체 시 어떻게 변하는가

NCCL의 빌드 대상 아키텍처는 [빌드 시스템](https://github.com/NVIDIA/nccl/blob/master/makefiles/common.mk)에서 CUDA toolkit 버전에 따라 결정된다. 새 GPU 세대가 나오면 해당 SM이 추가되고, 오래된 세대는 점진적으로 제거된다.

[이전 글]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})의 트러블슈팅 과정에서 문제의 NCCL 2.26.2와 교체 대상인 2.29.7의 SASS를 `cuobjdump`로 직접 비교해 봤다.

| | NCCL 2.26.2 (CUDA 12.2) | NCCL 2.29.7 (CUDA 12.8) |
| --- | --- | --- |
| SASS | sm_50, sm_60, sm_61, sm_70, sm_80, sm_90 | sm_60, sm_61, sm_70, sm_80, sm_90, sm_100, sm_120 |
| PTX | sm_90 | sm_120 |
| 추가된 것 | — | sm_100, sm_120 (Blackwell) |
| 제거된 것 | — | sm_50 (Maxwell, deprecated) |
| 유지된 것 | — | sm_80 (Ampere family base) |

이 비교에서 읽을 수 있는 것은 세 가지다.

- **sm_50이 제거되었다**: Maxwell/초기 Pascal 세대로, CUDA 13.0부터는 sm_75 미만 전체가 deprecated 대상이다. NCCL도 이에 맞춰 점진 제거한다
- **sm_80은 제거되지 않았다**: Ampere GPU(A100, RTX 3090 등)가 아직 현역이므로 base SASS를 유지한다. sm_86/87/89를 커버하는 유일한 SASS이기 때문에, sm_80이 빠지면 Ampere 계열 전체가 동작하지 않는다
- **sm_100, sm_120이 추가되었다**: CUDA 12.8에서 Blackwell 지원이 들어오면서 추가. 이것이 없으면 Blackwell GPU에서 NCCL이 동작하지 않는다 — [이전 글]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})에서 겪었던 문제의 정확한 원인이다

이 패턴은 예측 가능하다. 새 GPU가 나오면 해당 SASS가 추가되고, 오래된 GPU가 deprecated되면 해당 SASS가 제거된다. 그 사이 **family base는 반드시 유지된다** — 제거하면 해당 family 전체가 깨지기 때문이다. 이 성질을 활용하면 호환성 게이트를 설계할 때 "exact SM이 있는가?"가 아니라 "같은 major의 base SASS가 있는가?"로 판정할 수 있다. 이 판정 로직의 구체적인 구현은 [CI 게이트](#major-호환성-판정) 섹션에서 다룬다.

## cuobjdump: fatbin을 들여다보는 도구

`cuobjdump`는 CUDA Toolkit의 developer tools에 속하는 바이너리로, `.so`나 `.fatbin` 안에 묶인 GPU 코드를 분석하는 도구다.

| 컨테이너 이미지 계층 | cuobjdump 포함 여부 |
| --- | --- |
| NVIDIA 공식 `-devel` 이미지 (`nvidia/cuda:12.x-devel-*`) | O |
| NVIDIA 공식 `-runtime` 이미지 (`nvidia/cuda:12.x-runtime-*`) | X |
| PyTorch wheel (`torch+cu12x`) | X |
| pip `nvidia-nccl-cu12` wheel | X |

호환성 게이트를 사용하려면 학습 이미지가 `-devel` variant 기반이거나, `cuda-cuobjdump-12-x` 패키지가 별도 설치되어 있어야 한다. ML 학습 이미지는 보통 `-devel` 기반이므로 대부분 바로 사용 가능하다.

### 핵심 옵션

게이트에서 사용하는 옵션은 아래 두 가지다.

| 옵션 | 출력 |
| --- | --- |
| `-lelf` | fatbin에 포함된 **SASS(cubin)** 목록. 각 cubin의 아키텍처 식별 가능 |
| `-lptx` | fatbin에 포함된 **PTX** 목록 |

```bash
# NCCL .so의 SASS 아키텍처 목록 확인
$ cuobjdump -lelf /path/to/libnccl.so.2 | grep -oP 'sm_\d+' | sort -u
sm_100
sm_120
sm_60
sm_61
sm_70
sm_80
sm_90

# PTX 아키텍처 확인
$ cuobjdump -lptx /path/to/libnccl.so.2 | grep -oP 'sm_\d+' | sort -u
sm_120
```

위 결과를 해석해 보자.

- SASS 7종이 들어 있다. sm_60~sm_120까지 family별 base가 모두 있고, sm_86(Ampere 변종)은 sm_80이 커버한다
- PTX는 sm_120 하나만 포함되어 있다. 미래 아키텍처를 위한 fallback 용도다
- 총 cubin 수는 132개 정도다. 7개 아키텍처 x 약 19개 collective primitive(allreduce, broadcast 등)가 각각 별도 cubin으로 들어 있다

<br>

# CI 게이트: 빌드 타임 검증

## 학습 이미지와 호환성의 결정 시점

ML 학습 이미지는 보통 NVIDIA base 이미지(CUDA user-space libraries 포함, driver는 host 노드에 별도 설치) 위에 PyTorch, NCCL 등 의존성을 쌓아 빌드한다. 이 이미지에 어떤 버전의 NCCL `.so`가 들어가느냐에 따라 GPU 호환성이 결정되므로, **이미지 빌드가 곧 "호환성이 결정되는 시점"**이다.

[이전 글]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})에서 다뤘던 문제가 정확히 이 지점에서 발생했다. base 이미지에 포함된 NCCL 2.26.2가 CUDA 12.2로 빌드되어 있어서 sm_120(Blackwell) 커널이 누락되어 있었고, 그 위에 빌드된 학습 이미지가 RTX 5090 노드에 배포되면서 silent hang이 발생했다. NCCL을 sm_120 지원 버전(2.29.7)으로 올린 새 base 이미지를 만들어서 문제 자체는 해결했지만, "다음에 또 같은 실수가 반복되지 않으려면?" 이라는 질문이 남았다. CI 게이트는 그 답이다.

## 원리

이미지를 빌드한 직후, 레지스트리에 push하기 전에 "이 이미지 안의 NCCL이 우리 클러스터의 GPU를 지원하는가?"를 검증한다. GPU 디바이스 없이도 가능한 정적 분석이다.

```text
Git tag push → CI 트리거 → 이미지 빌드 완료
  → GPU 호환성 게이트 (cuobjdump 분석)
    → PASS → 이미지 push
    → FAIL → push 차단, 빌드 실패
```

## 패턴

CI 러너에서 빌드된 이미지를 `docker run`으로 띄우고, 이미지 내부의 `cuobjdump`로 NCCL `.so`를 분석한다.

```bash
# CI 게이트 핵심 로직 (간략화)
IMAGE="registry.example.com/myorg/train-image:latest"
REQUIRED_GPU_ARCHS="sm_120 sm_80"  # 클러스터에 있는 GPU들의 base SM

docker run --rm --entrypoint="" "$IMAGE" python3 -c "
import subprocess, re, glob, sys

# 1. NCCL .so 경로 탐지 (환경에 따라 후보 경로를 조정)
search_patterns = [
    '/usr/lib/x86_64-linux-gnu/libnccl.so*',           # system NCCL
    '/usr/local/lib/python*/dist-packages/nvidia/nccl/lib/libnccl.so*',  # pip wheel
    '/opt/conda/lib/python*/site-packages/nvidia/nccl/lib/libnccl.so*',  # conda
]
nccl_paths = []
for pat in search_patterns:
    nccl_paths.extend(glob.glob(pat))
if not nccl_paths:
    print('NCCL_NOT_FOUND'); sys.exit(2)
nccl_so = nccl_paths[0]

# 2. cuobjdump로 SASS/PTX 추출
sass_out = subprocess.run(['cuobjdump', '-lelf', nccl_so], capture_output=True, text=True)
sass_archs = sorted(set(re.findall(r'sm_\d+', sass_out.stdout)))

ptx_out = subprocess.run(['cuobjdump', '-lptx', nccl_so], capture_output=True, text=True)
ptx_archs = sorted(set(re.findall(r'sm_\d+', ptx_out.stdout)))

print(f'SO_PATH={nccl_so}')
print(f'SASS={\" \".join(sass_archs)}')
print(f'PTX={\" \".join(ptx_archs)}')
"
```

> 이 스크립트는 이미지 내부에 `python3`이 있어야 동작한다. ML 학습 이미지는 PyTorch 등 Python 기반 프레임워크가 기본이므로 거의 문제 없지만, 외부 벤더의 runtime-only 이미지처럼 Python이 없는 경우를 대비해 스크립트 진입 전에 `python3 --version` probe를 넣어 두는 것이 좋다. probe 실패 시 "python3 미존재" 명시적 에러로 분리하면, "SASS가 없어서 실패한 건지" "분석 자체가 안 된 건지" 모호함을 방지할 수 있다.

## Major 호환성 판정

CI 게이트가 `REQUIRED_GPU_ARCHS="sm_120 sm_80"`을 받으면, 각 required arch에 대해 3단계로 판정한다.

1. **Exact SASS match**: SASS 목록에 해당 SM이 있으면 PASS
2. **Major-compatible SASS**: 같은 major의 base SM이 있으면 PASS (예: sm_86 요구 → sm_80 있으면 통과)
3. **PTX coverage**: PTX가 해당 SM 이상이면 WARNING (JIT 가능하지만 성능 불확실)
4. 어디에도 해당 없으면 FAIL

Major 추출은 `floor(SM번호 / 10)`으로 계산한다. sm_80 → major 8, sm_86 → major 8, sm_120 → major 12. compute capability X.Y에서 SM = X*10+Y이므로, floor(SM/10) = X(major)가 된다.

```bash
# major 호환성 함수 (bash)
extract_major() {
    local sm="$1"
    local num="${sm#sm_}"
    echo $((num / 10))
}
# sm_80 → 8, sm_86 → 8, sm_120 → 12, sm_90 → 9
```

## PASS/FAIL 출력 예시

sm_80이 정확히 일치하여 PASS하는 경우다.

```text
[gpu-compat-check]   .so path: /path/to/libnccl.so.2
[gpu-compat-check]   SASS architectures: sm_50 sm_60 sm_61 sm_70 sm_80 sm_90
[gpu-compat-check]   PTX architectures:  none
[gpu-compat-check]   RESULT: PASS
[gpu-compat-check] All GPU compatibility checks passed.
```

sm_86을 sm_80의 major 호환으로 통과하는 경우다.

```text
[gpu-compat-check]   SASS architectures: sm_50 sm_60 sm_61 sm_70 sm_80 sm_90
[gpu-compat-check]   sm_86: covered by sm_80 (same major 8)
[gpu-compat-check]   RESULT: PASS
```

sm_120이 누락되어 NCCL 구버전이 Blackwell을 지원하지 못해 FAIL하는 경우다.

```text
========================================
  FATAL: GPU kernel mismatch
========================================
  Library:   libnccl
  Image:     registry.example.com/myorg/train-image:v1.2.3
  SASS:      sm_50 sm_60 sm_61 sm_70 sm_80 sm_90
  PTX:       none
  Required:  sm_120 sm_80
  Missing:   sm_120

  Action:  Upgrade the GPU library to a version built with a
           CUDA toolkit that supports the missing architectures.
========================================
```

이 FAIL이 걸리면 이미지 push 단계가 실행되지 않으므로, 호환되지 않는 이미지가 레지스트리에 올라가는 것 자체를 차단한다.

## CI workflow에서의 위치

```yaml
# CI workflow (간략화)
jobs:
  build:
    steps:
      - name: Build image
        # ... docker build ...

      - name: Validate GPU library compatibility
        if: ${{ inputs.skip_gpu_check != 'true' }}
        env:
          IMAGE: ${{ steps.meta.outputs.image_tag }}
          REQUIRED_GPU_ARCHS: "sm_120 sm_80"
        run: |
          bash gpu-compat-check.sh

      - name: Push image
        # ... docker push ...
```

`skip_gpu_check` input은 긴급 우회용이다. 게이트 자체에 문제가 있거나, 의도적으로 호환되지 않는 이미지를 push해야 할 때 사용한다.

<br>

# 런타임 게이트: init container

## 원리

CI 게이트는 "이미지가 특정 GPU를 지원하는가"를 이미지 빌드 시점에 검증하지만, 실제로 어떤 GPU가 할당되는지는 배포 시점에야 알 수 있다. 런타임 게이트는 **실제 GPU가 할당된 상태에서** 호환성을 검증하고, 학습 컨테이너가 뜨기 전에 차단한다.

```text
Pod 생성 → init container (gpu-compat-check)
  → PASS → main container (학습) 시작
  → FAIL → Pod Init:Error, 학습 미시작
```

## 3-Stage 구조

init container는 3단계로 검사한다. 단계가 올라갈수록 검증 범위가 넓어진다.

### Stage 1: GPU Detection

```bash
# nvidia-smi로 GPU 정보 쿼리
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
# → "NVIDIA GeForce RTX 5090", "12.0"
# SM 계산: 12.0 → sm_120
```

GPU가 감지되지 않으면 즉시 FATAL로 종료한다. device plugin 미등록 등의 문제를 학습 시작 전에 잡아낸다.

### Stage 2: NCCL Kernel Static Check

Stage 1에서 얻은 GPU SM과, NCCL `.so`의 SASS/PTX를 대조한다. CI 게이트와 동일한 major 호환성 로직을 사용한다.

```bash
# cuobjdump으로 NCCL SASS/PTX 분석
NCCL_SO=$(find / -name 'libnccl.so*' -type f 2>/dev/null | head -1)
SASS=$(cuobjdump -lelf "$NCCL_SO" 2>&1 | grep -oP 'sm_\d+' | sort -u | tr '\n' ' ')
PTX=$(cuobjdump -lptx "$NCCL_SO" 2>&1 | grep -oP 'sm_\d+' | sort -u | tr '\n' ' ')

# GPU SM이 SASS에 있는지 (exact 또는 major-compat) 판정
```

`cuobjdump`이나 `libnccl.so`가 없는 경우 WARNING만 출력하고 Stage 3으로 넘어간다(graceful degradation).

### Stage 3: NCCL Init Dynamic Test

정적 분석을 통과했더라도 driver/runtime/PyTorch binding 레벨에서 문제가 있을 수 있다. 단일 rank로 NCCL `init_process_group` + `all_reduce`를 한 번 실행해서 스택 전체가 동작하는지 확인한다.

```bash
timeout $TIMEOUT python3 -c "
import os, torch, torch.distributed as dist
os.environ.update({
    'MASTER_ADDR': '127.0.0.1', 'MASTER_PORT': '29500',
    'RANK': '0', 'WORLD_SIZE': '1'
})
dist.init_process_group(backend='nccl')
t = torch.ones(1, device='cuda')
dist.all_reduce(t)
print('NCCL init + all_reduce: OK')
dist.destroy_process_group()
"
```

timeout이 발생하면(exit 124) NCCL init hang으로 판정한다.

> Stage 3도 `python3`을 호출한다. 학습 이미지이므로 PyTorch + Python이 없을 리 없지만, 스크립트 진입 전 `command -v python3` probe를 두면 "Python 미존재"와 "NCCL 문제"를 명확히 분리할 수 있다.

> Stage 3는 single-rank(WORLD_SIZE=1) sanity check다. single-rank `all_reduce`는 NCCL의 P2P 경로를 거의 타지 않으므로, 이 stage가 검증하는 것은 "NCCL communicator init이 시작되고 기본 collective primitive가 호출 가능한가" 수준이다. cross-rank handshake(NIC/IB 설정, NCCL_SOCKET_IFNAME 등) 이슈는 검증 범위 밖이다. 그러나 이 글이 다루는 문제(SASS 미스매치로 인한 lazy init hang)는 init 시점에 잡히는 종류이므로, Stage 2 정적 분석을 통과한 후 "실제로 NCCL init까지 가는가"를 확인하는 보완 검사로서 충분히 의미가 있다.

## PASS/FAIL 출력 예시

NCCL 신버전과 호환 GPU에서 PASS하는 경우다.

```text
========================================
  GPU Compatibility Pre-flight Check
========================================
  Node:  gpu-node-01
  Image: registry.example.com/myorg/train-image-base:latest

[Stage 1] Detecting GPU...
  GPU:     NVIDIA GeForce RTX 5090
  SM:      sm_120 (major: 12, base: sm_120)
  Driver:  580.126.09

[Stage 2] Checking NCCL kernels...
  NCCL path: /path/to/libnccl.so.2
  SASS: sm_100 sm_120 sm_60 sm_61 sm_70 sm_80 sm_90
  PTX:  sm_120
  RESULT: PASS (exact SASS match: sm_120)

[Stage 3] Testing NCCL initialization (timeout: 30s)...
NCCL init + all_reduce: OK

========================================
  All GPU compatibility checks PASSED
========================================
```

NCCL 구버전과 Blackwell GPU에서 FAIL하는 경우다.

```text
========================================
  GPU Compatibility Pre-flight Check
========================================
  Node:  gpu-node-01
  Image: registry.example.com/myorg/train-image:v1.2.3

[Stage 1] Detecting GPU...
  GPU:     NVIDIA GeForce RTX 5090
  SM:      sm_120 (major: 12, base: sm_120)
  Driver:  580.126.09

[Stage 2] Checking NCCL kernels...
  NCCL path: /path/to/libnccl.so.2
  SASS: sm_50 sm_60 sm_61 sm_70 sm_80 sm_90
  PTX:  none

========================================
  FATAL: NCCL GPU kernel mismatch
========================================
  Node:      gpu-node-01
  GPU:       NVIDIA GeForce RTX 5090 (sm_120)
  Driver:    580.126.09
  NCCL SASS: sm_50 sm_60 sm_61 sm_70 sm_80 sm_90
  NCCL PTX:  none
  Required:  sm_120 (or major-compatible sm_12X)

  NCCL .so에 이 GPU용 커널이 포함되어 있지 않습니다.
  분산 학습 시 ncclCommInitRank에서 silent hang이 발생합니다.

  해결:
  1. training-base 이미지의 nvidia-nccl-cu12 버전 확인
  2. sm_120 지원하는 NCCL 버전으로 업그레이드
  3. 참조: 호환성 매트릭스
========================================
```

이전 글에서 다뤘던 "학습이 한참 진행된 뒤에야 발견되는" 문제가, 여기서는 **학습 시작 전 수 초 만에** root cause를 직접 가리키는 에러 메시지와 함께 차단된다.

## Helm 통합

init container는 Helm values로 on/off 전환한다.

```yaml
# values.yaml
gpuCompatCheck:
  enabled: true
  timeoutSeconds: 30  # Stage 3 single-rank sanity check 기준. 실제 분산 학습 NCCL init timeout과는 별개
```

템플릿에서는 GPU worker group에만 init container를 추가한다. 아래 예시는 RayJob spec 기준이지만, init container 패턴 자체는 plain Pod, Job, KubeflowJob 등 어디에든 동일하게 적용할 수 있다.

```yaml
# rayjob.yaml (간략화)
workerGroupSpecs:
  - groupName: gpu-workers
    template:
      spec:
        {{- if .Values.gpuCompatCheck.enabled }}
        initContainers:
          - name: gpu-compat-check
            image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
            command: ["bash", "-c"]
            args:
              - |
                # 3-stage check script (~150줄)
                ...
            env:
              - name: NODE_NAME
                valueFrom:
                  fieldRef:
                    fieldPath: spec.nodeName
              - name: TIMEOUT
                value: "{{ .Values.gpuCompatCheck.timeoutSeconds }}"
            resources:
              limits:
                nvidia.com/gpu: {{ .Values.gpuWorker.gpu }}
        {{- end }}
        containers:
          - name: ray-gpu-worker
            # ... 학습 컨테이너 ...
```

설계 시 고려한 포인트는 다음과 같다.

- **head/cpu-workers에는 추가하지 않는다**: NCCL을 사용하지 않는 노드에 불필요
- **학습과 동일 이미지를 사용한다**: cuobjdump, NCCL `.so` 경로가 동일해야 정확한 검사가 가능
- **GPU 리소스를 동일하게 요청한다**: K8s는 `max(init, main)` 기준으로 스케줄링하므로 추가 GPU를 소비하지 않음
- **NODE_NAME을 fieldRef로 주입한다**: 에러 메시지에 노드 식별 정보를 포함, 이종 GPU 환경에서 어떤 노드가 문제인지 즉시 파악 가능

긴급 비활성화는 `gpuCompatCheck.enabled=false`로 전환한다.

<br>

# 두 게이트의 분업

## 비교

| | CI 게이트 (빌드 타임) | 런타임 게이트 (init container) |
| --- | --- | --- |
| 감지 시점 | 이미지 빌드 시 (배포 전) | Pod 시작 시 (학습 전) |
| GPU 필요 여부 | 불필요 (정적 분석) | 필요 (실제 GPU 할당 상태) |
| 에러 메시지 명확도 | 높음 (SASS/PTX 목록 + missing arch) | 높음 (GPU 모델 + SASS + 해결 가이드) |
| GPU 점유 | 없음 | 수 초 |
| 이종 GPU 대응 | 클러스터 known GPU set으로 정의 | 자동 (실제 GPU compute cap 감지) |
| 검증 깊이 | SASS/PTX 존재 여부만 | + driver/runtime/PyTorch binding |
| 우회 방법 | `skip_gpu_check=true` | `gpuCompatCheck.enabled=false` |

## 권장 조합

두 게이트는 상호 보완 관계다.

- **CI 게이트만 있으면**: 이미지에는 커널이 있지만, 실제 할당된 GPU가 예상과 다른 경우(이종 GPU 환경)를 놓친다
- **런타임 게이트만 있으면**: 호환되지 않는 이미지가 레지스트리에 올라가는 것을 막지 못한다. 매번 Pod 시작 시마다 GPU를 점유한다
- **둘 다 있으면**: CI 게이트가 1차 방어선으로 "명백히 틀린 이미지"를 배포 전에 차단하고, 런타임 게이트가 2차 방어선으로 "실제 GPU와의 정합성"을 확인한다

```text
이미지 빌드 → [CI 게이트] → 레지스트리 push → 배포 → [런타임 게이트] → 학습 시작
     ↑ 1차 방어: "이 이미지가 맞나?"        ↑ 2차 방어: "이 GPU에서 되나?"
```

<br>

# 정리

NCCL lazy init 환경에서 GPU 호환성 문제는 "학습이 한참 진행된 뒤에야" 발견되고, 에러 메시지는 root cause를 가리키지 않는다. 이 문제를 ML 엔지니어의 학습 코드를 건드리지 않고 플랫폼 레벨에서 해결하는 방법을 세 가지로 정리할 수 있다.

1. **원리**: `cuobjdump`로 NCCL `.so`의 SASS/PTX 아키텍처를 추출하고, GPU의 compute capability와 major 호환성 기준으로 대조한다
2. **빌드 타임**: CI 파이프라인에서 이미지 push 전에 정적 분석으로 차단한다. GPU 없이 실행 가능
3. **배포 타임**: K8s init container로 실제 GPU와 NCCL의 정합성을 확인한다. 학습 진입 전 초 단위로 판정

GPU 종류가 바뀌거나 NCCL 버전이 올라가도, 게이트 로직은 수정 없이 동작한다. cuobjdump가 매번 실제 바이너리를 분석하기 때문이다.

<br>

# 참고 자료

- [NVIDIA Ampere Compatibility Guide](https://docs.nvidia.com/cuda/ampere-compatibility-guide/) — cubin minor 호환성 규칙
- [NVIDIA Blackwell Compatibility Guide](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/) — Blackwell GPU 지원 요구사항
- [Matching CUDA arch and gencode for various NVIDIA architectures](https://arnon.dk/matching-sm-architectures-arch-and-gencode-for-various-nvidia-cards/) — SM 아키텍처 매핑 정리
- [CUDA Programming Guide — Compute Capabilities](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#compute-capabilities) — compute capability 공식 문서

<br>
