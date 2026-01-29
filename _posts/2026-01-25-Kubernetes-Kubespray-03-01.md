---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.1. ansible.cfg 분석"
excerpt: "Kubespray에서 사용하는 ansible.cfg 설정을 상세히 분석하고, 환경에 맞게 커스터마이징하는 방법을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray의 `ansible.cfg` 설정**을 상세히 분석한다.

- **[ssh_connection]**: SSH 파이프라이닝, 연결 재사용으로 성능 최적화
- **[defaults]**: Fact 캐싱, 역할 검색 경로, 콜백 플러그인 등 기본 설정
- **[inventory]**: 인벤토리 스캔 시 제외할 패턴
- **커스터마이징**: 환경에 맞게 설정을 수정하는 방법

<br>

# ansible.cfg 설정

[Ansible 시리즈]({% post_url 2026-01-12-Kubernetes-Ansible-04 %})에서 살펴본 것처럼, Ansible은 다음 순서로 설정 파일을 찾는다:

1. `ANSIBLE_CONFIG` 환경변수
2. **현재 디렉터리의 `ansible.cfg`** ← Kubespray 실행 시 적용
3. 홈 디렉터리의 `~/.ansible.cfg`
4. `/etc/ansible/ansible.cfg`

Kubespray는 프로젝트 루트에 자체 `ansible.cfg`를 포함하고 있다. 따라서 **Kubespray 디렉터리에서 `ansible-playbook`을 실행해야** 이 설정이 적용된다. 이것이 [이전 실습]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %})에서 항상 `cd ~/kubespray` 후 명령을 실행했던 이유다.

<br>

# Kubespray ansible.cfg

Kubespray의 `ansible.cfg` 전문은 다음과 같다:

```ini
[ssh_connection]
pipelining=True
ssh_args = -o ControlMaster=auto -o ControlPersist=30m -o ConnectionAttempts=100 -o UserKnownHostsFile=/dev/null
#control_path = ~/.ssh/ansible-%%r@%%h:%%p

[defaults]
# https://github.com/ansible/ansible/issues/56930 (to ignore group names with - and .)
force_valid_group_names = ignore

host_key_checking=False
gathering = smart
fact_caching = jsonfile
fact_caching_connection = /tmp
fact_caching_timeout = 86400
timeout = 300
stdout_callback = default
display_skipped_hosts = no
library = ./library
callbacks_enabled = profile_tasks
roles_path = roles:$VIRTUAL_ENV/usr/local/share/kubespray/roles:$VIRTUAL_ENV/usr/local/share/ansible/roles:/usr/share/kubespray/roles
deprecation_warnings=False
inventory_ignore_extensions = ~, .orig, .bak, .ini, .cfg, .retry, .pyc, .pyo, .creds, .gpg

[inventory]
ignore_patterns = artifacts, credentials
```

## 주요 설정 요약

| 설정 | 값 | 설명 |
|------|----|----- |
| `pipelining` | `True` | SSH 파이프라이닝으로 성능 향상 |
| `host_key_checking` | `False` | SSH 호스트 키 검증 비활성화 (초기 구성 시 편의) |
| `gathering` | `smart` | 팩트 수집 최적화 (캐시 활용) |
| `fact_caching` | `jsonfile` | 팩트를 JSON 파일로 캐싱 |
| `fact_caching_timeout` | `86400` | 캐시 유효 시간 (24시간) |
| `timeout` | `300` | SSH 연결 타임아웃 (5분) |
| `display_skipped_hosts` | `no` | 스킵된 호스트 출력 안 함 (로그 간결화) |
| `callbacks_enabled` | `profile_tasks` | 태스크별 실행 시간 프로파일링 |
| `roles_path` | 여러 경로 | 롤 검색 경로 (로컬 우선) |
| `force_valid_group_names` | `ignore` | 그룹명에 `-`, `.` 허용 |

각 섹션별로 상세히 살펴보자.

<br>

## [ssh_connection] 섹션

SSH 연결 관련 설정이다. **대규모 클러스터에 반복 접속**하는 Kubespray 특성에 맞게 성능과 안정성이 최적화되어 있다.

### pipelining = True

SSH 세션 하나에서 여러 명령을 파이프라인으로 전송한다.

```bash
# pipelining = False (기본값)
SSH 연결 → 명령1 실행 → 연결 종료
SSH 연결 → 명령2 실행 → 연결 종료
SSH 연결 → 명령3 실행 → 연결 종료

# pipelining = True
SSH 연결 → 명령1, 명령2, 명령3을 파이프라인으로 전송 → 결과 일괄 수신 → 연결 종료
```

SSH 연결 오버헤드가 줄어들어 **실행 속도가 크게 향상**된다. Kubespray처럼 수십~수백 개의 태스크를 실행하는 경우 효과가 크다.

<br>

### ssh_args

SSH 클라이언트 옵션을 지정한다. `-o Option=Value` 형식으로 여러 옵션을 설정한다.

```ini
ssh_args = -o ControlMaster=auto -o ControlPersist=30m -o ConnectionAttempts=100 -o UserKnownHostsFile=/dev/null
```

| 옵션 | 값 | 설명 |
|------|------|------|
| `ControlMaster` | `auto` | SSH 연결 멀티플렉싱 활성화. 첫 연결을 마스터로 사용하고 이후 연결은 재사용 |
| `ControlPersist` | `30m` | 마스터 연결을 30분간 유지. 매번 재인증 없이 빠른 연결 가능 |
| `ConnectionAttempts` | `100` | 연결 실패 시 최대 100번 재시도. 네트워크 불안정 환경에서 유용 |
| `UserKnownHostsFile` | `/dev/null` | known_hosts 파일을 사용하지 않음. 아래 상세 설명 참고 |

<br>

#### UserKnownHostsFile=/dev/null

SSH의 호스트 키 검증 메커니즘을 비활성화한다.

**SSH 호스트 키(지문)**이란, SSH 서버의 공개키를 해싱한 값이다. SSH 서버에 처음 접속하면 다음과 같은 메시지가 표시된다:

```
The authenticity of host '192.168.10.100 (192.168.10.100)' can't be established.
ECDSA key fingerprint is SHA256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.
Are you sure you want to continue connecting (yes/no)?
```

`yes`를 입력하면 `~/.ssh/known_hosts`에 저장되고, 다음 접속 시 지문이 일치하는지 확인한다. 지문이 달라지면 경고가 발생한다(중간자 공격 방지).

<br>

`UserKnownHostsFile=/dev/null`은 지문을 `/dev/null`로 보낸다. `/dev/null`이란 Linux의 널 장치(블랙홀)로, 이곳에 쓰여진 데이터는 모두 버려진다. 이렇게 설정하면:
- 지문이 저장되지 않음
- 지문 검증을 하지 않음
- 매번 새로운 호스트처럼 처리

동적으로 생성/삭제되는 클라우드 인스턴스나 VM 환경에서는 같은 IP에 다른 서버가 재생성될 수 있다. 이때 지문이 변경되어 SSH 연결이 실패하고, 자동화 스크립트가 중단된다. `/dev/null`로 설정하면 이 문제를 방지할 수 있다.

`host_key_checking=False`와 함께 사용하면 "Are you sure..." 프롬프트도 나타나지 않아 **완전한 비대화형 자동화**가 가능하다.

> **보안 고려사항**: 이 설정은 실습/개발 환경에서는 편리하지만, 프로덕션 환경에서는 보안 위험이 있다. 조직의 보안 정책에 따라 적절한 known_hosts 관리 방식을 사용해야 한다.

<br>

### control_path (주석 처리됨)

```ini
#control_path = ~/.ssh/ansible-%%r@%%h:%%p
```

SSH 연결 재사용을 위한 소켓 파일의 경로를 지정한다.

```bash
# 패턴 설명
%r: remote user
%h: hostname
%p: port

# 예: ~/.ssh/ansible-ubuntu@192.168.1.10:22
```

현재 설정에서는 **주석 처리**되어 있는데, 그 이유는 다음과 같다:
- Ansible은 기본적으로 자체 ControlPath를 관리함
- 명시적으로 설정하지 않으면 임시 디렉터리에 자동 생성
- 대부분의 경우 기본값으로 충분

<br>

## [defaults] 섹션

Ansible의 기본 동작을 설정한다.

### force_valid_group_names = ignore

```ini
# https://github.com/ansible/ansible/issues/56930 (to ignore group names with - and .)
force_valid_group_names = ignore
```

Ansible 2.8부터 그룹명에 `-`, `.` 사용 시 경고가 발생한다. 그러나 Kubernetes 리소스명에는 이 문자들이 자주 사용된다:

```ini
# Kubernetes에서 흔한 패턴
namespace: kube-system
deployment: coredns-12345

# Ansible 인벤토리에서 그룹명으로 사용 시
[kube-system]  # '-'가 포함되어 Ansible 2.8+에서 경고 발생
```

`ignore`로 설정하면 이 경고를 무시하고 Kubernetes 스타일 명명 규칙을 사용할 수 있다.

> **참고**: 이 설정은 Ansible 2.8의 `TRANSFORM_INVALID_GROUP_CHARS` 규칙과 관련이 있다. Kubernetes 생태계에서는 `kube-system`, `coredns-12345` 같이 하이픈을 포함한 명명 규칙이 표준이므로, Kubespray는 이 경고를 무시하도록 설정한다. 상세 내용은 [아래 참고 섹션](#참고-transform_invalid_group_chars-이슈)을 확인하자.

<br>

### host_key_checking = False

```ini
host_key_checking=False
```

새 서버 접속 시 호스트 키 확인 프롬프트를 비활성화한다.

```bash
# host_key_checking=True (기본값)
ssh new-server
# → "Are you sure you want to continue connecting (yes/no)?" 
# → 사용자 입력 대기

# host_key_checking=False
ssh new-server
# → 자동으로 yes 처리
# → 바로 접속
```

자동화 환경에서는 사람의 개입 없이 실행되어야 하므로 `False`로 설정한다. 앞서 설명한 `UserKnownHostsFile=/dev/null`과 함께 사용되어 완전한 비대화형 SSH 연결을 가능하게 한다.

<br>

### Fact 캐싱 설정

```ini
gathering = smart
fact_caching = jsonfile
fact_caching_connection = /tmp
fact_caching_timeout = 86400
```

| 설정 | 값 | 설명 |
|------|------|------|
| `gathering` | `smart` | Fact 수집 최적화. 캐시가 있으면 재수집하지 않음 |
| `fact_caching` | `jsonfile` | 캐시를 JSON 파일로 저장 |
| `fact_caching_connection` | `/tmp` | 캐시 파일 저장 경로 |
| `fact_caching_timeout` | `86400` | 캐시 유효 시간 (24시간 = 86400초) |

**Fact**란, Ansible이 대상 호스트에서 수집하는 시스템 정보(OS 종류, IP 주소, 메모리 등)다. 자세한 내용은 [Ansible 시리즈 - 3. Ad-hoc 명령어]({% post_url 2026-01-12-Kubernetes-Ansible-04 %})의 `setup` 모듈 부분을 참고하자.

`gathering = smart`로 설정하면 Fact가 캐시되어 있을 때 재수집하지 않아 **실행 시간이 단축**된다. Kubespray처럼 동일한 호스트에 여러 번 연결하는 경우 효과적이다.

<br>

### timeout = 300

```ini
timeout = 300
```

SSH 연결 타임아웃을 5분(300초)으로 설정한다. 네트워크 지연이 있거나 대상 호스트가 느린 경우에도 연결을 기다린다.

<br>

### 출력 관련 설정

```ini
stdout_callback = default
display_skipped_hosts = no
```

| 설정 | 값 | 설명 |
|------|------|------|
| `stdout_callback` | `default` | 표준 Ansible 출력 형식. `yaml`, `json`, `minimal` 등 선택 가능 |
| `display_skipped_hosts` | `no` | 스킵된 호스트를 출력하지 않음. 로그가 간결해짐 |

```bash
# display_skipped_hosts=yes
TASK [Install on Ubuntu only] ****
ok: [ubuntu-node]
skipping: [centos-node]
skipping: [debian-node]

# display_skipped_hosts=no
TASK [Install on Ubuntu only] ****
ok: [ubuntu-node]
```

수백 대의 서버를 관리할 때 스킵된 호스트를 모두 출력하면 로그가 매우 길어진다. `no`로 설정하면 실제로 작업이 수행된 호스트만 표시되어 가독성이 향상된다.

<br>

### library = ./library

```ini
library = ./library
```

커스텀 Ansible 모듈을 저장하는 경로를 지정한다. Kubespray는 표준 Ansible 모듈로 처리하기 어려운 Kubernetes 관련 작업을 위해 자체 모듈을 제공한다.

```bash
kubespray/
├── library/           # 커스텀 모듈 디렉토리
│   └── kube.py        # Kubernetes 리소스 관리 모듈
└── playbooks/
```

`kube.py` 모듈은 kubectl을 래핑하여 Kubernetes 리소스를 Ansible 태스크로 관리할 수 있게 해준다.

> **참고: kube.py 모듈**
>
> `kube.py`는 Kubernetes 리소스의 생성, 수정, 삭제를 Ansible 태스크로 수행할 수 있게 해주는 커스텀 모듈이다. `state` 파라미터로 리소스 상태를 선언적으로 관리한다(`present`, `absent`, `latest` 등).

<details markdown="1">
<summary>kube.py 전문 (클릭하여 펼치기)</summary>

```python
#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = """
---
module: kube
short_description: Manage Kubernetes Cluster
description:
  - Create, replace, remove, and stop resources within a Kubernetes Cluster
version_added: "2.0"
options:
  name:
    required: false
    default: null
    description:
      - The name associated with resource
  filename:
    required: false
    default: null
    description:
      - The path and filename of the resource(s) definition file(s).
      - To operate on several files this can accept a comma separated list of files or a list of files.
    aliases: [ 'files', 'file', 'filenames' ]
  kubectl:
    required: false
    default: null
    description:
      - The path to the kubectl bin
  namespace:
    required: false
    default: null
    description:
      - The namespace associated with the resource(s)
  resource:
    required: false
    default: null
    description:
      - The resource to perform an action on. pods (po), replicationControllers (rc), services (svc)
  label:
    required: false
    default: null
    description:
      - The labels used to filter specific resources.
  server:
    required: false
    default: null
    description:
      - The url for the API server that commands are executed against.
  kubeconfig:
    required: false
    default: null
    description:
      - The path to the kubeconfig.
  force:
    required: false
    default: false
    description:
      - A flag to indicate to force delete, replace, or stop.
  wait:
    required: false
    default: false
    description:
      - A flag to indicate to wait for resources to be created before continuing to the next step
  all:
    required: false
    default: false
    description:
      - A flag to indicate delete all, stop all, or all namespaces when checking exists.
  log_level:
    required: false
    default: 0
    description:
      - Indicates the level of verbosity of logging by kubectl.
  state:
    required: false
    choices: ['present', 'absent', 'latest', 'reloaded', 'stopped']
    default: present
    description:
      - present handles checking existence or creating if definition file provided,
        absent handles deleting resource(s) based on other options,
        latest handles creating or updating based on existence,
        reloaded handles updating resource(s) definition using definition file,
        stopped handles stopping resource(s) based on other options.
  recursive:
    required: false
    default: false
    description:
      - Process the directory used in -f, --filename recursively.
        Useful when you want to manage related manifests organized
        within the same directory.
requirements:
  - kubectl
author: "Kenny Jones (@kenjones-cisco)"
"""

EXAMPLES = """
- name: test nginx is present
  kube: name=nginx resource=rc state=present

- name: test nginx is stopped
  kube: name=nginx resource=rc state=stopped

- name: test nginx is absent
  kube: name=nginx resource=rc state=absent

- name: test nginx is present
  kube: filename=/tmp/nginx.yml

- name: test nginx and postgresql are present
  kube: files=/tmp/nginx.yml,/tmp/postgresql.yml

- name: test nginx and postgresql are present
  kube:
    files:
      - /tmp/nginx.yml
      - /tmp/postgresql.yml
"""

class KubeManager(object):

    def __init__(self, module):

        self.module = module

        self.kubectl = module.params.get('kubectl')
        if self.kubectl is None:
            self.kubectl =  module.get_bin_path('kubectl', True)
        self.base_cmd = [self.kubectl]

        if module.params.get('server'):
            self.base_cmd.append('--server=' + module.params.get('server'))

        if module.params.get('kubeconfig'):
            self.base_cmd.append('--kubeconfig=' + module.params.get('kubeconfig'))

        if module.params.get('log_level'):
            self.base_cmd.append('--v=' + str(module.params.get('log_level')))

        if module.params.get('namespace'):
            self.base_cmd.append('--namespace=' + module.params.get('namespace'))

        self.all = module.params.get('all')
        self.force = module.params.get('force')
        self.wait = module.params.get('wait')
        self.name = module.params.get('name')
        self.filename = [f.strip() for f in module.params.get('filename') or []]
        self.resource = module.params.get('resource')
        self.label = module.params.get('label')
        self.recursive = module.params.get('recursive')

    def _execute(self, cmd):
        args = self.base_cmd + cmd
        try:
            rc, out, err = self.module.run_command(args)
            if rc != 0:
                self.module.fail_json(
                    msg='error running kubectl (%s) command (rc=%d), out=\'%s\', err=\'%s\'' % (' '.join(args), rc, out, err))
        except Exception as exc:
            self.module.fail_json(
                msg='error running kubectl (%s) command: %s' % (' '.join(args), str(exc)))
        return out.splitlines()

    def _execute_nofail(self, cmd):
        args = self.base_cmd + cmd
        rc, out, err = self.module.run_command(args)
        if rc != 0:
            return None
        return out.splitlines()

    def create(self, check=True, force=True):
        if check and self.exists():
            return []

        cmd = ['apply']

        if force:
            cmd.append('--force')

        if self.wait:
            cmd.append('--wait')

        if self.recursive:
            cmd.append('--recursive={}'.format(self.recursive))

        if not self.filename:
            self.module.fail_json(msg='filename required to create')

        cmd.append('--filename=' + ','.join(self.filename))

        return self._execute(cmd)

    def replace(self, force=True):

        cmd = ['apply']

        if force:
            cmd.append('--force')

        if self.wait:
            cmd.append('--wait')

        if self.recursive:
            cmd.append('--recursive={}'.format(self.recursive))

        if not self.filename:
            self.module.fail_json(msg='filename required to reload')

        cmd.append('--filename=' + ','.join(self.filename))

        return self._execute(cmd)

    def delete(self):

        if not self.force and not self.exists():
            return []

        cmd = ['delete']

        if self.filename:
            cmd.append('--filename=' + ','.join(self.filename))
            if self.recursive:
                cmd.append('--recursive={}'.format(self.recursive))
        else:
            if not self.resource:
                self.module.fail_json(msg='resource required to delete without filename')

            cmd.append(self.resource)

            if self.name:
                cmd.append(self.name)

            if self.label:
                cmd.append('--selector=' + self.label)

            if self.all:
                cmd.append('--all')

            if self.force:
                cmd.append('--ignore-not-found')

            if self.recursive:
                cmd.append('--recursive={}'.format(self.recursive))

        return self._execute(cmd)

    def exists(self):
        cmd = ['get']

        if self.filename:
            cmd.append('--filename=' + ','.join(self.filename))
            if self.recursive:
                cmd.append('--recursive={}'.format(self.recursive))
        else:
            if not self.resource:
                self.module.fail_json(msg='resource required without filename')

            cmd.append(self.resource)

            if self.name:
                cmd.append(self.name)

            if self.label:
                cmd.append('--selector=' + self.label)

            if self.all:
                cmd.append('--all-namespaces')

        cmd.append('--no-headers')

        result = self._execute_nofail(cmd)
        if not result:
            return False
        return True

    # TODO: This is currently unused, perhaps convert to 'scale' with a replicas param?
    def stop(self):

        if not self.force and not self.exists():
            return []

        cmd = ['stop']

        if self.filename:
            cmd.append('--filename=' + ','.join(self.filename))
            if self.recursive:
                cmd.append('--recursive={}'.format(self.recursive))
        else:
            if not self.resource:
                self.module.fail_json(msg='resource required to stop without filename')

            cmd.append(self.resource)

            if self.name:
                cmd.append(self.name)

            if self.label:
                cmd.append('--selector=' + self.label)

            if self.all:
                cmd.append('--all')

            if self.force:
                cmd.append('--ignore-not-found')

        return self._execute(cmd)

def main():

    module = AnsibleModule(
        argument_spec=dict(
            name=dict(),
            filename=dict(type='list', aliases=['files', 'file', 'filenames']),
            namespace=dict(),
            resource=dict(),
            label=dict(),
            server=dict(),
            kubeconfig=dict(),
            kubectl=dict(),
            force=dict(default=False, type='bool'),
            wait=dict(default=False, type='bool'),
            all=dict(default=False, type='bool'),
            log_level=dict(default=0, type='int'),
            state=dict(default='present', choices=['present', 'absent', 'latest', 'reloaded', 'stopped', 'exists']),
            recursive=dict(default=False, type='bool'),
            ),
            mutually_exclusive=[['filename', 'list']]
        )

    changed = False

    manager = KubeManager(module)
    state = module.params.get('state')
    if state == 'present':
        result = manager.create(check=False)

    elif state == 'absent':
        result = manager.delete()

    elif state == 'reloaded':
        result = manager.replace()

    elif state == 'stopped':
        result = manager.stop()

    elif state == 'latest':
        result = manager.replace()

    elif state == 'exists':
        result = manager.exists()
        module.exit_json(changed=changed,
                     msg='%s' % result)

    else:
        module.fail_json(msg='Unrecognized state %s.' % state)

    module.exit_json(changed=changed,
                     msg='success: %s' % (' '.join(result))
                     )

from ansible.module_utils.basic import *  # noqa
if __name__ == '__main__':
    main()
```

</details>

<br>

### callbacks_enabled = profile_tasks

```ini
callbacks_enabled = profile_tasks
```

각 태스크의 실행 시간을 프로파일링한다. 플레이북 실행 완료 후 태스크별 소요 시간이 표시된다:

```
PLAY RECAP ****
Tuesday 28 January 2026  15:23:45 +0900 (0:00:02.456)

===============================================================================
Install Docker --------------------------------- 45.23s
Configure kubelet ------------------------------ 12.67s
Download images -------------------------------- 89.45s
```

어떤 단계에서 병목이 발생하는지 파악할 수 있어 **성능 튜닝에 유용**하다.

> 참고: **왜 "callback"인가?**
>
> Ansible은 태스크 실행 전후에 콜백 함수를 호출하는 메커니즘을 가지고 있다. `profile_tasks`는 `on_task_complete` 콜백에서 실행 시간을 수집하고 표시하는 플러그인이다.

<br>

### roles_path

```ini
roles_path = roles:$VIRTUAL_ENV/usr/local/share/kubespray/roles:$VIRTUAL_ENV/usr/local/share/ansible/roles:/usr/share/kubespray/roles
```

Ansible Role을 검색할 디렉터리 목록이다. `:`로 구분되며, 앞에 있는 경로가 우선순위가 높다.

| 순서 | 경로 | 설명 |
|------|------|------|
| 1 | `./roles` | 현재 디렉터리의 roles (Kubespray 기본) |
| 2 | `$VIRTUAL_ENV/usr/local/share/kubespray/roles` | Python 가상환경 내 Kubespray 롤 |
| 3 | `$VIRTUAL_ENV/usr/local/share/ansible/roles` | Python 가상환경 내 Ansible 롤 |
| 4 | `/usr/share/kubespray/roles` | 시스템 전역 Kubespray 롤 |

`$VIRTUAL_ENV`는 Python 가상환경 활성화 시 자동 설정되는 환경변수다. 가상환경을 사용하지 않으면 빈 문자열이 되어 해당 경로는 무시된다.

<br>

### 기타 설정

```ini
deprecation_warnings=False
inventory_ignore_extensions = ~, .orig, .bak, .ini, .cfg, .retry, .pyc, .pyo, .creds, .gpg
```

| 설정 | 값 | 설명 |
|------|------|------|
| `deprecation_warnings` | `False` | 사용 중단 예정 기능 경고 비활성화 |
| `inventory_ignore_extensions` | 여러 확장자 | 인벤토리 스캔 시 무시할 파일 확장자. 백업 파일, 임시 파일, 인증 정보 파일 등을 제외 |

<br>

## [inventory] 섹션

인벤토리 스캔 관련 설정이다.

```ini
[inventory]
ignore_patterns = artifacts, credentials
```

인벤토리 디렉터리 스캔 시 특정 패턴의 디렉터리/파일을 제외한다:
- `artifacts`: 배포 결과물 디렉터리
- `credentials`: 인증 정보 디렉터리

이 디렉터리들은 인벤토리 파일이 아니므로 스캔 대상에서 제외한다.

<br>

# ansible.cfg 커스터마이징

Kubespray의 `ansible.cfg`는 일반적인 환경을 위한 권장 설정이지만, **환경에 맞게 수정할 수 있다**.

## 설정 우선순위 활용

Ansible의 설정 우선순위를 활용하여 환경별 설정을 관리할 수 있다:

```bash
# 환경별 설정 파일
kubespray/
├── ansible.cfg           # 기본 설정
├── ansible.cfg.dev       # 개발 환경용
└── ansible.cfg.prod      # 프로덕션용

# 환경변수로 설정 파일 지정
ANSIBLE_CONFIG=ansible.cfg.dev ansible-playbook cluster.yml
ANSIBLE_CONFIG=ansible.cfg.prod ansible-playbook cluster.yml
```

<br>

## 자주 수정하는 항목

### SSH 연결 설정

```ini
[ssh_connection]
# 회사 방화벽 정책상 SSH 세션 유지 시간이 짧은 경우
ControlPersist=10m  # 30m → 10m으로 조정

# 네트워크가 안정적인 환경에서는 재시도 횟수 감소
ConnectionAttempts=10  # 100 → 10

# 보안 정책상 known_hosts 관리가 필요한 경우
ssh_args = -o ControlMaster=auto -o ControlPersist=30m
# UserKnownHostsFile=/dev/null 제거
```

### 출력 형식 변경

```ini
[defaults]
# CI/CD 파이프라인에서 JSON 파싱이 필요한 경우
stdout_callback = json

# 더 깔끔한 YAML 출력을 원하는 경우
stdout_callback = yaml

# 디버깅을 위해 스킵된 호스트도 확인하고 싶은 경우
display_skipped_hosts = yes
```

### 성능 튜닝

```ini
[defaults]
# 대규모 클러스터에서 Fact 수집 시간 단축 (필요할 때만 수집)
gathering = explicit

# Fact 수집 완전히 비활성화 (Fact를 사용하지 않는 경우)
gathering = none

# 개발 환경에서는 캐시 유효 시간을 짧게
fact_caching_timeout = 3600  # 24시간 → 1시간

# 동시에 처리할 호스트 수 증가 (네트워크 대역폭이 충분한 경우)
forks = 20  # 기본값 5
```

### 보안 강화

```ini
[defaults]
# known_hosts 검증 활성화
host_key_checking = True

[ssh_connection]
# 조직 표준 known_hosts 사용
ssh_args = -o ControlMaster=auto -o ControlPersist=30m -o UserKnownHostsFile=/etc/ansible/known_hosts
```

<br>

## 커스터마이징 팁

### 원본 보존

```bash
# Kubespray 원본 설정 백업
cp ansible.cfg ansible.cfg.original

# 수정 작업
vim ansible.cfg
```

### 변경 이유 주석으로 명시

```ini
[defaults]
# 우리 회사 프록시 환경에서는 Fact 수집이 느려서 비활성화
gathering = none

# 보안팀 요구사항: known_hosts 검증 필수
[ssh_connection]
ssh_args = -o ControlMaster=auto -o ControlPersist=30m
# UserKnownHostsFile=/dev/null 제거됨 - 보안 정책 준수
```

### 버전 관리

```bash
# 수정한 설정을 Git으로 추적
git add ansible.cfg
git commit -m "Adjust SSH timeout for our network environment"
```

<br>

# 결과

Kubespray의 `ansible.cfg`는 대규모 Kubernetes 클러스터 배포를 위해 최적화된 설정을 제공한다:

- **SSH 파이프라이닝과 연결 재사용**으로 성능 향상
- **Fact 캐싱**으로 반복 실행 시간 단축
- **profile_tasks 콜백**으로 병목 구간 파악
- **host_key_checking 비활성화**로 자동화 환경 지원

이 설정들은 대부분의 환경에서 잘 동작하지만, 조직의 네트워크 환경, 보안 정책, 성능 요구사항에 따라 적절히 수정할 수 있다.

> 다음 글에서는 `cluster.yml` 플레이북의 전체 실행 흐름을 분석한다.

<br>

# 참고 자료

- [Ansible Configuration Settings](https://docs.ansible.com/ansible/latest/reference_appendices/config.html)
- [Kubespray GitHub - ansible.cfg](https://github.com/kubernetes-sigs/kubespray/blob/master/ansible.cfg)
- [Ansible 시리즈 - 3. Ad-hoc 명령어]({% post_url 2026-01-12-Kubernetes-Ansible-04 %})
- [Kubespray 이전 글: Kubernetes The Kubespray Way]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %})
- [GitHub Issue #56930 - force_valid_group_names](https://github.com/ansible/ansible/issues/56930)

<br>
<br>

# 참고: TRANSFORM_INVALID_GROUP_CHARS 이슈

[GitHub Issue #89](https://github.com/ansible/ansible-documentation/issues/89)에서 제기된 문제다.

## 배경

Ansible 2.8.0에서 `TRANSFORM_INVALID_GROUP_CHARS` 설정이 추가되었다. 이 규칙은 그룹 이름과 호스트 이름에서 Python 변수명 규칙에 맞지 않는 문자(하이픈, 점 등)를 언더스코어로 변환한다:

```ini
# inventory
[k8s-masters]  # 그룹 이름도 변환 대상
node-1.example.com  # 호스트 이름도 변환 대상
node-2.example.com

# 내부적으로 변환됨
groups['k8s_masters'] = ['node_1_example_com', 'node_2_example_com']
```

## 제기된 문제점

- **문서 부족**: 소스 코드를 직접 읽지 않고서는 어떤 문자가 유효하지 않은지 알 수 없음
- **경고 메시지 불충분**: `-vvvv` 옵션을 사용해야만 현재 사용 중인 잘못된 문자 확인 가능
- **Python 변수 규칙**: 그룹 이름이 유효한 Python 변수 이름이어야 한다는 점이 문서화되지 않음
- **마이그레이션 가이드 누락**: Ansible 2.8 포팅 가이드에 관련 내용 없음

## 커뮤니티 논의

### 하이픈(-) 문제

EC2 instance id나 리전 이름처럼 하이픈을 포함하는 경우가 많은데, 이것이 그룹 이름에서 금지됨

변경 전 (Ansible 2.8 이전):

```yaml
# inventory
[varnish]
varnish-eu-central-1c-001

# playbook - 정상 작동
- hosts: all
  tasks:
    - debug:
        msg: "I'm in varnish group"
      when: ansible_hostname in groups['varnish']
```

변경 후 (Ansible 2.8+, TRANSFORM_INVALID_GROUP_CHARS 적용):

```ini
# 내부적으로 변환됨
groups['varnish'] = ['varnish_eu_central_1c_001']  # 하이픈이 언더스코어로 변환
```

```yaml
# ansible_hostname은 실제 호스트명(변환 안 됨)이므로 매칭 실패
# inventory_hostname을 사용해야 함
when: inventory_hostname in groups['varnish']
```

| 변수 | 설명 |
|------|------|
| `inventory_hostname` | 인벤토리에서 정의한 변환된 이름 |
| `ansible_hostname` | 실제 호스트의 hostname (fact에서 수집, 변환되지 않음) |

### 설계 논쟁

그룹 이름은 변수 이름이 아니라 변수의 **내용**이므로, 하이픈이 금지되어야 할 실질적 이유가 없다는 주장도 있었다.

## 결과

현재 이 이슈는 [Ansible 공식 문서](https://docs.ansible.com/ansible/latest/reference_appendices/config.html#transform-invalid-group-chars)로 이동되어 종료되었다.

## Kubespray에서의 적용

Kubernetes 환경에서는 하이픈을 매우 많이 사용한다:

```ini
# Kubespray 인벤토리 예시
[k8s-cluster:children]
kube-node
kube-master

[kube-node]
node-1
node-2
worker-01.k8s.example.com

[kube-master]
master-1.k8s.example.com
master-2.k8s.example.com
```

따라서, **Kubespray는 `ignore` 설정을 사용하여** 다음 환경에서의 호환성 문제를 회피한다:

1. **Kubernetes 네이밍 컨벤션**: 노드 이름, 클러스터 이름 등에 하이픈 사용이 표준
2. **AWS EC2 인스턴스**: `i-1234567890abcdef0` 형태의 인스턴스 ID
3. **리전/가용영역**: `eu-central-1a`, `us-west-2` 등의 명명 규칙
4. **기존 인벤토리**: 수천 개 배포에서 이미 사용 중인 하이픈 포함 인벤토리

<br>

