---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 0. Overview"
excerpt: "Kubernetes The Hard Way를 따라 자동화 도구 없이 쿠버네티스 클러스터를 손으로 직접 구성해 보자."
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

[Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way/tree/master/units)를 따라 직접 클러스터를 구성해 보자.

일반적으로 쿠버네티스 클러스터는 kubeadm, kubespray, Rancher 등 자동화 도구를 사용하여 설치한다. 하지만 이번 실습에서는 자동화 도구 없이 **손으로 직접 설치**하며 클러스터의 각 구성 요소를 이해하는 것을 목표로 한다. 

<br>

> *참고*: 알아 두면 쓸모 있는 지식들
> 
> - [기본 암호학 지식]({% post_url 2026-01-04-CS-Cryptography-01 %}): 특히,
>   - [비대칭키 암호화]({% post_url 2026-01-04-CS-Cryptography-04 %})와 TLS/mTLS
>   - X.509 인증서
> - kind: Docker 컨테이너를 노드로 사용하여 로컬에서 Kubernetes 클러스터를 테스트할 수 있게 해주는 도구
> - minikube: 로컬에서 단일 노드 Kubernetes 클러스터를 실행할 수 있게 해주는 도구
> - virtualbox: 가상화 도구
> - vagrant: 가상 머신 환경을 구성하고 관리할 수 있게 해주는 도구

<br>

# 쿠버네티스 클러스터 손설치

## Kubernetes The Hard Way란?

Kubernetes The Hard Way는 말 그대로 **쿠버네티스 클러스터를 어렵게(수동으로) 세팅**하는 가이드이다. kubeadm, kubespray 같은 자동화 도구 없이 클러스터를 구성하면서 각 구성 요소를 직접 이해하는 것을 목표로 한다.

레포 원작자(Kelsey Hightower)의 설명에 따르면, 자동화된 방법을 원하는 사람을 위한 가이드가 아니다. **학습을 위해 긴 길을 택하여 쿠버네티스 클러스터를 부트스트래핑하는 데 필요한 각 태스크를 이해**하는 것을 목적으로 한다.

> This tutorial walks you through setting up Kubernetes the hard way. This guide is not for someone looking for a fully automated tool to bring up a Kubernetes cluster. Kubernetes The Hard Way is optimized for learning, which means taking the long route to ensure you understand each task required to bootstrap a Kubernetes cluster.

<br>

## 손설치를 하는 이유

AI가 나보다 프로그래밍도 더 잘 하는 세상에, 왜 굳이 손 설치를 하느냐면, 그만큼 얻는 것이 많기 때문이다.

- **기초 이해**: 근간이 되는 수동 설치 과정을 이해하면 클러스터 노드별 구성 요소와 각 구성 요소의 셋업 과정에 대해 알 수 있다. 
- **운영 환경 대응**: 운영 환경에서 발생하는 복잡한 이슈를 디버깅할 때 도움이 된다.
- **자동화 도구 이해**: kubeadm(수동 작업 자동화), kubespray(더 높은 수준의 자동화) 등이 내부적으로 무엇을 하는지 이해할 수 있다.

<br>

## 손설치의 범위

무엇보다 개인적으로는 쿠버네티스 클러스터 구성뿐만 아니라, 인프라 전반에 대한 이해를 넓힐 수 있어서 좋은 학습 경험이었다. 

"손설치"가 비단 쿠버네티스 클러스터 구성의 범위를 넘어, 다음과 같은 작업까지 포함하기 때문이다: 

- 가상 머신(VM) 세팅 및 구성
- 컴퓨트 리소스 프로비저닝
- 네트워크 설정
- 보안 설정 (인증서, 키 관리 등)

<br>

"Kubernetes the Hard Way"를 직접 경험해보면 클라우드 프로바이더가 얼마나 많은 작업을 자동화해주는지, 그리고 온프레미스 환경에서 인프라팀이 얼마나 많은 수동 작업을 수행해야 하는지 체감할 수 있다. Jumpbox 구성, 리소스 할당, 네트워크 설정 등 모든 것을 직접 구성해야 하기 때문이다.

<br>

# 실습 환경 및 버전

본 실습은 GitHub의 [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way/tree/master/units) 레포지토리 가이드를 따라 진행한다.

- **가이드 기준 버전**: Kubernetes 1.32.3 (레포가 9개월 전에 업데이트됨)
- **현재 최신 버전**: Kubernetes 1.35
- **실습 버전**: 가이드에 맞춰 Kubernetes 1.32 버전으로 설치
- **참고 문서**: [Kubernetes 1.32 공식 문서](https://v1-32.docs.kubernetes.io/docs/home)

<br>

## 실습 환경 요구사항

실습 환경에 대한 상세한 설명은 [다음 글]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %})에서 다루겠지만, 기본적으로 다음과 같은 환경이 필요하다:

- **최소 사양**: 최소 8GB 이상의 RAM
- **가상 머신**: 총 4대의 가상 머신 필요
  - Jumpbox: 관리용 호스트 (2 CPU, 1.5GB RAM)
  - Server: Kubernetes Control Plane (2 CPU, 2GB RAM)
  - Node-0, Node-1: Kubernetes Worker Nodes (각각 2 CPU, 2GB RAM)
- **개인 실습 환경**: Apple M1 Pro Macbook (32GB RAM)

<br>

# 구성도


실습이 끝나면 완전한 쿠버네티스 클러스터를 구성할 수 있을 것이다. 한 땀 한 땀 직접 만든 클러스터에 대한 성취감과 함께, 이 모든 과정을 자동화해주는 kubeadm, 더 높은 수준의 자동화를 제공하는 kubespray, 그리고 경량화된 k3s 같은 도구들의 가치를 새삼 느낄 수 있다.

![kubernetes-the-hard-way-cluster-structure-0]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-0.png)

<br>

특기할 만한 구성 요소를 설명하면 다음과 같다.
- **Jumpbox**: 클러스터 외부에서 클러스터 내부 노드들에 접근하기 위한 베스천 호스트(Bastion Host) 역할을 한다. 관리자가 클러스터 내부의 서버들에 SSH 접속하거나 파일을 전송할 때 사용한다.
- **Server(컨트롤 플레인)**: 클러스터의 두뇌 역할을 하는 컨트롤 플레인(Control Plane) 노드이다. 클러스터 전체를 관리하고 조율하는 핵심 컴포넌트들이 설치된다.
- **Node-0, Node-1(워커 노드)**: 실제 워크로드(Pod)가 실행되는 워커 노드(Worker Node)이다. 컨트롤 플레인의 지시에 따라 컨테이너를 실행하고 관리한다.
- **etcd**: Kubernetes 클러스터의 모든 상태 정보를 저장하는 분산 키-값 저장소이다. 원래는 보안을 위해 HTTPS 통신을 해야 하지만, 이 가이드에서는 학습 목적으로 HTTP 통신을 사용할 수도 있다.

<br>

## 각 VM별 설치 컴포넌트

Kubernetes 클러스터는 [여러 컴포넌트](https://v1-32.docs.kubernetes.io/docs/concepts/overview/components/)로 구성된다. 실습을 진행하면서 각 VM에 다음과 같은 컴포넌트들을 설치하게 된다.

### Server: 컨트롤 플레인
- **kube-apiserver**: 쿠버네티스 API를 노출하는 컴포넌트로, 모든 요청의 진입점 역할을 한다.
- **kube-controller-manager**: 컨트롤러 프로세스를 실행하며, 클러스터의 상태를 원하는 상태로 유지한다.
- **kube-scheduler**: 새로 생성된 Pod를 어떤 노드에 배치할지 결정한다.
- **etcd**: 클러스터의 모든 데이터를 저장하는 분산 키-값 저장소이다.

### Node-0, Node-1: 워커 노드
- **kubelet**: 각 노드에서 실행되며, Pod 내 컨테이너가 실행되도록 관리한다.
- **kube-proxy**: 네트워크 규칙을 관리하여 Pod로의 네트워크 통신을 가능하게 한다.
- **containerd**: 컨테이너 런타임으로, 실제 컨테이너를 실행하고 관리한다.



<br>

## 레포지토리 클론

실습을 시작하기 전에 [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) 레포지토리를 클론한다.

```bash
# (host) $
git clone https://github.com/kelseyhightower/kubernetes-the-hard-way.git
cd kubernetes-the-hard-way
```

<br>

## 레포지토리 구조

레포지토리에는 다음과 같은 파일과 디렉토리가 포함되어 있다:

```bash
# (jumpbox) #
tree -L 1
```

****
```
kubernetes-the-hard-way/
├── configs/              # 설정 파일들
├── docs/                 # 문서 (실습 가이드)
├── units/                # 실습 단위별 가이드
├── ca.conf               # CA(인증 기관) 설정 파일
├── downloads-amd64.txt   # AMD64 아키텍처용 다운로드 링크
└── downloads-arm64.txt   # ARM64 아키텍처용 다운로드 링크
```

주요 디렉토리 설명:
- **`docs/`**: 실습을 단계별로 안내하는 마크다운 문서들
- **`configs/`**: Kubernetes 컴포넌트 설정 파일들
- **`units/`**: 실습 단위별 상세 가이드
- **`ca.conf`**: OpenSSL을 사용한 인증서 생성 시 필요한 CA 설정 파일

<br>

## 레포지토리 관련 참고사항

이 레포지토리는 약 9개월 전에 마지막으로 업데이트되었으며, 쿠버네티스 버전도 현재 최신 버전과 다르다. 또한 일부 오류가 있을 수 있다. 

하지만 오픈소스로 이렇게 귀중한 학습 자료를 제공해주는 것에 감사하며, 오류가 있다면 좋은 실전 학습 기회로 생각하고 직접 수정해보자. 기회가 된다면 Issue나 PR을 제출하는 것도 좋은 기여가 될 것이다.

다행히도 가시다님의 사전 검토를 통해 잘못된 부분이 미리 수정된 상태에서 학습할 수 있었다.
