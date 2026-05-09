---
title:  "[Linux] Everything is a File 철학"
excerpt: "Unix/Linux의 Everything is a File 철학에 대해 알아보자."
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
---

<br>

리눅스에 대해 공부하다 보면 여기저기서 "Everything is a file"이라는 말을 듣게 된다. 장치 드라이버, 소켓, 프로세스 등 시스템 프로그래밍이나 인프라 관련 내용을 다룰 때마다 등장하는 이 철학은 Unix/Linux를 이해하는 핵심 개념이다. 이 글에서는 "Everything is a file" 철학의 의미와 장점, 그리고 현실적인 한계를 살펴본다.

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

## "파일"의 여러 의미

"Everything is a file"은 **설계 철학**이지, 모든 것이 완벽하게 파일로만 표현된다는 의미는 아니다.

"파일"이라는 용어는 맥락에 따라 다른 레이어를 가리킨다:

1. **파일 시스템 경로** (namespace) → **"Everything is a file"의 철학적 범위**
   - 모든 리소스가 파일 시스템 경로를 가짐
   - `/dev/null`, `/proc/cpuinfo`, `/sys/class/net/...` 등

2. **파일 디스크립터** (fd abstraction) → **Linux의 실제 구현 범위**
   - 모든 리소스가 파일 디스크립터(`fd`)로 조작 가능
   - 소켓, `epoll`, `signalfd`, `timerfd` 등 경로 없이 `fd`만으로 존재하는 것도 포함

3. **바이트 스트림 인터페이스** (data model) → **기본 파일 연산의 범위**
   - `open()`, `read()`, `write()`, `close()` 등의 단순한 인터페이스
   - 순차적 데이터 스트림 읽기/쓰기

"Everything is a file"은 본래 1번(경로)을 지향하는 철학이고, Linux는 2번(fd)으로 이를 더 확장했다. 하지만 3번(바이트 스트림)만으로는 모든 리소스를 표현하기 어렵기 때문에, [뒤에서 살펴볼](#한계와-확장) 전용 시스템 콜로 보완한다.

<br>

## 동일한 방식으로 접근

하드웨어 장치, 프로세스 정보, 네트워크 소켓, 파이프 등 거의 모든 시스템 리소스를 파일로 추상화하여, 모두 같은 방식 방식(`cat`, `echo`)으로 다룬다.

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

# 파일 종류

Linux에는 7가지 파일 종류가 있다. `ls -l` 출력의 첫 번째 문자로 파일 타입을 구분할 수 있다.

| 기호 | 종류 | 설명 | 예시 |
|-----|------|------|------|
| `-` | 일반 파일 | 텍스트, 바이너리, 이미지 등 | `-rw-r--r-- file.txt` |
| `d` | 디렉토리 | 폴더 | `drwxr-xr-x /home/` |
| `l` | 심볼릭 링크(symbolic link) | 다른 파일을 가리키는 링크 | `lrwxrwxrwx rtc -> rtc0` |
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
| `/sys/` | 커널 2.6부터 도입된 가상 파일 시스템. <br>장치와 드라이버 정보를 계층적으로 제공하며, 일부 설정은 쓰기도 가능. <br>PCI/PCIe, USB 등 버스에 연결된 장치도 `/sys/bus/` 아래에 노출 |


> **참고: 가상 파일 시스템(virtual filesystem)**
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

# 구체적인 예시

위 장점들이 실제로 어떻게 활용되는지 살펴보자.


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

# 디스크 I/O 스케줄러 변경
echo none > /sys/block/sda/queue/scheduler

# PCI/PCIe 장치 목록
ls /sys/bus/pci/devices/
```

> **참고: 디스크 I/O 스케줄러**
>
> I/O 스케줄러는 디스크에 전달할 읽기/쓰기 요청의 순서를 결정한다. `none`(커널 4.11+ blk-mq)은 재정렬 없이 요청을 그대로 장치에 전달하는 스케줄러로, NVMe SSD처럼 장치 자체에 내부 스케줄링이 있는 경우에 적합하다. 레거시 단일 큐 시절에는 같은 역할을 `noop`이라 불렀으나, 커널 4.20 이후 완전히 제거되었다.

> **참고: `/sys/bus/pci/`와 PCIe**
>
> PCI(Peripheral Component Interconnect)는 병렬 버스 규격이고, PCIe(PCI Express)는 그 후속 직렬 버스 규격이다. 현대 장치(GPU, NVMe, NIC 등)는 대부분 PCIe를 사용하지만, Linux 커널은 PCI 서브시스템이라는 이름으로 PCI와 PCIe 장치를 모두 관리한다. PCIe가 소프트웨어 호환성을 유지하도록 설계되었기 때문에, sysfs에서는 `/sys/bus/pci/` 경로 아래에 PCIe 장치도 함께 노출된다.
>
> 여기서 NVMe(Non-Volatile Memory Express)는 PCIe 위에서 동작하는 **스토리지 전용 프로토콜**로, 기존 SATA 버스의 AHCI(Advanced Host Controller Interface) 프로토콜을 대체한다. PCIe가 버스(데이터를 어떻게 전송할지)라면, NVMe는 프로토콜(스토리지 데이터를 어떻게 읽고 쓸지)이다. NVMe SSD가 SATA SSD보다 빠른 이유는 PCIe의 높은 대역폭을 플래시 메모리의 병렬성에 맞게 활용하도록 처음부터 설계되었기 때문이다.

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

[앞에서 살펴본 것처럼](#파일의-여러-의미), "Everything is a File" 철학은 **파일 시스템 경로**(1번)로 모든 리소스를 표현하는 것을 지향하고, Linux는 이를 **파일 디스크립터**(2번)로 더 확장했다. 하지만 실제 구현에서는 아래와 같은 한계가 있다.

## 바이트 스트림 인터페이스로 부족한 경우

**바이트 스트림 인터페이스**(3번)만으로는 모든 리소스를 파일로 추상화하기에 부족함이 있다.

파일은 본질적으로 **순차적 데이터 스트림**이다. 다음과 같은 작업은 `read()`/`write()`로 표현하기 어렵다.

### 1. 복잡한 장치 제어

GPU 클럭 주파수를 변경하거나 터미널의 baud rate를 설정하는 것은 "데이터를 읽고 쓰는" 작업이 아니라 **장치의 동작 방식을 바꾸는 제어 명령**이다. 바이트 스트림에는 "이것은 데이터가 아니라 명령이다"라는 구분이 없으므로, `ioctl()` 같은 별도 시스템 콜이 필요하다.

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


### 2. 구조화된 데이터 교환

네트워크 인터페이스의 IP 주소를 읽으려면 `struct ifreq`라는 C 구조체를 커널과 주고받아야 한다. 바이트 스트림은 **"어디서 어디까지가 하나의 필드인지" 구조를 알 수 없으므로**, `ioctl()`을 통해 구조체 포인터를 직접 전달한다. 네트워크 라우팅 테이블이나 복잡한 드라이버 설정도 마찬가지다.

```c
// 네트워크 인터페이스 설정
struct ifreq ifr;
ioctl(sockfd, SIOCGIFADDR, &ifr);  // IP 주소 읽기
```

<br>

## 파일 경로 추상화로 부족한 경우: 네트워크

위의 두 경우는 "fd는 있지만 `read()`/`write()`만으로는 부족하다"는 이야기였다. 네트워크는 한 단계 더 근본적인 문제가 있다. **하나의 파일 경로로 리소스를 식별하는 것 자체가 불가능**하다.

대부분의 하드웨어 장치는 `/dev/` 아래에 장치 파일이 있다. `/dev/sda`(디스크), `/dev/nvidia0`(GPU) 등을 `open()`하면 된다. 그런데 네트워크 인터페이스는 `/dev/eth0`라는 파일이 존재하지 않는다. 커널 내부에서 `struct net_device`로 관리되며, 유저 공간에서는 `socket()` 시스템 콜을 통해서만 접근한다.

핵심 이유는 **다중화(multiplexing)**다. 디스크나 GPU는 장치와 프로세스의 관계가 비교적 단순하지만, 하나의 NIC(네트워크 인터페이스 카드)은 수천 개의 동시 연결을 처리한다. 각 연결은 (프로토콜, 출발 IP, 출발 포트, 도착 IP, 도착 포트)의 5-tuple로 식별되는데, 이것을 하나의 파일 경로로 표현할 수 없다.

```text
/dev/eth0 ← 프로세스 A (TCP 10.0.0.1:8080 → 10.0.0.2:443)
          ← 프로세스 B (TCP 10.0.0.1:9090 → 10.0.0.3:80)
          ← 프로세스 C (UDP 10.0.0.1:5353 → 224.0.0.251:5353)
          ← ... 수천 개의 동시 연결
```

`open("/dev/eth0")`를 한다고 해도, "어떤 프로토콜로, 어디에, 어떤 포트로 연결할지"를 파일 경로만으로는 지정할 수 없다. BSD(4.2BSD, 1983)는 이 문제를 `socket()` + `bind()` + `connect()`라는 별도 시스템 콜 체계로 해결했고, Linux가 이를 계승했다.

```c
int sock = socket(AF_INET, SOCK_STREAM, 0);  // 프로토콜 지정
bind(sock, &addr, sizeof(addr));              // 로컬 주소/포트 지정
connect(sock, &remote_addr, sizeof(remote_addr));  // 원격 주소/포트 지정

// 연결 수립 후에는 일반 파일처럼 read/write 가능
write(sock, "Hello", 5);
read(sock, buffer, sizeof(buffer));
```

연결이 수립된 이후에는 fd를 통해 `read()`/`write()`를 쓸 수 있으므로, 파일 디스크립터 차원에서는 "Everything is a file" 철학을 부분적으로 따르고 있다. 또한 네트워크 인터페이스가 완전히 파일 세계 밖에 있는 것은 아니다. 인터페이스의 상태 정보는 `/sys/class/net/`에서 파일로 확인할 수 있다.

```bash
cat /sys/class/net/eth0/address     # MAC 주소
cat /sys/class/net/eth0/operstate   # 인터페이스 상태 (up/down)
cat /sys/class/net/eth0/speed       # 링크 속도 (Mbps)
```

> **참고: Plan 9의 네트워크 파일 인터페이스**
>
> Unix의 후속 연구 OS인 Plan 9에서는 네트워크도 파일로 표현하는 데 성공했다. `/net/tcp/clone`을 열면 새 연결 번호 N을 반환하고, `/net/tcp/N/ctl`에 `connect 10.0.0.2!80`을 써서 연결하고, `/net/tcp/N/data`로 데이터를 송수신하는 방식이다. 디렉토리 계층으로 각 연결을 분리하여 다중화 문제를 해결했다. 기술적으로 가능하다는 것을 증명했지만, Linux가 등장할 때 BSD 소켓이 이미 POSIX 표준으로 굳어진 상태여서 그 모델을 계승했다.

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

> **참고: ioctl()의 필요성과 한계**
>
> `read()`/`write()`는 순차적 데이터 전송만 담당한다. 장치 제어(클럭 변경, 상태 조회 등)처럼 데이터 입출력이 아닌 연산이 필요할 때 `ioctl()`을 사용한다. 하나의 시그니처(`ioctl(fd, request, ...)`)에 정수 명령 코드를 넘겨 모든 제어 연산을 처리하는 범용 시스템 콜이다. 구조와 드라이버별 구현 방식은 [리눅스 디바이스 드라이버 구조]({% post_url 2026-02-01-CS-Linux-Device-Driver %}#ioctl)를 참고하자.
>
> 실용적 해결책이지만, Unix 철학과는 거리가 있다:
>
> - 명령 코드가 표준화되지 않음 (각 드라이버가 자체 정의하므로 같은 숫자가 다른 의미를 가질 수 있음)
> - `read()`/`write()`만큼 직관적이지 않음
> - 보안 검증이 어려움 (임의의 명령을 전달할 수 있어 권한 검사가 각 구현에 의존)
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

macOS는 BSD 기반 Unix 계열이므로 "Everything is a file" 철학을 부분적으로 따른다. `/dev`는 존재하지만, Linux의 `/proc`와 `/sys`는 제공하지 않는다. 시스템 정보 조회는 `sysctl` 커맨드와 API로 대체한다.

```bash
# macOS에서 /dev는 존재
ls /dev/disk*
# disk0   disk0s1  disk0s2  disk1  disk1s1  ...

# /proc는 존재하지 않음
ls /proc
# ls: /proc: No such file or directory

# 시스템 정보는 sysctl로 조회
sysctl hw.memsize        # 메모리 크기
# hw.memsize: 34359738368

sysctl hw.ncpu           # CPU 코어 수
# hw.ncpu: 10

sysctl kern.hostname     # 호스트명
# kern.hostname: my-macbook.local
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

앞에서 살펴본 것처럼 `/proc`, `/sys`는 시스템 메트릭(CPU 사용률, 메모리, 네트워크 통계 등)을 파일로 노출한다. 프로덕션 환경에서 이러한 메트릭을 수집하고 모니터링할 때는 Prometheus, node-exporter, cAdvisor 같은 전문 도구를 사용하는 것이 일반적이다. 이들 도구가 내부적으로 `/proc`, `/sys`를 파싱하여 메트릭을 수집하고, 알림·대시보드·장기 저장 등을 제공하기 때문이다.

하지만 **디버깅, 경량 모니터링, 커스텀 도구 개발** 등 특정 상황에서는 `/proc`, `/sys`를 직접 읽는 방식을 고려해볼 수 있다.

## cgroup 정보 읽기

cgroup(Control Groups)은 프로세스 그룹의 리소스 사용(CPU, 메모리, I/O 등)을 제한·격리하는 커널 기능이다. 컨테이너 런타임이 내부적으로 cgroup을 사용하므로, 컨테이너 내부에서 CPU/메모리 제한을 파일로 직접 확인할 수 있다.

아래는 cgroup v1 기준 예시다. cgroup v2(커널 5.x+ 기본)에서는 경로가 다르다: `cpu.cfs_quota_us` → `cpu.max`, `memory.limit_in_bytes` → `memory.max`.

```go
package main

import (
    "fmt"
    "os"
    "strconv"
    "strings"
)

// CPU 쿼터 읽기 (cgroup v1 경로)
func readCPUQuota() (int64, error) {
    data, err := os.ReadFile("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    if err != nil {
        return 0, err
    }
    return strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
}

// 메모리 제한 읽기 (cgroup v1 경로)
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

## GPU 상태 확인

컨테이너에서 GPU 상태도 파일로 읽을 수 있다. 단, sysfs 경로는 드라이버에 따라 다르다.

```go
// AMD GPU VRAM 사용량 확인 (amdgpu 드라이버 전용)
func getAMDGPUMemory(deviceID int) (int64, error) {
    path := fmt.Sprintf("/sys/class/drm/card%d/device/mem_info_vram_used", 
                        deviceID)
    data, err := os.ReadFile(path)
    if err != nil {
        return 0, err
    }
    return strconv.ParseInt(strings.TrimSpace(string(data)), 10, 64)
}

// hwmon 센서를 통한 온도 확인 (AMD, Intel 등 hwmon 지원 장치)
// NVIDIA GPU는 hwmon을 노출하지 않으므로 nvidia-smi 또는 NVML을 사용해야 한다
func getGPUTemperature(hwmonID int) (int, error) {
    path := fmt.Sprintf("/sys/class/hwmon/hwmon%d/temp1_input", hwmonID)
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

> **참고**: 컨테이너에 GPU를 주입하는 방법은 [컨테이너 장치 주입]({% post_url 2026-02-02-CS-Container-Device-Injection %})을 참고하자.

<br>

이와 같이 "Everything is a File" 철학에 근거해 시스템 정보가 파일로 노출되므로, 특정 상황에서는 이렇게 노출된 `/proc`, `/sys` 파일 등을 직접 읽는 방식도 고려해볼 수 있다.

<br>
