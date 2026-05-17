---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 7. 엔드포인트 액세스 분석"
excerpt: "Public-Public 구성에서 API 서버 엔드포인트 구성에 대해 살펴보자."
categories:
  - Kubernetes
toc: true
hidden: true
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

이번 글에서는 Public-Public 구성에서 EKS API 서버 **엔드포인트의 네트워크 특성**과 **보안 노출 수준**을 분석한다.

- **엔드포인트 구성**: `endpointPublicAccess: true`, `endpointPrivateAccess: false` → 외부 공인 접근만 허용
- **NLB 구조**: 각 EKS 클러스터에 전용 NLB 1개가 생성되고, AZ별 고정 공인 IP를 가짐. `dig`으로 확인하면 NLB IP 2개 반환
- **로드밸런싱 2단계**: DNS 레벨에서 클라이언트가 NLB IP 중 하나를 선택 → NLB가 뒤의 API 서버 인스턴스로 분산
- **내부 검증 (ss, tcpdump)**: 노드 프로세스(kubelet 등)는 NLB 공인 경로를 타지만, **Pod는 kubernetes Service의 Endpoints(ENI 사설 IP)를 통해 사설 경로**를 탄다
- **외부 검증 (curl)**: DNS 이름이든 공인 IP든 네트워크 레벨에서 API 서버 443 포트에 도달 가능. 인증(토큰)이 마지막 방어선
- **레이턴시**: `kubectl -v=6`으로 확인하면 공인 인터넷 경유 약 876ms

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %})에서 컨트롤 플레인과 데이터 플레인을 잇는 EKS Owned ENI를 확인했다. 이 글에서 다루는 **공인 엔드포인트 경로**는 그 사설 경로와 대비되는, **Public-Public 모드에 고유**한 특성이다.

<br>


# 들어가며

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %})에서 EKS Owned ENI를 통한 컨트롤 플레인 ↔ 데이터 플레인 사설 통신 경로를 확인했다. 이번 글에서는 그와 대비되는 **공인 엔드포인트 접근 경로**에 집중한다.

현재 클러스터는 Public-Public 구성으로 배포되어 있는데, 이 구성에서 API 서버 엔드포인트가 어떤 네트워크 경로로 접근되는지, 그리고 그 경로가 **보안 관점에서 어떤 의미**를 갖는지 살펴 본다. 이후 Public-Private, Private-Private 구성으로 전환할 때 이 엔드포인트 경로가 어떻게 바뀌는지가 핵심 비교 포인트가 된다.

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

이 조합이 **Public-Public** 구성이다. kubectl 클라이언트(로컬 PC)와 워커 노드(EC2) 모두 공인 인터넷 경로를 통해 API 서버에 접근한다. 워커 노드도 VPC 내부에 있지만, `endpointPrivateAccess: false`이므로 프라이빗 경로가 아닌 IGW → 인터넷 → NLB 공인 경로를 사용한다.

EKS는 엔드포인트 모드를 3가지로 제공한다.

| 모드 | Public | Private | 특징 |
| --- | --- | --- | --- |
| **Public-Public** (현재) | `true` | `false` | API 서버로 향하는 트래픽이 모두 공인 경로. 가장 간단하지만 보안 취약 |
| **Public-Private** | `true` | `true` | 외부는 공인, 워커 노드 → API 서버는 프라이빗 경로 |
| **Private-Private** | `false` | `true` | 공인 접근 차단. VPN/Direct Connect/bastion 필요 |

<br>



# Public-Public 네트워크 경로 정리

현재 구성의 네트워크 경로를 정리하면 다음과 같다.

## kubectl (로컬 PC) → API 서버

![public-public-kubectl-to-apiserver]({{site.url}}/assets/images/public-public-kubectl-to-apiserver.png){: .align-center}

<center><sup>Public-Public 구성의 전체 네트워크 경로 — kubectl은 인터넷을 통해 NLB 공인 IP로 직접 접근한다.</sup></center>

```
로컬 PC → 인터넷 → NLB(공인 IP) → EKS 관리형 VPC → API 서버
```

로컬 PC에서 kubectl을 실행하면 EKS 엔드포인트 도메인을 DNS 조회하여 NLB의 공인 IP를 얻고, 공인 인터넷을 통해 접근한다. `publicAccessCidrs: 0.0.0.0/0`이므로 어디서든 접근 가능하다. 인증 정보 없이도 TCP 연결까지는 가능한데, 이는 뒤의 [Public 엔드포인트 검증](#통신-경로-검증-public-엔드포인트-curl)에서 curl로 직접 확인한다.

## 워커 노드 (kubelet) → API 서버

![public-public-kubelet-to-apiserver]({{site.url}}/assets/images/public-public-kubelet-to-apiserver.png){: .align-center}

<center><sup>kubelet → kube-apiserver 네트워크 경로 — 퍼블릭 서브넷의 워커 노드가 IGW를 통해 인터넷으로 나간 뒤 NLB 공인 IP로 API 서버에 접근한다</sup></center>

```
EC2 (퍼블릭 서브넷, 퍼블릭 IP) → IGW → 인터넷 → NLB(공인 IP) → EKS 관리형 VPC → API 서버
```

`endpointPrivateAccess: false`이므로, VPC 내부의 워커 노드도 프라이빗 경로를 사용할 수 없다. 현재 실습 환경에서는 워커 노드가 [퍼블릭 서브넷에 퍼블릭 IP를 가지고 배치]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#vpc-모듈이-자동으로-해주는-것)되어 있으므로(`map_public_ip_on_launch = true`, `enable_nat_gateway = false`), IGW를 통해 직접 인터넷으로 나간 뒤 NLB 공인 IP로 돌아오는 경로를 탄다. kubelet, kube-proxy 등 노드의 모든 컴포넌트가 이 경로를 사용한다.

> **참고**: 프로덕션 환경에서는 워커 노드를 **프라이빗 서브넷**에 배치하는 것이 일반적이다. 이 경우 경로는 `EC2 (프라이빗 서브넷) → NAT Gateway → IGW → 인터넷 → NLB → API 서버`가 된다. 어느 쪽이든 Public-Public 구성에서는 VPC 밖으로 나갔다가 돌아오는 비효율은 동일하다.

VPC 안에 있으면서도 VPC 밖으로 나갔다가 다시 들어오는 구조인데, [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %})를 통한 사설 경로가 존재함에도 `endpointPrivateAccess: false` 설정 때문에 사용하지 못하는 것이다. Public-Private 구성으로 전환하면 이 경로가 VPC 내부로 바뀐다.

## API 서버 → 워커 노드 (kubelet)

![public-public-apiserver-to-kubelet]({{site.url}}/assets/images/public-public-apiserver-to-kubelet.png){: .align-center}

<center><sup>kube-apiserver → kubelet 네트워크 경로 — API 서버가 EKS Owned ENI를 통해 워커 노드의 kubelet에 직접 도달한다. NLB·IGW·인터넷을 경유하지 않는 사설 경로로, 엔드포인트 모드와 무관하게 항상 동일하다.</sup></center>

```
API 서버 (EKS 관리형 VPC) → EKS Owned ENI → 워커 노드 (EC2)
```

API 서버가 kubelet에 명령을 내릴 때(`kubectl exec`, `kubectl logs`, webhook 호출 등)는 **항상 [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %})를 통한 사설 경로**를 사용한다. 이 방향은 엔드포인트 모드와 무관하게 동일하다. 공인 인터넷을 경유하지 않으므로, `kubectl exec`이나 `kubectl logs` 같은 명령의 레이턴시는 상대적으로 낮다.

## 보안

| 항목 | 현재 설정 | 보안 영향 |
| --- | --- | --- |
| `endpointPublicAccess` | `true` | API 서버가 공인 인터넷에 노출 |
| `publicAccessCidrs` | `0.0.0.0/0` | **모든 IP에서 접근 가능** (제한 없음) |
| `endpointPrivateAccess` | `false` | VPC 내부 프라이빗 경로 없음 |

프로덕션 환경에서는 최소한 `publicAccessCidrs`를 관리자 IP로 제한하거나, Public-Private 또는 Private-Private 구성으로 전환하는 것이 권장된다.

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

두 IP 모두 서울 리전의 Amazon 소유다. 이 IP들은 AWS가 관리하는 **NLB(Network Load Balancer)**의 공인 IP다.

## NLB 구조

NLB(Network Load Balancer)는 AWS의 **L4(TCP/UDP) 로드밸런서**다. HTTP 헤더 같은 애플리케이션 내용을 보지 않고, TCP 연결 레벨에서 트래픽을 뒤의 타겟으로 분산한다. 고정 IP 지원, 초저지연, 초고성능이 특징이다.

EKS에서 NLB는 다음과 같이 구성된다.

| 항목 | 설명 |
| --- | --- |
| **클러스터당 전용 NLB** | 각 EKS 클러스터에 별도의 NLB가 생성됨 |
| **AZ별 고정 공인 IP** | NLB가 여러 개인 것이 아니라, **하나의 NLB가 각 AZ에 고정 IP를 하나씩** 가짐 |
| **워커 노드와 독립** | NLB, [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}), 컨트롤 플레인 EC2는 클러스터 서브넷 설정(AZ 수)에 따라 자동 생성. 워커 노드가 0대여도 존재 |
| **DNS 자동 등록** | EKS가 NLB 프로비저닝 → 각 AZ에 고정 IP 할당 → 해당 IP들을 **A 레코드로 등록**한 DNS 이름(`xxxx.gr7.ap-northeast-2.eks.amazonaws.com`) 생성까지 전부 자동 처리 |

`dig` 결과에서 IP가 **2개** 반환된 것은, 해당 도메인에 **A 레코드가 2개 등록**되어 있다는 뜻이다. 서브넷을 3개(AZ 3개)로 설정했지만 IP가 2개만 나온 것은, NLB가 트래픽이 있는 AZ에만 활성화되었거나 EKS가 내부적으로 2개 AZ만 선택했기 때문일 수 있다.

[EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#컨트롤-플레인)에서 살펴본 것처럼, 컨트롤 플레인은 최소 2개의 API 서버와 3개의 etcd 인스턴스가 분산 배치된다. API 서버의 정확한 인스턴스 수는 **AWS가 공개하지 않는** 내부 구현이다. NLB IP 2개는 AZ별 진입점이지, API 서버 인스턴스 수와 같은 것은 아니다.

온프레미스에서 API 서버 HA 구성 시 HAProxy/nginx 같은 LB를 API 서버 앞에 직접 놓고, TLS 인증서의 SAN(Subject Alternative Name)에 LB의 IP/도메인을 포함시켜야 했다. EKS는 이를 **전부 자동으로** 해준다: NLB 프로비저닝, DNS 설정, TLS 인증서, API 서버 다중화까지. 온프레미스에서 선택이었던 HA가 EKS에서는 기본 제공이다.

| | **온프레미스 Kubernetes** | **EKS (Public-Public)** |
| --- | --- | --- |
| API 서버 위치 | 컨트롤 플레인 노드에 직접 | AWS 관리형 VPC, NLB 뒤 |
| dig 결과 | 컨트롤 플레인 노드 IP 1개 | NLB 공인 IP 2개 (HA) |
| IP 소유자 | 내가 관리하는 서버 | Amazon (AS16509) |
| HA 구성 | 직접 구성 ([Kubespray HA]({% post_url 2026-02-02-Kubernetes-Kubespray-05-01 %}): HAProxy, nginx static pod 등) | AWS가 자동 HA |
| TLS 인증서 SAN | LB IP/도메인을 수동으로 추가 | EKS가 자동 관리 |
| DNS | 수동 설정 또는 없음 | EKS가 자동 등록 |

## 로드밸런싱 2단계

클라이언트가 API 서버에 접근할 때, 로드밸런싱은 **2단계**로 이루어진다.

**1단계 — DNS 레벨**: 클라이언트(kubectl, kubelet 등)가 API 서버 도메인을 DNS resolve하면, A 레코드에 등록된 NLB IP 목록이 반환된다. 이 중 **하나를 OS의 DNS resolver(glibc `getaddrinfo()`)가 선택**한다. 보통 round-robin 또는 랜덤이다. kubelet이나 kube-proxy가 직접 선택하는 것이 아니라, OS 레벨에서 일어나는 DNS 기반 로드밸런싱의 일반적인 동작이다.

**2단계 — NLB 레벨**: 선택된 IP의 NLB가 뒤에 있는 여러 API 서버 인스턴스(타겟 그룹) 중 하나로 TCP 연결을 포워딩한다. NLB는 단순 통과 장치가 아니라 L4 로드밸런서이므로, 하나의 NLB IP 뒤에 여러 API 서버가 있을 수 있다.

온프레미스에서 kube-apiserver의 기본 포트는 6443이다. EKS에서 포트가 443인 이유는 클라이언트가 API 서버에 직접 접속하는 것이 아니라 NLB를 경유하기 때문이다. NLB 리스너가 HTTPS 표준 포트인 443으로 받아서 뒤의 API 서버로 전달하는 구조이므로, 클라이언트에게 내부 포트가 노출되지 않는다. 굳이 API 서버가 리스닝하고 있는 6443 포트를 열어주 줄 필요도 없다. AWS의 다른 HTTPS API 엔드포인트(S3, IAM, STS 등)와도 일관된 포트 체계이기도 하다.

```
클라이언트 ──DNS resolve──→ [IP-A, IP-B]
                                │
                    glibc가 IP-A 선택
                                │
                                ▼
                          NLB (IP-A)
                           ╱      ╲
                  API 서버 1    API 서버 2    ...
```

같은 워커 노드에서도 kubelet과 kube-proxy가 서로 다른 NLB IP에 연결될 수 있다. 각 프로세스가 독립적으로 DNS resolve를 수행하기 때문이다.

<br>


# 통신 경로 검증: 클러스터 내부 (ss, tcpdump)

이론적으로 정리한 엔드포인트 구조를 `ss`와 `tcpdump`로 실제 확인해 보자.

## 노드 → API 서버 (ss -tnp)

워커 노드에서 TCP 연결 상태를 확인한다. `ss -tnp`는 TCP 연결(`-t`)을 숫자 포트 그대로(`-n`) 프로세스 정보와 함께(`-p`) 보여준다. kubelet 등의 프로세스 정보를 보려면 `sudo`가 필요하고, SSH 연결은 `grep -v ssh`로 제외한다.

```bash
for i in my-eks-node1 my-eks-node2; do echo ">> node $i <<"; ssh $i sudo ss -tnp | grep -v ssh; echo; done
```

```
>> node my-eks-node1 <<
State Recv-Q Send-Q Local Address:Port     Peer Address:Port Process
ESTAB 0      0       192.168.2.21:43312  43.201.196.244:443   users:(("kube-proxy",pid=2888,fd=12))
ESTAB 0      0       192.168.2.21:47296   54.116.87.122:443   users:(("aws-k8s-agent",pid=1772863,fd=8))
ESTAB 0      0       192.168.2.21:43580   54.116.87.122:443   users:(("kubelet",pid=2236,fd=12))

>> node my-eks-node2 <<
State Recv-Q Send-Q Local Address:Port     Peer Address:Port Process
ESTAB 0      0       192.168.3.96:38580   54.116.87.122:443   users:(("aws-k8s-agent",pid=1777947,fd=12))
ESTAB 0      0       192.168.3.96:42788   54.116.87.122:443   users:(("kube-proxy",pid=2887,fd=12))
ESTAB 0      0       192.168.3.96:38512   54.116.87.122:443   users:(("kubelet",pid=2232,fd=18))
```

결과를 정리하면 다음과 같다.

| 노드 | 프로세스 | Local (노드) | Peer (API 서버) |
| --- | --- | --- | --- |
| node1 | kube-proxy | 192.168.2.21:**43312** | **43.201.196.244**:443 |
| node1 | aws-k8s-agent | 192.168.2.21:**47296** | **54.116.87.122**:443 |
| node1 | kubelet | 192.168.2.21:**43580** | **54.116.87.122**:443 |
| node2 | aws-k8s-agent | 192.168.3.96:**38580** | **54.116.87.122**:443 |
| node2 | kube-proxy | 192.168.3.96:**42788** | **54.116.87.122**:443 |
| node2 | kubelet | 192.168.3.96:**38512** | **54.116.87.122**:443 |

주목해서 봐야 할 점은 다음과 같다.

- **Peer Address:443** — 상대방 포트가 443이다. 온프레미스라면 6443이 보이겠지만, EKS에서는 NLB가 443으로 리스닝하므로 443이 나온다. `dig`으로 확인한 NLB 공인 IP(`43.201.196.244`, `54.116.87.122`)와 정확히 일치한다.
- **Local Address:3xxxx~4xxxx** — 클라이언트 측 Ephemeral Port(임시 포트, 32768~60999 범위). OS 커널이 랜덤으로 배정한 것이다.
- **세 프로세스 모두 API 서버와 연결** — kubelet(파드 스케줄링, 노드 상태 보고), kube-proxy(Service/iptables 규칙 갱신), aws-k8s-agent(VPC CNI — ENI 관리, IP 할당 정보를 API 서버에 업데이트) 모두 API 서버를 watch하며 연결을 유지한다.
- **DNS 레벨 로드밸런싱 실증** — node1의 kube-proxy는 `43.201.196.244`에, kubelet은 `54.116.87.122`에 연결되어 있다. 같은 노드의 프로세스인데 서로 다른 NLB IP에 연결된 것은, 각 프로세스가 독립적으로 DNS resolve를 수행한 결과다.

## API 서버 → kubelet (kubectl exec)

이번에는 반대 방향을 확인한다. `kubectl exec`으로 파드에 접속하면, API 서버가 kubelet의 **10250 포트**로 연결을 맺는다.

여기서 kubelet이 **서버** 역할을 하는 이유는 Kubernetes 아키텍처에서 비롯된다.

- **전제**: API 서버는 컨트롤 플레인에 있고, 컨테이너 런타임(containerd)은 각 워커 노드에서 로컬로 돌고 있다.
- **제약**: API 서버가 직접 컨테이너를 제어할 수 없다. containerd에 접근할 수 있는 것은 해당 노드의 kubelet뿐이다.
- **필요**: 컨테이너 관련 작업(`exec`, `logs`, `attach`, `port-forward`)을 하려면, API 서버가 kubelet에게 요청해야 한다.

그래서 kubelet은 단순한 에이전트가 아니라, **10250 포트에서 HTTPS 서버를 돌리며** 컨테이너 관련 API 엔드포인트(`/exec`, `/logs`, `/attach`, `/portForward`)를 제공한다. API 서버가 이 엔드포인트들을 **클라이언트로서** 호출하는 것이다.

![public-public-kubectl-exec-flow]({{site.url}}/assets/images/public-public-kubectl-exec-flow.png){: .align-center}

<center><sup><code>kubectl exec</code>의 전체 흐름 — 사용자 → kubectl → API 서버까지는 공인 경로(NLB), API 서버 → kubelet은 EKS Owned ENI를 통한 사설 경로, kubelet → containerd는 loopback</sup></center>

```bash
# 파드에 bash 접속 (node2에 있는 파드)
kubectl exec -it -n kube-system deploy/kube-ops-view -- bash
```

접속을 유지한 상태에서 `ss -tnp`를 다시 확인하면, node2에 새로운 연결이 추가되어 있다.

```
>> node my-eks-node2 <<
ESTAB  192.168.3.96:38580          54.116.87.122:443   users:(("aws-k8s-agent"...))
ESTAB  192.168.3.96:42788          54.116.87.122:443   users:(("kube-proxy"...))
ESTAB  192.168.3.96:38512          54.116.87.122:443   users:(("kubelet"...))
ESTAB      127.0.0.1:43055              127.0.0.1:40534 users:(("containerd"...))  ← 새로 추가
ESTAB      127.0.0.1:40534              127.0.0.1:43055 users:(("kubelet"...))     ← 새로 추가
ESTAB  [::ffff:192.168.3.96]:10250 [::ffff:192.168.1.227]:56574 users:(("kubelet"...))  ← 새로 추가
```

새로 추가된 연결 3개를 분석한다.

**API 서버 → kubelet (10250)**

```
ESTAB [::ffff:192.168.3.96]:10250 [::ffff:192.168.1.227]:56574 users:(("kubelet",pid=2232,fd=12))
```

- **Local 192.168.3.96:10250** — 이 노드의 kubelet이 **서버**로서 10250 포트에서 대기 중. 포트 번호가 잘 알려진 서비스 포트(10250)이므로 이쪽이 서버다.
- **Peer 192.168.1.227:56574** — 상대방은 [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %})의 사설 IP(`192.168.1.227`)다. 이 IP는 콘솔에서 확인한 EKS Owned ENI의 IP와 정확히 일치한다. API 서버가 EKS Owned ENI를 통해 **사설 경로로 kubelet에 연결**해 온 것이다.
- **`[::ffff:]` 표기** — kubelet이 IPv6 dual-stack 소켓으로 listen하고 있어서 IPv4 연결이 IPv4-mapped IPv6 주소로 표시된다. 실제 통신은 IPv4다.

> `kubectl exec`의 전체 흐름: 사용자 → kubectl → NLB → **API 서버** → etcd에서 파드 위치 조회 → **EKS Owned ENI → kubelet:10250** → containerd → 컨테이너 shell 연결

**kubelet ↔ containerd (loopback)**

```
ESTAB 127.0.0.1:43055  127.0.0.1:40534  containerd
ESTAB 127.0.0.1:40534  127.0.0.1:43055  kubelet
```

kubelet이 로컬의 containerd에게 CRI(Container Runtime Interface) 요청을 보내는 연결이다. 둘 다 `127.0.0.1`(loopback)이므로 같은 노드 안에서의 통신이다. 하나의 TCP 연결인데 클라이언트 소켓과 서버 소켓이 모두 같은 노드에 있어서 `ss`에 2줄로 표시된다.

## 핵심 발견: 노드 프로세스 vs Pod의 경로 차이

`kubernetes` Service의 Endpoints를 확인하면, 앞서 식별한 EKS Owned ENI의 IP가 그대로 등록되어 있다.

```bash
kubectl get endpoints kubernetes
```

```
NAME         ENDPOINTS                            AGE
kubernetes   192.168.1.227:443,192.168.3.82:443   6d18h
```

`192.168.1.227`과 `192.168.3.82`는 [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}#콘솔에서-eks-owned-eni-식별)에서 콘솔로 확인한 EKS Owned ENI의 IP와 정확히 일치한다.

이것이 중요한 이유는, **Public-Public 구성에서도 Pod는 사설 경로를 탄다**는 것을 의미하기 때문이다.

| 주체 | API 서버 주소를 어디서 가져오나 | 실제 경로 |
| --- | --- | --- |
| **kubelet, kube-proxy** (노드 프로세스) | kubeconfig의 `server:` 필드 → 공인 DNS → NLB IP | **공인 경로** (IGW 경유) |
| **Pod** (coredns 등 클러스터 내부) | `kubernetes` Service ClusterIP (`10.100.0.1`) → DNAT → Endpoints | **사설 경로** (ENI 직접) |

노드 프로세스(kubelet, kube-proxy)는 kubeconfig의 `server:` 필드에 적힌 **공인 DNS 엔드포인트**를 사용하므로 NLB 공인 IP로 나간다. 반면, Pod는 kubeconfig을 쓰지 않는다. Pod가 API 서버와 통신할 때는 in-cluster config(`/var/run/secrets/kubernetes.io/serviceaccount`)를 사용하는데, 이때 환경변수 `KUBERNETES_SERVICE_HOST=10.100.0.1`이 주입된다. 이것이 바로 `default/kubernetes` **Service의 ClusterIP**다. Pod는 이 ClusterIP로 요청하고, kube-proxy의 iptables DNAT가 Endpoints 목록(`192.168.1.227`, `192.168.3.82` — ENI 사설 IP) 중 하나로 변환하므로 **사설 경로**를 타게 된다.

### 패킷 캡쳐 분석

tcpdump로 패킷 흐름을 캡쳐하면 이 두 경로가 동시에 관찰된다.

```bash
sudo tcpdump -i any port 10250 or port 443 -nn -w capture.pcap
```

**패턴 1 — Pod → ClusterIP → ENI (사설 경로)**

```
enib3a22542c88 In   192.168.2.210:46154 → 10.100.0.1:443       ← Pod가 ClusterIP로 요청
ens5            Out  192.168.2.210:46154 → 192.168.1.227:443    ← iptables DNAT → ENI IP
ens5            In   192.168.1.227:443   → 192.168.2.210:46154  ← API 서버 응답
enib3a22542c88 Out  10.100.0.1:443      → 192.168.2.210:46154  ← 역DNAT → Pod에게 전달
```

`192.168.2.210`은 coredns Pod의 IP다. Pod가 `10.100.0.1`(kubernetes Service ClusterIP)로 요청하면, kube-proxy의 iptables 규칙이 목적지를 `192.168.1.227`(EKS Owned ENI)로 DNAT한다. 공인 인터넷을 거치지 않는 **VPC 내부 사설 경로**다.

**패턴 2 — 노드 프로세스 → NLB (공인 경로)**

```
ens5  Out  192.168.2.21:2120   → 54.116.87.122:443    ← 노드 → NLB 공인 IP
ens5  In   54.116.87.122:443   → 192.168.2.21:2120    ← NLB → 노드 응답
```

kubelet, kube-proxy 등 노드 프로세스는 kubeconfig의 공인 DNS를 통해 NLB 공인 IP로 연결한다.

**같은 Public-Public 모드인데 경로가 다른** 근본 원인은, API 서버에 도달하는 주소가 다르기 때문이다. 노드 프로세스는 kubeconfig의 공인 엔드포인트를, Pod는 kubernetes Service의 ClusterIP를 사용하고, 그 ClusterIP의 Endpoints가 ENI 사설 IP로 설정되어 있다.

<br>


# 통신 경로 검증: Public 엔드포인트 (curl)

`publicAccessCidrs: 0.0.0.0/0`이 실제로 무엇을 의미하는지 curl로 직접 확인해 보자. "아무나 호출 가능하다"는 것이 어느 수준까지인지를 보는 것이다.

## 인증 없이 접근

```bash
curl -sk https://$APIDNS/version
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "Unauthorized",
  "reason": "Unauthorized",
  "code": 401
}
```

인증 정보 없이 요청하면 **401 Unauthorized**가 반환된다. 하지만 핵심은 **응답이 온다**는 것이다. TCP 연결이 성립되고 TLS handshake가 완료된 후 API 서버가 응답한 것이므로, 엔드포인트 자체는 인터넷에 노출되어 있다.

> **참고**: 이전 EKS 버전에서는 `/version` 엔드포인트가 인증 없이도 Kubernetes 버전 정보를 반환했다. 공격자가 알려진 CVE를 타겟팅할 수 있는 보안 위험이었는데, 현재는 인증되지 않은 요청에 401을 반환하도록 변경되었다.
>
> ![eks-version-endpoint-exposed]({{site.url}}/assets/images/eks-version-endpoint-exposed.png){: .align-center width="600"}
>
> <center><sup>이전 동작 — 다른 EKS 클러스터(v1.31.5)에서 <code>/version</code> 접근 시 버전 정보가 그대로 노출됨</sup></center>
>
> ![eks-version-endpoint-blocked]({{site.url}}/assets/images/eks-version-endpoint-blocked.png){: .align-center width="600"}
>
> <center><sup>현재 동작 — 인증 없이 접근하면 401 Unauthorized 반환</sup></center>

## IAM 토큰으로 직접 API 호출

인증 정보를 포함하면 공인 엔드포인트로 API를 정상적으로 호출할 수 있다.

```bash
# IAM 토큰 발급
TOKEN=$(aws eks get-token --cluster-name myeks --region ap-northeast-2 --output json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['token'])")

# API 서버 직접 호출
curl -s \
  --cacert <(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d) \
  -H "Authorization: Bearer $TOKEN" \
  "https://$APIDNS/api/v1/namespaces/default/pods"
```

```json
{
  "kind": "PodList",
  "apiVersion": "v1",
  "metadata": { "resourceVersion": "1588655" },
  "items": [
    {
      "metadata": {
        "name": "mario-868699b58f-62v5m",
        "namespace": "default",
        "labels": { "app": "mario" }
      }
    }
  ]
}
```

kubectl 없이 curl만으로 파드 목록을 가져올 수 있다. 공인 엔드포인트에 인증 토큰만 있으면 어디서든 클러스터를 제어할 수 있다는 뜻이다.

## 공인 IP로 직접 접근

DNS 이름 대신 `dig`으로 확인한 **공인 IP로 직접** 접근하면 어떻게 될까?

### 케이스 1 — TLS 검증 있음 (실패)

```bash
curl -v --cacert <(ca.crt) \
  -H "Authorization: Bearer $TOKEN" \
  "https://43.201.196.244/api/v1/namespaces/default/pods"
```

```
* Server certificate:
*  subject: CN=kube-apiserver
*  subjectAltName does not match ipv4 address 43.201.196.244
* SSL: no alternative certificate subject name matches target host name
curl: (60) SSL: no alternative certificate subject name matches ...
```

TLS handshake는 성공했지만, API 서버의 TLS 인증서 SAN에 NLB의 raw IP가 포함되어 있지 않아 검증 실패한다. 인증서는 `*.eks.amazonaws.com` 도메인 기준으로 발급된 것이기 때문이다. 다만, **TCP 연결 자체가 막힌 것은 아니다**.

### 케이스 2 — TLS 검증 무시 `-k` (성공)

```bash
curl -sk \
  -H "Authorization: Bearer $TOKEN" \
  "https://43.201.196.244/api/v1/namespaces/default/pods"
```

```
kind: PodList
  pod: mario-868699b58f-62v5m  → Running
```

`-k` 옵션으로 TLS 검증을 건너뛰면 **정상 응답**이 온다. IP를 알기만 하면, TLS 검증을 무시하고 API 서버에 도달할 수 있다는 뜻이다.

### 케이스 3 — `--resolve`로 DNS 우회 (성공)

```bash
curl -s \
  --cacert <(ca.crt) \
  --resolve "$APIDNS:443:43.201.196.244" \
  -H "Authorization: Bearer $TOKEN" \
  "https://$APIDNS/api/v1/namespaces/default/pods"
```

`--resolve`는 DNS를 우회하되 호스트명은 도메인으로 인식하게 한다. TLS 인증서의 SAN이 도메인과 일치하므로 검증도 통과하고, 응답도 정상이다. 두 IP 모두 동일하게 200 OK — 같은 NLB 뒤의 API 서버로 로드밸런싱되고 있음을 확인할 수 있다.

## 접근 방식별 비교

| 계층 | DNS 이름으로 접속 | 공인 IP로 직접 접속 |
| --- | --- | --- |
| **네트워크 (TCP)** | 도달 가능 | 도달 가능 |
| **TLS 인증서** | 통과 | SAN 불일치로 실패 (`-k`로 무시 가능) |
| **K8s 인증 (AuthN)** | 토큰 없으면 401 | 토큰 없으면 401 |

순수하게 네트워크 관점에서 보면, **DNS 이름이든 공인 IP든 NLB의 443 포트가 열려 있으니 누구나 TCP 연결 자체는 가능**하다. 차이는 TLS 검증 단계뿐이고, 이것도 `-k`로 우회 가능하다. 보안 관점에서 노출 수준은 사실상 같다.

## 보안 리스크의 실체

이를 통해 확인할 수 있는 Public Endpoint의 보안 리스크는 꽤나 구체적이다.

- **인증(토큰)이 마지막 방어선**: 네트워크 레벨에서는 전 세계 어디서든 API 서버에 도달할 수 있다. 인증만이 유일한 차단 계층이다.
- **brute force 공격 대상**: 엔드포인트가 인터넷에 노출되어 있으므로, 토큰 추측 공격이 가능하다.
- **DoS 공격 대상**: 인증 없이도 TCP 연결과 TLS handshake까지는 진행되므로, 대량 요청으로 리소스를 소모시킬 수 있다.

```bash
# 인증 없이도 연결은 됨 → DoS 가능
curl -sk https://$APIDNS
curl -sk https://$APIDNS/version
```

이것이 `publicAccessCidrs: 0.0.0.0/0`을 프로덕션에서 반드시 제한해야 하는 이유다.

<br>


# Public-Public 구성의 비효율성: 레이턴시

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
| API 서버 주소 | 컨트롤 플레인 노드 IP (`192.168.10.100:6443`) | EKS 엔드포인트 (NLB 공인 IP) |
| 레이턴시 | 내부 네트워크라 빠름 (수~수십 ms) | 공인 경로라 상대적으로 느림 (수백 ms) |

876ms의 레이턴시에는 STS 토큰 발급 시간도 포함되어 있지만, 근본적으로 **kubectl → 인터넷 → NLB → API 서버**라는 공인 경로를 거치기 때문에 온프레미스보다 느릴 수밖에 없다.

<br>


# 정리

Public-Public 구성의 엔드포인트 특성을 정리한다.

| 항목 | Public-Public |
| --- | --- |
| **kubectl 접근 경로** | 로컬 PC → 인터넷 → NLB(공인 IP) → API 서버 |
| **워커 노드 접근 경로** | EC2 (퍼블릭 서브넷) → IGW → 인터넷 → NLB(공인 IP) → API 서버 |
| **API 서버 → 워커 노드** | API 서버 → [EKS Owned ENI]({% post_url 2026-03-12-Kubernetes-EKS-01-01-06-EKS-Owned-ENI %}) → 워커 노드 (항상 사설 경로) |
| **NLB** | 클러스터당 전용 NLB 1개. AZ별 고정 공인 IP |
| **로드밸런싱** | 2단계: DNS 레벨(클라이언트가 IP 선택) → NLB 레벨(API 서버 인스턴스로 분산) |
| **dig 결과** | NLB 공인 IP 2개 (A 레코드 2개) |
| **레이턴시** | ~876ms (공인 인터넷 경유) |
| **Pod 접근 경로** | ClusterIP(10.100.0.1) → DNAT → ENI 사설 IP (Public 모드에서도 사설 경로) |
| **보안** | 전 세계 노출 (`0.0.0.0/0`). DNS/IP 무관하게 TCP 도달 가능. 인증이 유일한 방어선 |

가장 간단한 구성이지만, 노드 프로세스가 공인 경로를 거치는 비효율과 보안 노출이 있다. 다만, Pod는 kubernetes Service Endpoints(ENI 사설 IP)를 통해 사설 경로를 타므로, 공인 경로의 영향을 받는 것은 kubelet/kube-proxy 등 노드 레벨 컴포넌트다. 이후 Public-Private 구성으로 전환하면 노드 프로세스도 VPC 내부 프라이빗 경로(EKS Owned ENI)를 사용하게 되어 레이턴시와 보안이 모두 개선된다.

<br>
