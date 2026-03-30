---
title: "[EKS] EKS: Networking - 2. 실습 환경 구성 - 2. 확인"
excerpt: "배포된 EKS 클러스터의 네트워크 구성을 노드 수준에서 직접 확인하고, VPC CNI가 ENI와 보조 IP를 어떻게 관리하는지 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - Networking
  - VPC-CNI
  - ENI
  - kube-proxy
  - iptables
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-2
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 배포 직후 EKS 클러스터에는 **aws-node**(VPC CNI), **kube-proxy**, **coredns** 파드가 실행된다. aws-node과 kube-proxy는 **Host Network** 모드로 노드 IP를 그대로 사용하고, coredns만 별도 파드 IP를 받는다
- 파드 IP(`192.168.x.x`)가 노드 IP와 **동일한 VPC CIDR**에 속한다. 이것이 VPC CNI의 핵심 특징으로, 오버레이 CNI와의 결정적 차이다
- coredns가 배치된 노드에는 **ENI 2개**(ens5 + ens6)와 **veth pair**가 존재하고, 파드가 없는 노드에는 **ENI 1개**(ens5)만 있다. `WARM_ENI_TARGET=1`이라도 파드가 하나라도 있어야 추가 ENI가 붙는다
- IPAM 디버깅 엔드포인트(`localhost:61679`)로 ENI별 IP 할당 현황을 실시간 확인할 수 있다

<br>

# 노드 접속 준비

워커 노드에 SSH로 접속하기 위한 환경을 준비한다.

```bash
# EC2 인스턴스 목록 확인
aws ec2 describe-instances \
  --query "Reservations[*].Instances[*].{PublicIPAdd:PublicIpAddress,PrivateIPAdd:PrivateIpAddress,InstanceName:Tags[?Key=='Name']|[0].Value,Status:State.Name}" \
  --filters Name=instance-state-name,Values=running \
  --output table
```

```
---------------------------------------------------------------------
|                         DescribeInstances                         |
+-----------------------+-----------------+--------------+----------+
|     InstanceName      |  PrivateIPAdd   | PublicIPAdd  | Status   |
+-----------------------+-----------------+--------------+----------+
|  myeks-1nd-node-group |  192.168.4.12   |  3.35.7.241  |  running |
|  myeks-1nd-node-group |  192.168.0.152  |  3.35.238.88 |  running |
|  myeks-1nd-node-group |  192.168.9.102  |  3.39.9.127  |  running |
+-----------------------+-----------------+--------------+----------+
```

퍼블릭 IP를 변수로 지정하고 SSH config를 설정한다.

```bash
N1=3.35.7.241
N2=3.35.238.88
N3=3.39.9.127

# ~/.ssh/config에 추가
cat >> ~/.ssh/config <<'EOF'
Host w2-node-1
    HostName 3.35.7.241
    User ec2-user
    IdentityFile ~/.ssh/my-eks-keypair.pem

Host w2-node-2
    HostName 3.35.238.88
    User ec2-user
    IdentityFile ~/.ssh/my-eks-keypair.pem

Host w2-node-3
    HostName 3.39.9.127
    User ec2-user
    IdentityFile ~/.ssh/my-eks-keypair.pem
EOF
```

SSH 접속이 정상적으로 되는지 확인한다.

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do echo ">> node $i <<"; ssh $i hostname; echo; done
```

```
>> node w2-node-1 <<
ip-192-168-4-12.ap-northeast-2.compute.internal

>> node w2-node-2 <<
ip-192-168-0-152.ap-northeast-2.compute.internal

>> node w2-node-3 <<
ip-192-168-9-102.ap-northeast-2.compute.internal
```

노드 호스트명은 프라이빗 IP를 포함하는 AWS 내부 DNS 이름이다. 노드 1은 `192.168.4.12`, 노드 2는 `192.168.0.152`, 노드 3은 `192.168.9.102`다.

<br>

# 네트워크 구조 개요

이 실습 환경의 노드 네트워크 구조를 확인해 보자.

![실습 환경 노드 네트워크 구조]({{site.url}}/assets/images/eks-w2-networking-node-structure.png){: .align-center}

노드마다 파드 배치 상황에 따라 네트워크 구조가 달라진다.

**노드 1** (coredns 파드 있음) — 완전한 구조:

- **ENI0**(ens5): 주 IP `192.168.4.12/22`. 노드 자체의 기본 네트워크 인터페이스다
- **ENI1**(ens6): 주 IP `192.168.7.41/22`. VPC CNI(ipamd)가 파드 IP 확보를 위해 추가로 붙인 ENI다. t3.medium은 ENI당 [슬롯]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#슬롯-ip-관리의-기본-단위) 6개(주 IP 1개 + 보조 IP 5개)를 가지므로, 보조 IP 5개가 warm pool에 있다
- **veth pair**: `enifdec4b696ce@if3`(호스트 측) ↔ `eth0`(파드 측). coredns 파드의 네트워크 네임스페이스를 호스트에 연결한다
- **Host Network 파드**: aws-node, kube-proxy는 `hostNetwork: true`로 노드 IP를 그대로 사용한다

> `enifdec4b696ce@if3`에서 `@if3`은 peer veth가 위치한 네트워크 네임스페이스 내의 인터페이스 인덱스를 나타낸다. 파드 네임스페이스 안에서 `ip link`를 실행하면 해당 인덱스의 `eth0`이 호스트 측 veth와 짝을 이루는 것을 확인할 수 있다.

**노드 2** (일반 파드 없음) — 최소 구조:

- **ENI0**(ens5)만 존재한다. `WARM_ENI_TARGET=1`이 설정되어 있어 "여분 ENI 1개를 확보"해야 하지만, 일반 파드가 0개이므로 ENI0의 보조 IP 5개만으로 충분하다. 추가 ENI를 붙일 필요가 없는 상태다
- Host Network 파드(aws-node, kube-proxy)만 존재한다
- veth pair도 없다

**노드 3**은 노드 1과 동일한 구조다 (coredns가 배치되어 ens6과 veth pair가 있다).

<br>

# 기본 정보 확인

## 파드 구성

클러스터에 실행 중인 파드와 IP를 확인한다.

```bash
kubectl get pod -n kube-system -o=custom-columns=NAME:.metadata.name,IP:.status.podIP,STATUS:.status.phase
```

```
NAME                       IP              STATUS
aws-node-d56xl             192.168.0.152   Running
aws-node-j5xl2             192.168.9.102   Running
aws-node-xqf8f             192.168.4.12    Running
coredns-759c77bd6c-8b9vj   192.168.8.196   Running
coredns-759c77bd6c-9m46w   192.168.5.1     Running
kube-proxy-4z97s           192.168.4.12    Running
kube-proxy-zvgss           192.168.9.102   Running
kube-proxy-zzfzh           192.168.0.152   Running
```

여기서 두 가지를 확인할 수 있다.

### Host Network 파드

aws-node과 kube-proxy의 IP가 노드 IP와 동일하다. `hostNetwork: true`로 실행되어 노드의 네트워크 네임스페이스를 공유하기 때문이다.

| 파드 | IP | 비고 |
|------|-----|------|
| aws-node-xqf8f | 192.168.4.12 | = 노드 1 IP |
| aws-node-d56xl | 192.168.0.152 | = 노드 2 IP |
| aws-node-j5xl2 | 192.168.9.102 | = 노드 3 IP |
| kube-proxy-* | 각 노드 IP와 동일 | = 노드 IP |

### 파드 IP와 VPC CIDR

coredns 파드의 IP(`192.168.8.196`, `192.168.5.1`)가 노드와 동일한 `192.168.0.0/16` VPC CIDR에 속한다. 이것이 AWS VPC CNI의 핵심 특징이다. 오버레이 CNI(Calico, Flannel 등)에서는 파드에 `10.244.x.x` 같은 별도 대역을 부여하지만, VPC CNI는 VPC의 실제 IP를 사용하므로 NAT 없이 VPC 내 어디서든 파드에 직접 라우팅할 수 있다.

## kube-proxy 모드

kube-proxy의 프록시 모드를 확인한다.

```bash
kubectl describe cm -n kube-system kube-proxy-config
```

<details markdown="1">
<summary><b>kube-proxy-config 전체 출력</b></summary>

```yaml
apiVersion: kubeproxy.config.k8s.io/v1alpha1
bindAddress: 0.0.0.0
clientConnection:
  acceptContentTypes: ""
  burst: 10
  contentType: application/vnd.kubernetes.protobuf
  kubeconfig: /var/lib/kube-proxy/kubeconfig
  qps: 5
clusterCIDR: ""
configSyncPeriod: 15m0s
conntrack:
  maxPerCore: 32768
  min: 131072
  tcpCloseWaitTimeout: 1h0m0s
  tcpEstablishedTimeout: 24h0m0s
enableProfiling: false
healthzBindAddress: 0.0.0.0:10256
hostnameOverride: ""
iptables:
  masqueradeAll: false
  masqueradeBit: 14
  minSyncPeriod: 0s
  syncPeriod: 30s
ipvs:
  excludeCIDRs: null
  minSyncPeriod: 0s
  scheduler: ""
  syncPeriod: 30s
kind: KubeProxyConfiguration
metricsBindAddress: 0.0.0.0:10249
mode: "iptables"
nodePortAddresses: null
oomScoreAdj: -998
portRange: ""
```

</details>

`mode: "iptables"`로 설정되어 있다. kube-proxy가 Service → Pod 매핑을 iptables NAT 규칙으로 구현한다는 의미다. 주요 설정 항목은 다음과 같다.

| 설정 | 값 | 설명 |
|---|---|---|
| `conntrack.maxPerCore` | `32768` | CPU 코어당 최대 conntrack 테이블 엔트리 수 |
| `conntrack.tcpEstablishedTimeout` | `24h` | ESTABLISHED 상태 TCP 연결의 conntrack 유지 시간 |
| `conntrack.tcpCloseWaitTimeout` | `1h` | CLOSE_WAIT 상태 TCP 연결의 conntrack 유지 시간 |
| `iptables.masqueradeAll` | `false` | 모든 트래픽에 SNAT를 적용하지 않음. `clusterCIDR` 외부로 나가는 트래픽만 마스커레이드 |
| `iptables.masqueradeBit` | `14` | iptables fwmark에서 마스커레이드 마킹에 사용할 비트 위치 |
| `iptables.minSyncPeriod` | `0s` | iptables 규칙 최소 동기화 주기. `0`이면 Service/Endpoint 변경 즉시 동기화 |
| `iptables.syncPeriod` | `30s` | iptables 규칙 전체 재동기화 주기 |
| `mode` | `"iptables"` | 프록시 모드. `iptables`, `ipvs`, `nftables` 중 선택 |
| `oomScoreAdj` | `-998` | OOM Killer 우선순위. 값이 낮을수록 종료 우선순위가 낮아 보호됨 |

> 참고: **IPVS 모드 지원 중단**
> 
> Kubernetes v1.35부터 kube-proxy의 [IPVS 모드 지원이 중단](https://kubernetes.io/blog/2025/11/26/kubernetes-v1-35-sneak-peek/#deprecation-of-ipvs-mode-in-kube-proxy)될 예정이다 ([KEP-5495](https://github.com/kubernetes/enhancements/issues/5495)). 대안으로 [nftables 모드](https://kubernetes.io/docs/reference/networking/virtual-ips/#proxy-mode-nftables)가 권장된다. 이번 실습은 iptables 모드를 사용하므로 영향은 없다. iptables 모드의 성능 최적화에 대해서는 [Kubernetes 공식 문서](https://kubernetes.io/docs/reference/networking/virtual-ips/#optimizing-iptables-mode-performance)를, EKS에서의 IPVS 사용에 대해서는 [AWS Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/ipvs.html)를 참고하자.

## aws-node 환경 변수

aws-node(VPC CNI) 데몬셋의 환경 변수를 확인한다. VPC CNI의 동작을 제어하는 핵심 설정들이다.

```bash
kubectl get ds aws-node -n kube-system -owide
```

```
NAME       DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE   CONTAINERS                   IMAGES                                                                                                                                                                                    SELECTOR
aws-node   3         3         3       3            3           <none>          25m   aws-node,aws-eks-nodeagent   602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni:v1.21.1-eksbuild.5,602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon/aws-network-policy-agent:v1.3.1-eksbuild.1   k8s-app=aws-node
```

3개 노드 모두에 aws-node 데몬셋이 실행 중이다. 컨테이너가 2개(`aws-node`, `aws-eks-nodeagent`)인데, `aws-node`은 VPC CNI(ipamd) 본체이고, `aws-eks-nodeagent`는 Network Policy 에이전트다.

주요 환경 변수만 정리하면 다음과 같다.

| 환경 변수 | 값 | 설명 |
|-----------|-----|------|
| `WARM_ENI_TARGET` | `1` | 사용 중인 ENI 외에 **여유 ENI 1개**를 항상 확보 |
| `WARM_PREFIX_TARGET` | `1` | Prefix Delegation 모드에서 여유 prefix 수 (현재 미사용) |
| `AWS_VPC_K8S_CNI_VETHPREFIX` | `eni` | veth pair 호스트 측 이름 접두어 (`eniXXX@ifN` 형태) |
| `AWS_VPC_ENI_MTU` | `9001` | ENI의 MTU. EC2 Jumbo Frame 지원 |
| `ENABLE_PREFIX_DELEGATION` | `false` | Prefix Delegation 비활성화. Secondary IP 모드 사용 |
| `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` | `false` | Custom Networking 비활성화 |
| `AWS_VPC_K8S_CNI_EXTERNALSNAT` | `false` | VPC 외부 통신 시 노드 IP로 SNAT 수행 |

`WARM_ENI_TARGET=1`은 이전 포스트에서 Terraform으로 설정한 값이다. 현재 사용 중인 ENI 외에 1개의 ENI를 항상 미리 붙여 두라는 의미로, 새 파드가 생성되면 warm pool의 IP를 즉시 할당할 수 있다. 웜 풀 전략의 상세 동작과 `WARM_IP_TARGET`, `MINIMUM_IP_TARGET` 등 다른 전략과의 비교는 [VPC CNI 설정 - 웜 풀 전략]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#웜-풀-전략)을 참고하자. 이번 실습에서 확인하는 환경 변수들의 이론적 배경(Secondary IP vs Prefix Delegation, Custom Networking 등)도 같은 글의 [IP 할당 설정]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#ip-할당-설정)에서 다루고 있다.

<details markdown="1">
<summary><b>aws-node 전체 환경 변수</b></summary>

```bash
kubectl get ds aws-node -n kube-system -o json | jq '.spec.template.spec.containers[0].env'
```

```json
[
  { "name": "ADDITIONAL_ENI_TAGS", "value": "{}" },
  { "name": "ANNOTATE_POD_IP", "value": "false" },
  { "name": "AWS_VPC_CNI_NODE_PORT_SUPPORT", "value": "true" },
  { "name": "AWS_VPC_ENI_MTU", "value": "9001" },
  { "name": "AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG", "value": "false" },
  { "name": "AWS_VPC_K8S_CNI_EXTERNALSNAT", "value": "false" },
  { "name": "AWS_VPC_K8S_CNI_LOGLEVEL", "value": "DEBUG" },
  { "name": "AWS_VPC_K8S_CNI_LOG_FILE", "value": "/host/var/log/aws-routed-eni/ipamd.log" },
  { "name": "AWS_VPC_K8S_CNI_RANDOMIZESNAT", "value": "prng" },
  { "name": "AWS_VPC_K8S_CNI_VETHPREFIX", "value": "eni" },
  { "name": "AWS_VPC_K8S_PLUGIN_LOG_FILE", "value": "/var/log/aws-routed-eni/plugin.log" },
  { "name": "AWS_VPC_K8S_PLUGIN_LOG_LEVEL", "value": "DEBUG" },
  { "name": "CLUSTER_ENDPOINT", "value": "https://BC5D9DD98C53D848472F89889BAAB6F1.yl4.ap-northeast-2.eks.amazonaws.com" },
  { "name": "CLUSTER_NAME", "value": "myeks" },
  { "name": "DISABLE_INTROSPECTION", "value": "false" },
  { "name": "DISABLE_METRICS", "value": "false" },
  { "name": "DISABLE_NETWORK_RESOURCE_PROVISIONING", "value": "false" },
  { "name": "ENABLE_IMDS_ONLY_MODE", "value": "false" },
  { "name": "ENABLE_IPv4", "value": "true" },
  { "name": "ENABLE_IPv6", "value": "false" },
  { "name": "ENABLE_MULTI_NIC", "value": "false" },
  { "name": "ENABLE_POD_ENI", "value": "false" },
  { "name": "ENABLE_PREFIX_DELEGATION", "value": "false" },
  { "name": "ENABLE_SUBNET_DISCOVERY", "value": "true" },
  { "name": "NETWORK_POLICY_ENFORCING_MODE", "value": "standard" },
  { "name": "VPC_CNI_VERSION", "value": "v1.21.1" },
  { "name": "VPC_ID", "value": "vpc-0c8f9d6d4b8038dd1" },
  { "name": "WARM_ENI_TARGET", "value": "1" },
  { "name": "WARM_PREFIX_TARGET", "value": "1" }
]
```

</details>

<details markdown="1">
<summary><b>kubectl describe daemonset aws-node 전체 출력</b></summary>

```
Name:           aws-node
Namespace:      kube-system
Selector:       k8s-app=aws-node
Node-Selector:  <none>
Labels:         app.kubernetes.io/instance=aws-vpc-cni
                app.kubernetes.io/managed-by=Helm
                app.kubernetes.io/name=aws-node
                app.kubernetes.io/version=v1.21.1
                helm.sh/chart=aws-vpc-cni-1.21.1
                k8s-app=aws-node
Annotations:    deprecated.daemonset.template.generation: 1
Desired Number of Nodes Scheduled: 3
Current Number of Nodes Scheduled: 3
Number of Nodes Scheduled with Up-to-date Pods: 3
Number of Nodes Scheduled with Available Pods: 3
Number of Nodes Misscheduled: 0
Pods Status:  3 Running / 0 Waiting / 0 Succeeded / 0 Failed
Pod Template:
  Labels:           app.kubernetes.io/instance=aws-vpc-cni
                    app.kubernetes.io/name=aws-node
                    k8s-app=aws-node
  Service Account:  aws-node
  Init Containers:
   aws-vpc-cni-init:
    Image:      602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni-init:v1.21.1-eksbuild.5
    Port:       <none>
    Host Port:  <none>
    Requests:
      cpu:  25m
    Environment:
      DISABLE_TCP_EARLY_DEMUX:  false
      ENABLE_IPv6:              false
    Mounts:
      /host/opt/cni/bin from cni-bin-dir (rw)
  Containers:
   aws-node:
    Image:      602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni:v1.21.1-eksbuild.5
    Port:       61678/TCP (metrics)
    Host Port:  0/TCP (metrics)
    Requests:
      cpu:      25m
    Liveness:   exec [/app/grpc-health-probe -addr=:50051 -connect-timeout=5s -rpc-timeout=5s] delay=60s timeout=10s period=10s #success=1 #failure=3
    Readiness:  exec [/app/grpc-health-probe -addr=:50051 -connect-timeout=5s -rpc-timeout=5s] delay=1s timeout=10s period=10s #success=1 #failure=3
    Mounts:
      /host/etc/cni/net.d from cni-net-dir (rw)
      /host/opt/cni/bin from cni-bin-dir (rw)
      /host/var/log/aws-routed-eni from log-dir (rw)
      /run/xtables.lock from xtables-lock (rw)
      /var/run/aws-node from run-dir (rw)
   aws-eks-nodeagent:
    Image:      602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon/aws-network-policy-agent:v1.3.1-eksbuild.1
    Port:       8162/TCP (agentmetrics)
    Host Port:  0/TCP (agentmetrics)
    Args:
      --enable-ipv6=false
      --enable-network-policy=false
      --enable-cloudwatch-logs=false
      --enable-policy-event-logs=false
      --log-file=/var/log/aws-routed-eni/network-policy-agent.log
      --metrics-bind-addr=:8162
      --health-probe-bind-addr=:8163
      --conntrack-cache-cleanup-period=300
      --log-level=debug
    Requests:
      cpu:  25m
    Mounts:
      /host/opt/cni/bin from cni-bin-dir (rw)
      /sys/fs/bpf from bpf-pin-path (rw)
      /var/log/aws-routed-eni from log-dir (rw)
      /var/run/aws-node from run-dir (rw)
  Volumes:
   bpf-pin-path:
    Type:          HostPath (bare host directory volume)
    Path:          /sys/fs/bpf
   cni-bin-dir:
    Type:          HostPath (bare host directory volume)
    Path:          /opt/cni/bin
   cni-net-dir:
    Type:          HostPath (bare host directory volume)
    Path:          /etc/cni/net.d
   log-dir:
    Type:          HostPath (bare host directory volume)
    Path:          /var/log/aws-routed-eni
    HostPathType:  DirectoryOrCreate
   run-dir:
    Type:          HostPath (bare host directory volume)
    Path:          /var/run/aws-node
    HostPathType:  DirectoryOrCreate
   xtables-lock:
    Type:               HostPath (bare host directory volume)
    Path:               /run/xtables.lock
    HostPathType:       FileOrCreate
  Priority Class Name:  system-node-critical
  Node-Selectors:       <none>
  Tolerations:          op=Exists
Events:
  Type    Reason            Age   From                  Message
  ----    ------            ----  ----                  -------
  Normal  SuccessfulCreate  24m   daemonset-controller  Created pod: aws-node-xqf8f
  Normal  SuccessfulCreate  24m   daemonset-controller  Created pod: aws-node-j5xl2
  Normal  SuccessfulCreate  24m   daemonset-controller  Created pod: aws-node-d56xl
```

</details>

<br>

# 노드 네트워크 상세

## 네트워크 인터페이스

각 노드의 네트워크 인터페이스를 확인한다.

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do echo ">> node $i <<"; ssh $i sudo ip -br -c addr; echo; done
```

```
>> node w2-node-1 <<
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens5             UP             192.168.4.12/22 metric 512 fe80::4dc:41ff:fe7e:4b63/64
enifdec4b696ce@if3 UP             fe80::cc95:7bff:fe38:fb50/64
ens6             UP             192.168.7.41/22 fe80::49f:54ff:fee3:4edd/64

>> node w2-node-2 <<
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens5             UP             192.168.0.152/22 metric 512 fe80::9:e9ff:fe32:9d7b/64

>> node w2-node-3 <<
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens5             UP             192.168.9.102/22 metric 512 fe80::894:43ff:fe87:a687/64
enic285aa78f9a@if3 UP             fe80::c8e5:bcff:fe98:9e09/64
ens6             UP             192.168.9.176/22 fe80::833:cfff:fe48:fe09/64
```

노드별 차이가 명확하다.

- **노드 1, 3** (coredns 파드 있음): `ens5`, `ens6` 존재. 일반 파드가 있으므로 추가 ENI가 필요
  - `ens5`: ENI0의 주 IP. 노드 자체의 기본 네트워크 인터페이스
  - `eniXXX@if3`: coredns 파드와 연결된 veth pair의 호스트 측.`AWS_VPC_K8S_CNI_VETHPREFIX=eni`에 의해 `eni` 접두어가 붙음
  - `ens6`: ENI1. ipamd가 추가로 붙인 ENI. 보조 IP를 통해 파드에 IP를 제공

- **노드 2** (일반 파드 없음): `ens5`만 존재. 일반 파드가 없으므로 추가 ENI나 veth pair가 필요하지 않음

<details markdown="1">
<summary><b>ip addr 상세 출력 (노드 1)</b></summary>

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute
       valid_lft forever preferred_lft forever
2: ens5: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc mq state UP group default qlen 1000
    link/ether 06:dc:41:7e:4b:63 brd ff:ff:ff:ff:ff:ff
    altname enp0s5
    inet 192.168.4.12/22 metric 512 brd 192.168.7.255 scope global dynamic ens5
       valid_lft 3457sec preferred_lft 3457sec
    inet6 fe80::4dc:41ff:fe7e:4b63/64 scope link proto kernel_ll
       valid_lft forever preferred_lft forever
3: enifdec4b696ce@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc noqueue state UP group default
    link/ether ce:95:7b:38:fb:50 brd ff:ff:ff:ff:ff:ff link-netns cni-a24612c8-f50a-f583-2169-9bd0cba99aeb
    inet6 fe80::cc95:7bff:fe38:fb50/64 scope link proto kernel_ll
       valid_lft forever preferred_lft forever
4: ens6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc mq state UP group default qlen 1000
    link/ether 06:9f:54:e3:4e:dd brd ff:ff:ff:ff:ff:ff
    altname enp0s6
    inet 192.168.7.41/22 brd 192.168.7.255 scope global ens6
       valid_lft forever preferred_lft forever
    inet6 fe80::49f:54ff:fee3:4edd/64 scope link proto kernel_ll
       valid_lft forever preferred_lft forever
```

veth pair의 `link-netns cni-a24612c8-f50a-f583-2169-9bd0cba99aeb`는 coredns 파드의 네트워크 네임스페이스를 가리킨다. ens5와 ens6 모두 MTU가 `9001`(Jumbo Frame)인 것도 확인할 수 있다.

</details>

## 라우팅 테이블

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do echo ">> node $i <<"; ssh $i sudo ip -c route; echo; done
```

```
>> node w2-node-1 <<
default via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.0.2 via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.4.0/22 dev ens5 proto kernel scope link src 192.168.4.12 metric 512
192.168.4.1 dev ens5 proto dhcp scope link src 192.168.4.12 metric 512
192.168.5.1 dev enifdec4b696ce scope link

>> node w2-node-2 <<
default via 192.168.0.1 dev ens5 proto dhcp src 192.168.0.152 metric 512
192.168.0.0/22 dev ens5 proto kernel scope link src 192.168.0.152 metric 512
192.168.0.1 dev ens5 proto dhcp scope link src 192.168.0.152 metric 512
192.168.0.2 dev ens5 proto dhcp scope link src 192.168.0.152 metric 512

>> node w2-node-3 <<
default via 192.168.8.1 dev ens5 proto dhcp src 192.168.9.102 metric 512
192.168.0.2 via 192.168.8.1 dev ens5 proto dhcp src 192.168.9.102 metric 512
192.168.8.0/22 dev ens5 proto kernel scope link src 192.168.9.102 metric 512
192.168.8.1 dev ens5 proto dhcp scope link src 192.168.9.102 metric 512
192.168.8.196 dev enic285aa78f9a scope link
```

핵심은 마지막 라우팅 엔트리다.

- 노드 1: `192.168.5.1 dev enifdec4b696ce scope link` → coredns 파드 IP(`192.168.5.1`)로 향하는 트래픽을 veth pair로 전달
- 노드 3: `192.168.8.196 dev enic285aa78f9a scope link` → coredns 파드 IP(`192.168.8.196`)로 향하는 트래픽을 veth pair로 전달
- 노드 2: 파드가 없으므로 이런 엔트리가 없다

VPC CNI는 파드가 생성될 때마다 해당 파드 IP에 대한 host-scope 라우트를 추가한다. 이 라우트가 호스트 네트워크 네임스페이스에서 파드 네임스페이스 안으로 트래픽을 전달하는 핵심 경로다.

## iptables NAT 규칙

iptables NAT 테이블을 확인한다. kube-proxy가 생성한 Service 규칙과 VPC CNI가 생성한 SNAT 규칙이 공존한다.

```bash
ssh w2-node-1 sudo iptables -t nat -S
```

<details markdown="1">
<summary><b>iptables -t nat -S 전체 출력</b></summary>

```
-P PREROUTING ACCEPT
-P INPUT ACCEPT
-P OUTPUT ACCEPT
-P POSTROUTING ACCEPT
-N AWS-CONNMARK-CHAIN-0
-N AWS-SNAT-CHAIN-0
-N KUBE-KUBELET-CANARY
-N KUBE-MARK-MASQ
-N KUBE-NODEPORTS
-N KUBE-POSTROUTING
-N KUBE-PROXY-CANARY
-N KUBE-SEP-2N3JDGAKOBPFSD4A
-N KUBE-SEP-CEMFOZLTYAJH5UDS
-N KUBE-SEP-HOKCJAFUAG3GHP6G
-N KUBE-SEP-HWXGIH65P2ISZIII
-N KUBE-SEP-MPQZI6WE5BDSIZOZ
-N KUBE-SEP-NUTL4QCULNUI7OTY
-N KUBE-SEP-OF5PR7X6L6ES6TUS
-N KUBE-SEP-XYDDOFWXZXQGZRSQ
-N KUBE-SEP-YNNS5I3UHCGZ6ZUH
-N KUBE-SERVICES
-N KUBE-SVC-ERIFXISQEP7F7OF4
-N KUBE-SVC-I7SKRZYQ7PWYV5X7
-N KUBE-SVC-JD5MR3NA4I4DYORP
-N KUBE-SVC-NPX46M4PTMTKRN6Y
-N KUBE-SVC-TCOU7JCQXEZGVUNU
-A PREROUTING -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
-A PREROUTING -i eni+ -m comment --comment "AWS, outbound connections" -j AWS-CONNMARK-CHAIN-0
-A PREROUTING -m comment --comment "AWS, CONNMARK" -j CONNMARK --restore-mark --nfmask 0x80 --ctmask 0x80
-A OUTPUT -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
-A POSTROUTING -m comment --comment "kubernetes postrouting rules" -j KUBE-POSTROUTING
-A POSTROUTING -m comment --comment "AWS SNAT CHAIN" -j AWS-SNAT-CHAIN-0
-A AWS-CONNMARK-CHAIN-0 -d 192.168.0.0/16 -m comment --comment "AWS CONNMARK CHAIN, VPC CIDR" -j RETURN
-A AWS-CONNMARK-CHAIN-0 -m comment --comment "AWS, CONNMARK" -j CONNMARK --set-xmark 0x80/0x80
-A AWS-SNAT-CHAIN-0 -d 192.168.0.0/16 -m comment --comment "AWS SNAT CHAIN" -j RETURN
-A AWS-SNAT-CHAIN-0 ! -o vlan+ -m comment --comment "AWS, SNAT" -m addrtype ! --dst-type LOCAL -j SNAT --to-source 192.168.4.12 --random-fully
-A KUBE-MARK-MASQ -j MARK --set-xmark 0x4000/0x4000
-A KUBE-POSTROUTING -m mark ! --mark 0x4000/0x4000 -j RETURN
-A KUBE-POSTROUTING -j MARK --set-xmark 0x4000/0x0
-A KUBE-POSTROUTING -m comment --comment "kubernetes service traffic requiring SNAT" -j MASQUERADE --random-fully
-A KUBE-SEP-HOKCJAFUAG3GHP6G -s 192.168.5.1/32 -m comment --comment "kube-system/kube-dns:dns" -j KUBE-MARK-MASQ
-A KUBE-SEP-HOKCJAFUAG3GHP6G -p udp -m comment --comment "kube-system/kube-dns:dns" -m udp -j DNAT --to-destination 192.168.5.1:53
-A KUBE-SEP-OF5PR7X6L6ES6TUS -s 192.168.8.196/32 -m comment --comment "kube-system/kube-dns:dns" -j KUBE-MARK-MASQ
-A KUBE-SEP-OF5PR7X6L6ES6TUS -p udp -m comment --comment "kube-system/kube-dns:dns" -m udp -j DNAT --to-destination 192.168.8.196:53
-A KUBE-SERVICES -d 10.100.0.1/32 -p tcp -m comment --comment "default/kubernetes:https cluster IP" -m tcp --dport 443 -j KUBE-SVC-NPX46M4PTMTKRN6Y
-A KUBE-SERVICES -d 10.100.253.10/32 -p tcp -m comment --comment "kube-system/eks-extension-metrics-api:metrics-api cluster IP" -m tcp --dport 443 -j KUBE-SVC-I7SKRZYQ7PWYV5X7
-A KUBE-SERVICES -d 10.100.0.10/32 -p udp -m comment --comment "kube-system/kube-dns:dns cluster IP" -m udp --dport 53 -j KUBE-SVC-TCOU7JCQXEZGVUNU
-A KUBE-SERVICES -d 10.100.0.10/32 -p tcp -m comment --comment "kube-system/kube-dns:dns-tcp cluster IP" -m tcp --dport 53 -j KUBE-SVC-ERIFXISQEP7F7OF4
-A KUBE-SERVICES -d 10.100.0.10/32 -p tcp -m comment --comment "kube-system/kube-dns:metrics cluster IP" -m tcp --dport 9153 -j KUBE-SVC-JD5MR3NA4I4DYORP
-A KUBE-SERVICES -m comment --comment "kubernetes service nodeports; NOTE: this must be the last rule in this chain" -m addrtype --dst-type LOCAL -j KUBE-NODEPORTS
-A KUBE-SVC-TCOU7JCQXEZGVUNU -m comment --comment "kube-system/kube-dns:dns -> 192.168.5.1:53" -m statistic --mode random --probability 0.50000000000 -j KUBE-SEP-HOKCJAFUAG3GHP6G
-A KUBE-SVC-TCOU7JCQXEZGVUNU -m comment --comment "kube-system/kube-dns:dns -> 192.168.8.196:53" -j KUBE-SEP-OF5PR7X6L6ES6TUS
```

</details>

[kubeadm 환경에서의 iptables 분석]({% post_url 2026-01-18-Kubernetes-Networking-Linux-Stack %})에서 다뤘듯이, iptables NAT 규칙은 **kube-proxy**와 **CNI** 두 컴포넌트가 각자의 목적에 맞게 생성한다. EKS 환경에서도 이 구조는 동일하지만, CNI 부분이 Flannel 대신 VPC CNI로 바뀌면서 체인 이름과 SNAT 동작이 달라진다.

| 구분 | kube-proxy | Flannel (kubeadm) | VPC CNI (EKS) |
|------|------------|-------------------|---------------|
| **목적** | Service → Pod 라우팅 | Pod 오버레이 네트워크 SNAT | Pod → VPC 외부 SNAT |
| **nat 체인** | `KUBE-SERVICES`, `KUBE-SVC-*`, `KUBE-SEP-*` | `FLANNEL-POSTRTG` | `AWS-SNAT-CHAIN-0`, `AWS-CONNMARK-CHAIN-0` |
| **SNAT 대상** | — | Pod CIDR(`10.244.0.0/16`) → 노드 IP | **VPC 외부 트래픽만** → 노드 IP |
| **SNAT 방식** | — | `MASQUERADE` | `SNAT --to-source <노드IP>` |

kube-proxy가 생성하는 `KUBE-SERVICES` → `KUBE-SVC-*` → `KUBE-SEP-*` 체인 구조는 kubeadm이든 EKS든 동일하다. Service ClusterIP를 Pod IP로 DNAT하는 역할이기 때문이다.

차이가 나는 것은 **CNI가 생성하는 SNAT 규칙**이다. Flannel은 오버레이 네트워크(10.244.0.0/16)의 파드가 외부로 통신할 때 `MASQUERADE`로 노드 IP를 입힌다. 파드 IP가 VPC에서 라우팅 불가능한 가상 IP이므로 반드시 노드 IP로 변환해야 응답이 돌아올 수 있기 때문이다. 반면 VPC CNI에서는 파드 IP 자체가 VPC의 실제 IP이므로, **VPC 내부 통신에는 SNAT가 필요 없다**. VPC 외부로 나가는 트래픽에만 노드 IP로 SNAT한다.

주요 규칙만 살펴보면 다음과 같다.

**KUBE-SERVICES** (kube-proxy가 생성):

```
-A KUBE-SERVICES -d 10.100.0.10/32 -p udp --dport 53 -j KUBE-SVC-TCOU7JCQXEZGVUNU

-A KUBE-SVC-TCOU7JCQXEZGVUNU --probability 0.50000000000 -j KUBE-SEP-HOKCJAFUAG3GHP6G
-A KUBE-SVC-TCOU7JCQXEZGVUNU -j KUBE-SEP-OF5PR7X6L6ES6TUS

-A KUBE-SEP-HOKCJAFUAG3GHP6G -p udp -j DNAT --to-destination 192.168.5.1:53
-A KUBE-SEP-OF5PR7X6L6ES6TUS -p udp -j DNAT --to-destination 192.168.8.196:53
```

ClusterIP `10.100.0.10:53`(kube-dns Service)으로 들어오는 DNS 트래픽을 KUBE-SVC 체인으로 분기하고, 50% 확률로 coredns 파드 2개(`192.168.5.1:53`, `192.168.8.196:53`)에 DNAT한다. 체인 이름이나 확률 기반 로드밸런싱 구조 모두 kubeadm 환경의 kube-proxy와 동일하다.

**AWS-SNAT-CHAIN-0** (VPC CNI가 생성):

```
-A AWS-SNAT-CHAIN-0 -d 192.168.0.0/16 -j RETURN
-A AWS-SNAT-CHAIN-0 ! -o vlan+ -m addrtype ! --dst-type LOCAL -j SNAT --to-source 192.168.4.12 --random-fully
```

Flannel의 `FLANNEL-POSTRTG`에 해당하는 역할이지만, 동작이 다르다. 첫 번째 규칙에서 VPC CIDR(`192.168.0.0/16`) 대상 트래픽은 즉시 `RETURN`하여 SNAT 없이 통과시킨다. 파드 IP가 VPC의 실제 IP이므로 VPC 내부에서는 원본 IP 그대로 라우팅이 가능하기 때문이다. 두 번째 규칙에서 VPC 외부로 나가는 트래픽만 노드 IP(`192.168.4.12`)로 SNAT한다. `AWS_VPC_K8S_CNI_EXTERNALSNAT=false`(기본값)일 때의 동작이다.

또한 VPC CNI는 `AWS-CONNMARK-CHAIN-0` 체인을 추가로 생성하여, 파드에서 나가는 트래픽(`eni+` 인터페이스 유래)에 connection mark(`0x80`)를 설정한다. 이 마크는 응답 패킷이 돌아왔을 때 올바른 ENI로 라우팅하기 위해 사용된다. Flannel에는 없는 VPC CNI 고유의 메커니즘이다.

## CNI 로그

VPC CNI의 로그 파일 구조를 확인한다.

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do echo ">> node $i <<"; ssh $i tree /var/log/aws-routed-eni; echo; done
```

```bash
>> node w2-node-1 <<
/var/log/aws-routed-eni
├── ebpf-sdk.log
├── egress-v6-plugin.log
├── ipamd.log
├── network-policy-agent.log
└── plugin.log

# plugin.log 없음
>> node w2-node-2 << 
/var/log/aws-routed-eni
├── ebpf-sdk.log
├── ipamd.log
└── network-policy-agent.log

>> node w2-node-3 <<
/var/log/aws-routed-eni
├── ebpf-sdk.log
├── egress-v6-plugin.log
├── ipamd.log
├── network-policy-agent.log
└── plugin.log
```

네트워크 트러블슈팅 시 주로 확인할 로그는 두 가지다.

| 로그 파일 | 역할 | 기록 주체 |
|-----------|------|-----------|
| `ipamd.log` | ENI/IP 할당·해제 이력, warm pool 관리 | L-IPAM 데몬 (ipamd) |
| `plugin.log` | CNI ADD/DEL 이벤트, veth pair 설정 | CNI 플러그인 바이너리 |

ipamd는 장기 실행 데몬으로 ENI와 IP를 **미리 확보하고 관리**하는 역할을 하고, plugin은 kubelet이 파드를 생성/삭제할 때 **호출되는 바이너리**로 실제 네트워크 설정(veth 생성, 라우트 추가 등)을 수행한다. 둘의 역할이 다르므로 문제 유형에 따라 확인할 로그가 달라진다. IP 할당 관련 문제라면 `ipamd.log`, veth/라우트 설정 문제라면 `plugin.log`를 확인하면 된다.

노드 2에는 `plugin.log`가 없다. 일반 파드가 한 번도 스케줄링되지 않아 CNI ADD 이벤트가 발생하지 않았기 때문이다.

ipamd 로그에서 IP 풀 상태를 확인할 수 있다.

```json
{
  "level": "debug",
  "ts": "2026-03-28T15:08:23.319Z",
  "caller": "ipamd/ipamd.go:765",
  "msg": "IP stats for Network Card 0 - total IPs: 10, assigned IPs: 1, cooldown IPs: 0"
}
```

`total IPs: 10`은 ENI 2개 x 보조 IP 5개 = 10개, `assigned IPs: 1`은 coredns 파드에 할당된 IP 1개를 의미한다. 이 수치는 아래에서 EC2 콘솔과 IPAM 디버깅 엔드포인트로 교차 검증한다.

<details markdown="1">
<summary><b>plugin.log 샘플 (노드 1, coredns CNI ADD)</b></summary>

```json
{
  "level": "info",
  "ts": "2026-03-28T14:39:05.085Z",
  "caller": "routed-eni-cni-plugin/cni.go:140",
  "msg": "Received CNI add request: ContainerID(d7721eee3b76...) Netns(/var/run/netns/cni-a24612c8-f50a-f583-2169-9bd0cba99aeb) IfName(eth0) Args(K8S_POD_NAMESPACE=kube-system;K8S_POD_NAME=coredns-759c77bd6c-9m46w;...)"
}
{
  "level": "info",
  "ts": "2026-03-28T14:39:05.092Z",
  "caller": "routed-eni-cni-plugin/cni.go:140",
  "msg": "Received add network response from ipamd ... Success:true IPAllocationMetadata:{IPv4Addr:\"192.168.5.1\" RouteTableId:254} VPCv4CIDRs:\"192.168.0.0/16\""
}
{
  "level": "debug",
  "ts": "2026-03-28T14:39:05.092Z",
  "caller": "routed-eni-cni-plugin/cni.go:279",
  "msg": "SetupPodNetwork: hostVethName=enifdec4b696ce, contVethName=eth0, netnsPath=/var/run/netns/cni-a24612c8-f50a-f583-2169-9bd0cba99aeb, ipAddr=192.168.5.1/32, routeTableNumber=254, mtu=9001"
}
{
  "level": "debug",
  "ts": "2026-03-28T14:39:05.139Z",
  "caller": "driver/driver.go:286",
  "msg": "Successfully setup container route, containerAddr=192.168.5.1/32, hostVeth=enifdec4b696ce, rtTable=main"
}
{
  "level": "debug",
  "ts": "2026-03-28T14:39:05.139Z",
  "caller": "driver/driver.go:286",
  "msg": "Successfully setup toContainer rule, containerAddr=192.168.5.1/32, rtTable=main"
}
```

CNI ADD 요청 → ipamd에서 IP(`192.168.5.1`) 할당 → veth pair 생성(`enifdec4b696ce` ↔ `eth0`) → 라우트 설정의 흐름이 로그로 확인된다.

</details>

<br>

# 콘솔 확인

## EC2 인스턴스 네트워크

EC2 콘솔에서 워커 노드 1(coredns가 배치된 노드)의 네트워크 정보를 확인한다.

인스턴스 요약에서 **프라이빗 IPv4 주소**가 2개인 것을 확인할 수 있다.

![EC2 인스턴스 상세 - 프라이빗 IPv4 주소 2개]({{site.url}}/assets/images/eks-w2-ec2-instance-detail.png){: .align-center}

- `192.168.4.12` = ENI0(ens5)의 주 IP
- `192.168.7.41` = ENI1(ens6)의 주 IP

네트워킹 탭을 클릭하면 각 ENI의 **보조 프라이빗 IPv4 주소**를 확인할 수 있다.

![EC2 네트워킹 탭 - 보조 프라이빗 IPv4 주소 목록]({{site.url}}/assets/images/eks-w2-ec2-instance-networking-tab.png){: .align-center}

ENI0에 보조 IP 5개, ENI1에 보조 IP 5개, 총 10개다. ipamd 로그의 `total IPs: 10`과 일치한다. t3.medium은 ENI당 최대 6개의 IPv4 주소(주 IP 1개 + 보조 IP 5개)를 가질 수 있으므로, 2개 ENI에서 확보 가능한 보조 IP 최대치인 10개가 모두 할당된 상태다.

## 네트워크 인터페이스(ENI)

EC2 콘솔의 네트워크 인터페이스 페이지에서 myeks로 필터링하면 전체 ENI 목록을 볼 수 있다.

![네트워크 인터페이스 목록 - 보조 프라이빗 IPv4 주소]({{site.url}}/assets/images/eks-w2-ec2-network-interfaces-list.png){: .align-center}

각 ENI의 기본 프라이빗 IPv4 주소와 보조 프라이빗 IPv4 주소를 한눈에 비교할 수 있다. 같은 인스턴스 ID를 가진 ENI 2개가 동일 EC2에 붙어 있는 것이다. ipamd가 warm pool로 보조 IP를 미리 확보하고 있다가, 파드가 스케줄링되면 할당한다.

주 ENI(DeviceNumber 0)와 VPC CNI가 추가한 ENI(DeviceNumber 1)는 **설명(Description) 필드**로 구분할 수 있다. 주 ENI의 설명은 비어 있거나 노드 그룹 이름이 들어 있고, VPC CNI가 동적으로 붙인 ENI에는 `aws-K8S-i-...` 형식의 설명이 자동으로 붙는다.

<br>

# 보조 IP 할당 확인

coredns 파드가 실제로 ENI의 보조 IP를 사용하는지 확인한다.

## coredns 파드 위치

```bash
kubectl get pod -n kube-system -l k8s-app=kube-dns -owide
```

```
NAME                       READY   STATUS    RESTARTS   AGE   IP              NODE                                               NOMINATED NODE   READINESS GATES
coredns-759c77bd6c-8b9vj   1/1     Running   0          74m   192.168.8.196   ip-192-168-9-102.ap-northeast-2.compute.internal   <none>           <none>
coredns-759c77bd6c-9m46w   1/1     Running   0          74m   192.168.5.1     ip-192-168-4-12.ap-northeast-2.compute.internal    <none>           <none>
```

- coredns `9m46w`: 노드 1(`192.168.4.12`)에 배치, 파드 IP `192.168.5.1`
- coredns `8b9vj`: 노드 3(`192.168.9.102`)에 배치, 파드 IP `192.168.8.196`
- 노드 2에는 coredns가 없다

앞서 확인한 라우팅 테이블의 `192.168.5.1 dev enifdec4b696ce`와 정확히 일치한다.

## IPAM 디버깅

VPC CNI의 IPAM 디버깅 엔드포인트(`localhost:61679`)를 통해 각 노드의 ENI별 IP 할당 현황을 실시간으로 확인할 수 있다.

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do
  echo ">> node $i <<"
  ssh $i curl -s http://localhost:61679/v1/enis | jq '.["0"] | {TotalIPs, AssignedIPs}'
  echo
done
```

```
>> node w2-node-1 <<
{
  "TotalIPs": 10,
  "AssignedIPs": 1
}

>> node w2-node-2 <<
{
  "TotalIPs": 5,
  "AssignedIPs": 0
}

>> node w2-node-3 <<
{
  "TotalIPs": 10,
  "AssignedIPs": 1
}
```

| 노드 | TotalIPs | AssignedIPs | ENI 수 | 이유 |
|------|----------|-------------|--------|------|
| 노드 1 | 10 | 1 | 2 (ens5 + ens6) | coredns 1개 → 보조 IP 1개 사용 |
| 노드 2 | 5 | 0 | 1 (ens5만) | 일반 파드 없음 → 추가 ENI 불필요 |
| 노드 3 | 10 | 1 | 2 (ens5 + ens6) | coredns 1개 → 보조 IP 1개 사용 |

노드 1의 상세 IPAM 데이터를 보면, coredns 파드에 할당된 IP를 정확히 확인할 수 있다.

<details markdown="1">
<summary><b>노드 1 IPAM 상세 데이터</b></summary>

```bash
ssh w2-node-1 curl -s http://localhost:61679/v1/enis | jq
```

```json
{
  "0": {
    "TotalIPs": 10,
    "AssignedIPs": 1,
    "ENIs": {
      "eni-04637c806b9ad599b": {
        "ID": "eni-04637c806b9ad599b",
        "IsPrimary": false,
        "DeviceNumber": 1,
        "AvailableIPv4Cidrs": {
          "192.168.4.164/32": { "IPAddresses": {} },
          "192.168.4.255/32": { "IPAddresses": {} },
          "192.168.5.7/32": { "IPAddresses": {} },
          "192.168.6.186/32": { "IPAddresses": {} },
          "192.168.7.54/32": { "IPAddresses": {} }
        }
      },
      "eni-0d3a675348ac2ee80": {
        "ID": "eni-0d3a675348ac2ee80",
        "IsPrimary": true,
        "DeviceNumber": 0,
        "AvailableIPv4Cidrs": {
          "192.168.4.248/32": { "IPAddresses": {} },
          "192.168.4.89/32": { "IPAddresses": {} },
          "192.168.5.1/32": {
            "IPAddresses": {
              "192.168.5.1": {
                "Address": "192.168.5.1",
                "IPAMMetadata": {
                  "k8sPodNamespace": "kube-system",
                  "k8sPodName": "coredns-759c77bd6c-9m46w"
                },
                "AssignedTime": "2026-03-28T14:39:05.088169145Z"
              }
            }
          },
          "192.168.5.190/32": { "IPAddresses": {} },
          "192.168.5.239/32": { "IPAddresses": {} }
        }
      }
    }
  }
}
```

</details>

<details markdown="1">
<summary><b>노드 2 IPAM 상세 데이터</b></summary>

```bash
ssh w2-node-2 curl -s http://localhost:61679/v1/enis | jq
```

```json
{
  "0": {
    "TotalIPs": 5,
    "AssignedIPs": 0,
    "ENIs": {
      "eni-084dd084d4ad1b250": {
        "ID": "eni-084dd084d4ad1b250",
        "IsPrimary": true,
        "DeviceNumber": 0,
        "AvailableIPv4Cidrs": {
          "192.168.0.30/32": { "IPAddresses": {} },
          "192.168.1.142/32": { "IPAddresses": {} },
          "192.168.2.151/32": { "IPAddresses": {} },
          "192.168.2.240/32": { "IPAddresses": {} },
          "192.168.3.62/32": { "IPAddresses": {} }
        }
      }
    }
  }
}
```

</details>

<details markdown="1">
<summary><b>노드 3 IPAM 상세 데이터</b></summary>

```bash
ssh w2-node-3 curl -s http://localhost:61679/v1/enis | jq
```

```json
{
  "0": {
    "TotalIPs": 10,
    "AssignedIPs": 1,
    "ENIs": {
      "eni-043f96bb77823049c": {
        "ID": "eni-043f96bb77823049c",
        "IsPrimary": false,
        "DeviceNumber": 1,
        "AvailableIPv4Cidrs": {
          "192.168.10.32/32": { "IPAddresses": {} },
          "192.168.11.161/32": { "IPAddresses": {} },
          "192.168.11.97/32": { "IPAddresses": {} },
          "192.168.9.129/32": { "IPAddresses": {} },
          "192.168.9.213/32": { "IPAddresses": {} }
        }
      },
      "eni-0e5343d24bb3fd568": {
        "ID": "eni-0e5343d24bb3fd568",
        "IsPrimary": true,
        "DeviceNumber": 0,
        "AvailableIPv4Cidrs": {
          "192.168.11.173/32": { "IPAddresses": {} },
          "192.168.11.195/32": { "IPAddresses": {} },
          "192.168.11.45/32": { "IPAddresses": {} },
          "192.168.8.196/32": {
            "IPAddresses": {
              "192.168.8.196": {
                "Address": "192.168.8.196",
                "IPAMMetadata": {
                  "k8sPodNamespace": "kube-system",
                  "k8sPodName": "coredns-759c77bd6c-8b9vj"
                },
                "AssignedTime": "2026-03-28T14:39:05.151004925Z"
              }
            }
          },
          "192.168.9.194/32": { "IPAddresses": {} }
        }
      }
    }
  }
}
```

</details>

노드 1의 Primary ENI(`DeviceNumber: 0`)에서 보조 IP `192.168.5.1`이 `coredns-759c77bd6c-9m46w` 파드에 할당되어 있다. 나머지 9개의 보조 IP는 warm pool에서 대기 중이다. 새 파드가 스케줄링되면 이 pool에서 즉시 IP를 받게 된다.

노드 2는 ENI 1개에 보조 IP 5개뿐이고 할당된 IP가 없다. 파드가 스케줄링되면 그때 보조 IP를 할당하고, 필요 시 추가 ENI도 붙일 것이다.

<br>

# 테스트 파드 배포

지금까지는 시스템 파드(coredns, aws-node, kube-proxy)만으로 네트워크 구조를 확인했다. aws-node과 kube-proxy는 Host Network이라 별도 IP를 쓰지 않고, coredns만 파드 IP를 사용하는 상태다.

[Network-MultiTool](https://github.com/Praqma/Network-MultiTool) 디플로이먼트(replicas: 3)를 배포하여 **일반 파드가 추가될 때 노드 네트워크에 어떤 변화가 일어나는지** 관찰한다. Network-MultiTool은 `curl`, `ping`, `traceroute`, `ip`, `dig` 등 네트워크 진단 도구가 내장된 경량 컨테이너 이미지로, 쿠버네티스 환경에서 네트워크 테스트에 자주 사용된다.

## 노드 모니터링 준비

파드 생성 시 노드에서 일어나는 변화를 실시간으로 관찰하기 위해, 각 노드에 SSH로 접속하여 모니터링을 시작한다.

```bash
# [터미널1] 노드 1 모니터링
ssh w2-node-1
watch -d "ip link | egrep 'ens|eni' ;echo;echo '[ROUTE TABLE]'; route -n | grep eni"

# [터미널2] 노드 2 모니터링
ssh w2-node-2
watch -d "ip link | egrep 'ens|eni' ;echo;echo '[ROUTE TABLE]'; route -n | grep eni"

# [터미널3] 노드 3 모니터링
ssh w2-node-3
watch -d "ip link | egrep 'ens|eni' ;echo;echo '[ROUTE TABLE]'; route -n | grep eni"
```

## 디플로이먼트 생성

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: netshoot-pod
spec:
  replicas: 3
  selector:
    matchLabels:
      app: netshoot-pod
  template:
    metadata:
      labels:
        app: netshoot-pod
    spec:
      containers:
      - name: netshoot-pod
        image: praqma/network-multitool
        ports:
        - containerPort: 80
        - containerPort: 443
        env:
        - name: HTTP_PORT
          value: "80"
        - name: HTTPS_PORT
          value: "443"
      terminationGracePeriodSeconds: 0
EOF
```

파드 이름을 변수로 지정해 두면 이후 실습에서 편하다.

```bash
PODNAME1=$(kubectl get pod -l app=netshoot-pod -o jsonpath='{.items[0].metadata.name}')
PODNAME2=$(kubectl get pod -l app=netshoot-pod -o jsonpath='{.items[1].metadata.name}')
PODNAME3=$(kubectl get pod -l app=netshoot-pod -o jsonpath='{.items[2].metadata.name}')
echo $PODNAME1 $PODNAME2 $PODNAME3
```

```
netshoot-pod-64fbf7fb5-bs2z6 netshoot-pod-64fbf7fb5-jbqff netshoot-pod-64fbf7fb5-wz7nl
```

```bash
kubectl get pod -o wide
```

```
NAME                           READY   STATUS    RESTARTS   AGE     IP               NODE                                               NOMINATED NODE   READINESS GATES
netshoot-pod-64fbf7fb5-bs2z6   1/1     Running   0          3m18s   192.168.2.151    ip-192-168-0-152.ap-northeast-2.compute.internal   <none>           <none>
netshoot-pod-64fbf7fb5-jbqff   1/1     Running   0          3m18s   192.168.4.248    ip-192-168-4-12.ap-northeast-2.compute.internal    <none>           <none>
netshoot-pod-64fbf7fb5-wz7nl   1/1     Running   0          3m18s   192.168.11.173   ip-192-168-9-102.ap-northeast-2.compute.internal   <none>           <none>
```

3개 파드가 각 노드에 하나씩 배치되었다. 각 파드는 VPC CIDR에서 실제 IP를 부여받았다.

## 네트워크 변화 확인

파드 생성 직후 모니터링 터미널에서 변화가 관찰된다. 각 노드에 veth pair(`eniY@ifN`)가 추가되고, 라우팅 테이블에 파드 IP 경로가 추가된다.

![테스트 파드 배포 시 노드 네트워크 변화]({{site.url}}/assets/images/eks-networking-deployment-result.gif){: .align-center}

특히 **노드 2**의 변화가 눈에 띈다. 이전까지 `ens5`만 있던 노드 2에 파드가 배치되면서 **ens6(추가 ENI)이 자동으로 올라오고**, veth pair도 생성된다.

여기서 주의할 점은, 이것이 IP 풀이 바닥나서 발생한 것이 **아니라는** 것이다. ENI0(ens5)에는 아직 보조 IP 4개가 남아 있다. 트리거는 [`WARM_ENI_TARGET`]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#전략-1-eni-단위--warm_eni_target)이다. 이 설정은 "사용 중이 아닌 **여유 ENI 수**"를 지정하는데, 파드 1개가 ENI0의 IP를 하나라도 사용하면 ENI0은 더 이상 "여유"로 취급되지 않는다. warm ENI 수가 0으로 떨어지고, `WARM_ENI_TARGET=1`을 다시 충족하기 위해 ipamd가 새 ENI를 붙이는 것이다. IP가 부족해서가 아니라 warm ENI target 조건이 깨졌기 때문에 발생하는 동작이다.

새 ENI가 붙는 메커니즘 자체는 [IP 풀 고갈 시 ENI 추가 확보]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#ip-풀-고갈-시-eni-추가-확보)에서 설명한 `CreateNetworkInterface` → `AttachNetworkInterface` → `AssignPrivateIpAddresses` 흐름과 동일하다. [설정별 실제 ENI/IP 소비 테이블]({% post_url 2026-03-19-Kubernetes-EKS-02-01-01-EKS-VPC-CNI %}#참고-설정별-실제-eniip-소비)에서 확인할 수 있듯, `WARM_ENI_TARGET=1`은 파드가 1개만 떠도 새 ENI를 통째로 붙이는 전략이다. 이로 인해 노드 2도 이제 ENI 2개에 보조 IP 10개를 갖게 된다.

라우팅 테이블에도 새 파드의 경로가 추가된다.

```bash
for i in w2-node-1 w2-node-2 w2-node-3; do echo ">> node $i <<"; ssh $i sudo ip -c route; echo; done
```

```
>> node w2-node-1 <<
default via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.0.2 via 192.168.4.1 dev ens5 proto dhcp src 192.168.4.12 metric 512
192.168.4.0/22 dev ens5 proto kernel scope link src 192.168.4.12 metric 512
192.168.4.1 dev ens5 proto dhcp scope link src 192.168.4.12 metric 512
192.168.4.248 dev eni31b43252b24 scope link
192.168.5.1 dev enifdec4b696ce scope link

>> node w2-node-2 <<
default via 192.168.0.1 dev ens5 proto dhcp src 192.168.0.152 metric 512
192.168.0.0/22 dev ens5 proto kernel scope link src 192.168.0.152 metric 512
192.168.0.1 dev ens5 proto dhcp scope link src 192.168.0.152 metric 512
192.168.0.2 dev ens5 proto dhcp scope link src 192.168.0.152 metric 512
192.168.2.151 dev eniac70eec268d scope link

>> node w2-node-3 <<
default via 192.168.8.1 dev ens5 proto dhcp src 192.168.9.102 metric 512
192.168.0.2 via 192.168.8.1 dev ens5 proto dhcp src 192.168.9.102 metric 512
192.168.8.0/22 dev ens5 proto kernel scope link src 192.168.9.102 metric 512
192.168.8.1 dev ens5 proto dhcp scope link src 192.168.9.102 metric 512
192.168.8.196 dev enic285aa78f9a scope link
192.168.11.173 dev eni73af7ba7811 scope link
```

이전과 비교하면 각 노드에 새 파드 IP 경로가 추가된 것을 확인할 수 있다.

- 노드 1: `192.168.4.248 dev eni31b43252b24` (netshoot-pod)가 기존 coredns 경로에 추가
- 노드 2: `192.168.2.151 dev eniac70eec268d` (netshoot-pod)가 새로 생성. 이전에는 파드 라우트가 전혀 없었다
- 노드 3: `192.168.11.173 dev eni73af7ba7811` (netshoot-pod)가 기존 coredns 경로에 추가

### 노드 네트워크 네임스페이스

노드 3에서 네트워크 네임스페이스를 확인하면, 파드별로 격리된 네트워크 네임스페이스가 존재하는 것을 볼 수 있다.

```bash
ssh w2-node-3 sudo lsns -t net
```

```
        NS TYPE NPROCS   PID USER     NETNSID NSFS                                                COMMAND
4026531840 net     119     1 root  unassigned                                                     /usr/lib/systemd/systemd --switched-root --system --
4026532210 net       2  3977 65535          0 /run/netns/cni-d5455b69-dc85-fedf-adf3-f6d0dd7b9cf9 /pause
4026532326 net       3 30688 65535          1 /run/netns/cni-f6c99138-c72d-6238-a84a-de30574ef6a8 /pause
4026532404 net       1 32708 root  unassigned                                                     /usr/lib/systemd/systemd-hostnamed
```

- `4026531840`: 호스트(Root) 네트워크 네임스페이스. 119개 프로세스가 공유한다 (systemd, aws-node, kube-proxy 등 Host Network 파드 포함)
- `4026532210`: coredns 파드의 네트워크 네임스페이스. `/pause` 컨테이너가 네임스페이스를 유지한다
- `4026532326`: netshoot-pod의 네트워크 네임스페이스. 마찬가지로 `/pause` 컨테이너가 유지

각 파드가 독립된 네트워크 네임스페이스를 가지며, veth pair로 호스트와 연결되는 구조를 다시 한번 확인할 수 있다.

<details markdown="1">
<summary><b>노드 3 네트워크 인터페이스 상세</b></summary>

```bash
ssh w2-node-3 ip -br -c addr show
```

```
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens5             UP             192.168.9.102/22 metric 512 fe80::894:43ff:fe87:a687/64
enic285aa78f9a@if3 UP             fe80::c8e5:bcff:fe98:9e09/64
ens6             UP             192.168.9.176/22 fe80::833:cfff:fe48:fe09/64
eni73af7ba7811@if3 UP             fe80::44b5:1eff:fec8:d19a/64
```

```bash
ssh w2-node-3 ip -c link
```

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: ens5: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 0a:94:43:87:a6:87 brd ff:ff:ff:ff:ff:ff
    altname enp0s5
3: enic285aa78f9a@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc noqueue state UP mode DEFAULT group default
    link/ether ca:e5:bc:98:9e:09 brd ff:ff:ff:ff:ff:ff link-netns cni-d5455b69-dc85-fedf-adf3-f6d0dd7b9cf9
4: ens6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 0a:33:cf:48:fe:09 brd ff:ff:ff:ff:ff:ff
    altname enp0s6
5: eni73af7ba7811@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc noqueue state UP mode DEFAULT group default
    link/ether 46:b5:1e:c8:d1:9a brd ff:ff:ff:ff:ff:ff link-netns cni-f6c99138-c72d-6238-a84a-de30574ef6a8
```

`enic285aa78f9a`는 coredns 파드의 네임스페이스(`cni-d5455b69...`)에, `eni73af7ba7811`은 netshoot-pod의 네임스페이스(`cni-f6c99138...`)에 각각 연결되어 있다.

</details>

## 파드 내부 네트워크 확인

파드 안에서 네트워크가 어떻게 구성되어 있는지 직접 확인한다.

```bash
kubectl exec -it $PODNAME1 -- ip -c addr
```

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host
       valid_lft forever preferred_lft forever
3: eth0@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9001 qdisc noqueue state UP group default
    link/ether fe:cc:8f:10:4f:d8 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    inet 192.168.2.151/32 scope global eth0
       valid_lft forever preferred_lft forever
    inet6 fe80::fccc:8fff:fe10:4fd8/64 scope link
       valid_lft forever preferred_lft forever
```

파드 안에서는 `lo`와 `eth0` 두 개의 인터페이스만 보인다. `eth0@if3`이 호스트 측 veth pair(`eniac70eec268d@if3`)의 짝이다. IP가 `/32`(호스트 라우트)로 할당되어 있는 점이 특징인데, VPC CNI가 point-to-point 방식으로 파드 IP를 설정하기 때문이다.

```bash
kubectl exec -it $PODNAME1 -- ip -c route
```

```
default via 169.254.1.1 dev eth0
169.254.1.1 dev eth0 scope link
```

파드의 기본 게이트웨이가 `169.254.1.1`(link-local 주소)이다. 이것은 실제 존재하는 IP가 아니라 VPC CNI가 사용하는 가상 게이트웨이다. 파드에서 나가는 모든 트래픽은 이 주소를 통해 veth pair의 호스트 측으로 전달되고, 호스트의 라우팅 테이블이 최종 목적지로 라우팅한다.

다른 노드의 파드에도 동일한 네트워크 구조가 적용되어 있다.

```bash
kubectl exec -it $PODNAME2 -- ip -br -c addr
```

```
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0@if5         UP             192.168.4.248/32 fe80::b4ae:e0ff:fe0e:6ff5/64
```

```bash
kubectl exec -it $PODNAME3 -- ip -br -c addr
```

```
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0@if5         UP             192.168.11.173/32 fe80::74b0:75ff:fe2a:51f9/64
```

파드 2, 3의 `eth0@if5`에서 인덱스가 `@if5`인 이유는, 해당 노드에 이미 coredns의 veth pair가 인덱스 3을 사용하고 있고, ens6이 인덱스 4를 사용하여 다음 인덱스인 5가 할당되었기 때문이다. 파드 1(노드 2)은 기존 veth가 없었으므로 `@if3`이다.

## 파드 간 통신 테스트

노드 2의 파드(192.168.2.151)에서 노드 1의 파드(192.168.4.248)로 ping을 보내 **크로스 노드 통신**이 되는지 확인한다.

```bash
kubectl exec -it $PODNAME1 -- ping -c 1 192.168.4.248
```

```
PING 192.168.4.248 (192.168.4.248) 56(84) bytes of data.
64 bytes from 192.168.4.248: icmp_seq=1 ttl=125 time=1.11 ms

--- 192.168.4.248 ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 1.114/1.114/1.114/0.000 ms
```

노드를 넘어가는 파드 간 통신이 정상적으로 동작한다. VPC CNI에서 파드 IP는 VPC의 실제 IP이므로, VPC 라우팅 패브릭이 별도의 오버레이 없이 직접 전달한다. `ttl=125`는 응답 패킷의 TTL이 초기값 127에서 2만큼 감소한 것으로, L3 라우터를 2번 거쳤다(2홉)는 의미다.

> **참고: TTL과 홉**
>
> **TTL**(Time To Live)은 IP 패킷 헤더의 수명 카운터다. 패킷이 **L3 라우터를 지날 때마다 1씩 감소**하고, 0이 되면 폐기된다. 라우팅 설정 오류로 패킷이 A → B → A → B로 무한 순환하는 것을 방지하기 위한 메커니즘이다. L2 전달(스위치, 브릿지, veth pair)은 TTL을 감소시키지 않는다. 패킷이 L3 라우팅 장비를 한 번 거치는 것을 **1홉(hop)**이라 하며, `초기 TTL - 수신 TTL = 홉 수`로 경유한 라우터 수를 역산할 수 있다.
>
> 초기 TTL은 [커널 파라미터]({% post_url 2026-03-18-CS-Linux-Kernel-Parameter %}) `net.ipv4.ip_default_ttl`로 결정되며, 배포판마다 기본값이 다르다:
>
> | OS | `net.ipv4.ip_default_ttl` |
> |----|--------------------------|
> | Linux 커널 기본 | 64 (RFC 1700 권장) |
> | Amazon Linux 2023 (AL2023) | **127** ([AL2023 커널 변경 사항](https://docs.aws.amazon.com/linux/al2023/ug/compare-with-al2-kernel.html)) |
> | Amazon Linux 2 (AL2) | 255 |
> | Windows | 128 |
>
> 이 실습 환경은 EKS AL2023 AMI(`AL2023_x86_64_STANDARD`)이므로 초기 TTL이 127이다. 파드 컨테이너는 별도의 네트워크 네임스페이스를 갖지만, [커널은 호스트와 공유]({% post_url 2026-03-18-CS-Linux-Kernel-Parameter %}#왜-커널-파라미터가-중요한가)하므로 호스트의 TTL 설정을 그대로 따른다. 따라서 `ttl=125`는 `127 - 125 = 2`홉, 즉 호스트 B의 L3 포워딩(1홉)과 VPC 라우터(1홉)를 거친 것이다.

<br>

# 정리

| 확인 항목 | 배포 전 (coredns만) | 배포 후 (+ netshoot-pod) |
|-----------|---------------------|------------------------|
| 노드 2 ENI | 1개 (ens5만) | 2개 (ens5 + ens6) |
| 노드 2 veth | 없음 | 1개 (`eniY@ifN`) |
| 노드 2 Total IPs | 5 | 10 |
| 전체 파드 라우트 | coredns 2개 | coredns 2개 + netshoot 3개 |
| 크로스 노드 통신 | (미확인) | ping 성공 (1.11ms) |

배포 직후의 네트워크 상태와 테스트 파드 배포 후의 변화를 종합하면 다음과 같다.

- **VPC CNI**는 파드에게 VPC의 실제 IP를 부여하고, 노드의 라우팅 테이블과 veth pair로 트래픽을 전달한다
- **WARM_ENI_TARGET=1** 설정에 의해 파드가 배치된 노드에는 추가 ENI가 붙어 warm pool이 확보된다. 이전에 파드가 없던 노드 2도 파드 배치 시점에 자동으로 ENI가 추가되었다
- 파드 내부에서는 `eth0`(veth pair) 하나만 보이며, 기본 게이트웨이가 `169.254.1.1`(link-local)로 설정된다. 모든 아웃바운드 트래픽이 이 가상 게이트웨이를 통해 호스트로 전달된다
- 파드 간 **크로스 노드 통신**은 VPC 라우팅 패브릭이 직접 처리한다. 오버레이 없이 VPC IP로 통신하므로 추가 캡슐화 오버헤드가 없다
- **kube-proxy**는 iptables 모드로 Service ClusterIP를 파드 IP로 DNAT한다
- **AWS SNAT 체인**은 VPC 외부 통신에만 SNAT를 적용하고, VPC 내부 통신은 원본 IP를 유지한다
- 트러블슈팅 시에는 **ipamd.log**(IP 할당/해제)와 **plugin.log**(veth/라우트 설정)를 확인하고, **IPAM 디버깅 엔드포인트**(`localhost:61679`)로 실시간 상태를 점검할 수 있다

*다음 포스트: [EKS: Networking - 4. 파드 간 통신]({% post_url 2026-03-19-Kubernetes-EKS-02-02-02-Pod-to-Pod-Network %})*

<br>
