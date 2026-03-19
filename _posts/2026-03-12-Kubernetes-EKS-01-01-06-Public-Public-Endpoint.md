---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 6. 엔드포인트 분석"
excerpt: "Public-Public 구성에서 API 서버 엔드포인트 구성에 대해 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - NLB
  - Endpoint
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Public-Public 구성에서 EKS API 서버 **엔드포인트의 네트워크 특성**을 분석한다.

- **엔드포인트 구성**: `endpointPublicAccess: true`, `endpointPrivateAccess: false` → 외부 공인 접근만 허용
- **dig 분석**: API 서버 도메인이 NLB 공인 IP 2개로 해석 → AWS 관리형 NLB 뒤에 HA 구성
- **레이턴시**: `kubectl -v=6`으로 확인하면 공인 인터넷 경유 약 876ms
- **보안**: `publicAccessCidrs: 0.0.0.0/0`으로 전 세계에 노출. 프로덕션에서는 제한 필요

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %})에서 확인한 구성 요소(시스템 파드, VPC CNI 등)는 엔드포인트 모드와 무관한 공통 사항이고, 이 글에서 다루는 네트워크 경로는 **Public-Public 모드에 고유**한 특성이다.

<br>


# 들어가며

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %})에서 EKS 클러스터의 구성 요소를 확인했다. 시스템 파드, VPC CNI, ECR 이미지, Add-on 등은 엔드포인트 모드에 관계없이 동일하다.

이번 글에서는 **엔드포인트 접근 경로**에 집중한다. 현재 클러스터는 Public-Public 구성으로 배포되어 있는데, 이 구성에서 API 서버 엔드포인트가 어떤 네트워크 경로로 접근되는지 살펴 본다. 이후 Public-Private, Private-Private 구성으로 전환할 때 이 엔드포인트 경로가 어떻게 바뀌는지가 핵심 비교 포인트가 된다.

<br>


# 엔드포인트 구성 확인

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %}#aws-eks-describe-cluster)의 `aws eks describe-cluster` 출력에서 `resourcesVpcConfig`의 엔드포인트 관련 필드를 분석한다.

```json
"resourcesVpcConfig": {
  "endpointPublicAccess": true,
  "endpointPrivateAccess": false,
  "publicAccessCidrs": [
    "0.0.0.0/0"
  ]
}
```

| 필드 | 값 | 의미 |
| --- | --- | --- |
| `endpointPublicAccess` | `true` | API 서버에 **공인 인터넷**으로 접근 가능 |
| `endpointPrivateAccess` | `false` | VPC 내부에서 **프라이빗 DNS로 접근 불가** |
| `publicAccessCidrs` | `0.0.0.0/0` | 모든 IP에서 접근 허용 (제한 없음) |

이 조합이 **Public-Public** 구성이다. kubectl 클라이언트(로컬 PC)와 워커 노드(EC2) 모두 공인 인터넷 경로를 통해 API 서버에 접근한다. 워커 노드도 VPC 내부에 있지만, `endpointPrivateAccess: false`이므로 프라이빗 경로가 아닌 NAT Gateway → 인터넷 → NLB 경로를 사용한다.

EKS는 엔드포인트 모드를 3가지로 제공한다.

| 모드 | Public | Private | 특징 |
| --- | --- | --- | --- |
| **Public-Public** (현재) | `true` | `false` | 모든 트래픽이 공인 경로. 가장 간단하지만 보안 취약 |
| **Public-Private** | `true` | `true` | 외부는 공인, 워커 노드는 프라이빗 경로. 워커 ↔ API 서버 통신이 VPC 내부 |
| **Private-Private** | `false` | `true` | 공인 접근 차단. VPN/Direct Connect/bastion 필요 |

<br>


# API 서버 엔드포인트 분석

API 서버 엔드포인트가 실제로 어떤 인프라 뒤에 있는지 `dig`으로 확인한다.

```bash
CLUSTER_NAME=myeks
APIDNS=$(aws eks describe-cluster --name $CLUSTER_NAME | jq -r .cluster.endpoint | cut -d '/' -f 3)
echo $APIDNS
```

```
461A1FA....gr7.ap-northeast-2.eks.amazonaws.com
```

```bash
dig +short $APIDNS
```

```
xx.xxx.xxx.xx1
xx.xxx.xxx.xx2
```

공인 IP 2개가 반환된다. `ipinfo.io`로 해당 IP의 소유자를 확인해 보자.

```bash
curl -s ipinfo.io/xx.xxx.xxx.xx1
```

```json
{
  "ip": "xx.xxx.xxx.xx1",
  "hostname": "ec2-xx-xxx-xxx-xx1.ap-northeast-2.compute.amazonaws.com",
  "city": "Incheon",
  "region": "Incheon",
  "country": "KR",
  "org": "AS16509 Amazon.com, Inc.",
  "timezone": "Asia/Seoul"
}
```

```bash
curl -s ipinfo.io/xx.xxx.xxx.xx2
```

```json
{
  "ip": "xx.xxx.xxx.xx2",
  "hostname": "ec2-xx-xxx-xxx-xx2.ap-northeast-2.compute.amazonaws.com",
  "city": "Incheon",
  "region": "Incheon",
  "country": "KR",
  "org": "AS16509 Amazon.com, Inc.",
  "timezone": "Asia/Seoul"
}
```

두 IP 모두 서울 리전의 Amazon 소유다. 이 IP들은 AWS가 관리하는 **NLB(Network Load Balancer)**의 IP로, EKS 컨트롤 플레인은 AWS가 관리하는 **별도의 VPC**에 있고 API 엔드포인트는 NLB를 통해 공인 IP로 노출되는 구조다.

IP가 **2개**라는 점이 중요하다. [EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#컨트롤-플레인)에서 살펴본 것처럼 EKS 컨트롤 플레인은 3개 가용 영역에 분산 배치되는데, NLB가 이 API 서버들을 앞단에서 로드밸런싱하므로 **자동 HA**가 보장된다.

| | **온프레미스 Kubernetes** | **EKS (Public-Public)** |
| --- | --- | --- |
| API 서버 위치 | 마스터 노드에 직접 | AWS 관리형 VPC, NLB 뒤 |
| dig 결과 | 마스터 노드 IP 1개 | NLB 공인 IP 2개 (HA) |
| IP 소유자 | 내가 관리하는 서버 | Amazon (AS16509) |
| HA | 직접 구성 ([Kubespray HA]({% post_url 2026-02-02-Kubernetes-Kubespray-05-01 %}): HAProxy, nginx static pod 등) | AWS가 자동 HA |

> **참고**: 이전 EKS 버전에서는 인증 없이 API 서버의 `/version` 엔드포인트에 접근하면 Kubernetes 버전 정보가 응답에 포함되었다. 공격자가 알려진 CVE를 타겟팅할 수 있는 보안 위험이었는데, 현재는 인증되지 않은 요청에 **401 Unauthorized를 반환**하도록 변경되어 클러스터 버전 정보가 외부에 노출되지 않는다.
>
> ![eks-version-endpoint-exposed]({{site.url}}/assets/images/eks-version-endpoint-exposed.png){: .align-center width="600"}
>
> <center><sup>이전 동작 — 다른 EKS 클러스터(v1.31.5)에서 <code>/version</code> 접근 시 버전 정보가 그대로 노출됨</sup></center>
>
> ![eks-version-endpoint-blocked]({{site.url}}/assets/images/eks-version-endpoint-blocked.png){: .align-center width="600"}
>
> <center><sup>현재 동작 — 인증 없이 접근하면 401 Unauthorized 반환</sup></center>

<br>


# kubectl -v=6으로 레이턴시 확인

`-v=6`은 kubectl의 verbosity level로, HTTP 요청/응답 로그를 확인할 수 있다. Public-Public 구성의 네트워크 경로를 체감해 보자.

> **참고: kubectl verbosity level (`-v`)**
>
> kubectl의 `-v` 플래그는 로그 출력의 상세 수준을 조절한다. 숫자가 클수록 더 많은 내부 동작이 출력된다.
>
> | 레벨 | 출력 내용 |
> | --- | --- |
> | `-v=0` | 기본값. 결과만 출력 |
> | `-v=4` | 디버그 수준. 요청 URL 표시 |
> | `-v=6` | **요청/응답 요약** (HTTP 메서드, URL, 상태 코드, 소요 시간). 레이턴시 확인에 적합 |
> | `-v=7` | 요청 헤더까지 표시 |
> | `-v=8` | 요청/응답 **본문(body)**까지 표시 |
> | `-v=9` | 최대 상세. 응답 본문을 잘림 없이 전부 출력 |
>
> 일상적인 디버깅에는 `-v=6`이면 충분하고, API 요청/응답 페이로드까지 확인해야 할 때 `-v=8` 이상을 쓴다.

```bash
kubectl get node -v=6
```

```
I0315 02:08:21.202434   30270 loader.go:405] Config loaded from file:  /Users/eraser/.kube/config
I0315 02:08:21.206611   30270 envvar.go:172] "Feature gate default state" feature="WatchListClient" enabled=true
I0315 02:08:21.206628   30270 envvar.go:172] "Feature gate default state" feature="ClientsAllowCBOR" enabled=false
...
I0315 02:08:22.088887   30270 round_trippers.go:632] "Response" verb="GET" url="https://461A1FA....gr7.ap-northeast-2.eks.amazonaws.com/api/v1/nodes?limit=500" status="200 OK" milliseconds=876
NAME                                              STATUS   ROLES    AGE   VERSION
ip-192-168-2-21.ap-northeast-2.compute.internal   Ready    <none>   27h   v1.34.4-eks-f69f56f
ip-192-168-3-96.ap-northeast-2.compute.internal   Ready    <none>   27h   v1.34.4-eks-f69f56f
```

핵심은 HTTP 요청과 응답이다.

```
GET https://461A1FA...eks.amazonaws.com/api/v1/nodes?limit=500
→ 200 OK in 876 milliseconds
```

- **어디로 요청했는지**: EKS API 서버 엔드포인트로 HTTPS 요청
- **어떤 API를 호출했는지**: `/api/v1/nodes?limit=500` (노드 목록 조회)
- **응답 코드**: `200 OK` → 인증 + 인가 성공
- **레이턴시**: 876ms → 공인 인터넷을 통해 AWS 관리형 API 서버까지 왕복한 시간

| | **온프레미스 Kubernetes** | **EKS (Public-Public)** |
| --- | --- | --- |
| config 로드 | `~/.kube/config` | 동일 |
| 인증 방식 | 클라이언트 인증서 (X.509) | `aws eks get-token` ([STS 토큰]({% post_url 2026-03-12-Kubernetes-EKS-01-01-03-Kubeconfig-Authentication %})) |
| API 서버 주소 | 마스터 노드 IP (`192.168.10.100:6443`) | EKS 엔드포인트 (NLB 공인 IP) |
| 레이턴시 | 내부 네트워크라 빠름 (수~수십 ms) | 공인 경로라 상대적으로 느림 (수백 ms) |

876ms의 레이턴시에는 STS 토큰 발급 시간도 포함되어 있지만, 근본적으로 **kubectl → 인터넷 → NLB → API 서버**라는 공인 경로를 거치기 때문에 온프레미스보다 느릴 수밖에 없다.

<br>


# Public-Public 네트워크 경로 정리

현재 구성의 네트워크 경로를 정리하면 다음과 같다.

## kubectl (로컬 PC) → API 서버

```
로컬 PC → 인터넷 → NLB(공인 IP) → EKS 관리형 VPC → API 서버
```

로컬 PC에서 kubectl을 실행하면 EKS 엔드포인트 도메인을 DNS 조회하여 NLB의 공인 IP를 얻고, 공인 인터넷을 통해 접근한다. `publicAccessCidrs: 0.0.0.0/0`이므로 어디서든 접근 가능하다.

## 워커 노드 (EC2) → API 서버

```
EC2 (프라이빗 서브넷) → NAT Gateway → 인터넷 → NLB(공인 IP) → EKS 관리형 VPC → API 서버
```

`endpointPrivateAccess: false`이므로, VPC 내부의 워커 노드도 프라이빗 경로를 사용할 수 없다. kubelet, kube-proxy 등 노드의 컴포넌트가 API 서버와 통신할 때도 NAT Gateway를 거쳐 공인 인터넷으로 나간 뒤 다시 NLB로 돌아오는 비효율적인 경로를 탄다.

## 보안

| 항목 | 현재 설정 | 보안 영향 |
| --- | --- | --- |
| `endpointPublicAccess` | `true` | API 서버가 공인 인터넷에 노출 |
| `publicAccessCidrs` | `0.0.0.0/0` | **모든 IP에서 접근 가능** (제한 없음) |
| `endpointPrivateAccess` | `false` | VPC 내부 프라이빗 경로 없음 |

프로덕션 환경에서는 최소한 `publicAccessCidrs`를 관리자 IP로 제한하거나, Public-Private 또는 Private-Private 구성으로 전환하는 것이 권장된다.

<br>


# 정리

Public-Public 구성의 엔드포인트 특성을 정리한다.

| 항목 | Public-Public |
| --- | --- |
| **kubectl 접근 경로** | 로컬 PC → 인터넷 → NLB(공인 IP) → API 서버 |
| **워커 노드 접근 경로** | EC2 → NAT GW → 인터넷 → NLB(공인 IP) → API 서버 |
| **dig 결과** | NLB 공인 IP 2개 |
| **레이턴시** | ~876ms (공인 인터넷 경유) |
| **보안** | 전 세계 노출 (`0.0.0.0/0`) |

가장 간단한 구성이지만, 워커 노드까지 공인 경로를 거치는 비효율과 보안 노출이 있다. 이후 Public-Private 구성으로 전환하면 워커 노드가 VPC 내부 프라이빗 경로를 사용하게 되어 레이턴시와 보안이 모두 개선된다.

<br>
