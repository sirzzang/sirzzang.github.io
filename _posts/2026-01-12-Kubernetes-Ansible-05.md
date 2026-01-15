---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 4. Playbook"
hidden: true
excerpt: "Ansible Playbook의 구조와 문법을 이해하고, 조건문을 활용한 멀티 OS 환경 관리를 실습해 보자."
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

이번 글의 목표는 **Ansible Playbook의 구조 이해와 조건문 활용**이다.

- Playbook 구조: Play → Task → Module 계층
- 문법 검사: `--syntax-check` 옵션
- 실행 전 점검: `--check` 옵션 (dry-run)
- 조건문: `when` 키워드로 OS별 분기 처리

<br>

# Playbook이란?

## 개념

Playbook은 **대상 호스트에 수행할 작업을 정의한 YAML 파일**이다. Ad-hoc 명령어가 단일 작업을 즉시 실행한다면, Playbook은 여러 작업을 순차적으로 정의하고 재사용할 수 있다.

- YAML 형식으로 작성
- 파일 확장자: `.yml` 또는 `.yaml` (둘 다 동일하게 동작)

<br>

## 구조와 용어

Playbook은 다음과 같은 계층 구조를 가진다:

```
Playbook
  └── Play (1개 이상)
        └── Task (1개 이상)
              └── Module
```

| 용어 | 설명 |
| --- | --- |
| **Playbook** | Play의 목록. 위에서 아래로 순차 실행 |
| **Play** | 특정 호스트 그룹에 대해 실행할 Task의 목록 |
| **Task** | 단일 모듈을 호출하는 작업 단위 |
| **Module** | 실제 작업을 수행하는 코드 단위 (예: `debug`, `service`, `copy`) |

<br>

## 기본 문법

```yaml
---
- hosts: all          # Play: 대상 호스트 지정
  tasks:              # Task 목록
    - name: Print message    # Task 이름 (설명용)
      debug:                 # Module 이름
        msg: Hello World     # Module 인자
```

- `---`: YAML 문서 시작
- `hosts`: 작업 대상 호스트 또는 그룹
- `tasks`: 실행할 작업 목록
- `name`: 작업 설명 (실행 시 출력됨)

<br>

## FQCN (Fully Qualified Collection Name)

모듈은 **FQCN** 형식으로 지정할 수 있다: `<namespace>.<collection>.<module>`

```yaml
# 짧은 형식 (암묵적)
- debug:
    msg: Hello

# FQCN 형식 (명시적)
- ansible.builtin.debug:
    msg: Hello
```

FQCN을 사용하면 동일한 이름의 모듈이 여러 Collection에 있을 때 어떤 것을 사용할지 명확히 지정할 수 있다.

> **참고**: `ansible.builtin`은 Ansible 기본 제공 모듈 Collection이다.

<br>

# ansible-playbook 명령어

## 기본 문법

```bash
ansible-playbook [옵션] playbook.yml
```

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `--syntax-check` | 문법 검사만 수행 (실행하지 않음) |
| `-C`, `--check` | Dry-run 모드. 실제 변경 없이 예상 결과 확인 |
| `-D`, `--diff` | 파일 변경 시 diff 출력 (`--check`와 함께 사용) |
| `-v`, `-vv`, `-vvv` | 상세 출력 (v 개수에 따라 상세도 증가) |
| `-i INVENTORY` | 인벤토리 파일 지정 |
| `-l SUBSET` | 실행 대상을 특정 호스트로 제한 |
| `-t TAGS` | 특정 태그가 붙은 Task만 실행 |
| `--list-tasks` | 실행될 Task 목록 출력 |
| `--list-hosts` | 대상 호스트 목록 출력 |

<br>

# 실습 1: Hello World

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > first-playbook.yml
---
- hosts: all
  tasks:
    - name: Print message
      debug:
        msg: Hello World
EOT
```

<br>

## 문법 검사

`--syntax-check` 옵션으로 실행 전에 문법 오류를 확인할 수 있다.

```bash
# (server) #
ansible-playbook --syntax-check first-playbook.yml
```

```
playbook: first-playbook.yml
```

오류가 없으면 Playbook 파일명만 출력된다.

<br>

### 문법 오류 예시

다음과 같이 들여쓰기가 잘못된 Playbook을 작성해 보자:

```bash
# (server) #
cat <<'EOT' > first-playbook-with-error.yml
---
- hosts: all
  tasks:
    - name: Print message
      debug:
      msg: Hello World
EOT
```

```bash
# (server) #
ansible-playbook --syntax-check first-playbook-with-error.yml
```

```
[ERROR]: conflicting action statements: debug, msg
Origin: /root/my-ansible/first-playbook-with-error.yml:4:7

2 - hosts: all
3   tasks:
4     - name: Print message
        ^ column 7
```

`msg`가 `debug` 모듈의 인자가 아니라 별도의 액션으로 해석되어 오류가 발생한다. YAML에서 들여쓰기는 매우 중요하다.

<br>

## Playbook 실행

```bash
# (server) #
ansible-playbook first-playbook.yml
```

![ansible-05-first-playbook-result]({{site.url}}/assets/images/ansible-05-first-playbook-result.png){: .align-center width="600"}

**출력 해석:**
- `PLAY [all]`: all 그룹에 대한 Play 시작
- `TASK [Gathering Facts]`: 호스트 정보 수집 (기본 동작)
- `TASK [Print message]`: 우리가 정의한 Task 실행
- `ok`: 성공, 변경 없음
- `PLAY RECAP`: 실행 결과 요약

<br>

# 실습 2: 서비스 재시작

## Playbook 작성

SSH 서비스를 재시작하는 Playbook을 작성해 보자.

```bash
# (server) #
cat <<'EOT' > restart-service.yml
---
- hosts: all
  tasks:
    - name: Restart sshd service
      ansible.builtin.service:
        name: ssh
        state: restarted
EOT
```

<br>

## service 모듈의 state

`ansible.builtin.service` 모듈은 서비스 상태를 관리한다. `state` 매개변수의 값에 따라 동작이 달라진다:

| state | 동작 | 멱등성 |
| --- | --- | --- |
| `started` | 서비스 시작 (이미 실행 중이면 무시) | O |
| `stopped` | 서비스 중지 (이미 중지 상태면 무시) | O |
| `restarted` | 서비스 재시작 (항상 실행) | X |
| `reloaded` | 설정 리로드 (항상 실행) | X |

> **참고**: `restarted`와 `reloaded`는 항상 실행되므로 멱등성이 보장되지 않는다.

<br>

## 실행 전 점검 (--check)

`--check` 옵션은 **Dry-run 모드**로, 실제 변경 없이 예상 결과를 확인할 수 있다.

```bash
# (server) #
ansible-playbook --check restart-service.yml
```

![ansible-05-restart-service-check]({{site.url}}/assets/images/ansible-05-restart-service-check.png){: .align-center width="600"}

> **참고**: `--check`는 Kubernetes의 `kubectl apply --dry-run`과 유사한 개념이다. 실제 변경 없이 "이렇게 변경될 것이다"를 미리 확인할 수 있다.

<br>

## 실행 및 오류 발생

```bash
# (server) #
ansible-playbook restart-service.yml
```

![ansible-05-restart-ssh]({{site.url}}/assets/images/ansible-05-restart-ssh.gif){: .align-center}

Ubuntu 노드(tnode1, tnode2)에서는 성공하지만, Rocky Linux 노드(tnode3)에서는 실패한다.

![ansible-05-restart-service-error]({{site.url}}/assets/images/ansible-05-restart-service-error.png){: .align-center width="600"}

- **실패 원인**: Ubuntu의 SSH 서비스명은 `ssh`이고, Rocky Linux의 SSH 서비스명은 `sshd`이다.

<br>

## 조건문으로 OS별 분기

### OS 정보 확인

`ansible.builtin.setup` 모듈로 호스트의 OS 정보를 확인할 수 있다.

```bash
# (server) #
ansible tnode1 -m ansible.builtin.setup | grep -E 'os_family|distribution"'
```

```bash
...
        "ansible_distribution": "Ubuntu",
        "ansible_os_family": "Debian",    # Ubuntu OS Family: Debian
```bash

```bash
# (server) #
ansible tnode3 -m ansible.builtin.setup | grep -E 'os_family|distribution"'
```

```bash
...
        "ansible_distribution": "Rocky",
        "ansible_os_family": "RedHat",  # Rocky OS Family: RedHat
...
```

<br>

### when 조건문

`when` 키워드를 사용하면 조건에 따라 Task 실행 여부를 결정할 수 있다.

```bash
# (server) #
cat <<'EOT' > restart-service.yml
---
- hosts: all
  tasks:
    - name: Restart SSH on Debian
      ansible.builtin.service:
        name: ssh
        state: restarted
      when: ansible_facts['os_family'] == 'Debian'

    - name: Restart SSH on RedHat
      ansible.builtin.service:
        name: sshd
        state: restarted
      when: ansible_facts['os_family'] == 'RedHat'
EOT
```

- `ansible_facts['os_family']`: Gathering Facts 단계에서 수집된 OS 계열 정보
- `when`: 조건이 true일 때만 해당 Task 실행

<br>

### 실행 결과 확인

```bash
# (server) #
ansible-playbook --check restart-service.yml
```

```
PLAY [all] *********************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Restart SSH on Debian] ***************************************************
skipping: [tnode3]
changed: [tnode1]
changed: [tnode2]

TASK [Restart SSH on RedHat] ***************************************************
skipping: [tnode1]
skipping: [tnode2]
changed: [tnode3]

PLAY RECAP *********************************************************************
tnode1                     : ok=2    changed=1    unreachable=0    failed=0    skipped=1
tnode2                     : ok=2    changed=1    unreachable=0    failed=0    skipped=1
tnode3                     : ok=2    changed=1    unreachable=0    failed=0    skipped=1
```

- `skipping`: 조건 불충족으로 건너뜀 (파란색)
- `changed`: 변경 예정 (주황색)
- `skipped=1`: 건너뛴 Task 수

실제 실행:

```bash
# (server) #
ansible-playbook restart-service.yml
```

![ansible-05-restart-service-no-error]({{site.url}}/assets/images/ansible-05-restart-service-no-error.gif)

모든 노드에서 성공적으로 SSH 서비스가 재시작된다.

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Playbook 구조 이해**: Play, Task, Module의 계층 구조
2. **문법 검사**: `--syntax-check` 옵션으로 실행 전 문법 오류 확인
3. **Dry-run**: `--check` 옵션으로 실제 변경 없이 예상 결과 확인
4. **조건문 활용**: `when` 키워드로 OS별 분기 처리

<br>

Playbook을 사용하면 여러 작업을 순차적으로 정의하고, 조건문을 통해 다양한 환경에 대응할 수 있다. 이는 Kubespray가 멀티 OS 환경에서 Kubernetes를 배포할 때 사용하는 핵심 기법이다.

<br>

다음 글에서는 변수와 템플릿을 활용하여 더 유연한 Playbook을 작성하는 방법을 알아본다.
