---
title:  "[Kubernetes] Kubernetes 클러스터 API 액세스 에러 해결"
excerpt: Kubernetes 인증 메커니즘에서 나타날 수 있는 kubeconfig 인증서 만료로 인한 클러스터 API 사용 불가 문제를 이해해 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - TLS
  - PKI
  - certificate
---

<br>
# 배경

무려 반 년 가까이 된 일이지만, K3s 클러스터 내 인증서 만료 문제를 해결한 과정을 다시 한 번 짚어 본다. 부끄럽게도 당시에는 이런 저런 일정으로 인해 문제 해결이 급급하여, `/etc/rancher/k3s/k3s.yaml` 파일을 교체해 주면 되더라, 하고 넘어 갔다. 더 알아 보고 싶었지만, 줄줄이 딸려오는 개념이 많고 어디서부터 어떻게 접근해야 할지 몰라 `나중에..`하고 넘어 갔다.

당시에는 PKI가 무엇인지, CA가 무슨 역할을 하는지, 인증서가 어떻게 신뢰 체계를 구축하는지 제대로 이해하지 못했다. 그저 "인증서가 만료되었으니 새로운 인증서로 교체한다"는 표면적인 해결책만 알고 있었을 뿐이다. 하지만 운영 환경의 Kubernetes 클러스터를 관리하다 보면, 이러한 기본 원리에 대한 이해 없이는 문제의 본질을 파악하기 어렵고, 유사한 문제가 발생했을 때 적절히 대응하기 힘들다.

마침 최근 [Kubernetes The Hard Way 실습](https://sirzzang.github.io/kubernetes/Kubernetes-Cluster-The-Hard-Way-04-1/)을 진행하면서 Kubernetes 클러스터의 인증서 체계를 처음부터 구성해 보는 경험을 했다. CA 인증서를 직접 생성하고, 각 컴포넌트의 인증서를 서명하며, kubeconfig를 구성하는 과정을 통해 비로소 PKI의 동작 원리와 TLS 인증 메커니즘을 체득할 수 있었다.

이제 그때의 상황을 다시 돌아보며, 단순한 문제 해결을 넘어 Kubernetes의 보안 아키텍처를 이해하는 관점에서 재정리해 보고자 한다.

<br>
# TL;DR

1. 문제와 해결
   - kubeconfig 인증서 만료로 kubectl API 호출 불가
   - `/etc/rancher/k3s/k3s.yaml` → `~/.kube/config` 복사로 해결

2. 원리
   - Kubernetes는 TLS 기반 PKI로 모든 통신 인증
   - CA가 서명한 인증서로 신뢰 체계 구축
   - TLS handshake 5단계에서 인증서 유효 기간 검증 필수

3. 교훈
   - K3s는 인증서 자동 관리하지만 `~/.kube/config`는 수동 복사 필요
   - 표면적 해결 넘어 PKI 원리 이해해야 문제 본질 파악 가능
   - 정기적인 인증서 만료 모니터링 중요 (만료 30일 전 갱신 권장)

<br>


# 문제

K3s 클러스터 내 kubectl을 이용한 쿠버네티스 클러스터 API가 작동하지 않는다.

```bash
$ kubectl get pod -n <namespace>
E0807 14:15:26.155304 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.155898 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.157457 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.157934 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.159294 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
error: You must be logged in to the server (the server has asked for the client to provide credentials)
```

<br>

# 원인

## 인증서 만료 확인

`kubectl` 클라이언트가 해당 kubernetes 클러스터에 인증되어 있지 않다. kubernetes 클러스터 인증을 위해 사용되는 kubeconfig 파일에서 인증서 만료 기한을 확인해 보자.

```bash
$ kubectl config view --raw -o jsonpath='{.users[0].user.client-certificate-data}' | base64 -d | openssl x509 -noout -enddate
notAfter=Jul 29 05:36:03 2025 GMT
```

당시 기준으로 하루 전에 클라이언트 인증서가 만료되었다.

<br>

## Kubernetes의 인증서 기반 인증 메커니즘

Kubernetes는 클러스터 컴포넌트 간 통신과 클라이언트 인증을 위해 TLS 기반 PKI를 사용한다. PKI 구조, 인증서의 역할(CA/서버/클라이언트 인증서), mTLS 인증 과정에 대한 자세한 내용은 [Kubernetes PKI 글]({% post_url 2026-01-18-Kubernetes-PKI %})을 참고하자.

kubectl이 API Server에 접근할 때 mTLS Handshake 과정에서 클라이언트 인증서의 유효 기간을 확인하는데, 이 단계에서 만료된 인증서가 문제가 된다.


### 인증서 만료가 문제가 되는 이유

위의 5단계에서 서버가 클라이언트 인증서의 유효 기간을 확인한다. 인증서가 만료되면,

- `notBefore`와 `notAfter` 필드로 정의된 유효 기간을 벗어나기 때문에,
- 서버는 만료된 인증서를 신뢰할 수 없다고 판단하여,
- TLS handshake가 실패하고,
- 서버는 유효한 인증서를 요구하게 되며

결과적으로 `the server has asked for the client to provide credentials` 에러가 발생하는 것이다. X.509 인증서 표준에서 유효 기간 검증은 필수 사항이며, 이는 **보안을 위해 타협할 수 없는 부분**이다.

<br>

# 해결

K3s는 클러스터 접근을 위한 credentials 파일을 자체적으로 업데이트한다([참고: K3s Cluster Access](https://docs.k3s.io/cluster-access)). 그러니 K3s의 새로운 kubeconfig 파일로 대체해 주면 된다.


## kubeconfig 파일 변경

K3s kubeconfig 파일 위치: `/etc/rancher/k3s/k3s.yaml`

```bash
# 기존 인증서 백업
$ mv ~/.kube/config ~/.kube/config.bak

# kubeconfig 업데이트
$ sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config

# 권한 설정 (필요 시)
$ sudo chown $(id -u):$(id -g) ~/.kube/config
```

## 결과 확인
교체 후 kubectl을 이용해 API를 호출해 보면, 정상적으로 작동함을 확인할 수 있다.

```bash
$ kubectl get pod -n <my-namespace>
NAME                                         READY   STATUS    RESTARTS   AGE
<pod-name>                                   1/1     Running   0          22d
```

## 새 인증서 검증

갱신된 인증서의 유효 기간을 확인해 보자.

```bash
$ kubectl config view --raw -o jsonpath='{.users[0].user.client-certificate-data}' | base64 -d | openssl x509 -noout -text

Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number: <serial>
        Signature Algorithm: sha256WithRSAEncryption
        Issuer: CN = k3s-client-ca@<timestamp>
        Validity
            Not Before: <date>
            Not After : <date>  # 1년 뒤
        Subject: O = system:masters, CN = system:admin
        ...
```

이 인증서에는 다음 정보가 포함되어 있다:

- **Issuer**: `k3s-client-ca` - K3s가 관리하는 클라이언트 CA
- **Subject CN**: `system:admin` - Kubernetes 사용자 이름
- **Subject O**: `system:masters` - Kubernetes 그룹(`cluster-admin` 권한을 가진 그룹)
- **Validity**: 발급일로부터 1년간 유효

<br>

# 참고

## K3s의 PKI 관리

K3s는 클러스터 시작 시 자동으로 PKI 인프라를 구성한다.

### 인증서 구조

K3s는 `/var/lib/rancher/k3s/server/tls`에 다음과 같은 인증서들을 생성한다.

```
/var/lib/rancher/k3s/server/tls/
├── client-ca.crt              # 클라이언트 인증서 서명용 CA
├── client-ca.key              # CA 개인키
├── server-ca.crt              # 서버 인증서 서명용 CA
├── server-ca.key              # CA 개인키
├── request-header-ca.crt      # API Aggregation용 CA
├── client-admin.crt           # admin 사용자 클라이언트 인증서
├── client-admin.key           # admin 클라이언트 개인키
├── serving-kube-apiserver.crt # API 서버 인증서
├── serving-kube-apiserver.key # API 서버 개인키
└── ...
```

### kubeconfig 구조와 인증서 활용

`/etc/rancher/k3s/k3s.yaml`은 `/var/lib/rancher/k3s/server/cred/admin.kubeconfig`를 기반으로 K3s가 자동 생성한 kubeconfig 파일이다.

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: <base64-encoded-CA-certificate>
    server: https://127.0.0.1:6443
  name: default
contexts:
- context:
    cluster: default
    user: default
  name: default
current-context: default
kind: Config
preferences: {}
users:
- name: default
  user:
    client-certificate-data: <base64-encoded-client-certificate>
    client-key-data: <base64-encoded-client-private-key>
```

1. **certificate-authority-data**
   - 서버 CA 인증서 (server-ca.crt)의 base64 인코딩 값
   - kubectl이 API 서버 인증서를 검증할 때 사용
   - "이 CA가 서명한 서버 인증서만 신뢰한다"는 정책

2. **client-certificate-data**
   - 클라이언트 인증서 (client-admin.crt)의 base64 인코딩 값
   - 클라이언트(kubectl)의 신원을 증명
   - Subject CN과 O 필드로 사용자 이름과 그룹 정보 전달

3. **client-key-data**
   - 클라이언트 개인키 (client-admin.key)의 base64 인코딩 값
   - TLS handshake 시 클라이언트가 인증서의 소유자임을 증명
   - 절대 공유하거나 전송해서는 안 되는 민감 정보

### 인증서 자동 갱신 메커니즘

K3s는 다음과 같이 인증서를 관리한다.

1. **인증서 생성**: 클러스터 최초 시작 시
   - 기본 유효 기간: 365일 (1년)
   - 자체 서명된 CA 인증서 생성
   - CA로 서버 및 클라이언트 인증서 서명

2. **인증서 갱신**: K3s 서버 재시작 시
   - 만료 90일 전부터 자동 갱신 시도
   - 기존 인증서를 새 인증서로 교체
   - `/etc/rancher/k3s/k3s.yaml` 자동 업데이트

3. **유효 기간 커스터마이징**: 유효기간 변경 가능
   ```bash
   k3s server \
     --cluster-init \
     --cluster-csr-ttl 43800h  # 5년
   ```
   - 이미 발급된 인증서는 변경되지 않음
   - 새로 생성되는 인증서에만 적용

### 인증서 갱신 시 고려사항

K3s가 자동으로 인증서를 갱신하더라도, 다음 상황에서는 수동 개입이 필요할 수 있다.

1. **kubeconfig 파일 미갱신**: *← 내가 겪은 상황*
   - 홈 디렉토리의 `~/.kube/config`는 자동 갱신되지 않음
   - `/etc/rancher/k3s/k3s.yaml`에서 수동 복사 필요

2. **외부 클라이언트**: 
   - K3s 노드 외부에서 접속하는 클라이언트
   - 갱신된 kubeconfig를 수동으로 배포해야 함

3. **Service Account 토큰**: 
   - Pod 내에서 사용하는 Service Account 토큰은 별도 관리
   - 기본적으로 만료되지 않지만, BoundServiceAccountTokenVolume 기능 사용 시 주기적 갱신

<br>

## 다른 Kubernetes 배포판에서의 인증서 관리

Kubernetes 배포판마다 인증서 관리 방식이 다르지만, 모두 동일한 PKI 원리를 기반으로 한다.

### kubeadm 기반 클러스터

```bash
# 인증서 상태 확인
$ kubeadm certs check-expiration

# 모든 인증서 갱신
$ kubeadm certs renew all

# kubeconfig 갱신
$ kubeadm init phase kubeconfig admin
```

kubeadm도 K3s와 유사하게 `/etc/kubernetes/pki`에 인증서를 관리한다.

### 클라우드 매니지드 클러스터

클라우드 제공자들은 인증서 대신 단기 토큰 기반 인증을 주로 사용한다:

- **EKS**
  ```bash
  $ aws eks update-kubeconfig --name <cluster-name>
  ```
  - AWS IAM을 통한 인증
  - `aws-iam-authenticator`로 단기 토큰 발급
  - 토큰 유효 기간: 15분 (자동 갱신)

- **GKE**
  ```bash
  $ gcloud container clusters get-credentials <cluster-name>
  ```
  - Google Cloud IAM을 통한 인증
  - gcloud가 자동으로 토큰 관리

- **AKS**
  ```bash
  $ az aks get-credentials --name <cluster-name> --resource-group <rg>
  ```
  - Azure AD를 통한 인증
  - Azure CLI가 토큰 관리

### Minikube

```bash
$ minikube update-context
```

Minikube는 VM을 재생성할 때마다 새 인증서를 발급하므로, 인증서 만료 문제가 거의 발생하지 않는다.

<br>

## Kubernetes The Hard Way에서의 인증서 배포

[Kubernetes The Hard Way 실습](https://sirzzang.github.io/kubernetes/Kubernetes-Cluster-The-Hard-Way-04-3/)에서 직접 클러스터를 구성하면서, K3s와 같은 배포판이 자동으로 처리해 주는 인증서 관리의 복잡성을 체감할 수 있었다. 수동으로 PKI를 구성하는 과정을 통해 각 인증서의 역할과 배포 위치를 명확히 이해하게 되었다.

### 수동 PKI 구성 시 인증서 배포 위치

Kubernetes The Hard Way 방식으로 클러스터를 구축할 때는 openssl을 사용해 인증서를 직접 생성하고 배포했다.


### **Controller 노드** 
`/var/lib/kubernetes/`에 인증서가 위치한다.
```
/var/lib/kubernetes/
├── ca.pem                      # CA 인증서
├── ca-key.pem                  # CA 개인키
├── kubernetes.pem              # API 서버 인증서
├── kubernetes-key.pem          # API 서버 개인키
├── service-account.pem         # Service Account 서명용 공개키
└── service-account-key.pem     # Service Account 서명용 개인키
```

### **Worker 노드**
`/var/lib/kubelet/`에 인증서가 위치한다.
```
/var/lib/kubelet/
├── ca.pem                      # CA 인증서 (API 서버 검증용)
├── <worker-name>.pem           # 각 워커 노드의 클라이언트 인증서
└── <worker-name>-key.pem       # 각 워커 노드의 개인키
```

### **kubeconfig 배포** 
`~/.kube/config` 또는 `/etc/kubernetes/`에 인증서가 위치한다.
- admin kubeconfig: 클러스터 관리자용
- kube-proxy kubeconfig: kube-proxy 컴포넌트용
- kubelet kubeconfig: 각 워커 노드의 kubelet용

### K3s vs 수동 구성 비교

| 항목 | K3s | Kubernetes The Hard Way |
|------|-----|-------------------------|
| CA 인증서 생성 | 자동 (`/var/lib/rancher/k3s/server/tls`) | 수동 (openssl 등 도구 사용) |
| 컴포넌트 인증서 서명 | 자동 | 수동 (각 컴포넌트별 CSR 생성 및 서명) |
| kubeconfig 생성 | 자동 (`/etc/rancher/k3s/k3s.yaml`) | 수동 (kubectl config 명령어로 구성) |
| 인증서 배포 | 단일 노드에 집중 | Controller/Worker 노드에 수동 배포 |
| 인증서 갱신 | 자동 (90일 전부터) | 수동 (만료 시 재발급 및 배포) |
| kubeconfig 위치 | `/etc/rancher/k3s/k3s.yaml` | 사용자 정의 (`~/.kube/config` 등) |

### 수동 배포를 통해 얻은 인사이트

수동으로 인증서를 생성하고 배포하는 과정을 거치면서 깨달았던 것은 다음과 같다:

1. **CA의 중요성**: 모든 신뢰의 기반이 되는 CA 개인키(`ca-key.pem`)를 안전하게 보관해야 한다는 것
2. **인증서의 목적별 분리**: 인증서를 목적에 따라 분리해야 한다는 것
   - API 서버는 서버 인증서를 사용
   - kubelet, kube-proxy는 클라이언트 인증서를 사용
   - Service Account는 별도의 키 쌍을 사용
3. **SAN의 필요성**: API 서버 인증서에는 여러 접근 경로(IP, DNS)를 SAN에 명시해야 한다는 것
4. **권한 관리**: 인증서의 CN과 O 필드로 Kubernetes RBAC 권한이 결정된다는 것

<br>

무엇보다 가장 큰 깨달음은, 여러 노드에 걸쳐 적절한 인증서를 배포하고 관리하는 것은 매우 복잡하다는 것이다. 

<br>
K3s는 이 모든 과정을 자동화해 주기 때문에 편리하다. 그러나 문제가 발생했을 때 근본 원인을 파악하려면 이러한 수동 과정을 이해하는 것이 큰 도움이 된다. 특히 이번 kubeconfig 만료 문제처럼, "왜 `/etc/rancher/k3s/k3s.yaml`을 복사하면 해결되는가"를 이해하려면 kubeconfig 파일이 어떻게 구성되고 어떤 인증서를 참조하는지 알아야 한다.

<br>

## 인증서 관리 모범 사례

1. **개인키 보호**
   - `client-key-data`는 절대 공유하지 말 것
   - kubeconfig 파일 권한: `chmod 600 ~/.kube/config`
   - Git 저장소에 커밋하지 말 것 (.gitignore 추가)

2. **인증서 유효 기간 모니터링** *← 내가 하지 않았던 것*
   ```bash
   # 클라이언트 인증서 만료일 확인
   $ kubectl config view --raw -o jsonpath='{.users[0].user.client-certificate-data}' \
     | base64 -d | openssl x509 -noout -enddate
   
   # 서버 인증서 만료일 확인 (K3s)
   $ openssl x509 -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt -noout -enddate
   ```

3. **정기적인 갱신**
   - 만료 30일 전 갱신 권장
   - 자동화된 모니터링 및 알림 설정
   - Kubernetes 클러스터 업그레이드 시 인증서도 함께 확인

4. **최소 권한 원칙**
   - 사용자별로 별도의 인증서 발급
   - `system:masters` 그룹은 긴급 상황에만 사용
   - RBAC과 조합하여 세밀한 권한 제어
   - 운영 환경에서는 개인별 kubeconfig 발급 및 관리

5. **백업 및 복구 계획**
   - CA 개인키는 안전한 곳에 별도 백업
   - kubeconfig 파일 백업 자동화
   - 인증서 갱신 절차 문서화


### 만료 여부 모니터링

이번 문제를 겪으면서 배운 교훈은, 정기적인 모니터링의 중요성이다. 다음과 같이 간단한 스크립트로 인증서 만료 여부를 체크할 수 있다.

```bash
#!/bin/bash
# check-cert-expiry.sh

CERT_PATH="/var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt"
WARNING_DAYS=30

EXPIRY_DATE=$(openssl x509 -in $CERT_PATH -noout -enddate | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
CURRENT_EPOCH=$(date +%s)
DAYS_LEFT=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))

if [ $DAYS_LEFT -lt $WARNING_DAYS ]; then
      echo "WARNING: Certificate expires in $DAYS_LEFT days!"
      # 알림 발송 로직 추가 가능
else
      echo "Certificate is valid for $DAYS_LEFT days"
fi
```


<br>

# 정리

이번 문제는 단순한 인증서 만료 문제처럼 보이지만, Kubernetes의 보안 아키텍처를 이해하는 좋은 기회였다. Kubernetes는 모든 컴포넌트 간 통신에 TLS를 사용하며, 이는 다음을 보장한다:

1. **기밀성(Confidentiality)**: 통신 내용 암호화
2. **무결성(Integrity)**: 통신 내용 변조 방지
3. **인증(Authentication)**: 통신 당사자의 신원 확인

kubeconfig 파일에 저장된 인증서와 키는 이 중 '인증' 부분을 담당하며, PKI를 통해 분산 환경에서도 신뢰할 수 있는 인증 체계를 구축한다. 

K3s와 같은 배포판이 인증서를 자동으로 관리해주는 것은 편리하지만, Kubernetes The Hard Way 실습을 통해 수동으로 PKI를 구성해 보면서 그 내부 동작 원리를 깊이 이해할 수 있었다. 문제 발생 시 빠르게 대응하고 보안을 강화하려면, 표면적인 해결책을 넘어 근본 원리를 이해하는 것이 중요하다는 것을 다시 한번 깨달았다.

반 년 전에는 그저 "파일을 복사하면 된다"는 해결책만 알았지만, 이제는 그 이유를 명확히 설명할 수 있게 되었다. TLS handshake의 각 단계에서 어떤 인증서가 어떻게 사용되는지, CA의 역할이 무엇인지, 왜 인증서 유효 기간이 중요한지를 이해하게 된 것이다. 이러한 개념적 이해는 앞으로 비슷한 문제를 마주쳤을 때 더 나은 대응을 가능하게 할 것이다.