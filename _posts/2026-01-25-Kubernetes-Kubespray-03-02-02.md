---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.2.2. 변수 분석 - 그룹 변수 확인"
excerpt: "Kubespray의 group_vars 디렉토리 구조와 주요 설정 변수들을 확인해보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray의 주요 변수들을 실제로 확인**한다.

- **Ansible 그룹 변수 체계**: 디렉토리별 적용 범위, 조건부 적용, 변수 우선순위
- **group_vars/all/**: 전역 설정 (all.yml, etcd.yml, containerd.yml, 클라우드 프로바이더 등)
- **group_vars/k8s_cluster/**: 클러스터 설정 (k8s-cluster.yml, addons.yml, 네트워크 플러그인 등)

<br>

# 분석 대상: group_vars

[이전 글]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %})에서 정리한 Kubespray의 변수 구조를 떠올려 보자:

| 위치 | 역할 | 사용자 수정 |
|------|------|-------------|
| `roles/*/defaults/` | Kubespray의 기본값 (sensible defaults) | 직접 수정하지 않음 |
| `roles/*/vars/` | 내부 고정값 (체크섬 등) | 높은 우선순위로 보호됨 |
| `inventory/*/group_vars/` | **사용자 커스터마이징 영역** | 여기서 덮어씀 |

사용자는 **role의 defaults를 직접 수정하지 않고**, `group_vars/`에서 필요한 값만 덮어쓴다. 따라서 실제 설정 작업에서 확인하고 수정하는 대상은 `group_vars/`이다. 이번 글에서는 이 영역의 변수들을 살펴본다.

> **분석 환경**: Kubespray v2.28.x

<br>

# group_vars 구조

Kubespray의 사용자 설정 영역인 `inventory/mycluster/group_vars/` 구조를 확인한다.

## 전체 디렉토리 구조

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

## Ansible 그룹 변수 체계

Kubespray는 [Ansible 그룹 변수]({% post_url 2026-01-12-Kubernetes-Ansible-06 %}#실습-1-그룹-변수) 체계를 따른다. 각 디렉토리와 파일은 특정 호스트 그룹에 적용된다.

### 디렉토리별 적용 범위

| 디렉토리 | 적용 대상 | 우선순위 | 설명 |
|----------|----------|----------|------|
| `group_vars/all/` | 모든 호스트 | 4 | etcd, control plane, worker 전부 |
| `group_vars/k8s_cluster/` | k8s_cluster 그룹 | 6 | control plane + worker (etcd 제외 가능) |

### 조건부 적용 파일

`group_vars/all/` 내 일부 파일들은 **특정 변수 값에 따라 조건부로 적용**된다:

| 파일 유형 | 조건 변수 | 예시 |
|----------|----------|------|
| 클라우드 프로바이더 | `cloud_provider` | `cloud_provider: aws` → `aws.yml` 적용 |
| 컨테이너 런타임 | `container_manager` | `container_manager: containerd` → `containerd.yml` 적용 |
| 네트워크 플러그인 | `kube_network_plugin` | `kube_network_plugin: calico` → `k8s-net-calico.yml` 적용 |

```yaml
# k8s-cluster.yml에서 설정하면
kube_network_plugin: calico      # → k8s-net-calico.yml 적용
container_manager: containerd    # → containerd.yml 적용
```

### 변수 우선순위

```
group_vars/all/ < group_vars/k8s_cluster/ < host_vars/ < 플레이북 변수 < 커맨드라인(-e)
```

더 구체적인 범위가 더 높은 우선순위를 가진다. `k8s_cluster`의 설정이 `all`의 설정을 덮어쓴다.

> **참고**: 공식 문서 [Kubespray Variables](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/ansible/vars.md)에서 변수 개요를 확인할 수 있다.

<br>

# group_vars/all/ 분석

모든 노드에 적용되는 전역 설정이다.

## all.yml

주석이 아닌 실제 설정값만 확인한다:

```bash
grep "^[^#]" inventory/mycluster/group_vars/all/all.yml
```

```yaml
---
bin_dir: /usr/local/bin
loadbalancer_apiserver_port: 6443
loadbalancer_apiserver_healthcheck_port: 8081
no_proxy_exclude_workers: false
kube_webhook_token_auth: false
kube_webhook_token_auth_url_skip_tls_verify: false
ntp_enabled: false
ntp_manage_config: false
ntp_servers:
  - "0.pool.ntp.org iburst"
  - "1.pool.ntp.org iburst"
  - "2.pool.ntp.org iburst"
  - "3.pool.ntp.org iburst"
unsafe_show_logs: false
allow_unsupported_distribution_setup: false
```

### 주요 변수 설명

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `bin_dir` | `/usr/local/bin` | 바이너리 설치 경로 |
| `loadbalancer_apiserver_port` | `6443` | API Server 로드밸런서 포트 |
| `ntp_enabled` | `false` | NTP 동기화 활성화 여부 |
| `ntp_servers` | pool.ntp.org | NTP 서버 목록 |
| `unsafe_show_logs` | `false` | 민감한 정보 로그 출력 여부 |
| `allow_unsupported_distribution_setup` | `false` | 미지원 OS 배포판 허용 여부 |

<br>

## etcd.yml

etcd 설정이다:

```bash
grep "^[^#]" inventory/mycluster/group_vars/all/etcd.yml
```

```yaml
---
etcd_data_dir: /var/lib/etcd
etcd_deployment_type: host
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `etcd_data_dir` | `/var/lib/etcd` | etcd 데이터 저장 경로 |
| `etcd_deployment_type` | `host` | etcd 배포 방식 (`host`: systemd, `kubeadm`: static pod) |

> **참고**: `etcd_deployment_type: host`는 etcd를 **Pod가 아닌 systemd unit**으로 실행한다. kubeadm 기본 방식(static pod)과 다르다.

<br>

## containerd.yml

컨테이너 런타임 설정이다:

```bash
cat inventory/mycluster/group_vars/all/containerd.yml
```

```yaml
---
# Please see roles/container-engine/containerd/defaults/main.yml for more configuration options

# containerd_storage_dir: "/var/lib/containerd"
# containerd_state_dir: "/run/containerd"
# containerd_oom_score: 0

# containerd_default_runtime: "runc"
# containerd_snapshotter: "native"

# containerd_runc_runtime:
#   name: runc
#   type: "io.containerd.runc.v2"
#   engine: ""
# ...(생략)...
```

대부분 주석 처리되어 있어 **defaults 값을 그대로 사용**한다. 커스터마이징이 필요한 경우 주석을 해제하고 값을 변경한다.

> 더 많은 옵션은 `roles/container-engine/containerd/defaults/main.yml` 참고

## 클라우드 프로바이더 파일들

`aws.yml`, `azure.yml`, `gcp.yml` 등은 `cloud_provider` 변수 값에 따라 **조건부로 활성화**된다:

```yaml
# all.yml에서 설정 시
cloud_provider: aws  # → aws.yml의 변수들이 활성화됨
```

| 파일 | 용도 |
|------|------|
| `aws.yml` | AWS EBS CSI Driver 등 AWS 특화 설정 |
| `azure.yml` | Azure Disk CSI 등 Azure 특화 설정 |
| `gcp.yml` | GCP Persistent Disk 등 GCP 특화 설정 |
| `openstack.yml` | OpenStack Cinder 등 OpenStack 특화 설정 |
| `vsphere.yml` | vSphere CSI 등 VMware 특화 설정 |
| `offline.yml` | 오프라인(에어갭) 환경 설치 설정 |

대부분 주석 처리되어 있으며, 해당 클라우드 환경에서만 주석을 해제하여 사용한다.

## docker.yml

Docker 컨테이너 런타임 설정이다 (`container_manager: docker` 시 적용):

```yaml
# docker_storage_options: -s overlay2
docker_container_storage_setup: false
docker_dns_servers_strict: false
docker_daemon_graph: "/var/lib/docker"
docker_iptables_enabled: "false"
docker_log_opts: "--log-opt max-size=50m --log-opt max-file=5"
docker_bin_dir: "/usr/bin"
docker_rpm_keepcache: 1
```

> **참고**: Kubernetes 1.24부터 Docker(dockershim)는 deprecated되었다. containerd 또는 CRI-O 사용을 권장한다.

<br>

# group_vars/k8s_cluster/ 분석

Kubernetes 클러스터 노드(control plane + worker)에 적용되는 설정이다.

## k8s-cluster.yml

클러스터의 핵심 설정 파일이다:

```bash
grep "^[^#]" inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```

```yaml
---
kube_config_dir: /etc/kubernetes
kube_script_dir: "{{ bin_dir }}/kubernetes-scripts"
kube_manifest_dir: "{{ kube_config_dir }}/manifests"
kube_cert_dir: "{{ kube_config_dir }}/ssl"
kube_token_dir: "{{ kube_config_dir }}/tokens"
kube_api_anonymous_auth: true
local_release_dir: "/tmp/releases"
retry_stagger: 5
kube_owner: kube
kube_cert_group: kube-cert
kube_log_level: 2
credentials_dir: "{{ inventory_dir }}/credentials"
kube_network_plugin: calico
kube_network_plugin_multus: false
kube_service_addresses: 10.233.0.0/18
kube_pods_subnet: 10.233.64.0/18
kube_network_node_prefix: 24
kube_service_addresses_ipv6: fd85:ee78:d8a6:8607::1000/116
kube_pods_subnet_ipv6: fd85:ee78:d8a6:8607::1:0000/112
kube_network_node_prefix_ipv6: 120
kube_apiserver_ip: "{{ kube_service_subnets.split(',') | ... }}"
kube_apiserver_port: 6443
kube_proxy_mode: ipvs
kube_proxy_strict_arp: false
kube_encrypt_secret_data: false
cluster_name: cluster.local
ndots: 2
dns_mode: coredns
enable_nodelocaldns: true
enable_nodelocaldns_secondary: false
nodelocaldns_ip: 169.254.25.10
resolvconf_mode: host_resolvconf
deploy_netchecker: false
dns_domain: "{{ cluster_name }}"
container_manager: containerd
kata_containers_enabled: false
k8s_image_pull_policy: IfNotPresent
kubernetes_audit: false
volume_cross_zone_attachment: false
persistent_volumes_enabled: false
event_ttl_duration: "1h0m0s"
auto_renew_certificates: false
kubeadm_patches_dir: "{{ kube_config_dir }}/patches"
kubeadm_patches: []
remove_anonymous_access: false
```

### 주요 변수 카테고리별 정리

#### 디렉토리 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `kube_config_dir` | `/etc/kubernetes` | Kubernetes 설정 디렉토리 |
| `kube_cert_dir` | `/etc/kubernetes/ssl` | 인증서 저장 경로 |
| `kube_manifest_dir` | `/etc/kubernetes/manifests` | static pod manifest 경로 |

#### 네트워크 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `kube_network_plugin` | `calico` | CNI 플러그인 (`calico`, `flannel`, `cilium` 등) |
| `kube_service_addresses` | `10.233.0.0/18` | Service CIDR |
| `kube_pods_subnet` | `10.233.64.0/18` | Pod CIDR |
| `kube_network_node_prefix` | `24` | 노드당 할당되는 Pod 서브넷 크기 |
| `kube_proxy_mode` | `ipvs` | kube-proxy 모드 (`iptables`, `ipvs`, `nftables`) |

#### DNS 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `dns_mode` | `coredns` | 클러스터 DNS 종류 |
| `enable_nodelocaldns` | `true` | NodeLocal DNSCache 활성화 |
| `nodelocaldns_ip` | `169.254.25.10` | NodeLocal DNS IP |
| `cluster_name` | `cluster.local` | 클러스터 도메인 |

#### 컨테이너 런타임

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `container_manager` | `containerd` | 컨테이너 런타임 (`containerd`, `crio`) |
| `kata_containers_enabled` | `false` | Kata Containers 활성화 |

#### 인증서 관리

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `auto_renew_certificates` | `false` | 인증서 자동 갱신 활성화 |
| `auto_renew_certificates_systemd_calendar` | (주석 처리) | 자동 갱신 스케줄 |

<br>

## addons.yml

Kubernetes 애드온 설정이다:

```bash
grep "^[^#]" inventory/mycluster/group_vars/k8s_cluster/addons.yml
```

```yaml
---
helm_enabled: false
registry_enabled: false
metrics_server_enabled: false
local_path_provisioner_enabled: false
local_volume_provisioner_enabled: false
gateway_api_enabled: false
ingress_nginx_enabled: false
ingress_publish_status_address: ""
ingress_alb_enabled: false
cert_manager_enabled: false
metallb_enabled: false
metallb_speaker_enabled: "{{ metallb_enabled }}"
metallb_namespace: "metallb-system"
argocd_enabled: false
kube_vip_enabled: false
node_feature_discovery_enabled: false
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `helm_enabled` | `false` | Helm 설치 |
| `metrics_server_enabled` | `false` | Metrics Server 설치 |
| `ingress_nginx_enabled` | `false` | Nginx Ingress Controller 설치 |
| `cert_manager_enabled` | `false` | cert-manager 설치 |
| `metallb_enabled` | `false` | MetalLB 설치 (Bare Metal LB) |
| `argocd_enabled` | `false` | ArgoCD 설치 |

> **참고**: 필요한 애드온은 `true`로 변경하여 활성화한다. 각 애드온별 세부 설정은 해당 파일 내 주석을 참고한다.

## kube_control_plane.yml

Control Plane 노드 전용 리소스 예약 설정이다:

```bash
cat inventory/mycluster/group_vars/k8s_cluster/kube_control_plane.yml
```

```yaml
# Reservation for control plane kubernetes components
# kube_memory_reserved: 512Mi
# kube_cpu_reserved: 200m
# kube_ephemeral_storage_reserved: 2Gi
# kube_pid_reserved: "1000"

# Reservation for control plane host system
# system_memory_reserved: 256Mi
# system_cpu_reserved: 250m
# system_ephemeral_storage_reserved: 2Gi
# system_pid_reserved: "1000"
```

| 변수 | 용도 |
|------|------|
| `kube_memory_reserved` | Kubernetes 컴포넌트용 메모리 예약 |
| `kube_cpu_reserved` | Kubernetes 컴포넌트용 CPU 예약 |
| `system_memory_reserved` | 호스트 시스템용 메모리 예약 |
| `system_cpu_reserved` | 호스트 시스템용 CPU 예약 |

기본적으로 모두 주석 처리되어 있다. 프로덕션 환경에서는 Control Plane 안정성을 위해 리소스 예약을 설정하는 것이 좋다.

## 네트워크 플러그인 파일들

`kube_network_plugin` 변수 값에 따라 해당 CNI 설정 파일이 적용된다:

| 파일 | CNI | 설명 |
|------|-----|------|
| `k8s-net-calico.yml` | Calico | BGP 기반, NetworkPolicy 지원 |
| `k8s-net-flannel.yml` | Flannel | 간단한 오버레이 네트워크 |
| `k8s-net-cilium.yml` | Cilium | eBPF 기반, 고성능 |
| `k8s-net-kube-ovn.yml` | Kube-OVN | OVN/OVS 기반 |
| `k8s-net-kube-router.yml` | Kube-Router | BGP 기반, 경량 |

```yaml
# k8s-cluster.yml에서
kube_network_plugin: calico  # → k8s-net-calico.yml 적용
```

<br>

# 지원 버전 확인

Kubespray가 지원하는 Kubernetes 버전을 확인할 수 있다:

```bash
cat roles/kubespray_defaults/vars/main/checksums.yml | grep -i kube -A40
```

`checksums.yml` 파일에는 각 버전별 바이너리 체크섬이 정의되어 있다. 이 파일에 체크섬이 있는 버전만 설치할 수 있다.

> **참고**: `checksums.yml`은 role vars(우선순위 15)에 위치하므로 사용자가 쉽게 덮어쓸 수 없다. 새로운 버전을 사용하려면 Kubespray를 업데이트해야 한다.

<br>

# 결과

Kubespray의 group_vars 구조와 주요 변수들을 확인했다:

1. **Ansible 그룹 변수 체계**: 디렉토리별 적용 범위와 조건부 적용 원리
2. **group_vars/all/**: 전역 설정 (all.yml, etcd.yml, containerd.yml, 클라우드 프로바이더)
3. **group_vars/k8s_cluster/**: 클러스터 설정 (k8s-cluster.yml, addons.yml, kube_control_plane.yml, 네트워크 플러그인)

핵심 이해:
- `cloud_provider`, `container_manager`, `kube_network_plugin` 값에 따라 **조건부로 파일이 적용**됨
- 더 구체적인 범위(`k8s_cluster`)가 전역 범위(`all`)보다 **높은 우선순위**를 가짐

다음 글에서는 [kubespray_defaults 역할]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-03 %})을 분석한다. 실제 변수 수정 및 클러스터 배포는 [실습 시리즈]({% post_url 2026-01-25-Kubernetes-Kubespray-04-01 %})에서 진행한다.

<br>

# 참고 자료

- [Kubespray Variables Documentation](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/ansible/vars.md)
- [이전 글: 변수 배치 전략]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %})

<br>
