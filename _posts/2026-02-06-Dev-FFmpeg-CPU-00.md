---
title:  "[Kubernetes] Pod CPU Limit과 FFmpeg Thread 최적 조정 - 0. 목격한 상황"
excerpt: "Kubernetes 환경에서 ffmpeg 프레임 추출이 비정상적으로 느렸던 상황에 대해 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - FFmpeg
  - CPU
  - Go
  - 성능
---

<br>

회사 백엔드 API에서 영상 처리가 비정상적으로 느린 현상을 발견했다. 처음에는 "좀 느리네?" 정도였는데, 직접 측정해 보고 눈을 의심했다. 동일한 노드에서 Docker 컨테이너로 실행하면 4.5초면 끝나는 작업이, K8s Pod에서는 148초가 걸리고 있었다. 약 37배 차이. 이 시리즈에서는 원인을 분석하고 해결해 나간 과정을 정리하고자 한다.

> 원인을 파악하는 과정에서, CPU 스케줄링, cgroup, 컨테이너의 리소스 관리, ffmpeg의 스레드 모델 등 파볼 것이 꽤 많았다. 배경지식을 정리하는 것만으로도 상당한 공부가 되어, 꽤 시간이 지났지만 당시의 과정을 시리즈로 기록해 두고자 한다.

<br>

# TL;DR

- 영상 업로드 API에서 ffmpeg 프레임 추출이 K8s 환경에서 비정상적으로 느린 현상 발생
- 동일 노드, 동일 이미지 기준 Docker 컨테이너(4.5초) 대비 K8s Pod(148초)에서 약 37배 느림
- 두 환경의 눈에 띄는 차이: K8s Pod에는 CPU limit `1000m` 설정, Docker 컨테이너에는 미설정
- CPU 리소스 제약이 유력하지만, I/O, 메모리, 네트워크 등 다른 가능성도 존재

<br>

# 상황

## 영상 처리 파이프라인

Backend 서버는 학습 데이터 준비를 위해 영상을 받아 프레임을 추출하는 API를 제공한다. 영상 업로드 요청이 들어오면 다음과 같은 순서로 처리된다.

1. 영상 파일 저장 (스트리밍 방식으로 디스크에 기록)
2. 영상 메타데이터 확인 및 필요 시 리사이즈
3. 병렬 처리
   - 프레임 추출 (ffmpeg)
   - 썸네일 추출 및 업로드 (ffmpeg + 오브젝트 스토리지)
   - 원본 영상 업로드 (오브젝트 스토리지)
4. 프로젝트 정보 업데이트

핵심은 3번이다. Go의 `errgroup`을 사용해 goroutine 3개로 병렬 처리하며, 이 중 프레임 추출과 썸네일 추출이 ffmpeg를 호출하는 CPU-intensive한 작업이다.

<br>

## 코드

### 영상 처리 서비스

영상 처리 함수의 핵심 흐름을 간략히 나타내면 다음과 같다.

```go
func processVideo(ctx context.Context, videoReader io.Reader, outputDir string) error {
    // 1. 영상 파일을 디스크에 저장
    videoPath := filepath.Join(outputDir, "video.mp4")
    if err := saveToFile(videoPath, videoReader); err != nil {
        return err
    }

    // 2. 메타데이터 확인 후, 필요하면 리사이즈
    meta, _ := getVideoMeta(videoPath)
    if needsResize(meta) {
        resizeVideo(videoPath, meta)
    }

    // 3. 병렬 처리
    eg, egCtx := errgroup.WithContext(ctx)

    eg.Go(func() error {
        return extractFrames(videoPath, outputDir+"/frames") // ffmpeg 호출
    })

    eg.Go(func() error {
        if err := extractThumbnail(videoPath, outputDir+"/thumb.webp"); err != nil { // ffmpeg 호출
            return err
        }
        return uploadToStorage(egCtx, outputDir+"/thumb.webp")
    })

    eg.Go(func() error {
        return uploadToStorage(egCtx, videoPath) // 오브젝트 스토리지 업로드
    })

    return eg.Wait()
}
```

1~2단계에서 영상을 저장하고 필요 시 리사이즈한 뒤, 3단계에서 `errgroup`을 사용해 세 작업을 동시에 수행한다. 이 중 ffmpeg를 호출하는 작업은 프레임 추출과 썸네일 추출이다.

<br>

### ffmpeg 호출

프레임 추출과 썸네일 추출은 Go의 [ffmpeg-go](https://github.com/u2takey/ffmpeg-go) 라이브러리를 통해 ffmpeg를 호출한다. 실제 요청 시 실행되는 ffmpeg 명령을 로그에서 확인하면 다음과 같다.

**프레임 추출**:

```bash
ffmpeg -i /data/video.mp4 \
  -filter_complex [0]scale=1280:720[s0] -map [s0] \
  -q:v 2 -vsync vfr \
  /data/frames/frame_%06d.jpg -y
```

입력 영상을 1280x720으로 스케일링한 뒤, 전체 프레임을 JPEG(품질 2)으로 추출한다.

**썸네일 추출**:

```bash
ffmpeg -ss 00:00:00 -i /data/video.mp4 \
  -f webp -s 320x180 -vframes 1 \
  /data/thumbnail.webp -y
```

영상 첫 프레임을 320x180 WebP 이미지로 추출한다.

두 명령 모두 별도의 thread 옵션(`-threads`)을 지정하지 않았다. 나중에 살펴보겠지만, 이것도 튜닝 포인트가 된다.

<br>

# 문제

## 현상: 동일 노드에서 37배 성능 차이

동일한 노드에서 동일한 이미지를 사용해 테스트했다.

| 환경 | 처리 시간 | CPU 제한 |
|------|----------|---------|
| Docker 컨테이너 | 4.5초 | 없음 |
| K8s Pod | 148초 | `1000m` (1 core) |

약 37배 차이다. 같은 노드, 같은 이미지, 같은 영상인데 K8s Pod에서만 비정상적으로 느리다.

<br>

## 두 환경의 차이

눈에 바로 띄는 차이는 CPU limit이다. K8s Deployment 매니페스트의 리소스 설정은 다음과 같았다.

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

이 값은 초기에 배경지식이 부족한 상태에서 잡은 초깃값이었다. 웹 서비스나 API 서버의 리소스 설정 예시를 찾아보면 CPU request 100m~500m, limit 1 core 정도로 안내하는 글이 많은데, 그 기준을 그대로 참고했다. 실측값을 보고 추후 조정하려고는 했지만, 이 서비스의 워크로드 특성 — ffmpeg라는 CPU-intensive한 작업이 핵심이라는 점 — 을 고려하지 못한 채 일반적인 API 서버 기준을 적용한 것이 문제였다.

> 돌이켜 보면, CPU limit을 설정하는 것 자체에 대한 논의가 있다는 것도 당시에는 몰랐다. CPU는 compressible 자원이라 limit을 초과해도 프로세스가 죽지 않고 throttling만 발생하기 때문에, request만 적절히 설정하면 CFS가 공정하게 분배해 주므로 [CPU limit을 아예 설정하지 않는 것이 낫다는 시각](https://littlemobs.com/blog/kubernetes-cpu-request-limit-configuration/)도 있다. 물론 무조건 limit을 빼는 것이 정답은 아니고, 워크로드 특성에 맞는 설정이 필요하다. 이 시리즈에서는 CPU limit을 조정하면서 변화를 관찰하고, 적절한 값을 찾아가는 과정을 다룬다.

<br>

CPU limit `1000m`은 1 core를 의미한다. 반면, Docker 컨테이너는 CPU limit 없이 실행되어 노드의 모든 CPU를 사용할 수 있었다.

그렇다면 CPU limit이 원인일까? 직관적으로는 그렇게 보인다. ffmpeg 프레임 추출은 영상 디코딩, 스케일 필터 적용, JPEG 인코딩 등 CPU를 많이 사용하는 작업이고, 1 core 제한이 병목이 되었을 수 있다.

하지만 단정짓기는 이르다. "이것 때문이겠지"라는 직감만으로 움직이면 놓치는 것이 생긴다.

<br>

## 의심 요인

성능 차이를 만들 수 있는 요인은 CPU limit 외에도 여러 가지가 있다.

| 요인 | 의심 근거 |
|------|----------|
| **CPU 리소스 제약** | Pod CPU limit `1000m` 설정, ffmpeg는 CPU-intensive 작업 |
| **I/O 성능 차이** | Volume mount 방식(PVC vs bind mount), container runtime 차이 |
| **메모리 압박** | memory limit `2Gi` 설정, ffmpeg 프레임 추출 시 버퍼 필요 |
| **네트워크 오버헤드** | K8s 환경의 CNI 플러그인, kube-proxy 등 추가 레이어 |

CPU가 유력해 보이는 이유는 있다. 나중에 살펴보겠지만, TTFB(Time To First Byte)는 두 환경 모두 약 0.2초로 유사했고, 차이가 벌어지는 구간이 ffmpeg 처리 구간이었기 때문이다. 그런데 37배라는 차이가 단순히 "CPU 1 core 제한" 만으로 설명이 될까? 노드에 CPU가 충분히 있다 해도, 1 core면 1 core 속도로 돌아가야지 왜 그보다도 훨씬 느린 걸까?

이 질문에 답하려면 몇 가지 개념을 짚어봐야 한다. 리눅스가 CPU 시간을 어떻게 분배하는지, Kubernetes의 CPU limit이 실제로 어떤 메커니즘으로 동작하는지, 그리고 ffmpeg가 내부적으로 스레드를 어떻게 사용하는지. 

<br>

# 마치며

다음 글부터 이 문제를 이해하기 위한 배경지식을 정리한다. CPU와 리눅스 스케줄러, cgroup, 컨테이너와 쿠버네티스의 CPU 리소스 관리, 그리고 ffmpeg의 스레드 모델이다. 배경지식을 바탕으로 가설을 세우고, 실험으로 검증해 나가려고 한다.
