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

현재 AWS에 EC2와 Load Balancer를 이용한 dev 환경, prod 환경을 구성했는데, 환경 세팅 및 관리를 위해 Elastic Beanstalk을 사용했다. 각각의 환경에 앱을 배포할 때는 Elastic Beanstalk CLI인 Elastic Beanstalk CLI를 이용하는데, 브랜치 전략은 논외로 하고, dev 환경에서는 dev 브랜치의 소스 코드를, prod 환경에서는 prod 브랜치의 소스 코드를 배포한다. 

- [AWS Elastic Beanstalk](https://aws.amazon.com/elasticbeanstalk/?gclid=CjwKCAiA9vS6BhA9EiwAJpnXw6pyJtPI1IYrXZDRR-bvyVSkxW2GSGoxoJhRMsSKY_mdWkzO8Em44BoCF_oQAvD_BwE&trk=3d211853-d899-491e-bd5a-fb5f17de6f0f&sc_channel=ps&ef_id=CjwKCAiA9vS6BhA9EiwAJpnXw6pyJtPI1IYrXZDRR-bvyVSkxW2GSGoxoJhRMsSKY_mdWkzO8Em44BoCF_oQAvD_BwE:G:s&s_kwcid=AL!4422!3!651510175878!e!!g!!elasticbeanstalk!19835789747!147297563979)
- [Elastic Beanstalk CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3.html)

<br>

Elastic Beanstalk 환경은 Docker 환경으로, Dockerfile을 이용해 이미지를 직접 빌드하는 방식으로 서버 앱을 구동한다.

- [Elastic Beanstalk Docker 환경](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/create_deploy_docker.container.console.html)
- [Dockerfile을 이용해 Elastic Beanstalk의 이미지 관리하기](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/single-container-docker-configuration.html#single-container-docker-configuration.dockerfile)
  - Dockerfile은 프로젝트 최상단 루트에 있어야 함

<br>

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

Elastic Beanstalk CLI를 이용해 앱을 배포하면, 위와 같이 소스 코드를 압축해 배포를 위한 `zip` 파일로 만들어 S3에 업로드한 뒤, 해당 배포 파일을 이용해 구동한다.

- `zip` 파일은 단순히 소스 코드를 압축해 놓은 것
- 배포를 위한 해당 `zip` 파일 내에 Dockerfile이 최상단에 위치해 있고, Elastic Beanstalk은 해당 파일을 이용해 이미지를 빌드하고 컨테이너를 실행함





<br>

# Github Actions

Github Repository에서 개발 워크플로우를 자동화할 수 있도록 Github에서 제공하는 툴이다. Repository에서 빌드, 테스트, 배포 등과 같은 개발 워크플로우를 구성하고, 이를 실행하기 위한 환경을 제공한다.

<br>

## 주요 개념



![github-workflow-concept]({{site.url}}/assets/images/github-workflow-concept.png){: .align-center}

<center><sup>이미지 출처: https://docs.github.com/en/actions/about-github-actions/understanding-github-actions#the-components-of-github-actions</sup></center>

<br>

위의 그림에서와 같이 Repository에서 Event가 발생할 경우, 1개 이상의 Step으로 정의된 Job으로 이루어진 Workflow가 실행된다. 물론, Event 없이 특정 스케줄이 되었을 때 실행하는 것이나, 수동으로 실행하는 것도 가능하다.

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
  - 하나의 Job은 하나의 동일한 Runner에서 실행되는 Workflow Step 모음
- Runner: Workflow를 실행하는 서버로, 하나의 Runner는 한 번에 하나의 Job을 실행함
  * Github에서 제공하는 host
    * Ubuntu Linux
    * Microsoft Windows
    * macOS
    * 그 외 [large runners](https://docs.github.com/en/actions/using-github-hosted-runners/using-larger-runners)
  * [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners) 사용 가능: 다른 운영 체제나, 특정 하드웨어 설정이 필요한 경우
- Step: Job에서 실행되는 각각의 태스크로, 미리 정의한 스크립트 혹은 Github Platform에 정의되어 있는 action을 이용할 수 있음
  - action: [Github Marketplace](https://github.com/marketplace)에서 미리 정의된 custom application
  - 하나의 Job에 정의된 각각의 Step은 동일한 Runner에서 실행되기 때문에, Step 간 데이터 공유 가능

<br>

# 적용

Github Actions를 이용해 Elastic Beanstalk에 소스 코드를 배포하는 Workflow를 만들어 보려고 한다. dev 환경에 배포될 `dev` 브랜치에 Commit이 Push되었을 때, prod 환경에 배포될 `prod` 브랜치에는 Pull Request가 Merge되었을 때를 가정하여 Workflow를 만들어 보려고 한다. 아래에서는 dev 환경에 대한 Workflow를 기준으로 기록한다.

Workflow를 만들기 위해서는 크게 아래와 같은 단계를 거치면 된다.

- Elastic Beanstalk 접근을 위한 AWS IAM 사용자 생성
- Github Actions에 위에서 생성한 IAM 사용자 관련 시크릿 설정
- Workflow YAML 파일 작성

<br>

## AWS IAM 사용자 생성

Elastic Beanstalk에 배포하기 위해, Elastic Beanstalk 리소스 제어를 위한 IAM 사용자를 생성한다. 기존에 다른 IAM 사용자를 생성해 두었다면 이를 사용해도 되지만, 리소스 별 액세스 제어를 위한 IAM 사용자가 필요하다는 생각에 따로 사용자를 생성했다.

<br>

![github-actions-aws-iam-user-create]({{site.url}}/assets/images/github-actions-aws-iam-user-create.png){: .align-center}

위와 같이 IAM - Users - Create user를 통해 새로운 user를 생성한다. 

![github-actions-aws-iam-user-create-2]({{site.url}}/assets/images/github-actions-aws-iam-user-create-2.png){: align-center}

![github-actions-aws-iam-user-create-3]({{site.url}}/assets/images/github-actions-aws-iam-user-create-3.png){: align-center}

원하는 이름을 설정한 뒤, Elastic Beanstalk에 대한 권한 정책을 설정해 준다.

<br>

![github-actions-aws-iam-user-create-4]({{site.url}}/assets/images/github-actions-aws-iam-user-create-4.png){: .align-center}

이후, 위에서 생성한 사용자에 대해 Access Key를 생성한다.

![github-actions-aws-iam-user-create-5]({{site.url}}/assets/images/github-actions-aws-iam-user-create-5.png){: .align-center}

Github Actions로부터 Elastic Beanstalk에 접근하기 위한 목적이므로, AWS 외부 어플리케이션으로부터의 접근에 해당하는 유스 케이스를 설정해 준다.

생성된 Access Key와 Secret Access Key를 잘 보관해 둔다.

<br>

## Github Action 설정

Github Actions에서 위의 IAM 사용자 Access Key를 이용해 Elastic Beanstalk에 접근할 수 있도록, Github Repository에 관련 설정을 해 준다.

<br>

![github-actions-repository-setting]({{site.url}}/assets/images/github-actions-repository-setting.png){: .align-center}

Repository - Settings - Secrets and variables - Actions를 통해 설정하면 된다.

<br>

![github-actions-repository-setting-2]({{site.url}}/assets/images/github-actions-repository-setting-2.png){: .align-center}

![github-actions-repository-setting-3]({{site.url}}/assets/images/github-actions-repository-setting-3.png){: .align-center}

위와 같이 적당한 변수명으로 Access Key, Secret Access Key를 저장해 준다.

여기서 저장한 값은 Workflow 작성 단계에서 사용된다.

<br>



## Workflow 작성

Elastic Beanstalk 배포를 위해 Github Actions Marketplace에서 beanstalk deploy라는 action을 이용하면 된다.

- [beanstalk deploy](https://github.com/marketplace/actions/beanstalk-deploy): Elastic Beanstalk 환경에의 배포를 위한 custom application

<br>

해당 action은 배포될 버전의 `zip` 파일이 이미 생성되었음을 가정한다. 따라서, 배포를 위한 `zip` 파일을 생성한 후, beanstalk deploy를 이용해 배포하는 Workflow를 작성하면 된다. 가장 무난한 `ubuntu` 플랫폼을 이용하도록 했다.

```yaml
name: Deploy master
on:
  push:
    branches:
    - dev
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - name: Checkout source code
      uses: actions/checkout@v2

    - name: Generate deployment package
      run: zip -r deploy.zip . -i 'cmd/*' 'internal/*' Dockerfile go.*  
   
    - name: Get current time
	    uses: josStorer/get-current-time@v2
	    id: current-time
	    with:
	      format: YYYY-MM-DDTHH-mm-ss
	      utcOffset: "+09:00"

    - name: Deploy to EB
      uses: einaregilsson/beanstalk-deploy@v22
      with:
        aws_access_key: ${{ secrets.AWS_ACCESS_KEY }}
        aws_secret_key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        application_name: backend-v2
        environment_name: backend-v2-dev
        version_label: github-action-${{steps.current-time.outputs.formattedTime}}
        region: us-west-2
        deployment_package: deploy.zip
```

- `dev` 브랜치에 push되었을 때 작동함
- `jobs`에는 4개의 step 구성
  - 브랜치 체크아웃
  - 배포 패키지 `zip` 파일 생성
    - `deploy.zip` 이라는 이름으로 생성
  - 배포 패키지 버전 관리를 위한 현재 시각 값 생성
    - [get-current-time](https://github.com/marketplace/actions/get-current-time)이라는 action 이용
  - beanstalk deploy를 이용해 Elastic Beanstalk에 배포
    - 위에서 설정한 IAM 사용자 시크릿에 접근하기 위해 `${{ secrets.AWS_ACCESS_KEY}}`, `${{ secrets.AWS_SECRET_ACCESS_KEY}}` 변수를 사용
    - 배포할 앱 버전을 설정하기 위해, `Get current time` step에서 생성한 현재 시각 값 활용

> *참고*: 배포 패키지 파일
>
> 사실 Elastic Beanstalk 환경 자체가 Docker 환경이기 때문에, 위에서 살펴 봤던 것처럼 소스 코드 자체를 그냥 `zip` 파일로 만들어 버리면 되는 간단한 상황이었다. 배포 패키지를 생성하는 것이 더 복잡한 경우도 있는데, 아래와 같은 글을 참고해 봐도 좋을 듯하다.
>
> - [https://jojoldu.tistory.com/549](https://jojoldu.tistory.com/549)

<br>

작성한 Workflow를 `dev` 브랜치 소스 내 `.github/workflows` 내에 위치시키면 된다. 

<br>

# 결과



위와 같이 Workflow를 설정한 뒤, `dev` 브랜치에 PR을 생성한 후 머지해 보았다. `dev` 브랜치에 Commit이 Push되며 아래와 같이 workflow가 작동한다.

![github-actions-result]({{site.url}}/assets/images/github-actions-result.png){: .align-center}

<br>

Elastic Beanstalk에도 환경 업데이트가 진행되고 있음을 확인해 볼 수 있다.

![github-actions-result-2]({{site.url}}/assets/images/github-actions-result-2.png){: .align-center}

<br>

# 결론

eb cli를 이용해 일일이 수동으로 배포해 주어야 하는 불편함을 덜었음에 매우 만족한다. 다만, Github Actions의 가격 정책 상, private repository에는 사용 제한이 있기 때문에, 어떻게 과금을 최소화할 수 있을지 생각해 보아야 할 듯하다. 실행 시간은 쉽사리 넘기지 않을 수 있을 것 같은데, Storage 한도는 좀 빡빡할 수도 있을 것 같다.

- [Github Actions Billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)



