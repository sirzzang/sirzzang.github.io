---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 7. 반복문"
excerpt: "Ansible 반복문(loop)을 활용하여 동일한 작업을 여러 항목에 대해 효율적으로 실행하는 방법을 실습해 보자."
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

이번 글의 목표는 **Ansible 반복문(loop)의 활용법 이해**다.

- 단순 반복문: `loop` + `item` 변수
- 변수 목록 반복: {% raw %}`loop: "{{ 변수명 }}"`{% endraw %}
- 사전 목록 반복: `item['키']` 또는 `item.키`
- 반복문과 register: 반복 실행 결과를 배열로 저장

<br>

# 반복문이란?

## 개념

반복문을 사용하면 **동일한 모듈을 사용하는 작업을 여러 번 작성하지 않아도 된다**. 예를 들어 여러 서비스를 시작하거나, 여러 사용자를 생성하거나, 여러 파일을 만들 때 반복문을 활용하면 코드를 간결하게 작성할 수 있다.

> **참고**: [Ansible Loops 공식 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_loops.html)

<br>

## 기본 문법

```yaml
- name: Task with loop
  ansible.builtin.모듈:
    name: "{{ item }}"
  loop:
    - 항목1
    - 항목2
    - 항목3
```

- `loop`: 반복할 항목 목록을 지정
- {% raw %}`{{ item }}`{% endraw %}: **loop의 기본 반복 변수**로, 현재 반복 중인 항목을 참조한다

<br>

### 기본 변수 {% raw %}`{{ item }}`{% endraw %}

**중요**: `loop`를 사용할 때 기본 반복 변수는 {% raw %}`{{ item }}`{% endraw %}이다. 임의로 다른 이름(예: {% raw %}`{{ user }}`{% endraw %}, {% raw %}`{{ service }}`{% endraw %})을 사용할 수 없다.

간단한 예제로 확인해 보자.

```bash
# (server) #
cat <<'EOT' > loop-basic.yml
---
- hosts: localhost
  tasks:
    - name: Print items
      ansible.builtin.debug:
        msg: "Current item: {{ item }}"
      loop:
        - apple
        - banana
        - cherry
EOT
```

```bash
# (server) #
ansible-playbook loop-basic.yml
```

실행 결과:

```bash
PLAY [localhost] ********************************************************************

TASK [Gathering Facts] **************************************************************
ok: [localhost]

TASK [Print items] ******************************************************************
ok: [localhost] => (item=apple) => {
    "msg": "Current item: apple"
}
ok: [localhost] => (item=banana) => {
    "msg": "Current item: banana"
}
ok: [localhost] => (item=cherry) => {
    "msg": "Current item: cherry"
}

PLAY RECAP **************************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0    ...
```

각 반복에서 `(item=apple)`, `(item=banana)`, `(item=cherry)`로 표시되며, {% raw %}`{{ item }}`{% endraw %} 변수가 각 항목의 값으로 치환되어 출력된다.

<br>

만약 {% raw %}`{{ item }}`{% endraw %} 대신 정의되지 않은 다른 변수(예: {% raw %}`{{ fruit }}`{% endraw %})를 사용하면 오류가 발생한다:

```bash
cat <<'EOT' > loop-basic-error.yml
---
- hosts: localhost
  tasks:
    - name: Print items
      ansible.builtin.debug:
        msg: "Current item: {{ fruit }}"
      loop:
        - apple
        - banana
        - cherry
EOT
```

```bash

PLAY [localhost] *********************************************************************************

TASK [Gathering Facts] ***************************************************************************
ok: [localhost]

TASK [Print items] *******************************************************************************
[ERROR]: Task failed: Finalization of task args for 'ansible.builtin.debug' failed: Error while resolving value for 'msg': 'fruit' is undefined

Task failed.
Origin: /root/my-ansible/loop-basic-error.yml:4:7

2 - hosts: localhost
3   tasks:
4     - name: Print items
        ^ column 7

<<< caused by >>>

Finalization of task args for 'ansible.builtin.debug' failed.
Origin: /root/my-ansible/loop-basic-error.yml:5:7

3   tasks:
4     - name: Print items
5       ansible.builtin.debug:
        ^ column 7

<<< caused by >>>

Error while resolving value for 'msg': 'fruit' is undefined
Origin: /root/my-ansible/loop-basic-error.yml:6:14

4     - name: Print items
5       ansible.builtin.debug:
6         msg: "Current item: {{ fruit }}"
               ^ column 14

failed: [localhost] (item=apple) => {"msg": "Task failed: Finalization of task args for 'ansible.builtin.debug' failed: Error while resolving value for 'msg': 'fruit' is undefined"}
failed: [localhost] (item=banana) => {"msg": "Task failed: Finalization of task args for 'ansible.builtin.debug' failed: Error while resolving value for 'msg': 'fruit' is undefined"}
failed: [localhost] (item=cherry) => {"msg": "Task failed: Finalization of task args for 'ansible.builtin.debug' failed: Error while resolving value for 'msg': 'fruit' is undefined"}
fatal: [localhost]: FAILED! => {"msg": "One or more items failed"}

PLAY RECAP ***************************************************************************************
localhost                  : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0   
```

<br>

### loop에 반복 목록 지정

`loop`에는 **반복할 목록(변수 또는 리스트)**을 지정해야 한다. 흔한 실수는 `loop` 자체에 {% raw %}`{{ item }}`{% endraw %}을 사용하는 것이다.

```yaml
# 잘못된 예
tasks:
  - name: Create user {{ item }}
    ansible.builtin.user:
      name: "{{ item }}"
      state: present
    loop: "{{ item }}"  # 오류!
```

이렇게 하면 다음과 같은 오류가 발생한다:

```bash
TASK [Create user << error 1 - 'item' is undefined >>] *****************************
[ERROR]: Task failed: 'item' is undefined

Task failed.
Origin: /root/my-ansible/create-and-delete-users.yml:20:13

18         name: "{{ item }}"
19         state: present
20       loop: "{{ item }}"
               ^ column 13

<<< caused by >>>

'item' is undefined

fatal: [localhost]: FAILED! => {"changed": false, "msg": "Task failed: 'item' is undefined"}
```

{% raw %}`{{ item }}`{% endraw %}은 `loop`가 실행될 때 생성되는 변수이다. 따라서 `loop` 정의 자체에는 사용할 수 없다. `loop`에는 반드시 **반복할 목록**을 지정해야 한다.

```yaml
# 올바른 예
- hosts: localhost
  vars:
    users:
      - user1
      - user2
  tasks:
    - name: Create user {{ item }}
      ansible.builtin.user:
        name: "{{ item }}"
        state: present
      loop: "{{ users }}"  # 변수나 리스트를 지정
```

또는 직접 리스트를 작성할 수도 있다:

```yaml
# 올바른 예 2
tasks:
  - name: Create user {{ item }}
    ansible.builtin.user:
      name: "{{ item }}"
      state: present
    loop:
      - user1
      - user2
```

<br>

# 실습 1: 단순 반복문

## 반복문 없이 작성한 경우

먼저 반복문 없이 여러 서비스를 확인하는 Playbook을 작성해 보자. 
- SSH 서비스가 시작되어 있지 않다면 시작
  - Debian 계열: ssh
  - RedHat 계열: sshd
- rsyslog 서비스가 시작되어 있지 않다면 시작

```bash
# (server) #
cat <<'EOT' > check-services.yml
---
- hosts: all
  tasks:
    - name: Check sshd state on Debian
      ansible.builtin.service:
        name: ssh
        state: started
      when: ansible_facts['os_family'] == 'Debian'

    - name: Check sshd state on RedHat
      ansible.builtin.service:
        name: sshd
        state: started
      when: ansible_facts['os_family'] == 'RedHat'

    - name: Check rsyslog state
      ansible.builtin.service:
        name: rsyslog
        state: started
EOT
```


> **참고**: `service` 모듈의 `state` 옵션
>
> service 모듈 [state parameter 설명](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/service_module.html#parameter-state)을 확인하면 각 옵션이 무엇을 의미하는지 확인할 수 있다.
> 
> | state | 동작 |
> | --- | --- |
> | `started` | 서비스 시작 (이미 실행 중이면 무시) |
> | `stopped` | 서비스 중지 (이미 중지 상태면 무시) |
> | `restarted` | 서비스 재시작 (항상 실행) |
> | `reloaded` | 설정 리로드 (항상 실행) |

> **참고**: `rsyslog` 서비스
>
> `rsyslog`는 Linux 시스템에서 로그를 수집, 저장, 전달하는 시스템 로깅 서비스이다. 
> 
> - 시스템 이벤트, 애플리케이션 로그, 커널 메시지 등을 `/var/log/` 디렉토리에 기록한다
> - `syslog` 프로토콜을 구현한 강력하고 유연한 로깅 시스템이다
> - 대부분의 Linux 배포판에서 기본 로깅 서비스로 사용된다
> - 예시: `/var/log/syslog` (Debian/Ubuntu), `/var/log/messages` (RedHat/CentOS/Rocky Linux)

<br>

## 실행

```bash
# (server) #
ansible-playbook check-services.yml
```

실행 결과는 다음과 같다.

```bash
PLAY [all] **********************************************************************

TASK [Gathering Facts] **********************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Check sshd service on Debian] *********************************************
skipping: [tnode3]
ok: [tnode1]
ok: [tnode2]

TASK [Check sshd state on RedHat] ***********************************************
skipping: [tnode1]
skipping: [tnode2]
ok: [tnode3]

TASK [Check rsyslog state] ******************************************************
ok: [tnode1]
ok: [tnode3]
ok: [tnode2]

PLAY RECAP **********************************************************************
tnode1                     : ok=3    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode2                     : ok=3    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode3                     : ok=3    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
```

모든 서비스가 이미 실행 중이므로 `changed=0`으로 표시된다. Ansible은 멱등성을 보장하므로, 서비스가 이미 원하는 상태(`started`)에 있으면 아무 작업도 수행하지 않는다.

tnode3에서 `journalctl -u sshd -f` 명령으로 sshd 서비스 로그를 확인하면, playbook 실행 시 SSH 세션이 열리는 것을 확인할 수 있다.

```bash
# (tnode3) #
journalctl -u sshd -f
```

```bash
Jan 17 18:08:36 tnode3 sshd[5042]: Accepted publickey for root from 10.10.1.10 port 41684 ssh2: RSA SHA256:waAwtC4JjrrH382ZcgzS3M2urXqppUXBmrWZF64oXs4
Jan 17 18:08:36 tnode3 sshd[5042]: pam_unix(sshd:session): session opened for user root(uid=0) by root(uid=0)
```

이는 Ansible이 playbook을 실행하기 위해 tnode3에 SSH로 접속했기 때문이다. `changed=0`으로 서비스를 재시작하지 않았지만, **서비스 상태를 확인하기 위해서는** SSH 접속이 필요하다.

다음과 같이 tnode3(Rocky Linux)에서 sshd 서비스를 중지한 후 다시 playbook을 실행해 보면, 서비스를 시작하는 것을 확인할 수 있다.

```bash
# (tnode3) #
systemctl stop sshd
```

```bash
# (server) #
ansible-playbook check-services.yml
```

```bash
PLAY [all] **********************************************************************

TASK [Gathering Facts] **********************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Check sshd service on Debian] *********************************************
skipping: [tnode3]
ok: [tnode1]
ok: [tnode2]

TASK [Check sshd state on RedHat] ***********************************************
skipping: [tnode1]
skipping: [tnode2]
changed: [tnode3]

TASK [Check rsyslog state] ******************************************************
ok: [tnode2]
ok: [tnode1]
ok: [tnode3]

PLAY RECAP **********************************************************************
tnode1                     : ok=3    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode2                     : ok=3    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
tnode3                     : ok=3    changed=1    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0   
```

tnode3에서 sshd 서비스가 중지되어 있었으므로, Ansible이 서비스를 시작하고 `changed=1`로 표시된다. tnode3의 `Check sshd state on RedHat` task에서 `changed`로 표시되는 것을 확인할 수 있다.


![ansible-08-change-services-result]({{site.url}}/assets/images/ansible-08-change-services-result.gif){: .align-center}

<br>

## loop 반복문 적용

동일한 작업을 `loop`를 사용하여 간결하게 작성할 수 있다.

```bash
# (server) #
cat <<'EOT' > check-services1.yml
---
- hosts: all
  tasks:
    - name: Check services state
      ansible.builtin.service:
        name: "{{ item }}"
        state: started
      loop:
        - vboxadd-service
        - rsyslog
EOT
```

<br>

### vboxadd-service와 SSH의 차이

`vboxadd-service`는 SSH 서비스가 **아니다**. VirtualBox Guest Additions의 서비스이다.

- **vboxadd-service**: VirtualBox VM에서 호스트와의 통신, 공유 폴더, 클립보드 공유 등을 담당하는 VirtualBox Guest Additions 서비스
- **SSH 서비스**: 
  - Debian/Ubuntu: `ssh`
  - RedHat/CentOS/Rocky Linux: `sshd`

모든 노드가 VirtualBox VM이므로 `vboxadd-service`는 모든 노드에서 동일한 이름으로 동작한다. 반면 SSH는 OS에 따라 서비스 이름이 다르다.

<br>

### 왜 loop에서 OS별로 다른 서비스를 사용하지 않나?

`loop` 안에서도 OS별 분기(`when`)가 가능하지만, 각 아이템마다 조건을 설정하려면 복잡한 구조가 필요하다. 예를 들어, 사전(dictionary) 형태로 서비스와 OS 조건을 함께 정의해야 한다.

간단한 예제에서는 모든 OS에서 동일한 이름을 가진 서비스(`vboxadd-service`, `rsyslog`)를 사용하는 것이 더 명확하다.

**OS마다 서비스 이름이 다른 예시:**

| 서비스 | Debian/Ubuntu | RedHat/CentOS/Rocky |
| :---: | :--- | :--- |
| SSH | `ssh` | `sshd` |
| Apache 웹서버 | `apache2` | `httpd` |
| 방화벽 | `ufw` | `firewalld` |
| 네트워크 | `networking` | `network` |

이런 서비스들을 `loop`로 처리하려면 OS별 분기가 필요하므로, 위의 예제(실습 0)처럼 각각 별도의 task로 작성하거나, 사전 목록(실습 3)을 활용해야 한다.

<br>

## 실행

```bash
# (server) #
ansible-playbook check-services1.yml
```

![ansible-08-check-services1-result]({{site.url}}/assets/images/ansible-08-check-services1-result.png){: .align-center}

<br>

# 실습 2: 변수를 활용한 반복문

## 변수 목록을 loop에 사용

`loop`에 사용할 항목을 변수로 정의하면 재사용성이 높아진다.

```bash
# (server) #
cat <<'EOT' > check-services2.yml
---
- hosts: all
  vars:
    services:
      - vboxadd-service
      - rsyslog
  tasks:
    - name: Check services state
      ansible.builtin.service:
        name: "{{ item }}"
        state: started
      loop: "{{ services }}"
EOT
```

- `vars`에서 서비스 목록을 변수로 정의
- {% raw %}`loop: "{{ services }}"`{% endraw %}로 변수 참조

<br>

## 실행

```bash
# (server) #
ansible-playbook check-services2.yml
```

<br>

# 실습 3: 사전 목록을 활용한 반복문

## 여러 속성이 필요한 경우

하나의 항목에 여러 속성이 필요한 경우, 여러 개의 item을 loop 안에서 **사전(dictionary) 목록**을 이용해 정의할 수도 있다.
- [dictionary를 활용한 루프](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_loops.html#iterating-over-a-dictionary)
- 예를 들어, 여러 개의 사용자 계정을 생성하는 Playbook이 필요하다면, 사용자 계정을 생성하기 위해 필요한 이름과 패스워드 등 여러 항목을 loop문에서 사전 목록으로 사용하면 됨



```bash
# (server) #
cat <<'EOT' > make-file.yml
---
- hosts: all
  tasks:
    - name: Create files
      ansible.builtin.file:
        path: "{{ item['log-path'] }}"
        mode: "{{ item['log-mode'] }}"
        state: touch
      loop:
        - log-path: /var/log/test1.log
          log-mode: '0644'
        - log-path: /var/log/test2.log
          log-mode: '0600'
EOT
```

- `item['키']` 또는 `item.키` 형식으로 사전의 값에 접근

> **참고**: `file` 모듈의 `state` 옵션
>
> file 모듈 [state parameter 설명](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html#parameter-state)을 확인하면 각 옵션이 무엇을 의미하는지 확인할 수 있다.
> 
> | state | 동작 |
> | --- | --- |
> | `touch` | 빈 파일 생성 또는 타임스탬프 갱신 |
> | `absent` | 파일/디렉토리 삭제 |
> | `directory` | 디렉토리 생성 (존재하지 않으면) |
> | `file` | 파일 속성만 변경 (파일이 존재해야 함) |
> | `link` | 심볼릭 링크 생성 |
> | `hard` | 하드 링크 생성 |

<br>

## 실행 및 확인

```bash
# (server) #
ansible-playbook make-file.yml
```

![ansible-08-make-files-result]({{site.url}}/assets/images/ansible-08-make-files-result.gif){: .align-center}

모든 노드에 파일이 올바른 권한으로 생성되었는지 확인한다.

```bash
# (server) #
# 파일 생성 확인
root@server:~/my-ansible# ansible -m shell -a "ls -l /var/log/test*log" all
tnode3 | CHANGED | rc=0 >>
-rw-r--r--. 1 root root 0 Jan 17 18:20 /var/log/test1.log
-rw-------. 1 root root 0 Jan 17 18:20 /var/log/test2.log
tnode1 | CHANGED | rc=0 >>
-rw-r--r-- 1 root root 0 Jan 17 18:20 /var/log/test1.log
-rw------- 1 root root 0 Jan 17 18:20 /var/log/test2.log
tnode2 | CHANGED | rc=0 >>
-rw-r--r-- 1 root root 0 Jan 17 18:20 /var/log/test1.log
-rw------- 1 root root 0 Jan 17 18:20 /var/log/test2.log
```

<br>

# (참고) 이전 스타일 반복문

Ansible 2.5 버전 이전에는 `with_*` 접두사를 사용하는 반복문 구문이 있었다. 현재는 `loop` 사용이 권장되지만, 기존 Playbook을 분석할 때 알아두면 유용하다.

| 반복문 키워드 | 설명 |
| :---: | :--- |
| `with_items` | 문자열 목록 또는 사전 목록과 같은 단순한 목록의 경우 `loop` 키워드와 동일하게 작동한다. `loop`와 달리 목록으로 이루어진 목록이 제공되는 경우 단일 수준의 목록으로 병합(flatten)된다. 반복문 변수 `item`에는 각 반복 작업 중 사용되는 목록 항목이 있다. |
| `with_file` | 제어 노드의 파일 이름을 목록으로 사용한다. 반복문 변수 `item`에는 각 반복 작업 중 파일 목록에 있는 해당 파일의 **콘텐츠**(내용)가 포함된다. |
| `with_sequence` | 숫자로 된 순서에 따라 값 목록을 생성하는 매개 변수가 필요한 경우 사용한다. 반복문 변수 `item`에는 각 반복 작업 중 생성된 순서대로 생성된 항목 중 하나의 값이 있다. |

```yaml
# 이전 스타일 (비권장)
- name: "with_items example"
  ansible.builtin.debug:
    msg: "{{ item }}"
  with_items: "{{ data }}"

# 현재 권장 스타일
- name: "loop example"
  ansible.builtin.debug:
    msg: "{{ item }}"
  loop: "{{ data }}"
```

<br>

## 이전 스타일 반복문 실습

이전 스타일 반복문이 여전히 작동하는지 확인해 보자.

```bash
# (server) #
cat <<'EOT' > old-style-loop.yml
---
- hosts: localhost
  vars:
    data:
      - user0
      - user1
      - user2
  tasks:
    - name: "with_items"
      ansible.builtin.debug:
        msg: "{{ item }}"
      with_items: "{{ data }}" # old style
EOT
```

```bash
# (server) #
ansible-playbook old-style-loop.yml
```

실행 결과는 다음과 같다.

```bash
PLAY [localhost] *******************************************************************************

TASK [Gathering Facts] *************************************************************************
ok: [localhost]

TASK [with_items] ******************************************************************************
ok: [localhost] => (item=user0) => {
    "msg": "user0"
}
ok: [localhost] => (item=user1) => {
    "msg": "user1"
}
ok: [localhost] => (item=user2) => {
    "msg": "user2"
}

PLAY RECAP *************************************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

실행 결과 확인 시, 아래와 같은 점을 확인할 수 있다:
- **정상 작동**: `with_items`는 여전히 정상적으로 작동한다. 각 item이 순회되며 출력된다.
- **동일한 동작**: `loop`를 사용한 것과 동일한 결과가 나온다.
- **경고 없음**: Ansible은 이전 스타일 사용에 대한 경고(deprecation warning)를 표시하지 않는다.

다만, 아래와 같은 이유로 `loop` 사용이 권장된다:
- **일관성**: `loop`는 모든 반복 작업에 대해 일관된 문법을 제공한다.
- **가독성**: `with_*` 접두사보다 `loop`가 더 명확하고 간결하다.
- **유지보수성**: 새로운 Playbook 작성 시 `loop`를 사용하면 최신 모범 사례를 따르게 된다.
- **미래 호환성**: Ansible 커뮤니티가 `loop`를 표준으로 권장하므로, 향후 새로운 기능은 `loop`에 우선 추가될 가능성이 높다.

<br>

# 실습 4: 반복문과 register

## 개념

`register` 변수는 반복 실행되는 작업의 출력을 캡처할 수 있게 해 준다. 따라서 `register` 변수를 반복문과 함께 사용하면 **각 반복 실행의 결과가 배열로 저장**할 수 있다. 이를 통해 반복 실행되는 작업들이 모두 잘 수행되었는지 확인할 수 있으며, 이 값을 이용해 다음 작업ㅇ르 수행할 수도 있다.

<br>

## Playbook 작성

다음과 같이 Playbook을 작성한다:
- `shell` 모듈을 이용하여 "I can speak~"라는 메시지를 출력한다
- `loop` 키워드를 이용하여 Korean과 English를 아이템으로 나열한다
- `register` 키워드를 이용하여 실행 결과를 `result` 변수에 저장한다
- `debug` 모듈을 통해 `result` 변수의 내용을 확인한다

```bash
# (server) #
cat <<'EOT' > loop_register.yml
---
- hosts: localhost
  tasks:
    - name: Loop echo test
      ansible.builtin.shell: "echo 'I can speak {{ item }}'"
      loop:
        - Korean
        - English
      register: result

    - name: Show result
      ansible.builtin.debug:
        var: result
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook loop_register.yml
```

실행 결과는 다음과 같다.

```bash
PLAY [localhost] *******************************************************************************

TASK [Gathering Facts] *************************************************************************
ok: [localhost]

TASK [Loop echo test] **************************************************************************
changed: [localhost] => (item=Korean)
changed: [localhost] => (item=English)

TASK [Show result] *****************************************************************************
ok: [localhost] => {
    "result": {
        "changed": true,
        "msg": "All items completed",
        "results": [
            {
                ...
                "item": "Korean",
                "stdout": "I can speak Korean",
                ...
            },
            {
                ...
                "item": "English",
                "stdout": "I can speak English",
                ...
            }
        ],
        "skipped": false
    }
}

PLAY RECAP *************************************************************************************
localhost                  : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```
실행 결과:
1. **`Loop echo test` 작업**: 2개의 아이템(`Korean`, `English`)에 대해 각각 실행되고 결과가 `changed`로 표시된다.
2. **`result` 변수 구조**:
   - `"msg": "All items completed"`: 모든 아이템이 성공적으로 완료됨
   - `"results": [...]`: **각 반복 실행의 결과가 배열로 저장**됨
   - 각 배열 요소에는 `"item"` (반복 아이템), `"stdout"` (명령 실행 결과) 등이 포함됨
3. **배열 구조**: 2번 반복했으므로 `results` 배열에 2개의 요소가 저장됨

<details>
<summary><strong>전체 result 변수 내용</strong></summary>

```json
{
    "result": {
        "changed": true,
        "msg": "All items completed",
        "results": [
            {
                "ansible_loop_var": "item",
                "changed": true,
                "cmd": "echo 'I can speak Korean'",
                "delta": "0:00:00.001586",
                "end": "2026-01-17 18:33:16.569898",
                "failed": false,
                "invocation": {
                    "module_args": {
                        "_raw_params": "echo 'I can speak Korean'",
                        "_uses_shell": true,
                        "argv": null,
                        "chdir": null,
                        "cmd": null,
                        "creates": null,
                        "executable": null,
                        "expand_argument_vars": true,
                        "removes": null,
                        "stdin": null,
                        "stdin_add_newline": true,
                        "strip_empty_ends": true
                    }
                },
                "item": "Korean",
                "msg": "",
                "rc": 0,
                "start": "2026-01-17 18:33:16.568312",
                "stderr": "",
                "stderr_lines": [],
                "stdout": "I can speak Korean",
                "stdout_lines": [
                    "I can speak Korean"
                ]
            },
            {
                "ansible_loop_var": "item",
                "changed": true,
                "cmd": "echo 'I can speak English'",
                "delta": "0:00:00.001498",
                "end": "2026-01-17 18:33:16.716173",
                "failed": false,
                "invocation": {
                    "module_args": {
                        "_raw_params": "echo 'I can speak English'",
                        "_uses_shell": true,
                        "argv": null,
                        "chdir": null,
                        "cmd": null,
                        "creates": null,
                        "executable": null,
                        "expand_argument_vars": true,
                        "removes": null,
                        "stdin": null,
                        "stdin_add_newline": true,
                        "strip_empty_ends": true
                    }
                },
                "item": "English",
                "msg": "",
                "rc": 0,
                "start": "2026-01-17 18:33:16.714675",
                "stderr": "",
                "stderr_lines": [],
                "stdout": "I can speak English",
                "stdout_lines": [
                    "I can speak English"
                ]
            }
        ],
        "skipped": false
    }
}
```

</details>

<br>

## 결과에서 특정 값 추출

반복 실행 결과는 `result.results` 배열에 저장됨을 확인했다. 이를 다시 `loop`로 순회하여 특정 값을 추출할 수 있다.
- `debug` 모듈에 `loop` 키워드를 사용해 `result.results`를 아이템 변수로 사용
- 해당 아이템의 stdout 값 출력을 위해 `item.stdout`이라는 변수로 결과값 출력

```bash
# (server) #
cat <<'EOT' > loop_register1.yml
---
- hosts: localhost
  tasks:
    - name: Loop echo test
      ansible.builtin.shell: "echo 'I can speak {{ item }}'"
      loop:
        - Korean
        - English
      register: result

    - name: Show result
      ansible.builtin.debug:
        msg: "Stdout: {{ item.stdout }}"
      loop: "{{ result.results }}"
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook loop_register1.yml
```

실행 결과는 다음과 같다.

```bash
PLAY [localhost] *******************************************************************************

TASK [Gathering Facts] *************************************************************************
ok: [localhost]

TASK [Loop echo test] **************************************************************************
changed: [localhost] => (item=Korean)
changed: [localhost] => (item=English)

TASK [Show result] *****************************************************************************
ok: [localhost] => (item={...}) => {
    "msg": "Stdout: I can speak Korean"
}
ok: [localhost] => (item={...}) => {
    "msg": "Stdout: I can speak English"
}

PLAY RECAP *************************************************************************************
localhost                  : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

**주목할 점:**

1. **`Loop echo test` 작업**: 이전 예제와 동일하게 2개 아이템에 대해 실행됨
2. **`Show result` 작업**: 
   - {% raw %}`loop: "{{ result.results }}"`{% endraw %}로 이전 작업의 결과 배열을 순회함
   - 각 반복에서 `item.stdout` 값을 추출하여 출력함
   - 결과: `"Stdout: I can speak Korean"`, `"Stdout: I can speak English"`
3. **값 추출**: `result.results` 배열에서 원하는 필드(`stdout`)만 깔끔하게 추출할 수 있음

<details>
<summary><strong>전체 실행 결과 (item 상세 내용 포함)</strong></summary>

```bash
TASK [Show result] *****************************************************************************
ok: [localhost] => (item={'changed': True, 'stdout': 'I can speak Korean', 'stderr': '', 'rc': 0, 'cmd': "echo 'I can speak Korean'", 'start': '2026-01-17 18:39:10.520614', 'end': '2026-01-17 18:39:10.521784', 'delta': '0:00:00.001170', 'msg': '', 'invocation': {'module_args': {'_raw_params': "echo 'I can speak Korean'", '_uses_shell': True, 'expand_argument_vars': True, 'stdin_add_newline': True, 'strip_empty_ends': True, 'cmd': None, 'argv': None, 'chdir': None, 'executable': None, 'creates': None, 'removes': None, 'stdin': None}}, 'stdout_lines': ['I can speak Korean'], 'stderr_lines': [], 'failed': False, 'item': 'Korean', 'ansible_loop_var': 'item'}) => {
    "msg": "Stdout: I can speak Korean"
}
ok: [localhost] => (item={'changed': True, 'stdout': 'I can speak English', 'stderr': '', 'rc': 0, 'cmd': "echo 'I can speak English'", 'start': '2026-01-17 18:39:10.660499', 'end': '2026-01-17 18:39:10.661790', 'delta': '0:00:00.001291', 'msg': '', 'invocation': {'module_args': {'_raw_params': "echo 'I can speak English'", '_uses_shell': True, 'expand_argument_vars': True, 'stdin_add_newline': True, 'strip_empty_ends': True, 'cmd': None, 'argv': None, 'chdir': None, 'executable': None, 'creates': None, 'removes': None, 'stdin': None}}, 'stdout_lines': ['I can speak English'], 'stderr_lines': [], 'failed': False, 'item': 'English', 'ansible_loop_var': 'item'}) => {
    "msg": "Stdout: I can speak English"
}
```

각 `item`에는 이전 작업의 전체 결과가 포함되어 있으며, 그 중 `stdout` 필드만 추출하여 출력했다.

</details>

<br>

## 참고: Return Values

Return Values란 Ansible 모듈이 실행된 후 반환하는 데이터이다. 이를 통해 작업의 성공/실패 여부, 출력 결과, 상태 변경 등을 확인할 수 있다. `register` 키워드를 사용하면 이 반환 값을 변수에 저장하여 후속 작업에서 활용할 수 있다.

- [Return Values 공식 문서](https://docs.ansible.com/ansible/latest/reference_appendices/common_return_values.html)

<br>

### 공통 반환 값

모든 모듈에서 공통적으로 반환하는 주요 값은 다음과 같다.

| 필드 | 타입 | 설명 |
| :---: | :---: | :--- |
| `changed` | boolean | 대상 시스템에 변경이 발생했는지 여부 |
| `failed` | boolean | 작업이 실패했는지 여부 |
| `skipped` | boolean | 작업이 건너뛰어졌는지 여부 (`when` 조건 등) |
| `msg` | string | 사용자에게 표시할 메시지 (주로 오류 메시지) |
| `rc` | integer | 리턴 코드 (명령 실행 결과). 0은 성공 |
| `stdout` | string | 표준 출력 (문자열) |
| `stderr` | string | 표준 에러 출력 (문자열) |
| `stdout_lines` | list | 표준 출력을 행 단위로 구분한 목록 |
| `stderr_lines` | list | 표준 에러를 행 단위로 구분한 목록 |
| `invocation` | dict | 모듈 호출 시 사용된 인자 정보 |
| `ansible_facts` | dict | 수집된 facts 정보 (setup 모듈 등) |
| `warnings` | list | 경고 메시지 목록 |
| `deprecations` | list | 더 이상 사용되지 않는 기능에 대한 경고 |

<br>

### shell/command 모듈 특화 반환 값

`shell`과 `command` 모듈은 추가로 다음 값들을 반환한다.

| 필드 | 타입 | 설명 |
| :---: | :---: | :--- |
| `cmd` | string | 실행된 명령어 |
| `delta` | string | 명령 실행 소요 시간 (예: `0:00:00.001586`) |
| `start` | string | 명령 실행 시작 시간 |
| `end` | string | 명령 실행 종료 시간 |

<br>

### 리턴 코드 (rc)

`rc` (return code)는 shell/command 모듈에서 실행한 명령어의 종료 상태(exit status)를 나타낸다. Linux/Unix 시스템에서 프로그램이 종료될 때 반환하는 숫자 값으로, 0은 성공을 의미하고 그 외의 값은 다양한 오류를 나타낸다.

주요 리턴 코드는 다음과 같다.

| 반환 코드 | 의미 |
| :---: | :--- |
| 0 | 성공 (명령이 정상적으로 실행됨) |
| 1 | 일반 오류 (catchall for general errors) |
| 2 | 잘못된 인자 (misuse of shell command) |
| 126 | 실행 권한 없음 (permission denied) |
| 127 | 명령 없음 (command not found) |
| 130 | Ctrl+C로 종료 (terminated with Ctrl+C) |
| 137 | SIGKILL로 종료 (killed with kill -9) |
| 139 | Segmentation fault |

Linux 터미널에서 `$?` 변수를 사용하여 바로 직전 명령의 반환 코드를 확인할 수 있다.

```bash
# 명령 실행 이후 반환 코드(exit status) 확인

# 바로 직전 명령의 반환 코드 확인
echo $?

# rc = 0 (성공)
ls -al
echo $?

# rc = 2 (존재하지 않는 파일/디렉토리)
ls abc
echo $?

# rc = 127 (명령어 없음)
aaa
echo $?
```

<br>

### changed vs failed

Ansible 실행 결과를 해석할 때 `changed`와 `failed`는 자주 혼동되는 개념이다. 두 개념은 서로 다른 관점에서 작업의 결과를 나타낸다.

- **`changed`**: 대상 시스템의 상태가 변경되었는지 여부
  - 파일 생성/수정, 서비스 시작/재시작 등 → `changed: true`
  - 이미 원하는 상태인 경우 (멱등성) → `changed: false`
- **`failed`**: 작업이 실패했는지 여부
  - 오류 발생 시 → `failed: true`
  - 정상 실행 시 → `failed: false`

예시는 다음과 같다:
- 이미 실행 중인 서비스를 시작하는 작업: `changed: false`, `failed: false`
- 새로운 파일을 생성하는 작업: `changed: true`, `failed: false`
- 존재하지 않는 서비스를 시작하는 작업: `changed: false`, `failed: true`

<br>

### stdout vs stdout_lines

명령 실행 결과를 저장할 때 `stdout`과 `stdout_lines` 중 어느 것을 사용할지 선택할 수 있다. 두 필드는 같은 데이터를 다른 형식으로 제공한다.

- **`stdout`**: 명령의 표준 출력을 하나의 문자열로 반환
  - 여러 줄 출력도 개행 문자(`\n`)를 포함한 하나의 문자열
- **`stdout_lines`**: 명령의 표준 출력을 행 단위로 분리한 리스트로 반환
  - 각 줄이 리스트의 개별 요소가 됨

예시:
```yaml
# stdout: "line1\nline2\nline3"
# stdout_lines: ["line1", "line2", "line3"]
```

`stdout_lines`는 출력을 반복문으로 처리하거나 특정 줄만 추출할 때 유용하다.

<br>

# 실습 5: 사용자 10명 생성 및 삭제

반복문을 사용하여 `user1` ~ `user10` 10명의 사용자를 생성하고, 확인 후 삭제한다.

<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > create-and-delete-users.yml
---
- hosts: all
  vars:
    users:
      - user1
      - user2
      - user3
      - user4
      - user5
      - user6
      - user7
      - user8
      - user9
      - user10
  tasks:
    - name: Create user {{ item }}
      ansible.builtin.user:
        name: "{{ item }}"
        state: present
      loop: "{{ users }}"

    - name: Delete user
      ansible.builtin.user:
        name: "{{ item }}"
        state: absent
      loop: "{{ users }}"
EOT
```

- `hosts: all` 사용 (모든 관리 노드에서 실행)
- `vars`에 `users` 리스트 정의 (user1~user10)
- 첫 번째 task: {% raw %}`name: Create user {{ item }}`{% endraw %} → task name에 {% raw %}`{{ item }}`{% endraw %} 사용 (WARNING 발생)
- 두 번째 task: `name: Delete user` → task name에 {% raw %}`{{ item }}`{% endraw %} 미사용 (WARNING 없음)

> **참고**: [user 모듈 공식 문서](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/user_module.html)

<br>

## 실행 및 확인

```bash
# (server) #
ansible-playbook create-and-delete-users.yml
```

실행 결과는 다음과 같다. 각 3개 노드에서 병렬로 사용자 생성/삭제가 일어나는 것을 볼 수 있다(예: user1 → tnode1, tnode2, tnode3).

```bash
PLAY [all] *************************************************************************************

TASK [Gathering Facts] *************************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]
[WARNING]: Encountered 1 template error.
error 1 - 'item' is undefined
Origin: /root/my-ansible/create-and-delete-users.yml:16:13

14       - user10
15   tasks:
16     - name: Create user {{ item }}
               ^ column 13

TASK [Create user] *****************************************************************************
changed: [tnode2] => (item=user1)
changed: [tnode1] => (item=user1)
changed: [tnode3] => (item=user1)
changed: [tnode2] => (item=user2)
changed: [tnode1] => (item=user2)
changed: [tnode3] => (item=user2)
...
changed: [tnode2] => (item=user10)
changed: [tnode1] => (item=user10)
changed: [tnode3] => (item=user10)

TASK [Delete user] *****************************************************************************
changed: [tnode2] => (item=user1)
changed: [tnode1] => (item=user1)
changed: [tnode3] => (item=user1)
changed: [tnode2] => (item=user2)
changed: [tnode1] => (item=user2)
changed: [tnode3] => (item=user2)
...
changed: [tnode2] => (item=user10)
changed: [tnode1] => (item=user10)
changed: [tnode3] => (item=user10)

PLAY RECAP *************************************************************************************
tnode1                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

![ansible-08-create-and-delete-users-result](ansible-08-create-and-delete-users-result.gif){: .align-center}

<br>


| 항목 | 설명 |
| :---: | :--- |
| **대상 노드** | 3개 노드 (tnode1, tnode2, tnode3) |
| **Task 수** | 3개 (Gathering Facts, Create user, Delete user) |
| **ok=3** | 3개 task 모두 성공적으로 실행됨 |
| **changed=2** | 2개 task에서 상태 변경 발생 (생성, 삭제). Gathering Facts는 정보 수집만 하므로, `ok`로만 카운트됨 |
| **총 생성/삭제** | 각 노드당 10명 = 총 30명 생성 후 삭제 |

<br>

### WARNING 비교

실행 결과에서 중요한 차이점을 확인할 수 있다:

<br>

**첫 번째 task (Create user)**: WARNING 발생

```bash
[WARNING]: Encountered 1 template error.
error 1 - 'item' is undefined
Origin: /root/my-ansible/create-and-delete-users.yml:16:13

16     - name: Create user {{ item }}
               ^ column 13

TASK [Create user << error 1 - 'item' is undefined >>] *****************************************
changed: [tnode2] => (item=user1)
...
```
- task name에 {% raw %}`{{ item }}`{% endraw %}을 사용했으므로 WARNING 발생
- task name은 loop 실행 **전에** 평가되므로 {% raw %}`{{ item }}`{% endraw %}이 undefined
- 하지만 모듈 파라미터({% raw %}`name: "{{ item }}"`{% endraw %})는 loop 실행 **중에** 평가되므로 정상 작동

<br>

**두 번째 task (Delete user)**: WARNING 없음
```bash
TASK [Delete user] *****************************************************************************
changed: [tnode2] => (item=user1)
...
```
- task name에 {% raw %}`{{ item }}`{% endraw %}을 사용하지 않았으므로 WARNING 없음
- 깔끔한 출력이지만, 어떤 사용자를 처리하는지 task 이름에서 확인 불가

<br>
WARNING이니까, 확인 목적으로 task name에 {% raw %}`{{ item }}`{% endraw %}을 사용하는 방식도 종종 볼 수 있다고 한다.

- **WARNING 있는 버전**: 디버깅이 쉽고, 실행 과정 추적이 용이
- **WARNING 없는 버전**: 깔끔한 출력, 로그가 간결함

<br>

# 실습 6: 파일 100개 생성 및 삭제

`with_sequence` 또는 `loop`와 `range` 필터를 사용하여 `/var/log/test1` ~ `/var/log/test100` 100개의 파일을 생성하고, 확인 후 삭제한다.

> **참고**:
> - [with_sequence 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_loops.html#with-sequence)
> - [range 필터](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_filters.html#manipulating-lists)

<br>

## Playbook 작성

`create-and-delete-files.yml` 파일을 생성한다.

```bash
# (server) #
cat << 'EOT' > create-and-delete-files.yml
---
- hosts: all
  tasks:
    - name: Create files
      ansible.builtin.file:
        path: "{{ '/var/log/test%03d' | format(item) }}"
        mode: '0600'
        state: touch
      loop: "{{ range(1, 101) | list }}"
    
    - name: Delete files
      ansible.builtin.file:
        path: "{{ '/var/log/test%03d' | format(item) }}"
        state: absent
      loop: "{{ range(1, 101) | list }}"
EOT
```

- `range(1, 101) | list`
  - `range(1, 101)`: 1부터 100까지 숫자 생성 (101은 포함 안 됨)
  - `list`: `range(1, 101)`이 생성한 이터러블 객체를 실제 리스트로 변환하는 필터 
- `'/var/log/test%03d' | format(item)`: 3자리 0으로 채운 번호 (test001, test002, ..., test100)
- `state: touch`: 파일 생성
- `state: absent`: 파일 삭제 (삭제 시 `mode` 불필요)

<br>

## 실행 및 확인

Playbook을 실행한다.

```bash
# (server) #
ansible-playbook create-and-delete-files.yml
```

실행 결과는 다음과 같다. 3개 노드에서 병렬로 100개 파일을 생성하고 삭제한다.

![ansible-08-create-and-delete-files-result]({{site.url}}/assets/images/ansible-08-create-and-delete-files-result.gif){: .align-center}

```bash
PLAY [all] *************************************************************************************

TASK [Gathering Facts] *************************************************************************
ok: [tnode1]
ok: [tnode2]
ok: [tnode3]

TASK [Create files] ****************************************************************************
changed: [tnode2] => (item=1)
changed: [tnode3] => (item=1)
changed: [tnode1] => (item=1)
changed: [tnode2] => (item=2)
changed: [tnode1] => (item=2)
changed: [tnode3] => (item=2)
...
changed: [tnode2] => (item=100)
changed: [tnode1] => (item=100)
changed: [tnode3] => (item=100)

TASK [Delete files] ****************************************************************************
changed: [tnode2] => (item=1)
changed: [tnode1] => (item=1)
changed: [tnode3] => (item=1)
changed: [tnode2] => (item=2)
changed: [tnode1] => (item=2)
changed: [tnode3] => (item=2)
...
changed: [tnode2] => (item=100)
changed: [tnode1] => (item=100)
changed: [tnode3] => (item=100)

PLAY RECAP *************************************************************************************
tnode1                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
```

- **총 300개 파일 생성 및 삭제**: 각 노드당 100개 × 3개 노드 = 300개
- **ok=3**: 3개 task 모두 성공 (Gathering Facts, Create files, Delete files)
- **changed=2**: 2개 task에서 상태 변경 (생성, 삭제)
- **실행 시간**: 100개 파일 × 3개 노드 × 2개 task = 600번의 작업이 병렬로 실행됨

> `watch -n 0.1 'ls /var/log/test* 2>/dev/null | wc -l'` 명령어로 실시간 모니터링 가능

<br>

## with_sequence 이용 작성

`loop`와 `range` 대신 이전 스타일인 `with_sequence`를 사용할 수도 있다.

```bash
# (server) #
cat << 'EOT' > create-and-delete-files-with-sequence.yml
---
- hosts: all
  tasks:
    - name: Create files
      ansible.builtin.file:
        path: "/var/log/test{{ '%03d' | format(item | int) }}"
        mode: '0600'
        state: touch
      with_sequence: start=1 end=100
    
    - name: Delete files
      ansible.builtin.file:
        path: "/var/log/test{{ '%03d' | format(item | int) }}"
        state: absent
      with_sequence: start=1 end=100
EOT
```

**loop vs with_sequence 비교**:

| 항목 | `loop` + `range` | `with_sequence` |
| :---: | :--- | :--- |
| **스타일** | 현대적 (Ansible 2.5+) | 이전 스타일 |
| **문법** | {% raw %}`loop: "{{ range(1, 101) \| list }}"`{% endraw %} | `with_sequence: start=1 end=100` |
| **가독성** | Python의 range와 동일하여 직관적 | start/end 매개변수로 명시적 |
| **추천** | 권장 (일관성, 유지보수성) | 레거시 지원 |

실행 결과는 동일하다. `loop` 방식이 더 일관되고 현대적이므로 새로운 코드에서는 `loop`를 사용하는 것이 좋다.

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **단순 반복문**: `loop` + `item` 변수로 동일 작업 반복
2. **변수 활용**: 변수 목록을 `loop`에 전달
3. **사전 목록**: 여러 속성이 필요한 경우 딕셔너리 사용
4. **register와 반복문**: 반복 실행 결과를 배열로 저장 및 활용

<br>

반복문을 활용하면 동일한 작업을 여러 대상에 대해 간결하게 작성할 수 있다. Kubespray에서도 여러 노드에 동일한 설정을 적용할 때 반복문을 적극 활용한다.

<br>

다음 글에서는 조건문을 활용하여 더 유연한 Playbook을 작성하는 방법을 알아본다.
