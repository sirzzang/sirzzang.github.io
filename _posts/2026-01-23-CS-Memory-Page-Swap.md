---
title:  "[CS] 메모리, 페이지, 스왑"
excerpt: "리눅스 메모리 관리의 기초 개념을 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Memory
  - Swap
  - Page
  - Linux
  - 메모리
  - 스왑
  - 페이지
---

<br>

# TL;DR

- **가상 메모리**: 프로세스에게 독립적 주소 공간 제공, MMU와 Page Table로 물리 메모리로 변환
- **페이지**: 4KB 단위의 메모리 관리 기본 단위 (Huge Pages는 2MB/1GB)
- **TLB**: Page Table 조회 결과를 캐싱하여 주소 변환 속도 향상
- **스왑**: 메모리 부족 시 Anonymous Page를 디스크로 대피시키는 메커니즘
- **Thrashing**: 스왑이 과도하게 발생하여 시스템이 거의 멈추는 상태
- **권장 설정**: 서버에서는 `vm.swappiness=1`, Kubernetes에서는 스왑 비활성화

<br>

# 개요

리눅스 시스템에서 메모리 관리는 성능과 안정성의 핵심이다. 이 글에서는 가상 메모리와 물리 메모리의 차이, 페이지의 개념, 스왑의 동작 원리를 살펴본다.

<br>

# 메모리

## 물리 메모리와 가상 메모리

리눅스는 **물리 메모리**와 **가상 메모리**를 구분하여 관리한다.

### 물리 메모리 (Physical Memory)

실제 RAM 하드웨어를 의미한다.

- 예: DDR4 8GB 메모리 칩
- 주소: `0x00000000` ~ `0x1FFFFFFFF` (실제 하드웨어 주소)
- 모든 프로세스가 공유

### 가상 메모리 (Virtual Memory)

프로세스가 보는 논리적 메모리 주소 공간이다.

- 예: 각 프로세스마다 갖는 독립적인 4GB 주소 공간
- 주소: `0x00000000` ~ `0xFFFFFFFF` (가상 주소)
- 각 프로세스마다 별도 공간

> **참고**: 4GB(2^32)는 32비트 시스템 기준이다. 64비트 시스템에서는 이론상 16EB(2^64)까지 가능하지만, 실제로는 커널/하드웨어 제약으로 128TB~256TB 정도를 사용한다. 현재 대부분의 64비트 시스템에서는 48비트 주소를 사용하여, 사용자 공간에서 약 **128TB**의 가상 주소 공간을 제공한다.

예를 들어 프로세스 A가 변수 `x`를 가상 주소 `0x1000`에 저장하고, 프로세스 B도 변수 `y`를 가상 주소 `0x1000`에 저장할 수 있다. 두 프로세스는 같은 가상 주소를 사용하지만, 서로의 존재를 알지 못하고 완전히 격리된다.

실제 물리 메모리에서는 이 주소들이 서로 다른 위치에 매핑된다. 프로세스 A의 `0x1000`은 물리 주소 `0x5000`에, 프로세스 B의 `0x1000`은 물리 주소 `0x8000`에 매핑되어 서로 다른 물리 메모리 영역을 사용한다.

이 매핑은 **운영체제(커널)**가 관리한다. 커널은 각 프로세스마다 별도의 Page Table을 생성하고, 프로세스가 메모리에 접근할 때마다 MMU가 이 테이블을 참조하여 가상 주소를 물리 주소로 변환한다. 프로세스는 이 과정을 전혀 인식하지 못한다.


<br>

## 가상 메모리의 필요성

물리 메모리에 직접 접근하면 여러 문제가 발생한다:

- **메모리 격리 불가**: 프로세스 A가 프로세스 B의 메모리에 접근 가능하여 보안 문제와 버그 시 시스템 전체 다운 위험
- **메모리 관리 어려움**: 프로세스마다 물리 주소를 수동 할당해야 하고, 메모리 파편화와 큰 프로그램 실행 불가 문제 발생
- **멀티태스킹 불가**: 여러 프로그램 동시 실행이 어려움

<br>

## 주소 변환

가상 메모리는 **주소 변환**을 통해 물리 메모리와 연결된다.

프로세스가 가상 주소 `0x1000`에 접근하면, CPU의 **MMU(Memory Management Unit)**가 **Page Table**을 확인하여 이를 물리 주소 `0x5000`으로 변환한다. 이후 실제 물리 메모리에서 데이터를 읽어 프로세스에 반환한다.

| 구성 요소 | 역할 |
|----------|------|
| **MMU** | 가상 주소를 물리 주소로 변환하는 CPU 내 하드웨어 |
| **Page Table** | 가상 주소와 물리 주소의 매핑 정보를 저장하는 자료구조 |
| **TLB (Translation Lookaside Buffer)** | Page Table 조회 결과를 캐싱하여 주소 변환 속도 향상 |

> **참고**: TLB는 최근 사용한 주소 변환 결과를 캐싱하여 성능을 높인다. TLB 미스가 발생하면 메모리에 있는 Page Table을 조회해야 하므로 성능이 저하된다.

<br>

## 메모리의 종류

리눅스 커널은 물리 메모리를 용도에 따라 다르게 분류하여 관리한다.

| 종류 | 설명 | 예시 |
|-----|------|------|
| **프로세스 메모리** | 프로세스가 사용하는 메모리 (Anonymous Page) | heap, stack, malloc 할당 영역 |
| **Page Cache** | 파일 I/O를 위한 디스크 캐시 (File-backed Page) | 읽은 파일 내용, mmap된 파일 |
| **Buffer** | 블록 장치 메타데이터 캐시 | 파일시스템 메타데이터, 디렉토리 정보 |
| **Shared Memory** | 프로세스 간 공유 메모리 | tmpfs, POSIX shm, System V shm |
| **Slab** | 커널 내부 자료구조 캐시 | inode, dentry, task_struct |

### Buffer vs. Cache
- **Buffer**: 블록 장치(디스크)의 메타데이터를 캐싱. 파일시스템의 구조 정보를 저장한다.
- **Cache (Page Cache)**: 파일의 실제 내용을 캐싱. 파일 읽기/쓰기 성능을 높인다.

> **참고**: Linux 2.4 이전에는 Buffer Cache와 Page Cache가 분리되어 있었으나, Linux 2.4 이후부터는 통합된 Page Cache로 관리된다. 현대 리눅스에서는 `free` 명령에서 `buff/cache`로 함께 표시된다.

**Shared Memory**는 프로세스 간 데이터 공유를 위해 사용된다. `tmpfs`(예: `/dev/shm`, `/run`)가 대표적이며, 메모리 기반 파일시스템으로 디스크 I/O 없이 빠른 데이터 공유가 가능하다.

<br>

## 메모리 오버커밋

### 오버커밋이란

**오버커밋(Overcommit)**이란 커널이 물리 메모리보다 더 많은 메모리 할당 요청을 허용하는 것이다.

프로세스가 메모리를 요청하면 커널은 **가상 주소 공간만 예약**하고 성공을 반환한다. 실제 물리 메모리는 프로세스가 해당 메모리에 **write할 때** 할당된다.

예를 들어 물리 RAM이 8GB인 시스템에서:

```
프로세스 A: malloc(4GB) → 커널: "OK" (가상 주소만 예약, 물리 메모리 0)
프로세스 B: malloc(4GB) → 커널: "OK" (가상 주소만 예약, 물리 메모리 0)
프로세스 C: malloc(4GB) → 커널: "OK" (가상 주소만 예약, 물리 메모리 0)

총 약속: 12GB, 실제 RAM: 8GB → 오버커밋 (over-commit)
```

이 방식 덕분에 많은 프로세스가 메모리를 "예약"만 하고 실제로는 일부만 사용하는 경우 효율적으로 운영할 수 있다. 하지만 모든 프로세스가 예약한 메모리를 실제로 사용하면 물리 메모리가 부족해져 OOM Killer가 발동한다.

### 커널 메모리 할당 시스템 콜

Linux 커널은 프로세스에게 메모리를 할당하기 위해 두 가지 주요 시스템 콜을 제공한다:

| 시스템 콜 | 동작 | 용도 |
|----------|------|------|
| `brk()` | 힙 영역의 끝(break) 위치를 조정 | 작은 메모리 할당 |
| `mmap()` | 가상 주소 공간에 새 영역을 매핑 | 큰 메모리 할당, 파일 매핑 |

> **참고**: glibc(GNU C Library)는 리눅스의 표준 C 라이브러리로, `malloc()` 등의 함수를 제공한다. glibc의 `malloc()`은 기본적으로 128KB 이하 요청은 `brk()`, 그 이상은 `mmap()`을 사용한다. 이 임계값은 `MMAP_THRESHOLD`로 조절할 수 있다.

오버커밋은 이 시스템 콜 수준에서 발생한다. 커널이 `brk()`나 `mmap()` 요청을 받으면 가상 주소 공간만 예약하고, 실제 물리 메모리는 나중에 할당한다.

### 프로그래밍 언어에서의 사용

모든 프로그래밍 언어는 결국 이 커널 시스템 콜을 사용하여 메모리를 할당한다:

| 언어 | 메모리 할당 방식 | 내부 동작 |
|-----|----------------|----------|
| C/C++ | `malloc()`, `calloc()`, `new` | glibc가 `brk()` 또는 `mmap()` 호출 |
| Python | 객체 생성, 리스트 확장 | CPython 인터프리터가 `mmap()` 호출 |
| Java | `new Object()` | JVM이 `mmap()`으로 힙 영역 확보 |
| Go | `make()`, `new()` | Go 런타임이 `mmap()` 호출 |
| Rust | `Box::new()`, `Vec::new()` | 시스템 allocator가 `mmap()` 호출 |

따라서 오버커밋은 특정 언어의 동작이 아니라 **Linux 커널의 동작**이며, 어떤 언어를 사용하든 동일하게 적용된다.

### vm.overcommit_memory 설정

커널의 오버커밋 동작은 `vm.overcommit_memory` 파라미터로 제어할 수 있다.

| 값 | 이름 | 동작 |
|---|------|------|
| **0** (기본값) | 휴리스틱 | 커널이 "합리적인" 범위 내에서 오버커밋 허용. 너무 큰 요청은 거부 |
| **1** | 항상 허용 | 메모리 할당 요청을 무조건 성공시킴. 실제 사용 시 메모리 부족하면 OOM Killer 발동 |
| **2** | 엄격한 제한 | `swap + RAM × overcommit_ratio`까지만 허용. 초과하면 할당 실패 |

```bash
# 오버커밋 설정 확인
cat /proc/sys/vm/overcommit_memory

# 오버커밋 비율 확인 (mode=2일 때 사용)
cat /proc/sys/vm/overcommit_ratio
# 50 = swap + RAM의 50%까지만 할당 허용
```

메모리가 중요한 서버에서는 `overcommit_memory=2`로 설정하여 물리적으로 불가능한 메모리 할당을 사전에 차단할 수 있다. 반면, Kubernetes 환경에서는 kubelet이 `overcommit_memory=1`로 설정하여 컨테이너 메모리 할당의 유연성을 확보한다.

<br>

# 페이지

## 개념

**페이지(Page)**는 메모리를 관리하는 기본 단위다. 리눅스에서는 보통 **4KB** 단위를 사용한다.

물리 메모리는 4KB 크기의 페이지들로 연속적으로 나뉘어 관리된다. Page 0, Page 1, Page 2, ... 식으로 번호가 매겨진다.

프로세스의 메모리도 페이지 단위로 구성된다. 예를 들어 프로세스 A의 메모리는 Code 영역에 Page 0~1, Data 영역에 Page 2~3, Heap 영역에 Page 4~6, Stack 영역에 Page 7이 할당되는 식이다. 이렇게 페이지 단위로 관리하면 메모리 할당과 회수가 효율적이다.

<br>

## 페이지 관련 용어

### 페이지 이동

- **Page Out (페이지 아웃)**: 메모리 → 스왑 영역으로 이동 (swapping out, paging out)
- **Page In (페이지 인)**: 스왑 영역 → 메모리로 이동 (swapping in, paging in)

### 페이지 폴트 (Page Fault)

프로세스가 접근하려는 페이지가 메모리에 없을 때 CPU가 발생시키는 **예외(Exception)**다. 외부 장치에서 오는 하드웨어 인터럽트와 달리, 명령어 실행 중 CPU 내부에서 동기적으로 발생한다.

- **Minor Page Fault**: 페이지가 메모리 어딘가에 있어서 재매핑만 필요
- **Major Page Fault**: 페이지가 디스크(스왑 영역)에 있어서 디스크에서 읽어와야 함

Major Page Fault가 발생하면 프로세스는 **D state(Uninterruptible Sleep)** 상태가 되어 I/O 완료를 기다린다. `ps aux` 명령에서 `STAT` 컬럼이 `D`로 표시되는 프로세스는 디스크 I/O를 기다리는 중이다.

### 기타 용어

- **Page Cache**: 파일 I/O를 위한 디스크 캐시
- **Page Reclaim**: 메모리 압박 시 페이지를 회수하는 과정

<br>

## 페이지 용어를 사용하는 이유

왜 "메모리"가 아닌 "페이지" 단위로 표현할까?

1. **기술적 정확성**: 프로세스 전체가 아니라 **페이지 단위**로 스왑이 이루어짐
2. **OS 설계의 핵심 개념**: 가상 메모리 시스템은 페이징(paging) 기반으로 동작
3. **역사적 관습**: Unix 시절부터 사용된 OS 교과서 표준 용어

<br>

# 스왑

## 스왑이란

메모리가 부족하면 커널은 **Page Reclaim**을 수행하여 메모리를 확보한다. 이 과정에서:

- **File Page**: 파일에서 다시 읽을 수 있으므로 그냥 버림 (Dirty면 먼저 디스크에 씀)
- **Anonymous Page**: 파일이 없으므로 **스왑 영역**에 저장해야 함

**스왑(Swap)**은 이 중 Anonymous Page를 디스크의 스왑 영역으로 옮기는 것을 말한다.

예를 들어 8GB RAM 시스템에서 프로세스 A가 2GB, B가 3GB, C가 2GB를 사용하여 여유 메모리가 1GB뿐인 상황을 가정하자. 새로운 프로세스 D가 2GB를 요청하면 메모리가 부족하다. 이때 커널은 프로세스 A의 일부 페이지(오래 사용하지 않은 것)를 디스크의 스왑 영역으로 대피시켜 물리 메모리 공간을 확보하고, 프로세스 D가 시작할 수 있게 한다.

<br>

## 스왑 발생 과정

스왑은 다음과 같은 과정으로 발생한다:

1. **메모리 압박 감지**: 커널이 가용 메모리 부족을 감지한다.
2. **페이지 선택**: LRU 기반 알고리즘으로 오래 사용하지 않은 페이지를 선택한다.
3. **페이지 아웃**: 선택된 Anonymous Page를 스왑 영역에 저장하고, 물리 메모리에서 해제한다.
4. **Page Fault 발생**: 나중에 프로세스가 스왑된 페이지에 접근하면 Page Fault가 발생한다.
5. **페이지 인**: 커널이 스왑 영역에서 페이지를 읽어 물리 메모리로 복원한다.

<br>

## 페이지 선택 알고리즘

페이지 교체 알고리즘은 메모리가 부족할 때 어떤 페이지를 내보낼지 결정하는 방식이다. 대표적인 알고리즘으로는 아래와 같은 것들이 있다:

| 알고리즘 | 설명 |
|---------|------|
| **FIFO** | 가장 먼저 들어온 페이지 교체 |
| **LRU** | 가장 오래 사용 안 된 페이지 교체 |
| **LFU** | 가장 적게 사용된 페이지 교체 |
| **Clock (Second Chance)** | FIFO + 참조 비트로 개선 |

Linux 커널은 **LRU 기반의 근사 알고리즘(Approximate LRU)**을 사용한다. 순수 LRU는 모든 페이지 접근 순서를 추적해야 해서 오버헤드가 크기 때문에, Linux는 **Active/Inactive 두 개의 리스트**로 페이지를 관리하는 [Two-List LRU](https://www.kernel.org/doc/gorman/html/understand/understand013.html) 방식을 사용한다.

### 페이지 나이 (Age)

각 페이지는 마지막 접근 시간 정보를 가진다:

- **Young (최근 접근)**: 자주 사용 중 → 스왑 대상에서 제외
- **Old (오래 안 건드림)**: 안 쓰는 중 → 스왑 대상

예를 들어 프로세스 A가 Page 1(10초 전 접근), Page 2(5분 전 접근), Page 3(1초 전 접근)을 사용 중이라면, Page 2가 가장 오래 전에 접근되었으므로 스왑 대상이 된다. Page 1과 Page 3은 최근에 사용되었으므로 스왑 대상에서 제외된다.

### 페이지 종류와 회수 방식

커널은 페이지 종류에 따라 다른 방식으로 메모리를 회수한다:

| 종류 | 설명 | 회수 방식 | 회수 난이도 |
|-----|------|----------|-----------|
| **Clean File Page** | 파일과 연결되고 수정 안 된 페이지 | 그냥 버림 (필요시 파일에서 다시 읽음) | 쉬움 |
| **Dirty File Page** | 파일과 연결되어 있지만 수정된 페이지 | 디스크에 쓴 후 버림 | 중간 |
| **Anonymous Page** | 파일과 연결되지 않은 페이지 (heap, stack, malloc) | 스왑 영역에 저장 | 어려움 (스왑 필요) |

커널은 쉬운 페이지부터 회수를 시도하고, Anonymous Page는 스왑 영역이 있어야만 회수할 수 있다.

### 메모리 압박 감지 기준

커널이 메모리 회수를 시작하는 시점은 다음과 같다:

| 메커니즘 | 트리거 조건 | 동작 | 성능 영향 |
|---------|-----------|------|----------|
| **kswapd** | Available 메모리가 `min_free_kbytes` 이하 | 백그라운드에서 메모리 회수 | 낮음 (비동기) |
| **Direct Reclaim** | kswapd로 부족할 때 | 프로세스가 직접 메모리 회수 | 높음 (동기, 프로세스 블록됨) |

`min_free_kbytes`는 `/proc/sys/vm/min_free_kbytes`에서 확인할 수 있으며, 시스템이 최소한 확보하려는 여유 메모리 양이다. 이 값 이하로 떨어지면 kswapd가 깨어나 메모리 회수를 시작한다.

> **참고**: 실제 커널은 후술할 [기타 메모리 관련 커널 파라미터](#기타-메모리-관련-커널-파라미터) 중 `min_free_kbytes`를 기반으로 `watermark_min`, `watermark_low`, `watermark_high` 세 단계의 임계값을 계산한다. kswapd는 `watermark_low` 이하에서 깨어나고, `watermark_high`까지 회수한다. 위 설명은 단순화한 것이다.

<br>

## 스왑된 페이지의 복귀

중요한 점은 **스왑된 페이지는 자동으로 메모리로 돌아오지 않는다**는 것이다.

### 복귀하는 경우

1. **프로세스가 접근할 때**:
   - 스왑된 페이지에 접근 시도 → **Page Fault(예외)** 발생 (동기적)
   - 커널이 디스크 I/O 요청, 프로세스는 **D state(Uninterruptible Sleep)** 진입
   - 디스크 읽기 완료 → **하드웨어 인터럽트** 발생 (비동기적)
   - 프로세스 wake up, 페이지가 메모리에 로드된 상태로 실행 재개

2. **명시적 스왑 해제**: 스왑의 모든 내용을 RAM으로 강제 이동
   ```bash
   sudo swapoff -a && sudo swapon -a
   ```

3. **프로세스 종료**: 해당 프로세스의 모든 페이지 자동 정리

4. **시스템 재부팅**: 스왑 영역 포함 모든 메모리 초기화

### 복귀하지 않는 경우

프로세스가 해당 페이지를 접근하지 않으면 계속 스왑에 남아있다. 예를 들어 메모리 압박이 해소되어 RAM에 4GB 여유가 생겼더라도, 스왑에 저장된 2GB는 자동으로 메모리로 돌아오지 않는다. 프로세스가 해당 데이터를 다시 사용할 때만 Page Fault를 통해 메모리로 복귀한다.

<br>

## 스왑의 효과와 한계

### OOM 회피

스왑이 활성화되어 있으면 **OOM(Out Of Memory)** 상황을 회피할 수 있다:

- 물리 메모리 부족 → 안 쓰는 메모리 스왑으로 → 새로운 메모리 할당 → OOM 회피

### 한계

그렇다고, 스왑이 만능은 아니다:

- **스왑 공간 소진**: 스왑 영역도 다 차면 결국 OOM 발생
- **Thrashing**: 메모리와 스왑 간 계속 페이지 이동으로 시스템이 거의 멈춤
- **메모리 급증**: 스왑 속도가 메모리 할당 요청을 따라가지 못하면 OOM 발생

<br>

## 스왑이 OOM을 지연시키며 시스템을 마비시키는 경우: Thrashing

역설적이게도 스왑이 있어서 **시스템이 더 오래 고통받을** 수 있다. 대표적인 시나리오가 **Thrashing**이다. 스왑 없이는 빠르게 OOM으로 끝날 상황이, 스왑이 있으면 수십 분간 시스템을 마비시킨 후에야 OOM에 도달한다.

### 시나리오: Thrashing으로 인한 OOM

32GB RAM, 16GB 스왑, `swappiness=60`인 시스템에서 Thrashing이 발생하는 과정을 살펴보자.

**초기 상황**: 프로세스 A(8GB), B(10GB), C(10GB)가 실행 중이고, 물리 메모리 28GB 사용, 여유 4GB, 스왑은 비어있다.

**1단계 - 새 프로세스 시작**: 새 프로세스 D가 6GB를 요청한다. 28GB + 6GB = 34GB로 32GB를 초과하므로 메모리가 부족하다. 커널은 `swappiness=60`이므로 적극적으로 스왑을 사용하여 A, B의 페이지 4GB를 스왑 아웃하고, D를 시작시킨다.

**2단계 - 악순환 시작**: 문제는 스왑된 프로세스 A, B가 실제로 해당 데이터를 사용 중이라는 점이다. 프로세스 A가 스왑된 데이터에 접근하면 Page Fault가 발생하고, 디스크에서 페이지를 읽어온다. 이때 메모리 공간을 확보하기 위해 D의 페이지를 스왑 아웃한다. 이제 D가 자기 데이터에 접근하면 또 Page Fault가 발생하고, B의 페이지를 스왑 아웃한다. B도 마찬가지로... 이 과정이 무한 반복된다.

**3단계 - 성능 붕괴**: Thrashing 상태에서 모든 프로세스는 실제 작업(5%)보다 디스크 I/O 대기(90%)에 대부분의 시간을 소비한다. CPU는 I/O 대기 상태로 거의 놀고, 디스크는 100% 사용률로 포화 상태가 된다. 시스템 전체가 거의 멈춘 것처럼 느려진다.

**4단계 - 결국 OOM 발생**: 이 상태에서 새 프로세스 E가 2GB를 요청하면, 이미 모든 프로세스가 스왑 in/out 중이라 메모리 회수 속도가 할당 요청 속도를 따라가지 못한다. 수 분에서 수십 분이 지나 결국 OOM Killer가 발동하여 프로세스를 강제 종료한다.

### 스왑 유무에 따른 결과 비교

같은 메모리 부족 상황에서 스왑 유무에 따른 결과를 비교해보자.

| 구분 | 스왑 없음 (`swappiness=0`) | 스왑 있음 (`swappiness=60`) |
|-----|---------------------------|----------------------------|
| **과정** | 물리 메모리 부족 → 캐시 회수 → 부족 → 즉시 OOM | 기존 프로세스 스왑 아웃 → D 시작 → Thrashing → OOM |
| **기존 프로세스** | 정상 동작 계속 | 모든 프로세스 성능 저하 |
| **새 프로세스** | 시작 실패 | 일단 시작, 나중에 종료 |
| **소요 시간** | 즉시 (수 초) | 수 분 ~ 수십 분 |
| **특징** | **명확하고 빠른 실패** | **늦고, 고통스러운 실패** |

스왑이 없으면 새 프로세스 D만 시작 실패하고 기존 프로세스는 정상 동작한다. 스왑이 있으면 D를 억지로 시작시키지만, 결국 Thrashing으로 모든 프로세스가 느려지다가 OOM이 발생한다.

### 가능한 시나리오: CI/CD Runner

8GB RAM, `swappiness=60`인 CI/CD Runner Host에서 발생할 수 있는 시나리오다.

**정상 상황**: Runner 1(빌드 2GB)과 Runner 2(테스트 2GB)가 실행 중이고, 시스템이 3GB를 사용하여 총 7GB 사용, 여유 1GB 상태다.

**문제 상황**: PR이 동시에 올라와 Runner 3, 4, 5가 동시에 시작되었다. 각각 2GB씩 필요하여 총 13GB가 필요한데, 물리 메모리는 8GB뿐이다.

**예상 결과**: Thrashing이 발생하여 모든 빌드가 지연되고, 평소 5분 걸리던 빌드가 30분 이상 소요될 수 있다. 결국 일부 빌드는 OOM으로 실패할 수 있다. 이런 상황에서는 `swappiness=1`로 변경하고 Runner 동시 실행 수를 제한하는 것이 해결책이 될 수 있다.

### Thrashing 예방 전략

Thrashing은 발생하면 시스템을 마비시키므로, 사전 예방이 중요하다.

#### 1. 메모리 오버커밋 제어

[메모리 오버커밋](#메모리-오버커밋) 섹션에서 설명한 `vm.overcommit_memory` 설정을 활용한다. 메모리가 중요한 서버에서는 `overcommit_memory=2`로 설정하여 물리적으로 불가능한 메모리 할당을 사전에 차단할 수 있다.

#### 2. cgroup 메모리 제한

컨테이너나 프로세스 그룹별로 메모리 상한을 설정하면, 특정 그룹의 메모리 폭주가 전체 시스템에 영향을 주는 것을 방지할 수 있다.

```bash
# cgroup v1 메모리 제한 예시
echo 2G > /sys/fs/cgroup/memory/my-app/memory.limit_in_bytes

# cgroup v2 메모리 제한 예시
echo 2G > /sys/fs/cgroup/my-app/memory.max
```

컨테이너 환경(Docker, Kubernetes)에서는 이 기능이 기본 제공된다. OOM 발생 시 전체 시스템이 아닌 해당 컨테이너만 영향을 받는다.

#### 3. 모니터링 알람

Thrashing은 서서히 진행되므로, 조기 경보 시스템을 구축하면 예방할 수 있다.

**권장 알람 설정**:
- `available` 메모리 < 전체의 10% 시 경고
- `vmstat`의 `si/so` 값이 지속적으로 0이 아닐 때 경고
- Major Page Fault(`pgmajfault`)가 급증할 때 경고

<br>

# 커널 스왑 설정

## vm.swappiness

`vm.swappiness`는 Linux 커널이 메모리 회수 시 **Anonymous Page와 File Page 중 어느 쪽을 먼저 회수할지** 결정하는 파라미터다. 0~100 사이의 값을 가진다.

> **참고**: swappiness는 "스왑을 얼마나 적극적으로 사용할지"로 알려져 있지만, 정확히는 Anonymous Page(스왑 필요)와 File Page(스왑 불필요) 간의 회수 비율을 조절한다.

### 값의 의미

- **높은 값 (예: 60, 기본값)**: Anonymous Page 회수를 선호 → 스왑 활발
- **낮은 값 (예: 0~10)**: File Page 회수를 선호 → 스왑 최소화

### swappiness = 0 vs 1

커널 버전 3.5 이후(현재 대부분의 시스템):

| 값 | 동작 |
|---|------|
| **0** | OOM 발생 전까지 절대 스왑하지 않음. 물리 메모리와 캐시/버퍼를 모두 소진한 후 OOM Killer 발동 |
| **1** | 거의 스왑하지 않지만, 정말 급할 때 최소한의 스왑. OOM 회피 가능성 제공 |

**swappiness=0**은 메모리 압박 상황에서 스왑이라는 안전 밸브를 전혀 사용하지 못하게 하므로, 급격한 메모리 증가 시 즉시 OOM이 발생한다. 반면 **swappiness=1**은 극단적인 상황에서만 가장 덜 중요한 페이지를 스왑하여 OOM을 회피할 여지를 남긴다. 서버 환경에서는 `swappiness=1`이 현실적인 안전장치로 권장된다.

### swappiness 값별 동작 비교

| swappiness | Anonymous Page 회수 선호도 | File Page 회수 선호도 | 권장 환경 |
|-----------|---------------------------|---------------------|----------|
| 0         | 거의 없음 (OOM 직전)        | 최대                | 절대 스왑 금지 (비권장) |
| 1         | 최소 (극한 상황만)          | 최대                | 서버 환경 권장 |
| 10        | 낮음                       | 높음                | DB 서버, 캐시 서버 |
| 60 (기본) | 중간                       | 중간                | 범용 데스크탑 |
| 100       | 최대                       | 최소                | 메모리 극소 환경 |

<br>

### 기본값이 60인 이유

`vm.swappiness`의 **Linux 커널 기본값은 60**이다. 대부분의 배포판이 이 값을 유지하지만, 특정 용도로 튜닝된 이미지에서는 다를 수 있다.

이 값은 **다양한 워크로드에서의 균형**을 고려한 것이다. 여러 프로세스가 동시에 실행될 때 오래 사용하지 않은 프로세스의 메모리는 스왑으로 보내고, 파일 캐시를 확보하여 I/O 성능을 높이는 방식이다. 메모리가 적은 시스템(1~2GB)부터 많은 시스템(32GB+)까지 범용적으로 동작하도록 설정된 값이다.

이 기본값이 유지되는 데는 역사적 맥락도 있다. 2000년대 초반에는 메모리가 비싸서(512MB~2GB 일반적) 스왑을 적극 활용하는 것이 합리적이었다. 현재는 메모리가 저렴해졌지만, 하위 호환성 때문에 기본값이 유지되고 있다. 서버 환경에서는 관리자가 워크로드에 맞게 수동으로 튜닝하는 것이 일반적이다.

### 설정 전략

환경에 따라 해당 값 설정 전략을 달리 가져가는 것이 좋다.

- **낮게 설정 (0~10)**: 성능 예측 가능성을 중시할 때 사용한다. 스왑으로 인한 지연을 최소화하고, 메모리 접근 속도를 일정하게 유지해야 하는 환경에 적합하다.
- **높게 설정 (60~100)**: 메모리 활용률을 중시할 때 사용한다. 물리 메모리가 부족하거나, 응답 속도보다 작업 완료가 중요한 환경에 적합하다.

| 낮은 설정 (0~10) | 높은 설정 (60~100) |
|-----------------|-------------------|
| 데이터베이스 서버 (Redis, PostgreSQL, MySQL) | 배치 처리 서버 (ETL 작업 등) |
| 실시간 처리 시스템 (GPU 추론, 게임 서버, 스트리밍) | 데스크탑/개발 환경 |
| Kubernetes 노드 | 메모리 부족 환경 (물리 메모리 2GB 등) |

> **참고 - 스왑 공간의 저장 매체**: swappiness 설정과 별개로, 스왑 공간이 어떤 저장 매체에 있는지도 성능에 영향을 준다. SSD에 있으면 HDD보다 스왑 I/O가 빠르지만, RAM보다는 여전히 수백~수천 배 느리다. SSD라고 해서 높은 swappiness를 권장하는 것은 아니며, 스왑 발생 시 성능 저하가 "덜 치명적"일 뿐이다. HDD 환경에서 스왑이 발생하면 시스템이 거의 멈출 수 있으므로, 오히려 낮은 swappiness와 충분한 RAM 확보가 더 중요하다.

### 설정 방법

```bash
# 현재 값 확인
cat /proc/sys/vm/swappiness

# 임시 변경
sudo sysctl -w vm.swappiness=1

# 영구 변경
echo "vm.swappiness=1" | sudo tee -a /etc/sysctl.conf

# 확인
sudo sysctl vm.swappiness
```

<br>

## 기타 메모리 관련 커널 파라미터

`vm.swappiness` 외에도 메모리 관리에 영향을 주는 여러 커널 파라미터가 있다.

### 주요 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| **vm.min_free_kbytes** | 시스템 의존 | 커널이 유지하려는 최소 여유 메모리. 이 이하로 떨어지면 kswapd 시작 |
| **vm.vfs_cache_pressure** | 100 | inode/dentry 캐시 회수 압박. 낮으면 캐시 유지, 높으면 적극 회수 |
| **vm.dirty_ratio** | 20~40 | 전체 메모리 대비 dirty page 비율. 초과 시 프로세스가 직접 writeback |
| **vm.dirty_background_ratio** | 10 | 백그라운드 writeback 시작 임계값 |
| **vm.overcommit_memory** | 0 | 오버커밋 정책 (0=휴리스틱, 1=항상허용, 2=엄격) |
| **vm.overcommit_ratio** | 50 | mode=2일 때 허용 비율 |
| **vm.oom_kill_allocating_task** | 0 | OOM 시 할당 요청한 프로세스 우선 종료 여부 |
| **vm.panic_on_oom** | 0 | OOM 시 커널 패닉 발생 여부 |
| **vm.nr_hugepages** | 0 | Explicit Huge Pages 개수 |

### 확인 방법

```bash
# 모든 vm 파라미터 확인
sysctl -a | grep ^vm

# 특정 값 확인
sysctl vm.min_free_kbytes
sysctl vm.dirty_ratio
```

<details markdown="1">
<summary>실제 커널 파라미터 출력 예시 (Rocky Linux 10, 클릭하여 펼치기)</summary>

```bash
$ sysctl -a | grep ^vm
vm.admin_reserve_kbytes = 8192
vm.compact_unevictable_allowed = 1
vm.compaction_proactiveness = 20
vm.dirty_background_bytes = 0
vm.dirty_background_ratio = 10        # 백그라운드 writeback 시작 임계값
vm.dirty_bytes = 0
vm.dirty_expire_centisecs = 3000      # dirty page 만료 시간 (30초)
vm.dirty_ratio = 40                   # 프로세스 직접 writeback 임계값
vm.dirty_writeback_centisecs = 500    # writeback 스레드 간격 (5초)
vm.dirtytime_expire_seconds = 43200
vm.enable_soft_offline = 1
vm.extfrag_threshold = 500
vm.hugetlb_shm_group = 0
vm.laptop_mode = 0
vm.legacy_va_layout = 0
vm.lowmem_reserve_ratio = 256   256     32      0       0
vm.max_map_count = 1048576            # 프로세스당 최대 mmap 영역 수
vm.memfd_noexec = 0
vm.memory_failure_early_kill = 0
vm.memory_failure_recovery = 1
vm.min_free_kbytes = 22528            # 최소 여유 메모리 (kswapd 트리거)
vm.min_slab_ratio = 5
vm.min_unmapped_ratio = 1
vm.mmap_min_addr = 65536
vm.mmap_rnd_bits = 18
vm.nr_hugepages = 0                   # Explicit Huge Pages 개수
vm.nr_hugepages_mempolicy = 0
vm.nr_overcommit_hugepages = 0
vm.numa_stat = 1
vm.numa_zonelist_order = Node
vm.oom_dump_tasks = 1                 # OOM 시 태스크 목록 덤프
vm.oom_kill_allocating_task = 0       # OOM 시 할당 요청 프로세스 종료
vm.overcommit_kbytes = 0
vm.overcommit_memory = 1              # 오버커밋 정책 (1=항상 허용)
vm.overcommit_ratio = 50              # mode=2일 때 허용 비율
vm.page-cluster = 3                   # 스왑 시 한 번에 읽는 페이지 수 (2^3=8)
vm.page_lock_unfairness = 5
vm.panic_on_oom = 0                   # OOM 시 커널 패닉 여부
vm.percpu_pagelist_high_fraction = 0
vm.stat_interval = 1
vm.swappiness = 10                    # 스왑 적극성 (낮으면 File Page 회수 선호)
vm.unprivileged_userfaultfd = 0
vm.user_reserve_kbytes = 57138
vm.vfs_cache_pressure = 100           # VFS 캐시 회수 압박 (100=기본)
vm.watermark_boost_factor = 15000
vm.watermark_scale_factor = 10
vm.zone_reclaim_mode = 0              # NUMA 메모리 회수 모드
```

</details>

### 배포판 간 차이

커널 파라미터 자체는 Linux 커널 기능이므로 **Ubuntu, RHEL, Rocky 등 모든 배포판에서 동일**하다. 다만:

- **기본값**은 배포판마다 다를 수 있음 (예: `vm.dirty_ratio`가 Ubuntu는 40, RHEL은 20)
- **커널 버전**에 따라 새 파라미터 추가, 동작 변경 가능
- **설정 파일 위치**가 다를 수 있음 (`/etc/sysctl.conf` vs `/etc/sysctl.d/`)

<br>

## 스왑 공간 설정

### 스왑 공간이란

`vm.swappiness`를 설정했다고 해서 스왑이 자동으로 활성화되는 것은 아니다. **스왑 공간(swap space)**이 별도로 설정되어 있어야 스왑이 동작한다.

스왑 공간은 두 가지 형태로 설정할 수 있다:

| 종류 | 설명 | 장점 | 단점 |
|-----|------|------|------|
| **스왑 파티션** | 디스크의 별도 파티션 | 성능이 약간 좋음 | 크기 변경이 어려움 |
| **스왑 파일** | 파일시스템 위의 파일 | 크기 변경 용이 | 약간의 오버헤드 |

### 스왑 상태 확인

```bash
# 스왑 활성화 여부 확인
swapon --show
# 출력이 없으면 스왑이 비활성화된 상태

# 또는 free로 확인
free -h
# Swap 행이 0이면 스왑 없음

# 스왑 파일/파티션 설정 확인
cat /etc/fstab | grep swap
```

### 스왑 파일 생성 (예시)

```bash
# 4GB 스왑 파일 생성
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile

# 스왑 활성화
sudo swapon /swapfile

# 부팅 시 자동 활성화 (/etc/fstab에 추가)
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 스왑 비활성화

```bash
# 일시적 비활성화 (재부팅 시 복구)
sudo swapoff -a

# 영구적 비활성화 (/etc/fstab에서 swap 라인 주석 처리)
sudo sed -i '/ swap / s/^/#/' /etc/fstab
```

> **주의**: 스왑이 사용 중일 때 `swapoff`를 실행하면 스왑된 모든 페이지가 RAM으로 이동한다. RAM이 부족하면 OOM이 발생할 수 있다.

<br>

# Huge Pages

## 개념

일반적인 페이지 크기는 4KB지만, 대용량 메모리를 사용하는 애플리케이션에서는 **Huge Pages**를 사용할 수 있다. Huge Pages는 2MB 또는 1GB 크기의 페이지를 사용한다.

## 장점

| 항목 | 일반 페이지 (4KB) | Huge Pages (2MB) |
|-----|------------------|------------------|
| **Page Table 크기** | 1GB 메모리 → 262,144개 항목 | 1GB 메모리 → 512개 항목 |
| **TLB 효율** | TLB 미스 빈번 | TLB 적중률 향상 |
| **메모리 접근 속도** | 느림 | 빠름 |

## Huge Pages의 종류

Linux에서 Huge Pages는 두 가지 방식으로 제공된다:

| 종류 | 관리 방식 | 스왑 가능 여부 | 용도 |
|-----|----------|--------------|------|
| **Explicit Huge Pages (HugeTLB)** | 관리자가 수동 설정 | **불가** (메모리에 고정) | DB, 가상화 등 성능 중요 애플리케이션 |
| **Transparent Huge Pages (THP)** | 커널이 자동 관리 | **가능** (4KB로 split 후 스왑) | 일반 애플리케이션 |

> **참고**: 이 글에서 다루는 Huge Pages는 Explicit Huge Pages(HugeTLB)를 의미한다. THP는 커널이 자동으로 관리하며, 필요 시 4KB 페이지로 분할되어 스왑될 수 있다.

## 사용 사례

- **데이터베이스**: Oracle, PostgreSQL, MySQL의 Shared Buffer
- **가상화**: KVM/QEMU 게스트 메모리
- **빅데이터**: Hadoop, Spark의 대용량 데이터 처리

## 확인 방법

```bash
# Huge Pages 정보 확인
cat /proc/meminfo | grep Huge

# 출력 예시
# HugePages_Total:       0
# HugePages_Free:        0
# Hugepagesize:       2048 kB
```

> **주의**: Explicit Huge Pages는 스왑되지 않고 메모리에 고정(pinned)되므로, 설정 시 물리 메모리 용량을 고려해야 한다.

<br>

# 모니터링

## 스왑 사용량 확인

```bash
$ free -h
               total        used        free      shared  buff/cache   available
Mem:           3.8Gi       1.5Gi       118Mi        51Mi       2.2Gi       1.9Gi
Swap:          4.0Gi       338Mi       3.7Gi
```

| 컬럼 | 설명 |
|-----|------|
| **total** | 전체 물리 메모리 |
| **used** | 사용 중인 메모리 (프로세스 + 커널) |
| **free** | 완전히 비어있는 메모리 (아무 용도로도 사용되지 않음) |
| **shared** | tmpfs 등 공유 메모리 |
| **buff/cache** | 버퍼(블록 장치 I/O)와 캐시(파일 I/O)로 사용 중인 메모리 |
| **available** | 새 프로세스가 사용 가능한 메모리 (free + 회수 가능한 buff/cache) |

> **참고**: `free`가 낮아도 `available`이 충분하면 정상이다. Linux는 유휴 메모리를 버퍼/캐시로 활용하여 I/O 성능을 높이고, 필요 시 회수한다. `available`이 낮아야 메모리 부족이다.

## 스왑 활동 확인

```bash
$ vmstat 1
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 0  0 346916 128064 450996 1821416    0    0     6     8    5   15  1  5 94  0  0
```

- **si (swap in)**: 스왑에서 메모리로 읽어온 페이지 수
- **so (swap out)**: 메모리에서 스왑으로 보낸 페이지 수
- si/so가 **0이 아니면** 활발한 스왑이 발생 중

## 메모리 압박 상태 확인

```bash
# 메모리 압박 이벤트 확인
cat /proc/vmstat | grep -E "pgmajfault|pgpgin|pgpgout"
# pgmajfault: Major Page Fault 발생 횟수 (높으면 스왑 활발)
# pgpgin: 디스크에서 읽어온 페이지 수 (KB 단위)
# pgpgout: 디스크에 쓴 페이지 수 (KB 단위)

# OOM Killer 로그 확인
dmesg | grep -i "out of memory"
journalctl -k | grep -i "killed process"
```

## 상황 판단

| 상황 | 스왑 사용량 | si/so | pgmajfault | 해석 |
|------|-----------|-------|-----------|------|
| 정상 | 수십~수백 MB | 거의 0 | 낮고 안정적 | 오래 안 쓴 페이지들이 조용히 스왑됨 |
| 위험 | 수 GB | 높고 계속 변동 | 급증 중 | Thrashing 발생, 메모리 압박 심각 |

## 스왑 사용 프로세스 확인

```bash
# 메모리 많이 쓰는 프로세스
ps aux --sort=-%mem | head -10

# 프로세스별 스왑 사용량
cat /proc/*/status | grep -E "^(Name|VmSwap)" | paste - -

# 또는 smem 도구 사용 (설치 필요)
sudo apt install smem
smem -s swap
```

<br>

# 정리

리눅스 메모리 관리의 핵심 개념을 정리하면 다음과 같다:

| 개념 | 설명 |
|-----|------|
| **가상 메모리** | 프로세스에게 독립적인 주소 공간을 제공하고, MMU가 물리 메모리로 변환 |
| **페이지** | 4KB 단위의 메모리 관리 기본 단위 |
| **TLB** | Page Table 조회 결과를 캐싱하여 주소 변환 속도 향상 |
| **Huge Pages** | 2MB/1GB 크기의 대형 페이지, TLB 효율 향상 (스왑 불가) |
| **Page Reclaim** | 메모리 압박 시 커널이 페이지를 회수하는 전체 과정 |
| **스왑** | Page Reclaim 중 Anonymous Page를 디스크로 대피시키는 메커니즘 |
| **LRU** | 오래 안 쓴 페이지부터 회수 대상으로 선택하는 알고리즘. Linux는 근사 LRU(Two-List LRU) 사용 |
| **Page Fault** | 스왑된 페이지 접근 시 발생, 디스크에서 다시 로드 |
| **vm.swappiness** | Anonymous Page vs File Page 회수 비율 조절 (0~100) |
| **Thrashing** | 스왑이 과도하게 발생하여 시스템이 거의 멈추는 상태 |

**권장 설정**:
- 서버 환경: `vm.swappiness=1` (OOM 안전장치 유지하면서 스왑 최소화)
- Kubernetes/컨테이너: 스왑 비활성화 (`swapoff -a`)

<br>

# 참고 자료

- [Linux Kernel Documentation - vm.txt](https://www.kernel.org/doc/Documentation/sysctl/vm.txt) - 커널 메모리 관련 sysctl 파라미터

- [Linux Memory Management - lwn.net](https://lwn.net/Kernel/Index/#Memory_management) - 커널 메모리 관리 심층 분석
- [Brendan Gregg - Linux Performance](https://www.brendangregg.com/linuxperf.html) - 성능 분석 도구 및 방법론

<br>
