---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 6.0.3. 노드 관리 - reset.yml"
excerpt: "Kubespray의 클러스터 초기화 플레이북 reset.yml의 전체 흐름과 구조를 분석해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - reset.yml
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray의 클러스터 초기화 플레이북 `reset.yml`**의 전체 흐름을 분석한다.

- **목적**: Kubernetes 클러스터 전체를 설치 전 상태로 완전 제거
- **플레이 구성**: 공통 작업 → 팩트 수집 → 사용자 확인 → 전체 노드 초기화
- **대상**: etcd, Control Plane, Worker, Calico RR 모든 노드
- **경고**: etcd 데이터 포함 완전 삭제, **복구 불가**

<br>

# reset.yml 전체 흐름

`reset.yml`은 Kubespray의 클러스터 초기화 플레이북으로, **전체 클러스터를 설치 전 상태로 되돌린다**.

![kubespray-reset-flowchart]({{site.url}}/assets/images/kubespray-reset-flowchart.png)
<center><sup>reset.yml 플레이북 실행 흐름</sup></center>

<br>

```
1. 공통 작업 (boilerplate.yml)
   ↓
2. 팩트 수집 (internal_facts.yml)
   ↓
3. 사용자 확인 (pause - "yes" 입력)
   ↓
4. 서비스 정보 수집 (service_facts)
   ↓
5. DNS 설정 복원 (preinstall - dns_early)
   ↓
6. 클러스터 초기화 (reset)
   ├── kubeadm reset
   ├── 컨테이너/이미지 삭제
   ├── 바이너리 삭제
   ├── 설정 파일 삭제
   └── etcd 데이터 삭제
```

## 단계별 그룹핑

위 흐름을 목적별로 그룹핑하면 다음과 같다:

| 단계 | 목적 | 플레이/태스크 |
|------|------|---------------|
| **공통 설정** | 변수, 핸들러 로딩 | boilerplate |
| **정보 수집** | 노드 상태 파악 | internal_facts, service_facts |
| **사용자 확인** | 실수 방지 | pause + fail |
| **DNS 복원** | 클러스터 DNS 설정 제거 | preinstall (dns_early) |
| **클러스터 초기화** | 모든 K8s 컴포넌트 제거 | reset |

<br>

# 플레이북 구조

## 전체 코드

<details markdown="1">
<summary>reset.yml 전체 코드 (클릭하여 펼치기)</summary>

{% raw %}
```yaml
---
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Gather facts
  import_playbook: internal_facts.yml

- name: Reset cluster
  hosts: etcd:k8s_cluster:calico_rr
  gather_facts: false
  pre_tasks:
    - name: Reset Confirmation
      pause:
        prompt: "Are you sure you want to reset cluster state? Type 'yes' to reset your cluster."
      register: reset_confirmation_prompt
      run_once: true
      when:
        - not (skip_confirmation | default(false) | bool)
        - reset_confirmation is not defined

    - name: Check confirmation
      fail:
        msg: "Reset confirmation failed"
      when:
        - not reset_confirmation | default(false) | bool
        - not reset_confirmation_prompt.user_input | default("") == "yes"

    - name: Gather information about installed services
      service_facts:

  environment: "{{ proxy_disable_env }}"
  roles:
    - { role: kubespray_defaults}
    - { role: kubernetes/preinstall, when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", tags: resolvconf, dns_early: true }
    - { role: reset, tags: reset }
```
{% endraw %}

</details>

<br>

## 플레이별 역할

| 순서 | 플레이 | 대상 호스트 | 주요 역할 |
|------|--------|-------------|-----------|
| 1 | Common tasks | - | 공통 설정, 변수 검증 |
| 2 | Gather facts | - | 시스템 정보 수집 |
| 3 | Reset cluster | `etcd:k8s_cluster:calico_rr` | 사용자 확인 + 클러스터 초기화 |

<br>

# 단계별 분석

## 1. 공통 설정 및 팩트 수집

```yaml
- name: Common tasks for every playbooks
  import_playbook: boilerplate.yml

- name: Gather facts
  import_playbook: internal_facts.yml
```

`scale.yml`, `remove-node.yml`과 동일하게 공통 설정과 시스템 정보를 수집한다.

## 2. 대상 호스트

```yaml
hosts: etcd:k8s_cluster:calico_rr
```

| 그룹 | 포함 노드 |
|------|----------|
| `etcd` | etcd 클러스터 노드 |
| `k8s_cluster` | Control Plane + Worker 노드 |
| `calico_rr` | Calico Route Reflector 노드 |

**전체 클러스터의 모든 노드**를 대상으로 한다. `remove-node.yml`이 특정 노드만 대상으로 하는 것과 대조적이다.

## 3. 사용자 확인 (pre_tasks)

노드 초기화 역시 클러스터 내 노드에 영향을 주는 중요한 작업이므로, 실수 방지를 위해 사용자 방지를 받는다.

{% raw %}
```yaml
pre_tasks:
  - name: Reset Confirmation
    pause:
      prompt: "Are you sure you want to reset cluster state? Type 'yes' to reset your cluster."
    register: reset_confirmation_prompt
    run_once: true
    when:
      - not (skip_confirmation | default(false) | bool)
      - reset_confirmation is not defined

  - name: Check confirmation
    fail:
      msg: "Reset confirmation failed"
    when:
      - not reset_confirmation | default(false) | bool
      - not reset_confirmation_prompt.user_input | default("") == "yes"

  - name: Gather information about installed services
    service_facts:
```
{% endraw %}

| 요소 | 설명 |
|------|------|
| `pre_tasks` | 롤 실행 전에 수행할 태스크 |
| `pause` | 플레이북 실행을 일시 중지하고 사용자 입력 대기. `prompt`로 메시지 표시, 입력값은 `register`로 저장 |
| `fail` | 조건이 충족되면 플레이북을 즉시 실패로 종료. `msg`로 에러 메시지 지정 |
| `run_once: true` | 모든 노드 대상이어도 한 번만 확인 |
| `service_facts` | 현재 설치된 서비스 정보 수집 |

### 확인 프롬프트 표시 조건

```yaml
when:
  - not (skip_confirmation | default(false) | bool)
  - reset_confirmation is not defined
```

1. `skip_confirmation`이 `false`이거나 미정의
2. `reset_confirmation`이 미정의

> **참고**: `skip_confirmation`은 `group_vars`나 인벤토리 파일 등 여러 방법으로 설정할 수 있지만, **`-e` 옵션 사용을 권장**한다. 확인 프롬프트는 실수 방지 목적이므로, `group_vars`에 `true`로 설정하면 항상 확인을 건너뛰게 되어 위험하다. CI/CD 자동화 시에만 명시적으로 `-e skip_confirmation=true`를 전달하는 것이 안전하다.

### 플레이북 실패 조건

```yaml
when:
  - not reset_confirmation | default(false) | bool
  - not reset_confirmation_prompt.user_input | default("") == "yes"
```

두 조건이 모두 참이면 `fail` 모듈이 실행되어 **플레이북이 즉시 중단**된다:

1. `reset_confirmation`이 `false`이거나 미정의
2. 사용자 입력이 "yes"가 아님

역으로, 다음 중 하나라도 만족하면 플레이북이 계속 진행된다:
- `reset_confirmation=true`로 설정됨
- 사용자가 프롬프트에 "yes" 입력

> **참고**: `reset_confirmation`도 `-e` 옵션으로 전달한다. `-e reset_confirmation=true`를 사용하면 프롬프트 없이 플레이북이 진행된다. `skip_confirmation`과 마찬가지로 CI/CD 자동화 시에만 사용하는 것이 안전하다.

> **참고**: `remove-node.yml`은 `assert`로 노드 지정을 강제하지만, `reset.yml`은 확인 프롬프트로 실수를 방지한다.

## 4. DNS 설정 복원

{% raw %}
```yaml
- { role: kubernetes/preinstall, when: "dns_mode != 'none' and resolvconf_mode == 'host_resolvconf'", tags: resolvconf, dns_early: true }
```
{% endraw %}

| 변수 | 설명 |
|------|------|
| `dns_early: true` | 클러스터 초기화 **전에** DNS 설정 복원 |
| `dns_mode != 'none'` | DNS 모드가 설정된 경우 |
| `resolvconf_mode == 'host_resolvconf'` | 호스트 resolv.conf 모드인 경우 |

클러스터 DNS(CoreDNS)가 사라지기 전에 `/etc/resolv.conf`를 원래 상태로 복원한다.

> **참고**: `scale.yml`에서는 `dns_late: true` (클러스터 구성 후 DNS 설정), `reset.yml`에서는 `dns_early: true` (클러스터 삭제 전 DNS 복원)를 사용한다.

## 5. 클러스터 초기화 (reset 롤)

```yaml
- { role: reset, tags: reset }
```

`reset` 롤은 **Kubernetes 관련 모든 것을 삭제**한다.


### 주요 삭제 대상

| 카테고리 | 삭제 대상 |
|----------|----------|
| **kubeadm** | `kubeadm reset -f` 실행 |
| **컨테이너** | 모든 컨테이너 중지 및 삭제 |
| **이미지** | 컨테이너 이미지 삭제 (선택) |
| **바이너리** | kubelet, kubectl, kubeadm 등 |
| **설정 파일** | `/etc/kubernetes/`, `~/.kube/` |
| **데이터** | `/var/lib/kubelet/`, `/var/lib/etcd/` |
| **네트워크** | CNI 설정, iptables 규칙 |
| **인증서** | PKI 인증서 및 키 |

### kubeadm reset

```bash
kubeadm reset -f
```

- kubelet 중지
- etcd 멤버에서 제거 (kubeadm 관리 etcd인 경우)
- `/etc/kubernetes/` 내 설정 파일 삭제
- 클러스터 상태 정리

### 삭제되는 디렉토리

```
/etc/kubernetes/        # K8s 설정
/var/lib/kubelet/       # kubelet 데이터
/var/lib/etcd/          # etcd 데이터 (복구 불가)
/etc/cni/               # CNI 설정
/opt/cni/               # CNI 바이너리
/var/log/pods/          # Pod 로그
/var/log/containers/    # 컨테이너 로그
```

<br>


# 실행 방법

## 기본 실행

```bash
ansible-playbook -i inventory/mycluster/inventory.ini reset.yml
```

실행 시 프롬프트에서 "yes"를 입력해야 한다.

```
[Reset Confirmation]
Are you sure you want to reset cluster state? Type 'yes' to reset your cluster.: yes
```

## 자동화 (확인 건너뛰기)

```bash
ansible-playbook reset.yml -e skip_confirmation=true
ansible-playbook reset.yml -e reset_confirmation=true
```

| 변수 | pause 건너뜀 | fail 건너뜀 | 권장 |
|------|-------------|-------------|------|
| `skip_confirmation=true` | O | X (실패 가능) | |
| `reset_confirmation=true` | O | O | 권장 |

`skip_confirmation=true`는 `pause` 조건의 첫 번째 항목만 false로 만든다. 그러나 `fail` 조건에서 `reset_confirmation`을 별도로 체크하므로 플레이북이 실패할 수 있다. 반면 `reset_confirmation=true`는 `pause` 조건의 두 번째 항목(`reset_confirmation is not defined`)을 false로 만들어 pause를 건너뛰고, `fail` 조건의 첫 번째 항목도 false로 만들어 fail도 건너뛴다.

 따라서 **`reset_confirmation=true` 사용을 권장**한다.

## 특정 태그만 실행

```bash
# reset 롤만 실행
ansible-playbook reset.yml --tags reset

# DNS 설정만 복원
ansible-playbook reset.yml --tags resolvconf
```


# 주의사항

## 복구 불가

`reset.yml` 실행 후에는 **클러스터를 복구할 수 없다**.

| 삭제 대상 | 복구 방법 |
|----------|----------|
| etcd 데이터 | 외부 백업에서 복원 (있는 경우) |
| 워크로드 | 매니페스트/Helm 차트로 재배포 |
| PV 데이터 | 스토리지 백업에서 복원 |

## 실행 전 체크리스트

1. **백업 확인**: etcd 스냅샷, PV 데이터 백업 여부
2. **워크로드 확인**: 재배포 가능한 매니페스트 보유 여부
3. **대상 확인**: 올바른 인벤토리 파일인지 확인

```bash
# 대상 노드 확인
ansible-inventory -i inventory/mycluster/inventory.ini --graph
```

## 언제 사용하는가?

| 시나리오 | 적합성 |
|----------|--------|
| 테스트 환경 정리 | 적합 |
| 클러스터 재구축 | 적합 |
| 노드 교체 | `remove-node.yml` 사용 |
| 프로덕션 환경 | 신중히 검토 |


<br>

# 정리

이번 글에서 `reset.yml`의 전체 흐름을 파악했다. 핵심은 **전체 클러스터를 완전히 삭제**한다는 점이다.

## remove-node.yml과의 주요 차이

| 항목 | remove-node.yml | reset.yml |
|------|-----------------|-----------|
| **대상** | 지정된 노드만 (`-e node=...`) | 전체 클러스터 |
| **검증** | `assert`로 노드 지정 강제 | 확인 프롬프트만 |
| **Drain** | 수행 (Pod 이동) | 수행하지 않음 |
| **etcd 멤버 제거** | 조건부 수행 | 전체 삭제 |
| **복구** | 노드 재추가 가능 | **불가** |

`reset.yml`은 **전체 클러스터를 삭제**하므로 Pod를 다른 노드로 이동시킬 필요가 없다.

## 주요 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `skip_confirmation` | `false` | 확인 프롬프트 건너뛰기 |
| `reset_confirmation` | (미정의) | 미리 확인 완료로 설정 |
| `dns_mode` | `coredns` | 클러스터 DNS 모드 |
| `resolvconf_mode` | `host_resolvconf` | resolv.conf 관리 방식 |

## Kubespray와 kubeadm

`reset.yml` 분석에서도 확인할 수 있듯이, **Kubespray는 kubeadm을 사용**한다.

| Kubespray가 하는 일 | 실제 동작 |
|---------------------|-----------|
| 클러스터 초기화 | `kubeadm reset -f` |
| DNS 복원 | 클러스터 삭제 전 resolv.conf 복원 |
| 완전 삭제 | 바이너리, 설정, 데이터 디렉토리 삭제 |

Kubespray의 `reset` 롤은 `kubeadm reset`만으로 삭제되지 않는 부분(바이너리, CNI 설정, 로그 등)까지 정리한다.

<br>


<br>

<br>

# 참고 자료

- [Kubespray GitHub - reset.yml](https://github.com/kubernetes-sigs/kubespray/blob/master/reset.yml)
- [Kubernetes - kubeadm reset](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-reset/)

<br>
