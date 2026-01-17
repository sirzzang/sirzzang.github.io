---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 9. 핸들러와 오류 처리"
excerpt: "Ansible 핸들러(Handler)와 작업 실패 처리 방법을 실습해 보자."
hidden: true
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-2

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Ansible 핸들러와 작업 실패 처리 방법 이해**다.

- 핸들러: `notify`로 호출, 변경 시에만 실행
- 실패 무시: `ignore_errors: yes`
- 실패 후 핸들러 실행: `force_handlers: yes`
- 실패 조건 지정: `failed_when`
- 변경 조건 지정: `changed_when`
- 블록 오류 처리: `block`, `rescue`, `always`

<br>

# 핸들러란?

## 개념

Ansible 모듈은 **멱등성**(idempotent)을 보장하도록 설계되어 있다. 플레이북을 여러 번 실행해도 결과는 항상 동일하며, 변경이 필요한 경우에만 실제로 변경된다.

하지만 한 작업에서 시스템을 변경한 경우 **추가 작업을 실행해야 할 수도 있다**. 예를 들어 서비스의 설정 파일을 변경하면, 변경 내용이 적용되도록 **서비스를 재시작**해야 한다. 이때 모든 실행마다 서비스를 재시작하면 불필요한 다운타임이 발생한다.

**핸들러(Handler)**는 다른 작업에서 **트리거한 알림에 응답하는 작업**이다. 핸들러는 해당 호스트에서 작업이 변경되었을 때(`changed`)만 통지를 받아 실행된다. 이를 통해 **실제로 변경이 발생했을 때만** 필요한 작업(예: 서비스 재시작)을 수행할 수 있다.

핵심은 다음과 같다고 기억해 두면 된다:
- 작업이 `changed` 상태일 때만 실행됨
- 모든 tasks 실행 후 마지막에 한 번만 실행됨
- 같은 핸들러가 여러 번 호출되어도 한 번만 실행됨

> **참고**: [Ansible Handlers 공식 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_handlers.html)

<br>

## 기본 문법

```yaml
tasks:
  - name: Task that may change something
    ansible.builtin.모듈:
      옵션: 값
    notify:
      - 핸들러 이름

handlers:
  - name: 핸들러 이름
    ansible.builtin.모듈:
      옵션: 값
```

- `notify`: 작업이 `changed` 상태일 때 지정한 핸들러 호출
- `handlers`: 핸들러 정의 섹션

## 주의 사항
핸들러 사용 시 다음 사항에 주의하도록 한다:
- **명시적 호출**: 핸들러는 `notify` 문을 사용하여 **명시적으로 호출**된 경우에만 실행된다. 자동으로 실행되지 않는다.
- **고유한 이름**: 각 핸들러는 **고유한 이름**을 가져야 한다. 같은 이름으로 여러 개의 핸들러를 정의하면 마지막에 정의된 핸들러만 실행된다.

<br>

# 실습 1: 기본 핸들러

## Playbook 작성

rsyslog 서비스를 재시작하고, 핸들러를 호출하여 메시지를 출력한다.

**핸들러 동작 확인**:
- `state: restarted` → 항상 `changed` → 핸들러 실행
- `state: started` (이미 실행 중) → `ok` (변경 없음) → 핸들러 실행 안 됨

```bash
# (server) #
cat <<'EOT' > handler-sample.yml
---
- hosts: tnode2
  tasks:
    - name: restart rsyslog
      ansible.builtin.service:
        name: "rsyslog"
        state: restarted
      notify:
        - print msg

  handlers:
    - name: print msg
      ansible.builtin.debug:
        msg: "rsyslog is restarted"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook handler-sample.yml
```

실행 결과:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [restart rsyslog] ******************************************************************
changed: [tnode2]

RUNNING HANDLER [print msg] *************************************************************
ok: [tnode2] => {
    "msg": "rsyslog is restarted"
}

PLAY RECAP ******************************************************************************
tnode2                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **restart rsyslog**: `state: restarted`로 서비스를 재시작하므로 항상 `changed` 상태
- **RUNNING HANDLER**: `changed` 상태이므로 핸들러가 실행됨
- **PLAY RECAP**: `ok=3` (Gathering Facts, restart rsyslog, print msg 핸들러)

<br>

## 다시 실행

두 번째 실행 시에도 `state: restarted`는 항상 `changed`를 반환하므로 핸들러가 호출된다.

```bash
# (server) #
ansible-playbook handler-sample.yml
```

실행 결과 (두 번째 실행):

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [restart rsyslog] ******************************************************************
changed: [tnode2]

RUNNING HANDLER [print msg] *************************************************************
ok: [tnode2] => {
    "msg": "rsyslog is restarted"
}

PLAY RECAP ******************************************************************************
tnode2                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **결과 동일**: `restarted`는 멱등적이지 않으므로 매번 `changed` 반환
- **핸들러 매번 실행**: `changed` 상태이므로 핸들러가 매번 실행됨

<br>

## started로 변경 후 확인

이제 기존 `handler-sample.yml` 파일에서 `state`를 `restarted`에서 `started`로만 변경하여 핸들러가 실행되지 않는 것을 확인해 보자.

**Playbook 수정 (state만 변경)**:

```bash
# (server) #
# vi나 sed로 handler-sample.yml 파일의 state를 restarted → started로 변경
sed -i 's/state: restarted/state: started/' handler-sample.yml

# 변경 확인
cat handler-sample.yml
```

변경된 파일 내용:

```yaml
---
- hosts: tnode2
  tasks:
    - name: restart rsyslog
      ansible.builtin.service:
        name: "rsyslog"
        state: started  # restarted → started로 변경
      notify:
        - print msg

  handlers:
    - name: print msg
      ansible.builtin.debug:
        msg: "rsyslog is restarted"
```

**실행**:

```bash
# (server) #
ansible-playbook handler-sample.yml
```

rsyslog는 이미 실행 중이므로 `ok` 상태가 되고, 핸들러가 실행되지 않는다:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [restart rsyslog] ******************************************************************
ok: [tnode2]

PLAY RECAP ******************************************************************************
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **restart rsyslog**: 서비스가 이미 실행 중이므로 `ok` 상태 (변경 없음)
- **핸들러 실행 안 됨**: `changed`가 아니므로 `RUNNING HANDLER` 섹션 자체가 나타나지 않음
- **PLAY RECAP**: `ok=2` (Gathering Facts, restart rsyslog만 실행, 핸들러는 실행 안 됨)

<br>

## 실제 사용 사례

실제 환경에서는 **설정 파일 변경 시에만 서비스를 재시작**하는 패턴을 많이 사용한다. 아래 Apache 설정 파일 변경 후 재시작하는 예시를 보자.

```yaml
---
- hosts: web
  tasks:
    - name: Update apache config
      ansible.builtin.copy:
        src: apache.conf
        dest: /etc/apache2/apache2.conf
      notify:
        - restart apache

  handlers:
    - name: restart apache
      ansible.builtin.service:
        name: apache2
        state: restarted
```

> 참고: [copy 모듈의 변경 감지 원리](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/copy_module.html)
>
> `copy` 모듈은 파일의 **체크섬(checksum)**을 비교하여 변경 여부를 판단한다:
> - **원본 파일**과 **대상 파일**의 체크섬을 계산
> - 체크섬이 다르면 → 내용이 변경됨 → `changed` 반환 → 핸들러 호출
> - 체크섬이 같으면 → 내용이 동일함 → `ok` 반환 (변경 없음) → 핸들러 호출 안 됨




**동작**:
1. **첫 번째 실행**: 설정 파일이 변경됨 → `changed` → 핸들러 실행 → 서비스 재시작
2. **두 번째 실행**: 설정 파일이 이미 최신 (체크섬 동일) → `ok` (변경 없음) → 핸들러 실행 안 됨 → 불필요한 재시작 없음

이 방식으로 **실제로 변경이 발생했을 때만** 서비스를 재시작하여 불필요한 다운타임을 방지할 수 있다.

<br>

# 실습 2: (도전 과제) apache2 설치 후 핸들러로 재시작

## 목표

`apt` 모듈로 apache2 패키지를 설치하고, **핸들러**를 호출하여 `service` 모듈로 apache2를 재시작한다.

> **참고**: 
> - [apt 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html)
> - [dnf 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/dnf_module.html)

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > handler-restart-apache-after-installation.yml
---
- hosts: all
  tasks:
    - name: Install Apache (Debian)
      ansible.builtin.apt:
        name: apache2
        state: present
      when: ansible_facts['os_family'] == "Debian"
      notify:
        - restart apache2
    - name: Install Apache (RedHat)
      ansible.builtin.dnf:
        name: httpd
        state: present
      when: ansible_facts['os_family'] == "RedHat"
      notify: 
        - restart httpd
  handlers:
    - name: restart apache2
      ansible.builtin.service:
        name: apache2
        state: restarted
      when: ansible_facts['os_family'] == "Debian"
    - name: restart httpd
      ansible.builtin.service:
        name: httpd
        state: restarted
      when: ansible_facts['os_family'] == "RedHat"
EOT
```

**주요 포인트**:
- **OS별 패키지 설치**: Debian 계열은 `apache2`, RedHat 계열은 `httpd` 설치
- **OS별 핸들러 분리**: 각 OS에 맞는 서비스 이름으로 핸들러 호출
- **`when` 조건문**: OS 계열에 따라 적절한 task와 handler만 실행

<br>

## 실행

```bash
# (server) #
ansible-playbook handler-restart-apache-after-installation.yml
```

**첫 번째 실행 결과**:

```bash
PLAY [all] ******************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Install Apache (Debian)] **********************************************************
skipping: [tnode3]
changed: [tnode2]
changed: [tnode1]

TASK [Install Apache (RedHat)] **********************************************************
skipping: [tnode1]
skipping: [tnode2]
changed: [tnode3]

RUNNING HANDLER [restart apache2] *******************************************************
changed: [tnode2]
changed: [tnode1]

RUNNING HANDLER [restart httpd] *********************************************************
changed: [tnode3]

PLAY RECAP ******************************************************************************
tnode1                     : ok=3    changed=2    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode2                     : ok=3    changed=2    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode3                     : ok=3    changed=2    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

**결과 분석**:
- **tnode1, tnode2 (Ubuntu)**: `apache2` 설치 → `restart apache2` 핸들러 실행
- **tnode3 (Rocky)**: `httpd` 설치 → `restart httpd` 핸들러 실행
- **skipped=1**: 각 노드에서 해당 OS가 아닌 task는 건너뜀
- **changed=2**: 패키지 설치(1) + 서비스 재시작(1)

<br>

## 개선: 핸들러 통합

위 예제에서는 OS별로 핸들러를 2개 작성했지만, **조건문을 활용하여 하나의 핸들러로 통합**할 수 있다.

**개선된 Playbook**:

```yaml
---
- hosts: all
  tasks:
    - name: Install Apache (Debian)
      ansible.builtin.apt:
        name: apache2
        state: present
      when: ansible_facts['os_family'] == "Debian"
      notify:
        - restart apache
    - name: Install Apache (RedHat)
      ansible.builtin.dnf:
        name: httpd
        state: present
      when: ansible_facts['os_family'] == "RedHat"
      notify: 
        - restart apache
  handlers:
    - name: restart apache
      ansible.builtin.service:
        name: "{{ 'apache2' if ansible_facts['os_family'] == 'Debian' else 'httpd' }}"
        state: restarted
```

**개선 사항**:
- **핸들러 하나로 통합**: `restart apache` 하나로 모든 OS 처리
- **동적 서비스 이름**: Jinja2 조건문(`if-else`)으로 서비스 이름 결정
  - Debian 계열: `apache2`
  - RedHat 계열: `httpd`
- **notify 단순화**: 두 task 모두 동일한 핸들러(`restart apache`) 호출
- **유지보수 개선**: 재시작 로직이 한 곳에 집중되어 관리가 쉬움

**장점**:
- 코드 중복 제거
- 핸들러 수 감소 → 가독성 향상
- 새로운 OS 추가 시 핸들러 수정 없이 조건문만 확장 가능

<br>

# 작업 실패 처리

Ansible은 플레이 실행 시 각 작업의 **반환 코드(return code)**를 평가하여 작업의 성공 여부를 판단한다. 일반적으로 작업이 실패하면 Ansible은 해당 호스트에서 이후의 모든 작업을 건너뛴다.

하지만 작업이 실패해도 플레이를 계속 실행해야 하는 경우가 있다. 이때 **`ignore_errors`** 키워드를 사용하여 실패를 무시하거나, **`failed_when`** 키워드로 실패 조건을 직접 정의할 수 있다.

> **참고**: [Error handling in playbooks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html)

<br>

# 실습 3: 작업 실패 무시 (ignore_errors)

## 개념

`ignore_errors: yes`를 사용하면 작업이 실패해도 플레이를 계속 실행할 수 있다.

<br>

## 비교: ignore_errors 없이

먼저 `ignore_errors` 없이 실행하여 기본 동작을 확인한다.

```bash
# (server) #
cat <<'EOT' > ignore-example-1.yml
---
- hosts: tnode1
  tasks:
    - name: Install apache3
      ansible.builtin.apt:
        name: apache3
        state: latest

    - name: Print msg
      ansible.builtin.debug:
        msg: "Before task is ignored"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook ignore-example-1.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Install apache3] ******************************************************************
[ERROR]: Task failed: Module failed: No package matching 'apache3' is available
Origin: /root/my-ansible/ignore-example-1.yml:3:7

1 - hosts: tnode1
2   tasks:
3     - name: Install apache3
       ^ column 7

fatal: [tnode1]: FAILED! => {"changed": false, "msg": "No package matching 'apache3' is available"}

PLAY RECAP ******************************************************************************
tnode1                     : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **Install apache3 실패**: `apache3`라는 패키지가 존재하지 않아 에러 발생
- **이후 작업 중단**: `fatal: [tnode1]: FAILED!` 발생 후 `Print msg` 작업이 실행되지 않음
- **PLAY RECAP**: `failed=1`, 전체 플레이 실패

<br>

## 비교: ignore_errors 사용

이제 `ignore_errors: yes`를 추가하여 에러를 무시하고 계속 진행하도록 한다.

```bash
# (server) #
cat <<'EOT' > ignore-example-2.yml
---
- hosts: tnode1
  tasks:
    - name: Install apache3
      ansible.builtin.apt:
        name: apache3
        state: latest
      ignore_errors: yes

    - name: Print msg
      ansible.builtin.debug:
        msg: "Before task is ignored"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook ignore-example-2.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Install apache3] ******************************************************************
[ERROR]: Task failed: Module failed: No package matching 'apache3' is available
Origin: /root/my-ansible/ignore-example-2.yml:3:7

1 - hosts: tnode1
2   tasks:
3     - name: Install apache3
       ^ column 7

fatal: [tnode1]: FAILED! => {"changed": false, "msg": "No package matching 'apache3' is available"}
...ignoring

TASK [Print msg] ************************************************************************
ok: [tnode1] => {
    "msg": "Before task is ignored"
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=1
```

**결과 분석**:
- **Install apache3 실패**: 동일하게 에러 발생 (`fatal: [tnode1]: FAILED!`)
- **`...ignoring` 표시**: `ignore_errors: yes` 덕분에 에러를 무시
- **이후 작업 실행**: `Print msg` 작업이 정상적으로 실행됨
- **PLAY RECAP**: `failed=0`, `ignored=1` (에러를 무시했음을 표시)

**핵심**:
- `ignore_errors: yes`를 사용하면 작업이 실패해도 플레이가 계속 진행됨
- PLAY RECAP에서 `ignored` 필드에 무시된 에러 수가 표시됨
- 에러는 발생하지만 플레이 전체는 성공으로 처리됨

<br>

# 실습 4: 작업 실패 후 핸들러 실행 (force_handlers)

## 개념

기본적으로 작업이 실패하면 알림을 받은 핸들러도 실행되지 않는다. `force_handlers: yes`를 사용하면 **작업이 실패해도 이미 알림을 받은 핸들러는 실행**된다.

<br>

## 비교: force_handlers 없이

먼저 `force_handlers` 없이 실행하여 기본 동작을 확인한다.

```bash
# (server) #
cat <<'EOT' > force-handler-1.yml
---
- hosts: tnode2
  tasks:
    - name: restart rsyslog
      ansible.builtin.service:
        name: "rsyslog"
        state: restarted
      notify:
        - print msg

    - name: install apache3
      ansible.builtin.apt:
        name: "apache3"
        state: latest

  handlers:
    - name: print msg
      ansible.builtin.debug:
        msg: "rsyslog is restarted"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook force-handler-1.yml
```

**실행 결과**:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [restart rsyslog] ******************************************************************
changed: [tnode2]

TASK [install apache3] ******************************************************************
[ERROR]: Task failed: Module failed: No package matching 'apache3' is available
Origin: /root/my-ansible/force-handler-1.yml:10:7

 8       notify:
 9         - print msg
10     - name: install apache3
        ^ column 7

fatal: [tnode2]: FAILED! => {"changed": false, "msg": "No package matching 'apache3' is available"}

PLAY RECAP ******************************************************************************
tnode2                     : ok=2    changed=1    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **restart rsyslog 성공**: `changed` 상태로 핸들러 `print msg`를 notify
- **install apache3 실패**: 작업 실패로 플레이 중단
- **핸들러 실행 안 됨**: `RUNNING HANDLER` 섹션이 나타나지 않음
- **PLAY RECAP**: `ok=2`, `changed=1`, `failed=1` (핸들러가 실행되지 않음)

<br>

## 비교: force_handlers 사용

이제 `force_handlers: yes`를 추가하여 실패 시에도 핸들러가 실행되도록 한다.

```bash
# (server) #
cat <<'EOT' > force-handler-2.yml
---
- hosts: tnode2
  force_handlers: yes
  tasks:
    - name: restart rsyslog
      ansible.builtin.service:
        name: "rsyslog"
        state: restarted
      notify:
        - print msg

    - name: install apache3
      ansible.builtin.apt:
        name: "apache3"
        state: latest

  handlers:
    - name: print msg
      ansible.builtin.debug:
        msg: "rsyslog is restarted"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook force-handler-2.yml
```

**실행 결과**:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [restart rsyslog] ******************************************************************
changed: [tnode2]

TASK [install apache3] ******************************************************************
[ERROR]: Task failed: Module failed: No package matching 'apache3' is available
Origin: /root/my-ansible/force-handler-2.yml:11:7

 9       notify:
10         - print msg
11     - name: install apache3
        ^ column 7

fatal: [tnode2]: FAILED! => {"changed": false, "msg": "No package matching 'apache3' is available"}

RUNNING HANDLER [print msg] *************************************************************
ok: [tnode2] => {
    "msg": "rsyslog is restarted"
}

PLAY RECAP ******************************************************************************
tnode2                     : ok=3    changed=1    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **restart rsyslog 성공**: `changed` 상태로 핸들러 `print msg`를 notify
- **install apache3 실패**: 동일하게 작업 실패
- **핸들러 실행됨**: `force_handlers: yes` 덕분에 `RUNNING HANDLER [print msg]` 실행
- **PLAY RECAP**: `ok=3` (핸들러 포함), `changed=1`, `failed=1`

**핵심**:
- `force_handlers: yes`를 사용하면 작업이 실패해도 **이미 notify된 핸들러는 실행**됨
- 작업 실패 여부와 관계없이 필수적으로 실행되어야 하는 정리 작업(cleanup)에 유용
- PLAY RECAP에서 `ok` 수가 증가 (핸들러 실행 반영)

<br>

# 실습 5: 작업 실패 조건 지정 (failed_when)

## 개념

`failed_when`을 사용해 **특정 조건에서 작업을 실패로 처리**할 수 있다. 멱등성이 보장되지 않는 모듈에서 유용하다.

### 멱등성이 보장되지 않는 모듈

대부분의 Ansible 모듈(`apt`, `service`, `copy` 등)은 **멱등성**이 보장된다. 즉, 현재 상태를 확인하여 변경이 필요한 경우에만 `changed`를 반환하고, 실패 시 자동으로 `failed`를 반환한다.

하지만 **`command`, `shell` 계열 모듈**은 임의의 명령어를 실행하므로 멱등성이 보장되지 않는다:

1. **항상 changed 상태**:
   - 명령이 실행되면 **반환 코드와 관계없이 `changed`로 처리**됨
   - 실제 시스템 상태가 변경되지 않아도 `changed`로 표시됨

2. **실패 감지 불가**:
   - 셸 스크립트가 에러 메시지를 출력해도 Ansible은 작업이 성공했다고 간주
   - 실제로 명령이 실패했는지 여부를 Ansible이 자동으로 판단하지 못함

3. **`failed_when` 필요성**:
   - 이런 경우 **`failed_when`** 키워드를 사용하여 **작업이 실패했음을 나타내는 조건을 직접 지정**할 수 있음
   - 예: 특정 문자열이 출력되거나, 특정 반환 코드가 반환되면 실패로 처리

> **참고**: [Defining failure](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html#defining-failure)

<br>

## 스크립트 준비

```bash
# (server) #
# 스크립트 다운로드
wget https://raw.githubusercontent.com/naleeJang/Easy-Ansible/refs/heads/main/chapter_07.3/adduser-script.sh
chmod +x adduser-script.sh

# tnode1에 복사 (copy 모듈 사용, mode=0755로 실행 권한 부여)
ansible -m copy -a 'src=/root/my-ansible/adduser-script.sh dest=/root/adduser-script.sh mode=0755' tnode1
```
- **`-m copy`**: copy 모듈 사용하여 파일 복사
- **`src`**: 서버(control node)의 소스 파일 경로
- **`dest`**: 대상 노드(managed node)의 복사될 경로
- **`mode=0755`**: 실행 권한 부여 (rwxr-xr-x)
- **`tnode1`**: 대상 호스트

다운 받은 스크립트는 아래와 같다. **입력받은 사용자 계정 목록을 생성하고 패스워드를 설정하는 스크립트**이다.

```bash
#!/bin/bash

# 사용자 계정 및 패스워드가 입력되었는지 확인
if [[ -n $1 ]] && [[ -n $2 ]]
then

  UserList=($1)
  Password=($2)

  # for문을 이용하여 사용자 계정 생성
  for (( i=0; i < ${#UserList[@]}; i++ ))
  do
    # if문을 사용하여 사용자 계정이 있는지 확인
    if [[ $(cat /etc/passwd | grep ${UserList[$i]} | wc -l) == 0 ]]
    then
      # 사용자 생성 및 패스워드 설정
      useradd ${UserList[$i]}
      echo ${Password[$i]} | passwd ${UserList[$i]} --stdin
    else
      # 사용자가 있다고 메시지를 보여줌
      echo "this user ${UserList[$i]} is existing."
    fi
  done

else
  # 사용자 계정과 패스워드를 입력하라는 메시지를 보여줌
  echo -e 'Please input user id and password.\nUsage: adduser-script.sh "user01 user02" "pw01 pw02"'
fi
```

tnode1에 잘 복사되었는지 확인한다.
```bash
# tnode1에 있는지 확인
ssh tnode1 ls -l /root
total 4
-rwxr-xr-x 1 root root 846 Jan 18 00:42 adduser-script.sh
```

<br>

## 비교: failed_when 없이

먼저 `failed_when` 없이 실행하여 기본 동작을 확인한다.

```bash
# (server) #
cat <<'EOT' > failed-when-1.yml
---
- hosts: tnode1
  tasks:
    - name: Run user add script
      ansible.builtin.shell: /root/adduser-script.sh
      register: command_result

    - name: Print msg
      ansible.builtin.debug:
        msg: "{{ command_result.stdout }}"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook failed-when-1.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Run user add script] **************************************************************
changed: [tnode1]

TASK [Print msg] ************************************************************************
ok: [tnode1] => {
    "msg": "Please input user id and password.\nUsage: adduser-script.sh \"user01 user02\" \"pw01 pw02\""
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **Run user add script**: 스크립트 실행 시 에러 메시지가 출력되었지만 `changed` 상태로 성공 처리됨
- **Print msg 실행**: 스크립트의 에러 메시지가 출력됨
- **PLAY RECAP**: `ok=3`, `changed=1`, `failed=0` (성공으로 처리)
- **문제점**: 실제로는 스크립트가 실패했지만 Ansible은 이를 감지하지 못함

**실행 후 user 추가 확인**:

```bash
# (server) #
ansible -m shell -a "tail -n 3 /etc/passwd" tnode1
```

```bash
tnode1 | CHANGED | rc=0 >>
vboxadd:x:999:1::/var/run/vboxadd:/bin/false
ansible:x:1001:1001::/home/ansible:/bin/sh
ansible2:x:1002:1002::/home/ansible2:/bin/sh
```

사용자가 추가되지 않았지만, Ansible은 작업을 성공으로 처리했다.

<br>

## 비교: failed_when 사용

이제 `failed_when`을 추가하여 특정 조건에서 실패로 처리하도록 한다. `command_result.stdout` 변수에 `"Please..."`라는 문자열이 있으면 작업을 실패로 처리하도록 한다.

```bash
# (server) #
cat <<'EOT' > failed-when-2.yml
---
- hosts: tnode1
  tasks:
    - name: Run user add script
      ansible.builtin.shell: /root/adduser-script.sh
      register: command_result
      failed_when: "'Please input user id and password' in command_result.stdout"

    - name: Print msg
      ansible.builtin.debug:
        msg: "{{ command_result.stdout }}"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook failed-when-2.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Run user add script] **************************************************************
[ERROR]: Task failed: Action failed.
Origin: /root/my-ansible/failed-when-2.yml:3:7

1 - hosts: tnode1
2   tasks:
3     - name: Run user add script
       ^ column 7

fatal: [tnode1]: FAILED! => {"changed": true, "cmd": "/root/adduser-script.sh", "delta": "0:00:00.002038", "end": "2026-01-18 00:46:45.286859", "failed_when_result": true, "msg": "", "rc": 0, "start": "2026-01-18 00:46:45.284821", "stderr": "", "stderr_lines": [], "stdout": "Please input user id and password.\nUsage: adduser-script.sh \"user01 user02\" \"pw01 pw02\"", "stdout_lines": ["Please input user id and password.", "Usage: adduser-script.sh \"user01 user02\" \"pw01 pw02\""]}

PLAY RECAP ******************************************************************************
tnode1                     : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **Run user add script 실패**: `failed_when` 조건(`'Please input user id and password' in command_result.stdout`)이 참이므로 실패 처리
- **`failed_when_result": true`**: 출력에서 실패 조건이 충족되었음을 확인
- **`"rc": 0`**: 반환 코드는 0(성공)이지만 `failed_when`에 의해 실패로 처리됨
- **Print msg 실행 안 됨**: 작업 실패로 플레이 중단
- **PLAY RECAP**: `ok=1`, `changed=0`, `failed=1`

**실행 후 user 추가 확인**:

```bash
# (server) #
ansible -m shell -a "tail -n 3 /etc/passwd" tnode1
```

```bash
tnode1 | CHANGED | rc=0 >>
vboxadd:x:999:1::/var/run/vboxadd:/bin/false
ansible:x:1001:1001::/home/ansible:/bin/sh
ansible2:x:1002:1002::/home/ansible2:/bin/sh
```

위의 결과와 동일하게, 새로운 사용자가 추가되지 않았다. 하지만 **중요한 차이점**은 다음과 같다:
- **`failed-when-1.yml`**: 실패했지만 Ansible은 성공으로 처리 (`failed=0`)
- **`failed-when-2.yml`**: 실패를 정확히 감지하여 실패로 처리 (`failed=1`)

<br>

## fail 모듈로 커스텀 메시지

`fail` 모듈을 사용하면 **커스텀 메시지와 함께 작업을 명시적으로 실패**시킬 수 있다. `failed_when`과 달리 실패 메시지를 더 명확하게 제어할 수 있다.

> **참고**: [fail 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/fail_module.html)

```bash
# (server) #
cat <<'EOT' > failed-when-custom.yml
---
- hosts: tnode1
  tasks:
    - name: Run user add script
      ansible.builtin.shell: /root/adduser-script.sh
      register: command_result
      ignore_errors: yes

    - name: Report script failure
      ansible.builtin.fail:
        msg: "{{ command_result.stdout }}"
      when: "'Please input user id and password' in command_result.stdout"
EOT
```

**주요 차이점**:
- **`ignore_errors: yes`**: 첫 번째 작업이 실패해도 계속 진행
- **`fail` 모듈**: 조건이 참일 때 커스텀 메시지와 함께 명시적으로 실패 처리
- **`when` 조건**: `fail` 모듈은 조건이 참일 때만 실행됨

**실행**:

```bash
# (server) #
ansible-playbook failed-when-custom.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Run user add script] **************************************************************
changed: [tnode1]

TASK [Report script failure] ************************************************************
[ERROR]: Task failed: Action failed: Please input user id and password.
Usage: adduser-script.sh "user01 user02" "pw01 pw02"
Origin: /root/my-ansible/failed-when-custom.yml:8:7

6       register: command_result
7       ignore_errors: yes
8     - name: Report script failure
       ^ column 7

fatal: [tnode1]: FAILED! => {"changed": false, "msg": "Please input user id and password.\nUsage: adduser-script.sh \"user01 user02\" \"pw01 pw02\""}

PLAY RECAP ******************************************************************************
tnode1                     : ok=2    changed=1    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **Run user add script**: `ignore_errors: yes`로 실행되어 에러를 무시하고 계속 진행 (`changed`)
- **Report script failure**: `when` 조건이 참이므로 `fail` 모듈 실행, 커스텀 메시지 출력
- **에러 메시지**: 스크립트의 Usage 메시지가 그대로 출력됨
- **PLAY RECAP**: `ok=2` (첫 번째 작업은 무시됨), `failed=1`

**활용**:
- 복잡한 조건 체크 후 명확한 실패 메시지 제공
- 여러 단계를 거친 후 종합적으로 실패 판단
- 사용자에게 더 친화적인 에러 메시지 제공

## 핵심
- `failed_when`을 사용하면 반환 코드와 무관하게 **특정 조건(출력 내용, 변수 값 등)에서 작업을 실패로 처리**할 수 있음
- `command`, `shell` 모듈처럼 멱등성이 보장되지 않는 모듈에서 필수적
- 스크립트의 실제 실행 결과를 기반으로 성공/실패를 정확히 판단 가능

<br>

# 실습 6: 작업 변경 조건 지정 (changed_when)

## 개념

`failed_when`이 **실패 조건**을 지정한다면, `changed_when`은 **변경 조건**을 지정한다. 일부 모듈은 실제로 변경이 발생하지 않아도 `changed` 상태를 반환하거나, 반대로 변경이 발생했는데도 `ok` 상태를 반환할 수 있다. 이럴 때 `changed_when`을 사용하여 명시적으로 변경 상태를 지정한다.

**주요 사용 사례**:
1. **핸들러 강제 실행**: `changed_when: true`로 항상 changed 상태로 만들어 핸들러 트리거
2. **변경 상태 억제**: `changed_when: false`로 changed를 방지 (읽기 전용 작업)
3. **조건부 변경**: 출력 내용이나 반환 코드를 기반으로 changed 판단

> **참고**: [Defining "changed"](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html#defining-changed)

<br>

## 기본 문법

```yaml
- name: Task name
  module_name:
    ...
  changed_when: <조건>
```

**예시**:
```yaml
# 항상 changed
- name: Always trigger handler
  ansible.builtin.command: /usr/bin/check_status
  changed_when: true

# 항상 ok (변경 없음)
- name: Read-only check
  ansible.builtin.command: /usr/bin/show_info
  changed_when: false

# 조건부 changed
- name: Check service
  ansible.builtin.command: systemctl status httpd
  register: result
  changed_when: "'inactive' in result.stdout"
```

<br>

## 실습: 핸들러 강제 실행

`uri` 모듈은 GET 요청 시 기본적으로 `changed=false`를 반환한다 (읽기 작업이므로). 하지만 핸들러를 실행하려면 `changed=true`가 필요하다. 이럴 때 `changed_when: true`를 사용한다.

> **참고**: [uri 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/uri_module.html)
> - `return_content: true`이면 HTTP 응답 본문을 반환값에 포함 (기본값: `false`)
> - 성공/실패는 HTTP 상태 코드로 판단 (200번대: 성공, 400/500번대: 실패)

```bash
# (server) #
cat <<'EOT' > changed-when-example.yml
---
- hosts: tnode1
  tasks:
    - name: Check web service
      ansible.builtin.uri:
        url: http://localhost
        return_content: true
      register: web_result
      changed_when: true
      notify: Print web content

  handlers:
    - name: Print web content
      ansible.builtin.debug:
        msg: "{{ web_result.content }}"
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook changed-when-example.yml
```

```
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Check web service] *******************************************************
changed: [tnode1]

RUNNING HANDLER [Print web content] ********************************************
ok: [tnode1] => {
    "msg": "Hello! Eraser\n"
}

PLAY RECAP *********************************************************************
tnode1                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**핵심**:
- `changed_when: true` 없이 실행하면: `changed=0`, 핸들러 실행 안 됨
- `changed_when: true` 추가하면: `changed=1`, 핸들러 실행됨

<br>

# failed_when vs changed_when

failed_when과 changed_when을 비교하면 다음과 같다.

| 키워드 | 목적 | 영향 | 사용 예시 |
|--------|------|------|-----------|
| `failed_when` | 실패 조건 지정 | 플레이 중단 (또는 ignore_errors와 함께 사용) | 특정 문자열 출력 시 실패, 특정 상태 코드 시 실패 |
| `changed_when` | 변경 조건 지정 | 핸들러 실행 여부, PLAY RECAP의 changed 카운트 | 핸들러 강제 실행, 읽기 전용 작업 표시 |

다음과 같이 함께 사용할 수도 있다.

```yaml
- name: Run script with custom status
  ansible.builtin.shell: /usr/local/bin/check_and_fix.sh
  register: result
  failed_when: "'ERROR' in result.stdout"
  changed_when: "'FIXED' in result.stdout"
```

<br>

# 실습 7: 블록과 오류 처리 (block, rescue, always)

## 개념

Ansible은 **블록(block)**이라는 오류를 제어하는 문법을 제공한다. 블록은 작업을 논리적으로 그룹화하는 절이며, `rescue`와 `always` 절과 함께 사용하여 오류를 처리할 수 있다.

**프로그래밍의 try-except-finally와 유사**하게 이해하면 도움이 된다.

```python
# Python의 try-except-finally
try:
    # 시도할 작업
    result = risky_operation()
except Exception as e:
    # 실패 시 처리
    handle_error(e)
finally:
    # 항상 실행
    cleanup()
```

```yaml
# Ansible의 block-rescue-always
- block:
    # 시도할 작업
    - name: Risky task
      ...
  rescue:
    # 실패 시 처리
    - name: Handle error
      ...
  always:
    # 항상 실행
    - name: Cleanup
      ...
```

### block/rescue/always 구조

| 키워드 | 설명 | 실행 조건 |
| --- | --- | --- |
| `block` | 실행할 기본 작업 정의 | 항상 먼저 실행 |
| `rescue` | block 작업이 실패할 경우 실행할 작업 정의 | block 실패 시에만 실행 |
| `always` | 성공/실패와 관계없이 항상 실행할 작업 정의 | block 성공/실패 여부와 무관하게 항상 실행 |

### handler와의 차이점

| 비교 | handler | block/rescue |
| --- | --- | --- |
| **목적** | 변경 발생 시 추가 작업 (예: 서비스 재시작) | 오류 처리 및 복구 |
| **실행 시점** | play 마지막에 실행 | 즉시 실행 (rescue는 block 실패 직후) |
| **트리거** | `notify`로 명시적 호출 필요 | 자동 (조건에 따라) |
| **조건** | 작업이 `changed` 상태일 때 | block 실패 여부에 따라 |
| **유사 개념** | 이벤트 핸들러 | try-except-finally |

**예시로 보는 차이**:

```yaml
# handler: 변경 발생 시 서비스 재시작
tasks:
  - name: Update config
    copy: ...
    notify: restart apache  # changed일 때만 notify
handlers:
  - name: restart apache   # play 마지막에 실행
    service: ...

# block/rescue: 오류 발생 시 즉시 복구
tasks:
  - block:
      - name: Try operation
        command: ...
    rescue:
      - name: Recover immediately  # 실패 직후 즉시 실행
        command: ...
```

> **참고**: [Blocks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_blocks.html)

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > block-example.yml
---
- hosts: tnode2
  vars:
    logdir: /var/log/daily_log
    logfile: todays.log
  tasks:
    - name: Configure Log Env
      block:
        - name: Find Directory
          ansible.builtin.find:
            paths: "{{ logdir }}"
          register: result
          failed_when: "'Not all paths' in result.msg"

      rescue:
        - name: Make Directory when Not found Directory
          ansible.builtin.file:
            path: "{{ logdir }}"
            state: directory
            mode: '0755'

      always:
        - name: Create File
          ansible.builtin.file:
            path: "{{ logdir }}/{{ logfile }}"
            state: touch
            mode: '0644'
EOT
```

- **block**: 디렉터리 존재 확인 (없으면 실패)
- **rescue**: 디렉터리가 없으면 생성
- **always**: 항상 로그 파일 생성

> **참고**: [find 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/find_module.html)

<br>

## 실행

### 첫 번째 실행: 디렉터리 없음

디렉터리가 없는 상태에서 실행하여 `rescue` 절이 동작하는지 확인한다.

```bash
# (server) #
ansible-playbook block-example.yml
```

**실행 결과**:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [Find Directory] *******************************************************************
[WARNING]: Skipped '/var/log/daily_og' path due to this access issue: '/var/log/daily_og' is not a directory
[ERROR]: Task failed: Action failed: Not all paths examined, check warnings for details
Origin: /root/my-ansible/block-example.yml:9:11

7     - name: Configure Log Env
8       block:
9         - name: Find Directory
           ^ column 11

fatal: [tnode2]: FAILED! => {"changed": false, "examined": 0, "failed_when_result": true, "files": [], "matched": 0, "msg": "Not all paths examined, check warnings for details", "skipped_paths": {"/var/log/daily_og": "'/var/log/daily_og' is not a directory"}}

TASK [Make Directory when Not Found Directory] ******************************************
changed: [tnode2]

TASK [Create File] **********************************************************************
changed: [tnode2]

PLAY RECAP ******************************************************************************
tnode2                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=1    ignored=0
```

**결과 분석**:
- **Find Directory (block)**: 디렉터리가 없어 실패 (`fatal: [tnode2]: FAILED!`)
- **Make Directory (rescue)**: block 실패로 인해 rescue 절 실행, 디렉터리 생성 (`changed`)
- **Create File (always)**: 실패 여부와 관계없이 always 절 실행, 파일 생성 (`changed`)
- **PLAY RECAP**: `rescued=1` (rescue 절이 실행됨을 나타냄), `failed=0` (rescue로 복구됨)

<br>

### 두 번째 실행: 디렉터리 있음

이제 디렉터리가 있는 상태에서 다시 실행하여 `block`이 성공하는지 확인한다.

```bash
# (server) #
ansible-playbook block-example.yml
```

**실행 결과**:

```bash
PLAY [tnode2] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode2]

TASK [Find Directory] *******************************************************************
ok: [tnode2]

TASK [Create File] **********************************************************************
changed: [tnode2]

PLAY RECAP ******************************************************************************
tnode2                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**결과 분석**:
- **Find Directory (block)**: 디렉터리가 있어 성공 (`ok`)
- **Make Directory (rescue)**: block 성공으로 인해 **실행되지 않음** (출력에 나타나지 않음)
- **Create File (always)**: 성공 여부와 관계없이 always 절 실행, 파일 재생성 (`changed`)
- **PLAY RECAP**: `rescued=0` (rescue 절이 실행되지 않음), `changed=1` (always만 실행)

**핵심 차이**:
- **첫 번째**: block 실패 → rescue 실행 → always 실행 (`rescued=1`, `changed=2`)
- **두 번째**: block 성공 → rescue 건너뜀 → always 실행 (`rescued=0`, `changed=1`)

<br>

# 실습 7: block, rescue, always 활용

## 배경

**실습 2**에서 이미 tnode1에 apache2를 설치하고 시작했다. 따라서 **포트 80이 apache2에 의해 사용 중**인 상태이다. 이 상태에서 nginx를 설치하고 시작하려고 하면 포트 충돌이 발생하여 실패할 것이다.

이 실습에서는 이러한 실패 상황을 `block/rescue/always`로 처리하여 **nginx 실패 시 apache2로 fallback**하는 전략을 구현한다.

<br>

## 목표

웹 서버를 배포하되, **nginx 설치 실패 시 apache2로 대체**하는 fallback 전략을 구현한다. `block`, `rescue`, `always`를 활용하여 다음을 수행한다:

- **block**: nginx 설치 및 시작 시도
- **rescue**: 실패 시 apache2로 대체
- **always**: 웹 서버 종류와 무관하게 index.html 생성 및 상태 확인

> **참고**: [Blocks 공식 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_blocks.html)

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > web-server-deploy.yml
---
- hosts: tnode1
  become: yes
  tasks:
    - name: Deploy Web Server with Fallback
      block:
        - name: Install nginx
          ansible.builtin.apt:
            name: nginx
            state: present
            update_cache: yes

        - name: Start nginx
          ansible.builtin.service:
            name: nginx
            state: started
            enabled: yes

        - name: Set web server type
          ansible.builtin.set_fact:
            web_server: "nginx"

      rescue:
        - name: Print nginx installation failure
          ansible.builtin.debug:
            msg: "Nginx installation failed. Trying apache2 as fallback..."

        - name: Install apache2 as fallback
          ansible.builtin.apt:
            name: apache2
            state: present
            update_cache: yes

        - name: Start apache2
          ansible.builtin.service:
            name: apache2
            state: started
            enabled: yes

        - name: Set web server type
          ansible.builtin.set_fact:
            web_server: "apache2"

      always:
        - name: Create index.html
          ansible.builtin.copy:
            content: |
              <html>
              <head><title>Web Server Running</title></head>
              <body>
                <h1>Web Server is Running!</h1>
                <p>Server type: {{ web_server | default('unknown') }}</p>
                <p>Deployed at: {{ ansible_date_time.iso8601 }}</p>
              </body>
              </html>
            dest: /var/www/html/index.html

        - name: Check web server process
          ansible.builtin.shell: "ps aux | grep -E '(nginx|apache2)' | grep -v grep"
          register: web_status
          ignore_errors: yes

        - name: Display web server status
          ansible.builtin.debug:
            msg: "{{ web_status.stdout_lines }}"
EOT
```

**주요 구조**:
- **`become: yes`**: root 권한으로 실행 (패키지 설치 필요)
- **`set_fact`**: 변수 설정하여 always 절에서 어떤 웹 서버가 설치되었는지 표시
- **`ignore_errors`**: always 절의 프로세스 확인이 실패해도 계속 진행

<br>

## 실행

```bash
# (server) #
ansible-playbook web-server-deploy.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Install nginx] ********************************************************************
changed: [tnode1]

TASK [Start nginx] **********************************************************************
[ERROR]: Task failed: Module failed: Unable to start service nginx: Job for nginx.service failed because the control process exited with error code.
See "systemctl status nginx.service" and "journalctl -xeu nginx.service" for details.

Origin: /root/my-ansible/web-server-deploy.yml:13:11

11             update_cache: yes
12
13         - name: Start nginx
             ^ column 11

fatal: [tnode1]: FAILED! => {"changed": false, "msg": "Unable to start service nginx: Job for nginx.service failed because the control process exited with error code.\nSee \"systemctl status nginx.service\" and \"journalctl -xeu nginx.service\" for details.\n"}

TASK [Print nginx installation failure] *************************************************
ok: [tnode1] => {
    "msg": "Nginx installation failed. Trying apache2 as fallback..."
}

TASK [Install apache2 as fallback] ******************************************************
ok: [tnode1]

TASK [Start apache2] ********************************************************************
ok: [tnode1]

TASK [Set web server type] **************************************************************
ok: [tnode1]

TASK [Create index.html] ****************************************************************
changed: [tnode1]

TASK [Check web server process] *********************************************************
changed: [tnode1]

TASK [Display web server status] ********************************************************
ok: [tnode1] => {
    "msg": [
        "www-data  208183  0.0  0.1   3596  1540 ?        Ss   00:28   0:00 /usr/bin/htcacheclean -d 120 -p /var/cache/apache2/mod_cache_disk -l 300M -n",
        "root      208371  0.0  0.3   8884  4488 ?        Ss   00:29   0:00 /usr/sbin/apache2 -k start",
        "www-data  208373  0.0  0.3 1216476 5264 ?        Sl   00:29   0:00 /usr/sbin/apache2 -k start",
        "www-data  208374  0.0  0.3 1216476 5264 ?        Sl   00:29   0:00 /usr/sbin/apache2 -k start"
    ]
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=9    changed=3    unreachable=0    failed=0    skipped=0    rescued=1    ignored=0
```

tnode1에 apache2가 이미 실행 중이어서 **포트 80(HTTP 기본 포트)이 사용 중**이었기 때문이다. nginx도 기본적으로 포트 80을 사용하려고 하므로 포트 충돌이 발생하여 시작에 실패했다. 하지만 `rescue` 절이 이를 감지하고 즉시 apache2로 fallback하여 서비스를 정상적으로 제공할 수 있게 된다.


**결과 분석**:

1. **Install nginx (block)**: nginx 패키지 설치 성공 (`changed`)
2. **Start nginx (block)**: 
   - nginx 서비스 시작 실패 (`fatal: [tnode1]: FAILED!`)
   - **실패 원인**: apache2가 이미 포트 80을 사용 중이어서 nginx가 시작되지 못함
3. **Print nginx installation failure (rescue)**: rescue 절 시작, 실패 메시지 출력
4. **Install apache2 as fallback (rescue)**: apache2는 이미 설치되어 있음 (`ok`)
5. **Start apache2 (rescue)**: apache2는 이미 실행 중 (`ok`)
6. **Set web server type (rescue)**: 변수 설정 (`web_server: "apache2"`)
7. **Create index.html (always)**: 웹 페이지 생성 (`changed`)
8. **Check web server process (always)**: apache2 프로세스 확인 (`changed`)
9. **Display web server status (always)**: apache2 프로세스 목록 출력

**PLAY RECAP**:
- `ok=9`: 총 9개 작업 성공 (rescue와 always 포함)
- `changed=3`: Install nginx, Create index.html, Check web server process
- `rescued=1`: rescue 절이 실행되어 복구됨
- `failed=0`: rescue로 복구되어 최종적으로 실패 없음

**핵심**:
- block 실패 → rescue로 즉시 복구 → always는 무조건 실행
- `rescued=1`로 rescue 절이 실행되었음을 확인 가능
- 최종적으로 `failed=0`이므로 배포는 성공

<br>

## 웹 페이지 확인

배포된 웹 서버가 정상적으로 동작하는지 확인한다.

```bash
# (server) #
# 웹 페이지 확인
curl http://tnode1
```

**curl 출력**:

```html
<html>
<head><title>Web Server Running</title></head>
<body>
  <h1>Web Server is Running!</h1>
  <p>Server type: apache2</p>
  <p>Deployed at: 2026-01-17T16:06:48Z</p>
</body>
</html>
```

`web_server` 변수가 `apache2`로 설정되어 **rescue 절이 실행되었음**을 확인할 수 있다.

<br>

## 서비스 상태 확인

nginx와 apache2의 상태를 확인하여 포트 충돌 원인을 파악한다.

```bash
# (server) #
# nginx와 apache2 상태 확인
ansible -m shell -a "systemctl status nginx || systemctl status apache2" tnode1 -b
```

**출력 결과**:

```bash
tnode1 | CHANGED | rc=0 >>
× nginx.service - A high performance web server and a reverse proxy server
     Loaded: loaded (/usr/lib/systemd/system/nginx.service; enabled; preset: enabled)
     Active: failed (Result: exit-code) since Sun 2026-01-18 01:06:54 KST; 1min 40s ago
       Docs: man:nginx(8)
    ...

Jan 18 01:06:52 tnode1 nginx[211052]: nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)
Jan 18 01:06:52 tnode1 nginx[211052]: nginx: [emerg] bind() to [::]:80 failed (98: Address already in use)
...
Jan 18 01:06:54 tnode1 nginx[211052]: nginx: [emerg] still could not bind()
Jan 18 01:06:54 tnode1 systemd[1]: nginx.service: Control process exited, code=exited, status=1/FAILURE
Jan 18 01:06:54 tnode1 systemd[1]: Failed to start nginx.service - A high performance web server and a reverse proxy server.

● apache2.service - The Apache HTTP Server
     Loaded: loaded (/usr/lib/systemd/system/apache2.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-01-18 00:29:05 KST; 39min ago
       Docs: https://httpd.apache.org/docs/2.4/
   Main PID: 208371 (apache2)
      Tasks: 55 (limit: 1453)
     Memory: 5.1M (peak: 5.5M)
        CPU: 221ms
     CGroup: /system.slice/apache2.service
             ├─208371 /usr/sbin/apache2 -k start
             ├─208373 /usr/sbin/apache2 -k start
             └─208374 /usr/sbin/apache2 -k start

Jan 18 00:29:05 tnode1 systemd[1]: Starting apache2.service - The Apache HTTP Server...
Jan 18 00:29:05 tnode1 systemd[1]: Started apache2.service - The Apache HTTP Server.
```
- **nginx**: `Active: failed`, `bind() to 0.0.0.0:80 failed (98: Address already in use)` - 포트 80 사용 불가
- **apache2**: `Active: active (running)` - 정상 실행 중, 포트 80 사용 중
- **결론**: apache2가 먼저 포트 80을 점유하고 있어 nginx가 시작에 실패했지만, rescue 절이 apache2로 fallback하여 서비스는 정상 제공됨

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **핸들러**: `notify`로 호출, 변경 시에만 실행
2. **실패 무시**: `ignore_errors: yes`로 실패해도 계속 진행
3. **실패 후 핸들러**: `force_handlers: yes`로 실패해도 핸들러 실행
4. **실패 조건**: `failed_when`으로 실패 조건 직접 지정
5. **블록 오류 처리**: `block`, `rescue`, `always`로 예외 처리

<br>

핸들러와 오류 처리를 활용하면 더 견고하고 유연한 Playbook을 작성할 수 있다. Kubespray에서도 설정 변경 후 서비스 재시작, 실패 시 롤백 등에 이러한 기법을 활용한다.

<br>

다음 글에서는 롤(Role)을 활용하여 재사용 가능한 Playbook 구조를 만드는 방법을 알아본다.
