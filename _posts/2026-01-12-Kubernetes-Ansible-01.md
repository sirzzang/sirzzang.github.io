---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 1. 개념"
excerpt: "Ansible의 구성 요소, 동작 원리, 멱등성 등 핵심 개념을 정리해보자."
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
- **Plugin**: Ansible 핵심 기능을 확장하는 모듈
- **Role**: 재사용 가능한 Playbook 패키지

## Control Node와 Managed Node

Ansible의 가장 기본적인 구성은 **Control Node**와 **Managed Node**다.

- **Control Node**: Ansible이 설치되어 실행되는 서버
  - **Ansible Core**(또는 Ansible 패키지)가 설치되어 Playbook 실행, 모듈 관리, SSH 통신 등을 담당함
  - Playbook, Inventory, 모듈을 보관하고 실행함
  - Ansible은 Python 모듈을 이용하므로 **Python이 함께 설치**되어 있어야 함
  - 리눅스, macOS, BSD 계열 유닉스, WSL을 지원하는 Windows 등에서 실행 가능
- **Managed Node**: Playbook이 실행되어 실제 작업(애플리케이션 설치, 클라우드 리소스 생성 등)이 수행되는 대상 서버들
  - **리눅스 또는 Windows**가 설치된 노드일 수 있음
  - **제어 노드와 SSH 통신이 가능**해야 하며(Windows는 WinRM 사용), **Python이 설치**되어 있어야 함

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
- 변수: 호스트나 그룹에 적용되는 상세 설정 값(접속 정보, 환경 변수 등)


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

Playbook에는 다양한 실행 옵션을 지정할 수 있다. 예를 들어 `serial`을 사용하면 한 번에 처리할 호스트 수를 제한할 수 있다.

```yaml
---
- hosts: webservers
  serial: 5  # 한 번에 5대의 머신만 업데이트
  roles:
    - common
    - webapp

- hosts: content_servers
  roles:
    - common
    - content
```

이렇게 하면 100대의 웹서버가 있어도 5대씩 순차적으로 업데이트되므로, 전체 서비스가 중단되는 것을 방지할 수 있다.

## Module

Task가 실제로 호출하는 코드 단위로, **이미 Python으로 작성된** 실행 스크립트다. Ansible은 수천 개의 빌트인 모듈을 제공한다.

- `apt`, `yum`: 패키지 관리
- `copy`, `template`: 파일 관리
- `service`: 서비스 관리
- `shell`, `command`: 명령 실행

모듈의 동작 방식은 다음과 같다:
- Control Node에서 SSH를 통해 Managed Node로 모듈을 **푸시(전송)**함
- 모듈은 **원하는 시스템 상태를 설명하는 매개변수**를 받아 실행됨
- 모듈 실행이 **완료되면 자동으로 제거**됨 (Managed Node에 흔적을 남기지 않음)

<br>

Playbook에 작성한 Task가 실제 서버에서 어떻게 실행되는지 살펴 보자.


```yaml
- name: Install nginx
  apt:                    # <- 'apt'라는 이름의 Python 모듈을 호출해라
    name: nginx
    state: present        # 모듈에 전달할 파라미터 1
```



1. **Playbook 파싱**: "apt 모듈을 `name=nginx, state=present` 파라미터로 호출해라"라고 해석
2. **모듈 찾기**: Control 노드 내에 저장된 `/usr/lib/python3/dist-packages/ansible/modules/apt.py` 파일을 찾음
3. **파라미터 변환**: 파라미터로 전달되어야 하는 설정값들을 JSON으로 직렬화함
   ```json
   { "name": "nginx", "state": "present" }
   ```
4. **모듈 실행**: `apt` 모듈과 직렬화된 JSON 파라미터를 Managed Node로 보냄
5. **모듈 내부**: Managed Node에서 `python3 apt.py {JSON 파라미터}` 형태로 명령이 실행됨


<br>
헷갈리기 쉬운 부분인데, Playbook(YAML)이 Python으로 변환되는 것이 아니다.

| 구분 | Playbook (YAML) | Module (Python) |
| :---: | :--- | :--- |
| **역할** | **"무엇을"** 할지 정의 (시나리오) | **"어떻게"** 할지 구현 (실행 코드) |
| **비유** | 식당의 **주문서** | 주문을 처리하는 **요리사** |
| **관계** | 어떤 모듈을 쓸지 지정함 | 이미 작성된 코드가 호출됨 |


Playbook 자체가 Python으로 변환되는 것이 아니라, **Playbook이 지정한 Module(Python)이 실행**된다. Playbook은 일종의 **호출 명세서**이다.

<br>

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

## Plugin

Plugin은 Ansible의 핵심 기능을 강화하는 확장 모듈이다. Module과의 가장 큰 차이는 **실행 위치**다.

| 구분 | Module | Plugin |
|------|--------|--------|
| **실행 위치** | Managed Node (대상 시스템) | Control Node |
| **실행 방식** | 별도의 프로세스로 실행 | Ansible 엔진 내부에서 실행 |
| **역할** | 대상 시스템의 상태 변경 | Ansible의 핵심 기능 확장 |

Plugin의 주요 기능:
- **데이터 변환**: 변수 처리, 템플릿 렌더링 (Jinja2 필터)
- **로그 출력**: 실행 결과를 다양한 형식으로 출력
- **인벤토리 연결**: 동적 인벤토리 생성 (AWS, Azure 등 클라우드 환경에서 자동으로 호스트 목록 가져오기)
- **Connection**: SSH 외 다른 프로토콜 지원 (WinRM, Docker 등)

예를 들어, AWS 동적 인벤토리 플러그인을 사용하면 EC2 인스턴스 목록을 자동으로 가져올 수 있다.

```yaml
# aws_ec2.yml (동적 인벤토리 플러그인 설정)
plugin: amazon.aws.aws_ec2
regions:
  - ap-northeast-2
filters:
  tag:Environment: production
```

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
| **ok** | Task 실행 성공 (상태 변경 없음 - 멱등성) |
| **failed** | 실행 실패 |
| **skipped** | 조건문(when)에 의해 건너뜀 |
| **unreachable** | 호스트 연결 불가 (SSH 실패 등) |

실행 결과 예시:

```bash
PLAY RECAP *************************************************************************
localhost                  : ok=3    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

<br>

### PLAY RECAP 해석

- **ok**: 성공적으로 완료된 **전체 task 수** (changed 포함)
- **changed**: 그 중 **시스템 상태를 변경한 task 수**
- **unreachable**: 호스트 연결 불가 (SSH 실패 등)
- **failed**: 실행 실패한 task 수
- **skipped**: 조건문(when)에 의해 건너뛴 task 수
- **rescued**: 에러 핸들링으로 복구된 task 수
- **ignored**: 에러가 발생했지만 무시된 task 수
- 관계: `ok ≥ changed` (항상)

**예시 해석**:
- `localhost`: 3개 task 성공 (`ok=3`), 그 중 1개가 상태 변경 (`changed=1`), 나머지 2개는 이미 원하는 상태

**다중 호스트 예시**:

```bash
PLAY RECAP *************************************************************************
tnode1                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode2                     : ok=2    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
tnode3                     : ok=1    changed=0    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0
```

- `tnode1, tnode2`: 2개 task 모두 성공 (`ok=2`), 상태 변경 없음 (`changed=0`)
- `tnode3`: 1개 task만 성공 (`ok=1`), 1개는 조건 불만족으로 건너뜀 (`skipped=1`) 

<br>


# 특징

Ansible은 아래와 같은 특징을 지닌다. 
- **에이전트리스(Agentless)**: SSH 기반으로 별도 에이전트 설치 불필요
- **YAML 기반**: 쉬운 작성과 가독성
- **멱등성 지향**

다른 특징은 [이전 글]({% post_url 2026-01-12-Kubernetes-Ansible-00 %})에서 자세히 살펴 보았으므로, 멱등성에 대해서 살펴 보자.

<br>

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


### Ansible과 멱등성

이렇게 어떤 모듈은 멱등하지 않음에도 불구하고 왜 Ansible을 이야기할 때 `멱등성`이 가장 먼저 언급될까? 그 이유는 Ansible이 단순히 명령을 전달하는 도구를 넘어, **시스템을 멱등하게 유지하기 위한 철학과 기능**을 갖추고 있기 때문이다.

<br>

**1. 설계 철학: Desired State**

Ansible은 "원하는 상태(desired state)"를 선언하는 도구다. "어떻게(how) 시스템을 바꿀 것인가"가 아니라 "시스템이 어떤 상태(what)여야 하는지" 선언하고, 현재 상태와 비교하여 필요한 변경만 수행한다. 
- 사용자는 원하는 최종 상태를 정의한다
- Ansible이 현재 상태와 비교해 차이가 있을 때만 작업을 수행한다

<br>

**2. 멱등성 확보를 위한 안전장치 제공**

멱등성이 보장되지 않는 하위 수준의 명령(`shell`, `command` 등)을 쓸 때도, 이를 멱등하게 만들 수 있는 옵션들을 제공

```yaml
# creates: 파일이 존재하면 실행 안 함(중복 설치 방지)
- name: Run install script
  shell: /tmp/install.sh
  args:
    creates: /opt/app/installed.txt

# when 조건으로 상태 확인 후 실행(상태 체크 결과를 조건문으로 활용)
- name: Check if configured
  stat:
    path: /etc/app/config
  register: config_stat

- name: Configure
  shell: /tmp/configure.sh
  when: not config_stat.stat.exists
```

<br>

**3. 결과 상태의 명시적 제어**: changed_when, failed_when

Ansible은 기본적으로 명령 실행 후 리턴 코드(`rc`)가 0이면 `changed`, 그 외에는 `failed`로 간주한다. 하지만, 단순히 상태를 조회하는 명령은 실제 변경이 일어나지 않았음에도 `changed`거나, 정상적인 상황임에도 에러(`failed`)로 처리될 수 있다. 

이 때 `changed_when`, `failed_when`으로 명시적으로 상태를 제어할 수 있는 것이다.

```yaml
- name: Check service status
  shell: systemctl is-active myapp
  register: result
  # 상태 조회일 뿐이므로, 실행되더라도 changed가 아니라 ok로 표시되게 함
  changed_when: false 
  # 리턴 코드가 0 혹은 3이면 정상, 그 외에는 실패
  failed_when: result.rc not in [0, 3] 
```

### 결론

사실 대부분의 맥락에서는 Ansible이 멱등성을 보장한다고 해도 크게 무리는 없어 보인다.
다만, 조금 더 엄밀하게 표현하고 싶다면, "Ansible은 멱등성을 보장한다"라는 표현 보다는, 아래와 같이 표현하는 것이 좋지 않을까:
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

<br>

## Terraform과의 비교

IaC 도구로는 Terraform이 가장 많이 언급되는데, Ansible과는 어떤 차이가 있을까?

| 구분 | Terraform | Ansible |
|------|-----------|---------|
| **주요 용도** | 인프라 프로비저닝 (생성/삭제) | 구성 관리 (Configuration Management) |
| **강점** | 클라우드 리소스 생성 (EC2, VPC 등) | 서버 설정, 애플리케이션 배포 |
| **상태 관리** | State 파일로 현재 상태 추적 | Stateless (상태 파일 없음) |
| **언어** | HCL (선언형) | YAML (절차형에 가까움) |
| **실행 방식** | 선언된 상태와 실제 상태 비교 후 조정 | Task를 정의된 순서대로 실행 |

간단히 말하면, **Terraform으로 인프라를 만들고, Ansible로 그 위에 소프트웨어를 설정**한다고 볼 수 있다. 실제로 두 도구를 함께 사용하는 경우가 많다고 한다.


<br>


# 여담

Ansible을 공부하면서 다른 기술들과의 유사성이 눈에 들어왔다.

## HTTP Status Code와의 유사성

Ansible의 반환 상태(changed, ok, failed)는 HTTP Status Code와 비슷한 구조다.

둘 다 **표준 규약을 정의**하고, **구현체가 적절한 코드를 반환**하는 구조다. HTTP가 "웹 통신의 표준 응답 규약"이라면, Ansible의 changed/ok/failed는 "인프라 자동화의 표준 응답 규약"이라 할 수 있다. 

멱등성 관점에서도 유사하다. REST API를 HTTP로 구현할 때 PUT/DELETE는 멱등해야 하지만 실제 구현은 개발자에 따라 다르듯, Ansible도 멱등성을 지향하지만 모든 모듈이 멱등한 건 아니다.

## Kubernetes Desired State와의 유사성

Ansible과 Kubernetes는 **Desired State(원하는 상태)**를 정의한다는 점에서 닮았다. 

다만, 핵심 차이는 상태를 유지하려는 지속성이다. Kubernetes는 Controller가 24시간 내내 현재 상태를 감시하며 원하는 상태로 되돌리는 Reconciliation Loop(조정 루프)가 동작하지만, Ansible은 사용자가 Playbook을 실행하는 그 시점에만 원하는 상태가 되도록 조정한다.
 

