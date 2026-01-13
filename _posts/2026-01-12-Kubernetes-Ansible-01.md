---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 1. 개념"
excerpt: "Ansible의 구성 요소, 동작 원리, 멱등성 등 핵심 개념을 정리한다."
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

Kubespray는 Ansible 기반의 Kubernetes 배포 도구다. Kubespray를 이해하려면 먼저 Ansible의 핵심 개념을 알아야 한다.

<br>

# 개념


Ansible은 여러 서버와 시스템의 IT 환경 구성 및 배포 작업을 자동화하는 오픈소스 IT 자동화 도구이다. 

- IT 업무를 코드 기반으로 작성하여 여러 환경에 동일하게 적용될 수 있도록 돕는 역할을 한다.
- Agentless 방식으로, Python과 SSH만 있으면 사용할 수 있다.

<br>

# 구성 요소

![ansible-architecture]({{site.url}}/assets/images/ansible-architecture.png)

Ansible을 사용할 때 알아야 하는 핵심 개념들이다.

- **Control Node, Managed Node**: Ansible 실행 주체와 작업 대상
- **Inventory**: 관리 대상 호스트 목록
- **Playbook, Play, Task**: 자동화 시나리오 정의
- **Module**: 실제 작업을 수행하는 코드 단위
- **Handler**: 변경 시 트리거되는 특수 Task
- **Role**: 재사용 가능한 Playbook 패키지

## Control Node와 Managed Node

Ansible의 가장 기본적인 구성은 **Control Node**와 **Managed Node**다.

- **Control Node**: Ansible이 설치되어 실행되는 서버
  - Playbook, Inventory, 모듈을 보관하고 실행함
  - 리눅스, macOS, BSD 계열 유닉스, WSL을 지원하는 Windows 등 Python이 설치된 환경이면 어디서든 실행할 수 있음
- **Managed Node**: Playbook이 실행되어 실제 작업(애플리케이션 설치, 클라우드 리소스 생성 등)이 수행되는 대상 서버들
  - Python이 설치되어 있고 SSH 연결이 가능해야 함

Ansible은 **Control Node에만** 설치된다. Managed Node에는 별도의 에이전트가 필요 없다(Agentless). Control Node에서 SSH를 통해 Managed Node에 접속하여 작업을 수행한다.

Ansible 버전에 따라 요구되는 Python 버전이 다르다.

| Ansible 버전 | Control Node | Managed Node |
|--------------|--------------|--------------|
| ansible 2.9 (레거시) | 2.7, 3.5+ | 2.6+ |
| ansible-core 2.14 | 3.9+ | 2.7, 3.5+ |
| ansible-core 2.17+ | 3.10+ | 3.7+ |

## Inventory

Managed Node 목록을 정의한 파일이다. 호스트를 그룹으로 묶거나, 호스트별 변수를 지정할 수 있다.

- 호스트: 개별 서버 (`web1.example.com`)
- 그룹: 서버들의 논리적 묶음 (`[webservers]`)
- 변수: 호스트나 그룹에 적용되는 설정


```ini
# /etc/ansible/hosts

[webservers]
web1.example.com ansible_host=192.168.1.10
web2.example.com ansible_host=192.168.1.11

[dbservers]
db1.example.com ansible_host=192.168.1.20

[webservers:vars]
ansible_user=deploy
ansible_python_interpreter=/usr/bin/python3
```


## Playbook, Play, Task

작업을 정의하는 계층 구조이다.

```bash
Playbook (playbook.yml)
└─ Play 1 (Configure webservers)
   ├─ Task 1 (Install nginx)
   └─ Task 2 (Start nginx)
```
- **Playbook**: 자동화 시나리오를 정의한 YAML 파일(전체 문서)
- **Play**: Playbook 내 하나의 실행 단위(어떤 호스트에 어떤 작업을 할지 정의)
- **Task**: Play 내 개별 작업(하나의 모듈을 호출)

```yaml
---
# Playbook (파일 전체)
- name: Configure webservers    # Play 시작
  hosts: webservers
  tasks:
    - name: Install nginx       # Task 1
      apt:
        name: nginx
        state: present
    - name: Start nginx         # Task 2
      service:
        name: nginx
        state: started
```

## Module

Task가 실제로 호출하는 코드 단위로, **이미 Python으로 작성된** 실행 코드다. Ansible은 수천 개의 빌트인 모듈을 제공한다.

- `apt`, `yum`: 패키지 관리
- `copy`, `template`: 파일 관리
- `service`: 서비스 관리
- `shell`, `command`: 명령 실행

**Playbook과 Module의 관계**

혼동하기 쉬운 부분인데, Playbook(YAML)이 Python으로 변환되는 것이 아니다.

- **Playbook**: "어떤 Module을, 어떤 파라미터로 호출할지" 정의하는 YAML 파일
- **Module**: 이미 Python으로 작성된 실행 코드

```yaml
- name: Install nginx
  apt:                    # <- apt 모듈 호출
    name: nginx
    state: present
```

위 Task를 실행하면:

1. **Playbook 파싱**: "apt 모듈을 `name=nginx, state=present` 파라미터로 호출해라"
2. **모듈 찾기**: `/usr/lib/python3/dist-packages/ansible/modules/apt.py`
3. **파라미터 변환**: JSON으로 직렬화
   ```json
   { "name": "nginx", "state": "present" }
   ```
4. **모듈 실행**: `python3 apt.py` + JSON 파라미터 전달
5. **모듈 내부**: `module.params['name']`으로 파라미터 접근

Playbook 자체가 Python으로 변환되는 것이 아니라, **Playbook이 지정한 Module(Python)이 실행**된다.

## Handler

Handler는 notify로 트리거되는 특수한 Task다. 변경 시 트리거된다. 설정 파일 변경 후 서비스 재시작 등과 같은 패턴에 사용한다.

```yaml
tasks:
  - name: Copy nginx config
    template:
      src: nginx.conf.j2
      dest: /etc/nginx/nginx.conf
    notify: Restart nginx       # 파일이 변경되면 handler 호출

handlers:
  - name: Restart nginx
    service:
      name: nginx
      state: restarted
```

동작 방식은 아래와 같다:
1. Task 실행 → 파일 변경됨 (changed=true)
2. notify: Restart nginx 트리거
3. 모든 Task 완료 후 Handler 실행
4. nginx 재시작
파일이 변경되지 않았다면 (changed=false) Handler는 실행되지 않는다.

## Role

재사용 가능한 Playbook 패키지다. Task, Handler, 변수, 템플릿 등을 디렉토리 구조로 묶어서 관리한다.

```bash
# 디렉토리 구조
roles/
└── nginx/
    ├── tasks/
    │   └── main.yml        # 실행할 Task들
    ├── handlers/
    │   └── main.yml        # Handler 정의
    ├── templates/
    │   └── nginx.conf.j2   # Jinja2 템플릿
    ├── files/
    │   └── index.html      # 정적 파일
    ├── vars/
    │   └── main.yml        # 변수 정의
    └── defaults/
        └── main.yml        # 기본 변수
```

Playbook에서 아래와 같이 사용한다.
```yaml
---
- name: Setup web servers
  hosts: webservers
  roles:
    - common
    - nginx
    - monitoring
```

Role을 사용하면 코드 재사용성이 높아지고, 구조화된 프로젝트 관리가 가능하다.

<br>

# 동작 원리

Ansible은 Playbook을 읽고, Inventory의 각 호스트에 SSH로 접속하여 모듈을 전송/실행한 뒤 결과를 수집한다.

![ansible-flow.png]({{site.url}}/assets/images/ansible-flow.png)


## 모듈 반환 상태

Task 실행 후 각 모듈은 상태를 반환한다. Ansible은 이를 기반으로 실행 결과를 리포팅한다.

| 상태 | 의미 |
|------|------|
| **changed** | 시스템 상태가 변경됨 (패키지 설치, 파일 생성 등) |
| **ok** | 성공, 변경 없음 (이미 원하는 상태 - 멱등성) |
| **failed** | 실행 실패 |
| **skipped** | 조건문(when)에 의해 건너뜀 |
| **unreachable** | 호스트 연결 불가 (SSH 실패 등) |

실행 결과 예시:

```bash
PLAY RECAP ********************************
web1  : ok=3  changed=2  unreachable=0  failed=0
web2  : ok=3  changed=0  unreachable=0  failed=0
```

<br>


# 특징

Ansible은 아래와 같은 특징을 지닌다. 
- **에이전트리스(Agentless)**: SSH 기반, 별도 에이전트 설치 불필요
- **멱등성 지향**: 아래에서 상세히 다룸
- **YAML 기반**: 쉬운 작성과 가독성

## 멱등성: 보장이 아니라 지향

Ansible의 특징으로 **멱등성(Idempotency)**이 자주 언급된다. 그런데 조금만 파고들면 의문이 생긴다. 멱등성을 보장하지 않는 모듈들도 있다. `shell`, `command`, `raw` 같은 모듈이 대표적이다. 그런데 과연 "Ansible = 멱등성"이라고 말해도 되는 걸까?

결론부터 말하면, **"Ansible이 멱등성을 보장한다"가 아니라 "Ansible은 멱등성을 지향하고 지원하는 도구"**라고 하는 게 정확하다.

### 멱등성이란

멱등성은 **동일한 연산을 여러 번 적용하더라도 결과가 달라지지 않는 성질**이다. 이 개념은 함수형 프로그래밍, 분산 시스템, 인프라 관리 등 여러 분야에서 활용된다.

인프라 관리에서 멱등성이 중요한 이유는 명확하다:
- CI/CD 파이프라인에서 **안전하게 재실행** 가능
- 실패 시 **다시 돌려도 문제없음**
- 정기 실행(cron)으로 **drift 방지** - 서버 상태가 변경되어도 원하는 상태로 되돌림

### 멱등성을 보장하지 않는 모듈

`shell`, `command`, `raw`, `script` 같은 모듈은 그 자체로는 멱등성을 보장하지 않는다.

```yaml
- name: Run script
  shell: /tmp/setup.sh
# 매번 실행됨, 항상 changed
```


### 멱등성을 보장하는 모듈

반면, `apt`, `copy`, `file` 같은 대부분의 핵심 모듈은 내부적으로 현재 상태를 확인하고 필요한 경우에만 변경을 수행한다.

```yaml
- name: Install nginx
  apt:
    name: nginx
    state: present
# 이미 설치되어 있으면 ok, 없으면 changed
```


### 그럼에도 불구하고 멱등성이 특징이라고 볼 수 있는 이유

그럼 왜 "멱등성"이 특징인가?

**1. 설계 철학: Desired State**

Ansible은 "원하는 상태(desired state)"를 선언하는 도구다. "어떻게(how)"가 아니라 "무엇을(what)" 선언하고, 현재 상태와 비교하여 필요한 변경만 수행한다. 이 철학 자체가 멱등성을 지향한다.

**2. 멱등성을 위한 기능 제공**

멱등하지 않은 모듈도 멱등하게 사용할 수 있는 도구를 제공한다.

```yaml
# creates: 파일이 존재하면 실행 안 함
- name: Run install script
  shell: /tmp/install.sh
  args:
    creates: /opt/app/installed.txt

# when 조건으로 상태 확인 후 실행
- name: Check if configured
  stat:
    path: /etc/app/config
  register: config_stat

- name: Configure
  shell: /tmp/configure.sh
  when: not config_stat.stat.exists
```

**3. changed_when으로 명시적 제어**

```yaml
- name: Check service status
  shell: systemctl is-active myapp
  register: result
  changed_when: false  # 항상 ok로 표시
  failed_when: result.rc not in [0, 3]
```

### 결론

사실 대부분의 맥락에서는 Ansible이 멱등성을 보장한다고 해도 크게 무리는 없어 보인다. 다만, 조금 더 엄밀하게 표현하고 싶다면, "Ansible은 멱등성을 보장한다"라는 표현 보다는, 아래와 같이 표현하는 것이 좋지 않을까:
- "Ansible은 멱등성을 **지향**하는 도구다"
- "Ansible의 **대부분의 핵심 모듈**은 멱등하다"
- "Ansible은 멱등성을 **구현할 수 있는 기능**을 제공한다"
- "Ansible은 멱등한 인프라 관리를 **쉽게** 만든다"

한편, Ansible이 완벽한 멱등성을 보장하는 것이 아니기 때문에, 플레이북 작성자가 멱등성을 **의식하고 설계해야** 한다는 사실을 잊지 말아야 할 것이다.

<br>

# IaC

Ansible은 IaC(Infrastructure as Code) 도구로 분류된다. IaC란 인프라를 코드로 관리하는 것을 의미한다.

- Infrastructure as Code = "인프라를 코드로 관리한다"
- 코드 = 텍스트 파일로 된 선언/명령
- 버전 관리 가능
- 자동화 가능

[Red Hat 공식 문서](https://www.redhat.com/en/topics/automation/what-is-infrastructure-as-code-iac)에서는 IaC를 아래와 같이 정의한다.

> Infrastructure as Code (IaC) is the managing and provisioning of infrastructure through code instead of manual processes.

그리고 Ansible을 IaC를 위한 자동화 도구로 소개한다.

> Codifying your infrastructure gives you a template to follow for provisioning. Though this can still be accomplished manually, an automation tool, such as Red Hat Ansible Automation Platform, can do it for you. 

# 여담

Ansible을 공부하면서 다른 기술들과의 유사성이 눈에 들어왔다.

## HTTP Status Code와의 유사성

Ansible의 반환 상태(changed, ok, failed)는 HTTP Status Code와 비슷한 구조다.

| HTTP Status | Ansible 상태 | 의미 |
|-------------|-------------|------|
| 200 OK | ok | 성공, 변경 없음 |
| 201 Created | changed | 성공, 상태 변경됨 |
| 4xx, 5xx | failed | 실패 |
| 304 Not Modified | skipped | 실행 안 함 |

둘 다 **표준 규약을 정의**하고, **구현체가 적절한 코드를 반환**하는 구조다. HTTP가 "웹 통신의 표준 응답 규약"이라면, Ansible의 changed/ok/failed는 "인프라 자동화의 표준 응답 규약"이라 할 수 있다.

멱등성 관점에서도 유사하다. REST API를 HTTP로 구현할 때 PUT/DELETE는 멱등해야 하지만 실제 구현은 개발자에 따라 다르듯, Ansible도 멱등성을 지향하지만 모든 모듈이 멱등한 건 아니다.

## Kubernetes Desired State와의 유사성

Ansible과 Kubernetes는 **Desired State(원하는 상태)** 철학을 공유한다.

| 비교 | Kubernetes | Ansible |
|------|------------|---------|
| 상태 선언 | `replicas: 3` | `state: present` |
| 조정 방식 | 지속적 Reconciliation | 실행 시점에만 |
| 감시 | Controller가 계속 감시 | 실행 전까지 모름 |
| 방식 | Pull (지속적) | Push (필요할 때) |

핵심 차이는 **지속성**이다. Kubernetes는 Controller가 계속 감시하며 Desired State를 유지하지만, Ansible은 Playbook 실행 시점에만 조정한다.

실무에서는 **Ansible로 Kubernetes 클러스터를 구축**하고, **Kubernetes로 애플리케이션을 운영**하는 패턴이 일반적이다. Kubespray가 바로 이 패턴의 대표적인 예다.

<br>

