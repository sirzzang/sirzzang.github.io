---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 10. Configuring kubectl for Remote Access"
excerpt: "Jumpbox에서 원격으로 클러스터를 관리할 수 있도록 kubectl을 설정해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Jumpbox에서 원격으로 kubectl을 사용하기 위한 설정**이다. [Kubernetes the Hard Way 튜토리얼의 Configuring kubectl for Remote Access 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/10-configuring-kubectl.md)를 수행한다.

- kubectl 기본 kubeconfig 설정: `~/.kube/config` 파일 생성
- admin 자격증명 사용: 클러스터 관리자 권한으로 원격 접근
- 클러스터 상태 확인: kubectl 명령어로 노드 및 클러스터 정보 조회

지금까지는 server 노드에서 `--kubeconfig admin.kubeconfig` 옵션을 명시적으로 지정해 kubectl을 사용했다. 이번 단계에서는 jumpbox에서 원격으로 클러스터를 관리할 수 있도록 kubectl 기본 설정을 구성한다.

<br>

# 배경

## 기존 admin kubeconfig의 한계

[5. Generating Kubernetes Configuration Files]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) 단계에서 생성한 `admin.kubeconfig`는 다음과 같이 구성되어 있다:

```bash
# admin.kubeconfig의 server 설정
--server=https://127.0.0.1:6443   # localhost
```

이 설정은 **Control Plane 노드(server)에서 직접 실행**하는 것을 전제로 한다. API Server가 같은 노드에 있으므로 localhost(127.0.0.1)로 접근할 수 있다.

하지만 **jumpbox에서 원격으로 클러스터를 관리**하려면 다른 설정이 필요하다. jumpbox는 Control Plane 노드가 아니므로, API Server의 실제 주소인 `server.kubernetes.local`로 접근해야 한다.

## server.kubernetes.local DNS 설정

jumpbox에서 `server.kubernetes.local`로 접근하려면 DNS 해석이 가능해야 한다. 

[1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) 단계에서 각 노드의 `/etc/hosts` 파일에 다음과 같이 설정했다:

```bash
# /etc/hosts
192.168.10.100 server.kubernetes.local server
```

이 설정 덕분에 jumpbox에서 `server.kubernetes.local`을 IP 주소로 해석할 수 있다.

```bash
# (jumpbox)
ping -c 1 server.kubernetes.local
PING server.kubernetes.local (192.168.10.100) 56(84) bytes of data.
64 bytes from server.kubernetes.local (192.168.10.100): icmp_seq=1 ttl=64 time=0.85 ms
```

<br>

# API Server 접근 확인

kubectl 설정 전에, curl로 API Server에 직접 접근 가능한지 확인한다. API Server의 `/version` 엔드포인트는 인증 없이 접근할 수 있다.

```bash
# (jumpbox)
curl -s --cacert ca.crt https://server.kubernetes.local:6443/version | jq
```

```json
{
  "major": "1",
  "minor": "32",
  "gitVersion": "v1.32.3",
  "gitCommit": "32cc146f75aad04beaaa245a7157eb35063a9f99",
  "gitTreeState": "clean",
  "buildDate": "2025-03-11T19:52:21Z",
  "goVersion": "go1.23.6",
  "compiler": "gc",
  "platform": "linux/arm64"
}
```

API Server가 정상 응답한다. `--cacert ca.crt` 옵션으로 CA 인증서를 지정해 TLS 검증을 수행했다.

<br>

# kubectl 설정

## 기존 파일 확인

jumpbox의 `~/kubernetes-the-hard-way` 디렉토리에는 이전 단계에서 생성한 admin 인증서와 kubeconfig가 있다.

```bash
# (jumpbox)
ls -al | grep admin
-rw-r--r-- 1 root root  2021 Jan  7 23:55 admin.crt
-rw-r--r-- 1 root root  1830 Jan  7 23:55 admin.csr
-rw------- 1 root root  3272 Jan  7 23:47 admin.key
-rw------- 1 root root  9953 Jan  8 22:32 admin.kubeconfig
```

- `admin.crt`, `admin.key`: admin 사용자의 인증서와 개인키
- `admin.kubeconfig`: server 노드용 kubeconfig (localhost 기준)

이번 단계에서는 기존 인증서(`admin.crt`, `admin.key`)를 재사용하되, **원격 접근용 kubeconfig를 새로 생성**한다.

## kubectl config 명령어로 설정

`kubectl config` 명령어는 kubeconfig 파일을 생성하고 관리하는 도구다. `--kubeconfig` 옵션을 생략하면 기본 경로인 `~/.kube/config`에 설정이 저장된다.

### cluster 설정

```bash
# (jumpbox)
kubectl config set-cluster kubernetes-the-hard-way \
  --certificate-authority=ca.crt \
  --embed-certs=true \
  --server=https://server.kubernetes.local:6443

Cluster "kubernetes-the-hard-way" set.
```

- `set-cluster`: 클러스터 정보 설정
- `--certificate-authority`: API Server 인증서를 검증할 CA 인증서
- `--embed-certs=true`: 인증서를 Base64로 인코딩해 kubeconfig에 포함
- `--server`: **API Server 주소** (`localhost`가 아닌 `server.kubernetes.local` 사용)

### user 설정

```bash
kubectl config set-credentials admin \
  --client-certificate=admin.crt \
  --client-key=admin.key

User "admin" set.
```

- `set-credentials`: 사용자(클라이언트) 인증 정보 설정
- `--client-certificate`: 클라이언트 인증서 경로
- `--client-key`: 클라이언트 개인키 경로

여기서 `--embed-certs`를 생략했으므로, kubeconfig에는 인증서 내용이 아닌 **파일 경로**가 저장된다.

### context 설정

```bash
kubectl config set-context kubernetes-the-hard-way \
  --cluster=kubernetes-the-hard-way \
  --user=admin

Context "kubernetes-the-hard-way" created.
```

- `set-context`: cluster와 user를 조합한 context 생성
- `--cluster`: 사용할 cluster 이름
- `--user`: 사용할 user 이름

### current-context 설정

```bash
kubectl config use-context kubernetes-the-hard-way

Switched to context "kubernetes-the-hard-way".
```

기본으로 사용할 context를 지정한다.

<br>

# 생성된 kubeconfig 확인

위 명령어들의 결과로 `~/.kube/config` 파일이 생성된다. kubectl은 기본적으로 이 경로의 설정을 사용하므로, 이제 `--kubeconfig` 옵션 없이도 kubectl을 실행할 수 있다.

```bash
cat ~/.kube/config
```

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0F...  # Base64 인코딩된 ca.crt
    server: https://server.kubernetes.local:6443                 # 원격 API Server 주소
  name: kubernetes-the-hard-way
contexts:
- context:
    cluster: kubernetes-the-hard-way
    user: admin
  name: kubernetes-the-hard-way
current-context: kubernetes-the-hard-way
kind: Config
preferences: {}
users:
- name: admin
  user:
    client-certificate: /root/kubernetes-the-hard-way/admin.crt  # 파일 경로 (embed 안 함)
    client-key: /root/kubernetes-the-hard-way/admin.key
```

### 기존 admin.kubeconfig와의 차이점

| 항목 | admin.kubeconfig | ~/.kube/config |
| --- | --- | --- |
| **server** | `https://127.0.0.1:6443` | `https://server.kubernetes.local:6443` |
| **용도** | Control Plane 노드(server)에서 사용 | jumpbox에서 원격 사용 |
| **인증서** | embed-certs=true (내용 포함) | 파일 경로 참조 |

<br>

# 검증

## kubectl version

클라이언트와 서버 버전을 확인한다.

```bash
# (jumpbox)
kubectl version
```

```
Client Version: v1.32.3
Kustomize Version: v5.5.0
Server Version: v1.32.3
```

`Server Version`이 표시되면 API Server와 정상적으로 통신되고 있다는 의미다.

## kubectl cluster-info

클러스터 정보를 확인한다.

```bash
kubectl cluster-info
```

```
Kubernetes control plane is running at https://server.kubernetes.local:6443

To further debug and diagnose cluster problems, use 'kubectl cluster-info dump'.
```

Control Plane이 `server.kubernetes.local:6443`에서 실행 중임을 확인할 수 있다.

## kubectl get nodes

클러스터에 등록된 노드 목록을 조회한다.

```bash
kubectl get nodes
```

```
NAME     STATUS   ROLES    AGE   VERSION
node-0   Ready    <none>   40m   v1.32.3
node-1   Ready    <none>   37m   v1.32.3
```

이전 단계에서 구성한 Worker 노드들(node-0, node-1)이 `Ready` 상태로 표시된다.

## 상세 로그 확인 (-v 옵션)

kubectl의 `-v` 옵션으로 상세 로그를 확인할 수 있다. verbosity 레벨에 따라 출력 정보가 다르다.

| 레벨 | 설명 |
| --- | --- |
| `-v=0` | 일반적인 출력 (기본값) |
| `-v=4` | 디버그 레벨 출력 |
| `-v=6` | HTTP 요청/응답 로그 |
| `-v=8` | HTTP 요청/응답 본문까지 출력 |
| `-v=9` | 최대 상세 로그 |

```bash
kubectl get nodes -v=6
```

```
I0110 01:10:28.576736    4061 loader.go:402] Config loaded from file:  /root/.kube/config
I0110 01:10:28.577240    4061 envvar.go:172] "Feature gate default state" feature="ClientsAllowCBOR" enabled=false
I0110 01:10:28.577253    4061 envvar.go:172] "Feature gate default state" feature="ClientsPreferCBOR" enabled=false
I0110 01:10:28.577256    4061 envvar.go:172] "Feature gate default state" feature="InformerResourceVersion" enabled=false
I0110 01:10:28.577259    4061 envvar.go:172] "Feature gate default state" feature="WatchListClient" enabled=false
I0110 01:10:28.577412    4061 cert_rotation.go:140] Starting client certificate rotation controller
I0110 01:10:28.598970    4061 round_trippers.go:560] GET https://server.kubernetes.local:6443/api/v1/nodes?limit=500 200 OK in 17 milliseconds
NAME     STATUS   ROLES    AGE   VERSION
node-0   Ready    <none>   40m   v1.32.3
node-1   Ready    <none>   37m   v1.32.3
```

`-v=6`은 HTTP 요청/응답 로그까지 출력하므로 추가 정보가 많이 표시된다. 주요 내용:
- `Config loaded from file: /root/.kube/config`: 설정 파일 로드 확인
- `GET https://server.kubernetes.local:6443/api/v1/nodes?limit=500 200 OK`: API 요청 및 응답

일반적인 사용 시에는 `-v` 옵션을 생략하면 된다.

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **kubectl 기본 설정**: jumpbox의 `~/.kube/config`에 원격 접근용 kubeconfig 생성
2. **옵션 없이 kubectl 사용**: `--kubeconfig` 옵션 없이 바로 클러스터에 접근 가능
3. **admin 권한으로 관리**: `system:masters` 그룹의 admin 자격증명으로 클러스터 전체 관리

<br>

이번 실습을 통해 jumpbox에서 원격으로 클러스터를 관리할 수 있는 환경을 구성했다. `kubectl config` 명령어로 kubeconfig의 각 구성 요소(cluster, user, context)를 설정하는 방법과, 기본 kubeconfig 파일 위치(`~/.kube/config`)의 역할을 이해할 수 있었다.

이제 jumpbox에서 kubectl 명령어로 클러스터를 관리할 수 있다. <br> 

다음 단계에서는 Pod 네트워킹을 위한 라우팅 설정을 구성한다.
