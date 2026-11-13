# 드리프트 판정과 표본 크기 실험 자료

머신러닝 플랫폼 엔지니어링 스터디 3주차 6.2절(Evidently 데이터 드리프트)을 따라가며 돌린 실험의 코드, 데이터, 결과다. Kubernetes 없이 로컬 Python 환경에서 실행했다. 환경은 Python 3.12, Evidently 0.5.0이다.

책의 실습 환경은 Python 3.10이다. 다만 보안 패치가 포함된 `filelock` 4.2.1 이상은 Python 3.11을 요구해서 3.12로 올렸다. Evidently 쪽 실험은 3.10에 묶여 있지 않다. 3.10과 3.12의 결과는 측정 시간을 빼면 같다.

## 구성

| 경로 | 내용 |
|---|---|
| `run_all.sh` | `results/`와 `reports/`를 다시 만든다 |
| `requirements.txt` | 핵심 패키지 버전 |
| `requirements-lock.txt` | 실행 환경의 전체 패키지 목록 |
| `code/` | 실험 스크립트 |
| `data/` | UCI Adult 원본, Sama 라벨에서 만든 표 |
| `results/` | 스크립트별 실행 출력 |
| `reports/` | Evidently HTML 보고서, 대시보드 캡처, 로컬 workspace |

결과 파일과 스크립트의 대응은 아래와 같다.

| 결과 | 스크립트 | 내용 |
|---|---|---|
| `01_adult_window_sweep` | `drift_window.py` | 같은 분포에서 뽑은 윈도의 크기별 판정 |
| `02_js_null_and_cost` | `null_and_seq.py` | Jensen-Shannon 거리 근사식 대조, 가상 시퀀스 모의, `report.run` 시간 |
| `03_small_reference` | `small_ref.py` | reference를 1000행으로 줄였을 때의 판정 |
| `04_lab_window_first` | `exact_window.py` | 첫 시도. 결측 행을 빼지 않아 실습 입력과 일치하지 않는다 |
| `05_lab_window_exact` | `exact_window2.py` | 실습 mock 요청과 같은 윈도의 판정 |
| `06_seq_frames_sweep` | `seq_frames_sweep.py` | 가상 모의에서 시퀀스당 프레임 수를 바꾼 결과 |
| `07_small_reference_why` | `small_ref_why.py` | reference 1000행에서 Native_country 판정을 reference에 없는 범주 유무로 나눈 결과 |
| `08_adult_sweep_direct` | `adult_sweep_direct.py` | 윈도 판정 5000회, 컬럼 판정 비율과 식, 오경보 5% 윈도, 연속 판정 |
| `08b_consecutive_alarms` | `consecutive_alarms.py` | 겹치지 않는 윈도의 연속 판정, 행 순서 300개 |
| `09_chi_reference_noise` | `chi_reference_noise.py` | chi-square 오경보의 원인과 표본이 클 때의 표 |
| `09b_evidently_knobs` | `evidently_knobs.py` | Evidently 인자의 동작, reference 크기별 데이터셋 판정 |
| `10`~`13` | `sama_probe.py`, `sama_tags.py`, `sama_objects.py`, `sama_table.py` | Sama 라벨 구조 확인과 태그 표 생성 |
| `20_sama_drift` | `sama_drift.py` | 주행 태그 판정. 프레임 무작위, 영상 묶음, 어두운 영상 비중 증가 |
| `21_sama_fix` | `sama_fix.py` | 판정 방식 비교 |
| `22_sama_chrono` | `sama_chrono.py` | 녹화 순서대로 자른 배치의 판정 |
| `23_sama_fix_splits` | `sama_fix_splits.py` | 판정 방식을 같은 분할 100개에서 비교한 결과 |
| `24_sama_effective_n` | `sama_effective_n.py` | 태그별 유효 표본 수 |
| `25_sama_hirep` | `sama_hirep.py` | 주행 태그 판정 5000회, 연속 구간, 녹화 순서의 재표본 임곗값 |
| `30_html_reports` | `make_html.py` | HTML 보고서 생성 |
| `31_dashboard` | `sama_dashboard.py` | 로컬 workspace 생성 |

## 다시 돌리기

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
bash run_all.sh
```

`SAMA_PARQUET_DIR`에 원본 parquet 폴더를 지정하면 `data/sama_*.csv`도 다시 만든다. 대시보드는 아래 명령으로 띄운다.

```bash
evidently ui --workspace reports/ws_driving --port 8100
```

## 결과 요약

### 책 실습 입력(Adult)

실습의 mock 요청 100행은 결측 행을 뺀 Adult의 앞 100행과 일치한다. reference를 결측 제외 전체 30,162행으로 두면 드리프트 컬럼 비율 0.5가 나오고, 앞 50행 윈도에서는 0.875가 나온다. 실습의 실제 reference 설정을 본 것은 아니다.

아래 표는 reference 32,561행과 같은 데이터에서 뽑은 윈도를 크기별로 5000회씩 판정한 결과다(`08`). 분포 변화가 없으므로 드리프트 판정은 전부 오경보다. Evidently로 40회 돌린 값은 `01`에 있다.

| 윈도 크기 | 드리프트 컬럼 비율 평균 | 5~95% 범위 | 데이터셋 드리프트 판정 비율 |
|---|---|---|---|
| 50 | 0.703 | 0.5~0.875 | 98.4% |
| 100 | 0.468 | 0.25~0.625 | 56.8% |
| 200 | 0.234 | 0.125~0.375 | 1.3% |
| 500 | 0.099 | 0~0.125 | 0% |
| 1000 이상 | 0 | 0 | 0% |

- reference가 1000행을 넘으면 범주형 컬럼은 Jensen-Shannon 거리 0.1로 판정한다. 윈도 크기는 이 판정에 반영되지 않는다.
- 같은 분포에서 거리의 크기는 약 `sqrt((k-1)/(8n))`이다(k는 범주 수, n은 윈도 크기). Education(k=16), n=200에서 모의 0.101, 식 0.097이다. 1% 미만 범주가 많은 Native_country는 n이 작을 때 식이 실제보다 크다.
- 컬럼 판정 비율은 `P(chi2(k-1) >= 0.08n)`으로 어림할 수 있다. 오경보 5% 윈도는 식으로 Education 312, 측정 350이다.
- reference를 유지하고 `stattest="chisquare"`만 주면 데이터셋 오경보는 1% 아래다. reference를 1000행으로 줄이면 기본 규칙이 chi-square를 고르고, 데이터셋 오경보는 1.7%, 5.7%, 9.0%로 윈도가 커질수록 는다(`09b`). 기대 빈도를 reference 표본 비율로 만들기 때문이다(`09`).
- 표본이 크면 두 표본 chi-square는 작은 변화까지 유의하다고 답한다. 0.5%p 변화가 n=100만에서 p 중앙값 2.3e-62이고 Jensen-Shannon 거리는 0.0086이다.
- 책의 보고서 구성으로 잰 `report.run` 중앙값은 reference 32,561행에서 약 400ms, 1000행에서 약 40ms다. 값은 실행마다 조금씩 다르다.

### 주행 태그(Sama)

프레임 1행 표의 컬럼은 아래와 같다. 마지막 열은 영상 171개 중 영상 내내 같은 값인 영상의 비율이다. `timeofday`, `weather`는 원본 라벨이고 나머지는 객체 라벨에서 만든 파생 컬럼이다.

| 컬럼 | 값 수 | 영상 내내 같은 값 |
|---|---|---|
| `timeofday` | 3 | 1.00 |
| `weather` | 4 | 1.00 |
| `pedestrian` | 2 | 0.81 |
| `opposite_lane` | 2 | 0.54 |
| `traffic_light` | 2 | 0.53 |
| `traffic` | 4 | 0.43 |
| `vehicles` | 4 | 0.04 |
| `sign` | 2 | 0.02 |

아래 표는 분포를 바꾸지 않은 배치의 판정이다. Evidently 기본값과 같은 거리를 직접 계산했고, 영상 묶음은 5000회, 프레임 무작위는 1000회 뽑았다(`25`). 비율은 드리프트로 판정된 횟수의 비율이다. Evidently로 40회 돌린 값은 `20`에 있다.

| 배치 구성 | 프레임 수 | 데이터셋 판정 | `weather` 컬럼 판정 |
|---|---|---|---|
| 프레임 무작위 추출 | 1,470 | 0% | 0% |
| 영상 10개 | 1,471 | 57% | 95% |
| 프레임 무작위 추출 | 2,940 | 0% | 0% |
| 영상 20개 | 2,940 | 15% | 76% |
| 영상 40개 | 5,878 | 2% | 63% |

프레임 수가 같아도 영상으로 묶으면 오경보가 난다. 영상 단위로 고정되는 태그의 표본 수는 영상을 섞은 조건에서 영상 수에 가깝고, 프레임마다 바뀌는 태그도 프레임 수보다 훨씬 작다(`24`). 녹화 순서의 연속 구간은 영상을 네 배로 늘려도 평균 거리가 거의 줄지 않는다(`25`).

실제 변화에 대한 결과는 다음과 같다.

- 녹화 순서대로 자른 배치에서 밤으로 갈수록 `timeofday` 거리가 0.05에서 0.83까지 오른다.
- 어두운 프레임을 63%까지 늘린 배치에서 `timeofday` 컬럼은 기본값으로 100% 판정됐지만 데이터셋 판정은 48%였다. 태그 하나의 변화는 컬럼 절반 기준에 잘 드러나지 않는다.

아래 표는 영상 20개 배치의 `timeofday` 판정 비율이다. 영상을 무작위로 절반씩 나눈 분할 100개의 평균이고 reference는 약 85개다(`23`). 변화 없음 열이 오경보다.

| 판정 방식 | 변화 없음 | 어두운 영상 30% | 어두운 영상 50% |
|---|---|---|---|
| 기본값, 프레임 그대로 | 65% | 96% | 100% |
| chi-square, 프레임 그대로 | 98% | - | - |
| 영상당 1행, Evidently chi-square | 14% | 62% | 100% |
| 영상당 1행, 두 표본 chi-square | 6% | 27% | 100% |
| 영상 재표본 임곗값 | 4% | 9% | 90% |

재표본 임곗값은 95번째 백분위수라 오경보가 설계상 약 5%다. `21_sama_fix`는 층화한 한 번의 분할로 먼저 재 본 값이다.

## 해석할 때 주의할 점

- 분포를 바꾸지 않은 배치는 영상을 무작위로 섞어 만들었다. 원본은 차 한 대의 연속 주행이라 영상 번호가 녹화 순서이고, 이웃한 영상은 조건을 공유한다. 실제로 연속으로 들어오는 배치는 `25`의 연속 구간에 가깝다.
- 대시보드의 날짜 축은 배치 순서를 나타내려고 넣은 값이다.
- `null_and_seq.py`의 시퀀스 모의는 가상 분포를 쓴다. 주행 데이터 실측(`20`, `21`)이 같은 내용을 실제 데이터로 보여 준다.
- 책의 서비스 코드와 대시보드 스크립트는 실행하지 않았다.

## 데이터와 라이선스

| 파일 | 출처 | 라이선스 |
|---|---|---|
| `data/adult.data` | Becker, B. & Kohavi, R. (1996). Adult [Dataset]. UCI Machine Learning Repository. <https://doi.org/10.24432/C5XW20> | CC BY 4.0 |
| `data/sama_frames.csv`, `data/sama_tags.csv`, `data/sama_objects.csv` | [Sama Drives California](https://huggingface.co/datasets/SamaAI/sama-drives-california), revision `5aad23e6089ca8a5a1ab0805cdb2aef272cca3df`의 라벨에서 만든 표. 이미지는 포함하지 않는다 | CC BY 4.0 |

`data/sama_*.csv`는 원본을 변경한 파생 자료다. 변경 내용은 `code/sama_tags.py`, `code/sama_objects.py`, `code/sama_table.py`에 있다.

원본 파일의 SHA-256은 아래와 같다.

```text
5b00264637dbfec36bdeaab5676b0b309ff9eb788d63554ca0a249491c86603d  adult.data
a212ec31f9585a6712cd2b7f08deb0fd6a713f5912db5090362341f3268b5632  train-00000-of-00003-b33e74c98af8a743.parquet
d4d1474a25e8748899a4923557c1d647000b146cc051353bcbe0ab286d5053fa  train-00001-of-00003-d896a89dc0ef6ec1.parquet
aa626a4b94e5610597fa65e592946dff221e5af5e919abd940bbee87adbdc6dd  train-00002-of-00003-1f03856c16fc7751.parquet
```

## 포함하지 않은 것

- **Sama 원본 parquet:** 약 1GB이고 파일 하나가 238~441MB라 GitHub의 파일 크기 제한을 넘는다. 위 주소와 해시로 받을 수 있다.
- **책 저장소의 코드와 mock 요청 CSV:** [practical-mlops/chapter-6](https://github.com/practical-mlops/chapter-6)에 라이선스 파일이 없어 복사하지 않았다. `run_all.sh`가 커밋 `890db04`에서 CSV를 받아 쓴다.
- **스터디 자료의 본문과 캡처.**
