"""Coder에서 세션 회수 시나리오를 돌린다. 표준 라이브러리만 쓰고 토큰은 출력하지 않는다.

전제: install.sh를 돌렸고, 127.0.0.1:3000이 서버로 이어져 있으며, 노드에 가짜 GPU 1장이 있고 다른 세션이 GPU를 잡고 있지 않다.
사용: CODER_BIN=<coder CLI 경로> python3 run_stage3.py
"""
import json
import os
import pathlib
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "http://127.0.0.1:3000"
IN_CLUSTER_URL = "http://coder.coder.svc.cluster.local"
NS = "coder"
PASSWORD = "Local-experiment-only-1!"
HERE = pathlib.Path(__file__).parent


def say(text):
    print(f"\n=== [{datetime.now():%H:%M:%S}] {text}", flush=True)


def call(method, path, token=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        request.add_header("Coder-Session-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode()
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as error:
        text = error.read().decode()
        try:
            return error.code, json.loads(text)
        except json.JSONDecodeError:
            return error.code, {"message": text[:200]}


def ok(result):
    status, body = result
    assert status < 300, (status, body)
    return body


def kubectl(*args, check=True):
    done = subprocess.run(["kubectl", "-n", NS, *args], capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError(done.stderr[:400])
    return done.stdout.strip()


def session_pods():
    lines = kubectl("get", "pods", "--no-headers", "-o", "custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready", check=False)
    return [line.split() for line in lines.splitlines() if line.startswith("coder-user")]


def show_pods():
    for pod in session_pods():
        print("  pod", *pod)
    if not session_pods():
        print("  pod 없음")


def ws_get(token, workspace):
    return ok(call("GET", f"/api/v2/workspaces/{workspace['id']}", token))


def wait_build(token, workspace):
    for _ in range(180):
        current = ws_get(token, workspace)
        job = current["latest_build"]["job"]["status"]
        if job in ("succeeded", "failed", "canceled"):
            assert job == "succeeded", current["latest_build"]["job"]
            return current
        time.sleep(1)
    raise TimeoutError("build")


def wait_running(name, seconds=180):
    for _ in range(seconds):
        rows = [p for p in session_pods() if name in p[0] and p[1] == "Running" and p[2] == "true"]
        if rows:
            return rows[0][0]
        time.sleep(1)
    raise TimeoutError(name)


def build(token, workspace, transition):
    return call("POST", f"/api/v2/workspaces/{workspace['id']}/builds", token, {"transition": transition})


def age(timestamp):
    """지금으로부터 몇 초 전인지 돌려준다. 소수 초의 자릿수가 일정하지 않아 버린다."""
    value = datetime.fromisoformat(timestamp.split(".")[0].rstrip("Z")).replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - value).total_seconds()


def main():
    say("준비: 계정 세 개와 템플릿")
    call("POST", "/api/v2/users/first", None, {"email": "owner@example.com", "username": "owner", "password": PASSWORD, "name": "owner", "trial": False})  # 다시 돌릴 때는 이미 있다
    owner = ok(call("POST", "/api/v2/users/login", None, {"email": "owner@example.com", "password": PASSWORD}))["session_token"]
    org = ok(call("GET", "/api/v2/users/me", owner))["organization_ids"][0]
    tokens = {}
    for name in ("usera", "userb"):
        call("POST", "/api/v2/users", owner, {"email": f"{name}@example.com", "username": name, "password": PASSWORD, "login_type": "password", "organization_ids": [org]})
        tokens[name] = ok(call("POST", "/api/v2/users/login", None, {"email": f"{name}@example.com", "password": PASSWORD}))["session_token"]
    version = ok(call("GET", "/api/v2/buildinfo"))["version"]
    print("server version", version)
    env = {**os.environ, "CODER_URL": URL, "CODER_SESSION_TOKEN": owner}
    resume = os.environ.get("RESUME_AT_5") == "1"
    for attempt in range(1, 4):  # 프로바이더 내려받기가 일시적으로 실패할 수 있다
        if resume:
            break
        push = subprocess.run([os.environ["CODER_BIN"], "templates", "push", "gpu-session", "-d", str(HERE / "template"), "--yes"], env=env, capture_output=True, text=True)
        if push.returncode == 0:
            break
        print("template push failed, attempt", attempt, flush=True)
    if not resume:
        assert push.returncode == 0, push.stderr[-800:]
        print("template pushed")
    template = ok(call("GET", f"/api/v2/organizations/{org}/templates/gpu-session", owner))

    def create(user, name):
        return ok(call("POST", "/api/v2/users/me/workspaces", tokens[user], {"name": name, "template_id": template["id"]}))

    deploy_a = "deploy/coder-usera-ws-a"
    if resume:  # 시나리오 5부터 이어서 돌린다
        ws_a = ok(call("GET", "/api/v2/users/usera/workspace/ws-a", tokens["usera"]))
        ws_b = ok(call("GET", "/api/v2/users/userb/workspace/ws-b", tokens["userb"]))
    else:
        say("시나리오 1: 사용자 A의 세션이 GPU를 잡으면 사용자 B의 세션은 파드가 대기한다")
        ws_a = wait_build(tokens["usera"], create("usera", "ws-a"))
        pod_a = wait_running("usera-ws-a")
        deploy_a = "deploy/coder-usera-ws-a"
        kubectl("exec", deploy_a, "--", "sh", "-c", "echo keep > /home/coder/keep.txt; echo gone > /tmp/gone.txt")
        ws_b = wait_build(tokens["userb"], create("userb", "ws-b"))
        print("  B 빌드:", ws_b["latest_build"]["transition"], ws_b["latest_build"]["job"]["status"], "/ 워크스페이스 상태:", ws_b["latest_build"]["status"])
        time.sleep(5)
        show_pods()

        say("시나리오 2: 권한 확인. 사용자 B는 A의 세션을 멈추지 못하고 owner는 멈출 수 있다")
        status, body = build(tokens["userb"], ws_a, "stop")
        print("  사용자 B의 stop:", status, str(body.get("message"))[:80])
        start = time.time()
        status, body = build(owner, ws_a, "stop")
        print("  owner의 stop:", status, "initiator:", body.get("initiator_name"), "reason:", body.get("reason"))
        wait_build(owner, ws_a)
        pod_b = wait_running("userb-ws-b")
        print(f"  stop 요청부터 B 파드 Ready까지 {time.time() - start:.0f}초")
        show_pods()
        print("  PVC:", kubectl("get", "pvc", "--no-headers", "-o", "custom-columns=NAME:.metadata.name,STATUS:.status.phase").replace("\n", " | "))

        say("시나리오 3: B를 멈추고 A를 다시 시작한다. 홈은 남고 /tmp는 사라지는가")
        ok(build(owner, ws_b, "stop"))
        wait_build(owner, ws_b)
        ok(build(tokens["usera"], ws_a, "start"))
        wait_build(tokens["usera"], ws_a)
        wait_running("usera-ws-a")
        print("  ", kubectl("exec", deploy_a, "--", "sh", "-c", "echo home=$(cat /home/coder/keep.txt); echo tmp=$(cat /tmp/gone.txt 2>&1)"))

        say("시나리오 4a: 대기 세션이 없을 때 파드를 지운다")
        before = wait_running("usera-ws-a")
        kubectl("delete", "pod", before, "--wait=true")
        after = wait_running("usera-ws-a")
        print("  파드 이름이 바뀌었다:", before != after, "/ 워크스페이스 상태:", ws_get(tokens["usera"], ws_a)["latest_build"]["status"])

        say("시나리오 4b: 대기 세션이 있을 때 파드를 지운다")
        ok(build(tokens["userb"], ws_b, "start"))
        wait_build(tokens["userb"], ws_b)
        time.sleep(5)
        show_pods()
        kubectl("delete", "pod", wait_running("usera-ws-a"), "--wait=true")
        time.sleep(30)
        show_pods()
        print("  A 상태:", ws_get(tokens["usera"], ws_a)["latest_build"]["status"], "/ B 상태:", ws_get(tokens["userb"], ws_b)["latest_build"]["status"])
        ok(build(owner, ws_b, "stop"))
        wait_build(owner, ws_b)
        wait_running("usera-ws-a")

    say("시나리오 5: 접속만 열어 둔다. last_used_at이 갱신되는가")
    subprocess.run(["kubectl", "-n", NS, "run", "client", "--image=ghcr.io/coder/coder:v2.36.0", "--restart=Never", "--image-pull-policy=IfNotPresent", "--command", "--", "sleep", "3600"], capture_output=True)
    subprocess.run(["kubectl", "-n", NS, "wait", "--for=condition=Ready", "pod/client", "--timeout=120s"], check=True, capture_output=True)
    prefix = f"CODER_URL={IN_CLUSTER_URL} CODER_SESSION_TOKEN={tokens['usera']} /opt/coder"
    print("  접속 전 last_used_at 경과", round(age(ws_get(tokens["usera"], ws_a)["last_used_at"])), "초")
    ssh = subprocess.Popen(["kubectl", "-n", NS, "exec", "client", "--", "sh", "-c", f"{prefix} ssh ws-a -- sleep 170"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(5):
        time.sleep(30)
        current = ws_get(tokens["usera"], ws_a)
        print("  접속 중 last_used_at 경과", round(age(current["last_used_at"])), "초")
    ssh.wait(timeout=60)

    say("시나리오 6: 백그라운드 작업을 남기고 접속을 끊는다. last_used_at이 멈추는가")
    subprocess.run(["kubectl", "-n", NS, "exec", "client", "--", "sh", "-c", f"{prefix} ssh ws-a -- 'nohup sleep 600 >/dev/null 2>&1 &'"], capture_output=True, timeout=120)
    print("  세션 안 sleep 프로세스 수:", kubectl("exec", deploy_a, "--", "sh", "-c", "pgrep -c sleep || true"))
    for _ in range(10):
        time.sleep(30)
        print("  접속 끊긴 뒤 last_used_at 경과", round(age(ws_get(tokens["usera"], ws_a)["last_used_at"])), "초")

    say("시나리오 7: 템플릿 자동 정지 시간은 기존 세션에 적용되는가, 사용자가 바꿀 수 있는가")

    def schedule(token, workspace):
        current = ws_get(token, workspace)
        deadline = current["latest_build"].get("deadline")
        left = "없음" if not deadline else f"{round(-age(deadline) / 60)}분 뒤"
        return f"ttl_ms={current.get('ttl_ms')} deadline={left}"

    ok(call("PATCH", f"/api/v2/templates/{template['id']}", owner, {"default_ttl_ms": 3_600_000, "activity_bump_ms": 3_600_000}))
    print("  템플릿 변경 직후 기존 세션:", schedule(tokens["usera"], ws_a))
    ok(build(owner, ws_a, "stop"))
    wait_build(owner, ws_a)
    ok(build(tokens["usera"], ws_a, "start"))
    wait_build(tokens["usera"], ws_a)
    time.sleep(3)
    print("  재시작 뒤 기존 세션:", schedule(tokens["usera"], ws_a))
    ws_c = wait_build(tokens["userb"], create("userb", "ws-c"))
    time.sleep(3)
    print("  템플릿 변경 뒤 만든 세션:", schedule(tokens["userb"], ws_c))
    wanted = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    status, body = call("PUT", f"/api/v2/workspaces/{ws_c['id']}/extend", tokens["userb"], {"deadline": wanted})
    print("  사용자의 연장(3시간 뒤로):", status, str(body.get("message"))[:90])
    print("  연장 뒤:", schedule(tokens["userb"], ws_c))
    status, body = call("PUT", f"/api/v2/workspaces/{ws_c['id']}/ttl", tokens["userb"], {"ttl_ms": None})
    print("  사용자의 자동 정지 끄기:", status, str(body.get("message"))[:90])
    print("  끈 뒤:", schedule(tokens["userb"], ws_c))


if __name__ == "__main__":
    main()
