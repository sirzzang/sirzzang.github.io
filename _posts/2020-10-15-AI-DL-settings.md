---
title:  "[AI] DL GPU 개발환경 구축: Windows"
excerpt: "GPU를 사용하는 Tensorflow, PyTorch 개발환경을 구축해 보자."
toc: true
toc_sticky: true
categories:
  - AI
tags:
  - DL
  - Python
  - Tensorflow
  - PyTorch
  - GPU

last_modified_at: 2020-10-20
---

<br>

 Tensorflow, PyTorch 등 딥러닝 프레임워크를 GPU 환경에서 사용해 보자. *내 기준*  Tensorflow 환경 구축이 더 어려웠기 때문에, Tensorflow 환경을 구축한 후 PyTorch를 설치하는 방식을 택했다.

<br>



## 1. GPU 사양 확인



 먼저 설치된 GPU의 `compute capability`를 확인한다. 컴퓨터에 설치된 GPU는 **NVIDIA Geforce 2060 SUPER**이다. [여기](https://developer.nvidia.com/cuda-gpus#compute){: .btn .btn--primary .btn--small} 를 기준으로 확인한 GPU의 compute capability가 3.0 미만이면 딥러닝 프레임워크에 필요한 CUDA를 활용할 수 없다.

![gpu-capability]({{site.url}}/assets/images/compute-capability.png)

<br>

## 2. Tensorflow GPU 환경 구축

 Tensorflow에서 GPU 환경을 구축하는 방법은 기본적으로  [Tensorflow 공식 문서](https://www.tensorflow.org/install/gpu){: .btn .btn--primary .btn--small}를 따른다.

<br>

![tf-gpu]({{site.url}}/assets/images/tf-gpu-requirements.png)

 *GPU 지원*  부분의 문서를 보면, 크게 설치해야 할 것은 다음의 3가지이다.

* NVIDIA 드라이버
* CUDA Toolkit
  * 컴파일러 도구: Visual Studio
* cuDNN

<br>

 이 중 CUDA Toolkit을 사용하기 위해서는 컴파일러로 Visual Studio를 설치해야 한다. 해당 프로그램은 파이썬 환경에서 동작하지만 대부분의 코드가 C++인 Tensorflow를 사용하기 위해서도 설치해야 한다. 한편, CUPTI도 설치해야 하는데, 이는 위의 문서에서도 나와 있듯 CUDA Toolkit 설치 시 바로 설치된다.

<br>

### 2.1. NVIDIA 드라이버 설치

 [NVIDIA 드라이버 설치 페이지](https://www.nvidia.com/Download/index.aspx?lang=kr){: .btn .btn--primary .btn--small}에서 NVIDIA 드라이버를 다운로드한다. 

![gpu-driver]({{site.url}}/assets/images/nvidia-driver.png)

조건에 맞게 드라이버를 검색해 보면 `460.89-desktop-win10-64bit-international-dch-whql` 버전이 검색된다. 설치하면 된다.

> *참고* : 드라이버 버전
>
>  Tensorflow 공식문서에서 `418.` 이상의 버전이 필요하다고 했으므로, 혹시나 드라이버 버전이 맞지 않는 경우에 참고하자.



<br>

### 2.2. CUDA 설치



  [NVIDIA CUDA 설치 페이지](https://developer.nvidia.com/cuda-toolkit-archive){: .btn .btn--primary .btn--small}에서 NVIDIA 드라이버를 다운로드한다. Tensorflow 공식 문서에서 CUDA 10.1 버전을 지원한다고 했으므로, 해당 파일을 검색해서 다운로드하면 된다.



![cuda-version]({{site.url}}/assets/images/cuda-version.png)

<center><sup> update 2 버전으로 다운받기는 했는데, 아래랑 무슨 차이인지는 모르겠다.</sup></center>

<br>

#### Visual Studio 설치



 CUDA documentation을 읽어 보면, Window 환경에서 CUDA를 사용하기 위해 Visual Studio 16.x 버전 컴파일러가 필요하다는 것을 알 수 있다. 

![visual-studio]({{site.url}}/assets/images/visual-studio.png)

<br>

 Tensorflow 공식 문서에도 나와 있는 [Visual STudio 설치 링크](https://support.microsoft.com/ko-kr/help/2977003/the-latest-supported-visual-c-downloads){: .btn .btn--primary .btn--small}로 가서 **Visual Studio 2019 Community** 버전을 다운받는다. 중간에 설치 과정에서 `C++를 이용한 데스크탑 개발`에 체크해 준다. ~~*(사실 처음에 개발에 사용할 모든 기능 다 체크해야 하는 줄 알고, `Python`이랑 `Node.js`까지 다 설치해 버린 건 안 비밀)*~~

<br>

### 2.3. cuDNN 설치



 cuDNN을 설치하려면 ~~번거롭지만~~ 회원가입이 필요하다. 일련의 회원가입 과정을 완료한 뒤,   [NVIDIA cuDNN 설치 페이지](https://developer.nvidia.com/rdp/cudnn-archive){: .btn .btn--primary .btn--small}로 이동해서 CUDA 버전과 맞는 cuDNN 드라이버를 다운받는다. Tensorflow 공식 문서에서 7.6을 쓰라고 했으므로, 7.6.5 버전을 다운로드했다.

![cudnn-version]({{site.url}}/assets/images/cudnn-version.png)

<br>

 역시 CUDA를 설치할 때와 마찬가지로 [공식 문서](https://docs.nvidia.com/deeplearning/cudnn/archives/cudnn_765/cudnn-install/index.html#install-windows){: .btn .btn--primary .btn--small}를 열어 보자. 설치 방법이 나와 있다. 

![cudnn-installation]({{site.url}}/assets/images/cudnn-installation.png)

 읽어 보니, 압축을 풀면 생기는 `bin`, `lib`, `include` 아래의 파일들을 CUDA Toolkit이 설치된 폴더 `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v10.1`의 동일한 경로 아래에 복사하면 된다는 말이다. 

<br>

 아래와 같이 압축을 풀어 생기는 `cuda` 폴더 아래의 `bin`, `include`, `lib` 폴더를 CUDA Toolkit 폴더에 덮어 씌우면(복사하면) 된다.

![cudnn-installation-2]({{site.url}}/assets/images/cudnn-installation-2.png)

<br> 그리고 공식 문서 상의 다음 단계에 따라 시스템 환경변수에 `CUDA_PATH`가 지정되어 있는지 확인하고, 없으면 추가해 주자.

![cudnn-installation-3]({{site.url}}/assets/images/cudnn-installation-3.png)

 <br>

> *참고* : 마지막 단계
>
>  cuDNN 설치 공식 문서 마지막 단계에서 Visual Studio에 `cudnn.lib`를 추가해 주라는? 말이 있었는데 무슨 말인지 모르겠다. 결과적으로는 이 단계를 몰라서 건너 뛰었는데, 나중에 프레임워크 동작에는 전혀 문제가 없었다. ~~뭐지~~

<br>

### 2.4. Tensorflow 설치 및 확인



 GPU를 사용해 Tensorflow를 구동할 가상환경을 설치하고, Jupyter Notebook 커널을 생성했다. 그리고 Jupyter Notebook 커널을 열어 다음을 입력한다.

```python
from tensorflow.python.client import device_lib
device_lib.list_local_devices()
```

<br>

GPU가 뜨는지 확인한다. 아래와 같이 화면이 나오면 성공!

![tensorflow-gpu-check]({{site.url}}/assets/images/tensorflow-gpu-check.png)

<br>

## 3. PyTorch 설치



 CUDA, cuDNN 등이 설치되어 있으면, PyTorch를 설치하는 것은 쉽다. [공식 문서 install guide](https://pytorch.org/get-started/locally/){: .btn .btn--primary .btn--small}를 보고, 자신의 상황에 맞게 선택하여 command를 복사하고, PyTorch를 설치해 주면 된다.



![pytorch-gpu]({{site.url}}/assets/images/pytorch-installation.png)

<br>

 마찬가지로 아래와 같이 입력해 보자. GPU가 인식되면 성공!

```python
import torch
torch.cuda.get_device_name()
```

<br>

![pytorch-gpu-check]({{site.url}}/assets/images/pytorch-gpu-check.png)