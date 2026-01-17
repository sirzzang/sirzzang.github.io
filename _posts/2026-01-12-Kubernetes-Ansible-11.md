---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 10. 롤(Role)"
excerpt: "Ansible 롤(Role)을 활용하여 재사용 가능한 Playbook 구조를 만드는 방법을 실습해 보자."
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

이번 글의 목표는 **Ansible 롤(Role)의 구조와 사용법 이해**다.

- 롤: 플레이북 내용을 기능 단위로 나누어 재사용하기 위한 구조
- 롤 생성: `ansible-galaxy role init 롤이름`
- 롤 추가: `import_role` (정적), `include_role` (동적)
- 특수 섹션: `pre_tasks`, `post_tasks`

<br>

# 롤이란?

## 개념

**롤**(Role)은 **플레이북 내용을 기능 단위로 나누어 공통 부품으로 관리/재사용하기 위한 구조**다. 플레이북에서 전달된 변수를 사용할 수 있고, 변수 미 설정 시 기본값을 롤의 해당 변수에 설정하기도 한다.

> **참고**: [Ansible Roles 공식 문서](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_reuse_roles.html)

<br>

## 롤의 필요성

지금까지 배운 모든 Ansible 요소들(tasks, handlers, variables, files, templates, conditionals, loops)은 **하나의 플레이북 파일에 모두 작성**되었다.

### 문제점

이와 같은 작성 방식은 작은 프로젝트에서는 문제없지만, 프로젝트가 커지면 다음과 같은 문제가 발생한다:

| 문제점 | 설명 |
|--------|------|
| **코드 중복** | 웹 서버 설치를 여러 플레이북에서 반복 작성 |
| **유지보수 어려움** | 수정 시 여러 파일을 찾아다녀야 함 |
| **구조 불명확** | tasks, vars, handlers가 한 파일에 섞여 있음 |
| **재사용 불가** | 다른 프로젝트에서 사용하려면 복사-붙여넣기 필요 |
| **협업 어려움** | 팀마다 다른 구조로 작성 |


### 롤의 해결 방법

롤은 **Ansible이 자동으로 인식하는 표준화된 디렉터리 구조**를 제공한다:

```yaml
# 롤 없이 (모든 것이 한 파일에)
---
- hosts: webservers
  vars:
    service_name: httpd
  tasks:
    - name: Install httpd
      dnf:
        name: httpd
        state: present
      notify: restart httpd
    - name: Copy index.html
      copy:
        src: files/index.html
        dest: /var/www/html/
  handlers:
    - name: restart httpd
      service:
        name: "{{ service_name }}"
        state: restarted
```

```yaml
# 롤 사용 (체계적으로 분리)
---
- hosts: webservers
  roles:
    - webserver-role  # ← 이것만!
```

롤 디렉터리 구조는 다음과 같이 자동으로 통합된다:

```bash
webserver-role/
├── vars/main.yml       # ← Ansible이 자동으로 변수 로드
├── tasks/main.yml      # ← Ansible이 자동으로 태스크 실행
├── handlers/main.yml   # ← 변경 시 Ansible이 자동으로 핸들러 실행
└── files/index.html    # ← copy 모듈이 자동으로 인식
```

### 핵심

롤은 **"누군가"가 조각들을 합쳐주는 구조**가 아니라, **Ansible이 자동으로 인식하고 통합하는 표준 구조**다. 개발자는 정해진 디렉터리에 파일만 배치하면 되고, Ansible이 알아서 로딩 순서와 실행을 관리한다.

<br>

## 특징
롤을 사용하면, 아래와 같은 장점이 있다:
- 콘텐츠를 그룹화하여 코드를 다른 사용자와 쉽게 공유
- 웹 서버, DB 서버 등 시스템 유형별 필수 요소 정의
- 대규모 프로젝트를 쉽게 관리
- 다른 사용자와 동시에 개발
- Ansible Galaxy를 통해 공유하거나 다른 사람의 롤 사용


<br>

## 롤 구조

롤은 하위 디렉토리 및 파일의 표준화된 구조로 정의된다.
- 최상위 디렉토리: 롤 자체의 이름을 의미함
- 최상위 디렉토리 안에 tasks, handlers 등 롤에서 목적에 따라 정의된 하위 디렉토리가 구성됨


| 디렉터리 | 설명 |
| --- | --- |
| `defaults` | `main.yml` 파일에 롤이 사용될 때 **덮어쓸 수 있는 롤 변수의 기본값** 포함. 우선순위가 낮으며 플레이에서 변경 가능 |
| `files` | 롤 작업에서 참조한 **정적 파일** 저장 (copy 모듈 등에서 사용) |
| `handlers` | `main.yml` 파일에 롤의 **핸들러 정의** 포함 |
| `meta` | `main.yml` 파일에 롤에 대한 정보 포함: 작성자, 라이선스, **플랫폼, 옵션, 롤 종속성** 등 |
| `tasks` | `main.yml` 파일에 롤의 **작업 정의** 포함 (롤의 주요 로직) |
| `templates` | 롤 작업에서 참조할 **Jinja2 템플릿** 저장 (template 모듈에서 사용) |
| `tests` | 롤을 테스트하는 데 사용할 **인벤토리와 test.yml 플레이북** 포함 |
| `vars` | `main.yml` 파일에 롤의 **변수 값** 정의. 롤 내부 목적으로 사용되며 **우선순위가 높아 플레이북에서 변경 불가** |

> **주의**: 각 디렉터리는 **main.yml을 진입점**으로 사용하지만, **다른 yml 파일도 포함 가능**하다. 예를 들어 `tasks/main.yml`에서 `include_tasks`나 `import_tasks`로 `tasks/setup.yml`, `tasks/configure.yml` 등을 참조할 수 있다.

```
my-role/              # 최상위 디렉토리
├── defaults/
│   └── main.yml      # 가변 변수 (우선순위 낮음, 덮어쓰기 가능)
├── files/            # 정적 파일 (copy 모듈에서 사용)
│   └── config.conf
├── handlers/
│   └── main.yml      # 핸들러 정의
├── meta/
│   └── main.yml      # 롤 메타 정보 (작성자, 라이선스, 플랫폼, 종속성 등)
├── tasks/
│   ├── main.yml      # 메인 태스크 (진입점)
│   ├── setup.yml     # 추가 태스크 파일 (main.yml에서 include 가능)
│   └── configure.yml # 추가 태스크 파일
├── templates/        # Jinja2 템플릿 (template 모듈에서 사용)
│   └── config.j2
├── tests/            # 테스트용 파일
│   ├── inventory     # 테스트용 인벤토리
│   └── test.yml      # 테스트용 플레이북
└── vars/
    └── main.yml      # 불변 변수 (우선순위 높음, 내부 목적용)
```

<br>

## main.yml과 추가 파일

각 디렉터리의 **main.yml은 진입점**이지만, 복잡한 롤에서는 **추가 yml 파일을 분리**하여 관리할 수 있다.

**예시: tasks 디렉터리**

```yaml
# tasks/main.yml (진입점)
---
- name: Include OS-specific tasks
  include_tasks: "{{ ansible_os_family }}.yml"

- name: Include setup tasks
  import_tasks: setup.yml

- name: Include configure tasks
  import_tasks: configure.yml
```

```yaml
# tasks/Debian.yml
---
- name: Install package on Debian
  apt:
    name: myapp
    state: present
```

```yaml
# tasks/RedHat.yml
---
- name: Install package on RedHat
  dnf:
    name: myapp
    state: present
```

**include vs import**:
- **`include_tasks`**: 런타임에 동적으로 포함 (조건부 포함 가능)
- **`import_tasks`**: 플레이북 파싱 시 정적으로 포함

<br>

# 실습 1: 롤 생성

## ansible-galaxy 명령어

`ansible-galaxy role` 명령어로 롤을 생성, 관리할 수 있다.

```bash
# (server) #
# 롤 관련 서브 명령어 확인
ansible-galaxy role -h
```

**출력 결과**:

```
usage: ansible-galaxy role [-h] ROLE_ACTION ...

positional arguments:
  ROLE_ACTION
    init       Initialize new role with the base structure of a role.
    remove     Delete roles from roles_path.
    delete     Removes the role from Galaxy. It does not remove or alter
               the actual GitHub repository.
    list       Show the name and version of each role installed in the
               roles_path.
    search     Search the Galaxy database by tags, platforms, author and
               multiple keywords.
    import     Import a role into a galaxy server
    setup      Manage the integration between Galaxy and the given
               source.
    info       View more details about a specific role.
    install    Install role(s) from file(s), URL(s) or Ansible Galaxy

options:
  -h, --help   show this help message and exit
```

**주요 서브 명령어**:
- **`init`**: 새 롤 초기화 (디렉터리 구조 생성)
- **`list`**: 설치된 롤 목록 확인
- **`search`**: Galaxy에서 롤 검색
- **`info`**: 롤 상세 정보 확인
- **`install`**: 롤 설치
- **`remove`**: 롤 삭제

<br>

## 롤 생성

```bash
# (server) #
cd ~/my-ansible

# 롤 생성
ansible-galaxy role init my-role
```

**출력 결과**:

```
- Role my-role was created successfully
```

<br>

## 생성된 구조 확인

```bash
# (server) #
# 디렉터리 구조 확인
tree ./my-role/
```

**출력 결과**:

```
./my-role
├── defaults
│   └── main.yml
├── files
├── handlers
│   └── main.yml
├── meta
│   └── main.yml
├── README.md
├── tasks
│   └── main.yml
├── templates
├── tests
│   ├── inventory
│   └── test.yml
└── vars
    └── main.yml

9 directories, 8 files
```

생성된 롤은 기본 디렉터리 구조와 각 디렉터리의 `main.yml` 파일을 포함한다.

<br>

# 실습 2: 롤 개발

## 목표

Apache 웹 서버를 설치하고 index.html 파일을 배포하는 롤을 개발한다.

<br>

## 프로세스

롤이 수행할 작업 흐름은 다음과 같다:

1. **운영체제 확인**: 롤이 호출되면 현재 호스트의 운영체제 버전이 **지원 운영체제 목록**에 포함되는지 확인한다.
2. **패키지 설치**: 운영체제가 CentOS나 레드햇이면 **httpd 관련 패키지**를 `dnf` 모듈을 이용해 설치한다.
3. **파일 복사**: 설치가 끝나면 제어 노드의 `files` 디렉터리 안에 있는 `index.html` 파일을 관리 노드의 `/var/www/html` 디렉터리에 복사한다.
4. **서비스 재시작**: 파일 복사가 끝나면 `httpd` 서비스를 재시작한다.

<br>

## 롤 구조

이 실습에서는 아래와 같은 구조로 롤을 작성한다:

```bash
my-role/
├── defaults/
│   └── main.yml          # 가변 변수: service_title
├── files/
│   └── index.html        # 배포할 HTML 파일
├── handlers/
│   └── main.yml          # restart service (httpd 서비스 재시작)
├── tasks/
│   └── main.yml          # install service, copy html file
└── vars/
    └── main.yml          # 불변 변수: service_name, src_file_path, dest_file_path,
                          #            httpd_packages, supported_distros
```

**디렉터리별 역할**:
- **`tasks/main.yml`**: 메인 태스크 (패키지 설치, 파일 복사)
- **`files/index.html`**: 배포할 정적 HTML 파일
- **`handlers/main.yml`**: httpd 서비스 재시작 핸들러
- **`defaults/main.yml`**: 플레이북에서 변경 가능한 변수 (`service_title`)
- **`vars/main.yml`**: 롤 내부에서 사용하는 불변 변수 (`service_name`, `src_file_path`, `dest_file_path`, `httpd_packages`, `supported_distros`)

<br>

## tasks/main.yml (메인 태스크)

메인 태스크는 2개의 작업으로 구성된다:

**1. install service**: Apache 웹 서버 패키지 설치
- 작업 이름에 `{{ service_title }}` 변수를 포함하여 출력
- `ansible.builtin.apt` 모듈로 패키지 설치
- `loop`로 `{{ httpd_packages }}` 변수의 여러 패키지를 순회 설치
- `when` 조건으로 지원되는 배포판(`supported_distros`)에서만 실행

**2. copy conf file**: HTML 파일 복사
- `ansible.builtin.copy` 모듈로 `files/index.html`을 `/var/www/html/index.html`로 복사
- 파일이 변경되면 `notify`로 `restart service` 핸들러 호출

```bash
# (server) #
cd ~/my-ansible/my-role

cat <<'EOT' > tasks/main.yml
---
# tasks file for my-role

- name: install service {{ service_title }}
  ansible.builtin.apt:
    name: "{{ item }}"
    state: latest
  loop: "{{ httpd_packages }}"
  when: ansible_facts.distribution in supported_distros

- name: copy conf file
  ansible.builtin.copy:
    src: "{{ src_file_path }}"
    dest: "{{ dest_file_path }}"
  notify:
    - restart service
EOT
```

<br>

## files/index.html (정적 파일)

```bash
# (server) #
echo "Hello! Ansible" > files/index.html
```

<br>

## handlers/main.yml (핸들러)

```bash
# (server) #
cat <<'EOT' > handlers/main.yml
---
# handlers file for my-role

- name: restart service
  ansible.builtin.service:
    name: "{{ service_name }}"
    state: restarted
EOT
```

<br>

## defaults/main.yml (가변 변수)

외부에서 덮어쓸 수 있는 변수를 정의한다.

```bash
# (server) #
echo 'service_title: "Apache Web Server"' >> defaults/main.yml
```

<br>

## vars/main.yml (불변 변수)

롤 내부에서만 사용되는 변수를 정의한다.

한번 정의되면 외부로부터 변수 값을 수정 할 수 없음. 롤 내의 플레이북에서만 사용되는 변수로 정의하는 것이 좋음

```bash
# (server) #
cat <<'EOT' > vars/main.yml
---
# vars file for my-role

service_name: apache2
src_file_path: ../files/index.html
dest_file_path: /var/www/html
httpd_packages:
  - apache2
  - apache2-doc

supported_distros:
  - Ubuntu
EOT
```

<br>

# 실습 3: 플레이북에 롤 추가

플레이북에 롤을 추가하려면, `ansible_builtin.import_role`과 `ansible.builtin.include_role` 모듈을 사용할 수 있다.

> **참고**: 
> - [import_role 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/import_role_module.html)
> - [include_role 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/include_role_module.html)

## import_role vs include_role

| 모듈 | 방식 | 설명 |
| --- | --- | --- |
| `import_role` | 정적 | 고정된 롤 추가 |
| `include_role` | 동적 | 반복문/조건문에 의해 롤 변경 가능 |


<br>

## Playbook 작성

```bash
# (server) #
cd ~/my-ansible

cat <<'EOT' > role-example.yml
---
- hosts: tnode1
  tasks:
    - name: Print start play
      ansible.builtin.debug:
        msg: "Let's start role play"

    - name: Install Service by role
      ansible.builtin.import_role:
        name: my-role
EOT
```

<br>

## 실행

```bash
# (server) #
ansible-playbook role-example.yml
```


```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Print start play] *****************************************************************
ok: [tnode1] => {
    "msg": "Let's start role play"
}

TASK [my-role : install service Apache Web Server] **************************************
ok: [tnode1] => (item=apache2)
changed: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
changed: [tnode1]

RUNNING HANDLER [my-role : restart service] *********************************************
changed: [tnode1]

PLAY RECAP ******************************************************************************
tnode1                     : ok=5    changed=3    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**결과 분석**:

1. **Print start play**: 플레이북의 일반 태스크 실행
2. **my-role : install service**: 롤의 `tasks/main.yml` 실행
   - `apache2` (이미 설치됨) → `ok`
   - `apache2-doc` (신규 설치) → `changed`
3. **my-role : copy conf file**: 롤의 `tasks/main.yml`에서 `index.html` 복사 → `changed`
4. **my-role : restart service**: 파일 복사로 인한 변경 발생, 롤의 `handlers/main.yml` 실행 → `changed`

**핵심**은, Ansible이 `import_role`을 만나면 `my-role` 디렉터리 구조를 자동으로 인식하고, **"조각들을 합쳐서 실행"**한다는 것이다:
- `my-role/vars/main.yml` → 변수 로드
- `my-role/defaults/main.yml` → 기본 변수 로드
- `my-role/tasks/main.yml` → 태스크 실행
- `my-role/handlers/main.yml` → 변경 시 핸들러 실행

<br>

## 웹 페이지 확인

```bash
# (server) #
curl tnode1
```

**curl 출력**:

```
Hello! Ansible
```

롤의 `files/index.html`에 작성한 내용이 정상적으로 배포되었다.

<br>

## 가변 변수 재정의

`defaults`에 정의된 변수는 롤 호출 시 덮어쓸 수 있다.

```bash
# (server) #
cat <<'EOT' > role-example.yml
---
- hosts: tnode1
  tasks:
    - name: Print start play
      ansible.builtin.debug:
        msg: "Let's start role play"

    - name: Install Service by role
      ansible.builtin.import_role:
        name: my-role
      vars:
        service_title: Httpd # 덮어씀
EOT
```

```bash
# (server) #
ansible-playbook role-example.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Print start play] *****************************************************************
ok: [tnode1] => {
    "msg": "Let's start role play"
}

TASK [my-role : install service Httpd] **************************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
ok: [tnode1]

PLAY RECAP ******************************************************************************
tnode1                     : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**변경된 부분 확인**:

1. **태스크 이름 변경**: `install service Httpd` ← `service_title` 변수가 `Httpd`로 덮어씌워짐
   - 이전: `install service Apache Web Server`
   - 이후: `install service Httpd`
2. **changed=0**: 이미 패키지가 설치되어 있고 파일도 변경 없음
3. **핸들러 미실행**: 변경이 없으므로 핸들러가 실행되지 않음

**웹 페이지 확인**:

```bash
# (server) #
curl tnode1
```

**curl 출력**:

```
Hello! Ansible
```

웹 페이지 내용은 동일하다. `index.html`은 **정적 파일**이므로 변수 변경이 반영되지 않는다. 만약 변수를 웹 페이지에 반영하려면 **Jinja2 템플릿**(`templates/` 디렉터리)을 사용해야 한다.

<br>

## 파일 변경 후 재배포

이번에는 **실제로 파일을 변경**한 후 플레이북을 다시 실행하여, 변경이 감지되고 핸들러가 실행되는지 확인한다.

```bash
# (server) #
# index.html 내용 변경
echo "Hello! Eraser" > my-role/files/index.html

# 플레이북 재실행
ansible-playbook role-example.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Print start play] *****************************************************************
ok: [tnode1] => {
    "msg": "Let's start role play"
}

TASK [my-role : install service Httpd] **************************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
changed: [tnode1]

RUNNING HANDLER [my-role : restart service] *********************************************
changed: [tnode1]

PLAY RECAP ******************************************************************************
tnode1                     : ok=5    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**변경 사항 비교**:

| 항목 | 이전 실행 (파일 미변경) | 이번 실행 (파일 변경) |
|------|------------------------|---------------------|
| **copy conf file** | `ok` (변경 없음) | `changed` (파일 변경 감지) |
| **핸들러 실행** | 실행 안 됨 | `RUNNING HANDLER [restart service]` 실행 |
| **PLAY RECAP** | `changed=0` | `changed=2` (파일 복사 + 서비스 재시작) |

**웹 페이지 확인**:

```bash
# (server) #
curl tnode1
```
```
Hello! Eraser
```

변경된 내용이 정상적으로 배포되었다.
- Ansible은 파일의 **체크섬(checksum)**을 비교하여 변경 여부를 자동으로 감지한다
- 파일이 변경되면 `copy` 태스크가 `changed`를 반환하고, 이에 따라 핸들러가 자동으로 실행된다
- 이것이 바로 **멱등성**과 **핸들러의 조건부 실행**이 결합된 예시다

<br>

# 실습 4: roles 섹션 사용

## 목표

이번 실습에서는 **두 개의 롤을 함께 사용**하는 방법을 익힌다:
- **my-role**: Apache 웹 서버 설치 (실습 3에서 생성)
- **my-role2**: firewalld 설정 (이번 실습에서 생성)

<br>

플레이북에서 `roles` 섹션을 사용하여 두 롤을 순차적으로 실행할 것이다. 이를 위한 전체 작업 흐름은 다음과 같다:
1. 사전 준비
   - tnode1에 firewalld 설치
   - 외부 접속 실패 확인 (방화벽이 80 포트 차단)
2. my-role2 생성
   - firewalld에 http 서비스 허용하는 롤
3. roles 섹션으로 두 롤 실행
   - my-role: Apache 설치
   - my-role2: firewalld 설정
4. 확인
   - 외부 접속 성공 (방화벽이 80 포트 허용)


<br>

## 사전 준비: tnode1에 firewalld 설치

먼저 tnode1에 firewalld를 설치한다. 설치 후에는 기본 보안 정책으로 인해 **외부에서 80 포트 접속이 차단**되는 것을 확인할 수 있다. 이후 Ansible 롤로 이 문제를 해결한다.

사전 설치가 필요한 이유는 다음과 같다:
- `ansible.posix.firewalld` 모듈은 firewalld가 설치되어 있다는 전제하에 **설정만 변경**하는 모듈
- firewalld가 없으면 롤 실행 시 오류 발생
- 실제 운영 환경에서는 기본 이미지에 firewalld가 포함되어 있거나, 별도의 설치 롤을 먼저 실행

firewalld를 설치한 뒤, 기본 보안 정책이 적용되며 기존과 달리 아래와 같은 변화가 나타난다:

| 시점 | 방화벽 상태 | curl tnode1 결과 |
|------|-----------|----------------|
| **실습 1-3** | firewalld 없음 | 성공 |
| **firewalld 설치 후** | 기본 보안 정책 적용 | 실패 (80 포트 차단) |
| **my-role2 적용 후** | http 서비스 허용 | 성공 (문제 해결) |


<br>

### firewalld 설치 및 확인

tnode1에 직접 접속하여 firewalld를 설치한다.

```bash
# (tnode1) #
# tnode1에 SSH 접속
ssh tnode1

# firewalld 설치
apt install firewalld -y

# (출력 생략)
# 8개 패키지 설치됨:
#   firewalld, python3-firewall, python3-nftables, ...
# systemd 서비스로 자동 등록 및 시작
```

<br>

### firewalld 서비스 상태 확인

`Active: active (running)` 상태로 정상 실행 중인지 확인한다.
```bash
# (tnode1) #
systemctl status firewalld
# ● firewalld.service - firewalld - dynamic firewall daemon
#      Loaded: loaded (/usr/lib/systemd/system/firewalld.service; enabled; preset: enabled)
#      Active: active (running) ...
```


<br>

### firewall-cmd로 현재 설정 확인
기본 zone은 `public`이며, `ssh`와 `dhcpv6-client` 서비스만 허용되어 있고, 포트는 비어있다.

```bash
# (tnode1) #
firewall-cmd --list-all
# public (default, active)
#   ...
#   services: dhcpv6-client ssh
#   ports: 
#   ...
```

> *참고*: firewalld 주요 개념
>
> - **zone**: firewalld의 보안 정책 단위. 네트워크 인터페이스나 소스에 적용되는 규칙 집합
>   - `public`: 공개 네트워크용 기본 zone, 최소한의 서비스만 허용
>   - 다른 zone: `trusted`, `home`, `internal`, `work`, `dmz`, `external`, `drop`, `block` 등
> - **services**: 사전 정의된 서비스 목록 (포트 + 프로토콜)
>   - `ssh`: SSH 서비스 (포트 22/tcp), 원격 접속용
>   - `dhcpv6-client`: DHCPv6 클라이언트 (포트 546/udp), 동적 IPv6 주소 할당
>   - `http`: HTTP 서비스 (포트 80/tcp) ← **현재 없음, 추가 필요**
> - **ports**: 개별 포트 지정 (services에 없는 포트를 직접 열 때 사용)




<br>

### 포트 추가 실습

`ports: 8080/tcp`를 추가한다. 

```bash
# (tnode1) #
# 포트 8080/tcp를 public zone에 영구적으로 추가
firewall-cmd --permanent --zone=public --add-port=8080/tcp
# success

# 설정 리로드
firewall-cmd --reload
# success

# 적용 확인
firewall-cmd --list-all
# public (default, active)
#   ...
#   ports: 8080/tcp
#   ...
```

<br>

### 웹 서버 동작 확인

tnode1 **내부**에서는 웹 페이지가 정상 동작한다.

```bash
# (tnode1) #
curl localhost
# Hello! Eraser

# 제어 노드로 돌아가기
exit
```


<br>

### 외부 접속 확인

**제어 노드(server)**에서 tnode1에 접속을 시도하면 실패한다.

```bash
# (server) #
ping -c 1 tnode1
# 64 bytes from tnode1 (10.10.1.11): icmp_seq=1 ttl=64 time=0.444 ms

curl tnode1
# curl: (7) Failed to connect to tnode1 port 80 after 0 ms: Couldn't connect to server
```

앞서 설명한 대로, firewalld가 80 포트를 차단하고 있기 때문이다. 이제 Ansible 롤로 firewalld에 **http 서비스를 허용**하는 설정을 추가한다.

<br>

## 두 번째 롤 생성 (firewalld 설정)

firewalld에 **http, https 서비스를 허용**하는 롤을 생성한다.

```bash
# (server) #
cd ~/my-ansible

# 롤 생성
ansible-galaxy role init my-role2
# - Role my-role2 was created successfully
```

<br>

### tasks 작성

firewalld에 서비스를 추가하고 설정을 리로드한다.

```bash
# (server) #
cat <<'EOT' > my-role2/tasks/main.yml
---
# tasks file for my-role2

- name: Config firewalld
  ansible.posix.firewalld:
    service: "{{ item }}"
    permanent: true
    state: enabled
  loop: "{{ service_port }}"

- name: Reload firewalld
  ansible.builtin.service:
    name: firewalld
    state: reloaded
EOT
```

**주요 포인트**:
- **`ansible.posix.firewalld`**: firewalld 설정 모듈
  - `service`: 허용할 서비스 이름 (`http`, `https` 등)
  - `permanent: true`: 재부팅 후에도 유지되는 영구 설정
  - `state: enabled`: 서비스를 허용 목록에 추가
- **`loop`**: `service_port` 변수의 각 항목에 대해 반복 실행
- **`state: reloaded`**: firewalld 설정을 리로드하여 즉시 적용

> **참고**: 서비스 대신 개별 포트를 지정하려면 `port: "8080/tcp"` 형식 사용 가능

<br>

### vars 작성

허용할 서비스 목록을 변수로 정의한다.

```bash
# (server) #
cat <<'EOT' > my-role2/vars/main.yml
---
# vars file for my-role2

service_port:
  - http
  - https
EOT
```

**설명**:
- **`http`**: 80/tcp 포트 (HTTP)
- **`https`**: 443/tcp 포트 (HTTPS)
- 서비스 이름을 사용하면 해당 포트와 프로토콜이 자동으로 매핑됨

> **참고**: [firewalld 모듈](https://docs.ansible.com/ansible/latest/collections/ansible/posix/firewalld_module.html)

<br>

## roles 섹션으로 여러 롤 사용

이제 **두 개의 롤**을 `roles` 섹션에 추가하여 순차적으로 실행한다.
- `roles` 섹션에 여러 롤을 나열하면 **위에서 아래 순서**로 실행
- 각 롤은 독립적인 기능을 수행하지만, **하나의 플레이로 통합 관리**
- `roles` 실행 후 `tasks`가 실행됨 (순서 보장)


```bash
# (server) #
cat <<'EOT' > role-example2.yml
---
- hosts: tnode1
  roles:
    - my-role      # 1. Apache 웹 서버 설치
    - my-role2     # 2. firewalld 설정 (http, https 허용)
  tasks:
    - name: Print finish role play
      ansible.builtin.debug:
        msg: "Finish role play"
EOT
```

**실행 순서**:
1. **Gathering Facts**: 호스트 정보 수집
2. **my-role**: Apache 웹 서버 설치 및 index.html 배포
3. **my-role2**: firewalld에 http, https 서비스 허용
4. **tasks**: 일반 태스크 실행 ("Finish role play" 메시지 출력)
5. **handlers**: 변경 발생 시 핸들러 실행

<br>

## 실행

롤 실행을 통해 아래 사항을 확인한다:

- 사전 준비에서는 방화벽 차단으로 접속 실패
- 롤 적용 후에는 http 서비스 허용으로 접속 성공
- **두 개의 롤**(my-role + my-role2)을 **하나의 플레이북**으로 통합 관리

### 1. Dry-Run으로 시뮬레이션

먼저 `--check` 옵션으로 실제 변경 없이 시뮬레이션한다.

```bash
# (server) #
ansible-playbook --check role-example2.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [my-role : install service Apache WEb Server] **************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
ok: [tnode1]

TASK [my-role2 : Config firewalld] ******************************************************
changed: [tnode1] => (item=http)
changed: [tnode1] => (item=https)

TASK [my-role2 : Reload firewalld] ******************************************************
changed: [tnode1]

TASK [Print finish role play] ***********************************************************
ok: [tnode1] => {
    "msg": "Finish role play"
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=6    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**분석**:
- **`--check` 모드**: 실제로 변경하지 않고 시뮬레이션만 수행
- **my-role**: apache2 이미 설치됨 (`ok`), 파일도 변경 없음 (`ok`)
- **my-role2**: http, https가 없다고 감지 → `changed`로 예측
- **PLAY RECAP**: `changed=2` (firewalld 2개 + reload 1개)

> **참고**: `--check`는 kubectl의 `--dry-run=server`와 유사. 호스트에 연결하여 현재 상태를 확인하고 변경 사항을 예측하지만, 실제로는 적용하지 않음.

<br>

### 2. 실제 실행

이제 실제로 롤을 적용한다.

```bash
# (server) #
ansible-playbook role-example2.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [my-role : install service Apache WEb Server] **************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
ok: [tnode1]

TASK [my-role2 : Config firewalld] ******************************************************
changed: [tnode1] => (item=http)
changed: [tnode1] => (item=https)

TASK [my-role2 : Reload firewalld] ******************************************************
changed: [tnode1]

TASK [Print finish role play] ***********************************************************
ok: [tnode1] => {
    "msg": "Finish role play"
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=6    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**분석**:
- **실행 순서**: my-role (Apache 설치) → my-role2 (firewalld 설정) → tasks (메시지 출력)
- **my-role**: 이미 설치되어 있어 `ok` 상태
- **my-role2**: firewalld에 http, https 서비스 추가 → `changed`
- `--check` 결과와 동일하게 `changed=2` 발생

<br>

### 3. 접속 확인

외부에서 80 포트 접속이 가능한지 확인한다.

```bash
# (server) #
curl tnode1
# Hello! Eraser
```

**성공**한다. 이제 firewalld가 80 포트(http)를 허용하므로 외부에서 접속 가능하다.

<br>

### 4. firewalld 설정 확인

```bash
# (server) #
ansible -m shell -a "firewall-cmd --list-all" tnode1
```

**출력 결과**:

```bash
tnode1 | CHANGED | rc=0 >>
public (default, active)
  target: default
  ...
  services: dhcpv6-client http https ssh
  ports: 8080/tcp
  ...
```
- **services**: `http`, `https`가 추가됨
- **ports**: 8080/tcp는 이전 실습에서 수동으로 추가한 것
- 롤이 정상적으로 firewalld 설정을 변경했음을 확인


<br>

## roles 섹션에서 변수 전달

```bash
# (server) #
cat <<'EOT' > role-example3.yml
---
- hosts: tnode1
  roles:
    - role: my-role
      service_title: "Httpd Web"
    - role: my-role2
  tasks:
    - name: Print finish role play
      ansible.builtin.debug:
        msg: "Finish role play"
EOT
```

```bash
# (server) #
ansible-playbook role-example3.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [my-role : install service Httpd Web] **********************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
ok: [tnode1]

TASK [my-role2 : Config firewalld] ******************************************************
ok: [tnode1] => (item=http)
ok: [tnode1] => (item=https)

TASK [my-role2 : Reload firewalld] ******************************************************
changed: [tnode1]

TASK [Print finish role play] ***********************************************************
ok: [tnode1] => {
    "msg": "Finish role play"
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=6    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**결과 분석**:

| 태스크 | 이전 실행 (role-example2.yml) | 이번 실행 (role-example3.yml) |
|--------|------------------------------|------------------------------|
| **my-role: install** | `ok` (이미 설치됨) | `ok` (이미 설치됨) |
| **my-role: copy** | `ok` (파일 변경 없음) | `ok` (파일 변경 없음) |
| **my-role2: Config firewalld** | `changed` (http, https 추가) | `ok` (이미 설정됨) |
| **my-role2: Reload** | `changed` | `changed` (reload는 항상 실행) |
| **PLAY RECAP** | `changed=2` | `changed=1` |

**핵심**:
- **멱등성**: 이미 설정된 상태는 `ok`로 표시되고 변경하지 않음
- **my-role2의 Config firewalld**: 이전에는 `changed`, 지금은 `ok` (http, https가 이미 있음)
- **Reload firewalld**: `state: reloaded`는 항상 `changed` (reload 자체가 변경 작업)
- 같은 플레이북을 여러 번 실행해도 안전하며, 필요한 경우에만 변경됨

<br>

# 실습 5: 특수 작업 섹션 (pre_tasks, post_tasks)

## 개념

지금까지는 플레이북에서 `roles`와 `tasks`를 사용했다. 하지만 때로는 **롤 실행 전에 사전 작업**을 하거나, **모든 작업 후에 정리 작업**을 해야 할 필요가 있다. 이럴 때 `pre_tasks`와 `post_tasks`를 사용한다. 

특수 작업을 사용할 경우, 실행 순서는 다음과 같다:
```
pre_tasks → roles → tasks → handlers → post_tasks
```

| 섹션 | 실행 시점 | 용도 예시 |
| --- | --- | --- |
| `pre_tasks` | roles 실행 전 | 사전 점검, 로그 디렉터리 생성, 필수 패키지 설치 |
| `roles` | - | 주요 기능 (웹 서버 설치, DB 설정 등) |
| `tasks` | roles 실행 후 | 추가 설정, 동작 확인 |
| `handlers` | tasks 실행 후 (변경 발생 시) | 서비스 재시작 등 |
| `post_tasks` | 모든 작업 완료 후 | 배포 완료 메시지, 정리 작업, 알림 전송 |



실행 순서를 고려하여, 아래와 같은 경우에 사용할 수 있다:
- **pre_tasks**: "롤 실행 전에 디스크 공간이 충분한지 확인"
- **post_tasks**: "배포 완료 후 Slack에 알림 전송"


<br>

## Playbook 작성

```bash
# (server) #
cat <<'EOT' > special_role.yml
---
- hosts: tnode1
  pre_tasks:
    - name: Print Start role
      ansible.builtin.debug:
        msg: "Let's start role play"

  roles:
    - role: my-role
    - role: my-role2

  tasks:
    - name: Curl test
      ansible.builtin.uri:
        url: http://tnode1
        return_content: true
      register: curl_result
      notify: Print result
      changed_when: true

  post_tasks:
    - name: Print Finish role
      ansible.builtin.debug:
        msg: "Finish role play"

  handlers:
    - name: Print result
      ansible.builtin.debug:
        msg: "{{ curl_result.content }}"
EOT
```

**주요 구성**:
- **`pre_tasks`**: 시작 메시지 출력
- **`roles`**: my-role (Apache), my-role2 (firewalld) 실행
- **`tasks`**: uri 모듈로 HTTP 요청 후 핸들러 notify
  - `return_content: true`: HTTP 응답 본문을 `curl_result.content`에 저장
  - `register: curl_result`: 응답 결과를 변수에 저장
  - `changed_when: true`: 항상 changed로 표시하여 핸들러 실행 보장
- **`handlers`**: curl 결과(웹 페이지 내용) 출력
- **`post_tasks`**: 완료 메시지 출력


<br>

## 실행

```bash
# (server) #
ansible-playbook special_role.yml
```

**실행 결과**:

```bash
PLAY [tnode1] ***************************************************************************

TASK [Gathering Facts] ******************************************************************
ok: [tnode1]

TASK [Print Start role] *****************************************************************
ok: [tnode1] => {
    "msg": "Let's start role play"
}

TASK [my-role : install service Apache WEb Server] **************************************
ok: [tnode1] => (item=apache2)
ok: [tnode1] => (item=apache2-doc)

TASK [my-role : copy conf file] *********************************************************
ok: [tnode1]

TASK [my-role2 : Config firewalld] ******************************************************
ok: [tnode1] => (item=http)
ok: [tnode1] => (item=https)

TASK [my-role2 : Reload firewalld] ******************************************************
changed: [tnode1]

TASK [Curl test] ************************************************************************
changed: [tnode1]

RUNNING HANDLER [Print result] **********************************************************
ok: [tnode1] => {
    "msg": "Hello! Eraser\n"
}

TASK [Print Finish role] ****************************************************************
ok: [tnode1] => {
    "msg": "Finish role play"
}

PLAY RECAP ******************************************************************************
tnode1                     : ok=9    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

pre_tasks 섹션 태스크 → my-role → my-role2 → tasks(curl test) ⇒ notify 구문에 의한 handlers 태스크 실행 → 마지막 post_tasks 가 실행된다.

| 순서 | 섹션 | 태스크 | 설명 |
|------|------|--------|------|
| 1 | - | Gathering Facts | 호스트 정보 수집 |
| 2 | `pre_tasks` | Print Start role | "Let's start role play" 출력 |
| 3 | `roles` | my-role: install service | apache2 설치 (이미 있음, `ok`) |
| 4 | `roles` | my-role: copy conf file | index.html 복사 (변경 없음, `ok`) |
| 5 | `roles` | my-role2: Config firewalld | http, https 확인 (이미 설정됨, `ok`) |
| 6 | `roles` | my-role2: Reload firewalld | firewalld 리로드 (`changed`) |
| 7 | `tasks` | Curl test | tnode1에 HTTP 요청, 핸들러 notify (`changed`) |
| 8 | `handlers` | Print result | curl 결과 출력 ("Hello! Eraser") |
| 9 | `post_tasks` | Print Finish role | "Finish role play" 출력 |

**핵심**:
- **pre_tasks → roles → tasks → handlers → post_tasks** 순서가 정확히 지켜짐
- `uri` 모듈에 `changed_when: true` 설정으로 핸들러 강제 실행
- `tasks`와 `post_tasks` 사이에 `handlers` 실행 (notify로 트리거됨)
- 전체 9개 태스크 실행, 2개 변경 (`changed=2`)

<br>

> **참고**: 이 실습에서 사용한 `changed_when: true`는 태스크를 항상 `changed` 상태로 표시하여 핸들러 실행을 보장한다. `changed_when`과 `failed_when`에 대한 자세한 내용은 [Ansible-10: 핸들러와 오류 처리]({% post_url 2026-01-12-Kubernetes-Ansible-10 %}) 참조.

<br>

# 결과

이 글을 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **롤 구조 이해**: tasks, handlers, defaults, vars, files 등
2. **롤 생성**: `ansible-galaxy role init`
3. **롤 추가**: `import_role`, `include_role`, `roles` 섹션
4. **변수 관리**: `defaults` (가변), `vars` (불변)
5. **특수 섹션**: `pre_tasks`, `post_tasks`

<br>

롤을 활용하면 Playbook을 모듈화하여 재사용성을 높일 수 있다. Kubespray도 수십 개의 롤로 구성되어 있으며, 각 롤이 Kubernetes 클러스터 구성의 특정 기능을 담당한다.

<br>

다음 글에서는 태그(Tag)를 활용하여 Playbook의 특정 작업만 선택적으로 실행하는 방법을 알아본다.
