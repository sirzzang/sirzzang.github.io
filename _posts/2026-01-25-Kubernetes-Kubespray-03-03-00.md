---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.3.0. cluster.yml - Overview"
excerpt: "Kubespray의 메인 플레이북 cluster.yml의 전체 흐름과 구조를 분석해보자."
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

이번 글에서는 **Kubespray의 메인 플레이북 `cluster.yml`**의 전체 흐름을 분석한다.

- **10단계 플레이**로 구성: 공통 작업 → 팩트 수집 → etcd → K8s 노드 → 컨트롤 플레인 → kubeadm → CNI → 앱
- **공통 패턴**: 모든 플레이에서 `kubespray_defaults` 롤 먼저 실행
- **태그 기반 선택 실행**: `--tags` 옵션으로 특정 단계만 실행 가능

<br>

# cluster.yml 전체 흐름

`cluster.yml`은 Kubespray의 메인 플레이북으로, 클러스터 생성의 전체 과정을 정의한다.

![kubespray-cluster-flowchart]({{site.url}}/assets/images/kubespray-cluster-flowchart.png)
<center><sup>cluster.yml 플레이북 실행 흐름</sup></center>

<br>

```
1. 공통 작업 (boilerplate.yml)
   ↓
2. 팩트 수집 (internal_facts.yml)
   ↓
3. etcd 설치 준비 (preinstall, container-engine, download)
   ↓
4. etcd 설치 (install_etcd.yml)
   ↓
5. K8s 노드 설치 (kubernetes/node)
   ↓
6. 컨트롤 플레인 설치 (kubernetes/control-plane)
   ↓
7. kubeadm 실행 + CNI 설치 (kubernetes/kubeadm, network_plugin)
   ↓
8. Calico Route Reflector (선택적)
   ↓
9. Windows 노드 패치 (선택적)
   ↓
10. K8s 앱 설치 (kubernetes-apps)
   ↓
11. resolv.conf 적용
```

<br>

# 플레이북 구조

## 전체 코드

<details markdown="1">
<summary>cluster.yml 전체 코드 (클릭하여 펼치기)</summary>

```yaml
---
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Gather facts
  import_playbook: internal_facts.yml

- name: Prepare for etcd install
  hosts: k8s_cluster:etcd
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, tags: preinstall }
    - { role: "container-engine", tags: "container-engine", when: deploy_container_engine }
    - { role: download, tags: download, when: "not skip_downloads" }

- name: Install etcd
  vars:
    etcd_cluster_setup: true
    etcd_events_cluster_setup: "{{ etcd_events_cluster_enabled }}"
  import_playbook: install_etcd.yml

- name: Install Kubernetes nodes
  hosts: k8s_cluster
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/node, tags: node }

- name: Install the control plane
  hosts: kube_control_plane
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/control-plane, tags: control-plane }
    - { role: kubernetes/client, tags: client }
    - { role: kubernetes-apps/cluster_roles, tags: cluster-roles }

- name: Invoke kubeadm and install a CNI
  hosts: k8s_cluster
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/kubeadm, tags: kubeadm}
    - { role: kubernetes/node-label, tags: node-label }
    - { role: kubernetes/node-taint, tags: node-taint }
    - { role: kubernetes-apps/common_crds }
    - { role: network_plugin, tags: network }

- name: Install Calico Route Reflector
  hosts: calico_rr
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: network_plugin/calico/rr, tags: ['network', 'calico_rr'] }

- name: Patch Kubernetes for Windows
  hosts: kube_control_plane[0]
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: win_nodes/kubernetes_patch, tags: ["control-plane", "win_nodes"] }

- name: Install Kubernetes apps
  hosts: kube_control_plane
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes-apps/external_cloud_controller, tags: external-cloud-controller }
    - { role: kubernetes-apps/policy_controller, tags: policy-controller }
    - { role: kubernetes-apps/ingress_controller, tags: ingress-controller }
    - { role: kubernetes-apps/external_provisioner, tags: external-provisioner }
    - { role: kubernetes-apps, tags: apps }

- name: Apply resolv.conf changes now that cluster DNS is up
  hosts: k8s_cluster
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", tags: resolvconf, dns_late: true }
```

</details>

<br>

## 플레이별 역할

| 순서 | 플레이 | 대상 호스트 | 주요 역할 |
|------|--------|-------------|-----------|
| 1 | Common tasks | - | 공통 설정, 변수 검증 |
| 2 | Gather facts | - | 시스템 정보 수집 |
| 3 | Prepare for etcd | `k8s_cluster:etcd` | OS 설정, 컨테이너 런타임, 바이너리 다운로드 |
| 4 | Install etcd | `etcd` | etcd 클러스터 설치 |
| 5 | Install K8s nodes | `k8s_cluster` | kubelet, kubeadm 설치 |
| 6 | Install control plane | `kube_control_plane` | API 서버, 스케줄러 등 설치 |
| 7 | kubeadm + CNI | `k8s_cluster` | kubeadm join, CNI 플러그인 설치 |
| 8 | Calico RR | `calico_rr` | Calico Route Reflector (선택) |
| 9 | Windows patch | `kube_control_plane[0]` | Windows 노드 지원 (선택) |
| 10 | K8s apps | `kube_control_plane` | CoreDNS, Ingress 등 애드온 |
| 11 | resolv.conf | `k8s_cluster` | DNS 설정 최종 적용 |

<br>

# Ansible 문법 분석

## import_playbook vs ansible.builtin.import_playbook

```yaml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml
```

`import_playbook`과 `ansible.builtin.import_playbook`은 **동일**하다.

- `ansible.builtin.import_playbook`: FQCN(Fully Qualified Collection Name)
- `import_playbook`: 단축형

Kubespray는 `.ansible-lint`에서 `fqcn-builtins` 규칙을 비활성화하여 단축형을 사용한다:

```yaml
# .ansible-lint
skip_list:
  - 'fqcn-builtins'  # FQCN 검사 비활성화
```

## 롤 import 문법

```yaml
roles:
  - { role: kubespray_defaults }
  - { role: kubernetes/preinstall, tags: preinstall }
  - { role: container-engine, tags: container-engine, when: deploy_container_engine }
```

`{ role: ..., tags: ..., when: ... }` 형식은 롤에 **태그**와 **조건**을 함께 지정하는 YAML 단축 문법이다.

풀어쓰면 아래와 같다.

```yaml
roles:
  - role: kubernetes/preinstall
    tags: preinstall
  
  - role: container-engine
    tags: container-engine
    when: deploy_container_engine
```

## 태그 사용

롤에 붙은 태그는 `--tags` 옵션으로 **선택적 실행**에 사용된다:

```bash
# 네트워크 플러그인만 재설치
ansible-playbook cluster.yml --tags network

# preinstall과 container-engine만 실행
ansible-playbook cluster.yml --tags preinstall,container-engine
```

| 태그 | 대상 롤 |
|------|---------|
| `preinstall` | `kubernetes/preinstall` |
| `container-engine` | `container-engine` |
| `download` | `download` |
| `node` | `kubernetes/node` |
| `control-plane` | `kubernetes/control-plane` |
| `kubeadm` | `kubernetes/kubeadm` |
| `network` | `network_plugin` |
| `apps` | `kubernetes-apps` |

<br>

# 공통 설정 분석

## gather_facts: false

```yaml
- name: Install Kubernetes nodes
  hosts: k8s_cluster
  gather_facts: false  # 왜 false?
```

`gather_facts: false`로 설정한 이유는, 첫 번째 플레이에서 이미 팩트를 수집했기 때문이다:

```yaml
- name: Gather facts
  import_playbook: internal_facts.yml  # 여기서 팩트 수집
```

이후 플레이에서는 **캐시된 팩트를 재사용**하므로 `gather_facts: false`로 설정하여 불필요한 팩트 수집을 방지한다. `ansible.cfg`에서 팩트 캐싱이 활성화되어 있다:

```ini
# ansible.cfg
gathering = smart
fact_caching = jsonfile
fact_caching_connection = /tmp
fact_caching_timeout = 86400  # 24시간
```

## any_errors_fatal

```yaml
any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
```

**하나의 호스트에서 오류가 발생하면 전체 플레이북을 중단**한다.

- 기본값: `true` (하나라도 실패하면 전체 중단)
- 클러스터 구성 중 일부 노드 실패 시 일관성 없는 상태 방지
- 필요 시 `any_errors_fatal: false`로 오버라이드 가능

## environment와 proxy_disable_env

```yaml
environment: "{{ proxy_disable_env }}"
```

롤 실행 시 적용할 **환경 변수**를 설정한다. `proxy_disable_env`는 프록시 설정을 비활성화하는 환경 변수다.

`roles/kubespray_defaults/defaults/main/main.yml`에서 정의:

```yaml
# 프록시 비활성화 환경 변수
proxy_disable_env:
  http_proxy: ""
  HTTP_PROXY: ""
  https_proxy: ""
  HTTPS_PROXY: ""
  no_proxy: ""
  NO_PROXY: ""
```

클러스터 내부 통신에서 프록시를 거치지 않도록 하기 위함이다.

<br>

# kubespray_defaults 롤

모든 플레이에서 **첫 번째로 실행**되는 롤이다:

```yaml
roles:
  - { role: kubespray_defaults }  # ← 항상 첫 번째
  - { role: kubernetes/node, tags: node }
```

## 디렉토리 구조

```bash
roles/kubespray_defaults/
├── defaults/main/
│   ├── download.yml    # 다운로드 관련 기본값
│   └── main.yml        # 주요 기본 변수
└── vars/main/
    ├── checksums.yml   # 바이너리 체크섬
    └── main.yml        # 고정 변수
```

## 역할

- **기본 변수 정의**: K8s 버전, 컨테이너 런타임 설정, 네트워크 설정 등
- **체크섬 정의**: 다운로드할 바이너리의 무결성 검증용 체크섬
- **조건부 변수**: OS별, 아키텍처별 분기 처리

> **참고**: [프로젝트 구조 Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-03-00 %})에서 `kubespray_defaults`와 `kubespray-defaults`의 차이를 설명했다. `kubespray_defaults`는 변수 **값**을 정의하고, `kubespray-defaults`는 변수를 **로드**하는 태스크를 담고 있다.

<br>

# 주요 조건부 변수

## deploy_container_engine

```yaml
- { role: container-engine, tags: container-engine, when: deploy_container_engine }
```

컨테이너 런타임을 설치할지 결정한다.

- 기본값: `true`
- `false`로 설정 시: 컨테이너 런타임이 이미 설치되어 있다고 가정하고 건너뜀

## etcd_events_cluster_enabled

```yaml
- name: Install etcd
  vars:
    etcd_cluster_setup: true
    etcd_events_cluster_setup: "{{ etcd_events_cluster_enabled }}"
  import_playbook: install_etcd.yml
```

**etcd events 클러스터**를 별도로 구성할지 결정한다.

- 기본값: `false`
- `true`로 설정 시: Kubernetes 이벤트 저장용 별도 etcd 클러스터 구성
- 용도: 대규모 클러스터에서 이벤트 트래픽을 분리하여 메인 etcd의 부하를 줄이고 성능을 향상시킬 수 있음

> **참고**: 외부 etcd를 사용하려면 `inventory/mycluster/group_vars/all/etcd.yml`에서 `etcd_deployment_type: host`(기본) 대신 `etcd_deployment_type: kubeadm_etcd_external`을 설정하고, `etcd_access_addresses` 등을 지정해야 한다.

## dns_mode와 resolvconf_mode

```yaml
- { role: kubernetes/preinstall, 
    when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", 
    tags: resolvconf, 
    dns_late: true }
```

클러스터 DNS 설정 방식을 결정한다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `dns_mode` | `coredns` | 클러스터 DNS 종류 (`coredns`, `none`) |
| `resolvconf_mode` | `host_resolvconf` | resolv.conf 관리 방식 |

`dns_late: true`는 클러스터 DNS가 올라온 **후에** resolv.conf를 업데이트하도록 지시한다.

<br>

# 결과

이번 글에서 `cluster.yml`의 전체 흐름을 파악했다. 다음 글에서는 각 플레이에서 실행되는 **롤들을 상세히 분석**한다:

1. `boilerplate.yml`: 공통 작업
2. `internal_facts.yml`: 팩트 수집
3. `kubernetes/preinstall`: OS 준비
4. `etcd`: etcd 클러스터 설치
5. `kubernetes/node`: kubelet 설치
6. `kubernetes/control-plane`: 컨트롤 플레인 설치
7. `network_plugin`: CNI 설치

<br>

# 참고 자료

- [Kubespray GitHub - cluster.yml](https://github.com/kubernetes-sigs/kubespray/blob/master/cluster.yml)
- [Ansible import_playbook](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/import_playbook_module.html)
- [이전 글: 프로젝트 구조 Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-03-00 %})

<br>
