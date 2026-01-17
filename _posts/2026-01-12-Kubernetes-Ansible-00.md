---
title:  "[Ansible] Kubespray: Kubespray를 위한 Ansible 기초 - 0. 들어 가며"
excerpt: "Ansible의 탄생 배경과 설계 철학을 살펴본다."
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

# 들어 가며

Kubespray는 Ansible을 기반으로 동작한다. Kubespray를 제대로 이해하려면 Ansible에 대해 먼저 알아야 한다. 

<br>

# 공식 문서 첫 페이지

어떤 기술을 접할 때, 공식 문서 첫 장을 읽는 걸 좋아하는 편이다. [Ansible 공식 문서](https://docs.ansible.com/) 첫 페이지를 보면, 깔끔한 디자인과 함께 아래 문구가 눈에 띈다.

> Ansible is open-source technology that can perform virtually any IT task and remove complexity from workflows.

*virtually any IT task*, 거의 모든 IT 태스크를 수행할 수 있고, workflow의 복잡함을 제거한다. '자동화'라는 말은 없지만, 사실상 자동화 도구임을 알 수 있다. 실제로 Ansible로 할 수 있는 것들을 나열해 보면, 정말 거의 모든 것이다.

- 서버 프로비저닝
- 애플리케이션 배포
- 네트워크 장비 설정 (Cisco, Juniper 등)
- 클라우드 리소스 관리 (AWS, Azure, GCP)
- 컨테이너 오케스트레이션
- 보안 정책 적용
- 백업 자동화
- 모니터링 설정
- 그 외 SSH로 할 수 있는 거의 모든 것

그런데 왜 '자동화'라는 말 대신 이런 표현을 썼을까. 뭔가 '거의 모든 것'을, '복잡하지 않게' 만들고 싶어서 탄생한 도구가 아닐까 하는 생각이 들었다.

<br>

조금 더 스크롤을 내리면, 아래 두 문구도 보인다.

- **Code that reads like documentation**: Ansible is an automation language that can describe *any IT environment*, whether homelab or large scale infrastructure. It is easy to learn, beautiful code that reads like clear documentation.
- **Freedom from repetitive tasks**: As an automation engine, Ansible ensures that your *IT environment stays exactly as you describe it, no matter the complexity*. Not only that, you can automate any command with Ansible to *eliminate drudgery* from your daily routine. Ansible gives you tooling to be more productive and solve problems that really matter.


정리하면 이렇다.

- **문서처럼 읽히는 코드**: 어떠한 IT 환경이든 표현할 수 있는 자동화 언어다. homelab이든 대규모 인프라든 상관없다. 배우기 쉽고, 마치 명확한 문서처럼 읽히는 아름다운 코드다.
- **반복 작업으로부터의 해방**: 자동화 엔진으로서, 복잡성과 관계없이 내가 묘사하는 대로 IT 환경이 유지되게 해 준다. 어떤 명령이든 자동화해서 일상의 고역(*drudgery*)을 없앨 수 있다. 더 생산적일 수 있고, 진짜 중요한 문제에 집중할 수 있게 도와준다.

<br>

거의 모든 IT 환경을, 내가 원하는 대로, 고역이지 않게, 복잡하지 않은 방식으로 설정할 수 있는 도구를 만들고 싶었던 것 같다.

<br>

# 탄생 배경

Ansible의 창시자는 Michael DeHaan이다. 그는 이전에 Puppet, Cobbler 같은 자동화 도구를 만들었던 사람인데, 2012년경 기존 자동화 도구들의 문제점을 느꼈다고 한다.

> **참고: Puppet과 Cobbler**
>
> Puppet은 Ruby 기반의 구성 관리 도구로, Master-Agent 아키텍처를 사용한다. Cobbler는 Linux 설치 서버로, PXE 기반의 네트워크 부팅과 자동 설치를 지원한다. DeHaan은 이러한 도구들을 만들면서 복잡성과 에이전트 관리의 어려움을 경험했다.

## 기존 도구들의 복잡성

당시 대표적인 자동화 도구였던 Puppet의 코드를 보자.

```ruby
# Puppet - Ruby DSL, 복잡한 문법
class nginx {
  package { 'nginx':
    ensure => installed,
  }
  
  service { 'nginx':
    ensure  => running,
    enable  => true,
    require => Package['nginx'],
  }
  
  file { '/etc/nginx/nginx.conf':
    ensure  => file,
    source  => 'puppet:///modules/nginx/nginx.conf',
    require => Package['nginx'],
    notify  => Service['nginx'],
  }
}
```

Ruby DSL 기반의 복잡한 문법이다. 리소스 간 의존성을 `require`, `notify` 등으로 명시적으로 관리해야 하고, 프로그래밍 지식이 필요하다. 기존 도구들은 아래와 같은 문제가 있었다.

- 에이전트 설치 필요 (Chef, Puppet)
- 복잡한 DSL 학습 필요
- Master-Slave 아키텍처
- 인증서 관리, 네트워크 설정 등 부가적인 복잡성

<br>

Michael DeHaan은 이러한 복잡성에서 벗어나고 싶었던 게 아닐까?

같은 nginx 설정을 Ansible로 작성하면 아래와 같다. 확실히 읽기 쉽다. 각 Task의 이름이 자연어로 되어 있고, 무엇을 하는지 명확하다. 의존성도 `notify`로 간단하게 표현된다.


```yaml
# Ansible - YAML 기반, 읽기 쉬운 선언적 구조
- name: Setup nginx
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
    
    - name: Copy config
      copy:
        src: nginx.conf
        dest: /etc/nginx/nginx.conf
      notify: Restart nginx
    
    - name: Start nginx
      service:
        name: nginx
        state: started
  
  handlers:
    - name: Restart nginx
      service:
        name: nginx
        state: restarted
```


<br>

# 설계 철학

## 핵심 신념

Michael DeHaan은 Ansible을 만들 때 명확한 원칙이 있었다. 그가 인터뷰에서 했다는 말을 살펴 보면:

> "If people aren't successful trying this out in about 30 minutes, they're going to move on. You have to make somebody successful within their lunch hour."

"사람들이 30분 안에 성공하지 못하면 다른 도구로 넘어간다. 점심시간 안에 성공 경험을 만들어줘야 한다."고 한다.

단순성에 대한 그의 철학은 여기서 나온다. 내부는 복잡해도 되지만, 사용자가 보는 인터페이스는 30분 안에 이해할 수 있어야 한다. 공식 문서에서 봤던 *"no matter the complexity"*의 진짜 의미가 여기에 있다. 복잡한 자동화 작업도 사용자에게는 간단해야 한다는 것이다.

## 설계 원칙

이러한 철학은 설계 원칙으로 이어진다.

1. **Simplicity over Power**: 복잡한 기능보다 단순한 사용성
2. **Readability over Cleverness**: 영리한 코드보다 읽기 쉬운 코드
3. **Agentless over Feature-rich**: 많은 기능보다 단순한 아키텍처(에이전트가 없는 방식)
4. **SSH over Custom Protocol**: 커스텀 프로토콜보다 표준 SSH
5. **YAML over DSL**: 복잡한 DSL보다 단순한 YAML
6. **Data over Code**: 프로그래밍 코드보다 데이터 표현

<br>

# 설계 결정

이러한 철학이 실제 설계에 어떻게 반영되었는지 살펴보자.

## 에이전트리스 아키텍처

왜 에이전트가 없는 방식을 선택했을까.

- 관리할 데몬이 없다
- 인증서 관리가 필요 없다
- 별도 포트를 열 필요가 없다
- SSH는 이미 있다
- 무엇보다, 단순하다

기존 도구들과 비교하면 차이가 명확하다.

- **Puppet/Chef (에이전트 방식)**: Control Server가 각 서버에 설치된 Agent와 통신해야 함
  - Agent가 항상 실행 중이어야 함
    - 에이전트를 설치하고 업데이트를 관리해야 함
    - 에이전트에 장애가 발생하면 처리해야 함
  - 위의 모든 과정이 복잡도를 증가시킴

- **Ansible (에이전트리스)**: Control Node가 SSH를 통해 서버에 직접 접근함
  - SSH만 있으면 되므로 별도로 관리할 에이전트가 없음
  - 에이전트라는 장애 포인트가 없어지므로 시스템이 단순해짐


## Push 방식

Ansible은 Pull이 아닌 Push 방식을 기본으로 사용(Pull 방식도 지원)한다.

- **Push 방식**: 사용자가 직접 명령을 실행하면 즉시 결과를 받는 방식
  - Playbook을 실행하면 바로 작업이 수행되고 결과가 출력됨
  - 언제 무엇을 실행할지 사용자가 완전히 제어할 수 있어 예측 가능
- **Pull 방식**: Agent가 주기적으로 Control Server에 접속해서 변경 사항을 가져 감
  - 사용자가 설정을 변경하더라도 Agent가 다음 체크 시점까지 기다려야 하므로, 언제 적용될지 예측하기 어려움
  - Agent 설정(체크 주기, 인증 등)을 이해해야 한다.

Ansible이 선택한 Push 방식은 사용자의 학습 곡선을 낮추기도 한다. "실행 → 결과"의 흐름이 직관적이기 때문이다. 명령을 실행하면 바로 어떤 일이 일어나는지 볼 수 있어 상대적으로 디버깅이 용이하기도 하다. Pull 방식처럼 "설정 변경 → 대기 → 언젠가 적용됨"의 비동기적 흐름을 이해할 필요가 없다.

## YAML 선택

Ansible은 복잡한 DSL 대신 YAML을 선택했다. 문서처럼 읽히고, 선언적 구조를 가진다. Chef와 비교해 보면 차이가 명확하다.

```ruby
# Chef - Ruby 기반, 프로그래밍 언어 형태
package 'nginx' do
  action :install
end

service 'nginx' do
  action [:enable, :start]
  subscribes :restart, 'template[/etc/nginx/nginx.conf]', :delayed
end

template '/etc/nginx/nginx.conf' do
  source 'nginx.conf.erb'
  notifies :restart, 'service[nginx]'
end
```

```yaml
# Ansible - YAML 기반, 데이터 형식
- name: Install nginx
  apt: name=nginx

- name: Copy config
  template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: Restart nginx

- name: Start nginx
  service: name=nginx state=started
```

<br>

# 마무리

Ansible은 이러한 배경과 철학을 가지고 탄생했다. 창시자 Michael DeHaan에 의해 AnsibleWorks라는 이름으로 2012년에 처음 소개되었고, 2015년 10월 Red Hat이 인수하여 현재까지 개발, 관리하고 있다.

사실 예전에 회사에서 프로젝트를 진행할 때 Ansible을 사용한 경험이 있다. 모놀리식 영상 관제 시스템을 마이크로서비스로 재구성하는 프로젝트였는데, 여러 호스트에 서비스를 배포하고 설정을 관리해야 했다. 원격 서버에서 타임존 설정, NTP 서버 설정 같은 작업을 Ansible 플레이북으로 자동화했다. 그때는 잘 모르고 사용해서 몰랐는데, 다시 보니 이런 철학들이 보인다. Michael DeHaan은 쉽게 읽히길 바랐다고 했는데, 그때의 나는 Ansible 플레이북이 너무 어려웠다. 

이제는 그 철학을 알게 되었으니, 다시 공부해 보면 된다. 다음 글에서는 Ansible의 기본 개념과 구성 요소를 살펴본다.