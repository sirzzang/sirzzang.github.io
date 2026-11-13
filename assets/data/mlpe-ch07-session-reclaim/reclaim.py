"""세션을 한 번 훑어 판정하고, 회수 대상이면 replicas를 0으로 내린다.

사용: python3 reclaim.py [--idle-limit 초] [--dry-run]
접속 신호는 code-server의 /healthz를 API 서버 프록시로 읽는다. 이 호출은 heartbeat를 올리지 않는다.
GPU 지표는 이 실험에 실제 GPU가 없어 metrics/<세션>.json 파일에서 읽는다.
"""
import argparse
import json
import pathlib
import subprocess
import time
from datetime import datetime

from decide import IDLE_LIMIT, Signals, decide

NS = "sessions"
HERE = pathlib.Path(__file__).parent


def kubectl(*args):
    return subprocess.run(["kubectl", "-n", NS, *args], check=True, capture_output=True, text=True).stdout


def heartbeat(name):
    """(접속 여부, 마지막 heartbeat 시각 초)를 돌려준다. 신호를 못 읽으면 None이다."""
    path = f"/api/v1/namespaces/{NS}/services/{name}:8080/proxy/healthz"
    try:
        body = json.loads(subprocess.run(["kubectl", "get", "--raw", path], check=True, capture_output=True, text=True).stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    return body["status"] == "alive", body["lastHeartbeat"] / 1000


def metrics(name):
    file = HERE / "metrics" / f"{name}.json"
    data = json.loads(file.read_text()) if file.exists() else {}
    return {"gpu_util": data.get("gpu_util", 0), "fb_mib": data.get("fb_mib", 0)}


def pod_started(name):
    pods = json.loads(kubectl("get", "pods", "-l", f"app={name}", "-o", "json"))["items"]
    running = [p for p in pods if p["status"].get("phase") == "Running"]
    if not running:
        return None
    return datetime.fromisoformat(running[0]["status"]["startTime"].replace("Z", "+00:00")).timestamp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idle-limit", type=float, default=IDLE_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deployments = json.loads(kubectl("get", "deploy", "-l", "session=true", "-o", "json"))["items"]
    for deployment in deployments:
        name = deployment["metadata"]["name"]
        if deployment["spec"]["replicas"] == 0:
            continue
        started = pod_started(name)
        if started is None:  # 파드가 아직 뜨지 않았다. GPU를 잡고 있지 않으므로 판정하지 않는다
            print(f"{name:<11} not-running  skip")
            continue
        beat = heartbeat(name)  # code-server의 /healthz에서 접속 여부와 마지막 heartbeat 시각을 읽는다
        if beat is None:  # 신호를 못 읽었다. 활동이 없다는 뜻은 아니므로 회수하지 않고 넘어간다
            print(f"{name:<11} no-signal    skip")
            continue
        connected, last_beat = beat
        idle = time.time() - max(last_beat, started)  # 마지막 접속 흔적과 파드 시작 중 늦은 쪽부터 지난 시간
        signals = Signals(connected=connected, idle_seconds=idle, **metrics(name))
        state, action = decide(signals, args.idle_limit)
        print(f"{name:<11} connected={connected!s:<5} idle={idle:6.0f}s state={state:<17} action={action}")
        if action == "reclaim" and not args.dry_run:
            kubectl("annotate", "deploy", name, "--overwrite", f"session.reclaim/reason={state}", f"session.reclaim/at={int(time.time())}")
            kubectl("scale", "deploy", name, "--replicas=0")
            print(f"{name:<11} reclaimed")


if __name__ == "__main__":
    main()
