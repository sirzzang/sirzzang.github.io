---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 0. Overview"
excerpt: "Kubespray가 제공하고자 하는 것과 자동화 도구의 양면성을 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# 들어가며

[Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})에서는 클러스터의 모든 구성 요소를 손으로 설치했다. [kubeadm]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %})은 인증서 생성, etcd 구성, 컨트롤 플레인 배포 등 핵심 부트스트래핑 작업을 자동화해주었다. 이번에는 **Kubespray**로 전체 과정을 자동화해 본다.

<br>

# Kubespray란

## 공식 문서 살펴보기

[Kubespray GitHub](https://github.com/kubernetes-sigs/kubespray)를 보면, Kubespray를 다음과 같이 소개한다.

> Deploy a Production Ready Kubernetes Cluster

**프로덕션 준비된 쿠버네티스 클러스터를 배포**한다. 단순히 클러스터를 설치하는 것이 아니라, 운영 환경에서 바로 사용할 수 있는 수준의 클러스터를 구성해준다는 의미다.


## 정의

Kubespray는 **Ansible 기반으로 쿠버네티스 클러스터를 자동으로 설치·업그레이드·관리하기 위한 오픈소스 배포 도구**다. Kubernetes [SIG(Special Interest Group)](https://github.com/kubernetes/community/blob/master/sig-cluster-lifecycle/README.md) 중 **Cluster Lifecycle** 그룹에서 관리하는 공식 프로젝트다.

[공식 문서](https://kubernetes.io/docs/setup/production-environment/tools/)에서는 다음과 같이 설명한다:

> Kubespray is a composition of Ansible playbooks, inventory, provisioning tools, and domain knowledge for generic OS/Kubernetes clusters configuration management tasks.

Ansible 플레이북, 인벤토리, 프로비저닝 도구, 그리고 OS/Kubernetes 클러스터 설정 관리에 대한 도메인 지식의 결합이라고 한다. 여기서 핵심은 **"domain knowledge"**다. 단순히 명령어를 자동화하는 것이 아니라, 운영 환경에서 검증된 Best Practice가 녹아 있다.

## 제공하고자 하는 것

kubeadm을 사용하더라도 여전히 수동으로 해야 하는 작업들이 있다:

- 머신 프로비저닝
- OS 사전 설정 (시간 동기화, SELinux, Swap, 커널 파라미터 등)
- containerd, kubelet 설치
- CNI 플러그인 설치
- HA 구성을 위한 로드밸런서 설정

Kubespray는 이러한 작업들까지 자동화해준다. Ansible 기반으로 동작하며, kubeadm을 내부적으로 사용하면서 그 위에 더 높은 수준의 자동화를 제공한다.

<br>

# 자동화의 양면성

자동화 수준이 높아지면서 점점 편해지는 것은 맞다. 하지만 그만큼 **경계해야 할 것**도 있다.

## 편해지는 것

Kubespray를 사용하면 `ansible-playbook cluster.yml` 한 줄로 클러스터가 구성된다. 손설치에서 수십 개의 명령어를 입력하고, kubeadm에서도 여러 노드를 돌아다니며 작업했던 것에 비하면 확실히 편하다.

- OS 사전 설정 (NTP, 커널 파라미터, Swap 등) → 자동
- containerd, kubelet 설치 → 자동
- 인증서 생성, etcd 구성, 컨트롤 플레인 배포 → 자동
- CNI 플러그인 설치 → 자동
- HA 로드밸런서 구성 → 자동

엔터 한 번 치면 수십 분 뒤에 프로덕션 레디 클러스터가 완성된다.

## 알아야 할 것

자동화 수준이 높아질수록, 그 안에서 **무엇이 어떻게 동작하는지** 알아야 할 것도 많아진다.

Kubespray는 수십 개의 Ansible Role로 구성되어 있다. 각 Role은 수십 개의 Task로 이루어져 있고, 수백 개의 변수로 동작이 제어된다.

```bash
kubespray/
├── roles/
│   ├── bootstrap-os/        # OS 기본 설정
│   ├── container-engine/    # containerd 설치
│   ├── etcd/                # etcd 클러스터 구성
│   ├── kubernetes/          # Kubernetes 컴포넌트
│   └── network_plugin/      # CNI 플러그인
└── inventory/
    └── sample/group_vars/   # 수백 개의 변수
```

이 구조를 모르면 **블랙박스**가 된다.

<br>

# 블랙박스의 위험

## 운영 중 문제가 생기면

클러스터가 잘 돌아갈 때는 괜찮다. 문제는 운영 중 이슈가 발생했을 때다.

- Pod가 스케줄링되지 않는다 → 어디를 봐야 하지?
- 노드 간 통신이 안 된다 → CNI 설정이 어디에 있지?
- 인증서가 만료되었다 → 어떻게 갱신하지?

직접 설치했다면 어디서 무엇을 설정했는지 알고 있다. 하지만 자동화 도구로 "엔터만 치고" 설치했다면, 문제의 원인을 찾는 것조차 어렵다.

## 업그레이드가 어려워질 수 있다

Kubernetes는 빠르게 발전한다. 3개월마다 새 버전이 나오고, 보안 패치도 자주 나온다. 클러스터를 운영하려면 주기적인 업그레이드가 필수다.

Kubespray는 업그레이드 기능(`upgrade-cluster.yml`)을 제공한다. 하지만 이것도 결국 Ansible Playbook이다. 무엇이 어떻게 바뀌는지 모르면, 아래와 같은 이유로 업그레이드가 어려워질 수 있다:

- 업그레이드 중 실패했을 때 복구가 어려워질 수 있음
- 버전 호환성 문제에 대응하기 어려워질 수 있음
- 결국 업그레이드를 두려워하게 될 수 있음

업그레이드가 어려워지면 자동화 도구의 이점을 충분히 누리지 못할 수 있다.

## 버전이 올라가면 또 알아야 한다

Kubespray도 계속 발전한다. 새 버전이 나올 때마다 아래와 같은 일이 발생할 수 있다:

- 새로운 Role이 추가됨
- 기존 변수 이름이 바뀜
- 기본값이 달라짐

이전 버전에서 알던 것이 새 버전에서는 다를 수 있다. **지속적인 학습**이 필요하다.

<br>

# 돌이켜 보며

## "일단 돌아가게만"의 유혹

개발자로서 종종 "일단 돌아가게만" 만들 때가 있다. 마감에 쫓기거나, 당장 결과가 필요할 때. 작동은 하는데 왜 작동하는지 모르는 상태.

자동화 도구를 사용할 때도 마찬가지다. `ansible-playbook cluster.yml` 치면 클러스터가 뜨니까, 일단 그렇게 쓴다. 그러면, 작동은 하는데 내부에서 무슨 일이 일어나는지 모르게 된다.

## 과거로부터 배운 점

[Ansible 글]({% post_url 2026-01-12-Kubernetes-Ansible-00 %}#마무리)에서도 언급했지만, 예전에 회사에서 Ansible을 사용한 경험이 있다. 그때는 Ansible을 **잘 모르고 사용**했다. 플레이북이 어렵게 느껴졌고, 왜 이렇게 동작하는지 이해하지 못한 채 복사-붙여넣기로 작업했다. 작동은 했지만, 문제가 생겼을 때 대응하기 어려웠다. 

돌이켜보면, 도구를 제대로 이해하지 않고 사용하면 **진정한 의미에서 사용하는 것이 아니다**. 도구가 해주는 것만 할 수 있고, 도구가 안 해주면 아무것도 못 한다.

<br>

# 결과

자동화 도구는 양날의 검이다. 잘 쓰면 생산성이 올라가지만, 소홀히 하면 블랙박스가 되어 오히려 발목을 잡을 수 있다.

이번 시리즈에서는 Kubespray를 "그냥 엔터 치면 되는 도구"로 쓰지 않으려고 한다. 단순히 "클러스터 띄우기"가 아니라, **Kubespray의 구조를 분석하는 것**에 초점을 맞춘다. Playbook 구조, Role 분석, 변수 파일, Task 흐름 등을 살펴보면서, 시간이 걸리더라도 어떤 경우에 Kubespray를 이용해야 하는지, 운영할 때 어떤 부분을 알고 있어야 하는지 알아 가고자 한다.

<br>

# 참고

- [쿠버네티스 프로비저닝 툴과의 만남부터 헤어짐까지](https://tech.kakao.com/posts/570): 카카오에서 프로비저닝 도구의 한계를 분석하고, 직접 핸드메이드 클러스터 프로비저닝 도구를 만든 사례
