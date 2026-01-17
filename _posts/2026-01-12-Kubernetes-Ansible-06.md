---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 5. 변수"
hidden: true
excerpt: "Ansible 변수의 종류와 우선순위를 이해하고, 다양한 변수 선언 방법을 실습해 보자."
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

이번 글의 목표는 **Ansible 변수의 종류와 우선순위 이해**다.

- 변수 종류: 그룹 변수, 호스트 변수, 플레이 변수, 추가 변수, 작업 변수
- 우선순위: 추가 변수 > 플레이 변수 > 호스트 변수 > 그룹 변수
- 변수 참조: {% raw %}`{{ 변수명 }}`{% endraw %} (Jinja2 템플릿 문법)
- 작업 변수: `register` 키워드로 Task 결과 저장

<br>

# 변수란?

## 개념

변수는 Playbook에서 **재사용 가능한 값을 저장**하는 방법이다. 변수를 활용하면 동일한 Playbook을 다양한 환경에서 재사용할 수 있다.

**활용 예시:**
- 생성할 사용자 이름
- 설치할 패키지 이름
- 서비스 이름
- 파일 경로

<br>

## 변수 종류

| 종류 | 설명 | 선언 위치 |
| --- | --- | --- |
| **그룹 변수** | 호스트 그룹에 적용되는 변수 | 인벤토리 `[그룹명:vars]` |
| **호스트 변수** | 특정 호스트에만 적용되는 변수 | 인벤토리 호스트 라인 |
| **플레이 변수** | Playbook 내에서 선언하는 변수 | Playbook `vars:` 또는 `vars_files:` |
| **추가 변수** | 실행 시 전달하는 변수 | `-e` 옵션 |
| **작업 변수** | Task 실행 결과를 저장하는 변수 | `register:` |

<br>

## 변수 우선순위

동일한 이름의 변수가 여러 곳에서 선언되면, 다음 순서로 우선순위가 적용된다:

```
추가 변수 (-e) > 플레이 변수 > 호스트 변수 > 그룹 변수
   (높음)                                      (낮음)
```

> **참고**: 추가 변수의 우선순위가 가장 높은 이유
>
> 실행 시점에 값을 덮어쓸 수 있어야 유연한 자동화가 가능하다. 예를 들어, 테스트 환경에서는 `user=test`, 운영 환경에서는 `user=admin`처럼 같은 Playbook을 다른 값으로 실행할 수 있다.

<br>

## 변수 참조 문법

변수는 **Jinja2 템플릿 문법**인 {% raw %}`{{ }}`{% endraw %} (겹중괄호)로 참조한다.

> **참고**: Jinja2란?
>
> [Jinja2](https://jinja.palletsprojects.com/)는 Python 기반의 템플릿 엔진이다. Ansible은 Jinja2를 사용하여 변수 치환, 조건문, 반복문 등을 처리한다.
> - {% raw %}`{{ }}`{% endraw %}: 변수 출력
> - {% raw %}`{% %}`{% endraw %}: 제어문 (조건문, 반복문)
> - {% raw %}`{# #}`{% endraw %}: 주석

```yaml
- name: Create User {{ user }}
  ansible.builtin.user:
    name: "{{ user }}"
    state: present
```

<br>

# 실습 1: 그룹 변수

## 인벤토리에 그룹 변수 선언

인벤토리 파일에 `[그룹명:vars]` 섹션을 추가하여 그룹 변수를 선언한다.

```bash
# (server) #
cat <<'EOT' > inventory
[web]
tnode1 ansible_python_interpreter=/usr/bin/python3
tnode2 ansible_python_interpreter=/usr/bin/python3

[db]
tnode3 ansible_python_interpreter=/usr/bin/python3

[all:children]
web
db

[all:vars]
user=ansible
EOT
```

- `[all:vars]`: `all` 그룹에 적용되는 변수 섹션
- `user=ansible`: 변수명=값 형식으로 선언

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > create-user.yml
---
- hosts: all
  tasks:
    - name: Create User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: present
EOT
```

- `ansible.builtin.user`: 시스템 사용자를 관리하는 모듈
- `state: present`: 사용자가 존재하도록 보장 (없으면 생성)

<br>

## 실행 및 확인

```bash
# (server) #
ansible-playbook create-user.yml
```

```
TASK [Create User ansible] *****************************************************
changed: [tnode1]
changed: [tnode2]
changed: [tnode3]
```

실행 시, Task 이름에서 {% raw %}`{{ user }}`{% endraw %}가 `ansible`로 치환된 것을 확인할 수 있다.

![ansible-06-create-user-result]({{site.url}}/assets/images/ansible-06-create-user-result.gif){: .align-center}

<br>

실제로 그룹 변수에 지정한 `ansible` 사용자가 생성되었는지 확인해 보자.
```bash
# (server) #
# 사용자 생성 확인
for i in {1..3}; do echo ">> tnode$i <<"; ssh tnode$i tail -n 1 /etc/passwd; done
```

```
>> tnode1 <<
ansible:x:1001:1001::/home/ansible:/bin/sh
>> tnode2 <<
ansible:x:1001:1001::/home/ansible:/bin/sh
>> tnode3 <<
ansible:x:1001:1001::/home/ansible:/bin/bash
```

<br>

### 멱등성 확인

멱등성이 보장되는지 확인해 보자. 아까 실행한 상태 그대로 한 번 더 실행하면 된다.

```bash
# (server) #
# 한번 더 실행
ansible-playbook create-user.yml
```

```
TASK [Create User ansible] *****************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]
```

![ansible-06-create-user-result-idempotency]({{site.url}}/assets/images/ansible-06-create-user-result-idempotency.gif){: .align-center}

이미 사용자가 존재하므로 `changed`가 아닌 `ok`가 출력된다. (`user` 모듈은 멱등성을 보장한다)

<br>

# 실습 2: 호스트 변수

**호스트 변수 > 그룹 변수**임을 확인한다.


## 인벤토리에 호스트 변수 선언

호스트 라인에 직접 변수를 선언하면 해당 호스트에만 적용된다.

```bash
# (server) #
cat <<'EOT' > inventory
[web]
tnode1 ansible_python_interpreter=/usr/bin/python3
tnode2 ansible_python_interpreter=/usr/bin/python3

[db]
tnode3 ansible_python_interpreter=/usr/bin/python3 user=ansible1

[all:children]
web
db

[all:vars]
user=ansible
EOT
```

- `tnode3` 라인에 `user=ansible1` 추가
- `tnode3`에서는 호스트 변수 `ansible1`이 그룹 변수 `ansible`보다 우선

<br>

## Playbook 작성 및 실행


```bash
# (server) #
cat <<'EOT' > create-user1.yml
---
- hosts: db
  tasks:
    - name: Create User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: present
EOT
```

```bash
# (server) #
ansible-playbook create-user1.yml
```

```
PLAY [db] **********************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode3]

TASK [Create User ansible1] ****************************************************
changed: [tnode3]

PLAY RECAP *********************************************************************
tnode3                     : ok=2    changed=1    unreachable=0    failed=0 
```

![ansible-06-create-user1-result]({{site.url}}/assets/images/ansible-06-create-user1-result.gif){: .align-center}

`db` 그룹에 지정된 호스트 `tnode3`에서 호스트 변수 `ansible1`이 적용되어 사용자 `ansible1`이 생성된다.

<br>

# 실습 3: 플레이 변수

**플레이 변수 > 호스트 변수 > 그룹 변수** 임을 확인한다.

## Playbook 내 변수 선언

Playbook의 `vars:` 섹션에 변수를 선언할 수 있다.

```bash
# (server) #
cat <<'EOT' > create-user2.yml
---
- hosts: all
  vars:
    user: ansible2
  tasks:
    - name: Create User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: present
EOT
```

<br>

## 실행 및 우선순위 확인

```bash
# (server) #
ansible-playbook create-user2.yml
```

```
TASK [Create User ansible2] ****************************************************
changed: [tnode1]
changed: [tnode2]
changed: [tnode3]
```

![ansible-06-create-user2-result]({{site.url}}/assets/images/ansible-06-create-user2-result.gif){: .align-center}

세 노드 모두에서 `ansible2` 사용자를 생성하는 태스크가 실행되었다.
- `tnode1`, `tnode2`: 그룹 변수 `ansible` → 플레이 변수 `ansible2`로 덮어씀
- `tnode3`: 호스트 변수 `ansible1` → 플레이 변수 `ansible2`로 덮어씀

```bash
for i in {1..3}; do echo ">> tnode$i <<"; ssh tnode$i tail -n 3 /etc/passwd; echo; done
```
```bash
>> tnode1 <<
vboxadd:x:999:1::/var/run/vboxadd:/bin/false
ansible:x:1001:1001::/home/ansible:/bin/sh
ansible2:x:1002:1002::/home/ansible2:/bin/sh # 생성

>> tnode2 <<
vboxadd:x:999:1::/var/run/vboxadd:/bin/false
ansible:x:1001:1001::/home/ansible:/bin/sh
ansible2:x:1002:1002::/home/ansible2:/bin/sh # 생성

>> tnode3 <<
ansible:x:1001:1001::/home/ansible:/bin/bash
ansible1:x:1002:1002::/home/ansible1:/bin/bash
ansible2:x:1003:1003::/home/ansible2:/bin/bash # 생성
```

<br>

## 변수 파일 분리

변수를 별도 파일로 분리하여 관리할 수 있다.

```bash
# (server) #
mkdir -p vars
echo "user: ansible3" > vars/users.yml
```

```bash
# (server) #
cat <<'EOT' > create-user3.yml
---
- hosts: all
  vars_files:
    - vars/users.yml
  tasks:
    - name: Create User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: present
EOT
```

- `vars_files`: 외부 YAML 파일에서 변수를 불러옴
- 변수 파일을 분리하면 환경별 설정 관리가 용이함

```bash
# (server) #
ansible-playbook create-user3.yml
```

```
TASK [Create User ansible3] ****************************************************
changed: [tnode1]
changed: [tnode2]
changed: [tnode3]
```

![ansible-06-create-user3-result]({{site.url}}/assets/images/ansible-06-create-user3-result.gif){: .align-center}

모든 노드에서 플레이 변수로 지정한 `ansible3`을 생성하는 태스크가 실행되었다.



<br>

# 실습 4: 추가 변수

**추가 변수(-e) > 플레이 변수(vars_files)** 임을 확인한다.

## -e 옵션으로 변수 전달

실행 시 `-e` (또는 `--extra-vars`) 옵션으로 변수를 전달할 수 있다.

```bash
# (server) #
ansible-playbook -e user=ansible4 create-user3.yml
```

```
TASK [Create User ansible4] ****************************************************
changed: [tnode1]
changed: [tnode2]
changed: [tnode3]
```

![ansible-06-create-user3-extra-var-result]({{site.url}}/assets/images/ansible-06-create-user3-extra-var-result.gif){: .align-center}

`vars_files`에서 `ansible3`으로 선언했지만, `-e` 옵션의 `ansible4`가 우선 적용된다.



<br>

# 실습 5: 작업 변수 (register)

## 개념

`register` 키워드를 사용하면 **Task 실행 결과를 변수에 저장**할 수 있다. 저장된 결과는 후속 Task에서 참조할 수 있다.

**활용 예시:**
- 명령 실행 결과를 확인하여 조건 분기
- 생성된 리소스 정보를 다음 Task에서 사용
- 디버깅을 위한 결과 출력

> 참고: 실무 활용 예
>
> 클라우드 시스템에 VM을 생성한다고 가정하자. 이를 위해서는 네트워크나 운영체제 이미지 등 가상 자원이 필요하다. 이 때, **가상 자원을 조회하고, 조회한 결과를 가지고** VM을 생성하고자 한다면 작업 변수를 사용하면 된다.

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > create-user4.yml
---
- hosts: db
  tasks:
    - name: Create User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: present
      register: result # result 변수에 저장

    - name: Print result
      ansible.builtin.debug:
        var: result # result 변수에 저장한 값 출력
EOT
```

- `register: result`: Task 실행 결과를 `result` 변수에 저장
- `debug` 모듈의 `var`: 변수 내용을 출력

> **참고**: `debug` 모듈
>
> `ansible.builtin.debug` 모듈은 디버깅용으로 변수나 메시지를 출력한다.
> - `msg`: 문자열 메시지 출력
> - `var`: 변수 내용 출력 (JSON 형식)


<br>

## 실행 및 결과 확인

```bash
# (server) #
ansible-playbook -e user=ansible5 create-user4.yml
```

```
PLAY [db] **********************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode3]

TASK [Create User ansible1] ****************************************************
ok: [tnode3]

TASK [ansible.builtin.debug] ***************************************************
ok: [tnode3] => {
    "result": {
        "append": false,
        "changed": false,
        "comment": "",
        "failed": false,
        "group": 1002,
        "home": "/home/ansible1",
        "move_home": false,
        "name": "ansible1",
        "shell": "/bin/bash",
        "state": "present",
        "uid": 1002
    }
}

PLAY RECAP *********************************************************************
tnode3                     : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

![ansible-06-create-user4-result]({{site.url}}/assets/images/ansible-06-create-user4-result.gif){: .align-center}

**PLAY RECAP 해석:**
- `ok=3`: 성공적으로 실행된 Task 수 (Gathering Facts, Create User, debug)
- `changed=0`: 실제 변경이 발생한 Task 수 (이미 사용자가 존재하므로 0)
- `failed=0`: 실패한 Task 수


`result` 변수에 `user` 모듈의 실행 결과가 딕셔너리 형태로 저장된다.

**주요 필드:**
- `changed`: 변경 여부 (`true`/`false`)
- `failed`: 실패 여부
- `name`: 생성된 사용자 이름
- `uid`: 사용자 ID
- `home`: 홈 디렉터리 경로


<br>

# 실습 6: 사용자 삭제

`user` 모듈의 `state: absent` 옵션을 사용하여 생성한 사용자를 삭제해 보자.

> **참고**: [user 모듈 공식 문서](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/user_module.html#examples)

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > remove-user.yml
---
- hosts: all
  tasks:
    - name: Remove User {{ user }}
      ansible.builtin.user:
        name: "{{ user }}"
        state: absent
        remove: yes
EOT
```

- `state: absent`: 사용자가 없도록 보장 (있으면 삭제)
- `remove: yes`: 홈 디렉터리도 함께 삭제

<br>

## 실행 및 확인

추가 변수로 삭제할 사용자명을 전달하여 실행한다.

```bash
# (server) #
ansible-playbook -e user=ansible4 remove-user.yml
```

```
TASK [Remove User ansible4] ****************************************************
changed: [tnode3]
changed: [tnode1]
changed: [tnode2]

PLAY RECAP *********************************************************************
tnode1                     : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

![ansible-06-remove-user-result]({{site.url}}/assets/images/ansible-06-remove-user-result.gif){: .align-center}

모든 노드에서 `ansible4` 사용자가 삭제되었다.

<br>

# 실습 7: 작업 변수 활용 - uptime 확인

`shell` 모듈과 `register`를 조합하여 관리 대상의 uptime 정보를 수집하고 출력해 보자.

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > debug-uptime.yml
---
- hosts: all
  tasks:
    - name: Get uptime information
      ansible.builtin.shell: /usr/bin/uptime
      register: result

    - name: Print uptime information
      ansible.builtin.debug:
        var: result.stdout
EOT
```

- `shell` 모듈로 `uptime` 명령어 실행
- `register: result`로 실행 결과를 변수에 저장
- `result.stdout`로 표준 출력만 추출하여 출력

<br>

## 실행 및 확인

```bash
# (server) #
ansible-playbook debug-uptime.yml
```

```
TASK [Get uptime information] **************************************************
changed: [tnode1]
changed: [tnode2]
changed: [tnode3]

TASK [Print uptime information] ************************************************
ok: [tnode1] => {
    "result.stdout": " 00:23:03 up  5:11,  1 user,  load average: 0.00, 0.00, 0.00"
}
ok: [tnode2] => {
    "result.stdout": " 00:23:03 up  5:10,  1 user,  load average: 0.00, 0.00, 0.00"
}
ok: [tnode3] => {
    "result.stdout": " 00:23:03 up  5:08,  2 users,  load average: 0.00, 0.00, 0.00"
}
```

각 노드의 uptime 정보가 출력된다.

<br>

## shell 모듈 실행 결과의 주요 필드

`shell` 모듈의 실행 결과를 `register`로 저장하면 다음 필드들이 포함된다:

| 필드 | 설명 |
| --- | --- |
| `stdout` | 표준 출력 (문자열) |
| `stdout_lines` | 표준 출력 (라인별 리스트) |
| `stderr` | 표준 에러 |
| `rc` | 리턴 코드 (0이면 성공) |
| `changed` | 변경 여부 (shell은 항상 `true`) |
| `cmd` | 실행된 명령어 |

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **변수 종류 이해**: 그룹, 호스트, 플레이, 추가, 작업 변수
2. **우선순위 이해**: 추가 변수 > 플레이 변수 > 호스트 변수 > 그룹 변수
3. **변수 참조**: {% raw %}`{{ 변수명 }}`{% endraw %} Jinja2 문법
4. **작업 변수**: `register` 키워드로 Task 결과 저장 및 활용
5. **user 모듈**: `state: present`(생성), `state: absent`(삭제)

<br>

변수를 활용하면 동일한 Playbook을 다양한 환경에서 재사용할 수 있다. Kubespray에서도 변수를 통해 클러스터 구성(노드 수, 네트워크 설정 등)을 커스터마이징한다.

<br>

다음 글에서는 팩트(Facts)를 활용하여 호스트 정보를 동적으로 활용하는 방법을 알아본다.
