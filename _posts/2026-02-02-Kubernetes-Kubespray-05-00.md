---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 5.0. HA 구성 - 개요"
excerpt: "Kubernetes Control Plane HA 구성의 3가지 패턴을 이해하고 Kubespray 설정 방법을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - HA
  - Load Balancer
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubernetes HA 개요**와 **API Server 접근 패턴**을 살펴본다.

- **Kubernetes HA 계층**: Control Plane, Workload, Network/Storage HA로 구성
- **API Server는 Active-Active**: 모든 인스턴스가 동시에 요청 처리, HA 구성 시 접근 패턴 설계 필요
- **3가지 접근 패턴**: Full Client-Side LB / Hybrid LB / Centralized LB
- **Kubespray 기본값**: Case 1 (Client-Side LB) - 외부 의존성 없이 자체 HA 구현

<br>

# 들어가며

[이전 글]({% post_url 2026-01-25-Kubernetes-Kubespray-04-02 %})까지 단일 Control Plane 노드로 클러스터를 구성했다. 하지만 프로덕션 환경에서는 **API Server 단일 장애점(SPOF)**을 제거해야 한다. Control Plane을 다중화하면 API Server 접근 방식에 대한 설계가 필요하다.

| 구성 요소 | 단일 Control Plane | HA Control Plane |
|-----------|-------------------|------------------|
| API Server 개수 | 1대 | 3대 (권장) |
| 장애 시 영향 | 전체 클러스터 중단 | 자동 failover |
| API 엔드포인트 | 1개 | 다중 엔드포인트 관리 필요 |

이번 글에서는 Kubernetes HA의 전체 구조를 살펴보고, **API Server 접근 패턴** 3가지를 비교한다. 이후 Kubespray에서 각 패턴을 어떻게 설정하는지 알아본다.

<br>

# Kubernetes HA

Kubernetes 클러스터의 고가용성(HA)은 여러 계층에서 고려해야 한다.

## HA 구성 요소

Kubernetes 클러스터의 고가용성은 크게 4가지 계층으로 나뉜다.

| 계층 | 구성 요소 | 세부 항목 |
|------|----------|----------|
| **1. Control Plane HA** | API Server HA | 접근 패턴 (Client-Side LB / External LB / Hybrid) ← **이 글에서 다룸** |
| | etcd HA | Topology (Stacked / External) |
| | Controller Manager / Scheduler HA | Leader Election (Active-Standby) |
| **2. Workload HA** | Pod 복제 | Deployment, StatefulSet |
| | 파드 중단 예산(PDB) | PodDisruptionBudget (PDB) |
| | 분산 배치 | Pod Anti-Affinity, Topology Spread Constraints |
| **3. Network HA** | Service | kube-proxy (iptables/ipvs) |
| | Ingress | Ingress Controller HA |
| | CNI | CNI Plugin HA |
| **4. Storage HA** | 분산 스토리지 | Ceph, Longhorn 등 |
| | CSI | CSI Driver HA |

## Control Plane HA 상세

Control Plane HA는 다시 여러 측면으로 나뉜다.

### 1. etcd HA - Topology

| Topology | 구성 | Kubespray 기본값 |
|----------|------|-----------------|
| **Stacked** | etcd가 Control Plane 노드에 함께 배치 | 기본값 |
| **External** | etcd를 별도 클러스터로 분리 | 별도 설정 필요 |

> 자세한 내용은 [1. Kubespray 소개](https://sirzzang.github.io/kubernetes/Kubernetes-Kubespray-01/#ha%EA%B3%A0%EA%B0%80%EC%9A%A9%EC%84%B1-%EA%B5%AC%EC%84%B1-%EC%A7%80%EC%9B%90) 참조

### 2. Controller Manager / Scheduler HA

Controller Manager와 Scheduler는 **Active-Standby** 방식으로 동작한다. HA 구성 시 여러 인스턴스 중 **1대만 Leader로 선출**되어 실제 작업을 수행하고, 나머지는 대기한다.

> **참고**: Leader Election에 사용되는 Lease 리소스에 대한 자세한 내용은 [kubeadm 클러스터 구성 - Lease]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#lease) 참조

```bash
# Leader 확인
kubectl get lease -n kube-system kube-controller-manager -o yaml
kubectl get lease -n kube-system kube-scheduler -o yaml
```

### 3. API Server HA

API Server는 **Active-Active** 방식으로 동작한다. 모든 인스턴스가 동시에 요청을 처리할 수 있다.

### 4. Control Plane 컴포넌트별 HA 비교

| 컴포넌트 | HA 방식 | 접근 설계 필요? |
|----------|---------|----------------|
| Controller Manager | Active-Standby | 불필요 (Leader가 처리) |
| Scheduler | Active-Standby | 불필요 (Leader가 처리) |
| **API Server** | **Active-Active** | **필요 (접근 패턴 설계 필요)** |

API Server는 Active-Active이므로 **어떤 인스턴스에 접근해도 정상 동작**한다. 하지만 문제가 있다:

- 클라이언트(kubectl, kubelet)는 보통 **하나의 endpoint**만 설정
- 그 endpoint가 장애 발생 시, **접근 불가**
- 따라서 **다중 API Server에 어떻게 접근할지** 설계가 필요

<br>

# Kubespray의 API Server HA 구성 패턴

Kubespray는 [HA endpoints for K8s](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/ha-mode.md) 문서에서 API Server 접근 방식을 설명한다. 핵심은 두 가지 변수의 조합이다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `loadbalancer_apiserver_localhost` | 각 노드에 로컬 프록시 배포 (localhost 접근) | `true` |
| `loadbalancer_apiserver` | External LB 주소 설정 | 미설정 |

이 두 변수의 조합에 따라 API Server 접근 패턴이 달라진다. 이해를 돕기 위해 다음과 같이 3가지 Case로 분류한다.

| 패턴 | Kubespray 설정 | 외부 접근 | 워커 노드 접근 |
|------|----------------|----------|---------------|
| **Case 1**: Full Client-Side LB | `localhost: true`, `apiserver: 미설정` | 직접 (첫 번째 CP IP) | localhost (로컬 프록시) |
| **Case 2**: Hybrid LB | `localhost: true`, `apiserver: 설정` | External LB | localhost (로컬 프록시) |
| **Case 3**: Centralized LB | `localhost: false`, `apiserver: 설정` | External LB | External LB |

> **참고**: Case 1/2/3 명칭은 공식 용어가 아니라, 이해를 돕기 위한 분류다.

## 패턴 분류 기준

- **Case 1 vs. Case 2**: 외부 → API Server 접근 시 External LB 사용 여부
- **Case 2 vs. Case 3**: 워커 노드 → API Server 접근 시 localhost proxy 사용 여부

<br>

## Case 1: Full Client-Side LB

**외부/워커 노드 모두 직접 3개 엔드포인트에 접근**한다.

![kubespray-ha-case1]({{site.url}}/assets/images/kubespray-ha-case1.png)

### 접근 원리

External LB 없이 클라이언트가 직접 여러 API Server에 접근한다.

| 항목 | 설명 |
|------|------|
| **워커 노드 → API** | 직접 접근 (3개 엔드포인트) |
| **외부 → API** | 직접 접근 (3개 엔드포인트) |
| **LB 장애 시 영향** | 없음 (LB 없음) |
| **External LB 필요** | 불필요 |
| **API 서버 추가/제거 시** | 모든 kubeconfig 수정 필요 |

#### 워커 노드 접근

워커 노드의 경우, Kubespray는 각 노드에 로컬 프록시를 생성한다 (기본: nginx, haproxy도 선택 가능). kubelet과 kube-proxy는 `localhost:6443`으로 접근하고, 로컬 프록시가 3개 API Server로 요청을 분산한다. API Server 1대 장애 시 자동으로 다른 서버로 failover한다.

```bash
# 워커 노드 kubelet
kubelet → localhost:6443 → 로컬 프록시 → CP1 (192.168.10.11:6443)
                                    → CP2 (192.168.10.12:6443)
                                    → CP3 (192.168.10.13:6443)
```

#### 외부 접근

외부 접근(kubectl, CI/CD)의 경우, kubeconfig에 여러 endpoint를 설정하거나 DNS Round-Robin 등 별도 구성이 필요하다.

```yaml
# 외부 kubeconfig 예시 (수동 failover)
clusters:
- cluster:
    server: https://192.168.10.11:6443  # 평소 사용
  name: cluster
# 장애 시 다른 endpoint로 수동 변경 필요
```

<br>

## Case 2: Hybrid LB

**외부는 External LB, 워커는 Client-Side LB**를 사용하는 하이브리드 구성이다.

![kubespray-ha-case2]({{site.url}}/assets/images/kubespray-ha-case2.png)

### 접근 원리

워커 노드는 Case 1과 동일하게 로컬 프록시를 통해 3개 API Server에 접근한다. 외부 접근(kubectl, CI/CD)은 External LB(HAProxy 등)를 경유하여 단일 VIP로 접근한다. 

Case 1의 외부 접근 문제(수동 failover)를 해결하면서, 워커 노드는 LB 장애에 영향받지 않는다. 실무에서 가장 많이 사용되는 구성이다.

| 항목 | 설명 |
|------|------|
| **워커 노드 → API** | 직접 접근 (3개 엔드포인트) |
| **외부 → API** | External LB 경유 (1개 VIP) |
| **LB 장애 시 영향** | 외부 접근만 영향, 워커 노드는 정상 |
| **External LB 필요** | 필요 (외부용) |
| **API 서버 추가/제거 시** | 워커 kubeconfig + LB 설정 수정 |


### 접근 경로

```yaml
# 외부 접근 (kubectl, CI/CD)
External Client → External LB (VIP: 192.168.10.10:6443)
                     → CP1, CP2, CP3

# 워커 노드 kubelet
Worker Node → localhost:6443 (로컬 프록시)
                  → CP1 (192.168.10.11:6443)
                  → CP2 (192.168.10.12:6443)
                  → CP3 (192.168.10.13:6443)
```

<br>

## Case 3: Centralized LB

**외부/워커 노드 모두 External LB**를 경유한다.

![kubespray-ha-case3]({{site.url}}/assets/images/kubespray-ha-case3.png)

### 접근 원리

모든 클라이언트(외부, 워커 노드)가 동일한 External LB를 통해 API Server에 접근한다. 로컬 프록시를 사용하지 않으며, kubelet과 kube-proxy 모두 LB VIP로 접근한다. kubeconfig가 단순해지고(모두 동일한 VIP) API Server 추가/제거 시 LB 설정만 변경하면 된다. 
단, LB 장애 시 워커 노드도 API Server에 접근할 수 없어 **전체 클러스터에 영향**을 준다. 따라서 LB 자체도 HA 구성이 필수다.

| 항목 | 설명 |
|------|------|
| **워커 노드 → API** | External LB 경유 (1개 VIP) |
| **외부 → API** | External LB 경유 (1개 VIP) |
| **LB 장애 시 영향** | **전체 장애** (워커 포함) |
| **External LB 필요** | 필수 (전체용), LB 자체도 HA 필요 |
| **API 서버 추가/제거 시** | LB 설정만 수정 |

> **참고**: 워커 노드에서 API Server에 접근하는 컴포넌트는 kubelet과 kube-proxy 두 가지다. kubelet은 Pod 스펙 조회 및 노드 상태 보고를, kube-proxy는 Service/EndpointSlice watch를 위해 API Server에 접근한다. 위 그림은 접근 경로를 단순화하여 kubelet만 표시했지만, 실제로는 kube-proxy도 동일한 경로로 API Server에 접근한다.

### kubeconfig 설정 예시

```yaml
# 워커 노드 & 외부 접근 모두 동일
clusters:
- cluster:
    server: https://192.168.10.10:6443  # LB VIP
  name: cluster
```

<br>

# 접근 패턴별 비교

## 접근 방식 비교

| 구분 | Case 1 | Case 2 | Case 3 |
|------|--------|--------|--------|
| **워커 노드 → API** | 직접 접근 (3개) | 직접 접근 (3개) | External LB 경유 (1개) |
| **외부 → API** | 직접 접근 (3개) | External LB 경유 | External LB 경유 |
| **워커 kubeconfig** | 3개 서버 주소 | 3개 서버 주소 | 1개 LB 주소 |
| **외부 kubeconfig** | 3개 서버 주소 | 1개 LB 주소 | 1개 LB 주소 |

## 운영 특성 비교

| 구분 | Case 1 | Case 2 | Case 3 |
|------|--------|--------|--------|
| **LB 장애 시 워커 영향** | 없음 | 없음 | **전체 장애** |
| **External LB 필요** | 불필요 | 필요 (외부용) | 필수 (전체용) |
| **워커 노드 LB 로직** | kubelet 내장 | kubelet 내장 | LB에 위임 |
| **API 서버 추가/제거 시** | kubeconfig 수정 | kubeconfig + LB | LB 설정만 |
| **관리 주체** | K8s 팀 단독 | K8s + 인프라 팀 | 인프라 + K8s 팀 |

## 접근 주체별 경로

| 접근 주체 | Case 1 | Case 2 | Case 3 |
|-----------|--------|--------|--------|
| kubectl (개발자) | CP1, CP2, CP3 | External LB → CP1/2/3 | External LB → CP1/2/3 |
| CI/CD 시스템 | CP1, CP2, CP3 | External LB → CP1/2/3 | External LB → CP1/2/3 |
| 워커 노드 kubelet | CP1, CP2, CP3 | CP1, CP2, CP3 | External LB → CP1/2/3 |
| 워커 노드 kube-proxy | CP1, CP2, CP3 | CP1, CP2, CP3 | External LB → CP1/2/3 |

<br>

# Case별 설정 방법

[앞서 설명한 두 변수](#kubespray의-api-server-ha-구성-패턴)(`loadbalancer_apiserver_localhost`, `loadbalancer_apiserver`)를 조합하여 각 Case를 구성한다.

## Case 1: Full Client-Side LB

External LB 없이 Kubespray 기본 설정만 사용한다. `loadbalancer_apiserver`를 설정하지 않으면 외부 kubeconfig에도 Control Plane 노드의 IP가 직접 들어간다.

```yaml
loadbalancer_apiserver_localhost: true
# loadbalancer_apiserver: (설정 안 함)
```
- 각 워커 노드에 로컬 프록시 생성
- kubelet/kube-proxy는 `localhost:6443` → 로컬 프록시 → API Server들
- 외부 kubeconfig는 첫 번째 Control Plane IP 사용 (장애 시 수동 변경 필요)

### Case 2: Hybrid LB

워커 노드는 Client-Side LB를 사용하고, 외부 접근용으로 External LB를 추가 설정한다. `loadbalancer_apiserver`를 설정하면 외부 kubeconfig에 해당 주소가 들어간다.

```yaml
loadbalancer_apiserver_localhost: true
loadbalancer_apiserver:
  address: 192.168.10.10
  port: 6443
```
- 각 워커 노드에 로컬 프록시 생성
- kubelet/kube-proxy는 `localhost:6443` → 로컬 프록시 → API Server들
- 외부 kubeconfig는 External LB 주소 사용 (`192.168.10.10:6443`)

### Case 3: Centralized LB

모든 접근을 External LB로 통일한다. `loadbalancer_apiserver_localhost`를 `false`로 설정하면 로컬 프록시가 생성되지 않는다.

```yaml
loadbalancer_apiserver_localhost: false
loadbalancer_apiserver:
  address: 192.168.10.10
  port: 6443
```
- 로컬 프록시 생성 안 함
- kubelet/kube-proxy도 External LB (`192.168.10.10:6443`)로 접근
- 외부 kubeconfig도 동일한 External LB 주소 사용

## Kubespray가 Case 1을 기본으로 지원하는 이유

Kubespray는 `loadbalancer_apiserver_localhost: true`를 기본값으로 설정한다. 이는 Kubespray 프로젝트의 핵심 철학을 반영한다.

> **Kubespray 철학**: Kubernetes 클러스터는 외부 의존성 없이 자체적으로 HA를 구현할 수 있어야 한다.

[1. Kubespray 개요]({% post_url 2026-01-25-Kubernetes-Kubespray-01 %}#왜-kubespray는-client-side-lb만-자동화하는가)에서 살펴보았듯이, External LB는 환경마다 구성 방식이 완전히 다르다(AWS ELB, GCP LB, 온프레미스 HAProxy 등). Kubespray는 "OS 위 소프트웨어"를 자동화하는 도구이지, VIP/방화벽/DNS 같은 인프라 레이어를 자동화하는 도구가 아니다. 반면 Client-side LB는 각 노드에 로컬 프록시만 설치하면 되므로 어떤 환경에서든 동일하게 동작한다.

온프레미스 환경에서 Kubernetes를 배포할 때, External LB가 항상 준비되어 있지 않다. 클라우드와 달리 관리형 LB 서비스가 없고, 별도의 HAProxy나 F5 같은 인프라를 구축해야 한다. Kubespray는 이러한 외부 인프라 없이도 HA 클러스터를 구성할 수 있도록 로컬 프록시 기반의 Client-Side LB를 기본으로 제공한다.

| 이점 | 설명 |
|------|------|
| **의존성 최소화** | External LB 없이 클러스터 구성 가능 |
| **자율성** | K8s 관리자가 인프라 팀 도움 없이 독립적으로 운영 |
| **장애 격리** | LB 장애가 클러스터에 영향을 주지 않음 |
| **온프레미스 친화적** | 별도 LB 인프라 구축 부담 없음 |

<br>

# 결과

API Server 접근 패턴 3가지를 살펴보았다.

| Case | 워커 노드 | 외부 접근 | 적합한 환경 |
|------|----------|----------|------------|
| **Case 1** | 로컬 프록시 | 직접 접근 | 온프레미스, K8s 팀 독립 운영 |
| **Case 2** | 로컬 프록시 | External LB | 온프레미스, 외부 접근 필요 |
| **Case 3** | External LB | External LB | 클라우드, 엄격한 네트워크 정책 |

Kubespray는 `loadbalancer_apiserver_localhost: true`를 기본값으로 설정하여, 외부 의존성 없이 자체적으로 HA를 구현한다. 온프레미스 환경에서는 일반적으로 Case 1 또는 Case 2를 권장한다.

다음 글에서는 **HA 실습 환경을 구성**하고, Control Plane 3대 구성으로 클러스터를 배포한다.

<br>

# 참고 자료

- [Kubespray - HA endpoints for K8s](https://kubespray.io/#/docs/ha-mode)
- [Kubernetes - Options for HA topology](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/)
- [이전 글: 4.2. 클러스터 배포 - 클러스터 배포]({% post_url 2026-01-25-Kubernetes-Kubespray-04-02 %})
- [이전 글: 1. Kubespray 개요]({% post_url 2026-01-25-Kubernetes-Kubespray-01 %})

<br>
