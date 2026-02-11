---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: kubespray-offline - 3. contrib/offline vs. kubespray-offline"
excerpt: "Kubespray 공식 contrib/offline 스크립트와 kubespray-offline 프로젝트를 비교하며, 각각의 구조와 커버리지 차이를 파악해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - kubespray-offline
  - Ansible
  - Nginx
  - Container-Registry
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Kubespray 오프라인 배포를 자동화하는 **두 가지 도구** — `contrib/offline`(공식 스크립트)과 `kubespray-offline`(외부 레포) — 의 구조를 비교한다.

- **contrib/offline**: 목록 생성, 파일 다운로드, 이미지 수집/등록에 집중하는 **최소한의 공식 스크립트 모음**
- **kubespray-offline**: contrib/offline의 `generate_list.sh`를 내부적으로 호출하면서, 서빙 인프라 구성부터 admin 노드 셋업까지 한번에 처리하는 **올인원 래퍼**
- **핵심 차이**: contrib/offline은 1단계(아티팩트 준비) + 3단계(아티팩트 배치)에 집중하고, kubespray-offline은 1~4단계를 폭넓게 커버한다
- **이미지 처리 방식**: contrib/offline은 `docker save` → tar 묶음 → `docker load` + tag + push 방식이고, kubespray-offline은 이미지를 개별 tar.gz로 저장해 target 노드에서 load + push한다
- **파일 다운로드 방식**: contrib/offline은 `wget -x`로 원본 URL 경로 구조를 그대로 보존하고, kubespray-offline은 자체 `decide_relative_dir` 함수로 경로를 재구성한다

[이전 글(8.2.0)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-00 %})에서 두 도구의 관계를 살펴봤다면, 이번 글에서는 실제 코드를 열어보며 **무엇이 같고 무엇이 다른지**를 구체적으로 확인해보고자 한다. 

다만, 실제 실습에서는 kubespray-offline을 사용하기에 contrib/offline은 이후 시리즈에서 별도로 다루지 않으므로 상세하게 분석하고, kubespray-offline은 이후 시리즈에서 상세 분석하고 지금 수준에서는 README 수준의 개요 분석에 그친다.

<br>

# 들어가며

[8.2.0]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-00 %})에서 그린 자동화 도구의 지형을 다시 떠올려 보자.

```
[가이드 문서] ─ 개념/설정 방법
├── offline-environment.md     → "뭘 준비하고 어떻게 설정하라"
├── downloads.md               → "다운로드가 내부적으로 어떻게 동작하나"
└── mirror.md                  → "미러 설정은 어떻게 하나"

[실행 도구] ─ 실제 자동화
├── contrib/offline            → 핵심 기능에 집중한 공식 스크립트
└── kubespray-offline          → contrib/offline을 래핑 + 서빙 인프라까지 한번에
```

[8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})과 [8.2.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-02 %})에서 가이드 문서 3종의 개념을 정리했으니, 이제 실행 도구 쪽을 살펴볼 차례다.

이번 글의 목표는 두 가지다.

1. **contrib/offline의 코드를 상세하게 분석**한다. 각 스크립트가 무엇을 하는지, 내부적으로 어떻게 동작하는지를 코드 레벨에서 파악한다. 이후 kubespray-offline을 분석할 때, "이 부분이 contrib/offline의 어느 기능에 대응하는 것인지"를 대응시키기 위한 기반이 된다.
2. **kubespray-offline의 전체 구조를 README 수준에서 파악**한다. 상세 분석은 이후 시리즈에서 다루므로, 여기서는 "어떤 스크립트가 있고, 어떤 순서로 실행되며, contrib/offline과 어떤 관계인지"까지만 정리한다.

<br>

# contrib/offline 상세 분석

## 디렉토리 구조

```
kubespray/contrib/offline/
├── README.md
├── generate_list.sh                     # 목록 생성
├── generate_list.yml                    # 목록 생성 (Ansible 플레이북)
├── manage-offline-container-images.sh   # 이미지 수집/등록
├── manage-offline-files.sh              # 파일 다운로드 + Nginx 서빙
├── upload2artifactory.py                # Artifactory 업로드 (선택)
├── docker-daemon.json                   # Docker insecure registry 설정 템플릿
├── registries.conf                      # Podman insecure registry 설정 템플릿
└── nginx.conf                           # Nginx 설정 파일
```

스크립트 3개 + 플레이북 1개 + 설정 파일 3개 + 유틸리티 1개로 구성된, 꽤 간결한 구조다. 핵심 스크립트를 하나씩 살펴보자.

## generate_list.sh — 목록 생성

오프라인 배포에 필요한 파일 URL 목록과 컨테이너 이미지 목록을 자동으로 생성하는 스크립트다. [8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 "아티팩트 목록은 설정에 따라 달라진다"고 정리했는데, 그 동적 목록 생성을 담당하는 것이 바로 이 스크립트다.

### 동작 흐름

동작 흐름을 간단히 나타내면 아래와 같다.
1. download.yml에서 *_download_url 패턴을 grep → files.list.template 생성
2. download.yml에서 downloads: 블록의 repo:/tag: 패턴을 파싱 → images.list.template 생성
3. kube-* 이미지(apiserver, controller-manager 등)를 수동으로 추가
4. generate_list.yml 플레이북 실행 → Jinja2 템플릿 변수를 실제 값으로 치환 → files.list, images.list 생성

<br>

실행 결과로 `temp/` 디렉토리에 4개 파일이 생긴다.

```bash
temp/
├── files.list              # 실제 다운로드 URL 목록 (변수가 치환된 최종 버전)
├── files.list.template     # Jinja2 템플릿 (치환 전)
├── images.list             # 실제 컨테이너 이미지 목록
└── images.list.template    # Jinja2 템플릿 (치환 전)
```

### 코드 분석

스크립트의 핵심 부분을 하나씩 살펴본다.

<br>

**경로 설정과 기본 변수**

```bash
set -eo pipefail

CURRENT_DIR=$(cd $(dirname $0); pwd)
TEMP_DIR="${CURRENT_DIR}/temp"
REPO_ROOT_DIR="${CURRENT_DIR%/contrib/offline}"

: ${DOWNLOAD_YML:="roles/kubespray_defaults/defaults/main/download.yml"}
```

- `set -eo pipefail`: `-e`는 에러 발생 시 즉시 종료, `-o pipefail`은 파이프라인 중 하나라도 실패하면 전체를 실패로 처리한다. 목록 생성에서 에러가 나면 잘못된 목록이 만들어질 수 있으니, 엄격하게 실패 처리하는 것이 맞다.
- `REPO_ROOT_DIR`: `${CURRENT_DIR%/contrib/offline}`은 bash 문자열 치환으로, 현재 디렉토리 경로에서 `/contrib/offline` 접미사를 제거해 kubespray 루트 경로를 얻는다.
- `: ${DOWNLOAD_YML:=...}`: bash의 기본값 설정 관용구다. `DOWNLOAD_YML` 환경변수가 비어 있으면 지정된 값을 할당한다. `:`은 no-op 명령어로, 변수 확장만 수행하고 아무 것도 하지 않는다.

<br>

**파일 목록 템플릿 생성**

```bash
grep 'download_url:' ${REPO_ROOT_DIR}/${DOWNLOAD_YML} \
    | sed 's/^.*_url: //g;s/\"//g' > ${TEMP_DIR}/files.list.template
```

`download.yml`에서 `download_url:`이 포함된 줄을 찾아, URL 부분만 추출한다. 예를 들어:

```yaml
# download.yml의 원본
kubelet_download_url: "{{ dl_k8s_io_url }}/release/v{{ kube_version }}/bin/linux/{{ image_arch }}/kubelet"
```

이 줄에서 `kubelet_download_url: ` 부분과 따옴표를 제거하면:

```
{{ dl_k8s_io_url }}/release/v{{ kube_version }}/bin/linux/{{ image_arch }}/kubelet
```

이것이 `files.list.template`에 들어간다. 아직 Jinja2 변수(`{{ }}`)가 치환되지 않은 템플릿 상태다.

<br>

**이미지 목록 템플릿 생성**

```bash
sed -n '/^downloads:/,/download_defaults:/p' ${REPO_ROOT_DIR}/${DOWNLOAD_YML} \
    | sed -n "s/repo: //p;s/tag: //p" | tr -d ' ' \
    | sed 'N;s#\n# #g' | tr ' ' ':' | sed 's/\"//g' > ${TEMP_DIR}/images.list.template
```

`download.yml`의 `downloads:` 블록부터 `download_defaults:` 블록까지를 잘라내고, 그 안에서 `repo:`와 `tag:` 값을 추출해 `repo:tag` 형식으로 조합한다. 파이프라인이 복잡해 보이지만, 핵심은 **`repo`와 `tag`를 한 쌍씩 묶어 이미지 참조를 만드는 것**이다.

<br>

**kube-* 이미지 수동 추가**

```bash
KUBE_IMAGES="kube-apiserver kube-controller-manager kube-scheduler kube-proxy"
for i in $KUBE_IMAGES; do
    echo "{{ kube_image_repo }}/$i:v{{ kube_version }}" >> ${TEMP_DIR}/images.list.template
done
```

주석에 이유가 명시되어 있다. `kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`는 kubeadm이 직접 pull하는 이미지라서, `download.yml`의 `downloads:` 블록에 정의되어 있지 않다. 그래서 별도로 추가해야 한다.

<br>

**Ansible 플레이북으로 템플릿 렌더링**

```bash
/bin/cp ${CURRENT_DIR}/generate_list.yml ${REPO_ROOT_DIR}

(cd ${REPO_ROOT_DIR} && ansible-playbook $* generate_list.yml && /bin/rm generate_list.yml) || exit 1
```

`generate_list.yml`을 kubespray 루트 디렉토리에 복사한 뒤, 거기서 `ansible-playbook`을 실행한다. kubespray 루트에서 실행해야 `roles/kubespray_defaults`와 `roles/download`의 변수를 로드할 수 있기 때문이다.

`$*`로 스크립트에 전달된 인자를 그대로 넘긴다. 특정 inventory 기준으로 목록을 생성하고 싶으면 `./generate_list.sh -i inventory/mycluster/hosts.yaml`처럼 쓸 수 있다. inventory에서 버전 변수를 오버라이드하면 해당 버전 기준의 목록이 생성된다.

### generate_list.yml 플레이북

```yaml
---
- name: Collect container images for offline deployment
  hosts: localhost
  become: false

  roles:
    - role: kubespray_defaults
      when: false
    - role: download
      when: false

  tasks:
    - name: Collect container images for offline deployment
      template:
        src: ./contrib/offline/temp/{{ item }}.list.template
        dest: ./contrib/offline/temp/{{ item }}.list
        mode: "0644"
      with_items:
        - files
        - images
```

`when: false`로 role을 "실행하지 않고 변수만 로드"하는 패턴이 핵심이다. Ansible에서 role을 선언하면 `defaults/main.yml`의 변수가 자동으로 로드된다. `when: false`는 role의 **task**만 건너뛰고, 변수 로딩은 그대로 수행된다. 이렇게 로드된 변수(`kube_version`, `etcd_version`, `calico_version` 등)로 `.list.template`의 Jinja2 변수를 치환해서 `.list` 파일을 생성한다.

결과적으로, 현재 kubespray 설정 기준으로 정확히 필요한 파일 URL과 이미지 목록이 `files.list`와 `images.list`에 담긴다.

<br>

## manage-offline-container-images.sh — 이미지 수집/등록

컨테이너 이미지를 **수집(create)**하고, 내부 레지스트리에 **등록(register)**하는 두 단계를 처리한다.

### 전체 구조

```
[온라인 환경] create 모드
  이미지 소스(클러스터 or 파일) → pull → save → tar.gz 묶음
       ↓ (물리 매체로 이동)
[오프라인 환경] register 모드
  tar.gz 풀기 → 레지스트리 기동 → load → tag → push
```

### 컨테이너 런타임 감지

```bash
if command -v nerdctl 1>/dev/null 2>&1; then
    runtime="nerdctl"
elif command -v podman 1>/dev/null 2>&1; then
    runtime="podman"
elif command -v docker 1>/dev/null 2>&1; then
    runtime="docker"
else
    echo "No supported container runtime found"
    exit 1
fi
```

nerdctl, podman, docker 순서로 감지한다. 이 패턴은 `manage-offline-files.sh`에서도 동일하게 사용된다.

### create 모드 — 이미지 수집

`./manage-offline-container-images.sh create`으로 실행한다.

<br>

**이미지 소스 결정**

```bash
if [ -z "${IMAGES_FROM_FILE}" ]; then
    # 실행 중인 클러스터에서 이미지 목록 추출
    kubectl describe cronjobs,jobs,pods --all-namespaces | grep " Image:" | awk '{print $2}' | sort | uniq > "${IMAGES}"
    kubectl cluster-info dump | grep -E "quay.io/coreos/etcd:|registry.k8s.io/pause:" | sed s@\"@@g >> "${IMAGES}"
else
    # 파일에서 이미지 목록 읽기
    IMAGES=$(realpath $IMAGES_FROM_FILE)
fi
```

두 가지 소스를 지원한다.

- **환경변수 `IMAGES_FROM_FILE` 미설정**: 현재 실행 중인 클러스터에서 `kubectl`로 이미지 목록을 추출한다. 이미 온라인으로 배포된 클러스터가 있을 때 유용하다. etcd와 pause 이미지는 Pod으로 보이지 않으므로 별도로 추출한다.
- **`IMAGES_FROM_FILE` 설정**: 파일에서 목록을 읽는다. `generate_list.sh`로 생성한 `temp/images.list`를 지정하면 된다.

<br>

**이미지 pull + save**

```bash
sudo --preserve-env=http_proxy,https_proxy,no_proxy ${runtime} pull ${image}
# ...
sudo ${runtime} save -o ${FILE_NAME} ${image}
```

각 이미지를 pull한 뒤, 개별 tar 파일로 save한다. 재시도를 5번까지 한다(`RETRY_COUNT=5`).

<br>

**레지스트리 접두사 제거**

```bash
FIRST_PART=$(echo ${image} | awk -F"/" '{print $1}')
if [ "${FIRST_PART}" = "registry.k8s.io" ] ||
   [ "${FIRST_PART}" = "gcr.io" ] ||
   [ "${FIRST_PART}" = "ghcr.io" ] ||
   [ "${FIRST_PART}" = "docker.io" ] ||
   [ "${FIRST_PART}" = "quay.io" ] ||
   [ "${FIRST_PART}" = "${PRIVATE_REGISTRY}" ]; then
    image=$(echo ${image} | sed s@"${FIRST_PART}/"@@ | sed -E 's/\@.*/\n/g')
fi
echo "${FILE_NAME}  ${image}" >> ${IMAGE_LIST}
```

이 부분이 중요하다. `registry.k8s.io/kube-apiserver:v1.31.0`에서 `registry.k8s.io/` 접두사를 제거해 `kube-apiserver:v1.31.0`만 남긴다. 왜냐하면, 나중에 register 모드에서 내부 레지스트리 주소(`DESTINATION_REGISTRY`)를 앞에 붙여 `내부레지스트리:5000/kube-apiserver:v1.31.0`으로 push하기 위해서다.

이것이 [8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 정리한 **"같은 경로 구조 유지"** 전략과 맞닿는 부분이다. 원본 레지스트리의 접두사만 내부 레지스트리로 바꾸고, 그 아래 경로는 동일하게 유지하면 `registry_host` 변수 하나만 바꾸면 된다.

`container-images.txt`에 기록되는 형식은 `파일명  이미지경로`다.

```
registry.k8s.io-kube-apiserver-v1.31.0.tar  kube-apiserver:v1.31.0
docker.io-calico-node-v3.28.0.tar  calico/node:v3.28.0
```

<br>

**tar 묶음 생성**

```bash
tar -zcvf ${IMAGE_TAR_FILE} ./container-images
rm -rf ${IMAGE_DIR}
```

개별 tar 파일들과 매핑 정보(`container-images.txt`)를 하나의 `container-images.tar.gz`로 묶는다. 이 파일을 물리 매체 등으로 오프라인 환경에 가져간다.

<br>

### register 모드 — 이미지 등록

`./manage-offline-container-images.sh register`로 실행한다.

<br>

**레지스트리 결정**

```bash
if [ -z "${DESTINATION_REGISTRY}" ]; then
    create_registry=true
    DESTINATION_REGISTRY="$(hostname):${REGISTRY_PORT}"
fi
```

`DESTINATION_REGISTRY` 환경변수가 설정되어 있으면 기존 레지스트리를 사용하고, 없으면 로컬에 새로 만든다.

<br>

**insecure registry 설정**

```bash
if [ -d /etc/docker/ ]; then
    # Docker: docker-daemon.json의 HOSTNAME을 현재 호스트명으로 치환
    cp ${CURRENT_DIR}/docker-daemon.json ${TEMP_DIR}/docker-daemon.json
    sed -i s@"HOSTNAME"@"$(hostname)"@ ${TEMP_DIR}/docker-daemon.json
    sudo cp ${TEMP_DIR}/docker-daemon.json /etc/docker/daemon.json
elif [ -d /etc/containers/ ]; then
    # Podman: registries.conf의 HOSTNAME을 현재 호스트명으로 치환
    cp ${CURRENT_DIR}/registries.conf ${TEMP_DIR}/registries.conf
    sed -i s@"HOSTNAME"@"$(hostname)"@ ${TEMP_DIR}/registries.conf
    sudo cp ${TEMP_DIR}/registries.conf /etc/containers/registries.conf
fi
```

앞서 본 `docker-daemon.json`과 `registries.conf`의 `HOSTNAME` 플레이스홀더가 여기서 실제 호스트명으로 치환된다. HTTP(비암호화) 레지스트리를 사용하기 위한 insecure registry 설정이다.

<br>

**레지스트리 기동 + 이미지 load/tag/push**

```bash
# 레지스트리 컨테이너 시작
sudo ${runtime} run --restart=always -d -p "${REGISTRY_PORT}":"${REGISTRY_PORT}" --name registry registry:latest

# 각 이미지를 load → tag → push
while read -r line; do
    file_name=$(echo ${line} | awk '{print $1}')
    raw_image=$(echo ${line} | awk '{print $2}')
    new_image="${DESTINATION_REGISTRY}/${raw_image}"
    # ...
    sudo ${runtime} load -i ${IMAGE_DIR}/${file_name}
    sudo ${runtime} tag  ${image_id} ${new_image}
    sudo ${runtime} push ${new_image}
done <<< "$(cat ${IMAGE_LIST})"
```

`container-images.txt`의 매핑 정보를 읽어가며, 각 이미지를 load하고 내부 레지스트리 주소로 tag한 뒤 push한다.

실행이 끝나면 친절하게 안내 메시지를 출력한다.

```
Succeeded to register container images to local registry.
Please specify "호스트:5000" for the following options in your inventry:
- kube_image_repo
- gcr_image_repo
- docker_image_repo
- quay_image_repo
```

[8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 정리한 변수 설정 가이드 그대로다. 레지스트리에 이미지를 넣은 뒤, inventory에서 `*_image_repo` 변수를 내부 레지스트리로 바꾸라는 것이다.

<br>

## manage-offline-files.sh — 파일 다운로드 + Nginx 서빙

`generate_list.sh`가 생성한 `temp/files.list`의 URL을 전부 다운로드한 뒤, Nginx 컨테이너를 기동해서 HTTP로 서빙한다.

### 코드 분석

**파일 다운로드**

```bash
FILES_LIST=${FILES_LIST:-"${CURRENT_DIR}/temp/files.list"}
NGINX_PORT=8080

while read -r url; do
  if ! wget -x -P "${OFFLINE_FILES_DIR}" "${url}"; then
    exit 1
  fi
done < "${FILES_LIST}"
```

`wget -x`의 `-x` 옵션이 핵심이다. **원본 URL의 디렉토리 구조를 그대로 로컬에 재현**한다. 예를 들어 `https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet`을 다운로드하면, 로컬에 `dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet` 경로가 생긴다.

이 방식의 장점은 URL 경로가 원본과 동일하게 유지되므로, Nginx에서 서빙할 때 경로 매핑을 별도로 할 필요가 없다는 것이다.

**tar 아카이브 생성**

```bash
tar -czvf "${OFFLINE_FILES_ARCHIVE}" "${OFFLINE_FILES_DIR_NAME}"

[ -n "$NO_HTTP_SERVER" ] && echo "skip to run nginx" && exit 0
```

다운로드한 파일을 `offline-files.tar.gz`로 묶는다. `NO_HTTP_SERVER` 환경변수가 설정되어 있으면 Nginx 기동을 건너뛴다. 다운로드만 하고 파일을 다른 곳으로 옮기고 싶은 경우에 유용하다.

**Nginx 컨테이너 기동**

```bash
sudo "${runtime}" run \
    --restart=always -d -p ${NGINX_PORT}:80 \
    --volume "${OFFLINE_FILES_DIR}":/usr/share/nginx/html/download \
    --volume "${CURRENT_DIR}"/nginx.conf:/etc/nginx/nginx.conf \
    --name nginx nginx:alpine
```

다운로드한 파일 디렉토리를 Nginx의 서빙 경로(`/usr/share/nginx/html/download`)에 마운트하고, 커스텀 `nginx.conf`를 적용한다. 포트 8080으로 접근할 수 있다.

### nginx.conf

```nginx
http {
    default_type application/octet-stream;
    server {
        listen 80 default_server;
        location / {
            root /usr/share/nginx/html/download;
        }
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
    }
}
```

주목할 설정들:

- **`default_type application/octet-stream`**: 바이너리 파일을 서빙하는 것이 주 목적이므로, MIME 타입을 알 수 없는 파일은 바이너리 스트림으로 처리한다. 브라우저가 파일을 렌더링하지 않고 다운로드하게 된다.
- **`autoindex on`**: 디렉토리 리스팅을 활성화한다. 브라우저에서 `http://host:8080/`에 접근하면 파일 목록이 보인다. 디버깅할 때 편하다.
- **`autoindex_exact_size off`**: 파일 크기를 바이트 단위 대신 KB/MB/GB로 보여준다.
- **`autoindex_localtime on`**: UTC 대신 로컬 시간대로 수정 시간을 표시한다.

<br>

## upload2artifactory.py — Artifactory 업로드

앞의 스크립트들로 다운로드한 파일을 [JFrog Artifactory](https://jfrog.com/artifactory/)에 업로드하는 선택적 유틸리티다. Artifactory는 바이너리/패키지 관리를 위한 범용 저장소 관리 도구로, 엔터프라이즈 환경에서 내부 아티팩트 관리에 많이 사용된다. 여기서 "Artifactory"는 JFrog의 제품명이지 일반 용어가 아니다.

환경변수로 인증 정보와 대상 URL을 설정한다.

```bash
export USERNAME=admin     # Deploy/Cache, Delete/Overwrite 권한을 가진 사용자
export TOKEN=...          # Artifactory의 Set Me Up 기능으로 생성한 토큰
export BASE_URL=https://artifactory.example.com/artifactory/a-generic-repo/
```

- **USERNAME**: Artifactory의 **권한(Permission)** 중 `Deploy/Cache`와 `Delete/Overwrite`를 최소한 갖고 있어야 하는 사용자 계정이다. Artifactory는 자체적으로 권한 체계를 가지고 있으며, 이 권한이 있어야 파일을 업로드하고 덮어쓸 수 있다.
- **TOKEN**: Artifactory UI의 "Set Me Up" 기능에서 생성하는 API 토큰이다.
- **BASE_URL**: repository name을 포함한 전체 URL이다.

Nginx로 직접 서빙하는 것이 충분한 환경이라면 이 단계는 필요 없다. 조직 내에 이미 Artifactory가 운영되고 있어서 아티팩트를 중앙 관리하고 싶을 때 사용한다.

<br>

## 부속 설정 파일

### docker-daemon.json

```json
{"insecure-registries":["HOSTNAME:5000"]}
```

Docker 데몬의 insecure registry 설정 **템플릿**이다. `HOSTNAME`은 고정 문자열이 아니라 **플레이스홀더**로, `register_container_images()` 함수에서 `sed`로 실제 호스트명으로 치환된다.

### registries.conf

```toml
[registries.search]
registries = ['registry.access.redhat.com', 'registry.redhat.io', 'docker.io']

[registries.insecure]
registries = ['HOSTNAME:5000']

[registries.block]
registries = []
```

Podman/CRI-O 계열의 insecure registry 설정 템플릿이다. `docker-daemon.json`과 마찬가지로 `HOSTNAME`이 플레이스홀더다. RHEL/CentOS 계열에서 `/etc/containers/registries.conf`에 복사된다.

<br>

## contrib/offline 정리

contrib/offline의 전체 워크플로우를 정리하면:

```
[온라인 환경]
1. generate_list.sh       → files.list + images.list 생성
2. manage-offline-container-images.sh create   → 이미지 pull + tar 묶음
3. manage-offline-files.sh                     → 파일 다운로드 (+ Nginx 기동)
4. (선택) upload2artifactory.py                → Artifactory에 파일 업로드
   ↓ 물리 매체/승인 경로로 이동
[오프라인 환경]
5. manage-offline-container-images.sh register → 레지스트리 기동 + 이미지 등록
6. (파일 서빙은 이미 Nginx가 돌고 있거나 별도로 구성)
```

커버하는 것과 커버하지 않는 것이 명확하다.

| 커버하는 것 | 커버하지 않는 것 |
|---|---|
| 아티팩트 목록 자동 생성 | OS 패키지 레포 미러링 |
| 컨테이너 이미지 수집/등록 | PyPI 미러 구축 |
| 바이너리 파일 다운로드 + HTTP 서빙 | inventory 변수 설정 |
| | admin 노드 환경 설정 (containerd 설치 등) |
| | Kubespray 자체의 다운로드/설치 |

**1단계(아티팩트 준비)와 3단계(아티팩트 배치) 중 파일/이미지에 한정된 부분만 자동화**한다. 나머지는 직접 해야 한다.

<br>

# kubespray-offline 개요

## 디렉토리 구조

```
kubespray-offline/
├── config.sh                        # 최상위 설정
├── download-all.sh                  # 다운로드 원스톱 스크립트
├── download-kubespray-files.sh      # kubespray 파일/이미지 다운로드 (contrib/offline 활용)
├── download-images.sh               # 이미지 개별 다운로드
├── download-additional-containers.sh# 추가 이미지 다운로드
├── get-kubespray.sh                 # kubespray 소스 다운로드
├── prepare-pkgs.sh                  # python, podman 등 사전 패키지 설치
├── prepare-py.sh                    # python venv + 패키지 설치
├── pypi-mirror.sh                   # PyPI 미러 파일 다운로드
├── build-ansible-container.sh       # Ansible 컨테이너 이미지 빌드
├── create-repo.sh                   # RPM/DEB 레포 다운로드
├── copy-target-scripts.sh           # target 노드용 스크립트 복사
├── install-containerd.sh            # containerd 로컬 설치
├── install-docker.sh                # docker 로컬 설치
├── install-nerdctl.sh               # nerdctl 로컬 설치
├── precheck.sh                      # 사전 점검
├── cleanup.sh                       # 정리
├── offline.yml                      # inventory 오버라이드 샘플
├── imagelists/
│   └── images.txt                   # 추가 이미지 목록
├── pkglist/                         # OS별 패키지 목록
│   ├── rhel/
│   └── ubuntu/
├── scripts/                         # 공통 함수
│   ├── common.sh
│   ├── images.sh
│   ├── create-repo-rhel.sh
│   ├── create-repo-ubuntu.sh
│   └── set-locale.sh
├── target-scripts/                  # target 노드에 복사되는 스크립트
│   ├── config.sh
│   ├── setup-all.sh
│   ├── setup-container.sh
│   ├── setup-offline.sh
│   ├── setup-py.sh
│   ├── start-nginx.sh
│   ├── start-registry.sh
│   ├── load-push-all-images.sh
│   ├── extract-kubespray.sh
│   └── playbook/                    # offline-repo.yml 등
├── ansible-container/               # Ansible 컨테이너 빌드용
├── docker/                          # Docker 내부 빌드/테스트용
└── test/                            # 테스트 스크립트
```

contrib/offline의 스크립트 3+1개에 비하면 규모가 훨씬 크다. 핵심은 **download 단계 스크립트들**(루트에 위치)과 **target 단계 스크립트들**(`target-scripts/`에 위치)의 2단 구조다.

## 핵심 워크플로우

### config.sh — 최상위 설정

```bash
source ./target-scripts/config.sh

# container runtime for preparation node
docker=${docker:-podman}

# Run ansible in container?
ansible_in_container=${ansible_in_container:-false}
```

최상위 `config.sh`는 `target-scripts/config.sh`를 먼저 로드한 뒤, 준비 노드(download를 수행하는 노드)의 컨테이너 런타임과 Ansible 실행 방식을 결정한다.

`target-scripts/config.sh`에는 Kubespray 버전, containerd/runc/nerdctl 버전, 레지스트리 포트 등 핵심 설정이 들어 있다.

```bash
KUBESPRAY_VERSION=${KUBESPRAY_VERSION:-2.30.0}
RUNC_VERSION=1.3.4
CONTAINERD_VERSION=2.2.1
NERDCTL_VERSION=2.2.1
CNI_VERSION=1.8.0
NGINX_VERSION=1.29.4
REGISTRY_VERSION=3.0.0
REGISTRY_PORT=${REGISTRY_PORT:-35000}
```

이 설정 파일을 먼저 수정한 뒤 이후 단계를 실행해야 한다. README에서 "Before download offline files, check and edit configurations in `config.sh`"라고 안내하는 이유다.

### download-all.sh — 원스톱 다운로드

```bash
source ./config.sh

run ./precheck.sh
run ./prepare-pkgs.sh || exit 1
run ./prepare-py.sh
run ./get-kubespray.sh
if $ansible_in_container; then
    run ./build-ansible-container.sh
else
    run ./pypi-mirror.sh
fi
run ./download-kubespray-files.sh
run ./download-additional-containers.sh
run ./create-repo.sh
run ./copy-target-scripts.sh
```

실행 순서를 정리하면:

| 순서 | 스크립트 | 하는 일 |
|---|---|---|
| 1 | `precheck.sh` | 사전 점검 |
| 2 | `prepare-pkgs.sh` | python, podman 등 필수 도구 설치 |
| 3 | `prepare-py.sh` | Python 가상환경 + 패키지 설치 |
| 4 | `get-kubespray.sh` | kubespray 소스 다운로드/압축 해제 |
| 5.1 | `pypi-mirror.sh` | PyPI 미러 파일 다운로드 (`ansible_in_container=false`일 때) |
| 5.2 | `build-ansible-container.sh` | Ansible 컨테이너 빌드 (`ansible_in_container=true`일 때) |
| 6 | `download-kubespray-files.sh` | kubespray 파일/이미지 다운로드 **(contrib/offline 활용)** |
| 7 | `download-additional-containers.sh` | 추가 이미지 다운로드 |
| 8 | `create-repo.sh` | RPM/DEB 패키지 레포 다운로드 |
| 9 | `copy-target-scripts.sh` | target 노드용 스크립트를 outputs/에 복사 |

[8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 고민했던 **"Ansible 실행 방식 결정이 아티팩트 준비에 영향을 준다"**는 문제가 5.1/5.2 분기에서 해결된다. `config.sh`에서 `ansible_in_container`를 먼저 결정해 두면, `download-all.sh`가 그에 맞는 아티팩트를 자동으로 준비한다.

모든 결과물은 `outputs/` 디렉토리에 모인다. 이 디렉토리를 통째로 target 노드(admin 노드)에 옮기면 된다.

### download-kubespray-files.sh — contrib/offline 활용 지점

이 스크립트가 contrib/offline과의 접점이다.

```bash
generate_list() {
    LANG=C /bin/bash ${KUBESPRAY_DIR}/contrib/offline/generate_list.sh || exit 1
}
```

contrib/offline의 `generate_list.sh`를 **그대로 호출**해서 `files.list`와 `images.list`를 생성한다. 목록 생성 로직을 재구현하지 않고 공식 스크립트를 활용하는 것이다.

하지만 그 이후의 파일 다운로드와 이미지 다운로드는 **자체 구현**을 사용한다.

**파일 다운로드 — 경로 재구성**

contrib/offline의 `manage-offline-files.sh`는 `wget -x`로 원본 URL 경로를 그대로 보존하는 반면, kubespray-offline은 `decide_relative_dir` 함수로 URL을 파싱해서 자체적인 경로 체계로 재구성한다.

```bash
decide_relative_dir() {
    local url=$1
    rdir=$(echo $rdir | sed "s@.*/\(v[0-9.]*\)/.*/kube\(adm\|ctl\|let\)@kubernetes/\1@g")
    rdir=$(echo $rdir | sed "s@.*/etcd-.*.tar.gz@kubernetes/etcd@")
    rdir=$(echo $rdir | sed "s@.*/cni-plugins.*.tgz@kubernetes/cni@")
    # ...
}
```

예를 들어 `https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet`이라는 URL은 `kubernetes/v1.31.0/kubelet`로 정리된다. 이렇게 하면 `files_repo` 변수에 맞춘 URL 경로 체계(`{{ files_repo }}/kubernetes/v{{ kube_version }}/kubelet`)와 정확히 대응한다. `offline.yml`에서 정의하는 다운로드 URL 패턴이 이 경로 체계를 전제로 되어 있기 때문이다.

**이미지 다운로드 — 개별 tar.gz**

contrib/offline은 모든 이미지를 하나의 `container-images.tar.gz`로 묶지만, kubespray-offline은 각 이미지를 **개별 tar.gz 파일**로 저장한다.

```bash
# scripts/images.sh
get_image() {
    $sudo $docker pull $image
    $sudo $docker save -o $IMAGES_DIR/$tarname $image
    gzip -v $IMAGES_DIR/$tarname
}
```

`outputs/images/` 디렉토리에 이미지별로 `registry.k8s.io_kube-apiserver-v1.31.0.tar.gz` 형태의 파일이 쌓인다. 하나의 큰 tar로 묶는 것과 비교했을 때, 개별 이미지 단위로 관리/전송/디버깅이 편하다.

### target-scripts — target 노드 실행 스크립트

`outputs/` 디렉토리를 target 노드에 복사한 뒤, 아래 스크립트들을 순서대로 실행한다. 일괄 실행 스크립트는 별도로 없고, 각 단계를 수동으로 실행한다.

| 순서 | 스크립트 | 하는 일 |
|---|---|---|
| 1 | `setup-container.sh` | 로컬 파일에서 containerd 설치 + nginx/registry 이미지를 containerd에 load |
| 2 | `start-nginx.sh` | Nginx 컨테이너 실행 (파일 서빙 + 패키지 레포 서빙 + PyPI 미러 서빙) |
| 3 | `setup-offline.sh` | yum/deb 레포 설정, PyPI 미러 설정을 로컬 Nginx 서버로 전환 |
| 4 | `setup-py.sh` | 로컬 레포에서 python3 + venv 설치 |
| 5 | `start-registry.sh` | Docker private registry 컨테이너 실행 |
| 6 | `load-push-all-images.sh` | 모든 이미지를 containerd에 load + private registry에 push |
| 7 | `extract-kubespray.sh` | kubespray tarball 압축 해제 + 패치 적용 |

1번의 "nginx/registry 이미지를 containerd에 load"라는 표현이 처음에는 헷갈릴 수 있는데, 의미는 간단하다. Nginx 컨테이너와 Registry 컨테이너를 실행하려면 **그 이미지가 먼저 containerd에 있어야** 한다. 온라인이면 pull하면 되지만 오프라인이므로, 미리 다운로드해 둔 `nginx:1.29.4` 이미지와 `registry:3.0.0` 이미지 tar를 `nerdctl load`로 containerd에 넣는 것이다.

`setup-offline.sh`에서 yum/deb 레포와 PyPI 미러를 로컬 Nginx로 전환하는 것은, [8.1 시리즈]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서 수동으로 했던 `/etc/yum.repos.d/` 설정 변경, pip의 `--index-url` 설정 등을 자동화한 것이다.

### offline.yml — inventory 오버라이드 샘플

kubespray-offline은 `offline.yml` 샘플 파일을 제공한다.

```yaml
http_server: "http://YOUR_HOST"
registry_host: "YOUR_HOST:35000"

files_repo: "{{ http_server }}/files"
yum_repo: "{{ http_server }}/rpms"
ubuntu_repo: "{{ http_server }}/debs"

kube_image_repo: "{{ registry_host }}"
gcr_image_repo: "{{ registry_host }}"
docker_image_repo: "{{ registry_host }}"
quay_image_repo: "{{ registry_host }}"
github_image_repo: "{{ registry_host }}"

kubeadm_download_url: "{{ files_repo }}/kubernetes/v{{ kube_version }}/kubeadm"
# ...
runc_download_url: "{{ files_repo }}/runc/v{{ runc_version }}/runc.{{ image_arch }}"
```

[8.2.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-01 %})에서 정리한 공식 문서의 변수 설정 예시와 거의 동일하다. 하나 주의할 점은 **`runc_download_url`의 경로에 `runc_version`이 포함**되어 있다는 것이다. 공식 문서의 예시(`{{ files_repo }}/runc.{{ image_arch }}`)와 다르며, kubespray-offline의 `decide_relative_dir`이 runc 파일을 `runc/v{version}/` 경로 아래에 배치하므로 이에 맞춰야 한다.

이 파일을 inventory의 `group_vars/all/offline.yml`에 복사하고, `YOUR_HOST`를 실제 IP로 바꾸면 된다.

### deploy offline repo configurations

kubespray-offline은 offline 레포 설정을 모든 target 노드에 배포하기 위한 별도의 플레이북(`playbook/offline-repo.yml`)도 제공한다.

```bash
cp -r ${outputs_dir}/playbook ${kubespray_dir}
cd ${kubespray_dir}
ansible-playbook -i ${your_inventory_file} offline-repo.yml
```

이 플레이북은 각 노드의 yum/deb 레포 설정을 내부 Nginx 서버를 사용하도록 변경한다. 노드마다 SSH로 접속해서 설정을 바꾸는 작업을 Ansible이 일괄 처리해 주는 것이다.

<br>

# 비교 분석

## 5단계 커버리지

[8.2.0]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-00 %})에서 정의한 오프라인 배포 5단계에 매핑하면:

| 단계 | contrib/offline | kubespray-offline |
|---|---|---|
| **1. 아티팩트 준비** | `generate_list.sh`로 목록 생성, `manage-offline-*.sh`로 파일/이미지 다운로드 | `generate_list.sh` 호출 + 자체 다운로드 로직 + OS 패키지/PyPI 미러까지 |
| **2. 서빙 인프라 구성** | `manage-offline-files.sh`의 Nginx 기동, `manage-offline-container-images.sh`의 레지스트리 기동 | containerd 설치, Nginx/Registry 자동 기동, PyPI 미러 설정 |
| **3. 아티팩트 배치** | 파일은 Nginx 자동 서빙, 이미지는 레지스트리 자동 push | 파일/패키지/PyPI Nginx 서빙, 이미지 load+push, 레포 설정 Ansible 배포 |
| **4. 변수 설정** | 안내 메시지 출력 (직접 설정) | `offline.yml` 샘플 + `offline-repo.yml` 플레이북 |
| **5. 배포 실행** | 직접 실행 | 직접 실행 |

contrib/offline은 파일과 이미지에 한정된 자동화를 제공하고, **OS 패키지 레포, PyPI 미러, admin 노드 환경 설정은 범위 밖**이다. kubespray-offline은 이 빈틈을 채우며 거의 전 과정을 자동화한다.

## 아키텍처 차이

| 관점 | contrib/offline | kubespray-offline |
|---|---|---|
| **위치** | kubespray 저장소 내부 | 독립 저장소 |
| **kubespray 의존성** | kubespray 트리 안에서 실행 | kubespray를 다운로드해서 사용 |
| **목록 생성** | `generate_list.sh` 자체 구현 | contrib/offline의 `generate_list.sh` 호출 |
| **파일 다운로드** | `wget -x`로 원본 경로 보존 | `curl` + `decide_relative_dir`로 경로 재구성 |
| **이미지 저장** | 모든 이미지를 하나의 tar.gz로 묶음 | 이미지별 개별 tar.gz |
| **OS 패키지** | 범위 밖 | `create-repo.sh`로 RPM/DEB 레포 자동 구성 |
| **PyPI 미러** | 범위 밖 | `pypi-mirror.sh`로 자동 구성 |
| **실행 환경 설정** | 범위 밖 | containerd 설치, Python venv 구성 등 |
| **설정 파일** | 환경변수 기반 | `config.sh` + `target-scripts/config.sh` |

## 이미지 처리 방식 차이

두 도구의 이미지 처리 방식은 근본적으로 다르다.

**contrib/offline**

```
[온라인] pull → save → 전체를 하나의 tar.gz로 묶음
         ↓ (물리 매체로 이동)
[오프라인] tar.gz 풀기 → 레지스트리 기동 → container-images.txt 기반으로 load → tag → push
```

- 이미지 목록 매핑(`container-images.txt`)을 별도로 관리한다
- 레지스트리 접두사를 미리 제거해 두고, push 시 대상 레지스트리를 앞에 붙인다
- 하나의 아카이브로 묶이므로 이동은 간편하지만, 개별 이미지만 갱신하기는 번거롭다

**kubespray-offline**

```
[온라인] pull → 이미지별로 save + gzip → outputs/images/에 개별 저장
         ↓ (outputs 디렉토리 통째로 이동)
[오프라인] target-scripts/load-push-all-images.sh로 개별 load → tag → push
```

- 이미지 파일명 자체가 이미지 참조를 인코딩한다 (`registry.k8s.io_kube-apiserver-v1.31.0.tar.gz`)
- 개별 파일이므로 특정 이미지만 교체/추가가 쉽다
- 파일 수는 많아지지만 관리 유연성이 높다

## 파일 다운로드 경로 차이

**contrib/offline**: `wget -x`

```
원본 URL: https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet
로컬 경로: offline-files/dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet
```

원본 URL의 호스트명을 포함한 전체 경로가 그대로 보존된다. Nginx로 서빙할 때 경로 매핑이 필요 없지만, kubespray의 `files_repo` 변수에서 참조하는 경로 패턴과는 다를 수 있다.

**kubespray-offline**: `curl` + `decide_relative_dir`

```
원본 URL: https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubelet
로컬 경로: outputs/files/kubernetes/v1.31.0/kubelet
```

URL을 파싱해서 kubespray의 `*_download_url` 변수 패턴에 맞는 경로로 재구성한다. `offline.yml`의 다운로드 URL 설정과 직접적으로 대응되므로, **"파일을 이 경로에 놓고, 이 URL로 가리키면 된다"가 일관성 있게 연결**된다.

<br>

# 정리

두 도구의 관계를 한 문장으로 요약하면: **kubespray-offline은 contrib/offline의 `generate_list.sh`를 목록 생성 엔진으로 활용하되, 다운로드/서빙/설정의 나머지 전 과정을 자체적으로 구현한 올인원 래퍼**다.

```
contrib/offline (공식 스크립트)
  "목록 생성 + 파일/이미지 다운로드/등록"
  → 핵심 기능에 집중, 나머지는 직접
       │
       │ 목록 생성(generate_list.sh)만 그대로 활용
       │ 다운로드/서빙/설정은 자체 구현으로 확장
       ▼
kubespray-offline (올인원 래퍼)
  "OS 패키지, PyPI 미러, containerd 설치, Nginx/Registry 기동,
   inventory 설정까지 한번에"
  → 거의 전 과정을 자동화
```

이 관계를 이해했으니, 이후 시리즈에서 kubespray-offline의 각 스크립트를 상세 분석할 때 "이 부분이 contrib/offline의 어느 기능을 대체/확장한 것인지"를 대응시키며 읽을 수 있다.

<br>

# 참고 자료

- [Kubespray - contrib/offline](https://github.com/kubernetes-sigs/kubespray/tree/master/contrib/offline)
- [Kubespray - Offline Environment](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/offline-environment.md)
- [kubespray-offline](https://github.com/kubespray-offline/kubespray-offline)
- [JFrog Artifactory](https://jfrog.com/artifactory/)

<br>
