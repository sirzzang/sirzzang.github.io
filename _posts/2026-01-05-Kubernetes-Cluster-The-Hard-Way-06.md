---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 6. Generating the Data Encryption Config and Key"
excerpt: "Kubernetes Secret 데이터를 암호화하기 위한 encryption-config.yaml 설정 파일을 생성하고 Control Plane에 배포해 보자."
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

이번 글의 목표는 **Kubernetes Secret 데이터를 암호화하기 위한 설정 파일 생성 및 배포**다. [Kubernetes the Hard Way 튜토리얼의 Generating the Data Encryption Config and Key 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/06-data-encryption-keys.md)를 수행한다.

- 암호화 키 생성: AES-256 암호화를 위한 32바이트 랜덤 키 생성
- encryption-config.yaml 생성: EncryptionConfiguration 리소스 매니페스트 작성
- 설정 파일 배포: Control Plane 노드에 암호화 설정 배포

직전 단계에서 kubeconfig 파일을 생성했다면, 이번 단계에서는 etcd에 저장되는 민감한 데이터를 보호하기 위한 암호화 설정을 구성한다.

<br>

# 암호화 단계 분류

데이터 보안에서 암호화는 **데이터의 생명주기** 전체에 걸쳐 적용되어야 한다. 데이터가 어디에 있고 어떤 상태인지에 따라 암호화 방식이 달라지며, 이를 세 가지 단계로 분류할 수 있다.


## Encryption in Transit

**Encryption in Transit**(전송 중 암호화)은 **네트워크를 통해 이동하는 데이터**를 보호하는 것이다. 데이터가 한 시스템에서 다른 시스템으로 전송될 때, 중간에서 가로채는 공격자로부터 데이터를 보호한다.

- **방어 대상**: 중간자 공격(MITM, Man-in-the-Middle)
- **핵심 원리**: 송신자와 수신자 사이에 암호화된 채널을 생성하여 제3자가 내용을 볼 수 없게 함
- **대표적인 구현**:
  - **HTTPS(TLS)**: 웹 트래픽 암호화의 표준
  - **mTLS(mutual TLS)**: 양방향 인증을 통한 더 강력한 보안 ← **Kubernetes에서 사용**
  - **gRPC with TLS**: 마이크로서비스 간 통신 암호화

Kubernetes에서는 앞서 살펴본 것처럼 **mTLS**를 통해 컴포넌트 간 통신을 보호한다. kube-apiserver와 kubelet, etcd 간의 모든 통신이 TLS로 암호화된다.

<br>

## Encryption at Rest

**Encryption at Rest**(저장 중 암호화)은 **저장소에 기록된 데이터**를 보호하는 것이다. 물리적 디스크 탈취, 백업 파일 유출, 스냅샷 접근 등으로부터 데이터를 보호한다.

- **방어 대상**: 
  - 물리적 디스크 탈취
  - 백업 파일 유출
  - 스토리지 스냅샷 유출
- **핵심 원리**: 데이터를 저장하기 전에 암호화하고, 읽을 때 복호화
- **대표적인 구현**:
  - **데이터베이스 암호화**: DB 파일 자체를 암호화
  - **S3 Server-Side Encryption**: 클라우드 스토리지 암호화
  - **LUKS, BitLocker**: 운영체제 수준의 디스크 암호화
  - **Kubernetes etcd 암호화**: etcd에 저장되는 리소스 암호화 ← *이번 실습에서 다룰 내용*

<br>

## Encryption in Use

**Encryption in Use**(사용 중 암호화)는 **메모리에서 처리 중인 데이터**를 보호하는 것이다. 가장 구현이 어렵고 성능 오버헤드가 큰 암호화 방식이다.

- **방어 대상**: 
  - 실행 중인 프로세스 메모리 덤프 공격
  - 악의적인 OS/하이퍼바이저 공격
  - Cold Boot Attack(메모리 내용 추출)
- **핵심 원리**: 하드웨어 수준에서 메모리 영역을 격리하고 암호화
- **대표적인 구현**:
  - **Intel SGX(Software Guard Extensions)**: 신뢰 실행 환경 제공
  - **AMD SEV(Secure Encrypted Virtualization)**: VM 메모리 암호화
  - **Confidential VM**: 클라우드의 기밀 컴퓨팅

<br>

## 세 단계 암호화 비교

| 단계 | 보호 대상 | 보호 시점 | Kubernetes 적용 |
| --- | --- | --- | --- |
| **In Transit** | 네트워크 데이터 | 전송 중 | mTLS (기본 적용) |
| **At Rest** | 저장된 데이터 | 저장 시 | etcd 암호화 (선택적) |
| **In Use** | 메모리 데이터 | 처리 중 | 거의 미적용 |

이번 실습에서는 **Encryption at Rest**, 즉 etcd에 저장되는 데이터를 암호화하는 방법에 집중한다.

<br>

# etcd와 Kubernetes 데이터 저장

## etcd란?

etcd는 Kubernetes 클러스터의 **모든 상태 정보를 저장하는 분산 Key-Value 저장소**다. 클러스터에서 생성되는 모든 리소스(Pod, Deployment, Secret, ConfigMap 등)가 etcd에 저장된다.

<br>

## 데이터 저장 방식

etcd에 저장되는 모든 Kubernetes 리소스는 **Protocol Buffers(protobuf)로 직렬화**된 바이너리 형태로 저장된다.

```text
Kubernetes API 요청 → protobuf 직렬화 → etcd에 바이너리로 저장
```

이 방식은 JSON보다 효율적이지만, 암호화와는 별개다. protobuf로 직렬화된 데이터도 `strings`나 `hexdump` 명령어로 내용을 확인할 수 있다. 즉, **직렬화 ≠ 암호화**다.

<br>

## 보안 관점에서의 문제

기본적으로 etcd에 저장된 데이터는 **평문(plaintext)**이다. etcd 데이터 파일에 접근할 수 있다면 누구나 데이터를 읽을 수 있다는 의미다. 특히 Secret에 저장된 비밀번호, API 토큰, 인증서 등 민감한 정보가 그대로 노출될 위험이 있다.

```bash
# etcd에서 Secret 데이터를 직접 조회하면 평문으로 확인 가능
etcdctl get /registry/secrets/default/my-secret | hexdump -C
```

이러한 보안 위험을 해결하기 위해 **Encryption at Rest**가 필요하다.

<br>

# Kubernetes Encryption at Rest

## 개념

Kubernetes에서 **Encryption at Rest**란, **kube-apiserver가 etcd에 데이터를 저장하기 전에 암호화하는 것**을 의미한다. 중요한 점은 **암호화를 수행하는 주체가 kube-apiserver**라는 것이다. etcd는 단순히 암호화된 바이너리 데이터를 저장하는 역할만 한다.

```text
Kubernetes object
  → protobuf serialize
    → (optional) encryption provider
      → etcd write
```

이 구조에서 암호화 단계는 **선택적(optional)**이다. EncryptionConfiguration을 설정해야만 암호화가 활성화된다.

<br>

## 설정 기본값

Kubernetes의 거의 모든 배포판에서 Secret at-rest encryption은 기본적으로 **비활성화**되어 있다.

| 배포판 | Secret at-rest encryption |
| --- | --- |
| kubeadm | 기본 OFF |
| k3s | 기본 OFF |
| EKS | 기본 OFF |
| GKE | (옵션) |
| AKS | (옵션) |

기본값이 OFF인 이유는 다음과 같다:

1. **키 관리 복잡성**: 암호화 키를 안전하게 저장하고 관리해야 함
2. **Key Rotation 어려움**: 키를 주기적으로 교체하는 운영 부담
3. **성능 오버헤드**: 모든 읽기/쓰기에 암호화/복호화 연산 추가
4. **복구 불가 위험**: 키를 분실하면 데이터 복구가 불가능

> Kubernetes는 "**암호화는 운영자가 책임지고 활성화하라**"는 철학을 가지고 있다.

<br>

## 책임 분리 구조

Kubernetes는 보안을 **조립식(modular)**으로 제공한다. 각 계층의 역할이 명확히 분리되어 있다. 

| 컴포넌트 | 역할 |
| --- | --- |
| kube-apiserver | 직렬화 + (선택적) 암호화 |
| etcd | 불투명 바이트(opaque bytes) 저장 |
| encryption provider | 암호화 알고리즘 제공 |
| key management | 운영자 책임 |

```text
kubectl apply
   ↓
kube-apiserver
   → validation
   → protobuf serialize
   → (optional) encrypt-at-rest
   ↓
etcd (BoltDB)
```

이러한 구조 덕분에:
- **네트워크 보안**은 TLS/mTLS로
- **저장 데이터 보안**은 optional encryption으로
- **메모리 보안**은 운영자의 추가 구성으로

무엇을 얼마나 보호할지는 **운영자의 선택과 책임**이다.

<br>

## 암호화 활성화 방법

Kubernetes는 kube-apiserver의 `--encryption-provider-config` 플래그를 통해 **etcd에 저장되는 리소스를 암호화**할 수 있는 기능을 제공한다.

- **etcd 저장 시**: kube-apiserver가 지정된 리소스를 암호화한 후 etcd에 저장
- **etcd 조회 시**: kube-apiserver가 암호화된 데이터를 복호화하여 반환

이렇게 하면 etcd 데이터베이스 파일에 직접 접근하더라도 암호화된 데이터의 내용을 알 수 없게 된다. 실제 etcd 값에는 `k8s:enc:aescbc:v1:key1:<ciphertext>`와 같은 형태의 데이터가 기록된다.

<br>

## 암호화 가능 리소스

암호화 가능 리소스는 아래 목록과 같다.

- **secrets**: 가장 일반적으로 암호화하는 리소스 (패스워드, 토큰 등)
- **configmaps**: 민감한 설정 정보를 포함하는 경우
- **customresources**: Custom Resource Definition(CRD)도 암호화 가능
- 기타 etcd에 저장되는 대부분의 리소스

이번 실습에서는 가장 중요한 사용 케이스인 **Secret 리소스 암호화**에 집중한다.

<br> 


# Encryption 설정

## Encryption Key 생성

암호화 키를 생성한다. 이 키는 Secret 데이터를 암호화/복호화하는 데 사용된다.

```bash
export ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64)
echo $ENCRYPTION_KEY
# 출력 예시
/G3g+Rpr44cOsVkH9dxZTp8qH2nK5vL3mN9pQ1sT4uV=
```
- `head -c 32 /dev/urandom`: `/dev/urandom` 장치에서 32바이트의 랜덤 데이터를 읽는다
  - `/dev/urandom`: Linux의 난수 생성 장치
  - `-c 32`: 32바이트만 읽기 (AES-256 암호화에 충분한 크기)
- `base64`: 바이너리 데이터를 Base64 인코딩하여 텍스트로 변환


## Encryption Config 파일 생성


실습에서는 암호화 설정 템플릿 파일 [encryption-config.yaml](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/configs/encryption-config.yaml)을 제공한다. 이 템플릿 파일을 이용해 EncryptionConfiguration 리소스 매니페스트를 작성하면 된다.
```bash
cat configs/encryption-config.yaml
```

```yaml
kind: EncryptionConfiguration
apiVersion: apiserver.config.k8s.io/v1
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: ${ENCRYPTION_KEY}
      - identity: {}
```

주요 설정 항목을 살펴 보자.

### kind와 apiVersion

```yaml
kind: EncryptionConfiguration
apiVersion: apiserver.config.k8s.io/v1
```

- **kind**: `EncryptionConfiguration`은 kube-apiserver가 etcd에 저장할 리소스를 어떻게 암호화할지 정의하는 설정 파일 리소스 타입이다.
- **apiVersion**: `apiserver.config.k8s.io/v1`은 현재 안정 버전의 API다.

이 설정 파일은 kube-apiserver의 `--encryption-provider-config` 플래그로 참조된다.

<br>

### resources

암호화를 적용할 Kubernetes 리소스를 지정한다.

```yaml
resources:
  - resources:
      - secrets  # 이번 실습에서는 Secret만 암호화
```

이번 실습에서는 Secret만 암호화하지만, 필요에 따라 다른 리소스도 추가할 수 있다:

```yaml
resources:
  - resources:
      - secrets
      - configmaps  # ConfigMap도 암호화
```

<br>

### providers

암호화 방식을 정의한다. Kubernetes는 **위에서 아래 순서대로** provider를 적용한다.

- **쓰기(Write)**: 첫 번째 provider 사용
- **읽기(Read)**: 위에서부터 순서대로 시도하여 복호화 성공 시 반환

```yaml
providers:
  - aescbc:
      keys:
        - name: key1
          secret: ${ENCRYPTION_KEY}
  - identity: {}
```

위 설정이 동작하는 방식은 다음과 같다:

| 상황 | 처리 과정 |
| --- | --- |
| 새 Secret 생성 | aescbc(첫 번째 provider)로 암호화하여 저장 |
| 암호화된 Secret 읽기 | aescbc로 복호화 성공 → 반환 |
| 기존 평문 Secret 읽기 | aescbc 실패 → identity로 평문 그대로 읽기 |

<br>

### aescbc provider

**aescbc**는 AES-CBC(Advanced Encryption Standard - Cipher Block Chaining) 방식으로 데이터를 암호화하는 provider다.

```yaml
- aescbc:
    keys:
      - name: key1                    # 키 식별자
        secret: ${ENCRYPTION_KEY}     # 암호화에 사용할 키 (Base64 인코딩)
```

- **name**: 키 식별자. etcd에 저장될 때 `k8s:enc:aescbc:v1:key1:ciphertext` 형태의 prefix로 사용된다.
- **secret**: 암호화에 사용할 32바이트 키를 Base64로 인코딩한 값. 앞서 생성한 `ENCRYPTION_KEY` 환경 변수가 여기에 치환된다.

> AES-CBC는 대칭 키 암호화 알고리즘으로, 같은 키로 암호화와 복호화를 수행한다. 32바이트 키를 사용하므로 AES-256 암호화가 적용된다.

<br>

#### identity provider

**identity**는 데이터를 암호화하지 않고 있는 그대로 처리하는 provider다.

```yaml
- identity: {}
```

현재 설정에서 identity는 **두 번째 provider**이므로 다음과 같이 동작한다:

| 동작 | 설명 |
| --- | --- |
| **쓰기 시** | 사용되지 않음 (첫 번째 provider인 aescbc가 사용됨) |
| **읽기 시** | aescbc로 복호화 실패 시 평문으로 읽기 시도 |

identity provider가 필요한 이유는 **하위 호환성** 때문이다:
- **역할**: 암호화 활성화 전에 저장된 기존 평문 Secret을 계속 읽을 수 있도록 함
- **필요성**: 암호화 기능을 처음 활성화할 때, 기존 데이터를 즉시 마이그레이션하지 않아도 됨
- **결과**: 새 Secret은 aescbc로 암호화되고, 기존 평문 Secret은 계속 읽을 수 있음 (점진적 마이그레이션)

> **주의**: identity를 첫 번째 provider로 설정하면 새 Secret이 평문으로 저장된다. 암호화를 원한다면 반드시 암호화 provider(aescbc 등)를 첫 번째로 배치해야 한다.

<br>

## 설정 파일 생성

`envsubst` 명령어로 템플릿의 `${ENCRYPTION_KEY}` 변수를 실제 값으로 치환한다.

```bash
envsubst < configs/encryption-config.yaml > encryption-config.yaml
```

생성된 파일을 확인한다.

```bash
cat encryption-config.yaml
```

```yaml
kind: EncryptionConfiguration
apiVersion: apiserver.config.k8s.io/v1
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: /G3g+Rpr44cOsVkH9d...  # 실제 키 값으로 치환됨
      - identity: {}
```

<br>

# 설정 파일 배포

생성한 Encryption Config 파일을 **Control Plane 노드**에만 배포한다.
- **Control Plane 노드에만 필요**: Encryption Config는 kube-apiserver가 사용하는 설정 파일
- **Worker 노드는 불필요**: Worker 노드는 etcd에 직접 접근하지 않으며, 암호화/복호화는 API Server가 담당

<br>
실습 환경의 경우, `server`가 단일 Control Plane 이므로, 해당 가상 머신에만 `encryption-config.yaml` 파일을 배포한다.

```bash
scp encryption-config.yaml root@server:~/
encryption-config.yaml                             100%  271   325.6KB/s   00:00

# 확인
ssh server ls -l /root/encryption-config.yaml
-rw-r--r-- 1 root root 271 Jan  8 22:55 /root/encryption-config.yaml
```

당연하지만, 프로덕션 환경에서 Control Plane이 여러 대인 경우, 모든 Control Plane 노드에 동일한 `encryption-config.yaml` 파일을 배포해야 한다. 모든 kube-apiserver가 동일한 암호화 키를 사용해야 Secret을 정상적으로 암호화/복호화할 수 있다.

<br>

# 결과

이번 실습을 통해 Kubernetes Secret 데이터를 암호화하기 위한 설정을 직접 구성해 보았다. 암호화 3단계(In Transit, At Rest, In Use)의 개념과 Kubernetes에서의 적용 방식을 이해하고, `encryption-config.yaml`의 구조와 providers 우선순위, AES-CBC 암호화 방식, 그리고 하위 호환성을 위한 identity provider의 역할을 학습했다. 이 설정은 다음 단계에서 kube-apiserver를 구성할 때 `--encryption-provider-config` 플래그로 참조된다.

<br>

다음 글에서는 Kubernetes 클러스터의 핵심 데이터 저장소인 etcd 클러스터를 구성한다.