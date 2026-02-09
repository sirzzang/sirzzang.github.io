---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 0. 실습 환경 배포"
excerpt: "폐쇄망 Kubernetes 클러스터 배포를 위한 Vagrant 실습 환경을 구성하고, 네트워크 구조를 확인해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - Vagrant
  - VirtualBox
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6
  
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 클러스터 배포 실습을 위한 **Vagrant 환경을 구성**하고, **네트워크 구조를 확인**한다.

- **Vagrant + VirtualBox**로 admin 1대 + k8s-node 2대 구성
- **admin**: Bastion + Admin 역할 통합 (120GB 디스크), 이후 NTP/DNS/Repo/Registry 서빙 예정
- **k8s-node1**: Control Plane, **k8s-node2**: Worker
- **네트워크**: `enp0s8`(NAT, 인터넷 접근) + `enp0s9`(Host-Only, 내부 통신 `192.168.10.0/24`)

<br>

# 실습 환경 아키텍처

실제 기업 환경에서는 DMZ의 Bastion Server와 내부망의 Admin Server가 분리되어 있지만, PC 스펙과 시간을 고려해 **admin 1대가 Bastion + Admin 역할을 겸하도록** 구성한다.

![VirtualBox 실습 환경 아키텍처](/assets/images/virtualbox-kubespray-lab-architecture.png)

| 호스트 | IP | 역할 | 스펙 |
|--------|-----|------|------|
| admin | 192.168.10.10 | Bastion + Admin | 4 vCPU, 2GB RAM, 120GB Disk |
| k8s-node1 | 192.168.10.11 | K8s Control Plane | 4 vCPU, 2GB RAM |
| k8s-node2 | 192.168.10.12 | K8s Worker | 4 vCPU, 2GB RAM |

<br>

# Vagrant 환경 파일

실습 환경은 3개의 파일로 구성된다.

| 파일 | 역할 |
|------|------|
| `Vagrantfile` | VM 정의 (스펙, 네트워크, 디스크) |
| `admin.sh` | admin 노드 프로비저닝 |
| `init_cfg.sh` | k8s-node 프로비저닝 |

## Vagrantfile

```ruby
# Base Image  https://portal.cloud.hashicorp.com/vagrant/discover/bento/rockylinux-10.0
BOX_IMAGE = "bento/rockylinux-10.0"
BOX_VERSION = "202510.26.0"
N = 2 # max number of Node

Vagrant.configure("2") do |config|

  # K8s Nodes
  (1..N).each do |i|
    config.vm.define "k8s-node#{i}" do |subconfig|
      subconfig.vm.box = BOX_IMAGE
      subconfig.vm.box_version = BOX_VERSION
      subconfig.vm.provider "virtualbox" do |vb|
        vb.customize ["modifyvm", :id, "--groups", "/Kubespary-offline-Lab"]
        vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
        vb.name = "k8s-node#{i}"
        vb.cpus = 4
        vb.memory = 2048
        vb.linked_clone = true
      end
      subconfig.vm.host_name = "k8s-node#{i}"
      subconfig.vm.network "private_network", ip: "192.168.10.1#{i}"
      subconfig.vm.network "forwarded_port", guest: 22, host: "6000#{i}", auto_correct: true, id: "ssh"
      subconfig.vm.synced_folder "./", "/vagrant", disabled: true
      subconfig.vm.provision "shell", path: "init_cfg.sh" , args: [ N ]
    end
  end

  # Admin Node
  config.vm.define "admin" do |subconfig|
    subconfig.vm.box = BOX_IMAGE
    subconfig.vm.box_version = BOX_VERSION
    subconfig.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Kubespary-offline-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "admin"
      vb.cpus = 4
      vb.memory = 2048
      vb.linked_clone = true
    end
    subconfig.vm.host_name = "admin"
    subconfig.vm.network "private_network", ip: "192.168.10.10"
    subconfig.vm.network "forwarded_port", guest: 22, host: "60000", auto_correct: true, id: "ssh"
    subconfig.vm.synced_folder "./", "/vagrant", disabled: true
    subconfig.vm.disk :disk, size: "120GB", primary: true
    subconfig.vm.provision "shell", path: "admin.sh" , args: [ N ]
  end

end
```

주요 포인트:

- **Rocky Linux 10.0**: RHEL 계열, 실제 기업 환경에서 많이 사용하는 배포판
- **admin 120GB 디스크**: 오프라인 패키지, 컨테이너 이미지 등을 로컬에 저장해야 하므로 용량을 크게 설정
- **private_network**: `192.168.10.0/24` 대역의 Host-Only 네트워크로 VM 간 내부 통신
- **linked_clone**: 디스크 공간 절약을 위한 linked clone 사용

## admin.sh

admin 노드의 프로비저닝 스크립트다. 각 TASK가 하는 일을 정리하면:

```bash
#!/usr/bin/env bash

echo ">>>> Initial Config Start <<<<"

echo "[TASK 1] Change Timezone and Enable NTP"
timedatectl set-local-rtc 0
timedatectl set-timezone Asia/Seoul

echo "[TASK 2] Disable firewalld and selinux"
systemctl disable --now firewalld >/dev/null 2>&1
setenforce 0
sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

echo "[TASK 3] Setting Local DNS Using Hosts file"
sed -i '/^127\.0\.\(1\|2\)\.1/d' /etc/hosts
echo "192.168.10.10 admin" >> /etc/hosts
for (( i=1; i<=$1; i++  )); do echo "192.168.10.1$i k8s-node$i" >> /etc/hosts; done

echo "[TASK 4] Delete default routing - enp0s9 NIC"
nmcli connection modify enp0s9 ipv4.never-default yes
nmcli connection up enp0s9 >/dev/null 2>&1

echo "[TASK 5] Config net.ipv4.ip_forward"
cat << EOF > /etc/sysctl.d/99-ipforward.conf
net.ipv4.ip_forward = 1
EOF
sysctl --system  >/dev/null 2>&1

echo "[TASK 6] Install packages"
dnf install -y python3-pip git sshpass cloud-utils-growpart >/dev/null 2>&1

echo "[TASK 7] Install Helm"
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | DESIRED_VERSION=v3.20.0 bash >/dev/null 2>&1

echo "[TASK 8] Increase Disk Size"
growpart /dev/sda 3 >/dev/null 2>&1
xfs_growfs /dev/sda3 >/dev/null 2>&1

echo "[TASK 9] Setting SSHD"
echo "root:qwe123" | chpasswd
cat << EOF >> /etc/ssh/sshd_config
PermitRootLogin yes
PasswordAuthentication yes
EOF
systemctl restart sshd >/dev/null 2>&1

echo "[TASK 10] Setting SSH Key"
ssh-keygen -t rsa -N "" -f /root/.ssh/id_rsa >/dev/null 2>&1
sshpass -p 'qwe123' ssh-copy-id -o StrictHostKeyChecking=no root@192.168.10.10  >/dev/null 2>&1
ssh -o StrictHostKeyChecking=no root@admin-lb hostname >/dev/null 2>&1
for (( i=1; i<=$1; i++  )); do sshpass -p 'qwe123' ssh-copy-id -o StrictHostKeyChecking=no root@192.168.10.1$i >/dev/null 2>&1 ; done
for (( i=1; i<=$1; i++  )); do sshpass -p 'qwe123' ssh -o StrictHostKeyChecking=no root@k8s-node$i hostname >/dev/null 2>&1 ; done

echo "[TASK 11] Install K9s"
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
wget -P /tmp https://github.com/derailed/k9s/releases/latest/download/k9s_linux_${CLI_ARCH}.tar.gz  >/dev/null 2>&1
tar -xzf /tmp/k9s_linux_${CLI_ARCH}.tar.gz -C /tmp
chown root:root /tmp/k9s
mv /tmp/k9s /usr/local/bin/
chmod +x /usr/local/bin/k9s

echo "[TASK 12] ETC"
echo "sudo su -" >> /home/vagrant/.bashrc

echo ">>>> Initial Config End <<<<"
```

| TASK | 설명 | 비고 |
|------|------|------|
| 1 | 타임존 설정 (Asia/Seoul) | NTP는 이후 별도로 구성 |
| 2 | firewalld / SELinux 비활성화 | 실습 편의상 |
| 3 | `/etc/hosts`에 노드 IP 등록 | 간이 DNS 역할 |
| 4 | `enp0s9`에서 default route 제거 | Host-Only NIC이 기본 경로가 되지 않도록 |
| 5 | `ip_forward` 활성화 | admin이 게이트웨이 역할을 할 수 있도록 |
| 6-7 | 필요 패키지 및 Helm 설치 | python3-pip, git, sshpass, growpart, helm |
| 8 | 디스크 확장 (120GB) | `growpart` + `xfs_growfs` |
| 9-10 | SSH 설정 및 키 배포 | root 로그인 허용, 모든 노드에 SSH 키 배포 |
| 11 | K9s 설치 | K8s TUI 관리 도구 |

## init_cfg.sh

k8s-node 프로비저닝 스크립트다. admin.sh와 공통 부분이 있지만, K8s 워크로드를 실행할 노드이므로 추가 설정이 필요하다.

```bash
#!/usr/bin/env bash

echo ">>>> Initial Config Start <<<<"

echo "[TASK 1] Change Timezone and Enable NTP"
timedatectl set-local-rtc 0
timedatectl set-timezone Asia/Seoul

echo "[TASK 2] Disable firewalld and selinux"
systemctl disable --now firewalld >/dev/null 2>&1
setenforce 0
sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

echo "[TASK 3] Disable and turn off SWAP & Delete swap partitions"
swapoff -a
sed -i '/swap/d' /etc/fstab
sfdisk --delete /dev/sda 2 >/dev/null 2>&1
partprobe /dev/sda >/dev/null 2>&1

echo "[TASK 4] Config kernel & module"
cat << EOF > /etc/modules-load.d/k8s.conf
overlay
br_netfilter
vxlan
EOF
modprobe overlay >/dev/null 2>&1
modprobe br_netfilter >/dev/null 2>&1

cat << EOF >/etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system >/dev/null 2>&1

echo "[TASK 5] Setting Local DNS Using Hosts file"
sed -i '/^127\.0\.\(1\|2\)\.1/d' /etc/hosts
echo "192.168.10.10 admin" >> /etc/hosts
for (( i=1; i<=$1; i++  )); do echo "192.168.10.1$i k8s-node$i" >> /etc/hosts; done

echo "[TASK 6] Delete default routing - enp0s9 NIC"
nmcli connection modify enp0s9 ipv4.never-default yes
nmcli connection up enp0s9 >/dev/null 2>&1

echo "[TASK 7] Setting SSHD"
echo "root:qwe123" | chpasswd
cat << EOF >> /etc/ssh/sshd_config
PermitRootLogin yes
PasswordAuthentication yes
EOF
systemctl restart sshd >/dev/null 2>&1

echo "[TASK 8] Install packages"
dnf install -y python3-pip git >/dev/null 2>&1

echo "[TASK 9] ETC"
echo "sudo su -" >> /home/vagrant/.bashrc

echo ">>>> Initial Config End <<<<"
```

admin.sh와의 차이:

| 항목 | admin.sh | init_cfg.sh |
|------|----------|-------------|
| SWAP | - | 비활성화 및 파티션 삭제 |
| 커널 모듈 | - | overlay, br_netfilter, vxlan 로드 |
| sysctl | `ip_forward`만 | `bridge-nf-call-iptables` 등 K8s 필수 설정 포함 |
| SSH 키 | 생성 + 배포 | - (admin에서 배포받음) |
| 디스크 | 120GB 확장 | - |
| 추가 도구 | Helm, K9s, sshpass, growpart | - |

<br>

# 환경 배포

## 파일 다운로드 및 VM 생성

```bash
mkdir k8s-offline
cd k8s-offline

# 실습 파일 다운로드
curl -O https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-kubespary-offline/Vagrantfile
curl -O https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-kubespary-offline/admin.sh
curl -O https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-kubespary-offline/init_cfg.sh

# VM 생성
vagrant up
```

VM 생성 과정에서 각 노드가 순차적으로 프로비저닝된다.

```
Bringing machine 'week06-node1' up with 'virtualbox' provider...
Bringing machine 'week06-node2' up with 'virtualbox' provider...
Bringing machine 'week06-admin' up with 'virtualbox' provider...
```

각 노드의 프로비저닝 완료 로그:

```
# k8s-node (init_cfg.sh)
>>>> Initial Config Start <<<<
[TASK 1] Change Timezone and Enable NTP
[TASK 2] Disable firewalld and selinux
[TASK 3] Disable and turn off SWAP & Delete swap partitions
[TASK 4] Config kernel & module
[TASK 5] Setting Local DNS Using Hosts file
[TASK 6] Delete default routing - enp0s9 NIC
[TASK 7] Setting SSHD
[TASK 8] Install packages
[TASK 9] ETC
>>>> Initial Config End <<<<

# admin (admin.sh)
>>>> Initial Config Start <<<<
[TASK 1] Change Timezone and Enable NTP
[TASK 2] Disable firewalld and selinux
[TASK 3] Setting Local DNS Using Hosts file
[TASK 4] Delete default routing - enp0s9 NIC
[TASK 5] Config net.ipv4.ip_forward
[TASK 6] Install packages
[TASK 7] Install Helm
[TASK 8] Increase Disk Size
[TASK 9] Setting SSHD
[TASK 10] Setting SSH Key
[TASK 11] Install K9s
[TASK 12] ETC
>>>> Initial Config End <<<<
```

## 상태 확인

모든 VM이 running 상태인지 확인한다.

```bash
vagrant status
```

```
Current machine states:

week06-node1              running (virtualbox)
week06-node2              running (virtualbox)
week06-admin              running (virtualbox)
```

## 접속 확인

각 노드에 SSH로 접속할 수 있는지 확인한다. 호스트 OS에 `sshpass`가 없으면 `ssh`로 접속 후 비밀번호(`qwe123`)를 입력한다.

```bash
# admin 접속
ssh root@192.168.10.10

# k8s-node1 접속
ssh root@192.168.10.11

# k8s-node2 접속
ssh root@192.168.10.12
```

<br>

# 네트워크 구조 확인

환경 배포가 완료되면, 네트워크가 의도한 대로 구성되었는지 확인한다. 이후 Network Gateway 구성(8.1.1)의 기반이 되는 내용이다. VirtualBox NAT/Host-Only 어댑터의 전체적인 동작 원리는 [VirtualBox + Vagrant 네트워크 어댑터 이해하기]({% post_url 2026-02-09-Dev-VirtualBox-Network %})를 참고하자.

## 라우팅 테이블

admin 노드에 접속하여 라우팅 테이블을 확인한다.

```bash
root@admin:~# ip -c route
default via 10.0.2.2 dev enp0s8 proto dhcp src 10.0.2.15 metric 100
10.0.2.0/24 dev enp0s8 proto kernel scope link src 10.0.2.15 metric 100
192.168.10.0/24 dev enp0s9 proto kernel scope link src 192.168.10.10 metric 101
```

| NIC | 네트워크 | 용도 |
|-----|----------|------|
| `enp0s8` | `10.0.2.0/24` (NAT) | VirtualBox NAT, **인터넷 접근** (default route) |
| `enp0s9` | `192.168.10.0/24` (Host-Only) | **VM 간 내부 통신** |

## NIC 설정 상세

두 NIC의 NetworkManager 설정을 비교하면, 각각의 역할이 명확히 드러난다.

### enp0s8 — NAT (인터넷)

```ini
# /etc/NetworkManager/system-connections/enp0s8.nmconnection
[connection]
id=enp0s8
type=ethernet
interface-name=enp0s8

[ipv4]
method=auto          # DHCP로 IP/서브넷/게이트웨이 자동 할당
```

- `method=auto`: VirtualBox NAT 네트워크의 DHCP 서버에서 IP를 할당받는다
- 이 NIC을 통해 인터넷에 접근할 수 있으며, default route가 여기를 가리킨다

### enp0s9 — Host-Only (내부망)

```ini
# /etc/NetworkManager/system-connections/enp0s9.nmconnection
[connection]
id=enp0s9
type=ethernet
autoconnect-priority=-100    # 자동 연결 우선순위 낮음
autoconnect-retries=1        # 실패 시 1회만 재시도
interface-name=enp0s9

[ipv4]
address1=192.168.10.10/24
method=manual                # 고정 IP
never-default=true           # 절대 default route를 생성하지 않음
```

- `method=manual`: Vagrantfile에서 지정한 IP(`192.168.10.10`)가 고정 설정
- **`never-default=true`**: 핵심 설정. 이 NIC이 default route를 생성하지 않도록 한다. `admin.sh`의 TASK 4에서 `nmcli connection modify enp0s9 ipv4.never-default yes`로 설정한 결과다.

이 설정이 없으면 두 NIC 모두 default route를 생성하려 하면서 라우팅 충돌이 발생할 수 있다.

## NetworkManager 서비스 구조

Rocky Linux 10에서 네트워크는 **NetworkManager**가 관리한다. 관련 systemd 서비스는 3개다.

| 서비스 | 역할 | 타입 |
|--------|------|------|
| `NetworkManager.service` | 네트워크 장치 관리, IP 할당의 핵심 데몬 | `dbus` |
| `NetworkManager-wait-online.service` | 부팅 시 네트워크 연결 완료까지 대기 | `oneshot` |
| `NetworkManager-dispatcher.service` | NIC up/down, IP 변경 등 이벤트 시 사용자 스크립트 실행 | `dbus` |

```bash
# 서비스 상태 확인
systemctl status NetworkManager.service --no-pager
systemctl status NetworkManager-wait-online.service --no-pager
systemctl status NetworkManager-dispatcher.service --no-pager

# dispatcher 스크립트 디렉터리 (현재 비어 있음)
tree /etc/NetworkManager/dispatcher.d/
/etc/NetworkManager/dispatcher.d/
├── no-wait.d
├── pre-down.d
└── pre-up.d

4 directories, 0 files
```

> **참고**: NetworkManager의 동작 원리와 네트워크 핵심 개념은 [다음 글(8.1.1 Network Gateway)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})에서 자세히 다룬다.

<br>

# 정리

실습 환경의 현재 상태를 정리하면:

| 호스트 | 항목 | 상태 |
|--------|------|------|
| admin (192.168.10.10) | enp0s8 (NAT) — 인터넷 접근 | 완료 |
| | enp0s9 (Host-Only) — 내부 통신 | 완료 |
| | ip_forward = 1 — 패킷 포워딩 준비 | 완료 |
| | SSH 키 배포 — 모든 노드 접근 가능 | 완료 |
| | NTP, DNS, Repo, Registry | 미구성 |
| k8s-node1/2 (192.168.10.11-12) | enp0s8 (NAT) — 인터넷 접근 | 완료 |
| | enp0s9 (Host-Only) — 내부 통신 | 완료 |
| | K8s 커널 모듈 — overlay, br_netfilter 로드 | 완료 |
| | SWAP 비활성화 — K8s 요구사항 충족 | 완료 |
| | containerd, kubelet | 미설치 |

현재는 모든 노드가 `enp0s8`(NAT)을 통해 인터넷에 접근할 수 있다. **폐쇄망 시뮬레이션은 이후 Network Gateway 구성(8.1.1)에서 이 인터넷 접근을 차단하는 것으로 시작**한다.

<br>

# 참고 자료

- [Vagrant Disk Configuration](https://developer.hashicorp.com/vagrant/docs/disks/usage)
- [Bento Box: Rocky Linux 10.0](https://portal.cloud.hashicorp.com/vagrant/discover/bento/rockylinux-10.0)

<br>

