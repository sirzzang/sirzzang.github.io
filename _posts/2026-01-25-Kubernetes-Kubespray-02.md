---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 2. Kubernetes The Kubespray Way"
excerpt: "Kubernetes The Hard Way에서 수동으로 진행했던 작업들을 Kubespray로 자동화하여 클러스터를 구성해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글은 **본격적인 Kubespray 실습에 앞서**, Kubernetes The Hard Way에서 수동으로 진행했던 작업들이 Kubespray에서 어떻게 자동화되는지 비교해보는 맛보기 실습이다.

- **목적**: Kubernetes The Hard Way의 각 단계가 Kubespray에서 어떻게 처리되는지 확인
- **핵심 차이**: 인증서 생성, etcd 구성, 컨트롤 플레인 부트스트래핑 등이 모두 자동화됨
- **실습 결과**: `ansible-playbook cluster.yml` 명령 하나로 전체 클러스터 구성 완료

<br>

# 들어가며

이 글은 Kubespray 공식 문서의 [Setting up your first cluster](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/getting_started/setting-up-your-first-cluster.md)를 기반으로 한다. 해당 문서는 [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way)에 영감을 받아 작성되었으며, 수동 설치 대신 Kubespray를 통한 자동화된 방식으로 클러스터를 구성하는 방법을 안내한다.

> This tutorial walks you through the detailed steps for setting up Kubernetes with Kubespray. The guide is inspired on the tutorial Kubernetes The Hard Way, with the difference that here we want to showcase how to spin up a Kubernetes cluster in a more managed fashion with Kubespray.

[Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})에서 수동으로 진행했던 단계들이 Kubespray 어떻게 처리되는지 비교하면서 진행한다.

<br>

# Prerequisites

## The Hard Way

[Kubernetes The Hard Way - 1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %})에서는 다음 사항들을 준비했다:
- VirtualBox, Vagrant 설치
- 호스트 시스템 요구사항 확인 (8GB+ RAM)
- 네트워크 설정 계획

## Kubespray

Kubespray를 사용하기 위한 요구사항은 다음과 같다:

| 요구사항 | 설명 |
| --- | --- |
| **Ansible Control Node** | Linux/Mac 환경, Python 3 설치 |
| **대상 노드** | SSH 접근 가능, Python 설치 |
| **네트워크** | 노드 간 통신 가능, 인터넷 접속 (이미지 다운로드) |
| **권한** | root 또는 sudo 권한 |

<br>

# Provisioning Compute Resources

## The Hard Way

[Kubernetes The Hard Way - 3. Provisioning Compute Resources]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %})에서는 다음 작업을 수행했다:
- Vagrant로 VM 4대 생성 (Jumpbox, Server, Node-0, Node-1)
- 네트워크 설정 (192.168.56.0/24)
- SSH 접근 설정

## Kubespray

동일하게 VM을 프로비저닝한다. 차이점은 **Ansible Control Node**가 별도로 필요하다는 것이다.

> **참고: 왜 Vagrant인가?**
>
> 원본 [Setting up your first cluster](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/getting_started/setting-up-your-first-cluster.md) 문서는 GCP(Google Cloud Platform)를 사용한다. 하지만 이 글에서는 **Vagrant**로 진행한다.
>
> | 구분 | Vagrant | GCP |
> | --- | --- | --- |
> | **비용** | 무료 | 유료 (무료 크레딧 $300, 90일) |
> | **설정** | Vagrantfile만 작성 | 계정, CLI, VPC, 방화벽 등 설정 필요 |
> | **속도** | 로컬 실행 (빠름) | 네트워크 지연 |
> | **재생성** | `vagrant destroy && up` | 콘솔/CLI로 삭제 후 재생성 |
>
> 학습 목적이라면 Vagrant가 더 편리하고, 1~3주차에서도 계속 Vagrant를 사용해왔기 때문에 이번에도 동일하게 진행한다. 원본 문서가 GCP를 사용한 것은 클라우드 환경에서의 범용적인 예시를 보여주기 위함이다.

### 노드 구성

| 호스트명 | IP | 역할 | The Hard Way 대응 |
| --- | --- | --- | --- |
| controller | 192.168.10.10 | Ansible Control Node | Jumpbox |
| controller-0 | 192.168.10.100 | Control Plane | Server |
| worker-0 | 192.168.10.101 | Worker Node | Node-0 |
| worker-1 | 192.168.10.102 | Worker Node | Node-1 |

### VM 생성

<details markdown="1">
<summary>Vagrantfile (클릭하여 펼치기)</summary>

```ruby
# -*- mode: ruby -*-
# vi: set ft=ruby :

# Base Image : https://portal.cloud.hashicorp.com/vagrant/discover/bento/debian-12
BOX_IMAGE = "bento/debian-12"
BOX_VERSION = "202510.26.0"

Vagrant.configure("2") do |config|
  # 공통 설정
  config.vm.box = BOX_IMAGE
  config.vm.box_version = BOX_VERSION
  config.vm.box_check_update = false
  
  # 공통 provision 스크립트
  config.vm.provision "shell", path: "init_cfg.sh"

  # Ansible Control Node (Jumpbox 역할)
  config.vm.define "controller" do |ctrl|
    ctrl.vm.hostname = "controller"
    ctrl.vm.network "private_network", ip: "192.168.10.10"
    ctrl.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "kubespray-controller"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
    # Ansible 설치
    ctrl.vm.provision "shell", inline: <<-SHELL
      apt-get update
      apt-get install -y python3-pip python3-venv git
    SHELL
  end

  # Control Plane Node
  config.vm.define "controller-0" do |cp|
    cp.vm.hostname = "controller-0"
    cp.vm.network "private_network", ip: "192.168.10.100"
    cp.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "kubespray-controller-0"
      vb.cpus = 2
      vb.memory = 4096
      vb.linked_clone = true
    end
  end

  # Worker Node 0
  config.vm.define "worker-0" do |w0|
    w0.vm.hostname = "worker-0"
    w0.vm.network "private_network", ip: "192.168.10.101"
    w0.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "kubespray-worker-0"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
  end

  # Worker Node 1
  config.vm.define "worker-1" do |w1|
    w1.vm.hostname = "worker-1"
    w1.vm.network "private_network", ip: "192.168.10.102"
    w1.vm.provider "virtualbox" do |vb|
      vb.customize ["modifyvm", :id, "--groups", "/Kubespray-Lab"]
      vb.customize ["modifyvm", :id, "--nicpromisc2", "allow-all"]
      vb.name = "kubespray-worker-1"
      vb.cpus = 2
      vb.memory = 2048
      vb.linked_clone = true
    end
  end
end
```

</details>

<details markdown="1">
<summary>init_cfg.sh (클릭하여 펼치기)</summary>

```bash
#!/usr/bin/env bash

# 타임존 설정
timedatectl set-timezone Asia/Seoul

# SSH 설정 - 패스워드 인증 허용 (ssh-copy-id 사용을 위해)
sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
systemctl restart sshd

# root 패스워드 설정 (실습용)
echo 'root:vagrant' | chpasswd

# /etc/hosts 설정
cat >> /etc/hosts <<EOF
192.168.10.10  controller
192.168.10.100 controller-0
192.168.10.101 worker-0
192.168.10.102 worker-1
EOF

# 기본 패키지 설치
apt-get update
apt-get install -y curl wget vim net-tools

# Python 설치 (Ansible 대상 노드 요구사항)
apt-get install -y python3 python3-pip

# IPv4 포워딩 활성화 (Kubespray 요구사항)
cat >> /etc/sysctl.conf <<EOF
net.ipv4.ip_forward = 1
EOF
sysctl -p

# kubectl 설치 (Jumpbox 전용)
if [ "$(hostname)" = "controller" ]; then
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl"
  chmod +x kubectl
  mv kubectl /usr/local/bin/
fi

echo "=== init_cfg.sh completed ==="
```

</details>

<br>

VM을 생성한다.

```bash
# Vagrantfile이 있는 디렉토리에서 실행
vagrant up
```

4개의 VM이 순차적으로 생성된다. 각 VM에서 `init_cfg.sh` 스크립트가 실행되며, 마지막에 `=== init_cfg.sh completed ===` 메시지가 출력되면 프로비저닝이 완료된 것이다.

```bash
# 생성된 VM 확인
vagrant status
```

```
Current machine states:

controller                running (virtualbox)
controller-0              running (virtualbox)
worker-0                  running (virtualbox)
worker-1                  running (virtualbox)

This environment represents multiple VMs. The VMs are all listed
above with their current state.
```

<br>

## Configuring SSH Access

[Kubernetes The Hard Way - 2. Set Up The Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %})에서 Jumpbox를 설정하고 다른 노드에 SSH 접속을 구성했던 것처럼, Ansible Control Node에서 다른 노드들에 SSH 접속이 가능해야 한다.

```bash
# Ansible Control Node에 접속
vagrant ssh controller

# SSH 키 생성
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa

# 각 노드에 SSH 키 복사
ssh-copy-id root@192.168.10.100  # controller-0
ssh-copy-id root@192.168.10.101  # worker-0
ssh-copy-id root@192.168.10.102  # worker-1
```

SSH 접속이 되는지 테스트하자.

```bash
ssh root@192.168.10.100 "hostname" # controller-0
ssh root@192.168.10.101 "hostname" # worker-0
ssh root@192.168.10.102 "hostname" # worker-1
```

비밀번호 입력 없이 각 노드의 hostname이 출력되면 SSH 키 설정이 완료된 것이다.

<br>

# Set Up Kubespray

여기서부터가 Kubernetes The Hard Way와 결정적으로 다른 부분이다. The Hard Way 이후 단계들을 모두 수동으로 진행했지만, Kubespray는 이를 자동화한다.

## The Hard Way

The Hard Way에서 수동으로 했던 작업들을 복기해 보자.

| The Hard Way 단계 | 수동 작업 내용 |
| --- | --- |
| [4. Provisioning a CA and Generating TLS Certificates]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) | OpenSSL로 CA 및 각 컴포넌트 인증서 생성 |
| [5. Generating Kubernetes Configuration Files]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) | kubectl로 kubeconfig 파일 생성 |
| [6. Generating the Data Encryption Config]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %}) | 암호화 키 및 설정 파일 생성 |
| [7. Bootstrapping the etcd Cluster]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}) | etcd 바이너리 설치, systemd 서비스 구성 |
| [8. Bootstrapping the Kubernetes Control Plane]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) | kube-apiserver, kube-controller-manager, kube-scheduler 설치 및 구성 |
| [9. Bootstrapping the Kubernetes Worker Nodes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) | containerd, kubelet, kube-proxy 설치 및 구성 |
| [11. Provisioning Pod Network Routes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %}) | CNI 플러그인 설정 |

## Kubespray

Kubespray는 이 모든 것을 자동화한다.

### Python 가상환경 생성

Ansible은 Python 애플리케이션이므로 가상환경을 사용한다.

```bash
python3 -m venv venv
source venv/bin/activate
```

### Kubespray 클론

```bash
git clone https://github.com/kubernetes-sigs/kubespray.git
cd kubespray
git checkout release-2.28
```

### 의존성 설치

```bash
pip install -r requirements.txt
```

```
Collecting ansible==9.13.0
  Downloading ansible-9.13.0-py3-none-any.whl (51.5 MB)
...
Successfully installed MarkupSafe-3.0.3 PyYAML-6.0.3 ansible-9.13.0 ansible-core-2.16.15 cffi-2.0.0 cryptography-45.0.2 jinja2-3.1.6 jmespath-1.0.1 netaddr-1.3.0 packaging-26.0 pycparser-3.0 resolvelib-1.0.1
```

Ansible 9.13.0과 필요한 의존성들이 설치된다.

<br>

## 인벤토리 구성

샘플 인벤토리를 복사하여 커스텀 인벤토리를 생성한다.

```bash
cp -rfp inventory/sample inventory/mycluster
```

### 인벤토리 파일 수정

`inventory/mycluster/inventory.ini` 파일을 수정한다:

```ini
[all]
controller-0 ansible_host=192.168.10.100 ip=192.168.10.100
worker-0     ansible_host=192.168.10.101 ip=192.168.10.101
worker-1     ansible_host=192.168.10.102 ip=192.168.10.102

[kube_control_plane]
controller-0

[etcd]
controller-0

[kube_node]
worker-0
worker-1

[calico_rr]

[k8s_cluster:children]
kube_control_plane
kube_node
calico_rr
```

> **중요**: `ip` 변수를 반드시 지정해야 한다. VirtualBox는 첫 번째 NIC로 NAT 인터페이스(`10.0.2.15`)를 사용하는데, `ip`를 생략하면 Kubespray가 이 주소를 사용하여 클러스터 구성에 실패한다. 자세한 내용은 [트러블 슈팅: VirtualBox NAT IP 문제](#트러블-슈팅-virtualbox-nat-ip-문제)를 참고하자.

### 인벤토리 상세 구조

| 그룹 | The Hard Way 대응 | 설명 |
| --- | --- | --- |
| `[all]` | - | 모든 호스트와 접속 정보 정의 |
| `[kube_control_plane]` | Server | 컨트롤 플레인 노드 |
| `[etcd]` | Server (etcd 포함) | etcd 클러스터 노드 |
| `[kube_node]` | Node-0, Node-1 | 워커 노드 |
| `[calico_rr]` | - | Calico Route Reflector (미사용) |
| `[k8s_cluster:children]` | - | 전체 클러스터 그룹 (하위 그룹 포함) |

### vs. Sample Inventory

Kubespray의 `inventory/sample/inventory.ini`와 비교하면 몇 가지 차이가 있다:

| 항목 | Sample | 현재 구성 | 이유 |
| --- | --- | --- | --- |
| **`[all]` 그룹** | 없음 (암시적) | 명시적 정의 | 호스트 정보를 한 곳에서 관리하여 가독성 향상 |
| **호스트 정의 위치** | 각 그룹에서 `ansible_host=` 지정 | `[all]`에서 한번에 정의 | 중복 제거, 유지보수 용이 |
| **etcd 그룹** | `[etcd:children]` | `[etcd]` 직접 나열 | 아래 참고 |

> 참고: **`[etcd]` vs `[etcd:children]`**
>
> Sample inventory는 `[etcd:children]`에 `kube_control_plane`을 포함하여 "control plane 노드 = etcd 노드"로 자동 매핑한다:
>
> ```ini
> [etcd:children]
> kube_control_plane
> ```
>
> 이 방식은 HA 구성(control plane 3대 = etcd 3대)에서 편리하다. 하지만 여기서는 `[etcd]`에 호스트를 직접 나열했다. 이렇게 하면 control plane과 etcd 노드를 **독립적으로** 관리할 수 있어 더 유연하다. 예를 들어 etcd를 별도 노드로 분리하거나, etcd 노드 수를 control plane과 다르게 구성할 때 유용하다.
>
> 현재 구성(컨트롤 플레인 1대)에서는 둘 다 동일하게 동작한다.

<br>

## 클러스터 설정

### 주요 설정 파일

| 파일 | 설명 |
| --- | --- |
| `group_vars/k8s_cluster/k8s-cluster.yml` | 클러스터 전체 설정 |
| `group_vars/k8s_cluster/addons.yml` | 애드온 설정 |

### 설정 확인

`k8s-cluster.yml` 파일에는 클러스터 구성에 필요한 수십 가지 설정이 포함되어 있다. 본격적인 Kubespray 실습에서 더 자세히 다루겠지만, 이번 실습에서 알아두면 좋을 핵심 설정 몇 가지만 짚고 넘어가자.

```bash
cat inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```

### 이번 실습의 핵심 설정

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `kube_network_plugin` | `calico` | CNI 플러그인 (The Hard Way에서 수동 설정했던 부분) |
| `kube_service_addresses` | `10.233.0.0/18` | Service CIDR |
| `kube_pods_subnet` | `10.233.64.0/18` | Pod CIDR |
| `container_manager` | `containerd` | 컨테이너 런타임 |
| `kube_proxy_mode` | `ipvs` | kube-proxy 모드 (iptables 대신 IPVS 사용) |
| `dns_mode` | `coredns` | 클러스터 DNS |
| `cluster_name` | `cluster.local` | 클러스터 도메인 |

```yaml
# CNI 플러그인 - The Hard Way에서는 별도로 Calico를 설치했지만 Kubespray가 자동 처리
kube_network_plugin: calico

# 네트워크 CIDR - The Hard Way의 POD_CIDR, SERVICE_CIDR에 해당
kube_service_addresses: 10.233.0.0/18
kube_pods_subnet: 10.233.64.0/18

# 컨테이너 런타임 - The Hard Way에서 containerd를 수동 설치했던 부분
container_manager: containerd

# kube-proxy 모드 - iptables 대신 IPVS 사용 (더 나은 성능)
kube_proxy_mode: ipvs
```

> 이 설정들은 The Hard Way에서 수동으로 구성했던 것들이다. Kubespray는 이 모든 것을 `k8s-cluster.yml` 파일 하나로 선언적으로 관리한다.

### 애드온 설정 (선택사항)

Kubespray는 인기 있는 Kubernetes 애드온을 쉽게 활성화할 수 있다. 공식 문서에서는 Metrics Server 활성화를 권장한다:

> Kubespray also offers to easily enable popular kubernetes add-ons. You can modify the list of add-ons in `inventory/mycluster/group_vars/k8s_cluster/addons.yml`. Let's enable the metrics server as this is a **crucial monitoring element** for the kubernetes cluster.

`inventory/mycluster/group_vars/k8s_cluster/addons.yml`에서 Metrics Server를 활성화한다:

```bash
# metrics_server_enabled를 true로 변경
vi inventory/mycluster/group_vars/k8s_cluster/addons.yml
```

```yaml
metrics_server_enabled: true
```

Metrics Server는 `kubectl top nodes`, `kubectl top pods` 명령어로 리소스 사용량을 확인하거나, HPA(Horizontal Pod Autoscaler)를 사용하기 위해 필요하다.

```bash
# 설정 확인
cat addons.yml | grep metrics_server_enabled
```
```
metrics_server_enabled: true
```

<br>

## 클러스터 배포

이제 The Hard Way에서 수동으로 수행했던 모든 작업을 **단일 명령**으로 실행한다.

```bash
# kubespray 디렉토리에서 실행 (ansible.cfg가 있는 위치)
cd ~/kubespray

# $USERNAME: SSH 접속 사용자 (이 실습에서는 root)
ansible-playbook -i inventory/mycluster/inventory.ini \
  -u $USERNAME -b -v \
  --private-key=~/.ssh/id_rsa \
  cluster.yml
```

| 옵션 | 설명 |
| --- | --- |
| `-i` | 인벤토리 파일 지정 |
| `-u` | SSH 사용자명 |
| `-b` | become (sudo 권한으로 실행) |
| `-v` | verbose (상세 로그 출력) |
| `--private-key` | SSH 개인키 경로 |

### 실행 위치
반드시 `ansible.cfg`가 있는 kubespray 디렉토리에서 실행해야 한다. Ansible은 설정 파일을 찾을 때 **현재 디렉토리의 `ansible.cfg`를 우선** 적용한다. Kubespray는 자체 `ansible.cfg`를 포함하고 있어, 해당 디렉토리에서 실행해야 올바른 설정이 적용된다. 
> `ansible.cfg` 설정 우선순위에 대한 자세한 내용은 [Ansible 시리즈 - 4. Ad-hoc 명령어]({% post_url 2026-01-12-Kubernetes-Ansible-04 %})를 참고하자.

<br>

### 트러블 슈팅: 인벤토리 경로

모든 PLAY에서 `skipping: no hosts matched`가 출력되고 아무 작업도 수행되지 않는다면, 인벤토리 **파일** 경로를 확인하자.

```
[WARNING]: Unable to parse /home/vagrant/kubespray/inventory/mycluster as an inventory source
[WARNING]: No inventory was parsed, only implicit localhost is available
```

`-i` 옵션에 디렉토리가 아닌 **파일 경로**를 지정하는 것이 좋다
- `-i inventory/mycluster/` (디렉토리): [공식 문서](https://kubespray.io/#/docs/getting_started/setting-up-your-first-cluster)에서 사용하는 방식이지만, 환경에 따라 동작하지 않을 수 있음
- `-i inventory/mycluster/inventory.ini` (파일): 명시적으로 파일을 지정하는 방식, 항상 동작
> 실제로 공식 문서대로 디렉토리를 지정했지만 모든 PLAY가 `skipping: no hosts matched`로 건너뛰어졌다. 파일 경로를 명시하니 정상 동작했다.

<br>

### 트러블 슈팅: `$USERNAME` 변수 오류

`ansible-playbook: error: argument -u/--user: expected one argument` 오류가 발생하거나, 오류 없이 `ansible-playbook` 명령어의 help만 출력된다면 `$USERNAME` 환경변수가 설정되지 않은 것이다.

[Kubespray 공식 문서](https://kubespray.io/#/docs/getting_started/setting-up-your-first-cluster?id=configuring-ssh-access)에서는 명령어 실행 전 `USERNAME=$(whoami)`로 변수를 설정하는 단계가 있다. `$USERNAME` 대신 `root`를 직접 지정해도 된다.

<br>

### 트러블 슈팅: VirtualBox NAT IP 문제

Worker 노드 조인 단계에서 다음과 같은 오류가 발생할 수 있다:

```
TASK [kubernetes/control-plane : kubeadm | Initialize first control plane node] ***
...
TASK [kubernetes/node : kubeadm | Join node to cluster] ************************
fatal: [worker-0]: FAILED! => {
    "attempts": 3,
    "changed": true,
    "cmd": ["kubeadm", "join", "--config", "/etc/kubernetes/kubeadm-client.conf", ...],
    "msg": "non-zero return code",
    "stderr": "error execution phase preflight: couldn't validate the identity of the API Server: 
        Get \"https://10.0.2.15:6443/api/v1/namespaces/kube-public/configmaps/cluster-info?timeout=10s\": 
        dial tcp 10.0.2.15:6443: connect: connection refused",
    ...
}
fatal: [worker-1]: FAILED! => { ... (동일한 오류) ... }

PLAY RECAP *********************************************************************
controller-0    : ok=XXX  changed=XX   unreachable=0    failed=0    ...
worker-0        : ok=XX   changed=X    unreachable=0    failed=1    ...
worker-1        : ok=XX   changed=X    unreachable=0    failed=1    ...
```

<br>

| 구분 | 내용 |
| --- | --- |
| **원인** | 멀티 NIC 환경에서 Kubespray IP 자동 감지 실패. NAT 인터페이스(`10.0.2.15`)를 API Server 주소로 잘못 선택 |
| **해결** | 인벤토리에 `ip` 변수 명시: `controller-0 ansible_host=192.168.10.100 ip=192.168.10.100` |
| **결과** | 멱등성 덕분에 실패한 단계만 재처리, 5분 내외로 클러스터 구성 완료 |

VirtualBox VM은 기본적으로 NAT 인터페이스(`10.0.2.15`)를 첫 번째 네트워크로 사용한다. Kubespray가 이 주소를 API Server 주소로 감지하면, Worker 노드들이 `https://10.0.2.15:6443`으로 접속을 시도하지만, 실제 API Server는 Private IP(`192.168.10.100`)에서 리스닝하고 있어 연결이 거부된다.

<br>

이 문제는 지금까지 기존 시리즈에서 **수도 없이** 다뤄왔다:

- [Kubernetes The Hard Way - 1단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}#vagrant-nic1-nic2-의미): Vagrant VM의 NIC1(NAT)과 NIC2(Private) 구조 설명
- [Ansible 시리즈 - Managed Node]({% post_url 2026-01-12-Kubernetes-Ansible-02 %}#8-네트워크-인터페이스-확인): `eth0`(10.0.2.15)은 NAT, `eth1`은 내부 통신용
- [Kubeadm 시리즈 - kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#설정-파일-방식): `node-ip` 미설정 시 NAT IP(10.0.2.15)가 사용되어 노드 간 통신 문제 발생
- [Kubeadm 시리즈 - Flannel CNI]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#flannel-개요): `--iface` 옵션으로 올바른 인터페이스 지정 필요

그렇게 열심히 공부해 놓고도 까먹으면, 15-30분간의 Kubespray 배포 끝에 **마지막 `kubeadm join` 단계에서 실패**하는 안타까운 결과를 보게 된다. 기억하자: **Vagrant + VirtualBox 환경에서는 항상 `ip` 변수를 명시해야 한다.**

<br>

문제 해결을 위해 인벤토리에 `ip` 변수를 명시적으로 지정한다:

```ini
[all]
controller-0 ansible_host=192.168.10.100 ip=192.168.10.100
worker-0     ansible_host=192.168.10.101 ip=192.168.10.101
worker-1     ansible_host=192.168.10.102 ip=192.168.10.102
```

- `ansible_host`: Ansible이 SSH로 접속할 주소
- `ip`: Kubernetes 내부 통신에 사용할 주소 (API Server 광고 주소, kubelet 바인딩 등)

<br>

수정 후 다시 `ansible-playbook`을 실행한다:

```bash
ansible-playbook -i inventory/mycluster/inventory.ini \
  -u root -b -v \
  --private-key=~/.ssh/id_rsa \
  cluster.yml
```

이미 완료된 작업은 `ok` 상태로 빠르게 건너뛰고, 실패했던 단계부터 정상 처리된다:

```
PLAY RECAP *********************************************************************
controller-0    : ok=XXX  changed=X    unreachable=0    failed=0    ...
worker-0        : ok=XXX  changed=XX   unreachable=0    failed=0    ...
worker-1        : ok=XXX  changed=XX   unreachable=0    failed=0    ...

Monday 27 January 2026  XX:XX:XX +0900 (0:00:00.123)    0:05:32.456 ***********
===============================================================================
kubernetes/kubeadm : kubeadm | Join node to cluster -------------------- 45.12s
download : Download_file | Download item -------------------------------- 8.34s
...
```

전체를 처음부터 다시 할 필요 없이, 대부분의 작업이 `ok`로 스킵되어 **5분 내외**로 완료된다.

<br>

### 트러블 슈팅: etcd 클러스터 헬스 체크 실패

NAT IP 문제를 뒤늦게 발견하여 인벤토리를 수정한 후 다시 실행하면, 이번엔 etcd 단계에서 실패할 수 있다:

```
FAILED - RETRYING: [controller-0]: Configure | Wait for etcd cluster to be healthy (4 retries left).
FAILED - RETRYING: [controller-0]: Configure | Wait for etcd cluster to be healthy (3 retries left).
...

TASK [etcd : Configure | Wait for etcd cluster to be healthy] *********************
fatal: [controller-0]: FAILED! => {
    "attempts": 4,
    "cmd": "... /usr/local/bin/etcdctl endpoint --cluster health ...",
    "stderr": "... dial tcp 192.168.10.100:2379: connect: connection refused ..."
}

PLAY RECAP ************************************************************************
controller-0    : ok=460  changed=17   unreachable=0    failed=1    ...
```

| 구분 | 내용 |
| --- | --- |
| **원인** | 이전 실행에서 etcd가 NAT IP(`10.0.2.15`)에 바인딩되어 설치됨. <br>인벤토리 수정 후에도 기존 etcd 설정은 변경되지 않음 |
| **해결** | `reset.yml`로 클러스터 초기화 후 재배포 |
| **교훈** | `ip` 변수는 **처음부터** 설정해야 한다. 중간에 수정하면 이미 설치된 컴포넌트와 불일치 발생 |

Ansible의 멱등성은 "같은 상태면 변경하지 않음"을 의미한다. etcd가 이미 실행 중이면 설정을 덮어쓰지 않기 때문에, 잘못된 IP로 바인딩된 상태가 유지된다.

<br>

문제 해결을 위해 `reset.yml` 플레이북으로 클러스터를 완전히 초기화한 후 다시 배포한다:

```bash
# 클러스터 초기화
ansible-playbook -i inventory/mycluster/inventory.ini \
  -u root -b -v \
  --private-key=~/.ssh/id_rsa \
  reset.yml
```

실행 중 확인 프롬프트가 나타난다:

```
TASK [reset : Reset | confirm reset] ******************************************
[reset : Reset | confirm reset]
Are you sure you want to reset cluster state? Type 'yes' to reset your cluster.: yes
```

클러스터를 완전히 삭제하는 위험한 작업이므로, `yes`를 입력해야 진행된다.

```bash
# 다시 배포
ansible-playbook -i inventory/mycluster/inventory.ini \
  -u root -b -v \
  --private-key=~/.ssh/id_rsa \
  cluster.yml
```

이번엔 `ip` 변수가 처음부터 설정되어 있으므로, etcd를 포함한 모든 컴포넌트가 올바른 IP(`192.168.10.100`)에 바인딩된다.

```
PLAY RECAP *****************************************************************************
controller-0               : ok=661  changed=111  unreachable=0    failed=0    skipped=1005 rescued=0    ignored=6   
worker-0                   : ok=439  changed=61   unreachable=0    failed=0    skipped=628  rescued=0    ignored=1   
worker-1                   : ok=439  changed=61   unreachable=0    failed=0    skipped=627  rescued=0    ignored=1   

Wednesday 28 January 2026  01:01:52 +0900 (0:00:00.036)       0:07:00.844 ***** 
=============================================================================== 
download : Download_container | Download image if required --------------------- 48.84s
download : Download_container | Download image if required --------------------- 33.23s
download : Download_container | Download image if required --------------------- 30.30s
kubernetes/kubeadm : Join to cluster if needed --------------------------------- 15.97s
...
```

모든 노드가 `failed=0`으로 성공적으로 배포되었다.

> **참고: `reset.yml` 후 재배포 시 나타나는 경고**
>
> `reset.yml`로 클러스터를 초기화한 후 다시 `cluster.yml`을 실행하면, etcd 버전 체크 단계에서 다음과 같은 실패가 나타날 수 있다:
> ```
> TASK [etcd : Get currently-deployed etcd version] **************************************
> fatal: [controller-0]: FAILED! => {"msg": "[Errno 2] No such file or directory: b'/usr/local/bin/etcd'"}
> ```
> 이는 reset으로 etcd 바이너리가 삭제되어 버전 확인이 실패한 것이다. Kubespray는 이 경우를 처리하도록 설계되어 있어서, 버전 체크 실패 후 etcd를 새로 설치하는 단계로 정상 진행된다. `PLAY RECAP`에서 `ignored=6` 등으로 표시되며, `failed=0`이면 정상이다.

<br>

### Kubespray가 자동으로 수행하는 작업

Kubespray의 `cluster.yml` 플레이북이 실행되면 다음 작업들이 자동으로 수행된다:

| Kubespray Role | The Hard Way 단계 | 자동화 내용 |
| --- | --- | --- |
| `bootstrap-os` | - | OS 기본 설정 (시간 동기화, 패키지 업데이트) |
| `kubernetes/preinstall` | - | 커널 모듈, sysctl, Swap 비활성화 |
| `container-engine/containerd` | [9.1. Worker Node 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}) | containerd 설치 및 설정 |
| `download` | [2. Set Up The Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %}) | 바이너리 및 이미지 다운로드 |
| `etcd` | [7. Bootstrapping etcd]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}) | etcd 클러스터 구성 |
| `kubernetes/control-plane` | [8. Bootstrapping Control Plane]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) | 컨트롤 플레인 구성 (kubeadm init) |
| `kubernetes/node` | [9. Bootstrapping Worker Nodes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) | 워커 노드 조인 (kubeadm join) |
| `network_plugin/calico` | [11. Pod Network Routes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %}) | CNI 플러그인 설치 |
| `kubernetes-apps` | - | CoreDNS, Metrics Server 등 애드온 설치 |

그리고 The Hard Way에서 가장 복잡했던 **인증서 생성**([4. TLS Certificates]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}))과 **kubeconfig 생성**([5. Configuration Files]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}))도 내부적으로 kubeadm이 자동으로 처리한다.

<br>

# Access the Kubernetes Cluster

클러스터 배포가 완료되면 컨트롤 플레인 노드에 kubeconfig 파일이 생성된다. 컨트롤 플레인에서 직접 kubectl을 사용할 수도 있지만, 관리용 머신(Jumpbox)에서도 클러스터를 관리할 수 있도록 kubeconfig를 복사해서 사용하는 것이 일반적이다.

> 참고: **왜 관리용 머신에서 kubectl을 사용하는가?**
>
> 컨트롤 플레인에서 직접 kubectl을 사용해도 되지만, 운영 환경에서는 관리용 머신(Jumpbox, 로컬 PC 등)에서 원격으로 관리하는 것이 권장된다:
> - **역할 분리**: 컨트롤 플레인은 API Server, etcd 등 핵심 컴포넌트 실행에 집중
> - **보안**: 컨트롤 플레인에 대한 직접 SSH 접근 최소화
> - **운영 편의**: 히스토리, 스크립트, 도구를 한 곳에서 관리

## The Hard Way

The Hard Way에서는 두 가지 방식으로 kubectl을 사용했다:

- **컨트롤 플레인(server)에서 직접 사용**: [5. Configuration Files]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %})에서 생성한 `admin.kubeconfig`(`--server=https://127.0.0.1:6443`) 사용
- **Jumpbox에서 원격 사용**: [10. Configuring kubectl for Remote Access]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-10 %})에서 원격 접근용 kubeconfig(`--server=https://server.kubernetes.local:6443`) 생성

## Kubespray

Kubespray 배포가 완료되면 컨트롤 플레인 노드(`controller-0`)에 kubeconfig 파일(`/etc/kubernetes/admin.conf`)이 자동으로 생성된다. Jumpbox에서 클러스터를 관리하려면 kubectl 설치와 kubeconfig 복사가 필요하다.

### kubectl 설치

앞서 `init_cfg.sh`에서 Jumpbox에 kubectl을 자동 설치하도록 구성했다. 수동으로 설치해야 하는 경우 다음 명령어를 사용한다:

```bash
# kubectl 다운로드 (ARM64 - x86_64는 arm64를 amd64로 변경)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/arm64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

### kubeconfig 가져오기

```bash
# Jumpbox(controller)에서 실행
# kubeconfig 저장 디렉토리 생성
mkdir -p ~/.kube

# 컨트롤 플레인 노드의 kubeconfig를 Jumpbox로 복사
scp root@192.168.10.100:/etc/kubernetes/admin.conf ~/.kube/config

# API Server 주소를 localhost에서 컨트롤 플레인 IP로 변경 (아래 트러블슈팅 참고)
sed -i 's/127.0.0.1/192.168.10.100/g' ~/.kube/config
```

### 클러스터 접속 확인

```bash
kubectl get nodes
```

```
NAME           STATUS   ROLES           AGE   VERSION
controller-0   Ready    control-plane   11m   v1.32.11
worker-0       Ready    <none>          10m   v1.32.11
worker-1       Ready    <none>          10m   v1.32.11
```

모든 노드가 `Ready` 상태로 클러스터에 정상 참여했다.

### 트러블 슈팅: kubeconfig localhost 문제

Jumpbox에서 `kubectl get nodes`를 실행했을 때 다음과 같은 오류가 발생할 수 있다:

```
E0128 01:10:24.389313   19707 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: 
    Get \"https://127.0.0.1:6443/api?timeout=32s\": dial tcp 127.0.0.1:6443: connect: connection refused"
The connection to the server 127.0.0.1:6443 was refused - did you specify the right host or port?
```

| 구분 | 내용 |
| --- | --- |
| **원인** | kubeadm이 생성한 `admin.conf`는 `server: https://127.0.0.1:6443`으로 설정됨. <br>컨트롤 플레인에서는 동작하지만 Jumpbox에서는 localhost에 API Server가 없음 |
| **해결** | `sed -i 's/127.0.0.1/192.168.10.100/g' ~/.kube/config`로 API Server 주소 변경 |
| **결과** | Jumpbox에서 원격으로 클러스터 관리 가능 |

이 문제는 기존 시리즈에서도 다뤘다:

- [The Hard Way - 10. Configuring kubectl]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-10 %}): localhost용 `admin.kubeconfig`(`127.0.0.1`)와 원격용 `~/.kube/config`(`server.kubernetes.local`)를 **별도로 생성**
- [Kubeadm 시리즈 - 01-3]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#설정-파일-방식): `--apiserver-advertise-address=192.168.10.100`을 명시하여 `admin.conf`에 **처음부터 올바른 IP가 설정**됨. 덕분에 이 문제를 피할 수 있었음

<br>

# Smoke Test

[Kubernetes The Hard Way - 12. Smoke Test]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %})와 동일한 검증 작업을 수행한다.

## Metrics

Metrics Server 애드온이 정상적으로 설치되었는지 확인한다.

```bash
kubectl top nodes
```

```
NAME           CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)   
controller-0   98m          7%       1939Mi          66%         
worker-0       40m          2%       977Mi           99%         
worker-1       43m          3%       994Mi           101%  
```

> **참고**: Metrics가 수집되기까지 몇 분 정도 소요될 수 있다.

<br>

## Network

Pod 간 네트워크 통신이 정상적으로 동작하는지 확인한다.

### Pod 간 통신 테스트

터미널 1에서 Pod 생성 후 IP 확인:

```bash
kubectl run myshell1 -it --rm --image busybox -- sh
/ # hostname -i
10.233.107.4
```

터미널 2에서 다른 Pod를 생성하고 myshell1의 IP로 ping:

```bash
kubectl run myshell2 -it --rm --image busybox -- sh
/ # ping 10.233.107.4
PING 10.233.107.4 (10.233.107.4): 56 data bytes
64 bytes from 10.233.107.4: seq=0 ttl=62 time=0.686 ms
64 bytes from 10.233.107.4: seq=1 ttl=62 time=0.620 ms
64 bytes from 10.233.107.4: seq=2 ttl=62 time=0.779 ms
^C
--- 10.233.107.4 ping statistics ---
3 packets transmitted, 3 packets received, 0% packet loss
round-trip min/avg/max = 0.620/0.695/0.779 ms
```

서로 다른 Pod 간 통신이 정상 동작한다. Calico CNI가 Pod 네트워크를 올바르게 구성했음을 확인할 수 있다.

<br>

## Deployments

Deployment가 정상적으로 생성되는지 확인한다.

```bash
kubectl create deployment nginx --image=nginx
# deployment.apps/nginx created

kubectl get pods -l app=nginx
# NAME                     READY   STATUS    RESTARTS   AGE
# nginx-5869d7778c-9nx4v   1/1     Running   0          24s
```

<br>

## Port Forwarding

포트 포워딩이 정상적으로 동작하는지 확인한다.

터미널 1:

```bash
POD_NAME=$(kubectl get pods -l app=nginx -o jsonpath="{.items[0].metadata.name}")
kubectl port-forward $POD_NAME 8080:80
# Forwarding from 127.0.0.1:8080 -> 80
# Forwarding from [::1]:8080 -> 80
```

터미널 2:

```bash
curl --head http://127.0.0.1:8080
# HTTP/1.1 200 OK
# Server: nginx/1.29.4
# Date: Tue, 27 Jan 2026 16:19:13 GMT
# Content-Type: text/html
# Content-Length: 615
# Last-Modified: Tue, 09 Dec 2025 18:28:10 GMT
# Connection: keep-alive
# ETag: "69386a3a-267"
# Accept-Ranges: bytes
```

<br>

## Logs

컨테이너 로그를 조회할 수 있는지 확인한다.

```bash
kubectl logs $POD_NAME
# /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
# /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
# /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
# 10-listen-on-ipv6-by-default.sh: info: Getting the checksum of /etc/nginx/conf.d/default.conf
# 10-listen-on-ipv6-by-default.sh: info: Enabled listen on IPv6 in /etc/nginx/conf.d/default.conf
# /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
# /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
# /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
# /docker-entrypoint.sh: Configuration complete; ready for start up
# 2026/01/27 16:18:34 [notice] 1#1: using the "epoll" event method
# 2026/01/27 16:18:34 [notice] 1#1: nginx/1.29.4
# ...
# 127.0.0.1 - - [27/Jan/2026:16:19:13 +0000] "HEAD / HTTP/1.1" 200 0 "-" "curl/7.88.1" "-"
```

앞서 `curl --head`로 요청한 로그(`HEAD / HTTP/1.1`)도 확인할 수 있다.

<br>

## Exec

컨테이너 내부에서 명령을 실행할 수 있는지 확인한다.

```bash
kubectl exec -ti $POD_NAME -- nginx -v
# nginx version: nginx/1.29.4
```

<br>

## Services

### NodePort Service

Service를 통해 외부에서 접근할 수 있는지 확인한다.

```bash
kubectl expose deployment nginx --port 80 --type NodePort
# service/nginx exposed

NODE_PORT=$(kubectl get svc nginx -o jsonpath='{.spec.ports[0].nodePort}')
echo $NODE_PORT
# 30531
```

워커 노드의 IP로 접근:

```bash
curl -I http://192.168.10.101:$NODE_PORT
# HTTP/1.1 200 OK
# Server: nginx/1.29.4
# Date: Tue, 27 Jan 2026 16:21:08 GMT
# Content-Type: text/html
# Content-Length: 615
# Last-Modified: Tue, 09 Dec 2025 18:28:10 GMT
# Connection: keep-alive
# ETag: "69386a3a-267"
# Accept-Ranges: bytes
```

```
# 예상 출력
HTTP/1.1 200 OK
Server: nginx/1.x.x
...
```

### Local DNS

클러스터 내부 DNS가 네임스페이스 간에 정상 동작하는지 확인한다.

```bash
# 네임스페이스 생성
kubectl create namespace dev
# namespace/dev created

kubectl get ns
# NAME              STATUS   AGE
# default           Active   21m
# dev               Active   1s
# kube-node-lease   Active   21m
# kube-public       Active   21m
# kube-system       Active   21m

# dev 네임스페이스에 nginx 배포
kubectl create deployment nginx --image=nginx -n dev
# deployment.apps/nginx created

kubectl expose deployment nginx --port 80 --type ClusterIP -n dev
# service/nginx exposed
```

다른 네임스페이스(default)에서 dev 네임스페이스의 서비스에 접근한다.

```bash
# default 네임스페이스에서 dev 네임스페이스의 서비스 접근
kubectl run curly -it --rm --image curlimages/curl:7.70.0 -- /bin/sh
/ $ curl --head http://nginx.dev:80
# HTTP/1.1 200 OK
# Server: nginx/1.29.4
# Date: Tue, 27 Jan 2026 16:22:43 GMT
# Content-Type: text/html
# Content-Length: 615
# Last-Modified: Tue, 09 Dec 2025 18:28:10 GMT
# Connection: keep-alive
# ETag: "69386a3a-267"
# Accept-Ranges: bytes
```

> **`nginx.dev`는 무엇인가?**
>
> Kubernetes는 클러스터 내부에서 서비스 디스커버리를 위해 CoreDNS를 사용한다. 서비스가 생성되면 자동으로 DNS 레코드가 등록되며, 다음 형식으로 접근할 수 있다:
>
> ```
> <service-name>.<namespace>.svc.cluster.local
> ```
>
> `nginx.dev`는 축약형으로, 전체 FQDN은 `nginx.dev.svc.cluster.local`이다. 같은 클러스터 내에서는 `<service>.<namespace>` 형식만으로도 CoreDNS가 자동으로 해석해준다. 이를 통해 Pod들은 서비스의 ClusterIP를 알 필요 없이 DNS 이름만으로 다른 서비스에 접근할 수 있다.

<br>

# Cleaning Up

## Kubernetes 리소스 정리

```bash
kubectl delete namespace dev
kubectl delete deployment nginx
kubectl delete svc nginx
```

## 클러스터 초기화 (VM 유지)

VM은 유지하면서 클러스터 상태만 초기화하려면:

```bash
ansible-playbook -i inventory/mycluster/inventory.ini \
  -u $USERNAME -b -v \
  --private-key=~/.ssh/id_rsa \
  reset.yml
```

## VM 삭제

```bash
vagrant destroy -f
```

<br>

# Kubernetes The Hard Way vs. Kubespray 비교

실습을 통해 확인한 두 방식의 차이를 정리한다.

| 단계 | Kubernetes The Hard Way | Kubespray |
| --- | --- | --- |
| [1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) | VirtualBox, Vagrant 설치 | 동일 + Python, Ansible 설치 |
| [2. Set Up The Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %}) | 바이너리 수동 다운로드 | `download` role에서 자동 |
| [3. Provisioning Compute Resources]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %}) | Vagrant로 VM 생성 | 동일 |
| [4. Provisioning TLS Certificates]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) | OpenSSL로 수동 생성 | kubeadm에서 자동 |
| [5. Generating Configuration Files]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) | kubectl로 수동 생성 | kubeadm에서 자동 |
| [6. Data Encryption Config]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %}) | 수동 생성 | 자동 |
| [7. Bootstrapping etcd]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}) | systemd 서비스 수동 구성 | `etcd` role에서 자동 |
| [8. Bootstrapping Control Plane]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) | systemd 서비스 수동 구성 | `kubernetes/control-plane` role에서 자동 |
| [9. Bootstrapping Worker Nodes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) | containerd, kubelet 수동 설치 | `kubernetes/node` role에서 자동 |
| [10. Configuring kubectl]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-10 %}) | kubeconfig 수동 복사 | 자동 생성, 복사만 필요 |
| [11. Pod Network Routes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %}) | bridge CNI 수동 설정 | Calico 자동 설치 |
| [12. Smoke Test]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}) | 수동 검증 | 동일 |

<br>

## 핵심 차이점

| 구분 | Kubernetes The Hard Way | Kubespray |
| --- | --- | --- |
| **명령 횟수** | 수백 개의 명령어 | `ansible-playbook cluster.yml` 하나 |
| **소요 시간** | 수 시간 (학습 포함) | 15-30분 |
| **재현성** | 낮음 (수동 작업) | 높음 (코드화) |
| **멱등성** | 없음 | 있음 (Ansible) |
| **CNI** | bridge (기본) | Calico (프로덕션급) |
| **목적** | 학습 | 프로덕션 배포 |

<br>

# 결과

Kubespray를 사용하면 Kubernetes The Hard Way에서 수동으로 수행했던 모든 작업을 **단일 명령**으로 자동화할 수 있다. 

1주차에 Kubernetes The Hard Way로 클러스터를 손으로 직접 구성하면서 각 구성 요소를 이해했기 때문에, 이제 Kubespray가 **무엇을 자동화해주는지** 정확히 알 수 있다. 인증서 생성, etcd 구성, 컨트롤 플레인 부트스트래핑 등 복잡한 작업들이 Ansible Role로 추상화되어 있다.

다음 글에서는 Kubespray의 주요 설정 옵션과 커스터마이징 방법을 살펴본다.

<br>
# 여담
> ~~또 다시~~ 반성

이번 실습에서 마주친 트러블슈팅 이슈들을 되돌아보니 조금 부끄럽다.

- **VirtualBox NAT IP 문제**: The Hard Way, Ansible, Kubeadm 시리즈에서 수없이 언급했던 멀티 NIC 환경의 IP 자동 감지 문제를 잊었다.
- **kubeconfig localhost 문제**: 원격 접근 시 `127.0.0.1`이 아닌 실제 API Server IP를 사용해야 한다는 것도 이미 배운 내용이었다.

모두 **"이미 공부했던 것들"**이다. 블로그에 정리까지 해놓고, 실습에서는 까맣게 잊어버렸다.

자동화 도구를 사용하면 복잡한 작업이 간단해지지만, 문제가 발생했을 때는 결국 **기본기**가 필요하다. 에러 메시지를 읽고, 원인을 파악하고, 해결책을 찾는 과정에서 과거에 학습한 지식이 떠오르지 않으면 같은 실수를 반복하게 된다.

실습 환경에서의 실수는 그나마 괜찮다. 시간을 들여 디버깅하면 되고, 클러스터를 리셋하고 다시 시작할 수도 있다. 시간을 낭비할 뿐이다.

하지만 **운영 환경**에서는 다르다. 한 번의 설정 실수가 서비스 장애로 이어질 수 있고, "아, 이거 예전에 배웠는데..."라며 뒤늦게 떠올리는 것은 이미 늦은 후다. 사소해 보이는 네트워크 설정 하나, IP 주소 하나가 전체 클러스터의 운명을 좌우할 수 있다.

**배운 것을 잊지 않도록**, 그리고 **잊더라도 빠르게 찾아볼 수 있도록** 기록을 꾸준히 남겨야겠다.
<br>


