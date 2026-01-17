---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 1-1. 환경 구성"
hidden: true
excerpt: "Ansible Control Node 설정과 SSH 키 기반 인증 구성을 통해 Kubespray 실습 환경을 준비한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Kubespray를 사용하기 위한 Ansible 실습 환경 구성**이다.

- Vagrant 기반 4대의 가상머신 환경 구성 (Ubuntu 3대, Rocky Linux 1대)
- Control Node에 Ansible 설치
- SSH 키 기반 인증 설정으로 Managed Node 접근 구성
- Python 환경 확인

Ansible은 SSH를 통해 여러 서버를 동시에 관리할 수 있는 자동화 도구다. Kubespray는 Ansible Playbook 기반으로 Kubernetes 클러스터를 배포하는 도구이므로, Ansible 환경 구성이 선행되어야 한다. 실습에서는 멀티 OS 환경(Ubuntu + Rocky Linux)에서 Ansible이 어떻게 동작하는지 확인한다.

<br>

# 실습 환경

가시다님이 구성해 놓은 실습 환경의 상세 스펙은 다음과 같다. Vagrant를 이용해 4대의 머신 환경을 구성한다. Ansible 실습 용도라 메모리는 1.5GB 정도면 된다. 

**tnode3만 Rocky Linux를 사용하는 이유는 Ansible의 멀티 OS 지원 능력을 실습하기 위함**이다. 실제 운영 환경에서는 Debian 계열(Ubuntu)과 RHEL 계열(Rocky Linux, CentOS)이 혼재하는 경우가 많으며, Ansible은 단일 Playbook으로 이러한 이질적인 환경을 통합 관리할 수 있다.

| Node | OS | Kernel | vCPU | Memory | Disk | NIC2 IP | 관리자 계정 | (기본) 일반 계정 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| server | Ubuntu 24.04 | 6.8.0 | 2 | 1.5GB | 30GB | 10.10.1.10 | root / qwe123 | vagrant / qwe123 |
| tnode1 | 상동 | 상동 | 2 | 1.5GB | 30GB | 10.10.1.11 | root / qwe123 | vagrant / qwe123 |
| tnode2 | 상동 | 상동 | 2 | 1.5GB | 30GB | 10.10.1.12 | root / qwe123 | vagrant / qwe123 |
| tnode3 | Rocky Linux 9 | 5.14.0 | 2 | 1.5GB | 60GB | 10.10.1.13 | root / qwe123 | vagrant / qwe123 |

- [Vagrantfile](https://github.com/gasida/vagrant-lab/blob/main/ansible/Vagrantfile)
- [init_cfg.sh](https://github.com/gasida/vagrant-lab/blob/main/ansible/init_cfg.sh): Ubuntu 24.04  가상 머신 설정
- [init_cfg2.sh](https://github.com/gasida/vagrant-lab/blob/main/ansible/init_cfg2.sh): Rocky Linux 가상 머신 설정

<br>

# 환경 구성

## Vagrant 실행

```bash
# (host) $
vagrant up
```

Vagrantfile에 정의된 4대의 가상 머신(server, tnode1, tnode2, tnode3)을 시작한다.

<br>

## Server 노드 접속

```bash
# (host) $
vagrant ssh server
```

- Control Node 역할을 할 server 노드에 SSH로 접속
- root 계정으로 자동 로그인됨 (init_cfg.sh에서 설정)
- 접속 시 시스템 정보 출력:
  - 시스템 로드, 디스크/메모리 사용량
  - NIC 정보: eth0 (10.0.2.15), eth1 (10.10.1.10)

> **주의**: 운영 환경에서의 root 사용
>
> **보안상 root 계정으로 직접 작업하는 것은 권장되지 않는다.** 실제 운영 환경에서는 일반 사용자로 접속 후 `sudo`를 통해 권한을 상승하는 방식을 사용해야 한다. 이 실습에서는 편의를 위해 root 계정을 사용하지만, 프로덕션 환경에서는 다음을 권장한다:
> - 일반 사용자 계정으로 SSH 접속
> - `become: true` 설정으로 필요 시에만 권한 상승
> - SSH 키 기반 인증 + sudo 권한 제한

<br>

## 시스템 환경 확인

### 1. 계정 및 권한 확인

```bash
# (server) #
whoami
id
```

```
root
uid=0(root) gid=0(root) groups=0(root)
```

- `whoami`: 현재 로그인한 사용자 이름 확인
- `id`: 사용자 ID(UID), 그룹 ID(GID), 소속 그룹 정보 확인
- root 계정으로 실행 중임을 확인 (Ansible 실행에는 root 권한이 필요하지 않지만, 실습 편의상 root 사용)

### 2. 커널 버전 확인

```bash
# (server) #
uname -r
```

```
6.8.0-86-generic
```

- `uname`: 시스템 정보 출력
  - `-r`: 커널 릴리즈 버전 확인
  - `-a`: 모든 시스템 정보 확인 (호스트명, 커널 버전, 아키텍처 등)
- **확인 이유**: 특정 커널 버전에서만 지원되는 기능이나 모듈이 있을 수 있음 (예: eBPF, cgroups v2 등)

### 3. 호스트 정보 확인

```bash
# (server) #
hostnamectl
```

```
Static hostname: server
Operating System: Ubuntu 24.04.3 LTS
         Kernel: Linux 6.8.0-86-generic
   Architecture: arm64
```

- **hostnamectl**: systemd 기반 시스템의 호스트명, OS 정보, 커널, 아키텍처 등을 한 번에 확인
- Static hostname이 `server`로 설정되어 있음 (Ansible Inventory에서 호스트 구분에 사용)

> **참고**: Static Hostname이란?
> 
> Linux에서 호스트명은 세 가지 유형이 있다:
> - **Static hostname**: `/etc/hostname`에 저장된 영구적인 호스트명. 재부팅해도 유지됨
> - **Transient hostname**: 커널이 관리하는 임시 호스트명. DHCP나 mDNS에 의해 변경될 수 있음
> - **Pretty hostname**: 사람이 읽기 쉬운 자유 형식의 호스트명 (예: "Eraser's Workstation")
> 
> Ansible에서는 주로 Static hostname을 사용하여 호스트를 식별한다.

### 4. 프로세스 모니터링

```bash
# (server) #
htop
```
![ansible-02-htop]({{site.url}}/assets/images/ansible-02-htop.png){: .align-center width="600"}
- **htop**: 실시간 프로세스 모니터링 도구 (top의 개선 버전)
- CPU, 메모리 사용률, 실행 중인 프로세스 목록을 시각적으로 확인
- 실습 환경에서 시스템 부하를 모니터링하는 용도

### 5. 메모리 사용량 확인

```bash
# (server) #
free -h
```

```
               total        used        free      shared  buff/cache   available
Mem:           1.3Gi       232Mi       507Mi       4.8Mi       675Mi       1.1Gi
Swap:          3.7Gi          0B       3.7Gi
```
- **free**: 시스템 메모리 사용량 확인
  - `-h`: Human-readable (사람이 읽기 쉬운 단위로 표시, MB/GB)
- **출력 의미**:
  - `total`: 전체 메모리 (1.3GB - Vagrantfile에서 설정한 1.5GB와 유사)
  - `used`: 사용 중인 메모리 (232MB)
  - `free`: 완전히 비어있는 메모리 (507MB)
  - `buff/cache`: 버퍼/캐시로 사용 중인 메모리 (675MB, 필요시 해제 가능)
  - `available`: 실제 사용 가능한 메모리 (1.1GB, free + 해제 가능한 cache 포함)
  - `Swap`: 스왑 메모리 (3.7GB, 현재 미사용)

### 6. 블록 디바이스 확인

```bash
# (server) #
lsblk
```

```
NAME                      MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
sda                         8:0    0   64G  0 disk 
├─sda1                      8:1    0    1G  0 part /boot/efi
├─sda2                      8:2    0    2G  0 part /boot
└─sda3                      8:3    0 60.9G  0 part 
  └─ubuntu--vg-ubuntu--lv 252:0    0 30.5G  0 lvm  /
```

- **lsblk**: 블록 디바이스(디스크, 파티션) 트리 구조 확인
- **출력 분석**:
  - `sda`: 64GB 디스크 (Vagrantfile에서 설정)
  - `sda1`: EFI 부트 파티션 (1GB)
  - `sda2`: 부트 파티션 (2GB)
  - `sda3`: LVM 물리 볼륨 (60.9GB)
    - `ubuntu-vg-ubuntu-lv`: 논리 볼륨 30.5GB가 `/`에 마운트

### 7. 파일시스템 사용량 확인

```bash
# (server) #
df -hT
```

```
Filesystem                        Type      Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv ext4       30G  5.3G   24G  19% /
/dev/sda2                         ext4      2.0G  103M  1.7G   6% /boot
/dev/sda1                         vfat      1.1G  6.4M  1.1G   1% /boot/efi
```

- **df**: 디스크 파일시스템 사용량 확인
  - `-h`: Human-readable (KB/MB/GB 단위)
  - `-T`: 파일시스템 타입 표시 (ext4, vfat, tmpfs 등)
- **주요 마운트 포인트**:
  - `/`: 루트 파일시스템 (30GB 중 5.3GB 사용, 19%)
  - `/boot`: 부트 파일 저장 (2GB 중 103MB 사용)
  - `/boot/efi`: EFI 부트로더 저장

### 8. 네트워크 인터페이스 확인

```bash
# (server) #
ip -c addr
```

```
1: lo: <LOOPBACK,UP,LOWER_UP> ...
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
    inet 10.0.2.15/24 scope global dynamic eth0
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
    inet 10.10.1.10/24 scope global eth1
```
- **ip**: 네트워크 인터페이스 정보 확인
  - `-c`: 컬러 출력 (가독성 향상)
  - `addr`: IP 주소 정보 표시
- **NIC 정보**:
  - `lo`: 루프백 인터페이스 (127.0.0.1)
  - `eth0`: NAT 네트워크 (10.0.2.15) - 외부 인터넷 연결용
  - `eth1`: 내부 네트워크 (10.10.1.10) - Ansible 통신용 (Managed Node와 통신)

<br>

## 네트워크 연결 확인

### hosts 파일 확인

```bash
# (server) #
cat /etc/hosts
```

```
10.10.1.10 server
10.10.1.11 tnode1
10.10.1.12 tnode2
10.10.1.13 tnode3
```

- `/etc/hosts`: 호스트명과 IP 주소 매핑 정보
- init_cfg.sh 스크립트에서 자동으로 설정: [init_cfg.sh#L27](https://github.com/gasida/vagrant-lab/blob/main/ansible/init_cfg.sh#L27)
- Ansible에서 호스트명으로 Managed Node 접근 가능

### Managed Node 통신 테스트

```bash
# (server) #
for i in {1..3}; do ping -c 1 tnode$i; done
```

```
64 bytes from tnode1 (10.10.1.11): icmp_seq=1 ttl=64 time=1.04 ms
64 bytes from tnode2 (10.10.1.12): icmp_seq=1 ttl=64 time=0.790 ms
64 bytes from tnode3 (10.10.1.13): icmp_seq=1 ttl=64 time=0.728 ms
```

- **ping**: ICMP 패킷을 보내 네트워크 연결 상태 확인
  - `-c 1`: 1개의 패킷만 전송 후 종료
- **확인 결과**: 모든 Managed Node(tnode1~3)와 통신 가능 (0% packet loss)
- **응답 시간**: 1ms 이하로 매우 빠름 (같은 호스트 내 VM 간 통신)

<br>

# Ansible 설치

## Python 버전 확인

```bash
# (server) #
python3 --version
```

```
Python 3.12.3
```

- **확인 이유**: Ansible은 Python으로 작성되어 Python이 필수
- **버전 요구사항**:
  - ansible-core 2.17+는 Control Node에 Python 3.10+ 필요
  - Python 3.12.3은 요구사항을 충족함

## PPA 저장소 추가

### 1. software-properties-common 설치

```bash
# (server) #
apt install software-properties-common -y
```

- **software-properties-common**: PPA(Personal Package Archive) 추가를 위한 유틸리티 패키지
- `add-apt-repository` 명령어를 제공함
- 이미 설치되어 있어서 추가 설치 없음

### 2. Ansible PPA 추가

```bash
# (server) #
add-apt-repository --yes --update ppa:ansible/ansible
```

- **PPA (Personal Package Archive)**: Ubuntu의 비공식 소프트웨어 저장소
- **ppa:ansible/ansible**: Ansible 공식 PPA (최신 버전 제공)
- **옵션**:
  - `--yes`: 자동으로 yes 응답 (대화형 프롬프트 건너뜀)
  - `--update`: 저장소 추가 후 자동으로 `apt update` 실행
- Ubuntu 기본 저장소는 구버전 Ansible을 제공할 수 있으므로, 최신 버전을 위해 공식 PPA 사용

## Ansible 설치

```bash
# (server) #
apt install ansible -y
```

```
The following NEW packages will be installed:
  ansible ansible-core python3-paramiko python3-winrm ...
```

- **설치되는 주요 패키지**:
  - `ansible`: Ansible 전체 패키지 (컬렉션 포함)
  - `ansible-core`: Ansible 핵심 엔진 (Playbook 실행, 모듈 관리)
  - `python3-paramiko`: SSH 통신을 위한 Python 라이브러리

# 설치 확인

## Ansible 버전 정보

```bash
# (server) #
ansible --version
```

```
ansible [core 2.19.5]
  config file = /etc/ansible/ansible.cfg
  configured module search path = ['/root/.ansible/plugins/modules', ...]
  ansible python module location = /usr/lib/python3/dist-packages/ansible
  ansible collection location = /root/.ansible/collections:...
  executable location = /usr/bin/ansible
  python version = 3.12.3
  jinja version = 3.1.2
  pyyaml version = 6.0.1
```

- **ansible [core 2.19.5]**: Ansible Core 버전
- **config file**: 설정 파일 경로 (`/etc/ansible/ansible.cfg`)
- **configured module search path**: 모듈 검색 경로
- **ansible python module location**: Ansible Python 패키지 위치
- **ansible collection location**: Collection 저장 경로
- **executable location**: `ansible` 명령어 위치 (`/usr/bin/ansible`)
- **python/jinja/pyyaml version**: 의존성 라이브러리 버전

<br>

### 설치 경로 확인

```bash
# (server) #
# 사용자 정의 모듈 경로 (아직 비어있음)
ls /root/.ansible
```

```
tmp
```

```bash
# (server) #
# Ansible Core Python 모듈 확인
ls /usr/lib/python3/dist-packages/ansible
```

```
cli/          executor/     modules/      playbook/     utils/
collections/  galaxy/       module_utils/ plugins/      vars/
config/       inventory/    parsing/      template/     ...
```

- `/root/.ansible`: 사용자별 Ansible 데이터 저장소 (처음 설치 시 비어있는 것이 정상)
- `/usr/lib/python3/dist-packages/ansible`: Ansible의 실제 Python 코드
  - `modules/`: 빌트인 모듈들 (apt, copy, service 등)
  - `plugins/`: 플러그인들 (connection, filter, callback 등)
  - `playbook/`: Playbook 실행 엔진
  - `cli/`: 명령행 인터페이스 (ansible, ansible-playbook 등)

<br>

## Ansible 설정 파일

### 전역 설정 파일 확인

```bash
# (server) #
cat /etc/ansible/ansible.cfg
```

```
# Since Ansible 2.12 (core):
# To generate an example config file (a "disabled" one with all default settings, commented out):
#               $ ansible-config init --disabled > ansible.cfg
#
# Also you can now have a more complete file by including existing plugins:
# ansible-config init --disabled -t all > ansible.cfg
```

- `/etc/ansible/ansible.cfg`: 기본 설정 파일이 거의 비어있음 (주석만 있음)
- Ansible 2.12+부터는 설정 파일을 자동 생성하는 명령어 제공
- **기본 설정 파일 생성 방법**:
  ```bash
  # 기본 설정만 (주석 처리된 형태)
  ansible-config init --disabled > ansible.cfg
  
  # 모든 플러그인 설정 포함
  ansible-config init --disabled -t all > ansible.cfg
  ```

### 사용 가능한 설정 목록 확인

```bash
# (server) #
ansible-config list
```

```
ACTION_WARNINGS:
  default: true
  description: By default, Ansible will issue a warning...
  env:
  - name: ANSIBLE_ACTION_WARNINGS
  ini:
  - key: action_warnings
    section: defaults
  type: boolean
... (수백 개의 설정 항목)
```

- **ansible-config list**: Ansible에서 사용 가능한 모든 설정 항목 출력
- 각 설정 항목은 다음 정보를 포함:
  - `default`: 기본값
  - `env`: 환경변수 이름
  - `ini`: 설정 파일 섹션/키 이름
  - `type`: 데이터 타입

<br>

## 작업 디렉토리 생성

```bash
# (server) #
mkdir my-ansible
cd my-ansible
```

- Ansible Playbook과 Inventory를 작성할 작업 디렉토리 생성
- 프로젝트별로 별도 디렉토리를 만들어 관리하는 것이 좋음
- 이 디렉토리에 `ansible.cfg`를 생성하면 전역 설정(`/etc/ansible/ansible.cfg`)보다 우선 적용됨

<br>

# 호스트 설정

Ansible은 SSH로 Managed Node에 접속한다. **SSH 키 기반 인증**을 설정하면 비밀번호 입력 없이 자동으로 로그인할 수 있다.

## SSH 공개키 인증 원리

SSH 공개키 인증은 **비대칭 암호화(공개키 암호화)** 방식을 사용한다. 

### 키 쌍의 특징

```
Private Key (비밀키)  ←→  Public Key (공개키)
     id_rsa                id_rsa.pub
     
수학적으로 쌍을 이루며, 하나로 암호화한 것은 다른 하나로만 복호화 가능
```

**핵심 특성:**
- Private key로 암호화 → Public key로만 복호화 가능
- Public key로 암호화 → Private key로만 복호화 가능
- Public key로부터 Private key 역산 불가능 (사실상)

### 인증 과정

```
  Control Node                              Managed Node
  (id_rsa)                                  (authorized_keys)
      |                                          |
      |  1. SSH Connection Request               |
      |  ---------------------------------------->
      |     "Login as root"                      |
      |                                          |
      |                        Find public key in authorized_keys
      |                        Encrypt challenge with public key
      |                                          |
      |  2. Challenge (encrypted)                |
      |  <----------------------------------------
      |                                          |
      |  Decrypt with                            |
      |  private key                             |
      |                                          |
      |  3. Response (decrypted challenge)       |
      |  ---------------------------------------->
      |                                          |
      |                              Verify response
      |                                          |
      |  4. Authentication Success               |
      |  <----------------------------------------
      |                                          |
```

**단계별 설명:**
1. Client가 서버에 SSH 접속 요청
2. Server가 `authorized_keys`에서 해당 사용자의 공개키를 찾아, 그 공개키로 챌린지(랜덤 데이터)를 암호화해서 Client에 전송
3. Client가 자신의 Private key로 챌린지를 복호화해서 응답
4. Server가 응답을 검증하여 인증 성공

### 보안상의 장점

**Private Key(비밀키):**
- 절대 외부로 전송되지 않음
- 본인만 가지고 있음
- Control Node에만 보관

**Public Key(공개키):**
- 마음껏 배포해도 됨
- 여러 서버에 등록 가능
- Managed Node에 복사
- 유출되어도 비밀키를 역산할 수 없으므로 안전

<br>

## SSH 키 설정

이제 SSH 키를 생성하고 Managed Node에 배포해 보자.

### 1. Control Node에서 SSH 키 생성

**키 생성 전:**

```bash
# (server) #
tree ~/.ssh
```

```
/root/.ssh
└── authorized_keys

1 directory, 1 file
```

**키 생성:**

```bash
# (server) #
ssh-keygen -t rsa -N "" -f /root/.ssh/id_rsa
```

```
Generating public/private rsa key pair.
Your identification has been saved in /root/.ssh/id_rsa
Your public key has been saved in /root/.ssh/id_rsa.pub
The key fingerprint is:
SHA256:waAwtC4JjrrH382ZcgzS3M2urXqppUXBmrWZF64oXs4 root@server
```

- **ssh-keygen**: SSH 키 쌍 생성 도구
  - `-t rsa`: RSA 알고리즘 사용 (기본 3072비트)
  - `-N ""`: 비밀번호(passphrase) 없이 생성 (자동화를 위해)
  - `-f /root/.ssh/id_rsa`: 키 파일 경로 지정

**키 생성 후:**

```bash
# (server) #
tree ~/.ssh
```

```
/root/.ssh
├── authorized_keys
├── id_rsa          # Private key (비밀키)
└── id_rsa.pub      # Public key (공개키)

1 directory, 3 files
```

<br>

### 2. Managed Node에 공개키 복사

생성한 공개키(`id_rsa.pub`)를 모든 Managed Node에 복사한다.

```bash
# (server) #
for i in {1..3}; do sshpass -p 'qwe123' ssh-copy-id -o StrictHostKeyChecking=no root@tnode$i; done
```

```
/usr/bin/ssh-copy-id: INFO: Source of key(s) to be installed: "/root/.ssh/id_rsa.pub"
/usr/bin/ssh-copy-id: INFO: 1 key(s) remain to be installed

Number of key(s) added: 1

Now try logging into the machine, with: "ssh 'root@tnode1'"
```

**명령어 설명:**
- **sshpass**: 비밀번호를 자동으로 입력해주는 도구
  - `-p 'qwe123'`: root 계정의 비밀번호 전달 (초기 접속 시 필요)
- **ssh-copy-id**: 공개키를 원격 서버의 `authorized_keys`에 자동으로 추가하는 유틸리티
  - 내부적으로 `~/.ssh/id_rsa.pub` 내용을 읽어서 원격의 `~/.ssh/authorized_keys`에 추가
  - `-o StrictHostKeyChecking=no`: SSH 옵션 전달
- **StrictHostKeyChecking=no**: 
  - 처음 접속하는 호스트일 때 "Are you sure you want to continue connecting?" 프롬프트 건너뜀
  - `~/.ssh/known_hosts`에 호스트 키를 자동으로 추가
  - **실습 환경에서만 사용**, 운영 환경에서는 보안 위험

**ssh-copy-id의 동작:**
```
1. Control Node의 ~/.ssh/id_rsa.pub 읽기
2. Managed Node에 SSH로 접속 (비밀번호 인증)
3. Managed Node의 ~/.ssh/authorized_keys 파일에 공개키 추가
4. 권한 설정 (chmod 600 authorized_keys)
```

> 참고: `ssh-copy-id` 없이 수동 설정
>
> ```bash
> # Control Node에서
> cat ~/.ssh/id_rsa.pub | ssh root@tnode1 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
> ```

<br>

### 3. 공개키 복사 확인

```bash
# (server) #
for i in {1..3}; do echo ">> tnode$i <<"; ssh tnode$i cat ~/.ssh/authorized_keys; echo; done
```

```
>> tnode1 <<
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB...== root@server

>> tnode2 <<
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB...== root@server

>> tnode3 <<
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB...== root@server
```

- 모든 Managed Node의 `~/.ssh/authorized_keys`에 Control Node의 공개키(`id_rsa.pub`)가 등록됨
- 키 끝의 `root@server`는 키를 생성한 사용자와 호스트 정보 (식별용)

<br>

### 4. SSH 키 기반 접속 테스트

```bash
# (server) #
for i in {1..3}; do echo ">> tnode$i <<"; ssh tnode$i hostname; echo; done
```

```
>> tnode1 <<
tnode1

>> tnode2 <<
tnode2

>> tnode3 <<
tnode3
```

- **비밀번호 입력 없이** SSH 접속 성공
- 각 노드에서 `hostname` 명령을 실행하여 정상 동작 확인
- 이제 Ansible이 이 SSH 연결을 사용하여 자동화 작업 수행 가능

<br>

### 5. Managed Node의 Python 버전 확인

```bash
# (server) #
for i in {1..3}; do echo ">> tnode$i <<"; ssh tnode$i python3 -V; echo; done
```

```
>> tnode1 <<
Python 3.12.3

>> tnode2 <<
Python 3.12.3

>> tnode3 <<
Python 3.9.21
```

- **Python 버전 차이 확인:**
  - **tnode1, tnode2 (Ubuntu 24.04)**: Python 3.12.3 (Ubuntu 24.04 기본 버전)
  - **tnode3 (Rocky Linux 9)**: Python 3.9.21 (Rocky Linux 9 기본 버전)
- 노드 간 버전 차이
  - 이유: OS마다 기본 제공 Python 버전이 다름
    - Ubuntu 24.04 (2024년 4월 릴리즈) → 최신 Python 3.12
    - Rocky Linux 9 (2022년 7월 릴리즈) → 안정성 중시로 Python 3.9 (RHEL 9 표준)
  - 버전 차이가 다르더라도 크게 문제되지 않음
    - Ansible 요구사항: Managed Node는 Python 2.7 또는 3.5+ 지원
    - Python 3.9.21은 요구사항을 충족하며, Rocky Linux 9의 기본 Python 버전

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Vagrant 환경 구성**: 4대의 가상 머신(server, tnode1~3) 프로비저닝 완료
2. **Ansible 설치**: Control Node(server)에 Ansible 2.19.5 설치 완료
3. **SSH 키 기반 인증**: 모든 Managed Node와 비밀번호 없이 SSH 접속 가능
4. **Python 환경 확인**: Control Node와 Managed Node 모두 Ansible 요구사항 충족

<br>

이번 실습을 통해 Kubespray를 사용하기 위한 Ansible 실습 환경을 구성했다. SSH 공개키 인증 원리와 Control Node에서 Managed Node로의 접근 설정 방법을 이해할 수 있었다. 멀티 OS 환경(Ubuntu + Rocky Linux)에서도 Ansible이 동일하게 동작함을 확인했다.

<br> 

다음 글에서는 Inventory 작성과 Ad-hoc 명령어 실행을 통해 Ansible의 기본 사용법을 익혀본다.