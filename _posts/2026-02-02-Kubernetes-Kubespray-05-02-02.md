---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 5.2.1. Full Client-Side LB(Case 1) HA 구성 - 클러스터 배포"
excerpt: "Kubespray로 HA Control Plane 클러스터를 배포하고 Client-Side LB 구성을 확인해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - HA
  - Client-Side LB
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray로 HA Control Plane 클러스터**를 배포하고 **Case 1 (Full Client-Side LB)** 구성을 확인한다.

- **Kubespray 배포**: Control Plane 3대 + Worker 1대 구성
- **Worker Node**: nginx static pod를 통한 Client-Side LB 확인
- **Control Plane**: 로컬 API Server 엔드포인트 확인
- **핵심**: 모든 컴포넌트가 `127.0.0.1:6443`으로 API Server 접근

<br>

# Kubespray 사전 확인

## Playbook Tag 확인

Kubespray는 다양한 태그를 제공하여 특정 작업만 실행할 수 있다.

```bash
# playbooks/ 파일 중 tags 확인
tree playbooks/
grep -Rni "tags" playbooks -A2 -B1

# roles/ 파일 중 tags 확인
tree roles/ -L 2
grep -Rni "tags" roles --include="*.yml" -A2 -B1 | less
```


| 태그 | 설명 |
|------|------|
| `containerd` | containerd 런타임 설치/설정 |
| `etcd` | etcd 클러스터 구성 |
| `kubernetes` | Kubernetes 컴포넌트 설치 |
| `network` | CNI 플러그인 설치 |
| `apps` | 애드온 설치 |


## Kubespray 버전 확인

```bash
cd /root/kubespray/
git describe --tags
```

> **참고**: 최근 Kubespray **v2.30.0**이 릴리스되었다. 최신 버전(v2.30.0) 사용 시 문서와 차이가 있을 수 있으니 [릴리스 노트](https://github.com/kubernetes-sigs/kubespray/releases)를 참고해야 한다.

<br>

# 인벤토리 확인

## 디렉터리 구조

<details markdown="1">
<summary>클릭하여 펼치기: tree inventory/mycluster/ 출력</summary>

```bash
tree inventory/mycluster/
```

```
inventory/mycluster/
├── group_vars
│   ├── all
│   │   ├── all.yml
│   │   ├── aws.yml
│   │   ├── azure.yml
│   │   ├── containerd.yml
│   │   ├── coreos.yml
│   │   ├── cri-o.yml
│   │   ├── docker.yml
│   │   ├── etcd.yml
│   │   ├── gcp.yml
│   │   ├── hcloud.yml
│   │   ├── huaweicloud.yml
│   │   ├── oci.yml
│   │   ├── offline.yml
│   │   ├── openstack.yml
│   │   ├── upcloud.yml
│   │   └── vsphere.yml
│   └── k8s_cluster
│       ├── addons.yml
│       ├── k8s-cluster.yml
│       ├── k8s-net-calico.yml
│       ├── k8s-net-cilium.yml
│       ├── k8s-net-custom-cni.yml
│       ├── k8s-net-flannel.yml
│       ├── k8s-net-kube-ovn.yml
│       ├── k8s-net-kube-router.yml
│       ├── k8s-net-macvlan.yml
│       └── kube_control_plane.yml
└── inventory.ini

4 directories, 27 files
```

</details>

## inventory.ini

```bash
cat /root/kubespray/inventory/mycluster/inventory.ini
```

```ini
[kube_control_plane]
k8s-node1 ansible_host=192.168.10.11 ip=192.168.10.11 etcd_member_name=etcd1
k8s-node2 ansible_host=192.168.10.12 ip=192.168.10.12 etcd_member_name=etcd2
k8s-node3 ansible_host=192.168.10.13 ip=192.168.10.13 etcd_member_name=etcd3

[etcd:children]
kube_control_plane

[kube_node]
k8s-node4 ansible_host=192.168.10.14 ip=192.168.10.14
#k8s-node5 ansible_host=192.168.10.15 ip=192.168.10.15
```

| 그룹 | 노드 | 역할 |
|------|------|------|
| `kube_control_plane` | k8s-node1~3 | Control Plane (API Server, Controller Manager, Scheduler) |
| `etcd` | k8s-node1~3 | etcd 클러스터 (children으로 상속) |
| `kube_node` | k8s-node4 | Worker Node |

## host vars 확인 (ansible-inventory --list)

`inventory.ini`에 호스트별로 적은 변수(`ansible_host`, `ip`, `etcd_member_name` 등)와 `group_vars/`에서 로드된 변수가 합쳐져 각 호스트의 **host vars**로 적용된다. `ansible-inventory --list`를 이용하면 이렇게 해석된 인벤토리와 host vars를 확인할 수 있다. 출력 JSON의 **`_meta.hostvars`**에 호스트별 변수가 들어 있다.
- 참고: [Ansible 인벤토리 - ansible.cfg로 기본 인벤토리 지정]({% post_url 2026-01-12-Kubernetes-Ansible-03 %}#ansiblecfg로-기본-인벤토리-지정)

```bash
ansible-inventory -i /root/kubespray/inventory/mycluster/inventory.ini --list
```

`_meta.hostvars`에 각 호스트별로 적용된 변수 예시(k8s-node1)는 아래와 같다.

```json
"k8s-node1": {
    "ansible_host": "192.168.10.11",
    "ip": "192.168.10.11",
    "etcd_member_name": "etcd1",
    "etcd_data_dir": "/var/lib/etcd",
    "etcd_deployment_type": "host",
    "loadbalancer_apiserver_port": 6443,
    "loadbalancer_apiserver_healthcheck_port": 8081,
    "bin_dir": "/usr/local/bin",
    "docker_bin_dir": "/usr/bin",
    "docker_daemon_graph": "/var/lib/docker",
    "docker_iptables_enabled": "false",
    "docker_log_opts": "--log-opt max-size=50m --log-opt max-file=5",
    "ntp_enabled": false,
    "ntp_servers": ["0.pool.ntp.org iburst", "1.pool.ntp.org iburst", "2.pool.ntp.org iburst", "3.pool.ntp.org iburst"],
    "kube_webhook_token_auth": false,
    "no_proxy_exclude_workers": false,
    "unsafe_show_logs": false
}
```

k8s-node2, k8s-node3은 `ip`, `ansible_host`, `etcd_member_name`만 호스트별로 다르고 나머지 변수는 동일하다. k8s-node4(worker)는 `etcd_member_name`이 없고 `ip`/`ansible_host`만 192.168.10.14로 적용된다.

| 호스트 | ip / ansible_host | etcd_member_name | loadbalancer_apiserver_port |
|--------|-------------------|------------------|-----------------------------|
| k8s-node1 | 192.168.10.11 | etcd1 | 6443 |
| k8s-node2 | 192.168.10.12 | etcd2 | 6443 |
| k8s-node3 | 192.168.10.13 | etcd3 | 6443 |
| k8s-node4 | 192.168.10.14 | — | 6443 |

<br>

`ansible-inventory --list` 출력에서 **그룹·호스트 관계**만 따로 보면 다음과 같다. (`_meta.hostvars` 제외)

```json
"all": { "children": ["ungrouped", "etcd", "kube_node"] },
"etcd": { "children": ["kube_control_plane"] },
"kube_control_plane": { "hosts": ["k8s-node1", "k8s-node2", "k8s-node3"] },
"kube_node": { "hosts": ["k8s-node4"] }
```

## 인벤토리 그래프 확인

```bash
ansible-inventory -i /root/kubespray/inventory/mycluster/inventory.ini --graph

@all:
  |--@ungrouped:
  |--@etcd:
  |  |--@kube_control_plane:
  |  |  |--k8s-node1
  |  |  |--k8s-node2
  |  |  |--k8s-node3
  |--@kube_node:
  |  |--k8s-node4
```

<br>

# 변수 설정

## k8s-cluster.yml 수정

```bash
# CNI를 Flannel로 변경 (실습 환경 단순화)
sed -i 's|kube_network_plugin: calico|kube_network_plugin: flannel|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# kube-proxy 모드를 iptables로 변경
sed -i 's|kube_proxy_mode: ipvs|kube_proxy_mode: iptables|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# NodeLocal DNSCache 비활성화
sed -i 's|enable_nodelocaldns: true|enable_nodelocaldns: false|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# 파일 소유자 변경
sed -i 's|kube_owner: kube|kube_owner: root|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# CoreDNS autoscaler 비활성화
echo "enable_dns_autoscaler: false" >> inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# 설정 확인
grep -iE 'kube_owner|kube_network_plugin:|kube_proxy_mode|enable_nodelocaldns:' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```


```
kube_owner: root
kube_network_plugin: flannel
kube_proxy_mode: iptables
enable_nodelocaldns: false
```

`enable_dns_autoscaler: false`는 `echo "..." >>`로 추가했으므로 위 grep에는 안 나온다. 파일 끝에 추가되어 있다.

| 변수 | 기본값 | 변경값 | 이유 |
|------|--------|--------|------|
| `kube_network_plugin` | `calico` | `flannel` | 실습 환경 단순화 |
| `kube_proxy_mode` | `ipvs` | `iptables` | 기본 모드로 변경 |
| `enable_nodelocaldns` | `true` | `false` | 복잡도 감소 |
| `kube_owner` | `kube` | `root` | 파일 소유자 |
| `enable_dns_autoscaler` | `true` | `false` | 메모리 절약 |

## Flannel 설정

Flannel이 사용할 네트워크 인터페이스를 지정한다.
```bash
echo "flannel_interface: enp0s9" >> inventory/mycluster/group_vars/k8s_cluster/k8s-net-flannel.yml

# 설정 확인
grep "^[^#]" inventory/mycluster/group_vars/k8s_cluster/k8s-net-flannel.yml
```

```
flannel_interface: enp0s9
```

## addons.yml 수정

```bash
# Metrics Server 활성화
sed -i 's|metrics_server_enabled: false|metrics_server_enabled: true|g' \
  inventory/mycluster/group_vars/k8s_cluster/addons.yml

# 리소스 제한 (실습 환경용)
echo "metrics_server_requests_cpu: 25m" >> inventory/mycluster/group_vars/k8s_cluster/addons.yml
echo "metrics_server_requests_memory: 16Mi" >> inventory/mycluster/group_vars/k8s_cluster/addons.yml

# 설정 확인
grep -iE 'metrics_server_enabled:' inventory/mycluster/group_vars/k8s_cluster/addons.yml
```

```
metrics_server_enabled: true
```

`metrics_server_requests_cpu: 25m`, `metrics_server_requests_memory: 16Mi`는 `echo "..." >>`로 addons.yml 끝에 추가했다. 실습 환경 리소스 절약용이다.

### Metrics Server 변수 확인

addons.yml에서 덮어쓴 변수는 Kubespray **role**의 기본값을 오버라이드한다. 변수 적용 위치를 확인하려면 `roles/kubernetes-apps/metrics_server/`를 보면 된다.

```bash
# 메트릭서버 role 구조
ls roles/kubernetes-apps/metrics_server/
# defaults/  tasks/  templates/

# 디폴트 변수 (오버라이드 전 기본값)
cat roles/kubernetes-apps/metrics_server/defaults/main.yml

# Deployment 템플릿 (resources에 metrics_server_requests_* 등 사용)
cat roles/kubernetes-apps/metrics_server/templates/metrics-server-deployment.yaml.j2
```

**defaults/main.yml:**

```yaml
---
metrics_server_container_port: 10250
metrics_server_kubelet_insecure_tls: true
metrics_server_kubelet_preferred_address_types: "InternalIP,ExternalIP,Hostname"
metrics_server_metric_resolution: 15s
metrics_server_limits_cpu: 100m
metrics_server_limits_memory: 200Mi
metrics_server_requests_cpu: 100m          # addons.yml에서 25m으로 오버라이드
metrics_server_requests_memory: 200Mi     # addons.yml에서 16Mi로 오버라이드
metrics_server_host_network: false
metrics_server_replicas: 1
metrics_server_extra_tolerations: []
metrics_server_extra_affinity: {}
metrics_server_nodeselector: {}
```

<br>

**metrics-server-deployment.yaml.j2 (resources 부분):** 템플릿에서 아래처럼 `metrics_server_requests_cpu`, `metrics_server_requests_memory`를 사용한다. addons.yml에 넣은 값이 여기 적용된다.

```yaml
        resources:
          limits:
            cpu: {{ metrics_server_limits_cpu }}
            memory: {{ metrics_server_limits_memory }}
          requests:
            cpu: {{ metrics_server_requests_cpu }}
            memory: {{ metrics_server_requests_memory }}
```

| 변수 | defaults/main.yml | addons.yml 오버라이드 |
|------|-------------------|------------------------|
| `metrics_server_requests_cpu` | 100m | 25m |
| `metrics_server_requests_memory` | 200Mi | 16Mi |

<br>

# 클러스터 배포

## Task 목록 확인 (Dry Run)
```bash
ansible-playbook -i inventory/mycluster/inventory.ini -v cluster.yml --list-tasks
```

## cluster.yml 실행
클러스터를 배포한다.
```bash
# 배포 실행 (약 8분 소요)
ANSIBLE_FORCE_COLOR=true ansible-playbook -i inventory/mycluster/inventory.ini \
  -v cluster.yml -e kube_version="1.32.9" | tee kubespray_install.log
```

끝나면 **PLAY RECAP**과 소요 시간 요약이 나온다. 모든 노드가 `failed=0`이면 성공이다.

```
PLAY RECAP *********************************************************************
k8s-node1                  : ok=532  changed=120  unreachable=0    failed=0    skipped=836  rescued=0    ignored=2
k8s-node2                  : ok=499  changed=111  unreachable=0    failed=0    skipped=822  rescued=0    ignored=2
k8s-node3                  : ok=501  changed=112  unreachable=0    failed=0    skipped=820  rescued=0    ignored=2
k8s-node4                  : ok=437  changed=87   unreachable=0    failed=0    skipped=615  rescued=0    ignored=0

Thursday 05 February 2026  21:49:05 +0900 (0:00:00.061)       0:08:50.108 *****
===============================================================================
download : Download_file | Download item ------------------------------- 25.02s
download : Download_container | Download image if required ------------- 20.32s
download : Download_file | Download item ------------------------------- 20.12s
...
kubernetes/kubeadm : Join to cluster if needed ------------------------- 16.05s
...
kubernetes/control-plane : Joining control plane node to the cluster. --- 8.74s
kubernetes/control-plane : Kubeadm | Initialize first control plane node (1st try) --- 8.44s
...
```

### /tmp 디렉토리 확인

```bash
tree /tmp
```

```
/tmp
├── k8s-node1
├── k8s-node2
├── k8s-node3
├── k8s-node4
├── k9s_linux_arm64.tar.gz
├── ...
└── vagrant-shell

13 directories, 8 files
```

인벤토리 호스트명과 같은 이름의 항목(`k8s-node1`~`k8s-node4`)은 Ansible이 playbook 실행 시 **호스트별로 두는 임시 디렉터리**이다. 
- 모듈 전달·파일 스테이징 등에 쓰임
- fact 캐시를 사용하는 설정이면 **facts 수집 정보**가 저장되는 경로와도 연관

배포 후에도 남아 있을 수 있으므로, 어떤 노드에 대해 작업이 수행되었는지·Ansible(playbook을 실행한 쪽)이 각 노드를 제대로 인식했는지 확인할 때 참고하면 된다. 

 
`systemd-private-*`, `vagrant-shell` 등은 OS·Vagrant 쪽 임시 디렉터리다.

### 노드별 local_release_dir 확인

Kubespray는 변수 `local_release_dir`(기본값 `"/tmp/releases"`)에 맞춰 **각 노드**에 바이너리·아카이브를 받아 둔다. 배포 후 확인해 보면 Control Plane 노드와 Worker 노드에 다운로드된 파일이 다르다.

```bash
# Control Plane 노드 (k8s-node1)
ssh k8s-node1 tree /tmp/releases

/tmp/releases
├── cni-plugins-linux-arm64-1.8.0.tgz
├── containerd-2.1.5-linux-arm64.tar.gz
├── containerd-rootless-setuptool.sh
├── containerd-rootless.sh
├── crictl
├── crictl-1.32.0-linux-arm64.tar.gz
├── etcd-3.5.25-linux-arm64.tar.gz
├── etcd-v3.5.25-linux-arm64
│   ├── etcd
│   ├── etcdctl
│   ├── etcdutl
│   └── ...
├── images
├── kubeadm-1.32.9-arm64
├── kubectl-1.32.9-arm64
├── kubelet-1.32.9-arm64
├── nerdctl
├── nerdctl-2.1.6-linux-arm64.tar.gz
└── runc-1.3.4.arm64

7 directories, 24 files

# Worker 노드 (k8s-node4)
ssh k8s-node4 tree /tmp/releases

/tmp/releases
├── cni-plugins-linux-arm64-1.8.0.tgz
├── containerd-2.1.5-linux-arm64.tar.gz
├── containerd-rootless-setuptool.sh
├── containerd-rootless.sh
├── crictl
├── crictl-1.32.0-linux-arm64.tar.gz
├── images
├── kubeadm-1.32.9-arm64
├── kubelet-1.32.9-arm64
├── nerdctl
├── nerdctl-2.1.6-linux-arm64.tar.gz
└── runc-1.3.4.arm64

2 directories, 11 files
```

Control Plane 노드에는 **etcd**(아카이브·풀린 디렉터리)와 **kubectl** 바이너리가 있고, Worker 노드에는 없다. 공통으로는 containerd, crictl, runc, nerdctl, CNI 플러그인, kubeadm, kubelet이 있다. 즉, `local_release_dir`만 봐도 어떤 노드가 Control Plane용·Worker용으로 구성되었는지 구분할 수 있다.

### 노드별 sysctl 적용값 확인

Kubespray는 모든 노드에 동일한 커널 파라미터(sysctl)를 적용한다. `/etc/sysctl.conf`에서 주석을 제외한 적용값만 보려면 아래처럼 확인하면 된다.

```bash
# Control Plane 노드 (k8s-node1)
ssh k8s-node1 grep "^[^#]" /etc/sysctl.conf

# Worker 노드 (k8s-node4)
ssh k8s-node4 grep "^[^#]" /etc/sysctl.conf
```

**k8s-node1 (Control Plane):**

```
net.ipv4.ip_forward=1
kernel.keys.root_maxbytes=25000000
kernel.keys.root_maxkeys=1000000
kernel.panic=10
kernel.panic_on_oops=1
vm.overcommit_memory=1
vm.panic_on_oom=0
net.ipv4.ip_local_reserved_ports=30000-32767
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-arptables=1
net.bridge.bridge-nf-call-ip6tables=1
```

**k8s-node4 (Worker):** 위와 동일한 목록이 나온다.

Control Plane·Worker 구분 없이 **동일한 sysctl**이 적용된다. `net.ipv4.ip_forward=1`은 Pod 네트워킹을 위해, `net.bridge.bridge-nf-call-*`는 브리지 트래픽이 iptables/ip6tables를 타도록 하기 위한 설정이다.




## Kubespray가 자동으로 수행하는 작업

Kubespray는 아래와 같은 작업을 자동으로 수행한다. [클러스터 배포 - 실습 환경 구성]({% post_url 2026-01-25-Kubernetes-Kubespray-04-00 %})에서는 Vagrant/VM 구성만 다루었고, 이번 글에서는 **실제 cluster.yml 실행**으로 HA Control Plane 3대 + Worker 1대를 배포한다. 그중 **단계 4(Worker 노드에 nginx static pod 배포)**가 Case 1(Full Client-Side LB)의 핵심이다.

| 단계 | 작업 내용 |
|------|----------|
| 1 | 모든 노드에 containerd 설치 |
| 2 | Control Plane에 API Server, Controller Manager, Scheduler 설치 |
| 3 | Control Plane에 etcd 클러스터 구성 (3대) |
| 4 | **Worker 노드에 nginx static pod 배포** ← Case 1 핵심 |
| 5 | Flannel CNI 설치 |
| 6 | CoreDNS 설치 |

<br>

# 배포 후 기본 확인

## Control Plane API Server 확인

Control Plane 노드 각각에는 API Server 파드가 떠 있으므로, 해당 노드의 kubeconfig는 `127.0.0.1:6443`으로 설정되어 있다. 각 노드에서 `kubectl cluster-info -v=6`으로 확인하면 된다.

```bash
for i in {1..3}; do echo ">> k8s-node$i <<"; ssh k8s-node$i kubectl cluster-info -v=6; echo; done
```

```
>> k8s-node1 <<
I0205 22:18:19.355223   33204 loader.go:402] Config loaded from file:  /root/.kube/config
...
I0205 22:18:19.369517   33204 round_trippers.go:560] GET https://127.0.0.1:6443/api/v1/namespaces/kube-system/services?labelSelector=... 200 OK in 9 milliseconds
Kubernetes control plane is running at https://127.0.0.1:6443

>> k8s-node2 <<
I0205 22:18:42.158063   32648 loader.go:402] Config loaded from file:  /root/.kube/config
...
I0205 22:18:42.186430   32648 round_trippers.go:560] GET https://127.0.0.1:6443/api/v1/namespaces/kube-system/services?labelSelector=... 200 OK in 9 milliseconds
Kubernetes control plane is running at https://127.0.0.1:6443

>> k8s-node3 <<
I0205 22:18:14.430566   32774 loader.go:402] Config loaded from file:  /root/.kube/config
...
I0205 22:18:14.445100   32774 round_trippers.go:560] GET https://127.0.0.1:6443/api/v1/namespaces/kube-system/services?labelSelector=... 200 OK in 10 milliseconds
Kubernetes control plane is running at https://127.0.0.1:6443
```

세 노드 모두 kubeconfig는 `/root/.kube/config`에서 로드되고, API 요청이 `https://127.0.0.1:6443`으로 나가며 "Kubernetes control plane is running at https://127.0.0.1:6443"이 출력되면 Case 1 엔드포인트가 올바르게 설정된 것이다.

## kubeconfig 설정

이번 실습에서는 admin-lb(별도 호스트)에서 **하나의 API Server**만 보게 kubeconfig를 설정한다. [클러스터 배포 - 실습 환경 구성]({% post_url 2026-01-25-Kubernetes-Kubespray-04-00 %})이나 단일 노드 실습(4.1)에서는 admin-lb와 Control Plane이 분리되지 않았거나 kubectl을 Control Plane 노드에서만 썼기 때문에 `server`를 바꿀 필요가 없었다. Control Plane에서 가져온 config는 `server: https://127.0.0.1:6443`이라서, admin-lb에서는 그대로 쓰면 접근이 안 되므로 단일 IP(예: 192.168.10.11)로 바꾼다. 그 노드 장애 시 admin-lb에서 kubectl 접근이 불가할 수 있다.

### kubeconfig 복사

클러스터 배포 시 **admin용 kubeconfig**는 Control Plane 노드에만 생성된다. Worker에는 `/root/.kube/config`가 없거나 kubelet용 등 역할이 다르므로, admin-lb에서 쓸 config는 Control Plane 중 한 대에서 가져와야 한다. 보통 첫 번째 Control Plane(k8s-node1)에서 복사한다.

```bash
mkdir -p /root/.kube
scp k8s-node1:/root/.kube/config /root/.kube/

# API Server 주소 확인
cat /root/.kube/config | grep server
```

```
config                                      100% 5665     1.7MB/s   00:00
    server: https://127.0.0.1:6443
```

### 단일 IP로 변경

```bash
sed -i 's/127.0.0.1/192.168.10.11/g' /root/.kube/config

kubectl get node -owide -v=6
```

변경 후 아래 사항들을 확인한다:
- admin-lb에서 `kubectl`이 정상 동작하는지
- `-v=6` 로그에 `GET https://192.168.10.11:6443/... 200 OK`가 나오는지(실제로 해당 IP로 요청이 나가는지)
- 노드 목록이 4대 모두 나오는지

```
I0205 22:22:20.985079   14361 round_trippers.go:560] GET https://192.168.10.11:6443/api?timeout=32s 200 OK in 6 milliseconds
...
NAME        STATUS   ROLES           AGE   VERSION   INTERNAL-IP     EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION   CONTAINER-RUNTIME
k8s-node1   Ready    control-plane   34m   v1.32.9   192.168.10.11   <none>        Rocky Linux 10.0 ...  6.12.0-55...     containerd://2.1.5
k8s-node2   Ready    control-plane   34m   v1.32.9   192.168.10.12   <none>        Rocky Linux 10.0 ...  6.12.0-55...     containerd://2.1.5
k8s-node3   Ready    control-plane   34m   v1.32.9   192.168.10.13   <none>        Rocky Linux 10.0 ...  6.12.0-55...     containerd://2.1.5
k8s-node4   Ready    <none>          33m   v1.32.9   192.168.10.14   <none>        Rocky Linux 10.0 ...  6.12.0-55...     containerd://2.1.5
```



## 노드 상태 확인

```bash
kubectl get node -owide
```

```
# 예상 출력
NAME        STATUS   ROLES           AGE     VERSION   INTERNAL-IP     ...
k8s-node1   Ready    control-plane   3m37s   v1.32.9   192.168.10.11   ...
k8s-node2   Ready    control-plane   3m31s   v1.32.9   192.168.10.12   ...
k8s-node3   Ready    control-plane   3m29s   v1.32.9   192.168.10.13   ...
k8s-node4   Ready    <none>          3m3s    v1.32.9   192.168.10.14   ...
```

## Taint 확인

```bash
kubectl describe node | grep -E 'Name:|Taints'
```

```
Name:               k8s-node1
Taints:             node-role.kubernetes.io/control-plane:NoSchedule
Name:               k8s-node2
Taints:             node-role.kubernetes.io/control-plane:NoSchedule
Name:               k8s-node3
Taints:             node-role.kubernetes.io/control-plane:NoSchedule
Name:               k8s-node4
Taints:             <none>
```

## Pod CIDR 확인

노드별 Pod 네트워크 대역(CIDR)은 Flannel 등 CNI가 할당한다.

```bash
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'
```

```
k8s-node1       10.233.64.0/24
k8s-node2       10.233.65.0/24
k8s-node3       10.233.66.0/24
k8s-node4       10.233.67.0/24
```

## Pod 목록 확인

```bash
kubectl get pod -A
```

```
NAMESPACE     NAME                                READY   STATUS    RESTARTS   AGE
kube-system   coredns-664b99d7c7-74zjn            1/1     Running   0          42m
kube-system   coredns-664b99d7c7-pcxrv            1/1     Running   0          42m
kube-system   kube-apiserver-k8s-node1            1/1     Running   1          43m
kube-system   kube-apiserver-k8s-node2            1/1     Running   1          43m
kube-system   kube-apiserver-k8s-node3            1/1     Running   1          43m
kube-system   kube-controller-manager-k8s-node1   1/1     Running   2          43m
kube-system   kube-controller-manager-k8s-node2   1/1     Running   2          43m
kube-system   kube-controller-manager-k8s-node3   1/1     Running   2          43m
kube-system   kube-flannel-ds-arm64-9fg8h         1/1     Running   0          43m
kube-system   kube-flannel-ds-arm64-kppg4         1/1     Running   0          43m
kube-system   kube-flannel-ds-arm64-sfnfh         1/1     Running   0          43m
kube-system   kube-flannel-ds-arm64-xnm8r         1/1     Running   0          43m
kube-system   kube-proxy-97rb2                    1/1     Running   0          43m
kube-system   kube-proxy-dsrms                    1/1     Running   0          43m
kube-system   kube-proxy-qdkq8                    1/1     Running   0          43m
kube-system   kube-proxy-txpcm                    1/1     Running   0          43m
kube-system   kube-scheduler-k8s-node1            1/1     Running   1          43m
kube-system   kube-scheduler-k8s-node2            1/1     Running   1          43m
kube-system   kube-scheduler-k8s-node3            1/1     Running   1          43m
kube-system   metrics-server-65fdf69dcb-wp2zj     1/1     Running   0          42m
kube-system   nginx-proxy-k8s-node4               1/1     Running   0          43m
```

Control Plane 3대에는 API Server, Controller Manager,Scheduler가 노드별 static pod로, Worker(k8s-node4)에는 **nginx-proxy** static pod가 배포되어 있다. CoreDNS, Flannel, kube-proxy, metrics-server는 시스템 컴포넌트다.

## API Server 접근 확인

```bash
# Control Plane 노드 각각 API 접근 확인
for i in {1..3}; do 
  echo ">> k8s-node$i <<"
  curl -sk https://192.168.10.1$i:6443/version | grep gitVersion
  echo
done
```

```
>> k8s-node1 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",

>> k8s-node2 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",

>> k8s-node3 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",
```

admin-lb의 `/etc/hosts`에 `k8s-node1`~`k8s-node5`가 있으면 호스트명으로도 접근할 수 있다.

```bash
cat /etc/hosts
# ...
# 192.168.10.11 k8s-node1
# 192.168.10.12 k8s-node2
# ...

for i in {1..3}; do echo ">> k8s-node$i <<"; curl -sk https://k8s-node$i:6443/version | grep Version; echo; done
```

```
>> k8s-node1 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",

>> k8s-node2 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",

>> k8s-node3 <<
  "gitVersion": "v1.32.9",
  "goVersion": "go1.23.12",
```

## etcd 클러스터 확인

```bash
ssh k8s-node1 etcdctl.sh member list -w table
```

```
+------------------+---------+-------+----------------------------+----------------------------+------------+
|        ID        | STATUS  | NAME  |         PEER ADDRS         |        CLIENT ADDRS        | IS LEARNER |
+------------------+---------+-------+----------------------------+----------------------------+------------+
|  8b0ca30665374b0 | started | etcd3 | https://192.168.10.13:2380 | https://192.168.10.13:2379 |      false |
| 2106626b12a4099f | started | etcd2 | https://192.168.10.12:2380 | https://192.168.10.12:2379 |      false |
| c6702130d82d740f | started | etcd1 | https://192.168.10.11:2380 | https://192.168.10.11:2379 |      false |
+------------------+---------+-------+----------------------------+----------------------------+------------+
```

### etcd endpoint status (노드별)

각 Control Plane 노드에서 로컬 etcd(127.0.0.1:2379) 상태를 보면, 리더/팔로워와 RAFT 인덱스가 맞는지 확인할 수 있다.

```bash
for i in {1..3}; do echo ">> k8s-node$i <<"; ssh k8s-node$i etcdctl.sh endpoint status -w table; echo; done
```

```
>> k8s-node1 <<
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
|    ENDPOINT    |        ID        | VERSION | DB SIZE | IS LEADER | IS LEARNER | RAFT TERM | RAFT INDEX | RAFT APPLIED INDEX | ERRORS |
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
| 127.0.0.1:2379 | c6702130d82d740f |  3.5.25 |  6.6 MB |      true |      false |         5 |      10052 |              10052 |        |
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+

>> k8s-node2 <<
| 127.0.0.1:2379 | 2106626b12a4099f |  3.5.25 |  6.6 MB |     false |      false |         5 |      10056 |              10056 |        |

>> k8s-node3 <<
| 127.0.0.1:2379 | 8b0ca30665374b0 |  3.5.25 |  6.6 MB |     false |      false |         5 |      10057 |              10057 |        |
```

k8s-node1에서만 `IS LEADER`가 `true`이고, node2·node3은 팔로워다. RAFT INDEX는 노드마다 약간씩 다를 수 있다.

## etcd 백업 확인

```bash
for i in {1..3}; do echo ">> k8s-node$i <<"; ssh k8s-node$i tree /var/backups; echo; done
```

```
>> k8s-node1 <<
/var/backups
└── etcd-2026-02-05_21:47:00
    ├── member
    │   ├── snap
    │   │   └── db
    │   └── wal
    │       └── 0000000000000000-0000000000000000.wal
    └── snapshot.db

5 directories, 3 files

>> k8s-node2 <<
/var/backups
└── etcd-2026-02-05_21:47:01
    ├── member
    │   ├── snap
    │   │   └── db
    │   └── wal
    │       └── 0000000000000000-0000000000000000.wal
    └── snapshot.db

5 directories, 3 files

>> k8s-node3 <<
/var/backups
└── etcd-2026-02-05_21:47:00
    ├── member
    │   ├── snap
    │   │   └── db
    │   └── wal
    │       └── 0000000000000000-0000000000000000.wal
    └── snapshot.db

5 directories, 3 files
```

각 Control Plane 노드에 타임스탬프가 붙은 etcd 스냅샷 디렉터리(`etcd-YYYY-MM-DD_HH:MM:SS`)가 생성되어 있으면 배포 시점 백업이 수행된 것이다.

<br>

# Worker Node: Client-Side LB 확인

Case 1의 핵심은 **Worker 노드가 nginx static pod를 통해 API Server에 접근**하는 것이다.

## nginx static pod 확인

```bash
ssh k8s-node4 crictl ps | grep nginx
```

```
CONTAINER           IMAGE               CREATED             STATE               NAME                ...
3c09f930b22b0       5a91d90f47ddf       15 minutes ago      Running             nginx-proxy         ...
```

## nginx.conf 확인

```bash
ssh k8s-node4 cat /etc/nginx/nginx.conf
```

```nginx
error_log stderr notice;

worker_processes 2;
worker_rlimit_nofile 130048;
worker_shutdown_timeout 10s;
...
stream {
  upstream kube_apiserver {
    least_conn;
    server 192.168.10.11:6443;
    server 192.168.10.12:6443;
    server 192.168.10.13:6443;
  }

  server {
    listen        127.0.0.1:6443;
    proxy_pass    kube_apiserver;
    proxy_timeout 10m;
    proxy_connect_timeout 1s;
  }
}

http {
...
  server {
    listen 8081;
    location /healthz {
      access_log off;
      return 200;
...
```

| 설정 | 값 | 설명 |
|------|----|----- |
| `upstream kube_apiserver` | 3개 API Server | 백엔드 서버 목록 |
| `least_conn` | - | 최소 연결 부하 분산 알고리즘 |
| `listen 127.0.0.1:6443` | - | 로컬에서만 리스닝 |
| `listen 8081` | - | 헬스체크 엔드포인트 |

## 동작 흐름

```
k8s-node4 (Worker)
  └─ kubelet → localhost:6443 (nginx static pod)
       └─ nginx → CP1/CP2/CP3 (least_conn 분산)
```

## nginx 헬스체크 확인

```bash
ssh k8s-node4 curl -s localhost:8081/healthz -I
```

```
HTTP/1.1 200 OK
Server: nginx
...
```

## Worker 노드에서 API Server 호출 테스트

```bash
ssh k8s-node4 curl -sk https://127.0.0.1:6443/version | grep gitVersion
```

```
  "gitVersion": "v1.32.9",
```

## nginx 리스닝 포트 확인

```bash
ssh k8s-node4 ss -tnlp | grep nginx
```

```
LISTEN 0  511   0.0.0.0:8081    0.0.0.0:*  users:(("nginx",pid=15043,fd=6)...)
LISTEN 0  511  127.0.0.1:6443   0.0.0.0:*  users:(("nginx",pid=15043,fd=5)...)
```

## kubelet 자격증명 확인

```bash
ssh k8s-node4 cat /etc/kubernetes/kubelet.conf | grep server
```

```yaml
    server: https://localhost:6443
```

## kube-proxy 자격증명 확인

```bash
kubectl get cm -n kube-system kube-proxy -o yaml | grep 'kubeconfig.conf:' -A18
```

```yaml
  kubeconfig.conf: |-
    apiVersion: v1
    kind: Config
    clusters:
    - cluster:
        certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        server: https://127.0.0.1:6443
      name: default
...
```

<br>

# Control Plane: API Server 엔드포인트 분석

## kube-apiserver 바인딩 확인

```bash
kubectl describe pod -n kube-system kube-apiserver-k8s-node1 | grep -E 'address|secure-port'
```

```
Annotations:  kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint: 192.168.10.11:6443
      --advertise-address=192.168.10.11
      --secure-port=6443
      --bind-address=::
```

| 설정 | 값 | 설명 |
|------|----|----- |
| `--advertise-address` | `192.168.10.11` | 다른 컴포넌트에 알려주는 주소 |
| `--bind-address` | `::` | IPv6/IPv4 모두 리스닝 |
| `--secure-port` | `6443` | HTTPS 포트 |

## API Server 리스닝 확인

```bash
ssh k8s-node1 ss -tnlp | grep 6443
```

```
LISTEN 0  4096  *:6443  *:*  users:(("kube-apiserver",pid=26124,fd=3))
```

## 다양한 주소로 API Server 호출

```bash
ssh k8s-node1 curl -sk https://127.0.0.1:6443/version | grep gitVersion
ssh k8s-node1 curl -sk https://192.168.10.11:6443/version | grep gitVersion
ssh k8s-node1 curl -sk https://10.0.2.15:6443/version | grep gitVersion
```

모든 IP에서 정상 응답한다. `bind-address=::`로 설정되어 있어 모든 인터페이스에서 리스닝하기 때문이다.

## Control Plane 컴포넌트의 API Server 엔드포인트

```bash
# admin 자격증명
ssh k8s-node1 cat /etc/kubernetes/admin.conf | grep server
#     server: https://127.0.0.1:6443

# super-admin 자격증명 (첫 번째 노드만 존재)
ssh k8s-node1 cat /etc/kubernetes/super-admin.conf | grep server
#     server: https://192.168.10.11:6443

# kubelet
ssh k8s-node1 cat /etc/kubernetes/kubelet.conf | grep server
#     server: https://127.0.0.1:6443

# kube-controller-manager
ssh k8s-node1 cat /etc/kubernetes/controller-manager.conf | grep server
#     server: https://127.0.0.1:6443

# kube-scheduler
ssh k8s-node1 cat /etc/kubernetes/scheduler.conf | grep server
#     server: https://127.0.0.1:6443
```

**핵심**: Control Plane 노드의 모든 컴포넌트는 `https://127.0.0.1:6443`으로 API Server에 접근한다. 자기 노드에 API Server가 있기 때문에 로컬 호출이 가능하다.

## Lease 정보 확인

```bash
kubectl get lease -n kube-system
```

```
NAME                                   HOLDER                                   AGE
apiserver-3jsrenrspxlfjr2cvxzde6qwdi   apiserver-..._25f81820-25e1-4e92-...    5h12m
apiserver-syplgv2uz3ssgciixtnxs4xeza   apiserver-..._62b92e03-f014-4b16-...    5h12m
apiserver-z2kpjb5k5ch6lznxmv3gnpujmy   apiserver-..._c6523dd7-2550-462f-...    5h12m
kube-controller-manager                k8s-node2_5d90d703-85ad-4f58-...        5h12m
kube-scheduler                         k8s-node2_c3bdf688-9708-4313-...        5h12m
```

- **API Server**: 3개 모두 Active 동작
- **Controller Manager / Scheduler**: 1대만 리더 역할 (Leader Election)

<br>

# nginx.conf 생성 과정

## Jinja2 템플릿 확인

```bash
cat roles/kubernetes/node/templates/loadbalancer/nginx.conf.j2
```

```jinja2
error_log stderr notice;

worker_processes 2;
worker_rlimit_nofile 130048;
worker_shutdown_timeout 10s;

events {
  multi_accept on;
  use epoll;
  worker_connections 16384;
}

stream {
  upstream kube_apiserver {
    least_conn;
    {% for host in groups['kube_control_plane'] -%}
    server {{ hostvars[host]['main_access_ip'] | ansible.utils.ipwrap }}:{{ kube_apiserver_port }};
    {% endfor -%}
  }

  server {
    listen        127.0.0.1:{{ loadbalancer_apiserver_port|default(kube_apiserver_port) }};
    {% if ipv6_stack -%}
    listen        [::1]:{{ loadbalancer_apiserver_port|default(kube_apiserver_port) }};
    {% endif -%}
    proxy_pass    kube_apiserver;
    proxy_timeout 10m;
    proxy_connect_timeout 1s;
  }
}
...
```

| 템플릿 변수 | 설명 |
|------------|------|
| `groups['kube_control_plane']` | Control Plane 노드 목록 |
| `hostvars[host]['main_access_ip']` | 각 노드의 IP |
| `kube_apiserver_port` | API Server 포트 (6443) |

## Task 확인

```bash
cat roles/kubernetes/node/tasks/loadbalancer/nginx-proxy.yml
```

```yaml
- name: Nginx-proxy | Write nginx-proxy configuration
  template:
    src: "loadbalancer/nginx.conf.j2"
    dest: "{{ nginx_config_dir }}/nginx.conf"
    owner: root
    mode: "0755"
    backup: true
```

<br>

# 트러블슈팅: nginx rlimit 경고

## 문제 현상

```bash
kubectl logs -n kube-system nginx-proxy-k8s-node4
```

```
2026/01/28 04:02:40 [alert] 20#20: setrlimit(RLIMIT_NOFILE, 130048) failed (1: Operation not permitted)
2026/01/28 04:02:40 [alert] 21#21: setrlimit(RLIMIT_NOFILE, 130048) failed (1: Operation not permitted)
```

## 원인

containerd의 기본 OCI 스펙에서 `RLIMIT_NOFILE`이 65535로 제한되어 있는데, nginx 설정에서 130048을 요청하기 때문이다.

```bash
ssh k8s-node4 cat /etc/containerd/cri-base.json | jq | grep rlimits -A 6
```

```json
    "rlimits": [
      {
        "type": "RLIMIT_NOFILE",
        "hard": 65535,
        "soft": 65535
      }
    ],
```

## 해결 방법

containerd 설정을 수정하여 rlimits를 제거하면 OS 기본값을 사용한다.

```bash
# 변수 파일 수정
cat << EOF >> inventory/mycluster/group_vars/all/containerd.yml
containerd_default_base_runtime_spec_patch:
  process:
    rlimits: []
EOF

# containerd 태그만 재적용 (약 1분 소요)
ansible-playbook -i inventory/mycluster/inventory.ini -v cluster.yml \
  --tags "containerd" --limit k8s-node4 -e kube_version="1.32.9"
```

```bash
# 설정 확인
ssh k8s-node4 cat /etc/containerd/cri-base.json | jq | grep rlimits
#     "rlimits": [],

# nginx-proxy 컨테이너 재시작
ssh k8s-node4 crictl pods --namespace kube-system --name 'nginx-proxy-*' -q | xargs crictl rmp -f

# 로그 확인 (경고 없음)
kubectl logs -n kube-system nginx-proxy-k8s-node4
```

<br>

# Case 1 구성 요약

## 전체 구성도

```
┌─────────────────────────────────────────────────────────────┐
│                    Control Plane Nodes                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │   k8s-node1     │ │   k8s-node2     │ │   k8s-node3     │ │
│  │  ┌───────────┐  │ │  ┌───────────┐  │ │  ┌───────────┐  │ │
│  │  │ API Server│  │ │  │ API Server│  │ │  │ API Server│  │ │
│  │  │   :6443   │  │ │  │   :6443   │  │ │  │   :6443   │  │ │
│  │  └───────────┘  │ │  └───────────┘  │ │  └───────────┘  │ │
│  │       ▲         │ │       ▲         │ │       ▲         │ │
│  │       │         │ │       │         │ │       │         │ │
│  │  127.0.0.1:6443 │ │  127.0.0.1:6443 │ │  127.0.0.1:6443 │ │
│  │       ▲         │ │       ▲         │ │       ▲         │ │
│  │  ┌────┴────┐    │ │  ┌────┴────┐    │ │  ┌────┴────┐    │ │
│  │  │ kubelet │    │ │  │ kubelet │    │ │  │ kubelet │    │ │
│  │  │ kcm     │    │ │  │ kcm     │    │ │  │ kcm     │    │ │
│  │  │ sched   │    │ │  │ sched   │    │ │  │ sched   │    │ │
│  │  └─────────┘    │ │  └─────────┘    │ │  └─────────┘    │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ │
│           ▲                  ▲                  ▲             │
└───────────┼──────────────────┼──────────────────┼─────────────┘
            │                  │                  │
            └──────────────────┴──────────────────┘
                         least_conn
            ┌─────────────────────────────────────┐
            │       k8s-node4 (Worker)            │
            │  ┌──────────────────────────────┐   │
            │  │   nginx static pod           │   │
            │  │   listen 127.0.0.1:6443      │   │
            │  │   upstream:                  │   │
            │  │     - 192.168.10.11:6443     │   │
            │  │     - 192.168.10.12:6443     │   │
            │  │     - 192.168.10.13:6443     │   │
            │  └──────────────────────────────┘   │
            │               ▲                     │
            │               │                     │
            │  ┌────────────┴───────────────┐     │
            │  │ kubelet, kube-proxy        │     │
            │  │ → localhost:6443 (nginx)   │     │
            │  └────────────────────────────┘     │
            └─────────────────────────────────────┘
```

## 컴포넌트별 API Server 엔드포인트

| 위치 | 컴포넌트 | 엔드포인트 | 비고 |
|------|----------|-----------|------|
| **Control Plane** | kubelet | `https://127.0.0.1:6443` | 로컬 API Server 직접 접근 |
| **Control Plane** | kube-controller-manager | `https://127.0.0.1:6443` | 로컬 API Server 직접 접근 |
| **Control Plane** | kube-scheduler | `https://127.0.0.1:6443` | 로컬 API Server 직접 접근 |
| **Worker Node** | kubelet | `https://localhost:6443` | nginx static pod 경유 |
| **Worker Node** | kube-proxy | `https://127.0.0.1:6443` | nginx static pod 경유 |

## Case 1의 장점

| 장점 | 설명 |
|------|------|
| **인프라 팀 의존성 없음** | External LB 불필요, K8s 팀 독립 운영 |
| **장애 격리** | LB 레이어 없어 장애 포인트 감소 |
| **자동 Failover** | nginx가 백엔드 헬스체크 수행 |
| **간단한 구성** | Kubespray가 자동으로 nginx 배포 |

## Cilium 등 DaemonSet에서의 활용

```yaml
# Cilium Helm values 예시
k8sServiceHost: 127.0.0.1
k8sServicePort: 6443
```

**결론**: Control Plane이든 Worker 노드든 모두 `127.0.0.1:6443`으로 API Server에 접근할 수 있다. DaemonSet으로 배포된 CNI(Cilium 등)도 동일한 엔드포인트를 사용할 수 있다.

<br>

# 결과

Case 1 (Full Client-Side LB) 클러스터가 성공적으로 배포되었다.

| 구성 요소 | 상태 |
|----------|------|
| Control Plane (3대) | 정상 |
| etcd 클러스터 (3대) | 정상 |
| Worker Node (1대) | 정상 |
| nginx static pod | 정상 |
| Client-Side LB | 정상 |

다음 글에서는 **External LB(HAProxy)를 추가한 Case 2 (Hybrid LB)** 구성으로 전환하는 방법을 살펴본다.

<br>

# 참고 자료

- [Kubespray - HA endpoints for K8s](https://kubespray.io/#/docs/ha-mode)
- [Kubernetes - Options for HA topology](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/)
- [이전 글: HA 실습 환경]({% post_url 2026-02-02-Kubernetes-Kubespray-05-01 %})

<br>
