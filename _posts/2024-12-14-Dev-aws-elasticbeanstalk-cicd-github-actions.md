---
title:  "[AWS] Github Actions를 이용해 Elastic Beanstalk에 배포하기"
excerpt: Github Actions에서 Elastic Beanstalk에 배포하는 Workflow를 만들어 보자
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - AWS
  - Elastic Beanstalk
  - EC2
  - Github Actions
---

<br>

사이드 프로젝트에서 개발한 서버를 배포할 때, 배포를 위한 파이프라인을 구성할 수 있다면 배포가 더 쉬워질 것이라는 생각이 들었다. 이것 저것 찾아 보다, 서버 소스 코드를 관리하는 Github에서 제공하는 Workflow 툴인 Github Actions를 이용해 보기로 했다. 어떻게 적용하면 되는지 그 과정을 간단히 정리하고자 한다.

- [Github Actions](https://docs.github.com/en/actions)

<br>

# 배경

![aws-backend-structure]({{site.url}}/assets/images/aws-backend-structure.png){: .align-center}

현재 AWS에 EC2와 Load Balancer를 이용한 dev 환경, prod 환경을 구성했는데, 일일이 세팅해주지 않고, Elastic Beanstalk을 사용했다. 각각의 환경에 앱을 배포할 때는 Elastic Beanstalk CLI인 Elastic Beanstalk CLI를 이용하는데, 브랜치 전략은 논외로 하고, dev 환경에서는 dev 브랜치의 소스 코드를, prod 환경에서는 prod 브랜치의 소스 코드를 배포한다. 

- [AWS Elastic Beanstalk](https://aws.amazon.com/elasticbeanstalk/?gclid=CjwKCAiA9vS6BhA9EiwAJpnXw6pyJtPI1IYrXZDRR-bvyVSkxW2GSGoxoJhRMsSKY_mdWkzO8Em44BoCF_oQAvD_BwE&trk=3d211853-d899-491e-bd5a-fb5f17de6f0f&sc_channel=ps&ef_id=CjwKCAiA9vS6BhA9EiwAJpnXw6pyJtPI1IYrXZDRR-bvyVSkxW2GSGoxoJhRMsSKY_mdWkzO8Em44BoCF_oQAvD_BwE:G:s&s_kwcid=AL!4422!3!651510175878!e!!g!!elasticbeanstalk!19835789747!147297563979)
- [Elastic Beanstalk CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3.html)

<br>

Elastic Beanstalk 환경은 Docker 환경으로, Dockerfile을 이용해 이미지를 직접 빌드하는 방식으로 서버 앱을 구동한다.

- [Elastic Beanstalk Docker 환경](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/create_deploy_docker.container.console.html)
- [Dockerfile을 이용해 Elastic Beanstalk에서 이미지 관리하기](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/single-container-docker-configuration.html#single-container-docker-configuration.dockerfile)
  - Dockerfile은 프로젝트 최상단 루트에 있어야 함

<br>

Elastic Beanstalk CLI를 이용해 앱을 배포하면, 아래와 같이 소스 코드를 압축해 배포를 위한 `zip` 파일로 만들어 S3에 업로드한 뒤, 해당 배포 파일을 이용해 구동하는 것을 확인할 수 있다.

- `zip` 파일은 단순히 소스 코드를 압축해 놓은 것
- 해당 배포 파일 내에 Dockerfile이 최상단에 위치해 있고, Elastic Beanstalk은 해당 파일을 이용해 이미지를 빌드하고 컨테이너를 실행함

```bash
$ eb deploy <environment_name> --timeout 30
Creating application version archive "app-d66a-241214_213636476071".
Uploading <environment_name>/app-d66a-241214_213636476071.zip to S3. This may take a while.
Upload Complete.
2024-12-14 12:36:38    INFO    Environment update is starting.      
2024-12-14 12:36:42    INFO    Deploying new version to instance(s).
2024-12-14 12:37:17    INFO    Instance deployment completed successfully.
2024-12-14 12:37:20    INFO    New application version was deployed to running EC2 instances.
2024-12-14 12:37:20    INFO    Environment update completed successfully.
                                                                      
```



<br>

# Github Actions

Github Repository에서 개발 워크플로우를 자동화할 수 있도록 Github에서 제공하는 툴이다. Repository에서 빌드, 테스트, 배포 등과 같은 개발 워크플로우를 구성하고, 이를 실행하기 위한 환경을 제공한다.

<br>

## 주요 개념



![github-workflow-concept]({{site.url}}/assets/images/github-workflow-concept.png){: .align-center}

<center><sup>이미지 출처: https://docs.github.com/en/actions/about-github-actions/understanding-github-actions#the-components-of-github-actions</sup></center>

위의 그림에서와 같이 repository에서 event가 발생할 경우, 1개 이상의 step으로 정의된 job으로 이루어진 workflow가 실행된다. 물론, 이벤트 없이 특정 스케쥴이 되었을 때 실행하는 것이나, 수동으로 실행하는 것도 가능하다.

- Event: Repository에 발생하는 이벤트로, 정의할 수 있는 이벤트는 [공식 문서의 이벤트 목록](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows)을 통해 확인할 수 있음
  - PR 생성
  - Commit 푸시
  - Issue 생성
- Workflow: 1개 이상의 순차 혹은 병렬적으로 실행되는 Job
  - Job 간의 dependency를 정의할 수 있음
  - repository 소스 코드의 `.github/workflows` 디렉토리 안에 YAML 파일로 정의됨
  - 한 repository 안에 여러 개의 Workflow가 정의될 수 있음
  - 특정 Workflow에서 다른 Workflow를 참조하거나 재사용할 수 있음
- Job: 1개 이상의 Step으로 구성된 Workflow 구성 단위
  - 하나의 Job은 하나의 동일한 Runner에서 실행되는 workflow step 모음
- Runner: Workflow를 실행하는 서버로, 하나의 Runner는 한 번에 하나의 Job이 실행됨
  * Github에서 제공하는 host
    * Ubuntu Linux
    * Microsoft Windows
    * macOS
    * 그 외 [large runners](https://docs.github.com/en/actions/using-github-hosted-runners/using-larger-runners)
  * [self hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners) 사용 가능: 다른 운영 체제나, 특정 하드웨어 설정이 필요한 경우
- Step: Job에서 실행되는 각각의 태스크로, 미리 정의한 스크립트 혹은 Github Platform에 정의되어 있는 custom application을 이용할 수 있음
  - [Github Marketplace](https://github.com/marketplace)에서 미리 정의된 custom application을 찾을 수 있음

<br>

# 적용



<br>

## AWS IAM 사용자 생성



<br>

## Github Action 설정



<br>



## Workflow 작성



<br>

# 확인



