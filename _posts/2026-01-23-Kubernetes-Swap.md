---
title:  "[Kubernetes] 쿠버네티스와 스왑"
excerpt: "쿠버네티스에서 스왑 비활성화가 권장되는 이유와 최신 NodeSwap 기능을 살펴본다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Swap
  - Memory
  - kubelet
  - NodeSwap
---

<br>

# 개요

쿠버네티스는 전통적으로 **노드에서 스왑을 비활성화**하도록 요구해왔다. kubelet은 기본적으로 스왑이 감지되면 시작을 거부한다. 이 글에서는 왜 스왑 비활성화가 권장되는지, 그리고 최근 스왑 사용을 허용하려는 움직임에 대해 살펴본다.

> 메모리, 페이지, 스왑의 기본 개념은 [메모리, 페이지, 스왑](/cs/CS-Memory-Page-Swap/)을, 컨테이너 환경에서의 메모리 관리는 [컨테이너와 메모리]를 참고하자.

<br>

# 스왑 비활성화 요구 사항

## kubelet의 기본 동작

쿠버네티스 공식 문서에 따르면, **kubelet의 기본 동작은 노드에서 스왑 메모리가 감지되면 시작을 거부**하는 것이다.

```
The default behavior of a kubelet is to fail to start 
if swap memory is detected on a node.
```

따라서 스왑은 **비활성화하거나** kubelet이 **허용하도록 설정**해야 한다.

<br>

## 스왑 비활성화 방법

### 임시 비활성화

```bash
sudo swapoff -a
```

### 영구 비활성화

`/etc/fstab` 파일에서 swap 라인을 주석 처리:

```bash
# /swap.img      none    swap    sw    0   0
```

또는 systemd swap 유닛 비활성화:

```bash
sudo systemctl mask swap.target
```

<br>

## kubeadm 사전 검사

kubeadm은 클러스터 초기화 시 여러 항목을 검증한다. 스왑 비활성화 여부도 그 중 하나다:

| 검증 항목 | 설명 |
|---------|------|
| 포트 사용 | 6443, 10250, 10259, 10257, 2379-2380 등 |
| 컨테이너 런타임 | containerd, CRI-O 등 설치 여부 |
| 시스템 요구사항 | 메모리, CPU, **swap 비활성화 여부** |
| 커널 모듈 | br_netfilter, overlay 등 |

<br>

# 스왑 비활성화가 권장되는 이유

## 일반 서버 환경과의 차이

[일반 서버/PC 환경](/cs/CS-Memory-Page-Swap/#스왑의-효과와-한계)에서 스왑은 유용하다:
- RAM 부족 시 디스크를 사용하여 **시스템 전체 다운을 방지**
- 속도는 느려지지만 작업은 계속 진행

하지만 쿠버네티스는 **분산 시스템**이다. 단일 노드의 생존보다 **클러스터 전체의 안정성**이 중요하다. 메모리가 부족한 Pod는 빠르게 종료하고 다른 노드에서 재스케줄링하는 것이 전체 시스템 관점에서 더 낫다.

```
일반 서버: 메모리 부족 → 스왑 사용 → 느리지만 작업 계속
Kubernetes: 메모리 부족 → Pod 종료 (OOMKilled) → 다른 노드에서 재시작
```

스왑이 켜져 있으면 이 철학이 깨지면서 여러 문제가 발생한다.

<br>

## 리소스 예측 불가능

쿠버네티스의 핵심 설계 철학은 **리소스 격리와 예측 가능성**이다.

```yaml
resources:
  requests:
    memory: 1Gi  # 최소 필요 메모리
  limits:
    memory: 2Gi  # 최대 사용 가능 메모리
```

이 선언을 기반으로 스케줄러는 노드 배치를 결정한다:

```
Pod A: requests.memory = 2Gi, limits.memory = 4Gi
Pod B: requests.memory = 1Gi, limits.memory = 2Gi

스케줄러: "이 노드에 3Gi 여유 있으니 두 Pod 모두 배치 가능"
```

스왑이 있으면 이 계산이 불확실해진다:
- Pod가 메모리를 초과 사용해도 죽지 않고 디스크를 쓰면서 버팀
- Kubernetes는 정상 Pod로 인식하여 추가 Pod 배치
- 물리 메모리가 스왑으로 밀려나면 실제 가용 메모리 파악이 어려움

결과적으로:
- **스케줄링 판단 오류**: 리소스 사용량 예측 불가
- **노드 병목**: 스왑 I/O로 노드 전체 성능 저하
- **연쇄 지연**: 해당 노드의 다른 Pod에도 영향
- **클러스터 전체 성능 저하**: 서비스 응답 시간 증가

<br>

## Pod Eviction과의 충돌

kubelet은 메모리 압박 시 Pod Eviction을 통해 리소스를 확보한다:

```
메모리 압박 감지 → Pod 우선순위 계산 → 낮은 우선순위 Pod 축출
```

스왑이 활성화되어 있으면:
- 메모리 압박 신호가 지연됨 (스왑으로 버티기 때문)
- Eviction이 제때 일어나지 않음
- 노드 전체가 불안정해진 후에야 대응

<br>

## QoS와 OOM Killer

쿠버네티스는 Pod의 QoS(Quality of Service) 클래스에 따라 OOM 점수를 조정한다:

| QoS 클래스 | 조건 | oom-score-adj |
|-----------|------|---------------|
| **Guaranteed** | requests = limits (모든 컨테이너) | -998 (거의 죽지 않음) |
| **Burstable** | requests < limits | 2~999 (메모리 사용량에 따라) |
| **BestEffort** | requests/limits 미설정 | 1000 (가장 먼저 죽음) |

스왑이 있으면 OOM Killer가 제때 동작하지 않아, 이 우선순위 시스템이 무력화된다.

<br>

## 성능 예측 불가능

스왑 I/O는 RAM 접근보다 수백~수천 배 느리다:

```
RAM 접근: ~100ns
SSD 접근: ~100μs (1000배 느림)
HDD 접근: ~10ms (100000배 느림)
```

Pod가 스왑을 사용하기 시작하면:
- 응답 시간이 예측 불가능하게 변동
- SLA/SLO 보장 불가
- 마이크로서비스 간 연쇄 지연 발생

<br>

# 최신 트렌드: NodeSwap 기능

## 배경

스왑 비활성화가 항상 최선은 아니라는 인식이 생겼다:

- **레거시 워크로드 마이그레이션**: 스왑에 의존하는 기존 애플리케이션
- **개발 환경**: 리소스가 제한된 환경에서의 유연성
- **버스티(bursty) 워크로드**: 일시적으로 메모리가 급증하는 워크로드
- **비용 최적화**: 물리 메모리 대신 스왑으로 버퍼 확보

<br>

## NodeSwap 기능

Kubernetes 1.22부터 **NodeSwap** 기능이 알파로 도입되었고, 1.28에서 베타가 되었다. 이 기능을 통해 **노드에서 스왑을 제한적으로 사용**할 수 있다.

### kubelet 설정

`failSwapOn: false`로 설정하면 스왑이 있어도 kubelet이 시작된다:

```yaml
# /var/lib/kubelet/config.yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
failSwapOn: false
memorySwap:
  swapBehavior: LimitedSwap  # 또는 UnlimitedSwap
```

### swapBehavior 옵션

| 값 | 동작 |
|---|------|
| **LimitedSwap** | BestEffort와 Burstable Pod만 스왑 사용 가능, Guaranteed Pod는 스왑 불가 |
| **UnlimitedSwap** | 모든 Pod가 호스트 스왑 사용 가능 |

### QoS별 스왑 사용

```
Guaranteed Pod: 스왑 사용 불가 (예측 가능한 성능 보장)
Burstable Pod:  제한된 스왑 사용 가능
BestEffort Pod: 제한된 스왑 사용 가능
```

<br>

## 커널 파라미터 튜닝

스왑을 사용할 경우, 커널 파라미터 튜닝이 중요하다. Kubernetes 공식 블로그에서는 다음 설정을 권장한다:

```bash
# 스왑 적극성 낮춤
vm.swappiness=1

# 최소 유지 free 메모리 (커널 동작을 위한 여유 공간)
vm.min_free_kbytes=<적절한 값>

# 메모리 워터마크 조정 (더 일찍 메모리 회수 시작)
vm.watermark_scale_factor=<적절한 값>
```

이 설정의 목적은 커널이 **메모리 압박에 더 일찍 반응**하도록 하여, kubelet의 Eviction과 OOM Killer 개입 전에 적절한 스와핑이 이루어지도록 하는 것이다.

<br>

# 실무 권장 사항

## 프로덕션 환경

**여전히 스왑 비활성화를 권장**한다:

```bash
# 스왑 비활성화
sudo swapoff -a

# /etc/fstab에서 swap 라인 주석 처리
# /swap.img      none    swap    sw    0   0
```

이유:
- 예측 가능한 성능이 가장 중요
- QoS와 Eviction 메커니즘이 정상 동작
- 운영 복잡도 감소

<br>

## 스왑 허용이 필요한 경우

특수한 상황에서 스왑을 허용해야 한다면:

1. **NodeSwap 기능 활성화**:
   ```yaml
   # kubelet config
   failSwapOn: false
   memorySwap:
     swapBehavior: LimitedSwap
   ```

2. **커널 파라미터 튜닝**:
   ```bash
   sudo sysctl -w vm.swappiness=1
   echo "vm.swappiness=1" | sudo tee -a /etc/sysctl.conf
   ```

3. **모니터링 강화**:
   - 스왑 사용량 모니터링
   - Pod별 메모리 사용 패턴 분석
   - 성능 저하 알람 설정

<br>

## 메모리 부족 시 실무적 대안

스왑 대신 다음 방법을 고려하자:

1. **적절한 requests/limits 설정**: 리소스를 정확하게 요청하여 스케줄링 최적화
2. **HPA (Horizontal Pod Autoscaler)**: 부하에 따라 Pod 수 자동 조정
3. **VPA (Vertical Pod Autoscaler)**: Pod의 리소스 요청/제한 자동 조정
4. **노드 추가**: 클러스터 확장으로 전체 용량 증가
5. **워크로드 최적화**: 메모리 사용량이 큰 워크로드 분석 및 개선

<br>

# 정리

쿠버네티스와 스왑의 관계를 정리하면 다음과 같다:

1. **기본 요구사항**: kubelet은 스왑이 감지되면 시작을 거부함
2. **비활성화 이유**: 예측 가능한 리소스 관리, Pod Eviction, QoS/OOM Killer 정상 동작, 성능 예측 가능성
3. **NodeSwap 기능**: Kubernetes 1.28부터 베타로, 제한적인 스왑 사용 가능
4. **프로덕션 권장**: 여전히 스왑 비활성화 권장
5. **스왑 허용 시**: failSwapOn=false, swapBehavior 설정, 커널 튜닝 필요

쿠버네티스 클러스터 설치 시 스왑 비활성화 과정은 [Kubernetes Cluster The Hard Way](/kubernetes/Kubernetes-Cluster-The-Hard-Way-01/)나 [Kubeadm으로 클러스터 구성하기](/kubernetes/Kubernetes-Kubeadm-01-1/)를 참고하자.

<br>

