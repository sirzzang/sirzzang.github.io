---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 2. Set Up The Jumpbox"
excerpt: "Jumpbox에 Kubernetes The Hard Way 저장소를 클론하고, 클러스터 구성에 필요한 모든 바이너리(kubectl, kube-apiserver, etcd 등)를 다운로드하여 역할별로 분류해 보자."
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


이번 글의 목표는 **설치에 필요한 각종 파일 준비**다. [Kubernetes the Hard Way 튜토리얼의 Set Up The Jumpbox 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/02-jumpbox.md)를 따라 진행한다.

![kubernetes-the-hard-way-cluster-structure-2]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-2.png)

<br>

# Jumpbox 구성

Jumpbox(`jumpbox`)는 실습 동안 커맨드를 실행하기 위해 사용되는 관리용 호스트다. Kubernetes 클러스터를 처음부터 구축할 때 사용할 홈베이스 역할을 하는 관리 머신으로 생각하면 된다. 

> 참고: Jumpbox
> 
> Jumpbox(또는 Jump Host, Bastion Host)는 보안이 강화된 네트워크 환경에서 다른 서버에 접근하기 위한 중간 게이트웨이 역할을 하는 서버를 의미한다.
> 내부 네트워크의 서버들에 직접 접근하지 않고, jumpbox를 통해 간접적으로 접근함으로써 보안을 강화할 수 있다.
> 
> 이 실습에서는 Kubernetes 클러스터를 구성하는 모든 머신에 접근하고 관리 명령을 실행하기 위한 중앙 관리 머신으로 사용된다.

<br>

Jumpbox 구성을 위해 시작하기 전에 몇 가지 명령줄 유틸리티를 설치하고, Kubernetes The Hard Way git 저장소를 클론한다. 이 저장소에는 튜토리얼 전반에 걸쳐 다양한 Kubernetes 컴포넌트를 구성하는 데 사용될 추가 설정 파일들이 포함되어 있다.

<br>

## Jumpbox 접속

원본 튜토리얼에서는 `ssh root@jumpbox`로 접속하지만, 이 실습에서는 `vagrant ssh jumpbox`를 사용한다.

```bash
# VM 상태 확인
$ vagrant status
Current machine states:

jumpbox                   running (virtualbox)
server                    running (virtualbox)
node-0                    running (virtualbox)
node-1                    running (virtualbox)

# jumpbox 접속
$ vagrant ssh jumpbox
Linux jumpbox 6.1.0-40-arm64 #1 SMP Debian 6.1.153-1 (2025-09-20) aarch64
# ... (시스템 메시지) ...
Last login: Mon Jan  5 23:16:46 2026 from 10.0.2.2

# 접속 확인
root@jumpbox:~# whoami
root
root@jumpbox:~# pwd
/root
```

### root 계정

root 계정 설정은 [이전 글의 Prerequisites 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}#root-계정-설정)에서 이미 완료했다.

```bash
root@jumpbox:~# cat /home/vagrant/.bashrc | tail -n 1
sudo su -
```

vagrant 계정으로 로그인하면 자동으로 `sudo su -`가 실행되어 root 계정으로 전환된다. 모든 커맨드는 root 계정으로 실행되어야 하며, 이는 편의를 위한 설정이다. 세팅 시 필요한 커맨드에 `sudo`를 매번 붙이지 않아도 되므로 작업이 훨씬 간편해진다.

<br>

## 툴 설치

필요한 명령줄 유틸리티들은 [이전 글의 Prerequisites 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}#필수-툴-설치)에서 이미 설치했다. 설치 여부를 확인해보자.

```bash
root@jumpbox:~# apt-get update && apt install tree git jq yq unzip vim sshpass -y
Hit:1 http://security.debian.org/debian-security bookworm-security InRelease
Hit:2 http://httpredir.debian.org/debian bookworm InRelease
Get:3 http://httpredir.debian.org/debian bookworm-updates InRelease [55.4 kB]
Fetched 55.4 kB in 1s (74.8 kB/s)   
Reading package lists... Done
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
tree is already the newest version (2.1.0-1).
git is already the newest version (1:2.39.5-0+deb12u2).
jq is already the newest version (1.6-2.1+deb12u1).
yq is already the newest version (3.1.0-3).
unzip is already the newest version (6.0-28).
vim is already the newest version (2:9.0.1378-2+deb12u2).
sshpass is already the newest version (1.09-1).
0 upgraded, 0 newly installed, 0 to remove and 2 not upgraded.
```

<br>

## Github Repository 동기화

Kubernetes The Hard Way 저장소를 클론해야 한다. 이 저장소에는 Kubernetes 클러스터 구성에 필요한 설정 파일들(configs 디렉토리), systemd 유닛 파일들(units 디렉토리), 그리고 바이너리 다운로드 목록 등이 포함되어 있다.


```bash
# 현재 디렉토리 확인
root@jumpbox:~# pwd
/root

# git 저장소 동기화
root@jumpbox:~# git clone --depth 1 https://github.com/kelseyhightower/kubernetes-the-hard-way.git
Cloning into 'kubernetes-the-hard-way'...
remote: Enumerating objects: 41, done.
remote: Counting objects: 100% (41/41), done.
remote: Compressing objects: 100% (40/40), done.
remote: Total 41 (delta 3), reused 14 (delta 1), pack-reused 0 (from 0)
Receiving objects: 100% (41/41), 29.27 KiB | 4.18 MiB/s, done.
Resolving deltas: 100% (3/3), done.
root@jumpbox:~# cd kubernetes-the-hard-way
```
> 참고: `--depth 1` 옵션
> 
> 최신 커밋만 가져오는 shallow clone을 의미한다. 전체 git 히스토리가 필요 없으므로 이 옵션을 사용하면 다운로드 시간과 용량을 절약할 수 있다.

<br>
동기화한 저장소를 확인한다.

```
root@jumpbox:~/kubernetes-the-hard-way# tree
.
├── ca.conf
├── configs
│   ├── 10-bridge.conf
│   ├── 99-loopback.conf
│   ├── containerd-config.toml
│   ├── encryption-config.yaml
│   ├── kube-apiserver-to-kubelet.yaml
│   ├── kubelet-config.yaml
│   ├── kube-proxy-config.yaml
│   └── kube-scheduler.yaml
...
├── docs
│   ├── 01-prerequisites.md
│   ├── 02-jumpbox.md
│   ...
│   └── 13-cleanup.md
├── downloads-amd64.txt
├── downloads-arm64.txt
...
└── units
    ├── containerd.service
    ├── ...
    └── kube-scheduler.service

4 directories, 35 files
root@jumpbox:~/kubernetes-the-hard-way# pwd
/root/kubernetes-the-hard-way
```

<br>

## 바이너리 설치

쿠버네티스 컴포넌트 바이너리를 `jumpbox`의 `downloads` 디렉토리에 다운로드한다. 이렇게 하면 각 머신마다 바이너리를 여러 번 다운로드할 필요 없이, jumpbox에서 한 번만 다운로드한 후 필요한 머신에 복사하면 되므로 인터넷 대역폭을 절약할 수 있다.

### 아키텍처 확인

바이너리는 CPU 아키텍처에 따라 다르기 때문에, 먼저 시스템 아키텍처를 확인해야 한다.
```bash
root@jumpbox:~/kubernetes-the-hard-way# dpkg --print-architecture 
arm64
```

### 다운로드

저장소에는 아키텍처별 바이너리 다운로드 목록 파일이 포함되어 있다. 앞에서 확인한 아키텍처에 맞는 파일을 사용한다.

```bash
root@jumpbox:~/kubernetes-the-hard-way# ls -l downloads-*
-rw-r--r-- 1 root root 839 Jan  6 00:15 downloads-amd64.txt
-rw-r--r-- 1 root root 839 Jan  6 00:15 downloads-arm64.txt
```

<br>
다운로드 목록에 포함된 바이너리들을 확인해 보자. 

```bash
# 바이너리 목록 확인
root@jumpbox:~/kubernetes-the-hard-way# cat downloads-$(dpkg --print-architecture).txt
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kubectl
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kube-apiserver
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kube-controller-manager
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kube-scheduler
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kube-proxy
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kubelet
https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.32.0/crictl-v1.32.0-linux-arm64.tar.gz
https://github.com/opencontainers/runc/releases/download/v1.3.0-rc.1/runc.arm64
https://github.com/containernetworking/plugins/releases/download/v1.6.2/cni-plugins-linux-arm64-v1.6.2.tgz
https://github.com/containerd/containerd/releases/download/v2.1.0-beta.0/containerd-2.1.0-beta.0-linux-arm64.tar.gz
https://github.com/etcd-io/etcd/releases/download/v3.6.0-rc.3/etcd-v3.6.0-rc.3-linux-arm64.tar.gz
```
- **kubectl**: Kubernetes 클러스터를 관리하기 위한 CLI 도구
- **kube-apiserver**: Kubernetes API 서버, 클러스터의 프론트엔드 역할
- **kube-controller-manager**: 클러스터의 상태를 관리하는 컨트롤러들 실행
- **kube-scheduler**: Pod를 적절한 노드에 할당하는 스케줄러
- **kube-proxy**: 노드의 네트워크 프록시, 서비스 로드밸런싱 담당
- **kubelet**: 각 노드에서 실행되는 에이전트, Pod 생명주기 관리
- **cri-tools (crictl)**: Container Runtime Interface를 위한 CLI 도구
- **runc**: OCI 호환 컨테이너 런타임
- **cni-plugins**: 컨테이너 네트워크 인터페이스 플러그인들
- **containerd**: 컨테이너 런타임
- **etcd**: 분산 키-값 저장소, Kubernetes 클러스터 상태 저장

<br>

이제 다운로드하자. 총 500MB 이상의 바이너리들이 다운로드된다. 다운로드 시간은 인터넷 환경에 따라 달라질 수 있다.
```bash
root@jumpbox:~/kubernetes-the-hard-way# wget -q --show-progress \
  --https-only \
  --timestamping \
  -P downloads \
  -i downloads-$(dpkg --print-architecture).txt
kubectl                   100%[====================================>]  53.25M  11.3MB/s    in 4.6s    
kube-apiserver            100%[====================================>]  86.06M  11.4MB/s    in 7.3s    
kube-controller-manager   100%[====================================>]  79.56M  11.8MB/s    in 6.7s    
kube-scheduler            100%[====================================>]  61.25M  11.8MB/s    in 5.1s    
kube-proxy                100%[====================================>]  62.25M  11.4MB/s    in 5.3s    
kubelet                   100%[====================================>]  71.75M  11.8MB/s    in 6.0s    
crictl-v1.32.0-linux-arm6 100%[====================================>]  16.98M  12.3MB/s    in 1.4s    
runc.arm64                100%[====================================>]  10.78M  11.4MB/s    in 0.9s    
cni-plugins-linux-arm64-v 100%[====================================>]  47.17M  9.08MB/s    in 5.6s    
containerd-2.1.0-beta.0-l 100%[====================================>]  33.60M  11.1MB/s    in 3.0s    
etcd-v3.6.0-rc.3-linux-ar 100%[====================================>]  20.87M  8.01MB/s    in 2.6s    

# 다운로드 확인
root@jumpbox:~/kubernetes-the-hard-way# ls -oh downloads
total 544M
-rw-r--r-- 1 root 48M Jan  7  2025 cni-plugins-linux-arm64-v1.6.2.tgz
-rw-r--r-- 1 root 34M Mar 18  2025 containerd-2.1.0-beta.0-linux-arm64.tar.gz
-rw-r--r-- 1 root 17M Dec  9  2024 crictl-v1.32.0-linux-arm64.tar.gz
-rw-r--r-- 1 root 21M Mar 28  2025 etcd-v3.6.0-rc.3-linux-arm64.tar.gz
-rw-r--r-- 1 root 87M Mar 12  2025 kube-apiserver
-rw-r--r-- 1 root 80M Mar 12  2025 kube-controller-manager
-rw-r--r-- 1 root 54M Mar 12  2025 kubectl
-rw-r--r-- 1 root 72M Mar 12  2025 kubelet
-rw-r--r-- 1 root 63M Mar 12  2025 kube-proxy
-rw-r--r-- 1 root 62M Mar 12  2025 kube-scheduler
-rw-r--r-- 1 root 11M Mar  4  2025 runc.arm64

# 자주 쓸 변수 저장
root@jumpbox:~/kubernetes-the-hard-way# ARCH=$(dpkg --print-architecture)
root@jumpbox:~/kubernetes-the-hard-way# echo $ARCH
arm64

# 바이너리를 역할별로 분류하기 위한 디렉토리 생성
root@jumpbox:~/kubernetes-the-hard-way# mkdir -p downloads/{client,cni-plugins,controller,worker}
tree -d downloads
downloads
├── client
├── cni-plugins
├── controller
└── worker
```

### 압축 해제

다운로드한 압축 파일들을 적절한 디렉토리에 압축 해제한다.

```bash
# crictl 압축 해제
root@jumpbox:~/kubernetes-the-hard-way# tar -xvf downloads/crictl-v1.32.0-linux-${ARCH}.tar.gz \
  -C downloads/worker/
crictl

# containerd 압축 해제 (--strip-components 1: 최상위 디렉토리 제거)
root@jumpbox:~/kubernetes-the-hard-way# tar -xvf downloads/containerd-2.1.0-beta.0-linux-${ARCH}.tar.gz \
  --strip-components 1 \
  -C downloads/worker/
bin/containerd-shim-runc-v2
bin/containerd
bin/containerd-stress
bin/ctr

# CNI plugins 압축 해제
root@jumpbox:~/kubernetes-the-hard-way# tar -xvf downloads/cni-plugins-linux-${ARCH}-v1.6.2.tgz \
  -C downloads/cni-plugins/
./bandwidth
./bridge
./dhcp
# ... (생략) ...
./vrf

# etcd 압축 해제 (특정 파일만 추출, --strip-components 1: 디렉토리 구조 제거)
root@jumpbox:~/kubernetes-the-hard-way# tar -xvf downloads/etcd-v3.6.0-rc.3-linux-${ARCH}.tar.gz \
  -C downloads/ \
  --strip-components 1 \
  etcd-v3.6.0-rc.3-linux-${ARCH}/etcdctl \
  etcd-v3.6.0-rc.3-linux-${ARCH}/etcd
etcd-v3.6.0-rc.3-linux-arm64/etcdctl
etcd-v3.6.0-rc.3-linux-arm64/etcd
```
> 참고: `--strip-components 1` 옵션
> 압축 파일 내부에 `etcd-v3.6.0-rc.3-linux-arm64/etcd`와 같은 디렉토리 구조가 있을 때, `--strip-components 1`을 사용하면 최상위 디렉토리(`etcd-v3.6.0-rc.3-linux-arm64/`)를 제거하고 파일만 추출한다. 이를 통해 불필요한 중첩 디렉토리 없이 파일을 원하는 위치에 바로 배치할 수 있다.


<br>

정상적으로 압축 해제되었는지 확인한다.

```bash
# worker 디렉토리: 컨테이너 런타임 관련 바이너리 확인
root@jumpbox:~/kubernetes-the-hard-way# tree downloads/worker/
downloads/worker/
├── containerd
├── containerd-shim-runc-v2
├── containerd-stress
├── crictl
└── ctr

# cni-plugins 디렉토리: 네트워크 플러그인 확인
root@jumpbox:~/kubernetes-the-hard-way# tree downloads/cni-plugins | head -n 10
downloads/cni-plugins
├── bandwidth
├── bridge
├── dhcp
# ... (생략) ...

# etcd 바이너리 확인 (권한이 vagrant로 되어 있음 - 추후 수정 필요)
root@jumpbox:~/kubernetes-the-hard-way# ls -l downloads/{etcd,etcdctl}
-rwxr-xr-x 1 vagrant vagrant 24314008 Mar 28  2025 downloads/etcd
-rwxr-xr-x 1 vagrant vagrant 15925400 Mar 28  2025 downloads/etcdctl
```

### 파일 이동

바이너리들을 역할별 디렉토리로 이동시킨다. 

```bash
# client: 관리용 도구들
root@jumpbox:~/kubernetes-the-hard-way# mv downloads/{etcdctl,kubectl} downloads/client/

# controller: 컨트롤 플레인 컴포넌트들
root@jumpbox:~/kubernetes-the-hard-way# mv downloads/{etcd,kube-apiserver,kube-controller-manager,kube-scheduler} downloads/controller/

# worker: 워커 노드 컴포넌트들
root@jumpbox:~/kubernetes-the-hard-way# mv downloads/{kubelet,kube-proxy} downloads/worker/
root@jumpbox:~/kubernetes-the-hard-way# mv downloads/runc.${ARCH} downloads/worker/runc
```

<br>
하위 디렉토리를 확인해 보자.

```bash
root@jumpbox:~/kubernetes-the-hard-way# tree downloads/client
downloads/client
├── etcdctl
└── kubectl

1 directory, 2 files
root@jumpbox:~/kubernetes-the-hard-way# tree downloads/controller/
downloads/controller/
├── etcd
├── kube-apiserver
├── kube-controller-manager
└── kube-scheduler

1 directory, 4 files
root@jumpbox:~/kubernetes-the-hard-way# tree downloads/worker/
downloads/worker/
├── containerd
├── containerd-shim-runc-v2
├── containerd-stress
├── crictl
├── ctr
├── kubelet
├── kube-proxy
└── runc

1 directory, 8 files
```


이렇게 구성함으로써 각 역할 별로 필요한 바이너리를 명확하게 구분할 수 있다. 각 머신마다 필요한 바이너리를 쉽게 식별하고 복사할 수 있다.
- **client**: 클러스터 관리용 도구 (kubectl, etcdctl)
- **controller**: 컨트롤 플레인 컴포넌트 (etcd, kube-apiserver, kube-controller-manager, kube-scheduler)
- **worker**: 워커 노드 컴포넌트 (kubelet, kube-proxy, containerd, runc 등)
- **cni-plugins**: 네트워크 플러그인들


### 압축 파일 삭제

확인이 완료되면, 불필요한 압축 파일을 지운다.

```bash
# 불필요한 압축 파일 제거
root@jumpbox:~/kubernetes-the-hard-way# ls -l downloads/*gz
-rw-r--r-- 1 root root 49466083 Jan  7  2025 downloads/cni-plugins-linux-arm64-v1.6.2.tgz
-rw-r--r-- 1 root root 35229532 Mar 18  2025 downloads/containerd-2.1.0-beta.0-linux-arm64.tar.gz
-rw-r--r-- 1 root root 17805231 Dec  9  2024 downloads/crictl-v1.32.0-linux-arm64.tar.gz
-rw-r--r-- 1 root root 21884730 Mar 28  2025 downloads/etcd-v3.6.0-rc.3-linux-arm64.tar.gz
root@jumpbox:~/kubernetes-the-hard-way# rm -rf downloads/*gz
root@jumpbox:~/kubernetes-the-hard-way# ls -d downloads/*
downloads/client  downloads/cni-plugins  downloads/controller  downloads/worker
```


### 실행 권한 부여

일부 바이너리 파일에 실행 권한이 없는 경우가 있다. 모든 바이너리에 실행 권한을 부여한다.

```bash
# 실행 권한 확인 (일부 파일에 실행 권한 없음)
root@jumpbox:~/kubernetes-the-hard-way# ls -l downloads/{client,cni-plugins,controller,worker}/* | grep -v "^d" | grep -v "^-rwx"
-rw-r--r-- 1 root    root    55836824 Mar 12  2025 downloads/client/kubectl
-rw-r--r-- 1 root    root    90243224 Mar 12  2025 downloads/controller/kube-apiserver
-rw-r--r-- 1 root    root    83427480 Mar 12  2025 downloads/controller/kube-controller-manager
-rw-r--r-- 1 root    root    64225432 Mar 12  2025 downloads/controller/kube-scheduler
-rw-r--r-- 1 root    root    75235588 Mar 12  2025 downloads/worker/kubelet
-rw-r--r-- 1 root    root    65274008 Mar 12  2025 downloads/worker/kube-proxy
-rw-r--r-- 1 root    root    11305168 Mar  4  2025 downloads/worker/runc

# 모든 바이너리에 실행 권한 부여
root@jumpbox:~/kubernetes-the-hard-way# chmod +x downloads/{client,cni-plugins,controller,worker}/*

# 실행 권한 부여 확인 (출력 없음 - 모든 파일에 실행 권한 부여됨)
root@jumpbox:~/kubernetes-the-hard-way# ls -l downloads/{client,cni-plugins,controller,worker}/* | grep -v "^d" | grep -v "^-rwx"
```

### 소유자 및 그룹 권한 변경

일부 파일의 소유자가 vagrant나 다른 사용자로 되어 있어 root로 통일해야 한다.

```bash
# 권한 확인 (일부 파일이 vagrant 소유)
root@jumpbox:~/kubernetes-the-hard-way# tree -ug downloads | grep -E "(vagrant|1001)"
│   ├── [vagrant  vagrant ]  etcdctl
│   ├── [vagrant  vagrant ]  etcd
│   ├── [1001     127     ]  crictl
...

# 소유자 및 그룹을 root로 변경
root@jumpbox:~/kubernetes-the-hard-way# chown root:root downloads/client/etcdctl
root@jumpbox:~/kubernetes-the-hard-way# chown root:root downloads/controller/etcd
root@jumpbox:~/kubernetes-the-hard-way# chown root:root downloads/worker/crictl

# 변경 확인
root@jumpbox:~/kubernetes-the-hard-way# tree -ug downloads | grep -E "(vagrant|1001)"
# (출력 없음 - 모든 파일이 root 소유로 변경됨)
```

<br>

## kubectl 설치

쿠버네티스 공식 CLI 도구인 kubectl을 `jumpbox` 머신에 설치한다. 추후 구성할 Kubernetes 클러스터 컨트롤 플레인과 통신하기 위해 사용할 예정이다.

```bash
root@jumpbox:~/kubernetes-the-hard-way# cp downloads/client/kubectl /usr/local/bin/
```

### kubectl version 확인
```bash
root@jumpbox:~/kubernetes-the-hard-way# kubectl version --client
Client Version: v1.32.3
Kustomize Version: v5.5.0
```

> **참고: Version Skew**  
> Kubernetes는 버전 간 호환성 정책(version skew policy)을 가지고 있다. kubectl 버전은 클러스터 버전보다 최대 1 마이너 버전까지 차이가 나도 되지만, 너무 오래된 버전은 공식 지원이 종료될 수 있다. 이 실습에서는 v1.32.3을 사용하지만, 실제 운영 환경에서는 최신 안정 버전을 사용하는 것이 권장된다.

### 클러스터 정보 확인

아직 클러스터가 구성되지 않았으므로 연결 오류가 발생하는 것이 정상이다.

```bash
root@jumpbox:~/kubernetes-the-hard-way# kubectl cluster-info
E0106 00:37:10.968981    2589 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"http://localhost:8080/api?timeout=32s\": dial tcp [::1]:8080: connect: connection refused"
# ... (에러 반복) ...

The connection to the server localhost:8080 was refused - did you specify the right host or port?
```

이 오류는 아직 kube-apiserver가 실행되지 않았기 때문에 발생하는 것으로, 이후에 클러스터를 구성하면 정상적으로 연결될 것이다.

<br>

# 결과

이 시점에서 jumpbox는 이 튜토리얼의 실습을 완료하는 데 필요한 모든 명령줄 도구와 유틸리티가 설치된 상태다.

- 필수 유틸리티 설치 확인  
- Kubernetes The Hard Way 저장소 클론  
- Kubernetes 컴포넌트 바이너리 다운로드 및 압축 해제  
- 바이너리 역할별 분류 (client, controller, worker, cni-plugins)  
- 실행 권한 및 소유자 권한 설정  
- kubectl 설치 및 확인  

<br>

이번 실습을 통해 Kubernetes 클러스터 구성에 필요한 각 컴포넌트와 그 역할을 이해할 수 있었다. 실습 환경이었으니 편하게 진행되었지만, 만약 실무 환경에서 클러스터를 구축한다면, 각 바이너리를 버전에 맞춰 다운로드하고, 압축을 풀고, 권한을 설정하는 작업을 수동으로 해야 할 것이다.

다음 글 [Compute Resources 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %})에서는 각 머신의 리소스를 확인하고 설정하는 작업을 진행한다.