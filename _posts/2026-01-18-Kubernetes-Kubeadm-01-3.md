---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.3. CRI(containerd) 및 kubeadm 구성 요소 설치"
excerpt: "kubeadm 클러스터 구성을 위해 CRI(containerd)를 설치하고, kubeadm/kubelet/kubectl을 설치해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **CRI(containerd) 및 kubeadm 구성 요소 설치**다.

- **CRI 설치**: containerd v2.1.5 설치 및 SystemdCgroup 활성화
- **kubeadm 설치**: kubeadm, kubelet, kubectl v1.32.11 설치
- **설치 확인**: crictl 설정, kubelet 서비스 상태, CNI 바이너리 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %})에서 실습 환경을 확인하고 kubeadm 클러스터 구성을 위한 사전 설정을 완료했다. 이번 글에서는 컨테이너 런타임(containerd)과 Kubernetes 핵심 도구(kubeadm, kubelet, kubectl)를 설치한다. 이 글에서 생성되는 파일의 전체 그림은 [실습 구성도의 Stage 1~2]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-0 %}#stage-1-containerd-설치)를 참고한다.

이 글에서 다루는 모든 설치 작업은 **컨트롤 플레인 노드와 워커 노드 모두**에 적용해야 한다. 실습에서는 k8s-ctr, k8s-w1, k8s-w2 세 노드에 동일하게 진행한다.

<br>

# CRI 설치: containerd

Kubernetes는 컨테이너 런타임으로 CRI(Container Runtime Interface)를 준수하는 런타임을 사용한다. 이 실습에서는 containerd v2.1.5를 설치한다.

> containerd는 CNCF ['graduated'](https://landscape.cncf.io/?selected=containerd) 프로젝트로, 업계 표준 컨테이너 런타임이다. 단순성, 견고성, 이식성에 중점을 두고 설계되었다.

## containerd와 Kubernetes 버전 호환성

이 실습에서는 Kubernetes 1.32를 설치하고, 이후 1.33, 1.34로 업그레이드할 예정이다. containerd도 호환되는 버전을 사용해야 한다.([containerd Kubernetes support](https://containerd.io/releases/#kubernetes-support))

| Kubernetes Version | containerd Version | CRI Version |
| --- | --- | --- |
| **1.32** | **2.1.0+**, 2.0.1+, 1.7.24+, 1.6.36+ | v1 |
| **1.33** | **2.1.0+**, 2.0.4+, 1.7.24+, 1.6.36+ | v1 |
| **1.34** | **2.1.3+**, 2.0.6+, 1.7.28+, 1.6.36+ | v1 |
| 1.35 | 2.2.0+, 2.1.5+, 1.7.28+ | v1 |


containerd **2.1.5**를 설치하면 Kubernetes 1.32 ~ 1.35까지 모두 호환된다.

### config.toml 버전 주의

containerd는 `/etc/containerd/config.toml` 설정 파일을 사용하는데, **containerd 버전에 따라 config.toml 규격이 다르다**.

| containerd Version | config.toml Version |
| --- | --- |
| 1.x (1.7 이하) | version 2 |
| 2.x | **version 3** |

containerd 1.7에서 2.x로 업그레이드할 때 config.toml 규격이 달라지므로 주의가 필요하다. 이 실습에서는 처음부터 **containerd 2.x**를 설치하여 이러한 복잡성을 피한다.

<br>

## Docker 저장소 추가

containerd는 Docker 저장소에서 제공하는 패키지를 사용한다.

```bash
# 현재 저장소 확인
dnf repolist
# repo id          repo name
# appstream        Rocky Linux 10 - AppStream
# baseos           Rocky Linux 10 - BaseOS
# extras           Rocky Linux 10 - Extras

tree /etc/yum.repos.d/
# /etc/yum.repos.d
# ├── rocky-addons.repo
# ├── rocky-devel.repo
# ├── rocky-extras.repo
# └── rocky.repo
```

```bash
# Docker 저장소 추가
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
# Adding repo from: https://download.docker.com/linux/centos/docker-ce.repo

dnf repolist
# repo id              repo name
# appstream            Rocky Linux 10 - AppStream
# baseos               Rocky Linux 10 - BaseOS
# docker-ce-stable     Docker CE Stable - aarch64    <- 추가됨
# extras               Rocky Linux 10 - 

tree /etc/yum.repos.d/
# /etc/yum.repos.d/
# ├── docker-ce.repo    <- 추가됨
# ├── rocky-addons.repo
# ├── rocky-devel.repo
# ├── rocky-extras.repo
# └── rocky.repo

1 directory, 5 files

# 메타데이터 캐시 생성
dnf makecache
# Metadata cache created.
```

```bash
# 설치 가능한 containerd.io 버전 확인
dnf list --showduplicates containerd.io
# Available Packages
# containerd.io.aarch64    1.7.23-3.1.el10    docker-ce-stable
# containerd.io.aarch64    1.7.24-3.1.el10    docker-ce-stable
# ...
# containerd.io.aarch64    1.7.29-1.el10      docker-ce-stable
# containerd.io.aarch64    2.1.5-1.el10       docker-ce-stable   <- 설치할 버전
# containerd.io.aarch64    2.2.0-2.el10       docker-ce-stable
# containerd.io.aarch64    2.2.1-1.el10       docker-ce-stable
```

1.7.x와 2.x 버전이 모두 제공되는 것을 확인할 수 있다. 앞서 설명한 대로 **2.1.5**를 설치한다.

<br>

## containerd 설치

```bash
# containerd 2.1.5 설치
dnf install -y containerd.io-2.1.5-1.el10
# Installed: containerd.io-2.1.5-1.el10.aarch64
```

설치가 완료되면 함께 설치된 구성 요소들을 확인한다.

```bash
which runc && runc --version
# /usr/bin/runc
# runc version 1.3.3
# commit: v1.3.3-0-gd842d771
# spec: 1.2.1
# go: go1.24.9
# libseccomp: 2.5.3

which containerd && containerd --version
# /usr/bin/containerd
# containerd containerd.io v2.1.5 fcd43222d6b07379a4be9786bda52438f0dd16a1

which containerd-shim-runc-v2 && containerd-shim-runc-v2 -v
# /usr/bin/containerd-shim-runc-v2
# containerd-shim-runc-v2:
#   Version:  v2.1.5
#   Revision: fcd43222d6b07379a4be9786bda52438f0dd16a1
#   Go version: go1.24.9

which ctr && ctr --version
# /usr/bin/ctr
# ctr containerd.io v2.1.5
```

기본 설정 파일과 systemd 서비스 파일을 확인한다.

```bash
cat /etc/containerd/config.toml
# ...
# disabled_plugins = ["cri"]  # 기본 설정에서는 CRI 플러그인이 비활성화됨!
# ...
```

기본 설정 파일에서 `disabled_plugins = ["cri"]`로 CRI 플러그인이 비활성화되어 있다. Kubernetes에서 사용하려면 이 설정을 변경하고 systemd cgroup 드라이버를 활성화해야 한다. 다음 단계에서 설정 파일을 새로 생성한다.


<details markdown="1">
<summary>기본 설정 config.toml 전문</summary>

```toml
#   Copyright 2018-2022 Docker Inc.

#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at

#       http://www.apache.org/licenses/LICENSE-2.0

#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

disabled_plugins = ["cri"]

#root = "/var/lib/containerd"
#state = "/run/containerd"
#subreaper = true
#oom_score = 0

#[grpc]
#  address = "/run/containerd/containerd.sock"
#  uid = 0
#  gid = 0

#[debug]
#  address = "/run/containerd/debug.sock"
#  uid = 0
#  gid = 0
#  level = "info"
```

</details>

```bash
# systemd 서비스 파일 위치
tree /usr/lib/systemd/system | grep containerd
# ├── containerd.service

# 서비스 파일 내용 확인
cat /usr/lib/systemd/system/containerd.service
# [Unit]
# Description=containerd container runtime
# Documentation=https://containerd.io
# After=network.target dbus.service
#
# [Service]
# ExecStartPre=-/sbin/modprobe overlay
# ExecStart=/usr/bin/containerd
# Type=notify
# Delegate=yes          # cgroup 관리 위임
# KillMode=process
# Restart=always
# RestartSec=5
# LimitNPROC=infinity
# LimitCORE=infinity
# TasksMax=infinity
# OOMScoreAdjust=-999   # OOM Killer 대상에서 제외
#
# [Install]
# WantedBy=multi-user.target
```

> **주의**: 기본 설정 파일에서 `disabled_plugins = ["cri"]`로 CRI 플러그인이 비활성화되어 있다. Kubernetes에서 사용하려면 이 설정을 변경하고 systemd cgroup 드라이버를 활성화해야 한다. 다음 단계에서 설정 파일을 새로 생성한다.

<br>

## containerd 설정

### 기본 설정 생성 및 SystemdCgroup 활성화

**매우 중요한 단계**다. containerd가 systemd cgroup 드라이버를 사용하도록 설정해야 한다.

```bash
containerd config default | tee /etc/containerd/config.toml
# version = 3
# root = '/var/lib/containerd'
# state = '/run/containerd'
# ...
# disabled_plugins = []   # CRI 플러그인 활성화됨!
# ...
```

<details markdown="1">
<summary>containerd config default 전체 출력</summary>

```toml
version = 3
root = '/var/lib/containerd'
state = '/run/containerd'
temp = ''
disabled_plugins = []
required_plugins = []
oom_score = 0
imports = []

[grpc]
  address = '/run/containerd/containerd.sock'
  tcp_address = ''
  tcp_tls_ca = ''
  tcp_tls_cert = ''
  tcp_tls_key = ''
  uid = 0
  gid = 0
  max_recv_message_size = 16777216
  max_send_message_size = 16777216

[ttrpc]
  address = ''
  uid = 0
  gid = 0

[debug]
  address = ''
  uid = 0
  gid = 0
  level = ''
  format = ''

[metrics]
  address = ''
  grpc_histogram = false

[plugins]
  [plugins.'io.containerd.cri.v1.images']
    snapshotter = 'overlayfs'
    disable_snapshot_annotations = true
    discard_unpacked_layers = false
    max_concurrent_downloads = 3
    concurrent_layer_fetch_buffer = 0
    image_pull_progress_timeout = '5m0s'
    image_pull_with_sync_fs = false
    stats_collect_period = 10
    use_local_image_pull = false

    [plugins.'io.containerd.cri.v1.images'.pinned_images]
      sandbox = 'registry.k8s.io/pause:3.10'

    [plugins.'io.containerd.cri.v1.images'.registry]
      config_path = ''

    [plugins.'io.containerd.cri.v1.images'.image_decryption]
      key_model = 'node'

  [plugins.'io.containerd.cri.v1.runtime']
    enable_selinux = false
    selinux_category_range = 1024
    max_container_log_line_size = 16384
    disable_apparmor = false
    restrict_oom_score_adj = false
    disable_proc_mount = false
    unset_seccomp_profile = ''
    tolerate_missing_hugetlb_controller = true
    disable_hugetlb_controller = true
    device_ownership_from_security_context = false
    ignore_image_defined_volumes = false
    netns_mounts_under_state_dir = false
    enable_unprivileged_ports = true
    enable_unprivileged_icmp = true
    enable_cdi = true
    cdi_spec_dirs = ['/etc/cdi', '/var/run/cdi']
    drain_exec_sync_io_timeout = '0s'
    ignore_deprecation_warnings = []

    [plugins.'io.containerd.cri.v1.runtime'.containerd]
      default_runtime_name = 'runc'
      ignore_blockio_not_enabled_errors = false
      ignore_rdt_not_enabled_errors = false

      [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes]
        [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc]
          runtime_type = 'io.containerd.runc.v2'
          runtime_path = ''
          pod_annotations = []
          container_annotations = []
          privileged_without_host_devices = false
          privileged_without_host_devices_all_devices_allowed = false
          cgroup_writable = false
          base_runtime_spec = ''
          cni_conf_dir = ''
          cni_max_conf_num = 0
          snapshotter = ''
          sandboxer = 'podsandbox'
          io_type = ''

          [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runc.options]
            BinaryName = ''
            CriuImagePath = ''
            CriuWorkPath = ''
            IoGid = 0
            IoUid = 0
            NoNewKeyring = false
            Root = ''
            ShimCgroup = ''
            SystemdCgroup = false

    [plugins.'io.containerd.cri.v1.runtime'.cni]
      bin_dir = ''
      bin_dirs = ['/opt/cni/bin']
      conf_dir = '/etc/cni/net.d'
      max_conf_num = 1
      setup_serially = false
      conf_template = ''
      ip_pref = ''
      use_internal_loopback = false

  [plugins.'io.containerd.differ.v1.erofs']
    mkfs_options = []

  [plugins.'io.containerd.gc.v1.scheduler']
    pause_threshold = 0.02
    deletion_threshold = 0
    mutation_threshold = 100
    schedule_delay = '0s'
    startup_delay = '100ms'

  [plugins.'io.containerd.grpc.v1.cri']
    disable_tcp_service = true
    stream_server_address = '127.0.0.1'
    stream_server_port = '0'
    stream_idle_timeout = '4h0m0s'
    enable_tls_streaming = false

    [plugins.'io.containerd.grpc.v1.cri'.x509_key_pair_streaming]
      tls_cert_file = ''
      tls_key_file = ''

  [plugins.'io.containerd.image-verifier.v1.bindir']
    bin_dir = '/opt/containerd/image-verifier/bin'
    max_verifiers = 10
    per_verifier_timeout = '10s'

  [plugins.'io.containerd.internal.v1.opt']
    path = '/opt/containerd'

  [plugins.'io.containerd.internal.v1.tracing']

  [plugins.'io.containerd.metadata.v1.bolt']
    content_sharing_policy = 'shared'
    no_sync = false

  [plugins.'io.containerd.monitor.container.v1.restart']
    interval = '10s'

  [plugins.'io.containerd.monitor.task.v1.cgroups']
    no_prometheus = false

  [plugins.'io.containerd.nri.v1.nri']
    disable = false
    socket_path = '/var/run/nri/nri.sock'
    plugin_path = '/opt/nri/plugins'
    plugin_config_path = '/etc/nri/conf.d'
    plugin_registration_timeout = '5s'
    plugin_request_timeout = '2s'
    disable_connections = false

  [plugins.'io.containerd.runtime.v2.task']
    platforms = ['linux/arm64/v8']

  [plugins.'io.containerd.service.v1.diff-service']
    default = ['walking']
    sync_fs = false

  [plugins.'io.containerd.service.v1.tasks-service']
    blockio_config_file = ''
    rdt_config_file = ''

  [plugins.'io.containerd.shim.v1.manager']
    env = []

  [plugins.'io.containerd.snapshotter.v1.blockfile']
    root_path = ''
    scratch_file = ''
    fs_type = ''
    mount_options = []
    recreate_scratch = false

  [plugins.'io.containerd.snapshotter.v1.devmapper']
    root_path = ''
    pool_name = ''
    base_image_size = ''
    async_remove = false
    discard_blocks = false
    fs_type = ''
    fs_options = ''

  [plugins.'io.containerd.snapshotter.v1.erofs']
    root_path = ''
    ovl_mount_options = []
    enable_fsverity = false
    set_immutable = false

  [plugins.'io.containerd.snapshotter.v1.native']
    root_path = ''

  [plugins.'io.containerd.snapshotter.v1.overlayfs']
    root_path = ''
    upperdir_label = false
    sync_remove = false
    slow_chown = false
    mount_options = []

  [plugins.'io.containerd.snapshotter.v1.zfs']
    root_path = ''

  [plugins.'io.containerd.tracing.processor.v1.otlp']

  [plugins.'io.containerd.transfer.v1.local']
    max_concurrent_downloads = 3
    concurrent_layer_fetch_buffer = 0
    max_concurrent_uploaded_layers = 3
    check_platform_supported = false
    config_path = ''

[cgroup]
  path = ''

[timeouts]
  'io.containerd.timeout.bolt.open' = '0s'
  'io.containerd.timeout.cri.defercleanup' = '1m0s'
  'io.containerd.timeout.metrics.shimstats' = '2s'
  'io.containerd.timeout.shim.cleanup' = '5s'
  'io.containerd.timeout.shim.load' = '5s'
  'io.containerd.timeout.shim.shutdown' = '3s'
  'io.containerd.timeout.task.state' = '2s'

[stream_processors]
  [stream_processors.'io.containerd.ocicrypt.decoder.v1.tar']
    accepts = ['application/vnd.oci.image.layer.v1.tar+encrypted']
    returns = 'application/vnd.oci.image.layer.v1.tar'
    path = 'ctd-decoder'
    args = ['--decryption-keys-path', '/etc/containerd/ocicrypt/keys']
    env = ['OCICRYPT_KEYPROVIDER_CONFIG=/etc/containerd/ocicrypt/ocicrypt_keyprovider.conf']

  [stream_processors.'io.containerd.ocicrypt.decoder.v1.tar.gzip']
    accepts = ['application/vnd.oci.image.layer.v1.tar+gzip+encrypted']
    returns = 'application/vnd.oci.image.layer.v1.tar+gzip'
    path = 'ctd-decoder'
    args = ['--decryption-keys-path', '/etc/containerd/ocicrypt/keys']
    env = ['OCICRYPT_KEYPROVIDER_CONFIG=/etc/containerd/ocicrypt/ocicrypt_keyprovider.conf']
```

</details>

| 설정 | 값 | 의미 |
| --- | --- | --- |
| `disabled_plugins` | `[]` | CRI 플러그인 활성화 (패키지 기본값 `["cri"]`와 다름) |
| `version` | `3` | containerd 2.0 이상의 설정 포맷 |
| `sandbox` (pinned_images) | `registry.k8s.io/pause:3.10` | Pod sandbox 컨테이너 이미지 |
| `default_runtime_name` | `runc` | OCI 런타임으로 runc 사용 |
| `SystemdCgroup` | `false` | **이 값을 `true`로 변경해야 함** (아래에서 수정) |
| `conf_dir` (cni) | `/etc/cni/net.d` | CNI 설정 파일 경로 |
| `bin_dirs` (cni) | `['/opt/cni/bin']` | CNI 바이너리 경로 |

<br>

기본 설정에서 `disabled_plugins = []`로 CRI 플러그인이 활성화되어 있다. 하지만 **SystemdCgroup = false**가 기본값이므로 이를 활성화해야 한다. 이 설정이 없으면 kubelet과 containerd 간 cgroup 관리 충돌이 발생할 수 있다.

```bash
# SystemdCgroup 설정 확인 (기본값은 false)
cat /etc/containerd/config.toml | grep -i systemdcgroup
#             SystemdCgroup = false

# SystemdCgroup 활성화
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml

# 변경 확인
cat /etc/containerd/config.toml | grep -i systemdcgroup
#             SystemdCgroup = true
```

> 참고: **containerd 1.x vs 2.x 설정 차이**
>
> | containerd 버전 | config version | CRI 플러그인 경로 |
> | --- | --- | --- |
> | 1.x | version = 2 | `plugins."io.containerd.grpc.v1.cri"` |
> | **2.x** | **version = 3** | `plugins.'io.containerd.cri.v1.images'` |

<br>

### containerd 서비스 시작

```bash
systemctl daemon-reload
systemctl enable --now containerd
systemctl status containerd --no-pager  # Active: active (running)
```

상세 로그를 확인하면 **SystemdCgroup:true** 설정이 적용된 것을 확인할 수 있다.

```bash
journalctl -u containerd.service --no-pager
# Jan 23 01:12:46 k8s-ctr systemd[1]: Starting containerd.service - containerd container runtime...
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="starting containerd" ... version=v2.1.5
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="loading plugin" id=io.containerd.snapshotter.v1.overlayfs ...
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="starting cri plugin" config="...\"SystemdCgroup\":true..."
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... level=error msg="failed to load cni during init..." 
#   error="cni config load failed: no network config found in /etc/cni/net.d: ..."
# Jan 23 01:12:46 k8s-ctr containerd[11617]: ... msg="containerd successfully booted in 0.030233s"
# Jan 23 01:12:46 k8s-ctr systemd[1]: Started containerd.service - containerd container runtime.
```

> CNI 관련 에러(`failed to load cni during init`)는 아직 CNI 플러그인을 설치하지 않았기 때문에 발생하는 것으로, 정상이다. CNI는 `kubeadm init` 후 네트워크 플러그인(Calico 등)을 설치하면 구성된다.

프로세스 트리와 cgroup 계층을 확인한다. [사전 준비]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}) 직후와 비교하면, containerd 프로세스가 추가된 것을 볼 수 있다.

<details markdown="1">
<summary>pstree -alnp</summary>

```
systemd,1 --switched-root --system --deserialize=46 no_timer_check
  ├─systemd-journal,460
  ├─systemd-userdbd,496
  │   ├─systemd-userwor,5205
  │   ├─systemd-userwor,5231
  │   └─systemd-userwor,5244
  ├─systemd-udevd,505
  ├─rpcbind,589 -w -f
  ├─auditd,591
  │   ├─{auditd},592
  │   ├─sedispatch,593
  │   └─{auditd},594
  ├─dbus-broker-lau,632 --scope system --audit
  │   └─dbus-broker,640 --log 4 --controller 9 --machine-id ... --max-bytes 536870912 --max-fds 4096 --max-matches 131072 --audit
  ├─irqbalance,644
  │   └─{irqbalance},669
  ├─lsmd,645 -d
  ├─systemd-logind,648
  ├─chronyd,666 -F 2
  ├─VBoxService,749 --pidfile /var/run/vboxadd-service.sh
  │   ├─{VBoxService},752
  │   └─...
  ├─polkitd,802 --no-debug --log-level=err
  │   └─...
  ├─gssproxy,830 -i
  │   └─...
  ├─sshd,832
  │   ├─sshd-session,4510
  │   │   └─...
  │   └─sshd-session,4595
  │       └─...
  ├─tuned,837 -Es /usr/sbin/tuned -l -P
  │   └─...
  ├─rsyslogd,1117 -n
  │   └─...
  ├─atd,1126 -f
  ├─crond,1132 -n
  ├─agetty,1134 -o -- \\u --noreset --noclear - linux
  ├─NetworkManager,3037 --no-daemon
  │   └─...
  ├─systemd,4515 --user
  │   └─(sd-pam),4517
  ├─udisksd,4873
  │   └─...
  ├─containerd,5357           # ← containerd 프로세스
  │   ├─{containerd},5360
  │   ├─{containerd},5361
  │   ├─{containerd},5362
  │   ├─{containerd},5363
  │   ├─{containerd},5364
  │   ├─{containerd},5365
  │   ├─{containerd},5367
  │   └─{containerd},5371
  └─...
```

</details>

<details markdown="1">
<summary>systemd-cgls --no-pager</summary>

```
CGroup /:
-.slice
├─user.slice
│ └─user-1000.slice
│   ├─user@1000.service …
│   │ └─init.scope
│   │   ├─4515 /usr/lib/systemd/systemd --user
│   │   └─4517 (sd-pam)
│   ├─session-6.scope
│   │ ├─4595 sshd-session: vagrant [priv]
│   │ ├─4598 sshd-session: vagrant@pts/1
│   │ └─4599 -bash
│   └─session-4.scope
│     ├─4510 sshd-session: vagrant [priv]
│     ├─4532 sshd-session: vagrant@pts/0
│     ├─4533 -bash
│     ├─4638 sudo su -
│     ├─4641 sudo su -
│     ├─4642 su -
│     └─4643 -bash
├─init.scope
│ └─1 /usr/lib/systemd/systemd --switched-root --system --deserialize=46 no_timer_check
└─system.slice
  ├─containerd.service …
  │ └─5357 /usr/bin/containerd
  ├─irqbalance.service
  │ └─644 /usr/sbin/irqbalance
  ├─vboxadd-service.service
  │ └─749 /usr/sbin/VBoxService --pidfile /var/run/vboxadd-service.sh
  ├─sshd.service
  │ └─832 sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups
  ├─chronyd.service
  │ └─666 /usr/sbin/chronyd -F 2
  ├─NetworkManager.service
  │ └─3037 /usr/sbin/NetworkManager --no-daemon
  ├─...
```

</details>

`systemd-cgls` 출력에서 containerd가 `system.slice/containerd.service` cgroup 아래에서 실행되는 것을 확인할 수 있다. systemd cgroup 드라이버가 정상적으로 작동하고 있다.

네임스페이스도 확인해 두자. 아직 컨테이너가 실행되지 않은 상태이므로, 모든 네임스페이스가 시스템 서비스의 것이다. 이후 Pod가 생성되면 컨테이너별 네임스페이스가 추가되는 것을 비교할 수 있다.

<details markdown="1">
<summary>lsns</summary>

```
        NS TYPE   NPROCS   PID USER    COMMAND
4026531834 time      133     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531835 cgroup    133     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531836 pid       133     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531837 user      132     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531838 uts       124     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531839 ipc       133     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531840 net       131     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026531841 mnt       117     1 root    /usr/lib/systemd/systemd --switched-root --system --deserialize=46 ...
4026532079 uts         4   496 root    ├─/usr/lib/systemd/systemd-userdbd
4026532080 mnt         4   496 root    ├─/usr/lib/systemd/systemd-userdbd
4026532103 mnt         1   505 root    ├─/usr/lib/systemd/systemd-udevd
4026532104 uts         1   505 root    ├─/usr/lib/systemd/systemd-udevd
4026532124 mnt         2   632 dbus    ├─/usr/bin/dbus-broker-launch --scope system --audit
4026532125 mnt         1   666 chrony  ├─/usr/sbin/chronyd -F 2
4026532127 mnt         1  3037 root    ├─/usr/sbin/NetworkManager --no-daemon
4026532128 net         1   644 root    ├─/usr/sbin/irqbalance
4026532188 mnt         1   644 root    ├─/usr/sbin/irqbalance
4026532189 uts         1   666 chrony  ├─/usr/sbin/chronyd -F 2
4026532197 mnt         1   648 root    ├─/usr/lib/systemd/systemd-logind
4026532198 uts         1   644 root    ├─/usr/sbin/irqbalance
4026532199 uts         1   648 root    ├─/usr/lib/systemd/systemd-logind
4026532200 user        1   644 root    ├─/usr/sbin/irqbalance
4026532202 net         1   802 polkitd ├─/usr/lib/polkit-1/polkitd --no-debug --log-level=err
4026532265 mnt         1   802 polkitd ├─/usr/lib/polkit-1/polkitd --no-debug --log-level=err
4026532266 uts         1   802 polkitd ├─/usr/lib/polkit-1/polkitd --no-debug --log-level=err
4026532270 mnt         1  5372 root    ├─/usr/libexec/fwupd/fwupd
4026532340 mnt         1  1117 root    ├─/usr/sbin/rsyslogd -n
4026532342 mnt         1   830 root    └─/usr/sbin/gssproxy -i
4026531862 mnt         1    38 root    kdevtmpfs
```

</details>

<br>

### 소켓 및 플러그인 확인

```bash
# containerd 유닉스 도메인 소켓 확인 (kubelet, ctr, crictl이 이 소켓 사용)
ls -l /run/containerd/containerd.sock  # srw-rw----. 1 root root 0 ...
ss -xl | grep containerd               # .sock.ttrpc(gRPC), .sock(TTRPC) LISTEN 확인
ctr version                            # Client/Server: v2.1.5
```

플러그인 상태를 확인한다. Kubernetes에서 사용하는 주요 플러그인이 `ok` 상태인지 확인한다.

> **참고**: containerd는 코어를 가볍게 유지하고, 실제 기능(이미지 관리, 스냅샷, 런타임 실행, CRI 인터페이스 등)을 **플러그인**으로 분리한다. `ctr plugins ls`로 보이는 플러그인은 containerd 바이너리에 빌트인으로 컴파일된 것으로, 별도 설치 없이 `config.toml`의 `disabled_plugins` 설정에 따라 활성화/비활성화된다.

```bash
ctr plugins ls
# TYPE                                   ID                  PLATFORMS        STATUS
# io.containerd.content.v1               content             -                ok
# io.containerd.snapshotter.v1           overlayfs           linux/arm64/v8   ok
# io.containerd.snapshotter.v1           native              linux/arm64/v8   ok
# io.containerd.metadata.v1              bolt                -                ok
# io.containerd.monitor.task.v1          cgroups             linux/arm64/v8   ok
# io.containerd.runtime.v2               task                linux/arm64/v8   ok
# io.containerd.cri.v1                   images              -                ok
# io.containerd.cri.v1                   runtime             linux/arm64/v8   ok
# io.containerd.grpc.v1                  cri                 -                ok
# io.containerd.podsandbox.controller.v1 podsandbox          -                ok
# ...
```

Kubernetes 관점에서 주요 플러그인은 아래와 같다.

| 플러그인 | ID | 역할 |
| --- | --- | --- |
| `io.containerd.cri.v1` | `images`, `runtime` | CRI 플러그인. kubelet이 containerd와 통신하는 인터페이스. 이 플러그인이 비활성화되면 kubelet이 containerd를 사용할 수 없다 |
| `io.containerd.grpc.v1` | `cri` | CRI gRPC 서버. kubelet의 CRI 요청을 위 플러그인으로 라우팅 |
| `io.containerd.snapshotter.v1` | `overlayfs` | 컨테이너 이미지 레이어를 OverlayFS로 마운트하여 파일시스템 제공 |
| `io.containerd.runtime.v2` | `task` | 실제 컨테이너 실행. containerd-shim-runc-v2를 통해 runc를 호출 |
| `io.containerd.content.v1` | `content` | 이미지 레이어(blob) 저장소 관리 |
| `io.containerd.metadata.v1` | `bolt` | 컨테이너/이미지 메타데이터를 BoltDB에 저장 |
| `io.containerd.podsandbox.controller.v1` | `podsandbox` | Pod sandbox([pause 컨테이너]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너)) 라이프사이클 관리 |

> **참고: Lazy-loading Snapshotter**
> 
> 기본 `overlayfs` snapshotter는 컨테이너 시작 전 **전체 이미지를 다운로드**해야 한다. 대용량 이미지(ML 모델, 데이터 분석 도구 등)의 경우 이미지 pull 시간이 컨테이너 시작 시간의 대부분을 차지할 수 있다.
> 
> 이런 경우 **lazy-loading snapshotter**를 고려할 수 있다:
> - [**eStargz (stargz-snapshotter)**](https://github.com/containerd/stargz-snapshotter): CNCF containerd 프로젝트. 이미지를 부분적으로 다운로드하며 필요한 파일만 on-demand로 fetch
> - [**SOCI Snapshotter**](https://github.com/awslabs/soci-snapshotter): AWS에서 개발. 기존 OCI 이미지를 수정 없이 사용하면서 lazy-loading 지원 ([AWS 블로그](https://aws.amazon.com/ko/blogs/tech/under-the-hood-lazy-loading-container-images-with-seekable-oci-and-aws-fargate/))
>
> 이러한 snapshotter를 사용하면 이미지 크기와 관계없이 컨테이너를 빠르게 시작할 수 있어, 스케일링이 빈번한 워크로드에 유리하다.

<br>

# kubeadm, kubelet, kubectl 설치

이제 Kubernetes 핵심 도구들을 설치한다.

| 도구 | 역할 |
| --- | --- |
| **kubeadm** | 클러스터 부트스트래핑 도구 |
| **kubelet** | 각 노드에서 Pod를 관리하는 에이전트 |
| **kubectl** | 클러스터와 상호작용하는 CLI 도구 |

<br>

## Kubernetes 저장소 추가

kubeadm, kubelet, kubectl은 OS 기본 저장소에 없으므로, Kubernetes 프로젝트가 운영하는 `pkgs.k8s.io` 저장소를 추가해야 한다.

`exclude` 설정이 핵심이다. `dnf update` 시 이 패키지들이 의도치 않게 업그레이드되면, kubelet 버전이 Control Plane 버전과 맞지 않거나 노드마다 버전이 달라지는 문제가 발생할 수 있다. `exclude`로 자동 업그레이드를 막고, 업그레이드가 필요할 때만 `--disableexcludes=kubernetes` 옵션을 붙여 명시적으로 수행한다.

```bash
# 현재 저장소 확인
dnf repolist
tree /etc/yum.repos.d/

# Kubernetes 저장소 추가
cat <<EOF | tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF
dnf makecache
```

<br>

## 설치 가능 버전 확인

`exclude=kubelet kubeadm kubectl` 설정이 적용되어 있어 일반 `dnf list`로는 패키지가 보이지 않는다. `--disableexcludes=kubernetes` 옵션을 사용하면 해당 저장소의 exclude 규칙을 일시적으로 무시할 수 있다. Kubernetes 1.32.x 버전이 제공되는 것을 확인할 수 있다.

```bash
# exclude 설정이 적용된 경우 목록이 비어 있음
dnf list --showduplicates kubelet
# Error: No matching Packages to list

# --disableexcludes 옵션으로 exclude 규칙 무시 (1회성)
dnf list --showduplicates kubelet --disableexcludes=kubernetes
# Available Packages
# kubelet.aarch64    1.32.0-150500.1.1    kubernetes
# kubelet.aarch64    1.32.1-150500.1.1    kubernetes
# ...
# kubelet.aarch64    1.32.10-150500.1.1   kubernetes
# kubelet.aarch64    1.32.11-150500.1.1   kubernetes  <- 최신 버전

dnf list --showduplicates kubeadm --disableexcludes=kubernetes
# Available Packages
# kubeadm.aarch64    1.32.0-150500.1.1    kubernetes
# ...
# kubeadm.aarch64    1.32.11-150500.1.1   kubernetes

dnf list --showduplicates kubectl --disableexcludes=kubernetes
# Available Packages
# kubectl.aarch64    1.32.0-150500.1.1    kubernetes
# ...
# kubectl.aarch64    1.32.11-150500.1.1   kubernetes
```


<br>

## kubeadm, kubelet, kubectl 설치

```bash
dnf install -y kubelet kubeadm kubectl --disableexcludes=kubernetes
# Installed:
#   kubeadm-1.32.13    kubectl-1.32.13    kubelet-1.32.13
#   cri-tools-1.32.0   kubernetes-cni-1.6.0
```

### 설치 확인

```bash
which kubeadm && kubeadm version -o yaml
# /usr/bin/kubeadm
# clientVersion:
#   buildDate: "2026-02-26T20:22:27Z"
#   compiler: gc
#   gitCommit: 6172d7357c6287643350a4fc7e048f24098f2a1b
#   gitTreeState: clean
#   gitVersion: v1.32.13
#   goVersion: go1.24.13
#   major: "1"
#   minor: "32"
#   platform: linux/arm64

which kubectl && kubectl version --client=true
# /usr/bin/kubectl
# Client Version: v1.32.13
# Kustomize Version: v5.5.0

which kubelet && kubelet --version
# /usr/bin/kubelet
# Kubernetes v1.32.13
```

### crictl 설정

의존성으로 함께 설치된 `crictl`(CRI 호환 컨테이너 런타임용 CLI 도구)을 확인한다. 설정 파일이 없으면 경고가 발생하므로, 엔드포인트를 명시적으로 지정한다.

```bash
which crictl && crictl version
# /usr/bin/crictl
# WARN[0000] Config "/etc/crictl.yaml" does not exist, trying next: "/usr/bin/crictl.yaml"
# WARN[0000] runtime connect using default endpoints: [unix:///run/containerd/containerd.sock
#   unix:///run/crio/crio.sock unix:///var/run/cri-dockerd.sock].
#   As the default settings are now deprecated, you should set the endpoint instead.
# Version:  0.1.0
# RuntimeName:  containerd
# RuntimeVersion:  v2.1.5
# RuntimeApiVersion:  v1

cat << EOF > /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
EOF
```

<details markdown="1">
<summary>crictl info 전체 출력 (클릭하여 펼치기)</summary>
```bash
crictl info | jq
```

```json
{
  "cniconfig": {
    "Networks": [
      {
        "Config": {
          "CNIVersion": "0.3.1",
          "Name": "cni-loopback",
          "Plugins": [{ "Network": { "type": "loopback" } }]
        },
        "IFName": "lo"
      }
    ],
    "PluginConfDir": "/etc/cni/net.d",
    "PluginDirs": ["/opt/cni/bin"]
  },
  "config": {
    "cni": {
      "binDirs": ["/opt/cni/bin"],
      "confDir": "/etc/cni/net.d"
    },
    "containerd": {
      "defaultRuntimeName": "runc",
      "runtimes": {
        "runc": {
          "options": {
            "SystemdCgroup": true
          },
          "runtimeType": "io.containerd.runc.v2",
          "sandboxer": "podsandbox"
        }
      }
    },
    "containerdEndpoint": "/run/containerd/containerd.sock",
    "containerdRootDir": "/var/lib/containerd"
  },
  "golang": "go1.24.9",
  "lastCNILoadStatus": "cni config load failed: no network config found in /etc/cni/net.d",
  "status": {
    "conditions": [
      { "status": true, "type": "RuntimeReady" },              // containerd 런타임 정상
      { 
        "message": "Network plugin returns error: cni plugin not initialized",
        "reason": "NetworkPluginNotReady",
        "status": false,                                        // CNI 미설치 (정상)
        "type": "NetworkReady"
      },
      { "status": true, "type": "ContainerdHasNoDeprecationWarnings" }  // deprecation 경고 없음
    ]
  }
}
```

</details>

<br>

| 항목 | 값 | 의미 |
| --- | --- | --- |
| `RuntimeReady` | `true` | containerd 런타임 정상 - containerd가 CRI를 통해 정상적으로 컨테이너를 실행할 준비가 됨 |
| `NetworkReady` | `false` | CNI 미설치 (정상) - CNI 플러그인이 아직 설치되지 않음. `kubeadm init` 후 Calico 등 CNI를 설치하면 `true`가 됨 |
| `SystemdCgroup` | `true` | systemd cgroup 드라이버 사용 |
| `ContainerdHasNoDeprecationWarnings` | `true` | containerd 설정에 deprecated 옵션이 없음 |
| `containerdEndpoint` | `/run/containerd/containerd.sock` | CRI 소켓 경로 |

### kubelet 서비스 활성화

```bash
systemctl enable --now kubelet
# Created symlink '/etc/systemd/system/multi-user.target.wants/kubelet.service'
#   → '/usr/lib/systemd/system/kubelet.service'.
```

서비스를 활성화했지만, 상태를 확인하면 실패와 재시작을 반복하고 있다.

```bash
systemctl status kubelet
# ● kubelet.service - kubelet: The Kubernetes Node Agent
#      Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: disabled)
#     Drop-In: /usr/lib/systemd/system/kubelet.service.d
#              └─10-kubeadm.conf
#      Active: activating (auto-restart) (Result: exit-code) since Thu 2026-01-23 01:19:34 KST; 5s ago
#     Process: 5851 ExecStart=/usr/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS $KUBELET_KUBEADM_ARGS ...
#    Main PID: 5851 (code=exited, status=1/FAILURE)
```

저널 로그를 보면 10초 간격으로 시작 → 실패 → 재시작을 반복한다.

```bash
journalctl -u kubelet --no-pager
# Jan 23 01:19:08 k8s-ctr systemd[1]: Started kubelet.service - kubelet: The Kubernetes Node Agent.
# Jan 23 01:19:08 k8s-ctr (kubelet)[5613]: kubelet.service: Referenced but unset environment variable evaluates to an empty string: $KUBELET_...
# Jan 23 01:19:09 k8s-ctr kubelet[5613]: E0123 01:19:09.057083  5613 run.go:72] "command failed" err="failed to ..."
# Jan 23 01:19:09 k8s-ctr systemd[1]: kubelet.service: Main process exited, code=exited, status=1/FAILURE
# Jan 23 01:19:09 k8s-ctr systemd[1]: kubelet.service: Failed with result 'exit-code'.
# Jan 23 01:19:19 k8s-ctr systemd[1]: kubelet.service: Scheduled restart job, restart counter is at 1.
# Jan 23 01:19:19 k8s-ctr systemd[1]: Started kubelet.service - kubelet: The Kubernetes Node Agent.
# ... (10초 간격으로 반복)
```

이는 **정상적인 동작**이다. `kubeadm init` 또는 `kubeadm join`이 완료되어 필요한 설정 파일(`/etc/kubernetes/kubelet.conf` 등)이 생성되기 전까지 kubelet은 시작 직후 종료되는 crashloop 상태가 된다. kubeadm 공식 문서에서도 ["The kubelet is now restarting every few seconds, as it waits in a crashloop for kubeadm to tell it what to do"](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/)라고 설명한다.


<br>

## CNI 바이너리 및 설정 디렉토리 확인

kubelet 설치 시 의존성으로 함께 설치된 `kubernetes-cni` 패키지가 `/opt/cni/bin/`에 CNI 바이너리(bridge, loopback, portmap 등 기본 플러그인)를 제공한다. 반면 `/etc/cni/net.d/`(설정 디렉토리)는 아직 비어 있다. CNI 설정 파일은 이후 [CNI 플러그인(Flannel) 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}#flannel-설치) 시 `/etc/cni/net.d/`에 생성된다.

> **참고: containerd와 CNI의 관계**
>
> kubelet이 직접 CNI를 호출하는 것이 아니다. kubelet이 Pod 생성을 요청하면, **containerd가 Pod sandbox([pause 컨테이너]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너))를 만들면서 CNI 바이너리를 호출**하여 네트워크를 설정한다. 그래서 containerd가 "CNI 바이너리가 어디 있고, 어떤 설정을 쓸지" 알아야 하며, 이것이 [containerd 설정](#기본-설정-생성-및-systemdcgroup-활성화)의 `bin_dirs`, `conf_dir`이다. (상세한 호출 흐름은 [Kubernetes CNI - 동작 방식]({% post_url 2026-01-05-Kubernetes-CNI %}#동작-방식) 참고)
>
> ```
> kubelet → (CRI) → containerd → (CNI) → /opt/cni/bin/ 바이너리 실행
>                        ↑
>                 config.toml의 bin_dirs, conf_dir로
>                 바이너리와 설정 파일 경로를 참조
> ```
>
> Flannel 설치 시 설정하는 `cniBinDir`, `cniConfDir`도 같은 경로를 가리킨다. 세 곳(containerd config, kubernetes-cni 패키지, Flannel 설정)이 동일한 경로를 사용하는 것은 이 호출 체인이 일관되어야 하기 때문이다.

```bash
# CNI 바이너리 확인
ls -al /opt/cni/bin
# total 63200
# drwxr-xr-x. 2 root root    4096 Jan 23 01:19 .
# drwxr-xr-x. 3 root root      17 Jan 23 01:19 ..
# -rwxr-xr-x. 1 root root 3239200 Dec 12  2024 bandwidth
# -rwxr-xr-x. 1 root root 3731632 Dec 12  2024 bridge
# -rwxr-xr-x. 1 root root 9123544 Dec 12  2024 dhcp
# -rwxr-xr-x. 1 root root 3379872 Dec 12  2024 dummy
# -rwxr-xr-x. 1 root root 3742888 Dec 12  2024 firewall
# -rwxr-xr-x. 1 root root 3383408 Dec 12  2024 host-device
# -rwxr-xr-x. 1 root root 2812400 Dec 12  2024 host-local
# -rwxr-xr-x. 1 root root 3380928 Dec 12  2024 ipvlan
# -rwxr-xr-x. 1 root root 2953200 Dec 12  2024 loopback
# -rwxr-xr-x. 1 root root 3448024 Dec 12  2024 macvlan
# -rwxr-xr-x. 1 root root 3312488 Dec 12  2024 portmap
# -rwxr-xr-x. 1 root root 3524072 Dec 12  2024 ptp
# ...

tree /opt/cni
# /opt/cni
# └── bin
#     ├── bandwidth
#     ├── bridge
#     ├── dhcp
#     ├── dummy
#     ├── firewall
#     ├── host-device
#     ├── host-local
#     ├── ipvlan
#     ├── loopback
#     ├── macvlan
#     ├── portmap
#     ├── ptp
#     ├── sbr
#     ├── static
#     ├── tap
#     ├── tuning
#     ├── vlan
#     └── vrf
#
# 2 directories, 20 files

# CNI 설정 디렉토리 (아직 비어 있음)
tree /etc/cni
# /etc/cni
# └── net.d
```

<br>

# kubeadm init 전 상태 확인

containerd, kubelet, kubeadm, kubectl 설치가 모두 끝났다. `kubeadm init`을 실행하기 전에 현재 상태를 확인해 두자.

## kubelet 서비스 파일

위에서 확인한 것처럼 kubelet은 crashloop 상태다. `systemctl status` 출력의 `Drop-In` 항목에 `10-kubeadm.conf`가 보이는데, 이 서비스 파일들의 구조를 확인해 보자.

```bash
tree /usr/lib/systemd/system | grep kubelet -A1
# ├── kubelet.service
# ├── kubelet.service.d
# │   └── 10-kubeadm.conf
```

`kubelet.service.d/10-kubeadm.conf`는 systemd **drop-in 파일**이다. systemd에서 `<서비스명>.service.d/` 디렉토리 안에 `.conf` 파일을 두면, 원본 서비스 파일을 직접 수정하지 않고도 설정을 **오버라이드하거나 추가**할 수 있다. 파일명의 숫자 접두사(`10-`)는 로드 순서를 결정한다. kubeadm 패키지가 이 drop-in을 설치하여 kubelet의 실행 방식을 kubeadm에 맞게 변경한다.

> **참고: systemd 서비스 설정 주요 지시어**
>
> | 지시어 | 역할 |
> | --- | --- |
> | `ExecStart` | 서비스 시작 시 실행할 명령. drop-in에서 빈 값(`ExecStart=`)을 할당하면 원본의 `ExecStart`가 리셋되고, 다음 줄에서 새 명령을 설정할 수 있다 (systemd에서 리스트형 속성은 빈 값 할당으로 기존 값이 초기화됨) |
> | `Environment` | 환경변수를 직접 정의. `Environment="KEY=value"` 형식 |
> | `EnvironmentFile` | 외부 파일에서 환경변수를 읽어옴. `-` 접두사(`EnvironmentFile=-/path`)는 파일이 없어도 에러를 내지 않겠다는 뜻 |
> | `Restart` | 프로세스 종료 시 재시작 정책. `always`는 어떤 이유로 종료되든 항상 재시작 |
> | `RestartSec` | 재시작 간격 (초) |

먼저 원본 `kubelet.service`를 확인한다.

```bash
cat /usr/lib/systemd/system/kubelet.service
# [Unit]
# Description=kubelet: The Kubernetes Node Agent
# Documentation=https://kubernetes.io/docs/
# Wants=network-online.target
# After=network-online.target
#
# [Service]
# ExecStart=/usr/bin/kubelet
# Restart=always
# StartLimitInterval=0
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target

cat /usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf
# # Note: This dropin only works with kubeadm and kubelet v1.11+
# [Service]
# Environment="KUBELET_KUBECONFIG_ARGS=--bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf 
#              --kubeconfig=/etc/kubernetes/kubelet.conf"
# Environment="KUBELET_CONFIG_ARGS=--config=/var/lib/kubelet/config.yaml"
# # This is a file that "kubeadm init" and "kubeadm join" generates at runtime, 
# # populating the KUBELET_KUBEADM_ARGS variable dynamically
# EnvironmentFile=-/var/lib/kubelet/kubeadm-flags.env
# # KUBELET_EXTRA_ARGS should be sourced from this file.
# EnvironmentFile=-/etc/sysconfig/kubelet
# ExecStart=
# ExecStart=/usr/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS $KUBELET_KUBEADM_ARGS $KUBELET_EXTRA_ARGS
```

`kubelet.service` 자체는 단순히 `/usr/bin/kubelet`을 실행하고, 실패 시 10초마다 재시작(`Restart=always`, `RestartSec=10`)하는 것이 전부다. 실제 kubelet의 실행 인자는 `10-kubeadm.conf` drop-in 파일이 오버라이드한다. drop-in에서 `ExecStart=`(빈 값)으로 `kubelet.service`의 원래 `ExecStart`를 리셋한 뒤, 환경변수가 포함된 새 `ExecStart`를 설정하는 구조다. (systemd에서 리스트형 속성은 빈 값 할당으로 기존 값을 초기화할 수 있다.)

이 drop-in 파일이 참조하는 환경변수와 파일들이 kubelet이 crashloop하는 원인이기도 하다. 아직 `kubeadm init`을 실행하지 않아서 아래 파일들이 존재하지 않기 때문이다.

| 파일 | 설명 | 생성 시점 |
| --- | --- | --- |
| `/etc/kubernetes/bootstrap-kubelet.conf` | 부트스트랩 kubeconfig | `kubeadm init/join` |
| `/etc/kubernetes/kubelet.conf` | kubelet kubeconfig | `kubeadm init/join` |
| `/var/lib/kubelet/config.yaml` | kubelet 설정 파일 | `kubeadm init/join` |
| `/var/lib/kubelet/kubeadm-flags.env` | kubeadm이 생성하는 플래그 | `kubeadm init/join` |
| `/etc/sysconfig/kubelet` | 사용자 정의 추가 인자 | 수동 생성 (선택) |

`kubeadm init`이 실행되면 위 파일들이 생성된다.

> 실제 값은 `kubeadm init` + CNI 설치 후 [kubelet 상태 및 설정 확인]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#kubelet-상태-및-설정-확인)에서 확인한다.


### config.yaml

kubelet의 런타임 설정 파일이다.

| 설정 | 역할 |
| --- | --- |
| `staticPodPath` | kubelet이 감시할 Static Pod 매니페스트 디렉토리 (`/etc/kubernetes/manifests`) |
| `cgroupDriver` | cgroup 드라이버. containerd의 `SystemdCgroup` 설정과 일치해야 한다 |
| `clusterDNS` | 클러스터 DNS(CoreDNS) Service의 ClusterIP |
| `clusterDomain` | 클러스터 도메인 (`cluster.local`) |
| `rotateCertificates` | kubelet 클라이언트 인증서 자동 갱신 여부 |

### kubeadm-flags.env

kubeadm이 kubelet에 전달할 플래그를 `KUBELET_KUBEADM_ARGS` 환경변수로 정의한다.

| 플래그 | 역할 |
| --- | --- |
| `--container-runtime-endpoint` | CRI 소켓 경로 (containerd 유닉스 도메인 소켓) |
| `--node-ip` | 노드 IP (kubeadm 설정의 `localAPIEndpoint.advertiseAddress`) |
| `--pod-infra-container-image` | Pod의 [인프라 컨테이너(pause)]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너) 이미지 |

## kubernetes 관련 디렉토리

위 표에서 `kubeadm init/join` 시 생성된다고 한 파일들이 실제로 아직 없는지 확인해 보자.

```bash
tree /etc/kubernetes
# /etc/kubernetes
# └── manifests
#
# 2 directories, 0 files

tree /var/lib/kubelet
# /var/lib/kubelet
#
# 0 directories, 0 files   <- config.yaml 등 아직 없음

# kubelet 추가 인자 설정 파일
cat /etc/sysconfig/kubelet
# KUBELET_EXTRA_ARGS=
```

## 정리

현재 상태를 요약하면 다음과 같다.
- `/etc/kubernetes/manifests`: 비어 있음 (static pod manifest가 없음)
- `/var/lib/kubelet`: 비어 있음 (`config.yaml` 등 아직 없음)
- `/etc/sysconfig/kubelet`: `KUBELET_EXTRA_ARGS` 비어 있음
- containerd: 정상 실행 중 (프로세스, cgroup, 소켓, 네임스페이스는 [containerd 설치](#containerd-설치-및-설정) 섹션에서 확인)

<br>

## 설정 전후 비교용 기본 정보 저장

`kubeadm init` 전후로 시스템 상태 변화를 비교하기 위해 현재 상태를 저장해 둔다.

```bash
# 기본 환경 정보 저장
crictl images | tee -a crictl_images-1.txt
crictl ps -a | tee -a crictl_ps-1.txt
cat /etc/sysconfig/kubelet | tee -a kubelet_config-1.txt
tree /etc/kubernetes  | tee -a etc_kubernetes-1.txt
tree /var/lib/kubelet | tee -a var_lib_kubelet-1.txt
tree /run/containerd/ -L 3 | tee -a run_containerd-1.txt
pstree -alnp | tee -a pstree-1.txt
systemd-cgls --no-pager | tee -a systemd-cgls-1.txt
lsns | tee -a lsns-1.txt
ip addr | tee -a ip_addr-1.txt 
ss -tnlp | tee -a ss-1.txt
df -hT | tee -a df-1.txt
findmnt | tee -a findmnt-1.txt
sysctl -a | tee -a sysctl-1.txt
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| containerd | v2.1.5 설치, SystemdCgroup 활성화 |
| kubeadm | v1.32.11 설치 |
| kubelet | v1.32.11 설치, 서비스 활성화 |
| kubectl | v1.32.11 설치 |

<br>

현재 상태에서는 아직 클러스터가 구성되지 않았다:
- `/etc/kubernetes/` 디렉토리가 비어 있음
- `/var/lib/kubelet/` 디렉토리가 비어 있음
- kubelet이 재시작을 반복함 (정상)
- CNI가 설치되지 않아 NetworkReady 상태가 false

[다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %})에서 `kubeadm init`을 실행하여 컨트롤 플레인을 구성한다.
