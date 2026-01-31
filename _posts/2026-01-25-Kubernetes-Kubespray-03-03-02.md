---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.3.2. cluster.yml - boilerplate.yml"
excerpt: "Kubespray cluster.yml의 첫 번째 단계인 boilerplate.yml을 분석해보자."
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

이번 글에서는 **cluster.yml의 첫 번째 단계인 `boilerplate.yml`**을 분석한다.

- **ansible_version.yml**: Ansible 버전, Python netaddr, Jinja 버전 검증
- **dynamic_groups**: 구 그룹명 호환성 유지, `k8s_cluster` 그룹 자동 생성
- **validate_inventory**: 인벤토리 설정값 검증 (etcd 홀수, 네트워크 범위 등)

<br>

# 전체 흐름에서의 위치

![kubespray-boilerplate-flowchart]({{site.url}}/assets/images/kubespray-boilerplate-flowchart.png)
<center><sup>boilerplate.yml 상세 흐름</sup></center>

<br>

`boilerplate.yml`은 cluster.yml에서 **가장 먼저 실행**되는 플레이북으로, 본격적인 클러스터 설치 전에 환경 검증과 인벤토리 준비를 수행한다.

```yaml
# cluster.yml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml  # ← 첫 번째 실행
```

<br>

# boilerplate.yml 구조

{% raw %}
```yaml
---
- name: Check ansible version
  import_playbook: ansible_version.yml

- name: Inventory setup and validation
  hosts: all
  gather_facts: false
  tags: always
  roles:
    - dynamic_groups
    - validate_inventory

- name: Install bastion ssh config
  hosts: bastion[0]
  gather_facts: false
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: bastion-ssh-config, tags: ["localhost", "bastion"] }
```
{% endraw %}

| 플레이 | 대상 | 역할 |
|--------|------|------|
| Check ansible version | all (run_once) | Ansible/Python/Jinja 버전 검증 |
| Inventory setup and validation | all | 그룹 매핑, 인벤토리 검증 |
| Install bastion ssh config | bastion[0] | Bastion 호스트 SSH 설정 (선택) |

<br>

# 1. Check ansible version

![kubespray-check-ansible-version]({{site.url}}/assets/images/kubespray-check-ansible-version.jpg)

## ansible_version.yml 분석

{% raw %}
```yaml
---
- name: Check Ansible version
  hosts: all
  gather_facts: false
  become: false
  # 모든 호스트를 대상으로 설정되어 있지만, run_once 덕분에 실제로는 딱 한 번만 실행
  # 버전 체크는 배포 서버에서 한 번만 하면 됨
  run_once: true
  vars:
    minimal_ansible_version: 2.17.3
    maximal_ansible_version: 2.18.0
  # 다른 특정 태그를 지정해서 실행하더라도, 이 버전 체크 과정은 항상 포함
  tags: always
  # 목적: Kubespray 소스 코드와 Ansible 버전 간의 호환성 보장
  tasks:
    # Ansible 버전 체크: 2.17.3 <= version < 2.18.0
    - name: "Check {{ minimal_ansible_version }} <= Ansible version < {{ maximal_ansible_version }}"
      assert:
        msg: "Ansible must be between {{ minimal_ansible_version }} and {{ maximal_ansible_version }} exclusive"
        that:
          - ansible_version.string is version(minimal_ansible_version, ">=")
          - ansible_version.string is version(maximal_ansible_version, "<")
      tags: check

    # Python netaddr 라이브러리 설치 확인 (pip3 list | grep netaddr로도 확인 가능)
    # ipaddr 필터로 127.0.0.1을 처리해보고, 에러 발생 시 미설치로 판단
    - name: "Check that python netaddr is installed"
      assert:
        msg: "Python netaddr is not present"
        that: "'127.0.0.1' | ansible.utils.ipaddr"
      tags: check

    # Jinja2 템플릿 엔진 버전 확인
    # 최신 Jinja2 문법({% set ... %})을 실행해보고 정상 작동 여부 확인
    - name: "Check that jinja is not too old (install via pip)"
      assert:
        msg: "Your Jinja version is too old, install via pip"
        that: "{% set test %}It works{% endset %}{{ test == 'It works' }}"
      tags: check
```
{% endraw %}

## 주요 설정 분석

| 설정 | 값 | 설명 |
|------|-----|------|
| `hosts` | `all` | 모든 호스트 대상 |
| `gather_facts` | `false` | 시스템 정보 수집 안 함 (버전 체크에 불필요) |
| `run_once` | `true` | 한 번만 실행 (버전 체크는 배포 서버에서 한 번이면 충분) |
| `tags` | `always` | `--tags` 옵션과 관계없이 항상 실행 |

## vars 분석

```yaml
vars:
  minimal_ansible_version: 2.17.3
  maximal_ansible_version: 2.18.0
```

**play vars**로 정의된 변수다. 이 플레이 내에서만 유효하며, Kubespray가 지원하는 Ansible 버전 범위를 명시한다.

## assert 모듈

`assert`는 조건이 만족하지 않으면 **플레이북을 중단**시키는 모듈이다:

```yaml
- name: "Check Ansible version"
  assert:
    msg: "에러 메시지"  # 실패 시 출력할 메시지
    that:               # 검증할 조건 목록 (모두 true여야 통과)
      - 조건1
      - 조건2
```

### 검증 항목

| 검증 | 조건 | 목적 |
|------|------|------|
| Ansible 버전 | `2.17.3 <= version < 2.18.0` | 호환되는 Ansible 버전만 허용 |
| Python netaddr | `ipaddr` 필터 동작 여부 | IP 주소 처리에 필요한 라이브러리 |
| Jinja 버전 | {% raw %}`{% set %}`{% endraw %} 문법 동작 여부 | 템플릿 렌더링에 필요 |

<br>

# 2. Inventory setup and validation

## 플레이 구조

```yaml
- name: Inventory setup and validation
  hosts: all
  gather_facts: false
  tags: always
  roles:
    - dynamic_groups
    - validate_inventory
```

두 개의 롤이 순차적으로 실행된다.

<br>

## dynamic_groups 롤

![kubespray-dynamic-groups]({{site.url}}/assets/images/kubespray-dynamic-groups.jpg)

### 역할

**구 그룹명 호환성 유지**와 **k8s_cluster 그룹 자동 생성**을 담당한다.

| 기능 | 설명 |
|------|------|
| **이름 표준화** | 사용자가 하이픈(`kube-master`)을 쓰든 언더바(`kube_control_plane`)를 쓰든, 내부적으로 표준화된 이름 사용 |
| **자동 재분류** | 과거 방식 이름으로 그룹을 만들어도 최신 이름으로 서버들을 자동 재분류 |
| **계층적 구조 형성** | 워커/마스터 노드만 정의해도 `k8s_cluster`라는 통합 그룹 자동 생성 |

### 코드 분석

{% raw %}
```yaml
---
- name: Match needed groups by their old names or definition
  vars:
    # "A라는 이름은 B라는 이름을 포함한다"는 매핑 규칙 정의
    group_mappings:
      kube_control_plane:        # 과거 이름인 kube-master를 포함
        - kube-master
      kube_node:                 # 과거 이름인 kube-node를 포함
        - kube-node
      calico_rr:
        - calico-rr
      no_floating:
        - no-floating
      k8s_cluster:               # kube_node, kube_control_plane, calico_rr를 하나로 묶음
        - kube_node
        - kube_control_plane
        - calico_rr
  # 실행 중에(In-memory) 새로운 Ansible 그룹 생성
  # 조건에 맞는 서버들을 key 값으로 명명된 그룹에 실시간 할당
  group_by:
    key: "{{ item.key }}"
  # 겹치는 이름이 하나라도 있다면 group_by 실행
  when: group_names | intersect(item.value) | length > 0
  loop: "{{ group_mappings | dict2items }}"
```
{% endraw %}

### 동작 원리

| 요소 | 설명 |
|------|------|
| `group_mappings` | 신규 그룹명과 구 그룹명/하위 그룹의 매핑 규칙 |
| `group_by` | 호스트를 지정한 그룹에 동적으로 추가 (In-memory) |
| `when` | 호스트의 그룹과 매핑 값이 겹칠 때만 실행 |
| `loop` | `group_mappings` 딕셔너리를 순회 |

### 실제 동작 예시

인벤토리에 `kube_node`와 `kube_control_plane` 그룹이 정의되어 있으면:

```
k8s-w1이 kube_node에 속함
  → k8s_cluster 매핑의 value에 kube_node가 있음
  → group_names | intersect(['kube_node', ...]) | length > 0 → true
  → k8s-w1을 k8s_cluster 그룹에 추가
```

결과적으로 **k8s_cluster 그룹이 자동으로 생성**되어, 이후 작업에서 "모든 클러스터 노드"를 한 번에 지칭할 수 있다.

<br>

## validate_inventory 롤

![kubespray-validate-inventory]({{site.url}}/assets/images/kubespray-validate-inventory.jpg)

### 역할

인벤토리와 변수 설정의 **유효성을 검증**한다. 클러스터 구성 전에 잘못된 설정을 사전에 차단한다.

### 주요 검증 항목

{% raw %}
```yaml
---
# 그룹 검증
- name: Stop if kube_control_plane group is empty
  assert:
    that: groups.get('kube_control_plane')

- name: Stop if etcd group is empty in external etcd mode
  assert:
    that: groups.get('etcd') or etcd_deployment_type == 'kubeadm'

- name: Stop if even number of etcd hosts
  assert:
    that: groups.get('etcd', groups.kube_control_plane) | length is not divisibleby 2

# 네트워크 검증
- name: Guarantee that enough network address space is available for all pods
  assert:
    that: "{{ (kubelet_max_pods | default(110)) | int <= (2 ** (32 - kube_network_node_prefix | int)) - 2 }}"

- name: Check that kube_pods_subnet does not collide with kube_service_addresses
  assert:
    that:
      - kube_pods_subnet | ansible.utils.ipaddr(kube_service_addresses) | string == 'None'

# 옵션 검증
- name: Stop if unsupported options selected
  assert:
    that:
      - kube_network_plugin in ['calico', 'flannel', 'cloud', 'cilium', ...]
      - dns_mode in ['coredns', 'coredns_dual', 'manual', 'none']
      - kube_proxy_mode in ['iptables', 'ipvs', 'nftables']
      - container_manager in ['docker', 'crio', 'containerd']
```
{% endraw %}

### 검증 항목 정리

| 카테고리 | 검증 항목 | 설명 |
|----------|----------|------|
| **그룹** | `kube_control_plane` 비어있음 | 컨트롤플레인 노드 필수 |
| **그룹** | etcd 호스트 수가 짝수 | 홀수여야 quorum 형성 가능 |
| **네트워크** | Pod/Service 서브넷 충돌 | `kube_pods_subnet`과 `kube_service_addresses` 중복 불가 |
| **네트워크** | `kubelet_max_pods` 초과 | 노드당 Pod 수가 할당된 네트워크 범위 초과 |
| **네트워크** | 전체 IP 대역 부족 | 클러스터 노드 수 대비 IP 범위 검증 |
| **호환성** | K8s 버전 | Kubespray 릴리스에서 지원하는 최소 버전 이상인지 |
| **호환성** | 컨테이너 매니저 조합 | Docker/Containerd/CRI-O와 Kata/gVisor 조합 유효성 |
| **변수** | Boolean 타입 | Boolean 값이 문자열로 잘못 설정되지 않았는지 |
| **변수** | 상호 의존성 | RBAC/Cloud Provider/Dashboard 등 설정 짝 검증 |

> **참고**: 이러한 사전 검증 덕분에 클러스터 설치 중간에 실패하는 것을 방지할 수 있다. 설정 오류는 설치 시작 전에 발견하는 것이 좋다.

### 검증 공식 분해

**etcd 홀수 검증:**

```
groups.get('etcd', groups.kube_control_plane) | length is not divisibleby 2
```

etcd는 Raft 합의 알고리즘을 사용하며, **과반수(quorum)**가 동의해야 데이터를 쓸 수 있다.

| 노드 수 | quorum | 허용 장애 수 | 비고 |
|---------|--------|-------------|------|
| 2 | 2 | 0 | 1대만 죽어도 쓰기 불가 |
| 3 | 2 | 1 | 1대 장애 허용 |
| 4 | 3 | 1 | 3대와 동일한 장애 허용 (비효율) |
| 5 | 3 | 2 | 2대 장애 허용 |

짝수는 홀수 대비 장애 허용 수가 동일하면서 비용만 증가하므로 비효율적이다.

**네트워크 주소 공간 검증:**

{% raw %}
```
(kubelet_max_pods | default(110)) | int <= (2 ** (32 - kube_network_node_prefix | int)) - 2
```
{% endraw %}

각 노드는 `kube_network_node_prefix` 크기의 서브넷을 할당받는다.

| 요소 | 의미 |
|------|------|
| `kube_network_node_prefix` | 노드별 서브넷 크기 (예: `/24`) |
| `32 - prefix` | 호스트 비트 수 (예: `32 - 24 = 8`) |
| `2 ** (32 - prefix)` | 총 IP 수 (예: `2^8 = 256`) |
| `- 2` | 네트워크/브로드캐스트 주소 제외 |
| `kubelet_max_pods` | 노드당 최대 Pod 수 (기본 110) |

예시 (`/24` 서브넷):
```
사용 가능 IP = 2^(32-24) - 2 = 254개
kubelet_max_pods = 110
110 <= 254 → 검증 통과
```

<br>

# 3. Install bastion ssh config

## 플레이 구조

{% raw %}
```yaml
- name: Install bastion ssh config
  hosts: bastion[0]
  gather_facts: false
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults }
    - { role: bastion-ssh-config, tags: ["localhost", "bastion"] }
```
{% endraw %}

## 역할

**Bastion 호스트**를 통해 프라이빗 네트워크의 노드에 접근해야 할 때 SSH 설정을 자동으로 구성한다.

| 설정 | 값 | 설명 |
|------|-----|------|
| `hosts` | `bastion[0]` | bastion 그룹의 첫 번째 호스트 |
| `environment` | `proxy_disable_env` | 프록시 비활성화 |

## bastion-ssh-config 롤

{% raw %}
```yaml
---
- name: Set bastion host IP and port
  set_fact:
    bastion_ip: "{{ hostvars[groups['bastion'][0]]['ansible_host'] }}"
    bastion_port: "{{ hostvars[groups['bastion'][0]]['ansible_port'] | d(22) }}"
  delegate_to: localhost

- name: Create ssh bastion conf
  become: false
  delegate_to: localhost
  template:
    src: "{{ ssh_bastion_confing__name }}.j2"
    dest: "{{ playbook_dir }}/{{ ssh_bastion_confing__name }}"
```
{% endraw %}

Bastion 호스트의 IP와 포트를 가져와 SSH 설정 파일을 생성한다.

> **참고**: bastion 그룹이 인벤토리에 정의되어 있지 않으면 이 플레이는 **스킵**된다.

<br>

# 실행 로그 분석

실제 `ansible-playbook cluster.yml` 실행 시 boilerplate.yml 부분의 로그를 분석한다.

## Check Ansible version

```
PLAY [Check Ansible version] ***************************************************

TASK [Check 2.17.3 <= Ansible version < 2.18.0] ********************************
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [Check that python netaddr is installed] **********************************
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [Check that jinja is not too old (install via pip)] ***********************
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}
```

- 모든 검증이 `ok`로 통과
- `changed: false` - 시스템 상태를 변경하지 않음 (검증만 수행)

## Inventory setup and validation

```
PLAY [Inventory setup and validation] ******************************************

TASK [dynamic_groups : Match needed groups by their old names or definition] ***
changed: [k8s-ctr] => (item={'key': 'k8s_cluster', 'value': ['kube_node', 'kube_control_plane', 'calico_rr']})
```

- `k8s_cluster` 그룹이 **동적으로 생성**됨
- `changed: true` - 호스트가 새 그룹에 추가됨

```
TASK [validate_inventory : Stop if kube_control_plane group is empty] **********
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [validate_inventory : Stop if even number of etcd hosts] ******************
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}

TASK [validate_inventory : Guarantee that enough network address space is available for all pods] ***
ok: [k8s-ctr] => {
    "changed": false,
    "msg": "All assertions passed"
}
```

- 인벤토리 검증 항목들이 모두 통과
- etcd 홀수 검증, 네트워크 범위 검증 등

## Install bastion ssh config

```
PLAY [Install bastion ssh config] **********************************************
skipping: no hosts matched
```

- `bastion` 그룹이 인벤토리에 없으므로 **스킵**
- 일반적인 단일 노드/프라이빗 네트워크 없는 환경에서는 정상

<br>

# 결과

`boilerplate.yml`의 역할을 정리하면 다음과 같다:

| 단계 | 플레이 | 역할 |
|------|--------|------|
| 1 | Check ansible version | 실행 환경 검증 (Ansible, Python, Jinja) |
| 2 | Inventory setup | 그룹 호환성 유지, k8s_cluster 자동 생성 |
| 3 | Inventory validation | 설정 오류 사전 차단 |
| 4 | Bastion ssh config | (선택) Bastion 호스트 SSH 설정 |

`boilerplate.yml`은 클러스터 설치의 **사전 준비 단계**로, 잘못된 환경이나 설정을 미리 걸러내어 설치 중 실패를 방지한다.

다음 글에서는 OS 부트스트랩과 fact 수집을 담당하는 [internal_facts.yml]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-03 %})을 분석한다.

<br>

# 참고 자료

- [Ansible assert 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/assert_module.html)
- [Ansible group_by 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/group_by_module.html)
- [이전 글: 태스크 구조]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-01 %})

<br>
