---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 12. Smoke Test"
excerpt: "구성한 Kubernetes 클러스터가 정상적으로 동작하는지 다양한 테스트를 통해 검증해 보자."
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

이번 글의 목표는 **Kubernetes 클러스터 동작 검증**이다. [Kubernetes the Hard Way 튜토리얼의 Smoke Test 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/12-smoke-test.md)를 수행한다.

- Data Encryption 검증: Secret 암호화가 etcd에서 정상 동작하는지 확인
- Deployment 배포: nginx Deployment 생성 및 스케일링
- 네트워킹 검증: CNI 브릿지, veth 인터페이스, 파드 간 통신 확인
- kubectl 기능 테스트: port-forward, logs, exec, NodePort 서비스 노출

이전 단계에서 구성한 모든 컴포넌트가 실제로 동작하는지 종합적으로 검증한다.

<br>


# Data Encryption

[6단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %})에서 설정한 Secret 암호화가 실제로 동작하는지 확인한다. Secret을 생성하고 etcd에 저장된 데이터가 암호화되어 있는지 검증한다.

## Secret 생성

테스트용 Secret을 생성한다.

```bash
kubectl create secret generic kubernetes-the-hard-way --from-literal="mykey=mydata"
secret/kubernetes-the-hard-way created
```

## Secret 조회

생성한 Secret을 조회한다.

```bash
kubectl get secret kubernetes-the-hard-way
NAME                      TYPE     DATA   AGE
kubernetes-the-hard-way   Opaque   1      28s
```

YAML 형식으로 상세 정보를 확인한다.

```bash
kubectl get secret kubernetes-the-hard-way -o yaml
apiVersion: v1
data:
  mykey: bXlkYXRh
kind: Secret
metadata:
  creationTimestamp: "2026-01-09T16:22:15Z"
  name: kubernetes-the-hard-way
  namespace: default
  resourceVersion: "22353"
  uid: 3685406f-30e9-4d99-a05b-d7fafd312f12
type: Opaque
```

출력 결과를 살펴보면:

- **type: Opaque**: Kubernetes Secret의 기본 타입이다. "불투명한"이라는 의미로, 임의의 사용자 정의 데이터를 저장할 수 있음을 나타낸다. 다른 타입으로는 `kubernetes.io/tls`(TLS 인증서), `kubernetes.io/dockerconfigjson`(Docker 레지스트리 인증) 등이 있다.
- **data.mykey: bXlkYXRh**: 이것은 암호화가 아니라 Base64 인코딩된 값이다.

Base64로 디코딩하면 원본 데이터를 확인할 수 있다.

```bash
kubectl get secret kubernetes-the-hard-way -o jsonpath='{.data.mykey}' | base64 -d ; echo
mydata
```

> **Base64 인코딩 vs 암호화**
> 
> `bXlkYXRh`는 Base64 인코딩된 값으로, 누구나 디코딩할 수 있다. 이것은 Kubernetes API를 통해 반환되는 데이터 형식일 뿐, **실제 암호화는 etcd 저장 시점에 적용**된다. API 응답에서 Base64로 보이는 것은 kubectl이 이미 복호화된 데이터를 Base64 인코딩해서 보여주는 것이다.

## etcd에서 직접 확인

etcdctl로 etcd에 저장된 실제 데이터를 확인한다. Kubernetes API를 우회하여 raw 데이터를 조회하는 방식이다.

```bash
ssh root@server \
    'etcdctl get /registry/secrets/default/kubernetes-the-hard-way | hexdump -C'
00000000  2f 72 65 67 69 73 74 72  79 2f 73 65 63 72 65 74  |/registry/secret|
00000010  73 2f 64 65 66 61 75 6c  74 2f 6b 75 62 65 72 6e  |s/default/kubern|
00000020  65 74 65 73 2d 74 68 65  2d 68 61 72 64 2d 77 61  |etes-the-hard-wa|
00000030  79 0a 6b 38 73 3a 65 6e  63 3a 61 65 73 63 62 63  |y.k8s:enc:aescbc|
00000040  3a 76 31 3a 6b 65 79 31  3a ce bb 18 82 e1 c7 18  |:v1:key1:.......|
00000050  48 a8 f4 47 dc 02 d7 32  1a e4 1d f3 0a 6b b5 bb  |H..G...2.....k..|
00000060  32 a5 61 da ef 5d 32 b9  f2 a3 90 df 81 86 d1 6f  |2.a..]2........o|
00000070  0d c0 45 a3 53 10 8e f7  40 67 9f 44 27 2a 67 e4  |..E.S...@g.D'*g.|
...
```

hexdump 결과를 분석하면:

| 구성 요소 | 설명 |
| --- | --- |
| `/registry/secrets/default/kubernetes-the-hard-way` | etcd key 경로. Secret 리소스의 저장 경로 형식은 `/registry/<resource>/<namespace>/<name>` |
| `k8s:enc` | Kubernetes 암호화 포맷 prefix |
| `aescbc` | 암호화 알고리즘 (AES-CBC) |
| `v1` | encryption provider 버전 |
| `key1` | encryption-config.yaml에서 정의한 키 이름 |
| 이후 데이터 | 실제 암호화된 바이너리 데이터 (`.`으로 표시된 부분) |

etcd key 이름(`/registry/secrets/...`)은 항상 평문으로 저장된다. 어떤 리소스인지 식별해야 하기 때문이다. 반면 value 부분은 `k8s:enc:aescbc:v1:key1:` 이후의 바이너리 데이터가 AES-CBC로 암호화되어 있어 해독 불가능하다.

> **etcdctl 직접 조회가 강력한 이유**
> 
> `etcdctl get` 명령어는 Kubernetes API를 완전히 우회하여 etcd에 저장된 raw 데이터를 직접 조회한다. RBAC, Admission Controller, API 인증 등 모든 Kubernetes 보안 계층을 건너뛰므로, etcd 접근 권한만 있으면 모든 클러스터 데이터에 접근할 수 있다. 이것이 etcd의 접근 제어가 매우 중요한 이유다.

<br>

# Deployment 동작 검증

## Deployment 배포

nginx Deployment를 생성하고 Worker Node에 Pod가 정상 배포되는지 확인한다.

```bash
kubectl get pod
No resources found in default namespace.
```

nginx Deployment를 생성한다.

```bash
kubectl create deployment nginx --image=nginx --replicas=1
deployment.apps/nginx created
```

replica를 2개로 스케일링한다.

```bash
kubectl scale deployment nginx --replicas=2
deployment.apps/nginx scaled
```

Pod 배포 상태를 확인한다.

```bash
kubectl get pod -o wide
NAME                     READY   STATUS              RESTARTS   AGE   IP           NODE     NOMINATED NODE   READINESS GATES
nginx-5869d7778c-b28m4   0/1     ContainerCreating   0          14s   <none>       node-0   <none>           <none>
nginx-5869d7778c-gnscb   1/1     Running             0          31s   10.200.1.2   node-1   <none>           <none>
```

kube-scheduler가 Pod를 node-0, node-1에 각각 분산 배치했다. 각 Pod는 해당 노드의 PodCIDR 대역에서 IP를 할당받는다 (node-0: 10.200.0.x, node-1: 10.200.1.x).

## crictl로 컨테이너 확인

[crictl](https://sirzzang.github.io/dev/Dev-Container-Duplicate-Container-Images-2/#crictl)을 사용하여 각 노드에서 실행 중인 컨테이너를 직접 확인한다.

```bash
ssh node-0 crictl ps
time="2026-01-10T01:29:59+09:00" level=warning msg="Config \"/etc/crictl.yaml\" does not exist, trying next: \"/usr/local/bin/crictl.yaml\""
time="2026-01-10T01:29:59+09:00" level=warning msg="runtime connect using default endpoints: [unix:///run/containerd/containerd.sock unix:///run/crio/crio.sock unix:///var/run/cri-dockerd.sock]. As the default settings are now deprecated, you should set the endpoint instead."
time="2026-01-10T01:29:59+09:00" level=warning msg="Image connect using default endpoints: [unix:///run/containerd/containerd.sock unix:///run/crio/crio.sock unix:///var/run/cri-dockerd.sock]. As the default settings are now deprecated, you should set the endpoint instead."
CONTAINER           IMAGE               CREATED              STATE               NAME                ATTEMPT             POD ID              POD                      NAMESPACE
1a23a52e7c9e0       759581db3b0c2       About a minute ago   Running             nginx               0                   c7fd0a93cbea3       nginx-5869d7778c-b28m4   default
```

```bash
ssh node-1 crictl ps
time="2026-01-10T01:30:05+09:00" level=warning msg="Config \"/etc/crictl.yaml\" does not exist, trying next: \"/usr/local/bin/crictl.yaml\""
time="2026-01-10T01:30:05+09:00" level=warning msg="runtime connect using default endpoints: [unix:///run/containerd/containerd.sock unix:///run/crio/crio.sock unix:///var/run/cri-dockerd.sock]. As the default settings are now deprecated, you should set the endpoint instead."
time="2026-01-10T01:30:05+09:00" level=warning msg="Image connect using default endpoints: [unix:///run/containerd/containerd.sock unix:///run/crio/crio.sock unix:///var/run/cri-dockerd.sock]. As the default settings are now deprecated, you should set the endpoint instead."
CONTAINER           IMAGE               CREATED             STATE               NAME                ATTEMPT             POD ID              POD                      NAMESPACE
2549636c57fce       759581db3b0c2       2 minutes ago       Running             nginx               0                   7a27f5361d625       nginx-5869d7778c-gnscb   default
```

> **crictl 경고 메시지**
> 
> 경고는 crictl 설정 파일(`/etc/crictl.yaml`)이 없어서 발생한다. crictl은 여러 컨테이너 런타임(containerd, crio, docker)을 지원하므로, 어떤 런타임의 소켓에 연결할지 명시적으로 설정하는 것이 권장된다. 설정 파일 없이도 기본 엔드포인트를 순차적으로 시도하여 동작하므로 기능상 문제는 없다. 경고를 없애려면 `/etc/crictl.yaml` 파일을 생성하고 `runtime-endpoint: unix:///run/containerd/containerd.sock`를 설정하면 된다.

## 프로세스 트리 확인

Worker Node의 프로세스 트리를 확인하여 컨테이너 런타임 계층 구조를 파악한다.

```bash
ssh node-0 pstree -ap
systemd,1
  |-VBoxService,619 --pidfile /var/run/vboxadd-service.sh
  |   |-{VBoxService},620
  |   ...
  |-containerd,3440
  |   |-{containerd},3446
  |   ...
  |-containerd-shim,4099 -namespace k8s.io -id c7fd0a93cbea31c89a64ef71360b2cc7886338dd9704330b965c5e2c550fa60c -address/ru
  |   |-nginx,4154
  |   |   |-nginx,4188
  |   |   `-nginx,4189
  |   |-pause,4124
  |   |-{containerd-shim},4100
  |   ...
  |-kube-proxy,3433 --config=/var/lib/kube-proxy/kube-proxy-config.yaml
  |   |-{kube-proxy},3434
  |   ...
  |-kubelet,3441 --config=/var/lib/kubelet/kubelet-config.yaml --kubeconfig=/var/lib/kubelet/kubeconfig --v=2
  |   |-{kubelet},3442
  |   ...
```

프로세스 트리에서 확인해야 할 핵심 구조:

| 프로세스 | 역할 |
| --- | --- |
| **systemd** | 시스템 초기화 및 서비스 관리자 (PID 1) |
| **containerd** | 컨테이너 런타임 데몬. kubelet의 CRI 요청을 받아 컨테이너 생성 |
| **containerd-shim** | 각 Pod(컨테이너 그룹)마다 하나씩 생성. containerd와 실제 컨테이너 프로세스 사이의 중간 관리자 역할 |
| **pause** | Pod의 인프라 컨테이너. 네트워크 네임스페이스를 유지하고 다른 컨테이너들이 공유 |
| **nginx** | 실제 애플리케이션 컨테이너. master 프로세스(4154)와 worker 프로세스(4188, 4189) |
| **kubelet** | 노드 에이전트. API Server와 통신하며 Pod 라이프사이클 관리 |
| **kube-proxy** | 네트워크 프록시. Service의 ClusterIP/NodePort 트래픽 라우팅 |

containerd-shim 아래에 pause와 nginx가 함께 있는 구조는 **하나의 Pod 안에서 pause 컨테이너가 네트워크 네임스페이스를 소유하고, nginx 컨테이너가 그 네임스페이스를 공유**하는 Kubernetes Pod 모델을 보여준다.

<br>

# 네트워크 구성 확인

## CNI 브릿지 확인

brctl 명령어로 CNI가 생성한 Linux 브릿지를 확인한다.

```bash
ssh node-0 brctl show
bridge name     bridge id               STP enabled     interfaces
cni0            8000.7a5a8c463ad6       no              veth105f567d
```

| 항목 | 설명 |
| --- | --- |
| **cni0** | CNI bridge 플러그인이 생성한 Linux 브릿지. 노드 내 Pod들의 가상 스위치 역할 |
| **bridge id** | 브릿지 식별자 (MAC 주소 기반) |
| **STP enabled: no** | Spanning Tree Protocol 비활성화. 단순 Pod 네트워크에서는 불필요 |
| **interfaces** | 브릿지에 연결된 veth 인터페이스들. Pod 하나당 veth 하나가 연결 |

CNI 브릿지 확인은 **Pod 네트워킹이 정상 구성되었는지** 검증하는 것이다. cni0 브릿지가 있고 Pod의 veth가 연결되어 있다면, CNI 플러그인(bridge)이 정상 동작하고 Pod가 노드 내부 네트워크에 연결된 것이다.

## veth 인터페이스 확인

노드의 네트워크 인터페이스를 확인한다.

```bash
ssh node-0 ip addr 
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute 
       valid_lft forever preferred_lft forever
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 08:00:27:bc:d2:7e brd ff:ff:ff:ff:ff:ff
    altname enp0s8
    inet 10.0.2.15/24 brd 10.0.2.255 scope global dynamic eth0
       valid_lft 83311sec preferred_lft 83311sec
    inet6 fd17:625c:f037:2:a00:27ff:febc:d27e/64 scope global dynamic mngtmpaddr 
       valid_lft 86377sec preferred_lft 14377sec
    inet6 fe80::a00:27ff:febc:d27e/64 scope link 
       valid_lft forever preferred_lft forever
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 08:00:27:bd:8c:2b brd ff:ff:ff:ff:ff:ff
    altname enp0s9
    inet 192.168.10.101/24 brd 192.168.10.255 scope global eth1
       valid_lft forever preferred_lft forever
    inet6 fe80::a00:27ff:febd:8c2b/64 scope link 
       valid_lft forever preferred_lft forever
4: cni0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether 7a:5a:8c:46:3a:d6 brd ff:ff:ff:ff:ff:ff
    inet 10.200.0.1/24 brd 10.200.0.255 scope global cni0
       valid_lft forever preferred_lft forever
    inet6 fe80::785a:8cff:fe46:3ad6/64 scope link 
       valid_lft forever preferred_lft forever
5: veth105f567d@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue master cni0 state UP group default qlen 1000
    link/ether 4e:d6:91:4e:65:bf brd ff:ff:ff:ff:ff:ff link-netns cni-128ec8c5-72e4-425b-e3d8-fd542a387c4f
    inet6 fe80::4cd6:91ff:fe4e:65bf/64 scope link 
       valid_lft forever preferred_lft forever
```

각 인터페이스의 역할:

| 인터페이스 | IP | 설명 |
| --- | --- | --- |
| **lo** | 127.0.0.1 | 루프백 인터페이스 |
| **eth0** | 10.0.2.15 | VirtualBox NAT 네트워크. Vagrant 관리용으로 예약된 인터페이스 ([1단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) 참고) |
| **eth1** | 192.168.10.101 | Private network. 노드 간 실제 통신에 사용 |
| **cni0** | 10.200.0.1/24 | CNI 브릿지. node-0의 PodCIDR 대역 게이트웨이 |
| **veth105f567d** | (없음) | Pod와 연결된 veth 인터페이스. `master cni0`는 cni0 브릿지에 연결됨을 의미 |

### veth 인터페이스와 Pod 네트워킹

veth(Virtual Ethernet)는 **Linux 커널이 제공하는 가상 네트워크 인터페이스 쌍**이다. 항상 쌍(pair)으로 생성되며, 한쪽에서 들어온 패킷이 다른 쪽으로 나간다.

```text
[Pod 내부]                    [Host]
eth0 (Pod) <----veth pair----> vethXXXXXX (Host) --> cni0 브릿지 --> eth1 --> 외부
```

- Pod가 생성될 때 CNI 플러그인이 veth 쌍을 생성
- 한쪽 끝(eth0)은 Pod의 네트워크 네임스페이스에 배치
- 다른 쪽 끝(vethXXXXXX)은 호스트의 cni0 브릿지에 연결
- Pod에서 나가는 트래픽: Pod eth0 -> veth -> cni0 -> eth1 -> 외부
- Pod로 들어오는 트래픽: 외부 -> eth1 -> cni0 -> veth -> Pod eth0

> **Pod가 수백 개면 veth도 수백 개?**
> 
> 맞다. Pod 하나당 veth 쌍이 하나씩 생성된다. 이것이 성능 이슈가 될 수 있어 대규모 클러스터에서는 eBPF 기반 CNI(Cilium 등)를 사용하여 veth 오버헤드를 줄이기도 한다. 일반적인 워크로드에서는 노드당 수백 개의 veth도 문제없이 처리 가능하다.

## 노드에서 Pod IP 접근 확인

server 노드에서 Pod IP로 직접 접근이 가능한지 확인한다. 이전 단계에서 수동으로 설정한 라우팅 테이블 덕분에 다른 노드의 PodCIDR 대역으로 통신이 가능하다.

```bash
ssh server curl -s 10.200.1.2 | grep title
<title>Welcome to nginx!</title>
```

server(192.168.10.100)에서 node-1의 Pod(10.200.1.2)로 HTTP 요청이 성공했다. 이는 **Pod 네트워크 라우팅이 정상**임을 의미한다.

<br>

# kubectl 기능 테스트

## Port Forward

`kubectl port-forward`는 **로컬 머신의 포트와 Pod의 포트를 터널링**하는 기능이다. 주로 디버깅이나 임시 접근 용도로 사용한다. Service를 생성하지 않고도 Pod에 직접 접근할 수 있어 개발/테스트 시 유용하다.

Pod 이름을 추출한다.

```bash
POD_NAME=$(kubectl get pods -l app=nginx -o jsonpath="{.items[0].metadata.name}")
echo $POD_NAME
nginx-5869d7778c-b28m4
```

로컬 8080 포트를 nginx Pod의 80 포트로 포워딩한다.

```bash
kubectl port-forward $POD_NAME 8080:80 &
[1] 4159
Forwarding from 127.0.0.1:8080 -> 80
Forwarding from [::1]:8080 -> 80
```

`&`를 붙여 백그라운드로 실행하면 터미널을 계속 사용할 수 있다.

### 접속 테스트

```bash
curl --head http://127.0.0.1:8080
HTTP/1.1 200 OK
Server: nginx/1.29.4
Date: Fri, 09 Jan 2026 16:36:35 GMT
Content-Type: text/html
Content-Length: 615
Last-Modified: Tue, 09 Dec 2025 18:28:10 GMT
Connection: keep-alive
ETag: "69386a3a-267"
Accept-Ranges: bytes
```

port-forward를 실행한 터미널에서는 다음과 같은 로그가 출력된다.

```bash
Handling connection for 8080
```

이 메시지는 kubectl이 8080 포트로 들어온 연결을 받아 Pod로 전달했음을 의미한다.

### Port Forward 중지

백그라운드로 실행 중인 kubectl 프로세스를 종료한다.

```bash
kill -9 $(pgrep kubectl)
```

port-forward는 kubectl 프로세스가 살아있는 동안만 동작한다. 프로세스 종료 시 포트 포워딩도 함께 종료되므로, **지속적인 서비스 노출이 필요하다면 Service 리소스를 사용**해야 한다.

## Logs

`kubectl logs`는 컨테이너의 stdout/stderr 로그를 조회한다. 내부적으로 **kube-apiserver가 kubelet에 로그 요청을 전달**하고, kubelet이 컨테이너 런타임에서 로그를 읽어 반환한다.

```bash
kubectl logs $POD_NAME
/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
/docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
/docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
10-listen-on-ipv6-by-default.sh: info: Getting the checksum of /etc/nginx/conf.d/default.conf
10-listen-on-ipv6-by-default.sh: info: Enabled listen on IPv6 in /etc/nginx/conf.d/default.conf
/docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
/docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
/docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
/docker-entrypoint.sh: Configuration complete; ready for start up
2026/01/09 16:28:13 [notice] 1#1: using the "epoll" event method
2026/01/09 16:28:13 [notice] 1#1: nginx/1.29.4
2026/01/09 16:28:13 [notice] 1#1: built by gcc 14.2.0 (Debian 14.2.0-19) 
2026/01/09 16:28:13 [notice] 1#1: OS: Linux 6.1.0-40-arm64
2026/01/09 16:28:13 [notice] 1#1: getrlimit(RLIMIT_NOFILE): 1048576:1048576
2026/01/09 16:28:13 [notice] 1#1: start worker processes
2026/01/09 16:28:13 [notice] 1#1: start worker process 29
2026/01/09 16:28:13 [notice] 1#1: start worker process 30
127.0.0.1 - - [09/Jan/2026:16:36:35 +0000] "HEAD / HTTP/1.1" 200 0 "-" "curl/7.88.1" "-"
```

nginx 컨테이너의 시작 로그와 함께 앞서 curl로 요청한 액세스 로그도 확인할 수 있다.

## Exec

`kubectl exec`는 **실행 중인 컨테이너 안에서 명령어를 실행**한다. 컨테이너 내부 상태를 확인하거나 디버깅할 때 사용한다.

```bash
kubectl exec -ti $POD_NAME -- nginx -v
nginx version: nginx/1.29.4
```

- `-t`: TTY 할당
- `-i`: stdin 유지 (interactive)
- `--`: kubectl 옵션과 컨테이너 내 실행할 명령어를 구분

## NodePort 서비스 노출

NodePort는 **클러스터 외부에서 노드 IP:NodePort로 Pod에 접근**할 수 있게 하는 Service 타입이다.

Deployment를 NodePort 서비스로 노출한다.

```bash
kubectl expose deployment nginx --port=80 --target-port=80 --type=NodePort
service/nginx exposed
```

Service와 Endpoints를 확인한다.

```bash
kubectl get service,ep nginx
NAME            TYPE       CLUSTER-IP    EXTERNAL-IP   PORT(S)        AGE
service/nginx   NodePort   10.32.0.254   <none>        80:30443/TCP   37s

NAME              ENDPOINTS                     AGE
endpoints/nginx   10.200.0.2:80,10.200.1.2:80   37s
```

- **CLUSTER-IP (10.32.0.254)**: 클러스터 내부에서만 접근 가능한 가상 IP
- **PORT(S) (80:30443/TCP)**: 서비스 포트 80이 NodePort 30443에 매핑
- **ENDPOINTS**: 실제 트래픽이 전달될 Pod IP 목록

NodePort를 추출한다.

```bash
NODE_PORT=$(kubectl get svc nginx --output=jsonpath='{range .spec.ports[0]}{.nodePort}')
echo $NODE_PORT
30443
```

노드 IP와 NodePort로 접속을 테스트한다.

```bash
curl -s -I http://node-0:${NODE_PORT}
HTTP/1.1 200 OK
Server: nginx/1.29.4
Date: Fri, 09 Jan 2026 16:42:49 GMT
Content-Type: text/html
Content-Length: 615
Last-Modified: Tue, 09 Dec 2025 18:28:10 GMT
Connection: keep-alive
ETag: "69386a3a-267"
Accept-Ranges: bytes
```

node-0:30443으로 요청하면 kube-proxy가 트래픽을 nginx Pod로 라우팅한다. **어떤 노드로 요청해도 동일하게 동작**한다.

<br>

# 결과

이번 Smoke Test를 통해 다음 항목들이 정상 동작함을 확인했다:

| 테스트 항목 | 검증 내용 |
| --- | --- |
| **Data Encryption** | Secret이 etcd에 AES-CBC로 암호화되어 저장됨 |
| **Deployment** | Pod가 Worker Node에 정상 스케줄링 및 실행됨 |
| **컨테이너 런타임** | containerd가 Pod 컨테이너를 정상 관리함 |
| **CNI 네트워킹** | cni0 브릿지, veth 인터페이스 정상 생성됨 |
| **Pod 네트워크** | 다른 노드의 Pod IP로 통신 가능 |
| **kubectl 기능** | port-forward, logs, exec 정상 동작 |
| **kube-proxy** | NodePort 서비스가 트래픽을 Pod로 라우팅함 |

<br>

Kubernetes the Hard Way의 모든 단계를 완료했다. 클러스터의 핵심 구성 요소가 모두 정상 동작한다:

| 컴포넌트 | 노드 | 역할 |
| --- | --- | --- |
| etcd | server | 클러스터 상태 저장소 |
| kube-apiserver | server | API 엔드포인트 |
| kube-scheduler | server | Pod 스케줄링 |
| kube-controller-manager | server | 컨트롤러 실행 |
| containerd | node-0, node-1 | 컨테이너 런타임 |
| kubelet | node-0, node-1 | 노드 에이전트 |
| kube-proxy | node-0, node-1 | 네트워크 프록시 |

<br>

# 개인적인 소회

그냥 따라하면 되겠지 싶었지만, 일주일 꼬박 걸렸다. 도대체 쿠버네티스란 어떤 것인가.

뿌듯하긴 하지만, 솔직히 모르는 개념도 많고 꽤나 힘들었다. 정말 Hard Way가 왜 Hard Way인지 알겠다.

다른 무엇보다 인증과 네트워크 설정이 어려웠다. 비대칭키 인증을 이해했다고 생각했는데도, 왜 컴포넌트 구동 시에 `ca-file`, `client-key`, `client-cert` 이런 옵션이 들어가는지, `service-account-signing-key-file`은 무엇인지 한참동안 계속 생각해야 했다.

네트워크 대역도 헷갈렸다. 노드 대역(192.168.10.0/24), PodCIDR(10.200.0.0/24, 10.200.1.0/24), ServiceCIDR(10.32.0.0/24)이 각각 어떤 용도이고 어떻게 연결되는지 파악하는 데 시간이 걸렸다.

그래도 직접 손으로 구성해보니 kubeadm이나 managed Kubernetes가 얼마나 많은 복잡성을 감춰주는지 체감할 수 있었다. 클러스터가 "그냥 동작하는" 것이 아니라 수많은 인증서, 설정 파일, 네트워크 규칙이 맞물려 돌아간다는 것을 알게 되었다.

<br>

# 앞으로

솔직히 프로덕션 환경에서 이렇게 한땀한땀 클러스터를 구성할 일은 거의 없다. 대부분 kubeadm, EKS, GKE 같은 도구나 managed 서비스를 사용한다. 그렇다면 나는 앞으로 이 경험을 어떻게 활용할 것인가.

## 트러블슈팅 직관

클러스터에 문제가 생겼을 때 "어디를 봐야 하는지" 감이 생긴다. 예를 들어:

- Pod가 Pending 상태로 멈춰 있다면? kube-scheduler 로그를 확인하거나, 노드의 kubelet 상태를 점검
- Service로 접근이 안 된다면? kube-proxy가 정상 동작하는지, iptables 규칙이 제대로 생성되었는지 확인
- 노드가 NotReady 상태라면? kubelet의 인증서가 만료되었는지, API Server와 통신이 되는지 점검

컴포넌트 간 관계를 알아야 문제의 원인을 좁힐 수 있다.

## 인증서 관련 장애 대응

실무에서 가장 흔한 클러스터 장애 중 하나가 인증서 만료다. 이번 실습에서 배운 내용을 바탕으로 인증서 만료 문제가 나타났을 때 당황하지 않을 것이다.

- 어떤 인증서가 어떤 통신에 사용되는지 파악 가능
- `openssl x509 -in cert.pem -noout -dates`로 만료일 확인
- kubeconfig 파일 내 인증서 갱신 방법 이해
- CA 인증서와 클라이언트 인증서의 관계 파악

## Bastion Host 패턴과 폐쇄망 환경

실습에서 jumpbox를 통해 클러스터를 관리한 것처럼, 실무에서도 보안상 직접 Control Plane에 접근하지 않고 Bastion Host(점프 서버)를 경유하는 경우가 많다. 특히 **폐쇄망(Air-gapped) 환경**에서 클러스터를 운영해야 한다면, 이번 실습 경험이 더욱 값지다.

폐쇄망 환경에서는 외부 인터넷 접근이 차단되어 있어서, 다음과 같은 문제가 빈번히 발생한다.

- **컨테이너 이미지**: Docker Hub, GCR 등 외부 레지스트리 사용 불가. 내부 Private Registry를 구축하고 필요한 이미지를 미러링해야 함
- **바이너리 설치**: `apt install`이나 `curl`로 외부에서 다운로드 불가. 이번 실습처럼 바이너리를 직접 복사하고 배치하는 방식이 실제로 필요
- **인증서 관리**: Let's Encrypt 같은 외부 CA 사용 불가. 자체 CA를 운영하고 인증서를 직접 발급해야 함 (이번 실습에서 한 것처럼)
- **Bastion Host 필수**: 클러스터에 접근할 수 있는 유일한 경로. jumpbox에서 했던 것처럼 여기서 모든 관리 작업 수행



이번 실습에서 경험한 것들이 폐쇄망 환경에서 그대로 적용된다:

| Hard Way 실습 | 폐쇄망 환경 적용 |
| --- | --- |
| jumpbox에서 바이너리를 scp로 배포 | 내부망 배포 서버에서 노드로 패키지 배포 |
| 자체 CA 구축 및 인증서 발급 | 내부 PKI 인프라 운영, 인증서 수동 관리 |
| /etc/hosts로 DNS 설정 | 내부 DNS 서버 또는 hosts 파일 관리 |
| kubeconfig 파일 직접 생성 및 배포 | 사용자별 kubeconfig 수동 발급 |
| containerd, kubelet 바이너리 직접 설치 | 내부 저장소에서 바이너리 배포 |

Managed Kubernetes(EKS, GKE)는 인터넷 연결을 전제로 하기 때문에 폐쇄망에서는 사용하기 어렵다. 결국 kubeadm이나 직접 구성 방식을 사용하게 되는데, 이때 "내부에서 뭘 어떻게 해야 하는지" 아는 것이 중요하다.

특히 폐쇄망에서 클러스터 장애가 발생하면 구글 검색도, Stack Overflow도 볼 수 없다. 문서를 미리 다운받아두거나, 내부 구조를 머릿속에 가지고 있어야 한다. 이번 실습이 바로 그 "머릿속 지도"를 그리는 과정이었다.

## 네트워크 디버깅

Pod 간 통신이 안 될 때:

- `ip route`로 라우팅 테이블 확인
- `brctl show`로 CNI 브릿지 상태 점검
- PodCIDR, ServiceCIDR, 노드 대역 간의 관계 이해

이런 저수준 네트워크 구조를 알아야 "어디서 패킷이 막히는지" 파악할 수 있다.

## etcd 백업/복구

etcd가 클러스터의 모든 상태를 저장한다는 것을 알았으니:

- 정기적인 etcd 스냅샷 백업의 중요성 인식
- 클러스터 복구 시 etcd 데이터가 핵심이라는 점 이해
- `etcdctl snapshot save/restore` 명령어 활용

결국 Hard Way를 경험한 것은 "블랙박스를 열어본 것"이다. 문제가 생겼을 때 내부 구조를 아는 것과 모르는 것의 차이는 크다. 

<br>

이번 경험을 통해 배운 것을 계속 생각하고, 실무에서 의식적으로 적용하려 노력할 것이다.


