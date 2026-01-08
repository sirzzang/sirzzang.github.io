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

> Kubernetes Cluster: 내 손으로 클러스터 구성하기
> - (0) [Overview]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %}) - 실습 소개 및 목표
> - (1) [Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) - 가상머신 환경 구성
> - **(2) [Set Up The Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %}) - 관리 도구 및 바이너리 준비**
> - (3) [Provisioning Compute Resources]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %}) - 머신 정보 정리 및 SSH 설정
> - (4.1) [Provisioning a CA and Generating TLS Certificates - 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %}) - TLS/mTLS/X.509/PKI 이해
> - (4.2) [Provisioning a CA and Generating TLS Certificates - ca.conf]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-2 %}) - OpenSSL 설정 파일 분석
> - (4.3) [Provisioning a CA and Generating TLS Certificates - 실습]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) - 인증서 생성 및 배포
> - (5) Generating Kubernetes Configuration Files - kubeconfig 생성
> - (6) Generating the Data Encryption Config and Key - 데이터 암호화 설정
> - (7) Bootstrapping the etcd Cluster - etcd 클러스터 구성
> - (8) Bootstrapping the Kubernetes Control Plane - 컨트롤 플레인 구성
> - (9) Bootstrapping the Kubernetes Worker Nodes - 워커 노드 구성 
> - (10) Configuring kubectl for Remote Access - kubectl 원격 접속 설정 
> - (11) Provisioning Pod Network Routes - Pod 네트워크 라우팅 설정
> - (12) Smoke Test - 클러스터 동작 검증

<br>

# TL;DR

이번 글의 목표는 **설치에 필요한 각종 파일 준비**다. [Kubernetes the Hard Way 튜토리얼의 Set Up The Jumpbox 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/02-jumpbox.md)를 따라 진행한다.

- Kubernetes 컴포넌트 바이너리 일괄 다운로드
- 역할별(Controller, Worker 등) 바이너리 분류 및 권한 설정
- 관리용 도구인 kubectl 설치 및 초기 상태 확인

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
# (host) $
# VM 상태 확인
vagrant status

# jumpbox 접속
vagrant ssh jumpbox
```

### root 계정

root 계정 설정은 [이전 글의 Prerequisites 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}#root-계정-설정)에서 이미 완료했다.

```bash
# (jumpbox) #
# root 계정 자동 전환 설정 확인
cat /home/vagrant/.bashrc | tail -n 1
```

**실행 결과:**
```
sudo su -
```

vagrant 계정으로 로그인하면 자동으로 `sudo su -`가 실행되어 root 계정으로 전환된다. 모든 커맨드는 root 계정으로 실행되어야 하며, 이는 편의를 위한 설정이다. 세팅 시 필요한 커맨드에 `sudo`를 매번 붙이지 않아도 되므로 작업이 훨씬 간편해진다.

<br>

## 툴 설치

필요한 명령줄 유틸리티들은 [이전 글의 Prerequisites 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}#필수-툴-설치)에서 이미 설치했다. 설치 여부를 확인해보자.

```bash
# (jumpbox) #
# 필수 패키지 설치 확인 및 미설치 시 설치
apt-get update && apt install tree git jq yq unzip vim sshpass -y
```

<br>

## Github Repository 동기화

Kubernetes The Hard Way 저장소를 클론해야 한다. 이 저장소에는 Kubernetes 클러스터 구성에 필요한 설정 파일들(configs 디렉토리), systemd 유닛 파일들(units 디렉토리), 그리고 바이너리 다운로드 목록 등이 포함되어 있다.


```bash
# (jumpbox) #
# --depth 1: 최신 커밋만 가져오는 shallow clone
git clone --depth 1 https://github.com/kelseyhightower/kubernetes-the-hard-way.git
cd kubernetes-the-hard-way
```
> 참고: `--depth 1` 옵션
> 
> 최신 커밋만 가져오는 shallow clone을 의미한다. 전체 git 히스토리가 필요 없으므로 이 옵션을 사용하면 다운로드 시간과 용량을 절약할 수 있다.

<br>
동기화한 저장소를 확인한다.

```bash
# (jumpbox) #
tree -L 2
```

**실행 결과:**
```
.
├── ca.conf
├── configs
│   ├── 10-bridge.conf
│   ├── 99-loopback.conf
│   # ...
├── units
│   ├── containerd.service
│   # ...
├── downloads-amd64.txt
└── downloads-arm64.txt
```

<br>

## 바이너리 설치

쿠버네티스 컴포넌트 바이너리를 `jumpbox`의 `downloads` 디렉토리에 다운로드한다. 이렇게 하면 각 머신마다 바이너리를 여러 번 다운로드할 필요 없이, jumpbox에서 한 번만 다운로드한 후 필요한 머신에 복사하면 되므로 인터넷 대역폭을 절약할 수 있다.

### 아키텍처 확인

바이너리는 CPU 아키텍처에 따라 다르기 때문에, 먼저 시스템 아키텍처를 확인해야 한다.
```bash
# (jumpbox) #
# 현재 시스템 아키텍처 확인 (arm64 또는 amd64)
dpkg --print-architecture 
```

**실행 결과:**
```
arm64
```

### 다운로드

저장소에는 아키텍처별 바이너리 다운로드 목록 파일이 포함되어 있다. 앞에서 확인한 아키텍처에 맞는 파일을 사용한다.

```bash
# (jumpbox) #
# 바이너리 목록 확인
cat downloads-$(dpkg --print-architecture).txt
```

**실행 결과:**
```
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kubectl
https://dl.k8s.io/v1.32.3/bin/linux/arm64/kube-apiserver
# ...
```

<br>

이제 다운로드하자. 총 500MB 이상의 바이너리들이 다운로드된다. 다운로드 시간은 인터넷 환경에 따라 달라질 수 있다.
```bash
# (jumpbox) #
wget -q --show-progress \
  --https-only \
  --timestamping \
  -P downloads \
  -i downloads-$(dpkg --print-architecture).txt

# -q: 로그 출력 최소화
# --show-progress: 진행률 표시 바 노출
# --https-only: HTTPS 링크만 사용
# --timestamping: 서버 파일이 더 최신인 경우만 다운로드
# -P: 다운로드 경로 지정
# -i: 파일에서 URL 목록 읽기
```

<br>

### 압축 해제

다운로드한 압축 파일들을 적절한 디렉토리에 압축 해제한다.

```bash
# (jumpbox) #
# 환경 변수 설정 및 디렉토리 생성
ARCH=$(dpkg --print-architecture)
mkdir -p downloads/{client,cni-plugins,controller,worker}

# crictl 압축 해제
tar -xvf downloads/crictl-v1.32.0-linux-${ARCH}.tar.gz \
  -C downloads/worker/

# containerd 압축 해제
# --strip-components 1: 압축 내부의 최상위 디렉토리를 무시하고 내부 파일만 추출
tar -xvf downloads/containerd-2.1.0-beta.0-linux-${ARCH}.tar.gz \
  --strip-components 1 \
  -C downloads/worker/

# CNI plugins 압축 해제
tar -xvf downloads/cni-plugins-linux-${ARCH}-v1.6.2.tgz \
  -C downloads/cni-plugins/

# etcd 압축 해제 (특정 파일만 추출)
tar -xvf downloads/etcd-v3.6.0-rc.3-linux-${ARCH}.tar.gz \
  -C downloads/ \
  --strip-components 1 \
  etcd-v3.6.0-rc.3-linux-${ARCH}/etcdctl \
  etcd-v3.6.0-rc.3-linux-${ARCH}/etcd
```
> 참고: `--strip-components 1` 옵션
> 압축 파일 내부에 `etcd-v3.6.0-rc.3-linux-arm64/etcd`와 같은 디렉토리 구조가 있을 때, `--strip-components 1`을 사용하면 최상위 디렉토리(`etcd-v3.6.0-rc.3-linux-arm64/`)를 제거하고 파일만 추출한다. 이를 통해 불필요한 중첩 디렉토리 없이 파일을 원하는 위치에 바로 배치할 수 있다.


<br>

정상적으로 압축 해제되었는지 확인한다.

```bash
# (jumpbox) #
# worker 디렉토리: 컨테이너 런타임 관련 바이너리 확인
tree downloads/worker/
```

**실행 결과:**
```
downloads/worker/
├── containerd
├── containerd-shim-runc-v2
├── containerd-stress
├── crictl
└── ctr
```

### 파일 이동

바이너리들을 역할별 디렉토리로 이동시킨다. 

```bash
# (jumpbox) #
# 클라이언트 도구 이동
mv downloads/{etcdctl,kubectl} downloads/client/

# 컨트롤 플레인 도구 이동
mv downloads/{etcd,kube-apiserver,kube-controller-manager,kube-scheduler} downloads/controller/

# 워커 노드 도구 이동
mv downloads/{kubelet,kube-proxy} downloads/worker/
mv downloads/runc.${ARCH} downloads/worker/runc

# 불필요한 압축 파일 삭제
rm -rf downloads/*gz
```

<br>
하위 디렉토리를 확인해 보자.

```bash
# (jumpbox) #
tree downloads/client
tree downloads/controller/
tree downloads/worker/
```

**실행 결과:**
```
downloads/client
├── etcdctl
└── kubectl

downloads/controller/
├── etcd
├── kube-apiserver
├── kube-controller-manager
└── kube-scheduler

downloads/worker/
├── containerd
# ...
└── runc
```


### 실행 권한 및 소유권 설정

일부 바이너리 파일에 실행 권한이 없거나 소유자가 다른 경우가 있다. 이를 root로 통일하고 실행 권한을 부여한다.

```bash
# (jumpbox) #
# 모든 바이너리에 실행 권한 부여
chmod +x downloads/{client,cni-plugins,controller,worker}/*

# 소유자 및 그룹을 root로 통일
chown root:root downloads/client/etcdctl
chown root:root downloads/controller/etcd
chown root:root downloads/worker/crictl
```

<br>

## kubectl 설치

쿠버네티스 공식 CLI 도구인 kubectl을 `jumpbox` 머신에 설치한다. 추후 구성할 Kubernetes 클러스터 컨트롤 플레인과 통신하기 위해 사용할 예정이다.

```bash
# (jumpbox) #
# kubectl을 전역 실행 경로로 복사
cp downloads/client/kubectl /usr/local/bin/

# 버전 확인 (클라이언트 전용)
kubectl version --client
```

**실행 결과:**
```
Client Version: v1.32.3
Kustomize Version: v5.5.0
```

> **참고: Version Skew**  
> Kubernetes는 버전 간 호환성 정책(version skew policy)을 가지고 있다. kubectl 버전은 클러스터 버전보다 최대 1 마이너 버전까지 차이가 나도 되지만, 너무 오래된 버전은 공식 지원이 종료될 수 있다. 이 실습에서는 v1.32.3을 사용하지만, 실제 운영 환경에서는 최신 안정 버전을 사용하는 것이 권장된다.

### 클러스터 정보 확인

아직 클러스터가 구성되지 않았으므로 연결 오류가 발생하는 것이 정상이다.

```bash
# (jumpbox) #
kubectl cluster-info
```

**실행 결과:**
```
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
