---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 4.0. 클러스터 배포 - 실습 환경 구성"
excerpt: "cluster.yml을 이용해 클러스터 배포 실습을 위한 환경을 구성해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Vagrant
  - VirtualBox
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray 클러스터 배포를 위한 실습 환경**을 구성한다.

- **Vagrant + VirtualBox**로 Rocky Linux VM 생성
- **init_cfg.sh**로 Kubernetes 노드 사전 구성
- **Windows 환경 트러블슈팅**: Hyper-V 비활성화, VirtualBox 업그레이드


<br>

# 사전 준비

## 필수 요구 사항

| 항목 | 요구 사항 |
|------|-----------|
| VirtualBox | 7.2.4 이상 권장 |
| Vagrant | 2.4.x 이상 |
| 메모리 | 최소 8GB (VM에 4GB 할당) |
| 디스크 | 최소 20GB 여유 공간 |

## 실습 자료

본 실습에서 사용하는 `Vagrantfile`과 `init_cfg.sh`는 다음 출처를 기반으로 한다:

- [Vagrantfile](https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-kubespary/Vagrantfile)
- [init_cfg.sh](https://raw.githubusercontent.com/gasida/vagrant-lab/refs/heads/main/k8s-kubespary/init_cfg.sh)

> **참고**: `init_cfg.sh`는 Windows 환경 트러블슈팅 과정에서 동적 네트워크 인터페이스 탐색 로직이 추가되었다. 아래에서 수정된 버전을 사용한다.

## Windows 환경 사전 작업

> **TMI**: 평소에는 Mac으로 실습을 진행하는데, 이번에는 "색다르게 Windows에서 해볼까?"라는 생각에 도전했다가... 아래의 모든 과정을 경험하게 되었다. Mac에서는 `vagrant up` 한 방이면 끝났을 일이다. 

**Windows에서 VirtualBox를 사용하려면 Hyper-V를 비활성화해야 한다.** Hyper-V가 활성화되어 있으면 VirtualBox가 NEM 모드로 폴백되어 최신 Linux 커널에서 Kernel Panic이 발생할 수 있다.

```bash
[    1.511197] ---[ end trace 0000000000000000 ]---
[    1.513571] RIP: 0010:wait_for_xmitr+0x61/0xc0
[    1.559573] Kernel panic - not syncing: Fatal exception
[    1.563919] ---[ end Kernel panic - not syncing: Fatal exception ]---
```

> **참고**: [RL10 under VirtualBox?](https://forums.rockylinux.org/t/rl10-under-virtualbox/18762) 
>
>  Rocky Linux 포럼에서 정확히 동일한 증상을 겪은 사용자들의 논의를 발견했다. 내가 경험했던 위의 Kernel Panic과 완전히 일치하는 상황이다.
>
> - **원인**: VBox 로그에 `HM: HMR3Init: Attempting fall back to NEM: VT-x is not available` → Hyper-V가 VT-x 독점
> - **해결**: VirtualBox 업데이트 (7.1.10+), Hyper-V 비활성화, Core Isolation 비활성화
>
> *"Windows has made it very difficult to fully disable HyperV"* - 포럼 사용자 hspindel

<details markdown="1">
<summary>Hyper-V, VT-x, NEM (클릭하여 펼치기)</summary>

| 용어 | 설명 |
|------|------|
| **VT-x** | Intel의 하드웨어 가상화 기술. VM이 CPU를 직접 사용할 수 있게 해줌 |
| **Hyper-V** | Microsoft의 Type-1 하이퍼바이저. Windows에 내장된 가상화 플랫폼 |
| **NEM** | Native Execution Mode. VirtualBox가 VT-x를 사용할 수 없을 때 Hyper-V 위에서 실행되는 폴백 모드 |

**왜 Hyper-V가 활성화되어 있었나?**

다음 기능들이 Hyper-V(또는 Virtual Machine Platform)를 필요로 한다:
- **WSL2**: Windows Subsystem for Linux 2는 경량 VM으로 동작하며 Hyper-V 기반
- **Docker Desktop**: WSL2 백엔드 사용 시 필요
- **Windows Sandbox**: 격리된 데스크톱 환경 제공

<br>

**문제 상황**

```
┌───────────────────────────────────────┐
│            Windows 11                 │
│  ┌─────────────────────────────────┐  │
│  │   Hyper-V (owns VT-x)           │  │
│  │  ┌───────────────────────────┐  │  │
│  │  │  VirtualBox (NEM mode)    │  │  │  ← 느리고 불안정
│  │  │  ┌─────────────────────┐  │  │  │
│  │  │  │   Rocky Linux VM    │  │  │  │
│  │  │  └─────────────────────┘  │  │  │
│  │  └───────────────────────────┘  │  │
│  └─────────────────────────────────┘  │
└───────────────────────────────────────┘
```

Hyper-V가 활성화되면 하드웨어 가상화(VT-x)를 독점하여 VirtualBox가 직접 사용할 수 없다. VirtualBox는 NEM 모드로 폴백하는데, Rocky Linux 10의 최신 커널(6.x)이 이 환경에서 불안정하게 동작하여 Kernel Panic이 발생한다.

<br>

</details>

<br>

```powershell
# 관리자 권한 PowerShell에서 실행

# 1. Hyper-V 관련 기능 비활성화
Disable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -NoRestart
Disable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart
Disable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -NoRestart

# 2. Hypervisor 완전 비활성화
bcdedit /set hypervisorlaunchtype off

# 3. 재부팅
Restart-Computer
```

<br>

재부팅 후 상태를 확인한다.

```powershell
# 아무 출력 없어야 함
Get-WindowsOptionalFeature -Online | Where-Object {$_.FeatureName -like "*Hyper-V*" -and $_.State -eq "Enabled"}

# hypervisorlaunchtype이 Off여야 함
bcdedit /enum | Select-String hypervisorlaunchtype
```

> **주의**: Hyper-V 비활성화 시 WSL2, Docker Desktop(Hyper-V 백엔드)이 작동하지 않는다. 실습 종료 후 재활성화할 수 있다.

<br>

# Vagrantfile 작성

프로젝트 디렉터리에 `Vagrantfile`을 생성한다:

```ruby
# Base Image  https://portal.cloud.hashicorp.com/vagrant/discover/bento/rockylinux-10.0
BOX_IMAGE = "bento/rockylinux-10.0"
BOX_VERSION = "202510.26.0"

Vagrant.configure("2") do |config|

# ControlPlane Nodes 
    config.vm.define "k8s-ctr" do |subconfig|
      subconfig.vm.box = BOX_IMAGE
      subconfig.vm.box_version = BOX_VERSION
      subconfig.vm.provider "virtualbox" do |vb|
        vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]
        vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
        vb.name = "k8s-ctr"
        vb.cpus = 4
        vb.memory = 4096
        vb.linked_clone = true
      end
      subconfig.vm.host_name = "k8s-ctr"
      subconfig.vm.network "private_network", ip: "192.168.10.10"
      subconfig.vm.network "forwarded_port", guest: 22, host: "60100", auto_correct: true, id: "ssh"
      subconfig.vm.synced_folder "./", "/vagrant", disabled: true
      subconfig.vm.provision "shell", path: "init_cfg.sh"
    end

end
```

## 주요 설정 설명

| 설정 | 값 | 설명 |
|------|----|----- |
| `BOX_IMAGE` | `bento/rockylinux-10.0` | Rocky Linux 10.0 베이스 이미지 |
| `vb.cpus` | `4` | VM에 할당할 CPU 코어 수 |
| `vb.memory` | `4096` | VM에 할당할 메모리 (MB) |
| `vb.linked_clone` | `true` | 디스크 공간 절약을 위한 링크드 클론 |
| `private_network` | `192.168.10.10` | Host-Only 네트워크 IP |
| `forwarded_port` | `60100` | SSH 포트 포워딩 |

<br>

# init_cfg.sh 작성 (수정 버전)

VM 프로비저닝 시 실행될 초기화 스크립트다. 원본 대비 **TASK 6에서 동적 인터페이스 탐색** 로직이 추가되었다:

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
cat << EOF >> /etc/hosts
192.168.10.10 k8s-ctr
EOF

echo "[TASK 6] Delete default routing - Secondary NIC"
# 192.168.10.x 주소를 가진 인터페이스 동적 탐색
SECONDARY_NIC=$(ip -o -4 addr show | grep "192.168.10" | awk '{print $2}')

if [ -n "$SECONDARY_NIC" ]; then
  echo "Found secondary NIC: $SECONDARY_NIC, disabling default route..."
  nmcli connection modify "$SECONDARY_NIC" ipv4.never-default yes 2>/dev/null || true
  nmcli connection up "$SECONDARY_NIC" 2>/dev/null || true
else
  echo "No secondary NIC found, skipping..."
fi

echo "sudo su -" >> /home/vagrant/.bashrc

echo ">>>> Initial Config End <<<<"
```

## 스크립트 설명

| Task | 설명 | Kubernetes 관련성 |
|------|------|-------------------|
| TASK 1 | 타임존 설정 | 로그 및 인증서 시간 동기화 |
| TASK 2 | 방화벽/SELinux 비활성화 | Pod 네트워킹 문제 방지 |
| TASK 3 | Swap 비활성화 | kubelet 요구사항 |
| TASK 4 | 커널 모듈/파라미터 설정 | 컨테이너 네트워킹 지원 |
| TASK 5 | /etc/hosts 설정 | 노드 간 이름 해석 |
| TASK 6 | Secondary NIC 라우팅 | Host-Only 네트워크 우선순위 |

### TASK 6: 동적 네트워크 인터페이스 탐색 (수정된 부분)

원본 스크립트는 인터페이스명을 `enp0s9`로 지정했으나, 환경에 따라 `enp0s8`, `enp0s9` 등으로 달라질 수 있어 `unknown connection` 에러가 발생했다. IP 주소 패턴으로 동적 탐색하도록 수정했다:

```bash
# 192.168.10.x 주소를 가진 인터페이스 탐색
SECONDARY_NIC=$(ip -o -4 addr show | grep "192.168.10" | awk '{print $2}')
```

| 명령 | 설명 |
|------|------|
| `ip -o -4 addr show` | IPv4 주소 정보를 한 줄 형식으로 출력 |
| `grep "192.168.10"` | Host-Only 네트워크 대역 필터링 |
| `awk '{print $2}'` | 인터페이스명 추출 |

<br>

# VM 생성 및 확인

```bash
# VM 생성
vagrant up k8s-ctr

# SSH 접속
vagrant ssh k8s-ctr

# VM 상태 확인
vagrant status
```

## SSH 공개키 복사 (Ansible용)

Kubespray 실행을 위해 SSH 키 기반 인증을 설정한다:

```bash
# SSH 키 생성 (없는 경우)
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# 공개키 복사
ssh-copy-id -o StrictHostKeyChecking=no -p 60100 vagrant@127.0.0.1
# 비밀번호: vagrant
```

<br>

# Windows 환경 트러블슈팅

## 문제 1: Kernel Panic

- **증상**: `vagrant up` 후 VM 콘솔에 `Kernel panic - not syncing: Fatal exception` 메시지
- **원인**: Windows Hyper-V가 활성화되어 있으면 VirtualBox가 NEM 모드로 폴백되고, Rocky Linux 10의 최신 커널(6.x)이 NEM 환경에서 불안정하게 동작
- **해결**: 
  - Hyper-V 비활성화 (위의 사전 작업 참고)
  - VirtualBox를 7.2.4 이상으로 업그레이드

> 다양한 Vagrantfile 설정 변경(시리얼 포트 비활성화, paravirtprovider 변경 등)을 시도했으나, 근본적인 해결책은 Hyper-V 비활성화와 VirtualBox 업그레이드였다.

## 문제 2: VERR_ALREADY_EXISTS

- **증상**: `vagrant up` 재실행 시 `VERR_ALREADY_EXISTS` 에러
- **원인**: 이전 실행에서 생성된 VM 디렉터리가 남아있음. `--groups` 설정으로 인해 VirtualBox가 VM 디렉터리를 그룹 폴더로 이동하려 할 때, 이미 해당 폴더가 존재하면 충돌 발생
- **해결**:

```powershell
# 1. VM 제거
vagrant destroy -f k8s-ctr

# 2. 잔여 디렉터리 삭제
Remove-Item -Recurse -Force "C:\Users\User\VirtualBox VMs\Kubespray-Lab" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "C:\Users\User\VirtualBox VMs\k8s-ctr" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .vagrant -ErrorAction SilentlyContinue

# 3. 재시도
vagrant up k8s-ctr
```

### 대안: `--groups` 설정 비활성화

근본적인 해결책은 아니지만, 문제가 반복된다면 Vagrantfile에서 `--groups` 설정을 주석 처리하는 방법도 있다:

```ruby
subconfig.vm.provider "virtualbox" do |vb|
  # vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]  # 주석 처리
  vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
  # ... 나머지 설정
end
```

`--groups`는 VirtualBox Manager UI에서 VM을 폴더로 그룹화하는 기능으로, **VM 동작 자체에는 영향이 없다**. 이 설정을 제거하면 디렉터리 이동이 발생하지 않아 충돌을 우회할 수 있다.

## 문제 3: unknown connection 에러

- **증상**: `Error: unknown connection 'enp0s9'`
- **원인**: 원본 `init_cfg.sh`에서 네트워크 인터페이스명을 `enp0s9`로 지정했으나, 환경마다 다를 수 있음
- **해결**: `init_cfg.sh`의 TASK 6을 동적 인터페이스 탐색 방식으로 수정 (위의 수정된 스크립트 참고)

<br>

# 참고: Hyper-V 재활성화

실습 종료 후 WSL2/Docker Desktop을 다시 사용하려면:

```powershell
# 관리자 권한 PowerShell에서 실행
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -NoRestart
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart
Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -NoRestart
bcdedit /set hypervisorlaunchtype auto

# 재부팅
Restart-Computer
```

> WSL2 배포판 데이터는 Hyper-V를 껐다 켜도 보존된다.

<br>

# 결과

실습 환경이 준비되었다. 다음 글에서는 실제 Kubespray를 이용해 클러스터를 배포한다.

- VM SSH 접속 확인
- Kubespray 인벤토리 설정
- `cluster.yml` 실행

<br>

# 참고 자료

- [gasida/vagrant-lab - k8s-kubespary](https://github.com/gasida/vagrant-lab/tree/main/k8s-kubespary) (원본 Vagrantfile, init_cfg.sh)
- [Vagrant VirtualBox Provider](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox)
- [Rocky Linux 10 Release Notes](https://rockylinux.org/news/rocky-linux-10-0-ga-release)
- [VirtualBox NEM Mode Documentation](https://www.virtualbox.org/manual/ch10.html)
- [이전 글: 프로젝트 구조 Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-03-00 %})

<br>
