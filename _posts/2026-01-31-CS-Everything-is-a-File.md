---
title:  "[CS] Everything is a File - Unix/Linux의 핵심 철학"
excerpt: "리눅스에서 왜 모든 것을 파일처럼 다루는지, 그 철학과 한계를 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Unix
  - File
  - System Programming
  - 리눅스
  - 유닉스
  - 파일
---

<br>

리눅스 환경에서 업무를 하거나, 리눅스에 대해 공부하다 보면 여기저기서 "Everything is a file"이라는 말을 듣게 된다. 장치 드라이버, 소켓, 프로세스 등 시스템 프로그래밍이나 인프라 관련 내용을 다룰 때마다 등장하는 이 철학은 Unix/Linux를 이해하는 핵심 개념이다. 이 글에서는 "Everything is a file" 철학의 의미와 장점, 그리고 현실적인 한계를 살펴본다.

<br>

# TL;DR

- **Everything is a file**: Unix/Linux에서 모든 리소스를 파일처럼 다룬다
- **파일 종류 7가지**: 일반 파일, 디렉토리, 심볼릭 링크, 문자/블록 장치, 소켓, 파이프
- **주요 경로**: `/dev` (장치), `/proc` (프로세스/시스템), `/sys` (커널/드라이버)
- **장점**: 단순성, 일관성, 유연성, 투명성
- **한계**: 기본 파일 연산(`read`/`write`)만으로는 복잡한 작업 표현 어려움
- **실용적 해결**: `ioctl()`, `socket()`, `mmap()` 등 전용 시스템 콜로 보완

<br>

# Everything is a file

## 기본 개념

Unix/Linux에서는 **"Everything is a file"** 철학을 따른다. 모든 리소스를 파일처럼 다룬다는 의미다.

일반적인 파일뿐만 아니라 다음도 모두 파일처럼 접근한다:
- **하드웨어 장치**: GPU, 디스크, 키보드, 마우스 등
- **프로세스**: 실행 중인 프로그램의 정보
- **네트워크**: 소켓을 통한 통신
- **시스템 정보**: CPU, 메모리, 네트워크 상태 등

<br>

## "파일"의 두 가지 의미

"Everything is a file"은 **설계 철학**이지, 모든 것이 완벽하게 파일로만 표현된다는 의미는 아니다.

실제로 "파일"이라는 용어는 맥락에 따라 다르게 사용된다:

1. **파일 추상화** (넓은 의미) → **"Everything is a file"의 철학적 범위**
   - 파일 디스크립터(`fd`)로 접근 가능한 모든 것
   - 소켓, 장치, 파이프, 프로세스 등 포함
   - 

2. **기본 파일 연산** (좁은 의미) → **실제로 표현 가능한 범위**
   - `open()`, `read()`, `write()`, `close()` 등의 단순한 인터페이스
   - 순차적 데이터 스트림 읽기/쓰기

<br>

철학적으로는 1번(파일 추상화)을 추구하지만, 실제 구현에서는 2번(기본 파일 연산)만으로 모든 작업을 표현할 수 없다.

<br>

## 동일한 방식으로 접근
하드웨어 장치, 프로세스 정보, 네트워크 소켓, 파이프 등 거의 모든 시스템 리소스를 파일로 추상화하여, 모두 같은 방식 방식(`cat`, `echo`)으로 다룰 수 있다는 것을 알 수 있다.

```bash
# 1. 일반 파일 읽기
cat /tmp/file.txt

# 2. 장치 파일 읽기 (동일한 방식!)
cat /dev/random  # 랜덤 데이터 생성 장치

# 3. 프로세스 정보 읽기 (동일한 방식!)
cat /proc/cpuinfo  # CPU 정보

# 4. 시스템 설정 읽기/쓰기 (동일한 방식!)
cat /sys/class/net/eth0/address  # 네트워크 MAC 주소
echo 1 > /proc/sys/net/ipv4/ip_forward  # IP 포워딩 활성화
```

<br>

# 파일 시스템 계층

리눅스 파일 시스템은 **FHS(Filesystem Hierarchy Standard)**를 따른다. 이 표준 덕분에 배포판(Ubuntu, Rocky, Arch 등)이 달라도 주요 파일들의 위치가 대체로 동일하다.

```bash
/
├── bin/      # 필수 명령어
├── dev/      # 장치 파일
├── etc/      # 설정 파일
├── lib/      # 필수 라이브러리, 커널 모듈
├── proc/     # 프로세스/시스템 정보 (가상)
├── sys/      # 커널/장치 설정 (가상)
├── usr/      # 사용자 프로그램, 라이브러리
└── var/      # 가변 데이터 (로그 등)
```

<br>

이 중 "Everything is a file" 철학과 관련된 주요 경로는 다음과 같다.

| 경로 | 설명 |
|-----|------|
| `/dev/` | 하드웨어 장치에 접근하는 인터페이스. <br>실제 장치 파일이 위치 |
| `/proc/` | 커널이 런타임에 생성하는 가상 파일 시스템. <br>프로세스 정보(`/proc/[pid]/`)와 시스템 정보(`/proc/cpuinfo`, `/proc/meminfo` 등) 제공 |
| `/sys/` | 커널 2.6부터 도입된 가상 파일 시스템. <br>장치와 드라이버 정보를 계층적으로 제공하며, 일부 설정은 쓰기도 가능 |

<br>

# 파일 종류

Linux에는 7가지 파일 종류가 있다. `ls -l` 출력의 첫 번째 문자로 파일 타입을 구분할 수 있다.

| 기호 | 종류 | 설명 | 예시 |
|-----|------|------|------|
| `-` | 일반 파일 | 텍스트, 바이너리, 이미지 등 | `-rw-r--r-- file.txt` |
| `d` | 디렉토리 | 폴더 | `drwxr-xr-x /home/` |
| `l` | 심볼릭 링크 | 다른 파일을 가리키는 링크 | `lrwxrwxrwx rtc -> rtc0` |
| `c` | 문자 장치 | 한 바이트씩 스트림 방식 전송 | `crw-rw-rw- /dev/null` |
| `b` | 블록 장치 | 블록 단위 랜덤 액세스 | `brw-rw---- /dev/sda` |
| `s` | 소켓 | 프로세스 간 네트워크 통신 | `srwxrwxrwx /run/systemd/notify` |
| `p` | 파이프 | 프로세스 간 데이터 전달 (FIFO) | Named pipe |

<br>

## 파일 타입 확인

`ls -l` 명령으로 파일 타입을 확인할 수 있다.

```bash
ls -l /dev/ | head -20

# 출력 예시
brw-rw---- 1 root disk      8,   0 Feb  3 10:00 sda        # 블록 장치
brw-rw---- 1 root disk      8,   1 Feb  3 10:00 sda1       # 블록 장치 (파티션)
crw-rw-rw- 1 root tty       1,   3 Feb  3 10:00 null       # 문자 장치
crw-rw-rw- 1 root tty       1,   9 Feb  3 10:00 urandom    # 문자 장치
lrwxrwxrwx 1 root root          4 Feb  3 10:00 rtc -> rtc0 # 심볼릭 링크
srwxrwxrwx 1 root root          0 Feb  3 10:00 log        # 소켓
```


<br>

# 철학의 장점

이러한 철학의 장점은 다음과 같다.

- **단순성**: 파일을 다루는 방법(`open`, `read`, `write`, `close`)만 알면 모든 것을 다룰 수 있음
- **일관성**: 일반 파일, 하드웨어 장치, 프로세스, 네트워크 등을 **동일한 인터페이스**로 접근
- **유연성**: 파이프(`|`)와 리다이렉션(`>`, `<`)으로 쉽게 조합 가능
- **투명성**: `/proc`, `/sys`를 통해 시스템 내부를 쉽게 관찰하고 디버깅 가능

<br>

# 구체적인 예시

위 장점들이 실제로 어떻게 활용되는지 살펴보자.

> **참고: 가상 파일 시스템**
>
> `/proc`와 `/sys`는 디스크에 실제로 저장되지 않는다. 커널이 런타임에 메모리에서 동적으로 생성하며, 파일을 읽을 때마다 커널이 현재 상태를 조회해서 내용을 반환한다. `ls -l`로 보면 크기가 0으로 표시되지만, `cat`으로 읽으면 내용이 있다.
>
> ```bash
> # /proc - 프로세스/시스템 정보
> ls -l /proc
> dr-xr-xr-x.   9 root  root  0  1        # 프로세스 디렉토리 (PID 1)
> dr-xr-xr-x.   9 root  root  0  1126     # 프로세스 디렉토리
> -r--r--r--.   1 root  root  0  cpuinfo  # CPU 정보
> -r--r--r--.   1 root  root  0  meminfo  # 메모리 정보
> -r--r--r--.   1 root  root  0  modules  # 로드된 모듈
>
> # /sys - 커널/장치 설정
> ls -l /sys
> drwxr-xr-x.   2 root  root  0  block    # 블록 장치
> drwxr-xr-x.  41 root  root  0  bus      # 버스 (PCI, USB 등)
> drwxr-xr-x.  57 root  root  0  class    # 장치 클래스
> drwxr-xr-x.  14 root  root  0  devices  # 장치 트리
> drwxr-xr-x. 158 root  root  0  module   # 커널 모듈 파라미터
> ```

<br>

## 1. 프로세스 정보 (`/proc`)

`/proc`은 이 철학을 가장 잘 보여주는 예시다. 실제 디스크에 저장되지 않고 커널 메모리의 정보를 파일 형태로 노출한다.

### 프로세스별 정보

각 프로세스는 `/proc/[PID]/` 디렉토리로 표현된다.

```bash
# PID 1234 프로세스의 정보
ls /proc/1234/
# cmdline   - 실행 명령어
# status    - 프로세스 상태 (메모리, CPU 등)
# fd/       - 열린 파일 디스크립터들
# maps      - 메모리 맵
# environ   - 환경변수
# cwd       - 현재 작업 디렉토리 (심볼릭 링크)
# exe       - 실행 파일 경로 (심볼릭 링크)

# 실행 명령어 확인
cat /proc/1234/cmdline

# 프로세스가 열고 있는 파일들
ls -l /proc/1234/fd/

# 환경변수 확인 (null로 구분됨)
cat /proc/1234/environ | tr '\0' '\n'
```

<br>

### 시스템 전체 정보

`/proc`의 루트에는 시스템 전체 정보가 파일로 제공된다.

```bash
cat /proc/cpuinfo     # CPU 정보
cat /proc/meminfo     # 메모리 정보
cat /proc/uptime      # 가동 시간
cat /proc/loadavg     # 시스템 부하
cat /proc/net/dev     # 네트워크 인터페이스 통계
cat /proc/modules     # 로드된 커널 모듈
```

<br>

## 2. 시스템 설정 (`/sys`)

커널과 하드웨어 설정도 파일로 접근한다.

```bash
# CPU 주파수 확인
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq

# 디스크 스케줄러 변경
echo noop > /sys/block/sda/queue/scheduler

# PCI 장치 목록
ls /sys/bus/pci/devices/
```

<br>

## 3. 장치 파일 (`/dev`)

하드웨어 장치에 직접 접근한다.

```bash
# 랜덤 데이터 생성
dd if=/dev/urandom of=random.bin bs=1M count=10

# 디스크 직접 읽기
dd if=/dev/sda of=backup.img bs=4M

# 시리얼 포트 통신
echo "AT" > /dev/ttyS0  # 모뎀 명령
cat /dev/ttyS0          # 응답 읽기
```

<br>

# 한계와 확장

[앞에서 설명](#파일의-두-가지-의미)했듯이, 철학은 **파일 추상화**(넓은 의미)를 지향하지만 **기본 파일 연산**(좁은 의미)만으로는 모든 작업을 표현하기 어렵다.

## 기본 파일 연산으로 부족한 경우

파일은 본질적으로 **순차적 데이터 스트림**이다. 다음과 같은 작업은 `read()`/`write()`로 표현하기 어렵다.

### 1. 복잡한 장치 제어

```c
// GPU 클럭 주파수 설정
// read/write로는 불가능, ioctl() 필요
ioctl(fd, GPU_SET_CLOCK, &clock_freq);

// 터미널 설정 변경
struct termios settings;
ioctl(fd, TCGETS, &settings);  // 현재 설정 읽기
settings.c_cflag = B115200;     // baud rate 변경
ioctl(fd, TCSETS, &settings);   // 설정 적용
```

<br>

### 2. 구조화된 데이터 교환

네트워크 라우팅 테이블, 복잡한 드라이버 설정 등은 단순 텍스트로 표현하기 어렵다.

```c
// 네트워크 인터페이스 설정
struct ifreq ifr;
ioctl(sockfd, SIOCGIFADDR, &ifr);  // IP 주소 읽기
```

<br>

### 3. 양방향 통신 패턴

소켓은 파일 디스크립터를 사용하지만, 연결 설정은 별도 시스템 콜이 필요하다.

```c
int sock = socket(AF_INET, SOCK_STREAM, 0);  // 소켓 생성
bind(sock, &addr, sizeof(addr));              // 주소 바인딩
listen(sock, 5);                              // 리스닝 시작
int client = accept(sock, NULL, NULL);        // 연결 수락

// 이후 read/write 사용 가능
write(client, "Hello", 5);
```

<br>

## 성능 최적화

기본 파일 연산으로 **표현은 가능**하지만, **성능이 중요한 경우** 전용 시스템 콜이 더 효율적이다.

대용량 데이터는 `read()`/`write()` 대신 메모리 매핑(`mmap()`)이 훨씬 빠르다.

```c
// read()로 가능하지만 느림
char buffer[1024];
while (read(fd, buffer, sizeof(buffer)) > 0) {
    process_data(buffer);
}

// mmap()으로 직접 메모리 접근 (훨씬 빠름)
void *data = mmap(NULL, file_size, PROT_READ, 
                  MAP_PRIVATE, fd, 0);
process_data(data);  // read() 없이 접근
```

<br>

## 설계 트레이드오프

Unix/Linux는 다음과 같은 균형을 택했다.

- **원칙**: 가능하면 파일 인터페이스 사용 (단순성)
- **현실**: 부족하면 전용 시스템 콜 추가 (실용성)

<br>

> **참고: ioctl()의 필요성**
>
> `ioctl()`은 복잡한 장치 제어를 위한 **실용적 해결책**이지만, Unix 철학과는 거리가 있다.
>
> - 명령어가 표준화되지 않음 (장치마다 제각각)
> - `read()`/`write()`만큼 직관적이지 않음
> - 보안 검증이 어려움 (임의의 명령 전달)
>
> 이것이 Linux가 `/proc`, `/sys`를 통해 가능한 것들은 파일 인터페이스로 노출시키려는 이유다. 예를 들어 CPU 주파수는 `ioctl()` 대신 `/sys/devices/system/cpu/*/cpufreq/*`로 제어할 수 있다.

<br>

# 다른 OS의 접근 방식

## Windows

Windows는 이 철학을 따르지 않는다.

- 파일: `CreateFile()`, `ReadFile()`, `WriteFile()`
- 네트워크: `socket()`, `send()`, `recv()` (별도)
- 프로세스: `CreateProcess()`, `TerminateProcess()` (별도)
- 레지스트리: `RegOpenKey()`, `RegQueryValue()` (별도)

각 리소스마다 전용 API를 사용한다.

<br>

## macOS

macOS는 Unix 계열이므로 "Everything is a file" 철학을 따른다. 다만 일부 확장이 있다.

```bash
# macOS도 /dev, /proc 사용
ls /dev/disk*
```

<br>

# 정리

"Everything is a file"은 Unix/Linux의 **핵심 설계 철학**이다.

- **파일 추상화**: 모든 리소스를 파일 디스크립터로 접근
- **동일한 인터페이스**: `open()`, `read()`, `write()`, `close()`로 일관성 유지
- **실용적 확장**: 부족한 부분은 `ioctl()`, `socket()` 등으로 보완

<br>

이 철학은 **목표**이지 완벽한 현실은 아니다. 하지만 가능한 한 그렇게 만들려는 노력이 리눅스의 `/proc`, `/sys` 같은 가상 파일 시스템으로 나타난다.

<br>

시스템 프로그래밍, 장치 드라이버, 네트워크 프로그래밍, 인프라 관리 등 다양한 영역에서 이 철학을 이해하면 리눅스를 훨씬 쉽게 다룰 수 있다.

<br>

# 참고: 특정 상황에서의 활용

프로덕션 환경에서는 Prometheus, node-exporter, cAdvisor 같은 전문 모니터링 도구를 사용하는 것이 권장된다. 하지만 **디버깅, 경량 모니터링, 커스텀 도구 개발** 등 특정 상황에서는 `/proc`, `/sys`를 직접 읽는 방식을 고려해볼 수 있다.

## cgroup 정보 읽기

컨테이너 내부에서 CPU/메모리 제한을 파일로 확인하는 예시다.

```go
package main

import (
    "fmt"
    "os"
    "strconv"
    "strings"
)

// CPU 쿼터 읽기 (파일로!)
func readCPUQuota() (int64, error) {
    data, err := os.ReadFile("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    if err != nil {
        return 0, err
    }
    return strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
}

// 메모리 제한 읽기 (파일로!)
func readMemoryLimit() (int64, error) {
    data, err := os.ReadFile("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if err != nil {
        return 0, err
    }
    return strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
}

func main() {
    quota, _ := readCPUQuota()
    fmt.Printf("CPU Quota: %d μs\n", quota)
    
    limit, _ := readMemoryLimit()
    fmt.Printf("Memory Limit: %d bytes\n", limit)
}
```

<br>

## GPU 메모리 사용량 확인

컨테이너에서 GPU 상태도 파일로 읽을 수 있다.

```go
// GPU 메모리 사용량 확인 (파일로!)
func getGPUMemory(deviceID int) (int64, error) {
    path := fmt.Sprintf("/sys/class/drm/card%d/device/mem_info_vram_used", 
                        deviceID)
    data, err := os.ReadFile(path)
    if err != nil {
        return 0, err
    }
    return strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
}

// NVIDIA GPU 온도 확인 (파일로!)
func getGPUTemperature(deviceID int) (int, error) {
    path := fmt.Sprintf("/sys/class/hwmon/hwmon%d/temp1_input", deviceID)
    data, err := os.ReadFile(path)
    if err != nil {
        return 0, err
    }
    temp, err := strconv.Atoi(strings.TrimSpace(string(data)))
    return temp / 1000, err  // milli-celsius → celsius
}
```

<br>

## 실전 활용 예시

### Kubernetes Pod에서 리소스 모니터링

Pod 내부에서 파일을 읽어 리소스 사용량을 계산하는 예시다.

```go
// Pod의 현재 CPU 사용률 계산
func getCurrentCPUUsage() (float64, error) {
    // /proc/stat 파일 읽기
    data, err := os.ReadFile("/proc/stat")
    if err != nil {
        return 0, err
    }
    // CPU 시간 파싱 후 사용률 계산
    // ...
}

// 네트워크 인터페이스 통계
func getNetworkStats(iface string) (rx, tx int64, err error) {
    // /proc/net/dev 파일 읽기
    data, err := os.ReadFile("/proc/net/dev")
    if err != nil {
        return 0, 0, err
    }
    // 파싱 후 rx/tx 바이트 반환
    // ...
}
```

<br>

### 장치 주입 확인

컨테이너에 GPU가 제대로 주입되었는지 파일로 확인할 수 있다.

```bash
# 컨테이너 내부에서
ls -l /dev/nvidia*
# crw-rw-rw- 1 root root 195,   0 Feb  3 10:00 /dev/nvidia0
# crw-rw-rw- 1 root root 195, 255 Feb  3 10:00 /dev/nvidiactl

# GPU 정보 확인 (파일로!)
cat /proc/driver/nvidia/gpus/0000:01:00.0/information
```

> **참고**: 컨테이너에 GPU를 주입하는 방법은 [[Dev] 컨테이너 장치 주입](/dev/Dev-Container-Device-Injection/)을 참고하자.

<br>

이와 같이 "Everything is a File" 철학에 근거해 시스템 정보가 파일로 노출되므로, 특정 상황에서는 이렇게 노출된 `/proc`, `/sys` 파일 등을 직접 읽는 방식도 고려해볼 수 있다.

<br>

# 관련 글

- [[CS] 리눅스 디바이스 드라이버 구조](/cs/CS-Linux-Device-Driver/) - 장치 파일과 드라이버의 3계층 구조
- [[Dev] 컨테이너 장치 주입](/dev/Dev-Container-Device-Injection/) - 컨테이너에 GPU 등 장치를 주입하는 방법

<br>