---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 6.0.1. 노드 관리 - scale.yml"
excerpt: "Kubespray의 노드 추가 플레이북 scale.yml의 전체 흐름과 구조를 분석해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - scale.yml
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray의 노드 추가 플레이북 `scale.yml`**의 전체 흐름을 분석한다.

- **목적**: 기존 클러스터를 건드리지 않고, 새로 추가된 노드만 단계적으로 합류
- **플레이 구성**: 공통 작업 → 팩트 수집 → etcd(조건부) → 다운로드 → 노드 준비 → kubeadm join → CNI
- **공통 패턴**: 모든 플레이에서 `kubespray_defaults` 롤 먼저 실행
- **cluster.yml과 차이점**: etcd 클러스터는 건드리지 않음 (`etcd_cluster_setup: false`)

<br>

# scale.yml 전체 흐름

`scale.yml`은 Kubespray의 노드 추가 플레이북으로, **기존 클러스터를 유지하면서 새 노드만 합류**시킨다.

![kubespray-scale-flowchart]({{site.url}}/assets/images/kubespray-scale-flowchart.png)
<center><sup>scale.yml 플레이북 실행 흐름</sup></center>
<sup>`Download images to ansible host cache via first kube_control_node`에서 조건(*, **, ***)는 롤 실행 전마다 각각 평가되어야 하나, 편의상 한 번만 나타냈다.</sup>

<br>

```
1. 공통 작업 (boilerplate.yml)
   ↓
2. 팩트 수집 (internal_facts.yml)
   ↓
3. etcd 설치 (조건부 - 새 etcd 노드인 경우만)
   ↓
4. 이미지 다운로드 (첫 번째 Control Plane에서)
   ↓
5. Worker 노드 준비 (preinstall, container-engine, download)
   ↓
6. kubelet 설치 (kubernetes/node)
   ↓
7. 인증서 업로드 (kubeadm upload-certs)
   ↓
8. 클러스터 조인 (kubeadm join, node-label, node-taint, network_plugin)
   ↓
9. DNS 설정 (resolv.conf)
```

## 단계별 그룹핑

위 흐름을 목적별로 그룹핑하면 다음과 같다:

| 단계 | 목적 | 플레이 |
|------|------|--------|
| **초기화 및 정보 수집** | 공통 설정 적용, 서버 사양 정보 수집 | boilerplate, internal_facts |
| **etcd 준비 (조건부)** | 새 etcd 노드인 경우에만 etcd 설정 | install_etcd (etcd_cluster_setup=false) |
| **바이너리 캐시** | 이미지/바이너리를 CP에서 한 번만 다운로드 | download (kube_control_plane[0]) |
| **노드 인프라 준비** | OS 최적화, 컨테이너 런타임, 바이너리 다운로드 | preinstall, container-engine, download |
| **kubelet 설치** | kubelet 설치 및 systemd 등록 | kubernetes/node |
| **인증서 업로드** | kubeadm join에 필요한 인증서 업로드 | kubeadm upload-certs |
| **클러스터 조인** | kubeadm join, 레이블/테인트, CNI 설정 | kubeadm, node-label, node-taint, network_plugin |
| **DNS 설정** | 클러스터 DNS 설정 최종 적용 | resolv.conf |

<br>

# 플레이북 구조

## 전체 코드

<details markdown="1">
<summary>scale.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
---
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Gather facts
  import_playbook: internal_facts.yml

- name: Install etcd
  vars:
    etcd_cluster_setup: false
    etcd_events_cluster_setup: false
  import_playbook: install_etcd.yml

- name: Download images to ansible host cache via first kube_control_plane node
  hosts: kube_control_plane[0]
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults, when: "not skip_downloads and download_run_once and not download_localhost" }
    - { role: kubernetes/preinstall, tags: preinstall, when: "not skip_downloads and download_run_once and not download_localhost" }
    - { role: download, tags: download, when: "not skip_downloads and download_run_once and not download_localhost" }

- name: Target only workers to get kubelet installed and checking in on any new nodes(engine)
  hosts: kube_node
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, tags: preinstall }
    - { role: container-engine, tags: "container-engine", when: deploy_container_engine }
    - { role: download, tags: download, when: "not skip_downloads" }
    - role: etcd
      tags: etcd
      vars:
        etcd_cluster_setup: false
      when:
        - etcd_deployment_type != "kubeadm"
        - kube_network_plugin in ["calico", "flannel", "canal", "cilium"] or cilium_deploy_additionally | default(false) | bool
        - kube_network_plugin != "calico" or calico_datastore == "etcd"
```

> **참고**: Ansible의 `roles` 정의 방식
> - **인라인 형식**: `{ role: name, tags: tag, when: condition }` - 간단한 경우에 사용
> - **확장 형식**: `role`, `tags`, `vars`, `when`을 각각 별도 라인에 정의 - 복잡한 조건이나 변수 설정이 필요한 경우 사용
> 
> 위 예시에서 `etcd` role만 확장 형식을 사용한 이유는:
> 1. `vars`로 role 실행 시 변수 오버라이드가 필요 (`etcd_cluster_setup: false`)
> 2. `when` 조건이 여러 개의 리스트로 구성됨 (AND 조건)
> 
> 두 형식은 동일한 `roles` 리스트 내에서 혼용할 수 있다.

```yaml
- name: Target only workers to get kubelet installed and checking in on any new nodes(node)
  hosts: kube_node
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/node, tags: node }

- name: Upload control plane certs and retrieve encryption key
  hosts: kube_control_plane | first
  environment: "{{ proxy_disable_env }}"
  gather_facts: false
  tags: kubeadm
  roles:
    - { role: kubespray_defaults }
  tasks:
    - name: Upload control plane certificates
      command: >-
        {{ bin_dir }}/kubeadm init phase
        --config {{ kube_config_dir }}/kubeadm-config.yaml
        upload-certs
        --upload-certs
      environment: "{{ proxy_disable_env }}"
      register: kubeadm_upload_cert
      changed_when: false
    - name: Set fact 'kubeadm_certificate_key' for later use
      set_fact:
        kubeadm_certificate_key: "{{ kubeadm_upload_cert.stdout_lines[-1] | trim }}"
      when: kubeadm_certificate_key is not defined

- name: Target only workers to get kubelet installed and checking in on any new nodes(network)
  hosts: kube_node
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/kubeadm, tags: kubeadm }
    - { role: kubernetes/node-label, tags: node-label }
    - { role: kubernetes/node-taint, tags: node-taint }
    - { role: network_plugin, tags: network }

- name: Apply resolv.conf changes now that cluster DNS is up
  hosts: k8s_cluster
  gather_facts: false
  any_errors_fatal: "{{ any_errors_fatal | default(true) }}"
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", tags: resolvconf, dns_late: true }
```
{% endraw %}

</details>

<br>

## 플레이별 역할

| 순서 | 플레이 | 대상 호스트 | 주요 역할 |
|------|--------|-------------|-----------|
| 1 | Common tasks | - | 공통 설정, 변수 검증 |
| 2 | Gather facts | - | 시스템 정보 수집 |
| 3 | Install etcd | `etcd` | etcd 설정 (클러스터 변경 없음) |
| 4 | Download images | `kube_control_plane[0]` | 이미지/바이너리 캐시 |
| 5 | Workers (engine) | `kube_node` | OS 설정, 컨테이너 런타임, 다운로드 |
| 6 | Workers (node) | `kube_node` | kubelet 설치 |
| 7 | Upload certs | `kube_control_plane[0]` | kubeadm 인증서 업로드 |
| 8 | Workers (network) | `kube_node` | kubeadm join, 레이블/테인트, CNI |
| 9 | resolv.conf | `k8s_cluster` | DNS 설정 최종 적용 |

<br>

# 단계별 분석

## 1. 초기화 및 팩트 수집

{% raw %}
```yaml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Gather facts
  import_playbook: internal_facts.yml
```
{% endraw %}

| 플레이 | 역할 |
|--------|------|
| `boilerplate.yml` | 공통 설정 적용, Ansible 버전 검증 |
| `internal_facts.yml` | 서버 사양 정보 수집 (CPU, 메모리 등) |

모든 Kubespray 플레이북의 공통 시작점이다.

## 2. etcd 준비 (조건부)

{% raw %}
```yaml
- name: Install etcd
  vars:
    etcd_cluster_setup: false
    etcd_events_cluster_setup: false
  import_playbook: install_etcd.yml
```
{% endraw %}

### cluster.yml과의 차이

| Playbook | etcd_cluster_setup | 의미 |
|----------|-------------------|------|
| `cluster.yml` | `true` | etcd 클러스터 새로 구성 |
| `scale.yml` | `false` | 기존 etcd 클러스터 유지, 클라이언트 설정만 |

`etcd_cluster_setup: false`는 etcd 클러스터를 새로 구성하지 않는다는 의미다. 새 워커 노드는 기존 etcd 클러스터에 접근만 하면 되므로, etcd 멤버로 추가되지 않는다.

> **참고**: `etcd_cluster_setup` 변수에 대한 자세한 설명은 [cluster.yml 분석 - Play 변수]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %}#play-변수) 참조

### 실행 순서 차이

| Playbook | install_etcd.yml 위치 | 이유 |
|----------|----------------------|------|
| `cluster.yml` | preinstall/download **후** | etcd 설치에 컨테이너 런타임 필요 |
| `scale.yml` | preinstall/download **전** | 실제 설치 아님, 기존 클러스터 정보 참조만 |

`scale.yml`에서 앞에 올 수 있는 이유는 실제 etcd를 설치하지 않기 때문이다.

## 3. 이미지/바이너리 다운로드 (캐시)

{% raw %}
```yaml
- name: Download images to ansible host cache via first kube_control_plane node
  hosts: kube_control_plane[0]
  roles:
    - { role: kubespray_defaults, when: "not skip_downloads and download_run_once and not download_localhost" }
    - { role: kubernetes/preinstall, tags: preinstall, when: "..." }
    - { role: download, tags: download, when: "..." }
```
{% endraw %}

첫 번째 Control Plane에서 이미지/바이너리를 한 번만 다운로드하여 캐시한다.

| 조건 | 의미 |
|------|------|
| `not skip_downloads` | 다운로드 건너뛰기가 아닐 때 |
| `download_run_once` | 한 번만 다운로드하는 모드일 때 |
| `not download_localhost` | 로컬호스트에서 다운로드하지 않을 때 |

## 4. 워커 노드 준비

{% raw %}
```yaml
- name: Target only workers to get kubelet installed and checking in on any new nodes(engine)
  hosts: kube_node
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, tags: preinstall }
    - { role: container-engine, tags: "container-engine", when: deploy_container_engine }
    - { role: download, tags: download, when: "not skip_downloads" }
    - role: etcd
      tags: etcd
      vars:
        etcd_cluster_setup: false
      when:
        - etcd_deployment_type != "kubeadm"
        - kube_network_plugin in ["calico", "flannel", "canal", "cilium"] or cilium_deploy_additionally | default(false) | bool
        - kube_network_plugin != "calico" or calico_datastore == "etcd"
```
{% endraw %}

| 롤 | 역할 |
|----|------|
| `kubernetes/preinstall` | OS 최적화, swap 비활성화, sysctl 설정 |
| `container-engine` | containerd/CRI-O 설치 |
| `download` | 바이너리 다운로드 |
| `etcd` (조건부) | etcd 클라이언트 설정 |

### etcd 롤 실행 조건 분석

마지막 `etcd` 롤은 **CNI가 etcd에 접근해야 하는 경우에만** 실행된다.

| 조건 | 의미 |
|------|------|
| `etcd_deployment_type != "kubeadm"` | 외부 etcd 사용 시 (Stacked etcd가 아닌 경우) |
| `kube_network_plugin in [...]` | CNI가 etcd를 사용할 수 있는 플러그인인 경우 |
| `kube_network_plugin != "calico" or calico_datastore == "etcd"` | Calico가 아니거나, Calico면 etcd 데이터스토어 사용 시 |

<br>

**두 번째 조건 상세:**


주 CNI가 calico/flannel/canal/cilium이거나, 또는 주 CNI는 다른 것이지만 Cilium을 추가로 함께 배포하는 경우를 의미한다.

```
kube_network_plugin in ["calico", "flannel", "canal", "cilium"] or cilium_deploy_additionally | default(false) | bool
```

| 부분 | 설명 |
|------|------|
| `kube_network_plugin in [...]` | 주 CNI가 이 4개 중 하나인 경우 |
| `or` | 또는 |
| `cilium_deploy_additionally` | Cilium을 **추가 CNI**로 배포하는 변수 |
| `\| default(false)` | 변수 미정의 시 `false` 사용 (Jinja2 필터) |
| `\| bool` | boolean으로 변환 (Jinja2 필터) |

<br>

**세 번째 조건의 역할:**

Calico는 두 가지 데이터스토어를 지원하므로, etcd를 사용하는 경우에만 etcd 롤이 필요하다.

| Calico Datastore | etcd 접근 필요 |
|------------------|---------------|
| `kube` (기본값) | 불필요 |
| `etcd` | 필요 |

> **참고**: `etcd` 롤만 확장 형식을 사용한 이유는 [앞서 설명한 내용](#2-etcd-준비-조건부) 참조

## 5. kubelet 설치

{% raw %}
```yaml
- name: Target only workers to get kubelet installed and checking in on any new nodes(node)
  hosts: kube_node
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/node, tags: node }
```
{% endraw %}

`kubernetes/node` 롤이 kubelet을 설치하고 systemd에 등록한다.

## 6. 인증서 업로드

{% raw %}
```yaml
- name: Upload control plane certs and retrieve encryption key
  hosts: kube_control_plane | first
  roles:
    - { role: kubespray_defaults }
  tasks:
    - name: Upload control plane certificates
      command: >-
        {{ bin_dir }}/kubeadm init phase
        --config {{ kube_config_dir }}/kubeadm-config.yaml
        upload-certs --upload-certs
      register: kubeadm_upload_cert
    - name: Set fact 'kubeadm_certificate_key' for later use
      set_fact:
        kubeadm_certificate_key: "{{ kubeadm_upload_cert.stdout_lines[-1] | trim }}"
      when: kubeadm_certificate_key is not defined
```
{% endraw %}

| 요소 | 설명 |
|------|------|
| `hosts: kube_control_plane \| first` | 첫 번째 Control Plane에서만 실행 |
| `kubeadm init phase upload-certs` | 인증서를 Secret으로 업로드 |
| `kubeadm_certificate_key` | 새 노드가 join할 때 필요한 키 |

> **참고**: `kubeadm init`은 첫 번째 Control Plane에서만 실행되므로, `upload-certs` phase도 자연스럽게 첫 번째 노드에서만 수행된다. 자세한 내용은 [kubeadm init - upload-certs]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %}#9-upload-certs) 참조

## 7. 클러스터 조인 및 CNI 설정

새 워커 노드를 클러스터에 join하고, 네트워크 설정을 완료한다.

{% raw %}
```yaml
- name: Target only workers to get kubelet installed and checking in on any new nodes(network)
  hosts: kube_node
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/kubeadm, tags: kubeadm }
    - { role: kubernetes/node-label, tags: node-label }
    - { role: kubernetes/node-taint, tags: node-taint }
    - { role: network_plugin, tags: network }
```
{% endraw %}

| 롤 | 역할 |
|----|------|
| `kubernetes/kubeadm` | `kubeadm join` 실행하여 클러스터에 합류 |
| `kubernetes/node-label` | 노드 레이블 적용 (예: `node-role.kubernetes.io/worker`) |
| `kubernetes/node-taint` | 노드 테인트 적용 (스케줄링 제어) |
| `network_plugin` | CNI 설정 (Calico, Flannel 등) - Pod 네트워크 통신 활성화 |

롤 실행 순서의 의미를 확인해 보자.
1. **kubeadm** → 노드가 클러스터에 합류해야
2. **node-label/taint** → 레이블과 테인트를 적용할 수 있고
3. **network_plugin** → Pod가 스케줄링될 때 네트워크가 준비됨

## 8. DNS 설정

{% raw %}
```yaml
- name: Apply resolv.conf changes now that cluster DNS is up
  hosts: k8s_cluster
  roles:
    - { role: kubespray_defaults }
    - { role: kubernetes/preinstall, when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", tags: resolvconf, dns_late: true }
```
{% endraw %}

클러스터 DNS가 올라온 후 `/etc/resolv.conf`를 최종 설정한다.

<br>

# 실행 방법

## 기본 실행

```bash
ansible-playbook -i inventory/mycluster/inventory.ini scale.yml
```

## 특정 노드만 추가 (권장)

```bash
ansible-playbook -i inventory/mycluster/inventory.ini scale.yml --limit=new-worker-node
```

## 태그로 특정 단계만 실행

```bash
# 네트워크 플러그인만 재설치
ansible-playbook scale.yml --tags network

# kubeadm과 노드 레이블만 실행
ansible-playbook scale.yml --tags kubeadm,node-label
```

<br>

# 정리

이번 글에서 `scale.yml`의 전체 흐름을 파악했다. 핵심은 **기존 클러스터(특히 etcd)를 건드리지 않고 새 노드만 합류**시킨다는 점이다.

## cluster.yml과의 주요 차이

| 항목 | cluster.yml | scale.yml |
|------|-------------|-----------|
| **etcd_cluster_setup** | `true` | `false` |
| **install_etcd.yml 위치** | download 후 | download 전 |
| **주요 대상** | `k8s_cluster:etcd` | `kube_node` |
| **목적** | 클러스터 새로 구성 | 기존 클러스터에 노드 추가 |

## 주요 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `etcd_cluster_setup` | `false` (scale.yml) | etcd 클러스터 변경 여부 |
| `skip_downloads` | `false` | 다운로드 건너뛰기 |
| `download_run_once` | `true` | 한 번만 다운로드 |
| `download_localhost` | `false` | 로컬에서 다운로드 |
| `deploy_container_engine` | `true` | 컨테이너 런타임 설치 여부 |

## Kubespray와 kubeadm

`scale.yml` 분석에서도 다시 한 번 확인할 수 있는데, **Kubespray는 결국 kubeadm을 사용**한다.

| Kubespray가 하는 일 | 실제 동작 |
|---------------------|-----------|
| 인증서 업로드 | `kubeadm init phase upload-certs` |
| 노드 조인 | `kubeadm join` |
| 클러스터 초기화 | `kubeadm init` |

Kubespray의 역할은 kubeadm 명령을 직접 실행하는 것이 아니라, **Ansible을 통해 여러 노드에서 올바른 순서로 kubeadm을 실행**하도록 자동화하는 것이다. 이전 글에서 다룬 kubeadm의 개념(init, join, upload-certs 등)이 Kubespray 내부에서 어떻게 활용되는지 확인할 수 있다.

<br>

# 참고 자료

- [Kubespray GitHub - scale.yml](https://github.com/kubernetes-sigs/kubespray/blob/master/scale.yml)
- [Kubespray - Adding/removing a node](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/nodes.md)

<br>
