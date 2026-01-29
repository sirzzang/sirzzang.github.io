---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.2.1. 변수 분석 - Kubespray 변수 배치 전략"
excerpt: "Kubespray의 변수 배치 전략을 이해하고, 변수 분석 시 어디를 봐야 하는지 파악해보자."
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

이번 글에서는 **Kubespray의 변수 배치 전략**을 분석한다.

- **Ansible 변수 우선순위**: 22단계 우선순위에 따라 변수가 덮어쓰임
- **Kubespray 설계 전략**: role defaults(기본값) → inventory group_vars(사용자 설정) → role vars(내부 고정값)
- **변수 분석 흐름**: docs 개요 파악 → role defaults → inventory group_vars 순으로 분석
- **다음 글 예고**: 사용자가 실제로 수정할 수 있는 `inventory/group_vars/` 영역을 상세히 분석

> **분석 환경**: Kubespray v2.28.x. 버전에 따라 기본값이나 파일 구조가 다를 수 있다.

Kubespray 변수는 `roles/kubespray_defaults/defaults/main/main.yml`만 800줄이 넘고, `download.yml`은 1100줄이 넘는다. 모든 변수를 다 파악하기는 힘들기 때문에, 이 글에서는 **변수 배치 전략을 이해하고 어디를 봐야 하는지 파악하는 것**에 집중하고자 한다. 

<br>

# Kubespray 변수 개요

Kubespray는 Ansible 기반 프로젝트로, 수많은 변수를 통해 클러스터 구성을 제어한다. 공식 문서에서 변수 개요를 확인할 수 있다.

- [Kubespray Variables Documentation](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/ansible/vars.md)

> **참고**: 이 문서는 "어떤 변수들을 바꿀 수 있는지" 개요를 파악하는 용도로 적합하다. 실제 변수가 정의된 곳은 코드에서 직접 확인하는 것이 좋다.

## 주요 변수 카테고리

| 카테고리 | 설명 | 예시 |
|----------|------|------|
| **Generic Ansible variables** | Ansible이 자동 수집하는 팩트 | `ansible_user`, `ansible_default_ipv4.address` |
| **Common vars** | Kubespray에서 자주 사용하는 변수 | `kube_version`, `kube_network_plugin` |
| **Addressing variables** | 네트워크 주소 관련 | `ip`, `access_ip`, `loadbalancer_apiserver` |
| **Cluster variables** | 클러스터 전체 설정 | `cluster_name`, `kube_service_addresses` |
| **DNS variables** | DNS 설정 | `dns_mode`, `resolvconf_mode` |

<br>

## Generic Ansible Variables

Ansible이 자동으로 수집하는 [팩트(facts)](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html#ansible-facts)다.

| 변수 | 설명 |
|------|------|
| `ansible_user` | SSH 연결 유저 |
| `ansible_default_ipv4.address` | Ansible이 자동으로 선택하는 IP 주소 |

`ansible_default_ipv4.address`는 다음 커맨드 결과를 기반으로 생성된다:

```bash
root@k8s-ctr:~/kubespray# ip -4 route get 8.8.8.8
8.8.8.8 via 10.0.2.2 dev enp0s3 src 10.0.2.15 uid 0 
    cache 
```

## Common Vars

Kubespray에서 자주 사용하는 변수들이다.

| 변수 | 설명 | 비고 |
|------|------|------|
| `kube_version` | Kubernetes 버전 | |
| `kube_network_plugin` | CNI 플러그인 | `calico`, `flannel` 등 |
| `kube_proxy_mode` | kube-proxy 모드 | `iptables`, `ipvs`, `nftables` |
| `container_manager` | 컨테이너 런타임 | `containerd`, `docker` |
| `etcd_version` | etcd 버전 | |

### 컨테이너 런타임 관련 변수

`container_manager` 설정에 따라 사용하는 변수가 달라진다:

```bash
# container_manager 설정에 따라
container_manager: docker
  → docker_version, docker_containerd_version 사용

container_manager: containerd
  → containerd_version 사용
```

| 변수 | 조건 | 설명 |
|------|------|------|
| `containerd_version` | `container_manager: containerd` | 독립적인 containerd 버전 |
| `docker_containerd_version` | `container_manager: docker` | Docker 내부 containerd 버전 |
| `docker_version` | `container_manager: docker` | Docker 버전 (quoted string) |

> **참고**: `docker_version`은 `roles/container-engine/docker/vars/*.yml`에 정의된 `docker_versioned_pkg` 키 중 하나여야 한다. 각 OS 배포판마다 패키지 버전 표기법이 다르다.

### Calico 관련 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `calico_ipip_mode` | `Always` | IPIP encapsulation 모드 (`Never`, `Always`, `CrossSubnet`) |
| `calico_vxlan_mode` | `Never` | VXLAN encapsulation 모드 |
| `calico_network_backend` | `bird` | 네트워크 백엔드 (`none`, `bird`, `vxlan`) |

> **참고**: 이 기본값들은 Kubespray 버전에 따라 다를 수 있다. 실제 값은 `roles/network_plugin/calico/defaults/main.yml`에서 확인하자.

## Addressing Variables

네트워크 주소 관련 변수들이다.

| 변수 | 설명 | 비고 |
|------|------|------|
| `ip` | 서비스 바인딩에 사용할 IP (host var) | 대부분 public IP |
| `access_ip` | 다른 호스트가 해당 호스트에 접근할 때 사용할 IP | 대부분 private IP |
| `loadbalancer_apiserver` | API 서버 로드밸런서 주소 | HA 구성 시 사용 |

> **참고**: `ip`, `access_ip`가 없으면 `ansible_default_ipv4.address`가 fallback으로 사용된다.

<br>

# Ansible 변수 우선순위

Kubespray의 변수 시스템을 이해하려면 먼저 Ansible의 변수 우선순위를 알아야 한다. 

이전에 [Ansible 시리즈 - 변수 우선순위]({% post_url 2026-01-12-Kubernetes-Ansible-06 %}#변수-우선순위)와 [롤 구조]({% post_url 2026-01-12-Kubernetes-Ansible-11 %}#롤-구조)에서 다뤘던 내용을 Kubespray 관점에서 다시 정리한다.

## 우선순위 체계

Ansible은 [22단계 변수 우선순위](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)를 가진다. 숫자가 클수록 우선순위가 높다.

```
1.  command line values (for example, -u my_user)
2.  role defaults (roles/*/defaults/main.yml)
3.  inventory file or script group vars
4.  inventory group_vars/all
5.  playbook group_vars/all
6.  inventory group_vars/*
7.  playbook group_vars/*
8.  inventory file or script host vars
9.  inventory host_vars/*
10. playbook host_vars/*
11. host facts / cached set_facts
12. play vars
13. play vars_prompt
14. play vars_files
15. role vars (roles/*/vars/main.yml)
16. block vars
17. task vars
18. include_vars
19. set_facts / registered vars
20. role parameters
21. include parameters
22. extra vars (-e) (always win)
```

주요 계층을 나타내 보면, 아래와 같다.

```
┌─────────────────────┐
│   extra_vars (-e)   │  22 ← 최고 우선순위
├─────────────────────┤
│   task vars         │  17
├─────────────────────┤
│   role/vars/        │  15
├─────────────────────┤
│   play vars         │  12
├─────────────────────┤
│   host_vars/        │  9
├─────────────────────┤
│   group_vars/*      │  6
├─────────────────────┤
│   group_vars/all    │  4
├─────────────────────┤
│   role/defaults/    │  2  ← 최저 우선순위
└─────────────────────┘
```

## Kubespray 파일 경로 매핑

22단계 우선순위를 Kubespray 파일 경로와 매핑하면 다음과 같다:

| 순위 | 카테고리 | 설명 | Kubespray 파일/경로 |
|------|----------|------|---------------------|
| 1 | command line values | `-u`, `-k` 등 (변수 아님) | N/A |
| 2 | **role defaults** | role 기본값 | `roles/*/defaults/main.yml` |
| 3 | inventory file group vars | inventory 파일 내 `[group:vars]` | `inventory.ini` 내 `[all:vars]` 등 |
| 4 | **inventory group_vars/all** | 전역 그룹 변수 | `inventory/mycluster/group_vars/all/*.yml` |
| 5 | playbook group_vars/all | playbook 디렉토리의 group_vars | `playbooks/group_vars/all/*.yml` (거의 없음) |
| 6 | **inventory group_vars/*** | 특정 그룹 변수 | `inventory/mycluster/group_vars/k8s_cluster/*.yml` |
| 7 | playbook group_vars/* | playbook 디렉토리의 그룹 변수 | `playbooks/group_vars/*/*.yml` (거의 없음) |
| 8 | inventory file host vars | inventory 파일 내 호스트 변수 | `inventory.ini` 내 `node1 ansible_host=...` |
| 9 | **inventory host_vars/*** | 특정 호스트 변수 | `inventory/mycluster/host_vars/*.yml` |
| 10 | playbook host_vars/* | playbook 디렉토리의 호스트 변수 | `playbooks/host_vars/*.yml` (거의 없음) |
| 11 | host facts | gathered facts, cached facts | `ansible_*` 변수들 |
| 12 | **play vars** | play 레벨 `vars:` | [play vars 섹션 참조](#play-vars-우선순위-12) |
| 13 | play vars_prompt | play 레벨 `vars_prompt:` | 거의 없음 |
| 14 | play vars_files | play 레벨 `vars_files:` | 거의 없음 |
| 15 | **role vars** | role 내부 고정값 | `roles/*/vars/main.yml` |
| 16 | block vars | block 내 `vars:` | task 파일 내 `block:` + `vars:` |
| 17 | **task vars** | task 레벨 `vars:` | [task vars 섹션 참조](#task-vars-우선순위-17) |
| 18 | include_vars | `include_vars` 모듈 | task 파일 내 `include_vars:` |
| 19 | set_facts / register | 런타임 변수 | task 내 `set_fact:`, `register:` |
| 20 | role parameters | role 호출 시 파라미터 | playbook 내 `roles:` + `vars:` |
| 21 | include parameters | include 시 파라미터 | `include_role:` + `vars:` |
| 22 | **extra vars** | 명령줄 `-e` | `ansible-playbook -e "key=value"` |

> **굵은 글씨**로 표시된 항목이 Kubespray에서 주로 사용하는 우선순위다.

실제 Kubespray에서 각 위치에 얼마나 많은 변수 파일이 있는지 확인해 보자:

```bash
# 순위 2: role defaults
# - Ansible은 defaults/main/ 하위 디렉토리도 자동 로드
find roles -type f -name "*.yml" | grep "/defaults/" | wc -l   # 77개

# 순위 4, 6: inventory group_vars
# - sample만 세려면 inventory/sample로 제한
find inventory/sample -path "*/group_vars/all/*.yml" | wc -l           # 16개
find inventory/sample -path "*/group_vars/k8s_cluster/*.yml" | wc -l   # 10개

# 순위 15: role vars
find roles -type f -name "*.yml" | grep "/vars/" | wc -l   # 50개
```

| 순위 | Kubespray에서 주로 사용 | 파일/개수 | 설명 |
|------|--------------------------|-----------|------|
| 2 | `roles/**/defaults/**/*.yml` | **77개** | 대부분의 기본값 |
| 4 | `inventory/sample/group_vars/all/*.yml` | **16개** | 전역 사용자 설정 |
| 6 | `inventory/sample/group_vars/k8s_cluster/*.yml` | **10개** | 클러스터별 설정 |
| 12 | playbook 내 `vars:` | **4개** | etcd, ansible_version |
| 15 | `roles/**/vars/**/*.yml` | **50개** | 내부 고정값 |
| 17 | task 내 `vars:` (include_tasks용) | **~22개** | 다운로드 파라미터 등 |
| 22 | `-e` 옵션 | 실행 시 | 임시 오버라이드 |

<br>

## 핵심 이해

**숫자가 높을수록 우선순위가 높아 낮은 순위의 값을 덮어쓴다.** 더 구체적인 범위가 더 높은 우선순위를 가진다:

- `group_vars/all` (우선순위 4) < `group_vars/k8s_cluster` (우선순위 6)
- `group_vars/*` (우선순위 6) < `host_vars/*` (우선순위 9)

```yaml
# role/defaults/main.yml (우선순위 2)
kube_version: v1.30.0

# inventory/group_vars/all/all.yml (우선순위 4)
kube_version: v1.31.0   # ← 이 값이 적용됨

# 명령줄 -e 옵션 (우선순위 22)
ansible-playbook cluster.yml -e "kube_version=v1.32.0"  # ← 이 값이 최종 적용
```


<br>

# Kubespray 변수 배치 전략

Kubespray는 Ansible 변수 우선순위를 활용하여 체계적인 변수 관리 구조를 설계했다.

## 설계 의도

Kubespray는 Ansible 변수 우선순위를 활용하여 **기본값 → 사용자 설정 → 임시 오버라이드** 순으로 변수가 덮어쓰여지도록 설계했다. 기본값은 우선순위가 가장 낮은 `role defaults`에 두어 사용자가 쉽게 덮어쓸 수 있게 하고, 사용자 설정은 우선순위가 더 높은 `inventory group_vars`에서 관리하도록 했다. 내부 고정값(체크섬 등)은 `role vars`에 두어 사용자가 실수로 변경하지 않도록 했다.

```
[role defaults] ──override──→ [inventory group_vars] ──override──→ [extra_vars]
    기본값                         사용자 설정                       임시 설정
```

| 위치 | 역할 | 우선순위 | 용도 |
|------|------|----------|------|
| `roles/*/defaults/` | **기본값 제공** | 2 | sensible defaults(합리적인 기본값), 쉽게 덮어쓸 수 있음 |
| `inventory/*/group_vars/` | **사용자 커스터마이징** | 4-6 | 사용자가 변경할 값 |
| `roles/*/vars/` | **내부 고정값** | 15 | 변경 비권장, 체크섬 등 |


### 예시: override_system_hostname

```yaml
# roles/bootstrap_os/defaults/main.yml (우선순위 2)
override_system_hostname: true   # 기본값

# inventory/mycluster/group_vars/all/all.yml (우선순위 4)
override_system_hostname: false  # 사용자가 덮어씀
```

기본값이 우선순위 2(가장 낮음)이기 때문에 어디서든 쉽게 덮어쓸 수 있다.

<br>

## kubespray_defaults 롤

Kubespray의 핵심 기본값은 **`kubespray_defaults` 롤**에 집중되어 있다.

```bash
roles/kubespray_defaults/
├── defaults/main/
│   ├── main.yml        # 801 라인 - 핵심 기본값
│   └── download.yml    # 1139 라인 - 다운로드 관련 기본값
└── vars/main/
    ├── main.yml
    └── checksums.yml   # 바이너리 체크섬
```

| 파일 | 라인 수 | 내용 |
|------|---------|------|
| `defaults/main/main.yml` | ~800 | 핵심 기본값 (버전, 네트워크, 컨테이너 등) |
| `defaults/main/download.yml` | ~1100 | 다운로드 URL, 버전 매핑 |
| `vars/main/checksums.yml` | 많음 | 바이너리 무결성 검증용 체크섬 |

### role vars의 역할

`roles/*/vars/`는 우선순위 15로 높아서 사용자가 쉽게 덮어쓸 수 없다. 주로 **내부 고정값**을 저장한다:

| 파일 | 내용 |
|------|------|
| `kubespray_defaults/vars/main/checksums.yml` | 바이너리 무결성 검증용 SHA256 체크섬 |
| `kubespray_defaults/vars/main/main.yml` | 내부 경로 등 |

> **왜 role vars에 둘까?** 체크섬이나 내부 경로는 사용자가 실수로 변경하면 설치가 실패할 수 있다. 우선순위를 높여서 보호하는 것이다.

<br>

## inventory/group_vars 구조

사용자가 실제로 커스터마이징하는 곳이다.

### 그룹 범위

| 디렉토리 | 적용 대상 | 설명 |
|----------|----------|------|
| `group_vars/all/` | 모든 호스트 | etcd, control plane, worker 전부 |
| `group_vars/k8s_cluster/` | k8s_cluster 그룹 | control plane + worker (etcd 제외 가능) |
| `group_vars/etcd/` | etcd 그룹 | etcd 노드만 |

### 디렉토리 구조

```bash
inventory/mycluster/
├── group_vars/
│   ├── all/               # 모든 호스트에 적용 (우선순위 4)
│   │   ├── all.yml
│   │   ├── containerd.yml
│   │   ├── etcd.yml
│   │   └── ...
│   └── k8s_cluster/       # k8s_cluster 그룹에만 적용 (우선순위 6)
│       ├── k8s-cluster.yml
│       ├── k8s-net-calico.yml
│       ├── addons.yml
│       └── ...
└── inventory.ini
```

Kubespray는 기본값을 `roles/*/defaults/`에 정의하고, 사용자가 이를 변경할 수 있도록 우선순위가 더 높은 `inventory/group_vars/`를 제공한다. 사용 흐름은 다음과 같다:

1. `inventory/sample/group_vars/`: Kubespray가 제공하는 **템플릿/샘플**
2. 사용자가 이를 복사해서 `inventory/mycluster/group_vars/`로 만듦
3. 변경하고 싶은 변수는 `roles/*/defaults/`에서 확인 후 `group_vars`에 추가

즉, `group_vars` 파일들은 Kubespray가 제공하는 **"시작점"**이고, 사용자가 직접 defaults를 보고 필요한 변수를 추가/수정하는 구조다.

<br>

## play vars와 task vars

우선순위가 높은 play vars(12)와 task vars(17)도 있다.

### play vars (우선순위 12)

Kubespray에서 play vars를 사용하는 경우는 제한적이다:

| Playbook | YAML 키 | 변수 |
|----------|---------|------|
| `playbooks/cluster.yml` | `vars:` (line 20-22) | `etcd_cluster_setup`, `etcd_events_cluster_setup` |
| `playbooks/upgrade_cluster.yml` | `vars:` (line 39-41) | `etcd_cluster_setup`, `etcd_events_cluster_setup` |
| `playbooks/scale.yml` | `vars:` (line 9-11) | `etcd_cluster_setup`, `etcd_events_cluster_setup` |
| `playbooks/ansible_version.yml` | `vars:` (line 7-9) | `minimal_ansible_version`, `maximal_ansible_version` |

정리하면 총 4개 변수가 play vars로 사용된다:

| 변수명 | 사용 playbook | 설명 |
|--------|---------------|------|
| `etcd_cluster_setup` | cluster, upgrade, scale | etcd 클러스터 구성 여부 |
| `etcd_events_cluster_setup` | cluster, upgrade, scale | etcd events 클러스터 구성 여부 |
| `minimal_ansible_version` | ansible_version | 최소 Ansible 버전 |
| `maximal_ansible_version` | ansible_version | 최대 Ansible 버전 |

etcd 관련 변수는 같은 `install_etcd.yml`을 playbook마다 다르게 동작시키기 위해 사용된다. `cluster.yml`에서는 `true`로 설정해 etcd를 설치하고, `scale.yml`에서는 `false`로 설정해 기존 etcd를 사용한다.

```yaml
# playbooks/cluster.yml
- name: Install etcd
  vars:                    # ← play vars (우선순위 12)
    etcd_cluster_setup: true
  import_playbook: install_etcd.yml
```

Ansible 버전 변수는 `ansible_version.yml`에서 지원하는 Ansible 버전 범위를 명시적으로 선언하기 위해 사용된다.

> **참고**: `roles/etcd_defaults/defaults/main.yml`에 이미 `etcd_cluster_setup: true`가 기본값으로 정의되어 있는데, 왜 `cluster.yml`에서 다시 `true`로 설정할까? 핵심은 `scale.yml`의 `false`다. `scale.yml`은 기존 클러스터에 노드를 추가하므로 etcd를 새로 설치하면 안 되고, defaults의 `true`를 `false`로 덮어써야 한다. `cluster.yml`의 `true`는 defaults와 같은 값이지만, `scale.yml`과 대비되어 의도를 명확히 드러낸다.

<br>

### task vars (우선순위 17)

task vars도 확인해보려고 했는데, 역시 수가 많았다. 대략 20개 이상의 파일에서 task vars를 사용하고 있었다.

| Role/파일 | 변수명 | 용도 |
|-----------|--------|------|
| `container-engine/containerd/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `container-engine/runc/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `container-engine/crictl/tasks/crictl.yml` | `download` | 다운로드 파라미터 전달 |
| `container-engine/nerdctl/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `container-engine/crun/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `etcdctl_etcdutl/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `kubernetes-apps/helm/tasks/main.yml` | `download` | 다운로드 파라미터 전달 |
| `etcd/tasks/join_etcd_member.yml` | `etcd_peer_addresses` | etcd 피어 주소 |
| `etcd/tasks/join_etcd-events_member.yml` | `etcd_peer_addresses` | etcd 피어 주소 |
| `network_plugin/cilium/tasks/reset.yml` | `iface` | 인터페이스명 |

자세히 살펴보니, 대부분 **include_tasks에 파라미터를 전달**하는 용도로 사용되고 있었다:

```yaml
# 다운로드 파라미터 전달
- name: Download containerd
  include_tasks: "../download/tasks/download_file.yml"
  vars:                    # ← task vars (우선순위 17)
    download: "{{ download_defaults | combine(downloads.containerd) }}"
```

task vars에서 사용하는 변수명(`download`, `iface` 등)을 group_vars/defaults에서 검색해봤는데, 겹치는 게 없는 것 같았다. 즉, 상위 변수를 영구적으로 덮어쓰는 게 아니라 해당 task 범위에서만 유효한 **로컬 파라미터**로 사용하는 패턴이었다.

> **참고**: 솔직히 지금 시점에서 모든 task vars를 일일이 확인하기는 버겁다. 일단 "task vars는 대부분 include용 로컬 파라미터"라고 알아두고, 나중에 변수가 예상대로 동작하지 않을 때 task vars 충돌 여부를 확인해보면 될 것 같다. task vars에서 사용하는 변수명을 group_vars/defaults에서 검색해서 겹치는 게 있는지 확인한다.

<br>

# 변수 분석

Kubespray 변수를 어떤 순서로 분석하면 좋을지 생각해봤다.

1. **`docs/ansible/vars.md` 훑어보기**: "어떤 변수들을 바꿀 수 있는지" 개요를 파악한다. 모든 변수를 외울 필요는 없고, 대략 어떤 카테고리가 있는지만 알면 된다.
2. **`roles/*/defaults/` 분석**: 기본값이 어떻게 설정되어 있는지 확인한다. 특히 `kubespray_defaults/defaults/main/`에 핵심 기본값이 집중되어 있다.
3. **`inventory/group_vars/` 분석**: 사용자가 실제로 바꾸는 곳이다. `sample`과 `mycluster`를 비교해보면 어떤 값을 변경했는지 알 수 있다.
4. **`roles/*/vars/` (필요시)**: checksums 등 내부 고정값이 있는 곳이다. 변경 비권장 영역이므로 필요할 때만 확인한다.
5. **play vars / task vars (나중에)**: 특수 케이스만 해당된다. 대부분의 경우 신경 쓸 필요 없다.

<br>

# 변수 커스터마이징

위에서 분석한 내용을 바탕으로, 실제 변수를 커스터마이징할 때는 다음 워크플로우를 따라가면 될 것 같다.

## 수정 가능 영역

먼저 중요한 점은, **사용자가 수정해야 할 곳**과 **수정하면 안 되는 곳**을 구분하는 것이다.

```
┌───────────────────────────────────────────────┐
           Kubespray 코드 (수정 X)              
  playbooks/, roles/                           
  → git pull / 버전 업그레이드 시 덮어쓰임       
└───────────────────────────────────────────────┘
                       │
                       │ 참조만
                       ↓
┌───────────────────────────────────────────────┐
           사용자 영역 (수정 O)                 
  inventory/mycluster/                         
  → Kubespray 업그레이드해도 유지됨             
└───────────────────────────────────────────────┘
```

| 구분 | 위치 | 이유 |
|------|------|------|
| **수정 O** | `inventory/mycluster/group_vars/` | 사용자 영역, 업그레이드해도 안전 |
| **수정 O** | `inventory/mycluster/host_vars/` | 사용자 영역 |
| **수정 O** | `-e` 옵션 | 실행 시 임시 override |
| **수정 X** | `playbooks/*.yml` | Kubespray 코드, 업그레이드 시 덮어쓰임 |
| **수정 X** | `roles/*/defaults/` | Kubespray 코드, 업그레이드 시 덮어쓰임 |
| **수정 X** | `roles/*/vars/` | Kubespray 코드, 내부 고정값 |

Kubespray를 git clone해서 사용하는 경우, `git pull`이나 버전 업그레이드 시 `playbooks/`, `roles/` 등의 파일이 덮어쓰여진다. 하지만 `inventory/mycluster/`는 사용자가 `sample`에서 복사해서 만든 디렉토리이므로 Kubespray 코드와 분리되어 있고, 업그레이드해도 유지된다.

## 워크플로우

### 1단계: 샘플 복사

```bash
cp -r inventory/sample inventory/mycluster
```

`inventory/sample/group_vars/`에는 이미 일부 변수가 정의되어 있고, 일부는 주석 처리되어 있다. sample group_vars는 **템플릿 + 가이드** 역할을 한다.

| 상태 | 의미 |
|------|------|
| 값이 정의됨 | Kubespray 권장 설정, defaults override |
| 주석 처리됨 | "이런 옵션도 있다" 가이드 |
| 아예 없음 | defaults 값 그대로 사용 |

### 2단계: defaults에서 변수 확인

바꾸고 싶은 변수가 있으면 `roles/*/defaults/`에서 기본값을 확인한다. 모든 변수가 sample에 있는 건 아니므로, 필요한 변수는 직접 defaults에서 찾아야 한다.

```yaml
# roles/kubespray_defaults/defaults/main/main.yml 확인
kube_version: v1.31.0              # 기본값
container_manager: containerd      # 기본값
```

### 3단계: group_vars에 override

바꾸고 싶은 것만 `inventory/mycluster/group_vars/`에 정의한다. 정의하지 않은 변수는 defaults 값이 사용된다.

```yaml
# inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
kube_version: v1.30.0              # ← 이것만 override
# container_manager는 안 적으면 defaults 값(containerd) 사용
```

주요 group_vars 파일은 다음과 같다:

| 파일 | 주요 설정 |
|------|-----------|
| `all/all.yml` | 전역 설정, 타임존, 프록시 등 |
| `all/containerd.yml` | containerd 설정 |
| `all/etcd.yml` | etcd 설정 |
| `k8s_cluster/k8s-cluster.yml` | Kubernetes 버전, 네트워크 설정 |
| `k8s_cluster/k8s-net-calico.yml` | Calico CNI 설정 |
| `k8s_cluster/addons.yml` | 애드온(Dashboard, Ingress 등) 설정 |

필요하다면 `inventory/mycluster/host_vars/`에 호스트별 변수를 정의하거나, 실행 시 `-e` 옵션으로 임시 override할 수도 있다.

## 실전 예시: kube_version 변경하기

특정 변수를 변경하고 싶을 때 따라가는 단계를 예시로 보자.

### 1. 기본값 확인

```bash
grep -r "kube_version" roles/*/defaults/ | head -5
# → roles/kubespray_defaults/defaults/main/main.yml:kube_version: v1.31.0
```

### 2. sample에서 어떻게 설정했는지 확인

```bash
grep -r "kube_version" inventory/sample/group_vars/
# → k8s_cluster/k8s-cluster.yml:# kube_version: v1.31.0  (주석 처리)
```

### 3. mycluster에 설정

```yaml
# inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
kube_version: v1.30.0
```

이제 `cluster.yml` 실행 시 Kubernetes v1.30.0이 설치된다.

<br>

# 결과

Kubespray의 변수 배치 전략을 요약하면 다음과 같다.

1. **role defaults (우선순위 2)**: 기본값 제공. 사용자가 쉽게 덮어쓸 수 있음
2. **inventory group_vars (우선순위 4-6)**: 사용자 커스터마이징 영역. **실제로 수정하는 곳**
3. **role vars (우선순위 15)**: 내부 고정값. 변경 비권장
4. **extra_vars (우선순위 22)**: 임시 오버라이드 (명령줄 `-e` 옵션)

```
┌──────────────────────────────────────────────────────┐
│                    Kubespray                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  roles/kubespray_defaults/defaults/            │  │ ← 기본값
│  │  (sensible defaults, 합리적인 기본값)              │  │
│  └────────────────────────────────────────────────┘  │
│                        ↑ override                    │
│  ┌────────────────────────────────────────────────┐  │
│  │  inventory/mycluster/group_vars/               │  │ ← 사용자 설정
│  │  (user customization)                          │  │
│  └────────────────────────────────────────────────┘  │
│                        ↑ override                    │
│  ┌────────────────────────────────────────────────┐  │
│  │  ansible-playbook cluster.yml -e "key=value"   │  │ ← 임시 오버라이드
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

<br>

# 다음 단계

이번 글에서 Kubespray의 변수 배치 전략과 분석 흐름을 파악했다. 다음 글에서는 사용자가 실제로 수정할 수 있는 **`inventory/group_vars/` 영역**을 상세히 분석한다:

- `group_vars/all/` 파일들 분석
- `group_vars/k8s_cluster/` 파일들 분석
- 자주 변경하는 변수와 권장 설정

<br>

# 참고 자료

- [Kubespray Variables Documentation](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/ansible/vars.md)
- [Ansible Variable Precedence](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
- [Ansible 시리즈 - 변수 우선순위]({% post_url 2026-01-12-Kubernetes-Ansible-06 %}#변수-우선순위)
- [Ansible 시리즈 - 롤 구조]({% post_url 2026-01-12-Kubernetes-Ansible-11 %}#롤-구조)
- [이전 글: cluster.yml Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-00 %})

<br>
