---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.6. 노드 정보, 인증서 및 kubeconfig 확인"
excerpt: "kubeadm init 이후 노드 정보, 인증서, kubeconfig를 상세히 확인해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **노드 정보, 인증서, kubeconfig 확인**이다.

- **노드 정보**: kubelet 상태 및 설정, 노드 상세 정보, 커널 파라미터 확인
- **인증서**: PKI 구조, 인증서 내용, 만료 시간 확인
- **kubeconfig**: 각 컴포넌트별 kubeconfig 구조 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %})에서 Flannel CNI를 설치했다. 이번 글에서는 CNI 설치가 완료되어 `Ready` 상태가 된 노드의 정보, 인증서, kubeconfig를 상세히 확인한다.

<br>

# 노드 정보 확인

CNI 설치가 완료되어 노드가 `Ready` 상태가 되었다. 이 시점에서 노드의 상세 정보를 확인하면 kubeadm, kubelet, Flannel이 각각 어떤 설정을 추가했는지 파악할 수 있다.

## kubelet 상태 및 설정 확인

[1-3에서 kubelet을 설치했을 때]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubelet-서비스-활성화)는 설정 파일이 아직 생성되지 않아 crashloop 상태였다. `kubeadm init`과 CNI 설치를 거친 지금, kubelet이 정상 실행 중이고 당시 비어 있던 설정 파일들이 채워진 것을 확인할 수 있다.

```bash
systemctl is-active kubelet
# active

systemctl status kubelet --no-pager
# ● kubelet.service - kubelet: The Kubernetes Node Agent
#      Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: disabled)
#     Drop-In: /usr/lib/systemd/system/kubelet.service.d
#              └─10-kubeadm.conf
#      Active: active (running) since Fri 2026-01-23 19:41:11 KST; 46min ago
#    Main PID: 16072 (kubelet)
#       Tasks: 12 (limit: 18742)
#      Memory: 39.6M (peak: 40.9M)
#         CPU: 52.578s
#      CGroup: /system.slice/kubelet.service
#              └─16072 /usr/bin/kubelet --bootstrap-kubeconfig=... --kubeconfig=...
```

[1-3에서 비어 있던]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubernetes-관련-디렉토리) `/var/lib/kubelet/`에 `kubeadm init`이 [설정 파일들]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubelet-서비스-파일)을 생성했다. 각 설정의 역할은 1-3에서 설명했고, 여기서는 실제 값을 확인한다.

```bash
cat /var/lib/kubelet/config.yaml | grep -E 'staticPodPath|cgroupDriver|clusterDNS|clusterDomain|rotateCertificates'
# cgroupDriver: systemd
# clusterDNS:
# - 10.96.0.10
# clusterDomain: cluster.local
# rotateCertificates: true
# authentication:
#   anonymous:
#     enabled: false
#   webhook:
#     cacheTTL: 0s
#     enabled: true
#   x509:
#     clientCAFile: /etc/kubernetes/pki/ca.crt
# authorization:
#   mode: Webhook
# ...
# cgroupDriver: systemd
# staticPodPath: /etc/kubernetes/manifests
```

<details markdown="1">
<summary>kubelet 설정 파일(/var/lib/kubelet/config.yaml)</summary>

```bash
cat /var/lib/kubelet/config.yaml
```

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
authentication:
  anonymous:
    enabled: false
  webhook:
    cacheTTL: 0s
    enabled: true
  x509:
    clientCAFile: /etc/kubernetes/pki/ca.crt
authorization:
  mode: Webhook
  webhook:
    cacheAuthorizedTTL: 0s
    cacheUnauthorizedTTL: 0s
cgroupDriver: systemd
clusterDNS:
- 10.96.0.10
clusterDomain: cluster.local
containerRuntimeEndpoint: ""
cpuManagerReconcilePeriod: 0s
crashLoopBackOff: {}
evictionPressureTransitionPeriod: 0s
fileCheckFrequency: 0s
healthzBindAddress: 127.0.0.1
healthzPort: 10248
httpCheckFrequency: 0s
imageMaximumGCAge: 0s
imageMinimumGCAge: 0s
kind: KubeletConfiguration
logging:
  flushFrequency: 0
  options:
    json:
      infoBufferSize: "0"
    text:
      infoBufferSize: "0"
  verbosity: 0
memorySwap: {}
nodeStatusReportFrequency: 0s
nodeStatusUpdateFrequency: 0s
rotateCertificates: true
runtimeRequestTimeout: 0s
shutdownGracePeriod: 0s
shutdownGracePeriodCriticalPods: 0s
staticPodPath: /etc/kubernetes/manifests
streamingConnectionIdleTimeout: 0s
syncFrequency: 0s
volumeStatsAggPeriod: 0s
```

| 설정 | 값 | 출처 | 설명 |
| --- | --- | --- | --- |
| `staticPodPath` | `/etc/kubernetes/manifests` | `config.yaml` | Static Pod 매니페스트 감시 경로 |
| `cgroupDriver` | `systemd` | `config.yaml` | containerd의 SystemdCgroup 설정과 일치해야 함 |
| `clusterDNS` | `10.96.0.10` | `config.yaml` | CoreDNS Service ClusterIP |
| `rotateCertificates` | `true` | `config.yaml` | kubelet 클라이언트 인증서 자동 갱신 |

<br>

```bash
cat /var/lib/kubelet/kubeadm-flags.env
# KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///run/containerd/containerd.sock --node-ip=192.168.10.100 --pod-infra-container-image=registry.k8s.io/pause:3.10"
```

| 설정 | 값 | 출처 | 설명 |
| --- | --- | --- | --- |
| `--container-runtime-endpoint` | `unix:///run/containerd/containerd.sock` | `kubeadm-flags.env` | containerd CRI 소켓 경로 |
| `--node-ip` | `192.168.10.100` | `kubeadm-flags.env` | 노드 IP (kubeadm 설정에서 지정한 값) |
| `--pod-infra-container-image` | `registry.k8s.io/pause:3.10` | `kubeadm-flags.env` | Pod의 [인프라 컨테이너(pause)]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너) 이미지 |


</details>

## 프로세스 및 네임스페이스 전체 확인

프로세스 트리와 네임스페이스를 확인해 보자. [containerd 설치 직후]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#containerd-서비스-시작-및-확인)의 baseline과 비교하면 변화가 뚜렷하다.

<details markdown="1">
<summary>pstree</summary>

```
systemd─┬─NetworkManager───3*[{NetworkManager}]
        ├─VBoxService───8*[{VBoxService}]
        ├─agetty
        ├─atd
        ├─auditd─┬─sedispatch
        │        └─2*[{auditd}]
        ├─chronyd
        ├─containerd───12*[{containerd}]
        ├─containerd-shim─┬─kube-scheduler───9*[{kube-scheduler}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─kube-controller───6*[{kube-controller}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─etcd───10*[{etcd}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─kube-apiserver───11*[{kube-apiserver}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─kube-proxy───7*[{kube-proxy}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─flanneld───9*[{flanneld}]
        │                 ├─pause
        │                 └─11*[{containerd-shim}]
        ├─containerd-shim─┬─coredns───8*[{coredns}]
        │                 ├─pause
        │                 └─12*[{containerd-shim}]
        ├─containerd-shim─┬─coredns───8*[{coredns}]
        │                 ├─pause
        │                 └─11*[{containerd-shim}]
        ├─crond
        ├─dbus-broker-lau───dbus-broker
        ├─gssproxy───5*[{gssproxy}]
        ├─irqbalance───{irqbalance}
        ├─kubelet───11*[{kubelet}]
        ├─lsmd
        ├─polkitd───3*[{polkitd}]
        ├─rpcbind
        ├─rsyslogd───2*[{rsyslogd}]
        ├─sshd─┬─...
        ├─systemd───(sd-pam)
        ├─systemd-journal
        ├─systemd-logind
        ├─systemd-udevd
        ├─systemd-userdbd───3*[systemd-userwor]
        ├─tuned───3*[{tuned}]
        └─udisksd───6*[{udisksd}]
```

</details>

기존 baseline과 비교했을 때 주요 변화는 아래와 같다:

- **kubelet**: [정상 실행 중](#kubelet-상태-및-설정-확인) (crashloop 해소)
- **containerd-shim**: Pod마다 하나씩, 총 8개. 각각 `pause` + 실제 워크로드를 자식으로 가진다. 이것이 Pod sandbox 모델이다
- 총 8개 Pod: static pod 4개(apiserver, etcd, scheduler, controller-manager) + DaemonSet 2개(kube-proxy, flannel) + Deployment 2개(coredns)

<details markdown="1">
<summary>lsns</summary>

```
        NS TYPE   NPROCS   PID USER    COMMAND
4026531834 time      155     1 root    /usr/lib/systemd/systemd ...
4026531835 cgroup    148     1 root    /usr/lib/systemd/systemd ...
4026531836 pid       139     1 root    /usr/lib/systemd/systemd ...
4026531837 user      154     1 root    /usr/lib/systemd/systemd ...
4026531838 uts       142     1 root    /usr/lib/systemd/systemd ...
4026531839 ipc       139     1 root    /usr/lib/systemd/systemd ...
4026531840 net       149     1 root    /usr/lib/systemd/systemd ...
4026531841 mnt       124     1 root    /usr/lib/systemd/systemd ...
  ... (시스템 서비스 네임스페이스 생략)
4026532126 mnt         1  7600 65535   /pause
4026532190 ipc         2  7600 65535   /pause
4026532195 pid         1  7600 65535   /pause
4026532267 mnt         1  7601 65535   /pause
4026532268 ipc         2  7601 65535   /pause
4026532269 pid         1  7601 65535   /pause
4026532270 mnt         1  7650 root    kube-scheduler ...
4026532271 pid         1  7650 root    kube-scheduler ...
4026532272 cgroup      1  7650 root    kube-scheduler ...
4026532273 mnt         1  7656 root    kube-controller-manager ...
4026532274 pid         1  7656 root    kube-controller-manager ...
4026532275 cgroup      1  7656 root    kube-controller-manager ...
4026532276 mnt         1  7750 65535   /pause
4026532277 ipc         2  7750 65535   /pause
4026532278 pid         1  7750 65535   /pause
4026532279 mnt         1  7758 65535   /pause
4026532280 ipc         2  7758 65535   /pause
4026532281 pid         1  7758 65535   /pause
4026532282 mnt         1  7806 root    kube-apiserver ...
4026532283 pid         1  7806 root    kube-apiserver ...
4026532284 cgroup      1  7806 root    kube-apiserver ...
4026532285 mnt         1  7807 root    etcd ...
4026532286 pid         1  7807 root    etcd ...
4026532287 cgroup      1  7807 root    etcd ...
4026532288 mnt         1  7971 65535   /pause
4026532289 ipc         2  7971 65535   /pause
4026532290 pid         1  7971 65535   /pause
4026532291 mnt         1  7997 root    /usr/local/bin/kube-proxy ...
4026532292 pid         1  7997 root    /usr/local/bin/kube-proxy ...
4026532293 mnt         1 10250 65535   /pause
4026532294 ipc         2 10250 65535   /pause
4026532295 pid         1 10250 65535   /pause
4026532296 mnt         1 10400 root    /opt/bin/flanneld --ip-masq --kube-subnet-mgr --iface=enp0s9
4026532297 pid         1 10400 root    /opt/bin/flanneld --ip-masq --kube-subnet-mgr --iface=enp0s9
4026532298 cgroup      1 10400 root    /opt/bin/flanneld --ip-masq --kube-subnet-mgr --iface=enp0s9
4026532300 net         2 10702 65535   /pause
4026532375 net         2 10704 65535   /pause
4026532443 mnt         1 10702 65535   /pause
4026532444 uts         2 10702 65535   /pause
4026532445 ipc         2 10702 65535   /pause
4026532446 pid         1 10702 65535   /pause
4026532447 mnt         1 10704 65535   /pause
4026532448 uts         2 10704 65535   /pause
4026532449 ipc         2 10704 65535   /pause
4026532450 pid         1 10704 65535   /pause
4026532451 mnt         1 10755 65532   /coredns -conf /etc/coredns/Corefile
4026532452 pid         1 10755 65532   /coredns -conf /etc/coredns/Corefile
4026532453 cgroup      1 10755 65532   /coredns -conf /etc/coredns/Corefile
4026532454 mnt         1 10762 65532   /coredns -conf /etc/coredns/Corefile
4026532455 pid         1 10762 65532   /coredns -conf /etc/coredns/Corefile
4026532456 cgroup      1 10762 65532   /coredns -conf /etc/coredns/Corefile
```

</details>

baseline에서는 시스템 네임스페이스만 존재했는데, 이제 컨테이너별 네임스페이스가 대량으로 추가되었다.

- **`pause`(user 65535)가 공유 네임스페이스의 소유자**: ipc 네임스페이스의 `NPROCS=2`는 pause와 워크로드 컨테이너가 해당 네임스페이스를 공유한다는 뜻이다
- **호스트 네트워크 Pod** (control plane, kube-proxy, flannel): 별도 net 네임스페이스가 없다. 호스트의 `4026531840 net`(`NPROCS=149`)에 포함되어 호스트 네트워크를 직접 사용한다
- **Pod 네트워크 Pod** (coredns): pause가 소유하는 별도 net 네임스페이스(`4026532300`, `4026532375`)가 존재하고, `NPROCS=2`로 pause와 coredns가 공유한다

## 노드 상세 정보 확인

노드 주요 정보를 살펴 보자.

```bash
kc describe node k8s-ctr
```

<details markdown="1">
<summary>노드 정보 확인 전문</summary>
```bash
Name:               k8s-ctr
Roles:              control-plane
Labels:             beta.kubernetes.io/arch=arm64
                    beta.kubernetes.io/os=linux
                    kubernetes.io/arch=arm64
                    kubernetes.io/hostname=k8s-ctr
                    kubernetes.io/os=linux
                    node-role.kubernetes.io/control-plane=
                    node.kubernetes.io/exclude-from-external-load-balancers=
Annotations:        flannel.alpha.coreos.com/backend-data: {"VNI":1,"VtepMAC":"7e:e7:01:d7:1f:7c"}
                    flannel.alpha.coreos.com/backend-type: vxlan
                    flannel.alpha.coreos.com/kube-subnet-manager: true
                    flannel.alpha.coreos.com/public-ip: 192.168.10.100
                    kubeadm.alpha.kubernetes.io/cri-socket: unix:///run/containerd/containerd.sock
                    node.alpha.kubernetes.io/ttl: 0
                    volumes.kubernetes.io/controller-managed-attach-detach: true
CreationTimestamp:  Sun, 01 Mar 2026 23:15:13 +0900
Taints:             node-role.kubernetes.io/control-plane:NoSchedule
Unschedulable:      false
Lease:
  HolderIdentity:  k8s-ctr
  AcquireTime:     <unset>
  RenewTime:       Mon, 02 Mar 2026 13:10:49 +0900
Conditions:
  Type                 Status  LastHeartbeatTime                 LastTransitionTime                Reason                       Message
  ----                 ------  -----------------                 ------------------                ------                       -------
  NetworkUnavailable   False   Sun, 01 Mar 2026 23:44:52 +0900   Sun, 01 Mar 2026 23:44:52 +0900   FlannelIsUp                  Flannel is running on this node
  MemoryPressure       False   Mon, 02 Mar 2026 13:08:06 +0900   Sun, 01 Mar 2026 23:15:13 +0900   KubeletHasSufficientMemory   kubelet has sufficient memory available
  DiskPressure         False   Mon, 02 Mar 2026 13:08:06 +0900   Sun, 01 Mar 2026 23:15:13 +0900   KubeletHasNoDiskPressure     kubelet has no disk pressure
  PIDPressure          False   Mon, 02 Mar 2026 13:08:06 +0900   Sun, 01 Mar 2026 23:15:13 +0900   KubeletHasSufficientPID      kubelet has sufficient PID available
  Ready                True    Mon, 02 Mar 2026 13:08:06 +0900   Sun, 01 Mar 2026 23:45:01 +0900   KubeletReady                 kubelet is posting ready status
Addresses:
  InternalIP:  192.168.10.100
  Hostname:    k8s-ctr
Capacity:
  cpu:                4
  ephemeral-storage:  60970Mi
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  hugepages-32Mi:     0
  hugepages-64Ki:     0
  memory:             2893976Ki
  pods:               110
Allocatable:
  cpu:                4
  ephemeral-storage:  57538510753
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  hugepages-32Mi:     0
  hugepages-64Ki:     0
  memory:             2791576Ki
  pods:               110
System Info:
  Machine ID:                 3cf0cc5101474d6490f7225f4890667b
  System UUID:                3cf0cc5101474d6490f7225f4890667b
  Boot ID:                    1ef6fdee-ec07-4467-bb56-132c41e90f60
  Kernel Version:             6.12.0-55.39.1.el10_0.aarch64
  OS Image:                   Rocky Linux 10.0 (Red Quartz)
  Operating System:           linux
  Architecture:               arm64
  Container Runtime Version:  containerd://2.1.5
  Kubelet Version:            v1.32.13
  Kube-Proxy Version:         v1.32.13
PodCIDR:                      10.244.0.0/24
PodCIDRs:                     10.244.0.0/24
Non-terminated Pods:          (8 in total)
  Namespace                   Name                               CPU Requests  CPU Limits  Memory Requests  Memory Limits  Age
  ---------                   ----                               ------------  ----------  ---------------  -------------  ---
  kube-flannel                kube-flannel-ds-bdlq4              100m (2%)     0 (0%)      50Mi (1%)        0 (0%)         13h
  kube-system                 coredns-668d6bf9bc-bzdwl           100m (2%)     0 (0%)      70Mi (2%)        170Mi (6%)     13h
  kube-system                 coredns-668d6bf9bc-qzk56           100m (2%)     0 (0%)      70Mi (2%)        170Mi (6%)     13h
  kube-system                 etcd-k8s-ctr                       100m (2%)     0 (0%)      100Mi (3%)       0 (0%)         13h
  kube-system                 kube-apiserver-k8s-ctr             250m (6%)     0 (0%)      0 (0%)           0 (0%)         13h
  kube-system                 kube-controller-manager-k8s-ctr    200m (5%)     0 (0%)      0 (0%)           0 (0%)         13h
  kube-system                 kube-proxy-pclch                   0 (0%)        0 (0%)      0 (0%)           0 (0%)         13h
  kube-system                 kube-scheduler-k8s-ctr             100m (2%)     0 (0%)      0 (0%)           0 (0%)         13h
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests     Limits
  --------           --------     ------
  cpu                950m (23%)   0 (0%)
  memory             290Mi (10%)  340Mi (12%)
  ephemeral-storage  0 (0%)       0 (0%)
  hugepages-1Gi      0 (0%)       0 (0%)
  hugepages-2Mi      0 (0%)       0 (0%)
  hugepages-32Mi     0 (0%)       0 (0%)
  hugepages-64Ki     0 (0%)       0 (0%)
Events:              <none>
```
</details>

### Labels & Annotations

```yaml
Labels:
  node-role.kubernetes.io/control-plane=       # kubeadm이 추가
  node.kubernetes.io/exclude-from-external-load-balancers=
Annotations:
  flannel.alpha.coreos.com/backend-type: vxlan  # Flannel이 추가
  flannel.alpha.coreos.com/public-ip: 192.168.10.100
  kubeadm.alpha.kubernetes.io/cri-socket: unix:///run/containerd/containerd.sock
Taints:
  node-role.kubernetes.io/control-plane:NoSchedule   # 일반 워크로드 스케줄 방지
```

### Conditions

CNI 설치 전에는 `NetworkUnavailable=True`였지만, Flannel 설치 후 `False`로 변경되었다.

| Condition | Status | Reason |
| --- | --- | --- |
| `NetworkUnavailable` | **False** | FlannelIsUp |
| `MemoryPressure` | False | KubeletHasSufficientMemory |
| `DiskPressure` | False | KubeletHasNoDiskPressure |
| `PIDPressure` | False | KubeletHasSufficientPID |
| `Ready` | **True** | KubeletReady |

### 리소스 사용량

컨트롤 플레인 컴포넌트들이 CPU의 약 23%, 메모리의 약 10%를 사용 중이다.

```yaml
PodCIDR:     10.244.0.0/24
Capacity:    cpu: 4, memory: 2893976Ki, pods: 110
Allocatable: cpu: 4, memory: 2791576Ki, pods: 110

Non-terminated Pods: (8 in total)
  Namespace      Name                               CPU Requests  Memory Requests
  ---------      ----                               ------------  ---------------
  kube-flannel   kube-flannel-ds-hv2xd              100m (2%)     50Mi (1%)
  kube-system    coredns-668d6bf9bc-n8jxf           100m (2%)     70Mi (2%)
  kube-system    coredns-668d6bf9bc-z6h69           100m (2%)     70Mi (2%)
  kube-system    etcd-k8s-ctr                       100m (2%)     100Mi (3%)
  kube-system    kube-apiserver-k8s-ctr             250m (6%)     0 (0%)
  kube-system    kube-controller-manager-k8s-ctr    200m (5%)     0 (0%)
  kube-system    kube-proxy-5p6jx                   0 (0%)        0 (0%)
  kube-system    kube-scheduler-k8s-ctr             100m (2%)     0 (0%)

Allocated resources:
  cpu:    950m (23%)
  memory: 290Mi (10%)
```

### Events

CNI 설치 후 `NodeReady` 이벤트가 발생했다.

```
Events:
  Normal  Starting                 46m    kubelet          Starting kubelet.
  Normal  RegisteredNode           46m    node-controller  Node k8s-ctr event: Registered Node k8s-ctr in Controller
  Normal  NodeReady                4m30s  kubelet          Node k8s-ctr status is now: NodeReady
```

<br>

## 커널 파라미터 변경 사항

kubelet과 kube-proxy가 클러스터 안정성을 위해 일부 커널 파라미터를 자동으로 변경한다. `sysctl`을 이용해 변경된 값을 확인해 보자.

> 참고: sysctl
>
> `sysctl`은 Linux 커널 파라미터를 런타임에 조회/변경하는 인터페이스다. 내부적으로 `/proc/sys/` 디렉토리의 파일을 읽고 쓴다. 예를 들어 `sysctl net.ipv4.ip_forward`는 `/proc/sys/net/ipv4/ip_forward` 파일의 값을 조회한다. Kubernetes에서는 네트워크 포워딩, 메모리 관리, 연결 추적 등의 커널 설정이 중요하므로 kubelet과 kube-proxy가 시작 시 관련 파라미터를 자동으로 설정한다.

### kubelet이 변경하는 파라미터

kubelet은 `--protect-kernel-defaults=false`(기본값)일 때 아래 파라미터들을 자동으로 설정한다. `true`로 설정하면 kubelet이 직접 변경하지 않고, 기존 값이 kubelet의 기대값과 다르면 오류가 발생한다.

| 파라미터 | 변경 전 | 변경 후 | 이유 |
| --- | --- | --- | --- |
| `kernel.panic` | 0 | 10 | 커널 패닉 시 10초 후 자동 재부팅 (노드 복구) |
| `vm.overcommit_memory` | 0 | 1 | 메모리 오버커밋 허용 (컨테이너 메모리 할당 유연성) |

> 참고
> - [kubelet sysctl 관련 코드](https://github.com/kubernetes/kubernetes/blob/master/staging/src/k8s.io/component-helpers/node/util/sysctl/sysctl.go)
> - [kubelet이 원하는 커널 파라미터](https://www.kimsehwan96.com/kubelet-expected-kernel-parameters/)


#### vm.overcommit_memory

`vm.overcommit_memory`는 Linux가 메모리 할당 요청(`malloc()` 등)을 어떻게 처리할지 결정하는 파라미터다. 자세한 설명은 [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %}) 글의 메모리 오버커밋 섹션을 참고한다.

kubelet이 `vm.overcommit_memory=1`로, 기본값 `0`(휴리스틱)이 아닌 `1`(항상 허용)로 설정하는 이유는 **컨테이너 환경**에서 **장점**이 있기 때문이다:
- 컨테이너가 메모리를 요청할 때 **즉시 실패하지 않음** (가상 주소 공간만 예약)
- 많은 컨테이너가 메모리를 "예약"만 하고 실제로는 일부만 사용하는 패턴에 유리
- **오버프로비저닝**이 가능해져 노드당 더 많은 컨테이너 실행 가능
- Pod의 `requests`는 낮게, `limits`는 높게 설정하는 패턴을 지원

다만 **단점 및 주의할 점**도 있다:
- 물리 메모리가 실제로 부족해지면 **OOM Killer가 예고 없이** 프로세스를 종료
- 모든 컨테이너가 예약한 메모리를 동시에 사용하면 **Thrashing** 발생 가능
- 메모리 사용량 예측이 어려워 용량 계획이 복잡해짐

> Kubernetes는 이러한 단점을 **Resource Requests/Limits**와 **QoS Class**로 보완한다. `requests`로 최소 보장 메모리를 설정하고, `limits`로 최대 사용량을 제한하여 OOM Killer 발동을 제어한다.

아래 파라미터들은 kubelet이 확인하지만, 기본값이 이미 kubelet의 기대값과 일치하므로 변경되지 않는다:

| 파라미터 | 기존값 | 설명 |
| --- | --- | --- |
| `kernel.panic_on_oops` | 1 | oops 발생 시 패닉 |
| `vm.panic_on_oom` | 0 | OOM 시 패닉하지 않음 (OOM Killer가 처리) |
| `kernel.keys.root_maxkeys` | 1000000 | root 사용자의 최대 키 개수 |
| `kernel.keys.root_maxbytes` | 25000000 | root 사용자의 최대 키 바이트 (root_maxkeys × 25) |


> 참고: kubespray에서의 처리
>
> `--protect-kernel-defaults=true`로 운영할 경우, kubelet이 커널 파라미터를 직접 변경하지 않으므로 사전에 설정해야 한다. kubespray는 아래와 같이 Ansible로 처리한다:
>
> ```yaml
> - name: Ensure kube-bench parameters are set
>   ansible.posix.sysctl:
>     name: "{{ item.name }}"
>     value: "{{ item.value }}"
>     state: present
>     reload: yes
>   with_items:
>     - { name: kernel.keys.root_maxbytes, value: 25000000 }
>     - { name: kernel.keys.root_maxkeys, value: 1000000 }
>     - { name: kernel.panic, value: 10 }
>     - { name: kernel.panic_on_oops, value: 1 }
>     - { name: vm.overcommit_memory, value: 1 }
>     - { name: vm.panic_on_oom, value: 0 }
>   when: kubelet_protect_kernel_defaults | bool
> ```

### kube-proxy가 변경하는 파라미터

kube-proxy는 iptables/IPVS를 통해 Service 트래픽을 라우팅하므로, conntrack(연결 추적) 테이블 관련 파라미터를 자동으로 설정한다.

| 파라미터 | 변경 전 | 변경 후 | 이유 |
| --- | --- | --- | --- |
| `net.nf_conntrack_max` | 65536 | 131072 | conntrack 테이블 크기 증가 (더 많은 연결 추적) |
| `net.netfilter.nf_conntrack_tcp_timeout_close_wait` | 60 | 3600 | CLOSE_WAIT 타임아웃 증가 (연결 정리 지연) |
| `net.netfilter.nf_conntrack_tcp_timeout_established` | 432000 | 86400 | ESTABLISHED 타임아웃 감소 (5일 → 1일, 오래된 연결 정리) |

> 참고: [kube-proxy conntrack sysctl 관련 코드](https://github.com/kubernetes/kubernetes/blob/master/pkg/proxy/conntrack/sysctls.go)

### 트러블슈팅 팁

커널 파라미터 튜닝 중 **설정 값이 자꾸 원복되거나 변경**된다면 kubelet 또는 kube-proxy를 의심해볼 수 있다. 이들 컴포넌트는 시작 시 위 파라미터들을 자동으로 설정하므로, 수동 튜닝 값과 충돌할 수 있다.

<br>

# 인증서 확인

## 인증서 만료 시간 확인

Kubernetes 클러스터의 인증서는 기본적으로 **1년** 후 만료된다. 운영 환경에서는 인증서 만료 전에 갱신해야 클러스터 장애를 방지할 수 있다. `kubeadm certs renew` 명령으로 갱신하거나, `kubeadm upgrade`를 수행하면 자동으로 갱신된다.

### kubeadm-config에서 유효 기간 확인

`kubeadm-config` ConfigMap은 클러스터 업그레이드 시 참조되므로, 설정 변경이 필요하면 이 ConfigMap을 업데이트해야 한다.

```bash
kc describe cm -n kube-system kubeadm-config
# Data
# ====
# ClusterConfiguration:
# ----
# apiVersion: kubeadm.k8s.io/v1beta4
# caCertificateValidityPeriod: 87600h0m0s   # CA 인증서: 10년 (87600시간)
# certificateValidityPeriod: 8760h0m0s      # 일반 인증서: 1년 (8760시간)
# certificatesDir: /etc/kubernetes/pki
# kubernetesVersion: v1.32.11
# networking:
#   dnsDomain: cluster.local
#   podSubnet: 10.244.0.0/16
#   serviceSubnet: 10.96.0.0/16
```

### 인증서 만료 시간 확인

```bash
kubeadm certs check-expiration
# CERTIFICATE                EXPIRES                  RESIDUAL TIME   CERTIFICATE AUTHORITY   EXTERNALLY MANAGED
# admin.conf                 Jan 23, 2027 10:41 UTC   364d            ca                      no
# apiserver                  Jan 23, 2027 10:41 UTC   364d            ca                      no
# apiserver-etcd-client      Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# apiserver-kubelet-client   Jan 23, 2027 10:41 UTC   364d            ca                      no
# controller-manager.conf    Jan 23, 2027 10:41 UTC   364d            ca                      no
# etcd-healthcheck-client    Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# etcd-peer                  Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# etcd-server                Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# front-proxy-client         Jan 23, 2027 10:41 UTC   364d            front-proxy-ca          no
# scheduler.conf             Jan 23, 2027 10:41 UTC   364d            ca                      no
# super-admin.conf           Jan 23, 2027 10:41 UTC   364d            ca                      no
#
# CERTIFICATE AUTHORITY   EXPIRES                  RESIDUAL TIME   EXTERNALLY MANAGED
# ca                      Jan 21, 2036 10:41 UTC   9y              no
# etcd-ca                 Jan 21, 2036 10:41 UTC   9y              no
# front-proxy-ca          Jan 21, 2036 10:41 UTC   9y              no
```

| 인증서 유형 | 유효 기간 | 만료일 |
| --- | --- | --- |
| 일반 인증서 (apiserver, admin.conf 등) | **1년** | 2027-01-23 |
| CA 인증서 (ca, etcd-ca, front-proxy-ca) | **10년** | 2036-01-21 |

> **운영 팁**: 인증서 만료 30일 전에 알림을 받도록 모니터링을 설정하고, 정기적인 클러스터 업그레이드를 통해 인증서를 갱신하는 것이 좋다.

<br>

## 인증서 파일 구조

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %})에서 설명한 PKI 구조가 실제로 생성되었는지 확인한다.

```bash
tree /etc/kubernetes/pki
# /etc/kubernetes/pki
# ├── apiserver.crt                    # API Server 서버 인증서
# ├── apiserver.key
# ├── apiserver-etcd-client.crt        # API Server → etcd 클라이언트 인증서
# ├── apiserver-etcd-client.key
# ├── apiserver-kubelet-client.crt     # API Server → kubelet 클라이언트 인증서
# ├── apiserver-kubelet-client.key
# ├── ca.crt                           # 클러스터 CA (루트)
# ├── ca.key
# ├── front-proxy-ca.crt               # API Aggregation용 CA
# ├── front-proxy-ca.key
# ├── front-proxy-client.crt           # API Aggregation 클라이언트 인증서
# ├── front-proxy-client.key
# ├── sa.key                           # ServiceAccount 토큰 서명용 키
# ├── sa.pub
# └── etcd/                            # etcd 전용 PKI
#     ├── ca.crt                       # etcd CA
#     ├── ca.key
#     ├── healthcheck-client.crt       # etcd 헬스체크용
#     ├── healthcheck-client.key
#     ├── peer.crt                     # etcd 노드 간 통신용
#     ├── peer.key
#     ├── server.crt                   # etcd 서버 인증서
#     └── server.key
#
# 2 directories, 22 files
```

총 **22개 파일** (3개 CA + 8개 인증서/키 쌍 + SA 키 쌍)이 생성되었다. [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %})에서 OpenSSL로 수동 생성했던 인증서들이 kubeadm에 의해 자동으로 생성되었다.

<br>

## 주요 인증서 내용 확인

인증서 내용을 직접 확인하면 각 인증서가 **누구에게 발급되었는지(Subject)**, **어떤 용도인지(Key Usage)**, **어디서 유효한지(SAN)** 를 이해할 수 있다. 특히 API Server 인증서의 SAN은 클라이언트가 접속할 수 있는 모든 주소를 포함해야 한다.

### CA 인증서

```bash
cat /etc/kubernetes/pki/ca.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Version: 3 (0x2)
#         Serial Number: 9110514726841664365 (0x7e6f0cdfde5cc36d)
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 21 10:41:04 2036 GMT        ← 10년 유효
#         Subject: CN=kubernetes
#         Subject Public Key Info:
#             Public Key Algorithm: rsaEncryption
#                 Public-Key: (2048 bit)
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment, Certificate Sign
#             X509v3 Basic Constraints: critical
#                 CA:TRUE                                 ← 루트 CA 인증서
#             X509v3 Subject Alternative Name:
#                 DNS:kubernetes
```

- **Issuer = Subject = `CN=kubernetes`**: 자체 서명된 루트 CA
- **CA:TRUE**: 다른 인증서를 서명할 수 있는 CA 인증서
- **유효기간 10년**: CA 인증서는 장기간 유효

### API Server 인증서

```bash
cat /etc/kubernetes/pki/apiserver.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes                          ← CA가 서명
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT       ← 1년 유효
#         Subject: CN=kube-apiserver
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment
#             X509v3 Extended Key Usage:
#                 TLS Web Server Authentication          ← 서버 인증서
#             X509v3 Basic Constraints: critical
#                 CA:FALSE
#             X509v3 Subject Alternative Name:
#                 DNS:k8s-ctr, DNS:kubernetes, DNS:kubernetes.default,
#                 DNS:kubernetes.default.svc, DNS:kubernetes.default.svc.cluster.local,
#                 IP Address:10.96.0.1, IP Address:192.168.10.100
```

- **Subject: `CN=kube-apiserver`**: API Server의 서버 인증서
- **Extended Key Usage: `TLS Web Server Authentication`**: 서버 인증 전용
- **SAN (Subject Alternative Name)**: 클라이언트가 이 주소들로 접속 시 인증서 검증 통과
  - `kubernetes.default.svc.cluster.local`: Pod 내부에서 접근 시
  - `10.96.0.1`: Service ClusterIP (kubernetes 서비스)
  - `192.168.10.100`: 외부에서 접근 시

### API Server → Kubelet 클라이언트 인증서

```bash
cat /etc/kubernetes/pki/apiserver-kubelet-client.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT
#         Subject: O=kubeadm:cluster-admins, CN=kube-apiserver-kubelet-client
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment
#             X509v3 Extended Key Usage:
#                 TLS Web Client Authentication          ← 클라이언트 인증서
#             X509v3 Basic Constraints: critical
#                 CA:FALSE
```

- **Subject: `O=kubeadm:cluster-admins, CN=kube-apiserver-kubelet-client`**: 조직(O)과 이름(CN) 포함
- **Extended Key Usage: `TLS Web Client Authentication`**: 클라이언트 인증 전용
- API Server가 kubelet에 접속할 때 이 인증서로 자신을 증명

<br>

# kubeconfig 확인

kubeconfig 파일은 각 컴포넌트가 API Server에 접속할 때 사용하는 **인증 정보**를 담고 있다. 각 파일의 `user` 섹션에서 **누구로 인증하는지**를 확인할 수 있으며, 이 정보가 RBAC 권한과 연결된다.

대부분의 kubeconfig는 인증서가 base64로 **내장**(`client-certificate-data`)되어 있지만, **kubelet.conf만 외부 파일 경로**(`client-certificate`)를 참조한다. 이는 kubeadm이 kubelet 인증서 자동 갱신(Certificate Rotation)을 지원하기 때문이다.

> 참고: **Hard Way와의 차이 (클라이언트 인증서)**
>
> [Hard Way에서는 kubelet kubeconfig도 **클라이언트 인증서**가 base64로 내장]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}#kubelet-kubeconfig-생성)되어 있었다:
> - 수동으로 인증서를 생성하고 배포했기 때문에 **인증서 자동 갱신 기능이 없었다**
> - kubeconfig 파일 안에 인증서가 포함되어 있어 갱신 시 파일 전체를 교체해야 한다
>
> kubeadm은 kubelet 클라이언트 인증서를 **클러스터 CA로 서명**하여 생성하고, `rotateCertificates: true` 설정으로 만료 전 자동 갱신을 지원한다. 이를 위해 kubeconfig가 외부 파일을 참조하는 구조를 사용한다. 자동 갱신 메커니즘 상세는 [kubelet 클라이언트 인증서](#kubelet-클라이언트-인증서)에서, 서버 인증서는 [kubelet 서버 인증서](#kubelet-서버-인증서)에서 설명한다.

| 파일 | 사용자 | 용도 |
| --- | --- | --- |
| `admin.conf` | `kubernetes-admin` (O=`kubeadm:cluster-admins`) | kubectl 관리 작업용 |
| `super-admin.conf` | `kubernetes-super-admin` (O=`system:masters`) | 비상 복구용 (RBAC 우회) |
| `controller-manager.conf` | `system:kube-controller-manager` | Controller Manager 전용 |
| `scheduler.conf` | `system:kube-scheduler` | Scheduler 전용 |
| `kubelet.conf` | `system:node:<노드명>` | kubelet 전용 (외부 인증서 참조) |

## admin.conf

`O=kubeadm:cluster-admins` 그룹에 속한 `kubernetes-admin` 사용자로 인증한다. 일반적인 클러스터 관리 작업에 사용한다.

```bash
# 관리자용 kubeconfig
cat /etc/kubernetes/admin.conf
# apiVersion: v1
# clusters:
# - cluster:
#     certificate-authority-data: LS0t...   ← CA 인증서 (base64)
#     server: https://192.168.10.100:6443
#   name: kubernetes
# contexts:
# - context:
#     cluster: kubernetes
#     user: kubernetes-admin
#   name: kubernetes-admin@kubernetes
# current-context: kubernetes-admin@kubernetes
# users:
# - name: kubernetes-admin
#   user:
#     client-certificate-data: LS0t...      ← 클라이언트 인증서 (base64)
#     client-key-data: LS0t...              ← 클라이언트 키 (base64)
```



## super-admin.conf

`O=system:masters` 그룹에 속한 `kubernetes-super-admin` 사용자로 인증한다. `system:masters`는 kube-apiserver에 하드코딩된 특수 그룹으로, **RBAC 평가를 거치지 않고 모든 권한이 허용**된다. 클러스터 복구 시에만 사용해야 한다.

> 참고
> - [Using RBAC Authorization - Default roles and role bindings](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings)
> - [PKI certificates and requirements](https://kubernetes.io/docs/setup/best-practices/certificates/)


```bash
# 슈퍼 관리자용 kubeconfig (비상 복구용)
cat /etc/kubernetes/super-admin.conf
# apiVersion: v1
# clusters:
# - cluster:
#     certificate-authority-data: LS0t...
#     server: https://192.168.10.100:6443
#   name: kubernetes
# contexts:
# - context:
#     cluster: kubernetes
#     user: kubernetes-super-admin
#   name: kubernetes-super-admin@kubernetes
# current-context: kubernetes-super-admin@kubernetes
# users:
# - name: kubernetes-super-admin
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...
```

## controller-manager.conf, scheduler.conf

각 컴포넌트는 자신만의 kubeconfig로 API Server에 인증한다. `system:kube-controller-manager`와 `system:kube-scheduler`는 [Kubernetes가 부트스트랩 시 생성하는 기본 ClusterRoleBinding]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}#rbac-기본-역할)으로 필요한 권한을 부여받는다.

```bash
# 컴포넌트용 kubeconfig
cat /etc/kubernetes/controller-manager.conf
# users:
# - name: system:kube-controller-manager
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...

cat /etc/kubernetes/scheduler.conf
# users:
# - name: system:kube-scheduler
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...
```

## kubelet.conf

앞서 언급한 대로, kubelet.conf만 인증서를 외부 파일 경로로 참조한다. `kubelet-client-current.pem`은 현재 유효한 인증서에 대한 심볼릭 링크로, 인증서 갱신 시 이 링크가 새 인증서를 가리키도록 업데이트된다.

> 참고: **PEM 파일과 kubeconfig의 인증서 형식**
>
> [PEM 파일]({% post_url 2026-01-04-CS-Security-X509-Certificate %}#pemprivacy-enhanced-mail)은 DER의 Base64 인코딩에 헤더/푸터(`-----BEGIN CERTIFICATE-----`)를 추가한 형식이다. 다른 kubeconfig의 `client-certificate-data`는 이 헤더/푸터를 제거한 순수 base64가 들어간 것이다.
>
> kubelet은 인증서 갱신 시 kubeconfig 파일 수정 없이 새 PEM 파일 생성 후 심볼릭 링크만 업데이트하면 된다. 반면 다른 kubeconfig(admin.conf, controller-manager.conf 등)는 인증서 갱신 시 파일 내의 base64 값을 직접 교체해야 한다.

```bash
# kubelet kubeconfig
cat /etc/kubernetes/kubelet.conf
# contexts:
# - context:
#     cluster: kubernetes
#     user: system:node:k8s-ctr             ← 노드명 포함
#   name: system:node:k8s-ctr@kubernetes
# users:
# - name: system:node:k8s-ctr
#   user:
#     client-certificate: /var/lib/kubelet/pki/kubelet-client-current.pem
#     client-key: /var/lib/kubelet/pki/kubelet-client-current.pem
```

### kubelet 인증서 확인

kubelet.conf에서 참조하는 인증서 파일들을 확인한다.

```bash
ls -l /var/lib/kubelet/pki
# total 12
# -rw-------. 1 root root 2826 Jan 23 19:41 kubelet-client-2026-01-23-19-41-07.pem
# lrwxrwxrwx. 1 root root   59 Jan 23 19:41 kubelet-client-current.pem -> /var/lib/kubelet/pki/kubelet-client-2026-01-23-19-41-07.pem
# -rw-r--r--. 1 root root 2262 Jan 23 19:41 kubelet.crt
# -rw-------. 1 root root 1679 Jan 23 19:41 kubelet.key
```

| 파일 | 용도 |
| --- | --- |
| `kubelet-client-current.pem` | kubelet → API Server 클라이언트 인증서 (심볼릭 링크) |
| `kubelet-client-2026-01-23-...pem` | 실제 클라이언트 인증서 (자동 갱신 시 새 파일 생성) |
| `kubelet.crt` / `kubelet.key` | kubelet 서버 인증서 (API Server → kubelet 접속 시) |

kubelet은 **클라이언트 인증서**와 **서버 인증서** 두 가지를 모두 사용한다:
- **클라이언트 인증서** (`kubelet-client-*.pem`): kubelet → API Server 접속 시
- **서버 인증서** (`kubelet.crt/key`): API Server → kubelet 접속 시

두 인증서의 **발급자(Issuer)가 다른데**, 아래에서 각각 확인해 보자.

#### kubelet 서버 인증서

API Server가 kubelet의 `/logs`, `/exec`, `/attach` 등 API에 접속할 때 이 인증서로 kubelet을 검증한다.

```bash
cat /var/lib/kubelet/pki/kubelet.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=k8s-ctr-ca@1769164867              ← kubelet 자체 생성 CA
#         Validity
#             Not Before: Jan 23 09:41:06 2026 GMT
#             Not After : Jan 23 09:41:06 2027 GMT
#         Subject: CN=k8s-ctr@1769164867
#         X509v3 extensions:
#             X509v3 Extended Key Usage:
#                 TLS Web Server Authentication          ← 서버 인증서
#             X509v3 Subject Alternative Name:
#                 DNS:k8s-ctr                            ← 노드 호스트명
```

- **Issuer: `CN=k8s-ctr-ca@...`**: 클러스터 CA가 아닌 **kubelet이 자체 생성한 CA**로 서명됨
- **SAN: `DNS:k8s-ctr`**: 노드 호스트명만 포함

> 참고: **왜 자체 CA로 서명되었나?**
>
> kubelet 서버 인증서의 서명자를 결정하는 핵심 설정은 `serverTLSBootstrap`이다([KubeletConfiguration](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/#kubelet-config-k8s-io-v1beta1-KubeletConfiguration))
> - `serverTLSBootstrap: true` → 클러스터 CA가 서명 (CSR 승인 필요)
> - `serverTLSBootstrap: false` (기본값) → kubelet이 자체 CA 생성하여 서명
>
> [이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#선택-dry-run으로-사전-확인)에서 `kubelet-config` ConfigMap이 클러스터 내 모든 kubelet이 공유할 설정을 담고 있다고 설명했다. 실제 ConfigMap 내용을 확인해보면:
>
> ```bash
> kubectl get configmap kubelet-config -n kube-system -o yaml
> # apiVersion: v1
> # data:
> #   kubelet: |
> #     apiVersion: kubelet.config.k8s.io/v1beta1
> #     ...
> #     rotateCertificates: true
> #     ...
> #     (serverTLSBootstrap 설정 없음)
> ```
>
> `serverTLSBootstrap` 설정이 **명시되지 않았으므로 기본값 `false`가 적용**된다. 이 때문에:
> - kubelet이 **자체 CA를 생성**하여 서버 인증서에 서명
> - 클러스터 CA와 **독립적으로** 서버 인증서 관리
>
> 만약 `serverTLSBootstrap: true`로 설정하면 kubelet이 **CSR(Certificate Signing Request)**을 API Server에 요청한다. 그러나 kube-controller-manager의 기본 서명자는 **자동 승인하지 않으므로**, 관리자가 `kubectl certificate approve`로 수동 승인하거나 [kubelet-csr-approver](https://github.com/postfinance/kubelet-csr-approver) 같은 써드파티 컨트롤러가 필요하다. 
>
> 현재 실습에서는 이러한 복잡성을 피하기 위해 kubeadm의 기본 설정(비활성화)을 그대로 사용했다.
>
> 다만, 프로덕션 환경에서는 통일된 인증서 관리를 위해 `serverTLSBootstrap: true`를 고려할 수 있다. 이 경우, CSR 승인 자동화 메커니즘을 함께 구성해야 하므로 운영 복잡도가 증가할 수 있다. 아래 글을 참고해 보자.
> - [서명된 kubelet 인증서 활성화하기](https://kubernetes.io/ko/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/#kubelet-serving-certs)
- [Kubelet의 인증서 갱신 구성](https://kubernetes.io/ko/docs/tasks/tls/certificate-rotation/)

#### kubelet 클라이언트 인증서

kubelet이 API Server에 접속하여 Pod 정보 조회, 상태 보고 등을 수행할 때 이 인증서로 자신을 인증한다.

```bash
cat /var/lib/kubelet/pki/kubelet-client-current.pem | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes                         ← 클러스터 CA가 서명
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT
#         Subject: O=system:nodes, CN=system:node:k8s-ctr
#         X509v3 extensions:
#             X509v3 Extended Key Usage:
#                 TLS Web Client Authentication         ← 클라이언트 인증서
```

- **Issuer: `CN=kubernetes`**: **클러스터 CA**가 서명 → API Server가 신뢰함
- **Subject: `O=system:nodes, CN=system:node:k8s-ctr`**: RBAC에서 `system:nodes` 그룹과 `system:node:k8s-ctr` 사용자로 인식됨

> **참고: 클라이언트 인증서 자동 갱신 (`rotateCertificates`)**
>
> [이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#선택-dry-run으로-사전-확인)의 `kubelet-config` ConfigMap에서 `rotateCertificates: true`가 설정되어 있다. 이 설정으로 인해:
> 1. 인증서 만료가 임박하면 kubelet이 **CSR(Certificate Signing Request)**을 API Server에 제출
> 2. kube-controller-manager가 **자동 승인** 후 `--cluster-signing-cert-file`로 지정된 **클러스터 CA로 서명**
> 3. 새 인증서가 `kubelet-client-current.pem`에 갱신됨
>
> [위](#kubeconfig-확인)에서 설명한 대로 kubeadm은 kubelet.conf가 외부 파일을 참조하도록 구성하여 이 자동 갱신을 지원한다.

#### 두 인증서의 차이 요약

| 구분 | `kubelet.crt` (서버) | `kubelet-client-current.pem` (클라이언트) |
| --- | --- | --- |
| **용도** | API Server → kubelet 접속 시 | kubelet → API Server 접속 시 |
| **발급자** | kubelet 자체 CA | 클러스터 CA (`kubernetes`) |
| **Extended Key Usage** | Server Authentication | Client Authentication |
| **자동 갱신** | kubelet이 자체 관리 | kubelet이 CSR 요청, 컨트롤러가 승인 |

<br>

노드 정보, 인증서, kubeconfig를 확인했다. [다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-7 %})에서는 Static Pod와 필수 애드온(CoreDNS, kube-proxy)을 상세히 확인한다.

<br>
