---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 15. 결론"
excerpt: "Ansible의 철학이 Kubespray에서 어떻게 구현되어 있는지 살펴보자.."
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

Ansible 학습을 마무리하며, Ansible의 철학과 개념들이 Kubespray에서 어떻게 녹아 있는지 감상하고, [0편]({% post_url 2026-01-12-Kubernetes-Ansible-00 %})에서 언급했던 과거 프로젝트 경험을 다시 돌아본다. 그리고 앞으로 Ansible을 어떻게 활용할 수 있을지 생각해 본다.

- Kubespray 인벤토리: 호스트 변수, 역할 기반 그룹, `:children` 문법
- Kubespray Facts Playbook: 선택적 팩트 수집, 역할 캡슐화
- 과거 프로젝트 회고: 예전에 작성했던 플레이북을 새로운 눈으로 읽기
- 앞으로의 활용: 현재 운영 중인 Kubernetes 클러스터에 Ansible 도입 구상

<br>

# Kubespray 인벤토리

[Kubespray 인벤토리](https://github.com/kubernetes-sigs/kubespray/blob/master/inventory/sample/inventory.ini)를 살펴보자.

```ini
[all]
master01 ansible_host=192.168.10.10 ip=192.168.10.10 ansible_user=root
worker01 ansible_host=192.168.10.11 ip=192.168.10.11 ansible_user=root
worker02 ansible_host=192.168.10.12 ip=192.168.10.12 ansible_user=root

[kube_control_plane]
master01

[etcd]
master01

[kube_node]
worker01
worker02

[k8s_cluster:children]
kube_control_plane
kube_node
```

첫 번째로 눈에 띄는 것은 **호스트 변수**다. `ansible_host`, `ip`, `ansible_user` 같은 변수들이 호스트 정의와 함께 선언되어 있다. 이런 변수들 덕분에 Kubespray는 각 노드에 맞는 설정을 자동으로 적용할 수 있다. 예를 들어, Kubernetes 서비스가 바인딩할 IP를 `ip` 변수로 지정하면, 별도의 설정 파일 없이도 노드마다 다른 값을 사용할 수 있다.

두 번째로 눈에 띄는 것은 **역할 기반 그룹**이다. `kube_control_plane`, `etcd`, `kube_node`처럼 Kubernetes 컴포넌트의 역할에 따라 그룹이 나뉘어 있다. 같은 호스트(master01)가 여러 그룹에 속할 수 있다는 점이 인상적이다. master01은 `kube_control_plane`이면서 동시에 `etcd` 멤버다.

세 번째로 눈에 띄는 것은 `:children` 문법이다. `k8s_cluster:children`은 `kube_control_plane`과 `kube_node` 그룹을 포함하는 상위 그룹을 만든다. 이렇게 하면 클러스터 전체에 적용할 작업(`k8s_cluster` 대상)과 특정 역할에만 적용할 작업(`kube_control_plane` 대상)을 명확히 구분할 수 있다.

Kubernetes 클러스터의 복잡한 토폴로지가 몇 줄의 INI 파일로 표현된다. *virtually any IT environment*를 표현할 수 있다던 Ansible의 약속이 여기서 실현된다.

<br>

# Kubespray Facts Playbook

[Kubespray의 Facts 수집 Playbook](https://github.com/kubernetes-sigs/kubespray/blob/master/playbooks/internal_facts.yml)도 흥미롭다.

```yaml
- name: Gather facts
  hosts: k8s_cluster:etcd:calico_rr
  gather_facts: false
  tags: always
  tasks:
    - name: Gather and compute network facts
      import_role:
        name: network_facts

    - name: Gather minimal facts
      setup:
        gather_subset: '!all'

    - name: Gather necessary facts (network)
      setup:
        gather_subset: '!all,!min,network'
        filter: "ansible_*_ipv[46]*"

    - name: Gather necessary facts (hardware)
      setup:
        gather_subset: '!all,!min,hardware'
        filter: "ansible_*total_mb"
```

`hosts: k8s_cluster:etcd:calico_rr`는 세 그룹의 호스트를 모두 대상으로 한다. 콜론(`:`)으로 여러 그룹을 결합하는 패턴이다. 인벤토리에서 정의한 그룹들이 플레이북에서 자연스럽게 사용된다.

`gather_facts: false`로 자동 수집을 끄고, `setup` 모듈로 필요한 것만 선택적으로 수집한다. `gather_subset: '!all,!min,network'`는 네트워크 정보만, `filter: "ansible_*_ipv[46]*"`는 IPv4/IPv6 주소만 가져온다. 수천 대의 노드에서 불필요한 정보까지 수집하면 시간이 오래 걸릴 테니, 이런 최적화가 필요하다.

`import_role: name: network_facts`는 [network_facts 역할](https://github.com/kubernetes-sigs/kubespray/tree/master/roles/network_facts)을 가져와 네트워크 정보를 계산한다. 복잡한 네트워크 로직이 역할로 캡슐화되어 있어, 플레이북 자체는 간결하게 유지된다.

Kubernetes 클러스터 설치라는 복잡한 작업이, 읽기 쉬운 YAML로 표현된다. *Code that reads like documentation*이라던 Ansible의 철학이 여기서 빛난다.

<br>

# 과거 프로젝트 회고

[이 시리즈의 첫 번째 글]({% post_url 2026-01-12-Kubernetes-Ansible-00 %})에서 언급했던 과거 프로젝트를 다시 떠올려 본다. 모놀리식 영상 관제 시스템을 마이크로서비스로 재구성하는 프로젝트였다. 여러 호스트에 서비스를 배포하고 설정을 관리해야 했는데, Ansible이 그 핵심이었다.

## 내가 작성했던 플레이북

그때 내가 작성했던 플레이북들이 있다.

```yaml
# get-timezone.yaml
- name: Gather timezone information
  hosts: localhost
  tasks:
    - name: Read /etc/timezone file
      shell: 
        cat /etc/timezone
      register: result
    - name: Output timezone file content
      debug:
        var: result.stdout
```

```yaml
# get-chronyd-configuration.yaml
- name: Get chrony configuration
  hosts: all
  gather_facts: no
  tasks:
    - name: Check if chrony.conf file exists
      stat:
        path: /etc/chrony/chrony.conf
      register: chrony_conf_exists
    
    - name: Read chrony configuration
      shell:
        cmd: >
          sh -c '
            if grep -q "^local" /etc/chrony/chrony.conf; then
                grep "^local" /etc/chrony/chrony.conf
            else
                grep "^server" /etc/chrony/chrony.conf
            fi
          '
      register: result
      when: chrony_conf_exists.stat.exists
```

```yaml
# set-chronyd.yaml - NTP 서버 설정
- name: Configure chrony daemon
  hosts: all
  gather_facts: false
  become: true
  vars:
    chrony_mode: "server"
    chrony_server_mode: "private"
  tasks:
    - name: Make sure chronyd is installed
      apt:
        name: chrony
        state: latest

    - name: Check if chrony.conf exists
      stat:
        path: "/etc/chrony/chrony.conf"
      register: file_stat

    - name: Deploy chrony.conf template
      template:
        src: "template/chrony.{% raw %}{{ chrony_mode }}{% if chrony_mode == 'server' %}.{{ chrony_server_mode }}{% endif %}{% endraw %}.conf.j2"
        dest: "{% raw %}{{ file_stat.stat.path }}{% endraw %}"
        owner: root
        group: root
        mode: 0644
      when: file_stat.stat.exists

    - name: Restart chronyd
      service:
        name: chrony
        state: restarted
```

`template` 모듈이 참조하는 Jinja2 템플릿 파일도 있다. `chrony_mode`가 `client`일 때 사용되는 템플릿이다.

{% raw %}
```jinja2
{# template/chrony.client.conf.j2 #}
server {{ chrony_server_host }} iburst
keyfile /etc/chrony/chrony.keys
driftfile /var/lib/chrony/chrony.drift
ntsdumpdir /var/lib/chrony
log tracking measurements statistics
logdir /var/log/chrony
maxupdateskew 100.0
rtcsync
makestep 1 3
```
{% endraw %}

{% raw %}`{{ chrony_server_host }}`{% endraw %} 변수가 실제 NTP 서버 주소로 치환된다. 플레이북에서 변수를 선언하고, 템플릿에서 그 변수를 사용하는 패턴이다.

지금 다시 보니 많은 것들이 보인다. `hosts: all`, `gather_facts: no`, `register`, `when` 조건문, `stat` 모듈, `become: true`, `vars`, `template` 모듈. Kubespray의 플레이북과 같은 언어로 작성되어 있다. 이번에 배운 개념들이 전부 들어 있는데, 부끄럽게도 그때의 나는 이것들이 어떤 의미인지 제대로 이해하지 못한 채 사용했다(그래서 30분이면 된다는 철학을 따르지 못하고, 일주일이 걸렸다).

## 팀장님이 작성하신 플레이북

사실 프로젝트의 핵심 플레이북들은 대부분 팀장님이 작성하셨고, 나는 그걸 따라 배웠다. 지금 다시 보면 Ansible의 철학이 잘 녹아 있다.

```yaml
# install-docker-and-compose.yaml - Docker 설치
- hosts: all
  become: yes
  tasks:
    - name: Update APT cache
      apt:
        update_cache: yes

    - name: Install required system packages
      apt:
        name: ['apt-transport-https', 'ca-certificates', 'curl', 'software-properties-common']
        state: present

    - name: Add Docker GPG key
      apt_key:
        url: https://download.docker.com/linux/ubuntu/gpg
        state: present

    - name: Add Docker APT repository
      apt_repository:
        repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu {% raw %}{{ ansible_lsb.codename }}{% endraw %} stable"
        state: present

    - name: Install Docker
      apt:
        name: ['docker-ce', 'docker-ce-cli', 'containerd.io']
        state: present
        update_cache: yes

    - name: Ensure Docker service is running
      service:
        name: docker
        state: started

    - name: Add gaia user to docker group
      user:
        name: gaia
        groups: docker
        append: yes

    - name: Install Docker Compose
      get_url:
        url: "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-{% raw %}{{ ansible_system }}{% endraw %}-{% raw %}{{ ansible_userspace_architecture }}{% endraw %}"
        dest: /usr/local/bin/docker-compose
        mode: '0755'
```

`apt`, `apt_key`, `apt_repository`, `service`, `user`, `get_url` 모듈. {% raw %}`{{ ansible_lsb.codename }}`{% endraw %}, {% raw %}`{{ ansible_system }}`{% endraw %} 같은 Facts 변수를 활용해 OS에 맞는 패키지를 설치한다.

```yaml
# install-service.yaml - 서비스 설치 (Task 분리 패턴)
- hosts: all
  gather_facts: False
  vars_files:
    - gaia-vars.yaml
  vars:
    GAIA_SERVICE_NAME: "{% raw %}{{ image_name }}{% endraw %}"
    GAIA_SERVICE_ID: "{% raw %}{{ lookup('pipe', 'uuidgen') }}{% endraw %}"
  tasks:
    - name: Generate GAIA_SERVICE_ID
      set_fact:
        GAIA_SERVICE_ID: "{% raw %}{{ lookup('pipe', 'uuidgen') }}{% endraw %}"

    - name: Make GAIA_SERVICE_DIR
      set_fact:
        GAIA_SERVICE_DIR: "{% raw %}{{ GAIA_SERVICE_BASE_DIR }}/{{ GAIA_SERVICE_NAME }}/{{ GAIA_SERVICE_ID }}{% endraw %}"

    - name: Run login-to-registry task
      import_tasks: task-login-to-registry.yaml

    - name: Run pull-image task
      import_tasks: task-pull-image.yaml

    - name: Run make-sandbox task
      import_tasks: task-make-sandbox.yaml

    - name: Run launch-docker task
      import_tasks: task-launch-docker.yaml
```

`vars_files`로 변수 파일 분리, `set_fact`로 동적 변수 생성, `import_tasks`로 Task 모듈화. 복잡한 서비스 설치 과정을 작은 단위로 나누어 관리하는 패턴이다.

```yaml
# uninstall-service.yaml - 서비스 삭제 (조건부 실행 패턴)
- hosts: all
  gather_facts: no
  tasks:
    - name: Make GAIA_SERVICE_DIR
      set_fact:
        GAIA_SERVICE_DIR: "{% raw %}{{ GAIA_SERVICE_BASE_DIR }}/{{ GAIA_SERVICE_NAME }}/{{ GAIA_SERVICE_ID }}{% endraw %}"

    - name: Check if GAIA_SERVICE_DIR exists
      stat:
        path: "{% raw %}{{ GAIA_SERVICE_DIR }}{% endraw %}"
      register: service_dir

    - name: Fail if GAIA_SERVICE_DIR not exists
      fail:
        msg: "{% raw %}{{ GAIA_SERVICE_DIR }}{% endraw %} doesn't exists. Abandon."
      when: not service_dir.stat.isdir

    - name: Check if docker-compose.yaml exists
      stat:
        path: "{% raw %}{{ GAIA_SERVICE_DIR }}{% endraw %}/etc/docker-compose.yaml"
      register: docker_compose

    - name: Run stop-docker task
      import_tasks: task-stop-docker.yaml
      when: docker_compose.stat.exists

    - name: Check if systemd service exists
      stat:
        path: "/etc/systemd/system/gaia.{% raw %}{{ GAIA_SERVICE_NAME }}{% endraw %}.service"
      register: systemd_service

    - name: Run stop-systemd task
      import_tasks: task-stop-systemd.yaml
      when: systemd_service.stat.exists

    - name: Run remove-sandbox task
      import_tasks: task-remove-sandbox.yaml
```

`fail` 모듈로 조건 불충족 시 명시적 실패 처리, `stat`과 `when`을 조합한 조건부 Task 실행. Docker 컨테이너인지 Systemd 서비스인지에 따라 다른 정리 작업을 수행한다. Kubespray의 Role 구조와 비슷한 설계 철학이 보인다.

## 돌아보며

그 프로젝트에서 각 패키지는 `install.yaml` 플레이북을 포함했고, Package Manager가 이를 실행해 서비스를 설치했다. 타임존 설정, NTP 서버 구성, Docker 이미지 배포, Systemd 서비스 등록까지, 모든 것이 Ansible 플레이북으로 자동화되어 있었다.

그때는 플레이북이 어렵게 느껴졌다. YAML 문법도 낯설었고, 모듈들의 동작 방식도 이해하기 힘들었다. 하지만 이제는 다르다. `gather_facts: false`가 왜 필요한지, `become: true`가 무엇을 의미하는지, `import_tasks`로 Task를 분리하는 이유가 무엇인지 이해할 수 있다.

<br>

# 앞으로: 실무에 Ansible 도입하기

Ansible을 공부하면서, 현재 내가 운영하고 있는 Kubernetes 클러스터에도 도입해 보고 싶다는 생각이 들었다.

## 현재 상황

지금 운영 중인 K3s 클러스터는 설정이 파편화되어 있다. 노드마다 설정 방식이 다르고, 변경 이력 추적이 안 되고, "이 노드에서는 되는데 저 노드에서는 왜 안 되지?" 같은 상황이 빈번하다.

- 컨테이너 런타임 설정이 노드마다 다름 (어떤 노드는 config.yaml, 어떤 노드는 systemd 플래그)
- 프라이빗 레지스트리 설정이 일관성 없음
- 모든 설정 변경이 SSH 접속 후 수작업
- 노드 장애 시 재구성이 어려움

## Ansible로 해결할 수 있을까?

이번에 배운 Ansible 개념들을 적용해 보면:

| 문제 | Ansible 해결책 |
| --- | --- |
| 노드별 설정 파편화 | Playbook + Jinja2 템플릿으로 표준화 |
| 변경 이력 추적 불가 | Git 저장소에서 Playbook 관리 |
| 수작업 실수 | 멱등성 보장으로 일관된 상태 유지 |
| 노드 재구성 어려움 | Playbook 실행만으로 표준 설정 완료 |

특히 인벤토리의 그룹 기능이 유용할 것 같다. GPU 종류별로 노드를 그룹화하면:

```ini
[gpu_rtx4090]
node-01
node-02

[gpu_other]
node-03
node-04

[k3s_cluster:children]
gpu_rtx4090
gpu_other
```

GPU 종류에 따라 다른 드라이버나 설정을 적용하면서도, 공통 설정은 `k3s_cluster` 전체에 적용할 수 있다.

## 남은 고민

아직 해결하지 못한 질문들이 있다:

- **Kubernetes 리소스 관리**: GPU Operator, Argo Workflows 같은 Helm 차트도 Ansible로 관리할까? 아니면 기존처럼 Helm을 사용하되, GitOps와 조합할까?
- **역할 분담**: Ansible은 노드 레벨, GitOps(ArgoCD 등)는 Kubernetes 리소스 레벨로 나누는 게 일반적인가?
- **도입 전략**: 프로덕션 클러스터에서 어디서부터 시작하는 게 안전할까? 신규 노드부터? 특정 그룹부터?

이 질문들은 앞으로 더 공부하고 경험하면서 답을 찾아가야 할 것 같다.

<br>

# 마치며

*"If people aren't successful trying this out in about 30 minutes, they're going to move on."*

30분 안에 성공 경험을 만들어줘야 한다던 Michael DeHaan의 말이 떠오른다. Ansible을 사용했던 예전의 나는 30분 안에 성공하지 못했다. 설계 철학도, 구성 요소도 제대로 이해하지 못한 채, 문서를 보고 플레이북을 작성하기 급급했다. 

하지만 이번에 Ansible의 탄생 배경과 설계 철학을 공부하면서, 비로소 그 언어가 읽히기 시작했다. 문서처럼 읽히는 코드라더니, 정말 그랬다. Kubespray의 인벤토리와 플레이북을 보며 감탄했다. 복잡한 Kubernetes 클러스터 구성이, 몇 줄의 YAML로 선언되어 있었다.

도구를 사용하는 것과 도구를 이해하는 것은 다르다. 그때의 나는 Ansible을 사용했지만, 이해하지 못했다. 이제는 이해한다. 이해하니까 더 잘 사용할 수 있을 것 같다.

다시 예전 프로젝트의 플레이북들을 열어 본다면, 이제는 다르게 보일 것이다. 그리고 현재 운영 중인 클러스터에 Ansible을 도입하게 된다면, 그 내부에서 어떤 일이 일어나는지 상상할 수 있을 것이다.

언젠가 30분 안에 성공할 날이 오길 바란다.