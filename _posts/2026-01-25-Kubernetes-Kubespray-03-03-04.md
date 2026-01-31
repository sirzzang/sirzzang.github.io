---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.3.4. cluster.yml - Prepare for etcd install"
excerpt: "Kubespray cluster.yml의 세 번째 단계인 Prepare for etcd install 플레이를 분석해보자."
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

이번 글에서는 **cluster.yml의 세 번째 단계인 `Prepare for etcd install`** 플레이를 분석한다.

- **kubernetes/preinstall**: swap 비활성화, DNS 설정, sysctl 튜닝 등 K8s 노드 사전 준비
- **container-engine**: containerd/docker/cri-o 중 선택한 컨테이너 런타임 설치
- **download**: kubeadm, kubelet, 컨테이너 이미지 등 필요 바이너리/이미지 다운로드

<br>

# 전체 흐름에서의 위치

`Prepare for etcd install`은 cluster.yml에서 **세 번째로 실행**되는 플레이로, 본격적인 클러스터 구성 전 노드를 준비한다.

```yaml
# cluster.yml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Bootstrap and load facts
  import_playbook: internal_facts.yml

- name: Prepare for etcd install  # 세 번째 실행
  hosts: k8s_cluster:etcd
  ...
```

<br>

# 플레이 구조

{% raw %}
```yaml
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
```
{% endraw %}

| 설정 | 값 | 설명 |
|------|-----|------|
| `hosts` | `k8s_cluster:etcd` | 모든 K8s 노드 + etcd 노드 |
| `gather_facts` | `false` | 이미 internal_facts.yml에서 수집 완료 |
| `any_errors_fatal` | `true` | 하나라도 실패 시 전체 중단 |

| 역할 | 조건 | 목적 |
|------|------|------|
| `kubespray_defaults` | 항상 | 기본 변수 로드 |
| `kubernetes/preinstall` | 항상 | 노드 사전 준비 (swap, DNS, sysctl 등) |
| `container-engine` | `deploy_container_engine` | 컨테이너 런타임 설치 |
| `download` | `not skip_downloads` | 바이너리/이미지 다운로드 |

<br>

# 1. kubernetes/preinstall

## 역할

**Kubernetes 노드로 사용하기 위한 시스템 사전 준비**를 담당한다. swap 비활성화부터 DNS 설정까지 K8s가 요구하는 모든 시스템 설정을 수행한다.

## 태스크 구조

`kubernetes/preinstall` 롤은 **수십 개의 태스크 파일**로 구성되어 있다:

| 순서 | 태스크 파일 | 목적 |
|------|-------------|------|
| 0010 | `0010-swapoff.yml` | **K8s 필수** - swap 비활성화 |
| 0020 | `0020-set-facts.yml` | 변수/팩트 설정 |
| 0040 | `0040-verify-settings.yml` | 설정값 검증 |
| 0050 | `0050-create-directories.yml` | 필요 디렉토리 생성 |
| 0060-0063 | `0060-resolvconf.yml` 등 | DNS/resolv.conf 설정 |
| 0080 | `0080-system-configurations.yml` | sysctl, 커널 파라미터 등 |
| 0081 | `0081-ntp-client.yml` | 시간 동기화 |
| 0100-0110 | `0100-dhclient-hooks.yml` 등 | DHCP 관련 설정 |

## 주요 태스크

### swap 비활성화 (0010)

Kubernetes는 **swap이 활성화된 상태에서 동작하지 않는다**. kubelet이 시작 시 swap 상태를 확인하고, 활성화되어 있으면 실패한다.

```yaml
- name: Disable swap
  command: swapoff -a
  when: ansible_memory_mb.swap.total > 0

- name: Remove swap from fstab
  lineinfile:
    path: /etc/fstab
    regexp: '.*swap.*'
    state: absent
```

### DNS 설정 (0060-0063)

CoreDNS와 연동되는 DNS 설정을 구성한다. `resolvconf_mode` 변수에 따라 다르게 동작:

| resolvconf_mode | 동작 |
|-----------------|------|
| `docker_dns` | Docker 내장 DNS 사용 |
| `host_resolvconf` | 호스트의 resolv.conf 사용 |
| `none` | DNS 설정 건드리지 않음 |

### 시스템 설정 (0080)

K8s가 요구하는 커널 파라미터와 sysctl 설정:

```yaml
net.bridge.bridge-nf-call-iptables: 1
net.bridge.bridge-nf-call-ip6tables: 1
net.ipv4.ip_forward: 1
```

## 의존성: adduser 롤

`kubernetes/preinstall`은 `adduser` 롤을 의존성으로 가진다. Kubernetes 전용 사용자/그룹을 생성한다.

{% raw %}
```yaml
- name: User | Create User Group
  group:
    name: "{{ user.group | default(user.name) }}"
    system: "{{ user.system | default(omit) }}"

- name: User | Create User
  user:
    name: "{{ user.name }}"
    group: "{{ user.group | default(user.name) }}"
    system: "{{ user.system | default(omit) }}"
  when: user.name != "root"
```
{% endraw %}

## Azure VM 체크

preinstall 롤은 **Azure VM인지 감지**하는 태스크도 포함한다:

```yaml
- name: Check if this is an Azure VM
  stat:
    path: /var/lib/waagent
  register: azure_check
```

`/var/lib/waagent/`는 **Azure Linux Agent 디렉토리**로, Azure VM에만 존재한다.

| 항목 | 이유 |
|------|------|
| **네트워크** | Azure CNI, Load Balancer 설정 |
| **메타데이터** | Azure Instance Metadata Service |
| **스토리지** | Azure Disk CSI 드라이버 |

> **참고**: 온프레미스 실습 환경에서는 이 태스크가 스킵된다.

<br>

# 2. container-engine

## 역할

**컨테이너 런타임 설치**를 담당한다. Kubernetes 1.24부터 dockershim이 제거되면서, 별도의 CRI(Container Runtime Interface) 호환 런타임이 필요하다.

## 디렉토리 구조

`container-engine` 롤은 **여러 하위 롤의 집합**이다:

```
roles/container-engine/
├── meta/main.yml              # 의존성 정의
├── containerd/                # containerd 런타임
├── cri-o/                     # CRI-O 런타임
├── docker/                    # Docker 런타임
├── cri-dockerd/               # Docker용 CRI shim
├── crictl/                    # CRI 클라이언트 도구
├── nerdctl/                   # containerd용 Docker 호환 CLI
├── runc/                      # OCI 런타임
├── validate-container-engine/ # 런타임 검증
├── kata-containers/           # Kata Containers
├── gvisor/                    # gVisor
└── ...
```

## 의존성 기반 실행

`container-engine` 롤은 **tasks/main.yml이 없다**. 대신 `meta/main.yml`의 dependencies로 동작한다.

<details markdown="1">
<summary>meta/main.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
dependencies:
  # 항상 실행
  - role: container-engine/validate-container-engine
    tags:
      - container-engine
      - validate-container-engine

  # 조건부 실행 - 보안/샌드박스 런타임
  - role: container-engine/kata-containers
    when:
      - kata_containers_enabled

  - role: container-engine/gvisor
    when:
      - gvisor_enabled
      - container_manager in ['docker', 'containerd']

  - role: container-engine/crun
    when:
      - crun_enabled

  - role: container-engine/youki
    when:
      - youki_enabled
      - container_manager == 'crio'

  # container_manager에 따라 하나만 실행
  - role: container-engine/cri-o
    when:
      - container_manager == 'crio'

  - role: container-engine/containerd
    when:
      - container_manager == 'containerd'

  - role: container-engine/cri-dockerd
    when:
      - container_manager == 'docker'
```
{% endraw %}

</details>

핵심 구조:

{% raw %}
```yaml
dependencies:
  - role: container-engine/validate-container-engine  # 항상 실행

  - role: container-engine/containerd                 # container_manager == 'containerd'일 때
    when:
      - container_manager == 'containerd'
```
{% endraw %}

## 실습 환경 실행 흐름

기본 설정(`container_manager: containerd`)에서의 실행 흐름:

| 순서 | 롤 | 실행 여부 | 이유 |
|------|-----|----------|------|
| 1 | validate-container-engine | 실행 | 항상 |
| 2 | kata-containers | 스킵 | `kata_containers_enabled = false` |
| 3 | gvisor | 스킵 | `gvisor_enabled = false` |
| 4 | crun | 스킵 | `crun_enabled = false` |
| 5 | youki | 스킵 | `container_manager != crio` |
| 6 | cri-o | 스킵 | `container_manager != crio` |
| 7 | containerd | 실행 | `container_manager == containerd` |
| 8 | cri-dockerd | 스킵 | `container_manager != docker` |

## validate-container-engine

**기존 컨테이너 런타임 검증 및 정리**를 담당한다. 선택한 런타임과 다른 런타임이 이미 설치되어 있으면 제거한다.

<details markdown="1">
<summary>validate-container-engine 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
- name: Check if fedora coreos
  stat:
    path: /run/ostree-booted
  register: ostree

- name: Set is_ostree
  set_fact:
    is_ostree: "{{ ostree.stat.exists }}"

- name: Populate service facts
  service_facts:

- name: Check if containerd is installed
  find:
    file_type: file
    recurse: true
    use_regex: true
    patterns:
      - containerd.service$
    paths:
      - /lib/systemd
      - /etc/systemd
      - /run/systemd
  register: containerd_installed

- name: Uninstall containerd
  when:
    - container_manager != "containerd"
    - containerd_installed.matched > 0
    - ansible_facts.services['containerd.service']['state'] == 'running'
  block:
    - name: Drain node
      include_role:
        name: remove_node/pre_remove
    - name: Stop kubelet
      service:
        name: kubelet
        state: stopped
    - name: Remove Containerd
      import_role:
        name: container-engine/containerd
        tasks_from: reset
```
{% endraw %}

</details>

핵심 로직:

{% raw %}
```yaml
- name: Populate service facts
  service_facts:

- name: Uninstall containerd
  when:
    - container_manager != "containerd"          # 선택한 런타임이 containerd가 아니고
    - containerd_installed.matched > 0           # containerd가 설치되어 있고
    - ansible_facts.services['containerd.service']['state'] == 'running'  # 실행 중이면
  block:
    - name: Remove Containerd
      import_role:
        name: container-engine/containerd
        tasks_from: reset                        # 제거
```
{% endraw %}

## containerd 롤

containerd 설치 시 실행되는 의존성 체인:

```
containerd 롤
│
└── meta/main.yml dependencies:
    ├── containerd-common    # OS별 변수 로드
    ├── runc                 # OCI 런타임 설치
    ├── crictl               # CRI 클라이언트 설치
    └── nerdctl              # Docker 호환 CLI 설치
```

### 의존성 롤 요약

| 롤 | 목적 | 핵심 동작 |
|----|------|----------|
| containerd-common | OS별 변수 로드 | `include_vars`로 배포판별 설정 |
| runc | OCI 런타임 설치 | 바이너리 다운로드 및 복사 |
| crictl | CRI 클라이언트 | 컨테이너/이미지 관리 도구 |
| nerdctl | Docker 호환 CLI | `docker` 명령어와 유사한 인터페이스 |

<details markdown="1">
<summary>containerd/tasks/main.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
- name: Download containerd
  include_tasks: "../../../download/tasks/download_file.yml"
  vars:
    download: "{{ download_defaults | combine(downloads.containerd) }}"

- name: Unpack containerd archive
  unarchive:
    src: "{{ downloads.containerd.dest }}"
    dest: "{{ containerd_bin_dir }}"
    mode: "0755"
    remote_src: true
    extra_opts:
      - --strip-components=1
  notify: Restart containerd

- name: Generate systemd service for containerd
  template:
    src: containerd.service.j2
    dest: /etc/systemd/system/containerd.service
    mode: "0644"
  notify: Restart containerd

- name: Ensure containerd directories exist
  file:
    dest: "{{ item }}"
    state: directory
    mode: "0755"
  with_items:
    - "{{ containerd_systemd_dir }}"
    - "{{ containerd_cfg_dir }}"

- name: Write containerd proxy drop-in
  template:
    src: http-proxy.conf.j2
    dest: "{{ containerd_systemd_dir }}/http-proxy.conf"
    mode: "0644"
  notify: Restart containerd
  when: http_proxy is defined or https_proxy is defined

- name: Generate default base_runtime_spec
  command: "{{ containerd_bin_dir }}/ctr oci spec"
  register: ctr_oci_spec
  check_mode: false
  changed_when: false

- name: Copy containerd config file
  template:
    src: "config.toml.j2"
    dest: "{{ containerd_cfg_dir }}/config.toml"
    owner: "root"
    mode: "0640"
  notify: Restart containerd

- name: Configure containerd registries
  block:
    - name: Create registry directories
      file:
        path: "{{ containerd_cfg_dir }}/certs.d/{{ item.prefix }}"
        state: directory
        mode: "0755"
      loop: "{{ containerd_registries_mirrors }}"
    - name: Write hosts.toml file
      template:
        src: hosts.toml.j2
        dest: "{{ containerd_cfg_dir }}/certs.d/{{ item.prefix }}/hosts.toml"
        mode: "0640"
      loop: "{{ containerd_registries_mirrors }}"

- name: Flush handlers
  meta: flush_handlers

- name: Ensure containerd is started and enabled
  systemd_service:
    name: containerd
    daemon_reload: true
    enabled: true
    state: started
```
{% endraw %}

</details>

containerd 설치 핵심 단계:

{% raw %}
```yaml
# 1. 바이너리 다운로드 및 압축 해제
- name: Unpack containerd archive
  unarchive:
    src: "{{ downloads.containerd.dest }}"
    dest: "{{ containerd_bin_dir }}"

# 2. systemd 서비스 생성
- name: Generate systemd service for containerd
  template:
    src: containerd.service.j2
    dest: /etc/systemd/system/containerd.service

# 3. 설정 파일 생성
- name: Copy containerd config file
  template:
    src: "config.toml.j2"
    dest: "{{ containerd_cfg_dir }}/config.toml"

# 4. 서비스 시작
- name: Ensure containerd is started and enabled
  systemd_service:
    name: containerd
    enabled: true
    state: started
```
{% endraw %}

<br>

# 3. download

## 역할

**필요한 바이너리와 컨테이너 이미지를 다운로드**한다. Kubespray의 "오프라인 설치" 지원을 위해 캐싱 메커니즘도 포함한다.

## 메타 설정

```yaml
allow_duplicates: true
```

`allow_duplicates: true`는 이 롤이 **여러 번 호출되어도 매번 실행**되도록 한다.

## 태스크 구조

<details markdown="1">
<summary>download/tasks/main.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
- name: Prepare working directories and variables
  import_tasks: prep_download.yml
  when:
    - not skip_downloads | default(false)

- name: Get kubeadm binary and list of required images
  include_tasks: prep_kubeadm_images.yml
  when:
    - not skip_downloads | default(false)
    - ('kube_control_plane' in group_names)

- name: Download files / images
  include_tasks: "{{ include_file }}"
  loop: "{{ downloads | combine(kubeadm_images) | dict2items }}"
  vars:
    download: "{{ download_defaults | combine(item.value) }}"
    include_file: "download_{% if download.container %}container{% else %}file{% endif %}.yml"
  when:
    - not skip_downloads | default(false)
    - download.enabled
    - item.value.enabled
```
{% endraw %}

</details>

핵심 흐름:

{% raw %}
```yaml
# 1. 다운로드 환경 준비
- import_tasks: prep_download.yml

# 2. kubeadm 이미지 목록 생성 (컨트롤플레인 노드에서만)
- include_tasks: prep_kubeadm_images.yml
  when: ('kube_control_plane' in group_names)

# 3. 파일/이미지 다운로드
- include_tasks: "download_{% if download.container %}container{% else %}file{% endif %}.yml"
  loop: "{{ downloads | combine(kubeadm_images) | dict2items }}"
```
{% endraw %}

## prep_kubeadm_images.yml

kubeadm이 필요로 하는 이미지 목록을 동적으로 생성한다:

<details markdown="1">
<summary>prep_kubeadm_images.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
- name: Download kubeadm binary
  include_tasks: "download_file.yml"
  vars:
    download: "{{ download_defaults | combine(downloads.kubeadm) }}"
  when:
    - downloads.kubeadm.enabled

- name: Copy kubeadm binary from download dir to system path
  copy:
    src: "{{ downloads.kubeadm.dest }}"
    dest: "{{ bin_dir }}/kubeadm"
    mode: "0755"
    remote_src: true

- name: Create kubeadm config
  template:
    src: "kubeadm-images.yaml.j2"
    dest: "{{ kube_config_dir }}/kubeadm-images.yaml"
    mode: "0644"

- name: Generate list of required images
  shell: "set -o pipefail && {{ bin_dir }}/kubeadm config images list --config={{ kube_config_dir }}/kubeadm-images.yaml | grep -Ev 'coredns|pause'"
  args:
    executable: /bin/bash
  register: kubeadm_images_raw
  run_once: true

- name: Parse list of images
  vars:
    kubeadm_images_list: "{{ kubeadm_images_raw.stdout_lines }}"
  set_fact:
    kubeadm_image:
      key: "kubeadm_{{ (item | regex_replace('^(?:.*\\/)*', '')).split(':')[0] }}"
      value:
        enabled: true
        container: true
        repo: "{{ item | regex_replace('^(.*):.*$', '\\1') }}"
        tag: "{{ item | regex_replace('^.*:(.*)$', '\\1') }}"
        groups:
          - k8s_cluster
  loop: "{{ kubeadm_images_list | flatten(levels=1) }}"
  register: kubeadm_images_cooked
  run_once: true

- name: Convert list of images to dict
  set_fact:
    kubeadm_images: "{{ kubeadm_images_cooked.results | map(attribute='ansible_facts.kubeadm_image') | list | items2dict }}"
  run_once: true
```
{% endraw %}

</details>

핵심 동작:

{% raw %}
```yaml
# kubeadm을 이용해 필요한 이미지 목록 생성
- name: Generate list of required images
  shell: "{{ bin_dir }}/kubeadm config images list --config={{ kube_config_dir }}/kubeadm-images.yaml"
  register: kubeadm_images_raw

# 이미지 목록을 딕셔너리로 변환하여 다운로드에 사용
- name: Convert list of images to dict
  set_fact:
    kubeadm_images: "{{ ... | items2dict }}"
```
{% endraw %}

## download_file.yml

파일 다운로드의 핵심 로직:

<details markdown="1">
<summary>download_file.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
- name: Set pathname of cached file
  set_fact:
    file_path_cached: "{{ download_cache_dir }}/{{ download.dest | basename }}"

- name: Create dest directory on node
  file:
    path: "{{ download.dest | dirname }}"
    mode: "0755"
    state: directory
    recurse: true

- name: Create local cache directory
  file:
    path: "{{ file_path_cached | dirname }}"
    state: directory
    recurse: true
  delegate_to: localhost
  run_once: true
  become: false
  when:
    - download_force_cache

- name: Download item
  get_url:
    url: "{{ download.url }}"
    dest: "{{ file_path_cached if download_force_cache else download.dest }}"
    checksum: "{{ download.checksum }}"
    validate_certs: "{{ download_validate_certs }}"
  delegate_to: "{{ download_delegate if download_force_cache else inventory_hostname }}"
  run_once: "{{ download_force_cache }}"
  register: get_url_result
  until: "'OK' in get_url_result.msg or 'file already exists' in get_url_result.msg"
  retries: "{{ download_retries }}"
  delay: "{{ retry_stagger | default(5) }}"
  environment: "{{ proxy_env }}"

- name: Copy file from cache to nodes
  ansible.posix.synchronize:
    src: "{{ file_path_cached }}"
    dest: "{{ download.dest }}"
    use_ssh_args: true
    mode: push
  when:
    - download_force_cache

- name: Set mode and owner
  file:
    path: "{{ download.dest }}"
    mode: "{{ download.mode | default(omit) }}"
    owner: "{{ download.owner | default(omit) }}"
  when:
    - download_force_cache
```
{% endraw %}

</details>

캐싱 메커니즘:

{% raw %}
```yaml
# 1. 캐시 경로 또는 직접 다운로드
- name: Download item
  get_url:
    url: "{{ download.url }}"
    dest: "{{ file_path_cached if download_force_cache else download.dest }}"
  delegate_to: "{{ download_delegate if download_force_cache else inventory_hostname }}"

# 2. 캐시에서 각 노드로 복사
- name: Copy file from cache to nodes
  ansible.posix.synchronize:
    src: "{{ file_path_cached }}"
    dest: "{{ download.dest }}"
  when: download_force_cache
```
{% endraw %}

<br>

# 실행 로그 분석

> **참고**: 이 플레이는 태스크가 매우 많아 주요 태스크 위주로 분석한다. 전체 로그는 접은 글에서 확인할 수 있다.

## kubernetes/preinstall

<details markdown="1">
<summary>kubernetes/preinstall 실행 로그 (클릭하여 펼치기)</summary>

```
TASK [kubernetes/preinstall : Preinstall | restart kube-apiserver cance] *******
ok: [k8s-m]

TASK [kubernetes/preinstall : Stop if either kube_control_plane or kube_node group is empty] ***
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Stop if etcd group is empty in external etcd mode] ***
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Stop if non systemd OS type] ********************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Stop if unknown OS] ******************************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Ensure minimum kernel version] *******************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Ensure minimum containerd version] ***************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Stop if bad hostname] ****************************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [kubernetes/preinstall : Check if conntrack is installed] *****************
ok: [k8s-m]

TASK [kubernetes/preinstall : Stop if conntrack binary is missing] *************
ok: [k8s-m] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [adduser : User | Create User Group] **************************************
ok: [k8s-m]

TASK [adduser : User | Create User] ********************************************
ok: [k8s-m]

TASK [kubernetes/preinstall : ensure swap is off] ******************************
ok: [k8s-m]

TASK [kubernetes/preinstall : set default sysctl file path] ********************
ok: [k8s-m]

TASK [kubernetes/preinstall : Change sysctl setting] ***************************
ok: [k8s-m] => (item={'name': 'net.ipv4.ip_forward', 'value': 1})
ok: [k8s-m] => (item={'name': 'net.ipv4.conf.all.forwarding', 'value': 1})
ok: [k8s-m] => (item={'name': 'net.ipv6.conf.all.forwarding', 'value': 1})

TASK [kubernetes/preinstall : Hosts | create list from inventory] **************
ok: [k8s-m]

TASK [kubernetes/preinstall : Hosts | populate inventory into hosts file] ******
changed: [k8s-m]

TASK [kubernetes/preinstall : Configure dhclient to supersede search/domain/nameservers] ***
changed: [k8s-m]

TASK [kubernetes/preinstall : Configure dhclient hooks for resolv.conf] ********
ok: [k8s-m]

TASK [kubernetes/preinstall : Create kubernetes directories] *******************
ok: [k8s-m] => (item=/etc/kubernetes)
ok: [k8s-m] => (item=/etc/kubernetes/ssl)
ok: [k8s-m] => (item=/etc/kubernetes/manifests)
ok: [k8s-m] => (item=/usr/local/bin/kubernetes-scripts)
ok: [k8s-m] => (item=/usr/libexec/kubernetes/kubelet-plugins/volume/exec)
```

</details>

### 주요 태스크 분석

| 태스크 | 결과 | 설명 |
|--------|------|------|
| Stop if either kube_control_plane or kube_node group is empty | ok | 필수 그룹 존재 확인 |
| Stop if etcd group is empty in external etcd mode | ok | etcd 그룹 검증 |
| Stop if unknown OS | ok | 지원 OS 확인 |
| Ensure minimum kernel version | ok | 커널 버전 검증 |
| adduser: Create User | ok | kube 사용자 생성 |
| ensure swap is off | ok | swap 비활성화 확인 |
| Change sysctl setting | ok | `ip_forward` 등 커널 파라미터 설정 |
| Create kubernetes directories | ok | `/etc/kubernetes` 등 디렉토리 생성 |

## container-engine

<details markdown="1">
<summary>container-engine 실행 로그 (클릭하여 펼치기)</summary>

```
TASK [container-engine/validate-container-engine : Validate-container-engine | check if fedora coreos] ***
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Validate-container-engine | set is_ostree] ***
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Ensure kubelet systemd unit exists] ***
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Populate service facts] *****
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Check if containerd is installed] ***
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Check if docker is installed] ***
ok: [k8s-m]

TASK [container-engine/validate-container-engine : Check if crio is installed] ***
ok: [k8s-m]

TASK [container-engine/containerd-common : Containerd-common | check if fedora coreos] ***
ok: [k8s-m]

TASK [container-engine/containerd-common : Containerd-common | set is_ostree] ***
ok: [k8s-m]

TASK [container-engine/runc : Runc | check if fedora coreos] *******************
ok: [k8s-m]

TASK [container-engine/runc : Runc | set is_ostree] ****************************
ok: [k8s-m]

TASK [container-engine/runc : Runc | Uninstall runc package managed by package manager] ***
ok: [k8s-m]

TASK [container-engine/runc : Runc | Download runc binary] *********************
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m

TASK [container-engine/runc : Download_file | download /tmp/releases/runc] *****
ok: [k8s-m]

TASK [container-engine/runc : Copy runc binary from download dir] **************
ok: [k8s-m]

TASK [container-engine/crictl : Install crictl] ********************************
included: /kubespray/roles/container-engine/crictl/tasks/crictl.yml for k8s-m

TASK [container-engine/crictl : Crictl | Download crictl] **********************
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m

TASK [container-engine/crictl : Download_file | download /tmp/releases/crictl-v1.32.0-linux-amd64.tar.gz] ***
ok: [k8s-m]

TASK [container-engine/crictl : Install crictl config] *************************
ok: [k8s-m]

TASK [container-engine/crictl : Copy crictl binary from download dir] **********
ok: [k8s-m]

TASK [container-engine/nerdctl : Nerdctl | Download nerdctl] *******************
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m

TASK [container-engine/nerdctl : Download_file | download /tmp/releases/nerdctl-2.0.2-linux-amd64.tar.gz] ***
ok: [k8s-m]

TASK [container-engine/nerdctl : Nerdctl | Copy nerdctl binary from download dir] ***
ok: [k8s-m]

TASK [container-engine/nerdctl : Nerdctl | Create configuration dir] ***********
ok: [k8s-m]

TASK [container-engine/nerdctl : Nerdctl | Install nerdctl configuration] ******
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Download containerd] **********
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m

TASK [container-engine/containerd : Download_file | download /tmp/releases/containerd-2.0.1-linux-amd64.tar.gz] ***
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Unpack containerd archive] ****
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Generate systemd service for containerd] ***
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Ensure containerd directories exist] ***
ok: [k8s-m] => (item=/etc/systemd/system/containerd.service.d)
ok: [k8s-m] => (item=/etc/containerd)

TASK [container-engine/containerd : Containerd | Generate default base_runtime_spec] ***
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Store generated default base_runtime_spec] ***
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Copy containerd config file] ***
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Create registry directories] ***
ok: [k8s-m] => (item={'prefix': 'docker.io', 'mirrors': [{'host': 'https://mirror.gcr.io', 'capabilities': ['pull', 'resolve']}]})

TASK [container-engine/containerd : Containerd | Write hosts.toml file] ********
ok: [k8s-m] => (item={'prefix': 'docker.io', 'mirrors': [{'host': 'https://mirror.gcr.io', 'capabilities': ['pull', 'resolve']}]})

TASK [container-engine/containerd : Containerd | Flush handlers] ***************
ok: [k8s-m]

TASK [container-engine/containerd : Containerd | Ensure containerd is started and enabled] ***
ok: [k8s-m]
```

</details>

### 주요 태스크 분석

| 태스크 | 결과 | 설명 |
|--------|------|------|
| validate-container-engine: Check if containerd/docker/crio is installed | ok | 기존 런타임 확인 |
| runc: Download runc binary | ok | OCI 런타임 다운로드 |
| crictl: Download crictl | ok | CRI 클라이언트 다운로드 (v1.32.0) |
| nerdctl: Download nerdctl | ok | Docker 호환 CLI 다운로드 (v2.0.2) |
| containerd: Download containerd | ok | containerd 다운로드 (v2.0.1) |
| containerd: Unpack containerd archive | ok | 바이너리 압축 해제 |
| containerd: Generate systemd service | ok | systemd 서비스 파일 생성 |
| containerd: Copy containerd config file | ok | config.toml 생성 |
| containerd: Create registry directories | ok | docker.io 미러 설정 |
| containerd: Ensure containerd is started and enabled | ok | 서비스 시작 및 활성화 |

## download

<details markdown="1">
<summary>download 실행 로그 (클릭하여 펼치기)</summary>

```
TASK [download : Download | Prepare working directories and variables] *********
included: /kubespray/roles/download/tasks/prep_download.yml for k8s-m

TASK [download : Prep_download | Set a few facts] ******************************
ok: [k8s-m]

TASK [download : Prep_download | Register docker images info] ******************
ok: [k8s-m]

TASK [download : Prep_download | Create staging directory on remote node] ******
ok: [k8s-m]

TASK [download : Download | Get kubeadm binary and list of required images] ****
included: /kubespray/roles/download/tasks/prep_kubeadm_images.yml for k8s-m

TASK [download : Prep_kubeadm_images | Download kubeadm binary] ****************
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m

TASK [download : Download_file | download /tmp/releases/kubeadm-v1.32.0-amd64] ***
ok: [k8s-m]

TASK [download : Prep_kubeadm_images | Copy kubeadm binary from download dir to system path] ***
ok: [k8s-m]

TASK [download : Prep_kubeadm_images | Create kubeadm config] ******************
ok: [k8s-m]

TASK [download : Prep_kubeadm_images | Generate list of required images] *******
ok: [k8s-m]

TASK [download : Prep_kubeadm_images | Parse list of images] *******************
ok: [k8s-m] => (item=registry.k8s.io/kube-apiserver:v1.32.0)
ok: [k8s-m] => (item=registry.k8s.io/kube-controller-manager:v1.32.0)
ok: [k8s-m] => (item=registry.k8s.io/kube-scheduler:v1.32.0)
ok: [k8s-m] => (item=registry.k8s.io/kube-proxy:v1.32.0)

TASK [download : Prep_kubeadm_images | Convert list of images to dict] *********
ok: [k8s-m]

TASK [download : Download | Download files / images] ***************************
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m => (item={'key': 'kubeadm', ...})
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m => (item={'key': 'kubelet', ...})
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m => (item={'key': 'kubectl', ...})
included: /kubespray/roles/download/tasks/download_file.yml for k8s-m => (item={'key': 'cni', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'pause', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'coredns', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'nodelocaldns', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'calico_node', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'calico_cni', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'calico_apiserver', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'kubeadm_kube-apiserver', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'kubeadm_kube-controller-manager', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'kubeadm_kube-scheduler', ...})
included: /kubespray/roles/download/tasks/download_container.yml for k8s-m => (item={'key': 'kubeadm_kube-proxy', ...})

TASK [download : Download_file | download kubeadm-v1.32.0-amd64] ***************
ok: [k8s-m]

TASK [download : Download_file | download kubelet-v1.32.0-amd64] ***************
ok: [k8s-m]

TASK [download : Download_file | download kubectl-v1.32.0-amd64] ***************
ok: [k8s-m]

TASK [download : Download_file | download cni-plugins-linux-amd64-v1.6.1.tgz] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/pause:3.10] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/coredns/coredns:v1.11.4] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/dns/k8s-dns-node-cache:1.24.0] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image quay.io/calico/node:v3.29.1] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image quay.io/calico/cni:v3.29.1] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image quay.io/calico/apiserver:v3.29.1] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/kube-apiserver:v1.32.0] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/kube-controller-manager:v1.32.0] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/kube-scheduler:v1.32.0] ***
ok: [k8s-m]

TASK [download : Download_container | Pull image registry.k8s.io/kube-proxy:v1.32.0] ***
ok: [k8s-m]
```

</details>

### 주요 태스크 분석

**바이너리 다운로드:**

| 파일 | 버전 | 설명 |
|------|------|------|
| kubeadm | v1.32.0 | 클러스터 부트스트랩 도구 |
| kubelet | v1.32.0 | 노드 에이전트 |
| kubectl | v1.32.0 | CLI 도구 |
| cni-plugins | v1.6.1 | CNI 플러그인 |

**컨테이너 이미지 다운로드:**

| 이미지 | 버전 | 용도 |
|--------|------|------|
| pause | 3.10 | Pod 인프라 컨테이너 |
| coredns | v1.11.4 | 클러스터 DNS |
| k8s-dns-node-cache | 1.24.0 | 노드 로컬 DNS 캐시 |
| calico/node | v3.29.1 | Calico CNI 에이전트 |
| calico/cni | v3.29.1 | Calico CNI 플러그인 |
| calico/apiserver | v3.29.1 | Calico API 서버 |
| kube-apiserver | v1.32.0 | K8s API 서버 |
| kube-controller-manager | v1.32.0 | 컨트롤러 매니저 |
| kube-scheduler | v1.32.0 | 스케줄러 |
| kube-proxy | v1.32.0 | 네트워크 프록시 |

<br>

# 정리

`Prepare for etcd install` 플레이는 **실제 클러스터 구성 전 모든 준비 작업**을 수행한다:

| 역할 | 수행 작업 |
|------|----------|
| `kubespray_defaults` | 기본 변수 로드 |
| `kubernetes/preinstall` | swap 비활성화, DNS, sysctl 등 |
| `container-engine` | containerd/docker/cri-o 설치 |
| `download` | 바이너리, 이미지 다운로드 |

이 플레이가 완료되면:
- 모든 노드에서 swap이 비활성화됨
- 컨테이너 런타임(containerd)이 설치되고 실행 중
- kubeadm, kubelet 등 필요한 바이너리가 다운로드됨
- K8s 컴포넌트 이미지가 준비됨

다음 글에서는 etcd 클러스터를 설치하는 `install_etcd.yml`을 분석한다.

<br>

# 참고 자료

- [Kubespray kubernetes/preinstall 롤](https://github.com/kubernetes-sigs/kubespray/tree/master/roles/kubernetes/preinstall)
- [Kubespray container-engine 롤](https://github.com/kubernetes-sigs/kubespray/tree/master/roles/container-engine)
- [Kubespray download 롤](https://github.com/kubernetes-sigs/kubespray/tree/master/roles/download)
- [Kubernetes swap 요구사항](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/#before-you-begin)
- [containerd 공식 문서](https://containerd.io/docs/)
- [이전 글: internal_facts.yml]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-03 %})
