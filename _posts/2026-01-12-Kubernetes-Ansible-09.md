---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 8. 조건문"
excerpt: "Ansible 조건문(when)을 활용하여 특정 조건에서만 작업을 실행하는 방법을 실습해 보자."
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

이번 글의 목표는 **Ansible 조건문(when)의 활용법 이해**다.

- 조건문 기본: `when` 키워드로 조건부 실행
- 조건 연산자: `==`, `!=`, `in`, `is defined` 등
- 복수 조건문: `and`, `or` 연산자
- 반복문과 조건문 조합: `loop` + `when`

<br>

# 조건문이란?

## 개념

조건문을 사용하면 **특정 조건이 충족될 때만 작업을 실행**할 수 있다. 예를 들어 호스트의 운영체제 종류에 따라 다른 패키지를 설치하거나, 특정 서비스가 실행 중일 때만 작업을 수행하는 식이다. 조건문을 사용할 때에는 플레이 변수, 작업 변수, 팩트 등을 사용할 수 있다.

> **참고**: [Ansible Conditionals 공식 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_conditionals.html)

<br>

## 기본 문법

```yaml
- name: Task with condition
  ansible.builtin.모듈:
    옵션: 값
  when: 조건식
```

- `when`: 조건을 지정하는 키워드
- 조건이 **true**면 작업 실행
- 조건이 **false**면 작업 건너뜀 (skipping)

<br>

## 기본 사용법

가장 간단한 조건문은 Boolean 변수(`true`/`false`)를 사용하는 것이다.

```bash
# (server) #
cat <<'EOT' > when_task.yml
---
- hosts: localhost
  vars:
    run_my_task: true
  tasks:
    - name: echo message
      ansible.builtin.shell: "echo test"
      when: run_my_task
      register: result

    - name: Show result
      ansible.builtin.debug:
        var: result
EOT
```

**실행**:

```bash
# (server) #
ansible-playbook when_task.yml
```

`run_my_task` 변수가 `true`이므로 "echo message" task가 실행된다.

실행 결과:

```bash
PLAY [localhost] *******************************************************************

TASK [Gathering Facts] *************************************************************
ok: [localhost]

TASK [echo message] ****************************************************************
changed: [localhost]

TASK [show result] *****************************************************************
ok: [localhost] => {
    "result": {
        "changed": true,
        "cmd": "echo test",
        "delta": "0:00:00.001332",
        "end": "2026-01-17 22:56:39.465789",
        "failed": false,
        "msg": "",
        "rc": 0,
        "start": "2026-01-17 22:56:39.464457",
        "stderr": "",
        "stderr_lines": [],
        "stdout": "test",
        "stdout_lines": [
            "test"
        ]
    }
}

PLAY RECAP *************************************************************************
localhost                  : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **"echo message" task**: `when: run_my_task` 조건이 `true`이므로 실행됨 (`changed: [localhost]`)
- **"show result" task**: `register`로 저장된 결과가 출력됨 (stdout: "test")
- **PLAY RECAP**: `ok=3`, `changed=1` - 조건을 만족하여 정상 실행

<br>

**false로 변경 후 실행**:

`run_my_task: false`로 변경하면 해당 Task가 건너뛰어진다 (skipping).

```bash
# (server) #
# when_task.yml에서 run_my_task: false로 변경 후 실행
ansible-playbook when_task.yml
```

실행 결과:

```bash
PLAY [localhost] *******************************************************************

TASK [Gathering Facts] *************************************************************
ok: [localhost]

TASK [echo message] ****************************************************************
skipping: [localhost]

TASK [show result] *****************************************************************
ok: [localhost] => {
    "result": {
        "changed": false,
        "false_condition": "run_my_task",
        "skip_reason": "Conditional result was False",
        "skipped": true
    }
}

PLAY RECAP *************************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **"echo message" task**: `when: run_my_task` 조건이 `false`이므로 건너뜀 (`skipping: [localhost]`)
- **"show result" task**: `register`로 저장된 결과에 skip 정보가 담김
  - `"skipped": true`: task가 건너뛰어졌음
  - `"skip_reason": "Conditional result was False"`: 조건이 false였기 때문
- **PLAY RECAP**: `ok=2`, `skipped=1` - 조건을 만족하지 못하여 1개 task가 건너뛰어짐

## 주요 조건 연산자

| **연산자** | **설명** | **예시** |
| --- | --- | --- |
| `==` | 같으면 true | `max_memory == 512` : max_memory 값이 512와 같다면 true<br>`ansible_facts['machine'] == "x86_64"` : ansible_facts['machine'] 값이 x86_64와 같으면 true |
| `!=` | 다르면 true | `min_memory != 512` : min_memory 값이 512와 같지 않으면 true |
| `<` | 미만 | `min_memory < 128` : min_memory 값이 128보다 작으면 true |
| `>` | 초과 | `min_memory > 256` : min_memory 값이 256보다 크면 true |
| `<=` | 이하 | `min_memory <= 256` : min_memory 값이 256보다 작거나 같으면 true |
| `>=` | 이상 | `min_memory >= 512` : min_memory 값이 512보다 크거나 같으면 true |
| `in` | 포함되면 true | `ansible_facts['distribution'] in supported_distros` : ansible_facts['distribution']의 값이 supported_distros 변수에 있으면 true |
| `is defined` | 변수가 정의되면 true | `min_memory is defined` : min_memory 변수가 있으면 true |
| `is not defined` | 변수가 미정의면 true | `min_memory is not defined` : min_memory 변수가 없으면 true |
| `not` | 조건 부정 | `not memory_available` : memory_available이 false면 true |
| `and` | 그리고 (여러 조건 조합) | `조건1 and 조건2` : 두 조건이 모두 true일 때 true |
| `or` | 또는 (여러 조건 조합) | `조건1 or 조건2` : 둘 중 하나라도 true면 true |


<br>

# 실습 1: 조건 연산자

## in 연산자 사용

OS 종류에 따라 작업을 수행하는 예제이다. `ansible_facts['distribution']` 값이 `Ubuntu`이거나 `CentOS`인 경우에만 출력한다.

```bash
# (server) #
cat <<'EOT' > check-os.yml
---
- hosts: all
  vars:
    supported_distros:
      - Ubuntu
      - CentOS
  tasks:
    - name: Print supported os
      ansible.builtin.debug:
        msg: "This {{ ansible_facts['distribution'] }} need to use apt"
      when: ansible_facts['distribution'] in supported_distros
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Print supported os] **********************************************************
ok: [tnode1] => {
    "msg": "This Ubuntu need to use apt"
}
ok: [tnode2] => {
    "msg": "This Ubuntu need to use apt"
}
skipping: [tnode3]

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **tnode1, tnode2 (Ubuntu)**: `ansible_facts['distribution']`이 `supported_distros`에 포함되어 메시지 출력 (`ok=2`)
- **tnode3 (Rocky)**: `ansible_facts['distribution']`이 `supported_distros`에 없어서 건너뜀 (`skipping`, `ok=1`, `skipped=1`)
- `in` 연산자를 사용하여 특정 OS 목록에 포함된 경우에만 작업 실행

<br>

# 실습 2: 복수 조건문

## or 연산자

여러 조건 중 **하나라도 참**이면 작업을 수행하고자 할 때 `or` 연산자를 사용한다.

CentOS **또는** Ubuntu일 경우 작업을 수행하는 예제이다. `or` 연산자로 두 조건을 연결하여, 둘 중 하나라도 만족하면 OS 정보를 출력한다.

```bash
# (server) #
cat <<'EOT' > check-os1.yml
---
- hosts: all
  tasks:
    - name: Print os type
      ansible.builtin.debug:
        msg: "OS Type {{ ansible_facts['distribution'] }}"
      when: ansible_facts['distribution'] == "CentOS" or ansible_facts['distribution'] == "Ubuntu"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os1.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Print os type] ***************************************************************
ok: [tnode1] => {
    "msg": "OS Type Ubuntu"
}
skipping: [tnode3]
ok: [tnode2] => {
    "msg": "OS Type Ubuntu"
}

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **tnode1, tnode2 (Ubuntu)**: `ansible_facts['distribution'] == "Ubuntu"`가 true이므로 메시지 출력 (`ok=2`)
- **tnode3 (Rocky)**: CentOS도 아니고 Ubuntu도 아니므로 두 조건 모두 false, 건너뜀 (`skipped=1`)
- `or` 연산자로 여러 조건 중 하나라도 만족하면 실행

<br>

## and 연산자

여러 조건이 **모두 참**이어야 작업을 수행하고자 할 때 `and` 연산자를 사용한다.

Ubuntu **이고** 버전이 24.04일 경우에만 작업을 수행하는 예제이다. `and` 연산자로 두 조건을 연결하여, 두 조건이 모두 만족해야만 OS 정보를 출력한다.

```bash
# (server) #
cat <<'EOT' > check-os2.yml
---
- hosts: all
  tasks:
    - name: Print os type
      ansible.builtin.debug:
        msg: >-
          OS Type: {{ ansible_facts['distribution'] }}
          OS Version: {{ ansible_facts['distribution_version'] }}
      when: ansible_facts['distribution'] == "Ubuntu" and ansible_facts['distribution_version'] == "24.04"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os2.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Print os type] ***************************************************************
ok: [tnode1] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}
ok: [tnode2] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}
skipping: [tnode3]

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **tnode1, tnode2 (Ubuntu 24.04)**: 두 조건 모두 true (`distribution == "Ubuntu"` **and** `distribution_version == "24.04"`)이므로 메시지 출력 (`ok=2`)
- **tnode3 (Rocky 9.6)**: Ubuntu가 아니므로 첫 번째 조건이 false, 건너뜀 (`skipped=1`)
- `and` 연산자로 **모든 조건이 만족**해야만 실행

<br>

## and 연산자 - 목록 형태

`and` 조건은 **목록 형태**로도 표현할 수 있다. 각 항목이 모두 true여야 작업이 실행된다.

`when` 아래에 조건들을 리스트 형태(`-`)로 나열하는 방식이다. 이 방식은 `and` 키워드를 사용하지 않고도 동일한 동작을 하며, 조건이 많을 때 가독성이 더 좋다.

```bash
# (server) #
cat <<'EOT' > check-os3.yml
---
- hosts: all
  tasks:
    - name: Print os type
      ansible.builtin.debug:
        msg: >-
          OS Type: {{ ansible_facts['distribution'] }}
          OS Version: {{ ansible_facts['distribution_version'] }}
      when:
        - ansible_facts['distribution'] == "Ubuntu"
        - ansible_facts['distribution_version'] == "24.04"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os3.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Print os type] ***************************************************************
ok: [tnode1] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}
skipping: [tnode3]
ok: [tnode2] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **tnode1, tnode2 (Ubuntu 24.04)**: 목록의 모든 조건이 true이므로 메시지 출력 (`ok=2`)
- **tnode3 (Rocky 9.6)**: Ubuntu가 아니므로 첫 번째 조건이 false, 건너뜀 (`skipped=1`)
- 목록 형태의 `when`은 `and` 연산자와 동일하게 동작하며, 조건이 많을 때 가독성이 더 좋음

<br>

## and와 or 조합

더 복잡한 조건식을 만들기 위해 `and`와 `or`를 **조합**할 수 있다. 괄호 `()`를 사용하여 조건의 우선순위를 명확히 지정한다.

Rocky 9.6 **또는** Ubuntu 24.04인 경우 작업을 수행하는 예제이다. 각 OS는 버전까지 정확히 일치해야 하므로 `and`로 묶고, 두 조합 중 하나라도 만족하면 되므로 `or`로 연결한다.

```bash
# (server) #
cat <<'EOT' > check-os4.yml
---
- hosts: all
  tasks:
    - name: Print os type
      ansible.builtin.debug:
        msg: >-
          OS Type: {{ ansible_facts['distribution'] }}
          OS Version: {{ ansible_facts['distribution_version'] }}
      when: >
        ( ansible_facts['distribution'] == "Rocky" and
          ansible_facts['distribution_version'] == "9.6" )
        or
        ( ansible_facts['distribution'] == "Ubuntu" and
          ansible_facts['distribution_version'] == "24.04" )
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os4.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode2]
ok: [tnode1]
ok: [tnode3]

TASK [Print os type] ***************************************************************
ok: [tnode1] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}
ok: [tnode2] => {
    "msg": "OS Type: Ubuntu OS Version: 24.04"
}
ok: [tnode3] => {
    "msg": "OS Type: Rocky OS Version: 9.6"
}

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **tnode1, tnode2 (Ubuntu 24.04)**: `(distribution == "Ubuntu" and distribution_version == "24.04")`가 true이므로 메시지 출력 (`ok=2`)
- **tnode3 (Rocky 9.6)**: `(distribution == "Rocky" and distribution_version == "9.6")`이 true이므로 메시지 출력 (`ok=2`)
- **모든 노드 실행**: `or` 연산자로 인해 둘 중 하나만 만족하면 실행되며, 각 노드가 해당 조건을 만족하므로 모두 실행됨 (`skipped=0`)
- 괄호 `()`로 `and` 조건을 먼저 평가하고, `or`로 두 그룹을 연결

<br>

# 실습 3: 반복문과 조건문

## 개념

`loop`와 `when`을 함께 사용하면 반복 항목 중 조건을 만족하는 경우에만 작업을 수행할 수 있다.

<br>

## Playbook 작성

마운트 정보 중 루트(`/`) 디렉터리이고, 가용 용량이 **300MB** (300,000,000 bytes) 이상인 경우만 출력한다.

```bash
# (server) #
cat <<'EOT' > check-mount.yml
---
- hosts: db
  tasks:
    - name: Print Root Directory Size
      ansible.builtin.debug:
        msg: "Directory {{ item.mount }} size is {{ item.size_available }}"
      loop: "{{ ansible_facts['mounts'] }}"
      when: item['mount'] == "/" and item['size_available'] > 300000000
EOT
```

- `loop`: `ansible_facts['mounts']` (마운트 정보 배열) - 각 마운트 포인트별로 반복
- `when`: 두 조건을 모두 만족하는 경우만 출력
  - `item['mount'] == "/"`: 마운트 포인트가 루트 디렉터리
  - `item['size_available'] > 300000000`: 가용 용량이 300MB 초과

<br>

## 실행

```bash
# (server) #
ansible-playbook check-mount.yml
```

실행 결과:

```bash
PLAY [db] **************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode3]

TASK [Print Root Directory Size] ***************************************************
ok: [tnode3] => (item={'mount': '/', ..., 'size_available': 61805617152, ...}) => {
    "msg": "Directory / size is 61805617152"
}
skipping: [tnode3] => (item={'mount': '/boot/efi', ..., 'size_available': 620228608, ...})

PLAY RECAP *************************************************************************
tnode3                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **첫 번째 항목 (`/`)**: 가용 용량 약 61.8 GB (61805617152 bytes)로 조건 만족, 출력됨
- **두 번째 항목 (`/boot/efi`)**: 가용 용량 약 591 MB (620228608 bytes)이지만 마운트 포인트가 `/`가 아니므로 건너뜀 (`skipping`)
- `loop`와 `when`을 조합하여 **반복 항목 중 조건을 만족하는 경우만** 선택적으로 실행

<br>

# 실습 4: register와 조건문

## 개념

`register`로 저장한 작업 결과를 `when` 조건에서 활용할 수 있다.

이전 task의 실행 결과를 변수에 저장하고, 그 결과값에 따라 다음 task의 실행 여부를 결정할 수 있다. 예를 들어 명령어 실행 결과(`stdout`), 반환 코드(`rc`), 실행 여부(`changed`) 등을 조건으로 사용할 수 있다.

> **참고**: [command 모듈 공식 문서](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/command_module.html)

<br>

## Playbook 작성

rsyslog 서비스 상태를 확인하고, **active인 경우에만** 메시지를 출력하는 예제이다.

1. `command` 모듈로 `systemctl is-active rsyslog` 명령어를 실행하고 결과를 `result` 변수에 저장
2. `result.stdout` 값이 "active"인 경우에만 debug 메시지 출력

```bash
# (server) #
cat <<'EOT' > register-when.yml
---
- hosts: all
  tasks:
    - name: Get rsyslog service status
      ansible.builtin.command: systemctl is-active rsyslog
      register: result

    - name: Print rsyslog status
      ansible.builtin.debug:
        msg: "Rsyslog status is {{ result.stdout }}"
      when: result.stdout == "active"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook register-when.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode2]
ok: [tnode1]
ok: [tnode3]

TASK [Get rsyslog service status] **************************************************
changed: [tnode2]
changed: [tnode1]
changed: [tnode3]

TASK [Print rsyslog status] ********************************************************
ok: [tnode1] => {
    "msg": "Rsyslog status is active"
}
ok: [tnode2] => {
    "msg": "Rsyslog status is active"
}
ok: [tnode3] => {
    "msg": "Rsyslog status is active"
}

PLAY RECAP *************************************************************************
tnode1                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **Get rsyslog service status**: 모든 노드에서 명령어 실행 (`changed`) - `command` 모듈은 항상 `changed` 상태
- **Print rsyslog status**: 모든 노드에서 `result.stdout == "active"`이므로 메시지 출력 (`ok`)
- **PLAY RECAP**: 모든 노드에서 3개 task 성공 (`ok=3`), 1개 task 상태 변경 (`changed=1`)
- `register`와 `when`을 조합하여 **이전 task 결과에 따라** 다음 task를 조건부 실행

<br>

# 실습 5: OS + 호스트명 조건

**Ubuntu** OS이면서 fqdn이 **tnode1**인 경우, `debug` 모듈을 사용하여 OS 정보와 fqdn 정보를 출력한다.

여러 조건을 조합하여 특정 호스트만 선택하는 방법을 연습한다. 목록 형태의 `when`을 사용하여 두 조건이 모두 만족하는 경우에만 작업을 수행한다.

> **힌트**: `ansible_facts['distribution']`, `ansible_facts['fqdn']`

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > check-os-with-fqdn.yml
---
- hosts: all
  tasks:
    - name: Print os and fqdn
      ansible.builtin.debug:
        msg: >-
          OS Distribution: {{ ansible_facts['distribution'] }}
          FQDN: {{ ansible_facts['fqdn'] }}
      when:
        - ansible_facts['distribution'] == "Ubuntu"
        - ansible_facts['fqdn'] == 'tnode1'
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook check-os-with-fqdn.yml
```

실행 결과:

```bash
PLAY [all] *************************************************************************

TASK [Gathering Facts] *************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Print os and fqdn] ***********************************************************
ok: [tnode1] => {
    "msg": "OS Distribution: Ubuntu FQDN: tnode1"
}
skipping: [tnode2]
skipping: [tnode3]

PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- **tnode1 (Ubuntu, fqdn: tnode1)**: 두 조건 모두 만족하여 메시지 출력 (`ok=2`)
- **tnode2 (Ubuntu, fqdn: tnode2)**: Ubuntu이지만 fqdn이 tnode1이 아니므로 건너뜀 (`skipped=1`)
- **tnode3 (Rocky, fqdn: tnode3)**: Ubuntu가 아니므로 건너뜀 (`skipped=1`)
- 목록 형태의 `when`으로 **모든 조건**이 만족하는 호스트만 선택

<br>

# 실습 6: 반복문 + 조건문 조합

## 목표

반복문과 조건문을 함께 활용하는 Playbook을 작성한다.

> **참고**: [Using conditionals in loops](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_conditionals.html#using-conditionals-in-loops)

<br>

## Playbook 작성

1부터 10까지 숫자 중 **홀수**와 **짝수**를 각각 필터링하여 출력하는 예제이다.

반복문(`loop`)으로 숫자를 순회하면서, 조건문(`when`)으로 홀수(`% 2 == 1`)와 짝수(`% 2 == 0`)를 구분한다.

```bash
# (server) #
cat <<'EOT' > loop-with-when.yml
---
- hosts: localhost
  vars:
    nums:
      - 1
      - 2
      - 3
      - 4
      - 5
      - 6
      - 7
      - 8
      - 9
      - 10
  tasks:
    - name: Print odd num
      ansible.builtin.debug:
        msg: "{{ item }} is an odd number"
      loop: "{{ nums }}"
      when: item % 2 == 1
    
    - name: Print even num
      ansible.builtin.debug:
        msg: "{{ item }} is an even number"
      loop: "{{ nums }}"
      when: item % 2 == 0
EOT
```

<br>

### 주의: `when` 절에서 {% raw %}`{{ }}`{% endraw %} 사용하지 않기
```yaml
# 잘못됨 - YAML 파싱 에러 발생
when: {{ item }} % 2 == 1 
```
```yaml
# 올바른 사용
when: item % 2 == 1  
```

`when` 절은 이미 Jinja2 템플릿 컨텍스트이므로 {% raw %}`{{ }}`{% endraw %}를 사용하지 않는다.

- **모듈 파라미터** (`msg`, `name` 등): {% raw %}`"{{ item }}"`{% endraw %} 필요
- **`when` 조건절**: {% raw %}`{{ }}`{% endraw %} 불필요, 변수명만 사용

<br>

## 실행

```bash
# (server) #
ansible-playbook loop-with-when.yml
```

실행 결과:

```bash
PLAY [localhost] *******************************************************************

TASK [Gathering Facts] *************************************************************
ok: [localhost]

TASK [Print odd num] ***************************************************************
ok: [localhost] => (item=1) => {
    "msg": "1 is an odd number"
}
skipping: [localhost] => (item=2) 
... 
ok: [localhost] => (item=9) => {
    "msg": "9 is an odd number"
}
skipping: [localhost] => (item=10) 

TASK [Print even num] **************************************************************
skipping: [localhost] => (item=1) 
ok: [localhost] => (item=2) => {
    "msg": "2 is an even number"
}
...
skipping: [localhost] => (item=9) 
ok: [localhost] => (item=10) => {
    "msg": "10 is an even number"
}

PLAY RECAP *************************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **Print odd num**: 홀수(1, 3, 5, 7, 9)만 출력, 짝수는 `skipping`
- **Print even num**: 짝수(2, 4, 6, 8, 10)만 출력, 홀수는 `skipping`
- **PLAY RECAP**: 3개 task 모두 성공 (`ok=3`), 상태 변경 없음 (`changed=0`)
- `loop`와 `when`을 조합하여 **반복 항목 중 조건을 만족하는 경우만** 선택적으로 실행

<br>

## 개선: range 필터 활용

위 예제는 숫자를 하나씩 나열했지만, **`range` 필터**를 사용하면 더 간결하고 확장 가능하게 작성할 수 있다.

### Playbook 작성

`vars`에서 숫자를 직접 나열하는 대신, `loop`에서 `range` 필터를 사용하여 숫자 범위를 자동으로 생성한다.

```bash
# (server) #
cat <<'EOT' > loop-with-when2.yml
---
- hosts: localhost
  tasks:
    - name: Print odd num
      ansible.builtin.debug:
        msg: "{{ item }} is an odd number"
      loop: "{{ range(1, 11) | list }}"
      when: item % 2 == 1
    
    - name: Print even num
      ansible.builtin.debug:
        msg: "{{ item }} is an even number"
      loop: "{{ range(1, 11) | list }}"
      when: item % 2 == 0
EOT
```

### 장점

- **간결성**: 10줄의 숫자 나열 → `range(1, 11) | list` 한 줄로 축약
- **확장성**: 숫자 범위를 쉽게 변경 가능 (예: `range(1, 101)`로 1~100)
- **유지보수**: 하드코딩된 리스트 수정 불필요
- **가독성**: 의도가 명확함 ("1부터 10까지")

### 실행

```bash
# (server) #
ansible-playbook loop-with-when2.yml
```

실행 결과는 동일하다:

```bash
PLAY [localhost] *******************************************************************

TASK [Gathering Facts] *************************************************************
ok: [localhost]

TASK [Print odd num] ***************************************************************
ok: [localhost] => (item=1) => {
    "msg": "1 is an odd number"
}
skipping: [localhost] => (item=2) 
ok: [localhost] => (item=3) => {
    "msg": "3 is an odd number"
}
...

TASK [Print even num] **************************************************************
skipping: [localhost] => (item=1) 
ok: [localhost] => (item=2) => {
    "msg": "2 is an even number"
}
...

PLAY RECAP *************************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- 실행 결과는 기존과 동일하지만, 코드가 훨씬 간결하고 확장 가능
- `range` 필터는 **08편(반복문)**에서 학습한 내용을 조건문과 함께 활용한 예시

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **조건문 기본**: `when` 키워드로 조건부 작업 실행
2. **조건 연산자**: `==`, `!=`, `in`, `is defined` 등 활용
3. **복수 조건문**: `and`, `or` 연산자로 복잡한 조건 표현
4. **반복문과 조건문**: `loop` + `when` 조합

<br>

조건문을 활용하면 동일한 Playbook으로 다양한 환경에 대응할 수 있다. Kubespray에서도 OS 종류, 버전, 아키텍처 등에 따라 조건문을 활용하여 적절한 작업을 수행한다.

<br>

다음 글에서는 핸들러(Handler)를 활용하여 변경 시에만 특정 작업을 트리거하는 방법을 알아본다.
