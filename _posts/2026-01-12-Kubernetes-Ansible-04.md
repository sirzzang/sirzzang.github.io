---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 3. Ad-hoc 명령어"
hidden: true
excerpt: "Ansible 설정 파일 구성과 Ad-hoc 명령어를 통해 인벤토리에 정의된 호스트에 간단한 작업을 실행해 보자."
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

이번 글의 목표는 **Ansible 설정 파일 구성과 Ad-hoc 명령어 실행**이다.

- 설정 파일(`ansible.cfg`): 연결 사용자, 권한 상승, 설정 우선순위
- Ad-hoc 명령어: Playbook 없이 단일 명령을 즉시 실행하는 방법
- 주요 모듈: `ping`, `shell`, `command`, `copy`, `file` 등

<br>

# Ansible 설정 파일

## ansible.cfg 구조

`ansible.cfg`는 INI 형식으로 작성하며, 섹션별로 키-값 쌍으로 설정을 정의한다.

```ini
[defaults]
inventory = ./inventory
remote_user = root
ask_pass = false

[privilege_escalation]
become = true
become_method = sudo
become_user = root
become_ask_pass = false
```

<br>

## [defaults] 섹션

Ansible 작업의 기본값을 설정한다.

| 매개변수 | 설명 |
| --- | --- |
| `inventory` | 인벤토리 파일 경로 |
| `remote_user` | 관리 호스트에 연결할 사용자. 미지정 시 현재 로컬 사용자 이름 사용 |
| `ask_pass` | SSH 암호 입력 프롬프트 표시 여부. SSH 키 인증 사용 시 `false` |

<br>

## [privilege_escalation] 섹션

권한 상승(privilege escalation) 관련 설정이다. 일반 사용자로 접속 후 root 권한이 필요한 작업을 수행할 때 사용한다.

| 매개변수 | 설명 |
| --- | --- |
| `become` | 권한 상승 활성화 여부. `true`면 연결 후 자동으로 지정된 사용자로 전환 |
| `become_method` | 권한 상승 방식. `sudo`(기본값), `su`, `pfexec`, `doas` 등 |
| `become_user` | 전환할 사용자. 기본값은 `root` |
| `become_ask_pass` | 권한 상승 시 암호 입력 프롬프트 표시 여부 |

> **참고**: become의 동작 원리
>
> `become = true`로 설정하면 Ansible은 다음과 같이 동작한다:
> 1. `remote_user`로 SSH 접속
> 2. `become_method`(예: sudo)를 사용해 `become_user`(예: root)로 전환
> 3. 전환된 권한으로 작업 실행
>
> 이 방식은 root 직접 로그인을 피하고, 감사 로그를 남기며, 최소 권한 원칙을 따르기 위해 사용된다.

<br>

## 실습: 설정 파일 생성

```bash
# (server) #
cat <<EOT > ansible.cfg
[defaults]
inventory = ./inventory
remote_user = root
ask_pass = false

[privilege_escalation]
become = true
become_method = sudo
become_user = root
become_ask_pass = false
EOT
```

```bash
# (server) #
cat ansible.cfg
```

```ini
[defaults]
inventory = ./inventory
remote_user = root
ask_pass = false

[privilege_escalation]
become = true
become_method = sudo
become_user = root
become_ask_pass = false
```

> **참고**: 실습 환경에서의 설정
>
> 이 실습에서는 `remote_user = root`로 설정했다. 이는 실습 편의를 위한 것이며, 실제 운영 환경에서는 일반 사용자로 접속 후 `become`을 통해 권한을 상승하는 방식을 권장한다.

<br>

## 설정 파일 우선순위

Ansible은 여러 위치에서 설정 파일을 찾으며, 다음 순서로 우선순위가 적용된다:

1. `ANSIBLE_CONFIG` 환경변수로 지정된 파일
2. **현재 디렉터리의 `ansible.cfg`** ← 가장 많이 사용
3. 홈 디렉터리의 `~/.ansible.cfg`
4. `/etc/ansible/ansible.cfg`

현재 디렉터리에 `ansible.cfg`가 있으면 해당 설정이 우선 적용된다. 이것이 **Kubespray 실행 시 특정 디렉터리에서 실행해야 하는 이유**다. Kubespray는 자체 `ansible.cfg`를 포함하고 있어, 해당 디렉터리에서 실행해야 올바른 설정이 적용된다.

<br>

## 설정 확인 명령어

현재 적용된 Ansible 설정을 확인하려면 `ansible-config` 명령어를 사용한다.

```bash
# (server) #
# 현재 적용된 설정값 출력 (변경된 값만)
ansible-config dump --only-changed
```

```bash
# (server) #
# 사용 가능한 모든 설정 옵션 목록
ansible-config list
```

- `ansible-config dump`: 현재 적용된 모든 설정값 출력. `--only-changed` 옵션으로 기본값과 다른 설정만 확인
- `ansible-config list`: 사용 가능한 모든 설정 옵션과 설명 출력

<br>

# Ad-hoc 명령어

## 개념

Ad-hoc 명령어는 **Playbook 없이 단일 모듈을 즉시 실행하는 방법**이다. 반복하지 않을 일회성 작업이나 빠른 확인 작업에 유용하다.

공식 문서에 따르면:
> Ad hoc commands are great for tasks you repeat rarely. For example, if you want to power off all the machines in your lab for Christmas vacation, you could execute a quick one-liner in Ansible without writing a playbook.

<br>

## 기본 문법

```bash
ansible [pattern] -m [module] -a "[module options]"
```

| 요소 | 설명 |
| --- | --- |
| `pattern` | 대상 호스트 또는 그룹 (예: `all`, `web`, `tnode1`) |
| `-m [module]` | 실행할 모듈 이름 (기본값: `command`) |
| `-a "[options]"` | 모듈에 전달할 인자 |

<br>

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `-m` | 모듈 지정 |
| `-a` | 모듈 인자 |
| `-i` | 인벤토리 파일 지정 |
| `-f` | 병렬 실행 프로세스 수 (기본값: 5) |
| `-u` | 원격 사용자 지정 |
| `--become` | 권한 상승 활성화 |
| `--ask-pass` | SSH 암호 입력 프롬프트 |
| `-C` | Check 모드 (실제 실행 없이 변경 사항만 확인) |

<br>

# 실습

## ping 모듈

`ping` 모듈은 Ansible이 관리 호스트에 연결하고 Python을 실행할 수 있는지 확인한다.

> **주의**: Ansible의 `ping`은 **ICMP ping이 아니다**. SSH 연결 + Python 실행 가능 여부를 테스트하는 모듈이다.

```bash
# (server) #
ansible -m ping web
```

```json
tnode1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
tnode2 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

- `SUCCESS`: 연결 성공
- `"ping": "pong"`: 정상 응답
- `"changed": false`: 호스트에 변경 사항 없음

<br>

### Python 인터프리터 경고 해결

처음 실행 시 다음과 같은 경고가 나타날 수 있다:

```
[WARNING]: Host 'tnode1' is using the discovered Python interpreter at 
'/usr/bin/python3.12', but future installation of another Python interpreter 
could cause a different interpreter to be discovered.
```

이 경고는 Ansible이 Python 인터프리터를 자동 탐지(`auto`)했음을 알려준다. 명시적으로 지정하면 경고가 사라진다.

```bash
# (server) #
# 인벤토리에 Python 인터프리터 명시
cat <<EOT > inventory
[web]
tnode1 ansible_python_interpreter=/usr/bin/python3
tnode2 ansible_python_interpreter=/usr/bin/python3

[db]
tnode3 ansible_python_interpreter=/usr/bin/python3

[all:children]
web
db
EOT
```

경고 없이 실행됨:

```bash
# (server) #
ansible -m ping web
```

```json
tnode1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
tnode2 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

<br>

### 암호 입력 모드

`--ask-pass` 옵션을 사용하면 SSH 암호를 대화형으로 입력할 수 있다.

```bash
# (server) #
ansible -m ping --ask-pass web
```

```
SSH password: 
tnode1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
tnode2 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

> **참고**: 실습 환경 설정에서 root 계정의 비밀번호를 `qwe123`으로 설정했기 때문에 암호 입력으로도 접속이 가능하다. SSH 키 인증이 설정되어 있으면 `--ask-pass` 없이도 접속된다.

<br>

## shell 모듈

`shell` 모듈은 관리 호스트에서 셸 명령을 실행하고 결과를 반환한다. 파이프(`|`), 리다이렉션(`>`), 환경변수 등 셸 기능을 사용할 수 있다.

```bash
# (server) #
ansible -m shell -a "uptime" db
```

```
tnode3 | CHANGED | rc=0 >>
 21:53:50 up  2:39,  1 user,  load average: 0.06, 0.03, 0.00
```

**출력 해석:**
- `tnode3`: 실행 대상 호스트
- `CHANGED`: 명령이 실행됨 (shell/command 모듈은 항상 CHANGED 반환)
- `rc=0`: Return Code. 0은 성공, 0이 아니면 실패
- `>>` 이후: 명령 실행 결과

> **참고**: `uptime` 명령어
>
> 시스템 가동 시간, 현재 로그인 사용자 수, 시스템 부하 평균을 출력한다.
> - `21:53:50`: 현재 시간
> - `up 2:39`: 시스템 가동 시간 (2시간 39분)
> - `1 user`: 현재 로그인한 사용자 수
> - `load average: 0.06, 0.03, 0.00`: 1분, 5분, 15분 평균 부하

다른 셸 명령도 실행해 보자:

```bash
# (server) #
ansible -m shell -a "tail -n 3 /etc/passwd" all
```

```
tnode3 | CHANGED | rc=0 >>
tcpdump:x:72:72::/:/sbin/nologin
vagrant:x:1000:1000::/home/vagrant:/bin/bash
vboxadd:x:991:1::/var/run/vboxadd:/bin/false

tnode1 | CHANGED | rc=0 >>
sshd:x:107:65534::/run/sshd:/usr/sbin/nologin
vagrant:x:1000:1000:vagrant:/home/vagrant:/bin/bash
vboxadd:x:999:1::/var/run/vboxadd:/bin/false

tnode2 | CHANGED | rc=0 >>
sshd:x:107:65534::/run/sshd:/usr/sbin/nologin
vagrant:x:1000:1000:vagrant:/home/vagrant:/bin/bash
vboxadd:x:999:1::/var/run/vboxadd:/bin/false
```

> **참고**: `/etc/passwd` 파일
>
> Linux 사용자 계정 정보가 저장된 파일이다. 각 줄은 `사용자명:x:UID:GID:설명:홈디렉터리:셸` 형식이다.
> - `vagrant:x:1000:1000::/home/vagrant:/bin/bash`: vagrant 사용자, UID/GID 1000, bash 셸 사용
> - `vboxadd`: VirtualBox Guest Additions 관련 시스템 계정

<br>

### command vs shell 모듈

| 모듈 | 특징 |
| --- | --- |
| `command` | 기본 모듈. 셸을 거치지 않고 직접 실행. 파이프, 리다이렉션 불가 |
| `shell` | `/bin/sh`를 통해 실행. 셸 문법(파이프, 변수 등) 사용 가능 |

```bash
# command 모듈 (기본값, -m 생략 가능)
ansible -a "hostname" all

# shell 모듈 (셸 기능 필요 시)
ansible -m shell -a "echo $HOSTNAME | tr 'a-z' 'A-Z'" all
```

<br>

## 기타 유용한 모듈

### copy 모듈 - 파일 복사

```bash
# 파일을 모든 호스트에 복사
ansible -m copy -a "src=/etc/hosts dest=/tmp/hosts" all
```

### file 모듈 - 파일/디렉터리 관리

```bash
# 디렉터리 생성
ansible -m file -a "dest=/tmp/testdir state=directory mode=755" all

# 파일 삭제
ansible -m file -a "dest=/tmp/testdir state=absent" all
```

### setup 모듈 - 시스템 정보 수집

```bash
# 모든 시스템 정보 (Facts) 수집
ansible -m setup all

# 특정 정보만 필터링
ansible -m setup -a "filter=ansible_distribution*" all
```

<br>

# 출력 색상의 의미

![ansible-04-print-color]({{site.url}}/assets/images/ansible-04-print-color.png){: .align-center width="600"}

Ansible 실행 결과는 상태에 따라 다른 색상으로 표시된다:

| 색상 | 상태 | 의미 |
| --- | --- | --- |
| **초록색** | SUCCESS / ok | 성공, 변경 없음 |
| **주황색** | CHANGED | 성공, 변경 있음 |
| **빨간색** | FAILED | 실패 |
| **파란색** | SKIPPED | 조건 불충족으로 건너뜀 |

<br>

## shell 모듈과 멱등성

[Ansible 개요 글]({% post_url 2026-01-12-Kubernetes-Ansible-01 %})에서 멱등성에 대해 살펴볼 때, `shell` 모듈은 **멱등성이 보장되지 않는 대표적인 모듈**이라고 했다. 실제로 위 실습에서 `uptime`이나 `tail` 명령은 시스템에 아무런 변경을 가하지 않았음에도 결과가 모두 `CHANGED`로 표시된다.

![ansible-04-shell-changed-color]({{site.url}}/assets/images/ansible-04-shell-changed-color.png){: .align-center width="600"}

**이유**: `shell`과 `command` 모듈은 Ansible이 명령 실행 전후의 시스템 상태를 비교할 방법이 없다. 단순히 "명령이 실행되었다"는 사실만 알 수 있으므로, 항상 `CHANGED`를 반환한다.

반면, `apt`, `copy`, `file` 같은 모듈은 **현재 상태를 확인한 후 필요한 경우에만 변경**을 수행하므로 멱등성이 보장된다:
- 이미 설치된 패키지 → `ok` (변경 없음)
- 동일한 파일이 존재 → `ok` (변경 없음)
- 변경이 필요한 경우만 → `CHANGED`


<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **설정 파일 이해**: `ansible.cfg`의 섹션 구성과 설정 우선순위
2. **Ad-hoc 명령어**: Playbook 없이 단일 모듈을 즉시 실행하는 방법
3. **주요 모듈 사용**: `ping`, `shell`, `copy`, `file` 등 기본 모듈 활용
4. **출력 해석**: 색상별 상태와 반환 코드의 의미

<br>

Ad-hoc 명령어는 빠른 확인이나 일회성 작업에 유용하지만, 반복적인 작업은 Playbook으로 작성하는 것이 좋다. Playbook은 작업을 문서화하고, 버전 관리가 가능하며, 재사용할 수 있다.

<br>

다음 글에서는 Playbook을 작성하여 여러 작업을 순차적으로 실행하는 방법을 알아본다.
