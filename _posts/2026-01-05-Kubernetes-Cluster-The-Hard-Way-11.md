---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 11. Provisioning Pod Network Routes"
excerpt: "서로 다른 노드의 Pod 간 통신을 위해 수동 라우팅을 설정해 보자."
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

**서로 다른 노드에 배치된 Pod 간 통신을 위해 수동 라우팅을 설정한다.**

이번 글의 목표는 **Pod Network Routes 프로비저닝**이다. [Kubernetes the Hard Way 튜토리얼의 Provisioning Pod Network Routes 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/11-pod-network-routes.md)를 수행한다.

- 각 노드의 Pod CIDR 대역 확인
- 노드별 수동 라우팅 테이블 설정
- 서로 다른 노드의 Pod 간 통신 경로 확보

이전 단계에서 CNI 플러그인으로 bridge를 설정했는데, 이 방식은 같은 노드 내 Pod 간 통신만 지원한다. 서로 다른 노드에 배치된 Pod가 통신하려면 추가적인 라우팅 설정이 필요하다.

<br>

# 배경

## CNI와 Pod 네트워크

Kubernetes는 각 Pod에 고유한 IP 주소를 할당한다. Pod가 서로 통신하려면 네트워크 설정이 필요한데, 이를 CNI(Container Network Interface) 플러그인이 담당한다.

이번 실습에서는 [9.2. Bootstrapping the Kubernetes Worker Nodes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) 단계에서 기본 `bridge` CNI 플러그인을 설정했다. 각 노드에 설정된 bridge 네트워크는 다음과 같다:

| 노드 | Pod CIDR | Bridge 네트워크 |
| --- | --- | --- |
| node-0 | 10.200.0.0/24 | cni0 (10.200.0.1/24) |
| node-1 | 10.200.1.0/24 | cni0 (10.200.1.1/24) |

<br>

## 문제: 노드 간 Pod 통신 불가

bridge CNI 플러그인은 Layer 2 수준에서 동작한다. 즉, 같은 노드 내에 있는 Pod끼리는 bridge를 통해 통신할 수 있지만, **서로 다른 노드에 있는 Pod 간 통신은 지원하지 않는다**.

예를 들어 보자.
- node-0의 Pod(10.200.0.x)에서 node-1의 Pod(10.200.1.x)로 패킷을 보내려면?
- node-0의 커널은 10.200.1.0/24 대역으로 가는 경로를 모른다.
- 패킷은 기본 게이트웨이로 전달되거나 드롭된다.

<br>

## 해결책: 수동 라우팅 설정

노드의 커널 라우팅 테이블에 다른 노드의 Pod CIDR에 대한 경로를 직접 추가하면 된다. 각 노드가 다른 노드의 Pod 대역으로 가는 패킷을 어디로 보내야 하는지 알게 된다.

```
node-0 Pod (10.200.0.x)
    ↓
node-0 커널: "10.200.1.0/24는 192.168.10.102(node-1)로"
    ↓
node-1로 패킷 전달
    ↓
node-1 커널: cni0 bridge로 전달
    ↓
node-1 Pod (10.200.1.x)
```

실제 프로덕션 환경에서는 Calico, Flannel, Cilium 같은 CNI 플러그인이 이 작업을 자동으로 처리한다. 이번 실습에서는 학습 목적으로 수동 설정을 통해 원리를 이해한다.

<br>

# IP 및 CIDR 정보 확인

jumpbox에서 각 노드의 IP 주소와 Pod CIDR 대역을 확인한다.

```bash
# (jumpbox)
SERVER_IP=$(grep server machines.txt | cut -d " " -f 1)
NODE_0_IP=$(grep node-0 machines.txt | cut -d " " -f 1)
NODE_0_SUBNET=$(grep node-0 machines.txt | cut -d " " -f 4)
NODE_1_IP=$(grep node-1 machines.txt | cut -d " " -f 1)
NODE_1_SUBNET=$(grep node-1 machines.txt | cut -d " " -f 4)
echo $SERVER_IP $NODE_0_IP $NODE_0_SUBNET $NODE_1_IP $NODE_1_SUBNET
```

```
192.168.10.100 192.168.10.101 10.200.0.0/24 192.168.10.102 10.200.1.0/24
```

정보를 정리하면 다음과 같다:

| 변수 | 값 | 설명 |
| --- | --- | --- |
| SERVER_IP | 192.168.10.100 | Control Plane 노드 IP |
| NODE_0_IP | 192.168.10.101 | Worker 노드 0 IP |
| NODE_0_SUBNET | 10.200.0.0/24 | node-0의 Pod CIDR |
| NODE_1_IP | 192.168.10.102 | Worker 노드 1 IP |
| NODE_1_SUBNET | 10.200.1.0/24 | node-1의 Pod CIDR |

노드들은 192.168.10.0/24 대역의 호스트 네트워크로 연결되어 있고, 각 Worker 노드는 자신만의 Pod CIDR 대역을 가진다.

<br>

# 라우팅 설정

각 노드에 다른 노드의 Pod CIDR로 가는 경로를 추가한다.

## server

server 노드는 Control Plane이지만, Pod 네트워크 디버깅이나 관리 목적으로 Pod에 접근해야 할 수 있다. 두 Worker 노드의 Pod CIDR에 대한 라우팅을 추가한다.

### 설정 전 라우팅 테이블 확인

```bash
# (jumpbox)
ssh server ip -c route
```

```
default via 10.0.2.2 dev eth0 
10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15 
192.168.10.0/24 dev eth1 proto kernel scope link src 192.168.10.100 
```

현재 server는 10.200.x.x 대역에 대한 라우팅 정보가 없다.

### 라우팅 추가

```bash
ssh root@server <<EOF
  ip route add ${NODE_0_SUBNET} via ${NODE_0_IP}
  ip route add ${NODE_1_SUBNET} via ${NODE_1_IP}
EOF
```

추가한 라우팅의 의미:
- `ip route add 10.200.0.0/24 via 192.168.10.101`: 10.200.0.0/24 대역(node-0의 Pod들)으로 가는 패킷은 192.168.10.101(node-0)을 거쳐 전달
- `ip route add 10.200.1.0/24 via 192.168.10.102`: 10.200.1.0/24 대역(node-1의 Pod들)으로 가는 패킷은 192.168.10.102(node-1)을 거쳐 전달

### 설정 후 라우팅 테이블 확인

```bash
ssh server ip -c route
```

```
default via 10.0.2.2 dev eth0 
10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15 
10.200.0.0/24 via 192.168.10.101 dev eth1 
10.200.1.0/24 via 192.168.10.102 dev eth1 
192.168.10.0/24 dev eth1 proto kernel scope link src 192.168.10.100 
```

두 Pod CIDR 대역에 대한 라우팅이 추가되었다. 이제 server에서 10.200.0.x나 10.200.1.x로 패킷을 보내면 적절한 Worker 노드로 전달된다.

<br>

## node-0

node-0은 자신의 Pod CIDR(10.200.0.0/24)은 이미 알고 있다(bridge 설정으로). node-1의 Pod CIDR(10.200.1.0/24)에 대한 라우팅만 추가하면 된다.

### 설정 전 라우팅 테이블 확인

```bash
ssh node-0 ip -c route
```

```
default via 10.0.2.2 dev eth0 
10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15 
192.168.10.0/24 dev eth1 proto kernel scope link src 192.168.10.101 
```

### 라우팅 추가

```bash
ssh root@node-0 <<EOF
  ip route add ${NODE_1_SUBNET} via ${NODE_1_IP}
EOF
```

### 설정 후 라우팅 테이블 확인

```bash
ssh node-0 ip -c route
```

```
default via 10.0.2.2 dev eth0 
10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15 
10.200.1.0/24 via 192.168.10.102 dev eth1 
192.168.10.0/24 dev eth1 proto kernel scope link src 192.168.10.101 
```

`10.200.1.0/24 via 192.168.10.102` 라우팅이 추가되었다. 이제 node-0의 Pod가 node-1의 Pod(10.200.1.x)로 패킷을 보내면, node-1(192.168.10.102)을 통해 전달된다.

<br>

## node-1

동일한 방식으로 node-1에 node-0의 Pod CIDR에 대한 라우팅을 추가한다.

```bash
# 설정 전 확인
ssh node-1 ip -c route

# 라우팅 추가
ssh root@node-1 <<EOF
  ip route add ${NODE_0_SUBNET} via ${NODE_0_IP}
EOF

# 설정 후 확인
ssh node-1 ip -c route
```

```
default via 10.0.2.2 dev eth0 
10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15 
10.200.0.0/24 via 192.168.10.101 dev eth1 
192.168.10.0/24 dev eth1 proto kernel scope link src 192.168.10.102 
```

`10.200.0.0/24 via 192.168.10.101` 라우팅이 추가되었다.

<br>

# 라우팅 설정 요약

각 노드에 추가된 라우팅을 정리하면 다음과 같다:

| 노드 | 추가된 라우팅 | 의미 |
| --- | --- | --- |
| server | 10.200.0.0/24 via 192.168.10.101 | node-0 Pod로 가는 패킷 → node-0 경유 |
| server | 10.200.1.0/24 via 192.168.10.102 | node-1 Pod로 가는 패킷 → node-1 경유 |
| node-0 | 10.200.1.0/24 via 192.168.10.102 | node-1 Pod로 가는 패킷 → node-1 경유 |
| node-1 | 10.200.0.0/24 via 192.168.10.101 | node-0 Pod로 가는 패킷 → node-0 경유 |

이 설정으로 노드 간 Pod 통신 경로가 확보된다.

<br>

# 주의: 라우팅 설정의 휘발성

`ip route add` 명령으로 추가한 라우팅은 **메모리에만 저장**된다. 노드가 재부팅되면 설정이 사라진다.

영구적으로 유지하려면 다음 방법 중 하나를 사용해야 한다:
- `/etc/network/interfaces` 또는 `/etc/netplan/` 설정 파일에 추가
- systemd 네트워크 설정 사용
- 부팅 스크립트에 라우팅 명령 추가

다만 이번 실습에서는 학습 목적이므로 영구 설정은 생략한다. 실제 운영 환경에서는 Calico, Flannel 같은 CNI 플러그인이 이 작업을 자동으로 처리하고 유지한다.

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **노드 간 Pod 통신 가능**: node-0의 Pod와 node-1의 Pod가 IP로 직접 통신 가능
2. **라우팅 테이블 설정**: 각 노드가 다른 노드의 Pod CIDR 경로를 인식
3. **Control Plane 접근**: server에서도 Pod 네트워크에 접근 가능

<br>

이번 실습을 통해 Kubernetes Pod 네트워킹의 기본 원리를 이해할 수 있었다. CNI 플러그인이 자동으로 처리해주는 작업을 수동으로 수행하면서, 노드 간 Pod 통신이 어떻게 이루어지는지 파악했다.

다음 글에서는 Smoke Test를 통해 클러스터가 정상적으로 동작하는지 검증한다.
