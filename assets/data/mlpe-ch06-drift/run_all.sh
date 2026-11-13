#!/usr/bin/env bash
# 이 폴더의 results/와 reports/를 다시 만든다.
#   python3.12 -m venv .venv && . .venv/bin/activate
#   pip install -r requirements.txt
#   bash run_all.sh
# SAMA_PARQUET_DIR에 Sama 원본 parquet 폴더를 지정하면 태그 표(data/sama_*.csv)부터 다시 만든다.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
export DO_NOT_TRACK=1   # Evidently 사용 통계 전송 끄기

# 책 저장소에 라이선스 파일이 없어 mock 요청 CSV는 복사하지 않고 고정 커밋에서 받아 쓴다
MOCK_URL=https://raw.githubusercontent.com/practical-mlops/chapter-6/890db04409cb3f48c4e493470d79095ec6ab63d6/bentoml/scripts/mock_request_data.csv
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$MOCK_URL" -o "$tmp/mock_request_data.csv"

mkdir -p results reports
run() { name=$1; shift; echo "== $name"; "$PY" -W ignore "$@" | tee "results/$name.txt"; }

if [ -n "${SAMA_PARQUET_DIR:-}" ]; then
  run 10_sama_schema   code/sama_probe.py "$SAMA_PARQUET_DIR"
  run 11_sama_tags     code/sama_tags.py  "$SAMA_PARQUET_DIR" data/sama_tags.csv
  run 12_sama_objects  code/sama_objects.py   "$SAMA_PARQUET_DIR" data/sama_objects.csv
  run 13_sama_table    code/sama_table.py "$SAMA_PARQUET_DIR" data/sama_frames.csv
fi

# 책 실습 입력(Adult)
run 01_adult_window_sweep code/drift_window.py  data/adult.data
run 02_js_null_and_cost   code/null_and_seq.py  data/adult.data
run 03_small_reference    code/small_ref.py     data/adult.data
run 04_lab_window_first   code/exact_window.py  data/adult.data "$tmp/mock_request_data.csv"
run 05_lab_window_exact   code/exact_window2.py data/adult.data "$tmp/mock_request_data.csv"
run 06_seq_frames_sweep   code/seq_frames_sweep.py
run 07_small_reference_why code/small_ref_why.py data/adult.data
run 08_adult_sweep_direct code/adult_sweep_direct.py data/adult.data
run 08b_consecutive_alarms code/consecutive_alarms.py data/adult.data
run 09_chi_reference_noise code/chi_reference_noise.py data/adult.data
run 09b_evidently_knobs code/evidently_knobs.py data/adult.data

# 주행 태그(Sama)
run 20_sama_drift   code/sama_drift.py  data/sama_frames.csv 40
run 21_sama_fix     code/sama_fix.py    data/sama_frames.csv
run 22_sama_chrono  code/sama_chrono.py data/sama_frames.csv
run 23_sama_fix_splits code/sama_fix_splits.py data/sama_frames.csv
run 24_sama_effective_n code/sama_effective_n.py data/sama_frames.csv
run 25_sama_hirep code/sama_hirep.py data/sama_frames.csv

# 보고서와 대시보드 데이터
run 30_html_reports code/make_html.py data/adult.data data/sama_frames.csv reports
rm -rf reports/ws_driving
run 31_dashboard    code/sama_dashboard.py data/sama_frames.csv reports/ws_driving
