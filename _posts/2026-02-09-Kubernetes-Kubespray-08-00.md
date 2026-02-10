---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: Overview"
excerpt: "폐쇄망(Air-Gapped) 환경에서 Kubernetes 클러스터를 배포하기 위해 무엇이 필요한지 전체 그림을 그려보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **폐쇄망(Air-Gapped) 환경에서 Kubernetes 클러스터를 배포하기 위해 무엇이 필요한지** 전체 그림을 그린다.

- **왜 폐쇄망인가**: 실무 환경에서 폐쇄망이 필요한 이유와 온라인/오프라인 환경의 차이
- **폐쇄망 환경 아키텍처**: 기업망 구조, 리소스 전달 흐름
- **기반 인프라 구성요소**: NTP, DNS, Network Gateway, 패키지 저장소, 컨테이너 레지스트리 등 — 각각이 없으면 어떤 문제가 발생하는지
- **시리즈 구성 안내**: 이후 글의 구조와 순서

<br>

# 왜 폐쇄망인가

## 기업 환경의 현실

실무에서 Kubernetes 클러스터가 배포되는 환경은 대부분 **인터넷과 격리된 폐쇄망(Air-Gapped Network)**이다.

| 환경 | 특징 |
|------|------|
| **금융권** | 망분리 의무화, 외부 통신 원칙적 차단 |
| **공공기관** | 보안 등급에 따른 네트워크 분리 |
| **제조/산업** | OT(Operational Technology) 망 격리 |
| **의료** | 환자 데이터 보호를 위한 네트워크 분리 |

온라인 환경에서는 `apt install`, `docker pull`, `helm install` 한 줄이면 되는 일이, 폐쇄망에서는 **모든 의존성을 사전에 확보하고 내부에서 서빙할 수 있는 인프라를 구축**해야 한다.

## 온라인 vs. 오프라인

온라인 환경에서 당연하게 사용하는 것들이 오프라인에서는 모두 **직접 구축해야 할 대상**이 된다.

| 온라인 환경 | 오프라인 환경 |
|---|---|
| 공인 NTP 서버(`time.google.com` 등)로 시간 동기화 | 내부 NTP 서버 구축 필요 |
| 공인 DNS(`8.8.8.8` 등)로 이름 해석 | 내부 DNS 서버 구축 필요 |
| 기본 OS 리포지토리에서 패키지 설치 | 로컬 YUM/APT Mirror 구축 필요 |
| Docker Hub, quay.io 등에서 이미지 Pull | Private Container Registry 구축 필요 |
| PyPI, Go Proxy 등에서 언어 패키지 설치 | Private 언어 패키지 Mirror 구축 필요 |
| ArtifactHub 등에서 Helm Chart 다운로드 | Helm Chart Repository 구축 필요 |

<br>

# 폐쇄망 환경 아키텍처

## 일반적인 기업망 구성

보안이 요구되는 기업 환경에서는 **외부 방화벽 — DMZ — 내부 방화벽 — 내부망**의 구조를 가진다. 내부망에서는 외부 인터넷 접속이 불가능하며, 필요 시 방화벽 정책 승인 후 **Bastion Server를 통해서만** 외부 리소스를 가져올 수 있다.

![폐쇄망 Kubernetes 클러스터 배포 아키텍처](/assets/images/kubespray-offline-architecture.png){: .align-center width="500"}

## 리소스 전달 흐름

폐쇄망에서의 리소스 전달은 크게 두 단계로 나뉜다.

1. **수집 단계**: 인터넷이 가능한 환경(Bastion 등)에서 필요한 리소스를 모두 다운로드
2. **배포 단계**: 수집한 리소스를 내부망으로 전달하고, 내부 서버에서 서빙

```
[인터넷] → [Bastion] → (물리 매체 or 승인된 경로) → [Admin Server] → [K8s Nodes]
                                                        ├── NTP 서빙
                                                        ├── DNS 서빙
                                                        ├── YUM/APT Mirror 서빙
                                                        ├── Container Registry 서빙
                                                        ├── PyPI Mirror 서빙
                                                        └── Helm Chart Repo 서빙
```

<br>

# 폐쇄망 기반 인프라 구성요소

Kubernetes 클러스터 배포 이전에 폐쇄망 내부에서 갖춰야 할 인프라 구성요소를 정리한다. 이 구성요소들은 **K8s에 한정되는 것이 아니라, 폐쇄망 내에서 어떤 서비스든 동작시키기 위해 필요한 기반**이다.

## 필수 구성요소

| 구성요소 | 역할 | 구현 예시 |
|----------|------|-----------|
| **NTP Server** | 노드 간 시간 동기화 | chrony |
| **DNS Server** | 내부 도메인 이름 해석 | CoreDNS, BIND, dnsmasq |
| **Network Gateway** | 내부망 라우팅, 필요 시 DMZ 통신 | iptables, NAT |
| **Local Package Repository** | OS 패키지(RPM/DEB) 저장소 | reposync + createrepo, apt-mirror |
| **Private Container Registry** | 컨테이너 이미지 저장소 | Docker Registry, Harbor |

## 선택 구성요소

| 구성요소 | 역할 | 구현 예시 |
|----------|------|-----------|
| **Helm Chart Repository** | Helm Chart 저장소 | ChartMuseum, OCI Registry([zot](https://github.com/project-zot/zot)) |
| **Private PyPI Mirror** | Python 패키지 저장소 | [devpi](https://github.com/devpi/devpi) |
| **Private Go Module Proxy** | Go 모듈 프록시 | Athens |
| **File Server** | 바이너리, 설정 파일 등 배포 | Nginx, Apache |

## 구성 요소별 필요성

이 구성요소들 중 하나라도 빠지면 어떻게 되는지 생각해 보면, 각각의 필요성이 명확해진다.

- **NTP**: 노드 간 시간이 어긋나면 인증서 유효성 검증이 실패하고, etcd 합의에 장애가 생기고, 로그 타임스탬프가 뒤섞여 디버깅이 불가능해진다.
- **DNS**: 이름 해석이 안 되면 내부 서비스(Registry, Repo 등)에 도메인으로 접근할 수 없고, 노드 간 호스트명 기반 통신도 불가능해진다.
- **Package Repository**: 패키지를 설치할 수 없으면 컨테이너 런타임(containerd), kubelet 등 K8s 구성에 필요한 기본 소프트웨어 자체를 설치할 수 없다.
- **Container Registry**: 이미지를 Pull할 수 없으면 Pod는 `ImagePullBackOff`로 영원히 멈추고, 시스템 컴포넌트(CoreDNS, kube-proxy)조차 배포할 수 없다.

결국, 폐쇄망에서 Kubernetes 클러스터를 배포한다는 것은 **클러스터 자체를 구축하기 전에, 그 클러스터가 동작할 수 있는 토양을 먼저 만드는 것**이다.

<br>

# 시리즈 구성

## 전체 구조

|  | 주제 | 내용 |
|----|------|------|
| **8.0** | Overview (본 글) | 폐쇄망 환경의 전체 그림과 필요한 구성요소 |
| **8.1** | The Hard Way | 폐쇄망 기반 인프라를 한 땀 한 땀 수동 구축 |
| **8.2** | kubespray-offline | kubespray-offline 프로젝트 분석 및 자동화된 오프라인 배포 |
| **8.3** | 오프라인 서비스 실습 | Helm, Registry 등을 활용한 오프라인 환경 서비스 운영 |

## 8.1 상세 구성

8.1 시리즈에서는 폐쇄망 내부에서 서비스를 동작시키기 위한 기반 인프라를 하나씩 직접 구축한다. 각 글에서는 해당 구성요소의 **목적**, **필요한 배경지식**, **실습**을 다룬다.

| 편 | 구성요소 | 비고 |
|----|----------|------|
| **8.1.0** | 실습 환경 배포 | Bastion + Admin 역할의 서버 구성, 오프라인 환경 시뮬레이션 |
| **8.1.1** | Network Gateway | 내부망 라우팅, 네트워크 핵심 개념 |
| **8.1.2** | NTP Server / Client | chrony를 이용한 시간 동기화 |
|  | DNS Server / Client | 내부 도메인 이름 해석 |
| **8.1.3** | Local YUM/DNF Repository | reposync + createrepo를 이용한 OS 패키지 Mirror |
| **8.1.4** | Private Container Registry | Docker Registry를 이용한 이미지 저장소 |
| **8.1.5** | Private PyPI Mirror | devpi를 이용한 Python 패키지 저장소 |
| **8.1.6** | Private Go Module Proxy *(도전 과제)* | Athens를 이용한 Go 모듈 프록시 |

> **참고**: 8.1.3 이후 구성요소(Container Registry, PyPI Mirror, Go Module Proxy)는 kubespray-offline(8.2)에서 자동화해주는 영역이다. 스터디에서도 수동 구축은 skip을 권장했지만, 원리를 이해하기 위해 직접 구축해 보았다.

8.1에서 수동으로 구축하는 과정을 거치면, 8.2에서 kubespray-offline이 **왜** 그렇게 자동화했는지를 깊이 이해할 수 있다. 자동화 도구가 해주는 일을 먼저 직접 경험하는 것은 [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})에서부터 이어온 이 스터디 시리즈의 전체 철학이기도 하다.

<!--8.2, 8.3 상세 구성 작성 -->

<br>

# 실습 환경 개요

| 역할 | 호스트 | 비고 |
|------|--------|------|
| Admin(Bastion) Server | admin | NTP, DNS, Package Repo, Registry 등 서빙 |
| K8s Control Plane | cp1 | - |
| K8s Worker | w1, w2 | - |

> **참고**: 실습에서는 편의상 Bastion과 Admin Server를 한 대로 구성한다. 실제 환경에서는 보안상 분리하는 것이 바람직하다. 실습 환경의 상세 구성은 [8.1.0 실습 환경 배포]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서 다룬다.

<br>

# 참고 자료

- [Kubespray - Offline Environment](https://kubespray.io/#/docs/offline-environment)
- [kubespray-offline GitHub](https://github.com/kubernetes-sigs/kubespray/tree/master/contrib/offline)

<br>

