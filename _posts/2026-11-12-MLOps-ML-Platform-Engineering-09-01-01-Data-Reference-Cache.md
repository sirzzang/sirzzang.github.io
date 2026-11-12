---
title: "[Kubeflow Pipelines] 머신러닝 플랫폼 엔지니어링: Kubeflow Pipelines와 학습 트러블슈팅 - 9.1.1. 이름으로 가리킨 데이터와 캐시"
excerpt: "Kubeflow Pipelines의 캐시와 importer, PVC, MLflow 데이터셋 기록이 데이터의 무엇을 보고 같다고 판단하는지 로컬 클러스터에서 확인하며, 데이터 내용이 바뀌었을 때 생기는 일을 알아 보자."
categories:
  - mlops-pipeline
  - mlops-data
  - study
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - MLOps
  - Kubeflow
  - Kubeflow-Pipelines
  - MLflow
  - Data-Lineage
  - Machine-Learning-Platform-Engineering-Study
  - Machine-Learning-Platform-Engineering-Study-Week-4
use_math: false
last_modified_at: 2026-11-12
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Machine Learning Platform Engineering Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 학습 파이프라인의 단계들은 데이터 자체보다 데이터가 있는 곳의 이름(경로, 저장소 주소, 볼륨 이름)을 주고받는 경우가 많다. 4주차 책 범위의 Kubeflow Pipelines(KFP)도 큰 데이터는 경로로 넘기고, 9.1절에서는 볼륨 요청 객체(PVC) 하나를 여러 단계가 함께 붙여 쓴다([단계 사이에 넘기는 것](#단계-사이에-넘기는-것))
- KFP는 같은 이름의 파이프라인에서 같은 단계가 같은 입력으로 다시 실행되면 이전 결과를 재사용하는 실행 캐시를 기본으로 켜 둔다. 이 캐시가 입력이 같은지 판단할 때 데이터 쪽에서 비교하는 값은 경로 문자열, PVC 이름, KFP가 아티팩트를 등록할 때 붙인 ID뿐이고 파일 내용은 보지 않는다([KFP 실행 캐시의 키](#kfp-실행-캐시의-키))
- 로컬 kind 클러스터에서 데이터 내용만 바꾸고 같은 파이프라인을 다시 돌리자, URL 다운로드와 고정 경로를 아티팩트로 등록하는 importer의 기본 설정, PVC 공유 세 경우 모두 이전 결과가 경고 없이 재사용됐다([실험 2](#실험-2-실행-사이-데이터-변경)). 실행 도중 공유 PVC의 파일 내용만 바꾸면 검증 단계는 실패하지 않고 바뀐 데이터로 검증을 마쳤다([실험 1](#실험-1-실행-중-데이터-변경))
- MLflow도 파일 데이터셋을 `MetaDataset`으로 기록하면 데이터셋을 구별하는 digest가 이름과 원본 위치로만 계산돼, 내용이 다른 두 학습 기록이 데이터셋 레코드 하나에 묶였다. 생성자에 내용 다이제스트(파일 내용으로 계산한 해시)를 넘기자 레코드가 둘로 나뉘었다([실험 4](#실험-4-mlflow-데이터셋-digest))
- 데이터는 내용이 바뀌지 않는 이름(버전 디렉터리, 스냅샷 ID)으로 가리켜야 캐시와 기록이 이름만 보고도 맞게 동작한다고 보지만, 이 방식은 시험하지 않았다([바뀌지 않는 이름](#바뀌지-않는-이름)). 이름을 바꿀 수 없는 경로에서 내용 다이제스트를 다음 단계의 입력 파라미터로 넘기자 캐시가 내용 변경을 알아차렸고, 실행 중 변경은 막지 못했지만 검증 단계의 명시적 오류로 드러났다. 이때 다이제스트 단계와 검증 단계의 캐시는 꺼야 하고, 제출할 때 `enable_caching`을 주면 이 설정이 덮어써진다([캐시 키에 넣은 내용 다이제스트](#캐시-키에-넣은-내용-다이제스트))

<br>

# 들어가며

[4.1.1편]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-01-Introduction %}#kubeflow-pipelines)에서 KFP에 데이터 검증 단계를 두려면 실행 캐시를 운영 조건으로 따져야 한다고 적었다. KFP는 같은 파이프라인에서 같은 단계가 같은 입력으로 다시 실행되면 실행 파드를 띄우지 않고 이전 결과를 가져다 쓰는데, 이 실행 캐시가 기본으로 켜져 있기 때문이다. 그때 5장 실습에서 확인할 질문으로 "캐시를 켠 채 데이터만 바뀌면 무슨 일이 생기는지"를 남겼다. 5장 실습 글을 따로 쓰지 않아 그 질문이 그대로 남아 있었다.

4주차 스터디 범위는 책 [머신러닝 플랫폼 엔지니어링](https://www.onlybook.co.kr/entry/mlops)의 7장부터 9.1절까지로, KFP로 학습 파이프라인을 만드는 내용이다. 7장은 컴포넌트 사이에 데이터를 넘기는 방법과 데이터 준비 파이프라인, 8장은 학습·검증 컴포넌트, 9.1절은 여러 단계가 PVC(PersistentVolumeClaim, 쿠버네티스에서 볼륨을 요청하는 객체) 하나를 함께 붙여 데이터를 공유하는 방법을 다룬다.

스터디에서 공유된 실습 기록에도 이 질문과 관련된 장면이 두 번 있다. 7장 실습에서는 같은 데이터 준비 파이프라인을 컨테이너 이미지 방식으로 바꿔 다시 돌렸는데, 두 버전이 결과를 같은 저장소 경로에 써서 그 경로에는 나중 버전의 파일만 남았다. 앞 버전의 결과는 run(KFP가 파이프라인을 한 번 실행하는 단위)마다 KFP가 따로 만드는 경로에만 남았다. 8장 실습에서는 7장의 데이터 준비 컴포넌트를 가져다 써도 캐시가 적중하지 않아 매번 다운로드와 분할을 다시 했다. 원인을 확인하지 못한 채 고정 경로의 데이터를 가져오는 방식으로 바꿨다.

학습 플랫폼을 운영하면서도 비슷한 일을 겪었다. 여러 날 걸리는 분산 학습이 수십 epoch째 돌던 중, 직전 검증이 끝난 뒤 데이터셋 정리로 공유 스토리지의 검증 데이터가 다른 디렉터리로 옮겨졌다. 학습은 검증 데이터를 경로로만 알고 있어서 다음 검증에서 데이터를 여는 시점에 여러 프로세스가 함께 실패했다. 이 사례의 경과는 [9.1.2편]({% post_url 2026-11-12-MLOps-ML-Platform-Engineering-09-01-02-Data-Artifact-Cases %}#사례-1-학습-중에-옮겨진-검증-데이터)이 다룬다.

*데이터를 이름으로 가리킬 때 파이프라인은 그 아래 내용이 바뀐 것을 언제 알아차릴까. 캐시는 무엇을 보고 같은 실행이라고 판단할까.* 로컬 kind 클러스터에 KFP를 올려 확인했고, 코드와 결과는 [실험 폴더](https://github.com/sirzzang/sirzzang.github.io/tree/master/assets/data/mlpe-ch09-data-reference)에 두었다.

<br>

# 단계 사이에 넘기는 것

KFP의 컴포넌트는 각자 별도의 파드에서 실행되므로 한 단계가 메모리에 올린 데이터를 다음 단계가 볼 수 없다. 그래서 KFP는 단계 사이에 넘기는 것을 둘로 나눠, 숫자나 문자열 같은 작은 값은 파라미터로 값 그대로 넘기고 파일이나 디렉터리는 아티팩트로 넘긴다. 아티팩트는 KFP가 ML Metadata(MLMD)라는 기록 저장소에 항목을 만들고 등록 순서대로 번호(ID)를 붙인다. 이 번호는 파일 내용과 관계없이 정해진다.

데이터를 다음 단계로 넘기는 방법은 책과 공유된 실습 기록에 세 가지가 나온다.

| 방식 | 나오는 곳 | 다음 단계가 받는 것 | 실제 데이터의 위치 |
|---|---|---|---|
| 아티팩트 전달 | 책 7.2절, 7.3절 | 객체 저장소 경로 | 단계가 끝날 때 KFP가 run 전용 경로에 올린 사본 |
| importer | 공유된 8장 실습 | 객체 저장소 경로 | 파이프라인 밖에서 미리 올려 둔 고정 경로 |
| PVC 공유 | 책 9.1절 | PVC 이름과 마운트 경로 | 여러 run이 함께 쓰는 볼륨 |

아티팩트 전달은 책 7.2.2절이 큰 데이터에 권하는 방식이다. 큰 데이터를 값으로 넘기면 파드의 메모리 한도를 넘겨 OOMKilled로 종료될 수 있으니 파일이나 디렉터리에 쓰고 그 경로를 넘기라는 것이다. 컴포넌트가 `Output[Dataset]` 같은 출력 아티팩트에 파일을 쓰면 KFP가 단계가 끝날 때 객체 저장소에 올리고 다음 단계가 시작할 때 내려받는다. 올리는 경로는 `<파이프라인 루트>/<파이프라인 이름>/<run ID>/...`라 run마다 새 경로가 된다([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/metadata/client.go#L410-L423)).

importer(`dsl.importer`)는 이미 객체 저장소에 있는 경로를 아티팩트로 등록해 다음 단계에 넘긴다. 공유된 8장 실습에서는 7장에서 만든 분할 결과를 고정 경로에 복사해 두고 importer로 가져와, 25분 걸리던 다운로드와 9분 걸리던 분할을 건너뛰었다.

PVC 공유는 책 9.1절의 방식이다. 책은 7장과 8장의 파이프라인이 단계마다 데이터를 다시 내려받는다는 점을 한계로 꼽는다. 객체 저장소(MinIO)가 POSIX 파일시스템이 아니어서 일반 파일처럼 다루기 어렵다는 점도 PVC를 쓰는 이유로 든다. 데이터를 한 번 내려받은 볼륨을 여러 단계가 마운트하므로 복사가 없다. 실험에 쓴 KFP 2.17.3은 MinIO 대신 S3 호환 저장소 SeaweedFS를 쓰지만 경로는 `minio://`로 표기한다([4.1.2편]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-02-Lab-Environment %}#객체-저장소-minio-대신-seaweedfs)).

공유된 9.1절 실습은 PVC 공유와 객체 저장소 방식(importer, 아티팩트 전달)을 이렇게 비교했다. PVC 재사용은 복사가 없지만 데이터 버전이 파이프라인 밖(PVC)에 있어서 어떤 데이터를 썼는지가 파이프라인의 기록에 남지 않는다. 반면 객체 저장소 방식은 MinIO 경로로 계보, 즉 어느 run이 어떤 데이터를 읽고 썼는지의 기록이 남지만 단계마다 올리고 내려받아야 한다. 8장 실습 기록에서는 17GB를 파드로 받는 데 148초가 걸렸다.

**세 방식 모두 다음 단계에 넘기는 것은 데이터가 있는 곳의 이름이다.** 방식에 따라 달라지는 것은 그 이름 아래 내용이 run이 도는 동안, 그리고 다음 run까지 그대로인지다. importer의 고정 경로와 공유 볼륨은 파이프라인 밖의 누구든 바꿀 수 있고, 아티팩트 경로만 run마다 새로 만들어진다.

<br>

# 캐시와 importer, MLflow가 비교하는 값

단계가 넘겨받는 것이 이름이라면, 캐시나 기록이 두 데이터를 같다고 판단할 때 무엇을 비교하는지에 따라 내용이 바뀐 것을 알아차리는지가 정해진다. 그래서 KFP의 실행 캐시와 importer, MLflow의 데이터셋 기록이 비교하는 값을 소스에서 확인했다. 캐시와 MLflow는 비교할 값을 다이제스트로 줄여 쓴다.

> **참고: 다이제스트(digest)** 데이터를 해시 함수에 넣어 얻은 짧은 값이다. 같은 입력이면 같은 값이, 입력이 조금만 달라도 다른 값이 나와 두 데이터가 같은지 비교할 때 쓴다.

다이제스트는 해시에 무엇을 넣느냐에 따라 성질이 갈려서 이 글에서는 둘로 나눠 부른다. 파일 내용을 넣은 내용 다이제스트는 내용이 바뀌면 값이 바뀌고, 파일 이름이나 경로만 넣어 계산한 이름 기반 다이제스트는 내용이 바뀌어도 값이 그대로다.

## KFP 실행 캐시의 키

KFP는 단계마다 실행 파드보다 먼저 driver라는 준비 파드를 띄우고, 캐시 조회도 이 driver가 한다. [4.1.2편의 검증]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-02-Lab-Environment %}#검증-파이프라인-한-번-실행과-저장소-확인)에서 같은 인자로 두 번째 제출한 run이 driver 파드만 돌리고 끝난 것도 여기서 캐시가 적중했기 때문이다. driver는 다음 항목으로 캐시 키를 만든다([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/cacheutils/cache.go#L173-L229)).

| 항목 | 들어가는 값 |
|---|---|
| 입력 아티팩트 | MLMD 아티팩트 ID |
| 입력 파라미터 | 값 그대로 |
| 출력 | 아티팩트의 이름·타입·메타데이터(경로는 뺀다), 파라미터의 타입 |
| 컨테이너 | 이미지, 명령과 인자 |
| PVC | 마운트하는 PVC 이름 |

driver는 이 키를 JSON으로 직렬화해 SHA-256으로 해시한 fingerprint를 만들고, 이 값으로 ml-pipeline API 서버에 성공한 이전 실행이 있는지 묻는다. 이때 같은 네임스페이스에서 같은 이름의 파이프라인 안의 실행만 찾고, 찾은 것 가운데 가장 최근 것 하나를 쓴다([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/driver/cache.go#L80-L130), [조회](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/cacheutils/cache.go#L105-L138)). 오래된 실행을 거르는 조건은 없다. fingerprint도 다이제스트이고 파라미터 값, 이미지, 명령처럼 이름이 아닌 값도 들어간다. 다만 데이터 쪽에서 키에 들어가는 값은 경로 문자열, 아티팩트 ID, PVC 이름뿐이라 데이터에 대해서는 이름 기반 다이제스트로 동작한다.

PVC 이름을 키에 넣는 이유는 소스 주석에 있다.

```go
// getFingerPrint generates a fingerprint for caching. The PVC names are included in the fingerprint since it's assumed
// PVCs have side effects (e.g. files written for tasks later on in the run) on the execution. If the PVC names are
// different, the execution shouldn't be reused for the cache.
```

실행이 PVC에 부수 효과(같은 run의 뒤 단계가 쓸 파일 등)를 남긴다고 보고 이름을 넣지만, 키에 들어가는 것은 이름뿐이다. **캐시 키의 어느 항목에도 파일 내용은 없다.** 같은 이름의 PVC나 같은 ID의 아티팩트 아래 내용이 바뀌어도 키가 그대로인 것은 이 때문이다.

캐시에는 캐시를 켠 채 실행해 적중하지 않은 단계만, 그것도 [성공한 뒤](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/component/launcher_v2.go#L300-L316)에 fingerprint와 함께 기록된다. 그래서 캐시를 끄고 돈 실행은 나중에 캐시를 켠 run이 찾지 못한다.

<details markdown="1">
<summary><b>캐시 키를 만드는 코드</b></summary>

```go
// backend/src/v2/cacheutils/cache.go (KFP 2.17.3)
func (c *client) GenerateCacheKey(
	inputs *pipelinespec.ExecutorInput_Inputs,
	outputs *pipelinespec.ExecutorInput_Outputs,
	outputParametersTypeMap map[string]string,
	cmdArgs []string, image string,
	pvcNames []string,
) (*cachekey.CacheKey, error) {
	cacheKey := cachekey.CacheKey{
		InputArtifactNames:   make(map[string]*cachekey.ArtifactNameList),
		InputParameterValues: make(map[string]*structpb.Value),
		OutputArtifactsSpec:  make(map[string]*pipelinespec.RuntimeArtifact),
		OutputParametersSpec: make(map[string]string),
	}

	for inputArtifactName, inputArtifactList := range inputs.GetArtifacts() {
		inputArtifactNameList := cachekey.ArtifactNameList{ArtifactNames: make([]string, 0)}
		for _, artifact := range inputArtifactList.Artifacts {
			inputArtifactNameList.ArtifactNames = append(inputArtifactNameList.ArtifactNames, artifact.GetName())
		}
		cacheKey.InputArtifactNames[inputArtifactName] = &inputArtifactNameList
	}

	for inputParameterName, inputParameterValue := range inputs.GetParameterValues() {
		cacheKey.InputParameterValues[inputParameterName] = inputParameterValue
	}

	for outputArtifactName, outputArtifactList := range outputs.GetArtifacts() {
		if len(outputArtifactList.Artifacts) == 0 {
			continue
		}
		// TODO: Support multiple artifacts someday, probably through the v2 engine.
		outputArtifact := outputArtifactList.Artifacts[0]
		outputArtifactWithUriWiped := pipelinespec.RuntimeArtifact{
			Name:     outputArtifact.GetName(),
			Type:     outputArtifact.GetType(),
			Metadata: outputArtifact.GetMetadata(),
		}
		cacheKey.OutputArtifactsSpec[outputArtifactName] = &outputArtifactWithUriWiped
	}

	for outputParameterName := range outputs.GetParameters() {
		outputParameterType, ok := outputParametersTypeMap[outputParameterName]
		if !ok {
			return nil, fmt.Errorf("unknown parameter %q found in ExecutorInput_Outputs", outputParameterName)
		}

		cacheKey.OutputParametersSpec[outputParameterName] = outputParameterType
	}

	cacheKey.ContainerSpec = &cachekey.ContainerSpec{
		Image:    image,
		CmdArgs:  cmdArgs,
		PvcNames: pvcNames,
	}

	return &cacheKey, nil
}
```

입력 아티팩트는 `artifact.GetName()`만 키에 넣는다. driver가 MLMD의 아티팩트를 실행 입력으로 바꿀 때 이 필드에 아티팩트 ID를 10진 문자열로 넣으므로([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/metadata/converter.go#L186-L188)), 실험의 driver 로그에서 이 값은 `"183"` 같은 숫자였다.

</details>

> **참고**: 캐시 키의 구성은 버전마다 조금씩 다르고, 위는 실험에 쓴 2.17.3 기준이다. 공유된 실습 환경의 2.4.1은 캐시 키에 PVC 이름이 없어서 PVC가 달라도 키가 같다([2.4.1 소스](https://github.com/kubeflow/pipelines/blob/2.4.1/backend/src/v2/cacheutils/cache.go#L99-L102)). 2026년 10월 28일 릴리스된 2.18.0은 컨테이너 환경 변수를 키에 더했고([2.18.0 소스](https://github.com/kubeflow/pipelines/blob/2.18.0/backend/src/v2/cacheutils/cache.go#L225-L230)), SDK에 이미 있던 사용자 지정 키(`cache_key`)를 driver가 실제로 쓰기 시작했다. 파이프라인 이름으로 조회 범위를 나누는 것은 세 버전이 같다([2.4.1의 조회](https://github.com/kubeflow/pipelines/blob/2.4.1/backend/src/v2/cacheutils/cache.go#L143-L176)). 설치하면 `cache-server`도 함께 뜨는데, 이것은 v1 파이프라인의 캐시를 맡는 웹훅이라 v2 파드는 건너뛴다([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/cache/server/mutation.go#L97-L101)).

캐시를 끄는 방법은 범위에 따라 넷이다.

- 단계 하나: `set_caching_options(False)`
- 파이프라인 전체의 기본값: 컴파일할 때 `--disable-execution-caching-by-default`(환경 변수 `KFP_DISABLE_EXECUTION_CACHING_BY_DEFAULT`)
- 제출 시점: `enable_caching` 인자가 최상위 단계의 설정을 모두 그 값으로 덮어쓴다. 반복·조건·종료 처리(ExitHandler) 그룹과 하위 파이프라인 안의 단계, 업로드한 파이프라인 버전으로 만든 run에는 적용되지 않는다([덮어쓰는 범위](https://github.com/kubeflow/pipelines/blob/2.17.3/sdk/python/kfp/client/client.py#L1771-L1786), [패키지 제출에만 적용](https://github.com/kubeflow/pipelines/blob/2.17.3/sdk/python/kfp/client/client.py#L962-L971))
- 클러스터 전체: API 서버 설정 `CacheEnabled`(기본값 true)를 끄면 driver가 `--cache_disabled`로 실행된다

## importer의 재사용

importer에는 `reimport` 옵션이 있고 기본값은 `False`다. `True`면 실행할 때마다 새 아티팩트를 등록한다. `False`면 같은 경로로 등록된 기존 아티팩트 가운데 다음 조건을 모두 만족하는 것을 찾아 처음 찾은 것을 돌려준다([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/component/importer_launcher.go#L168-L184), [비교 조건](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/metadata/client.go#L1303-L1347)).

- 타입, 상태, 경로가 같다
- 새로 등록하려는 메타데이터 항목의 값이 모두 같다
- 같은 이름의 파이프라인에서 쓰인 적이 있다

조건은 모두 MLMD에 기록된 값이라 파일을 열지 않는다.

```go
// backend/src/v2/component/importer_launcher.go (KFP 2.17.3)
	if l.importer.Reimport {
		return artifactToImport, nil
	}
	matchedArtifact, err := l.metadataClient.FindMatchedArtifact(ctx, artifactToImport, execution.GetPipeline().GetCtxID())
	...
	if matchedArtifact != nil {
		return matchedArtifact, nil
	}
```

`reimport=False`로 기존 아티팩트를 돌려받으면 다음 단계의 입력 아티팩트 ID가 이전 run과 같다. [캐시 키](#kfp-실행-캐시의-키)에는 그 ID가 들어가므로 경로 아래 파일을 바꿔도 다음 단계는 캐시가 적중해 이전 결과를 재사용하고, 이것은 [S2b](#실험-2-실행-사이-데이터-변경)에서 확인했다. 공유된 실습의 importer도 기본값 `reimport=False`였으니 원본 경로의 데이터를 바꿔 다시 돌리면 같은 구조가 된다. 이 동작을 2.4.1에서 시험하지는 않았다. 반대로 `True`면 매번 새 ID가 생기므로 데이터가 그대로여도 다음 단계의 캐시는 적중하지 않는다.

## MLflow의 데이터셋 기록

같은 구조가 MLflow에도 있다. MLflow의 run은 학습 한 번을 기록하는 단위로 KFP의 run과는 별개이고, MLflow는 [Dataset tracking](https://mlflow.org/docs/latest/ml/dataset/)으로 이 run이 어떤 데이터로 학습했는지 남긴다. Dataset은 이름(name), 자동으로 계산되는 다이제스트(digest), 원본 위치(source), 스키마(schema), 요약 통계(profile)를 갖는다. run에는 `mlflow.log_input(dataset, context="training")`처럼 입력으로 붙인다. 데이터 타입별 Dataset(pandas, Spark, NumPy 등) 외에 데이터를 담지 않고 메타데이터만 갖는 `MetaDataset`도 있다. 문서는 이 타입을 외부 저장소의 대용량 데이터처럼 메타데이터와 계보만 남기고 싶을 때 쓰라고 소개한다. 공유 스토리지에 있는 이미지 디렉터리나 아카이브 파일을 기록한다면 이 타입을 쓰게 된다.

문서는 digest 계산 방식을 설명하며 `MetaDataset`은 "metadata only (name, source, schema) - no actual data hashing"이라고 적는다. 2026년 11월 기준 최신인 3.18.0의 코드도 이름, 원본 위치, 원본 종류, 스키마만으로 계산하며 데이터는 읽지 않는다([소스](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/data/meta_dataset.py)).

```python
# mlflow/data/meta_dataset.py (MLflow 3.18.0)
    def _compute_digest(self) -> str:
        """Computes a digest for the dataset.

        The digest computation of `MetaDataset` is based on the dataset's name, source, source type,
        and schema instead of the actual data. Basically we compute the sha256 hash of the config
        dict.
        """
        config = {
            "name": self.name,
            "source": self.source.to_json(),
            "source_type": self.source._get_source_type(),
            "schema": self.schema.to_dict() if self.schema else "",
        }
        return hashlib.sha256(json.dumps(config).encode("utf-8")).hexdigest()[:8]
```

표준 데이터셋은 문서에 "data content and structure"로 계산한다고만 적혀 있다. pandas 데이터셋의 [digest 코드](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/data/digest_utils.py)를 보면 앞 1만 행(`MAX_ROWS = 10000`)의 문자열·숫자 열 값만 해시하고 여기에 전체 행 수와 열 이름을 더한다. [`log_input`](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/tracking/fluent.py)은 이렇게 계산한 digest를 그대로 run에 남긴다.

추적 서버의 SQL 저장소는 기록을 쌓을 때도 digest에 기댄다. 한 실험 안에서 이름과 digest가 같은 데이터셋을 [이미 있는 레코드](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/store/tracking/sqlalchemy_store.py#L2532-L2546)로 보고 새 run을 그 레코드에 연결한다. 그래서 같은 경로의 파일이 바뀐 두 run은 MLflow에서 같은 데이터셋 레코드를 가리키게 된다. 생성자에 `digest`를 직접 넘길 수 있으니 내용 다이제스트를 따로 계산해 넘기면 이 문제를 피할 수 있다. 하지만 MLflow는 digest를 36자까지만 받는다. 저장하기 전에 `MAX_DATASET_DIGEST_SIZE`(36)로 길이를 검사하고([소스](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/utils/validation.py#L911-L915)) SQL 저장소의 열도 36자라([소스](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/store/tracking/dbmodels/models.py#L651)), SHA-256의 64자를 그대로 넣을 수는 없고 앞부분을 잘라 넘겨야 한다.

<br>

# 실험

## 환경과 데이터

[4.1.2편]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-02-Lab-Environment %})과 같은 방식으로 Apple Silicon Mac에 새 kind 클러스터(Docker 컨테이너를 노드로 쓰는 로컬 쿠버네티스)를 만들었다. 여기에 Kubeflow 전체 없이 파이프라인 기능만 있는 KFP standalone 2.17.3을 올렸고, SDK도 2.17.3이다.

| 구성 | 내용 |
|---|---|
| 공유 스토리지 | Mac의 디렉터리를 kind 노드에 붙이고 hostPath PV와 PVC로 연결했다. Mac에서 파일을 바꾸면 파드 안에서도 바로 바뀐다 |
| 데이터 | `dataset/train`에 20개, `dataset/val`에 8개, 파일당 64KiB. 시드를 고정해 만든다 |
| 데이터 서버 | 같은 디렉터리를 HTTP로 내보내는 서버. 책 7.3절의 URL 다운로드 단계를 흉내 낸다 |
| 바꾸기 | `edit`는 val 파일 하나의 내용만 바꾼다(이름과 크기는 그대로). `edit-train`은 train 파일 하나를 같은 방식으로 바꾼다. `reorg`는 val 디렉터리를 다른 이름으로 옮긴다 |
| 학습 단계 | 정해진 시간만 기다리는 대역이다. 데이터를 읽지 않는다 |

공유 디렉터리가 hostPath라 바꾼 내용이 곧바로 보인다. 반면 NFS 같은 네트워크 파일시스템은 클라이언트의 속성 캐시 때문에 바뀐 내용이 보이는 시점이 노드마다 다를 수 있다.

모든 단계는 같은 방식으로 내용 다이제스트를 계산한다. 하위 디렉터리까지 상대 경로 순으로 상대 경로, 크기, 파일 내용의 SHA-256을 차례로 붙여 다시 SHA-256으로 해시한다. 앞 8자로 적으면 처음 만든 val의 내용 다이제스트는 `e8d3825e`, `edit` 뒤에는 `e7943a3f`다. 각 run은 한 번씩 돌렸는데, 캐시 키가 같은지는 정해진 동작으로 결정되므로 반복하지 않았다.

캐시가 적중했는지는 run API의 단계 상태로 구별할 수 없었다. API 정의에는 캐시로 건너뛴 경우를 위한 `SKIPPED` 상태가 있지만([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/api/v2beta1/run.proto#L233-L237)) 이 실험에서는 캐시가 적중한 단계도 `SUCCEEDED`로 나왔다. 그래서 KFP가 run을 실행하는 Argo Workflows(쿠버네티스에서 여러 파드를 순서대로 실행하는 워크플로 엔진)의 워크플로 상태를 봤다. 단계마다 driver가 여기에 `cached-decision`이라는 값을 남기는데, 이 값이 `true`면 실행 파드를 만들지 않은 것이다.

> **로그 표기**: `·` 줄은 실험 스크립트(`run.py`)가 데이터를 바꾼 시점이고, 화살표 뒤는 그 직후 실제 데이터의 내용 다이제스트다. `[run 이름]` 줄은 run의 상태와 단계별 상태로, 단계 이름은 코드의 함수 이름에서 `_`를 `-`로 바꾼 것이고 나열 순서는 실행 순서와 관계없다. `[캐시]`는 `cached-decision`이 `true`였다는 표시이고, 단계 상태 `None`은 앞 단계가 실패해 실행되지 않았다는 뜻이다. 줄 끝의 `report=`는 마지막 단계가 받아서 남긴 다이제스트(없으면 `-`)이고, `↑ train 실행 중에 바꿨다`는 그 변경이 학습 단계 도중에 일어났다는 표시다.

```text
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
  [s2c-2] run=SUCCEEDED  report=SUCCEEDED, digest-path=SUCCEEDED[캐시]  report=e8d3825e
```

위 예에서는 실제 데이터가 `e7943a3f`인데 run이 `e8d3825e`를 남겼으므로 이전 결과를 재사용한 것이다.

## 실험 1: 실행 중 데이터 변경

실행 사이의 캐시를 따지기 전에, 한 run이 도는 동안 데이터가 바뀌면 무엇이 일어나는지부터 봤다. 캐시를 끄고 학습 단계가 도는 동안 val을 바꾸며 두 파이프라인을 비교했다.

- `shared`: 첫 단계 `list-files`가 학습 전에 PVC의 val 파일 목록을 만들고, 학습 뒤에는 `validate-listed`가 그 목록대로 파일을 연다. 데이터로더가 시작할 때 목록을 만들어 두는 방식에 해당한다
- `artifact`: 첫 단계 `stage-in`이 PVC의 val을 아티팩트로 복사하고, 학습 뒤에는 `validate-dataset`이 그 사본을 연다

| 실행 중 변경 | `shared` | `artifact` |
|---|---|---|
| `reorg`(디렉터리 이동) | 검증 단계 `FileNotFoundError`로 실패 | 성공, 변경 전 데이터 `e8d3825e`로 검증 |
| `edit`(내용만 변경) | 성공, 바뀐 데이터 `e7943a3f`로 검증 | 성공, 변경 전 데이터 `e8d3825e`로 검증 |

```text
  · data.py reorg → 지금 내용 다이제스트 val 없음, 데이터셋 전체 7520b834
    ↑ train 실행 중에 바꿨다
  [mid-reorg-shared] run=FAILED  train=SUCCEEDED, list-files=SUCCEEDED, report=None, validate-listed=FAILED  report=-
    validate-listed 마지막 오류: FileNotFoundError: [Errno 2] No such file or directory: '/data/dataset/val/img_000.bin'
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
    ↑ train 실행 중에 바꿨다
  [mid-edit-shared] run=SUCCEEDED  train=SUCCEEDED, report=SUCCEEDED, validate-listed=SUCCEEDED, list-files=SUCCEEDED  report=e7943a3f
```

디렉터리가 옮겨지면 공유 경로를 읽는 파이프라인은 학습이 끝난 뒤 검증 단계에서 실패했다. [들어가며](#들어가며)의 운영 사례처럼 학습이 오래 걸릴수록 실패가 늦게 드러나는 구조다. 반면 **이름과 크기는 그대로 두고 내용만 바뀌면 아무 오류 없이 끝났다.** 학습 전에 만든 파일 목록과 검증이 실제로 연 내용이 달라도 run은 성공으로 남아서, 실패한 경우보다 이쪽이 더 알아차리기 어렵다.

run 전용 사본을 읽은 파이프라인은 학습 전에 원본과 별개인 사본을 떠 두었으므로 두 경우 모두 변경 전 내용으로 끝까지 돌았다. 대신 원본이 바뀔 수 있는 구간이 사본을 뜨는 `stage-in` 단계로 옮겨 가서, 복사가 진행되는 도중에 바뀌면 사본이 섞일 수 있다. 캐시를 켜 두면 `stage-in` 자체도 경로와 PVC 이름만으로 캐시가 적중하고, 복사 비용도 따른다. 공유된 실습 기록에서 17GB를 받는 데 걸린 148초가 비슷한 규모의 예다.

importer도 시험했다. 파이프라인 안에서 importer가 넘긴 같은 아티팩트를 학습 전 단계(`digest-dataset`)와 학습 뒤 단계(`validate-dataset`)가 각자 받게 했다. 학습 중에는 같은 객체 경로의 파일을 덮어썼다.

```text
  [mid-edit-importer] run=SUCCEEDED  validate-dataset=SUCCEEDED, report-pair=SUCCEEDED, train=SUCCEEDED, digest-dataset=SUCCEEDED, importer=SUCCEEDED  report=e8d3825e e7943a3f
```

같은 run 안의 두 단계가 같은 아티팩트를 받았는데 내용이 달랐다(`e8d3825e`, `e7943a3f`). 단계마다 객체 저장소에서 다시 내려받았기 때문이다. **importer가 넘기는 아티팩트는 경로를 가리킬 뿐 그 시점의 사본이 아니다.**

## 실험 2: 실행 사이 데이터 변경

이제 4.1.1편에 남긴 질문, 즉 캐시를 켠 채 데이터만 바뀌면 무슨 일이 생기는지를 시험했다. 한 번 돌리고 `edit`로 val 파일 하나의 내용만 바꾼 뒤 같은 인자로 다시 돌리는 실험을, 데이터를 가져오는 방식만 바꿔 세 번 했다. S2a 같은 시나리오 번호는 실험 스크립트(`run.py`)에 붙인 이름이다.

| 시나리오 | 가져오는 방식 | 내용을 바꾼 뒤 | 결과(실제 `e7943a3f`) |
|---|---|---|---|
| S2a | URL에서 다운로드(아티팩트로 전달) | `download`, `digest-dataset` 캐시 적중 | `e8d3825e` |
| S2b | importer `reimport=False`(기본값) | `digest-dataset` 캐시 적중 | `e8d3825e` |
| S2b | importer `reimport=True` | 다시 실행 | `e7943a3f` |
| S2c | PVC 공유 | `digest-path` 캐시 적중 | `e8d3825e` |

`reimport=True`를 뺀 세 경우가 모두 변경 전 값을 냈다. **이전 run의 결과가 아무 경고 없이 재사용됐다.** 다운로드 단계는 URL이 같으니 입력 파라미터가 같고, PVC 단계도 PVC 이름이 같아 키가 같다. 또 다운로드 단계가 캐시로 이전 출력 아티팩트를 돌려주니 그것을 받는 `digest-dataset`의 입력 ID도 같아져 함께 적중했다. S2a에서 run 전체의 캐시를 끄고 다시 돌리자 그제야 `e7943a3f`가 나왔다.

importer 쪽은 driver 로그에서 입력 아티팩트 ID를 확인했는데, 로그의 "같은 객체 경로에 덮어쓰기"는 객체 저장소의 파일 경로를 말한다.

```text
  [s2b-reuse-1] run=SUCCEEDED  report=SUCCEEDED, importer=SUCCEEDED, digest-dataset=SUCCEEDED  report=e8d3825e
    digest-dataset 입력 아티팩트 ID = 183
  [s2b-reimport-1] run=SUCCEEDED  importer=SUCCEEDED, report=SUCCEEDED, digest-dataset=SUCCEEDED  report=e8d3825e
    digest-dataset 입력 아티팩트 ID = 186
  [s2b-reimport-1b-same] run=SUCCEEDED  importer=SUCCEEDED, digest-dataset=SUCCEEDED, report=SUCCEEDED  report=e8d3825e
    digest-dataset 입력 아티팩트 ID = 189
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
  · dataset/val/ → minio://mlpipeline/datasets/toy-val 업로드(같은 객체 경로에 덮어쓰기)
  [s2b-reuse-2] run=SUCCEEDED  report=SUCCEEDED, importer=SUCCEEDED, digest-dataset=SUCCEEDED[캐시]  report=e8d3825e
    digest-dataset 입력 아티팩트 ID = 183
  [s2b-reimport-2] run=SUCCEEDED  importer=SUCCEEDED, digest-dataset=SUCCEEDED, report=SUCCEEDED  report=e7943a3f
    digest-dataset 입력 아티팩트 ID = 193
```

`reimport=False`는 내용이 바뀐 뒤에도 같은 아티팩트 183을 돌려줘서 다음 단계의 캐시가 적중했다. 반면 `reimport=True`는 186, 189, 193으로 매번 새 아티팩트를 만들었다. 데이터가 그대로인 `s2b-reimport-1b-same`에서도 캐시가 적중하지 않았으니, 내용 변경은 놓치지 않지만 그 대가로 캐시를 끈 것과 같아진다.

## 실험 3: 파이프라인 이름과 캐시 조회 범위

캐시가 같은 이름의 파이프라인 안에서만 이전 실행을 찾는지 보려고, 같은 컴포넌트와 같은 인자를 이름만 다른 파이프라인으로 돌렸다. 로그의 `s2d`는 실험 스크립트가 이 실험에 붙인 시나리오 이름이다.

```text
  [s2d-1-original] run=SUCCEEDED  digest-dataset=SUCCEEDED, download=SUCCEEDED, report=SUCCEEDED  report=e8d3825e
  [s2d-2-renamed] run=SUCCEEDED  report=SUCCEEDED, digest-dataset=SUCCEEDED, download=SUCCEEDED  report=e8d3825e
  [s2d-3-original] run=SUCCEEDED  digest-dataset=SUCCEEDED[캐시], report=SUCCEEDED, download=SUCCEEDED[캐시]  report=e8d3825e
```

원래 이름으로 두 번째 돌린 run은 캐시가 적중했지만, 그 사이에 이름만 바꿔 돌린 run에서는 적중하지 않았다. 여기서 이름은 컴파일된 파이프라인 정의(SDK가 파이썬 코드를 제출용 YAML로 바꾼 것)의 이름(`pipelineInfo.name`)이다. driver는 이 값을 [실행 인자](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/compiler/argocompiler/container.go#L195)로 받아 조회 범위로 쓴다. 업로드 경로는 돌려 보지 않아 소스로만 확인했다. UI로 업로드할 때 붙이는 파이프라인 이름과 버전 이름은 API 서버가 [따로 저장](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/apiserver/resource/resource_manager.go#L507-L524)할 뿐 정의의 이름을 바꾸지 않으므로, 같은 정의 이름으로 새 버전을 올리면 캐시를 함께 쓴다.

공유된 실습에서 7장의 컴포넌트를 8장 파이프라인에 가져다 썼을 때 캐시가 적중하지 않은 것도 이것으로 설명된다. 두 파이프라인은 데코레이터에 `data_preparation_pipeline`과 `YOLO Object Detection Pipeline`으로 이름이 적혀 있었다. SDK가 이름을 소문자와 하이픈으로 바꾸므로([소스](https://github.com/kubeflow/pipelines/blob/2.17.3/sdk/python/kfp/dsl/utils.py#L52-L62)) 컴파일된 정의의 이름은 `data-preparation-pipeline`과 `yolo-object-detection-pipeline`으로 달랐다. 공유된 실습 환경의 [2.4.1](https://github.com/kubeflow/pipelines/blob/2.4.1/backend/src/v2/driver/driver.go#L2080)도 같은 이름 안에서만 이전 실행을 찾는다. 이름이 같았더라도 함수 소스를 명령 인자에 실어 실행하는 경량 컴포넌트(lightweight component)는 코드나 SDK 버전이 조금만 달라도 명령 항목이 달라져 키가 달라진다. 두 실습의 명령 항목까지 같았는지는 확인하지 않았다.

## 실험 4: MLflow 데이터셋 digest

소스에서 본 digest 계산이 실제로 내용 변경을 놓치는지 보려고 서버 없이 Dataset 객체만 만들어 digest를 비교했다. (a)는 같은 경로의 파일 내용을 바꾼 전후의 `MetaDataset` 기본 digest, (b)는 2만 행짜리 pandas 표에서 값 하나를 바꾼 전후, (c)는 생성자에 내용 다이제스트를 넘긴 경우다. (d)는 로컬 SQLite 파일을 추적 저장소로 써서 두 run을 기록한 결과다.

```text
(a) MetaDataset 기본 digest   변경 전 35daa1e0  변경 후 35daa1e0  같음=True
(c) digest=내용 다이제스트     변경 전 70ce35b8  변경 후 32d75ab4  같음=False
(b) pandas 앞 1만 행 안(5행) 값 변경   9cfe992a → dbd95021  같음=False
(b) pandas 1만 행 이후(15000행) 값 변경   9cfe992a → 9cfe992a  같음=True
(d) 기본 digest: 내용이 다른 run 2개 → 데이터셋 레코드 1개, run 입력 연결 2개
(d) 내용 다이제스트: 내용이 다른 run 2개 → 데이터셋 레코드 2개, run 입력 연결 2개
```

같은 경로의 파일 내용을 바꿔도 `MetaDataset`의 digest는 같았고, 1만 행 이후의 값만 바꾼 pandas 표도 digest가 같았다. 추적 저장소에서는 내용이 다른 두 run이 데이터셋 레코드 하나를 함께 가리켰고, 내용 다이제스트를 넘긴 경우에만 레코드가 둘로 나뉘었다.

<br>

# 캐시 키에 넣은 내용 다이제스트

실험에서 본 재사용은 모두 캐시 키에 데이터의 이름만 들어가서 생겼다. 그런데 캐시 키에는 입력 파라미터의 값이 그대로 들어가니, 데이터의 내용 다이제스트를 파라미터로 만들어 다음 단계에 넘기면 내용이 캐시 키에 들어간다.

```python
# mount: PVC shared-data 를 /data 에 붙인다(kfp-kubernetes 의 mount_pvc)
# nocache: 이 단계의 캐시를 끈다(set_caching_options(False))
@dsl.pipeline(name="s3-fingerprint")
def s3_fingerprint(seconds: int = 5, tag: str = "s3"):
    fp = mount(nocache(digest_path(root="/data/dataset")))      # 다이제스트 단계는 캐시를 끈다
    model = train(seconds=seconds, data_ref=fp.output)           # 다이제스트가 같을 때만 캐시가 적중한다
    val = mount(nocache(validate_pinned(root="/data/dataset", expected=fp.output, model=model.output)))
    mount(nocache(report(tag=tag, value=val.output)))
```

`digest_path`는 train과 val을 모두 담은 데이터셋 전체의 내용 다이제스트를 계산해 문자열로 내보내고, 학습 단계는 그 값을 입력 파라미터 `data_ref`로 받는다. 검증 단계 `validate_pinned`는 시작할 때 다이제스트를 다시 계산해 학습 전에 받은 값과 다르면 실패한다. `model=model.output`은 학습이 끝난 뒤에 검증하도록 순서를 거는 용도다. PVC를 붙이는 `mount`는 kfp-kubernetes(KFP 파이프라인에 PVC 같은 쿠버네티스 설정을 붙이는 확장 SDK)의 `mount_pvc`를 감싼 헬퍼다([전체 코드](https://github.com/sirzzang/sirzzang.github.io/blob/master/assets/data/mlpe-ch09-data-reference/pipelines.py)).

```text
  · data.py reset → 지금 내용 다이제스트 val e8d3825e, 데이터셋 전체 ee490bba
  [s3-1] run=SUCCEEDED  report=SUCCEEDED, validate-pinned=SUCCEEDED, digest-path=SUCCEEDED, train=SUCCEEDED  report=ee490bba
  [s3-2-same] run=SUCCEEDED  validate-pinned=SUCCEEDED, train=SUCCEEDED[캐시], report=SUCCEEDED, digest-path=SUCCEEDED  report=ee490bba
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
  [s3-3-edit-val] run=SUCCEEDED  validate-pinned=SUCCEEDED, digest-path=SUCCEEDED, report=SUCCEEDED, train=SUCCEEDED  report=90450f6e
  · data.py edit-train → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 f0f713eb
  [s3-4-edit-train] run=SUCCEEDED  train=SUCCEEDED, digest-path=SUCCEEDED, validate-pinned=SUCCEEDED, report=SUCCEEDED  report=f0f713eb
```

데이터가 같은 두 번째 run에서는 학습 단계의 캐시가 적중했다. val이나 train의 파일 하나만 바꾸면 데이터셋 전체의 다이제스트가 달라져 학습 단계가 다시 실행됐다. 캐시를 모두 끄지 않고도 데이터가 바뀐 경우만 다시 실행하게 된 것이다.

실행 중 변경은 [실행 중 데이터 변경](#실험-1-실행-중-데이터-변경)의 `shared`와 같은 조건으로 돌렸다.

```text
  [mid-reorg-digest] run=FAILED  digest-path=SUCCEEDED, train=SUCCEEDED, validate-pinned=FAILED, report=None  report=-
    validate-pinned 마지막 오류: RuntimeError: manifest mismatch: 고정 다이제스트 ee490bba, 현재 7520b834
  [mid-edit-digest] run=FAILED  digest-path=SUCCEEDED, validate-pinned=FAILED, train=SUCCEEDED, report=None  report=-
    validate-pinned 마지막 오류: RuntimeError: manifest mismatch: 고정 다이제스트 ee490bba, 현재 90450f6e
```

`shared`가 조용히 성공했던 내용 변경을 이유를 밝히며 실패로 바꿨다. 다만 실패는 `shared`와 같이 학습이 끝난 뒤에 일어난다. **이 방법은 변경을 막지 못하고 알아차릴 뿐이다.** 여러 날 걸리는 학습이라면 그 시간을 똑같이 잃으므로, 변경의 영향을 받지 않으려면 사본을 뜨거나 [바뀌지 않는 이름](#바뀌지-않는-이름)을 써야 한다. 더 일찍 알아차리려면 학습 코드가 파일을 열 때마다 매니페스트(파일별 경로, 크기, 해시 목록)와 대조해야 한다.

이 방법이 동작하려면 다이제스트를 계산하는 단계와 검증 단계의 캐시를 꺼야 한다. 다이제스트 단계의 입력은 경로 문자열과 PVC 이름뿐이라 캐시를 켜면 [S2c](#실험-2-실행-사이-데이터-변경)처럼 이전 다이제스트를 그대로 돌려준다. 검증 단계도 입력(경로, 고정 다이제스트, 모델)이 이전 run과 같으면 캐시가 적중해 검사를 건너뛴다. [4.1.1편]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-01-Introduction %}#kubeflow-pipelines)에 적은 "원본 데이터만 바뀐 데이터 수집·검증 단계는 캐시를 꺼야 한다"가 이 두 단계에 해당하고, 나머지 단계는 캐시를 켜 둘 수 있다.

또 **제출할 때 `enable_caching=True`를 주면 이 단계별 설정이 덮어써진다.** [캐시를 끄는 방법](#kfp-실행-캐시의-키)에서 본 것처럼 제출 시점의 `enable_caching`은 최상위 단계의 설정을 모두 덮어쓴다. 캐시를 끄고 돈 실행은 캐시에 기록되지 않으므로 첫 제출에서는 드러나지 않고, 그 뒤 데이터를 바꿔 다시 제출할 때 드러난다.

```text
  · data.py reset → 지금 내용 다이제스트 val e8d3825e, 데이터셋 전체 ee490bba
  [s3-5-submit-cache-true] run=SUCCEEDED  report=SUCCEEDED, train=SUCCEEDED[캐시], digest-path=SUCCEEDED, validate-pinned=SUCCEEDED  report=ee490bba
  · data.py edit → 지금 내용 다이제스트 val e7943a3f, 데이터셋 전체 90450f6e
  [s3-6-submit-cache-true-edited] run=SUCCEEDED  digest-path=SUCCEEDED[캐시], validate-pinned=SUCCEEDED[캐시], report=SUCCEEDED, train=SUCCEEDED[캐시]  report=ee490bba
```

첫 제출(`s3-5`)에서는 다이제스트 단계가 실행되면서 캐시에 처음 기록됐다. 그 결과 데이터를 바꾼 뒤의 두 번째 제출(`s3-6`)에서는 다이제스트, 학습, 검증 단계가 모두 캐시에서 적중했다. 실제 데이터는 `90450f6e`인데 변경 전 다이제스트 `ee490bba`로 검증을 통과했다고 남았다. 그래서 다이제스트 방식을 쓰는 파이프라인은 제출할 때 `enable_caching`을 비워 두고 단계별 설정을 따르게 해야 한다.

다이제스트가 보증하는 것은 계산한 시점의 내용뿐이라는 한계도 있다. 학습 도중 바뀌었다가 검증 전에 원래대로 돌아오면 학습이 실제로 읽은 내용과 기록이 다른데도 검사를 통과하는데, 이 경우는 시험하지 않았다.

다이제스트를 계산하려면 데이터를 한 번 다 읽어야 해서 그 비용도 쟀다([측정 코드](https://github.com/sirzzang/sirzzang.github.io/blob/master/assets/data/mlpe-ch09-data-reference/hash_cost.py)).

| 대상(합 1GiB) | 시간 |
|---|---|
| 파일 1개, 내용 SHA-256 | 0.38~0.39초 |
| 64KiB 파일 16,384개, 내용 다이제스트 | 2.26~2.77초 |
| 같은 16,384개, 크기와 수정 시각만 | 0.075~0.081초 |

같은 Mac에서 세 번씩 쟀다. 방금 만든 파일을 페이지 캐시(디스크 읽기를 메모리에 두는 운영체제의 캐시로, KFP 캐시와는 다르다)를 비우지 않고 읽었으므로 저장소 읽기를 뺀 계산 비용에 가깝다. 작은 파일이 많으면 같은 용량이라도 여러 배 느렸다. 네트워크 스토리지에 있는 수 TB 데이터라면 여기에 읽기 대역폭과 파일 열기, 목록 조회 비용이 더해진다. 크기와 수정 시각만 모으면 수십 배 빠르지만 수정 시각을 보존하는 복사로 내용이 바뀌면 놓친다.

2.18.0의 `cache_key`로도 캐시 키에 데이터 버전을 넣을 수 있는데, 2.18.0은 직접 돌려 보지 않았고 소스로 확인했다. `set_caching_options(enable_caching, cache_key=...)`로 키를 주면 [driver](https://github.com/kubeflow/pipelines/blob/2.18.0/backend/src/v2/driver/cache.go#L84-L96)는 입력, 이미지, 명령, 환경 변수, PVC 이름을 모두 무시하고 컴포넌트 이름과 그 키만 해시한다. 그런데 [컴파일러](https://github.com/kubeflow/pipelines/blob/2.18.0/sdk/python/kfp/compiler/pipeline_spec_builder.py#L134-L136)가 이 값을 파이프라인 정의의 문자열 필드에 그대로 넣는다. 앞 단계가 실행 중에 계산한 다이제스트를 받을 수 없고, 파이프라인 파라미터로 run마다 바꿀 수도 없다는 뜻이다. 제출할 때 클라이언트의 `cache_key` 인자로 넣을 수는 있지만 `enable_caching`과 함께 줘야 하고 최상위 단계 전부에 같은 값이 들어간다. `cache_key`는 컴파일할 때 이미 아는 데이터 버전을 넣는 용도인 셈이고, 이미지와 명령이 무시되므로 코드 버전도 키에 함께 넣어야 한다. SDK 2.17.3에도 같은 옵션이 있지만 2.17.3 백엔드의 driver는 이 값을 읽지 않아 아무 표시 없이 무시된다.

<br>

# 바뀌지 않는 이름

실험에서 본 문제는 모두 바뀔 수 있는 경로를 이름으로 넘겨서 생겼다. 내용 다이제스트는 이름 아래 내용이 바뀔 수 있다는 전제에서 쓰는 방법이고, 그 전제를 없애려면 이름 자체가 바뀌지 않는 내용을 가리키게 해야 한다. 한 번 쓰면 덮어쓰지 않는 버전 디렉터리(`dataset/v2026-11-12/`), 객체 저장소의 객체 버전 ID, lakeFS의 커밋이나 DVC의 해시 같은 데이터 버전 관리 도구의 식별자, 볼륨 스냅샷이 그런 이름이다. 이름에 버전이 들어가면 importer의 재사용, KFP의 캐시 키, MLflow의 기본 digest가 모두 이름만 보고도 맞게 동작한다. 그러려면 버전 식별자가 단계에 넘기는 경로 파라미터, importer 경로, `MetaDataset`의 원본 위치처럼 캐시 키와 digest가 보는 문자열에 들어가야 한다. PVC라면 스냅샷으로 새 PVC를 만들어 이름을 바꾸고, 2.4.1처럼 PVC 이름이 키에 없는 버전에서는 그 이름을 파라미터로도 넘겨야 한다. 이 절의 방식은 실험하지 않았다.

내용 다이제스트가 필요하다면 데이터를 만들어 내보내는 쪽이 한 번 계산해 함께 남기는 편이 낫다. 데이터를 쓰는 run마다 수 TB를 다시 읽지 않아도 되기 때문이다.

캐시 키의 이미지도 태그 문자열이라 같은 태그에 다른 이미지를 다시 올리면 키가 같다. 이미지에서는 `@sha256:` 다이제스트로 고정하는 것이 데이터의 버전 경로에 해당한다.

<br>

# 기록을 남기는 주체

이름에 버전을 넣든 내용 다이제스트를 계산하든, 그 값이 run마다 어디에 남는지 정해져 있어야 나중에 어떤 데이터로 학습했는지 찾을 수 있다. 그래서 공개된 학습 인프라 자료에서 그 기록을 누가 맡는지 찾아봤다. 자율주행 회사들의 자료에는 실행을 맡은 워크플로 시스템이 데이터셋과 모델을 job의 입출력으로 다루는 사례가 있었다. NVIDIA는 2019년 GTC [발표](https://developer.download.nvidia.com/video/gputechconf/gtc/2019/presentation/s9649-inside-nvidia-ai-infrastructure-for-self-driving-cars.pdf)에서 학습 인프라 MagLev의 구성 요소로 "Storing, tracking and versioning datasets"를 들었다. Argo 기반 워크플로 엔진은 "Each job is described by inputs and outputs: datasets and models."라고 설명했다. Aurora도 2024년 [글](https://mlops.community/auroras-data-engine-how-we-accelerate-machine-learning-model-workflows/)에서 데이터 엔진의 설계 원칙으로 아티팩트와 릴리스 보고서의 계보 추적을 들고, KFP를 고른 이유 가운데 하나로 메타데이터 추적을 들었다.

KFP의 아티팩트 전달에서도 컴포넌트가 입출력을 선언하면 KFP가 run마다 새 경로에 올리고, 어느 실행이 어느 아티팩트를 읽고 썼는지를 MLMD에 남긴다. 학습 코드가 기록 함수를 부르지 않아도 기록이 생기는 구조다. 다만 실험에서 본 것처럼 KFP도 내용을 해시하지는 않는다. [importer 실행 중 변경 실험](#실험-1-실행-중-데이터-변경)에서는 같은 run의 두 단계가 같은 아티팩트를 받았다고 남았지만 실제로 읽은 내용은 `e8d3825e`와 `e7943a3f`로 달랐다. [S2b](#실험-2-실행-사이-데이터-변경)에서도 내용이 바뀐 뒤의 run이 이전 run과 같은 아티팩트 183을 받았다고 남았다.

학습 플랫폼은 흔히 코드 버전과 이미지 태그를 run에 자동으로 남기지만 데이터는 학습 코드가 경로를 아는 데서 그치기 쉽다. 그래서 데이터 버전도 학습 코드에 기록을 맡기기보다 학습을 실행하는 쪽(제출을 받아 잡을 띄우는 플랫폼이나 오케스트레이터)이 남기는 편이 맞다고 본다. 외부 데이터 관리 시스템이 바뀌지 않는 스냅샷 ID를 준다면 그 ID만 남겨도 충분하다. 같은 ID나 경로 아래 내용이 바뀔 수 있다면 시작할 때 내용 다이제스트를 계산해 함께 남겨야 한다.

<br>

# 정리

[4.1.1편]({% post_url 2026-10-29-MLOps-ML-Platform-Engineering-04-01-01-Introduction %}#kubeflow-pipelines)을 쓰며 남긴 질문을 로컬 클러스터에서 돌려 보니, 데이터를 어떤 방식으로 가져오든 캐시가 비교한 것은 내용이 아니라 이름이었다. 이 시리즈에서 이름과 내용의 어긋남이라고 부르는 일이 KFP에서는 캐시 키와 importer의 재사용에서, MLflow에서는 데이터셋 digest에서 일어난 셈이다. 방식마다 그 어긋남이 드러나는 시점은 아래처럼 갈렸다.

| 방식 | 실행 중 디렉터리 이동 | 실행 중 내용만 변경 | 실행 사이 변경(캐시 켬) | 비용 |
|---|---|---|---|---|
| PVC 공유 | 학습 뒤 검증 단계에서 실패 | 오류 없이 바뀐 데이터로 진행 | PVC 이름이 같아 이전 결과 재사용 | 복사 없음 |
| 아티팩트 전달 | 영향 없음(사본) | 영향 없음(사본) | 가져오는 첫 단계의 입력이 같으면 이전 결과 재사용 | 단계마다 올리고 내려받기 |
| importer `reimport=False` | 시험하지 않음 | 같은 run 안에서도 단계마다 다른 내용 | 같은 아티팩트 ID라 이전 결과 재사용 | 고정 경로에 미리 복사 |
| 내용 다이제스트를 입력으로 | 학습 뒤 검증에서 명시적 실패 | 학습 뒤 검증에서 명시적 실패 | 다이제스트가 달라져 다시 실행 | 데이터 전체 읽기 |
| 바뀌지 않는 이름 | 규칙이 지켜지면 일어나지 않음 | 규칙이 지켜지면 일어나지 않음 | 이름이 달라져 다시 실행 | 버전마다 저장 공간 |

마지막 행은 실험하지 않았고 정의에서 따라 나오는 결과다. 스냅샷과 객체 버전 ID는 저장소가 강제하지만 버전 디렉터리는 덮어쓰지 않기로 한 관례라서 지키지 않으면 깨진다.

데이터 버전이 캐시와 기록에 반영되려면 결국 버전이 이름에 들어가야 하고, 이름을 바꿀 수 없는 공유 경로라면 내용 다이제스트를 이름 대신 입력으로 넘기는 수밖에 없다. 그래서 KFP 파이프라인을 운영에 쓴다면 먼저 다이제스트 단계와 검증 단계의 캐시를 끄고, 제출 스크립트가 `enable_caching`을 일괄로 넘기지 않게 해야 한다.

네 편의 사례를 실패를 언제 드러내는가와 실패가 났을 때 플랫폼이 어디까지 흡수하는가의 두 질문으로 다시 묶은 내용은 [9.1.3편]({% post_url 2026-11-12-MLOps-ML-Platform-Engineering-09-01-03-Troubleshooting-Retrospective %})에서 다룬다.

<br>

# 참고 링크

- [8.1.1편: 컴포넌트 이미지와 의존성 사례]({% post_url 2026-11-12-MLOps-ML-Platform-Engineering-08-01-01-Image-Dependency-Cases %})
- [8.1.2편: 분산 학습의 epoch별 검증 장애 사례]({% post_url 2026-11-12-MLOps-ML-Platform-Engineering-08-01-02-Distributed-Validation-Cases %})
- [9.1.2편: 학습 데이터 참조와 산출물 저장의 장애 사례]({% post_url 2026-11-12-MLOps-ML-Platform-Engineering-09-01-02-Data-Artifact-Cases %})
- [실험 코드와 결과](https://github.com/sirzzang/sirzzang.github.io/tree/master/assets/data/mlpe-ch09-data-reference)
- [Kubeflow Pipelines: 캐시 키 구성(2.17.3)](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/cacheutils/cache.go#L173-L229)
- [Kubeflow Pipelines: PVC 이름과 캐시 조회 범위(2.17.3)](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/driver/cache.go#L80-L130)
- [Kubeflow Pipelines: importer 재사용(2.17.3)](https://github.com/kubeflow/pipelines/blob/2.17.3/backend/src/v2/component/importer_launcher.go#L168-L184)
- [Kubeflow Pipelines: 사용자 지정 캐시 키(2.18.0)](https://github.com/kubeflow/pipelines/blob/2.18.0/backend/src/v2/driver/cache.go#L84-L96)
- [MLflow: Dataset tracking](https://mlflow.org/docs/latest/ml/dataset/)
- [MLflow: MetaDataset 소스(3.18.0)](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/data/meta_dataset.py)
- [MLflow: digest 계산 소스(3.18.0)](https://github.com/mlflow/mlflow/blob/v3.18.0/mlflow/data/digest_utils.py)
- [NVIDIA GTC 2019: Inside NVIDIA's AI Infrastructure for Self-driving Cars](https://developer.download.nvidia.com/video/gputechconf/gtc/2019/presentation/s9649-inside-nvidia-ai-infrastructure-for-self-driving-cars.pdf)
- [Aurora's Data Engine: How We Accelerate Machine Learning Model Workflows](https://mlops.community/auroras-data-engine-how-we-accelerate-machine-learning-model-workflows/)

<br>
