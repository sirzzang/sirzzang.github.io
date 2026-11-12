"""내용 다이제스트를 계산하는 비용.

(1) 1 GiB 파일 하나의 SHA-256
(2) 64 KiB 파일 16,384개(합 1 GiB)의 내용 다이제스트(파이프라인과 같은 방식)
(3) 같은 16,384개의 크기·수정 시각만 모은 다이제스트(내용을 읽지 않음)
파일을 만든 직후 읽으므로 운영체제의 페이지 캐시에 있을 가능성이 크다. 저장소 읽기를 뺀 계산 비용에 가깝고,
네트워크 스토리지라면 읽기 대역폭과 파일 열기·목록 조회 비용이 더해진다.
"""
import hashlib
import os
import tempfile
import time

CHUNK = 8 << 20


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.digest()


def content_digest(root):
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(str(os.path.getsize(p)).encode())
            h.update(sha_file(p))
    return h.hexdigest()


def stat_digest(root):
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            st = os.stat(os.path.join(d, f))
            h.update(f"{os.path.relpath(os.path.join(d, f), root)}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()


def timed(fn, *a):
    t = time.perf_counter()
    fn(*a)
    return time.perf_counter() - t


with tempfile.TemporaryDirectory() as tmp:
    big = os.path.join(tmp, "big.bin")
    with open(big, "wb") as f:
        for _ in range((1 << 30) // CHUNK):
            f.write(os.urandom(CHUNK))
    for i in range(3):
        dt = timed(sha_file, big)
        print(f"(1) 1 GiB 파일 1개 SHA-256 시도 {i + 1}: {dt:.2f}초 ({1024 / dt:.0f} MiB/s)")
    os.remove(big)

    small = os.path.join(tmp, "small")
    for i in range(16384):
        sub = os.path.join(small, f"d{i // 1024:02d}")
        os.makedirs(sub, exist_ok=True)
        open(os.path.join(sub, f"f{i:05d}.bin"), "wb").write(os.urandom(64 * 1024))
    for i in range(3):
        print(f"(2) 64 KiB 파일 16,384개 내용 다이제스트 시도 {i + 1}: {timed(content_digest, small):.2f}초")
    for i in range(3):
        print(f"(3) 같은 파일들의 크기·수정 시각 다이제스트 시도 {i + 1}: {timed(stat_digest, small):.3f}초")
