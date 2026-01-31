---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 4.2. 클러스터 배포 - 플레이북 실행"
excerpt: "Kubespray의 cluster.yml 플레이북을 실행해 클러스터를 배포해보자."
categories:
  - Kubernetes
toc: true
hidden: true
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

이번 글에서는 **cluster.yml 플레이북을 실행**해 클러스터를 배포한다.

- **실제 실행**: 약 5분 만에 단일 노드 클러스터 구성 완료
- **실행 결과**: ok=611, changed=138, failed=0

<br>

# 플레이북 실행

## 실행 명령어

```bash
ANSIBLE_FORCE_COLOR=true ansible-playbook -i inventory/mycluster/inventory.ini -v cluster.yml -e kube_version="1.33.3" | tee kubespray_install.log
```

| 옵션 | 설명 |
|------|------|
| `ANSIBLE_FORCE_COLOR=true` | 파이프 출력에서도 컬러 유지 |
| `-i inventory/mycluster/inventory.ini` | 인벤토리 파일 지정 |
| `-v` | verbose 모드 (상세 출력) |
| `-e kube_version="1.33.3"` | Kubernetes 버전 지정 |
| `tee kubespray_install.log` | 화면 출력과 동시에 로그 파일 저장 |

> 일반 사용자로 실행할 경우 `--become` 옵션이 필요하다.
> ```bash
> ANSIBLE_FORCE_COLOR=true ansible-playbook -i inventory/mycluster/inventory.ini -v cluster.yml -e kube_version="1.33.3" --become | tee kubespray_install.log
> ```

<br>

## 실행 결과

<details markdown="1">
<summary>PLAY RECAP 및 시간 분석</summary>

```
PLAY RECAP *********************************************************************
k8s-ctr                    : ok=611  changed=138  unreachable=0    failed=0    skipped=905  rescued=0    ignored=2   

Saturday 31 January 2026  19:30:17 +0900 (0:00:00.032)       0:05:18.926 ****** 
=============================================================================== 
network_plugin/flannel : Flannel | Wait for flannel subnet.env file presence -- 12.18s
download : Download_file | Download item ------------------------------- 10.65s
download : Download_file | Download item -------------------------------- 8.86s
etcd : Restart etcd ----------------------------------------------------- 8.43s
download : Download_container | Download image if required -------------- 8.35s
download : Download_container | Download image if required -------------- 8.31s
download : Download_container | Download image if required -------------- 8.26s
download : Download_container | Download image if required -------------- 8.24s
download : Download_file | Download item -------------------------------- 8.15s
download : Download_container | Download image if required -------------- 8.05s
kubernetes/control-plane : Kubeadm | Initialize first control plane node (1st try) --- 7.32s
system_packages : Manage packages --------------------------------------- 7.24s
download : Download_container | Download image if required -------------- 6.97s
download : Download_container | Download image if required -------------- 6.50s
container-engine/containerd : Download_file | Download item ------------- 6.16s
download : Download_container | Download image if required -------------- 5.95s
download : Download_file | Download item -------------------------------- 5.51s
download : Download_container | Download image if required -------------- 5.44s
etcd : Configure | Check if etcd cluster is healthy --------------------- 5.20s
kubernetes-apps/node_feature_discovery : Node Feature Discovery | Create manifests --- 4.64s
```

</details>

<br>

## 결과 분석

| 항목 | 값 | 설명 |
|------|-----|------|
| ok | 611 | 성공적으로 실행된 태스크 |
| changed | 138 | 시스템 상태를 변경한 태스크 |
| unreachable | 0 | 연결 실패한 호스트 |
| failed | 0 | 실패한 태스크 |
| skipped | 905 | 조건 불일치로 건너뛴 태스크 |
| ignored | 2 | 실패했지만 무시된 태스크 |

**소요 시간**: 약 5분 18초 (단일 노드 기준)

**시간이 많이 소요된 태스크**:
- `download` 관련 태스크들 (바이너리, 이미지 다운로드)
- `Flannel subnet.env` 대기 (CNI 준비)
- `kubeadm init` (컨트롤 플레인 초기화)

<br>

# 결과

이번 글에서 cluster.yml을 실행해 단일 노드 Kubernetes 클러스터를 배포했다.

| 항목 | 내용 |
|------|------|
| 실행 시간 | 약 5분 (단일 노드 기준) |
| 실행 결과 | ok=611, changed=138, failed=0 |
| 주요 소요 | 다운로드, etcd, kubeadm init |

다음 글에서는 배포된 클러스터를 확인하고 검증한다.

<br>

# 참고 자료

- [Kubespray GitHub - cluster.yml](https://github.com/kubernetes-sigs/kubespray/blob/master/cluster.yml)
- [cluster.yml 태스크 구조]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-01 %})
- [이전 글: 인벤토리 구성 및 변수 수정]({% post_url 2026-01-25-Kubernetes-Kubespray-04-01 %})

<br>
