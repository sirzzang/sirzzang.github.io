---
title:  "[Kubernetes] ConfigMap 볼륨 마운트와 inode: kubelet atomic_writer 딥다이브"
excerpt: "ConfigMap 볼륨 마운트가 subPath 유무에 따라 업데이트 반영에서 정반대로 동작하는 이유를 kubelet atomic_writer 코드와 bind mount의 inode 관점에서 파헤쳐 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - ConfigMap
  - subPath
  - kubelet
  - atomic-writer
  - bind mount
  - inode
  - inotify
---

<br>

ConfigMap을 파드에 볼륨으로 마운트하는 두 방식 — **subPath 없는 일반 마운트**와 **subPath 마운트** — 은 업데이트 반영에서 정반대로 동작한다. subPath 없는 일반 마운트는 파드 재시작 없이 자동 반영되는 반면, subPath 마운트는 파드를 다시 띄우지 않으면 영영 옛날 값을 본다. [Kubernetes 공식 문서](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#mounted-configmaps-are-updated-automatically)도 이 점을 명시한다.

> A container using a ConfigMap as a subPath volume mount will not receive ConfigMap updates.

이 글에서는 그 차이가 어디서 오는지를 kubelet의 [`atomic_writer.go`](https://github.com/kubernetes/kubernetes/blob/master/pkg/volume/util/atomic_writer.go) 동작과 bind mount의 inode 의미를 따라 파고든다. 마지막으로, 같은 inode 원리가 다른 문맥에서 어떻게 나타나는지 — 과거에 겪었던 [Docker 타임존 동기화 문제]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}) 와의 접점을 짧게 짚는다.

> ConfigMap의 기본 개념(생성·환경 변수 주입·`immutable` 등)은 [어플리케이션 설정 - 2. ConfigMap]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %}) 글을 참고한다. 이 글은 **볼륨 마운트의 파일 시스템 수준 동작**에 집중한다.

<br>

# TL;DR

- **두 시나리오로 분리하면 직관적이다.** 파드가 새로 뜨는 경우(`kubectl rollout restart` / 매니페스트 재배포 등)는 두 마운트 모두 시작 시점의 ConfigMap을 그대로 받으므로 자동 반영된다. 두 마운트가 갈라지는 건 **파드는 살아있고 ConfigMap만 단독으로 변경되는** 경우뿐이며, 이 글이 다루는 것이 그 경우다.
- 두 방식 모두 컨테이너 런타임 입장에서는 **bind mount**다. 호스트 측 kubelet이 만드는 `AtomicWriter` 심볼릭 링크 체인도 동일하게 깔린다. 차이는 컨테이너 런타임이 그 결과물을 **어떤 단위로** bind mount하느냐(디렉토리 vs 단일 파일)이다.
- ConfigMap **subPath 없는 일반 마운트**는 atomic_writer가 만든 디렉토리를 통째로 bind mount한다. 컨테이너는 디렉토리 inode를 잡고 있어 안의 `..data` 심볼릭 링크가 `rename()`으로 atomic swap될 때마다 자동으로 새 데이터를 본다 (전파 지연 ~60-90초).
- ConfigMap **subPath 마운트**는 컨테이너 시작 시점에 심볼릭 링크 체인을 resolve한 **단일 파일의 inode**를 직접 bind mount한다. 이후 kubelet이 `..data`를 아무리 갈아치워도 컨테이너는 옛 inode를 계속 본다 → 파드 재시작이 유일한 답.
- 본질은 한 줄로 요약된다: **bind mount는 마운트 시점의 inode를 잡는다.** 같은 원리가 [Docker 타임존 동기화 문제]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})에서도 동일한 인과 구조로 나타난다.
- 함정: ConfigMap 파일을 inotify로 감시하면 `IN_MODIFY`가 아니라 `IN_DELETE_SELF` 이벤트가 온다. atomic swap의 부산물이며, 핫 리로드 코드를 짤 때 watch를 다시 등록하지 않으면 업데이트를 놓친다.

<br>

# ConfigMap 볼륨 마운트의 두 가지 모습

ConfigMap을 파드 파일 시스템으로 노출하는 방법은 두 가지다 — `volumeMounts` 항목에 `subPath`를 지정하지 않은 **일반 마운트**, 그리고 `subPath`로 특정 키 하나만 끼워 넣는 **subPath 마운트**.

두 방식 모두 호스트 측에서 kubelet이 동일한 `AtomicWriter` 심볼릭 링크 체인을 깔고, 컨테이너 런타임이 Linux **bind mount**로 컨테이너 파일 시스템에 노출한다는 점은 같다. 차이는 컨테이너 런타임이 그 결과물을 **어떤 단위로** bind mount하느냐에 있다 — 디렉토리 통째로(일반 마운트) vs 심볼릭 링크 체인을 resolve한 단일 파일(subPath 마운트). 이 차이가 두 방식의 모든 격차를 만들어낸다.

## subPath 없는 일반 마운트

ConfigMap 전체를 디렉토리로 마운트한다. 각 키가 파일 이름, 값이 파일 내용이 되어 마운트 경로 아래 평평하게 펼쳐진다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  containers:
  - name: webapp
    image: nginx
    volumeMounts:
    - name: config-volume
      mountPath: /etc/config       # 디렉토리 마운트 경로
  volumes:
  - name: config-volume
    configMap:
      name: app-config
```

```bash
# 컨테이너 안에서 본 결과
/etc/config/APP_COLOR    # 내용: blue
/etc/config/APP_MODE     # 내용: prod
```

## subPath 마운트

ConfigMap의 **특정 키 하나**를 컨테이너의 특정 경로에 끼워 넣는다. 기존 디렉토리의 다른 파일을 가리지 않고 원하는 파일만 대체할 수 있어 편리하다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  containers:
  - name: webapp
    image: nginx
    volumeMounts:
    - name: config-volume
      mountPath: /etc/nginx/nginx.conf  # 단일 파일 경로
      subPath: nginx.conf               # ConfigMap의 키 이름
  volumes:
  - name: config-volume
    configMap:
      name: nginx-config
```

`/etc/nginx/` 디렉토리의 다른 파일은 그대로 두고 `nginx.conf` 한 개만 ConfigMap 값으로 대체된다.

## 차이

겉보기엔 그저 "마운트 단위가 디렉토리냐 파일이냐"의 차이지만, ConfigMap이 업데이트되는 순간 두 방식의 격차가 드러난다. 다만 이 격차는 **ConfigMap 변경 시 파드를 함께 재시작하는가**에 따라 양상이 다르다.

| 마운트 방식 | 파드는 살아있고 ConfigMap만 변경 | 파드가 새로 뜸 (rollout / 매니페스트 재배포) |
|---|---|---|
| 일반 마운트 (subPath 없음) | 자동 반영 (전파 지연 ~60-90초, atomic_writer가 처리) | 시작 시점 마운트로 자동 반영 |
| subPath 마운트 | **반영되지 않음** (단일 파일 inode 고정) | 시작 시점 마운트로 자동 반영 |

표의 우측 컬럼 — 파드가 새로 뜨는 경우 — 에서는 두 마운트가 동일하게 잘 동작한다. 새 파드의 마운트가 시작 시점에 새로 만들어지면서 그 순간의 ConfigMap을 통째로 가져오기 때문이다. atomic_writer가 만드는 디렉토리 / `..data` 심볼릭 링크 / user-visible 심볼릭 링크 / 컨테이너 측 bind mount 일체가 새로 깔리므로, "atomic update"나 "inode 고정" 같은 미세 메커니즘이 끼어들 자리가 없다. 매니페스트(Deployment + ConfigMap)를 함께 업데이트하거나 `kubectl rollout restart`로 파드를 명시적으로 재시작하는 흐름이 여기에 해당한다.

두 마운트가 갈라지는 건 좌측 컬럼, **파드는 그대로 살아있고 ConfigMap만 단독으로 변경되는** 경우다. 이 글의 deep-dive는 그 시나리오에 한해 의미가 있고, 그 격차의 뿌리를 따라가려면 일반 마운트가 어떻게 "자동 반영"되는지부터 들여다봐야 한다.

<br>

# subPath 없는 일반 마운트 동작 원리: kubelet의 atomic_writer 패턴

## 마운트된 디렉토리의 실제 구조

컨테이너 안에서 `/etc/config/`의 실제 구조를 들여다보면 단순한 평면 파일이 아니다.

```bash
/etc/config/
├── ..data           → ..2024_03_06_09_00_00.<random>/   # 심볼릭 링크
├── ..2024_03_06_09_00_00.<random>/                       # 실제 데이터 디렉토리
│   ├── APP_COLOR    # 내용: blue
│   └── APP_MODE     # 내용: prod
├── APP_COLOR        → ..data/APP_COLOR                   # user-visible 심볼릭 링크
└── APP_MODE         → ..data/APP_MODE                    # user-visible 심볼릭 링크
```

앱이 `/etc/config/APP_COLOR`를 읽으면 심볼릭 링크 체인을 따라간다.

```
APP_COLOR → ..data/APP_COLOR → ..2024_03_06_09_00_00.<random>/APP_COLOR → "blue"
```

> 타임스탬프 디렉토리 이름의 점(`.`) 뒤 부분에 대한 참고: kubelet 코드는 `os.MkdirTemp(targetDir, "..2006_01_02_15_04_05.")`로 디렉토리를 만든다. `os.MkdirTemp`가 prefix 뒤에 랜덤 문자열을 붙이므로, suffix는 마이크로초가 아니라 임의의 식별자다 ([atomic_writer.go newTimestampDir](https://github.com/kubernetes/kubernetes/blob/master/pkg/volume/util/atomic_writer.go)).

이 구조는 kubelet이 ConfigMap/Secret/DownwardAPI 볼륨을 마운트할 때 사용하는 `AtomicWriter`라는 헬퍼가 만들어낸다. 코드 한 줄을 가져오면 의도가 분명하다.

```go
// pkg/volume/util/atomic_writer.go
const (
    dataDirName    = "..data"
    newDataDirName = "..data_tmp"
)
```

`AtomicWriter`의 doc comment는 디자인을 한 단락으로 요약한다.

> The visible files in this volume are symlinks to files in the writer's data directory. Actual files are stored in a hidden timestamped directory which is symlinked to by the data directory. The timestamped directory and data directory symlink are created in the writer's target dir. **This scheme allows the files to be atomically updated by changing the target of the data directory symlink.**

핵심은 **모든 user-visible 파일이 `..data/<key>` 를 거쳐 간접적으로 실제 파일에 도달**한다는 것. 이 한 단계의 간접 참조가 atomic update를 가능하게 한다.

## atomic_writer.go의 Write 알고리즘

`AtomicWriter.Write()`의 12단계 흐름을 압축해서 보면 다음과 같다 ([소스](https://github.com/kubernetes/kubernetes/blob/master/pkg/volume/util/atomic_writer.go)). 여기서 `payload`는 **kubelet이 ConfigMap에서 만들어 낸, 이번 사이클에 이 볼륨에 반영되어야 할 desired state** — 즉 "어떤 파일이 어떤 내용으로 깔려 있어야 하는가"의 명세다 (정확한 자료구조는 본 섹션 끝 참고).


1. payload 검증 (경로가 ..으로 시작/포함되지 않는지 등)
2. 현재 ..data 심볼릭 링크를 readlink → 옛 타임스탬프 디렉토리 식별
3. 옛 디렉토리를 walk → payload에서 사라진 user-visible 경로 계산
4. 옛 디렉토리 내용 vs 새 payload 비교 → 변경 없으면 쓰기 자체를 skip
5. 새 타임스탬프 디렉토리 생성 (os.MkdirTemp + chmod 0755)
6. 새 payload를 그 디렉토리에 기록
7. (옵션) 권한/소유자 설정
8. ..data_tmp 심볼릭 링크 생성 (→ 새 타임스탬프 디렉토리)
9. os.Rename("..data_tmp", "..data")  ← 원자적 교체
10. 신규 user-visible 심볼릭 링크 생성 (예: APP_COLOR → ..data/APP_COLOR)
11. payload에서 사라진 옛 user-visible 심볼릭 링크 제거
12. 옛 타임스탬프 디렉토리 삭제 (os.RemoveAll)


12단계를 의미 단위로 묶어 보면 결국 세 단계다.

| 묶음 | 포함 step | 역할 | user-visible 상태 변화 |
|---|---|---|---|
| **(A) 준비** | 1-7 | 새 payload를 옛 데이터와 분리된 별도 위치(타임스탬프 디렉토리)에 작성 | 없음 — 아직 옛 버전이 보임 |
| **(B) 교체** | 8-9 | `..data_tmp` symlink 생성 → `os.Rename`으로 `..data` 통째 교체 | 이 한순간에 옛 버전 → 새 버전으로 일괄 전환 |
| **(C) 정리** | 10-12 | 신규 user-visible symlink 보정, 사라진 경로 제거, 옛 타임스탬프 디렉토리 삭제 | 없음 — 이미 새 버전이 보임 |

핵심은 (B) 교체 단계다. (A) 준비는 "교체될 새 상태를 옆에 미리 다 만들어 놓는" 사전 작업이고, (C) 정리는 교체 이후의 부산물 처리다. 외부에서 보이는 상태 전환은 오직 (B)의 `rename()` 한 줄에서만 일어난다 — 그 앞도 그 뒤도 user-visible 상태에는 영향을 주지 않는다. 이 구조 덕분에 컨테이너가 디렉토리를 읽는 시점은 항상 "옛 버전 전체" 아니면 "새 버전 전체" 둘 중 하나이고, 그 사이의 어떤 partial 상태도 존재하지 않는다.

이 구조에서 두 가지 부산물이 따라온다. 하나는 (A)의 step 4가 만들어내는 최적화 — 새 payload가 옛 payload와 동일하면 step 5 이후를 통째로 skip하므로, 동일한 ConfigMap에 대해 불필요한 디스크 쓰기가 발생하지 않는다. 다른 하나는 (C)의 step 12가 만들어내는 함정 — 옛 타임스탬프 디렉토리를 삭제하면서 그 안의 파일들을 watch하던 `inotify` watcher들에게 `IN_DELETE_SELF` 이벤트가 발생한다 (이 함정은 2.6에서 다룬다). 두 부산물 모두 (A)/(B)/(C) 3단계 구조의 직접적인 결과다.

이 가운데 가장 중요한 한 줄은 9번이다.

```go
// pkg/volume/util/atomic_writer.go (Write의 step 9, Linux 경로)
err = os.Rename(newDataDirPath, dataDirPath)
```

`rename(2)`은 동일 파일시스템 내에서 원자적이다. 즉 `..data` 심볼릭 링크는 어느 순간에도 "옛 디렉토리"이거나 "새 디렉토리"이지, 그 중간 상태가 없다. 컨테이너가 디렉토리를 읽는 시점에 항상 일관된 한 버전의 데이터를 보게 된다.

> 참고: `payload`의 정확한 자료구조
>
> `Write()`의 시그니처는 `Write(payload map[string]FileProjection, ...)`이다. key는 user-visible 상대 경로 (예: `APP_COLOR`, `config/database.yaml`)이고, value는 그 경로에 들어갈 바이트와 권한을 담은 `FileProjection` 구조체다.
>
> ```go
> // pkg/volume/util/atomic_writer.go
> type FileProjection struct {
>     Data   []byte   // 파일 내용
>     Mode   int32    // 파일 권한
>     FsUser *int64   // 파일 소유 UID (옵션)
> }
> ```
>
> 즉 `data: { APP_COLOR: blue, APP_MODE: prod }`인 ConfigMap이 마운트될 때 payload는 대략 이런 모양이 된다.
>
> ```go
> payload = map[string]FileProjection{
>     "APP_COLOR": {Data: []byte("blue"), Mode: 0644, FsUser: nil},
>     "APP_MODE":  {Data: []byte("prod"), Mode: 0644, FsUser: nil},
> }
> ```
>
> 12단계의 `payload 검증`(step 1), `옛 디렉토리 vs 새 payload 비교`(step 4), `새 payload 기록`(step 6), `payload에서 사라진 옛 user-visible 심볼릭 링크 제거`(step 11) 같은 표현은 모두 이 `map[string]FileProjection`을 desired state로 두고 reconcile하는 동작을 가리킨다.

## ConfigMap 업데이트 설계 원칙: 왜 이렇게 복잡한 구조인가

ConfigMap에 키가 N개 있다고 하자. 가장 단순한 구현은 N개 파일을 하나씩 덮어쓰는 것이지만, 그 사이에 컨테이너가 디렉토리를 읽으면 일부는 옛 값, 일부는 새 값인 **부분 갱신(partial update)** 상태를 만나게 된다. 설정 파일 N개가 서로 의존한다면 이 중간 상태가 곧 장애다.

`AtomicWriter`는 이 문제를 단계 8-9의 atomic swap으로 회피한다.

```text
[Before — step 8 직후, rename() 직전]
..data     → ..2024_03_06_09_00_00.<old>/   # 기존
..data_tmp → ..2024_03_06_10_30_00.<new>/   # 새로 생성

[After — step 9: rename("..data_tmp", "..data")]
..data     → ..2024_03_06_10_30_00.<new>/   # 한 번에 새 디렉토리로
```

`rename()`은 심볼릭 링크의 **타겟**을 변경하는 것이 아니라, **심볼릭 링크 파일 자체를 통째로 교체**한다. 파일시스템 수준에서 한 번에 일어나므로 중간 상태가 없고, `..data` 아래 모든 파일이 동시에 새 버전을 가리킨다.

이 방식이 동작하는 결정적 이유는, **컨테이너에 마운트된 것이 디렉토리이기 때문**이다. 디렉토리의 inode를 잡고 있으므로, 디렉토리 안의 심볼릭 링크가 바뀌면 컨테이너가 디렉토리를 다시 읽을 때 새 링크를 따라간다. (이 "디렉토리 inode를 잡는다 vs 파일 inode를 잡는다"의 차이는 4장에서 다시 정리한다.)

## 업데이트 전파 지연

"파드 재시작 없이 반영된다"고 했지만 즉시 반영되지는 않는다. 두 단계의 지연이 합쳐진다.

### 1단계: kubelet의 ConfigMap 변경 인지

kubelet이 ConfigMap의 변경을 인지하는 과정에서 한 차례 지연이 발생한다. kubelet은 `--config-map-and-secret-change-detection-strategy` 옵션 (KubeletConfiguration 필드 `configMapAndSecretChangeDetectionStrategy`) 으로 다음 셋 중 하나의 전략을 쓴다.

| 전략 | 동작 | 지연 |
|---|---|---|
| `Watch` (기본) | kubelet이 참조 중인 모든 ConfigMap/Secret에 watch를 건다 | watch propagation delay (보통 매우 짧음) |
| `Cache` | kubelet이 가져온 객체를 TTL로 캐싱 | 최대 TTL 만큼 |
| `Get` | 매 요청마다 API 서버에 직접 조회 | 0 (단, API 서버 부하 큼) |

### 2단계: kubelet의 변경 반영 지연

kubelet이 인지한 변경을 볼륨에 반영하는 과정에서도 지연이 발생한다. 위 전략은 kubelet이 **컨텐츠를 가져오는** 방식만 결정한다. 가져온 새 컨텐츠가 실제 볼륨 디렉토리에 `AtomicWriter.Write()`로 기록되는 것은 **pod sync** 사이클에 묶여 있는데, pod sync는 (a) pod 객체 변경, (b) 컨테이너 lifecycle 이벤트, (c) 주기적 트리거 셋 중 하나로 발동한다. 주기적 트리거의 기본 간격은 1초지만, 변경이 없는 pod에 대해서는 실질적으로 약 60~90초 간격으로 동작한다 ([Why Kubernetes secrets take so long to update? — Ahmet Alp Balkan](https://ahmet.im/blog/kubernetes-secret-volumes-delay/)).

[Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically)도 같은 합산을 언급한다.

> As a result, the total delay from the moment when the ConfigMap is updated to the moment when new keys are projected to the Pod can be as long as the kubelet sync period + cache propagation delay, where the cache propagation delay depends on the chosen cache type (it equals to watch propagation delay, ttl of cache, or zero correspondingly).

따라서 실무에서 "ConfigMap을 바꿨는데 즉시 안 보인다"고 느낀 적이 있다면, 그건 정상이다. 보통 1~2분 안에는 들어온다.

## 어플리케이션은 이걸 어떻게 읽는가

여기까지 호스트 측의 동작을 봤는데, 그렇다면 컨테이너 안의 어플리케이션은 이 구조와 어떻게 상호작용해야 할까.

먼저 신경 쓸 경로는 **user-visible 심볼릭 링크 하나뿐**이다. 즉 `/etc/config/APP_COLOR` 같은 경로다. 심볼릭 링크 체인(`APP_COLOR → ..data/APP_COLOR → ..2024_..../APP_COLOR`)은 커널이 `open(2)` 시점에 투명하게 resolve해 주므로, 어플리케이션은 그냥 평범한 파일을 열듯이 읽으면 된다. **`..data/`나 타임스탬프 디렉토리는 atomic_writer의 내부 구현**이므로 직접 참조해서는 안 된다 — 코드가 한순간에 "있던 디렉토리가 사라졌다"는 에러를 받게 된다.

여기에 한 가지 더 중요한 사실이 붙는다. `open()`이 반환한 file descriptor는 **그 시점에 resolve된 inode를 잡고** 있다. 이는 일반적인 Linux 파일 I/O의 동작이지만, atomic update 맥락에서는 결정적으로 작동한다 — `..data` 심볼릭 링크가 새 디렉토리로 갈아치워져도, 이미 열린 fd는 옛 inode를 계속 본다. **파일을 다시 열기 전까지는 새 값을 영영 못 본다.**

따라서 어플리케이션이 "ConfigMap 자동 반영"의 혜택을 실제로 받으려면 다음 세 가지 읽기 패턴 중 하나를 의도적으로 선택해야 한다.

| 패턴 | 동작 | 자동 반영 받는가 | 반영 지연 | 비고 |
|---|---|---|---|---|
| 1회성 읽기 | 시작 시 한 번 `open` + `read` → 메모리 캐시 | 아니오 | (영영) | atomic_writer가 아무리 정교해도 무용지물. 반영하려면 어플리케이션을 다시 띄워야 함 — `kubectl rollout restart` 등 명시 재시작 또는 매니페스트 재배포 |
| 폴링 (주기적 재읽기) | 일정 주기마다 다시 `open` + `read` | 예 | 폴링 주기 | 단순/견고. 매 주기 디스크 I/O 비용 |
| 이벤트 기반 워칭 | `inotify`/`fsnotify`로 변경 이벤트 수신 시 다시 `read` | 예 | 거의 즉시 | 가장 빠르지만 atomic_writer 특유의 함정 있음 (다음 절) |

대부분의 어플리케이션은 1회성 읽기 패턴이다. 이 경우 ConfigMap을 일반 마운트로 노출하든 환경 변수로 주입하든 결과는 같다 — 자동 반영은 받지 못한다. 자동 반영을 누리려면 어플리케이션이 폴링 또는 이벤트 기반 워칭 둘 중 하나를 명시적으로 구현해야 한다는 점은, atomic_writer 동작 원리와 무관하게 자주 간과되는 부분이다.

실무에서는 1회성 읽기 어플리케이션의 ConfigMap 변경을 "어플리케이션에 자동 반영 로직을 박는" 방향이 아니라 **명시적으로 파드를 다시 띄우는** 방향으로 처리하는 경우가 많다 — `kubectl rollout restart deployment/<name>` 한 방, 또는 매니페스트와 함께 재배포. 결국 "ConfigMap만 단독으로 갈아주는" 상황 자체를 만들지 않고, 파드를 새로 띄워 시작 시점 마운트로 최신값을 받게 하는 방식이다. 이 처방을 자동화하는 패턴, 그리고 같은 패턴이 subPath 마운트의 한계 우회와 운영적으로 어떻게 수렴하는지는 [subPath 한계를 우회하는 방법](#subpath-한계를-우회하는-방법)에서 함께 다룬다.

폴링은 구현이 단순하지만 폴링 주기만큼의 latency가 생긴다. 즉시 반응이 필요하면 이벤트 기반 워칭으로 가야 하는데 — 여기서 atomic_writer 특유의 함정 하나를 만난다.

## 함정: inotify로 감시하면 IN_DELETE_SELF만 온다

ConfigMap 파일을 `inotify`로 감시하는 어플리케이션은 일반적인 `IN_MODIFY` 이벤트가 아니라 `IN_DELETE_SELF` 이벤트를 받는다.

원인은 단순하다. `AtomicWriter`가 업데이트할 때 user-visible 심볼릭 링크의 **타겟 파일이 "수정"되는 게 아니라**, 심볼릭 링크가 가리키던 옛 타임스탬프 디렉토리가 step 12에서 통째로 삭제되기 때문이다. 앱 입장에서는 자기가 watch 걸어둔 파일이 사라진 것처럼 보인다.

```text
앱: inotify_add_watch(/etc/config/APP_COLOR)
    → 실제로 watch가 걸리는 inode = ..2024_03_06_09_00_00.<old>/APP_COLOR

[ConfigMap 업데이트 후]
- ..data 가 새 ts 디렉토리를 가리킴 (rename)
- 옛 ts 디렉토리는 step 12에서 삭제됨
- 옛 inode 의 link count = 0 → IN_DELETE_SELF 발생
```

따라서 핫 리로드를 직접 구현하려는 어플리케이션은 `IN_DELETE_SELF`(혹은 `IN_IGNORED`)를 받은 뒤 watch를 **새 파일 경로에 다시 등록**해야 한다. 그렇지 않으면 첫 변경 알림 한 번만 받고 그 이후 변경은 영영 놓친다. 자세한 사례·코드는 [kubernetes/kubernetes#112677](https://github.com/kubernetes/kubernetes/issues/112677) 와 [Pitfalls reloading files from Kubernetes Secret & ConfigMap volumes — Ahmet Alp Balkan](https://ahmet.im/blog/kubernetes-inotify/) 에 잘 정리되어 있다.

라이브러리(`fsnotify` 등)를 쓴다면 보통 이 재등록 로직이 내장되어 있지만, 일부 구버전이나 직접 구현은 이 함정에 걸린다.

<br>

# subPath 마운트 동작 원리

## 개별 파일 bind mount

`subPath`는 일반 마운트처럼 `..data` 심볼릭 링크 체인을 컨테이너에 노출하지 않는다. 컨테이너 시작 시점에 kubelet이 ConfigMap 볼륨 내의 **특정 파일 하나**를 컨테이너의 특정 경로에 직접 bind mount한다. 디렉토리 수준이 아니라 파일 수준이다.

이때 kubelet은 심볼릭 링크 체인을 따라가서 도달하는 **최종 실제 파일의 inode**를 잡는다.

```text
[컨테이너 시작 시점 — v1]
ConfigMap volume 내부: ..data/nginx.conf → ..2024_v1/nginx.conf (inode #1234)
컨테이너의 /etc/nginx/nginx.conf → inode #1234 에 직접 bind
```

## 시작 시점에 resolve된 inode 고정

ConfigMap이 업데이트되면, 일반 마운트와 마찬가지로 kubelet은 새 타임스탬프 디렉토리를 만들고 `..data` 링크를 atomic swap으로 교체한다. 그런데 subPath로 마운트된 파일은 심볼릭 링크 체인을 거치지 않는다. **이미 resolve된 최종 파일의 inode**에 직접 바인드되어 있다.

```text
[ConfigMap 업데이트 후 — v2]
ConfigMap volume 내부: ..data → ..2024_v2/nginx.conf (inode #5678)  # 새 파일
컨테이너의 subPath bind mount → 여전히 inode #1234                  # 옛 inode
```

kubelet이 `..data`를 아무리 갈아치워도, 컨테이너의 bind mount는 시작 시점에 잡은 옛 inode를 계속 본다. 게다가 step 12에서 옛 타임스탬프 디렉토리가 삭제될 때조차 컨테이너의 bind mount가 inode를 잡고 있으므로 inode 자체는 해제되지 않고 살아남는다 (열린 file descriptor가 있으면 `rm` 후에도 데이터를 읽을 수 있는 것과 같은 원리). 결과적으로 컨테이너는 "이름은 같고 내용도 정상 읽히지만 실은 옛날 inode" 라는 상태에 머무른다.

이건 버그가 아니라 known limitation이다 ([kubernetes/kubernetes#50345](https://github.com/kubernetes/kubernetes/issues/50345)).

파드를 재시작하면 kubelet이 볼륨을 처음부터 다시 마운트한다. 이때 최신 ConfigMap 데이터로 새 디렉토리를 만들고 subPath도 새 파일의 inode를 잡으니까, 그제야 최신 값이 반영된다.

## 직접 재현해 보기

직접 손으로 확인해보면 inode 고정 현상이 분명하게 드러난다. 아래는 재현 절차와 예상 출력 형식이다.

```bash
# 1. ConfigMap + 두 개의 파드(일반 마운트 / subPath 마운트)를 준비
kubectl create configmap demo --from-literal=key=v1
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata: { name: demo-dir }
spec:
  containers:
  - { name: c, image: alpine, command: ["sleep", "infinity"], volumeMounts: [{ name: v, mountPath: /etc/demo }] }
  volumes:
  - { name: v, configMap: { name: demo } }
---
apiVersion: v1
kind: Pod
metadata: { name: demo-sub }
spec:
  containers:
  - { name: c, image: alpine, command: ["sleep", "infinity"], volumeMounts: [{ name: v, mountPath: /etc/demo/key, subPath: key }] }
  volumes:
  - { name: v, configMap: { name: demo } }
EOF
```

```bash
# 2. 두 파드의 마운트된 파일 inode와 내용을 확인
for p in demo-dir demo-sub; do
  echo "--- $p ---"
  kubectl exec "$p" -- stat -c 'inode=%i  name=%n' /etc/demo/key
  kubectl exec "$p" -- cat /etc/demo/key
done

# 예시 출력 형식
# --- demo-dir ---
# inode=2097153  name=/etc/demo/key
# v1
# --- demo-sub ---
# inode=2097154  name=/etc/demo/key
# v1
```

```bash
# 3. ConfigMap 값을 변경하고 충분히 대기 (전파 지연 ~60-90초)
kubectl create configmap demo --from-literal=key=v2 --dry-run=client -o yaml | kubectl apply -f -
sleep 120
```

```bash
# 4. 다시 확인 — 일반 마운트는 inode가 바뀌고 v2를 보지만, subPath는 그대로
for p in demo-dir demo-sub; do
  echo "--- $p ---"
  kubectl exec "$p" -- stat -c 'inode=%i  name=%n' /etc/demo/key
  kubectl exec "$p" -- cat /etc/demo/key
done

# 예시 출력 형식
# --- demo-dir ---
# inode=2097200  name=/etc/demo/key   ← 새 inode
# v2                                  ← 새 값
# --- demo-sub ---
# inode=2097154  name=/etc/demo/key   ← 시작 시점 inode 그대로
# v1                                  ← 옛 값
```

`demo-dir`(일반 마운트)는 사용자에게 보이는 파일 이름이 같아도 backing inode가 갱신되어 새 값을 보고, `demo-sub`(subPath 마운트)는 inode가 시작 시점에 잡힌 값 그대로다. 한 줄로 말하면, **사용자가 보는 파일 이름은 같지만 가리키는 정체가 다르다**.

## subPath 한계를 우회하는 방법

파드 재시작 없이 ConfigMap 변경을 반영해야 한다면, subPath 대신 다음과 같은 방법을 고려할 수 있다.

- **디렉토리 전체 마운트 + 컨테이너 내부 심볼릭 링크**: ConfigMap을 별도 경로에 디렉토리로 마운트하고, 컨테이너 엔트리포인트에서 필요한 파일만 심볼릭 링크로 연결한다. [Docker 타임존 동기화 글의 4단계]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#4단계-컨테이너-내부-심볼릭-링크-재설정)와 같은 발상이다.
- **사이드카 컨테이너**: ConfigMap 변경을 감시하는 사이드카를 두고, 변경 시 설정 파일을 갱신하거나 메인 프로세스에 시그널을 보내 reload한다.
- **콘텐츠 해시 기반 롤아웃**: Kustomize의 `configMapGenerator`처럼 ConfigMap 이름에 콘텐츠 해시를 붙여, 내용이 바뀌면 이름도 바뀌게 만든다. 이름이 바뀌면 Deployment의 spec이 변하므로 자연스럽게 롤아웃이 트리거된다 (= 결국 파드 재시작을 명시적·안전하게 트리거하는 우회).

위의 세 방법 중 **콘텐츠 해시 기반 롤아웃**은 사실 subPath만의 처방이 아니다. [어플리케이션은 이걸 어떻게 읽는가](#어플리케이션은-이걸-어떻게-읽는가)에서 본 **1회성 읽기 어플리케이션** 시나리오에서도 운영적 답은 같은 곳으로 수렴한다 — 두 경우 모두 "파일이 살아있는 동안 새 값을 못 본다"는 한계가 있고, 가장 단순한 답이 "새 파드를 띄우는 것"이며, 그걸 자동화하는 패턴이 콘텐츠 해시 기반 롤아웃이다. 결국 atomic_writer가 본질적으로 가치를 발휘하는 것은 어플리케이션이 파일을 다시 읽는 패턴(폴링 / 이벤트 워칭)을 채택한 일반 마운트 케이스에 한정된다.

<br>

# 디렉토리 마운트 vs 파일 마운트

지금까지의 결과는 한 줄로 환원된다. **bind mount는 마운트 시점의 inode를 잡는다 — 다만 그 inode가 디렉토리냐 파일이냐에 따라 그 이후 변경에 대한 가시성이 달라진다.** bind mount의 inode 의미와 디렉토리/파일 단위 차이의 자세한 배경지식은 [Docker 타임존 동기화 글의 bind mount 섹션]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#bind-mount)에 정리되어 있다.

## 일반 마운트 = 디렉토리 inode

디렉토리 전체를 bind mount한다. 컨테이너가 잡고 있는 건 디렉토리의 inode다. 디렉토리 안의 내용물(심볼릭 링크 포함)은 접근할 때마다 다시 탐색되므로, kubelet이 `..data` 심볼릭 링크를 atomic swap으로 갈아치우면 컨테이너가 디렉토리를 읽을 때 새 링크를 따라간다.

```text
mount: /etc/config/  (디렉토리 inode)
       └── ..data → 새 디렉토리로 교체 가능 → 자동 반영
```

## subPath 마운트 = 파일 inode

개별 파일을 bind mount한다. 컨테이너가 잡고 있는 건 파일의 inode 자체다. 심볼릭 링크를 resolve한 최종 파일의 inode에 직접 바인드되어 있으므로, 원본 쪽에서 심볼릭 링크가 바뀌어도 bind mount는 옛 inode를 계속 바라본다.

```text
mount: /etc/nginx/nginx.conf → inode #1234 (직접 바인드)
       원본에서 ..data 링크 교체 → inode #5678
       컨테이너는 여전히 inode #1234
```

이 차이가 두 마운트 방식의 자동 반영 여부를 가른다.

<br>

# 같은 뿌리, 다른 양상: Docker 타임존 문제와의 연결

bind mount의 inode 의미는 ConfigMap에만 등장하는 이야기는 아니다. [Docker 타임존 동기화 문제]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %})는 호스트 `/etc/localtime`과 `/etc/timezone`을 컨테이너에 bind mount한 상황에서, 호스트에서 타임존을 바꿔도 컨테이너에 반영되지 않는 문제다. 두 문제는 서로 다른 도구·문맥에 있지만 인과 구조가 동일하다.

## 두 문제의 동일한 인과 구조

| 문맥 | 마운트한 것 | 원본 변경 양상 | 결과 |
|---|---|---|---|
| ConfigMap subPath | 파일(시작 시 resolve된 inode) | kubelet이 `..data` 심볼릭 링크 교체 → 새 inode 등장 | bind mount는 옛 inode 고정 → 반영 안 됨 |
| Docker `/etc/localtime` bind mount | 파일(심볼릭 링크 resolve 결과) | 호스트에서 심볼릭 링크 대상 변경 → 새 inode 등장 | bind mount는 옛 inode 고정 → 반영 안 됨 |
| Docker `/etc/timezone` bind mount | 파일 | 호스트에서 파일 삭제-재생성 → 새 inode 배정 | bind mount는 옛 inode 고정 → 반영 안 됨 |

세 케이스 모두 한 줄로 같다: **bind mount는 마운트 시점의 inode를 잡으므로, 원본 쪽에서 inode가 바뀌면(symlink 교체 / 파일 삭제-재생성 / atomic swap) 끊긴다.**

## 해결 전략의 비교

같은 원인이지만 해결 방식은 문맥에 따라 다르다.

| 케이스 | bind mount 단위 | 업데이트 전략 | 결과 |
|---|---|---|---|
| ConfigMap 일반 마운트 | 디렉토리 | kubelet `AtomicWriter` (symlink atomic swap) | 자동 반영 |
| ConfigMap subPath 마운트 | 단일 파일 | (없음) | 파드 재시작 필요 |
| [Docker 타임존 동기화 해결책]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#디렉토리를-마운트한다) | 디렉토리 | inotify 감지 + 파일 복사 | 자동 반영 |

ConfigMap 일반 마운트와 Docker 타임존 해결책은 **bind mount 단위를 파일에서 디렉토리로 올려서 inode 불일치를 우회**하는 같은 전략이다. ConfigMap subPath 마운트는 이 전략이 적용되지 않은 경우라 파드 재시작만이 답인데, [Docker 타임존 동기화 글의 컨테이너 재시작 절]({% post_url 2026-03-07-Dev-Docker-Timezone-Sync %}#컨테이너-재시작) 에서 다뤘듯 재시작은 불필요한 다운타임과 운영 부담을 수반한다.

요약하면 세 케이스의 처방은 한 축에 정렬된다.

- ConfigMap 일반 마운트: 디렉토리 inode 고정 → 안의 심볼릭 링크 교체는 보임 → **자동 반영**
- Docker 타임존 동기화 해결책: 디렉토리 inode 고정 → 안의 파일 교체는 보임 → **자동 반영**
- ConfigMap subPath 마운트: 파일 inode 고정 → 내용 변경 방법 없음 → **재시작만이 답**

<br>

# 정리

ConfigMap 볼륨 마운트의 자동 반영 동작은 결국 두 층의 설계가 맞물린 결과다.

1. **kubelet의 `AtomicWriter`** — 타임스탬프 디렉토리 + `..data` 심볼릭 링크 + `rename()` atomic swap으로 N개 파일의 일관된 갱신을 보장한다. 이 한 단계의 간접 참조 덕분에 컨테이너는 항상 일관된 한 버전의 ConfigMap을 본다.
2. **bind mount의 단위와 inode 의미** — 일반 마운트는 디렉토리를 bind mount하므로 컨테이너가 디렉토리 inode를 잡는다. 안의 심볼릭 링크 교체가 그대로 보인다. subPath 마운트는 단일 파일을 bind mount하므로 컨테이너가 시작 시점에 resolve된 파일 inode에 못 박힌다. 같은 atomic swap 메커니즘이 마운트 단위에 따라 정반대 결과를 낳는다.

같은 원리가 다른 문맥에서도 같은 양상으로 나타난다는 점도 확인했다. ConfigMap subPath 마운트의 한계와 Docker 타임존 동기화 문제는 서로 다른 도구·시기에 만난 문제지만, **bind mount는 마운트 시점의 inode를 잡는다**는 한 줄로 수렴한다. 그리고 그 한 줄이 곧 처방을 결정한다 — mount 단위를 파일에서 디렉토리로 올리거나, 그것이 불가능하면 재시작이거나.

부록처럼 챙겨둘 만한 운영 디테일도 같이 정리해두자.

- 일반 마운트의 전파 지연은 `kubelet sync period + cache propagation delay` 합산이다. 보통 1-2분 안에 반영된다.
- 핫 리로드를 직접 구현한다면 `IN_DELETE_SELF` 이벤트를 처리하고 watch를 다시 등록해야 한다. 라이브러리를 쓰는 게 안전하다.
- subPath의 자동 반영이 정말 필요하면, Kustomize `configMapGenerator` 같은 콘텐츠 해시 기반 롤아웃으로 명시적·안전한 재시작 트리거를 두는 패턴을 고려한다.

추상화된 도구의 제약과 설계가 왜 그런 모양인지는, 결국 한 층 아래 파일시스템의 동작 원리에서 온다.

<br>
