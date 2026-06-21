---
title: "[GenAI] GenAI on K8s: 9.1 - 보안 개념: Defense in Depth"
excerpt: "GenAI 워크로드를 K8s에 올릴 때의 보안 원칙을 defense in depth 관점에서 정리하고, 컨테이너 생애주기 전체에 걸친 보안 영역과 GenAI 고유 고려사항까지 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GenAI
  - Security
  - EKS
  - Defense-in-Depth
  - Container-Security
  - Pod-Identity
  - IRSA
  - Kubernetes-for-Generative-AI-Solutions
  - Kubernetes-for-Generative-AI-Solutions-Chapter-9
hidden: true
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 9장의 학습 내용을 바탕으로 합니다*

<br>

# TL;DR

- GenAI 워크로드의 보안 출발점은 **defense in depth** — 한 겹이 뚫려도 다음 겹이 막도록 여러 층의 통제를 겹쳐 둔다
- 컨테이너 보안은 **빌드부터 런타임까지 생애주기 전체**에 걸쳐야 한다: 공급망(supply chain) → 호스트(host) → 런타임(runtime) → 네트워크(network) → 시크릿(secrets)
- 공급망 보안의 핵심은 신뢰된 경량 이미지, 이미지 불변성(immutable tag), 서명·검증, 지속적 취약점 스캔이다
- 호스트 하드닝은 클라우드 공통 원리 — 컨테이너 전용 OS(Bottlerocket), IMDSv2, 프라이빗 서브넷 배치 등
- GenAI 배포는 표준 K8s 보안 위에 **모델 무결성, 데이터 프라이버시, GPU 자원 격리** 같은 공격면이 더해진다
- 파드의 AWS 자격증명 획득 방식은 IRSA(2019)에서 **Pod Identity(2023)**로 진화 중이다

<br>

# Defense in Depth

GenAI 워크로드를 K8s에 올릴 때의 보안은 **defense in depth**(심층 방어)에서 시작한다. 여러 공격 벡터에 대비해 보안 레이어를 동심원으로 겹친 모델로, 안쪽일수록 핵심 자산이고 각 원이 하나의 레이어이자 공격 벡터다. ([NIST 정의](https://csrc.nist.gov/glossary/term/defense_in_depth))

![계층형 보안 모델 — defense in depth]({{site.url}}/assets/images/genai-on-k8s-ch09-layered-security-model.png){: .align-center}

| 레이어(안→밖) | 무엇 | 대표 위협 | 대응 |
|---|---|---|---|
| **User Data** | 민감 사용자 데이터(비밀번호, PII) | 데이터 유출 | 저장·전송 시 암호화 |
| **Configuration** | env, 설정, secret, API key | 설정 노출 → 데이터 유출/권한 상승/오작동 | secret 관리, 노출 최소화 |
| **Application Code** | 앱 코드 | SQL injection, 원격 코드 실행(RCE) | 정적·동적 분석, 즉시 패치 |
| **Dependencies** | 라이브러리, 프레임워크, 외부 패키지 | 취약·구버전 의존성(**가장 흔한 침투 경로**) | 의존성 취약점 스캔 |
| **Containers** | 런타임, 이미지 | 권한 상승, host 공격, 정보 노출 | 이미지 서명, 런타임 보안(Falco) |
| **Host** | 노드 OS, 커널 | 커널이 모든 컨테이너에 공유 → host 뚫리면 전체 감염 | OS 하드닝, 컨테이너 전용 OS |

> Configuration 레이어의 위험이 상위 레이어로 번지는 예시: API key가 평문 env로 유출 → 그 키로 다른 시스템에 접근(권한 상승) → 정상처럼 보이는 악성 동작(오작동). 설정 한 줄의 노출이 상위 레이어 침해로 번진다.

> Dependencies가 "가장 흔한 진입점"인 대표 사례: Log4Shell(Log4j), event-stream(npm) 등 라이브러리 취약점이 곧 앱 침해로 이어진 경우가 많다.

<br>

# 컨테이너 보안

컨테이너는 소프트웨어와 의존성을 캡슐화해 이식성이 높지만, 그만큼 위험도 캡슐화한다. 보안은 빌드부터 런타임까지 **생애주기 전체**에 걸쳐야 한다.

## 공급망 보안 (Supply Chain)

이미지 빌드에서 운영 배포·모니터링까지 전 과정을 포괄한다.

![컨테이너 공급망 단계]({{site.url}}/assets/images/genai-on-k8s-ch09-container-supply-chain.png){: .align-center}

| 단계 | 위협 | 대응 | 도구 |
|---|---|---|---|
| **Build** | 비검증 의존성·잘못된 설정으로 악성코드 유입 | 신뢰된 베이스·경량 이미지(distroless/scratch), 이미지 불변성 | DockerSlim |
| **Test** | 미탐 취약점·오설정이 하류로 전파 | CI/CD에 보안 테스트(정적·동적) 통합 | Snyk |
| **Store** | 레지스트리 내 이미지 변조·구버전 | 이미지 서명·검증, RBAC | Cosign, OPA Gatekeeper |
| **Encrypt** | 이미지에 secret이 박힘 | secret 임베드 금지 → 외부 secret store에서 런타임 주입 | Vault, Secrets Manager |
| **Scan** | 이미지·의존성 취약점 | 빌드·저장 단계 지속 스캔(CVE DB 대조) | Trivy, ECR Enhanced Scanning |

### 이미지 불변성과 multi-stage build

**이미지 불변성(immutable tag)**이란 한 번 push한 태그를 덮어쓸 수 없게 고정하는 것이다(`latest`=mutable, `v1.0`=immutable). 보안상 의미는 *"안전하다고 검증·서명한 바로 그 이미지가 나중에 몰래 바뀌지 않음"*을 보장하는 데 있다. 재현성과 감사 추적에도 중요하고, GenAI에서는 fine-tune/추론 이미지의 model integrity 보장에 특히 중요하다.

**multi-stage build**는 빌드 과정을 단계로 쪼개 각 단계는 적합한 베이스로 특정 작업(컴파일, 의존성 설치)만 하고, 최종 이미지에는 필요한 산출물만 복사하는 기법이다. GenAI에서는 거대한 학습 프레임워크·전처리 스크립트를 최종 추론 이미지에서 제외해 더 작고 안전한 이미지를 만들 수 있다.

## Host 보안

노드 OS·커널은 모든 컨테이너가 공유하므로, host가 뚫리면 전체가 위험하다. 호스트 하드닝의 원리는 클라우드 공통이다 — 아래 원리로 일반화해 두면 다른 클라우드에도 그대로 통한다.

| 원리 (클라우드 공통) | AWS/EKS 구현 예시 |
|---|---|
| 노드를 외부에 직접 노출하지 않는다 | **private subnet** 배치 — 외부 공개는 LB/Ingress로만 |
| 관리 접근 경로를 최소화한다 | **SSH 차단** → SSM Session Manager |
| 자격증명·메타데이터 통로를 보호한다 | **IMDSv2** — 세션 토큰 요구 + `hop_limit=1`로 컨테이너 접근 차단 |
| 저장 데이터를 암호화한다 | EBS 볼륨 KMS 암호화, NVMe instance store는 XTS-AES-256 자동 |
| OS 공격표면을 최소화한다 | 컨테이너 전용 OS(**Bottlerocket**), CIS 벤치마크 |

### Bottlerocket

Bottlerocket은 AWS의 컨테이너 전용 OS로, host 계층의 공격 표면을 최소화한다.

| 항목 | 일반 AL2023 | Bottlerocket |
|---|---|---|
| 루트 파일시스템 | 읽기/쓰기 | **읽기 전용**(immutable) |
| 패키지 매니저 | 있음 | **없음**(공격 표면 축소) |
| 업데이트 | in-place | **atomic**(이미지 교체·롤백) |
| 용도 | 범용 | 컨테이너 전용 |

> **atomic 업데이트**란 OS를 패키지 단위(`yum`/`apt`)로 in-place 갱신하지 않고, **OS 이미지 통째**를 교체하는 방식이다. A/B 두 파티션을 두고 비활성 파티션에 새 이미지를 다 받은 뒤 재부팅 시 전환한다. "전부 적용 / 전혀 미적용" 둘 중 하나라 중간 깨진 상태가 없다. 문제 시 부팅 포인터를 직전 파티션으로 되돌려 롤백한다. 루트 FS가 읽기전용(dm-verity 무결성 검증)이라 실행 중 변조가 불가능하다 — EKS 노드를 *고쳐 쓰지 않고 통째로 교체*하는 **불변 인프라(immutable infrastructure)** 철학과 맞는다.

### IMDSv2와 hop_limit

EC2 안에는 **IMDS**(Instance Metadata Service)라는 특수 주소 `169.254.169.254`가 있고, 여기에 요청하면 그 노드에 붙은 IAM Role의 임시 자격증명을 돌려준다. **SSRF**(Server-Side Request Forgery) 공격으로 이 자격증명을 탈취하는 시나리오가 위험하다.

**IMDSv2**는 두 겹으로 이를 막는다.

- `http_tokens = "required"` — 자격증명을 받으려면 먼저 `PUT`으로 세션 토큰을 받고 그 토큰을 헤더에 실어야 한다. SSRF는 보통 단순 `GET`만 시킬 수 있어 토큰 협상을 못 한다
- `http_put_response_hop_limit = 1` — 메타데이터 응답의 네트워크 hop을 1로 제한한다. 컨테이너는 별도 network namespace라 응답이 host netns → veth/bridge → pod netns로 포워딩되며 여기서 TTL이 1 깎인다. `hop_limit=1`이면 파드로 들어가는 순간 TTL=0이 되어 폐기된다

> 파드가 **Pod Identity**로 자격증명을 받는다면 IMDS는 불필요하므로 `hop_limit=1`로 차단하는 게 맞다. `hostNetwork: true` 파드는 호스트 netns를 공유하므로 hop_limit에 영향받지 않는다.

## 런타임 보안 (Container Runtime)

실행 중인 컨테이너의 권한 상승·무단 접근을 방지한다.

| 항목 | 내용 |
|---|---|
| 자원 제한 | CPU/메모리 limit 미설정 시 한 컨테이너가 노드 자원 독식 → DoS·클러스터 불안정 |
| 비-root 실행 | `securityContext`로 non-root 강제 |
| capability drop | 불필요한 Linux capability 제거(`drop: [ALL]`) |
| **PSS**(Pod Security Standards) | 내장 Pod Security Admission으로 프로파일 강제, namespace 라벨로 적용 |
| 런타임 모니터링 | Falco 등으로 실시간 이상행위 탐지 |

핵심 `securityContext` 예시:

```yaml
securityContext:
  runAsUser: 1000          # 비-root 일반 사용자
  runAsGroup: 1000
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
```

### Pod Security Standards 3단계

| 프로파일 | 수준 | 설명 |
|---|---|---|
| `privileged` | 제한 없음 | 모든 권한 허용 |
| `baseline` | 흔한 권한상승 차단 | 일반 워크로드에 적합 |
| `restricted` | 엄격 | 강제 non-root, capability drop 등 |

namespace에 `pod-security.kubernetes.io/enforce=<level>` 라벨로 적용한다.

### Falco

**Falco**는 DaemonSet으로 커널을 **eBPF**(또는 전통 syscall hook)로 관찰해 컨테이너 내 셸 생성, `/etc/passwd`·`/etc/shadow` 변조, 비신뢰 IP 연결, SA 토큰 오용 등을 실시간 탐지한다.

> **eBPF**는 리눅스 커널 안에서 안전하게 돌리는 샌드박스 프로그램이다. 커널을 수정하거나 모듈을 올리지 않고도 syscall·네트워크 이벤트를 가로채 관찰할 수 있다. 지금은 여기까지 알면 충분하다. 더 파고 싶다면 eBPF internals(커널 검증기, 맵, 프로그램 타입)를 별도로 살펴보자.

## 네트워크 보안

| 항목 | 내용 |
|---|---|
| 세그먼트·격리 | namespace로 경계 분리, **NetworkPolicy**로 ingress/egress 제어(Pod 레벨) |
| Pod-to-Pod | 기본 전부 허용 → 위험. zero-trust + service mesh(Istio/Linkerd) **mTLS**로 인증·암호화 |
| Ingress/Egress | Ingress는 HTTPS/TLS + WAF, Egress는 egress 정책으로 외부 유출 제한 |
| API server | RBAC + OIDC/IAM 인증, 신뢰 소스만 접근 허용 |
| DNS | CoreDNS spoofing 방어. NetworkPolicy로 질의 제한, DNSSEC |
| 모니터링 | Cilium, Calico, Datadog 등으로 트래픽 가시성 확보 |


> **참고 — Ingress/Egress 보안 방향**
> - **Ingress (들어오는 트래픽):** HTTPS/TLS 로 전송 구간 암호화 + **WAF(Web Application Firewall, 웹 애플리케이션 방화벽)** 으로 SQL injection·XSS 등 L7 공격 차단.
> - **Egress (나가는 트래픽):** egress 정책으로 외부로 나가는 연결을 화이트리스트화 → 데이터 유출(exfiltration) 경로 제한.

> **참고 — L7 방화벽(WAF) vs 일반 방화벽(L3/L4)**
>
> 우리가 흔히 "방화벽"이라 부르는 것(`iptables`, 보안그룹, K8s NetworkPolicy)은 대부분 **L3/L4** 에서 동작한다. 둘의 차이는 *패킷의 무엇을 보고 허용/차단을 결정하느냐* 에 있다.
>
> | 구분 | 일반 방화벽 (L3/L4) | WAF (L7) |
> |---|---|---|
> | 판단 기준 | IP(L3) + 포트·프로토콜(L4) — 5-tuple | HTTP 요청 내용: URL·헤더·쿼리·바디·쿠키 |
> | 보는 범위 | 패킷 봉투(주소·포트)만, 내용물은 안 봄 | TLS 복호화 후 애플리케이션 메시지를 파싱 |
> | 막는 것 | "이 IP·포트로의 연결 자체"를 허용/거부 | SQL injection, XSS, path traversal 등 **요청 내용**에 숨은 공격 |
> | K8s 대응 | NetworkPolicy, 보안그룹 | ALB 앞단 AWS WAF, Ingress 게이트웨이 |
>
> **왜 둘 다 필요한가:** L3/L4 방화벽 입장에선 `443/TCP 로 들어오는 정상 HTTPS 연결`일 뿐이라, 그 안의 `GET /items?id=1' OR '1'='1` 같은 SQLi 페이로드를 구분할 수 없다. 포트·IP는 멀쩡하기 때문. WAF 는 그 HTTP 요청을 직접 열어보고 패턴/시그니처로 걸러낸다. 즉 **방어 계층(layer)이 달라 서로 대체가 아니라 보완** 관계다.


## Secrets 관리

| 항목 | 내용 |
|---|---|
| K8s Secret | 네이티브 리소스. **base64 인코딩일 뿐 암호화가 아니다** → 추가 보호 필요 |
| etcd 암호화 | EKS는 기본적으로 AWS 관리 키로 etcd 암호화. **envelope encryption** 추가 가능 |
| RBAC | 최소권한 — 필요한 Secret에만 접근 허용 |
| 외부 도구 | Vault, Secrets Manager(중앙관리·암호화·감사·세밀 접근제어) + `secrets-store-csi-driver`로 K8s 통합 |
| 회전 | K8s Secret은 자동 회전 미지원 → 외부 도구로 보완 |
| 전송 | 자격증명 교환 시 TLS |
| 감사 | K8s audit log + SIEM 연동 |

> **참고 — envelope encryption**
>
> **envelope encryption**이란 데이터를 **데이터 키**로 암호화하고, 그 데이터 키를 다시 **KMS 마스터 키**로 암호화하는 2단 구조다. 마스터 키는 KMS 밖으로 나오지 않고, etcd에는 암호화된 데이터 키만 남아 노출 위험이 줄어든다.


> **참고 — SIEM(Security Information and Event Management)**
>
> 여러 소스의 보안 로그·이벤트를 **한 곳으로 모아 상관분석(correlation)·탐지·알림** 하는 시스템. 이름 그대로 두 축의 결합이다.
> - **SIM (Information):** 로그를 장기 수집·저장·검색 → 사후 감사·컴플라이언스 증적.
> - **SEM (Event):** 실시간 이벤트 상관분석 → 의심 패턴 탐지·즉시 알림.
>
> **K8s audit log 와의 관계:** API server 의 audit log 는 "누가(user) / 무엇을(verb·resource) / 언제 / 결과(allow·deny)" 를 남기는 *원천 데이터*일 뿐이다. 그 자체로는 노드 로컬 파일에 쌓일 뿐 탐지·알림 기능이 없다. SIEM 으로 흘려보내야 비로소
> - 여러 클러스터·여러 소스(CloudTrail, VPC Flow Log, 앱 로그)와 **교차 상관분석**,
> - "비정상 권한 상승 시도", "심야 대량 Secret 조회" 같은 **룰 기반 실시간 알림**,
> - 장기 보존 + 검색으로 **사고 발생 시 역추적**
> 이 가능해진다.
>
> | 대표 도구 | 비고 |
> |---|---|
> | Splunk, IBM QRadar, Microsoft Sentinel | 상용 SIEM |
> | Elastic Stack(ELK), Wazuh | 오픈소스 계열 |
> | **AWS:** GuardDuty + Security Hub | EKS audit log 연동 가능, 매니지드 위협 탐지 |


<br>

# GenAI 워크로드 추가 고려사항

GenAI 배포는 모델 아티팩트, 대용량 민감 학습 데이터, 비신뢰 추론 요청을 다루기 때문에 표준 K8s 보안 위에 공격면이 더해진다.

## 데이터 프라이버시와 컴플라이언스

학습/파인튜닝 데이터는 data lake/warehouse에 있다. 데이터 분류·규제에 맞춰 저장 암호화·엄격한 접근제어·감사를 적용하고, 접근은 TLS + 최소권한으로 한다. EKS라면 **IRSA 또는 Pod Identity**로 임시 자격증명을 받아 S3 등에 접근한다.

## IRSA vs Pod Identity

둘 다 *파드가 장기 자격증명 없이 IAM Role 권한으로 AWS에 접근*하게 하는 메커니즘이다.

| | IRSA (2019) | Pod Identity (2023) |
|---|---|---|
| trust principal | OIDC provider ARN | 서비스 principal `pods.eks.amazonaws.com` |
| 사전 준비 | 클러스터마다 OIDC provider 등록, SA annotation, 복잡한 trust policy | `eks-pod-identity-agent` 애드온 + association API |
| SA 연결 | SA annotation `eks.amazonaws.com/role-arn` | `create-pod-identity-association`(cluster·ns·sa·role) |
| 자격증명 흐름 | SDK가 `AssumeRoleWithWebIdentity`(STS)로 web identity 토큰 교환 | agent가 임시 자격증명 주입(`AssumeRole`+`TagSession`) |
| 장점 | — | OIDC 의존 제거, trust 단순, **세션 태그**(cluster·ns·pod·sa)로 한 Role을 여러 워크로드에 세밀 제어 |

![IRSA 동작 개요]({{site.url}}/assets/images/genai-on-k8s-ch09-irsa-overview.png){: .align-center}

> IRSA 흐름: annotated SA의 파드 생성 → control plane의 webhook이 projected SA 토큰을 마운트하도록 파드 스펙 mutate → 파드 내 SDK가 그 토큰으로 STS `AssumeRoleWithWebIdentity` 호출 → STS가 OIDC 검증·trust policy 확인 후 임시 자격증명 반환.

이 개념들이 실제 Terraform 코드에 어떻게 적용되는지는 [다음 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-09-02-Security-Infrastructure-Code %})에서 살펴본다.

## 모델 엔드포인트 보안

파인튜닝 후 모델 아티팩트는 S3(접근제어) 또는 이미지에 패키징해 레지스트리로 보관한다. 엔드포인트는 K8s Service/Ingress로 노출하되 네트워크·API 레벨 보호를 건다.

| 보호 | 방법 |
|---|---|
| 전송 암호화 | ACM 인증서를 ALB/NLB에 붙여 TLS(443) 종단 |
| 공격 방어 | ALB에 **AWS WAF** 부착 → injection·악성 입력 차단 |
| 인증 | 클라이언트·서비스 진위 검증 |

<br>

# 정리

GenAI 워크로드의 보안은 defense in depth를 뼈대로, 컨테이너 생애주기 전체에 걸쳐 공급망·호스트·런타임·네트워크·시크릿 5개 영역에 통제를 겹쳐야 한다. 여기에 GenAI 고유의 모델 무결성·데이터 프라이버시·GPU 격리까지 더해진다.

| 영역 | 핵심 포인트 |
|---|---|
| 공급망 | 경량 이미지, immutable tag, 서명·검증, 지속 스캔 |
| 호스트 | Bottlerocket(읽기전용·atomic), IMDSv2(SSRF 차단) |
| 런타임 | non-root, capability drop, PSS, Falco |
| 네트워크 | NetworkPolicy, mTLS, WAF |
| 시크릿 | 외부 store(Secrets Manager), CSI driver, envelope encryption |
| GenAI 고유 | Pod Identity, 모델 엔드포인트 TLS/WAF, 데이터 암호화 |

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions — GitHub](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions)
- [NIST — Defense in Depth 정의](https://csrc.nist.gov/glossary/term/defense_in_depth)
- [AWS Bottlerocket 공식 페이지](https://aws.amazon.com/bottlerocket/)
- [EKS Pod Identity 소개](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Secrets Store CSI Driver](https://secrets-store-csi-driver.sigs.k8s.io/)
- [Falco — Cloud Native Runtime Security](https://falco.org/)

<br>
