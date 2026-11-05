"""dcgmi dmon 기록을 부하별 평균으로 요약한다. 시작과 끝의 5초는 빼고 평균을 낸다.
사용: python3 summarize.py <기록 폴더> <결과 폴더>
기록 폴더: dmon.txt(시각을 앞에 붙인 dmon 출력), phases.txt(시각 start|end 구간 이름), procs.txt(구간 이름 프로세스 수)"""
import csv, pathlib, statistics, sys

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
FIELDS = ["gpu_util", "fb_mib", "power_w", "gr_active", "sm_active"]
TRIM = 5
phases = {}
for line in (src / "phases.txt").read_text().splitlines():
    t, what, name = line.split()
    phases.setdefault(name, {})[what] = int(t)
order = sorted(phases, key=lambda n: phases[n]["start"])
base = phases[order[0]]["start"]
rows = []
for line in (src / "dmon.txt").read_text().splitlines():
    parts = line.split()
    if len(parts) != 3 + len(FIELDS) or parts[1] != "GPU":
        continue
    rows.append((int(parts[0]), [None if v == "N/A" else float(v) for v in parts[3:]]))
procs = dict(l.split() for l in (src / "procs.txt").read_text().splitlines())
with open(dst / "dcgm_1s.csv", "w", newline="") as h:
    w = csv.writer(h, lineterminator="\n")
    w.writerow(["seconds", "phase"] + FIELDS)
    for t, v in rows:
        ph = next((n for n in order if phases[n]["start"] <= t <= phases[n]["end"]), "")
        w.writerow([t - base, ph] + ["" if x is None else x for x in v])
with open(dst / "summary.txt", "w") as out:
    print(f'{"phase":<13}{"sec":>4}{"util%":>7}{"util_max":>9}{"fb_MiB":>8}{"power_W":>9}{"gr_act":>8}{"sm_act":>9}{"procs":>6}', file=out)
    for n in order:
        a, b = phases[n]["start"] + TRIM, phases[n]["end"] - TRIM
        c = [v for t, v in rows if a <= t <= b]
        col = lambda i: [v[i] for v in c if v[i] is not None]
        m = lambda i: statistics.fmean(col(i)) if col(i) else float("nan")
        print(f'{n:<13}{len(c):>4}{m(0):>7.1f}{max(col(0)):>9.0f}{m(1):>8.0f}{m(2):>9.1f}{m(3):>8.3f}{m(4):>9.4f}{procs.get(n, "-"):>6}', file=out)
print((dst / "summary.txt").read_text())
