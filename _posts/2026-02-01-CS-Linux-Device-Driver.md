---
title:  "[Linux] 디바이스 드라이버: 3계층 구조"
excerpt: "리눅스에서 장치를 다루기 위한 3계층 구조를 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Device Driver
  - Kernel Module
  - ioctl
  - VFS
  - Character Device
  - Block Device
---

<br>

GPU를 컨테이너에 노출시키거나, 커널 모듈과 장치 파일의 관계를 이해하거나, 디바이스 드라이버 관련 트러블슈팅을 해야 할 때 리눅스가 장치를 다루는 구조를 알아야 한다. 이 글에서는 리눅스 디바이스 드라이버의 3계층 구조와 각 구성 요소의 역할을 살펴본다.

<br>

# TL;DR

- **Everything is a file**: Unix/Linux에서 장치도 파일처럼 다룬다
- **3계층 구조**: 유저 라이브러리(`.so`) → 장치 파일(`/dev/*`) → 커널 모듈(`.ko`) → 하드웨어
- **장치 파일 종류**: 문자 장치(`c`)와 블록 장치(`b`)
- **시스템 콜**: `open()`, `read()`, `write()`, `ioctl()`을 통해 커널과 통신
- **FHS 표준 경로**: 커널 모듈은 `/lib/modules/$(uname -r)/kernel/`, 장치 파일은 `/dev/`, 유저 라이브러리는 `/lib/`, `/usr/lib/`
- **유저 라이브러리의 필요성**: 간단한 장치는 불필요, 복잡한 장치(GPU 등)는 필수

<br>

# 개요

Unix/Linux에서는 **["Everything is a file"]({% post_url 2026-01-31-CS-Everything-is-a-File %})** 철학에 따라 하드웨어 장치도 파일처럼 다룬다.

```bash
# 1. 일반 파일 읽기
cat /tmp/file.txt  # 텍스트 파일

# 2. 장치 파일 읽기 (동일한 방식!)
cat /dev/random  # 랜덤 데이터 생성 장치

# 3. 프로세스 정보 읽기 (동일한 방식!)
cat /proc/cpuinfo  # CPU 정보

# 4. 시스템 설정 읽기/쓰기 (동일한 방식!)
cat /sys/class/net/eth0/address  # 네트워크 MAC 주소
echo 1 > /proc/sys/net/ipv4/ip_forward  # IP 포워딩 활성화
```

<br>

장치를 파일처럼 다루면 `cat`, `echo` 같은 일반 명령어로 장치를 제어할 수 있다. [해당 철학의 한계]({% post_url 2026-01-31-CS-Everything-is-a-File %}#한계와-확장)에서 살펴봤듯이 복잡한 장치 제어(GPU 설정, 디스크 파티션 등)는 기본 파일 연산만으로는 부족하다. 이런 경우 `ioctl()` 같은 확장 시스템 콜을 사용한다 ([시스템 콜](#시스템-콜) 참고).


<br>

## 파일 시스템 계층

리눅스 시스템은 [이전 글]({% post_url 2026-01-31-CS-Everything-is-a-File %}#파일-시스템-계층)에서 살펴본 **FHS(Filesystem Hierarchy Standard)**를 따른다. 장치와 드라이버를 다룰 때 주로 사용하는 경로는 다음과 같다.

| 경로 | 역할 | 용도 |
|-----|------|------|
| `/dev/` | 장치 파일 인터페이스 | 유저 프로그램이 장치에 **직접 접근** |
| `/proc/` | 프로세스/시스템 정보 | 장치 드라이버 상태 **조회** |
| `/sys/` | 장치/드라이버 설정 | 드라이버 파라미터 **조회 및 변경** |

이 글에서는 장치 파일이 위치하는 `/dev/`를 주로 다룬다. `/proc/`와 `/sys/`는 장치 정보를 확인하거나 설정을 변경할 때 보조적으로 사용된다. 예를 들어:
- `/proc/devices`: 등록된 장치 드라이버 목록 확인
- `/sys/class/*/`: 장치 클래스별 정보 및 설정 접근

디바이스 드라이버 3계층 구조를 이해하는 데는 `/dev/`만 알면 충분하다.

<br>

## 파일 종류

Linux에는 [7가지 파일 종류]({% post_url 2026-01-31-CS-Everything-is-a-File %}#파일-종류)가 있다. 이 중 **`c`(문자 장치)**와 **`b`(블록 장치)**가 하드웨어를 나타내는 장치 파일이다.

```bash
ls -l /dev/ | head -5
brw-rw---- 1 root disk    8,   0 Feb  3 10:00 sda     # 블록 장치
crw-rw-rw- 1 root tty     1,   3 Feb  3 10:00 null    # 문자 장치
crw-rw-rw- 1 root tty     1,   9 Feb  3 10:00 urandom # 문자 장치
```

<br>

# 장치 파일

## 종류

장치 파일은 크게 두 종류로 나뉜다.
- 문자 장치
- 블록 장치

<br>

### 문자 장치 (Character Device)

블록 레이어와 페이지 캐시를 거치지 않는 **바이트 스트림** 인터페이스다.

- **특징**: 한 번의 `read()`/`write()`로 임의 크기를 전송할 수 있으며, 드라이버가 `llseek`을 구현하면 시킹도 가능(`/dev/mem` 등)
- **용도**: 터미널, 시리얼 포트, 키보드, 마우스, GPU 제어, 사운드카드

> 참고: **문자 장치와 페이지 캐시**
> 
> 문자 장치도 커널 내부적으로는 작은 버퍼를 사용하지만, **페이지 캐시를 사용하지 않는다**. 이는 문자 장치가 페이지 캐시가 가정하는 "고정 블록 단위로 주소화 가능한 저장소" 구조 자체를 갖지 않기 때문이다. 키보드 입력에는 캐싱할 "페이지"가 존재하지 않는다.
>
> 반면 블록 장치(디스크 등)는 효율을 위해 커널이 **페이지 캐시**를 적극 활용하여 I/O를 최적화한다. 다만 `O_DIRECT` 플래그로 페이지 캐시를 우회할 수도 있으며, NVMe 같은 빠른 장치에서는 우회가 오히려 유리한 경우가 많다.

```bash
crw-rw-rw- 1 root root 1,  3 /dev/null      # 널 장치
crw-rw-rw- 1 root root 1,  8 /dev/random    # 랜덤 생성기
crw-rw---- 1 root root 4, 64 /dev/ttyS0     # 시리얼 포트
crw------- 1 root root 237, 0 /dev/hidraw0  # HID 입력장치
```

<br>

### 블록 장치 (Block Device)

데이터를 블록 단위(보통 512B, 4KB)로 읽고 쓴다.

- **특징**: 랜덤 액세스 가능, 커널이 버퍼링/캐싱 수행, 파일 시스템 마운트 가능
- **용도**: 하드디스크, SSD, USB 드라이브, CD/DVD, 파티션

```bash
brw-rw---- 1 root disk 8, 0 /dev/sda     # 하드디스크
brw-rw---- 1 root disk 8, 1 /dev/sda1    # 파티션
brw-rw---- 1 root disk 7, 0 /dev/loop0   # 루프백 장치
```

<br>

### 장치 번호 (Major/Minor)

`ls -l /dev/`에서 파일 크기 위치에 두 개의 숫자가 표시된다. 이것이 장치 번호다.

```bash
crw-rw-rw- 1 root root 1, 3 /dev/null
                        ↑  ↑
                     Major Minor
```

| 번호 | 역할 |
|-----|------|
| **Major** | 어떤 드라이버를 사용할지 (등록된 드라이버 식별) |
| **Minor** | 같은 드라이버 내에서 어떤 장치인지 (장치 인스턴스 식별) |

예시:
- `/dev/sda` (8, 0) - SCSI(Small Computer System Interface) 디스크 드라이버, 첫 번째 디스크 전체
- `/dev/sda1` (8, 1) - SCSI 디스크 드라이버, 첫 번째 디스크의 파티션 1
- `/dev/nvidia0` (195, 0) - NVIDIA 드라이버, GPU 0번
- `/dev/nvidia1` (195, 1) - NVIDIA 드라이버, GPU 1번

Minor 번호가 무엇을 식별하는지는 드라이버마다 다르다. SCSI 디스크 드라이버는 디스크 하나당 minor 16개를 묶어서 할당하므로(0=디스크 전체, 1~15=파티션, 16=두 번째 디스크 전체, ...) minor 번호가 디스크와 파티션을 동시에 인코딩한다. 반면 NVIDIA 드라이버는 각 minor가 독립된 GPU 한 장에 1:1 대응한다.

실제로 시스템에 등록된 major number ↔ 드라이버 이름 매핑은 `cat /proc/devices`로 확인할 수 있다.

```bash
$ cat /proc/devices
Character devices:
  1 mem
  4 tty
  5 /dev/tty
195 nvidia
...

Block devices:
  8 sd
259 blkext
...
```

<br>

## 예시

주요 장치 파일 예시는 아래와 같다.

| 구분 | 장치 파일 | 설명 |
|-----|----------|------|
| **문자 장치** | `/dev/null` | 모든 것을 버림 (블랙홀) |
| | `/dev/zero` | 무한한 0 제공 |
| | `/dev/random`, `/dev/urandom` | 난수 생성 |
| | `/dev/ttyS0` | 시리얼 포트 |
| | `/dev/input/mouse0` | 마우스 |
| | `/dev/nvidia0` | NVIDIA GPU |
| **블록 장치** | `/dev/sda` | 첫 번째 SATA/SCSI 디스크 |
| | `/dev/nvme0n1` | 첫 번째 NVMe(Non-Volatile Memory Express) SSD |
| | `/dev/loop0` | 루프백 장치 (ISO 마운트 등) |

> **참고: NVMe와 SATA**
>
> 위 테이블에서 `/dev/sda`(SATA 디스크)와 `/dev/nvme0n1`(NVMe SSD)은 같은 블록 장치이지만 사용하는 버스와 프로토콜이 다르다. SATA 버스의 AHCI(Advanced Host Controller Interface) 프로토콜은 HDD 시대에 설계되어 큐가 하나(깊이 32)뿐이다. NVMe는 PCIe 버스 위에서 동작하는 스토리지 전용 프로토콜로, 최대 65535개의 큐(각 깊이 65536)를 지원하여 플래시 메모리의 병렬성을 충분히 활용한다. PCIe와 NVMe의 관계는 [이전 글]({% post_url 2026-01-31-CS-Everything-is-a-File %}#2-시스템-설정-sys)의 PCIe 참고 노트를 참고하자.

<br>

**Everything is a file** 철학에 따라 모든 장치를 파일처럼 다루므로, 복잡한 하드웨어도 파일을 다루는 것과 동일한 방식(예: `read`, `write`, `ioctl`)으로 제어할 수 있다. 

구체적인 시스템 콜은 [시스템 콜](#시스템-콜) 섹션에서 다룬다. 

<br>

# 3계층 구조

리눅스에서 디바이스를 다루는 구조는 **3계층**으로 명확하게 분리되어 있다.

```text
┌─────────────────────────────────────┐
    User Application (애플리케이션)    
    - GPU 프로그램 (CUDA 코드 등)      
└─────────────────────────────────────┘
              ↓ (함수 호출)
┌─────────────────────────────────────┐
    User-space Library (.so)           
    - libcuda.so, libasound.so 등      
    - 고수준 API 제공                  
└─────────────────────────────────────┘
              ↓ (시스템 콜: open, read, write, ioctl)
┌─────────────────────────────────────┐
    Device File (/dev/*)               
    - /dev/nvidia0, /dev/sda 등        
    - 시스템 콜의 대상 (파일 경로)     
└─────────────────────────────────────┘
              ↓ (커널 모드 전환, 커널 진입)
─────────────────────────────────────── 유저 / 커널 경계
┌─────────────────────────────────────┐
    Kernel Module (.ko)                
    - nvidia.ko, snd_hda_intel.ko 등   
    - 실제 하드웨어 제어 로직          
└─────────────────────────────────────┘
              ↓ (I/O 명령)
┌─────────────────────────────────────┐
    Hardware (GPU, 디스크 등)          
└─────────────────────────────────────┘
```


## 특징

- **진입점**: `/dev/` 파일은 유저 공간에서 커널 드라이버에 접근하는 진입점 중 하나 (유저/커널 분리 자체는 CPU 보호 모드가 강제하며, `socket()`, `pipe()`, `mmap` 등도 그 경계를 넘는다)
- **통신 방식**: 시스템 콜(`open()`, `read()`, `write()`, `ioctl()`)을 통해서만 커널 접근
- **선택적 라이브러리**: 간단한 장치는 유저 라이브러리 없이 직접 `/dev/` 접근 가능

## 구성 요소

3계층의 구성 요소는 다음과 같다.

- **커널 모듈 (.ko)**: 하드웨어를 직접 제어하는 드라이버 코드 (필수)
- **장치 파일 (/dev/*)**: 유저 공간에서 커널에 접근하는 인터페이스 (필수)
- **유저 라이브러리 (.so)**: 고수준 API를 제공하는 공유 라이브러리 (선택적 - 복잡한 장치에만 필요)

### 경로 배치

각 구성 요소는 [파일 시스템 계층](#파일-시스템-계층)에서 언급한 FHS 표준에 따라 다음 경로에 배치된다.

| 계층 | 파일 형식 | 표준 경로 |
|-----|----------|----------|
| 커널 모듈 | `.ko` (Kernel Object) | `/lib/modules/$(uname -r)/kernel/` |
| 장치 파일 | 특수 파일 | `/dev/` |
| 유저 라이브러리 | `.so` (Shared Object) | `/lib/`, `/usr/lib/`, `/usr/local/lib/` |

<br>

실제 장치별로 3계층 구조별 구성 요소 및 파일 배치 경로 예시는 다음과 같다.

| 장치 | 커널 모듈 | 장치 파일 | 유저 라이브러리 |
|-----|----------|----------|----------------|
| 네트워크 카드 | `e1000e.ko` | 없음 (`socket()` API 사용) | libc socket API |
| 사운드 카드 | `snd_hda_intel.ko` | `/dev/snd/*` | `libasound.so` |
| NVIDIA GPU | `nvidia.ko` | `/dev/nvidia*` | `libcuda.so` |

> **참고: 네트워크 인터페이스에 `/dev/` 장치 파일이 없는 이유**
>
> 네트워크 인터페이스는 "Everything is a file" 철학의 대표적 예외다. 하나의 NIC이 수천 개의 동시 연결을 처리하는데, 각 연결은 (프로토콜, 출발 IP, 출발 포트, 도착 IP, 도착 포트)의 5-tuple로 식별된다. 이 다중화된 연결을 `/dev/eth0` 같은 단일 파일 경로로 표현할 수 없기 때문에, BSD가 `socket()` + `bind()` + `connect()`라는 별도 인터페이스를 설계했고 Linux가 이를 계승했다. 상세 배경은 [이전 글]({% post_url 2026-01-31-CS-Everything-is-a-File %}#4-네트워크-인터페이스-dev-파일이-없는-장치)을 참고하자.

<br>

# 커널 모듈 (.ko)

하드웨어를 직접 제어하는 커널 레벨 코드다.

## 특징

- 커널과 동일한 주소 공간에서 실행
- 역사적으로 거의 모든 커널 코드가 **C 언어**로 작성되어 있고, 일부 어셈블리가 섞임
- 커널 6.1(2022.12)부터 **Rust**도 공식 지원 언어로 합류하여, 일부 드라이버가 Rust로 작성·머지되고 있음

> **참고: 커널 모듈이 하드웨어와 통신하는 세 가지 메커니즘**
>
> 커널 모듈은 다음 세 메커니즘을 조합하여 하드웨어를 제어한다.
> - **MMIO(Memory-Mapped I/O)**: `ioremap()`으로 디바이스 레지스터 영역을 커널 가상 주소로 매핑하고, `writel()`/`readl()`로 명령을 내린다.
> - **DMA(Direct Memory Access)**: 대량 데이터를 CPU 개입 없이 디바이스가 직접 RAM과 주고받는다.
> - **인터럽트(IRQ)**: 디바이스가 작업 완료나 이벤트 발생을 CPU에 통보한다.
>
> 예를 들어 GPU 드라이버는 MMIO로 제어 레지스터에 명령을 쓰고, DMA로 대용량 텍스처를 GPU 메모리로 전송하며, 렌더링 완료 시 인터럽트를 받는다.

## 표준 경로

커널 버전별로 `/lib/modules/5.15.0-xxx/` 형태로 관리된다.

```bash
/lib/modules/$(uname -r)/kernel/
├── drivers/          # 하드웨어 드라이버
│   ├── gpu/
│   │   └── drm/
│   │       └── nvidia/
│   ├── net/
│   └── sound/
└── ...
```

> **참고**: `uname`은 시스템 정보를 출력하는 명령어다. `uname -r`은 현재 실행 중인 커널 버전을 출력한다. 예를 들어 `6.8.0-86-generic`(Ubuntu) 또는 `6.12.0-55.39.1.el10_0.aarch64`(Rocky) 같은 형태다. 커널 모듈은 커널 버전별로 별도 디렉토리에 저장되므로, 경로에 `$(uname -r)`이 포함된다.


## 로드와 언로드

커널 모듈은 시스템 부팅 시 자동으로 로드되지만, 수동으로 로드/언로드할 수도 있다.

| 명령어 | 설명 |
|-------|------|
| `modprobe <모듈명>` | 모듈 로드 (의존성 자동 해결) |
| `modprobe -r <모듈명>` | 모듈 언로드 (이 모듈에 의존하는 모듈도 함께 제거 시도) |
| `insmod <모듈파일.ko>` | 모듈 로드 (의존성 자동 해결 안 함) |
| `rmmod <모듈명>` | 모듈 언로드 (의존 모듈이 있으면 실패) |

```bash
# 모듈 로드 (권장: 의존성 자동 해결)
sudo modprobe nvidia

# 모듈 언로드
sudo modprobe -r nvidia

# 모듈 정보 확인
modinfo nvidia
```

> **참고**: 일반적으로 `insmod`/`rmmod`보다 `modprobe`를 사용하는 것이 권장된다. `modprobe`는 `/lib/modules/$(uname -r)/modules.dep` 파일을 참조하여 의존성을 자동으로 해결한다.

## 모듈 의존성

모듈 A가 모듈 B의 기능(함수, 심볼)을 사용하면 **의존 관계**가 생긴다. 이 의존 관계는 모듈 언로드 시 중요하다.

- 의존하는 모듈이 있으면 해당 모듈을 **먼저 언로드**해야 함
- 드라이버 업데이트나 트러블슈팅 시 의존 관계 파악 필요
- 예: `nvidia` 모듈을 언로드하려면 `nvidia_uvm`, `nvidia_modeset` 등을 먼저 언로드
> 참고: **NVIDIA 드라이버 업데이트 시 의존성**
>
> NVIDIA 드라이버를 업데이트하거나 재로드할 때, 단순히 `rmmod nvidia`를 실행하면 의존성 때문에 실패한다.
> ```bash
> # 실패: nvidia를 사용하는 모듈이 있음
> $ sudo rmmod nvidia
> rmmod: ERROR: Module nvidia is in use by: nvidia_uvm nvidia_modeset
>
> # 올바른 순서: 의존 모듈부터 언로드
> $ sudo rmmod nvidia_uvm
> $ sudo rmmod nvidia_modeset
> $ sudo rmmod nvidia
> ```
> 또는 `modprobe -r nvidia`를 사용하면 이 모듈에 의존하는 모듈도 함께 제거를 시도한다.

의존 관계는 `lsmod` 명령의 **Used by** 컬럼으로 확인할 수 있다.

<br>

## 확인 방법

### lsmod

현재 로드된 커널 모듈 목록을 보여주는 명령어다. `/proc/modules`를 읽어서 보기 좋게 포맷팅한 결과를 출력한다.

```bash
lsmod

# 출력 예시
Module                  Size  Used by
nvidia_uvm           1781760  30
nvidia_drm             90112  0
nvidia              56889344  1156 nvidia_uvm,nvidia_modeset

# 특정 모듈 검색
lsmod | grep nvidia
```

| 컬럼 | 설명 |
|-----|------|
| **Module** | 모듈 이름 |
| **Size** | 모듈이 사용하는 메모리 크기 (바이트) |
| **Used by** | 참조 카운트(reference count)와 의존 모듈 목록. 첫 번째 숫자는 이 모듈을 참조하는 fd·컨텍스트·의존 모듈의 총합이고(GPU를 여러 프로세스가 열면 그 수만큼 증가), 콤마로 나열되는 이름이 의존 관계에 있는 모듈 목록이다. 위 예시에서 `nvidia`의 1156은 참조 카운트, `nvidia_uvm,nvidia_modeset`이 의존 모듈 |

<br>

### /proc/modules

커널이 현재 로드된 모듈 정보를 제공하는 가상 파일이다. `lsmod`가 내부적으로 읽는 원본 데이터다. `모듈명 크기 사용수 의존모듈 상태 메모리주소`의 형식을 가지는데, `lsmod`는 이 중 모듈명, 크기, 사용 정보만 추출해서 보여준다.

```bash
cat /proc/modules
 
# 출력 예시 (일부)
vxlan 131072 0 - Live 0xffff80007bcd5000
ip6_udp_tunnel 16384 1 vxlan, Live 0xffff80007bcc9000
bridge 327680 1 br_netfilter, Live 0xffff80007bc11000
stp 12288 1 bridge, Live 0xffff80007bc07000
llc 16384 2 bridge,stp, Live 0xffff80007bb9f000
overlay 200704 22 - Live 0xffff80007bbbd000
nf_conntrack 188416 6 nf_conntrack_netlink,xt_nat,xt_MASQUERADE,xt_conntrack,nft_ct,nf_nat, Live 0xffff80007bb10000
```


<br>

# 장치 파일 (/dev/*)

유저 프로그램이 하드웨어에 접근하기 위한 표준 인터페이스다.

## 특징

- User space와 Kernel space의 **경계 인터페이스**
- 시스템 콜을 통해 커널에 요청 전달

## 표준 경로

```bash
/dev/                 # 모든 장치 파일
├── sda, sdb          # 블록 장치
├── tty*, pts/*       # 터미널
├── nvidia*           # NVIDIA GPU
└── input/            # 입력 장치
```

> **참고: `/dev/` 엔트리는 누가 만드는가**
>
> 현대 리눅스에서 `/dev/`는 정적 디렉토리가 아니라 **udev**(또는 systemd-udevd)가 sysfs의 hotplug 이벤트를 받아 동적으로 생성하는 것이다. 예를 들어 GPU를 핫플러그하면 커널이 sysfs에 장치를 등록하고, udev가 규칙(rules)에 따라 `/dev/nvidia*` 엔트리를 만들어 준다.

## 확인 방법

### ls -l

장치 파일을 직접 조회하는 방법이다.

```bash
# 장치 파일 목록 확인
ls -l /dev/

# 특정 장치 찾기
ls -l /dev/nvidia*
ls -l /dev/sda*
```

### 장치 확인 명령어

특정 유형의 장치를 조회하는 전용 명령어들이다.

| 명령어 | 용도 |
|-------|------|
| `lsblk` | 블록 장치 (디스크, 파티션) |
| `lspci` | PCI 장치 (GPU, 네트워크 카드) |
| `lsusb` | USB 장치 |

> **참고**: `ls`는 "list"의 약자다. Unix/Linux에서 목록을 보여주는 명령어들이 `ls` 접두사를 따르는 네이밍 컨벤션이 있다. `lsblk`는 "list block devices", `lspci`는 "list PCI devices"를 의미한다.

## 시스템 콜

### VFS와 `file_operations`

커널의 VFS(Virtual File System) 계층은 파일처럼 다룰 수 있는 모든 객체가 구현해야 할 연산을 `struct file_operations`라는 함수 포인터 테이블로 정의한다. "Everything is a file" 철학이 실제로 작동하는 핵심 메커니즘이다.

```c
struct file_operations {
    int (*open)(struct inode *, struct file *);
    ssize_t (*read)(struct file *, char __user *, size_t, loff_t *);
    ssize_t (*write)(struct file *, const char __user *, size_t, loff_t *);
    long (*unlocked_ioctl)(struct file *, unsigned int cmd, unsigned long arg);
    int (*release)(struct inode *, struct file *);
    loff_t (*llseek)(struct file *, loff_t, int);
    int (*mmap)(struct file *, struct vm_area_struct *);
    // ... 약 30개 이상의 연산 슬롯
};
```

각 장치 드라이버는 이 테이블에서 자신이 지원하는 연산만 구현하여 등록한다. 유저 공간에서 `open()`, `read()`, `write()`, `ioctl()` 등의 시스템 콜을 호출하면, VFS가 해당 fd에 연결된 드라이버의 대응 함수를 호출한다.

```c
// 드라이버: 지원하는 연산만 구현하여 등록
static struct file_operations my_fops = {
    .open = my_open,
    .read = my_read,
    .write = my_write,
    .unlocked_ioctl = my_ioctl,
    .release = my_release,
};
```

아래에서 다루는 기본 파일 연산(`open`, `read`, `write`, `close`)과 `ioctl()`은 모두 이 테이블의 슬롯에 대응한다.

<br>

### 기본 파일 연산

장치 파일에 접근할 때 사용하는 기본 시스템 콜이다.

| 시스템 콜 | 설명 |
|----------|------|
| `open()` | 장치 파일 열기 |
| `read()` | 장치에서 데이터 읽기 |
| `write()` | 장치로 데이터 쓰기 |
| `close()` | 장치 파일 닫기 |

<br>

### ioctl

`ioctl()`은 `read()`/`write()`로 표현할 수 없는 **제어 명령**을 파일 디스크립터에 보내는 범용 시스템 콜이다.

```c
int ioctl(int fd, unsigned long request, ...);
//        ^fd     ^명령 코드              ^명령별 인자(포인터 등)
```

하나의 시그니처 안에 `request` 코드를 분기하여 모든 제어 연산을 처리하는 구조다. 장치 파일에만 한정되지 않고, 해당 fd에 연결된 커널 객체(장치 드라이버, 파일시스템, 소켓 레이어 등)가 ioctl 핸들러를 구현했다면 사용할 수 있다.

```c
// 장치 파일: 터미널 설정
ioctl(tty_fd, TCGETS, &settings);

// 소켓: 네트워크 인터페이스 IP 조회
ioctl(sock_fd, SIOCGIFADDR, &ifr);

// 일반 파일: 파일시스템 플래그 조회
ioctl(file_fd, FS_IOC_GETFLAGS, &flags);
```

<br>

### 구조와 한계

`ioctl()`의 핵심 구조는 **하나의 `request` 정수 코드로 모든 연산을 다중화(multiplexing)**하는 것이다. 커널은 해당 fd의 핸들러를 호출하고, 핸들러 내부에서 `request` 값에 따라 분기한다. `request`가 정수 하나이므로 `switch`로 분기하는 것이 사실상 관례적 패턴이다(커널이 강제하는 구조가 아니라 자연스럽게 정착된 것).

```c
// 사실상 표준 패턴: switch(cmd)로 분기
static long my_ioctl(struct file *f, unsigned int cmd, unsigned long arg) {
    switch (cmd) {
    case MY_CMD_SET_CLOCK:   /* 클럭 설정 로직 */ break;
    case MY_CMD_GET_STATUS:  /* 상태 조회 로직 */ break;
    default: return -ENOTTY; // 미지원 명령
    }
}
```

명령이 수백 개로 많아지면 `switch` 대신 명령 코드→함수 포인터의 디스패치 테이블(배열)을 만들어 간접 호출하기도 한다(DRM(Direct Rendering Manager) 서브시스템 등). 하지만 "정수 코드로 분기한다"는 본질은 동일하다.

이 구조는 본질적으로 아래와 같은 한계를 갖는다:

- **명령 코드가 표준화되지 않음**: 각 드라이버/모듈이 자체 코드를 정의하므로, 같은 숫자가 드라이버마다 다른 의미를 가질 수 있다
- **타입 안전성 없음**: 세 번째 인자가 `...`(가변 인자)이므로 컴파일러가 타입을 검증하지 못한다
- **보안 검증 어려움**: 임의의 명령을 전달할 수 있어, 권한 검사가 각 핸들러 구현에 의존한다

> **참고**: 이러한 한계 때문에 Linux는 가능한 것들을 `/proc`, `/sys` 파일 인터페이스로 노출시키려 한다. 예를 들어 CPU 주파수는 `ioctl()` 대신 `/sys/devices/system/cpu/*/cpufreq/*`에 `echo`로 쓸 수 있다([이전 글]({% post_url 2026-01-31-CS-Everything-is-a-File %}#한계와-확장) 참고).

<br>

### 장치 드라이버에서의 ioctl 구현

`ioctl()`은 위의 `file_operations` 테이블에서 `.unlocked_ioctl` 슬롯에 해당한다. 드라이버는 자신만의 명령 코드를 정의하고, 핸들러를 등록하면 된다.

유저 공간에서 `ioctl(fd, MY_CMD, &data)`를 호출하면, 커널이 해당 fd에 연결된 드라이버의 `.unlocked_ioctl` 핸들러를 호출한다. 따라서 드라이버마다 지원하는 명령 코드와 인자 형식이 다르며, 사용하려면 해당 드라이버의 헤더 파일(예: `<linux/videodev2.h>`, `<drm/drm.h>`)을 참조해야 한다.

<br>

### 사용

`read()`와 `write()`는 데이터 전송만 가능하다. 장치별 특수 제어(설정 변경, 상태 조회 등)는 `ioctl()`을 사용해야 한다. 아래와 같이 역할이 구분된다.

| 시스템 콜 | 역할 | 예시 |
|----------|-----|------|
| `read()`/`write()` | 데이터 입출력 전용 | 시리얼 포트에서 데이터 받기, GPU 메모리 읽기 |
| `ioctl()` | 장치 제어 및 설정 | baud rate 설정, GPU 클럭 주파수 변경, 터미널 크기 조회 |

<br>

아래와 같은 방식으로 사용한다.

```c
// 장치 관련 시스템 콜 사용 예
int fd = open("/dev/ttyS0", O_RDWR);

// 1. ioctl()로 설정 변경 (제어)
struct termios tty;
ioctl(fd, TCGETS, &tty);          // 현재 설정 읽기
tty.c_cflag = B115200 | CS8;      // baud rate 115200, 8bit
ioctl(fd, TCSETS, &tty);          // 설정 적용

// 2. write()로 데이터 전송 (데이터 입출력)
write(fd, "Hello", 5);

// 3. read()로 데이터 수신 (데이터 입출력)
char buffer[100];
read(fd, buffer, 100);
```




<br>

# 유저 라이브러리 (.so)

하드웨어를 쉽게 사용하기 위한 고수준 API를 제공한다.

## 특징

- 주로 C/C++이지만 다른 언어로도 작성 가능
  - Rust: `.so` 생성 가능 (예: `librsvg.so`)
  - Go: `.so` 생성 가능 (cgo 사용, 예: `libnvidia-container-go.so`)
- ELF(Executable and Linkable Format) 포맷의 공유 라이브러리 파일 형식으로, 특정 언어에 종속된 것이 아님
- C ABI(Application Binary Interface)를 준수하면 어떤 언어든 `.so` 생성 가능

## 표준 경로

설치 방식에 따라 여러 경로에 배치된다.

```bash
/lib/            # 부팅과 기본 시스템 동작에 필요한 핵심 라이브러리
/usr/lib/        # 패키지 매니저로 설치한 일반 애플리케이션 라이브러리
/usr/local/lib/  # 사용자가 직접 소스 빌드하여 설치한 라이브러리
/opt/*/lib/      # 독립 패키지(벤더 제공 소프트웨어 등)의 라이브러리
```


> **참고**: 64비트 시스템에서는 `/lib/x86_64-linux-gnu/` 같은 아키텍처별 경로를 사용하기도 한다.

## 캐시 관리

프로그램 실행 시 동적 링커가 필요한 `.so` 파일을 찾아야 한다. 매번 디렉토리를 검색하면 느리므로, `ldconfig`가 라이브러리 경로를 캐시(`/etc/ld.so.cache`)에 미리 저장해둔다.

```bash
# 라이브러리 캐시 재생성 (새 라이브러리 설치 후 필요)
sudo ldconfig
```

> **참고**: 새 라이브러리를 설치한 후 `sudo ldconfig`를 실행해야 시스템이 해당 라이브러리를 인식한다.

## 확인 방법

### ldconfig

`ldconfig -p`로 캐시에 등록된 라이브러리 목록을 확인할 수 있다.

> **참고**: 위에서 보았듯 `ldconfig`의 본래 역할은 캐시 관리지만, `-p` 옵션으로 캐시에 등록된 라이브러리 목록을 확인할 수 있어 유저 라이브러리 조회에 활용된다.

```bash
# 라이브러리 캐시 확인
ldconfig -p

# 특정 라이브러리 검색
ldconfig -p | grep nvidia
```

## 장치별 유저 라이브러리 필요성

### 간단한 장치: 라이브러리 불필요

간단한 장치는 시스템 콜만으로 직접 `/dev/` 파일에 접근할 수 있다. 따라서 유저 라이브러리가 불필요한 경우도 있다.

#### 문자 장치

```bash
# /dev/null, /dev/zero, /dev/random 등
cat /dev/random | head -c 10  # 랜덤 데이터 10바이트 읽기
echo "test" > /dev/null       # 데이터 버리기
```

#### 시리얼 포트

시리얼 포트는 데이터를 한 비트씩 순차적으로 전송하는 통신 인터페이스다.

- **과거 용도**: 마우스, 모뎀, 프린터 연결 (RS-232(Recommended Standard 232) 포트)
- **현재 용도**: 임베디드 시스템 디버깅, 산업용 장비 제어, Arduino/Raspberry Pi 통신

```bash
# 시리얼 포트 장치 파일
/dev/ttyS0       # 하드웨어 시리얼 포트 (COM1)
/dev/ttyUSB0     # USB-to-Serial 어댑터
/dev/ttyACM0     # Arduino 같은 USB CDC(Communications Device Class) 장치

# 시스템 콜만으로 직접 제어 가능 (baud rate 등 설정이 선행되어야 정상 데이터를 볼 수 있다)
stty -F /dev/ttyUSB0 115200  # baud rate 설정
cat /dev/ttyUSB0             # 데이터 읽기
echo "hello" > /dev/ttyUSB0  # 데이터 쓰기

# 터미널 프로그램으로도 접근 가능 (설정을 자동 처리해 줌)
screen /dev/ttyUSB0 115200
```

편의성을 위한 라이브러리(libserial 등)는 존재하지만 필수는 아니다.

<br>

### 복잡한 장치: 라이브러리 필수

장치가 복잡할수록 유저 라이브러리가 필요하다.

| 구분 | 특징 | 예시 |
|-----|------|------|
| 간단한 장치 | 몇 개의 ioctl 명령어면 충분 | `/dev/null`, 시리얼 포트, 일부 센서 |
| 복잡한 장치 | 수천 개의 명령어, 메모리 관리, 복잡한 초기화 필요 | GPU, 사운드카드 |

#### 예시: NVIDIA GPU

NVIDIA GPU는 다음과 같은 복잡한 기능을 제공한다.

- 수천 개의 제어 명령어
- GPU 메모리 관리
- 쉐이더 컴파일
- CUDA 커널 실행

이 모든 것을 애플리케이션이 직접 `ioctl()`로 호출하기는 사실상 불가능하다. `libcuda.so`가 고수준 API를 제공하여 이러한 복잡성을 추상화한다.

<br>

# 배포판별 차이

## 공통 사항: FHS 표준

대부분의 배포판이 FHS 표준을 따르므로 경로는 대체로 동일하다.

- `/lib/modules/$(uname -r)/` - 커널 모듈
- `/dev/` - 장치 파일
- `/lib/`, `/usr/lib/` - 유저 라이브러리

<br>

## 배포판별 차이점

| 항목 | Ubuntu/Debian | RHEL/Rocky/CentOS | Arch Linux |
|-----|---------------|-------------------|------------|
| 커널 버전 suffix | `-generic` | `.el8.x86_64` | `-arch1` |
| 64비트 라이브러리 경로 | `/usr/lib/x86_64-linux-gnu/` | `/usr/lib64/` | `/usr/lib/` |

### 예시

```bash
# Ubuntu
/lib/modules/5.15.0-76-generic/kernel/drivers/gpu/
/usr/lib/x86_64-linux-gnu/

# Rocky/RHEL
/lib/modules/5.15.0-76.el8.x86_64/kernel/drivers/gpu/
/usr/lib64/

# Arch
/lib/modules/5.15.0-arch1/kernel/drivers/gpu/
```

커널 버전이 같으면 배포판이 달라도 기본 경로 구조는 동일하다. 차이는 주로 커널 버전 네이밍과 64비트 라이브러리 경로에서 발생한다.

<br>

# 확인 도구 모음

각 계층별로 사용할 수 있는 확인 명령어를 정리한다.

## 커널 모듈

```bash
# 로드된 모듈 확인
lsmod

# 특정 모듈 검색
lsmod | grep nvidia

# 모듈 상세 정보
modinfo nvidia
```

## 장치 및 하드웨어

| 명령어 | 용도 |
|-------|------|
| `ls -l /dev/` | 장치 파일 목록 |
| `lsblk` | 블록 장치 (디스크, 파티션) |
| `lspci` | PCI 장치 (GPU, 네트워크 카드) |
| `lsusb` | USB 장치 |
| `lscpu` | CPU 정보 |
| `lshw` | 전체 하드웨어 상세 정보 |
| `ip link` | 네트워크 인터페이스 |

<details markdown="1">
<summary>ls -l /dev/ (클릭하여 펼치기)</summary>

```bash
$ ls -l /dev/ | head -30
# 첫 번째 문자: c=문자장치, b=블록장치, d=디렉토리, l=심볼릭링크
# major,minor 번호: 커널이 드라이버를 식별하는 번호
total 0
crw-r--r--. 1 root root  10, 235 Jan 26 21:23 autofs       # c: 문자 장치
drwxr-xr-x. 2 root root      100 Jan 26 21:23 block        # d: 디렉토리
crw--w----. 1 root tty    5,   1 Jan 26 21:23 console      # c: 콘솔 (문자 장치)
lrwxrwxrwx. 1 root root       11 Jan 26 21:23 core -> /proc/kcore  # l: 심볼릭 링크
drwxr-xr-x. 7 root root      140 Jan 26 21:23 disk         # d: 디스크 관련 디렉토리
crw-rw-rw-. 1 root root    1,  7 Jan 26 21:23 full         # c: /dev/full
crw-rw-rw-. 1 root root   10,229 Jan 26 21:23 fuse         # c: FUSE 장치
crw-------. 1 root root  241,  0 Jan 26 21:23 hidraw0      # c: HID 입력 장치
drwxr-xr-x. 4 root root      200 Jan 26 21:23 input        # d: 입력 장치 디렉토리
crw-rw-rw-. 1 root root    1,  3 Jan 26 21:23 null         # c: /dev/null (블랙홀)
...
```

</details>

<details markdown="1">
<summary>lsblk (클릭하여 펼치기)</summary>

```bash
$ lsblk
# NAME: 장치명, MAJ:MIN: major/minor 번호, TYPE: disk/part
NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
sda      8:0    0   64G  0 disk              # 디스크 전체
├─sda1   8:1    0  600M  0 part /boot/efi    # 파티션 1 (EFI)
└─sda3   8:3    0 59.6G  0 part /            # 파티션 3 (루트)
```

</details>

<details markdown="1">
<summary>lspci (클릭하여 펼치기)</summary>

```bash
$ lspci
# 형식: 버스:장치.기능 장치유형: 제조사 모델명
00:00.0 PCI bridge: Intel Corporation 82801 Mobile PCI Bridge (rev f2)
00:01.0 System peripheral: InnoTek Systemberatung GmbH VirtualBox Guest Service
00:03.0 SCSI storage controller: Red Hat, Inc. Virtio 1.0 SCSI (rev 01)  # 스토리지
00:06.0 USB controller: Intel Corporation 7 Series/C210 Series...        # USB
00:08.0 Ethernet controller: Intel Corporation 82540EM Gigabit...        # 네트워크
00:09.0 Ethernet controller: Intel Corporation 82540EM Gigabit...        # 네트워크
```

</details>


<details markdown="1">
<summary>lscpu (클릭하여 펼치기)</summary>

```bash
$ lscpu
# CPU 아키텍처 및 코어 정보
Architecture:             aarch64       # ARM 64비트 (Apple Silicon VM)
  CPU op-mode(s):         64-bit
  Byte Order:             Little Endian
CPU(s):                   4             # 총 CPU 수
  On-line CPU(s) list:    0-3
Vendor ID:                Apple
    Thread(s) per core:   1             # 코어당 스레드 (HT 없음)
    Core(s) per cluster:  4             # 클러스터당 코어
    BogoMIPS:             48.00
NUMA:                     
  NUMA node(s):           1             # NUMA 노드 수
...
```

</details>

<details markdown="1">
<summary>lshw -short (클릭하여 펼치기)</summary>

```bash
$ sudo lshw -short
# H/W path: 하드웨어 계층 경로, Class: 장치 유형
H/W path        Device     Class      Description
=================================================
                           system     Computer
/0                         bus        Motherboard
/0/2                       memory     4GiB System memory     # 메모리
/0/4                       processor                         # CPU
/0/3                       storage    Virtio 1.0 SCSI        # 스토리지 컨트롤러
/0/3/0/0.0.0    /dev/sda   disk       68GB HARDDISK          # 디스크
/0/3/0/0.0.0/1  /dev/sda1  volume     599MiB Windows FAT     # EFI 파티션
/0/3/0/0.0.0/3             volume     59GiB EFI partition    # 루트 파티션
/0/6                       bus        USB xHCI Host          # USB 컨트롤러
/0/6/0/1        input1     input      VirtualBox USB Keyboard
/0/8            enp0s8     network    82540EM Gigabit...     # 네트워크
/0/9            enp0s9     network    82540EM Gigabit...     # 네트워크
```

</details>

<details markdown="1">
<summary>ip link (클릭하여 펼치기)</summary>

```bash
$ ip link
# 인터페이스번호: 이름: <플래그> mtu 값 상태
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN    # 루프백
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: enp0s8: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP  # 물리 NIC
    link/ether aa:bb:cc:dd:ee:01 brd ff:ff:ff:ff:ff:ff           # MAC 주소
3: enp0s9: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP  # 물리 NIC
    link/ether aa:bb:cc:dd:ee:02 brd ff:ff:ff:ff:ff:ff
...
```

</details>

<br>

## 유저 라이브러리

```bash
# 라이브러리 캐시 확인
ldconfig -p

# 특정 라이브러리 검색
ldconfig -p | grep nvidia

# 라이브러리 캐시 재생성
sudo ldconfig
```

`ldconfig`는 공유 라이브러리 캐시를 관리한다. `/etc/ld.so.cache`에 바이너리 형태로 캐시를 저장하여 프로그램 실행 시 라이브러리를 빠르게 찾을 수 있게 한다.

> **참고**: `/etc/ld.so.cache`는 바이너리 파일이므로 `cat`으로 직접 읽으면 깨진 문자가 출력된다. 내용을 확인하려면 `ldconfig -p`를 사용해야 한다.

<br>

# 정리

리눅스 디바이스 드라이버의 핵심 개념을 정리하면 다음과 같다.

| 개념 | 설명 |
|-----|------|
| **Everything is a file** | Unix/Linux에서 장치도 파일처럼 다룬다 |
| **3계층 구조** | 유저 라이브러리 → 장치 파일 → 커널 모듈 → 하드웨어 |
| **문자 장치 (c)** | 블록 레이어/페이지 캐시를 거치지 않는 바이트 스트림 (터미널, GPU, 시리얼 포트) |
| **블록 장치 (b)** | 블록 단위 랜덤 액세스 (디스크, SSD) |
| **시스템 콜** | `open()`, `read()`, `write()`, `ioctl()`로 커널과 통신 |
| **커널 모듈 경로** | `/lib/modules/$(uname -r)/kernel/` |
| **장치 파일 경로** | `/dev/` |
| **유저 라이브러리 경로** | `/lib/`, `/usr/lib/`, `/usr/local/lib/` |

> 참고: 이 3계층 구조를 컨테이너 환경에서 주입하는 방식(OCI Runtime Hook, CDI)은 [컨테이너 장치 주입]({% post_url 2026-02-02-CS-Container-Device-Injection %})을 참고하자.

<br>

# 참고 자료

추후 더 확인해 보면 좋을 참고 자료 목록을 정리해 둔다.

- [Linux Kernel Documentation - devices.txt](https://www.kernel.org/doc/Documentation/admin-guide/devices.txt) - 장치 번호 목록
- [Filesystem Hierarchy Standard](https://refspecs.linuxfoundation.org/FHS_3.0/fhs/index.html) - FHS 표준 문서
- [Linux Device Drivers, 3rd Edition](https://lwn.net/Kernel/LDD3/) - O'Reilly 무료 공개 서적

<br>
