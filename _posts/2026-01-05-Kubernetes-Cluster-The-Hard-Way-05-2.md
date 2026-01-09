---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 5.2. Generating Kubernetes Configuration Files"
excerpt: "OpenSSL을 사용하여 각 컴포넌트를 위한 kubeconfig 파일을 생성하고 배포해 보자."
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

이번 글의 목표는 **Kubernetes 컴포넌트를 위한 kubeconfig 파일 생성 및 배포**다. [Kubernetes the Hard Way 튜토리얼의 Generating Kubernetes Configuration Files for Authentication 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/05-kubernetes-configuration-files.md)를 수행한다.

- kubeconfig 파일 생성: kubelet, kube-proxy, kube-controller-manager, kube-scheduler, admin
- kubeconfig 파일 배포: 각 노드에 필요한 설정 파일 선별적으로 배포

직전 단계에서 TLS 인증서를 생성했다면, 이번 단계에서는 해당 인증서를 사용해 각 컴포넌트가 API Server와 통신할 수 있도록 설정 파일을 구성한다.

<br>

# kubelet kubeconfig 생성

노드 별로 kubelet이 API Server와 통신하기 위한 kubeconfig 파일을 생성한다. kubeconfig 생성 순서는 4단계로 구성된다.
1. `set-cluster`: API Server 접속 정보 설정 (어디로 접속할지)
2. `set-credentials`: 클라이언트 인증 정보 설정 (내가 누구인지)
3. `set-context`: cluster와 user를 조합하여 context 생성
4. `use-context`: 사용할 context를 current-context로 지정

각 단계마다 kubeconfig 파일의 `clusters`, `users`, `contexts`, `current-context` 섹션이 차례대로 채워진다.

> **참고**: [원래 가이드에서는 `for host in node-0 node-1; do` 반복문을 사용](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/05-kubernetes-configuration-files.md#the-kubelet-kubernetes-configuration-file)하지만, 이 실습에서는 각 노드별로 명시적으로 실행하여 단계별 변화를 확인한다.


## set-cluster

```bash
# jumpbox에서 실행

# node-0 kubeconfig의 cluster 정보 설정
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443 \
  --kubeconfig=node-0.kubeconfig

# node-1 kubeconfig의 cluster 정보 설정
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443 \
  --kubeconfig=node-1.kubeconfig

# 출력
Cluster "kubernetes-the-hard-way" set.

# 생성 확인
ls -l node-0.kubeconfig
-rw------- 1 root root 2758 Jan  8 21:29 node-0.kubeconfig
```

`set-cluster` 단계는 kubeconfig의 `clusters` 섹션을 채운다. API Server의 위치와 해당 서버의 신뢰성을 검증할 CA 인증서 정보를 설정한다.

<br>

주요 옵션은 다음과 같다.
- `--certificate-authority`: API Server의 인증서를 검증할 CA 인증서 파일 경로
- `--embed-certs=true`: CA 인증서 내용을 base64로 인코딩하여 kubeconfig 내부에 포함
- `--server`: API Server 접속 주소 (HTTPS 엔드포인트)
- `--kubeconfig`: 설정을 저장할 kubeconfig 파일 경로

### certificate-authority

API Server가 제시하는 TLS 인증서를 검증하기 위한 CA 인증서를 지정한다. [직전 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %}#mTLS)에서 본 것처럼, mTLS에서 클라이언트(kubelet)도 서버(API Server)의 인증서를 검증해야 한다. 

### embed-certs

CA 인증서 내용을 kubeconfig 파일 내부에 base64로 인코딩하여 포함시킨다. 이렇게 하면:
- 별도의 CA 인증서 파일 경로를 관리할 필요 없음
- kubeconfig 파일 하나로 모든 접속 정보 포함
- 파일 배포 및 관리가 단순해짐

### server

API Server의 접속 주소를 지정한다. kubelet은 이 항목의 값을 참고해 API Server에 접속한다.
- `https://server.kubernetes.local:6443`: Control Plane의 로드밸런서 주소
  - DNS(`server.kubernetes.local`) 또는 IP 주소 직접 지정 가능
  - 포트 6443은 API Server의 기본 HTTPS 포트

### kubeconfig 파일 확인
kubeconfig 파일 확인 시, cluster 섹션이 채워진 것을 확인할 수 있다.

```bash
apiVersion: v1
clusters:
- cluster: # cluster 섹션만 채워짐
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...
    server: https://server.kubernetes.local:6443
  name: kubernetes-the-hard-way
contexts: null
current-context: ""
kind: Config
preferences: {}
users: null
```

## set-credentials
```bash
# node-0 credentials 설정 후 확인
kubectl config set-credentials system:node:node-0 \
  --client-certificate=node-0.crt \
  --client-key=node-0.key \
  --embed-certs=true \
  --kubeconfig=node-0.kubeconfig && cat node-0.kubeconfig

# node-1 credentials 설정 후 확인
kubectl config set-credentials system:node:node-1 \
  --client-certificate=node-1.crt \
  --client-key=node-1.key \
  --embed-certs=true \
  --kubeconfig=node-1.kubeconfig && cat node-1.kubeconfig
```

`set-credentials` 단계는 kubeconfig의 `users` 섹션을 채운다. API Server와 mTLS 통신을 위해 **클라이언트 측 인증 정보**를 설정하는 단계다.

<br>

주요 옵션은 다음과 같다.
- `--client-certificate`: 클라이언트 인증서 파일 경로. mTLS에서 클라이언트가 자신을 증명하는 데 사용
- `--client-key`: 클라이언트 개인키 파일 경로. 인증서와 쌍을 이루며, 서명에 사용
- `--embed-certs=true`: 인증서와 키의 내용을 base64로 인코딩하여 kubeconfig 파일 내부에 직접 포함

### client-certificate와 client-key 설정

[지난 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %}#mTLS)에서 보았듯, mTLS에서 API Server는 클라이언트의 인증서를 요구한다. 따라서 kubelet이 나중에 API Server에 요청할 때, 이 단계에서 설정한 certificate, key를 이용한다.

### embed-certs

인증서와 키 파일의 **내용 자체**를 kubeconfig에 내장시킨다. 이렇게 함으로써, kubeconfig 파일 하나만으로 모든 인증 정보를 포함할 수 있다.
- 별도의 인증서 파일 경로를 관리할 필요 없음
- 파일 배포 및 관리가 단순해짐

### system:node:node-0 사용자 이름의 의미

여기서 `system:node:node-0`은 **새로운 사용자를 생성하는 것이 아니다**. 이것은 인증서에 담긴 CN(Common Name) 값을 kubeconfig에 기록하는 것이다.

**실제 통신 흐름:**

1. kubelet이 실행되어 kubeconfig 파일 읽기
2. `users` 섹션에서 `client-certificate-data`와 `client-key-data` 확인
3. API Server에 요청할 때 이 인증서를 제시
4. API Server가 인증서 검증:
   - CA 서명 확인 (인증서가 신뢰할 수 있는가?)
   - CN과 O 확인 (누구인가?)
5. Node Authorizer가 CN(`system:node:node-0`)과 O(`system:nodes`)를 보고 "이것은 node-0의 kubelet이다"라고 **자동 인식**
6. 해당 kubelet에게 node-0의 리소스에 대한 권한 자동 부여

<br>

### kubeconfig 확인
kubeconfig 확인 시, users 섹션이 추가된 것을 볼 수 있다.
```bash
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FU...
    server: https://server.kubernetes.local:6443
  name: kubernetes-the-hard-way
contexts: null
current-context: ""
kind: Config
preferences: {}
users: # 추가됨
- name: system:node:node-0 # Node Authorizer가 인식할 수 있는 패턴
  user:
    client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0F...
    client-key-data: LS0tLS1CRUdJTiBQUklWQVRFI...
```

## set-context

`set-context` 단계는 kubeconfig의 `contexts` 섹션을 채운다. 앞서 설정한 cluster와 user를 조합하여 context를 생성한다.


```bash
# node-0 context 생성
kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=system:node:node-0 \
  --kubeconfig=node-0.kubeconfig

# node-1 context 생성
kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=system:node:node-1 \
  --kubeconfig=node-1.kubeconfig

# 출력
Context "default" created.
```

주요 옵션은 다음과 같다.
- `--cluster`: 접속할 클러스터 이름 (set-cluster에서 설정한 이름)
- `--user`: 사용할 인증 정보 이름 (set-credentials에서 설정한 이름)
- `--kubeconfig`: 설정을 저장할 kubeconfig 파일 경로

### context의 역할

context는 "어떤 클러스터에 어떤 사용자로 접속할 것인가"를 정의하는 조합이다. 

- node-0의 경우: `kubernetes-the-hard-way` 클러스터에 `system:node:node-0` 사용자로 접속
- node-1의 경우: `kubernetes-the-hard-way` 클러스터에 `system:node:node-1` 사용자로 접속

여러 클러스터나 사용자를 관리하는 환경에서는 context를 전환하여 손쉽게 접속 대상을 변경할 수 있다. 이번 실습에서는 각 노드의 kubelet이 단일 클러스터에만 접속하므로 `default`라는 이름의 context 하나만 생성한다.

### kubeconfig 파일 확인 

kubeconfig 확인 시, context 섹션이 채워진 것을 확인할 수 있다.
```bash
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJ...
    server: https://server.kubernetes.local:6443
  name: kubernetes-the-hard-way
contexts:
- context: # 채워짐
    cluster: kubernetes-the-hard-way
    user: system:node:node-1
  name: default
current-context: ""
kind: Config
preferences: {}
users:
- name: system:node:node-1
  user:
    client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ...
    client-key-data: LS0tLS1CRUdJTiBQUklWQVRF...
```

## use-context
current-context 에 default 추가

```bash
kubectl config use-context default \
  --kubeconfig=node-0.kubeconfig

kubectl config use-context default \
  --kubeconfig=node-1.kubeconfig
Switched to context "default".
Switched to context "default".
```

### kubeconfig 파일 확인
kubeconfig 파일 확인 시, current-context 부분이 채워진 것을 확인할 수 있다.

```bash
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS...
    server: https://server.kubernetes.local:6443
  name: kubernetes-the-hard-way
contexts:
- context:
    cluster: kubernetes-the-hard-way
    user: system:node:node-1
  name: default
current-context: default # 채워짐
kind: Config
preferences: {}
users:
- name: system:node:node-1
  user:
    client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FUR...
    client-key-data: LS0tLS1CRUdJTiBQUklWQVRFIEtFW...

```

## 생성된 파일 확인

결과적으로 아래와 같은 노드별 kubeconfig 파일이 생성된다.

```bash
ls -l *.kubeconfig
-rw------- 1 root root 10161 Jan  8 21:44 node-0.kubeconfig # node-0 이름으로 생성
-rw------- 1 root root 10161 Jan  8 21:44 node-1.kubeconfig # node-1 이름으로 생성
```

<br>

# 기타 컴포넌트 kubeconfig 생성

kubelet 설정 파일 생성 과정과 동일하게, 다른 컴포넌트들도 set-cluster → set-credentials → set-context → use-context 순서로 kubeconfig를 생성한다. 차이점은 **사용하는 인증서와 kubeconfig 파일 이름**뿐이다.

## kube-proxy

```bash
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443 \
  --kubeconfig=kube-proxy.kubeconfig  # 파일명

kubectl config set-credentials system:kube-proxy \  # 사용자명
  --client-certificate=kube-proxy.crt \             # kube-proxy 인증서
  --client-key=kube-proxy.key \                     # kube-proxy 키
  --embed-certs=true \
  --kubeconfig=kube-proxy.kubeconfig

kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=system:kube-proxy \
  --kubeconfig=kube-proxy.kubeconfig

kubectl config use-context default \
  --kubeconfig=kube-proxy.kubeconfig
```

## kube-controller-manager

```bash
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443 \
  --kubeconfig=kube-controller-manager.kubeconfig  # 파일명

kubectl config set-credentials system:kube-controller-manager \  # 사용자명
  --client-certificate=kube-controller-manager.crt \             # kube-controller-manager 인증서
  --client-key=kube-controller-manager.key \                     # kube-controller-manager 키
  --embed-certs=true \
  --kubeconfig=kube-controller-manager.kubeconfig

kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=system:kube-controller-manager \
  --kubeconfig=kube-controller-manager.kubeconfig

kubectl config use-context default \
  --kubeconfig=kube-controller-manager.kubeconfig
```

## kube-scheduler

```bash
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443 \
  --kubeconfig=kube-scheduler.kubeconfig  # 파일명

kubectl config set-credentials system:kube-scheduler \  # 사용자명
  --client-certificate=kube-scheduler.crt \             # kube-scheduler 인증서
  --client-key=kube-scheduler.key \                     # kube-scheduler 키
  --embed-certs=true \
  --kubeconfig=kube-scheduler.kubeconfig

kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=system:kube-scheduler \
  --kubeconfig=kube-scheduler.kubeconfig

kubectl config use-context default \
  --kubeconfig=kube-scheduler.kubeconfig
```

<br>

# admin

admin kubeconfig는 컴포넌트가 아닌 **관리자 사용자**를 위한 설정이다. kubectl을 사용하여 클러스터를 관리할 때 사용한다.

기존 컴포넌트 설정과 다음의 항목들이 다르다.
- **server 주소**: `https://127.0.0.1:6443` (localhost)
  - 컴포넌트들은 `https://server.kubernetes.local:6443` (로드밸런서)를 사용
  - admin kubeconfig는 Control Plane 노드나 별도 관리 머신에서 사용하는 것을 전제로 함
    - Control Plane 노드에서 직접 실행하는 경우 localhost 사용 (API Server가 같은 노드에 있음)
    - Worker node에서는 일반적으로 kubectl을 사용하지 않는 것이 좋은 관행 (보안 및 역할 분리)
- **사용자 이름**: `admin` (system: 접두사 없음)
  - 컴포넌트들은 `system:kube-proxy`, `system:node:node-0` 등 system: 접두사 사용
  - admin은 일반 사용자이므로 system: 접두사 없음

목적과 용도는 다르지만, kubeconfig를 생성하는 절차 자체는 동일하다.

```bash
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://127.0.0.1:6443 \    # localhost
  --kubeconfig=admin.kubeconfig  # 파일명

kubectl config set-credentials admin \  # 사용자명: admin (system: 접두사 없음)
  --client-certificate=admin.crt \       # admin 인증서
  --client-key=admin.key \               # admin 키
  --embed-certs=true \
  --kubeconfig=admin.kubeconfig

kubectl config set-context default \
  --cluster=kubernetes-the-hard-way \
  --user=admin \
  --kubeconfig=admin.kubeconfig

kubectl config use-context default \
  --kubeconfig=admin.kubeconfig
```

<br>

# 설정 파일 배포

위의 과정을 통해 생성된 kubeconfig 파일들을 확인해 보자.
```bash
ls -l *.kubeconfig
-rw------- 1 root root  9953 Jan  8 22:32 admin.kubeconfig
-rw------- 1 root root 10305 Jan  8 22:24 kube-controller-manager.kubeconfig
-rw------- 1 root root 10187 Jan  8 21:48 kube-proxy.kubeconfig
-rw------- 1 root root 10211 Jan  8 22:32 kube-scheduler.kubeconfig
-rw------- 1 root root 10161 Jan  8 21:44 node-0.kubeconfig
-rw------- 1 root root 10161 Jan  8 21:44 node-1.kubeconfig
```

[지난 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %})에서 노드 별로 필요한 인증서가 달랐듯, kubeconfig도 노드 별로 필요한 게 다르다.

| 노드 유형 | 필요한 kubeconfig | 이유 |
| --- | --- | --- |
| **Worker Node** | `node-X.kubeconfig`, `kube-proxy.kubeconfig` | kubelet과 kube-proxy가 API Server와 통신하기 위해 필요 |
| **Control Plane** | `kube-controller-manager.kubeconfig`, `kube-scheduler.kubeconfig`, `admin.kubeconfig` | Control Plane 컴포넌트가 API Server와 통신하고, 관리자가 클러스터를 관리하기 위해 필요 |

지난 단계에서와 같이, 노드 별로 필요한 파일을 배포한 후 확인해 보자.

## Worker Node

```bash
# Worker Node 배포
for host in node-0 node-1; do
  ssh root@${host} "mkdir -p /var/lib/{kube-proxy,kubelet}"

  scp kube-proxy.kubeconfig \
    root@${host}:/var/lib/kube-proxy/kubeconfig \

  scp ${host}.kubeconfig \
    root@${host}:/var/lib/kubelet/kubeconfig
done
kube-proxy.kubeconfig                              100%   10KB   6.4MB/s   00:00    
node-0.kubeconfig                                  100%   10KB   6.2MB/s   00:00    
kube-proxy.kubeconfig                              100%   10KB  12.7MB/s   00:00    
node-1.kubeconfig                                  100%   10KB   1.7MB/s   00:00

# 확인
ssh node-1 ls -l /var/lib/*/kubeconfig
-rw------- 1 root root 10161 Jan  8 22:39 /var/lib/kubelet/kubeconfig
-rw------- 1 root root 10187 Jan  8 22:39 /var/lib/kube-proxy/kubeconfig
ssh node-0 ls -l /var/lib/*/kubeconfig
-rw------- 1 root root 10161 Jan  8 22:39 /var/lib/kubelet/kubeconfig
-rw------- 1 root root 10187 Jan  8 22:39 /var/lib/kube-proxy/kubeconfig
```

## Control Plane

```bash
scp admin.kubeconfig \
  kube-controller-manager.kubeconfig \
  kube-scheduler.kubeconfig \
  root@server:~/
admin.kubeconfig                                   100% 9953     7.6MB/s   00:00    
kube-controller-manager.kubeconfig                 100%   10KB   6.7MB/s   00:00    
kube-scheduler.kubeconfig                          100%   10KB   9.2MB/s   00:00    

# 확인
ssh server ls -l /root/*.kubeconfig
-rw------- 1 root root  9953 Jan  8 22:41 /root/admin.kubeconfig
-rw------- 1 root root 10305 Jan  8 22:41 /root/kube-controller-manager.kubeconfig
-rw------- 1 root root 10211 Jan  8 22:41 /root/kube-scheduler.kubeconfig
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **kubeconfig 파일 생성**: 각 컴포넌트(kubelet, kube-proxy, kube-controller-manager, kube-scheduler)와 관리자(admin)를 위한 kubeconfig 파일 생성
2. **kubeconfig 파일 배포**: 
   - Worker Node: `node-X.kubeconfig`, `kube-proxy.kubeconfig` 배포
   - Control Plane: `kube-controller-manager.kubeconfig`, `kube-scheduler.kubeconfig`, `admin.kubeconfig` 배포
3. **kubeconfig 구성 이해**: clusters, users, contexts의 역할과 Node Authorizer와의 연동 방식 이해

<br>

이번 실습을 통해 Kubernetes 컴포넌트가 API Server와 통신하기 위한 kubeconfig 파일을 직접 생성하고 배포해 보았다. kubeconfig의 구성 요소(clusters, users, contexts)와 각 컴포넌트별 인증서 사용 방식, Node Authorizer가 kubelet을 자동으로 인식하는 명명 규칙 등을 이해할 수 있었다. 각 노드에 필요한 kubeconfig만 선별적으로 배포하여 보안을 강화했다.

<br>

다음 글에서는 Kubernetes Secret 데이터를 암호화하기 위한 설정을 구성한다.

