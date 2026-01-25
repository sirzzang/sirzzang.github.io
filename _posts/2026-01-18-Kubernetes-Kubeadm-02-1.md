---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 2.1. kubeadm join"
excerpt: "kubeadm join 명령어의 동작 원리와 각 단계를 살펴 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubeadm join 명령어의 동작 원리 이해**다.

- **kubeadm join**: 워커 노드 또는 추가 컨트롤 플레인 노드를 클러스터에 합류시키는 명령어
- **양방향 신뢰**: Discovery(노드 → 컨트롤 플레인 신뢰) + TLS Bootstrap(컨트롤 플레인 → 노드 신뢰)
- **Bootstrap Token**: 아직 인증서가 없는 노드가 임시로 인증받아 CSR을 제출하는 메커니즘
- **워커 vs 컨트롤 플레인**: 컨트롤 플레인 노드 join 시 추가 단계 수행 (인증서 다운로드, etcd 합류 등)

<br>

# 들어가며

`kubeadm init`이 완료되면 마지막에 다음과 같은 join 명령어가 출력된다:

```bash
kubeadm join 192.168.1.100:6443 --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx...
```

이번 글에서는 이 **`kubeadm join`** 명령어가 내부적으로 어떻게 동작하는지 살펴본다.

- [kubeadm join](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/)

<br>

# kubeadm join

![kubeadm-worker-node-join-process]({{site.url}}/assets/images/kubeadm-worker-node-join-process.png){: .align-center}
<center><sup>kubeadm join을 이용한 worker node join 과정</sup></center>

## 개요

`kubeadm join`은 새 노드를 기존 Kubernetes 클러스터에 합류시키는 명령어다.

```bash
kubeadm join [api-server-endpoint] [flags]
```

이 명령어로 두 가지 유형의 노드를 추가할 수 있다:
- **워커 노드**: 기본 동작. 워크로드를 실행할 노드 추가
- **컨트롤 플레인 노드**: `--control-plane` 플래그 사용. HA 구성을 위한 추가 컨트롤 플레인

<br>

## 양방향 신뢰 (Bidirectional Trust)

kubeadm으로 초기화된 클러스터에 join할 때는 **양방향 신뢰**가 필요하다.

| 방향 | 이름 | 설명 |
| --- | --- | --- |
| 노드 → 컨트롤 플레인 | **Discovery** | 새 노드가 "이 API Server가 진짜 우리 클러스터의 컨트롤 플레인인가?"를 확인 |
| 컨트롤 플레인 → 노드 | **TLS Bootstrap** | 컨트롤 플레인이 "이 노드가 클러스터에 합류할 자격이 있는가?"를 확인 |

### 양방향 신뢰 과정

- **Discovery**: 새 노드가 컨트롤 플레인의 신원을 확인하는 과정. Token 기반 또는 파일 기반으로 수행한다.
- **TLS Bootstrap**: 새 노드가 Bootstrap Token으로 임시 인증한 뒤, CSR(Certificate Signing Request)을 제출하여 정식 kubelet 인증서를 발급받는 과정.

두 메커니즘 모두 **token 기반**으로 동작하며, 대부분의 경우 **같은 token을 공유**한다. `--token` 플래그 하나로 두 용도를 모두 지정할 수 있다:

```bash
# --token은 Discovery와 TLS Bootstrap 둘 다에 사용됨
kubeadm join 192.168.1.100:6443 --token abcdef.1234567890abcdef ...
```

### 왜 양방향 신뢰가 필요한가?

단방향만 있다면, 아래와 같은 문제가 발생할 수 있다.

1. **노드가 컨트롤 플레인을 신뢰하지 않는 경우**: 공격자가 가짜 API Server를 세우고 노드를 유인할 수 있음. 노드는 민감한 정보(kubelet 자격 증명 등)를 가짜 서버에 전송하게 됨.

2. **컨트롤 플레인이 노드를 신뢰하지 않는 경우**: 아무나 클러스터에 노드를 추가할 수 있음. 악의적인 노드가 클러스터 리소스에 접근하거나 워크로드를 가로챌 수 있음.

<br>

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `--token` | Discovery와 TLS Bootstrap 모두에 사용할 토큰 |
| `--discovery-token-ca-cert-hash` | 컨트롤 플레인 CA 공개키의 해시값 (검증용) |
| `--discovery-token-unsafe-skip-ca-verification` | CA 해시 검증 건너뛰기 (보안 취약) |
| `--control-plane` | 컨트롤 플레인 노드로 join |
| `--certificate-key` | 컨트롤 플레인 join 시 인증서 복호화 키 |
| `--apiserver-advertise-address` | 컨트롤 플레인 노드의 API Server 광고 주소 |
| `--discovery-file` | 파일 기반 discovery 사용 시 kubeconfig 파일 경로 |

<br>

# Discovery

Discovery는 새 노드가 컨트롤 플레인의 신원을 확인하는 과정이다. Token 기반, 파일 기반의 두 가지 방식이 있으며, **한 번에 하나의 방식만** 사용할 수 있다.

```bash
# 1. Token 기반 Discovery
kubeadm join --discovery-token abcdef.1234567890abcdef 1.2.3.4:6443

# 2. 파일 기반 Discovery (로컬)
kubeadm join --discovery-file path/to/file.conf

# 3. 파일 기반 Discovery (URL, HTTPS 필수)
kubeadm join --discovery-file https://url/file.conf
```

> **참고**: URL로 discovery 파일을 로드할 때는 반드시 HTTPS를 사용해야 하며, 호스트에 설치된 CA 번들(예: `/etc/ssl/certs/ca-certificates.crt`)을 사용해 연결을 검증한다. 따라서 공인 인증서를 사용하는 서버이거나, 사설 CA를 호스트 CA 번들에 추가해야 한다.

## Token 기반 Discovery (기본)

Bootstrap Token과 API Server 주소를 사용하는 방식이다.

```bash
kubeadm join 192.168.1.100:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx...
```

### CA 해시 검증 (CA Pinning)

`--discovery-token-ca-cert-hash`는 컨트롤 플레인이 제시하는 루트 CA의 공개키를 검증하는 플래그다. 새 노드는 이 해시로 API Server가 제시하는 CA 인증서가 진짜인지 검증한다.

- **형식**: `<hash-type>:<hex-encoded-value>` (예: `sha256:xxxx...`)
- **지원 해시 타입**: `sha256`
- **해시 대상**: CA 인증서의 SPKI(Subject Public Key Info) 객체 (RFC7469)
- **여러 공개키 허용**: 플래그를 여러 번 반복하여 사용 가능 (CA 교체 시 유용)
  ```bash
  kubeadm join ... \
      --discovery-token-ca-cert-hash sha256:aaa... \
      --discovery-token-ca-cert-hash sha256:bbb...  # 둘 중 하나만 일치해도 검증 성공
  ```

해시 값은 `kubeadm init` 출력에서 확인하거나, 다음 명령으로 직접 계산할 수 있다:

```bash
# CA 해시 계산 방법
openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt | \
    openssl rsa -pubin -outform der 2>/dev/null | \
    openssl dgst -sha256 -hex | sed 's/^.* //'
```

CA 해시 검증 방식의 장단점은 아래와 같다: 
- 장점:
    - 네트워크가 손상되어도 컨트롤 플레인의 진위를 안전하게 검증
    - 모든 정보가 한 명령어에 포함되어 실행이 간편
- 단점:
    - CA 해시는 컨트롤 플레인이 프로비저닝된 후에야 알 수 있음
    - 자동화 도구 구축 시 순서 의존성 발생 (해결책: CA를 미리 생성)

### CA 검증 없이 사용 (비권장)

CA 공개키 해시를 미리 알 수 없는 경우, `--discovery-token-unsafe-skip-ca-verification` 플래그로 검증을 건너뛸 수 있다.

```bash
kubeadm join 192.168.1.100:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-unsafe-skip-ca-verification
```

다만, 이 옵션은 매우 **위험**하다. kubeadm 보안 모델을 약화시키기 때문이다. 다른 노드가 컨트롤 플레인을 사칭할 수 있으므로, 공격자가 Bootstrap Token을 탈취하면 가짜 컨트롤 플레인을 세워 노드를 속일 수 있다.

## 파일 기반 Discovery

kubeconfig 파일 형식으로 클러스터 정보를 제공하는 방식이다.

```bash
# 로컬 파일
kubeadm join --discovery-file /path/to/file.conf

# HTTPS URL
kubeadm join --discovery-file https://url/file.conf
```

### kubeconfig 인증 방식

Discovery용 kubeconfig 파일은 다음과 같은 인증 방식을 지원한다.

| 방식 | 설명 | 사용 예 |
| --- | --- | --- |
| `token` | kubeconfig에 토큰 값 직접 지정 | 테스트, 간단한 설정 |
| `tokenFile` | 파일에서 토큰 읽기 | ServiceAccount, 토큰 갱신 환경 |
| `exec` | 외부 명령어로 토큰 획득 | EKS, GKE, AKS 등 클라우드 |
| `authProvider` | 클라우드 제공자 인증 (deprecated) | 레거시 GKE/AKS 설정 |

```yaml
# token 방식 예시
users:
- name: user
  user:
    token: "eyJhbGciOiJSUzI1NiIs..."

# exec 방식 예시 (AWS EKS)
users:
- name: user
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: aws
      args: ["eks", "get-token", "--cluster-name", "my-cluster"]
```

> kubeconfig의 구조와 구성 요소에 대한 자세한 내용은 [kubeconfig 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-1 %}#kubeconfig)을 참고하자.

파일 기반 인증 방식의 장단점은 다음과 같다:
- **장점:**
    - 네트워크나 다른 노드가 손상되어도 신뢰 근거를 안전하게 전달
    - 자동화 프로비저닝에 적합
- **단점:**
    - Discovery 정보를 노드에 전달하는 별도 메커니즘 필요
    - 자격 증명이 포함된 경우 보안 채널로 전송해야 함

<br>

# TLS Bootstrap

TLS Bootstrap은 컨트롤 플레인이 새 노드를 신뢰하도록 하는 메커니즘이다. Discovery와 마찬가지로 **공유 토큰(shared token)**을 사용한다. 이 토큰으로 컨트롤 플레인에 임시 인증하여 CSR(Certificate Signing Request)을 제출하고, kubelet 인증서를 발급받는다.

## 문제: 닭과 달걀

컨트롤 플레인이 새 노드를 신뢰하고자 할 때 흔히 발생하는 문제다.

노드가 클러스터에 join하려면 kubelet 인증서가 필요하다. kubelet 인증서를 발급받으려면 API Server에 CSR(Certificate Signing Request)을 제출해야 한다. 그런데 CSR을 제출하려면 API Server에 자신을 인증해야 하고, 일반적으로 이 인증에는 **클라이언트 인증서**가 필요하다.

- 새 노드가 클러스터에 join하려면 kubelet 인증서가 필요
- kubelet 인증서를 받으려면 API Server에 CSR 제출 필요
- CSR을 제출하려면 API Server에 인증 필요 → **클라이언트 인증서 필요**
- 그런데 아직 인증서가 없음 → **닭과 달걀 문제**


## 해결: Bootstrap Token

Bootstrap Token으로 이 문제를 해결한다. 이 토큰은 컨트롤 플레인에 임시로 인증하여, 로컬에서 생성한 키 페어에 대한 CSR(Certificate Signing Request)을 제출하는 데 사용된다. 기본적으로 kubeadm은 이러한 서명 요청을 **자동 승인**하도록 컨트롤 플레인을 설정한다.

```
새 노드
  │
  │ 1. Bootstrap Token으로 임시 인증
  ▼
API Server
  │
  │ 2. CSR(Certificate Signing Request) 제출 허용
  ▼
Controller Manager
  │
  │ 3. CSR 자동 승인 및 인증서 발급
  ▼
새 노드: 정식 kubelet 인증서 획득
```


대부분의 경우 **discovery와 TLS bootstrap에 같은 토큰**을 사용한다. 이때는 `--token` 플래그로 한 번에 지정할 수 있다:

```bash
# --token은 discovery와 TLS bootstrap 둘 다에 사용됨
kubeadm join 192.168.1.100:6443 --token abcdef.1234567890abcdef ...
```

반대로 discovery와 TLS bootstrap에 **다른 토큰**을 사용하고 싶다면, `--tls-bootstrap-token` 플래그로 TLS Bootstrap용 토큰을 별도로 지정할 수 있다:

```bash
# Discovery는 --token, TLS Bootstrap은 --tls-bootstrap-token으로 별도 지정
kubeadm join 192.168.1.100:6443 \
    --discovery-token abcdef.1234567890abcdef \
    --tls-bootstrap-token xyz123.9876543210fedcba
```

### cluster-info ConfigMap

`kubeadm init`에서 생성한 `cluster-info` ConfigMap이 이 과정을 가능하게 한다.

```yaml
# kube-public 네임스페이스의 cluster-info ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-info
  namespace: kube-public
data:
  kubeconfig: |
apiVersion: v1
kind: Config
clusters:
- cluster:
        certificate-authority-data: <base64-encoded-ca-cert>
        server: https://192.168.1.100:6443
  name: ""
```

- **`kube-public` 네임스페이스**: 누구나 읽을 수 있는 공개 네임스페이스
- **`system:unauthenticated` 접근 허용**: 아직 인증서 없는 노드도 이 정보를 가져올 수 있음
- **Trust on First Use**: 처음 연결할 때 CA 인증서를 받아서 이후 통신에 사용

<br>

# kubeadm join 단계

`kubeadm join`은 조인하려는 노드 종류에 따라 실행되는 단계가 다르다.

| 워커 노드 | 컨트롤 플레인 노드 |
| --- | --- |
| preflight | preflight |
| kubelet-start | control-plane-prepare |
| kubelet-wait-bootstrap | kubelet-start |
| | etcd-join |
| | kubelet-wait-bootstrap |
| | control-plane-join |
| | wait-control-plane |

워커 노드는 kubelet만 시작하면 되지만, 컨트롤 플레인 노드는 인증서 다운로드, 컨트롤 플레인 컴포넌트 배포, etcd 합류 등 추가 단계가 필요하다.

## 워커 노드 Join

워커 노드 join은 다음 흐름으로 진행된다:

1. preflight: 시스템 요구사항 검증
2. Discovery: 클러스터 정보 다운로드 및 검증
3. TLS Bootstrap → CSR 제출 → 인증서 발급
4. kubelet 설정 완료 → 정식 인증서로 API Server와 mTLS 연결   


```bash
# 워커 노드 join
kubeadm join 192.168.1.100:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx...
```

### 1. preflight

시스템 요구사항을 검증한다. `kubeadm init`의 preflight와 유사하지만, join에 필요한 항목을 검증한다.
- 필요 포트 사용 가능 여부 (10250 등)
- 컨테이너 런타임 설치 여부
- 커널 모듈 로드 여부 (br_netfilter, overlay 등)

### 2. Discovery

API Server에서 클러스터 정보를 다운로드하고 검증한다.
- `kube-public` 네임스페이스의 `cluster-info` ConfigMap에서 CA 인증서, API Server 주소 획득
- `--discovery-token-ca-cert-hash`로 CA 인증서 진위 검증

> **참고**: `cluster-info` ConfigMap

> API Server에서 **유일하게 인증 없이 접근 가능한** 엔드포인트다. `kubeadm init`의 bootstrap-token 단계에서 `system:unauthenticated` 그룹에 이 ConfigMap에 대한 읽기 권한을 부여한다.
> 이렇게 해서 아직 인증서가 없는 새 노드도 클러스터 정보를 가져올 수 있다.

### 3. TLS Bootstrap

Discovery로 클러스터 정보(CA 인증서, API Server 주소)를 확보한 후, kubelet이 TLS Bootstrap 과정을 시작한다. Bootstrap Token으로 임시 인증하여 kubelet 인증서를 발급받는다.

#### **Bootstrap Token 인증 과정**

Bootstrap Token(`abcdef.0123456789abcdef`)은 `kubeadm init`에서 `kube-system` 네임스페이스에 Secret으로 저장된다:

```yaml
# kube-system 네임스페이스의 bootstrap-token-abcdef Secret
apiVersion: v1
kind: Secret
metadata:
  name: bootstrap-token-abcdef  # Token ID
  namespace: kube-system
type: bootstrap.kubernetes.io/token
data:
  token-id: YWJjZGVm                        # abcdef
  token-secret: MDEyMzQ1Njc4OWFiY2RlZg==    # 0123456789abcdef
  usage-bootstrap-authentication: dHJ1ZQ==  # true
  auth-extra-groups: c3lzdGVtOmJvb3RzdHJhcHBlcnM=  # system:bootstrappers
```

새 노드는 이 토큰을 Bearer Token으로 API Server에 전달한다:

```
Authorization: Bearer abcdef.0123456789abcdef
```

API Server는 `kube-system`의 Secret과 비교하여 토큰을 검증하고, 검증 성공 시 `system:bootstrappers` 그룹으로 인증한다. 이 그룹은 CSR 생성 권한이 있어 kubelet 인증서 서명 요청을 제출할 수 있다.

#### **CSR 발급 과정**

1. 로컬에서 키 페어 생성
2. Bootstrap Token으로 API Server에 임시 인증
3. CSR(Certificate Signing Request) 제출
4. Controller Manager가 CSR 자동 승인 및 인증서 발급

### 4. kubelet 설정 완료

발급받은 정식 인증서로 kubelet을 설정하고 클러스터에 합류한다.

1. **kubeconfig 생성**: 발급받은 인증서로 `/etc/kubernetes/kubelet.conf` 파일 생성
2. **노드 등록**: kubelet이 API Server에 자신을 `Node` 리소스로 등록
3. **최종 합류**: 컨트롤 플레인이 `kube-proxy` 등 필수 컴포넌트를 배포하고, 노드 상태가 `Ready`로 전환

이후 kubelet은 정식 인증서로 API Server와 mTLS 통신을 수행한다.

## 컨트롤 플레인 노드 Join

컨트롤 플레인 노드 join은 워커 노드와 동일한 과정에 **추가 단계**가 수행된다:

1. preflight: 시스템 요구사항 검증
2. Discovery: 클러스터 정보 다운로드 및 검증
3. **control-plane-prepare**: 인증서 다운로드, 컨트롤 플레인 컴포넌트 준비
4. TLS Bootstrap: CSR 제출 → 인증서 발급
5. **etcd-join**: 로컬 etcd를 기존 클러스터에 합류
6. kubelet 설정 완료
7. **control-plane-join**: 노드에 컨트롤 플레인 label/taint 추가


```bash
# 컨트롤 플레인 노드 join
kubeadm join 192.168.1.100:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx... \
    --control-plane \
    --certificate-key <certificate-key>
```

### 1. preflight

워커 노드와 동일. 추가로 컨트롤 플레인에 필요한 포트(6443, 10259, 10257, 2379-2380 등)도 검증한다.

### 2. Discovery

워커 노드와 동일. 클러스터 정보를 다운로드하고 검증한다.

### 3. control-plane-prepare

컨트롤 플레인 노드에만 수행되는 **핵심 단계**다.

| 하위 단계 | 설명 |
| --- | --- |
| /download-certs | `kubeadm-certs` Secret에서 공유 인증서 다운로드 |
| /certs | 새 컨트롤 플레인용 인증서 생성 (기존 CA로 서명) |
| /kubeconfig | controller-manager, scheduler용 kubeconfig 생성 |
| /control-plane | kube-apiserver, kube-controller-manager, kube-scheduler 매니페스트 생성 |

#### --certificate-key 옵션

HA 구성에서 추가 컨트롤 플레인 노드가 join할 때, 첫 번째 컨트롤 플레인의 인증서를 공유해야 한다. [`kubeadm init --upload-certs`]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %}#9-upload-certs)로 인증서를 암호화하여 Secret에 업로드하면, `--certificate-key`로 이를 복호화하여 가져올 수 있다.

```bash
# 첫 번째 컨트롤 플레인에서 인증서 업로드
kubeadm init --control-plane-endpoint "LOAD_BALANCER:6443" --upload-certs

# 출력된 certificate-key를 사용하여 추가 컨트롤 플레인 join
kubeadm join LOAD_BALANCER:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxx... \
    --control-plane \
    --certificate-key <certificate-key>
```

> **참고**: 업로드된 인증서는 기본적으로 2시간 후 자동 삭제된다.

### 4. TLS Bootstrap

워커 노드와 동일. Bootstrap Token으로 임시 인증하여 kubelet 인증서를 발급받는다.

### 5. etcd-join

로컬 etcd 인스턴스를 기존 etcd 클러스터에 합류시킨다. 이 단계에서:
- 로컬 etcd Static Pod 매니페스트 생성
- 기존 etcd 클러스터에 새 멤버로 등록
- 데이터 동기화 시작

### 6. kubelet 설정 완료

워커 노드와 동일. 발급받은 정식 인증서로 kubelet을 설정한다.

### 7. control-plane-join

컨트롤 플레인 join을 완료한다.
- 노드에 `node-role.kubernetes.io/control-plane` label 추가
- 노드에 `node-role.kubernetes.io/control-plane:NoSchedule` taint 추가



<br>

# 더 알아보기

이 글에서는 `kubeadm join`의 기본적인 동작 원리와 단계를 살펴보았다. 공식 문서에서는 이 외에도 다양한 고급 사용법을 다루고 있다:

| 주제 | 설명 |
| --- | --- |
| [Use of custom kubelet credentials](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/#use-of-custom-kubelet-credentials-with-kubeadm-join) | TLS Bootstrap을 건너뛰고 미리 생성된 kubelet 인증서 사용 |
| [Using kubeadm join with a configuration file](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/#using-kubeadm-join-with-a-configuration-file) | YAML 설정 파일로 join 구성을 선언적으로 관리 |
| [Discovering what cluster CA to trust](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/#discovering-what-cluster-ca-to-trust) | Discovery 모드별 보안 트레이드오프 상세 설명 |
| [Securing your installation even more](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/#securing-your-installation-even-more) | CSR 자동 승인 비활성화, cluster-info 공개 접근 비활성화 등 |

특히 **Configuration File**을 활용하면 명령줄 옵션 대신 YAML 파일로 join 구성을 관리할 수 있어, 버전 관리나 재현 가능한 배포에 유리하다.


## Discovery 보안 모드 비교

| 모드 | 보안 수준 | 사용 사례 |
| --- | --- | --- |
| **Token + CA Pinning** | 높음 | 기본 권장. 네트워크 손상에도 안전 |
| **Token without CA Pinning** | 중간 | CA 해시를 미리 알 수 없는 경우. MITM 공격에 취약 |
| **File/HTTPS-based** | 높음 | 자동화 프로비저닝. 파일 전송 채널 보안 필요 |

<br>

## 보안 강화 옵션

### CSR 자동 승인 비활성화

기본적으로 kubeadm은 Bootstrap Token으로 인증된 CSR을 자동 승인한다. 더 엄격한 보안이 필요하면 자동 승인을 끄고 수동으로 승인할 수 있다.

```bash
# 자동 승인 비활성화
kubectl delete clusterrolebinding kubeadm:node-autoapprove-bootstrap

# CSR 목록 확인
kubectl get csr
# NAME                                   AGE   REQUESTOR                 CONDITION
# node-csr-xxxx                          18s   system:bootstrap:878f07   Pending

# 수동 승인
kubectl certificate approve node-csr-xxxx
```

### cluster-info 공개 접근 비활성화

Bootstrap Token만으로 join을 허용하지 않으려면 `cluster-info` ConfigMap의 공개 접근을 끌 수 있다.

```bash
# 공개 접근 비활성화
kubectl -n kube-public delete rolebinding kubeadm:bootstrap-signer-clusterinfo

# 이후에는 --discovery-file로만 join 가능
kubeadm join --discovery-file /path/to/cluster-info.yaml
```

<br>

# 마무리

`kubeadm join`은 새 노드를 클러스터에 합류시키는 명령어다. 내부적으로 **양방향 신뢰**를 수립하여 안전한 노드 추가를 보장한다.

핵심 개념을 정리하면:

| 개념 | 설명 |
| --- | --- |
| **Discovery** | 노드가 컨트롤 플레인의 진위를 확인 (CA 인증서 검증) |
| **TLS Bootstrap** | 인증서 없는 노드가 Bootstrap Token으로 임시 인증 → CSR 제출 → 정식 인증서 발급 |
| **cluster-info** | 부트스트래핑에 필요한 최소 정보를 담은 공개 ConfigMap |
| **Bootstrap Token** | Discovery와 TLS Bootstrap 모두에 사용되는 임시 토큰 (기본 24시간 만료) |

Kubernetes The Hard Way에서 수동으로 수행했던 작업들과 비교하면:

| 수동 작업 (The Hard Way) | kubeadm join |
| --- | --- |
| kubelet 인증서 수동 생성 | TLS Bootstrap으로 자동 발급 |
| kubeconfig 수동 생성 | 자동 생성 |
| kubelet 설정 수동 작성 | ConfigMap에서 자동 적용 |

다음 글에서는 실제로 kubeadm을 사용하여 워커 노드를 클러스터에 join하는 실습을 진행한다.
