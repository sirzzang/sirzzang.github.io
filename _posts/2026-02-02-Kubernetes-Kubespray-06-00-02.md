---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 6.0.2. 노드 관리 - remove-node.yml"
excerpt: "Kubespray의 노드 제거 플레이북 remove-node.yml의 전체 흐름과 구조를 분석해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - remove-node.yml
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray의 노드 제거 플레이북 `remove-node.yml`**의 전체 흐름을 분석한다.

- **목적**: 특정 노드를 안전하게 클러스터에서 제거
- **플레이 구성**: 검증 → 확인 → 팩트 수집 → 노드 초기화(drain/etcd/reset) → 클러스터에서 삭제
- **핵심 특징**: Graceful 제거 (Drain → etcd 제거 → Reset → Delete)
- **안전 장치**: 노드 지정 검증, 사용자 확인 프롬프트

<br>

# remove-node.yml 전체 흐름

`remove-node.yml`은 Kubespray의 노드 제거 플레이북으로, **특정 노드를 안전하게 클러스터에서 제거**한다.

![kubespray-remove-node-flowchart]({{site.url}}/assets/images/kubespray-remove-node-flowchart.png)
<center><sup>remove-node.yml 플레이북 실행 흐름</sup></center>

<br>

```
1. 노드 지정 검증 (assert)
   ↓
2. 공통 작업 (boilerplate.yml)
   ↓
3. 사용자 확인 (pause)
   ↓
4. 팩트 수집 (internal_facts.yml)
   ↓
5. 노드 초기화
   ├── pre_remove (drain, cordon)
   ├── remove-etcd-node (etcd 멤버인 경우)
   └── reset (kubeadm reset)
   ↓
6. 클러스터에서 삭제 (kubectl delete node)
```

## 단계별 그룹핑

위 흐름을 목적별로 그룹핑하면 다음과 같다:

| 단계 | 목적 | 플레이/태스크 |
|------|------|---------------|
| **사전 검증** | 노드 명시적 지정 확인 | assert |
| **공통 설정** | 변수, 핸들러 로딩 | boilerplate |
| **사용자 확인** | 실수 방지 | pause + fail |
| **정보 수집** | 노드 상태 파악 | internal_facts |
| **Graceful 제거** | Pod 이동, 스케줄링 중지 | pre_remove (drain, cordon) |
| **etcd 제거** | etcd 클러스터 정합성 유지 | remove-etcd-node |
| **노드 초기화** | kubeadm reset, 파일 삭제 | reset |
| **메타데이터 삭제** | K8s 리소스 정리 | post-remove (kubectl delete node) |

<br>

# 플레이북 구조

## 전체 코드

<details markdown="1">
<summary>remove-node.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
---
- name: Validate nodes for removal
  hosts: localhost
  gather_facts: false
  become: false
  tasks:
    - name: Assert that nodes are specified for removal
      assert:
        that:
          - node is defined
          - node | length > 0
        msg: "No nodes specified for removal. The `node` variable must be set explicitly."

- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Confirm node removal
  hosts: "{{ node | default('this_is_unreachable') }}"
  gather_facts: false
  tasks:
    - name: Confirm Execution
      pause:
        prompt: "Are you sure you want to delete nodes state? Type 'yes' to delete nodes."
      register: pause_result
      run_once: true
      when:
        - not (skip_confirmation | default(false) | bool)

    - name: Fail if user does not confirm deletion
      fail:
        msg: "Delete nodes confirmation failed"
      when: pause_result.user_input | default('yes') != 'yes'

- name: Gather facts
  import_playbook: internal_facts.yml
  when: reset_nodes | default(True) | bool

- name: Reset node
  hosts: "{{ node | default('this_is_unreachable') }}"
  gather_facts: false
  environment: "{{ proxy_disable_env }}"
  pre_tasks:
    - name: Gather information about installed services
      service_facts:
      when: reset_nodes | default(True) | bool
  roles:
    - { role: kubespray_defaults, when: reset_nodes | default(True) | bool }
    - { role: remove_node/pre_remove, tags: pre-remove }
    - role: remove-node/remove-etcd-node
      when: "'etcd' in group_names"
    - { role: reset, tags: reset, when: reset_nodes | default(True) | bool }

# Currently cannot remove first control plane node or first etcd node
- name: Post node removal
  hosts: "{{ node | default('this_is_unreachable') }}"
  gather_facts: false
  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults, when: reset_nodes | default(True) | bool }
    - { role: remove-node/post-remove, tags: post-remove }
```
{% endraw %}

</details>

<br>

## 플레이별 역할

| 순서 | 플레이 | 대상 호스트 | 주요 역할 |
|------|--------|-------------|-----------|
| 1 | Validate nodes | `localhost` | 노드 지정 검증 |
| 2 | Common tasks | - | 공통 설정, 변수 검증 |
| 3 | Confirm removal | `{{ node }}` | 사용자 확인 |
| 4 | Gather facts | - | 시스템 정보 수집 |
| 5 | Reset node | `{{ node }}` | drain, etcd 제거, kubeadm reset |
| 6 | Post removal | `{{ node }}` | kubectl delete node |

<br>

# reset_nodes 변수

`remove-node.yml`에서 가장 중요한 변수 중 하나인 `reset_nodes`는 **노드 자체를 초기화할 것인지** 결정한다.

| 값 | 의미 | 수행 작업 |
|----|------|----------|
| `true` (기본값) | 노드 초기화 O | `reset` 롤 실행 |
| `false` | 노드 초기화 X | 클러스터에서만 제거 (drain → delete node) |

이 변수에 따라 팩트 수집, 서비스 정보 수집, reset 롤 실행 여부가 결정된다. 자세한 사용 사례는 [실행 방법 - 노드 초기화 없이 클러스터에서만 제거](#노드-초기화-없이-클러스터에서만-제거) 섹션을 참고한다.

<br>

# 단계별 분석

## 1. 노드 지정 검증

제거할 노드를 지정했는지 검증한다.

```yaml
- name: Validate nodes for removal
  hosts: localhost
  gather_facts: false
  become: false
  tasks:
    - name: Assert that nodes are specified for removal
      assert:
        that:
          - node is defined
          - node | length > 0
        msg: "No nodes specified for removal. The `node` variable must be set explicitly."
```

| 요소 | 설명 |
|------|------|
| `hosts: localhost` | 로컬에서 검증 실행 |
| `become: false` | root 권한 불필요 |
| `assert` | `that` 조건이 모두 참이어야 통과, 하나라도 거짓이면 `msg`와 함께 즉시 실패 |
| `node is defined` | `node` 변수가 정의되어 있는지 확인 |
| `node \| length > 0` | `node` 변수가 빈 문자열이 아닌지 확인 |

**안전 장치**: `node` 변수가 정의되지 않았거나 빈 값이면 플레이북이 즉시 실패한다.

```bash
# 올바른 실행
ansible-playbook remove-node.yml -e node=k8s-node5

# 실패하는 실행
ansible-playbook remove-node.yml  # assert 실패
```

## 2. 공통 작업 (boilerplate)

```yaml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml
```

모든 Kubespray 플레이북의 공통 시작점으로, 변수와 핸들러를 로딩한다.

## 3. 사용자 확인

노드 제거는 클러스터에 영향을 주는 중요한 작업이므로, 실수 방지를 위해 사용자 확인을 받는다.

{% raw %}
```yaml
- name: Confirm node removal
  hosts: "{{ node | default('this_is_unreachable') }}"
  tasks:
    - name: Confirm Execution
      pause:
        prompt: "Are you sure you want to delete nodes state? Type 'yes' to delete nodes."
      register: pause_result
      run_once: true
      when:
        - not (skip_confirmation | default(false) | bool)

    - name: Fail if user does not confirm deletion
      fail:
        msg: "Delete nodes confirmation failed"
      when: pause_result.user_input | default('yes') != 'yes'
```
{% endraw %}

| 요소 | 설명 |
|------|------|
| `pause` | 사용자 입력 대기 |
| `run_once: true` | 여러 노드 지정해도 한 번만 확인. 확인 대상은 "삭제 의도"이지 "각 노드별 삭제"가 아니므로, 반복 확인은 불필요 |
| `skip_confirmation` | `true`로 설정 시 확인 건너뛰기 |

### 동적 호스트 지정

{% raw %}
```yaml
hosts: "{{ node | default('this_is_unreachable') }}"
```
{% endraw %}

| 요소 | 설명 |
|------|------|
| `{{ node }}` | 사용자가 `-e node=<노드명>`으로 지정 |
| `default('this_is_unreachable')` | 미지정 시 존재하지 않는 호스트로 설정 |

**Fail-safe**: `node` 변수가 정의되지 않으면 `this_is_unreachable`이라는 존재하지 않는 호스트를 대상으로 하여 아무 작업도 수행하지 않는다.

### 자동화 지원

```bash
# 인터랙티브 실행 (프롬프트 표시)
ansible-playbook remove-node.yml -e node=k8s-node5

# 자동화 실행 (프롬프트 건너뛰기)
ansible-playbook remove-node.yml -e node=k8s-node5 -e skip_confirmation=true
```

## 4. 팩트 수집

`reset_nodes=true`일 때만 팩트를 수집한다.

```yaml
- name: Gather facts
  import_playbook: internal_facts.yml
  when: reset_nodes | default(True) | bool
```

**왜 `reset_nodes=true`일 때만 필요한가?**: `reset` 롤에서 kubeadm reset, 서비스 중지, CNI 플러그인 삭제 등을 수행하려면 노드에 어떤 컴포넌트가 설치되어 있는지 알아야 한다. 반면 `reset_nodes=false`일 때는 drain과 delete node가 Control Plane에서 kubectl로 실행되므로, 노드의 상세 시스템 정보가 필요 없다.


## 5. 노드 초기화 (Reset node)

{% raw %}
```yaml
- name: Reset node
  hosts: "{{ node | default('this_is_unreachable') }}"
  pre_tasks:
    - name: Gather information about installed services
      service_facts:
      when: reset_nodes | default(True) | bool
  roles:
    - { role: kubespray_defaults, when: reset_nodes | default(True) | bool }
    - { role: remove_node/pre_remove, tags: pre-remove }
    - role: remove-node/remove-etcd-node
      when: "'etcd' in group_names"
    - { role: reset, tags: reset, when: reset_nodes | default(True) | bool }
```
{% endraw %}

### pre_tasks

`pre_tasks`는 Ansible 플레이북에서 **roles가 실행되기 전에 먼저 수행되는 태스크**다. 여기서는 `service_facts` 모듈을 사용해 노드에 설치된 서비스 정보를 수집한다.

```yaml
pre_tasks:
  - name: Gather information about installed services
    service_facts:
    when: reset_nodes | default(True) | bool
```

| 요소 | 설명 |
|------|------|
| `pre_tasks` | roles 실행 전 먼저 수행되는 태스크 블록 |
| `service_facts` | 시스템에 설치된 서비스 목록과 상태 수집 |
| `when: reset_nodes` | 노드 초기화 시에만 실행 |

서비스 정보는 이후 `reset` 롤에서 kubelet, containerd 등의 서비스를 중지하고 삭제할 때, 해당 서비스가 실제로 설치되어 있는지 확인하기 위해 필요하다.

> `pre_tasks`에 대한 자세한 설명은 [Ansible 플레이북 특수 섹션]({% post_url 2026-01-12-Kubernetes-Ansible-11 %})을 참고한다.

### 5.1 pre_remove 롤

노드 제거 전 **워크로드를 안전하게 이동**시킨다.

```yaml
# roles/remove_node/pre_remove/defaults/main.yml
allow_ungraceful_removal: false
drain_grace_period: 300
drain_timeout: 360s
drain_retries: 3
drain_retry_delay_seconds: 10
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `allow_ungraceful_removal` | `false` | drain 실패 시 강제 제거 허용 여부 |
| `drain_grace_period` | `300` | Pod 종료 유예 시간 (초) |
| `drain_timeout` | `360s` | drain 타임아웃 |
| `drain_retries` | `3` | drain 재시도 횟수 |
| `drain_retry_delay_seconds` | `10` | 재시도 간격 (초) |

**주요 태스크:**
1. **kubectl drain**: DaemonSet 제외하고 모든 Pod 축출
2. **kubectl cordon**: 새 Pod 스케줄링 방지
3. **kubelet 중지**: 노드의 kubelet 서비스 중지

### 5.2 remove-etcd-node 롤 (조건부)

{% raw %}
```yaml
- role: remove-node/remove-etcd-node
  when: "'etcd' in group_names"
```
{% endraw %}

| 조건 | 설명 |
|------|------|
| `'etcd' in group_names` | 해당 노드가 `etcd` 그룹에 속해 있는 경우에만 실행 |

**etcd 클러스터에서 멤버를 안전하게 제거**한다. Worker 노드 제거 시에는 이 롤이 실행되지 않는다.

### 5.3 reset 롤

`kubeadm reset`을 수행하고 노드의 K8s 관련 파일을 정리한다.

## 6. 클러스터에서 삭제 (Post removal)

{% raw %}
```yaml
- name: Post node removal
  hosts: "{{ node | default('this_is_unreachable') }}"
  roles:
    - { role: kubespray_defaults, when: reset_nodes | default(True) | bool }
    - { role: remove-node/post-remove, tags: post-remove }
```
{% endraw %}

### post-remove 롤

**Kubernetes 클러스터에서 노드 메타데이터를 삭제**한다.

{% raw %}
```yaml
- name: Remove-node | Delete node
  command: "{{ kubectl }} delete node {{ kube_override_hostname | default(inventory_hostname) }}"
  delegate_to: "{{ groups['kube_control_plane'] | first }}"
  retries: "{{ delete_node_retries }}"
  delay: "{{ delete_node_delay_seconds }}"
  register: result
  until: result is not failed
```
{% endraw %}

| 요소 | 설명 |
|------|------|
| `kubectl delete node` | K8s API에서 노드 리소스 삭제 |
| `delegate_to` | Control Plane에서 실행 |
| `retries` / `until` | 실패 시 재시도 |

<br>

# 제한사항

플레이북 주석에 명시된 제한사항을 확인한다. **첫 번째 Control Plane 노드와 첫 번째 etcd 노드는 이 플레이북으로 제거할 수 없다.**

```yaml
# Currently cannot remove first control plane node or first etcd node
```

| 제거 불가 노드 | 이유 |
|---------------|------|
| 첫 번째 Control Plane | 클러스터 초기화 시 기준 노드 |
| 첫 번째 etcd 노드 | etcd 클러스터의 리더 역할 가능 |

## 첫 번째 Control Plane 노드
- Kubespray에서 클러스터 초기화 시 첫 번째 Control Plane이 `kubeadm init`을 실행하는 기준 노드
- Kubespray의 많은 태스크들이 `groups['kube_control_plane'] | first`로 첫 번째 Control Plane에서 실행됨 (kubectl 명령, 인증서 생성 등)
- 이 노드가 없어지면 Kubespray가 의존하는 많은 작업들이 실패

## 첫 번째 etcd 노드
- etcd 클러스터 구성 시 첫 번째 노드가 초기 클러스터를 생성
- etcd는 Raft 합의 알고리즘을 사용하므로, 리더 노드를 갑자기 제거하면 클러스터 안정성에 문제
- Kubespray가 etcd 관련 작업 시 첫 번째 노드를 참조

이 노드들을 제거하려면 **수동 작업**이 필요하다.

<br>

# 안전한 제거를 위한 설계

`remove-node.yml`의 주요 설계 특징은 다음과 같다. 이러한 특징들이 노드를 "우아하게" 제거한다는 느낌을 준다:

## 1. 엄격한 검증

```yaml
- name: Assert that nodes are specified for removal
  assert:
    that:
      - node is defined
      - node | length > 0
    msg: "No nodes specified for removal. The `node` variable must be set explicitly."
```

- **명시적 노드 지정 강제**: `-e node=<노드명>` 없이는 실행 불가
- **실수 방지**: 전체 클러스터에 대한 의도치 않은 실행 차단

## 2. 사용자 확인

```yaml
- name: Confirm Execution
  pause:
    prompt: "Are you sure you want to delete nodes state? Type 'yes' to delete nodes."
```

- **인터랙티브 확인**: "yes" 입력 필수
- **자동화 지원**: `-e skip_confirmation=true`로 CI/CD에서 사용 가능

## 3. 안전한 제거 순서

```
1. Drain (Pod 이동)
   ↓
2. Cordon (스케줄링 중지)
   ↓
3. etcd 멤버 제거 (해당 시)
   ↓
4. kubeadm reset
   ↓
5. kubectl delete node
```

- **Graceful Shutdown**: Pod들이 다른 노드로 안전하게 이동
- **PDB 준수**: PodDisruptionBudget 정책을 존중
- **etcd 정합성**: etcd 멤버 제거 후 노드 초기화

> Kubespray를 사용하지 않더라도, 노드를 수동으로 제거할 때 이 순서를 참고하면 좋다.

## 4. 재시도 로직

```yaml
drain_retries: 3
drain_retry_delay_seconds: 10
```

- **일시적 실패 대응**: drain 실패 시 자동 재시도
- **타임아웃 설정**: 무한 대기 방지

## 5. 조건부 실행

```yaml
- { role: reset, tags: reset, when: reset_nodes | default(True) | bool }
```

- **선택적 초기화**: `reset_nodes: false`로 노드 초기화 건너뛰기 가능
- **etcd 조건부**: etcd 멤버인 경우에만 etcd 제거 실행

<br>

# reset_nodes=false 사용 사례

[앞서 설명한 `reset_nodes` 변수](#reset_nodes-변수)의 기본값은 `true`다. 따라서 **명시적으로 `-e reset_nodes=false`를 지정하지 않으면 항상 노드 초기화가 수행**된다. 그렇다면 언제 굳이 `false`로 지정할까?

## 왜 reset_nodes=false를 사용하는가?

다음과 같은 상황에서는 `reset_nodes=false`가 유용하다:

| 상황 | 설명 |
|------|------|
| **노드 접근 불가** | 노드가 다운되었거나 네트워크 단절로 SSH 접속이 불가능한 경우. `kubeadm reset`을 실행할 수 없으므로 클러스터 메타데이터만 정리 |
| **노드 폐기** | 노드를 재사용하지 않고 폐기할 예정인 경우. 초기화 작업이 불필요 |
| **물리적 제거 후 정리** | 노드가 이미 물리적으로 제거된 후, 클러스터에 남아있는 메타데이터만 삭제 |
| **빠른 제거 필요** | 긴급 상황에서 `kubeadm reset` 없이 빠르게 클러스터에서 제거해야 하는 경우 |

## reset_nodes=false일 때 수행되는 작업

`reset_nodes=false`로 설정하면 일부 작업이 스킵된다:

| 작업 | reset_nodes=true | reset_nodes=false |
|------|------------------|-------------------|
| 노드 지정 검증 (assert) | O | O |
| 공통 작업 (boilerplate) | O | O |
| 사용자 확인 (pause) | O | O |
| 팩트 수집 (internal_facts) | O | **X** |
| 서비스 정보 수집 (service_facts) | O | **X** |
| **pre_remove** (drain, cordon) | O | O |
| **remove-etcd-node** (etcd 멤버인 경우) | O | O |
| **reset** (kubeadm reset) | O | **X** |
| **post-remove** (kubectl delete node) | O | O |

**핵심 차이**: `reset_nodes=false`는 노드 자체를 초기화하지 않고, **클러스터 관점에서의 제거만 수행**한다.

```
reset_nodes=true:   drain → etcd 제거 → kubeadm reset → kubectl delete node
reset_nodes=false:  drain → etcd 제거 →      (X)      → kubectl delete node
```

## 주의사항

`reset_nodes=false`로 제거한 노드를 나중에 다시 클러스터에 추가하려면, **수동으로 `kubeadm reset`을 실행**해야 한다. 노드에 남아있는 K8s 관련 파일과 설정이 충돌을 일으킬 수 있기 때문이다.

```bash
# 노드에서 수동으로 실행
kubeadm reset -f
rm -rf /etc/cni/net.d
rm -rf ~/.kube
```

<br>

# 실행 방법

## 기본 실행

```bash
ansible-playbook -i inventory/mycluster/inventory.ini remove-node.yml -e node=k8s-node5
```

## 여러 노드 제거

```bash
ansible-playbook remove-node.yml -e "node=k8s-node5,k8s-node6"
```

## 자동화 (확인 건너뛰기)

```bash
ansible-playbook remove-node.yml -e node=k8s-node5 -e skip_confirmation=true
```

## 노드 초기화 없이 클러스터에서만 제거

```bash
ansible-playbook remove-node.yml -e node=k8s-node5 -e reset_nodes=false
```


<br>

# 정리

이번 글에서 `remove-node.yml`의 전체 흐름을 파악했다. 핵심은 **엄격한 검증과 Graceful한 제거 과정**이다.


## 주요 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `node` | (필수) | 제거할 노드 이름 |
| `skip_confirmation` | `false` | 확인 프롬프트 건너뛰기 |
| `reset_nodes` | `true` | 노드 초기화 수행 여부 |
| `allow_ungraceful_removal` | `false` | drain 실패 시 강제 제거 |
| `drain_timeout` | `360s` | drain 타임아웃 |
| `drain_retries` | `3` | drain 재시도 횟수 |

## scale.yml과의 비교

`scale.yml`이 노드를 추가한다면, `remove-node.yml`은 노드를 제거한다.

| 항목 | scale.yml | remove-node.yml |
|------|-----------|-----------------|
| **목적** | 기존 클러스터에 노드 추가 | 기존 클러스터에서 노드 제거 |
| **주요 대상** | `kube_node` | `-e node=<노드명>` |
| **etcd 영향** | etcd 클러스터 변경 안 함 | etcd 멤버 제거 (해당 시) |
| **kubeadm 명령** | `kubeadm join` | `kubeadm reset` |
| **사용자 확인** | 없음 | `pause` 프롬프트 |

## Kubespray와 kubeadm

`remove-node.yml` 분석에서도 확인할 수 있듯이, **Kubespray는 결국 kubeadm을 사용**한다.

| Kubespray가 하는 일 | 실제 동작 |
|---------------------|-----------|
| 노드 초기화 | `kubeadm reset` |
| 노드 조인 | `kubeadm join` |
| 클러스터 초기화 | `kubeadm init` |

## 주요 특징

| 특징 | 설명 |
|------|------|
| **명시적 노드 지정** | `-e node=<노드명>` 필수 |
| **사용자 확인** | "yes" 입력 또는 `skip_confirmation` |
| **Graceful 제거** | drain → etcd 제거 → reset → delete |
| **재시도 로직** | drain/delete 실패 시 자동 재시도 |
| **조건부 실행** | etcd 멤버, reset_nodes 등 조건에 따라 선택적 실행 |

<br>

# 참고 자료

- [Kubespray GitHub - remove-node.yml](https://github.com/kubernetes-sigs/kubespray/blob/master/remove-node.yml)
- [Kubespray - Adding/removing a node](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/nodes.md)

<br>
