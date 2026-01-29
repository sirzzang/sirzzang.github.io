---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.0. 프로젝트 구조 Overview"
excerpt: "Kubespray 프로젝트의 전체 디렉토리 구조를 살펴보고, 핵심 파일들을 파악해보자."
categories:
  - Kubernetes
toc: true
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

이번 글에서는 **Kubespray 프로젝트의 전체 구조**를 파악한다.

- **핵심 플레이북**: `cluster.yml`, `reset.yml`, `scale.yml`, `upgrade-cluster.yml` 등
- **roles/**: 실제 작업을 수행하는 Ansible 롤들
- **inventory/**: 클러스터 호스트 정보와 변수 정의
- **ansible.cfg**: Ansible 실행 설정


<br>

# 프로젝트 구조 개요

Kubespray는 Ansible 기반 프로젝트로, 표준 Ansible 프로젝트 구조를 따른다.

```bash
kubespray/
├── ansible.cfg                 # Ansible 설정
├── cluster.yml                 # 메인 플레이북 (클러스터 생성)
├── reset.yml                   # 클러스터 초기화
├── scale.yml                   # 노드 추가
├── upgrade-cluster.yml         # 클러스터 업그레이드
├── remove-node.yml             # 노드 제거
├── recover-control-plane.yml   # 컨트롤 플레인 복구
│
├── inventory/                  # 인벤토리 (호스트 정보)
│   ├── local/                  # 로컬 테스트용
│   └── sample/                 # 샘플 인벤토리
│
├── roles/                      # Ansible 롤 (실제 작업 정의)
│   ├── kubernetes/             # K8s 컴포넌트 설치
│   ├── etcd/                   # etcd 설치/관리
│   ├── container-engine/       # containerd 등 컨테이너 런타임
│   ├── network_plugin/         # CNI 플러그인
│   └── ...
│
├── playbooks/                  # 하위 플레이북
└── docs/                       # 문서
```

<details markdown="1">
<summary>전체 디렉토리 구조 (클릭하여 펼치기)</summary>

```bash
.
├── ansible.cfg
├── CHANGELOG.md
├── cluster.yml
├── CNAME
├── code-of-conduct.md
├── _config.yml
├── contrib
│   ├── aws_iam
│   ├── aws_inventory
│   ├── azurerm
│   ├── offline
│   ├── os-services
│   └── terraform
├── CONTRIBUTING.md
├── Dockerfile
├── docs
│   ├── advanced
│   ├── ansible
│   ├── calico_peer_example
│   ├── cloud_controllers
│   ├── cloud_providers
│   ├── CNI
│   ├── CRI
│   ├── CSI
│   ├── developers
│   ├── external_storage_provisioners
│   ├── figures
│   ├── getting_started
│   ├── img
│   ├── ingress
│   ├── operating_systems
│   ├── operations
│   ├── roadmap
│   ├── _sidebar.md
│   └── upgrades
├── extra_playbooks
│   ├── files
│   ├── inventory -> ../inventory
│   ├── migrate_openstack_provider.yml
│   ├── roles -> ../roles
│   ├── upgrade-only-k8s.yml
│   └── wait-for-cloud-init.yml
├── galaxy.yml
├── index.html
├── inventory
│   ├── local
│   └── sample
├── library
│   └── kube.py -> ../plugins/modules/kube.py
├── LICENSE
├── logo
├── meta
│   └── runtime.yml
├── OWNERS
├── OWNERS_ALIASES
├── pipeline.Dockerfile
├── playbooks
│   ├── ansible_version.yml
│   ├── boilerplate.yml
│   ├── cluster.yml
│   ├── facts.yml
│   ├── install_etcd.yml
│   ├── internal_facts.yml
│   ├── recover_control_plane.yml
│   ├── remove_node.yml
│   ├── reset.yml
│   ├── scale.yml
│   └── upgrade_cluster.yml
├── plugins
│   └── modules
├── README.md
├── recover-control-plane.yml
├── RELEASE.md
├── remove-node.yml
├── remove_node.yml
├── requirements.txt
├── reset.yml
├── roles
│   ├── adduser
│   ├── bastion-ssh-config
│   ├── bootstrap-os
│   ├── bootstrap_os
│   ├── container-engine
│   ├── download
│   ├── dynamic_groups
│   ├── etcd
│   ├── etcdctl_etcdutl
│   ├── etcd_defaults
│   ├── helm-apps
│   ├── kubernetes
│   ├── kubernetes-apps
│   ├── kubespray-defaults
│   ├── kubespray_defaults
│   ├── network_facts
│   ├── network_plugin
│   ├── recover_control_plane
│   ├── remove-node
│   ├── remove_node
│   ├── reset
│   ├── system_packages
│   ├── upgrade
│   ├── validate_inventory
│   └── win_nodes
├── scale.yml
├── scripts
│   ├── assert-sorted-checksums.yml
│   ├── collect-info.yaml
│   ├── component_hash_update
│   ├── Dockerfile.j2
│   ├── galaxy_version.py
│   ├── gen_docs_sidebar.sh
│   ├── get_node_ids.sh
│   ├── gitlab-runner.sh
│   ├── openstack-cleanup
│   ├── pipeline.Dockerfile.j2
│   ├── propagate_ansible_variables.yml
│   └── readme_versions.md.j2
├── SECURITY_CONTACTS
├── test-infra
│   ├── image-builder
│   └── vagrant-docker
├── tests
├── upgrade-cluster.yml
├── upgrade_cluster.yml
└── Vagrantfile

77 directories, 70 files
```

</details>

<br>

# 핵심 플레이북

루트 디렉토리에 있는 주요 플레이북들이다. 클러스터 운영의 전체 라이프사이클을 커버한다.

| 플레이북 | 용도 | 비고 |
|----------|------|------|
| `cluster.yml` | 클러스터 생성 | 메인 플레이북 |
| `reset.yml` | 클러스터 초기화 | `kubeadm reset`과 유사 |
| `scale.yml` | 노드 추가 | 기존 클러스터에 노드 추가 |
| `upgrade-cluster.yml` | 클러스터 업그레이드 | K8s 버전 업그레이드 |
| `remove-node.yml` | 노드 제거 | 특정 노드 제거 |
| `recover-control-plane.yml` | 컨트롤 플레인 복구 | 장애 복구 |

> **참고: 중복 파일명**
>
> `remove-node.yml`과 `remove_node.yml`처럼 하이픈(-) 버전과 언더스코어(_) 버전이 공존한다. 이는 **하위 호환성**을 위한 것이다.
> - Kubespray가 파일명 표준을 `snake_case` → `kebab-case`로 변경
> - 기존 스크립트가 깨지지 않도록 두 버전 모두 유지
> - **권장**: 새로운 코드 작성 시 하이픈(-) 버전 사용

<br>

# 주요 디렉토리

## inventory/

클러스터 호스트 정보와 그룹 변수를 정의하는 곳이다.

```bash
inventory/
├── local/                    # 단일 노드 로컬 테스트용
└── sample/                   # 샘플 인벤토리 (복사해서 사용)
    ├── inventory.ini         # 호스트 정의
    └── group_vars/           # 그룹별 변수
        ├── all/              # 전체 공통 변수
        │   └── all.yml
        └── k8s_cluster/      # 클러스터 설정
            ├── k8s-cluster.yml
            └── addons.yml
```

[이전 실습]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %})에서 `inventory/sample`을 복사하여 `inventory/mycluster`를 만들고 사용했다.

### Sample Inventory 구조

```ini
# inventory/sample/inventory.ini
[kube_control_plane]
# node1 ansible_host=95.54.0.12

[etcd:children]
kube_control_plane

[kube_node]
# node4 ansible_host=95.54.0.15

[k8s_cluster:children]
kube_control_plane
kube_node
```

### `[etcd]` vs `[etcd:children]`

Sample inventory는 `[etcd:children]`을 사용한다:

```ini
[etcd:children]
kube_control_plane
```

이 방식은 **"control plane 노드 = etcd 노드"로 자동 매핑**한다. HA 구성(control plane 3대 = etcd 3대)에서 편리하다.

[이전 실습]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %})에서는 `[etcd]`에 직접 호스트를 나열했다:

```ini
[etcd]
controller-0
```

| 방식 | 장점 | 적합한 경우 |
|------|------|-------------|
| `[etcd:children]` | 설정 간단, 자동 매핑 | control plane = etcd 노드인 경우 |
| `[etcd]` 직접 나열 | 독립적 관리 가능 | etcd를 별도 노드로 분리하거나, 노드 수가 다른 경우 |

> **결론**: 현재 구성(컨트롤 플레인 1대)에서는 둘 다 동일하게 동작한다. `cluster.yml`은 `[etcd]` 그룹의 호스트들에 etcd를 설치하는데, `[etcd:children]`으로 정의하면 자식 그룹의 호스트들이 자동으로 포함된다.

<br>

## roles/

실제 작업을 수행하는 Ansible 롤들이다. Kubespray의 핵심이다.

| 롤 | 역할 |
|----|------|
| `bootstrap-os` | OS 기본 설정 (패키지, 커널 파라미터 등) |
| `container-engine` | containerd, Docker 등 컨테이너 런타임 설치 |
| `etcd` | etcd 클러스터 설치/관리 |
| `kubernetes` | K8s 컴포넌트 (kubelet, kubeadm 등) 설치 |
| `kubernetes-apps` | 애드온 (CoreDNS, Dashboard 등) 설치 |
| `network_plugin` | CNI 플러그인 (Calico, Flannel 등) 설치 |
| `download` | 필요한 바이너리/이미지 다운로드 |
| `kubespray-defaults` | 기본 변수 로드 태스크 |
| `kubespray_defaults` | 기본 변수 값 정의 |

> **참고: 롤의 하이픈/언더스코어 버전 차이**
>
> `bootstrap-os`와 `bootstrap_os`처럼 하이픈/언더스코어 버전이 공존하는 롤이 있다. 플레이북처럼 단순 하위 호환성인 경우도 있지만, **역할이 다른 경우**도 있다.
>
> 예: `kubespray-defaults` vs. `kubespray_defaults`
>
> ```bash
> # kubespray_defaults: 변수 값 정의 (defaults/, vars/)
> roles/kubespray_defaults/
> ├── defaults/main/
> │   ├── download.yml      # 다운로드 관련 기본값
> │   └── main.yml
> └── vars/main/
>     ├── checksums.yml     # 체크섬 값들
>     └── main.yml
>
> # kubespray-defaults: 변수 로드 태스크 (tasks/)
> roles/kubespray-defaults/
> └── tasks/
>     └── main.yml          # 변수를 로드하는 태스크
> ```
>
> | 롤 | 역할 |
> |----|------|
> | `kubespray_defaults` | 실제 변수 **값**을 정의 |
> | `kubespray-defaults` | 변수를 **로드/설정**하는 태스크 |
>
> 비슷하게 `bootstrap_os`는 변수를, `bootstrap-os`는 실제 태스크를 담고 있을 수 있다. 롤 분석 시 내부 구조를 확인해야 한다.

<br>

## playbooks/

메인 플레이북(`cluster.yml` 등)에서 import하는 하위 플레이북들이다.

```bash
playbooks/
├── cluster.yml              # 실제 클러스터 생성 로직
├── facts.yml                # 팩트 수집
├── install_etcd.yml         # etcd 설치
├── scale.yml                # 노드 추가
├── reset.yml                # 초기화
└── upgrade_cluster.yml      # 업그레이드
```

루트의 `cluster.yml`은 주로 `playbooks/cluster.yml`을 import한다.

<br>

# ansible.cfg

Kubespray는 프로젝트 루트에 자체 `ansible.cfg`를 포함하고 있다. **Kubespray 디렉토리에서 실행해야** 이 설정이 적용된다.

> `ansible.cfg`의 상세 분석은 [ansible.cfg 분석]({% post_url 2026-01-25-Kubernetes-Kubespray-03-01 %}) 글을 참고하자.

<br>

# 결과

Kubespray 분석 시 다음 순서로 살펴보면 좋다:

1. **cluster.yml**: 메인 플레이북 흐름 파악
2. **inventory/sample**: 인벤토리 구조와 group_vars 이해
3. **roles/kubespray-defaults**: 기본 변수 확인
4. **roles/kubernetes**: K8s 컴포넌트 설치 로직
5. **roles/etcd**: etcd 설치 로직
6. **roles/network_plugin**: CNI 설치 로직

> 다음 글부터 `cluster.yml`을 시작으로 각 롤을 상세히 분석한다.

<br>

# 참고 자료

- [Kubespray GitHub](https://github.com/kubernetes-sigs/kubespray)
- [Kubespray 이전 글: Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %})
- [Kubespray 이전 글: 개요]({% post_url 2026-01-25-Kubernetes-Kubespray-01 %})
- [Kubespray 이전 글: Kubernetes The Kubespray Way]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %})

<br>
