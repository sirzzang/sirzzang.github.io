---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 11. 태그(Tags)"
excerpt: "Ansible 태그를 활용하여 플레이북의 특정 작업만 선택적으로 실행하거나 건너뛰는 방법을 실습해보자."
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

이번 글의 목표는 **Ansible 태그(Tags)를 활용한 선택적 작업 실행 이해**다.

- 태그: 플레이북에서 특정 작업만 선택적으로 실행하거나 건너뛰기 위한 키워드
- 태그 추가 대상: 개별 작업, 블록, 플레이, 롤, imports/includes
- 태그 실행 옵션: `--tags`, `--skip-tags`, `--list-tags`, `--list-tasks`
- 특수 태그: `always`, `never`, `tagged`, `untagged`, `all`

<br>

# 태그란?

**태그**(Tags)는 플레이북에서 **특정 작업만 선택적으로 실행하거나 건너뛰도록 설정**하기 위한 기능이다.

플레이북이 큰 경우, 전체 플레이북을 실행하는 대신 특정 부분만 실행하는 것이 유용할 수 있다. 태그를 사용하면 이를 쉽게 구현할 수 있다.

`tags` 키워드는 플레이북의 '사전 처리(pre processing)' 단계에 포함되며, 실행 가능한 작업을 결정할 때 높은 우선순위를 갖는다. 사전 처리는 [Playbook 실행 과정]({{site.url}}/kubernetes/Kubernetes-Ansible-01/#playbook과-module)의 1~3단계(Playbook 파싱, 모듈 찾기, 파라미터 변환)에서 태그를 평가하여 실행할 작업을 결정하는 과정을 의미한다.

- 참고: [Ansible Tags 공식 문서](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html)

<br>

태그 사용 과정은 두 단계로 구성된다:

1. **태그 추가**: 작업에 태그를 추가한다. 태그는 개별 작업, 블록, 플레이, 롤 또는 imports에 추가할 수 있다.
2. **태그 선택**: 플레이북을 실행할 때 `--tags` 또는 `--skip-tags` 옵션으로 태그를 선택하거나 건너뛴다.

`tags` 키워드를 통해 태그를 추가하더라도 이는 태그를 정의하고 작업에 추가할 뿐, 실행할 작업을 선택하거나 건너뛰지는 않는다. 실제 작업 선택/건너뛰기는 **플레이북 실행 시 명령줄에서만** 가능하다.


<br>

# 태그 추가

`tags` 키워드를 사용하여 다양한 수준에서 태그를 추가할 수 있다. `tags` 키워드는 항상 태그를 정의하고 작업에 추가하며, 실행할 작업을 선택하거나 건너뛰지는 않는다. **플레이북을 실행**할 때 **명령줄에서만** 태그를 기반으로 작업을 선택하거나 건너뛸 수 있다.

| 수준 | 설명 | 태그 적용 범위 |
|------|------|---------------|
| **개별 작업** (task) | 단일 Task에 태그 추가 | 해당 Task만 |
| **블록** (block) | block 구문에 태그 추가 | block 내 모든 Task |
| **플레이** (play) | play 수준에 태그 추가 | play 내 모든 Task |
| **롤** (role) | role 호출 시 태그 추가 | role 내 모든 Task |
| **imports/includes** | import_tasks, include_tasks 등에 태그 추가 | 포함된 모든 Task |

```yaml
# 예시: 다양한 수준의 태그 적용
---
- hosts: all
  tags: play_tag                # Play 수준 - 이 play의 모든 작업에 적용

  tasks:
    - name: Single task         # 개별 작업 수준
      debug:
        msg: "Task 1"
      tags: task_tag            # 이 task에만 적용

    - block:                    # Block 수준
        - name: Block task 1
          debug:
            msg: "Block 1"
        - name: Block task 2
          debug:
            msg: "Block 2"
      tags: block_tag           # block 내 모든 task에 적용

    - import_tasks: setup.yml   # Import 수준
      tags: import_tag          # setup.yml의 모든 task에 적용

  roles:
    - role: webserver           # Role 수준
      tags: role_tag            # webserver role의 모든 task에 적용
```

## 개별 작업에 태그 추가

가장 기본적인 수준에서, 개별 작업에 하나 이상의 태그를 적용할 수 있다. playbooks, task files 또는 role 내의 작업에 태그를 추가할 수 있다.

### 두 작업에 서로 다른 태그 지정

```yaml
tasks:
- name: Install the servers
  ansible.builtin.yum:
    name:
    - httpd
    - memcached
    state: present
  tags:
  - packages
  - webservers

- name: Configure the service
  ansible.builtin.template:
    src: templates/src.j2
    dest: /etc/foo.conf
  tags:
  - configuration
```

### 여러 작업에 동일한 태그 적용

```yaml
---
# file: roles/common/tasks/main.yml

- name: Install ntp
  ansible.builtin.yum:
    name: ntp
    state: present
  tags: ntp

- name: Configure ntp
  ansible.builtin.template:
    src: ntp.conf.j2
    dest: /etc/ntp.conf
  notify:
  - restart ntpd
  tags: ntp

- name: Enable and run ntpd
  ansible.builtin.service:
    name: ntpd
    state: started
    enabled: true
  tags: ntp

- name: Install NFS utils
  ansible.builtin.yum:
    name:
    - nfs-utils
    - nfs-util-lib
    state: present
  tags: filesharing
```

위 예시에서 `--tags ntp`로 플레이북을 실행하면, Ansible은 `ntp` 태그가 지정된 **세 가지 작업은 실행**하고 `filesharing` 태그가 지정된 **한 가지 작업은 건너뛴다**.

## 블록에 태그 추가

플레이북의 특정 블록에 태그를 추가한다. 플레이 내 일부 태스크 묶음을 블록으로 정의하고, 블록 수준에서 태그를 정의하면 된다. 블록 내 모든 태스크가 해당 태그를 상속 받는다. 
- 블록 내 모든 태스크가 해당 태그를 상속받는다. 
- 플레이의 모든 작업에 태그를 적용하지 않고, 일부 작업에만 특정 태그를 적용하고자 할 때 유용하다.

```yaml
# myrole/tasks/main.yml
- name: ntp tasks
  tags: ntp # 블록 레벨 태그
  block:
  - name: Install ntp
    ansible.builtin.yum:
      name: ntp
      state: present

  - name: Configure ntp
    ansible.builtin.template:
      src: ntp.conf.j2
      dest: /etc/ntp.conf
    notify:
    - restart ntpd

  - name: Enable and run ntpd
    ansible.builtin.service:
      name: ntpd
      state: started
      enabled: true

- name: Install NFS utils
  ansible.builtin.yum:
    name:
    - nfs-utils
    - nfs-util-lib
    state: present
  tags: filesharing
```


### 주의: 블록 내 개별 태스크 태그와 rescue/always

블록 내 개별 태스크에 태그를 추가하는 경우는 블록 레벨 태스크 추가가 아니라, **개별 태스크 태그 추가**이다. 

이 경우, `tag` 선택 옵션이 `block`의 오류 처리를 포함한 다른 대부분의 논리보다 우선한다. 따라서 `rescue`나 `always` 섹션에 태그를 설정하지 않으면, `tag` 선택 옵션(*`-tags` 등*)으로 실행했을 때, 해당 섹션의 작업이 실행되지 않을 수 있다.

```yaml
- block:
  - debug: msg=run with tag, but always fail
    failed_when: true
    tags: example

  rescue:
  - debug: msg=I always run because the block always fails, except if you select to only run 'example' tag

  always:
  - debug: msg=I always run, except if you select to only run 'example' tag
```

위 예시는 태그 지정 없이 호출하면 3개의 작업을 모두 실행하지만, `--tags example`을 지정하여 실행하면 **첫 번째 작업만 실행**한다.

<br>

## Plays에 태그 추가

플레이에 포함된 모든 작업에 동일한 태그를 지정해야 하는 경우, 플레이 수준에서 태그를 추가할 수 있다.

```yaml
- hosts: all
  tags: ntp

  tasks:
  - name: Install ntp
    ansible.builtin.yum:
      name: ntp
      state: present

  - name: Configure ntp
    ansible.builtin.template:
      src: ntp.conf.j2
      dest: /etc/ntp.conf
    notify:
    - restart ntpd

  - name: Enable and run ntpd
    ansible.builtin.service:
      name: ntpd
      state: started
      enabled: true

- hosts: fileservers
  tags: filesharing
  tasks:
  # ...
```

## Roles에 태그 추가

롤 수준에서 태그를 추가할 수 있다. 이 경우, **해당 롤의 모든 작업**뿐만 아니라 **해당 롤의 종속 작업(dependencies)**에도 태그가 적용된다.

롤에 태그를 추가하는 방법은 **3가지**가 있다. 각 방법의 태그 적용 범위가 다르다.

| 방법 | 태그 적용 범위 | `--tags` 실행 시 |
|------|---------------|------------------|
| `roles` 키워드 | 롤 내 **모든 작업**에 적용 | 롤 **전체** 실행 or 전체 스킵 |
| `import_role` | 롤 내 **모든 작업**에 적용 | 롤 **전체** 실행 or 전체 스킵 |
| 롤 내 개별 작업 태그 + `include_role` | 지정한 작업에만 적용 | 롤 내 **일부 작업만** 선택 실행 가능 |

### roles 키워드에서 태그 설정

`roles` 키워드와 함께 롤을 정적으로 통합하면 Ansible은 해당 롤의 모든 작업에 정의한 태그를 추가한다.

```yaml
roles:
  - role: webserver
    vars:
      port: 5000
    tags: [ web, foo ] 
```

또는 YAML 형식으로 아래와 같이 지정할 수도 있다.

```yaml
---
- hosts: webservers
  roles:
    - role: foo
      tags:
        - bar
        - baz
    # using YAML shorthand, this is equivalent to:
    # - { role: foo, tags: ["bar", "baz"] }
```

> 여러 태그를 지정하면 OR 조건으로 작동한다. 즉, 위의 예시에서 `--tags bar` 또는 `--tags baz` 중 하나만 지정해도 해당 롤이 실행된다.

<br>

### import_role에서 태그 설정

정적 `import_role` 및 `import_tasks` 문에서 가져온 모든 작업에 태그를 적용할 수 있다.

```yaml
---
- hosts: webservers
  tasks:
    - name: Import the foo role
      import_role:
        name: foo
      tags:
        - bar
        - baz

    - name: Import tasks from foo.yml
      import_tasks: foo.yml
      tags: [ web, foo ]
```

### include_role + 롤 내 개별 작업/블록에 태그 설정 

롤 내의 **일부 작업만 선택적으로 실행**하기 위한 방법이다. 

위의 두 방법(`roles` 키워드, `import_role`)은 롤에 태그를 붙이면 **롤 전체**가 실행된다. 롤 안의 특정 작업만 골라서 실행하려면, 롤 내의 개별 작업이나 블록에 태그를 설정하고, 플레이북에서 동적 `include_role`을 사용한 다음, 동일한 태그를 include 항목에 추가해야 한다.

```yaml
# roles/foo/tasks/main.yml
- name: Setup task
  debug: msg="Setting up..."
  tags: setup

- name: Cleanup task
  debug: msg="Cleaning up..."
  tags: cleanup
```

```yaml
# playbook.yml
- hosts: webservers
  tasks:
    - name: Include foo role
      include_role:
        name: foo
      tags: setup  # include 항목에도 동일한 태그 추가
```

| 실행 명령 | 결과 |
|----------|------|
| `ansible-playbook playbook.yml` | Setup task, Cleanup task **둘 다** 실행 |
| `ansible-playbook playbook.yml --tags setup` | **Setup task만** 실행 |
| `ansible-playbook playbook.yml --tags cleanup` | 아무것도 실행 안 됨 (include 항목 자체가 `cleanup` 태그가 없어서 건너뜀) |

> **참고**: `--tags setup`으로 실행하면 Ansible이 먼저 `include_role` 항목을 실행하고(태그 `setup`이 있으므로), 그 다음 롤 내에서 `setup` 태그가 있는 작업만 선택적으로 실행한다.

> *아래 "Includes에 태그 추가" 섹션에서 dynamic include의 태그 동작을 더 자세히 다룬다.*

<br>

## Includes에 태그 추가

플레이북의 **dynamic includes 항목**에 태그를 적용할 수 있다. 개별 작업의 태그와 마찬가지로, `include_*` 작업의 태그는 **include 항목 자체에만 적용**되며 **포함된 파일이나 롤 내의 작업에는 적용되지 않는다**.
- 참고: [Selectively running tagged tasks in reusable files](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html#selective-reuse)

dynamic **includes** 항목에 태그를 추가한 다음 `--tags mytags`로 해당 플레이북을 실행하면, Ansible은 **include 항목 자체를 실행**하고 포함된 파일이나 롤 내의 모든 작업을 해당 태그로 지정한 후, 해당 태그 없이 포함된 파일이나 롤 내의 모든 작업을 건너뛸 수 있다.

<br>

다른 작업에 태그를 추가하는 것과 동일한 방식으로 태그를 추가한다:

```yaml
---
# file: roles/common/tasks/main.yml

- name: Dynamic reuse of database tasks
  include_tasks: db.yml
  tags: db
```

아래 예시에서 `foo` 태그는 `bar` 롤 내부의 작업에는 적용되지 않는다:

```yaml
---
- hosts: webservers
  tasks:
    - name: Include the bar role
      include_role:
        name: bar
      tags:
        - foo
```

<br>

# 태그 상속

**태그 상속**(Tag Inheritance)은 상위 수준에서 정의한 태그가 **모든 하위 작업에 자동으로 적용**되는 것을 말한다. 태그 상속 여부는 태그를 정의한 위치에 따라 달라진다:

- **태그 상속이 적용되는 경우:**
  - 플레이 수준의 태그
  - 블록 수준의 태그
  - `roles` 키워드의 태그
  - 정적 imports (`import_role`, `import_tasks`)

- **태그 상속이 적용되지 않는 경우:**
  - 동적 includes (`include_role`, `include_tasks`)

## 동적 includes 태그 상속

동적 includes에 태그를 추가하면 **include 항목 자체**에만 적용되며, 포함된 파일이나 롤 내의 작업에는 적용되지 않는다. 이로 인해, 아래와 같은 문제 상황이 발생할 수 있다:

```yaml
# db.yml (포함될 파일)
- name: Create database
  mysql_db: name=mydb

- name: Create user
  mysql_user: name=admin
```

```yaml
# playbook.yml
- include_tasks: db.yml
  tags: db
```

이렇게 하고 `--tags db`로 실행하면 겉껍데기(`include` 작업)는 실행되지만, 정작 실제로 해야 할 일(`db.yml` 내부 태스크)이 스킵되는 황당한 상황이 발생한다.
- `include_tasks` 작업 자체는 `db` 태그가 **있으므로** 실행됨 
- 하지만 db.yml 내부의 태스크들은 `db` 태그가 **없으므로** 스킵됨

따라서 이러한 상황을 해결하고자, 동적 include에서 태그 상속이 필요한 경우, `apply` 키워드 또는 `block`을 사용할 수 있다.

### apply 키워드 사용

`apply` 키워드를 사용하면 포함된 파일 내부의 태스크들에도 태그를 전파할 수 있다.

```yaml
- name: Apply the db tag to the include and to all tasks in db.yml
  include_tasks:
    file: db.yml
    apply:
      tags: db    # ← db.yml 내부 태스크들에 'db' 태그 전파
  tags: db        # ← include_tasks 작업 자체에 'db' 태그 적용
```

| 부분 | 역할 |
|------|------|
| `tags: db` (바깥) | `--tags db` 실행 시 이 include 작업 자체가 실행되게 함 |
| `apply: tags: db` | db.yml 내부 태스크들에도 `db` 태그를 전파 |

> **참고**: 둘 다 필요하다. 바깥 `tags`만 있으면 include는 실행되지만 내부 태스크가 스킵되고, `apply`만 있으면 `--tags db` 실행 시 include 자체가 스킵된다.

### block 사용

`block`으로 감싸면 블록의 태그가 내부 작업에 상속된다.

```yaml
- block:
   - name: Include tasks from db.yml
     include_tasks: db.yml
  tags: db
```

이 방법은 `apply`보다 간단하지만, 블록 안의 모든 작업에 동일한 태그가 적용된다.

# 핸들러에 태그 추가

**핸들러**(handlers)는 알림을 받았을 때만 실행되는 특수한 작업 유형으로, **모든 태그를 무시**하며 선택 대상이 될 수 없다.

<br>

# 태그 선택 및 건너 뛰기

작업에 태그를 추가하고, 포함(include), 블록(block), 플레이(play), 역할(role) 및 가져오기(import)를 완료한 후, **ansible-playbook을 실행**할 때 **태그를 기반**으로 **작업을 선택적으로 실행**하거나 **건너뛸** 수 있다.

- Ansible은 명령줄에서 전달하는 태그와 일치하는 태그로 모든 작업을 실행하거나 건너뛸 수 있다.
- 블록 또는 플레이 수준, 역할, 가져오기에서 태그를 추가한 경우 해당 태그는 블록 내의 모든 작업, 플레이, 역할 또는 가져오기에 적용된다.
- 여러 태그가 있는 역할이 있고 다른 시간에 역할의 하위 집합을 호출하고 싶다면 동적 포함과 함께 사용하거나 역할을 여러 역할로 나누어야 한다.

## 명령줄 옵션

ansible-playbook은 **다섯 가지 태그 관련 명령줄 옵션**을 제공한다:

| 옵션 | 설명 | 비고 |
|------|------|------|
| `--tags all` | 태그 지정 여부와 관계없이 모든 작업 실행 | `never` 태그 제외 (기본 동작) |
| `--tags tag1,tag2` | tag1 또는 tag2 태그가 있는 작업만 실행 | `always` 태그된 작업도 포함 |
| `--skip-tags tag3,tag4` | tag3 또는 tag4 태그가 있는 작업 제외하고 모든 작업 실행 | `never` 태그 작업도 제외 |
| `--tags tagged` | 태그가 하나 이상 있는 작업만 실행 | `never` 태그를 덮어쓰지 않음 |
| `--tags untagged` | 태그가 없는 작업만 실행 | `always`를 덮어씀 |

사용 예시는 다음과 같다.

```bash
# configuration 또는 packages 태그가 있는 작업만 실행
ansible-playbook example.yml --tags "configuration,packages"

# packages 태그가 있는 작업 제외하고 실행
ansible-playbook example.yml --skip-tags "packages"

# never 태그가 있는 작업도 포함하여 모든 작업 실행
ansible-playbook example.yml --tags "all,never"

# tag1 또는 tag3 태그 작업 실행, tag4는 건너뜀
ansible-playbook example.yml --tags "tag1,tag3" --skip-tags "tag4"
```

# 태그 미리보기

실행 전 어떤 작업이 어떤 태그를 가지고 있는지 확인할 수 있다.

| 옵션 | 설명 | 사용 예시 |
|------|------|-----------|
| `--list-tags` | 사용 가능한 태그 목록 표시 | `ansible-playbook playbook.yml --list-tags` |
| `--list-tasks` | 실행될 작업 목록 미리보기(`--tags`나 `--skip-tags`와 함께 사용) | `ansible-playbook playbook.yml --tags "configuration" --list-tasks` |

```bash
# 플레이북에 정의된 사용 가능한 모든 태그 목록 확인 (실행하지 않음)
ansible-playbook example.yml --list-tags

# configuration, packages 태그가 있는 작업 목록 미리보기 (실행하지 않음)
ansible-playbook example.yml --tags "configuration,packages" --list-tasks
```

> **참고**: 이 명령줄 플래그들은 **동적으로 포함된 파일이나 롤 내의 태그나 작업은 표시할 수 없다**.

<br>

# 특수 태그

Ansible은 특별한 동작을 위해 `always`, `never`, `tagged`, `untagged`, `all` 등 여러 태그 이름을 예약한다.

| 특수 태그 | 설명 | 사용 목적 |
|-----------|------|-----------|
| `always` | 항상 실행 (`--skip-tags always`로 명시적 건너뛰기 가능) | 작업 자체를 태그 |
| `never` | 항상 건너뜀 (`--tags never`로 명시적 실행 가능) | 작업 자체를 태그 |
| `tagged` | 태그가 하나 이상 있는 작업만 실행 | 태그 선택 시 사용 |
| `untagged` | 태그가 없는 작업만 실행 | 태그 선택 시 사용 |
| `all` | 모든 작업 실행 (기본 동작) | 태그 선택 시 사용 |

- `always`와 `never`는 주로 **작업 자체를 태그**하는 데 사용
- 나머지 세 가지는 **실행하거나 건너뛸 태그를 선택**할 때 사용

## always 태그

`always` 태그를 작업이나 플레이에 할당하면, 특정 작업을 건너뛰거나(`--skip-tags always`) 해당 작업에 정의된 다른 태그를 제외하고는 **항상 해당 작업을 실행**한다.

```yaml
tasks:
- name: Print a message
  ansible.builtin.debug:
    msg: "Always runs"
  tags:
  - always

- name: Print a message
  ansible.builtin.debug:
    msg: "runs when you use specify tag1, all(default) or tagged"
  tags:
  - tag1

- name: Print a message
  ansible.builtin.debug:
    msg: "always runs unless you explicitly skip, like if you use ``--skip-tags tag2``"
  tags:
     - always
     - tag2
```

> **참고**: **내부 팩트 수집 작업(Gathering Facts)**은 기본적으로 `always` 태그가 지정되어 있다. 하지만 태그를 플레이에 적용하고 직접 건너뛰거나(`--skip-tags`) 다른 태그를 사용할 때 간접적으로 건너뛸 수 있다.

## never 태그

`never` 태그를 작업이나 플레이에 할당하면, 특별히 요청하지 않는 한(`--tags never`) 또는 해당 작업에 정의된 다른 태그를 사용하지 않는 한 **해당 작업이나 플레이를 건너뛴다**.

```yaml
tasks:
  - name: Run the rarely-used debug task, either with ``--tags debug`` or ``--tags never``
    ansible.builtin.debug:
     msg: '{{ showmevar }}'
    tags: [ never, debug ]
```

위 예시에서 `--tags debug` 또는 `--tags never`로 실행해야만 해당 작업이 실행된다.

```bash
# 실행 예시
ansible-playbook playbook.yml --tags "never"    # never 태그 작업만 실행
ansible-playbook playbook.yml --tags "tagged"   # 태그가 있는 모든 작업 실행
ansible-playbook playbook.yml --tags "untagged" # 태그가 없는 모든 작업 실행
```

<br>

# 주의 사항

Ansible 태그 지정 및 선택에 따른 동작 과정에서 다음의 사항에 주의한다:

1. **태그 미지정 시 동작**
   - 플레이북 실행 시 태그 옵션을 지정하지 않으면, 모든 작업이 실행됨 (`never` 태그 제외)
   
2. **태그 상속**
   - 정적 imports에는 태그 상속이 적용되지만, 동적 includes에는 적용되지 않음
   - 자세한 내용은 위의 [태그 상속](#태그-상속) 참조
   
3. **태그 이름 규칙**
   - 태그 이름은 문자, 숫자, 밑줄(`_`), 하이픈(`-`)을 사용할 수 있음
   - 의미 있고 일관된 명명 규칙을 사용하는 것이 좋음 (예: `install`, `configure`, `deploy`)
   
4. **여러 플레이에서의 태그**
   - 한 플레이북에 여러 플레이가 있을 때, 각 플레이의 작업에 같은 이름의 태그를 사용할 수 있음
   - `--tags` 옵션은 모든 플레이에서 해당 태그가 지정된 작업을 실행함

5. **성능 고려사항**
   - 태그를 사용하면 불필요한 작업을 건너뛰어 플레이북 실행 시간을 단축할 수 있음
   - 하지만 fact gathering은 기본적으로 항상 실행됨 (`gather_facts: no`로 비활성화 가능)

<br>

# 실습 1: 기본 태그 사용

두 작업에 서로 다른 태그를 지정하고, 플레이북 실행 시 선택하거나 건너뛰어 보자.

## 플레이북 작성

```bash
# (server) #
cat << EOF > tags1.yml
---
- hosts: web
  tasks:
    - name: Install the servers
      ansible.builtin.apt:
       name:
         - htop
       state: present
      tags:
        - packages

    - name: Restart the service
      ansible.builtin.service:
        name: rsyslog
        state: restarted
      tags:
        - service
EOF
```

## 실행 1: 태그 목록 확인

```bash
# (server) #
ansible-playbook tags1.yml --list-tags
```

## 실행 2: 특정 태그의 작업 목록 확인

```bash
# (server) #
ansible-playbook tags1.yml --tags "packages" --list-tasks
```

## 실행 3: 특정 태그만 실행

`packages` 태그가 포함된 작업만 실행한다.

```bash
# (server) #
ansible-playbook tags1.yml --tags "packages"
```

## 실행 4: 특정 태그 제외

`packages` 태그가 포함된 작업만 제외하고 실행한다.

```bash
# (server) #
ansible-playbook tags1.yml --skip-tags "packages"
```

## 실행 5: 태그가 하나 이상 있는 작업만 실행

```bash
# (server) #
ansible-playbook tags1.yml --tags tagged
```

<br>


# 실습 2: 개별 작업에 태그 지정하기

가장 기본적인 수준에서, 개별 작업에 하나 이상의 태그를 적용할 수 있다. 아래 예시에서는 여러 작업에 서로 다른 태그를 지정하고, `--tags`, `--skip-tags` 옵션으로 선택적으로 실행한다.

## 플레이북 작성

4개 작업에 서로 다른 태그 조합을 지정한 플레이북을 작성한다.
- 단일 작업에 태그 적용 가능
- 여러 작업에 동일한 태그 적용 가능

```bash
# (server) #
cat <<'EOT' > tags-example.yml
---
- hosts: tnode1
  tasks:
    - name: Install web servers
      apt:
        name:
          - nginx
          - apache2
        state: present
      tags:
        - packages
        - webservers

    - name: Create web content directory
      file:
        path: /var/www/html/test
        state: directory
        mode: '0755'
      tags:
        - configuration
        - webservers

    - name: Create test file
      copy:
        content: "Test page for tags\n"
        dest: /var/www/html/test/index.html
      tags:
        - configuration

    - name: Install monitoring tools
      apt:
        name:
          - htop
          - iotop
        state: present
      tags:
        - packages
        - monitoring
EOT
```
- `packages`: 패키지 설치 작업
- `webservers`: 웹 서버 관련 작업
- `configuration`: 설정 및 파일 생성 작업
- `monitoring`: 모니터링 도구 설치 작업


## 실행 1: 태그 목록 확인

플레이북에 어떤 태그가 있는지 확인한다.

```bash
# (server) #
ansible-playbook tags-example.yml --list-tags
```

플레이북에 정의된 모든 태그가 알파벳 순으로 표시됨을 확인할 수 있다.

```bash
# 실행 결과
playbook: tags-example.yml

  play #1 (tnode1): tnode1	TAGS: []
      TASK TAGS: [configuration, monitoring, packages, webservers]
```

- `play #1 (tnode1): tnode1 TAGS: []`: Play 수준에는 태그가 없음
- `TASK TAGS`: Task 수준에 정의된 4개의 고유 태그
- 실제 실행 없이 플레이북의 태그 구조를 빠르게 파악할 수 있다.

## 실행 2: 특정 태그만 실행

`packages` 태그가 지정된 작업만 실행한다.

```bash
# (server) #
ansible-playbook tags-example.yml --tags packages
```

`packages` 태그가 있는 작업만 실행됨을 확인할 수 있다.

```bash
# 실행 결과
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install web servers] *****************************************************
ok: [tnode1]

TASK [Install monitoring tools] ************************************************
changed: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업** (총 2개):
  - **Install web servers** (`packages`, `webservers` 태그): `ok` (nginx, apache2가 이미 설치되어 있음)
  - **Install monitoring tools** (`packages`, `monitoring` 태그): `changed` (htop, iotop를 새로 설치)
- **건너뛴 작업**: "Create web content directory", "Create test file"은 `packages` 태그가 없어서 건너뛰었다.
- **PLAY RECAP**: `ok=3`은 Gathering Facts를 포함한 숫자 (실제 태그로 선택된 작업은 2개), `changed=1` (실제로 변경된 작업은 1개)

## 실행 3: 여러 태그 동시 실행

`configuration,webservers` 태그가 지정된 작업을 실행한다. 여러 개의 태그를 지정하면 OR 조건이 적용되어 태그 중 하나라도 일치하면 실행된다.

```bash
# (server) #
ansible-playbook tags-example.yml --tags configuration,webservers
```

**OR 조건**에 의해 `configuration` **또는** `webservers` 태그가 있는 작업이 실행됨을 확인할 수 있다.

```bash
# 실행 결과
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install web servers] *****************************************************
ok: [tnode1]

TASK [Create web content directory] ********************************************
changed: [tnode1]

TASK [Create test file] ********************************************************
changed: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=4    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업** (총 3개):
  - **Install web servers** (`webservers` 태그): `ok` (이미 설치됨)
  - **Create web content directory** (`configuration`, `webservers` 태그): `changed` (디렉터리 새로 생성)
  - **Create test file** (`configuration` 태그): `changed` (파일 새로 생성)
- **건너뛴 작업**: "Install monitoring tools"는 `monitoring` 태그만 있어서 건너뛰었다.
- **PLAY RECAP**: `ok=4`는 Gathering Facts를 포함한 숫자 (실제 태그로 선택된 작업은 3개)

## 실행 4: 특정 태그 제외

`monitoring` 태그를 제외하고 실행한다.

```bash
# (server) #
ansible-playbook tags-example.yml --skip-tags monitoring
```

**`--skip-tags` 동작**에 의해 `monitoring` 태그가 **없는** 작업들이 실행됨을 확인할 수 있다.

```bash
# 실행 결과
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install web servers] *****************************************************
ok: [tnode1]

TASK [Create web content directory] ********************************************
ok: [tnode1]

TASK [Create test file] ********************************************************
ok: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업** (총 3개):
  - **Install web servers** (`packages`, `webservers` 태그): `ok` (이미 설치됨)
  - **Create web content directory** (`configuration`, `webservers` 태그): `ok` (이미 존재함)
  - **Create test file** (`configuration` 태그): `ok` (이미 존재함)
- **건너뛴 작업**: "Install monitoring tools" 작업은 `monitoring` 태그만 있어서 건너뛰었다.
- **멱등성**: 모든 작업이 `ok`로 표시됨 (이미 설정된 상태와 동일)
- **PLAY RECAP**: `ok=4`는 Gathering Facts를 포함한 숫자 (실제 실행된 작업은 3개)
- `--skip-tags`는 특정 태그를 가진 작업을 명시적으로 제외할 때 유용하다.

## 실행 5: 작업 목록 확인 (실제 실행 안 함)

특정 태그로 실행 시 어떤 작업이 실행될지 미리 확인한다.

```bash
# (server) #
ansible-playbook tags-example.yml --tags webservers --list-tasks
```

실행 결과:

```
playbook: tags-example.yml

  play #1 (tnode1): tnode1      TAGS: []
    tasks:
      Install web servers       TAGS: [packages, webservers]
      Create web content directory      TAGS: [configuration, webservers]
```

- **필터링 결과**: `webservers` 태그를 가진 2개 작업만 표시되었다.
- **태그 정보 포함**: 각 작업의 태그 목록도 함께 표시되어, 어떤 태그 조합으로 실행될지 확인 가능하다.
- **Dry-run 검증**: 실제 실행 전에 영향 범위를 확인할 수 있어 안전하다.

<br>

# 실습 3: 블록(Blocks)에 태그 추가

플레이의 일부 작업에만 태그를 적용하려면 블록을 사용하고 블록 수준에서 태그를 정의한다. 블록에 태그를 지정하면 블록 내 모든 작업에 해당 태그가 자동으로 적용된다.

## 블록에 태그 지정

개별 작업에 일일이 태그를 추가하는 대신, 블록에 한 번만 태그를 지정하면 블록 내 모든 작업에 태그가 상속된다.

### 플레이북 작성

블록 수준에서 태그를 지정하면 블록 내 모든 작업에 자동으로 적용된다.

```bash
# (server) #
cat <<'EOT' > tags-block-example.yml
---
- hosts: tnode1
  tasks:
    - name: System setup tasks
      tags: system
      block:
        - name: Install system tools
          apt:
            name:
              - curl
              - wget
            state: present

        - name: Create system directory
          file:
            path: /opt/system-config
            state: directory
            mode: '0755'

    - name: Database setup tasks
      tags: database
      block:
        - name: Install database client
          apt:
            name: postgresql-client
            state: present

        - name: Create database directory
          file:
            path: /opt/db-config
            state: directory
            mode: '0755'

    - name: Install monitoring
      apt:
        name: htop
        state: present
      tags: monitoring
EOT
```

### 실행: system 태그만 실행

```bash
# (server) #
ansible-playbook tags-block-example.yml --tags system
```

실행 결과:

```bash
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install system tools] ****************************************************
changed: [tnode1]

TASK [Create system directory] *************************************************
changed: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업**: `system` 블록의 2개 작업만 실행
- **건너뛴 작업**: `database` 블록과 `monitoring` 작업은 건너뜀

### 실행: 여러 태그 동시 실행

```bash
# (server) #
ansible-playbook tags-block-example.yml --tags database,monitoring
```

실행 결과:

```bash
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install database client] *************************************************
changed: [tnode1]

TASK [Create database directory] ***********************************************
changed: [tnode1]

TASK [Install monitoring] ******************************************************
changed: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=4    changed=3    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업**: `database` 블록(2개) + `monitoring`(1개) = 총 3개 작업

### 블록과 오류 처리

**중요**: 태그 선택은 블록의 오류 처리(`rescue`, `always`)보다 우선한다.

```bash
# (server) #
cat <<'EOT' > tags-block-rescue.yml
---
- hosts: localhost
  tasks:
    - block:
        - name: Task that always fails
          debug:
            msg: "This will fail"
          failed_when: true
          tags: example

      rescue:
        - name: Rescue task
          debug:
            msg: "Run on failure"

      always:
        - name: Always task
          debug:
            msg: "Always run"
EOT
```

#### 태그 없이 전체 실행

```bash
# (server) #
ansible-playbook tags-block-rescue.yml
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Task that always fails] **************************************************
ok: [localhost] => {
    "msg": "This will fail"
}

TASK [Task that always fails] **************************************************
fatal: [localhost]: FAILED! => {"msg": "Failed as requested from task"}

TASK [Rescue task] *************************************************************
ok: [localhost] => {
    "msg": "Run on failure"
}

TASK [Always task] *************************************************************
ok: [localhost] => {
    "msg": "Always run"
}

PLAY RECAP *********************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=1    ignored=0
```

#### example 태그만 실행

```bash
# (server) #
ansible-playbook tags-block-rescue.yml --tags example
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Task that always fails] **************************************************
ok: [localhost] => {
    "msg": "This will fail"
}

TASK [Task that always fails] **************************************************
fatal: [localhost]: FAILED! => {"msg": "Failed as requested from task"}

PLAY RECAP *********************************************************************
localhost                  : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
```

- **태그 선택이 우선**: `--tags example`로 실행하면 `rescue`와 `always` 섹션이 **실행되지 않음**
- 태그가 없는 `rescue`, `always`는 건너뛰어짐

<br>

# 실습 4: Plays에 태그 추가

플레이에 포함된 모든 작업에 동일한 태그를 지정해야 하는 경우, 플레이 수준에서 태그를 추가할 수 있다.

## 플레이 수준 태그 지정

```bash
# (server) #
cat <<'EOT' > tags-play-example.yml
---
- hosts: tnode1
  tags: webserver
  tasks:
    - name: Install web server
      apt:
        name: nginx
      state: present

    - name: Start web server
      service:
        name: nginx
      state: started

- hosts: tnode1
  tags: database
  tasks:
    - name: Install database client
      apt:
        name: postgresql-client
        state: present

    - name: Create database config
      file:
        path: /etc/db.conf
        state: touch
        mode: '0644'
EOT
```

### 태그 목록 확인

```bash
# (server) #
ansible-playbook tags-play-example.yml --list-tags
```

```
playbook: tags-play-example.yml

  play #1 (tnode1): tnode1    TAGS: [webserver]
      TASK TAGS: []

  play #2 (tnode1): tnode1    TAGS: [database]
      TASK TAGS: []
```

- 플레이 수준에 태그가 지정되어 있고, 개별 작업에는 태그가 없음

### webserver 태그만 실행

```bash
# (server) #
ansible-playbook tags-play-example.yml --tags webserver
```

```bash
PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install web server] ******************************************************
changed: [tnode1]

TASK [Start web server] ********************************************************
ok: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업**: 첫 번째 플레이의 모든 작업(2개) 실행
- **건너뛴 작업**: 두 번째 플레이(database) 전체 건너뜀

### database 태그만 실행

```bash
# (server) #
ansible-playbook tags-play-example.yml --tags database
```

```bash
PLAY [tnode1] ******************************************************************
skipping: no hosts matched

PLAY [tnode1] ******************************************************************

TASK [Gathering Facts] *********************************************************
ok: [tnode1]

TASK [Install database client] *************************************************
changed: [tnode1]

TASK [Create database config] **************************************************
changed: [tnode1]

PLAY RECAP *********************************************************************
tnode1                     : ok=3    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **실행된 작업**: 두 번째 플레이의 모든 작업(2개) 실행
- **건너뛴 작업**: 첫 번째 플레이(webserver) 전체 건너뜀

<br>

# 실습 5: Roles에 태그 추가

롤에 태그를 추가하는 방법은 **3가지**가 있다.

## 방법 1: roles 키워드에서 태그 설정

`roles` 키워드와 함께 롤을 정적으로 통합할 때 태그를 정의하면, Ansible은 해당 롤의 모든 작업에 태그를 추가한다.

```yaml
---
- hosts: webservers
  roles:
  - role: webserver
    vars:
      port: 5000
    tags: [ web, foo ]
```

또는 YAML 형식으로:

```yaml
---
- hosts: webservers
  roles:
    - role: foo
      tags:
        - bar
        - baz
```

> **중요**: 롤 수준에서 태그를 추가하면 **해당 롤의 모든 작업**뿐만 아니라 **종속 롤(dependencies)의 작업에도 태그가 적용**된다.

### 실습: 롤에 태그 적용

아래와 같은 디렉토리 구조를 생성한다:

```
.
├── roles/
│   └── webserver/
│       └── tasks/
│           └── main.yml
└── site.yml
```

```yaml
# roles/webserver/tasks/main.yml
---
- name: Install web packages
  debug:
    msg: "Installing web packages on port {{ port | default(80) }}"

- name: Configure web server
  debug:
    msg: "Configuring web server"

- name: Start web service
  debug:
    msg: "Starting web service"
```

```yaml
# site.yml
---
- hosts: localhost
  connection: local
  roles:
    - role: webserver
      vars:
        port: 5000
      tags: [ web, foo ]
```

태그가 롤의 모든 작업에 적용되었는지 확인한다:

```bash
$ ansible-playbook site.yml --list-tags

playbook: site.yml

  play #1 (localhost): localhost    TAGS: []
      TASK TAGS: [foo, web]
```

`web` 태그로 실행하면 롤의 모든 작업이 실행된다:

```bash
$ ansible-playbook site.yml --tags web

PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [webserver : Install web packages] ****************************************
ok: [localhost] => {
    "msg": "Installing web packages on port 5000"
}

TASK [webserver : Configure web server] ****************************************
ok: [localhost] => {
    "msg": "Configuring web server"
}

TASK [webserver : Start web service] *******************************************
ok: [localhost] => {
    "msg": "Starting web service"
}

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

> **참고**: `ok=4`인 이유는 Ansible이 기본으로 **Gathering Facts** 태스크를 실행하기 때문이다. 롤의 작업 3개 + Gathering Facts 1개 = 4개. 이를 비활성화하려면 플레이에 `gather_facts: false`를 추가하면 된다.

## 방법 2: import_role에서 태그 설정

정적 `import_role` 및 `import_tasks` 문에서 가져온 모든 작업에 태그를 적용할 수 있다.

```yaml
---
- hosts: webservers
  tasks:
    - name: Import the foo role
      import_role:
        name: foo
      tags:
        - bar
        - baz

    - name: Import tasks from foo.yml
      import_tasks: foo.yml
      tags: [ web, foo ]
```

## 방법 3: 롤 내 개별 작업/블록에 태그 설정

롤 내의 **일부 작업만 선택적으로 실행**하려면 이 방법이 **유일한 방법**이다.

롤 내의 개별 작업이나 블록에 태그를 설정하고, 플레이북에서 동적 `include_role`을 사용한 다음, 동일한 태그를 include 항목에 추가해야 한다.

```yaml
# roles/foo/tasks/main.yml
- name: Install packages
  ansible.builtin.apt:
    name: nginx
    state: present
  tags: packages

- name: Configure service
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  tags: configuration
```

```yaml
# playbook.yml
---
- hosts: webservers
  tasks:
    - name: Include the foo role
      include_role:
        name: foo
      tags:
        - packages
        - configuration
```

`--tags packages`로 실행하면 `foo` 롤 내에서 `packages` 태그가 있는 작업만 실행된다.

<br>

# 실습 6: Includes에 태그 추가 및 태그 상속

## Includes에 태그 추가

플레이북의 dynamic includes 항목에 태그를 적용할 수 있다.

**중요**: 개별 작업의 태그와 마찬가지로, `include_*` 작업의 태그는 **include 항목 자체에만 적용**되며 **포함된 파일이나 롤 내의 작업에는 적용되지 않는다**.

```yaml
---
# file: roles/common/tasks/main.yml

- name: Dynamic reuse of database tasks
  include_tasks: db.yml
  tags: db
```

아래 예시에서 `foo` 태그는 `bar` 롤 내부의 작업에는 적용되지 않는다:

```yaml
---
- hosts: webservers
  tasks:
    - name: Include the bar role
      include_role:
        name: bar
      tags:
        - foo
```

## 태그 상속: blocks 및 apply 키워드

기본적으로 Ansible은 `include_role`과 `include_tasks`를 사용하는 **동적 재사용(dynamic reuse)**에 **태그 상속을 적용하지 않는다**.

Include 항목에 태그를 추가하면 **include 항목 자체**에만 적용되며 포함된 파일이나 롤의 어떤 작업에도 적용되지 않는다. 이를 통해 롤 또는 작업 파일 내에서 선택한 작업을 실행할 수 있다.

태그 상속이 필요한 경우, 다음 두 가지 방법을 사용할 수 있다:

### 방법 1: apply 키워드 사용

```yaml
- name: Apply the db tag to the include and to all tasks in db.yml
  include_tasks:
    file: db.yml
    # adds 'db' tag to tasks within db.yml
    apply:
      tags: db
  # adds 'db' tag to this 'include_tasks' itself
  tags: db
```

### 방법 2: block 사용

```yaml
- block:
   - name: Include tasks from db.yml
     include_tasks: db.yml
  tags: db
```

## 핸들러(Handlers)에 태그 추가

**핸들러**(handlers)는 알림을 받았을 때만 실행되는 특수한 작업 유형으로, **모든 태그를 무시**하며 선택 대상이 될 수 없다.

<br>

# 실습 7: 특수 태그 (Special Tags)

Ansible은 특별한 동작을 위해 다음 태그 이름을 예약한다.

## 특수 태그 종류

| 특수 태그 | 설명 | 사용 목적 |
|-----------|------|-----------|
| `always` | 항상 실행 (`--skip-tags always`로 명시적 건너뛰기 가능) | 작업 자체를 태그 |
| `never` | 항상 건너뜀 (`--tags never`로 명시적 실행 가능) | 작업 자체를 태그 |
| `tagged` | 태그가 하나 이상 있는 작업만 실행 | 태그 선택 시 사용 |
| `untagged` | 태그가 없는 작업만 실행 | 태그 선택 시 사용 |
| `all` | 모든 작업 실행 (기본 동작) | 태그 선택 시 사용 |

- `always`와 `never`는 주로 **작업 자체를 태그**하는 데 사용
- 나머지 세 가지는 **실행하거나 건너뛸 태그를 선택**할 때 사용

## always 태그 실습

`always` 태그를 작업에 할당하면, 특정 작업을 건너뛰거나(`--skip-tags always`) 해당 작업에 정의된 다른 태그를 제외하고는 **항상 해당 작업을 실행**한다.

```bash
# (server) #
cat <<'EOT' > tags-always-example.yml
---
- hosts: localhost
tasks:
    - name: Always print this message
      debug:
        msg: "This always runs"
  tags:
  - always

    - name: Print tag1 message
      debug:
        msg: "This runs when you specify tag1"
  tags:
  - tag1

    - name: Print tag2 message (also always)
      debug:
        msg: "This always runs unless you explicitly skip tag2"
  tags:
     - always
     - tag2

    - name: Print untagged message
      debug:
        msg: "This runs without any tag specification"
EOT
```

### 실행 1: 태그 없이 실행

```bash
# (server) #
ansible-playbook tags-always-example.yml
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Always print this message] ***********************************************
ok: [localhost] => {
    "msg": "This always runs"
}

TASK [Print tag1 message] ******************************************************
ok: [localhost] => {
    "msg": "This runs when you specify tag1"
}

TASK [Print tag2 message (also always)] ****************************************
ok: [localhost] => {
    "msg": "This always runs unless you explicitly skip tag2"
}

TASK [Print untagged message] **************************************************
ok: [localhost] => {
    "msg": "This runs without any tag specification"
}

PLAY RECAP *********************************************************************
localhost                  : ok=5    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **모든 작업 실행**: 태그 없이 실행하면 모든 작업이 실행됨

### 실행 2: tag1만 실행

```bash
# (server) #
ansible-playbook tags-always-example.yml --tags tag1
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Always print this message] ***********************************************
ok: [localhost] => {
    "msg": "This always runs"
}

TASK [Print tag1 message] ******************************************************
ok: [localhost] => {
    "msg": "This runs when you specify tag1"
}

TASK [Print tag2 message (also always)] ****************************************
ok: [localhost] => {
    "msg": "This always runs unless you explicitly skip tag2"
}

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **always 태그 작업은 항상 실행**: tag1 지정해도 always 태그 작업 2개 + tag1 작업 = 총 3개 실행

### 실행 3: always 태그 건너뛰기

```bash
# (server) #
ansible-playbook tags-always-example.yml --skip-tags always
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Print tag1 message] ******************************************************
ok: [localhost] => {
    "msg": "This runs when you specify tag1"
}

TASK [Print untagged message] **************************************************
ok: [localhost] => {
    "msg": "This runs without any tag specification"
}

PLAY RECAP *********************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **always 태그 건너뜀**: 명시적으로 `--skip-tags always`로 건너뛸 수 있음

> **참고**: **내부 팩트 수집 작업(Gathering Facts)**은 기본적으로 `always` 태그가 지정되어 있다.

## never 태그 실습

`never` 태그를 작업에 할당하면, 특별히 요청하지 않는 한(`--tags never`) **해당 작업을 건너뛴다**.

```bash
# (server) #
cat <<'EOT' > tags-never-example.yml
---
- hosts: localhost
tasks:
    - name: Normal task
      debug:
        msg: "This runs normally"

    - name: Dangerous operation
      debug:
        msg: "This only runs when explicitly requested"
      tags: [ never, dangerous ]

    - name: Debug task
      debug:
        msg: "This runs with debug tag or never tag"
    tags: [ never, debug ]
EOT
```

### 실행 1: 태그 없이 실행

```bash
# (server) #
ansible-playbook tags-never-example.yml
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Normal task] *************************************************************
ok: [localhost] => {
    "msg": "This runs normally"
}

PLAY RECAP *********************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **never 태그 작업 건너뜀**: never 태그가 있는 2개 작업은 실행되지 않음

### 실행 2: debug 태그로 실행

```bash
# (server) #
ansible-playbook tags-never-example.yml --tags debug
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Debug task] **************************************************************
ok: [localhost] => {
    "msg": "This runs with debug tag or never tag"
}

PLAY RECAP *********************************************************************
localhost                  : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **debug 태그 지정하면 실행**: never와 debug 태그가 함께 있는 작업이 실행됨

### 실행 3: never 태그로 실행

```bash
# (server) #
ansible-playbook tags-never-example.yml --tags never
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Dangerous operation] *****************************************************
ok: [localhost] => {
    "msg": "This only runs when explicitly requested"
}

TASK [Debug task] **************************************************************
ok: [localhost] => {
    "msg": "This runs with debug tag or never tag"
}

PLAY RECAP *********************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **never 태그 명시적 실행**: `--tags never`로 never 태그가 있는 모든 작업 실행

<br>

# 실습 8: 재사용 가능한 파일에서 선택적 실행

롤이나 작업 파일 내에서 태그가 지정된 작업을 선택적으로 실행하려면, **동적 include**를 사용하고 **include 항목과 내부 작업에 동일한 태그**를 설정해야 한다.

## 태그가 지정된 작업 파일 생성

```bash
# (server) #
cat <<'EOT' > mixed-tasks.yml
---
# mixed-tasks.yml
- name: Run the task with no tags
  debug:
    msg: "This task has no tags"

- name: Run the tagged task
  debug:
    msg: "This task is tagged with mytag"
  tags: mytag

- name: Install package (mytag)
  apt:
    name: tree
    state: present
  tags: mytag
EOT
```

## 플레이북에서 작업 파일 포함 (태그 상속 없음)

```bash
# (server) #
cat <<'EOT' > tags-include-no-inherit.yml
---
- hosts: localhost
  tasks:
    - name: Run tasks from mixed-tasks.yml
      include_tasks: mixed-tasks.yml
      tags: mytag
EOT
```

### 실행: mytag 지정

```bash
# (server) #
ansible-playbook tags-include-no-inherit.yml --tags mytag
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Run the task with no tags] ***********************************************
ok: [localhost] => {
    "msg": "This task has no tags"
}

TASK [Run the tagged task] *****************************************************
ok: [localhost] => {
    "msg": "This task is tagged with mytag"
}

TASK [Install package (mytag)] *************************************************
ok: [localhost]

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **include_tasks의 태그는 상속되지 않음**: include문 자체만 `mytag`로 선택되고, 내부 작업 중 `mytag`가 있는 작업만 실행됨
- 실제로는 **모든 작업이 실행됨** (태그가 없는 작업 포함)

## 태그 상속 적용: apply 키워드 사용

```bash
# (server) #
cat <<'EOT' > tags-include-with-apply.yml
---
- hosts: localhost
  tasks:
    - name: Apply the mytag to all tasks in mixed-tasks.yml
    include_tasks:
        file: mixed-tasks.yml
        apply:
    tags: mytag
      tags: mytag
EOT
```

### 실행: mytag 지정

```bash
# (server) #
ansible-playbook tags-include-with-apply.yml --tags mytag
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Run the task with no tags] ***********************************************
ok: [localhost] => {
    "msg": "This task has no tags"
}

TASK [Run the tagged task] *****************************************************
ok: [localhost] => {
    "msg": "This task is tagged with mytag"
}

TASK [Install package (mytag)] *************************************************
ok: [localhost]

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **apply 키워드로 태그 상속**: `apply` 내 `tags: mytag`로 포함된 파일의 모든 작업에 `mytag` 적용

## 태그 상속 적용: block 사용

```bash
# (server) #
cat <<'EOT' > tags-include-with-block.yml
---
- hosts: localhost
  tasks:
    - block:
        - name: Include tasks from mixed-tasks.yml
          include_tasks: mixed-tasks.yml
      tags: mytag
EOT
```

### 실행: mytag 지정

```bash
# (server) #
ansible-playbook tags-include-with-block.yml --tags mytag
```

```bash
PLAY [localhost] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [localhost]

TASK [Run the task with no tags] ***********************************************
ok: [localhost] => {
    "msg": "This task has no tags"
}

TASK [Run the tagged task] *****************************************************
ok: [localhost] => {
    "msg": "This task is tagged with mytag"
}

TASK [Install package (mytag)] *************************************************
ok: [localhost]

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

- **block으로 태그 상속**: 블록 수준에 태그를 지정하여 포함된 파일의 모든 작업에 태그 적용

<br>

# 정리

## 실습 파일 삭제

```bash
# (server) #
rm -f tags1.yml tags-*.yml mixed-tasks.yml
```

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **태그 추가**: 작업, 블록, 플레이, 롤, includes에 태그 적용
2. **태그 선택**: `--tags`, `--skip-tags`로 선택적 실행
3. **특수 태그**: `always`, `never`, `tagged`, `untagged`, `all`
4. **태그 상속**: 정적 imports에만 적용, 동적 includes는 `apply` 또는 `block` 필요
5. **태그 미리보기**: `--list-tags`, `--list-tasks`로 실행 전 확인

<br>

태그를 활용하면 대규모 플레이북에서 특정 부분만 선택적으로 실행할 수 있다. Kubespray에서도 설치, 업그레이드, 네트워크 설정 등 단계별로 태그를 활용하여 필요한 작업만 실행한다.

<br>

다음 글에서는 **Ansible Galaxy**를 활용하여 커뮤니티 롤을 검색하고 설치하는 방법을 알아본다.
