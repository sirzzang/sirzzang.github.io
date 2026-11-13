"""토이 데이터셋을 만들고 바꾼다. 호스트에서 실행하며, 바뀐 내용은 노드의 /shared 에 바로 보인다.

데이터셋은 <SHARED_DIR>/dataset/{train,val}/ 에 둔다.

사용: python data.py <SHARED_DIR> {reset|edit|edit-train|reorg}
  reset       train 20개, val 8개 파일을 결정적으로 만든다(시드 고정, 파일당 64KiB)
  edit        val 파일 하나의 내용만 바꾼다. 이름과 크기는 그대로다
  edit-train  train 파일 하나의 내용만 바꾼다. 이름과 크기는 그대로다
  reorg       val 디렉터리를 다른 이름으로 옮긴다. 다른 작업이 데이터를 재조직한 상황이다
"""
import os
import random
import shutil
import sys

SIZE = 64 * 1024


def write(path, seed):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(random.Random(seed).randbytes(SIZE))


def main(root, action):
    ds = os.path.join(root, "dataset")
    if action == "reset":
        shutil.rmtree(ds, ignore_errors=True)
        for i in range(20):
            write(os.path.join(ds, "train", f"img_{i:03d}.bin"), seed=i)
        for i in range(8):
            write(os.path.join(ds, "val", f"img_{i:03d}.bin"), seed=1000 + i)
    elif action == "edit":
        write(os.path.join(ds, "val", "img_000.bin"), seed=9999)
    elif action == "edit-train":
        write(os.path.join(ds, "train", "img_000.bin"), seed=8888)
    elif action == "reorg":
        os.rename(os.path.join(ds, "val"), os.path.join(ds, "val_v2"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(*sys.argv[1:3])
