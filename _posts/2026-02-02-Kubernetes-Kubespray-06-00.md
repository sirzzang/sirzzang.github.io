---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 6.0. 노드 관리 - Playbook Overview"
excerpt: "Kubespray의 노드 관리 Playbook(scale.yml, remove-node.yml, reset.yml) 개요"
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Node Management
  - Ansible
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-5

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 5주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Kubespray 노드 관리 Playbook**의 개요를 살펴본다.

- **scale.yml**: 노드 추가 (기존 클러스터 유지, 새 노드만 합류)
- **remove-node.yml**: 노드 제거 (Drain → etcd 제거 → Reset)
- **reset.yml**: 클러스터 전체 초기화 (복구 불가)

<br>

# 노드 관리 Playbook 개요

Kubespray는 클러스터 운영을 위한 전용 Playbook을 제공한다.

| Playbook | 용도 | 설명 |
|----------|------|------|
| `cluster.yml` | 클러스터 생성 | 전체 클러스터 배포 |
| `scale.yml` | 노드 추가 | 새 노드만 프로비저닝 |
| `remove-node.yml` | 노드 제거 | 노드 정리 및 클러스터에서 제거 |
| `reset.yml` | 클러스터 초기화 | k8s 클러스터 전체 제거 |
| `upgrade-cluster.yml` | 클러스터 업그레이드 | Kubernetes 버전 업그레이드 |

## 플레이북 간 관계

```
cluster.yml (클러스터 생성)
    │
    ├── scale.yml (노드 추가)
    │       └── 기존 클러스터에 새 노드 join
    │
    ├── remove-node.yml (노드 제거)
    │       └── 특정 노드 drain → reset → delete
    │
    └── reset.yml (클러스터 초기화)
            └── 전체 클러스터 삭제 (복구 불가)
```

## 사용 시나리오

| 시나리오 | 사용할 Playbook |
|----------|-----------------|
| 워크로드 증가로 워커 노드 확장 | `scale.yml` |
| 노드 교체 (구 노드 제거) | `remove-node.yml` |
| 장애 노드 제거 | `remove-node.yml` |
| 클러스터 재구축 | `reset.yml` → `cluster.yml` |
| 테스트 환경 정리 | `reset.yml` |

<br>

# Playbook 비교 요약

| Playbook | 대상 | 영향 범위 | 복구 가능 |
|----------|------|----------|----------|
| `scale.yml` | 새 노드만 | 기존 클러스터 유지 | - |
| `remove-node.yml` | 지정된 노드 | 해당 노드만 제거 | 노드 재추가 가능 |
| `reset.yml` | 전체 클러스터 | etcd 포함 완전 삭제 | **불가** |

<br>

# 참고 자료

- [Kubespray - Adding/removing a node](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/nodes.md)

<br>
