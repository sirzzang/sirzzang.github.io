---
title: "[GenAI] GenAI on K8s: 11.4 - Argo Workflows와 ML 파이프라인 오케스트레이션"
excerpt: "Argo Workflows의 K8s-native DAG 실행, Kubeflow Pipelines와의 레이어 관계, Argo CD와의 책임 분리를 정리해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GenAI
  - Argo-Workflows
  - Argo-CD
  - Kubeflow-Pipelines
  - DAG
  - MLOps
  - Kubernetes-for-Generative-AI-Solutions
  - Kubernetes-for-Generative-AI-Solutions-Chapter-11
use_math: false
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 11장의 학습 내용을 바탕으로 합니다*

<br>

[11.2]({% post_url 2026-06-09-Kubernetes-GenAI-on-K8s-11-02-Kubeflow-Ecosystem %})에서 Kubeflow Pipelines가 Argo Workflows를 백엔드로 쓴다고 했다. 이번 글은 그 **백엔드 자체**인 Argo Workflows와 Argo CD와의 관계, ML·인프라·CI/CD 유스케이스를 정리한다.

<br>

# TL;DR

- **Argo Workflows** = K8s-native 범용 DAG 실행 엔진. 각 step이 Pod, CRD(`Workflow`, `WorkflowTemplate`, `CronWorkflow`)로 정의
- **Kubeflow Pipelines** = Argo 위 ML-specific layer (DSL, artifact tracking, metadata store)
- **Argo CD** = GitOps 상태 reconcile — Workflows와 같은 Argo 패밀리이지만 "절차 실행" vs "상태 동기화"로 책임이 다름
- Argo `parallelism` cap은 **워크플로우 Pod 동시 실행 상한** — Ray task scheduling과는 별 레이어

<br>

# Argo Workflows 개요

K8s-native **범용 워크플로우 엔진**이다. 복잡한 파이프라인을 K8s 환경에서 오케스트레이션한다.

- 워크플로우를 **DAG** 또는 step-by-step 명령으로 정의
- DAG의 각 step이 **K8s Pod**로 실행 → 확장성·fault tolerance 활용
- K8s **CRD**: `Workflow`, `WorkflowTemplate`, `CronWorkflow`
- step 간 artifact passing, parallel task, conditional branch
- **수평 확장** — 수천 워크플로우 동시 오케스트레이션
- 자동 retry, error handling, artifact management, resource monitoring

<br>

# Argo를 내부 엔진으로 쓰는 도구

| 도구 | 사용 방식 |
|---|---|
| **Kubeflow Pipelines** | Pipelines DSL → Argo Workflow 컴파일 실행 |
| **Katib** (옵션) | trial orchestrator로 Argo 선택 가능 |
| **Seldon Core** | 모델 배포 워크플로우 일부 |
| **MLflow Projects** | `mlflow run`을 Argo step으로 오케스트레이션 |

<br>

# Kubeflow Pipelines와의 레이어 관계

같은 백엔드(Argo)를 공유하지만 추상화 레벨과 타깃 사용자가 다르다.

![argo-workflows]({{site.url}}/assets/images/argo-workflows.png)

| 항목 | Argo Workflows | Kubeflow Pipelines |
|---|---|---|
| 카테고리 | 범용 K8s workflow engine | ML 특화 플랫폼 |
| 인터페이스 | YAML / WorkflowTemplate | Python DSL (`@dsl.component`, `@dsl.pipeline`) |
| 타깃 사용자 | 플랫폼/DevOps | 데이터 사이언티스트 |
| ML 통합 | 일반 컨테이너 step | artifact tracking, metadata, metric 시각화 |
| 백엔드 | (본인) | **Argo Workflows** (default) |

Kubeflow Pipelines는 **Argo 위에 ML metadata·UI·SDK를 얹은 layer**. 경쟁이 아니라 **레이어 관계**다.

<br>

# Argo Workflows vs Argo CD

같은 Argo 패밀리이지만 책임이 다르다.

| 도구 | 책임 |
|---|---|
| **Argo Workflows** | step-by-step task DAG 실행. "build → test → deploy" **절차** 자동화 |
| **Argo CD** | GitOps 컨트롤러. Git desired state ↔ K8s actual state **상태 reconcile** |

CI/CD 흐름: Workflows로 빌드·테스트·이미지 푸시 → CD가 Git에 manifest 반영 → Argo CD가 클러스터에 적용. 보완 관계다.

<br>

# 유스케이스

**ML 파이프라인** — 데이터 전처리 → 학습 → 평가 → 배포 DAG. [11.1]({% post_url 2026-06-09-Kubernetes-GenAI-on-K8s-11-01-GenAIOps-Pipeline-and-Monitoring %}) 파이프라인 5단계 중 adaptation·serving 사이를 자동화한다.

**데이터 배치 처리** — ETL, 스케줄된 데이터 sync (`CronWorkflow`)

**인프라 자동화** — EKS 프로비저닝, namespace/RBAC 자동 생성, 테넌트 온보딩

**CI/CD** — 코드 빌드 → 테스트 → 이미지 push → manifest apply

<br>

# parallelism과 Ray scheduling — 레이어 구분

Argo Workflows와 Ray가 같은 클러스터에 있을 때 제한이 겹치는 것처럼 보이지만 **레이어가 다르다**.

| 레이어 | 제한 주체 | 무엇을 제한 |
|---|---|---|
| **Argo** | Workflow spec `parallelism` | 동시 실행 **워크플로우 step Pod** 수 |
| **Ray** | Ray scheduler + autoscaler | task/actor/PG bundle이 **Ray node**에 배치되는 수 |
| **K8s** | Resource quota, scheduler | namespace·노드 단위 Pod/자원 |

Argo step 안에서 Ray cluster를 띄우면, Argo는 "이 step Pod가 떠 있는가"만 관리하고 Ray 내부 task 배치는 Ray scheduler가 담당한다. 병목이 어디인지 분리해서 봐야 한다 — [11.5]({% post_url 2026-06-09-Kubernetes-GenAI-on-K8s-11-05-Ray-KubeRay-and-vLLM-Inference %}) Ray 계층적 스케줄링 참조.

<br>

# 정리

| 영역 | 핵심 |
|---|---|
| **Argo Workflows** | K8s CRD 기반 DAG, step = Pod |
| **vs Pipelines** | Argo = 엔진, Pipelines = ML layer |
| **vs Argo CD** | 절차 실행 vs GitOps reconcile |
| **parallelism** | 워크플로우 Pod cap — Ray task와 별개 |

<br>

# 참고 링크

- [Argo Workflows](https://argo-workflows.readthedocs.io/)
- [Argo CD](https://argo-cd.readthedocs.io/)

<br>
