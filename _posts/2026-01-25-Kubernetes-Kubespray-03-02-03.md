---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.2.3. 변수 분석 - kubespray_defaults 역할"
excerpt: "Kubespray의 kubespray_defaults 역할과 변수 시스템을 분석해보자."
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

이번 글에서는 **kubespray_defaults 역할의 변수 시스템**을 분석한다.

- **kubespray_defaults 역할**: 변수 로드 전용, `defaults/`와 `vars/` 분리
- **defaults/main/**: 사용자가 커스터마이징할 수 있는 설정 (kube_version, network 등)
- **vars/main/**: 체크섬, 내부 계산값 등 변경하면 안 되는 값
- **변수 커스터마이징**: `group_vars/`에서 오버라이드 가능한 설정과 변경 불가 항목

> [이전 글]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-02 %})에서 그룹 변수를 확인했다. 이번 글에서는 `kubespray_defaults` 역할의 변수 시스템을 분석한다.

<br>

# kubespray_defaults 

kubespray_defaults role은 kubespray 전체 play, role, task가 참조하는 최상위 기본 변수 집합이다. 

## 역할의 목적

Kubespray의 거의 모든 플레이북에서 `kubespray_defaults` 역할이 포함된다:

```yaml
- hosts: all
  gather_facts: false
  roles:
    - { role: kubespray_defaults }
```

이 역할은 **변수 로드 전용**이다. 실제 태스크는 하나도 없고, `defaults/main/`과 `vars/main/` 디렉토리에서 변수만 가져온다.

<br>

## 디렉토리 구조

`kubespray_defaults` 역할의 변수 디렉토리 구조:

```
roles/kubespray_defaults/
├── defaults/
│   └── main/
│       ├── main.yml          # 핵심 설정 (kube_version, network 등)
│       └── download.yml      # 다운로드 URL, 이미지 저장소 등
└── vars/
    └── main/
        ├── main.yml          # 내부 계산값 (버전 매핑 등)
        └── checksums.yml     # 바이너리 SHA256 체크섬
```

Kubespray는 Ansible 변수 우선순위를 활용해 변수를 분리한다:

| 우선순위 | 위치 | 용도 |
|----------|------|------|
| 2 (낮음) | `defaults/main/` | 기본값, 사용자가 쉽게 오버라이드 가능 |
| 4-6 | `inventory/group_vars/*` | 사용자 커스터마이징 (실제 수정하는 곳) |
| 15 (높음) | `vars/main/` | 내부 고정값, 변경 비권장 (체크섬 등) |

> **참고**: `inventory/group_vars/`는 `kubespray_defaults` 역할의 디렉토리가 아니다. 변수 흐름 이해를 위해 포함했다.
> Ansible 변수 우선순위(22단계)와 Kubespray의 변수 배치 전략에 대한 상세한 내용은 [변수 분석 - Kubespray 변수 배치 전략]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %})을 참고한다.


[그룹 변수 확인]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-02 %})에서 살펴봤듯이, 실제 변수 커스터마이징은 `inventory/group_vars/`에서 진행된다. `kubespray_defaults/defaults/`에 정의된 변수는 `group_vars/`의 우선순위가 더 높기 때문에 덮어쓸 수 있다. 반면 `kubespray_defaults/vars/`에 정의된 변수는 `group_vars/`보다 우선순위가 높아 덮어쓰기 어렵다.

<br>

## defaults/main 분석

### main.yml - 핵심 설정

![kubespray-deafult-default_main]({{site.url}}/assets/images/kubespray-deafult-default_main.svg)

Kubernetes 클러스터의 핵심 설정을 정의한다. 버전, 네트워크, 컨테이너 런타임 등 클러스터 구성의 기본값이 여기에 있다. 주요 변수는 아래와 같다.


**클러스터 기본 설정:**

{% raw %}
```yaml
# Kubernetes 버전 (기본값: 체크섬이 있는 최신 버전)
kube_version: "{{ (kubelet_checksums['amd64'] | dict2items)[0].key }}"

# kube-proxy 모드
kube_proxy_mode: ipvs  # ipvs, iptables, nftables 중 선택

# kubeadm config API 버전
kubeadm_config_api_version: "{{ 'v1beta4' if kube_version is version('1.31.0', '>=') else 'v1beta3' }}"

# 컨테이너 런타임
container_manager: containerd

# 네트워크 플러그인
kube_network_plugin: calico

# DNS 설정
dns_mode: coredns
enable_nodelocaldns: true

# 서비스/파드 네트워크
kube_service_addresses: 10.233.0.0/18
kube_pods_subnet: 10.233.64.0/18
kube_network_node_prefix: 24
```
{% endraw %}

**네트워크 스택 설정:**

{% raw %}
```yaml
# IPv4/IPv6 듀얼 스택 설정
# enable_dual_stack_networks: false  # deprecated

# IPv4 스택 활성화
ipv4_stack: true

# IPv6 스택 활성화 (기본값: enable_dual_stack_networks의 값, 기본 false)
ipv6_stack: "{{ enable_dual_stack_networks | default(false) }}"

# API 서버 바인드 주소
# "::" = 모든 IPv6 주소 (IPv4-mapped IPv6 포함)
# "0.0.0.0"으로 변경 시 API 서버 파드 동작 실패 가능
kube_apiserver_bind_address: "::"
```
{% endraw %}

> **주의**: `kube_apiserver_bind_address`를 `0.0.0.0`으로 변경하면 API 서버가 시작되지 않을 수 있다. 기본값 `::`는 IPv6와 IPv4-mapped IPv6를 모두 지원한다.

**kubeadm 관련 설정:**

{% raw %}
```yaml
# kubeadm init 시 스킵할 단계
kubeadm_init_phases_skip_default: [ "addon/coredns" ]
kubeadm_init_phases_skip: >-
  {%- if kube_network_plugin == 'cilium' and cilium_kube_proxy_replacement -%}
  {{ kubeadm_init_phases_skip_default + ["addon/kube-proxy"] }}
  {%- else -%}
  {{ kubeadm_init_phases_skip_default }}
  {%- endif -%}

# kubeadm init 타임아웃
kubeadm_init_timeout: 300s
```
{% endraw %}

**디렉토리 설정:**

{% raw %}
```yaml
bin_dir: /usr/local/bin
kube_config_dir: /etc/kubernetes
kube_cert_dir: "{{ kube_config_dir }}/ssl"
kube_manifest_dir: "{{ kube_config_dir }}/manifests"
etcd_data_dir: /var/lib/etcd
```
{% endraw %}

**sysctl 커널 파라미터 설정:**

{% raw %}
```yaml
# 커스텀 sysctl 변수 추가
# 예: additional_sysctl:
#      - { name: kernel.pid_max, value: 131072 }
additional_sysctl: []

# Feature Gates 설정
kube_feature_gates: []
kube_apiserver_feature_gates: []
kube_controller_feature_gates: []
kube_scheduler_feature_gates: []
kube_proxy_feature_gates: []
kubelet_feature_gates: []
kubeadm_feature_gates: []

# sysctl 설정 파일 경로
sysctl_file_path: "/etc/sysctl.d/99-sysctl.conf"

# 알 수 없는 sysctl 키에 대한 오류 무시 여부
sysctl_ignore_unknown_keys: false
```
{% endraw %}

Kubespray는 Kubernetes 클러스터 동작에 필요한 커널 파라미터를 자동으로 `/etc/sysctl.d/99-sysctl.conf`에 적용한다:

```bash
# 파드 간 패킷 라우팅 활성화
net.ipv4.ip_forward=1

# 브리지 트래픽에 iptables/ip6tables 규칙 적용
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-arptables=1
net.bridge.bridge-nf-call-ip6tables=1

# NodePort 서비스를 위한 포트 예약 (30000-32767)
net.ipv4.ip_local_reserved_ports=30000-32767

# 기타 커널 안정성 설정
kernel.keys.root_maxbytes=25000000
kernel.keys.root_maxkeys=1000000
kernel.panic=10
kernel.panic_on_oops=1
vm.overcommit_memory=1
vm.panic_on_oom=0
```

이 설정들이 올바르게 적용되었는지 확인한다. 

```bash
cat /etc/sysctl.d/99-sysctl.conf
```

해당 설정들은 클러스터 네트워킹 설정에 필수적인 값들로, 해당 설정이 잘못되면 클러스터 네트워킹이 정상 동작하지 않을 수 있다.
- `net.ipv4.ip_forward=1`: 파드 간 통신에 필수
- `net.bridge.bridge-nf-call-*`: 네트워크 플러그인(Calico, Cilium 등) 동작에 필수
- `net.ipv4.ip_local_reserved_ports`: NodePort 서비스가 다른 애플리케이션과 포트 충돌을 방지

### download.yml - 다운로드 설정

![kubespray-deafult-default_download]({{site.url}}/assets/images/kubespray-deafult-default_download.svg)

바이너리와 컨테이너 이미지의 다운로드 URL, 저장소 주소를 정의한다. 에어갭 환경이나 프라이빗 레지스트리 사용 시 이 변수들을 오버라이드한다.

#### A. 다운로드 정책 / 캐시 전략

```yaml
# 노드에 실제 배포될 파일 위치
local_release_dir: /tmp/releases

# Ansible runner 캐시 디렉토리
download_cache_dir: /tmp/kubespray_cache

# 1회 다운로드 후 모든 노드에 공유 (대역폭 절약)
download_run_once: false

# localhost에서 다운로드 후 배포
download_localhost: false

# 캐시 강제 재사용 (재다운로드 방지)
download_force_cache: false

# 다운로드 재시도 횟수
download_retries: 4
```

**전략 조합 예시:**

- **대규모 클러스터**: `download_run_once: true` → 한 노드에서만 다운로드, 나머지는 복사
- **에어갭 환경**: `download_localhost: true` + `download_force_cache: true` → 로컬 캐시 활용
- **불안정한 네트워크**: `download_retries: 10` → 재시도 횟수 증가

#### B. 이미지 Pull 엔진 추상화

컨테이너 런타임에 따라 적절한 이미지 pull 도구를 자동으로 선택한다:

{% raw %}
```yaml
# container_manager에 따른 이미지 pull 도구 선택
image_command_tool: "{{ 'nerdctl' if container_manager == 'containerd' else 'crictl' if container_manager == 'crio' else 'docker' }}"

# 이미지 pull 명령어 (lookup을 통해 런타임별 명령어 매핑)
image_pull_command: "{{ lookup('vars', container_manager + '_pull_command') }}"

# 이미지 정보 조회 명령어
image_info_command: "{{ lookup('vars', container_manager + '_info_command') }}"
```
{% endraw %}

| 컨테이너 런타임 | Pull 도구 | 명령어 예시 |
|----------------|-----------|-------------|
| containerd | nerdctl | `nerdctl pull registry.k8s.io/pause:3.10` |
| crio | crictl | `crictl pull registry.k8s.io/pause:3.10` |
| docker | docker | `docker pull registry.k8s.io/pause:3.10` |

런타임 추상화 덕분에 사용자는 `container_manager` 변수만 설정하면 나머지는 자동 처리된다.

#### C. Checksum 기반 버전 결정 로직

Kubespray는 체크섬 목록을 기반으로 **안전하게 검증된 버전만 자동 선택**한다:

{% raw %}
```yaml
# containerd 버전: 체크섬이 있는 최신 버전 자동 선택
containerd_version: "{{ (containerd_archive_checksums['amd64'] | dict2items)[0].key }}"

# 동일 패턴이 모든 컴포넌트에 적용
etcd_version: "{{ (etcd_binary_checksums['amd64'] | dict2items | selectattr('key', 'version', etcd_supported_versions[kube_major_version], '=='))[0].key }}"
```
{% endraw %}

**동작 원리:**

1. **체크섬 목록 = 허용된 버전 집합**: `vars/main/checksums.yml`에 정의된 버전만 사용 가능
2. **가장 최신 안정 버전 자동 선택**: 딕셔너리의 첫 번째 키 추출 (`[0].key`)
3. **Kubernetes 버전과 호환성 보장**: `etcd_supported_versions` 매핑으로 K8s 버전별 호환 etcd 선택

**장점:**
- 변조된 바이너리 설치 방지
- 버전 간 호환성 자동 관리
- 안전하게 검증된 조합만 배포

#### D. 다운로드 URL 생성

URL은 **(Repo) × (Version) × (Arch)** 조합으로 동적 생성된다:

**기본 다운로드 URL:**

```yaml
github_url: https://github.com
dl_k8s_io_url: https://dl.k8s.io
storage_googleapis_url: https://storage.googleapis.com
get_helm_url: https://get.helm.sh
```

**URL 템플릿 예시:**

{% raw %}
```yaml
kubelet_download_url: "{{ dl_k8s_io_url }}/release/v{{ kube_version }}/bin/linux/{{ image_arch }}/kubelet"
kubectl_download_url: "{{ dl_k8s_io_url }}/release/v{{ kube_version }}/bin/linux/{{ image_arch }}/kubectl"
kubeadm_download_url: "{{ dl_k8s_io_url }}/release/v{{ kube_version }}/bin/linux/{{ image_arch }}/kubeadm"
etcd_download_url: "{{ github_url }}/etcd-io/etcd/releases/download/v{{ etcd_version }}/etcd-v{{ etcd_version }}-linux-{{ image_arch }}.tar.gz"
containerd_download_url: "{{ github_url }}/containerd/containerd/releases/download/v{{ containerd_version }}/containerd-{{ containerd_version }}-linux-{{ image_arch }}.tar.gz"
```
{% endraw %}

**변수 치환 예시:**

- `kube_version: 1.33.3` + `image_arch: amd64`
- → `https://dl.k8s.io/release/v1.33.3/bin/linux/amd64/kubelet`

에어갭 환경에서는 `dl_k8s_io_url`만 변경하면 모든 URL이 자동으로 미러 서버를 가리킨다.

#### E. 이미지/바이너리 Repo 정의

Mirror 또는 Private Registry 전환이 용이하도록 **공급망 분리 설계**가 적용되어 있다:

```yaml
# 공식 Kubernetes 이미지
kube_image_repo: registry.k8s.io

# 서드파티 이미지 저장소
docker_image_repo: docker.io
quay_image_repo: quay.io
github_image_repo: ghcr.io
gcr_image_repo: gcr.io
```

**프라이빗 레지스트리 전환 예시:**

```yaml
# inventory/group_vars/all.yml 에서 오버라이드
kube_image_repo: my-registry.company.com/kubernetes
docker_image_repo: my-registry.company.com/dockerhub
```

이렇게 설정하면 모든 이미지가 자동으로 프라이빗 레지스트리에서 pull된다.

#### F. downloads: 실제 다운로드 객체 목록 (핵심)

Kubespray의 핵심 데이터 구조로, 다운로드할 모든 파일과 이미지를 정의한다.

**공통 구조 패턴:**

{% raw %}
```yaml
downloads:
  <name>:
    enabled: <조건식>          # 다운로드 활성화 조건
    container: true|false      # 컨테이너 이미지 여부
    file: true|false           # 바이너리/YAML 파일 여부
    repo: <이미지 저장소>       # container: true 일 때
    tag: <이미지 태그>          # container: true 일 때
    url: <다운로드 URL>         # file: true 일 때
    checksum: <SHA256>         # file: true 일 때
    dest: <저장 경로>           # file: true 일 때
    groups: [<호스트 그룹>]    # 배포 대상 노드 그룹
```
{% endraw %}

**container/file 이중 모델 (타입별 의미):**

| 타입 | `container` | `file` | 용도 | 처리 방식 |
|------|------------|--------|------|----------|
| 컨테이너 이미지 | `true` | `false` | pause, coredns, etcd 등 | `nerdctl pull` / `crictl pull` |
| 바이너리 파일 | `false` | `true` | kubelet, kubectl, kubeadm 등 | `wget` / `curl` 다운로드 |
| YAML 매니페스트 | `false` | `true` | CNI 플러그인 설정 등 | 파일 다운로드 |

**Node Group 기반 배포 전략 (groups별 의미):**

| 그룹 | 배포 대상 | 예시 컴포넌트 |
|------|----------|--------------|
| `etcd` | etcd 전용 노드 | etcd 바이너리/이미지 |
| `k8s_cluster` | 모든 노드 (컨트롤+워커) | kubelet, kubectl, pause, coredns |
| `kube_control_plane` | 컨트롤 플레인만 | kube-apiserver, kube-controller-manager |
| `kube_node` | 워커 노드만 | 워커 전용 CNI 플러그인 |

**실제 예시:**

<details markdown="1">
<summary>1. kubelet (바이너리 파일)</summary>

{% raw %}
```yaml
kubelet:
  enabled: true
  file: true
  dest: "{{ local_release_dir }}/kubelet-{{ kube_version }}-{{ image_arch }}"
  url: "{{ kubelet_download_url }}"
  checksum: "{{ kubelet_binary_checksum }}"
  unarchive: false
  owner: root
  mode: "0755"
  groups:
    - k8s_cluster  # 모든 노드에 배포
```
{% endraw %}

</details>

<details markdown="1">
<summary>2. coredns (컨테이너 이미지)</summary>

{% raw %}
```yaml
coredns:
  enabled: "{{ dns_mode in ['coredns', 'coredns_dual'] }}"  # DNS 모드가 coredns일 때만
  container: true
  repo: "{{ kube_image_repo }}/coredns/coredns"
  tag: "v1.12.1"
  groups:
    - k8s_cluster  # 모든 노드에서 이미지 pull
```
{% endraw %}

</details>

<details markdown="1">
<summary>3. etcd (조건부 배포)</summary>

{% raw %}
```yaml
etcd:
  enabled: "{{ etcd_deployment_type == 'host' }}"  # 호스트 모드일 때만
  file: true
  url: "{{ etcd_download_url }}"
  checksum: "{{ etcd_binary_checksum }}"
  groups:
    - etcd  # etcd 노드에만 배포
```
{% endraw %}

</details>

#### G. download_defaults: 공통 fallback

누락된 필드를 방지하기 위한 기본값이다:

```yaml
download_defaults:
  container: false
  file: false
  enabled: false
  dest: ""
  repo: ""
  tag: ""
  sha256: ""
  url: ""
  unarchive: false
  owner: root
  mode: "0644"
  groups: []
```

Ansible의 `combine` 필터로 병합되어, `downloads` 딕셔너리의 각 항목에서 정의되지 않은 필드는 `download_defaults`의 값으로 자동 채워진다:

{% raw %}
```yaml
# 실제 사용 예시
{{ download_defaults | combine(downloads['kubelet']) }}
```
{% endraw %}

**장점:**
- 일관된 데이터 구조 보장
- 누락된 필드로 인한 에러 방지
- 태스크 로직 단순화

<br>

## vars/main 분석

### checksums.yml - 바이너리 체크섬

모든 바이너리의 SHA256 체크섬이 아키텍처별로 정의되어 있다. **변조되었거나 손상된 파일의 설치를 방지**하기 위한 목적이다. `download` 롤이 kubelet, kubectl, etcd, containerd 등의 바이너리를 다운로드할 때, 다운로드된 파일의 SHA256 해시를 정의된 값과 비교하여 일치하지 않으면 태스크 실패 처리한다.

아키텍처별, 버전별로 바이너리 파일 내용이 다르므로 체크섬도 다르다. 지원하는 모든 아키텍처-버전 조합에 대해 체크섬이 사전 정의되어 있다.



```yaml
kubelet_checksums:
  arm64:
    1.33.3: sha256:3f69bb32debfaf25fce91aa5e7181e1e32f3550f3257b93c17dfb37bed621a9c
    1.33.2: sha256:0fa15aca9b90fe7aef1ed3aad31edd1d9944a8c7aae34162963a6aaaf726e065
    # ...
  amd64:
    1.33.3: sha256:37f9093ed2b4669cccf5474718e43ec412833e1267c84b01e662df2c4e5d7aaa
    1.33.2: sha256:77fa5d29995653fe7e2855759a909caf6869c88092e2f147f0b84cbdba98c8f3
    # ...
```

**지원되는 컴포넌트:**

- `kubelet_checksums`, `kubectl_checksums`, `kubeadm_checksums`
- `etcd_binary_checksums`
- `containerd_archive_checksums`
- `cni_binary_checksums`
- `crictl_checksums`
- `calicoctl_binary_checksums`
- `helm_archive_checksums`
- 그 외 다수

### main.yml - 내부 계산값

**버전 관련 변수:**

{% raw %}
```yaml
# Kubernetes 메이저 버전 추출 (1.33.3 => 1.33)
kube_major_version: "{{ (kube_version | split('.'))[:-1] | join('.') }}"

# 다음 메이저 버전 계산
kube_next: "{{ ((kube_version | split('.'))[1] | int) + 1 }}"
kube_major_next_version: "1.{{ kube_next }}"
```
{% endraw %}

**버전 호환성 매핑:**

{% raw %}
```yaml
pod_infra_supported_versions:
  '1.33': '3.10'
  '1.32': '3.10'
  '1.31': '3.10'

etcd_supported_versions:
  '1.33': "{{ (etcd_binary_checksums['amd64'].keys() | select('version', '3.6', '<'))[0] }}"
  '1.32': "{{ (etcd_binary_checksums['amd64'].keys() | select('version', '3.6', '<'))[0] }}"
  '1.31': "{{ (etcd_binary_checksums['amd64'].keys() | select('version', '3.6', '<'))[0] }}"
```
{% endraw %}

**네트워크 서브넷 계산:**

{% raw %}
```yaml
# IPv4/IPv6 스택에 따른 서비스 서브넷
kube_service_subnets: >-
  {%- if ipv4_stack and ipv6_stack -%}
  {{ kube_service_addresses }},{{ kube_service_addresses_ipv6 }}
  {%- elif ipv4_stack -%}
  {{ kube_service_addresses }}
  {%- else -%}
  {{ kube_service_addresses_ipv6 }}
  {%- endif -%}
```
{% endraw %}

실제 변수 커스터마이징은 `inventory/group_vars/`에서 진행한다. 상세한 내용은 [그룹 변수 확인]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-02 %})을 참고한다.

<br>

# 결과

이번 글에서 `kubespray_defaults` 역할의 변수 시스템을 분석했다.

| 항목 | 내용 |
|------|------|
| `kubespray_defaults` | 변수 로드 전용 역할 |
| 변수 우선순위 | defaults(2) < group_vars(4-6) < vars(15) |
| `defaults/main/` | 커스터마이징 가능한 설정 |
| `vars/main/` | 체크섬, 내부 계산값 |

다음 글에서는 [cluster.yml 플레이북 구조]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-00 %})를 분석한다.

<br>

# 참고 자료

- [Kubespray GitHub - kubespray_defaults](https://github.com/kubernetes-sigs/kubespray/tree/master/roles/kubespray_defaults)
- [Ansible Variable Precedence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
- [이전 글: 그룹 변수 확인]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-02 %})

<br>
