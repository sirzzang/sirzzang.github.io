---
title:  "[AI] DL GPU 개발환경 구축: WSL"
excerpt: "WSL에서 GPU 개발 환경을 구축해 보자."
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
  - Linux
---

<br>

DL GPU 개발환경 구축(참고: [윈도우 버전](https://sirzzang.github.io/ai/AI-DL-settings/))을 WSL에서 진행해 보자.

- GPU: NVIDIA Geforce RTX 3060
  - compute possibility: 8.6
- CUDA: 11.7
  - WSL 환경 지원
- cuDNN: 8.5.0
  - Linux 환경 기준으로 진행하면 됨



<br>

# NVIDIA GPU 드라이버 설치

- NVIDIA 그래픽 드라이버 설치
  - 설치 링크: [NVIDIA drivers](https://www.nvidia.com/en-us/drivers/)
- `nvidia-utils` 패키지 설치
  ```bash
  sudo apt install nvidia-utils-510
  ```




<br>

# CUDA 설치

GPU의 [compute possibility](https://developer.nvidia.com/cuda-gpus)에 맞는 CUDA를 설치한다.

- compute possibility: 8.6
- CUDA: 11.7
  - [CUDA 별로 지원되는 GPU 사양](https://en.wikipedia.org/wiki/CUDA#GPUs_supported)에 맞는 CUDA 버전을 선택하면 됨
  - PyTorch 2.0 이상에서 CUDA 11.7을 필요로 하기 때문에 해당 버전 선택

NVIDIA에서 CUDA 설치 시 WSL 환경을 지원하고 있다.

- 설치 링크: [cuda 11.7 download archive](https://developer.nvidia.com/cuda-11-7-0-download-archive)
- 아래와 같이 target platform 선택
  ![wsl-cuda-target-platform]({{site.url}}/assets/images/cuda-wsl.png){: .align-center}
- 선택 후 가이드에 따라 아래 명령어 진행
  ```bash
  wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
  sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
  wget https://developer.download.nvidia.com/compute/cuda/11.7.0/local_installers/cuda-repo-wsl-ubuntu-11-7-local_11.7.0-1_amd64.deb
  sudo dpkg -i cuda-repo-wsl-ubuntu-11-7-local_11.7.0-1_amd64.deb
  sudo cp /var/cuda-repo-wsl-ubuntu-11-7-local/cuda-*-keyring.gpg /usr/share/keyrings/
  sudo apt-get update
  sudo apt-get -y install cuda
  ```

- cuda 11.7 설치되어 있는지 확인
  ![cuda-check]({{site.url}}/assets/images/cuda-check.png){: .align-center}
- 환경 변수 설정
  ```bash
  export PATH=/usr/local/cuda-11.7/bin:$PATH
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/cuda-11.7/lib64:$LD_LIBRARY_PATH
  ```
- cuda 버전 확인
  ```bash
  nvcc --version
  ```
  ![nvcc-check]({{site.url}}/assets/images/nvcc-check.png){: .align-center}



<br>

# cuDNN 설치

- cuDNN: 8.5.0
  - 설치 링크: [cuDNN archive](https://developer.nvidia.com/rdp/cudnn-archive)
  - 위 링크에서 CUDA 버전에 맞는 것을 찾으면 됨
- cuDNN 설치 가이드에 따라 아래 명령어 진행
  - 설치 가이드: [cudnn-895 install guide](https://docs.nvidia.com/deeplearning/cudnn/archives/cudnn-895/install-guide/index.html)
  ```bash
  $ sudo dpkg -i cudnn-local-repo-ubuntu2204-8.5.0.96_1.0-1_amd64.deb
  $ sudo cp sudo cp /var/cudnn-local-repo-ubuntu2204-8.5.0.96/cudnn-local-7ED72349-keyring.gpg /usr/share/keyrings/
  $ sudo apt-get update
  $ sudo apt-get install libcudnn8=8.5.0.96-1+cuda11.7
  $ sudo apt-get install libcudnn8-dev=8.5.0.96-1+cuda11.7
  $ sudo apt-get install libcudnn8-samples=8.5.0.96-1+cuda11.7
  ```

- 설치된 cuDNN 버전 확인
  - `/usr/include/x86_64-linux-gnu/cudnn_version_v8.h`
  ```bash
  eraser@DESKTOP-FAIGO7U:~$ cat /usr/include/x86_64-linux-gnu/cudnn_version_v8.h | grep CUDNN
  #ifndef CUDNN_VERSION_H_
  #define CUDNN_VERSION_H_
  #define CUDNN_MAJOR 8
  #define CUDNN_MINOR 5
  #define CUDNN_PATCHLEVEL 0
  #define CUDNN_VERSION (CUDNN_MAJOR * 1000 + CUDNN_MINOR * 100 + CUDNN_PATCHLEVEL)
  #endif /* CUDNN_VERSION_H *
  ```

> *참고*: cuDNN 8.5.0 설치의 이유
>
> cuDNN archive 링크에서 찾으면, CUDA 11.x 버전에 맞는 cuDNN 버전은 꽤 많은 것으로 나온다. 다만, 해당 버전들 중, `libcudnn` 설치 시 CUDA 11.7 버전에 맞는 것이 없다고 확인된 버전들이 있어서, `libcudnn` deb 파일 리스트를 보고, CUDA 11.7 버전에 호환되는 `libcudnn` 파일이 있는 것을 확인해 설치했다.
>
> ![libcudnn8-not-found]({{site.url}}/assets/images/libcudnn8-not-found.png){: .align-center}
>
> <center><sup>CUDA 11.x 버전을 위한 cuDNN 버전이지만, libcudnn을 찾을 수 없음</sup></center>
>
> ![libcudnn8-debfiles]({{site.url}}/assets/images/libcudnn8-debfiles.png)
>
> <center><sup>CUDA 11.7에 맞는 libcudnn이 있는 버전을 찾음</sup></center>







<br>

# 설치 확인

pytorch가 설치된 상태에서 아래 테스트 코드 실행

```python
import torch

print(torch.cuda.is_available())
print(torch.__version__)
```
```bash
(gaze-env) eraser@DESKTOP-FAIGO7U:~/projects$ python3 test.py
True
2.5.0+cu124
```



