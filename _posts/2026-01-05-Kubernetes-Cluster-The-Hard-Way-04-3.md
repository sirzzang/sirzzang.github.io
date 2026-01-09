---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 4.3. Provisioning a CA and Generating TLS Certificates"
excerpt: "OpenSSL을 사용하여 Root CA 인증서와 각 컴포넌트 인증서를 생성하고 배포해 보자."
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

이번 글의 목표는 **Kubernetes 클러스터를 위한 TLS 인증서 생성 및 배포**다. [Kubernetes the Hard Way 튜토리얼의 Provisioning a CA and Generating TLS Certificates 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/04-certificate-authority.md)를 수행한다.

- Root CA 생성: Self-Signed 방식으로 클러스터 CA 생성
- 컴포넌트 인증서 생성: admin, kubelet, kube-proxy, kube-scheduler, kube-controller-manager, kube-api-server, service-accounts
- 인증서 배포: 각 노드에 필요한 인증서만 선별적으로 배포

<br>

# Prerequisite

[Kubernetes the Hard Way 튜토리얼에서 제공하는 ca.conf kube-scheduler 섹션의 `O` 필드](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/ca.conf#L155)에 `system`이 두 번 들어가 있다.

```bash
# ca.conf 오타 확인
cat ca.conf | grep -A 1 "\[kube-scheduler\]"
[kube-scheduler]
CN = system:kube-scheduler
O  = system:system:kube-scheduler  # system이 두 번!
```

Kubernetes에서 인증서의 `O`(Organization) 필드는 **사용자가 속한 그룹**을 나타낸다. RBAC에서 권한 부여 시 이 그룹명을 참조하므로, 오타가 있으면 kube-scheduler가 올바른 권한을 받지 못한다.

```bash
# (jumpbox) 오타 수정
sed -i 's/system:system:kube-scheduler/system:kube-scheduler/' ca.conf

# 수정 확인
cat ca.conf | grep -A 2 "\[kube-scheduler\]"
[kube-scheduler]
CN = system:kube-scheduler
O  = system:kube-scheduler  # 수정됨
```

<br>

# Root CA

CA(Certificate Authority)는 다른 인증서에 서명하는 역할을 한다. 이 단계에서는 클러스터 RootCA의 개인키와 인증서를 생성한다.

| 파일 | 설명 |
| --- | --- |
| `ca.key` | CA 개인키. 다른 인증서에 서명할 때 사용 |
| `ca.crt` | CA 인증서(루트 인증서). CA의 공개키 포함 |

## 개인키 생성

`openssl genrsa` 명령어로 4096비트 RSA 개인키를 생성한다.

```bash
# (jumpbox) #
openssl genrsa -out ca.key 4096
```

개인키 파일의 권한이 `600`(-rw-------)인 것을 확인한다. 개인키는 소유자만 읽을 수 있어야 한다.

```bash
# 결과 확인
ls -l ca.key
-rw------- 1 root root 3272 Jan  7 23:21 ca.key 
```



<br>

## 개인키 내용 확인

`openssl rsa -text` 명령어로 개인키의 구성 요소를 확인할 수 있다.

```bash
openssl rsa -in ca.key -text -noout
```

```bash
# 출력 예시 (축약)
Private-Key: (4096 bit, 2 primes)
modulus:
    00:af:9c:95:c5:6f:69:2c:fa:9f:15:20:7a:52:c0:
    ... (생략)
publicExponent: 65537 (0x10001) 
privateExponent:
    22:59:d3:54:24:f8:62:53:7d:d5:c0:9e:1c:dc:b7:
    ... (생략)
prime1, prime2, exponent1, exponent2, coefficient:
    ... (생략)
```

<br>

## 인증서 생성

Root CA는 상위 CA가 없으므로, Self-Signed** 방식으로 생성한다. 즉, CA가 자기 자신의 개인키로 자신의 인증서에 서명한다. 이 때, 위에서 생성한 개인키를 이용한다. 

`-section` 옵션을 지정하지 않았으므로, OpenSSL은 `ca.conf`의 기본 `[req]` 섹션을 사용한다. 뒤에서 이어질 다른 컴포넌트 인증서 생성 시에는 `-section` 옵션으로 각 섹션을 명시적으로 지정한다.

```bash
# (jumpbox)
# -x509: CSR 대신 Self-Signed 인증서 직접 생성
# -new: 새 인증서 생성 요청
# -sha512: SHA-512 해시 알고리즘으로 서명
# -noenc: 개인키 암호호 없음(패스프레이즈 없음)
# -key ca.key: 서명에 사용할 개인키(위에서 생성한 개인키)
# -days 3653: 유효 기간 약 10년
# -config ca.conf: 설정 파일에서 DN 정보 읽기
# -out ca.crt: 출력 인증서 파일
openssl req -x509 -new -sha512 -noenc \
  -key ca.key -days 3653 \
  -config ca.conf \
  -out ca.crt
```

```bash
# 결과 확인
ls -l ca.crt
-rw-r--r-- 1 root root 1899 Jan  7 23:23 ca.crt
```

<br>

## 인증서 내용 확인

`cat` 명령어로 인증서 파일을 확인하면 PEM 형식의 Base64 인코딩 텍스트가 출력된다. `-----BEGIN CERTIFICATE-----`와 `-----END CERTIFICATE-----` 사이가 인증서 데이터이다.

```bash
cat ca.crt
-----BEGIN CERTIFICATE-----
MIIFTDCCAzSgAwIBAgIUW8mqGlfxAkjpEL+xuhLrax2itNcwDQYJKoZIhvcNAQEN
BQAwQTELMAkGA1UEBhMCVVMxEzARBgNVBAgMCldhc2hpbmd0b24xEDAOBgNVBAcM
...
-----END CERTIFICATE-----
```

### 상세 정보 확인

`openssl x509 -text` 명령어로 인증서의 상세 정보를 확인한다. 이전 글에서 살펴 보았던 X.509 인증서 구조를 확인할 수 있다. 

 Self-Signed 인증서이므로 `Issuer`와 `Subject`가 동일하며, `X509v3 Basic Constraints: CA:TRUE` 항목 덕분에 이 인증서로 다른 인증서에 서명할 수 있다.


```bash
openssl x509 -in ca.crt -text -noout
```

```bash
# 출력 내용 (축약)
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            5b:c9:aa:1a:57:f1:02:48:e9:10:bf:b1:ba:12:eb:6b:1d:a2:b4:d7
        Signature Algorithm: sha512WithRSAEncryption
        Issuer: C = US, ST = Washington, L = Seattle, CN = CA # 발급자. Self-Signed이므로 Subject와 동일
        Validity # 유효 기간. 약 10년
            Not Before: Jan  7 14:23:41 2026 GMT
            Not After : Jan  8 14:23:41 2036 GMT
        Subject: C = US, ST = Washington, L = Seattle, CN = CA # 인증서 소유자. CN = CA
        Subject Public Key Info:
            Public Key Algorithm: rsaEncryption
                Public-Key: (4096 bit) # 공개키. 4096 bit RSA
                Modulus:
                    00:af:9c:95:c5:6f:69:2c:... (생략)
                Exponent: 65537 (0x10001)
        X509v3 extensions:
            X509v3 Basic Constraints: 
                CA:TRUE # CA 인증서임을 나타냄
            X509v3 Key Usage: # Certificate Sign, CRL Sign 권한
                Certificate Sign, CRL Sign
            X509v3 Subject Key Identifier: 
                F0:A4:CE:7F:0F:4A:C4:8D:74:7B:ED:C1:CD:50:4E:80:1C:09:DC:8D
    Signature Algorithm: sha512WithRSAEncryption
    Signature Value:
        2e:6d:a0:cc:9f:32:16:56:... (생략)
```



<br>

## 생성된 파일 정리

이 단계를 마치면 아래와 같은 파일이 생성되어야 한다. 이후 다음 각 단계에서 `ca.key`를 이용해 각 컴포넌트의 인증서에 서명하고, `ca.crt`는 모든 노드에 복사하는 과정을 진행한다. 거듭 말하지만, 클러스터 내 모든 컴포넌트는 `ca.crt`를 가지고 있어야 상대방 인증서를 검증할 수 있다. 


```bash
ls -la ca.*
-rw-r--r-- 1 root root 5863 Jan  6 00:15 ca.conf
-rw-r--r-- 1 root root 1899 Jan  7 23:23 ca.crt   # CA 인증서 (공개)
-rw------- 1 root root 3272 Jan  7 23:21 ca.key   # CA 개인키 (비공개)
```
<br>

# Admin 

상위 CA가 없었던 위 단계와 달리, CSR 생성 단계가 추가된다.


## 개인키 생성
```bash
# (jumpbox) #
openssl genrsa -out admin.key 4096
```
```bash
# 결과 확인
ls -l admin.key
-rw------- 1 root root 3272 Jan  7 23:47 admin.key
```

## 개인키 내용 확인

`openssl rsa -in admin.key -text -noout`으로 `ca.key`를 확인했던 방법과 마찬가지로 구조를 볼 수 있다. 여기서는 생략한다.

## CSR 생성

```bash
# csr 파일 생성
# admin.key 개인키를 사용해 
# 'CN=admin, O=system:masters'인 Kubernetes 관리자용 클라이언트 인증서 요청(admin.csr) 생성
openssl req -new -key admin.key -sha256 \
  -config ca.conf -section admin \
  -out admin.csr
ls -l admin.csr
```

### CSR 내용 확인

```bash
openssl req -in admin.csr -text -noout
```

CSR의 서명은 CA가 아닌 요청자 본인의 개인키로 이루어진다. 즉, 아직 서명되지 않은 인증서 요청이므로 `Issuer`나 `Validity` 정보가 없다. 대신 `Subject`와 `Requested Extensions`가 핵심이다. 


```bash
Certificate Request:
    Data:
        Version: 1 (0x0)
        Subject: CN = admin, O = system:masters   # Kubernetes 관리자 그룹: Kubernetes 관리자 권한 부여
        Subject Public Key Info:
            Public Key Algorithm: rsaEncryption
                Public-Key: (4096 bit)
                Modulus:
                    00:b1:e3:ca:89:7e:67:95:14:99:ea:10:8e:68:d7:
                    ... (생략)
                Exponent: 65537 (0x10001)
        Attributes:
            Requested Extensions:
                X509v3 Basic Constraints: 
                    CA:FALSE                      # 일반 인증서로, 다른 인증서에 서명 불가
                X509v3 Extended Key Usage: 
                    TLS Web Client Authentication # 클라이언트 인증 용도: kubectl 같은 클라이언트에서 사용
                X509v3 Key Usage: critical
                    Digital Signature, Key Encipherment
                Netscape Cert Type: 
                    SSL Client
                Netscape Comment: 
                    Admin Client Certificate
    Signature Algorithm: sha256WithRSAEncryption # CSR 자체의 서명 (자기 개인키로 서명)
```



## 인증서 생성

CSR을 이용해 CA에 인증서를 요청해 생성한다.

```bash
# ca에 csr 요청을 통한 crt 파일 생성
## -req : CSR를 입력으로 받아 인증서를 생성, self-signed 아님, CA가 서명하는 방식
## -days 3653 : 인증서 유효기간 3653일 (약 10년)
## -copy_extensions copyall : CSR에 포함된 모든 X.509 extensions를 인증서로 복사
## -CAcreateserial : CA 시리얼 번호 파일 자동 생성, 다음 인증서 발급 시 재사용, 기본 생성 파일(ca.srl)
openssl x509 -req -days 3653 -in admin.csr \
  -copy_extensions copyall \
  -sha256 -CA ca.crt \
  -CAkey ca.key \
  -CAcreateserial \
  -out admin.crt
Certificate request self-signature ok
subject=CN = admin, O = system:masters
```

## 인증서 내용 확인


```bash
# (jumpbox) #
openssl x509 -in admin.crt -text -noout
```

CSR과 달리 CA가 서명한 인증서에는 `Issuer`, `Validity` 정보가 추가되고, `X509v3 Authority Key Identifier`를 통해 어떤 CA가 서명했는지 확인할 수 있다.

```bash
# 출력 내용 (축약)
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            02:da:41:2b:39:d1:c6:ff:97:8a:06:3c:e1:fd:65:2b:59:0a:fd:ed
        Signature Algorithm: sha256WithRSAEncryption
        Issuer: C = US, ST = Washington, L = Seattle, CN = CA # CA가 발급
        Validity
            Not Before: Jan  7 14:55:57 2026 GMT
            Not After : Jan  8 14:55:57 2036 GMT # 10년
        Subject: CN = admin, O = system:masters
        Subject Public Key Info:
            Public Key Algorithm: rsaEncryption
                Public-Key: (4096 bit)
                Modulus:
                    00:b1:e3:ca:89:... (생략)
                Exponent: 65537 (0x10001)
        X509v3 extensions:
            X509v3 Basic Constraints: 
                CA:FALSE
            X509v3 Extended Key Usage: 
                TLS Web Client Authentication
            X509v3 Key Usage: critical
                Digital Signature, Key Encipherment
            Netscape Cert Type: 
                SSL Client
            Netscape Comment: 
                Admin Client Certificate
            X509v3 Subject Key Identifier: # 이 인증서의 식별자
                B5:E2:57:FC:79:31:DB:B2:B4:68:9A:CC:3A:E7:02:41:CA:6C:E7:5B
            X509v3 Authority Key Identifier: # 서명한 CA의 식별자 (ca.crt와 동일)
                F0:A4:CE:7F:0F:4A:C4:8D:74:7B:ED:C1:CD:50:4E:80:1C:09:DC:8D
    Signature Algorithm: sha256WithRSAEncryption # CA 개인키로 서명
    Signature Value:
        81:f4:08:5a:a7:3e:6f:47:... (생략)
```

## 참고: `system:masters` 그룹 사용 주의

`system:masters`는 Kubernetes의 **내장(built-in) 슈퍼유저 그룹**이다.

이 그룹에 속한 사용자는 막강한(?) 권한을 가진다:
- **인증(Authentication)** 통과 후 → **인가(Authorization) 우회**
- RBAC(`Role`/`ClusterRole`)이나 Webhook 기반 인가 검사를 **거치지 않음**
- API Server에서 모든 동작을 무조건 허용 (클러스터 슈퍼유저 권한)

따라서, 이 그룹에 대해서는 아래와 같은 보안 권고 사항이 제시된다:
- [Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/security/rbac-good-practices/#least-privilege)에서도 이 그룹 사용을 최소화하라고 권고
- 실무에서는 **AWS Root 계정**처럼 관리해야 함:
  - 클러스터 부트스트랩 목적으로만 사용
  - 일상적인 관리 작업에는 `cluster-admin` ClusterRole을 사용
  - **인증서가 탈취되면 복구가 매우 어려움**
- 필요한 경우, [`cluster-admin` ClusterRole](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#user-facing-roles)과 ClusterRoleBinding을 통해 관리자 권한을 부여하는 것이 안전

<br>

# 기타

이후 다른 컴포넌트의 인증서 생성은 비슷한 단계를 거친다.
- 컴포넌트 개인키 생성
- 컴포넌트 CSR 생성
- 컴포넌트 인증서 생성

반복 작업이기 때문에, 각 실행 내용 및 결과만 간단히 기록한다.

## 반복 작업 

나머지 컴포넌트 인증서를 반복문으로 생성한다.

```bash
# (jumpbox) 인증서 목록 변수 지정
certs=(
  "node-0" "node-1"
  "kube-proxy" "kube-scheduler"
  "kube-controller-manager"
  "kube-api-server"
  "service-accounts"
)

# 반복문으로 각 컴포넌트 인증서 생성
for cert in "${certs[@]}"; do
  openssl genrsa -out ${cert}.key 4096
  openssl req -new -key ${cert}.key -sha256 \
    -config ca.conf -section ${cert} \
    -out ${cert}.csr
  openssl x509 -req -days 3653 -in ${cert}.csr \
    -copy_extensions copyall \
    -sha256 -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out ${cert}.crt
done
```

각 인증서 생성 시 CA로부터 서명받는 과정이 성공하면 아래와 같은 메시지가 출력된다.

```bash
Certificate request self-signature ok
subject=CN = system:node:node-0, O = system:nodes, ...
Certificate request self-signature ok
subject=CN = system:node:node-1, O = system:nodes, ...
... (각 컴포넌트별 출력)
```

## 생성된 파일 확인

모든 인증서 생성이 완료되면 각 컴포넌트별로 `.key`, `.csr`, `.crt` 파일 3개씩 생성된다.

```bash
# (jumpbox) 생성된 파일 확인
ls -1 *.{crt,key,csr} | wc -l
27  # 9개 컴포넌트 × 3개 파일 = 27개

# 컴포넌트별 파일 확인
ls -1 *.crt
admin.crt
ca.crt
kube-api-server.crt
kube-controller-manager.crt
kube-proxy.crt
kube-scheduler.crt
node-0.crt
node-1.crt
service-accounts.crt
```

## 각 인증서 확인

각 인증서별로 주요 필드만 확인한다.

```bash
# node-0: 워커 노드 인증서. Client + Server 역할
openssl x509 -in node-0.crt -text -noout | grep -A 2 "Subject:"
        Subject: CN = system:node:node-0, O = system:nodes, C = US, ST = Washington, L = Seattle
        X509v3 extensions:
            X509v3 Extended Key Usage: 
                TLS Web Client Authentication, TLS Web Server Authentication
            X509v3 Subject Alternative Name: 
                DNS:node-0, IP Address:127.0.0.1

# node-1: 워커 노드 인증서. Client + Server 역할
openssl x509 -in node-1.crt -text -noout | grep -A 1 "Subject:"
        Subject: CN = system:node:node-1, O = system:nodes
            X509v3 Subject Alternative Name: 
                DNS:node-1, IP Address:127.0.0.1

# kube-proxy: 클라이언트 인증서
openssl x509 -in kube-proxy.crt -text -noout | grep "Subject:"
        Subject: CN = system:kube-proxy, O = system:node-proxier

# kube-scheduler: 클라이언트 인증서
openssl x509 -in kube-scheduler.crt -text -noout | grep "Subject:"
        Subject: CN = system:kube-scheduler, O = system:kube-scheduler

# kube-controller-manager: 클라이언트 인증서
openssl x509 -in kube-controller-manager.crt -text -noout | grep "Subject:"
        Subject: CN = system:kube-controller-manager, O = system:kube-controller-manager

# kube-api-server: Client + Server 역할. SAN에 여러 DNS/IP 포함
openssl x509 -in kube-api-server.crt -text -noout | grep -A 2 "Subject:"
        Subject: CN = kubernetes, C = US, ST = Washington, L = Seattle
            Netscape Cert Type: 
                SSL Client, SSL Server # 클라이언트이자 서버 역할
            X509v3 Subject Alternative Name: 
                IP Address:127.0.0.1, IP Address:10.32.0.1, # 10.32.0.1은 kubernetes Service ClusterIP
                DNS:kubernetes, DNS:kubernetes.default, DNS:kubernetes.default.svc,
                DNS:kubernetes.default.svc.cluster, DNS:kubernetes.svc.cluster.local,
                DNS:server.kubernetes.local, DNS:api-server.kubernetes.local
```


### API Server 인증서

API Server 인증서의 SAN에는 `10.32.0.1`이 포함되어 있다. 중요하게 확인하자.

이는 클러스터 내부에서 API Server에 접근할 때 사용하는 **kubernetes Service의 ClusterIP**이다. 참고로 실습 환경에서 사용하는 네트워크 대역은 다음과 같다.

| 항목 | 네트워크 대역 or IP | 설명 |
| --- | --- | --- |
| **clusterCIDR** | 10.200.0.0/16 | Pod들이 사용하는 전체 네트워크 대역 |
| → node-0 PodCIDR | 10.200.0.0/24 | node-0에 할당된 Pod IP 대역 |
| → node-1 PodCIDR | 10.200.1.0/24 | node-1에 할당된 Pod IP 대역 |
| **ServiceCIDR** | 10.32.0.0/24 | Service들이 사용하는 네트워크 대역 |
| → **kubernetes Service** | **10.32.0.1** | API Server에 접근하기 위한 ClusterIP |

클러스터 내부의 Pod들은 `kubernetes` DNS 이름 또는 `10.32.0.1` IP를 통해 API Server에 접근한다. 따라서 API Server 인증서의 SAN에는 이러한 모든 접근 경로가 포함되어야 한다.

```bash
# service-accounts: ServiceAccount 토큰 서명용 인증서
openssl x509 -in service-accounts.crt -text -noout | grep "Subject:"
        Subject: CN = service-accounts
```

<br>

# 인증서 배포

생성한 인증서를 각 노드에 배포한다. 각 노드는 역할에 따라 필요한 인증서만 받는다.

## 배포 전략

클러스터는 Control Plane 노드(server)와 Worker 노드(node-0, node-1)로 구성되어 있다. 각 노드 유형에 따라 필요한 인증서가 다르다.

| 노드 유형 | 필요한 인증서 | 이유 |
| --- | --- | --- |
| **Worker Node** | `ca.crt`, `node-X.crt`, `node-X.key` | kubelet이 API Server와 통신하기 위해 필요 |
| **Control Plane** | `ca.key`, `ca.crt`, `kube-api-server.*`, `service-accounts.*` | API Server 운영 및 ServiceAccount 토큰 서명에 필요 |

<br>

## Worker Node 배포

Worker Node(node-0, node-1)에는 kubelet이 실행된다. kubelet은 아래 역할을 한다.
- **클라이언트 역할**: API Server에 노드 상태와 Pod 정보를 보고
- **서버 역할**: API Server와 다른 컴포넌트로부터 요청을 받음

따라서 각 Worker Node에는 다음이 필요하다:
- `ca.crt`: API Server 인증서 검증용
- `kubelet.crt`, `kubelet.key`: kubelet의 클라이언트/서버 인증서

```bash
# (jumpbox) Worker Node에 인증서 배포
for host in node-0 node-1; do
  ssh root@${host} mkdir /var/lib/kubelet/

  scp ca.crt root@${host}:/var/lib/kubelet/

  scp ${host}.crt \
    root@${host}:/var/lib/kubelet/kubelet.crt

  scp ${host}.key \
    root@${host}:/var/lib/kubelet/kubelet.key
done
```

배포 후 node-0에 접속해 확인해 보자.

```bash
# (node-0) 배포된 인증서 확인
root@node-0:~# ls -l /var/lib/kubelet
total 12
-rw-r--r-- 1 root root 1899 Jan  8 00:14 ca.crt
-rw-r--r-- 1 root root 2147 Jan  8 00:14 kubelet.crt
-rw------- 1 root root 3272 Jan  8 00:14 kubelet.key
```

<br>

## Control Plane 배포

Control Plane(server)에는 API Server를 비롯한 핵심 컴포넌트들이 실행된다. 필요한 인증서 목록은 다음과 같다.
- `ca.key`, `ca.crt`: 다른 인증서 서명 및 검증
- `kube-api-server.key`, `kube-api-server.crt`: API Server의 TLS 통신
- `service-accounts.key`, `service-accounts.crt`: ServiceAccount 토큰 생성 및 검증

아래와 같이 배포한다. `root@server:~/` 경로는 server 노드의 root 사용자 홈 디렉토리(`/root`)를 의미한다. 이후 단계에서 API Server 설정 시 이 경로의 인증서를 참조한다.
```bash
# (jumpbox) Control Plane에 인증서 배포
scp ca.key ca.crt \
    kube-api-server.key kube-api-server.crt \
    service-accounts.key service-accounts.crt \
    root@server:~/ 
```

배포 후 server 노드에서 확인해 보자.

```bash
# (server) 배포된 인증서 확인
root@server:~# ls -l /root
total 24
-rw-r--r-- 1 root root 1899 Jan  8 00:21 ca.crt
-rw------- 1 root root 3272 Jan  8 00:21 ca.key
-rw-r--r-- 1 root root 2354 Jan  8 00:21 kube-api-server.crt
-rw------- 1 root root 3272 Jan  8 00:21 kube-api-server.key
-rw-r--r-- 1 root root 2004 Jan  8 00:21 service-accounts.crt
-rw------- 1 root root 3272 Jan  8 00:21 service-accounts.key
```

<br>

*나머지 인증서들(admin, kube-proxy, kube-scheduler, kube-controller-manager)은 다음 단계에서 kubeconfig 파일 생성에 사용된다.*   

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Root CA 생성**: Self-Signed 방식으로 `ca.key`, `ca.crt` 생성
2. **컴포넌트 인증서 생성**: admin, kubelet(node-0, node-1), kube-proxy, kube-scheduler, kube-controller-manager, kube-api-server, service-accounts
3. **인증서 배포**: Worker Node에는 `ca.crt`와 각 노드의 kubelet 인증서, Control Plane에는 CA 키/인증서와 API Server, ServiceAccount 인증서 배포

<br>

이번 실습을 통해 Kubernetes 클러스터의 mTLS 통신에 필요한 인증서들을 직접 생성하고 배포해 보았다. 각 컴포넌트의 Subject(CN, O)가 Kubernetes RBAC과 연동되는 방식, API Server 인증서에 다양한 SAN이 필요한 이유 등을 이해할 수 있었다. CA 개인키는 Control Plane 외에 배포하지 않도록 주의해야 한다.

<br>

다음 글에서는 생성한 인증서를 이용해 kubeconfig 파일을 생성한다.
