# GPU 개발 세션 회수 실험 자료

쿠버네티스에서 GPU를 잡은 개발 세션을 실제로 돌려받을 수 있는지 확인한 코드와 결과다. 머신러닝 플랫폼 엔지니어링 스터디 3주차 7.1절의 "유휴 상태일 때 파드를 종료하는 규칙"에서 출발했다.

| 단계 | 질문 | 환경 |
|---|---|---|
| 1 | 세션을 내리면 GPU가 돌아오고 대기 세션이 뜨는가 | kind, 가짜 GPU 1장, code-server |
| 2 | GPU 지표는 실제 부하를 어떻게 보여 주는가 | AWS EC2 `g5.xlarge`(NVIDIA A10G 1장), DCGM 4.7.1 |
| 3 | 오픈소스 도구 Coder에서는 어떻게 되는가 | kind, 가짜 GPU 1장, Coder v2.36.0 |

## 구성

| 경로 | 내용 |
|---|---|
| `decide.py` | 회수 판정 함수. 직접 실행하면 규칙을 검사한다 |
| `reclaim.py` | 세션을 훑어 판정하고 replicas를 0으로 내린다 |
| `session.yaml` | 세션 매니페스트(Deployment, 홈 PVC, Service) |
| `kind.yaml`, `run_stage1.sh` | 단계 1의 클러스터 설정과 시나리오 |
| `gpu/` | 단계 2의 요약 스크립트와 측정값 |
| `coder/` | 단계 3의 템플릿, 설치 스크립트, 시나리오 |
| `results/` | 단계 1, 3의 실행 로그 |

## 다시 돌리기

단계 1은 아래처럼 돌린다. 시나리오 5는 실제 브라우저 접속을 쓰므로 `CHROME`에 Chrome 실행 파일을 지정한다.

```bash
kind create cluster --config kind.yaml --kubeconfig ./kubeconfig
KUBECONFIG=$PWD/kubeconfig bash run_stage1.sh | tee results/stage1.txt
```

`--kubeconfig`를 주지 않으면 `kind`가 기본 kubeconfig의 현재 컨텍스트를 바꾼다.

단계 2는 AWS EC2 서울 리전의 `g5.xlarge`에서 돌렸다. AMI는 `Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04)`이고 드라이버와 PyTorch가 포함돼 있다. 부하 스크립트는 올리지 않았다. 부하가 하는 일은 아래 결과 표와 7.1.3편에 적었다.

```bash
sudo apt-get install -y datacenter-gpu-manager-4-cuda12
sudo systemctl start nvidia-dcgm
dcgmi dmon -i 0 -e 203,252,155,1001,1002 -d 1000
python3 gpu/summarize.py <기록 폴더> gpu/results
```

기록 폴더 원본(`dmon.txt`, `phases.txt`, `procs.txt`)은 올리지 않았고 산출물 `dcgm_1s.csv`와 `summary.txt`만 `gpu/results`에 있다.

단계 3은 다른 세션이 GPU를 잡고 있지 않은 클러스터에서 돌린다. 템플릿의 `arch`는 노드 아키텍처에 맞춘다.

```bash
KUBECONFIG=$PWD/kubeconfig bash coder/install.sh
kubectl -n coder port-forward svc/coder 3000:80 &
curl -o coder-cli http://127.0.0.1:3000/bin/coder-darwin-arm64 && chmod +x coder-cli
CODER_BIN=$PWD/coder-cli python3 coder/run_stage3.py
```

## 결과 요약

### 단계 1: 세션 회수

GPU 1장을 두고 세션 두 개를 경쟁시킨 결과다. 시나리오마다 한 번 돌렸다. 전체 로그는 `results/stage1.txt`에 있다.

| 시나리오 | 결과 |
|---|---|
| 1. 세션 A가 GPU를 잡음 | 세션 B는 `Insufficient nvidia.com/gpu`로 Pending |
| 2. A에 접속 없음, 지표 0 | A가 회수되고 몇 초 안에 B가 Running |
| 3. A를 다시 올림 | B가 있는 동안 Pending. 사용률 100%지만 메모리가 빈 B(phantom)가 회수되면 A가 Running. 홈 파일은 남고 `/tmp` 파일은 사라짐 |
| 4a. 대기 세션 없이 파드만 삭제 | 새 파드가 GPU를 다시 잡음 |
| 4b. 대기 세션이 있을 때 파드만 삭제 | 이번 실행에서는 대기하던 B가 GPU를 받고 A의 새 파드가 Pending. 어느 쪽이 먼저 받는지는 보장되지 않는다 |
| 5. 브라우저 접속만 유지, 지표 0 | heartbeat가 약 60초마다 갱신됨. 판정 규칙이 접속을 유지로 보므로 회수되지 않음. 브라우저를 닫으면 기준 시간 뒤 회수 |

파드만 지우면 Deployment가 남아 GPU를 다시 요구한다.

### 단계 2: GPU 지표

AWS EC2 `g5.xlarge`의 NVIDIA A10G 1장(SM 80개, 전력 상한 300W, 드라이버 580.126.09)에 부하를 120초씩 걸고 DCGM 4.7.1 지표를 1초 간격으로 기록했다. 한 번 돌린 값이고 부하 순서는 고정이다. 값은 시작과 끝 5초를 뺀 평균이고, GPU 프로세스 수는 부하마다 한 번 읽은 값이다. 1초 단위 값은 `gpu/results/dcgm_1s.csv`에 있다. 부하 스크립트는 올리지 않았다.

| 부하 | 사용률 | 메모리 | 전력 | `GR_ENGINE_ACTIVE` | `SM_ACTIVE` | GPU 프로세스 |
|---|---|---|---|---|---|---|
| 아무것도 돌리지 않음 | 0% | 0MiB | 24.3W | 0.000 | 0.000 | - |
| 메모리만 잡고 대기 | 0% | 19,376MiB | 89.1W | 0.000 | 0.000 | 1 |
| 스레드 하나짜리 커널 반복 | 100% | 302MiB | 90.0W | 1.000 | 0.012 | 1 |
| 큰 행렬곱 반복 | 100% | 850MiB | 299.2W | 1.000 | 0.984 | 1 |

- 스레드 하나짜리 커널과 큰 행렬곱은 사용률과 `GR_ENGINE_ACTIVE`가 같다. `SM_ACTIVE`는 값이 갈린다. 0.012는 SM 80개 중 한 개의 몫(0.0125)에 가깝다.
- 메모리만 잡은 프로세스는 사용률로는 유휴로 보이고 메모리로는 쓰는 중으로 보인다.
- 이 GPU에서 2분 동안은 프로세스가 GPU를 잡고 있는 것만으로 전력이 유휴보다 높았다. 클럭은 기록하지 않아 원인은 확인하지 않았다.

### 단계 3: Coder

GPU 1장을 두고 일반 사용자 두 명의 세션을 경쟁시킨 결과다. 로그는 `results/stage3_part1.txt`, `results/stage3_part2.txt`에 있다.

| 시나리오 | 결과 |
|---|---|
| 1. 두 번째 세션 시작 | 파드는 Pending이지만 빌드는 succeeded, 빌드 상태(`latest_build.status`)는 `running` |
| 2. 다른 사용자의 세션 정지 | 일반 사용자는 `404`, owner는 `201`. 정지 뒤 대기 세션이 Running |
| 3. 정지 뒤 다시 시작 | 홈 파일은 남고 `/tmp` 파일은 사라짐 |
| 4a. 대기 세션 없이 파드만 삭제 | 새 파드가 뜨고 세션 상태는 그대로 |
| 4b. 대기 세션이 있을 때 파드만 삭제 | 이번 실행에서는 대기 세션이 GPU를 받음. 지운 세션은 파드가 Pending인 채 상태는 `running` |
| 5. 접속만 유지 | `last_used_at`이 약 60초마다 갱신 |
| 6. 백그라운드 `sleep`을 남기고 접속 끊기 | 끊은 뒤 두 번 더 갱신되고 약 80초 뒤부터 멈춤 |
| 7. 템플릿 자동 정지 시간 변경 | 기존 세션에는 재시작 뒤에도 적용되지 않음. 새 세션은 적용되지만 사용자가 연장(`200`)도 끄기(`204`)도 할 수 있음 |

정지는 세션 도구의 API로 해야 Coder의 기록과 쿠버네티스 상태가 맞는다. 위 시나리오 7은 오픈소스 기능 범위의 결과다.

## 해석할 때 주의할 점

- 단계 1, 3의 GPU는 확장 리소스로 광고한 가짜다. 스케줄러의 배정과 반납은 실제와 같지만, 장치 할당은 일어나지 않는다.
- 단계 1의 GPU 지표는 `metrics/` 파일로 주입했다. phantom 상태를 재현한 것이 아니라 판정 로직만 시험했다. `decide.py`는 로그를 남긴 뒤 실험에 쓴 규칙만 남겼다. 로그의 시나리오에서 판정 결과는 같고, 지표 파일의 `sm_active`, `cpu_cores`는 지금 코드가 읽지 않는다. 지표 파일이 없는 세션은 0으로 처리되며, 못 읽은 경우를 나눠 구현하지는 않았다.
- 단계 1의 유휴 기준 90초는 실험용이다. `decide.py`의 임곗값도 시작값이며 권장값이 아니다.
- 단계 2는 GPU 한 장의 한 번 측정이고 부하 순서는 고정이다. `SM_ACTIVE` 같은 프로파일링 지표는 나오지 않는 기종이 있다.
- 단계 3의 "stop 요청부터 Ready까지"는 대부분 빌드 시간이다. 같은 로그의 다른 빌드도 약 135~143초였다. 회수 지연의 기준값이 아니다.
- `results/stage3_part2.txt`의 시나리오 7 제목은 실행 뒤 문구만 고쳤다.
- 단계 3은 시나리오 5에서 스크립트 버그로 멈춰, 고친 뒤 나머지를 돌렸다. 그래서 로그가 두 파일이고, `RESUME_AT_5=1`은 그때 쓴 옵션이다.
