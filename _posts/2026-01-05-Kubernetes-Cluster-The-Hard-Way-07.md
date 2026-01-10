---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 7. Bootstrapping the etcd Cluster"
excerpt: "Kubernetes 클러스터의 핵심 데이터 저장소인 etcd를 Control Plane 노드에 구성하고 시작해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1

---

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Kubernetes 클러스터의 핵심 데이터 저장소인 etcd 클러스터 구성**이다. [Kubernetes the Hard Way 튜토리얼의 Bootstrapping the etcd Cluster 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/07-bootstrapping-etcd.md)를 수행한다.

- etcd 서비스 설정: HTTP 평문 통신으로 etcd systemd service 파일 생성
- etcd 바이너리 배포: Control Plane 노드에 etcd 및 etcdctl 배포
- etcd 클러스터 시작: 단일 노드 etcd 클러스터 구성 및 기동
- 동작 확인: 서비스 상태 및 클러스터 멤버 확인

etcd는 Kubernetes의 모든 상태 정보를 저장하는 분산 key-value 저장소로, Control Plane의 핵심 컴포넌트다. 이번 단계에서는 실습 환경에 맞게 단일 노드로 구성하지만, 프로덕션에서는 고가용성을 위해 3개 이상의 홀수 개수로 클러스터를 구성해야 한다.

<br>


# Prerequisites: hostname 변경

etcd 클러스터 내에서 각 멤버는 고유한 이름을 가져야 한다. 우리 실습 환경에서 Control Plane 호스트명은 `server`이므로, controller에서 server로 hostname을 변경한다.

```bash
# 기존 controller인 부분 확인
cat units/etcd.service | grep controller
# 출력
  --name controller \
  --initial-cluster controller=http://127.0.0.1:2380 \
```
<br>
# etcd 서비스 파일 생성

이후 실습 과정에서 etcd를 systemd 서비스로 기동하게 되는데, 이를 위해 서비스 파일을 생성한다.

```bash
ETCD_NAME=server
cat > units/etcd.service <<EOF
[Unit]
Description=etcd
Documentation=https://github.com/etcd-io/etcd

[Service]
Type=notify
ExecStart=/usr/local/bin/etcd \\
  --name ${ETCD_NAME} \\
  --initial-advertise-peer-urls http://127.0.0.1:2380 \\
  --listen-peer-urls http://127.0.0.1:2380 \\ 
  --listen-client-urls http://127.0.0.1:2379 \\
  --advertise-client-urls http://127.0.0.1:2379 \\
  --initial-cluster-token etcd-cluster-0 \\
  --initial-cluster ${ETCD_NAME}=http://127.0.0.1:2380 \\
  --initial-cluster-state new \\
  --data-dir=/var/lib/etcd
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

바뀌었는지 잘 확인해 보자.

```bash
cat units/etcd.service | grep server
# 확인
  --name server \
  --initial-cluster server=http://127.0.0.1:2380 \
```

## ExecStart 

`ExecStart`는 systemd가 서비스를 시작할 때 실행할 명령어를 지정한다. 즉, `systemctl start etcd`를 실행하면 여기 정의된 명령어가 실행된다.

 etcd 실행 명령어가 정의되는데, 이 때 실행되는 옵션을 확인해 보자:
- `--name`: etcd 멤버의 고유 이름 (여기서는 `server`)
- `--initial-advertise-peer-urls`: 클러스터 내 다른 멤버에게 알릴 피어 통신 URL (HTTP 사용)
- `--listen-peer-urls`: 피어 통신을 위해 리스닝할 URL (포트 2380)
- `--listen-client-urls`: 클라이언트 요청을 위해 리스닝할 URL (포트 2379)
- `--advertise-client-urls`: 클라이언트에게 알릴 URL (HTTP 사용)
- `--initial-cluster-token`: 클러스터의 고유 토큰
- `--initial-cluster`: 초기 클러스터 구성 정보
- `--initial-cluster-state`: 클러스터 초기 상태 (`new`: 새로운 클러스터)
- `--data-dir`: etcd 데이터 저장 디렉토리

위 설정 중 중요하게 볼 것은 HTTP 평문 통신이다. 프로덕션 환경에서는 보안을 위해 HTTPS(TLS)를 사용해야 하지만, 실습 환경의 단순화를 위해 HTTP 평문 통신을 사용한다.

<br>

# etcd 바이너리 및 설정 파일 배포

etcd는 Kubernetes의 **Control Plane 컴포넌트**로, 클러스터의 모든 상태 정보를 저장하는 분산 key-value 저장소다. 따라서 Control Plane 노드인 `server` 가상머신에 설치해야 한다.

이를 위해 `server` 가상머신에 etcd 바이너리와 systemd unit 파일을 복사한다.

```bash
scp \
  downloads/controller/etcd \
  downloads/client/etcdctl \
  units/etcd.service \
  root@server:~/
etcd                          100%   23MB  60.4MB/s   00:00    
etcdctl                       100%   15MB  97.7MB/s   00:00    
etcd.service                  100%  564     1.2MB/s   00:00    
```

<br>

# etcd 클러스터 시작

`server` 가상머신에 접속하여 etcd 클러스터를 시작한다.

```bash
ssh root@server

# 현재 작업 디렉토리 확인
pwd
/root
```

## etcd 바이너리 설치

etcd 서버와 etcdctl 유틸리티를 설치한다.

```bash
mv etcd etcdctl /usr/local/bin/
```

## etcd 서버 설정

etcd 설정 디렉토리와 데이터 디렉토리를 생성하고 권한을 설정한다.

```bash
mkdir -p /etc/etcd /var/lib/etcd
chmod 700 /var/lib/etcd
cp ca.crt kube-api-server.key kube-api-server.crt /etc/etcd/
```

## systemd unit 파일 생성

etcd.service systemd unit 파일을 생성한다.

```bash
mv etcd.service /etc/systemd/system/
# 확인
tree /etc/systemd/system/
/etc/systemd/system/
├── apt-daily.service -> /dev/null
├── apt-daily-upgrade.service -> /dev/null
├── dbus-org.freedesktop.timesync1.service -> /lib/systemd/system/systemd-timesyncd.service
├── etcd.service # 확인
...
```

## etcd 서버 시작

```bash
systemctl daemon-reload  # systemd 설정 파일 변경 사항 반영
systemctl enable etcd    # 부팅 시 자동 시작 설정
systemctl start etcd     # etcd 서비스 시작
```

```bash
# enable 실행 시 출력
Created symlink /etc/systemd/system/multi-user.target.wants/etcd.service → /etc/systemd/system/etcd.service
```

<br>

# 검증

## etcd 서비스 상태 확인

```bash
systemctl status etcd --no-pager
● etcd.service - etcd
     Loaded: loaded (/etc/systemd/system/etcd.service; enabled; preset: enabled)
     Active: active (running) since Thu 2026-01-08 23:53:58 KST; 54s ago
       Docs: https://github.com/etcd-io/etcd
   Main PID: 2799 (etcd)
      Tasks: 8 (limit: 2096)
     Memory: 11.8M
        CPU: 277ms
     CGroup: /system.slice/etcd.service
             └─2799 /usr/local/bin/etcd --name server --initial…

Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…n"}
Jan 08 23:53:58 server systemd[1]: Started etcd.service - etcd.
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…n"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…G"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…6"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…6"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…6"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…0"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…0"}
Jan 08 23:53:58 server etcd[2799]: {"level":"info","ts":"202…9"}
Hint: Some lines were ellipsized, use -l to show in full.
```

## etcd 포트 확인

etcd가 2379(클라이언트), 2380(피어) 포트에서 리스닝하는지 확인한다.

```bash
ss -tnlp | grep etcd
LISTEN 0      4096       127.0.0.1:2380      0.0.0.0:*    users:(("etcd",pid=2799,fd=3))                          
LISTEN 0      4096       127.0.0.1:2379      0.0.0.0:*    users:(("etcd",pid=2799,fd=6))     
```

## etcd 클러스터 멤버 확인

```bash
etcdctl member list  # etcd 클러스터 멤버 목록 조회
6702b0a34e2cfd39, started, server, http://127.0.0.1:2380, http://127.0.0.1:2379, false
```

> **참고**: 현재는 단일 노드 etcd 클러스터로 구성되어 있어 `server` 멤버 하나만 표시된다. 프로덕션 환경에서는 고가용성을 위해 최소 3개 이상의 홀수 개수로 클러스터를 구성하는 것이 권장된다.

```bash
# 테이블 형식으로 확인
etcdctl member list -w table  # 멤버 목록을 테이블 형식으로 출력
+------------------+---------+--------+-----------------------+-----------------------+------------+
|        ID        | STATUS  |  NAME  |      PEER ADDRS       |     CLIENT ADDRS      | IS LEARNER |
+------------------+---------+--------+-----------------------+-----------------------+------------+
| 6702b0a34e2cfd39 | started | server | http://127.0.0.1:2380 | http://127.0.0.1:2379 |      false |
+------------------+---------+--------+-----------------------+-----------------------+------------+
```
- `ID`: etcd 멤버의 고유 ID
- `STATUS`: 멤버의 상태 (started: 정상 동작 중)
- `NAME`: 멤버 이름 (우리가 `--name`으로 설정한 값)
- `PEER ADDRS`: 클러스터 내 피어 통신 주소 (포트 2380)
- `CLIENT ADDRS`: 클라이언트 통신 주소 (포트 2379)
- `IS LEARNER`: 학습자 노드 여부 (false: 정식 멤버)

<br>

```bash
etcdctl endpoint status -w table  # etcd 엔드포인트 상태 상세 정보 조회
+----------------+------------------+------------+-----------------+---------+--------+-----------------------+-------+-----------+------------+-----------+------------+--------------------+--------+--------------------------+-------------------+
|    ENDPOINT    |        ID        |  VERSION   | STORAGE VERSION | DB SIZE | IN USE | PERCENTAGE NOT IN USE | QUOTA | IS LEADER | IS LEARNER | RAFT TERM | RAFT INDEX | RAFT APPLIED INDEX | ERRORS | DOWNGRADE TARGET VERSION | DOWNGRADE ENABLED |
+----------------+------------------+------------+-----------------+---------+--------+-----------------------+-------+-----------+------------+-----------+------------+--------------------+--------+--------------------------+-------------------+
| 127.0.0.1:2379 | 6702b0a34e2cfd39 | 3.6.0-rc.3 |           3.6.0 |   20 kB |  16 kB |                   20% |   0 B |      true |      false |         2 |          4 |                  4 |        |                          |             false |
+----------------+------------------+------------+-----------------+---------+--------+-----------------------+-------+-----------+------------+-----------+------------+--------------------+--------+--------------------------+-------------------+
```
- `VERSION`: etcd 버전
- `DB SIZE`: 데이터베이스 크기 (현재 20 kB로 비어있음)
- `IS LEADER`: 리더 노드 여부 (단일 노드이므로 항상 true)

<br>

## server 가상머신 종료

완료되었으면 가상머신을 종료한다.

```bash
exit
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **etcd 서비스 설정**: HTTP 평문 통신으로 etcd systemd service 파일 생성
2. **etcd 바이너리 설치**: Control Plane 노드에 etcd와 etcdctl 설치
3. **etcd 클러스터 시작**: 단일 노드 etcd 클러스터 구성 및 시작
4. **etcd 동작 확인**: 
   - 서비스 정상 동작 (포트 2379, 2380 리스닝)
   - 클러스터 멤버 목록 조회
   - 엔드포인트 상태 확인

<br>

이번 실습을 통해 Kubernetes의 핵심 데이터 저장소인 etcd를 직접 구성해 보았다. etcd는 클러스터의 모든 상태 정보를 저장하는 분산 key-value 저장소로, systemd service로 관리하여 자동 재시작 및 부팅 시 자동 시작이 가능하도록 설정했다. 실습 환경에서는 단일 노드로 구성했지만, 프로덕션 환경에서는 고가용성을 위해 3개 이상의 홀수 개수로 클러스터를 구성하고 HTTPS(TLS)를 사용해야 한다.

<br>

<br> 

다음 단계에서는 Kubernetes Control Plane을 구성한다.