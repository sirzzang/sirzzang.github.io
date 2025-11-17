---
title:  "[AI] SlowFast Demo 실행"
excerpt: "<<Video Understanding>> 사전 훈련된 SlowFast 모델을 돌려 보자."
toc: true
toc_sticky: true
categories:
  - AI
tags:
  - Video Understanding
  - SlowFast
---



<br>

영상 인식 분야에서 사용되는 [SlowFast](https://github.com/facebookresearch/SlowFast) 모델을 일단 그냥 돌려만 보자. 사전 학습된 모델 가중치 파일을 이용해 돌려만 보는 건 Demo로 가능하다.

- 하드웨어 사양
  - Windows 11
  - RTX 3060
- 개발 환경
  - WSL
  - Conda environment
  - Prerequisites
    - [GPU 환경 설정](https://sirzzang.github.io/ai/AI-DL-settings-wsl/)
      - CUDA 11.7
      - cuDNN 8.5.0
- 사용할 모델 및 데이터셋
  - 모델: [SLOWFAST_32x2_R101_50_50_v2.1.pkl](https://dl.fbaipublicfiles.com/pyslowfast/model_zoo/ava/SLOWFAST_32x2_R101_50_50_v2.1.pkl)
    - [Model Zoo](https://github.com/facebookresearch/SlowFast/blob/main/MODEL_ZOO.md)에서 필요한 모델 다운로드

  - 데이터셋: AVA



<br>

# 개발 환경 구성

> *참고*: Python 패키지 외의 프로그램
> gcc, ffmpeg도 필요하나, Python 패키지가 아니므로 아래 내용에서 제외한다.
> - gcc >= 4.9
>   ```bash
>   $ gcc --version
>   gcc (Ubuntu 11.3.0-1ubuntu1~22.04) 11.3.0
>   Copyright (C) 2021 Free Software Foundation, Inc.
>   This is free software; see the source for copying conditions.  There is NO
>   warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
>   ```
> - ffmpeg: 4.0이 선호되나, 돌려 본 결과 다른 버전이어도 크게 상관은 없어 보임
>   - 만약 설치되지 않았다고 한다면, PyAV 설치 시 같이 설치됨
>   ```bash
>   $ ffmpeg -version
>   ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright (c) 2000-2021 the FFmpeg developers
>   built with gcc 11 (Ubuntu 11.2.0-19ubuntu1)
>   configuration: --prefix=/usr --extra-version=0ubuntu0.22.04.1 --toolchain=hardened --libdir=/usr/lib/x86_64-linux-gnu --incdir=/usr/include/x86_64-linux-gnu --arch=amd64 --enable-gpl --disable-stripping --enable-gnutls --enable-ladspa --enable-libaom --enable-libass --enable-libbluray --enable-libbs2b --enable-libcaca --enable-libcdio --enable-libcodec2 --enable-libdav1d --enable-libflite --enable-libfontconfig --enable-libfreetype --enable-libfribidi --enable-libgme --enable-libgsm --enable-libjack --enable-libmp3lame --enable-libmysofa --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-libpulse --enable-librabbitmq --enable-librubberband --enable-libshine --enable-libsnappy --enable-libsoxr --enable-libspeex --enable-libsrt --enable-libssh --enable-libtheora --enable-libtwolame --enable-libvidstab --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libx265 --enable-libxml2 --enable-libxvid --enable-libzimg --enable-libzmq --enable-libzvbi --enable-lv2 --enable-omx --enable-openal --enable-opencl --enable-opengl --enable-sdl2 --enable-pocketsphinx --enable-librsvg --enable-libmfx --enable-libdc1394 --enable-libdrm --enable-libiec61883 --enable-chromaprint --enable-frei0r --enable-libx264 --enable-shared
>   libavutil      56. 70.100 / 56. 70.100
>   libavcodec     58.134.100 / 58.134.100
>   libavformat    58. 76.100 / 58. 76.100
>   libavdevice    58. 13.100 / 58. 13.100
>   libavfilter     7.110.100 /  7.110.100
>   libswscale      5.  9.100 /  5.  9.100
>   libswresample   3.  9.100 /  3.  9.100
>   libpostproc    55.  9.100 / 55.  9.100
>   ```


Anaconda 환경 및 해당 환경에 설치한 `pip`를 이용해 필요한 Python 패키지를 설치한다. 필요한 패키지는 [Requirements](https://github.com/facebookresearch/SlowFast/blob/main/INSTALL.md#requirements)에서 확인할 수 있다.
```bash
$ conda create -n slowfast-env python=3.10
$ conda activate slowfast-env
(slowfast-env) $ conda install pip 
```

- PyTorch >= 1.3, torchvision
  - CUDA, cuDNN 버전에 맞는 PyTorch 버전 설치
  - 해당 PyTorch 버전에 맞는 torchvision 설치
    - 참고: [torchvision installation](https://pypi.org/project/torchvision/)
  ```bash
  (slowfast-env) $ conda install pytorch==2.0.1 torchvision==0.15.2 pytorch-cuda=11.7 -c pytorch -c nvidia
  ```

- fvcore
  - SlowFast 공식 문서에서는 `pip install 'git+https://github.com/facebookresearch/fvcore'`로 설치하라고 안내되어 있음
  - [fvcore Github](https://github.com/facebookresearch/fvcore/) 참고하여 아래 명령어로 설치
  ```bash
  (slowfast-env) $ conda install -c fvcore -c iopath -c conda-forge fvcore
  ```

- PyYaml, tqdm
  - fvcore가 설치되면 정상적으로 같이 설치됨

- PyAV
  ```bash
  (slowfast-env) $ conda install av -c conda-forge
  ```

- iopath
  ```bash
  (slowfast-env) $ conda install -c iopath iopath
  ```

- tensorboard
  - 공식 문서에는 `pip install tensorboard`로 안내되어 있음
  ```bash
  (slowfast-env) $ conda install tensorboardx
  (slowfast-env) $ conda install tensorboard
  ```

- PyTorchVideo
  - 공식 문서에는 `pip install pytorchvideo`로 안내되어 있으나, 해당 방식으로 설치하면 `ImportError: cannot import name 'cat_all_gather' from 'pytorchvideo.layers.distributed'` 발생
  - [관련 이슈](https://github.com/facebookresearch/SlowFast/issues/663) 참고하여 [pytorchvideo](https://github.com/facebookresearch/pytorchvideo) repository clone 후 설치 진행
    ```bash
    (slowfast-env) $ git clone https://github.com/facebookresearch/pytorchvideo.git
    (slowfast-env) $ cd pytorchvideo
    (slowfast-env) $ pip install -e .
    ```

- simplejson
  ```bash
  (slowfast-env) $ pip install simplejson
  ```

- psutil
  ```bash
  (slowfast-env) $ pip install psutil
  ```

- opencv
  ```bash
  (slowfast-env) $ pip install opencv-python
  ```

- detectron
  - [Detectron 2](https://github.com/facebookresearch/detectron2) repository clone 후 설치 진행
  ```bash
  (slowfast-env) $ git clone https://github.com/facebookresearch/detectron2.git
  (slowfast-env) $ cd detectron2
  (slowfast-env) $ pip install -e .
  ```

- moviepy: optional이나, 설치 진행
  ```bash
  (slowfast-env) $ conda install -c conda-forge moviepy
  ```
  
- Fairscale
  ```bash
  (slowfast-env) $ pip install 'git+https://github.com/facebookresearch/fairscale'
  ```

<br>


## 추가 패키지 설치

위에서 공식 안내된 패키지를 다 설치했더라도, 실제 실행하면 설치되어 있지 않다고 나오는 패키지들이 있다. 아래 패키지들을 추가로 설치해 준다.

- scipy
- pandas
- sklearn

<br>

# Dataset

SlowFast Dataset Preparation(참고: [DATASET.md](https://github.com/facebookresearch/SlowFast/blob/main/slowfast/datasets/DATASET.md))에 안내된 대로 데이터셋을 준비한다. Action Recognition을 위해 사용할 수 있는 공개 데이터셋 여러 가지가 있는데, 그 중에서도 AVA 데이터셋(참고: [AVA Dataset](https://research.google.com/ava/))을 이용한다. 해당 데이터셋이 아니더라도, 다른 데이터셋을 사용하더라도 위의 문서에 안내된 대로 따르면 된다.



<br>


# Config

사용할 사전학습 모델을 돌리기 위해 필요한 config 파일을 수정한다.

- 사용할 모델: 
- config 위치: `demo/AVA/SLOWFAST_32x2_R101_50_50.yaml`

```yaml
TRAIN:
  ENABLE: False
  DATASET: ava
  BATCH_SIZE: 16
  EVAL_PERIOD: 1
  CHECKPOINT_PERIOD: 1
  AUTO_RESUME: True
  CHECKPOINT_FILE_PATH: /mnt/d/projects/model_zoo/SLOWFAST_32x2_R101_50_50_v2.1.pkl  #path to pretrain model
  CHECKPOINT_TYPE: caffe2 # https://github.com/facebookresearch/SlowFast/issues/653#issuecomment-1568273996
DATA:
  PATH_TO_DATA_DIR: /mnt/d/projects/ava
  NUM_FRAMES: 32
  SAMPLING_RATE: 2
  TRAIN_JITTER_SCALES: [256, 320]
  TRAIN_CROP_SIZE: 224
  TEST_CROP_SIZE: 256
  INPUT_CHANNEL_NUM: [3, 3]
DETECTION:
  ENABLE: True
  ALIGNED: False
AVA:
  ANNOTATION_DIR: /mnt/d/projects/ava
  FRAME_DIR: /mnt/d/projects/ava/frames
  FRAME_LIST_DIR: /mnt/d/projects/ava/frame_lists
  LABEL_MAP_FILE: /mnt/d/projects/ava/annotations/ava_action_list_v2.1_for_activitynet_2018.pbtxt
  GROUNDTRUTH_FILE: /mnt/d/projects/ava/annotations/ava_val_v2.1.csv
  BGR: False
  DETECTION_SCORE_THRESH: 0.8
  TEST_PREDICT_BOX_LISTS: ["/mnt/d/projects/ava/annotations/ava_val_predicted_boxes.csv"]
  EXCLUSION_FILE: /mnt/d/projects/ava/annotations/ava_val_excluded_timestamps_v2.1.csv
  TRAIN_GT_BOX_LISTS: ["/mnt/d/projects/ava/annotations/ava_train_v2.1.csv"]
SLOWFAST:
  ALPHA: 4
  BETA_INV: 8
  FUSION_CONV_CHANNEL_RATIO: 2
  FUSION_KERNEL_SZ: 5
RESNET:
  ZERO_INIT_FINAL_BN: True
  WIDTH_PER_GROUP: 64
  NUM_GROUPS: 1
  DEPTH: 101
  TRANS_FUNC: bottleneck_transform
  STRIDE_1X1: False
  NUM_BLOCK_TEMP_KERNEL: [[3, 3], [4, 4], [6, 6], [3, 3]]
  SPATIAL_DILATIONS: [[1, 1], [1, 1], [1, 1], [2, 2]]
  SPATIAL_STRIDES: [[1, 1], [2, 2], [2, 2], [1, 1]]
NONLOCAL:
  LOCATION: [[[], []], [[], []], [[6, 13, 20], []], [[], []]]
  GROUP: [[1, 1], [1, 1], [1, 1], [1, 1]]
  INSTANTIATION: dot_product
  POOL: [[[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]]]
BN:
  USE_PRECISE_STATS: False
  NUM_BATCHES_PRECISE: 200
SOLVER:
  MOMENTUM: 0.9
  WEIGHT_DECAY: 1e-7
  OPTIMIZING_METHOD: sgd
MODEL:
  NUM_CLASSES: 80
  ARCH: slowfast
  MODEL_NAME: SlowFast
  LOSS_FUNC: bce
  DROPOUT_RATE: 0.5
  HEAD_ACT: sigmoid
TEST:
  ENABLE: False
  DATASET: ava
  BATCH_SIZE: 8
DATA_LOADER:
  NUM_WORKERS: 2
  PIN_MEMORY: True
NUM_GPUS: 1
NUM_SHARDS: 1
RNG_SEED: 0
OUTPUT_DIR: .
# TENSORBOARD:
#   MODEL_VIS:
#     TOPK: 2
DEMO:
  ENABLE: True
  LABEL_FILE_PATH: /mnt/d/projects/ava/ava_classnames.json
  INPUT_VIDEO: /mnt/d/projects/ava/videos_15min/4k-rTF3oZKw.mp4
  OUTPUT_FILE: /mnt/d/projects/4k-rTF3oZKw_output.mp4
  # WEBCAM: 0
  DETECTRON2_CFG: "COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"
  DETECTRON2_WEIGHTS: detectron2://COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl

```
기존에 제공되는 config 파일에서 변경한 부분은 다음과 같다.
- `NUM_GPUS`: GPU 개수에 맞게 변경
- `TRAIN`
  - `CHECKPOINT_FILE_PATH`
  - `CHECKPOINT_TYPE`: pytorch로 두고 돌렸더니 육안으로 확인하기에도 성능이 너무 낮아, [이 이슈의 댓글](https://github.com/facebookresearch/SlowFast/issues/653#issuecomment-1568273996)을 참고해 `caffe2`로 변경했다.
- `DATA`
  - `PATH_TO_DATA_DIR`
- `AVA`
  - `ANNOTATION_DIR`
  - `FRAME_DIR`
  - `FRAME_LIST_DIR`
  - `LABEL_MAP_FILE`
  - `GROUND_TRUTH_FILE`
  - `TEST_PREDICT_VOX_LISTS`
  - `EXCLUSION_FILE`
  - `TRAIN_GT_BOX_LISTS`
- `TENSORBOARD`: 관련 config key가 없다는 에러가 발생해 해당 항목 모두 주석 처리
  > *참고*: 관련 에러
  > ```bash
  > (slowfast-env) eraser@DESKTOP-FAIGO7U:~/projects/SlowFast$ python tools/run_net.py      --cfg ./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml
  > config files: ['./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml']
  > Traceback (most recent call last):
  > File "/home/eraser/projects/SlowFast/tools/run_net.py", line 50, in <module>
  > main()
  > File "/home/eraser/projects/SlowFast/tools/run_net.py", line 21, in main
  > cfg = load_config(args, path_to_config)
  > File "/home/eraser/projects/SlowFast/slowfast/utils/parser.py", line 78, in load_config
  > cfg.merge_from_file(path_to_config)
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/fvcore/common/config.py", line 121, in merge_from_file
  > self.merge_from_other_cfg(loaded_cfg)
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/fvcore/common/config.py", line 132, in merge_from_other_cfg
  > return super().merge_from_other_cfg(cfg_other)
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/yacs/config.py", line 217, in merge_from_other_cfg
  > _merge_a_into_b(cfg_other, self, self, [])
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/yacs/config.py", line 478, in _merge_a_into_b
  > _merge_a_into_b(v, b[k], root, key_list + [k])
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/yacs/config.py", line 478, in _merge_a_into_b
  > _merge_a_into_b(v, b[k], root, key_list + [k])
  > File "/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/yacs/config.py", line 491, in _merge_a_into_b
  > raise KeyError("Non-existent config key: {}".format(full_key))
  > KeyError: 'Non-existent config key: TENSORBOARD.MODEL_VIS.TOPK'
  > ```

- `DEMO`
  - `LABEL_FILE_PATH`
  - `INPUT_VIDEO`
  - `OUTPUT_FILE`
  - `WEBCAM`: 카메라 영상을 이용하는 게 아니므로 관련 항목 주석 처리
    > *참고*: 관련 에러
    >
    > ```bash
    > (slowfast-env) eraser@DESKTOP-FAIGO7U:~/projects/SlowFast$ python tools/run_net.py      --cfg ./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml
    > config files: ['./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml']
    > [ WARN:0@0.498] global cap_v4l.cpp:999 open VIDEOIO(V4L2:/dev/video0): can't open camera by index
    > [ERROR:0@0.498] global obsensor_uvc_stream_channel.cpp:158 getStreamChannelGroup Camera index out of range
    > Traceback (most recent call last):
    >   File "/home/eraser/projects/SlowFast/tools/run_net.py", line 50, in <module>
    >     main()
    >   File "/home/eraser/projects/SlowFast/tools/run_net.py", line 46, in main
    >     demo(cfg)
    >   File "/home/eraser/projects/SlowFast/tools/demo_net.py", line 111, in demo
    >     frame_provider = VideoManager(cfg)
    >   File "/home/eraser/projects/SlowFast/slowfast/visualization/demo_loader.py", line 48, in __init__
    >     raise IOError("Video {} cannot be opened".format(self.source))
    > OSError: Video 0 cannot be opened\
    > ```

 



<br>

# Demo 실행

```bash
$ python tools/run_net.py \
	--cfg ./configs/AVA/c2/SLOWFAST_64x2_R101_50_50.yaml
```



## Troubleshooting

실제로 돌리려고 할 때, 코드 단을 수정해서 해결해 주어야 하는 에러들이 있었다. 
> *참고*: 코드 수정 외의 방식으로 해결해야 했던 에러들
> - `Could not load library libcudnn_cnn_infer.so.8. Error: [libcuda.so](http://libcuda.so/): cannot open shared object file: No such file or directory`
>   - `LD_LIBRARY_PATH` 환경 변수에 `libcuda.so` 파일 경로 추가
>     ```bash
>     export LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/local/cuda-11.7/lib64:$LD_LIBRARY_PATH
>     ```
>   - `libcuda.so` 파일 경로 확인
>     ```bash
>     sudo find /usr/ -name 'libcuda.so.*'
>     ```
>     ![libcuda-ld-library-path]({{site.url}}/assets/images/libcuda-ld-library-path.png){: .align-center}
>
> - `CUDA error: invalid device ordinal`
>   - `NUM_GPUS` 설정이 제대로 되었는지 확인

<br>

### ModuleNotFoundError: No module named 'vision’
`tools/run_net.py`의 import 문 경로 수정

```python
#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

"""Wrapper to train and test a video classification model."""
from slowfast.config.defaults import assert_and_infer_cfg
from slowfast.utils.misc import launch_job
from slowfast.utils.parser import load_config, parse_args
from demo_net import demo # import 경로 수정
from test_net import test # import 경로 수정
from train_net import train # import 경로 수정
from visualization import visualize # import 경로 수정
```
- 관련 이슈: [No module named 'vision'](https://github.com/facebookresearch/SlowFast/issues/718)



<br>



### ModuleNotFoundError: No module named 'torch._six’

`datasets/multigrid_helper.py`의 pytorch 버전 확인 코드 수정

```python
TORCH_MAJOR = int(torch.__version__.split(".")[0])
TORCH_MINOR = int(torch.__version__.split(".")[1])

if TORCH_MAJOR >= 2 or (TORCH_MAJOR == 1 and TORCH_MINOR >= 8): # torch version 2 이상일 때 추가
    _int_classes = int
else:
    from torch._six import int_classes as _int_classes
```
- 관련 이슈: [fix import torch._six error for pytorch 2.0](https://github.com/facebookresearch/SlowFast/pull/649)
  - pytorch 특정 버전 이상에서 `_six` 모듈 사라짐(참고: [pytorch int import error](https://stackoverflow.com/questions/69170518/potential-bug-when-upgrading-to-pytorch-1-9-importerror-cannot-import-name-int))

<br>

### ValueError: Trying to pause a Timer that is already paused!

`tools/run_net.py`에서 `test_meter.iter_toc()` 부분의 코드를 아래와 같이 변경
```python
try:
    test_meter.iter_toc()
except:
    pass
```
- 관련 이슈: [a bug about test_net.py](https://github.com/facebookresearch/SlowFast/issues/599)

<br>



### TypeError: AVAMeter.log_iter_stats() missing 1 required positional argument: 'cur_iter’

`tools/run_net.py`에서 `test_meter.log_iter_stats(cur_iter)` 부분 코드를 아래와 같이 변경
```python
if not cfg.VIS_MASK.ENABLE:
    # Update and log stats.
    test_meter.update_stats(preds.detach(), labels.detach(), video_idx.detach())
    test_meter.log_iter_stats(None, cur_iter)
    
    test_meter.iter_tic()
```




<br>



# 결과

![4k-rTF3oZKw_output_cut1]({{site.url}}/assets/images/4k-rTF3oZKw_output_cut1.gif){: .align-center}

![4k-rTF3oZKw_output_cut2]({{site.url}}/assets/images/4k-rTF3oZKw_output_cut2.gif){: .align-center}





<br>

# 참고

<br>

## requirements.txt

```bash
# This file may be used to create an environment using:
# $ conda create --name <env> --file <this file>
# platform: linux-64
_libgcc_mutex=0.1=conda_forge
_openmp_mutex=4.5=2_gnu
absl-py=2.1.0=py310h06a4308_0
antlr4-python3-runtime=4.9.3=pypi_0
aom=3.9.1=hac33072_0
av=12.3.0=py310hfb821dd_0
black=24.10.0=pypi_0
blas=1.0=mkl
bottleneck=1.3.7=py310ha9d4c09_0
brotli-python=1.0.9=py310h6a678d5_8
bzip2=1.0.8=h5eee18b_6
c-ares=1.19.1=h5eee18b_0
ca-certificates=2024.9.24=h06a4308_0
cairo=1.18.0=h3faef2a_0
certifi=2024.8.30=py310h06a4308_0
charset-normalizer=3.3.2=pyhd3eb1b0_0
click=8.1.7=pypi_0
cloudpickle=3.1.0=pypi_0
colorama=0.4.6=pyhd8ed1ab_0
contourpy=1.3.0=pypi_0
cuda-cudart=11.7.99=0
cuda-cupti=11.7.101=0
cuda-libraries=11.7.1=0
cuda-nvrtc=11.7.99=0
cuda-nvtx=11.7.91=0
cuda-runtime=11.7.1=0
cuda-version=12.6=3
cycler=0.12.1=pypi_0
cython=3.0.11=pypi_0
dataclasses=0.8=pyh6d0b6a4_7
dav1d=1.2.1=hd590300_0
decorator=5.1.1=pyhd8ed1ab_0
detectron2=0.6=dev_0
expat=2.6.3=h5888daf_0
fairscale=0.4.13=pypi_0
ffmpeg=6.1.1=gpl_he44c6f3_112
filelock=3.13.1=py310h06a4308_0
font-ttf-dejavu-sans-mono=2.37=hab24e00_0
font-ttf-inconsolata=3.000=h77eed37_0
font-ttf-source-code-pro=2.038=h77eed37_0
font-ttf-ubuntu=0.83=h77eed37_3
fontconfig=2.14.2=h14ed4e7_0
fonts-conda-ecosystem=1=0
fonts-conda-forge=1=0
fonttools=4.54.1=pypi_0
freetype=2.12.1=h4a9f257_0
fribidi=1.0.10=h36c2ea0_0
fvcore=0.1.5.post20221221=pyhd8ed1ab_0
gmp=6.3.0=hac33072_2
gmpy2=2.1.2=py310heeb90bb_0
gnutls=3.7.9=hb077bed_0
graphite2=1.3.13=h59595ed_1003
grpcio=1.62.2=py310h6a678d5_0
harfbuzz=8.5.0=hfac3d4d_0
hydra-core=1.3.2=pypi_0
icu=73.2=h59595ed_0
idna=3.7=py310h06a4308_0
imageio=2.36.0=pyh12aca89_1
imageio-ffmpeg=0.5.1=pyhd8ed1ab_0
intel-openmp=2023.1.0=hdb19cb5_46306
iopath=0.1.9=pypi_0
jinja2=3.1.4=py310h06a4308_0
jpeg=9e=h5eee18b_3
kiwisolver=1.4.7=pypi_0
lame=3.100=h7b6447c_0
lcms2=2.12=h3be6417_0
ld_impl_linux-64=2.40=h12ee557_0
lerc=3.0=h295c915_0
libabseil=20240116.2=cxx17_he02047a_1
libass=0.17.1=h8fe9dca_1
libcublas=11.10.3.66=0
libcufft=10.7.2.124=h4fbf590_0
libcufile=1.11.1.6=0
libcurand=10.3.7.77=0
libcusolver=11.4.0.1=0
libcusparse=11.7.4.91=0
libdeflate=1.17=h5eee18b_1
libdrm=2.4.123=hb9d3cd8_0
libexpat=2.6.3=h5888daf_0
libffi=3.4.4=h6a678d5_1
libgcc=14.2.0=h77fa898_1
libgcc-ng=14.2.0=h69a702a_1
libgfortran-ng=11.2.0=h00389a5_1
libgfortran5=11.2.0=h1234567_1
libglib=2.80.2=hf974151_0
libgomp=14.2.0=h77fa898_1
libgrpc=1.62.2=h2d74bed_0
libhwloc=2.11.1=default_hecaa2ac_1000
libiconv=1.17=hd590300_2
libidn2=2.3.4=h5eee18b_0
libnpp=11.7.4.75=0
libnsl=2.0.1=hd590300_0
libnvjpeg=11.8.0.2=0
libopenvino=2024.1.0=h2da1b83_7
libopenvino-auto-batch-plugin=2024.1.0=hb045406_7
libopenvino-auto-plugin=2024.1.0=hb045406_7
libopenvino-hetero-plugin=2024.1.0=h5c03a75_7
libopenvino-intel-cpu-plugin=2024.1.0=h2da1b83_7
libopenvino-intel-gpu-plugin=2024.1.0=h2da1b83_7
libopenvino-intel-npu-plugin=2024.1.0=he02047a_7
libopenvino-ir-frontend=2024.1.0=h5c03a75_7
libopenvino-onnx-frontend=2024.1.0=h07e8aee_7
libopenvino-paddle-frontend=2024.1.0=h07e8aee_7
libopenvino-pytorch-frontend=2024.1.0=he02047a_7
libopenvino-tensorflow-frontend=2024.1.0=h39126c6_7
libopenvino-tensorflow-lite-frontend=2024.1.0=he02047a_7
libopus=1.3.1=h7f98852_1
libpciaccess=0.18=hd590300_0
libpng=1.6.39=h5eee18b_0
libprotobuf=4.25.3=h08a7969_0
libsqlite=3.46.0=hde9e2c9_0
libstdcxx=14.2.0=hc0a3c3a_1
libstdcxx-ng=14.2.0=h4852527_1
libtasn1=4.19.0=h5eee18b_0
libtiff=4.5.1=h6a678d5_0
libunistring=0.9.10=h27cfd23_0
libuuid=2.38.1=h0b41bf4_0
libva=2.21.0=h4ab18f5_2
libvpx=1.14.1=hac33072_0
libwebp-base=1.3.2=h5eee18b_1
libxcb=1.15=h0b41bf4_0
libxcrypt=4.4.36=hd590300_1
libxml2=2.12.7=hc051c1a_1
libzlib=1.2.13=h4ab18f5_6
lz4-c=1.9.4=h6a678d5_1
markdown=3.4.1=py310h06a4308_0
markupsafe=2.1.3=py310h5eee18b_0
matplotlib=3.9.2=pypi_0
mkl=2023.1.0=h213fc3f_46344
mkl-service=2.4.0=py310h5eee18b_1
mkl_fft=1.3.10=py310h5eee18b_0
mkl_random=1.2.7=py310h1128e8f_0
moviepy=1.0.3=pyhd8ed1ab_1
mpc=1.1.0=h10f8cd9_1
mpfr=4.0.2=hb69a4c5_1
mpmath=1.3.0=py310h06a4308_0
mypy-extensions=1.0.0=pypi_0
ncurses=6.4=h6a678d5_0
nettle=3.9.1=h7ab15ed_0
networkx=3.2.1=py310h06a4308_0
numexpr=2.8.7=py310h85018f9_0
numpy=1.26.4=py310h5f9d8c6_0
numpy-base=1.26.4=py310hb5e798b_0
ocl-icd=2.3.2=hd590300_1
omegaconf=2.3.0=pypi_0
opencv-python=4.10.0.84=pypi_0
openH.264=2.4.1=h59595ed_0
openjpeg=2.5.2=he7f1fd0_0
openssl=3.3.2=hb9d3cd8_0
p11-kit=0.24.1=hc5aa10d_0
packaging=24.1=py310h06a4308_0
pandas=2.2.2=py310h6a678d5_0
parameterized=0.9.0=pypi_0
pathspec=0.12.1=pypi_0
pcre2=10.43=hcad00b1_0
pillow=10.4.0=py310h5eee18b_0
pip=24.2=py310h06a4308_0
pixman=0.43.2=h59595ed_0
platformdirs=4.3.6=pypi_0
portalocker=2.10.1=py310hff52083_1
proglog=0.1.10=pyhaa61c55_0
protobuf=4.25.3=py310h12ddb61_0
psutil=6.1.0=pypi_0
pthread-stubs=0.4=hb9d3cd8_1002
pugixml=1.14=h59595ed_0
pybind11-abi=4=hd3eb1b0_1
pycocotools=2.0.8=pypi_0
pyparsing=3.2.0=pypi_0
pysocks=1.7.1=py310h06a4308_0
python=3.10.13=hd12c33a_1_cpython
python-dateutil=2.9.0post0=py310h06a4308_2
python-tzdata=2023.3=pyhd3eb1b0_0
python_abi=3.10=2_cp310
pytorch=2.0.1=py3.10_cuda11.7_cudnn8.5.0_0
pytorch-cuda=11.7=h778d358_5
pytorch-mutex=1.0=cuda
pytorchvideo=0.1.5=dev_0
pytz=2024.1=py310h06a4308_0
pyyaml=6.0.2=py310ha75aee5_1
re2=2022.04.01=h295c915_0
readline=8.2=h5eee18b_0
requests=2.32.3=py310h06a4308_0
scipy=1.13.1=py310h5f9d8c6_0
setuptools=75.1.0=py310h06a4308_0
simplejson=3.19.3=pypi_0
six=1.16.0=pyhd3eb1b0_1
snappy=1.2.1=ha2e4443_0
sqlite=3.45.3=h5eee18b_0
svt-av1=2.1.0=hac33072_0
sympy=1.13.2=py310h06a4308_0
tabulate=0.9.0=pyhd8ed1ab_1
tbb=2021.13.0=h84d6215_0
tensorboard=2.17.0=py310h06a4308_0
tensorboard-data-server=0.7.0=py310h52d8a92_1
tensorboardx=2.6.2.2=py310h06a4308_0
termcolor=2.5.0=pyhd8ed1ab_0
tk=8.6.14=h39e8969_0
tomli=2.0.2=pypi_0
torchtriton=2.0.0=py310
torchvision=0.15.2=py310_cu117
tqdm=4.66.5=pyhd8ed1ab_0
typing-extensions=4.11.0=py310h06a4308_0
typing_extensions=4.11.0=py310h06a4308_0
tzdata=2024b=h04d1e81_0
urllib3=2.2.3=py310h06a4308_0
werkzeug=3.0.3=py310h06a4308_0
wheel=0.44.0=py310h06a4308_0
x264=1!164.3095=h166bdaf_2
x265=3.5=h924138e_3
xorg-fixesproto=5.0=hb9d3cd8_1003
xorg-kbproto=1.0.7=hb9d3cd8_1003
xorg-libice=1.1.1=hb9d3cd8_1
xorg-libsm=1.2.4=he73a12e_1
xorg-libx11=1.8.9=h8ee46fc_0
xorg-libxau=1.0.11=hb9d3cd8_1
xorg-libxdmcp=1.1.5=hb9d3cd8_0
xorg-libxext=1.3.4=h0b41bf4_2
xorg-libxfixes=5.0.3=h7f98852_1004
xorg-libxrender=0.9.11=hd590300_0
xorg-renderproto=0.11.1=hb9d3cd8_1003
xorg-xextproto=7.3.0=hb9d3cd8_1004
xorg-xproto=7.0.31=hb9d3cd8_1008
xz=5.4.6=h5eee18b_1
yacs=0.1.8=pyhd8ed1ab_0
yaml=0.2.5=h7f98852_2
zlib=1.2.13=h4ab18f5_6
zstd=1.5.6=hc292b87_0
```
