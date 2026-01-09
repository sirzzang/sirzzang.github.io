---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 1. Prerequisites"
excerpt: "VirtualBox와 Vagrant를 사용하여 Kubernetes 실습을 위한 4대의 가상 머신(jumpbox, server, node-0, node-1)을 구성하고 초기 설정을 완료해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1
---

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **실습용 가상 머신 준비**다. [Kubernetes the Hard Way 튜토리얼의 Prerequisites 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/01-prerequisites.md)를 따라 진행한다.

- VirtualBox와 Vagrant를 이용한 VM 프로비저닝
- Debian 12 기반 실습 환경 초기 설정
- Private network를 통한 VM 간 통신 구성


![kubernetes-the-hard-way-cluster-structure-1]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-1.png)

<br>

# 실습 환경

## 시스템 요구사항

Kubernetes the Hard Way 튜토리얼은 다음 조건을 만족하는 환경이 필요하다.

> 4 ARM64 or AMD64 based virtual or physical machines connected to the same network

- **4개의 ARM64 또는 AMD64 가상/물리 머신**이 필요하며, 각 머신은 **Debian 12 (bookworm)**를 실행해야 함
- 모든 머신이 **같은 네트워크**에 연결되어 있어야 함
- **최소 사양**: RAM 16GB 이상, 4코어 이상 (로컬 환경에서 구동할 수 없다면 AWS 등의 클라우드 환경을 고려해야 함)

<br>

## 머신 구성

실습에 사용할 4대의 머신은 다음과 같이 구성된다.

- **jumpbox**: 관리용 호스트 (Administration host)
- **server**: Kubernetes Control Plane 노드
- **node-0, node-1**: Kubernetes Worker 노드 (Data Plane)

<br>

## 실습 환경 상세

가시다님이 구성해 놓은 실습 환경의 상세 스펙은 다음과 같다. Vagrant를 이용해 4대의 머신 환경을 구성하며, Booting OS로는 Vagrant 카탈로그에서 제공하는 `bento/debian-12` 이미지를 사용한다. 각 머신은 VirtualBox 기반으로 동작하며, private network를 통해 서로 통신한다.

| NAME | Description | CPU | RAM | NIC1 | NIC2 | HOSTNAME |
| --- | --- | --- | --- | --- | --- | --- |
| jumpbox | Administration host | 2 | 1536 MB | 10.0.2.15 | **192.168.10.10** | **jumpbox** |
| server | Kubernetes server | 2 | 2GB | 10.0.2.15 | **192.168.10.100** | server.kubernetes.local **server** |
| node-0 | Kubernetes worker  | 2 | 2GB | 10.0.2.15 | **192.168.10.101** | node-0.kubernetes.local **node-0** |
| node-1 | Kubernetes worker  | 2 | 2GB | 10.0.2.15 | **192.168.10.102** | node-1.kubernetes.local **node-1** |


### Vagrant NIC1, NIC2 의미

Vagrant VM은 기본적으로 최소 2개의 네트워크 인터페이스(NIC)를 가진다.

1. 첫 번째 NIC: NIC1 (eth0 또는 enp0s3)
  - **용도**: Vagrant 관리 전용 (SSH 접속, 프로비저닝 등)
  - **네트워크 타입**: NAT
  - **IP 주소**: 모든 Vagrant VM에서 동일하게 `10.0.2.15` 사용
  - **특징**
    - Vagrant가 VM을 제어하기 위해 예약된 인터페이스
    - 사용자가 직접 설정하거나 변경할 수 없음
    - VM 간 통신에는 사용되지 않음
    
2. 두 번째 NIC 이후: NIC2 (eth1 또는 enp0s8)
  - **용도**: 실제 네트워크 통신 (VM 간 통신, 호스트-VM 통신 등)
  - **네트워크 타입**: Vagrantfile에서 정의한 설정 (private_network, public_network 등)
  - **IP 주소**: 사용자가 지정한 IP (예: 192.168.10.10, 192.168.10.100 등)

<br>

NAT 네트워크 특성상 각 VM은 독립된 NAT 환경 안에 있기 때문에, 여러 Vagrant VM이 모두 첫 번째 NIC에서 `10.0.2.15`라는 동일한 IP를 가질 수 있지만 서로 충돌하지 않는다. 두 번째 네트워크부터는 사용자가 정의한 네트워크 설정에 따라 IP가 할당되며, 이 인터페이스를 통해 VM들 간의 실제 통신이 이루어진다. 

이러한 구조 덕분에 Vagrant는 VM을 안정적으로 관리하면서도, 사용자는 두 번째 NIC 이후로 원하는 네트워크 구성을 자유롭게 설정할 수 있다.

<br>

실습에서는 `192.168.10.0/24` 대역의 private network를 사용하여 VM들이 서로 통신할 수 있도록 구성할 것이다.

<br>

# 필요 도구 설치

가상 머신을 실행하기 위한 도구를 설치한다.

## VirtualBox 설치

VirtualBox는 Oracle에서 개발한 오픈소스 가상화 소프트웨어다. 하나의 물리 머신에서 여러 개의 가상 머신을 실행할 수 있게 해준다.

```bash
# (host) $
# --cask: GUI 애플리케이션 설치를 위한 Homebrew 옵션
brew install --cask virtualbox 

# 설치 버전 확인
VBoxManage --version
```

**실행 결과:**
```
7.2.4r170995
```

> 참고: VirtualBox 버전
> 설치한 VirtualBox는 7.2.4버전이다.
> - 2024년 12월에 릴리즈된 최신 버전
> - M1/M2/M3 등 Apple Silicon 지원 개선
> - 주요 버그 수정 및 성능 개선
> - 상세 변경사항: [Changelog](https://www.virtualbox.org/wiki/Changelog)

<br>

## Vagrant 설치

Vagrant는 HashiCorp에서 개발한 가상 환경 프로비저닝 및 관리 도구다. 코드 기반으로 가상 머신을 정의하고 배포할 수 있다.
- 가상 머신 환경을 코드로 정의하고 재현 가능한 개발 환경 구축
- VirtualBox, VMware, Docker 등 다양한 프로바이더 지원
- 하나의 설정 파일(Vagrantfile)로 여러 대의 VM을 일관되게 관리
- 초기 설정 스크립트 자동 실행 (프로비저닝)
- 팀원들과 동일한 개발 환경 공유 가능

```bash
# (host) $
# Vagrant 설치
brew install --cask vagrant

# 설치 버전 확인
vagrant version
```

**실행 결과:**
```
Installed Version: 2.4.9
Latest Version: 2.4.9
 
You're running an up-to-date version of Vagrant!
```

<br>

# 구성

작업용 디렉터리를 생성하고 필요한 파일을 다운로드한다. Vagrantfile과 초기 설정 스크립트가 다운로드된다.

```bash
# (host) $
# 작업용 디렉터리 생성
mkdir k8s-hardway
cd k8s-hardway

# Vagrantfile, init_cfg.sh 파일 다운로드
# -O: 원본 파일 이름 유지하며 다운로드
curl -O https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-hardway/Vagrantfile
curl -O https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-hardway/init_cfg.sh
```

- Vagrantfile: [gasida/vagrant-lab/k8s-hardway/Vagrantfile](https://github.com/gasida/vagrant-lab/blob/main/k8s-hardway/Vagrantfile)
- init_cfg.sh: [gasida/vagrant-lab/k8s-hardway/init_cfg.sh](https://github.com/gasida/vagrant-lab/blob/main/k8s-hardway/init_cfg.sh)

<br>

## Vagrantfile

실습에 사용할 가상 환경 구성 파일로, 총 4개의 가상 머신을 정의한다. 각 VM은 동일한 베이스 이미지(`bento/debian-12`)를 사용하며, VirtualBox 프로바이더를 통해 실행된다.

```ruby
# Base Image : https://portal.cloud.hashicorp.com/vagrant/discover/bento/debian-12
BOX_IMAGE = "bento/debian-12"
BOX_VERSION = "202510.26.0"

Vagrant.configure("2") do |config|
# jumpbox
  config.vm.define "jumpbox" do |subconfig|
    subconfig.vm.box = BOX_IMAGE
    subconfig.vm.box_version = BOX_VERSION
    subconfig.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Hardway-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "jumpbox"
      vb.cpus = 2
      vb.memory = 1536 # 2048 2560 3072 4096
      vb.linked_clone = true
    end
    subconfig.vm.host_name = "jumpbox"
    subconfig.vm.network "private_network", ip: "192.168.10.10"
    subconfig.vm.network "forwarded_port", guest: 22, host: 60010, auto_correct: true, id: "ssh"
    subconfig.vm.synced_folder "./", "/vagrant", disabled: true
    subconfig.vm.provision "shell", path: "init_cfg.sh"
  end

# server
  config.vm.define "server" do |subconfig|
    subconfig.vm.box = BOX_IMAGE
    subconfig.vm.box_version = BOX_VERSION
    subconfig.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Hardway-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "server"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
    subconfig.vm.host_name = "server"
    subconfig.vm.network "private_network", ip: "192.168.10.100"
    subconfig.vm.network "forwarded_port", guest: 22, host: 60100, auto_correct: true, id: "ssh"
    subconfig.vm.synced_folder "./", "/vagrant", disabled: true
    subconfig.vm.provision "shell", path: "init_cfg.sh"
  end

# node-0
  config.vm.define "node-0" do |subconfig|
    subconfig.vm.box = BOX_IMAGE
    subconfig.vm.box_version = BOX_VERSION
    subconfig.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Hardway-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "node-0"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
    subconfig.vm.host_name = "node-0"
    subconfig.vm.network "private_network", ip: "192.168.10.101"
    subconfig.vm.network "forwarded_port", guest: 22, host: 60101, auto_correct: true, id: "ssh"
    subconfig.vm.synced_folder "./", "/vagrant", disabled: true
    subconfig.vm.provision "shell", path: "init_cfg.sh"
  end

# node-1
  config.vm.define "node-1" do |subconfig|
    subconfig.vm.box = BOX_IMAGE
    subconfig.vm.box_version = BOX_VERSION
    subconfig.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Hardway-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "node-1"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
    subconfig.vm.host_name = "node-1"
    subconfig.vm.network "private_network", ip: "192.168.10.102"
    subconfig.vm.network "forwarded_port", guest: 22, host: 60102, auto_correct: true, id: "ssh"
    subconfig.vm.synced_folder "./", "/vagrant", disabled: true
    subconfig.vm.provision "shell", path: "init_cfg.sh"
  end

end
```

### 주요 설정 항목
1. 베이스 이미지: `bento/debian-12` (버전 202510.26.0)
2. 프로바이더 설정 (VirtualBox)
  - `vb.name`: VirtualBox에서 표시될 VM 이름
  - `vb.cpus`: CPU 코어 수
  - `vb.memory`: 메모리 크기 (MB 단위)
  - `vb.linked_clone`: true로 설정하여 디스크 공간 절약
  - `vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]`: 두 번째 NIC를 promiscuous 모드로 설정하여 네트워크 통신 허용
3. 네트워크 설정
  - `private_network`: 각 VM에 고정 IP 할당
  - `forwarded_port`: SSH 접속을 위한 포트 포워딩 (jumpbox: 60010, server: 60100, node-0: 60101, node-1: 60102)
4. 프로비저닝: `init_cfg.sh` 스크립트를 실행하여 초기 설정 수행
  - **파일 위치**: `path: "init_cfg.sh"`는 상대 경로로, Vagrantfile이 있는 디렉터리 기준
  - 같은 디렉터리에 있을 필요는 없으며, 상대 경로(예: `"scripts/init_cfg.sh"`) 또는 절대 경로(예: `"/path/to/init_cfg.sh"`)로도 지정 가능
  - **파일 이름**: `init_cfg.sh`는 고정된 이름이 아니며, 원하는 이름(예: `setup.sh`, `bootstrap.sh`)으로 변경 가능. Vagrantfile의 `path` 값만 수정하면 됨

<br>

## init_cfg.sh

가상 머신이 처음 부팅될 때 자동으로 실행되는 초기 설정 스크립트다.

```bash
#!/usr/bin/env bash

echo ">>>> Initial Config Start <<<<"

echo "[TASK 1] Setting Profile & Bashrc"
echo "sudo su -" >> /home/vagrant/.bashrc
echo 'alias vi=vim' >> /etc/profile
ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime # Change Timezone

echo "[TASK 2] Disable AppArmor"
systemctl stop apparmor && systemctl disable apparmor >/dev/null 2>&1

echo "[TASK 3] Disable and turn off SWAP"
swapoff -a && sed -i '/swap/s/^/#/' /etc/fstab

echo "[TASK 4] Install Packages"
apt update -qq >/dev/null 2>&1
apt install tree git jq yq unzip vim sshpass -y -qq >/dev/null 2>&1

echo "[TASK 5] Setting Root Password"
echo "root:qwe123" | chpasswd

echo "[TASK 6] Setting Sshd Config"
cat << EOF >> /etc/ssh/sshd_config
PasswordAuthentication yes
PermitRootLogin yes
EOF
systemctl restart sshd  >/dev/null 2>&1

echo "[TASK 7] Setting Local DNS Using Hosts file"
sed -i '/^127\.0\.\(1\|2\)\.1/d' /etc/hosts
cat << EOF >> /etc/hosts
192.168.10.10  jumpbox
192.168.10.100 server.kubernetes.local server 
192.168.10.101 node-0.kubernetes.local node-0
192.168.10.102 node-1.kubernetes.local node-1
EOF

echo ">>>> Initial Config End <<<<"
```

### 작업 상세 설명
1. TASK 1: Profile & Bashrc 설정
  - `.bashrc`에 `sudo su -` 명령을 추가하여 vagrant 사용자가 자동으로 root로 전환되도록 설정
    - 실습 과정의 많은 부분에 root 권한이 필요함 (시스템 서비스 설치, 설정 파일 수정, 네트워크 구성 등)
    - 매번 `sudo`를 입력하거나 `sudo su -`를 실행하는 것보다 SSH 접속 시 자동으로 root로 전환되는 게 편리
    - 프로덕션 환경에서는 권장되지 않지만, 실습 환경이므로 보안보다 편의성 우선
  - `vi`를 `vim`으로 alias 설정
  - 타임존을 Asia/Seoul로 변경
2. TASK 2: AppArmor 비활성화
  - AppArmor: Linux 커널의 보안 모듈로, 프로그램의 리소스 접근을 제한하는 Mandatory Access Control (MAC) 시스템
  - 비활성화 이유: Kubernetes 실습 환경에서는 AppArmor가 일부 컨테이너 런타임이나 네트워크 플러그인과 충돌할 수 있음
  - 프로덕션 환경에서는 보안을 위해 활성화 권장
3. TASK 3: SWAP 비활성화
  - SWAP: 디스크 공간을 메모리처럼 사용하는 가상 메모리
  - 비활성화 이유
    - Kubernetes는 노드의 메모리 사용량을 정확히 모니터링해야 하는데, SWAP이 활성화되어 있으면 메모리 부족 상황을 제대로 감지하지 못할 수 있음
    - kubelet은 기본적으로 SWAP이 비활성화되어 있어야 정상 동작함
4. TASK 4: 필수 패키지 설치
  - `tree`, `git`, `jq`, `yq`, `unzip`, `vim`, `sshpass` 등 실습에 필요한 유틸리티 설치
5. TASK 5: Root 비밀번호 설정
  - root 비밀번호를 `qwe123`으로 설정 (실습 환경용)
  - **chpasswd**: 사용자 비밀번호를 일괄 변경하는 명령어. `echo "username:password" | chpasswd` 형식으로 사용
6. TASK 6: SSH 설정
  - 실습 편의를 위해 패스워드 기반 인증과 root 로그인을 허용
    - `PasswordAuthentication yes`: 패스워드 인증 허용
    - `PermitRootLogin yes`: root 계정으로 직접 SSH 접속 허용
  - 프로덕션 환경에서는 보안상 키 기반 인증만 사용하고 root 로그인을 비활성화해야 함
7. TASK 7: Local DNS 설정 (Hosts 파일)
  - `/etc/hosts` 파일에 각 호스트의 IP와 호스트명을 매핑하여 도메인 이름으로 접근할 수 있도록 설정
  - 예: `192.168.10.100 server.kubernetes.local server` → `server.kubernetes.local` 또는 `server`로 접근 가능

<br>

# 실습 시작

## 가상 머신 시작

Vagrantfile과 init_cfg.sh를 준비한 후, 다음 명령어로 가상 머신을 시작한다. 

```bash
# (host) $
# 정의된 모든 가상 머신(jumpbox, server, node-0, node-1) 생성 및 시작
vagrant up
```

<br>

### 확인

```bash
# (host) $
# 다운로드된 Vagrant Box 목록 확인
vagrant box list

# 배포된 가상머신 상태 확인
vagrant status
```

**실행 결과:**
```
bento/debian-12 (virtualbox, 202510.26.0, (arm64))

Current machine states:

jumpbox                   running (virtualbox)
server                    running (virtualbox)
node-0                    running (virtualbox)
node-1                    running (virtualbox)
```

<br>

## Jumpbox SSH 접속

가상 머신이 모두 시작되면, jumpbox에 SSH로 접속하여 환경을 확인한다. 접속 후 자동으로 root로 전환되며, 각 호스트의 네트워크 설정과 호스트명이 올바르게 구성되었는지 확인할 수 있다.

```bash
# (host) $
# jumpbox 가상 머신으로 SSH 접속
vagrant ssh jumpbox
```

**실행 결과:**
```
Linux jumpbox 6.1.0-40-arm64 #1 SMP Debian 6.1.153-1 (2025-09-20) aarch64
# ...
root@jumpbox:~# whoami
root
```

### OS 확인

Debian 12 (bookworm)가 정상적으로 설치되었다.

```bash
# (jumpbox) #
cat /etc/os-release
```

**실행 결과:**
```
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
NAME="Debian GNU/Linux"
VERSION_ID="12"
VERSION="12 (bookworm)"
VERSION_CODENAME=bookworm
ID=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://bugs.debian.org/"
```

<br>


### AppArmor 상태 확인

AppArmor가 정상적으로 비활성화되었다.

```bash
# (jumpbox) #
# AppArmor 서비스 상태 확인
systemctl status apparmor

# 서비스 활성화 여부 확인 (inactive 예상)
systemctl is-active apparmor
```

**실행 결과:**
```
○ apparmor.service - Load AppArmor profiles
# ...
inactive
```

<br>

### Hosts 파일 확인

모든 호스트가 정상적으로 등록되었다.

```bash
# (jumpbox) #
# 로컬 DNS 설정 확인
cat /etc/hosts
```

**실행 결과:**
```
127.0.0.1       localhost
::1     localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
192.168.10.10  jumpbox
192.168.10.100 server.kubernetes.local server 
192.168.10.101 node-0.kubernetes.local node-0
192.168.10.102 node-1.kubernetes.local node-1
```

<br>

### 네트워크 연결 확인

DNS 설정과 네트워크 통신이 정상적으로 동작한다.

```bash
# (jumpbox) #
# 호스트명을 이용한 ICMP 에코 요청 테스트
ping -c 3 server.kubernetes.local
```

**실행 결과:**
```
PING server.kubernetes.local (192.168.10.100) 56(84) bytes of data.
64 bytes from server.kubernetes.local (192.168.10.100): icmp_seq=1 ttl=64 time=1.18 ms
# ...
```


<br>

# 결과

VirtualBox와 Vagrant를 이용하여 Kubernetes 실습 환경을 위한 4대의 가상 머신을 성공적으로 구성했다. 각 머신은 Debian 12를 기반으로 동작하며, 192.168.10.0/24 대역의 private network를 통해 서로 통신할 수 있다. 

다음 글 [Setup The Jumpbox 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %})에서는 이 환경을 기반으로 Kubernetes 클러스터를 직접 구축해 본다.
