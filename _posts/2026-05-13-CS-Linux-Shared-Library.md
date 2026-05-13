---
title: "[Linux] 공유 라이브러리(.so): soname 계약부터 동적 링커 탐색까지"
excerpt: "soname/ABI 계약, RPATH와 RUNPATH의 우선순위 역전, 정적 링크 트레이드오프, NVIDIA pip 이중 구조를 정리해 보자."
categories:
  - CS
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Shared Library
  - Dynamic Linking
  - ELF
  - soname
  - ABI
  - RPATH
  - LD_LIBRARY_PATH
---

<br>

[NCCL 트러블슈팅]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %}) 과정에서 컨테이너 안의 NCCL 버전이 GPU와 맞지 않는 상황을 만났다. 보통 Linux에서 `.so`를 교체할 때는 `LD_LIBRARY_PATH` 환경변수로 탐색 경로를 바꾸면 되는데, 이번에는 그 방법이 통하지 않았다. PyTorch pip wheel이 `DT_RPATH`에 번들 NCCL 경로를 하드코딩하고 있어서, 동적 링커가 환경변수보다 RPATH를 먼저 탐색하기 때문이었다. 

이 한 문장을 이해하려면 `.so` 파일, soname, ABI, 동적 링커의 탐색 순서가 어떻게 얽혀 있는지를 같이 봐야 했다.

돌이켜 보면 [디바이스 드라이버 3계층 구조]({% post_url 2026-02-01-CS-Linux-Device-Driver %})에서 유저 라이브러리(`.so`)를 한 계층으로 소개하긴 했지만, `.so` 자체가 어떻게 버전 관리되고 런타임에 어떤 규칙으로 로드되는지까지는 다루지 않았다. 이번 트러블슈팅이 정확히 그때 미뤄둔 부분에서 발목을 잡은 셈이라, 이 참에 한 번 제대로 정리해 두기로 했다.

개념을 짚되 트러블슈팅 사례를 곁들여 가는 식으로 구성해 보고자 한다. 이에 soname/ABI 계약, 동적 링커의 탐색 순서, 정적 vs 동적 링크의 트레이드오프, NVIDIA pip 배포가 만드는 이중 구조를 차례로 다루되, 각 절마다 위 NCCL 사례가 어디에 어떻게 걸렸는지를 함께 짚어 본다. 본문에 등장하는 `readelf -d`, `ldd`, `LD_DEBUG` 같은 확인 도구는 마지막 섹션에 한 번에 모아 두었다.

<br>

# TL;DR

- soname은 라이브러리 관리자의 ABI 호환 약속을 시스템 레벨에서 표현한다. 동적 링커는 soname 문자열 매칭만 강제한다
- 동적 링커의 `.so` 탐색 순서는 바이너리에 `DT_RPATH`가 박혀 있는지 `DT_RUNPATH`가 박혀 있는지에 따라 분기한다. 둘이 동시에 존재하면 RPATH는 무시된다
- `DT_RPATH`가 박혀 있으면 `LD_LIBRARY_PATH`로 우회 불가. `LD_PRELOAD`나 바이너리 수정이 필요하다
- 정적 링크는 self-contained 대신 내부 버전을 외부에서 교체할 수 없는 경직성과 묶여 있다
- NVIDIA pip 배포 전략으로 시스템 경로와 pip 경로에 같은 soname의 `.so`가 이중 존재한다

<br>

# .so 파일이란

**Shared Object** — Linux에서 여러 프로세스가 공유해서 쓰는 컴파일된 네이티브 코드 바이너리다. Windows의 `.dll`에 해당한다.

- C/C++ 소스를 `-fPIC`로 컴파일해서 위치 독립 오브젝트(`.o`)를 만들고 `-shared`로 링크하면 `.so` 파일이 만들어진다 (`gcc -shared`는 엄밀히 링크 단계 옵션이고, `.o`가 PIC로 컴파일되어 있어야 동작한다)
- NCCL, CUDA runtime, cuDNN 등은 전부 C/C++로 작성된 라이브러리이고, 최종 산출물이 `.so` 파일이다
- Python 자체도 네이티브 확장을 `.so`로 만든다 (예: `torch._C.cpython-310-x86_64-linux-gnu.so`)

디바이스 드라이버 3계층 중 유저 라이브러리 계층이 바로 이 `.so`다. 커널 모듈(`.ko`)이 하드웨어와 직접 통신하는 인터페이스라면, `.so`는 그 위에서 유저 프로그램이 사용하는 고수준 인터페이스다. [FHS(Filesystem Hierarchy Standard)]({% post_url 2026-01-31-CS-Everything-is-a-File %}#파일-시스템-계층)에서 `.so`가 배치되는 표준 경로는 `/lib/`, `/usr/lib/`이다.

<br>

# soname 관례와 심볼릭 링크 체인

## 버전 번호와 3단 구조

`.so` 파일에는 버전 번호가 붙고, 심볼릭 링크 체인으로 연결된다.

```text
libnccl.so       → libnccl.so.2           (심볼릭 링크. 빌드 시 -lnccl로 참조)
libnccl.so.2     → libnccl.so.2.26.2      (심볼릭 링크. soname — 런타임에 실제 참조되는 이름)
libnccl.so.2.26.2                         (실제 바이너리 파일)
```

| 파일 | 역할 | 참조 시점 |
|------|------|-----------|
| `libnccl.so` | 개발용(development) 링크 | 빌드 타임 (`gcc -lnccl`) |
| `libnccl.so.2` | **soname** — 런타임 참조 이름 | 런타임 (동적 링커가 탐색) |
| `libnccl.so.2.26.2` | 실제 바이너리 | 항상 (심볼릭 링크의 최종 목적지) |

개발용 링크(`libnccl.so`)는 보통 `libnccl-dev` 같은 별도 dev 패키지에 들어 있다. 런타임 패키지(`libnccl2`)만 설치된 시스템에는 이 심볼릭 링크가 없어 `gcc ... -lnccl` 시 `cannot find -lnccl` 에러가 날 수 있다.

핵심은 **soname**(`libnccl.so.2`)이다. 프로그램이 빌드될 때 "나는 `libnccl.so.2`가 필요하다"가 ELF(Executable and Linkable Format) 바이너리의 `DT_NEEDED` 태그에 기록된다. 런타임에 동적 링커가 이 이름을 찾아서 로드하면, 심볼릭 링크가 가리키는 실제 바이너리(`libnccl.so.2.26.2`)가 메모리에 매핑된다.

soname 자체는 파일 이름이 아니라 `.so` 안의 `DT_SONAME` 태그에 박힌 문자열이다 (빌드 시 `gcc -Wl,-soname=...`로 결정). 관례적으로 그 문자열을 심볼릭 링크 이름과 같게 쓸 뿐이다.

`DT_`는 "Dynamic Tag"의 약자로, ELF 바이너리의 `.dynamic` 섹션에 저장되는 메타데이터 태그다. 정적 링커가 빌드 시 기록하고, 동적 링커가 런타임에 읽는다. 본문에서 반복 등장하는 `DT_` 태그를 미리 정리하면 아래와 같다.

| 태그 | 역할 | 예시 |
|------|------|------|
| `DT_NEEDED` | 이 바이너리가 의존하는 `.so`의 soname | `libnccl.so.2` |
| `DT_SONAME` | 이 `.so` 자신의 soname | `libnccl.so.2` |
| `DT_RPATH` | 하드코딩된 탐색 경로 (`LD_LIBRARY_PATH`보다 우선) | `$ORIGIN/../../nvidia/nccl/lib` |
| `DT_RUNPATH` | 하드코딩된 탐색 경로 (`LD_LIBRARY_PATH`보다 후순위) | `$ORIGIN/../lib` |

`readelf -d`로 이 태그들을 확인할 수 있다. `DT_NEEDED`와 `DT_SONAME`은 바로 위 soname 체계의 구현이고, `DT_RPATH`/`DT_RUNPATH`는 뒤에서 다룰 동적 링커 탐색 순서의 핵심 변수다.

## 심볼릭 링크는 누가 만드는가

두 가지 경로가 있다.

### 경로 1: 패키지 매니저 설치 (일반적)

패키지의 post-install 스크립트가 심볼릭 링크를 만들고, `ldconfig`를 실행해서 캐시를 갱신한다. `apt install libnccl2` → 바이너리 배치 + ldconfig 자동 실행 → 심볼릭 링크 생성까지 한 번에 일어난다.

`ldconfig`는 `.so` 파일을 스캔하여 soname 심볼릭 링크를 자동 생성하는 시스템 도구다.

1. `.so` 바이너리 안에는 자신의 soname이 기록되어 있다 (`readelf -d libnccl.so.2.26.2 | grep SONAME` → `libnccl.so.2`)
2. `ldconfig`를 실행하면, 지정된 경로(`/etc/ld.so.conf`에 등록된 디렉토리 + `/lib`, `/usr/lib`)를 스캔한다
3. 각 `.so` 파일에서 soname을 읽어서 해당 이름의 심볼릭 링크를 자동 생성한다
4. 동시에 `/etc/ld.so.cache`를 갱신하여 동적 링커가 빠르게 찾을 수 있게 한다

### 경로 2: 수동 설치

소스에서 직접 빌드(`make install`)하거나, tarball을 풀어서 `.so` 파일을 직접 배치하는 경우다. 패키지 매니저가 개입하지 않으므로:

- `make install` 후 사용자가 `ldconfig`를 수동으로 실행해야 심볼릭 링크가 만들어진다
- 또는 `ln -s libnccl.so.2.26.2 libnccl.so.2`로 직접 링크를 만들 수도 있다 — ldconfig 관리 경로 밖에 `.so`를 배치하는 경우(예: `/opt/custom/lib/`)에는 이 방법을 쓰기도 한다

## 업그레이드와 ldconfig

같은 soname(`libnccl.so.2`)을 가진 `libnccl.so.2.26.2`와 `libnccl.so.2.29.7`이 같은 디렉토리에 있을 때 `ldconfig`를 실행하면, 두 파일을 같은 soname 그룹으로 묶은 뒤 그 그룹 안에서 **버전 문자열을 자연순(version sort)으로 비교해 큰 쪽**(`libnccl.so.2.29.7`)으로 심볼릭 링크를 만든다. ldconfig 자체는 glibc의 `strverscmp(3)`을 직접 호출하지 않고, 내부 비교 함수(`_dl_cache_libcmp` 등)로 비슷한 자연순 비교를 자체 구현한다. 그룹화는 각 `.so`의 `DT_SONAME` 기준이므로, `libnccl.so.2.x`와 `libnccl.so.3.x`가 같은 디렉토리에 공존해도 서로 다른 그룹으로 분리되어 각자 별개의 심볼릭 링크가 만들어진다. 결과적으로 같은 major 안에서 minor/patch가 큰 쪽이 선택된다.

```text
libnccl.so.2 → libnccl.so.2.29.7      (링크가 새 버전을 가리킴)
libnccl.so.2.26.2                       (구 바이너리, 아직 남아있을 수 있음)
libnccl.so.2.29.7                       (새 바이너리)
```

즉 업그레이드 흐름은 상위 버전 `.so` 설치 → ldconfig 실행(패키지 매니저가 자동으로 해 줌) → 심볼릭 링크가 새 바이너리를 가리키도록 갱신하는 것이다. 따라서 `libnccl.so.2`를 `NEEDED`로 기록해 둔 프로그램은 재빌드 없이 자동으로 새 버전을 사용하게 된다 — soname이 같으므로 동적 링커 입장에서는 아무것도 바뀌지 않게 되는 셈이다.

<br>

# ABI 계약

앞에서 soname이 같으면 minor 버전이 달라도 안전하게 교체할 수 있다고 했다. 이것이 가능한 이유가 ABI 계약이다. soname은 단순한 이름 규칙이 아니라, "이 이름 안에서는 바이너리 호환성을 보장한다"는 약속을 담고 있다.

## ABI란

**ABI(Application Binary Interface)**는 컴파일된 바이너리 수준에서의 인터페이스 규약이다. 구체적으로 다음을 정의한다:

- **호출 규약**(calling convention): 함수 인자를 어떤 레지스터/스택에 넣는가, 반환값은 어디에 놓는가
- **심볼 이름**: 컴파일된 바이너리에서 함수/변수가 어떤 이름으로 노출되는가 (C++ name mangling 포함)
- **구조체 메모리 레이아웃**: 필드 순서, 크기, 정렬(alignment)이 바이너리 수준에서 어떻게 배치되는가

ABI가 호환되면 프로그램을 다시 빌드하지 않고 `.so`만 교체해도 정상 동작한다. soname은 이 ABI 계약의 메커니즘이다.

## API와의 관계

**API(Application Programming Interface)**는 소스코드 수준의 인터페이스 규약이다. "이 함수는 `const char*`를 받아서 `int`를 반환한다"처럼, 프로그래머가 코드를 작성할 때 의존하는 계약이다. REST API의 엔드포인트 스펙, 라이브러리의 헤더 파일, Python 모듈의 public 함수 시그니처 등이 모두 API에 해당한다.

ABI는 이 API를 **컴파일한 결과물**에 대한 규약이다. 같은 API라도 컴파일러 버전, 최적화 옵션, 타깃 아키텍처에 따라 다른 ABI가 나올 수 있다.

| | API | ABI |
|---|---|---|
| 수준 | 소스코드 | 바이너리(컴파일 후) |
| 적용 범위 | 모든 인터페이스 (REST, 라이브러리, 프로토콜 등) | 네이티브 바이너리 간 인터페이스에 한정 |
| 호환 시 | **재컴파일하면** 동작 | **재컴파일 없이** `.so` 교체로 동작 |
| 보장 수준 | source-level | binary-level |

ABI와 API는 일반적으로 별개 차원이다. 한쪽이 다른 쪽을 함의하지 않는다는 뜻이다. 가장 자주 만나는 케이스는 **API 호환이지만 ABI 비호환**인 경우다. 예를 들어 `struct ncclComm`의 기존 필드 사이에 새 필드를 끼워넣으면, 기존 바이너리가 `comm->rank`를 읽으려 했던 오프셋에 다른 값이 있게 된다. 함수 시그니처는 그대로이므로 소스를 다시 컴파일하면 동작하지만(API 호환), `.so`만 교체하면 크래시한다(ABI 비호환). 실무적으로 soname을 유지하는 라이브러리는 API와 ABI 양쪽을 다 깨지 않으려고 노력하지만, 공유 라이브러리에서 soname이 일차적으로 보장하려는 것은 바이너리 쪽(ABI)이다.

<details markdown="1">
<summary>반대 방향: API 비호환이지만 ABI 호환인 경우</summary>

이 카테고리는 실무에서 드물지만 가능하긴 하다. 예를 들어:

- **함수의 default 값을 제거** (파라미터 타입은 유지): `void foo(int x = 0)` → `void foo(int x)`. 기존 `foo()` 호출은 컴파일이 깨지지만, mangled symbol(`_Z3fooi`)은 동일하므로 ABI는 유지된다
- **`[[deprecated]]` attribute 추가**: 컴파일러가 경고를 띄워 코드 흐름은 영향을 받지만 바이너리 인터페이스는 그대로다
- **헤더에서만 쓰이는 typedef 이름 변경** (같은 underlying 타입을 가리키는 경우): 소스에는 영향이 가도 컴파일된 결과는 동일하다

참고로 default 값이 *있는* 파라미터를 추가하는 건(`void foo(int)` → `void foo(int, int = 0)`) 이 카테고리에 속하지 않는다. Itanium C++ ABI는 mangled name에 default 값은 포함하지 않지만 파라미터 타입 리스트는 포함하므로, `_Z3fooi`와 `_Z3fooii`는 서로 다른 심볼이다. 그러면서 기존 `foo(5)` 호출 코드는 그대로 컴파일되므로, 오히려 "API 호환 / ABI 비호환" 쪽에 가깝다.

</details>

## soname이 보장하는 계약

- **라이브러리 쪽(NCCL 등)의 약속**: "같은 soname(`libnccl.so.2`) 안에서는 ABI를 깨지 않겠다." 기존 함수의 시그니처를 바꾸지 않고, 구조체의 메모리 레이아웃(필드 순서, 크기, 정렬)을 변경하지 않는다. 2.26.2에서 2.29.7로 올라가도 기존 심볼이 동일한 방식으로 동작한다
- **소비자 쪽(PyTorch 등)의 신뢰**: `NEEDED libnccl.so.2`만 기록하면, 런타임에 2.26.2든 2.29.7이든 ABI 호환을 신뢰할 수 있다. 소비자가 minor 버전까지 확인할 필요가 없다
- **major 버전이 바뀌면(`.so.3`)**: 라이브러리 관리자 관례상 ABI 비호환 신호. `.so.2`를 찾는 프로그램은 파일 이름이 다른 `.so.3`을 로드하지 않으므로 "not found" 에러로 깔끔하게 실패한다.

여기서 동적 링커가 하는 일은 ABI 자체를 검사하는 게 아니라, soname을 이름으로 분리해서 비호환 로드를 사실상 차단하는 것이다. 만약 soname 관례 없이 `libnccl.so`만 사용했다면, 라이브러리 업그레이드 시 ABI 비호환인 새 버전이 아무 경고 없이 로드되어 segfault이나 데이터 손상으로 이어질 수 있다. soname은 이런 의도치 않은 비호환 로드를 구조적으로 차단하는 설계다.

같은 "not found" 메시지가 `ldconfig` 캐시 미갱신 같은 다른 원인에서도 동일하게 나타날 수 있으므로, ABI 비호환인지 캐시 미갱신인지 구별하려면 `readelf -d`로 ELF 안의 `DT_NEEDED`와 실제 `.so` 위치를 함께 확인해야 한다.

## ABI가 보장하는 것과 보장하지 않는 것

ABI 호환은 "함수 호출이 깨지지 않는다"(시그니처, 메모리 레이아웃 유지)를 보장하지, "기능적 동작이 동일하다"를 보장하지는 않는다. 예를 들어 NCCL 2.26.2에서 특정 allreduce 알고리즘이 ring이었는데 2.29.7에서 tree로 바뀔 수 있다. ABI는 깨지지 않지만 성능 특성이 달라질 수 있는 경우다.

정리하면, soname/ABI는 가장 치명적인 문제(비호환 로드)를 시스템 수준에서 막아주는 최소한의 장치이고, 그 안의 세부 변화는 사람이 관리해야 하는 영역이다.

| 계층 | 보호 대상 | 메커니즘 |
|------|----------|---------|
| soname + 동적 링커 | ABI 비호환 라이브러리 로드 차단 | 시스템이 강제 (단, soname 문자열 매칭만 — ABI 자체를 검사하지는 않음) |
| ABI 관례 | major 안에서 호출 인터페이스 유지 | 라이브러리 관리자의 약속 |
| 릴리스 노트 / 테스트 | 기능적 동작 변화 감지 | 소비자가 확인 |

> 위로 갈수록 시스템이 강제, 아래로 갈수록 사람이 관리한다.

이 관례 덕분에 같은 soname이 시스템마다 다른 minor 버전을 가리켜도 안전하다. 서버 A의 `libnccl.so.2`가 `libnccl.so.2.26.2`를, 서버 B의 `libnccl.so.2`가 `libnccl.so.2.29.7`을 가리켜도 major가 같으므로 `libnccl.so.2`를 요구하는 프로그램은 양쪽에서 정상 동작한다.

<br>

# 같은 soname의 복수 존재

하나의 디렉토리 안에서 `libnccl.so.2`는 하나뿐이다 (파일명은 디렉토리 내에서 유니크). 그러나 **서로 다른 디렉토리**에 같은 soname의 바이너리가 별개로 존재할 수 있다.

같은 라이브러리를 **서로 다른 배포 채널**로 설치하면, 각 채널의 설치 경로에 같은 soname의 `.so`가 생긴다. Python이 `/usr/bin/python3`(apt)과 `/home/user/anaconda3/bin/python3`(conda)에 별개로 존재할 수 있는 것과 같은 구조다.

예를 들어 Dockerfile에서 `apt install libnccl2`로 시스템 NCCL을 설치하고, 이후 `pip install torch`가 `nvidia-nccl-cu12`를 자동으로 가져오면, 두 경로에 `libnccl.so.2`가 각각 존재하게 된다.

```text
/usr/lib/x86_64-linux-gnu/
  libnccl.so.2 → libnccl.so.2.26.2      ← 시스템 NCCL (apt)

site-packages/nvidia/nccl/lib/
  libnccl.so.2 → libnccl.so.2.26.2      ← 번들 NCCL (pip)
```

이 두 파일은 파일명(`libnccl.so.2.26.2`), NCCL 버전(2.26.2), soname(`libnccl.so.2`)이 모두 동일할 수 있다.

그러나 외형적 메타데이터가 같다고 같은 파일은 아니다. 두 파일은 서로 다른 디렉토리에 위치하며, 디스크 상으로는 별개 inode에 저장된 독립된 바이너리다. 같은 soname을 가진다는 것은 "동적 링커가 같은 이름으로 매칭할 수 있다"는 의미일 뿐, 실제로 어느 쪽이 로드될지는 탐색 경로가 결정한다.

내부 빌드 옵션도 다를 수 있다. 예를 들어 apt 판은 CUDA 12.8 toolkit으로, pip 판은 CUDA 12.2로 빌드되어 있는 식으로 바이너리 안에 박힌 빌드 CUDA 버전이 달라질 수 있다. 이 차이는 `strings libnccl.so.2 | grep "NCCL version"` 등으로 바이너리 내부를 열어 봐야 드러난다.

두 파일이 공존할 때, **어느 쪽이 실제로 로드되는지는 동적 링커의 탐색 순서에 의해 결정된다**. 이 구조가 왜 생겼는지와 어떻게 로드되는지를 이어서 살펴본다.

<br>

# 동적 링커의 탐색 순서

탐색 순서를 다루기 전에 "링커"가 가리키는 두 프로그램을 구분해야 한다. **정적 링커**(GNU `ld`, `lld` 등)는 빌드 타임에 오브젝트 파일을 결합하여 최종 바이너리를 만들면서 RPATH/RUNPATH를 기록하는 도구이고, **동적 링커**(`ld-linux-x86-64.so.2`)는 런타임에 `DT_NEEDED`에 기록된 `.so`를 찾아 메모리에 로드하는 도구다. 정적 링커가 "어디서 찾아라"를 기록하고, 동적 링커가 그 기록을 읽어서 실제로 찾는다.

<details markdown="1">
<summary>"정적 링커"라는 이름이 헷갈리는 이유</summary>

"정적 링커"는 "정적 링크만 하는 링커"가 아니라 "빌드 타임(정적 시점)에 동작하는 링커"라는 뜻이다. 같은 정적 링커가 두 가지 일을 모두 수행한다:

- `.a`(정적 라이브러리)가 지정되면 그 안의 오브젝트 코드를 바이너리에 직접 복사한다 (정적 링크)
- `.so`(공유 라이브러리)가 지정되면 soname만 `DT_NEEDED`에 기록해 두고, 실제 로드는 런타임의 동적 링커에게 맡긴다 (동적 링크)

즉 "정적/동적 링크"는 라이브러리를 결합하는 **방식**의 구분이고, "정적/동적 링커"는 동작하는 **시점**(빌드 타임 vs 런타임)의 구분이다.

</details>

프로그램이 `libnccl.so.2`를 필요로 한다는 것은 `DT_NEEDED` 태그에 그 soname이 기록되어 있다는 의미다. 실행 시 동적 링커가 이 이름에 매칭되는 `.so`를 탐색한다. 모든 단계보다 먼저 `LD_PRELOAD`가 적용되고, 그다음 분기는 바이너리에 어떤 하드코딩 태그(`DT_RPATH` / `DT_RUNPATH`)가 박혀 있는지에 달려 있다. 두 태그는 ELF에 동시에 들어 있을 수 있지만, RUNPATH가 있으면 RPATH는 무시되므로 실제로는 한 번에 한 케이스만 동작한다.

**RPATH 환경 (`DT_RPATH`만 있고 `DT_RUNPATH`는 없음)**:

```text
LD_PRELOAD → DT_RPATH → LD_LIBRARY_PATH → ldconfig 캐시 → 기본 경로
```

**RUNPATH 환경 (`DT_RUNPATH` 있음, `DT_RPATH`는 같이 있어도 무시)**:

```text
LD_PRELOAD → LD_LIBRARY_PATH → DT_RUNPATH → ldconfig 캐시 → 기본 경로
```

핵심적인 차이는 두 하드코딩 태그(`DT_RPATH` / `DT_RUNPATH`)가 **LD_LIBRARY_PATH보다 먼저인지 나중인지**다.

| 태그 | LD_LIBRARY_PATH 대비 | 환경변수로 덮어쓰기 |
|------|---------------------|-------------------|
| `DT_RPATH` | **먼저** 탐색됨 | 불가 |
| `DT_RUNPATH` | **나중에** 탐색됨 | 가능 |

## 각 단계의 의미

본격적인 탐색 단계를 정리하기 전에, 모든 단계보다 먼저 적용되는 0단계를 따로 떼어 둔다.

**0단계 — `LD_PRELOAD` / `/etc/ld.so.preload`**: 그 어떤 단계보다도 먼저 적용된다. 환경변수(`LD_PRELOAD`) 또는 시스템 파일(`/etc/ld.so.preload`)로 특정 `.so`를 강제 주입할 수 있어, 디버깅이나 심볼 가로채기에 쓰인다.

<details markdown="1">
<summary>secure-execution 모드에서의 제약</summary>

setuid/sgid 바이너리 등 secure-execution 모드에서는 `LD_PRELOAD`와 `LD_LIBRARY_PATH`가 제한된다.

- `LD_PRELOAD`: 슬래시를 포함한 경로는 무시되고, 슬래시 없는 이름조차 표준 디렉토리의 set-user-ID 비트가 켜진 객체로 한정되므로 사실상 차단된다
- `LD_LIBRARY_PATH`: secure-execution에서 완전히 무시된다
- `/etc/ld.so.preload`: root 권한 시스템 전역 설정이므로 secure-execution과 무관하게 동작한다

디버깅 용도라면 환경변수 `LD_PRELOAD`를 셸 단위로 쓰는 편이 안전하다. 상세는 ld.so(8)의 "Secure-execution mode" 참조.

</details>

본격 탐색은 그다음부터 시작된다.

1. **`DT_RPATH`**: 바이너리를 빌드할 때 `-rpath`로 경로를 `.so` 안에 하드코딩한 것. RPATH에 번들 라이브러리 경로가 기록되어 있으면, 해당 번들이 강제 로드된다. `LD_LIBRARY_PATH`보다 먼저 탐색되므로, `LD_LIBRARY_PATH`만으로는 우회 불가 (`LD_PRELOAD`는 가능)
2. **`LD_LIBRARY_PATH`**: 환경변수로 `.so` 탐색 경로를 추가. RUNPATH 환경에서는 RUNPATH보다 우선이지만, **RPATH 환경에서는 RPATH 다음**. secure-execution 모드에서는 무시
3. **`DT_RUNPATH`**: RPATH와 같은 하드코딩 경로이나, `LD_LIBRARY_PATH`보다 후순위. ELF 안에 `DT_RPATH`와 `DT_RUNPATH`가 동시에 들어 있을 수 있지만, **`DT_RUNPATH`가 있으면 `DT_RPATH`는 무시된다** (ld.so(8) 명시 동작)
4. **`ldconfig` 캐시**: apt로 설치된 `.so`들이 여기 등록된다. `/etc/ld.so.conf.d/`에 경로를 추가하고 `ldconfig`를 실행하면 캐시에 반영된다
5. **기본 경로**: `/usr/lib/x86_64-linux-gnu` 등

어떤 태그가 기록되는지는 정적 링커의 설정에 달려 있다. GNU `ld`는 `--enable-new-dtags`가 켜져 있으면 RUNPATH를, `--disable-new-dtags`이면 RPATH만 기록한다. 다른 정적 링커(lld/gold/mold)는 자체 기본값을 가지고, 배포판/툴체인에 따라서도 기본이 갈리므로 바이너리마다 `readelf -d`로 직접 확인하는 편이 안전하다. 트러블슈팅 당시 확인했을 때 PyTorch pip wheel(torch 2.x + cu12x)은 RPATH로 빌드되어 있어, `LD_LIBRARY_PATH`만으로는 번들 `.so`를 교체할 수 없었다.

## RPATH vs RUNPATH: 우선순위 역전

두 태그의 주된 실무 차이는 `LD_LIBRARY_PATH`와의 순서다. `DT_RPATH`는 `LD_LIBRARY_PATH`보다 우선하여 빌드 후 환경변수로 우회할 수 없다. 이 점이 개발/디버깅 관점에서 불편함으로 지적되었고(베타 빌드로 잠깐 교체해서 검증하거나, 디버그 심볼 포함 빌드로 임시 교체하거나, hotfix 라이브러리를 적용하는 시나리오가 막힌다), 이를 해결하기 위해 환경변수가 우선하는 `DT_RUNPATH`가 도입되었다 (GNU `ld`의 `--enable-new-dtags` 옵션으로 활성화, 2000년대 초반에 추가됨. 정확한 도입 버전은 binutils ChangeLog와 `ld`의 NEWS 파일에서 확인할 수 있다). 

`DT_RPATH`는 deprecated이지만 아직 동작하며, 이 순서 차이가 실무에서 큰 영향을 미친다.

<details markdown="1">
<summary>미세한 차이 하나 더 — transitive 의존성</summary>

먼저 용어부터 정리한다. 어떤 바이너리 A가 자기 `NEEDED`에 적은 `.so`(B)는 A의 **직접 의존성**이고, B가 다시 자기 `NEEDED`에 적은 `.so`(C)는 A 입장에서 **간접(transitive) 의존성**이다. 의존 관계가 `A → B → C → ...`로 트리/그래프로 이어진다고 보면 된다.

`DT_RPATH`와 `DT_RUNPATH`는 이 의존 트리를 따라 내려갈 때의 적용 범위가 다르다.

- **`DT_RPATH`는 transitive에도 적용된다**: A의 RPATH가 `/opt/myorg/lib`라면, A가 로드한 B가 다시 C를 찾을 때도 A의 RPATH가 탐색 경로에 들어간다. A의 빌드 시 결정이 자기 직접 의존성을 넘어 간접 의존성의 해석에까지 영향을 미친다는 뜻이고, B 입장에서 보면 "내가 의도하지 않은 경로"에서 C가 로드되는 셈이다.
- **`DT_RUNPATH`는 자기 `NEEDED`에만 적용된다**: A의 RUNPATH는 A가 직접 로드하는 B를 찾을 때만 쓰이고, B가 다시 C를 찾을 때는 적용되지 않는다. C는 B 자신의 RUNPATH나 시스템 경로(`ldconfig` 캐시)에서 찾는다.

이 좁힘은 RPATH의 "신뢰 전파(trust propagation)" 범위가 너무 넓다는 문제를 정돈하기 위한 설계로 이해할 수 있다. 동시에 실무에서는 부작용으로 나타나는데, "번들 구성이 일부만 격리된다"는 게 바로 이 부작용이다. 예를 들어 어떤 wheel이 RUNPATH로 자기 번들 라이브러리 A를 가져오더라도, A가 다시 의존하는 라이브러리는 RUNPATH 적용 대상이 아니므로 시스템 경로의 다른 버전이 로드될 수 있다.

</details>

**RPATH 환경 (환경변수로 교체 불가)**:

```text
DT_RPATH: $ORIGIN/../../nvidia/nccl/lib/
  → 여기서 libnccl.so.2를 찾으면 바로 로드. 끝.
  → LD_LIBRARY_PATH에 뭘 넣든 무시됨
```

**RUNPATH 환경 (환경변수로 교체 가능)**:

```text
LD_LIBRARY_PATH=/custom/nccl/lib
  → 여기서 먼저 탐색
  → 못 찾으면 DT_RUNPATH → ldconfig → 기본 경로
```

`$ORIGIN`은 동적 링커가 제공하는 특수 토큰으로, **현재 `.so` 파일이 위치한 디렉토리**를 가리킨다. `$ORIGIN/../../nvidia/nccl/lib/`(트러블슈팅 당시 확인한 wheel의 RPATH 예시 — wheel 버전에 따라 깊이가 다를 수 있다)는 "이 `.so`로부터 두 단계 상위 디렉토리의 `nvidia/nccl/lib/`"를 의미한다. 상대 경로로 기록하면 설치 위치가 바뀌어도 번들 라이브러리를 찾을 수 있어, pip wheel 같은 relocatable 배포에서 활용된다. 다만 이 편의성이 곧 우회 불가는 아니다 — `$ORIGIN` 자체는 RPATH/RUNPATH 모두에서 해석되므로 편의성과 우회 불가는 별개 축이다. PyTorch pip wheel은 RPATH와 `$ORIGIN`을 함께 쓰기 때문에 `LD_LIBRARY_PATH`로 우회할 수 없는 것이지, `$ORIGIN` 자체 때문은 아니다.

RPATH 환경에서 번들 `.so`를 교체하려면 아래 세 가지 중 하나를 택해야 하는데, 각각 대가가 있다.

| 방법 | 장점 | 비용 |
|------|------|------|
| 번들 `.so` 제거 | 환경변수 없이 시스템 NCCL로 폴백 | wheel RECORD 무결성 깨짐, 재설치 시 원복 |
| `patchelf --set-rpath` | 영구적으로 우선순위 변경 | wheel 무결성 깨짐, 재설치 시 원복 |
| `LD_PRELOAD` | wheel 손대지 않음 | secure-execution 바이너리에는 적용 불가 |

위 방법들은 모두 wheel 단위의 영구 해결책이 아니다. 운영 환경에서는 NCCL을 맞춘 base 이미지로 교체하는 편이 정공법이다 — [NCCL 트러블슈팅]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})에서 실제 채택한 해결책도 이미지 교체였다.

<br>

# 정적 링크 vs 동적 링크

## NEEDED 헤더

`.so` 파일에는 "나를 로드하려면 이 `.so`들도 함께 로드해야 한다"는 목록(`DT_NEEDED`)이 기록되어 있다.

```bash
$ readelf -d libnccl.so.2 | grep NEEDED
  (NEEDED)  libpthread.so.0
  (NEEDED)  librt.so.1
  (NEEDED)  libdl.so.2
  (NEEDED)  libstdc++.so.6
  (NEEDED)  libm.so.6
  (NEEDED)  libgcc_s.so.1
  (NEEDED)  libc.so.6
  (NEEDED)  ld-linux-x86-64.so.2
```

위 NEEDED는 모두 시스템 표준 라이브러리(C 런타임, pthread, 동적 링커 자체)다. NCCL이 직접 호출하는 GPU 관련 라이브러리는 한 줄도 보이지 않는다.

NCCL은 GPU 통신 라이브러리이므로 당연히 CUDA에 의존하지만, **위 NEEDED 목록에는 `libcudart.so` 같은 CUDA runtime이 보이지 않는다**. 가능한 이유는 세 가지다:

- (a) `cudart_static.a`로 CUDA runtime을 정적 링크한 경우
- (b) 일부 의존을 `dlopen`으로 늦게 로드하는 경우
- (c) 실제로는 CUDA Driver API(`libcuda.so.1`)만 사용하고 그조차 `dlopen`하는 경우

NCCL 공식 빌드 가이드의 기본값이 `cudart_static`이라 (a)가 가장 흔하지만, NEEDED 부재 한 가지로 정적 링크를 단정하기보다는 빌드 매뉴얼이나 `strings libnccl.so.2 | grep cudart` 같은 positive evidence로 확인하는 편이 안전하다. 더 직접적으로는 `nm -D libnccl.so.2 | grep -i cuda`로 동적 심볼 종류를 보는 방법이 있다. NEEDED에 `libcudart.so`가 없는데 `cudart_*` 심볼이 `T`/`W`(정의됨)로 잡히면 정적 링크의 강한 증거이고, `U`(undefined)로 잡히는데도 NEEDED에 보이지 않는다면 `dlopen` 경로일 가능성이 크다.

## 동적 링크 vs 정적 링크 비교

| | 동적 링크 | 정적 링크 |
|---|---|---|
| 방식 | `NEEDED`에 soname을 기록. 런타임에 동적 링커가 찾아서 로드 | 빌드 시 `.a`(정적 라이브러리)의 코드를 바이너리에 직접 복사 |
| NEEDED에 나옴? | 나옴 | 안 나옴 |
| 버전 교체 | 의존 `.so` 파일만 바꾸면 됨 (ABI 호환 범위 내) | 정적으로 머금은 의존을 바꾸려면 그 의존을 포함한 상위 바이너리(`.so` 또는 실행 파일)를 재빌드해야 함 |
| 의존 환경 | 런타임에 해당 `.so`가 시스템에 존재해야 함 | 외부 `.so` 불필요 (self-contained) |

정적 링크된 코드 자체는 soname 체계와 무관하다 — 빌드 시 `.a`(정적 라이브러리)의 코드가 바이너리 안에 복사되므로, 그 부분은 런타임에 외부 `.so`를 탐색할 일이 없다. 단, 정적 링크를 포함한 바이너리도 다른 동적 라이브러리(libc, libpthread 등)에는 여전히 의존할 수 있고, 그쪽은 NEEDED에 남는다 — 위 readelf 예시도 같은 경우다. NCCL pip 번들도 일반적으로 CUDA runtime은 정적, glibc 계열은 동적으로 남는 구성이 흔하다. 본인 환경에서는 `readelf -d $(python -c "import nvidia.nccl, os; print(os.path.dirname(nvidia.nccl.__file__) + '/lib/libnccl.so.2')")` 같은 식으로 직접 확인하는 편이 안전하다.

## 왜 정적 링크인가, 그리고 그 대가

정적 링크의 동기는 pip 배포 모델과의 정합성이다. pip으로 배포할 때는 대상 시스템에 어떤 CUDA가 설치되어 있는지 보장할 수 없다 (`pip install torch`를 실행하는 환경에 `libcudart.so`가 아예 없을 수도 있음). 정적 링크하면 GPU 가속 라이브러리 측면에서는 "`.so` 하나만 있으면 동작한다"에 가까운 자급력을 얻는다 (호스트 GPU 드라이버(`libcuda.so.1`)에는 여전히 의존하므로 엄밀히 self-contained 바이너리는 아니다).

대가는 경직성이다. 동적 링크였다면 시스템에 설치된 CUDA runtime을 자동으로 사용하므로, Dockerfile에서 CUDA 버전만 맞추면 같은 형태의 NCCL 버전 불일치 이슈로는 재현되지 않았을 것이다. 그러나 정적 링크는 "pip만으로 GPU 가속 환경이 거의 자급"을 가능하게 하는 설계이며, 이 편의성의 대가로 **내부에 CUDA 버전이 고정되는 경직성**이 생긴다.

| 링크 방식 | 장점 | 대가 |
|-----------|------|------|
| 동적 | 시스템 `.so` 교체만으로 업그레이드 가능 | 런타임 환경에 해당 `.so`가 반드시 있어야 함 |
| 정적 | 외부 의존 없이 self-contained | 내부 고정된 버전을 외부에서 교체 불가 |

> 정적 링크된 NCCL은 CUDA 버전을 `.so` 안에 고정한다. 외부에서 보이는 OS의 CUDA 라벨과 라이브러리 내부의 CUDA는 다른 시계열을 가질 수 있다 — 본문 도입부의 NCCL 트러블슈팅이 부딪힌 구조적 원인 중 한 축이다.

<br>

# NVIDIA pip .so 배포 전략

## 시스템 경로 vs pip 경로

Linux `.so`는 다양한 경로에 존재한다. GPU/CUDA 계열을 기준으로 두 범주로 나뉜다.

**"시스템" `.so` — apt/yum 등 OS 패키지 매니저로 설치**:

```text
/usr/lib/x86_64-linux-gnu/libnccl.so.2        ← 시스템 NCCL
/usr/local/cuda-12.8/lib64/libcudart.so.12     ← CUDA toolkit (base 이미지에 포함)
/usr/lib/x86_64-linux-gnu/libcuda.so.1         ← GPU 드라이버 (호스트에서 주입)
```

- `/usr/lib/` 계열은 OS가 관리하는 표준 라이브러리 경로
- `/usr/local/cuda-*/lib64/`는 NVIDIA CUDA toolkit의 관례적 설치 경로
- `ldconfig`가 이 경로들을 스캔해서 캐시를 만든다

**"pip" `.so` — Python wheel에 포함된 네이티브 라이브러리**:

```text
site-packages/nvidia/nccl/lib/libnccl.so.2     ← pip install nvidia-nccl-cu12
site-packages/nvidia/cublas/lib/libcublas.so.12 ← pip install nvidia-cublas-cu12
site-packages/torch/lib/libtorch_cuda.so        ← pip install torch
```

`site-packages`에 `.so`가 있는 것 자체는 새로운 일이 아니다 — Python C 확장은 원래 `.so`로 컴파일된다. NVIDIA가 한 것은 기존에 apt/yum으로만 설치하던 **독립 시스템 라이브러리**(libnccl, libcublas, libcudart 등)를 pip 패키지로 배포하기 시작한 것이다 (2022~2023년경 공식화). `pip install torch`만으로 CUDA 런타임까지 전부 딸려오는 "userspace-level self-contained GPU 환경"을 만들기 위한 전략이었고(호스트 GPU 드라이버는 여전히 별도), 그 결과 시스템 경로(`/usr/lib/`)와 pip 경로(`site-packages/`)에 **같은 라이브러리가 이중으로 존재하는 구조**가 굳어졌다.

## 이 구조의 의미

- **apt 없이도 GPU 라이브러리를 설치 가능**: `pip install torch`만으로 CUDA runtime, NCCL, cuBLAS 등이 전부 딸려온다
- **Python 환경별 격리**: 시스템 NCCL은 모든 프로세스가 공유하지만, pip NCCL은 해당 Python 환경에만 영향을 준다
- **버전 독립성**: 시스템에 CUDA 12.8용 NCCL이 설치되어 있어도, pip으로 설치된 NCCL(CUDA 12.2 빌드)이 별개로 존재할 수 있다

이것이 "두 개의 NCCL이 공존할 수 있는" 구조적 원인이다. 시스템 NCCL(`/usr/lib/`)과 PyTorch 번들 NCCL(`site-packages/nvidia/nccl/lib/`)은 물리적으로 다른 파일이고, 빌드된 CUDA 버전도 다를 수 있다.

## 컨테이너 환경에서의 의미

[컨테이너 장치 주입]({% post_url 2026-02-02-CS-Container-Device-Injection %})에서 다뤘듯이, nvidia-container-toolkit은 주로 GPU 드라이버 라이브러리(`libcuda.so.1`, `libnvidia-ml.so.1` 등)와 디바이스 파일(`/dev/nvidia*`)을 주입하고, 부수적으로 `nvidia-smi`, `nvidia-debugdump` 같은 일부 드라이버 유틸리티 바이너리도 마운트한다 (정확한 범위는 CDI 모드와 legacy 모드에 따라 다르다). 핵심은 호스트의 CUDA toolkit, NCCL, cuDNN 같은 userspace 라이브러리는 주입되지 않는다는 점이다. 따라서 컨테이너 안에서 사용하는 NCCL은 전적으로 이미지 빌드 시점에 결정된다.

컨테이너 환경에서는 이미지 빌드 시점에 userspace `.so`(NCCL, cuDNN, CUDA toolkit 등) 구성이 확정되고, 그 이미지를 쓰는 모든 Pod이 동일한 userspace 구성을 갖는다. 단, 호스트가 주입하는 `libcuda.so.1`은 노드별 드라이버 버전에 따라 다를 수 있고, 같은 이미지를 쓰더라도 GPU 모델이 다른 노드에 스케줄되면 fatbin 호환성은 별도로 검증해야 한다 — [GPU 호환성 게이트]({% post_url 2026-04-30-Dev-NCCL-GPU-Compat-CI-Runtime-Gate %}) 참고. "이미지 = 동일 구성"은 어디까지나 userspace 한정이다. 또한 컨테이너의 read-only rootfs에서는 `ldconfig` 실행 자체가 안 될 수 있으므로, 이미지 빌드 시점에 캐시를 확정짓는 편이 안전하다.

<br>

# 확인 도구

지금까지의 RPATH/RUNPATH/NEEDED 분기와 정적/동적 구성을 자기 환경에서 직접 확인하려면 다음 도구를 본다. 각각이 대응하는 본문 섹션도 함께 적었다.

| 도구 | 용도 | 예시 |
|------|------|------|
| `ldd` | 바이너리가 의존하는 `.so` 목록과 실제 해석 경로 확인 | `ldd /path/to/binary` |
| `readelf -d` | ELF Dynamic Section 태그 확인 (NEEDED, RPATH, RUNPATH, SONAME) | `readelf -d libnccl.so.2 \| grep -iE 'needed\|rpath\|runpath\|soname'` |
| `ldconfig -p` | ldconfig 캐시에 등록된 `.so` 목록 확인 | `ldconfig -p \| grep nccl` |
| `LD_DEBUG` | 동적 링커의 실시간 탐색 과정 추적 | `LD_DEBUG=libs python -c "import torch" 2>&1 \| grep nccl` |
| `patchelf` | RPATH/RUNPATH 수정, `.so` 의존성 변경 | `patchelf --print-rpath binary` |

```bash
# NCCL .so의 soname 확인
$ readelf -d libnccl.so.2.26.2 | grep SONAME
  0x000000000000000e (SONAME)  Library soname: [libnccl.so.2]

# 바이너리에 하드코딩된 탐색 경로 확인 (RPATH vs RUNPATH)
$ readelf -d $(python -c "import torch; print(torch._C.__file__)") | grep -iE 'rpath|runpath'

# 실제 어떤 .so가 로드되는지 확인
$ ldd $(python -c "import torch; print(torch._C.__file__)") | grep nccl
  libnccl.so.2 => /path/to/site-packages/nvidia/nccl/lib/libnccl.so.2

# 동적 링커의 탐색 과정을 실시간 추적
$ LD_DEBUG=libs python -c "import torch" 2>&1 | grep nccl
```

<br>

# 정리

Linux 공유 라이브러리의 구조를 한 문장으로 요약하면: **`.so`는 soname으로 ABI 호환 의사를 표현하고, 동적 링커는 정해진 순서대로 탐색하되 `DT_RPATH`가 박혀 있으면 `LD_LIBRARY_PATH`보다 먼저 본다.**

본문에서 다룬 네 축을 한 단락씩 다시 정리하면:

- **soname/ABI 계약**: soname은 라이브러리 관리자의 ABI 호환 약속이며, 동적 링커는 그 문자열 매칭만 강제한다. ABI 자체는 관리자의 관례(major bump = 비호환 신호)에 기댄다
- **탐색 순서**: `LD_PRELOAD`가 모든 단계보다 먼저 적용되고, 그다음 분기는 바이너리에 `DT_RPATH`가 박혔는지 `DT_RUNPATH`가 박혔는지에 따라 갈린다 (RPATH는 `LD_LIBRARY_PATH`보다 먼저, RUNPATH는 뒤에 탐색). 이 한 가지 순서 차이가 실무 트러블슈팅의 분기점이다
- **정적 vs 동적 링크**: 정적 링크는 "pip만으로 self-contained 환경" 같은 편의성을 주지만, 내부에 박힌 버전을 외부에서 교체할 수 없는 경직성과 묶여 있다
- **NVIDIA pip 배포의 이중 구조**: 시스템 경로(apt)와 pip 경로에 같은 soname의 `.so`가 별개 파일로 공존할 수 있고, 어느 쪽이 로드되는지는 위 탐색 순서가 결정한다

이 구조가 적용된 사례가 [NCCL 트러블슈팅]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})이다. 확인 시점의 PyTorch pip wheel이 `DT_RPATH`에 `$ORIGIN/../../nvidia/nccl/lib/` 같은 경로를 하드코딩하므로 번들 NCCL이 `LD_LIBRARY_PATH`보다 먼저 로드되고, 그 번들이 NCCL 2.26.2(CUDA 12.2 toolkit으로 빌드)라 fatbin에 Blackwell sm_120용 SASS가 들어 있지 않다 — 자세한 사슬은 [GPU 호환성 게이트]({% post_url 2026-04-30-Dev-NCCL-GPU-Compat-CI-Runtime-Gate %})에서 정리한다. Compat-Gate 글은 이 구조를 전제로, `.so` 안의 GPU 커널(fatbin)을 `cuobjdump`로 분석해 호환성을 사전 검증하는 방법이다.

<br>

# 참고 자료

- [Program Library HOWTO — Shared Libraries](https://tldp.org/HOWTO/Program-Library-HOWTO/shared-libraries.html) — Linux 공유 라이브러리 기초
- [ld.so(8) man page](https://man7.org/linux/man-pages/man8/ld.so.8.html) — 동적 링커의 탐색 순서 공식 문서
- [ldconfig(8) man page](https://man7.org/linux/man-pages/man8/ldconfig.8.html) — ldconfig 동작 원리
- [Drepper, "How To Write Shared Libraries"](https://www.akkadia.org/drepper/dsohowto.pdf) — ELF 공유 라이브러리 심화 (Ulrich Drepper, glibc maintainer)

<br>
