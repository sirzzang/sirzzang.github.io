---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 2. 인벤토리"
hidden: true
excerpt: "Ansible 인벤토리의 개념과 형식, 구성 요소를 이해하고 실습 환경에서 인벤토리 파일을 작성해 보자."
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

이번 글의 목표는 **Ansible 인벤토리의 개념과 작성법 이해**다.

- 인벤토리 정의: Ansible이 관리할 대상 호스트 목록
- 인벤토리 형식: INI, YAML
- 구성 요소: 호스트, 그룹, 기본 그룹(all, ungrouped), 중첩 그룹(children)
- 인벤토리 검증: `ansible-inventory` 명령어
- 기본 인벤토리 지정: `ansible.cfg`의 `inventory` 설정

<br>

# 인벤토리란?

## 정의

인벤토리(Inventory)는 **Ansible이 자동화 대상으로 하는 관리 호스트(Managed Node)를 지정하는 파일**이다. 인벤토리에 정의된 호스트에 대해서만 Ansible 작업이 실행된다.

인벤토리 파일에는 다음 정보를 포함할 수 있다:
- 관리 대상 호스트의 호스트명 또는 IP 주소
- 호스트를 논리적으로 묶은 그룹
- 호스트별/그룹별 변수

<br>

## 플레이북과의 관계

Ansible에서 실제 자동화 작업을 정의하는 것은 **플레이북(Playbook)**이다. 인벤토리와 플레이북의 관계는 다음과 같다:

```
인벤토리 (Inventory)     플레이북 (Playbook)
   "어디에"         +        "무엇을"
   ─────────────────────────────────────
   관리 대상 호스트           실행할 작업
```

- **인벤토리**: "어떤 서버에 작업할 것인가?"를 정의
- **플레이북**: "어떤 작업을 수행할 것인가?"를 정의

플레이북 실행 시 인벤토리를 지정하면, 해당 인벤토리에 정의된 호스트들에 대해 플레이북의 작업이 실행된다.

```bash
# 플레이북 실행 시 인벤토리 지정
ansible-playbook -i inventory playbook.yml
```

<br>

# 인벤토리 형식

인벤토리는 **INI** 또는 **YAML** 형식으로 작성할 수 있다. 두 형식 모두 동일한 기능을 제공하며, 선호에 따라 선택하면 된다.

## INI 형식

가장 간단한 형태의 INI 스타일 인벤토리는 호스트명 또는 IP 주소를 한 줄씩 나열한다:

```ini
web1.example.com
web2.example.com
db1.example.com
db2.example.com
192.0.2.42
```

그룹을 정의하려면 대괄호(`[]`) 안에 그룹명을 작성하고, 그 아래에 해당 그룹에 속하는 호스트를 나열한다:

```ini
[web]
tnode1
tnode2

[db]
tnode3

[all:children]
web
db
```

<br>

## YAML 형식

동일한 인벤토리를 YAML 형식으로 작성하면 다음과 같다:

```yaml
web:
  hosts:
    tnode1:
    tnode2:
db:
  hosts:
    tnode3:
all:
  children:
    web:
    db:
```

YAML 형식은 계층 구조가 명확하게 드러나며, 복잡한 변수 설정 시 가독성이 좋다.

<br>

# 인벤토리 구성 요소

## 호스트

호스트는 Ansible이 관리할 개별 서버를 의미한다. **호스트명** 또는 **IP 주소** 모두 사용할 수 있다.

```ini
# 호스트명 사용
web1.example.com
tnode1

# IP 주소 사용
192.168.1.10
10.10.1.11
```

> **참고**: 호스트명을 사용하려면 DNS 또는 `/etc/hosts` 파일에서 해당 호스트명을 IP 주소로 해석할 수 있어야 한다.

<br>

## 그룹

그룹은 여러 호스트를 논리적으로 묶은 단위다. 그룹을 사용하면 **역할, 위치, 환경** 등에 따라 호스트를 분류하고, 그룹 단위로 작업을 실행할 수 있다.

```ini
[webservers]
web1.example.com
web2.example.com

[db-servers]
db01.example.com
db02.example.com
```

<br>

## 기본 그룹

Ansible 인벤토리에는 명시적으로 정의하지 않아도 자동으로 존재하는 **두 개의 기본 그룹**이 있다:

| 그룹 | 설명 |
| --- | --- |
| **all** | 인벤토리에 정의된 모든 호스트를 포함하는 그룹 |
| **ungrouped** | 어떤 그룹에도 속하지 않은 호스트를 포함하는 그룹 |

```ini
# 이 인벤토리에서:
server1.example.com    # ungrouped에 속함

[webservers]
web1.example.com       # webservers에 속함, all에도 속함
```

- `all` 그룹을 대상으로 작업을 실행하면 인벤토리의 모든 호스트에 작업이 적용된다
- `ungrouped` 그룹에는 그룹 헤더(`[그룹명]`) 이전에 나열된 호스트가 포함된다

<br>

# 인벤토리 파일 생성

IP 주소나 호스트명을 이용해 인벤토리 파일을 생성할 수 있다.

## IP 주소로 지정

```bash
# (server) #
cat <<EOT > inventory
10.10.1.11
10.10.1.12
10.10.1.13
EOT
```

> **참고**: Heredoc 구분자 (EOF vs EOT)
> 
> `<<EOF`나 `<<EOT`는 **Heredoc(Here Document)** 문법의 구분자(delimiter)다. `EOF`(End Of File)와 `EOT`(End Of Text)는 관례적인 이름일 뿐, 실제로는 아무 문자열이나 사용할 수 있다. 동작에는 차이가 없으며, 문서 내용과 겹치지 않는 고유한 문자열을 선택하면 된다.
>
> ```bash
> # 모두 동일하게 동작
> cat <<EOF > file.txt
> cat <<EOT > file.txt
> cat <<MYDELIMITER > file.txt
> ```

<br>

## 호스트명으로 지정

호스트명을 사용하려면 `/etc/hosts` 파일에 호스트명과 IP 매핑이 되어 있어야 한다.

```bash
# (server) #
# /etc/hosts 파일 확인
cat /etc/hosts
10.10.1.10 server
10.10.1.11 tnode1
10.10.1.12 tnode2
10.10.1.13 tnode3
```

```bash
# (server) #
# 호스트명으로 inventory 파일 생성
cat <<EOT > inventory
tnode1
tnode2
tnode3
EOT
```

<br>

# 인벤토리 검증

`ansible-inventory` 명령어로 인벤토리 파일의 구문 오류를 확인하고, Ansible이 인벤토리를 어떻게 해석하는지 확인할 수 있다.

## --list 옵션

JSON 형식으로 인벤토리의 전체 구조를 출력한다.

```bash
# (server) #
ansible-inventory -i ./inventory --list | jq
```

```json
{
  "_meta": {
    "hostvars": {},
    "profile": "inventory_legacy"
  },
  "all": {
    "children": [
      "ungrouped"
    ]
  },
  "ungrouped": {
    "hosts": [
      "10.10.1.11",
      "10.10.1.12",
      "10.10.1.13"
    ]
  }
}
```

**출력 해석:**
- `_meta.hostvars`: 호스트별 변수 (현재 없음)
- `_meta.profile`: 인벤토리 플러그인 프로파일 정보
- `all.children`: `all` 그룹의 자식 그룹 목록
- `ungrouped.hosts`: 그룹에 속하지 않은 호스트 목록

그룹을 정의하지 않았으므로 모든 호스트가 `ungrouped`에 속해 있다.

> **참고**: `profile: "inventory_legacy"`란?
>
> Ansible 인벤토리 플러그인의 프로파일 정보다. `inventory_legacy`는 전통적인 INI 형식의 정적 인벤토리 파일을 파싱했음을 나타낸다. 동적 인벤토리나 다른 플러그인을 사용하면 다른 값이 표시될 수 있다.

<br>

## --graph 옵션

트리 구조로 인벤토리의 그룹 계층을 시각화한다.

```bash
# (server) #
ansible-inventory -i ./inventory --graph
```

```
@all:
  |--@ungrouped:
  |  |--10.10.1.11
  |  |--10.10.1.12
  |  |--10.10.1.13
```

`@` 기호는 그룹을 나타내며, 하위 항목은 해당 그룹에 속한 호스트 또는 자식 그룹이다.

> **주의**: 인벤토리 파싱 실패 경고
>
> 다음과 같은 경고가 발생하면 인벤토리 파싱에 실패한 것이다:
> ```
> [WARNING]: Unable to parse /root/my-ansible/inventory as an inventory source
> [WARNING]: No inventory was parsed, only implicit localhost is available
> ```
>
> **발생 원인:**
> - 파일이 존재하지 않음 (경로 오타 포함)
> - 파일 형식 오류 (INI/YAML 문법 오류)
> - 파일 권한 문제로 읽을 수 없음
>
> 이 경우 Ansible은 암묵적인 `localhost`만 사용 가능한 상태가 된다. 경로와 파일 내용을 다시 확인하자.

<br>

# 인벤토리 활용

## 그룹별 호스트 설정

호스트에 역할(Role)을 부여하고 역할별로 작업을 수행하려면 그룹을 정의한다. 그룹명은 대괄호(`[]`) 안에 작성하고, 그 아래에 해당 그룹에 속하는 호스트를 나열한다.

```ini
[webservers]
web1.example.com
web2.example.com

[db-servers]
db01.example.com
db02.example.com
```

플레이북에서 특정 그룹만 대상으로 작업을 실행할 수 있다:

```yaml
# webservers 그룹에만 작업 실행
- hosts: webservers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
```

<br>

## 다중 그룹 소속

하나의 호스트는 **여러 그룹에 동시에 속할 수 있다**. 이를 활용하면 역할, 위치, 환경 등 다양한 기준으로 호스트를 분류할 수 있다.

```ini
[webservers]
web1.example.com
web2.example.com
192.0.2.42

[db-servers]
db01.example.com
db02.example.com

[east-datacenter]
web1.example.com
db01.example.com

[west-datacenter]
web2.example.com
db02.example.com

[production]
web1.example.com
web2.example.com
db01.example.com
db02.example.com

[development]
192.0.2.42
```

위 예시에서 `web1.example.com`은 다음 그룹에 모두 속한다:
- `webservers` (역할)
- `east-datacenter` (위치)
- `production` (환경)

이렇게 구성하면 "동쪽 데이터센터의 모든 서버" 또는 "프로덕션 환경의 웹서버"처럼 다양한 조건으로 호스트를 선택할 수 있다.

<br>

## 중첩 그룹 (children)

기존에 정의한 그룹을 포함하는 **상위 그룹**을 만들 수 있다. 그룹 이름에 `:children` 접미사를 추가한다.

```ini
[webservers]
web1.example.com
web2.example.com

[db-servers]
db01.example.com
db02.example.com

[datacenter:children]
webservers
db-servers
```

`datacenter:children`은 `webservers`와 `db-servers` 그룹을 자식으로 포함한다. 결과적으로 `datacenter` 그룹에는 다음 호스트가 포함된다:
- `web1.example.com`
- `web2.example.com`
- `db01.example.com`
- `db02.example.com`

<br>

## 범위 지정

호스트 이름이나 IP 주소가 연속적인 패턴을 따르는 경우, **범위 지정** 문법으로 간결하게 표현할 수 있다. 대괄호 사이에 시작값과 종료값을 콜론(`:`)으로 구분하여 `[start:end]` 형식으로 작성한다.

```ini
[webservers]
web[1:2].example.com

[db-servers]
db[01:02].example.com
```

위 인벤토리는 다음과 같이 전개된다:
- `webservers`: `web1.example.com`, `web2.example.com`
- `db-servers`: `db01.example.com`, `db02.example.com`

> **참고**: `[1:2]`와 `[01:02]`의 차이
> - `[1:2]` → `1`, `2` (숫자 그대로)
> - `[01:02]` → `01`, `02` (앞에 0이 붙은 형태 유지)

### 다양한 범위 지정 예시

```ini
# IP 주소 범위: 192.168.4.0 ~ 192.168.4.255
[defaults]
192.168.4.[0:255]

# 호스트명 범위: com01.example.com ~ com20.example.com
[compute]
com[01:20].example.com

# 알파벳 범위: a.dns.example.com ~ c.dns.example.com
[dns]
[a:c].dns.example.com

# IPv6 범위: 2001:db8::a ~ 2001:db8::f
[ipv6]
2001:db8::[a:f]
```

**범위 지정 원리:**
- 숫자 범위(`[1:10]`)와 알파벳 범위(`[a:z]`) 모두 지원
- 문자열 패턴 매칭 방식으로 동작하며, 시작값과 종료값 사이의 모든 값을 순차적으로 생성
- 알파벳 범위는 ASCII 코드 순서를 따름

> **주의**: IPv6 주소에서 범위 지정 시, 콜론(`:`)이 IPv6 구분자와 범위 구분자로 중복 사용될 수 있어 혼란을 줄 수 있다. `2001:db8::[a:f]`처럼 범위 부분을 명확히 구분해야 한다. `[2001:2007]:db[1:7]::[a:f]`와 같은 복잡한 패턴은 지원되지 않는다.

<br>

# 기본 인벤토리 파일

Ansible 설치 시 `/etc/ansible/hosts` 파일이 기본 인벤토리로 제공된다. 이 파일은 인벤토리 작성 방법에 대한 예시와 주석이 포함되어 있다.

```bash
# (server) #
cat /etc/ansible/hosts
```

```ini
# This is the default ansible 'hosts' file.
#
# It should live in /etc/ansible/hosts
#
#   - Comments begin with the '#' character        # 주석은 '#'으로 시작
#   - Blank lines are ignored                      # 빈 줄은 무시됨
#   - Groups of hosts are delimited by [header]    # 그룹은 [헤더]로 구분
#   - You can enter hostnames or ip addresses      # 호스트명 또는 IP 주소 사용 가능
#   - A hostname/ip can be a member of multiple groups  # 하나의 호스트가 여러 그룹에 속할 수 있음
```

### 예시 1: 그룹 없는 호스트 (Ungrouped)

그룹 헤더(`[그룹명]`) 이전에 나열된 호스트는 자동으로 `ungrouped` 그룹에 속한다.

```ini
# Ex 1: Ungrouped hosts, specify before any group headers:

## green.example.com
## blue.example.com
## 192.168.100.1
## 192.168.100.10
```


### 예시 2: 그룹 정의

```ini
# Ex 2: A collection of hosts belonging to the 'webservers' group:

## [webservers]
## alpha.example.org
## beta.example.org
## 192.168.1.100
## 192.168.1.110
```

### 예시 3: 범위 패턴

범위 지정은 호스트명 중간에도 사용할 수 있다.

```ini
# If you have multiple hosts following a pattern, you can specify
# them like this:

## www[001:006].example.com    # www001 ~ www006

# You can also use ranges for multiple hosts:

## db-[99:101]-node.example.com    # db-99-node ~ db-101-node
```


### 예시 4: OS별 그룹

```ini
# Ex 4: Multiple hosts arranged into groups such as 'Debian' and 'openSUSE':

## [Debian]
## alpha.example.org
## beta.example.org

## [openSUSE]
## green.example.com
## blue.example.com
```

<br>

## 기본 인벤토리 검증

`/etc/ansible/hosts` 파일은 모든 내용이 주석 처리되어 있으므로, 검증 시 빈 인벤토리로 해석된다.

```bash
# (server) #
ansible-inventory -i /etc/ansible/hosts --list
```

```json
{
    "_meta": {
        "hostvars": {}
    },
    "all": {
        "children": [
            "ungrouped"
        ]
    }
}
```

주석을 제외하면 실제 호스트가 없으므로 `ungrouped`에 호스트가 없고, `all` 그룹의 자식으로 `ungrouped`만 표시된다.

<br>


# 실습: 그룹이 포함된 인벤토리

실습 환경에서 그룹을 포함한 인벤토리 파일을 생성해 보자.

## 인벤토리 파일 생성

```bash
# (server) #
cat <<EOT > inventory
[web]
tnode1
tnode2

[db]
tnode3

[all:children]
web
db
EOT
```

```bash
# (server) #
cat inventory
```

```ini
[web]
tnode1
tnode2

[db]
tnode3

[all:children]
web
db
```

<br>

## 인벤토리 검증

```bash
# (server) #
ansible-inventory -i ./inventory --list | jq
```

```json
{
  "_meta": {
    "hostvars": {},
    "profile": "inventory_legacy"
  },
  "all": {
    "children": [
      "ungrouped",
      "web",
      "db"
    ]
  },
  "db": {
    "hosts": [
      "tnode3"
    ]
  },
  "web": {
    "hosts": [
      "tnode1",
      "tnode2"
    ]
  }
}
```

```bash
# (server) #
ansible-inventory -i ./inventory --graph
```

```
@all:
  |--@ungrouped:
  |--@web:
  |  |--tnode1
  |  |--tnode2
  |--@db:
  |  |--tnode3
```

`web` 그룹에 `tnode1`, `tnode2`가, `db` 그룹에 `tnode3`이 속해 있다. `all:children`으로 두 그룹을 `all`의 자식으로 명시적으로 정의했다.

<br>

# ansible.cfg로 기본 인벤토리 지정

`ansible.cfg`에 기본 인벤토리 경로를 지정하면 매번 `-i` 옵션을 사용하지 않아도 된다.

```bash
# (server) #
cat <<EOT > ansible.cfg
[defaults]
inventory = ./inventory
EOT
```

```bash
# (server) #
# -i 옵션 없이 인벤토리 확인
ansible-inventory --list | jq
```

```json
{
  "_meta": {
    "hostvars": {},
    "profile": "inventory_legacy"
  },
  "all": {
    "children": [
      "ungrouped",
      "web",
      "db"
    ]
  },
  "db": {
    "hosts": [
      "tnode3"
    ]
  },
  "web": {
    "hosts": [
      "tnode1",
      "tnode2"
    ]
  }
}
```

> **참고**: `ansible.cfg`의 전체 구조(섹션 구성, 설정 우선순위 등)는 [다음 글]({% post_url 2026-01-12-Kubernetes-Ansible-04 %})에서 자세히 다룬다.

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **인벤토리 개념 이해**: Ansible이 관리할 대상 호스트를 정의하는 파일
2. **형식 이해**: INI, YAML 두 가지 형식으로 작성 가능
3. **구성 요소 이해**: 호스트, 그룹, 기본 그룹(all, ungrouped), 중첩 그룹(children)
4. **인벤토리 검증**: `ansible-inventory` 명령어로 구문 확인 및 해석 결과 확인
5. **기본 인벤토리 지정**: `ansible.cfg`로 인벤토리 경로 설정

<br>

Ansible 인벤토리는 "어디에" 작업할지를 정의하는 파일이며, 플레이북과 함께 사용하여 자동화 작업을 수행한다. 그룹과 중첩 그룹을 활용하면 역할, 위치, 환경 등 다양한 기준으로 호스트를 분류하고 관리할 수 있다.

<br>

다음 글에서는 Ad-hoc 명령어를 통해 인벤토리에 정의된 호스트에 간단한 작업을 실행해 본다.
