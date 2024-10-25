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

[SlowFast](https://github.com/facebookresearch/SlowFast) 모델을 일단 그냥 돌려만 보자. 사전 학습된 모델 가중치 파일을 이용해 돌려만 보는 건 Demo로 가능하다.

- 하드웨어 사양
  - Windows 11
  - RTX 3060
- 개발 환경
  - WSL
  - Conda environment
  - Prerequisites
    - [GPU 환경 설정](https://sirzzang.github.io/ai/AI-DL-settings-linux/)
      - CUDA 11.7
      - cuDNN 8.5.0
- 사용할 모델 및 데이터셋
  - 모델: [SLOWFAST_32x2_R101_50_50_v2.1.pkl](https://dl.fbaipublicfiles.com/pyslowfast/model_zoo/ava/SLOWFAST_32x2_R101_50_50_v2.1.pkl)
    - [Model Zoo](https://github.com/facebookresearch/SlowFast/blob/main/MODEL_ZOO.md)에서 필요한 모델 다운로드

  - 데이터셋: AVA



<br>

# 개발 환경 구성

> *참고*: Python 패키지 외의 프로그램
>
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

- moviepy
  - optional이나, 설치 진행
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
  >
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


### ModuleNotFoundError: No module named 'vision’



### ModuleNotFoundError: No module named 'torch._six’



### ValueError: Trying to pause a Timer that is already paused!



### TypeError: AVAMeter.log_iter_stats() missing 1 required positional argument: 'cur_iter’





### KeyError: 'Non-existent config key: TENSORBOARD.MODEL_VIS.TOPK'

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
openh264=2.4.1=h59595ed_0
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



<br>



## 로그

```bash
(slowfast-env) eraser@DESKTOP-FAIGO7U:~/projects/SlowFast$ python tools/run_net.py --cfg ./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml
/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/torchvision/transforms/_functional_video.py:6: UserWarning: The 'torchvision.transforms._functional_video' module is deprecated since 0.12 and will be removed in the future. Please use the 'torchvision.transforms.functional' module instead.
  warnings.warn(
/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/torchvision/transforms/_transforms_video.py:22: UserWarning: The 'torchvision.transforms._transforms_video' module is deprecated since 0.12 and will be removed in the future. Please use the 'torchvision.transforms' module instead.
  warnings.warn(
config files: ['./demo/AVA/SLOWFAST_32x2_R101_50_50.yaml']
0it [00:00, ?it/s][10/25 14:59:06][INFO] demo_net.py:   38: Run demo with config:
[10/25 14:59:06][INFO] demo_net.py:   39: AUG:
  AA_TYPE: rand-m9-mstd0.5-inc1
  COLOR_JITTER: 0.4
  ENABLE: False
  GEN_MASK_LOADER: False
  INTERPOLATION: bicubic
  MASK_FRAMES: False
  MASK_RATIO: 0.0
  MASK_TUBE: False
  MASK_WINDOW_SIZE: [8, 7, 7]
  MAX_MASK_PATCHES_PER_BLOCK: None
  NUM_SAMPLE: 1
  RE_COUNT: 1
  RE_MODE: pixel
  RE_PROB: 0.25
  RE_SPLIT: False
AVA:
  ANNOTATION_DIR: /mnt/d/projects/ava
  BGR: False
  DETECTION_SCORE_THRESH: 0.8
  EXCLUSION_FILE: /mnt/d/projects/ava/annotations/ava_val_excluded_timestamps_v2.1.csv
  FRAME_DIR: /mnt/d/projects/ava/frames
  FRAME_LIST_DIR: /mnt/d/projects/ava/frame_lists
  FULL_TEST_ON_VAL: False
  GROUNDTRUTH_FILE: /mnt/d/projects/ava/annotations/ava_val_v2.1.csv
  IMG_PROC_BACKEND: cv2
  LABEL_MAP_FILE: /mnt/d/projects/ava/annotations/ava_action_list_v2.1_for_activitynet_2018.pbtxt
  TEST_FORCE_FLIP: False
  TEST_LISTS: ['val.csv']
  TEST_PREDICT_BOX_LISTS: ['/mnt/d/projects/ava/annotations/ava_val_predicted_boxes.csv']
  TRAIN_GT_BOX_LISTS: ['/mnt/d/projects/ava/annotations/ava_train_v2.1.csv']
  TRAIN_LISTS: ['train.csv']
  TRAIN_PCA_JITTER_ONLY: True
  TRAIN_PREDICT_BOX_LISTS: []
  TRAIN_USE_COLOR_AUGMENTATION: False
BENCHMARK:
  LOG_PERIOD: 100
  NUM_EPOCHS: 5
  SHUFFLE: True
BN:
  GLOBAL_SYNC: False
  NORM_TYPE: batchnorm
  NUM_BATCHES_PRECISE: 200
  NUM_SPLITS: 1
  NUM_SYNC_DEVICES: 1
  USE_PRECISE_STATS: False
  WEIGHT_DECAY: 0.0
CONTRASTIVE:
  BN_MLP: False
  BN_SYNC_MLP: False
  DELTA_CLIPS_MAX: inf
  DELTA_CLIPS_MIN: -inf
  DIM: 128
  INTERP_MEMORY: False
  KNN_ON: True
  LENGTH: 239975
  LOCAL_SHUFFLE_BN: True
  MEM_TYPE: 1d
  MLP_DIM: 2048
  MOCO_MULTI_VIEW_QUEUE: False
  MOMENTUM: 0.5
  MOMENTUM_ANNEALING: False
  NUM_CLASSES_DOWNSTREAM: 400
  NUM_MLP_LAYERS: 1
  PREDICTOR_DEPTHS: []
  QUEUE_LEN: 65536
  SEQUENTIAL: False
  SIMCLR_DIST_ON: True
  SWAV_QEUE_LEN: 0
  T: 0.07
  TYPE: mem
DATA:
  COLOR_RND_GRAYSCALE: 0.0
  DECODING_BACKEND: torchvision
  DECODING_SHORT_SIZE: 256
  DUMMY_LOAD: False
  ENSEMBLE_METHOD: sum
  IN22K_TRAINVAL: False
  IN22k_VAL_IN1K:
  INPUT_CHANNEL_NUM: [3, 3]
  INV_UNIFORM_SAMPLE: False
  IN_VAL_CROP_RATIO: 0.875
  LOADER_CHUNK_OVERALL_SIZE: 0
  LOADER_CHUNK_SIZE: 0
  MEAN: [0.45, 0.45, 0.45]
  MULTI_LABEL: False
  NUM_FRAMES: 32
  PATH_LABEL_SEPARATOR:
  PATH_PREFIX:
  PATH_TO_DATA_DIR: /mnt/d/projects/ava
  PATH_TO_PRELOAD_IMDB:
  RANDOM_FLIP: True
  REVERSE_INPUT_CHANNEL: False
  SAMPLING_RATE: 2
  SKIP_ROWS: 0
  SSL_BLUR_SIGMA_MAX: [0.0, 2.0]
  SSL_BLUR_SIGMA_MIN: [0.0, 0.1]
  SSL_COLOR_BRI_CON_SAT: [0.4, 0.4, 0.4]
  SSL_COLOR_HUE: 0.1
  SSL_COLOR_JITTER: False
  SSL_MOCOV2_AUG: False
  STD: [0.225, 0.225, 0.225]
  TARGET_FPS: 30
  TEST_CROP_SIZE: 256
  TIME_DIFF_PROB: 0.0
  TRAIN_CROP_NUM_SPATIAL: 1
  TRAIN_CROP_NUM_TEMPORAL: 1
  TRAIN_CROP_SIZE: 224
  TRAIN_JITTER_ASPECT_RELATIVE: []
  TRAIN_JITTER_FPS: 0.0
  TRAIN_JITTER_MOTION_SHIFT: False
  TRAIN_JITTER_SCALES: [256, 320]
  TRAIN_JITTER_SCALES_RELATIVE: []
  TRAIN_PCA_EIGVAL: [0.225, 0.224, 0.229]
  TRAIN_PCA_EIGVEC: [[-0.5675, 0.7192, 0.4009], [-0.5808, -0.0045, -0.814], [-0.5836, -0.6948, 0.4203]]
  USE_OFFSET_SAMPLING: False
DATA_LOADER:
  ENABLE_MULTI_THREAD_DECODE: False
  NUM_WORKERS: 2
  PIN_MEMORY: True
DEMO:
  BUFFER_SIZE: 0
  CLIP_VIS_SIZE: 10
  COMMON_CLASS_NAMES: ['watch (a person)', 'talk to (e.g., self, a person, a group)', 'listen to (a person)', 'touch (an object)', 'carry/hold (an object)', 'walk', 'sit', 'lie/sleep', 'bend/bow (at the waist)']
  COMMON_CLASS_THRES: 0.7
  DETECTRON2_CFG: COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml
  DETECTRON2_THRESH: 0.9
  DETECTRON2_WEIGHTS: detectron2://COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl
  DISPLAY_HEIGHT: 0
  DISPLAY_WIDTH: 0
  ENABLE: True
  FPS: 30
  GT_BOXES:
  INPUT_FORMAT: BGR
  INPUT_VIDEO: /mnt/d/projects/ava/videos_15min/4k-rTF3oZKw.mp4
  LABEL_FILE_PATH: /mnt/d/projects/ava/ava_classnames.json
  NUM_CLIPS_SKIP: 0
  NUM_VIS_INSTANCES: 2
  OUTPUT_FILE: /mnt/d/projects/4k-rTF3oZKw_output.mp4
  OUTPUT_FPS: -1
  PREDS_BOXES:
  SLOWMO: 1
  STARTING_SECOND: 900
  THREAD_ENABLE: False
  UNCOMMON_CLASS_THRES: 0.3
  VIS_MODE: thres
  WEBCAM: -1
DETECTION:
  ALIGNED: False
  ENABLE: True
  ROI_XFORM_RESOLUTION: 7
  SPATIAL_SCALE_FACTOR: 16
DIST_BACKEND: nccl
LOG_MODEL_INFO: True
LOG_PERIOD: 10
MASK:
  DECODER_DEPTH: 0
  DECODER_EMBED_DIM: 512
  DECODER_SEP_POS_EMBED: False
  DEC_KV_KERNEL: []
  DEC_KV_STRIDE: []
  ENABLE: False
  HEAD_TYPE: separate
  MAE_ON: False
  MAE_RND_MASK: False
  NORM_PRED_PIXEL: True
  PER_FRAME_MASKING: False
  PRED_HOG: False
  PRETRAIN_DEPTH: [15]
  SCALE_INIT_BY_DEPTH: False
  TIME_STRIDE_LOSS: True
MIXUP:
  ALPHA: 0.8
  CUTMIX_ALPHA: 1.0
  ENABLE: False
  LABEL_SMOOTH_VALUE: 0.1
  PROB: 1.0
  SWITCH_PROB: 0.5
MODEL:
  ACT_CHECKPOINT: False
  ARCH: slowfast
  DETACH_FINAL_FC: False
  DROPCONNECT_RATE: 0.0
  DROPOUT_RATE: 0.5
  FC_INIT_STD: 0.01
  FP16_ALLREDUCE: False
  FROZEN_BN: False
  HEAD_ACT: sigmoid
  LOSS_FUNC: bce
  MODEL_NAME: SlowFast
  MULTI_PATHWAY_ARCH: ['slowfast']
  NUM_CLASSES: 80
  SINGLE_PATHWAY_ARCH: ['2d', 'c2d', 'i3d', 'slow', 'x3d', 'mvit', 'maskmvit']
MULTIGRID:
  BN_BASE_SIZE: 8
  DEFAULT_B: 0
  DEFAULT_S: 0
  DEFAULT_T: 0
  EPOCH_FACTOR: 1.5
  EVAL_FREQ: 3
  LONG_CYCLE: False
  LONG_CYCLE_FACTORS: [(0.25, 0.7071067811865476), (0.5, 0.7071067811865476), (0.5, 1), (1, 1)]
  LONG_CYCLE_SAMPLING_RATE: 0
  SHORT_CYCLE: False
  SHORT_CYCLE_FACTORS: [0.5, 0.7071067811865476]
MVIT:
  CLS_EMBED_ON: True
  DEPTH: 16
  DIM_MUL: []
  DIM_MUL_IN_ATT: False
  DROPOUT_RATE: 0.0
  DROPPATH_RATE: 0.1
  EMBED_DIM: 96
  HEAD_INIT_SCALE: 1.0
  HEAD_MUL: []
  LAYER_SCALE_INIT_VALUE: 0.0
  MLP_RATIO: 4.0
  MODE: conv
  NORM: layernorm
  NORM_STEM: False
  NUM_HEADS: 1
  PATCH_2D: False
  PATCH_KERNEL: [3, 7, 7]
  PATCH_PADDING: [2, 4, 4]
  PATCH_STRIDE: [2, 4, 4]
  POOL_FIRST: False
  POOL_KVQ_KERNEL: None
  POOL_KV_STRIDE: []
  POOL_KV_STRIDE_ADAPTIVE: None
  POOL_Q_STRIDE: []
  QKV_BIAS: True
  REL_POS_SPATIAL: False
  REL_POS_TEMPORAL: False
  REL_POS_ZERO_INIT: False
  RESIDUAL_POOLING: False
  REV:
    BUFFER_LAYERS: []
    ENABLE: False
    PRE_Q_FUSION: avg
    RESPATH_FUSE: concat
    RES_PATH: conv
  SEPARATE_QKV: False
  SEP_POS_EMBED: False
  USE_ABS_POS: True
  USE_FIXED_SINCOS_POS: False
  USE_MEAN_POOLING: False
  ZERO_DECAY_POS_CLS: True
NONLOCAL:
  GROUP: [[1, 1], [1, 1], [1, 1], [1, 1]]
  INSTANTIATION: dot_product
  LOCATION: [[[], []], [[], []], [[6, 13, 20], []], [[], []]]
  POOL: [[[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]], [[2, 2, 2], [2, 2, 2]]]
NUM_GPUS: 1
NUM_SHARDS: 1
OUTPUT_DIR: .
RESNET:
  DEPTH: 101
  INPLACE_RELU: True
  NUM_BLOCK_TEMP_KERNEL: [[3, 3], [4, 4], [6, 6], [3, 3]]
  NUM_GROUPS: 1
  SPATIAL_DILATIONS: [[1, 1], [1, 1], [1, 1], [2, 2]]
  SPATIAL_STRIDES: [[1, 1], [2, 2], [2, 2], [1, 1]]
  STRIDE_1X1: False
  TRANS_FUNC: bottleneck_transform
  WIDTH_PER_GROUP: 64
  ZERO_INIT_FINAL_BN: True
  ZERO_INIT_FINAL_CONV: False
RNG_SEED: 0
SHARD_ID: 0
SLOWFAST:
  ALPHA: 4
  BETA_INV: 8
  FUSION_CONV_CHANNEL_RATIO: 2
  FUSION_KERNEL_SZ: 5
SOLVER:
  BASE_LR: 0.1
  BASE_LR_SCALE_NUM_SHARDS: False
  BETAS: (0.9, 0.999)
  CLIP_GRAD_L2NORM: None
  CLIP_GRAD_VAL: None
  COSINE_AFTER_WARMUP: False
  COSINE_END_LR: 0.0
  DAMPENING: 0.0
  GAMMA: 0.1
  LARS_ON: False
  LAYER_DECAY: 1.0
  LRS: []
  LR_POLICY: cosine
  MAX_EPOCH: 300
  MOMENTUM: 0.9
  NESTEROV: True
  OPTIMIZING_METHOD: sgd
  STEPS: []
  STEP_SIZE: 1
  WARMUP_EPOCHS: 0.0
  WARMUP_FACTOR: 0.1
  WARMUP_START_LR: 0.01
  WEIGHT_DECAY: 1e-07
  ZERO_WD_1D_PARAM: False
TASK:
TENSORBOARD:
  CATEGORIES_PATH:
  CLASS_NAMES_PATH:
  CONFUSION_MATRIX:
    ENABLE: False
    FIGSIZE: [8, 8]
    SUBSET_PATH:
  ENABLE: False
  HISTOGRAM:
    ENABLE: False
    FIGSIZE: [8, 8]
    SUBSET_PATH:
    TOPK: 10
  LOG_DIR:
  MODEL_VIS:
    ACTIVATIONS: False
    COLORMAP: Pastel2
    ENABLE: False
    GRAD_CAM:
      COLORMAP: viridis
      ENABLE: True
      LAYER_LIST: []
      USE_TRUE_LABEL: False
    INPUT_VIDEO: False
    LAYER_LIST: []
    MODEL_WEIGHTS: False
    TOPK_PREDS: 1
  PREDICTIONS_PATH:
  WRONG_PRED_VIS:
    ENABLE: False
    SUBSET_PATH:
    TAG: Incorrectly classified videos.
TEST:
  BATCH_SIZE: 8
  CHECKPOINT_FILE_PATH:
  CHECKPOINT_TYPE: pytorch
  DATASET: ava
  ENABLE: False
  NUM_ENSEMBLE_VIEWS: 10
  NUM_SPATIAL_CROPS: 3
  NUM_TEMPORAL_CLIPS: []
  SAVE_RESULTS_PATH:
TRAIN:
  AUTO_RESUME: True
  BATCH_SIZE: 16
  CHECKPOINT_CLEAR_NAME_PATTERN: ()
  CHECKPOINT_EPOCH_RESET: False
  CHECKPOINT_FILE_PATH: /mnt/d/projects/model_zoo/SLOWFAST_32x2_R101_50_50_v2.1.pkl
  CHECKPOINT_INFLATE: False
  CHECKPOINT_IN_INIT: False
  CHECKPOINT_PERIOD: 1
  CHECKPOINT_TYPE: caffe2
  DATASET: ava
  ENABLE: False
  EVAL_PERIOD: 1
  KILL_LOSS_EXPLOSION_FACTOR: 0.0
  MIXED_PRECISION: False
VIS_MASK:
  ENABLE: False
X3D:
  BN_LIN5: False
  BOTTLENECK_FACTOR: 1.0
  CHANNELWISE_3x3x3: True
  DEPTH_FACTOR: 1.0
  DIM_C1: 12
  DIM_C5: 2048
  SCALE_RES2: False
  WIDTH_FACTOR: 1.0
[10/25 14:59:09][INFO] predictor.py:  177: Initialized Detectron2 Object Detection Model.
[10/25 14:59:09][INFO] detection_checkpoint.py:   38: [DetectionCheckpointer] Loading from detectron2://COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl ...
[10/25 14:59:09][INFO] file_io.py:  798: URL https://dl.fbaipublicfiles.com/detectron2/COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl cached in /home/eraser/.torch/iopath_cache/detectron2/COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl
[10/25 14:59:09][INFO] checkpoint.py:  150: [Checkpointer] Loading from /home/eraser/.torch/iopath_cache/detectron2/COCO-Detection/faster_rcnn_R_50_FPN_3x/137849458/model_final_280758.pkl ...
[10/25 14:59:09][INFO] detection_checkpoint.py:   76: Reading a file from 'Detectron2 Model Zoo'
[10/25 14:59:09][INFO] predictor.py:   44: Start loading model weights.
[10/25 14:59:09][INFO] checkpoint.py:  213: Loading network weights from /mnt/d/projects/model_zoo/SLOWFAST_32x2_R101_50_50_v2.1.pkl.
[10/25 14:59:14][INFO] checkpoint.py:  252: res4_19_branch2c_bn_riv: (1024,) => s4.pathway0_res19.branch2.c_bn.running_var: (1024,)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res3_2_branch2b_bn_rm: (16,) => s3.pathway1_res2.branch2.b_bn.running_mean: (16,)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res4_2_branch2b_bn_riv: (32,) => s4.pathway1_res2.branch2.b_bn.running_var: (32,)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res2_1_branch2b_w: (8, 8, 1, 3, 3) => s2.pathway1_res1.branch2.b.weight: (8, 8, 1, 3, 3)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res4_9_branch2a_bn_rm: (32,) => s4.pathway1_res9.branch2.a_bn.running_mean: (32,)
[10/25 14:59:14][INFO] checkpoint.py:  252: res5_1_branch2b_w: (512, 512, 1, 3, 3) => s5.pathway0_res1.branch2.b.weight: (512, 512, 1, 3, 3)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res4_9_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res9.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:14][INFO] checkpoint.py:  252: t_res4_5_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res5.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_16_branch2b_bn_s: (256,) => s4.pathway0_res16.branch2.b_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_0_branch2c_bn_rm: (1024,) => s4.pathway0_res0.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_4_branch2c_bn_rm: (128,) => s4.pathway1_res4.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res2_0_branch2a_w: (8, 8, 3, 1, 1) => s2.pathway1_res0.branch2.a.weight: (8, 8, 3, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_2_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res2.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_21_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res21.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_20_branch2a_bn_b: (256,) => s4.pathway0_res20.branch2.a_bn.bias: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_20_branch2a_bn_s: (256,) => s4.pathway0_res20.branch2.a_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_20_branch2a_bn_s: (32,) => s4.pathway1_res20.branch2.a_bn.weight: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_2_branch2c_bn_rm: (128,) => s4.pathway1_res2.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_20_branch2a_bn_b: (32,) => s4.pathway1_res20.branch2.a_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_21_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res21.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_8_branch2c_bn_rm: (128,) => s4.pathway1_res8.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_19_branch2c_bn_rm: (128,) => s4.pathway1_res19.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res3_0_branch1_w: (512, 320, 1, 1, 1) => s3.pathway0_res0.branch1.weight: (512, 320, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res3_0_branch2b_bn_rm: (16,) => s3.pathway1_res0.branch2.b_bn.running_mean: (16,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_16_branch2b_bn_b: (32,) => s4.pathway1_res16.branch2.b_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_21_branch2c_bn_rm: (1024,) => s4.pathway0_res21.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_5_branch2a_bn_rm: (32,) => s4.pathway1_res5.branch2.a_bn.running_mean: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_6_branch2c_bn_rm: (128,) => s4.pathway1_res6.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res2_0_branch2c_w: (32, 8, 1, 1, 1) => s2.pathway1_res0.branch2.c.weight: (32, 8, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_8_branch2a_bn_rm: (32,) => s4.pathway1_res8.branch2.a_bn.running_mean: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: nonlocal_conv4_13_phi_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal13.conv_phi.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_21_branch2b_bn_rm: (256,) => s4.pathway0_res21.branch2.b_bn.running_mean: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res5_0_branch2a_bn_riv: (512,) => s5.pathway0_res0.branch2.a_bn.running_var: (512,)
[10/25 14:59:15][INFO] checkpoint.py:  252: nonlocal_conv4_6_phi_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal6.conv_phi.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: nonlocal_conv4_6_phi_b: (512,) => s4.pathway0_nonlocal6.conv_phi.bias: (512,)
[10/25 14:59:15][INFO] checkpoint.py:  252: nonlocal_conv4_13_phi_b: (512,) => s4.pathway0_nonlocal13.conv_phi.bias: (512,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_20_branch2a_bn_riv: (256,) => s4.pathway0_res20.branch2.a_bn.running_var: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_5_branch2b_bn_s: (256,) => s4.pathway0_res5.branch2.b_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res2_1_branch2b_bn_rm: (8,) => s2.pathway1_res1.branch2.b_bn.running_mean: (8,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_22_branch2a_bn_b: (32,) => s4.pathway1_res22.branch2.a_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_15_branch2c_bn_b: (128,) => s4.pathway1_res15.branch2.c_bn.bias: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res3_1_branch2a_bn_riv: (128,) => s3.pathway0_res1.branch2.a_bn.running_var: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_15_branch2c_bn_s: (128,) => s4.pathway1_res15.branch2.c_bn.weight: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_21_branch2c_bn_rm: (128,) => s4.pathway1_res21.branch2.c_bn.running_mean: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res3_2_branch2b_bn_riv: (16,) => s3.pathway1_res2.branch2.b_bn.running_var: (16,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_0_branch2a_bn_b: (32,) => s4.pathway1_res0.branch2.a_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_16_branch2a_bn_rm: (256,) => s4.pathway0_res16.branch2.a_bn.running_mean: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_20_branch2b_bn_riv: (256,) => s4.pathway0_res20.branch2.b_bn.running_var: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_0_branch2a_bn_s: (32,) => s4.pathway1_res0.branch2.a_bn.weight: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_15_branch2c_bn_b: (1024,) => s4.pathway0_res15.branch2.c_bn.bias: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res3_1_branch2b_bn_b: (128,) => s3.pathway0_res1.branch2.b_bn.bias: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_1_branch2a_bn_s: (256,) => s4.pathway0_res1.branch2.a_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res2_1_branch2c_bn_b: (256,) => s2.pathway0_res1.branch2.c_bn.bias: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_20_branch2b_bn_b: (32,) => s4.pathway1_res20.branch2.b_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res3_1_branch2b_bn_s: (128,) => s3.pathway0_res1.branch2.b_bn.weight: (128,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_1_branch2a_bn_b: (256,) => s4.pathway0_res1.branch2.a_bn.bias: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_subsample_w: (256, 128, 5, 1, 1) => s4_fuse.conv_f2s.weight: (256, 128, 5, 1, 1)
[10/25 14:59:15][INFO] checkpoint.py:  252: res2_1_branch2c_bn_s: (256,) => s2.pathway0_res1.branch2.c_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_20_branch2b_bn_s: (32,) => s4.pathway1_res20.branch2.b_bn.weight: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_7_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res7.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_6_branch2c_bn_riv: (1024,) => s4.pathway0_res6.branch2.c_bn.running_var: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_10_branch2a_bn_rm: (32,) => s4.pathway1_res10.branch2.a_bn.running_mean: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: nonlocal_conv4_6_bn_rm: (1024,) => s4.pathway0_nonlocal6.bn.running_mean: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_9_branch2c_bn_riv: (1024,) => s4.pathway0_res9.branch2.c_bn.running_var: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_12_branch2a_bn_rm: (32,) => s4.pathway1_res12.branch2.a_bn.running_mean: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_17_branch2a_bn_rm: (256,) => s4.pathway0_res17.branch2.a_bn.running_mean: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_1_branch2b_bn_b: (256,) => s4.pathway0_res1.branch2.b_bn.bias: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_17_branch2b_bn_riv: (256,) => s4.pathway0_res17.branch2.b_bn.running_var: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_1_branch2b_bn_s: (256,) => s4.pathway0_res1.branch2.b_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_3_branch2c_bn_rm: (1024,) => s4.pathway0_res3.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_15_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res15.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_8_branch2a_bn_riv: (32,) => s4.pathway1_res8.branch2.a_bn.running_var: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_20_branch2a_bn_rm: (256,) => s4.pathway0_res20.branch2.a_bn.running_mean: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_2_branch2a_bn_rm: (32,) => s4.pathway1_res2.branch2.a_bn.running_mean: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_14_branch2b_bn_s: (256,) => s4.pathway0_res14.branch2.b_bn.weight: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_6_branch2a_bn_b: (32,) => s4.pathway1_res6.branch2.a_bn.bias: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: res4_14_branch2b_bn_b: (256,) => s4.pathway0_res14.branch2.b_bn.bias: (256,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_11_branch2b_bn_s: (32,) => s4.pathway1_res11.branch2.b_bn.weight: (32,)
[10/25 14:59:15][INFO] checkpoint.py:  252: t_res4_6_branch2a_bn_s: (32,) => s4.pathway1_res6.branch2.a_bn.weight: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_7_branch2c_bn_riv: (1024,) => s4.pathway0_res7.branch2.c_bn.running_var: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res2_0_branch2a_bn_rm: (8,) => s2.pathway1_res0.branch2.a_bn.running_mean: (8,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_1_branch2b_bn_b: (32,) => s4.pathway1_res1.branch2.b_bn.bias: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: nonlocal_conv4_13_out_b: (1024,) => s4.pathway0_nonlocal13.conv_out.bias: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_22_branch2a_bn_b: (256,) => s4.pathway0_res22.branch2.a_bn.bias: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_4_branch2a_bn_b: (32,) => s4.pathway1_res4.branch2.a_bn.bias: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_9_branch2c_bn_b: (128,) => s4.pathway1_res9.branch2.c_bn.bias: (128,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_14_branch2b_bn_rm: (256,) => s4.pathway0_res14.branch2.b_bn.running_mean: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_11_branch2b_bn_riv: (32,) => s4.pathway1_res11.branch2.b_bn.running_var: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_0_branch2a_bn_s: (16,) => s3.pathway1_res0.branch2.a_bn.weight: (16,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_9_branch2c_bn_s: (128,) => s4.pathway1_res9.branch2.c_bn.weight: (128,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_2_branch2c_bn_riv: (128,) => s4.pathway1_res2.branch2.c_bn.running_var: (128,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_0_branch2a_bn_b: (16,) => s3.pathway1_res0.branch2.a_bn.bias: (16,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res2_0_branch2b_bn_riv: (8,) => s2.pathway1_res0.branch2.b_bn.running_var: (8,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res2_2_branch2b_w: (64, 64, 1, 3, 3) => s2.pathway0_res2.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_15_branch2a_bn_rm: (32,) => s4.pathway1_res15.branch2.a_bn.running_mean: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_11_branch2a_bn_riv: (256,) => s4.pathway0_res11.branch2.a_bn.running_var: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_18_branch2a_bn_rm: (256,) => s4.pathway0_res18.branch2.a_bn.running_mean: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_6_branch2b_bn_riv: (256,) => s4.pathway0_res6.branch2.b_bn.running_var: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_16_branch2c_bn_rm: (128,) => s4.pathway1_res16.branch2.c_bn.running_mean: (128,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res5_0_branch1_bn_b: (256,) => s5.pathway1_res0.branch1_bn.bias: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_16_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res16.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_subsample_bn_rm: (256,) => s4_fuse.bn.running_mean: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res5_0_branch1_bn_s: (256,) => s5.pathway1_res0.branch1_bn.weight: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_16_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res16.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_22_branch2a_bn_riv: (256,) => s4.pathway0_res22.branch2.a_bn.running_var: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res5_0_branch2b_bn_rm: (64,) => s5.pathway1_res0.branch2.b_bn.running_mean: (64,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_8_branch2c_bn_b: (1024,) => s4.pathway0_res8.branch2.c_bn.bias: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res5_2_branch2a_w: (512, 2048, 3, 1, 1) => s5.pathway0_res2.branch2.a.weight: (512, 2048, 3, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_8_branch2c_bn_s: (1024,) => s4.pathway0_res8.branch2.c_bn.weight: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res2_0_branch2c_bn_rm: (256,) => s2.pathway0_res0.branch2.c_bn.running_mean: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_3_branch2b_bn_s: (256,) => s4.pathway0_res3.branch2.b_bn.weight: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_3_branch2b_bn_b: (256,) => s4.pathway0_res3.branch2.b_bn.bias: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res2_1_branch2a_bn_rm: (8,) => s2.pathway1_res1.branch2.a_bn.running_mean: (8,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res2_0_branch2b_bn_rm: (64,) => s2.pathway0_res0.branch2.b_bn.running_mean: (64,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_13_branch2b_bn_b: (256,) => s4.pathway0_res13.branch2.b_bn.bias: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_8_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res8.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_9_branch2b_bn_riv: (32,) => s4.pathway1_res9.branch2.b_bn.running_var: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res5_2_branch2b_w: (512, 512, 1, 3, 3) => s5.pathway0_res2.branch2.b.weight: (512, 512, 1, 3, 3)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_11_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res11.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res2_1_branch2c_bn_riv: (32,) => s2.pathway1_res1.branch2.c_bn.running_var: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res3_0_branch2c_bn_rm: (512,) => s3.pathway0_res0.branch2.c_bn.running_mean: (512,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res3_2_branch2c_bn_b: (512,) => s3.pathway0_res2.branch2.c_bn.bias: (512,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_0_branch2a_w: (16, 32, 3, 1, 1) => s3.pathway1_res0.branch2.a.weight: (16, 32, 3, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res5_1_branch2c_bn_riv: (2048,) => s5.pathway0_res1.branch2.c_bn.running_var: (2048,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_1_branch2a_bn_riv: (256,) => s4.pathway0_res1.branch2.a_bn.running_var: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_1_branch2b_bn_rm: (32,) => s4.pathway1_res1.branch2.b_bn.running_mean: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_20_branch2c_bn_rm: (128,) => s4.pathway1_res20.branch2.c_bn.running_mean: (128,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_0_branch2c_w: (64, 16, 1, 1, 1) => s3.pathway1_res0.branch2.c.weight: (64, 16, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_19_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res19.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_16_branch2c_bn_b: (1024,) => s4.pathway0_res16.branch2.c_bn.bias: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_16_branch2c_bn_s: (1024,) => s4.pathway0_res16.branch2.c_bn.weight: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_19_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res19.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_14_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res14.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_15_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res15.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res2_0_branch2a_bn_riv: (64,) => s2.pathway0_res0.branch2.a_bn.running_var: (64,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_7_branch2b_bn_riv: (32,) => s4.pathway1_res7.branch2.b_bn.running_var: (32,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_17_branch2c_bn_b: (1024,) => s4.pathway0_res17.branch2.c_bn.bias: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_2_branch2a_bn_b: (16,) => s3.pathway1_res2.branch2.a_bn.bias: (16,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_22_branch2b_bn_riv: (256,) => s4.pathway0_res22.branch2.b_bn.running_var: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_12_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res12.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res3_2_branch2a_bn_s: (16,) => s3.pathway1_res2.branch2.a_bn.weight: (16,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_17_branch2c_bn_s: (1024,) => s4.pathway0_res17.branch2.c_bn.weight: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_12_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res12.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_20_branch2c_bn_s: (1024,) => s4.pathway0_res20.branch2.c_bn.weight: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res5_2_branch2c_bn_b: (256,) => s5.pathway1_res2.branch2.c_bn.bias: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_8_branch2b_bn_rm: (256,) => s4.pathway0_res8.branch2.b_bn.running_mean: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res4_10_branch2c_bn_rm: (1024,) => s4.pathway0_res10.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res4_0_branch1_w: (128, 64, 1, 1, 1) => s4.pathway1_res0.branch1.weight: (128, 64, 1, 1, 1)
[10/25 14:59:16][INFO] checkpoint.py:  252: t_res5_2_branch2c_bn_s: (256,) => s5.pathway1_res2.branch2.c_bn.weight: (256,)
[10/25 14:59:16][INFO] checkpoint.py:  252: res2_2_branch2c_w: (256, 64, 1, 1, 1) => s2.pathway0_res2.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_11_branch2c_bn_rm: (1024,) => s4.pathway0_res11.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res5_2_branch2b_bn_rm: (512,) => s5.pathway0_res2.branch2.b_bn.running_mean: (512,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res5_0_branch2b_bn_s: (512,) => s5.pathway0_res0.branch2.b_bn.weight: (512,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res5_0_branch2b_bn_b: (512,) => s5.pathway0_res0.branch2.b_bn.bias: (512,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_1_branch2c_bn_b: (128,) => s4.pathway1_res1.branch2.c_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_17_branch2b_bn_riv: (32,) => s4.pathway1_res17.branch2.b_bn.running_var: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_1_branch2c_bn_s: (128,) => s4.pathway1_res1.branch2.c_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_0_branch2b_bn_rm: (256,) => s4.pathway0_res0.branch2.b_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res2_2_branch2c_bn_rm: (256,) => s2.pathway0_res2.branch2.c_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_10_branch2a_bn_riv: (256,) => s4.pathway0_res10.branch2.a_bn.running_var: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_0_branch1_bn_b: (1024,) => s4.pathway0_res0.branch1_bn.bias: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_10_branch2a_bn_s: (32,) => s4.pathway1_res10.branch2.a_bn.weight: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_2_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res2.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_14_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res14.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_10_branch2a_bn_b: (32,) => s4.pathway1_res10.branch2.a_bn.bias: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res5_2_branch2b_bn_riv: (64,) => s5.pathway1_res2.branch2.b_bn.running_var: (64,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_15_branch2a_bn_b: (32,) => s4.pathway1_res15.branch2.a_bn.bias: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_1_branch2b_bn_rm: (256,) => s4.pathway0_res1.branch2.b_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_17_branch2c_bn_riv: (128,) => s4.pathway1_res17.branch2.c_bn.running_var: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_17_branch2c_bn_riv: (1024,) => s4.pathway0_res17.branch2.c_bn.running_var: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_b: (128,) => s4.pathway1_res22.branch2.c_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_22_branch2a_bn_rm: (32,) => s4.pathway1_res22.branch2.a_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_13_branch2b_bn_rm: (32,) => s4.pathway1_res13.branch2.b_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res2_1_branch2a_w: (8, 32, 3, 1, 1) => s2.pathway1_res1.branch2.a.weight: (8, 32, 3, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_s: (128,) => s4.pathway1_res22.branch2.c_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_4_branch2a_w: (32, 128, 3, 1, 1) => s4.pathway1_res4.branch2.a.weight: (32, 128, 3, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_2_branch2b_bn_rm: (256,) => s4.pathway0_res2.branch2.b_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_3_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res3.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_0_branch2b_bn_b: (32,) => s4.pathway1_res0.branch2.b_bn.bias: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_0_branch2b_bn_s: (32,) => s4.pathway1_res0.branch2.b_bn.weight: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_3_branch2a_w: (32, 128, 3, 1, 1) => s4.pathway1_res3.branch2.a.weight: (32, 128, 3, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_rm: (128,) => s4.pathway1_res22.branch2.c_bn.running_mean: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res2_1_branch2a_bn_s: (64,) => s2.pathway0_res1.branch2.a_bn.weight: (64,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_20_branch2c_bn_b: (128,) => s4.pathway1_res20.branch2.c_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_5_branch2b_bn_rm: (256,) => s4.pathway0_res5.branch2.b_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res2_1_branch2a_bn_b: (64,) => s2.pathway0_res1.branch2.a_bn.bias: (64,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res3_1_branch2b_w: (128, 128, 1, 3, 3) => s3.pathway0_res1.branch2.b.weight: (128, 128, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_20_branch2c_bn_s: (128,) => s4.pathway1_res20.branch2.c_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_7_branch2a_bn_rm: (32,) => s4.pathway1_res7.branch2.a_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_4_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res4.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res5_1_branch2c_bn_riv: (256,) => s5.pathway1_res1.branch2.c_bn.running_var: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res3_0_branch2b_bn_b: (128,) => s3.pathway0_res0.branch2.b_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_17_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res17.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_12_branch2b_bn_riv: (32,) => s4.pathway1_res12.branch2.b_bn.running_var: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res3_0_branch2b_bn_s: (128,) => s3.pathway0_res0.branch2.b_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_0_branch2a_bn_rm: (32,) => s4.pathway1_res0.branch2.a_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_15_branch2b_bn_rm: (32,) => s4.pathway1_res15.branch2.b_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_2_branch2a_bn_s: (32,) => s4.pathway1_res2.branch2.a_bn.weight: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_17_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res17.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_2_branch2a_bn_b: (32,) => s4.pathway1_res2.branch2.a_bn.bias: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: nonlocal_conv4_20_theta_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal20.conv_theta.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_5_branch2c_bn_s: (128,) => s4.pathway1_res5.branch2.c_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_8_branch2b_bn_s: (256,) => s4.pathway0_res8.branch2.b_bn.weight: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_19_branch2c_bn_rm: (1024,) => s4.pathway0_res19.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_10_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res10.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_8_branch2b_bn_b: (256,) => s4.pathway0_res8.branch2.b_bn.bias: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res2_0_branch2c_bn_rm: (32,) => s2.pathway1_res0.branch2.c_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_8_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res8.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_12_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res12.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_0_branch2c_bn_riv: (1024,) => s4.pathway0_res0.branch2.c_bn.running_var: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_10_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res10.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_3_branch2a_bn_s: (256,) => s4.pathway0_res3.branch2.a_bn.weight: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_8_branch2a_bn_b: (256,) => s4.pathway0_res8.branch2.a_bn.bias: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_13_branch2a_bn_rm: (256,) => s4.pathway0_res13.branch2.a_bn.running_mean: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res3_2_branch2b_w: (128, 128, 1, 3, 3) => s3.pathway0_res2.branch2.b.weight: (128, 128, 1, 3, 3)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res3_3_branch2b_bn_rm: (16,) => s3.pathway1_res3.branch2.b_bn.running_mean: (16,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_12_branch2c_bn_rm: (128,) => s4.pathway1_res12.branch2.c_bn.running_mean: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_5_branch2c_bn_b: (128,) => s4.pathway1_res5.branch2.c_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_2_branch2b_bn_b: (32,) => s4.pathway1_res2.branch2.b_bn.bias: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_4_branch2b_bn_rm: (32,) => s4.pathway1_res4.branch2.b_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_13_branch2a_bn_riv: (256,) => s4.pathway0_res13.branch2.a_bn.running_var: (256,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_2_branch2b_bn_s: (32,) => s4.pathway1_res2.branch2.b_bn.weight: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_20_branch2b_bn_rm: (32,) => s4.pathway1_res20.branch2.b_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_18_branch2c_bn_b: (128,) => s4.pathway1_res18.branch2.c_bn.bias: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: res4_4_branch2c_bn_rm: (1024,) => s4.pathway0_res4.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_18_branch2c_bn_s: (128,) => s4.pathway1_res18.branch2.c_bn.weight: (128,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_17_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res17.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res4_0_branch2b_bn_rm: (32,) => s4.pathway1_res0.branch2.b_bn.running_mean: (32,)
[10/25 14:59:17][INFO] checkpoint.py:  252: t_res5_0_branch2b_bn_s: (64,) => s5.pathway1_res0.branch2.b_bn.weight: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_1_branch2b_bn_rm: (64,) => s5.pathway1_res1.branch2.b_bn.running_mean: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: nonlocal_conv4_20_bn_riv: (1024,) => s4.pathway0_nonlocal20.bn.running_var: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_6_branch2a_bn_riv: (32,) => s4.pathway1_res6.branch2.a_bn.running_var: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res3_2_branch2c_w: (64, 16, 1, 1, 1) => s3.pathway1_res2.branch2.c.weight: (64, 16, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_14_branch2a_bn_s: (32,) => s4.pathway1_res14.branch2.a_bn.weight: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_0_branch2b_bn_b: (64,) => s5.pathway1_res0.branch2.b_bn.bias: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_1_branch2c_bn_rm: (256,) => s5.pathway1_res1.branch2.c_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_18_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res18.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_14_branch2a_bn_b: (32,) => s4.pathway1_res14.branch2.a_bn.bias: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_12_branch2c_bn_riv: (128,) => s4.pathway1_res12.branch2.c_bn.running_var: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_15_branch2a_bn_s: (32,) => s4.pathway1_res15.branch2.a_bn.weight: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res3_2_branch2a_w: (16, 64, 3, 1, 1) => s3.pathway1_res2.branch2.a.weight: (16, 64, 3, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_subsample_bn_riv: (256,) => s4_fuse.bn.running_var: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_0_branch2a_bn_rm: (64,) => s5.pathway1_res0.branch2.a_bn.running_mean: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_1_branch2a_w: (256, 1024, 3, 1, 1) => s4.pathway0_res1.branch2.a.weight: (256, 1024, 3, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_10_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res10.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_0_branch2c_bn_s: (32,) => s2.pathway1_res0.branch2.c_bn.weight: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_12_branch2b_bn_rm: (256,) => s4.pathway0_res12.branch2.b_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_pool1_subsample_w: (16, 8, 5, 1, 1) => s1_fuse.conv_f2s.weight: (16, 8, 5, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_1_branch2c_bn_riv: (128,) => s4.pathway1_res1.branch2.c_bn.running_var: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_13_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res13.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_4_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res4.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_15_branch2c_bn_rm: (1024,) => s4.pathway0_res15.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_1_branch2b_bn_riv: (64,) => s5.pathway1_res1.branch2.b_bn.running_var: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res5_1_branch2c_bn_rm: (2048,) => s5.pathway0_res1.branch2.c_bn.running_mean: (2048,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_2_branch2a_bn_rm: (8,) => s2.pathway1_res2.branch2.a_bn.running_mean: (8,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_7_branch2c_bn_s: (128,) => s4.pathway1_res7.branch2.c_bn.weight: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_12_branch2a_bn_s: (256,) => s4.pathway0_res12.branch2.a_bn.weight: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res2_2_branch2b_bn_rm: (64,) => s2.pathway0_res2.branch2.b_bn.running_mean: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_7_branch2c_bn_b: (128,) => s4.pathway1_res7.branch2.c_bn.bias: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_12_branch2a_bn_b: (256,) => s4.pathway0_res12.branch2.a_bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_20_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res20.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_subsample_bn_s: (256,) => s4_fuse.bn.weight: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_18_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res18.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_pool1_subsample_bn_rm: (16,) => s1_fuse.bn.running_mean: (16,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_subsample_bn_b: (256,) => s4_fuse.bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_b: (64,) => s3.pathway1_res3.branch2.c_bn.bias: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_17_branch2b_bn_b: (256,) => s4.pathway0_res17.branch2.b_bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_2_branch2c_bn_rm: (256,) => s5.pathway1_res2.branch2.c_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_17_branch2b_bn_s: (256,) => s4.pathway0_res17.branch2.b_bn.weight: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_2_branch2a_bn_s: (64,) => s5.pathway1_res2.branch2.a_bn.weight: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_18_branch2c_bn_b: (1024,) => s4.pathway0_res18.branch2.c_bn.bias: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_18_branch2c_bn_s: (1024,) => s4.pathway0_res18.branch2.c_bn.weight: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res5_2_branch2a_bn_b: (64,) => s5.pathway1_res2.branch2.a_bn.bias: (64,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_0_branch2c_bn_b: (128,) => s4.pathway1_res0.branch2.c_bn.bias: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_0_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res0.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_17_branch2a_bn_s: (256,) => s4.pathway0_res17.branch2.a_bn.weight: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_0_branch1_bn_rm: (128,) => s4.pathway1_res0.branch1_bn.running_mean: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_10_branch2a_bn_b: (256,) => s4.pathway0_res10.branch2.a_bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_16_branch2b_bn_s: (32,) => s4.pathway1_res16.branch2.b_bn.weight: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_17_branch2a_bn_b: (256,) => s4.pathway0_res17.branch2.a_bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_20_branch2b_bn_rm: (256,) => s4.pathway0_res20.branch2.b_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_1_branch2a_bn_b: (32,) => s4.pathway1_res1.branch2.a_bn.bias: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_6_branch2b_bn_rm: (256,) => s4.pathway0_res6.branch2.b_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_18_branch2b_bn_riv: (32,) => s4.pathway1_res18.branch2.b_bn.running_var: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_3_branch2b_bn_riv: (256,) => s4.pathway0_res3.branch2.b_bn.running_var: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res3_3_branch2a_bn_rm: (128,) => s3.pathway0_res3.branch2.a_bn.running_mean: (128,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res4_3_branch2b_bn_riv: (32,) => s4.pathway1_res3.branch2.b_bn.running_var: (32,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_5_branch2b_bn_b: (256,) => s4.pathway0_res5.branch2.b_bn.bias: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res3_0_branch1_bn_rm: (512,) => s3.pathway0_res0.branch1_bn.running_mean: (512,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_14_branch2a_bn_rm: (256,) => s4.pathway0_res14.branch2.a_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_5_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res5.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: res3_3_branch2c_bn_b: (512,) => s3.pathway0_res3.branch2.c_bn.bias: (512,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_4_branch2c_bn_riv: (1024,) => s4.pathway0_res4.branch2.c_bn.running_var: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res3_3_branch2c_bn_s: (512,) => s3.pathway0_res3.branch2.c_bn.weight: (512,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_6_branch2a_bn_rm: (256,) => s4.pathway0_res6.branch2.a_bn.running_mean: (256,)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_2_branch2c_w: (32, 8, 1, 1, 1) => s2.pathway1_res2.branch2.c.weight: (32, 8, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_0_branch2b_bn_b: (8,) => s2.pathway1_res0.branch2.b_bn.bias: (8,)
[10/25 14:59:18][INFO] checkpoint.py:  252: nonlocal_conv4_6_out_w: (1024, 512, 1, 1, 1) => s4.pathway0_nonlocal6.conv_out.weight: (1024, 512, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_2_branch2a_w: (8, 32, 3, 1, 1) => s2.pathway1_res2.branch2.a.weight: (8, 32, 3, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: t_res2_0_branch2b_bn_s: (8,) => s2.pathway1_res0.branch2.b_bn.weight: (8,)
[10/25 14:59:18][INFO] checkpoint.py:  252: nonlocal_conv4_6_out_b: (1024,) => s4.pathway0_nonlocal6.conv_out.bias: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_4_branch2c_bn_b: (1024,) => s4.pathway0_res4.branch2.c_bn.bias: (1024,)
[10/25 14:59:18][INFO] checkpoint.py:  252: nonlocal_conv4_20_phi_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal20.conv_phi.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:18][INFO] checkpoint.py:  252: res5_2_branch2b_bn_riv: (512,) => s5.pathway0_res2.branch2.b_bn.running_var: (512,)
[10/25 14:59:18][INFO] checkpoint.py:  252: res4_11_branch2c_bn_riv: (1024,) => s4.pathway0_res11.branch2.c_bn.running_var: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: nonlocal_conv4_20_phi_b: (512,) => s4.pathway0_nonlocal20.conv_phi.bias: (512,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_16_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res16.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_4_branch2c_bn_s: (1024,) => s4.pathway0_res4.branch2.c_bn.weight: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res3_1_branch2b_bn_rm: (16,) => s3.pathway1_res1.branch2.b_bn.running_mean: (16,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_8_branch2a_bn_s: (256,) => s4.pathway0_res8.branch2.a_bn.weight: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_1_branch2b_bn_b: (512,) => s5.pathway0_res1.branch2.b_bn.bias: (512,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_13_branch2a_bn_b: (32,) => s4.pathway1_res13.branch2.a_bn.bias: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_13_branch2b_bn_riv: (256,) => s4.pathway0_res13.branch2.b_bn.running_var: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_1_branch2b_bn_s: (512,) => s5.pathway0_res1.branch2.b_bn.weight: (512,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res3_0_branch1_bn_rm: (64,) => s3.pathway1_res0.branch1_bn.running_mean: (64,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_13_branch2a_bn_s: (32,) => s4.pathway1_res13.branch2.a_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_14_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res14.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_2_branch2c_bn_s: (1024,) => s4.pathway0_res2.branch2.c_bn.weight: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_9_branch2c_bn_rm: (128,) => s4.pathway1_res9.branch2.c_bn.running_mean: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_3_branch2b_bn_rm: (256,) => s4.pathway0_res3.branch2.b_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_15_branch2c_bn_s: (1024,) => s4.pathway0_res15.branch2.c_bn.weight: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_14_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res14.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res5_0_branch1_w: (256, 128, 1, 1, 1) => s5.pathway1_res0.branch1.weight: (256, 128, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_13_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res13.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_12_branch2c_bn_riv: (1024,) => s4.pathway0_res12.branch2.c_bn.running_var: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_7_branch2c_bn_rm: (128,) => s4.pathway1_res7.branch2.c_bn.running_mean: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_1_branch2c_w: (2048, 512, 1, 1, 1) => s5.pathway0_res1.branch2.c.weight: (2048, 512, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_5_branch2b_bn_rm: (32,) => s4.pathway1_res5.branch2.b_bn.running_mean: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res3_2_branch2a_bn_rm: (16,) => s3.pathway1_res2.branch2.a_bn.running_mean: (16,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_1_branch2c_bn_s: (32,) => s2.pathway1_res1.branch2.c_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_2_branch2c_bn_riv: (2048,) => s5.pathway0_res2.branch2.c_bn.running_var: (2048,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_10_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res10.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: res3_0_branch1_bn_riv: (512,) => s3.pathway0_res0.branch1_bn.running_var: (512,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_19_branch2c_bn_riv: (128,) => s4.pathway1_res19.branch2.c_bn.running_var: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_10_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res10.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_9_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res9.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res3_2_branch2c_bn_rm: (64,) => s3.pathway1_res2.branch2.c_bn.running_mean: (64,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_9_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res9.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_19_branch2a_bn_riv: (32,) => s4.pathway1_res19.branch2.a_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_13_branch2b_bn_riv: (32,) => s4.pathway1_res13.branch2.b_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res5_0_branch2b_bn_riv: (64,) => s5.pathway1_res0.branch2.b_bn.running_var: (64,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_14_branch2c_bn_rm: (128,) => s4.pathway1_res14.branch2.c_bn.running_mean: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_6_branch2a_bn_riv: (256,) => s4.pathway0_res6.branch2.a_bn.running_var: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_20_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res20.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_22_branch2a_bn_s: (32,) => s4.pathway1_res22.branch2.a_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_riv: (32,) => s2.pathway1_res2.branch2.c_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_2_branch2b_w: (8, 8, 1, 3, 3) => s2.pathway1_res2.branch2.b.weight: (8, 8, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_5_branch2a_bn_rm: (256,) => s4.pathway0_res5.branch2.a_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_4_branch2b_bn_s: (32,) => s4.pathway1_res4.branch2.b_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_4_branch2b_bn_b: (32,) => s4.pathway1_res4.branch2.b_bn.bias: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_22_branch2a_bn_s: (256,) => s4.pathway0_res22.branch2.a_bn.weight: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_17_branch2a_bn_riv: (32,) => s4.pathway1_res17.branch2.a_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_18_branch2a_bn_s: (32,) => s4.pathway1_res18.branch2.a_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_22_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res22.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_18_branch2a_bn_b: (32,) => s4.pathway1_res18.branch2.a_bn.bias: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_2_branch2b_bn_rm: (8,) => s2.pathway1_res2.branch2.b_bn.running_mean: (8,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_15_branch2b_bn_riv: (32,) => s4.pathway1_res15.branch2.b_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_1_branch2a_bn_rm: (32,) => s4.pathway1_res1.branch2.a_bn.running_mean: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_13_branch2b_bn_rm: (256,) => s4.pathway0_res13.branch2.b_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_11_branch2b_bn_rm: (32,) => s4.pathway1_res11.branch2.b_bn.running_mean: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res3_3_branch2a_bn_b: (128,) => s3.pathway0_res3.branch2.a_bn.bias: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: nonlocal_conv4_6_bn_b: (1024,) => s4.pathway0_nonlocal6.bn.bias: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_18_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res18.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res3_1_branch2b_w: (16, 16, 1, 3, 3) => s3.pathway1_res1.branch2.b.weight: (16, 16, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: res3_3_branch2a_bn_s: (128,) => s3.pathway0_res3.branch2.a_bn.weight: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_5_branch2a_bn_riv: (256,) => s4.pathway0_res5.branch2.a_bn.running_var: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: nonlocal_conv4_6_bn_s: (1024,) => s4.pathway0_nonlocal6.bn.weight: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_22_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res22.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_0_branch1_bn_s: (32,) => s2.pathway1_res0.branch1_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_0_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res0.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_19_branch2b_bn_riv: (32,) => s4.pathway1_res19.branch2.b_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_6_branch2c_bn_s: (128,) => s4.pathway1_res6.branch2.c_bn.weight: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res2_0_branch1_bn_b: (32,) => s2.pathway1_res0.branch1_bn.bias: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_15_branch2b_bn_rm: (256,) => s4.pathway0_res15.branch2.b_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_13_branch2a_bn_riv: (32,) => s4.pathway1_res13.branch2.a_bn.running_var: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_6_branch2c_bn_b: (128,) => s4.pathway1_res6.branch2.c_bn.bias: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_0_branch2c_w: (2048, 512, 1, 1, 1) => s5.pathway0_res0.branch2.c.weight: (2048, 512, 1, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_5_branch2b_bn_s: (32,) => s4.pathway1_res5.branch2.b_bn.weight: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_3_branch2c_bn_rm: (128,) => s4.pathway1_res3.branch2.c_bn.running_mean: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_5_branch2b_bn_b: (32,) => s4.pathway1_res5.branch2.b_bn.bias: (32,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_17_branch2b_bn_rm: (256,) => s4.pathway0_res17.branch2.b_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_20_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res20.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:19][INFO] checkpoint.py:  252: res2_2_branch2c_bn_b: (256,) => s2.pathway0_res2.branch2.c_bn.bias: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_19_branch2a_bn_riv: (256,) => s4.pathway0_res19.branch2.a_bn.running_var: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_7_branch2a_bn_riv: (256,) => s4.pathway0_res7.branch2.a_bn.running_var: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res5_0_branch2a_w: (512, 1280, 3, 1, 1) => s5.pathway0_res0.branch2.a.weight: (512, 1280, 3, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: t_res4_20_branch2c_bn_riv: (128,) => s4.pathway1_res20.branch2.c_bn.running_var: (128,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_4_branch2a_bn_rm: (256,) => s4.pathway0_res4.branch2.a_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_14_branch2c_bn_rm: (1024,) => s4.pathway0_res14.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res3_1_branch2c_bn_b: (512,) => s3.pathway0_res1.branch2.c_bn.bias: (512,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_0_branch2a_w: (256, 640, 3, 1, 1) => s4.pathway0_res0.branch2.a.weight: (256, 640, 3, 1, 1)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_21_branch2c_bn_riv: (1024,) => s4.pathway0_res21.branch2.c_bn.running_var: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_16_branch2b_bn_rm: (256,) => s4.pathway0_res16.branch2.b_bn.running_mean: (256,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res4_0_branch2c_bn_b: (1024,) => s4.pathway0_res0.branch2.c_bn.bias: (1024,)
[10/25 14:59:19][INFO] checkpoint.py:  252: res3_3_branch2b_bn_s: (128,) => s3.pathway0_res3.branch2.b_bn.weight: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_0_branch2c_bn_s: (1024,) => s4.pathway0_res0.branch2.c_bn.weight: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_3_branch2b_bn_b: (128,) => s3.pathway0_res3.branch2.b_bn.bias: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch1_bn_riv: (256,) => s2.pathway0_res0.branch1_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_11_branch2b_bn_riv: (256,) => s4.pathway0_res11.branch2.b_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_0_branch2b_bn_rm: (512,) => s5.pathway0_res0.branch2.b_bn.running_mean: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_1_branch2c_bn_riv: (1024,) => s4.pathway0_res1.branch2.c_bn.running_var: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_16_branch2a_bn_riv: (32,) => s4.pathway1_res16.branch2.a_bn.running_var: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_20_branch2c_bn_riv: (1024,) => s4.pathway0_res20.branch2.c_bn.running_var: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res5_0_branch2a_bn_b: (64,) => s5.pathway1_res0.branch2.a_bn.bias: (64,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_8_branch2b_bn_rm: (32,) => s4.pathway1_res8.branch2.b_bn.running_mean: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res5_0_branch2a_bn_s: (64,) => s5.pathway1_res0.branch2.a_bn.weight: (64,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_2_branch2a_bn_rm: (64,) => s2.pathway0_res2.branch2.a_bn.running_mean: (64,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_18_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res18.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_0_branch2a_bn_rm: (512,) => s5.pathway0_res0.branch2.a_bn.running_mean: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_17_branch2a_bn_rm: (32,) => s4.pathway1_res17.branch2.a_bn.running_mean: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_12_branch2c_bn_rm: (1024,) => s4.pathway0_res12.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_0_branch2a_bn_b: (512,) => s5.pathway0_res0.branch2.a_bn.bias: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_18_branch2c_bn_riv: (1024,) => s4.pathway0_res18.branch2.c_bn.running_var: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_8_branch2b_bn_riv: (256,) => s4.pathway0_res8.branch2.b_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_0_branch2a_bn_s: (512,) => s5.pathway0_res0.branch2.a_bn.weight: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_13_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res13.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_15_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res15.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_7_branch2a_bn_s: (256,) => s4.pathway0_res7.branch2.a_bn.weight: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_22_branch2c_bn_rm: (1024,) => s4.pathway0_res22.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_15_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res15.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_21_branch2b_bn_rm: (32,) => s4.pathway1_res21.branch2.b_bn.running_mean: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_0_branch2b_bn_rm: (128,) => s3.pathway0_res0.branch2.b_bn.running_mean: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_6_branch2c_bn_rm: (1024,) => s4.pathway0_res6.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_22_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res22.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_2_branch2a_bn_b: (512,) => s5.pathway0_res2.branch2.a_bn.bias: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_3_branch2c_bn_riv: (512,) => s3.pathway0_res3.branch2.c_bn.running_var: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch1_bn_s: (256,) => s2.pathway0_res0.branch1_bn.weight: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res5_2_branch2a_bn_s: (512,) => s5.pathway0_res2.branch2.a_bn.weight: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch2c_bn_riv: (256,) => s2.pathway0_res0.branch2.c_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch1_bn_b: (256,) => s2.pathway0_res0.branch1_bn.bias: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_3_branch2a_bn_riv: (256,) => s4.pathway0_res3.branch2.a_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_2_branch2a_bn_rm: (256,) => s4.pathway0_res2.branch2.a_bn.running_mean: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_0_branch1_bn_b: (128,) => s4.pathway1_res0.branch1_bn.bias: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch2b_w: (64, 64, 1, 3, 3) => s2.pathway0_res0.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res5_0_branch2c_w: (256, 64, 1, 1, 1) => s5.pathway1_res0.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_1_branch2c_bn_rm: (1024,) => s4.pathway0_res1.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_1_branch2a_w: (32, 128, 3, 1, 1) => s4.pathway1_res1.branch2.a.weight: (32, 128, 3, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_13_branch2a_bn_s: (256,) => s4.pathway0_res13.branch2.a_bn.weight: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_0_branch1_bn_b: (512,) => s3.pathway0_res0.branch1_bn.bias: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_21_branch2b_bn_riv: (32,) => s4.pathway1_res21.branch2.b_bn.running_var: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_13_branch2a_bn_b: (256,) => s4.pathway0_res13.branch2.a_bn.bias: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_0_branch1_bn_s: (512,) => s3.pathway0_res0.branch1_bn.weight: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res5_0_branch2a_w: (64, 128, 3, 1, 1) => s5.pathway1_res0.branch2.a.weight: (64, 128, 3, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_20_branch2a_bn_rm: (32,) => s4.pathway1_res20.branch2.a_bn.running_mean: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_1_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res1.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res3_2_branch2c_bn_s: (64,) => s3.pathway1_res2.branch2.c_bn.weight: (64,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res3_2_branch2c_bn_b: (64,) => s3.pathway1_res2.branch2.c_bn.bias: (64,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_1_branch2c_bn_riv: (512,) => s3.pathway0_res1.branch2.c_bn.running_var: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_0_branch2b_bn_riv: (32,) => s4.pathway1_res0.branch2.b_bn.running_var: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_0_branch1_bn_s: (128,) => s4.pathway1_res0.branch1_bn.weight: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_0_branch2a_w: (64, 80, 1, 1, 1) => s2.pathway0_res0.branch2.a.weight: (64, 80, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_6_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res6.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: nonlocal_conv4_6_g_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal6.conv_g.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_14_branch2a_bn_riv: (256,) => s4.pathway0_res14.branch2.a_bn.running_var: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: nonlocal_conv4_6_g_b: (512,) => s4.pathway0_nonlocal6.conv_g.bias: (512,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_0_branch2c_w: (512, 128, 1, 1, 1) => s3.pathway0_res0.branch2.c.weight: (512, 128, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_8_branch2b_bn_b: (32,) => s4.pathway1_res8.branch2.b_bn.bias: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_8_branch2b_bn_s: (32,) => s4.pathway1_res8.branch2.b_bn.weight: (32,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_6_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res6.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_0_branch2a_w: (128, 320, 1, 1, 1) => s3.pathway0_res0.branch2.a.weight: (128, 320, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res_conv1_bn_b: (8,) => s1.pathway1_stem.bn.bias: (8,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_19_branch2a_bn_b: (256,) => s4.pathway0_res19.branch2.a_bn.bias: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_8_branch2c_bn_b: (128,) => s4.pathway1_res8.branch2.c_bn.bias: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res_conv1_bn_s: (8,) => s1.pathway1_stem.bn.weight: (8,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res3_1_branch2b_bn_rm: (128,) => s3.pathway0_res1.branch2.b_bn.running_mean: (128,)
[10/25 14:59:20][INFO] checkpoint.py:  252: res2_1_branch2c_w: (256, 64, 1, 1, 1) => s2.pathway0_res1.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:20][INFO] checkpoint.py:  252: res4_19_branch2a_bn_s: (256,) => s4.pathway0_res19.branch2.a_bn.weight: (256,)
[10/25 14:59:20][INFO] checkpoint.py:  252: t_res4_8_branch2c_bn_s: (128,) => s4.pathway1_res8.branch2.c_bn.weight: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_18_branch2a_bn_riv: (256,) => s4.pathway0_res18.branch2.a_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res3_3_branch2c_w: (512, 128, 1, 1, 1) => s3.pathway0_res3.branch2.c.weight: (512, 128, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_0_branch2b_bn_b: (64,) => s2.pathway0_res0.branch2.b_bn.bias: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res3_3_branch2a_w: (128, 512, 1, 1, 1) => s3.pathway0_res3.branch2.a.weight: (128, 512, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_0_branch2b_bn_s: (64,) => s2.pathway0_res0.branch2.b_bn.weight: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_5_branch2c_bn_rm: (128,) => s4.pathway1_res5.branch2.c_bn.running_mean: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_11_branch2a_bn_s: (32,) => s4.pathway1_res11.branch2.a_bn.weight: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_21_branch2a_bn_riv: (256,) => s4.pathway0_res21.branch2.a_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_13_branch2c_bn_rm: (1024,) => s4.pathway0_res13.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_rm: (32,) => s2.pathway1_res2.branch2.c_bn.running_mean: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_11_branch2a_bn_b: (32,) => s4.pathway1_res11.branch2.a_bn.bias: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_3_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res3.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_20_g_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal20.conv_g.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_16_branch2a_bn_s: (256,) => s4.pathway0_res16.branch2.a_bn.weight: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_6_branch2b_bn_rm: (32,) => s4.pathway1_res6.branch2.b_bn.running_mean: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_15_branch2a_bn_b: (256,) => s4.pathway0_res15.branch2.a_bn.bias: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_0_branch1_w: (256, 80, 1, 1, 1) => s2.pathway0_res0.branch1.weight: (256, 80, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_1_branch2c_bn_rm: (256,) => s2.pathway0_res1.branch2.c_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_16_branch2a_bn_b: (256,) => s4.pathway0_res16.branch2.a_bn.bias: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_15_branch2a_bn_s: (256,) => s4.pathway0_res15.branch2.a_bn.weight: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_22_branch2b_bn_rm: (32,) => s4.pathway1_res22.branch2.b_bn.running_mean: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_21_branch2a_bn_rm: (256,) => s4.pathway0_res21.branch2.a_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_17_branch2c_bn_rm: (1024,) => s4.pathway0_res17.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_5_branch2c_bn_rm: (1024,) => s4.pathway0_res5.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_12_branch2b_bn_b: (256,) => s4.pathway0_res12.branch2.b_bn.bias: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_9_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res9.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_12_branch2b_bn_s: (256,) => s4.pathway0_res12.branch2.b_bn.weight: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_5_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res5.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_14_branch2a_bn_b: (256,) => s4.pathway0_res14.branch2.a_bn.bias: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_11_branch2a_bn_rm: (256,) => s4.pathway0_res11.branch2.a_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_14_branch2a_bn_s: (256,) => s4.pathway0_res14.branch2.a_bn.weight: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_1_branch2a_w: (64, 256, 1, 1, 1) => s2.pathway0_res1.branch2.a.weight: (64, 256, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_0_branch1_w: (1024, 640, 1, 1, 1) => s4.pathway0_res0.branch1.weight: (1024, 640, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_8_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res8.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_2_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res2.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_18_branch2a_bn_rm: (32,) => s4.pathway1_res18.branch2.a_bn.running_mean: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_13_bn_rm: (1024,) => s4.pathway0_nonlocal13.bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_6_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res6.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_20_branch2b_bn_riv: (32,) => s4.pathway1_res20.branch2.b_bn.running_var: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res2_0_branch2b_w: (8, 8, 1, 3, 3) => s2.pathway1_res0.branch2.b.weight: (8, 8, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_10_branch2b_bn_riv: (256,) => s4.pathway0_res10.branch2.b_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_10_branch2b_bn_rm: (32,) => s4.pathway1_res10.branch2.b_bn.running_mean: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_9_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res9.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res_conv1_bn_rm: (64,) => s1.pathway0_stem.bn.running_mean: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_8_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res8.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_6_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res6.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_1_branch2c_bn_rm: (128,) => s4.pathway1_res1.branch2.c_bn.running_mean: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_17_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res17.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_conv1_w: (8, 3, 5, 7, 7) => s1.pathway1_stem.conv.weight: (8, 3, 5, 7, 7)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_0_branch1_bn_rm: (1024,) => s4.pathway0_res0.branch1_bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res5_0_branch1_bn_s: (2048,) => s5.pathway0_res0.branch1_bn.weight: (2048,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_1_branch2b_bn_b: (64,) => s2.pathway0_res1.branch2.b_bn.bias: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_0_branch2a_w: (32, 64, 3, 1, 1) => s4.pathway1_res0.branch2.a.weight: (32, 64, 3, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res5_0_branch1_bn_b: (2048,) => s5.pathway0_res0.branch1_bn.bias: (2048,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res2_1_branch2b_bn_s: (64,) => s2.pathway0_res1.branch2.b_bn.weight: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res2_2_branch2a_bn_riv: (8,) => s2.pathway1_res2.branch2.a_bn.running_var: (8,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res5_0_branch2c_bn_rm: (256,) => s5.pathway1_res0.branch2.c_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_22_branch2c_bn_riv: (128,) => s4.pathway1_res22.branch2.c_bn.running_var: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_13_theta_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal13.conv_theta.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_3_branch2b_bn_s: (32,) => s4.pathway1_res3.branch2.b_bn.weight: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_13_branch2c_bn_s: (128,) => s4.pathway1_res13.branch2.c_bn.weight: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_13_theta_b: (512,) => s4.pathway0_nonlocal13.conv_theta.bias: (512,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_3_branch2b_bn_b: (32,) => s4.pathway1_res3.branch2.b_bn.bias: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_20_branch2a_bn_riv: (32,) => s4.pathway1_res20.branch2.a_bn.running_var: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_13_branch2c_bn_b: (128,) => s4.pathway1_res13.branch2.c_bn.bias: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_4_branch2b_bn_riv: (32,) => s4.pathway1_res4.branch2.b_bn.running_var: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_21_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res21.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_18_branch2c_bn_riv: (128,) => s4.pathway1_res18.branch2.c_bn.running_var: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_15_branch2b_bn_b: (32,) => s4.pathway1_res15.branch2.b_bn.bias: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_16_branch2a_bn_riv: (256,) => s4.pathway0_res16.branch2.a_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res3_3_branch2a_w: (16, 64, 3, 1, 1) => s3.pathway1_res3.branch2.a.weight: (16, 64, 3, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res3_1_branch2b_bn_riv: (16,) => s3.pathway1_res1.branch2.b_bn.running_var: (16,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_15_branch2b_bn_s: (32,) => s4.pathway1_res15.branch2.b_bn.weight: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_16_branch2c_bn_rm: (1024,) => s4.pathway0_res16.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_subsample_w: (64, 32, 5, 1, 1) => s2_fuse.conv_f2s.weight: (64, 32, 5, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_5_branch2a_bn_s: (256,) => s4.pathway0_res5.branch2.a_bn.weight: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_19_branch2a_bn_rm: (256,) => s4.pathway0_res19.branch2.a_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_5_branch2a_bn_b: (256,) => s4.pathway0_res5.branch2.a_bn.bias: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res3_3_branch2c_w: (64, 16, 1, 1, 1) => s3.pathway1_res3.branch2.c.weight: (64, 16, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res_conv1_bn_b: (64,) => s1.pathway0_stem.bn.bias: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res_conv1_bn_s: (64,) => s1.pathway0_stem.bn.weight: (64,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res3_3_branch2b_bn_riv: (16,) => s3.pathway1_res3.branch2.b_bn.running_var: (16,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_20_bn_b: (1024,) => s4.pathway0_nonlocal20.bn.bias: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_2_branch2a_bn_riv: (32,) => s4.pathway1_res2.branch2.a_bn.running_var: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res3_1_branch2c_bn_s: (512,) => s3.pathway0_res1.branch2.c_bn.weight: (512,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_20_bn_s: (1024,) => s4.pathway0_nonlocal20.bn.weight: (1024,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_7_branch2a_bn_rm: (256,) => s4.pathway0_res7.branch2.a_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_8_branch2c_bn_riv: (128,) => s4.pathway1_res8.branch2.c_bn.running_var: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res5_0_branch2c_bn_riv: (2048,) => s5.pathway0_res0.branch2.c_bn.running_var: (2048,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_11_branch2b_bn_b: (32,) => s4.pathway1_res11.branch2.b_bn.bias: (32,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res5_2_branch2c_bn_riv: (256,) => s5.pathway1_res2.branch2.c_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_2_branch2a_w: (32, 128, 3, 1, 1) => s4.pathway1_res2.branch2.a.weight: (32, 128, 3, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_16_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res16.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_19_branch2b_bn_rm: (256,) => s4.pathway0_res19.branch2.b_bn.running_mean: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: res4_17_branch2a_bn_riv: (256,) => s4.pathway0_res17.branch2.a_bn.running_var: (256,)
[10/25 14:59:21][INFO] checkpoint.py:  252: nonlocal_conv4_13_out_w: (1024, 512, 1, 1, 1) => s4.pathway0_nonlocal13.conv_out.weight: (1024, 512, 1, 1, 1)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_11_branch2c_bn_rm: (128,) => s4.pathway1_res11.branch2.c_bn.running_mean: (128,)
[10/25 14:59:21][INFO] checkpoint.py:  252: t_res4_19_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res19.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_11_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res11.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2b_bn_rm: (256,) => s4.pathway0_res10.branch2.b_bn.running_mean: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_2_branch2a_bn_s: (128,) => s3.pathway0_res2.branch2.a_bn.weight: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_22_branch2c_bn_riv: (1024,) => s4.pathway0_res22.branch2.c_bn.running_var: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_2_branch2a_bn_b: (128,) => s3.pathway0_res2.branch2.a_bn.bias: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_1_branch2b_bn_riv: (256,) => s4.pathway0_res1.branch2.b_bn.running_var: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_4_branch2b_bn_b: (256,) => s4.pathway0_res4.branch2.b_bn.bias: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2b_bn_s: (256,) => s4.pathway0_res10.branch2.b_bn.weight: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_4_branch2b_bn_s: (256,) => s4.pathway0_res4.branch2.b_bn.weight: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2b_bn_b: (256,) => s4.pathway0_res10.branch2.b_bn.bias: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_0_branch2a_bn_rm: (64,) => s2.pathway0_res0.branch2.a_bn.running_mean: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res3_1_branch2c_bn_riv: (64,) => s3.pathway1_res1.branch2.c_bn.running_var: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_22_branch2a_bn_riv: (32,) => s4.pathway1_res22.branch2.a_bn.running_var: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_7_branch2a_bn_s: (32,) => s4.pathway1_res7.branch2.a_bn.weight: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_5_branch2c_bn_riv: (1024,) => s4.pathway0_res5.branch2.c_bn.running_var: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_1_branch2a_bn_rm: (64,) => s2.pathway0_res1.branch2.a_bn.running_mean: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_3_branch2a_bn_riv: (32,) => s4.pathway1_res3.branch2.a_bn.running_var: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2c_bn_s: (1024,) => s4.pathway0_res7.branch2.c_bn.weight: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_7_branch2a_bn_b: (32,) => s4.pathway1_res7.branch2.a_bn.bias: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2c_bn_b: (1024,) => s4.pathway0_res7.branch2.c_bn.bias: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2b_bn_s: (256,) => s4.pathway0_res7.branch2.b_bn.weight: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_13_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res13.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2b_bn_b: (256,) => s4.pathway0_res7.branch2.b_bn.bias: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_1_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res1.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res5_2_branch2b_w: (64, 64, 1, 3, 3) => s5.pathway1_res2.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_8_branch2a_bn_rm: (256,) => s4.pathway0_res8.branch2.a_bn.running_mean: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res5_1_branch2a_w: (512, 2048, 3, 1, 1) => s5.pathway0_res1.branch2.a.weight: (512, 2048, 3, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res7.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res5_2_branch2b_bn_rm: (64,) => s5.pathway1_res2.branch2.b_bn.running_mean: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_7_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res7.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res2_1_branch2c_bn_b: (32,) => s2.pathway1_res1.branch2.c_bn.bias: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_12_branch2a_bn_riv: (32,) => s4.pathway1_res12.branch2.a_bn.running_var: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res3_2_branch2c_bn_riv: (64,) => s3.pathway1_res2.branch2.c_bn.running_var: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res5_1_branch2b_bn_rm: (512,) => s5.pathway0_res1.branch2.b_bn.running_mean: (512,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2c_bn_s: (1024,) => s4.pathway0_res10.branch2.c_bn.weight: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2c_bn_b: (1024,) => s4.pathway0_res10.branch2.c_bn.bias: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res2_1_branch2c_w: (32, 8, 1, 1, 1) => s2.pathway1_res1.branch2.c.weight: (32, 8, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_2_branch2c_bn_riv: (256,) => s2.pathway0_res2.branch2.c_bn.running_var: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_3_branch2c_bn_rm: (512,) => s3.pathway0_res3.branch2.c_bn.running_mean: (512,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_3_branch2a_bn_riv: (128,) => s3.pathway0_res3.branch2.a_bn.running_var: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2c_bn_riv: (1024,) => s4.pathway0_res10.branch2.c_bn.running_var: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_16_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res16.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_2_branch2a_w: (64, 256, 1, 1, 1) => s2.pathway0_res2.branch2.a.weight: (64, 256, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_18_branch2b_bn_rm: (256,) => s4.pathway0_res18.branch2.b_bn.running_mean: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_0_branch2b_bn_riv: (64,) => s2.pathway0_res0.branch2.b_bn.running_var: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res5_0_branch1_bn_riv: (2048,) => s5.pathway0_res0.branch1_bn.running_var: (2048,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_10_branch2b_bn_riv: (32,) => s4.pathway1_res10.branch2.b_bn.running_var: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_3_branch2b_bn_rm: (32,) => s4.pathway1_res3.branch2.b_bn.running_mean: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_21_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res21.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_13_branch2c_bn_b: (1024,) => s4.pathway0_res13.branch2.c_bn.bias: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_22_branch2b_bn_rm: (256,) => s4.pathway0_res22.branch2.b_bn.running_mean: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_2_branch2b_bn_b: (128,) => s3.pathway0_res2.branch2.b_bn.bias: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_10_branch2a_bn_rm: (256,) => s4.pathway0_res10.branch2.a_bn.running_mean: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_13_branch2c_bn_s: (1024,) => s4.pathway0_res13.branch2.c_bn.weight: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res3_2_branch2b_bn_s: (128,) => s3.pathway0_res2.branch2.b_bn.weight: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_15_branch2c_bn_riv: (1024,) => s4.pathway0_res15.branch2.c_bn.running_var: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_6_branch2a_bn_b: (256,) => s4.pathway0_res6.branch2.a_bn.bias: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res5_1_branch2c_bn_s: (2048,) => s5.pathway0_res1.branch2.c_bn.weight: (2048,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_16_branch2c_bn_s: (128,) => s4.pathway1_res16.branch2.c_bn.weight: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_17_branch2b_bn_s: (32,) => s4.pathway1_res17.branch2.b_bn.weight: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_6_branch2a_bn_s: (256,) => s4.pathway0_res6.branch2.a_bn.weight: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res5_1_branch2c_bn_b: (2048,) => s5.pathway0_res1.branch2.c_bn.bias: (2048,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_16_branch2c_bn_b: (128,) => s4.pathway1_res16.branch2.c_bn.bias: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_17_branch2b_bn_b: (32,) => s4.pathway1_res17.branch2.b_bn.bias: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res2_1_branch2b_bn_rm: (64,) => s2.pathway0_res1.branch2.b_bn.running_mean: (64,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res3_3_branch2a_bn_s: (16,) => s3.pathway1_res3.branch2.a_bn.weight: (16,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_4_branch2c_bn_riv: (128,) => s4.pathway1_res4.branch2.c_bn.running_var: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res3_3_branch2a_bn_b: (16,) => s3.pathway1_res3.branch2.a_bn.bias: (16,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res2_1_branch2b_bn_riv: (8,) => s2.pathway1_res1.branch2.b_bn.running_var: (8,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_4_branch2a_bn_s: (256,) => s4.pathway0_res4.branch2.a_bn.weight: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_0_branch2c_bn_rm: (128,) => s4.pathway1_res0.branch2.c_bn.running_mean: (128,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_4_branch2a_bn_b: (256,) => s4.pathway0_res4.branch2.a_bn.bias: (256,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_1_branch2b_bn_s: (32,) => s4.pathway1_res1.branch2.b_bn.weight: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_12_branch2a_bn_b: (32,) => s4.pathway1_res12.branch2.a_bn.bias: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_0_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res0.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_12_branch2a_bn_s: (32,) => s4.pathway1_res12.branch2.a_bn.weight: (32,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_14_branch2c_bn_s: (1024,) => s4.pathway0_res14.branch2.c_bn.weight: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: t_res4_20_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res20.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_2_branch2c_bn_rm: (1024,) => s4.pathway0_res2.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:22][INFO] checkpoint.py:  252: res4_14_branch2c_bn_b: (1024,) => s4.pathway0_res14.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_19_branch2b_bn_rm: (32,) => s4.pathway1_res19.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_7_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res7.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:23][INFO] checkpoint.py:  252: res5_0_branch2b_bn_riv: (512,) => s5.pathway0_res0.branch2.b_bn.running_var: (512,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res3_1_branch2a_bn_b: (128,) => s3.pathway0_res1.branch2.a_bn.bias: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_21_branch2a_bn_riv: (32,) => s4.pathway1_res21.branch2.a_bn.running_var: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_9_branch2b_bn_rm: (32,) => s4.pathway1_res9.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res3_1_branch2a_bn_s: (128,) => s3.pathway0_res1.branch2.a_bn.weight: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_15_branch2a_bn_riv: (32,) => s4.pathway1_res15.branch2.a_bn.running_var: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_0_branch2a_bn_riv: (256,) => s4.pathway0_res0.branch2.a_bn.running_var: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_3_branch2a_bn_rm: (16,) => s3.pathway1_res3.branch2.a_bn.running_mean: (16,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res5_2_branch2a_bn_riv: (512,) => s5.pathway0_res2.branch2.a_bn.running_var: (512,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_4_branch2a_bn_s: (32,) => s4.pathway1_res4.branch2.a_bn.weight: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_5_branch2a_w: (256, 1024, 3, 1, 1) => s4.pathway0_res5.branch2.a.weight: (256, 1024, 3, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_7_branch2b_bn_rm: (256,) => s4.pathway0_res7.branch2.b_bn.running_mean: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_18_branch2c_bn_rm: (1024,) => s4.pathway0_res18.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_13_branch2c_bn_riv: (128,) => s4.pathway1_res13.branch2.c_bn.running_var: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_12_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res12.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_18_branch2a_bn_s: (256,) => s4.pathway0_res18.branch2.a_bn.weight: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_18_branch2a_bn_b: (256,) => s4.pathway0_res18.branch2.a_bn.bias: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_8_branch2b_bn_riv: (32,) => s4.pathway1_res8.branch2.b_bn.running_var: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res5_2_branch2a_bn_riv: (64,) => s5.pathway1_res2.branch2.a_bn.running_var: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_s: (64,) => s3.pathway1_res3.branch2.c_bn.weight: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_7_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res7.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_14_branch2b_bn_b: (32,) => s4.pathway1_res14.branch2.b_bn.bias: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res2_0_branch2a_bn_riv: (8,) => s2.pathway1_res0.branch2.a_bn.running_var: (8,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_22_branch2b_bn_riv: (32,) => s4.pathway1_res22.branch2.b_bn.running_var: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_16_branch2b_bn_rm: (32,) => s4.pathway1_res16.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_7_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res7.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_7_branch2b_bn_rm: (32,) => s4.pathway1_res7.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_subsample_bn_s: (64,) => s2_fuse.bn.weight: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_subsample_bn_b: (64,) => s2_fuse.bn.bias: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_17_branch2a_bn_s: (32,) => s4.pathway1_res17.branch2.a_bn.weight: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_14_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res14.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_14_branch2a_bn_rm: (32,) => s4.pathway1_res14.branch2.a_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_15_branch2c_bn_rm: (128,) => s4.pathway1_res15.branch2.c_bn.running_mean: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_5_branch2c_bn_b: (1024,) => s4.pathway0_res5.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_subsample_bn_rm: (64,) => s2_fuse.bn.running_mean: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_22_branch2c_bn_b: (1024,) => s4.pathway0_res22.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_5_branch2c_bn_s: (1024,) => s4.pathway0_res5.branch2.c_bn.weight: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_22_branch2c_bn_s: (1024,) => s4.pathway0_res22.branch2.c_bn.weight: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res5_2_branch2b_bn_b: (64,) => s5.pathway1_res2.branch2.b_bn.bias: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_15_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res15.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_14_branch2b_bn_rm: (32,) => s4.pathway1_res14.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_9_branch2a_bn_s: (256,) => s4.pathway0_res9.branch2.a_bn.weight: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res5_2_branch2b_bn_s: (64,) => s5.pathway1_res2.branch2.b_bn.weight: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_9_branch2a_bn_b: (256,) => s4.pathway0_res9.branch2.a_bn.bias: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res_conv1_bn_riv: (8,) => s1.pathway1_stem.bn.running_var: (8,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_0_branch1_w: (64, 32, 1, 1, 1) => s3.pathway1_res0.branch1.weight: (64, 32, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: conv1_w: (64, 3, 1, 7, 7) => s1.pathway0_stem.conv.weight: (64, 3, 1, 7, 7)
[10/25 14:59:23][INFO] checkpoint.py:  252: res3_2_branch2c_bn_rm: (512,) => s3.pathway0_res2.branch2.c_bn.running_mean: (512,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_11_branch2c_bn_riv: (128,) => s4.pathway1_res11.branch2.c_bn.running_var: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_4_branch2b_bn_riv: (256,) => s4.pathway0_res4.branch2.b_bn.running_var: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_0_branch2a_bn_riv: (16,) => s3.pathway1_res0.branch2.a_bn.running_var: (16,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_5_branch2a_w: (32, 128, 3, 1, 1) => s4.pathway1_res5.branch2.a.weight: (32, 128, 3, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res2_0_branch2b_bn_rm: (8,) => s2.pathway1_res0.branch2.b_bn.running_mean: (8,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_pool1_subsample_bn_riv: (16,) => s1_fuse.bn.running_var: (16,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_9_branch2c_bn_riv: (128,) => s4.pathway1_res9.branch2.c_bn.running_var: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_0_branch2c_bn_s: (128,) => s4.pathway1_res0.branch2.c_bn.weight: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_10_branch2c_bn_rm: (128,) => s4.pathway1_res10.branch2.c_bn.running_mean: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res5_2_branch2a_bn_rm: (512,) => s5.pathway0_res2.branch2.a_bn.running_mean: (512,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_4_branch2c_bn_s: (128,) => s4.pathway1_res4.branch2.c_bn.weight: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_19_branch2c_bn_s: (1024,) => s4.pathway0_res19.branch2.c_bn.weight: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_4_branch2c_bn_b: (128,) => s4.pathway1_res4.branch2.c_bn.bias: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_19_branch2c_bn_b: (1024,) => s4.pathway0_res19.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_21_branch2b_bn_riv: (256,) => s4.pathway0_res21.branch2.b_bn.running_var: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_12_branch2b_bn_rm: (32,) => s4.pathway1_res12.branch2.b_bn.running_mean: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res2_0_branch1_bn_rm: (256,) => s2.pathway0_res0.branch1_bn.running_mean: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_11_branch2c_bn_s: (1024,) => s4.pathway0_res11.branch2.c_bn.weight: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_3_branch2c_bn_s: (1024,) => s4.pathway0_res3.branch2.c_bn.weight: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res5_0_branch2a_bn_riv: (64,) => s5.pathway1_res0.branch2.a_bn.running_var: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_11_branch2c_bn_b: (1024,) => s4.pathway0_res11.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res5_2_branch2b_bn_b: (512,) => s5.pathway0_res2.branch2.b_bn.bias: (512,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_3_branch2c_bn_b: (1024,) => s4.pathway0_res3.branch2.c_bn.bias: (1024,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_subsample_bn_riv: (128,) => s3_fuse.bn.running_var: (128,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_12_branch2b_bn_s: (32,) => s4.pathway1_res12.branch2.b_bn.weight: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_0_branch1_bn_b: (64,) => s3.pathway1_res0.branch1_bn.bias: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_10_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res10.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res4_12_branch2b_bn_b: (32,) => s4.pathway1_res12.branch2.b_bn.bias: (32,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_0_branch1_bn_s: (64,) => s3.pathway1_res0.branch1_bn.weight: (64,)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_8_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res8.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_11_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res11.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_8_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res8.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:23][INFO] checkpoint.py:  252: res4_3_branch2a_bn_rm: (256,) => s4.pathway0_res3.branch2.a_bn.running_mean: (256,)
[10/25 14:59:23][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_riv: (64,) => s3.pathway1_res3.branch2.c_bn.running_var: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_2_branch2a_bn_rm: (64,) => s5.pathway1_res2.branch2.a_bn.running_mean: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_9_branch2b_bn_b: (256,) => s4.pathway0_res9.branch2.b_bn.bias: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_1_branch2a_bn_s: (32,) => s4.pathway1_res1.branch2.a_bn.weight: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_1_branch2a_bn_riv: (64,) => s5.pathway1_res1.branch2.a_bn.running_var: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_9_branch2b_bn_s: (256,) => s4.pathway0_res9.branch2.b_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_0_branch2c_bn_b: (512,) => s3.pathway0_res0.branch2.c_bn.bias: (512,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_0_branch2a_bn_rm: (128,) => s3.pathway0_res0.branch2.a_bn.running_mean: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res2_1_branch2b_bn_s: (8,) => s2.pathway1_res1.branch2.b_bn.weight: (8,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res5_0_branch2c_bn_s: (2048,) => s5.pathway0_res0.branch2.c_bn.weight: (2048,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_1_branch2a_bn_b: (64,) => s5.pathway1_res1.branch2.a_bn.bias: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res5_2_branch2c_w: (2048, 512, 1, 1, 1) => s5.pathway0_res2.branch2.c.weight: (2048, 512, 1, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_11_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res11.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_0_branch2c_bn_s: (512,) => s3.pathway0_res0.branch2.c_bn.weight: (512,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res5_0_branch2c_bn_b: (2048,) => s5.pathway0_res0.branch2.c_bn.bias: (2048,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_1_branch2a_bn_s: (64,) => s5.pathway1_res1.branch2.a_bn.weight: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_10_branch2a_bn_s: (256,) => s4.pathway0_res10.branch2.a_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_0_branch2b_bn_riv: (256,) => s4.pathway0_res0.branch2.b_bn.running_var: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_0_branch2b_w: (16, 16, 1, 3, 3) => s3.pathway1_res0.branch2.b.weight: (16, 16, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res2_0_branch2a_bn_s: (64,) => s2.pathway0_res0.branch2.a_bn.weight: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_1_branch2c_bn_rm: (64,) => s3.pathway1_res1.branch2.c_bn.running_mean: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_19_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res19.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_2_branch2a_w: (256, 1024, 3, 1, 1) => s4.pathway0_res2.branch2.a.weight: (256, 1024, 3, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_13_branch2b_bn_s: (256,) => s4.pathway0_res13.branch2.b_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res2_0_branch2a_bn_b: (64,) => s2.pathway0_res0.branch2.a_bn.bias: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_2_branch2b_w: (16, 16, 1, 3, 3) => s3.pathway1_res2.branch2.b.weight: (16, 16, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_2_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res2.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_18_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res18.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_2_branch2c_bn_s: (512,) => s3.pathway0_res2.branch2.c_bn.weight: (512,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_1_branch2a_bn_rm: (128,) => s3.pathway0_res1.branch2.a_bn.running_mean: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_9_branch2b_bn_b: (32,) => s4.pathway1_res9.branch2.b_bn.bias: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_21_branch2a_bn_b: (256,) => s4.pathway0_res21.branch2.a_bn.bias: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_1_branch2a_bn_riv: (32,) => s4.pathway1_res1.branch2.a_bn.running_var: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_9_branch2b_bn_s: (32,) => s4.pathway1_res9.branch2.b_bn.weight: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_21_branch2a_bn_s: (256,) => s4.pathway0_res21.branch2.a_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_9_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res9.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_7_branch2c_bn_rm: (1024,) => s4.pathway0_res7.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_17_branch2c_bn_rm: (128,) => s4.pathway1_res17.branch2.c_bn.running_mean: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_0_branch2c_bn_s: (256,) => s5.pathway1_res0.branch2.c_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_20_branch2c_bn_rm: (1024,) => s4.pathway0_res20.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_22_branch2b_bn_b: (32,) => s4.pathway1_res22.branch2.b_bn.bias: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_6_branch2c_bn_riv: (128,) => s4.pathway1_res6.branch2.c_bn.running_var: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res5_0_branch2c_bn_b: (256,) => s5.pathway1_res0.branch2.c_bn.bias: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_22_branch2b_bn_s: (32,) => s4.pathway1_res22.branch2.b_bn.weight: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_0_branch1_bn_riv: (64,) => s3.pathway1_res0.branch1_bn.running_var: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_18_branch2b_bn_rm: (32,) => s4.pathway1_res18.branch2.b_bn.running_mean: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res_conv1_bn_riv: (64,) => s1.pathway0_stem.bn.running_var: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_18_branch2a_bn_riv: (32,) => s4.pathway1_res18.branch2.a_bn.running_var: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_4_branch2a_bn_riv: (256,) => s4.pathway0_res4.branch2.a_bn.running_var: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_17_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res17.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_20_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res20.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_3_branch2b_bn_s: (16,) => s3.pathway1_res3.branch2.b_bn.weight: (16,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_2_branch2a_bn_riv: (16,) => s3.pathway1_res2.branch2.a_bn.running_var: (16,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_3_branch2b_bn_b: (16,) => s3.pathway1_res3.branch2.b_bn.bias: (16,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_5_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res5.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res2_2_branch2b_bn_s: (64,) => s2.pathway0_res2.branch2.b_bn.weight: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_2_branch2b_bn_rm: (128,) => s3.pathway0_res2.branch2.b_bn.running_mean: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res2_2_branch2b_bn_b: (64,) => s2.pathway0_res2.branch2.b_bn.bias: (64,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res2_2_branch2c_bn_s: (256,) => s2.pathway0_res2.branch2.c_bn.weight: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: nonlocal_conv4_20_theta_b: (512,) => s4.pathway0_nonlocal20.conv_theta.bias: (512,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_11_branch2c_bn_b: (128,) => s4.pathway1_res11.branch2.c_bn.bias: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: nonlocal_conv4_13_g_b: (512,) => s4.pathway0_nonlocal13.conv_g.bias: (512,)
[10/25 14:59:24][INFO] checkpoint.py:  252: nonlocal_conv4_13_g_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal13.conv_g.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_11_branch2c_bn_s: (128,) => s4.pathway1_res11.branch2.c_bn.weight: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_13_branch2c_bn_rm: (128,) => s4.pathway1_res13.branch2.c_bn.running_mean: (128,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res3_1_branch2a_bn_rm: (16,) => s3.pathway1_res1.branch2.a_bn.running_mean: (16,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_21_branch2a_bn_rm: (32,) => s4.pathway1_res21.branch2.a_bn.running_mean: (32,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res4_3_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res3.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_7_branch2a_bn_b: (256,) => s4.pathway0_res7.branch2.a_bn.bias: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res4_1_branch2a_bn_rm: (256,) => s4.pathway0_res1.branch2.a_bn.running_mean: (256,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_1_branch2a_w: (128, 512, 1, 1, 1) => s3.pathway0_res1.branch2.a.weight: (128, 512, 1, 1, 1)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_res2_2_branch2b_bn_riv: (8,) => s2.pathway1_res2.branch2.b_bn.running_var: (8,)
[10/25 14:59:24][INFO] checkpoint.py:  252: t_pool1_subsample_bn_s: (16,) => s1_fuse.bn.weight: (16,)
[10/25 14:59:24][INFO] checkpoint.py:  252: res3_1_branch2c_w: (512, 128, 1, 1, 1) => s3.pathway0_res1.branch2.c.weight: (512, 128, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_pool1_subsample_bn_b: (16,) => s1_fuse.bn.bias: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_3_branch2c_bn_riv: (128,) => s4.pathway1_res3.branch2.c_bn.running_var: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_16_branch2c_bn_riv: (128,) => s4.pathway1_res16.branch2.c_bn.running_var: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: pred_b: (80,) => head.projection.bias: (80,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_4_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res4.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_1_branch2b_bn_riv: (64,) => s2.pathway0_res1.branch2.b_bn.running_var: (64,)
[10/25 14:59:25][INFO] checkpoint.py:  252: pred_w: (80, 2304) => head.projection.weight: (80, 2304)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_0_branch2a_bn_s: (8,) => s2.pathway1_res0.branch2.a_bn.weight: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_5_branch2a_bn_s: (32,) => s4.pathway1_res5.branch2.a_bn.weight: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_8_branch2a_bn_s: (32,) => s4.pathway1_res8.branch2.a_bn.weight: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_17_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res17.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_5_branch2a_bn_riv: (32,) => s4.pathway1_res5.branch2.a_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_0_branch2a_bn_b: (8,) => s2.pathway1_res0.branch2.a_bn.bias: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_5_branch2a_bn_b: (32,) => s4.pathway1_res5.branch2.a_bn.bias: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_8_branch2a_bn_b: (32,) => s4.pathway1_res8.branch2.a_bn.bias: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_12_branch2a_bn_riv: (256,) => s4.pathway0_res12.branch2.a_bn.running_var: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_14_branch2b_bn_riv: (32,) => s4.pathway1_res14.branch2.b_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_12_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res12.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_16_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res16.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res3_0_branch2a_bn_riv: (128,) => s3.pathway0_res0.branch2.a_bn.running_var: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_4_branch2b_bn_rm: (256,) => s4.pathway0_res4.branch2.b_bn.running_mean: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_12_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res12.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res3_2_branch2a_w: (128, 512, 1, 1, 1) => s3.pathway0_res2.branch2.a.weight: (128, 512, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_2_branch2b_bn_s: (16,) => s3.pathway1_res2.branch2.b_bn.weight: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: nonlocal_conv4_20_bn_rm: (1024,) => s4.pathway0_nonlocal20.bn.running_mean: (1024,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res3_2_branch2c_w: (512, 128, 1, 1, 1) => s3.pathway0_res2.branch2.c.weight: (512, 128, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_2_branch2a_bn_riv: (64,) => s2.pathway0_res2.branch2.a_bn.running_var: (64,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_2_branch2b_bn_b: (16,) => s3.pathway1_res2.branch2.b_bn.bias: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_1_branch2a_bn_b: (16,) => s3.pathway1_res1.branch2.a_bn.bias: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res5_0_branch2c_bn_riv: (256,) => s5.pathway1_res0.branch2.c_bn.running_var: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_2_branch2a_bn_b: (64,) => s2.pathway0_res2.branch2.a_bn.bias: (64,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_1_branch2a_bn_s: (16,) => s3.pathway1_res1.branch2.a_bn.weight: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_2_branch2a_bn_s: (64,) => s2.pathway0_res2.branch2.a_bn.weight: (64,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_22_branch2a_bn_rm: (256,) => s4.pathway0_res22.branch2.a_bn.running_mean: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res5_1_branch2a_bn_rm: (512,) => s5.pathway0_res1.branch2.a_bn.running_mean: (512,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_8_branch2c_bn_rm: (1024,) => s4.pathway0_res8.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_1_branch2b_bn_b: (8,) => s2.pathway1_res1.branch2.b_bn.bias: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_18_branch2b_bn_b: (256,) => s4.pathway0_res18.branch2.b_bn.bias: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res5_1_branch2a_bn_riv: (512,) => s5.pathway0_res1.branch2.a_bn.running_var: (512,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_18_branch2b_bn_s: (256,) => s4.pathway0_res18.branch2.b_bn.weight: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_2_branch2b_bn_riv: (64,) => s2.pathway0_res2.branch2.b_bn.running_var: (64,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res5_0_branch1_bn_rm: (2048,) => s5.pathway0_res0.branch1_bn.running_mean: (2048,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_6_branch2b_bn_riv: (32,) => s4.pathway1_res6.branch2.b_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_subsample_bn_s: (128,) => s3_fuse.bn.weight: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_9_branch2b_bn_rm: (256,) => s4.pathway0_res9.branch2.b_bn.running_mean: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_subsample_bn_b: (128,) => s3_fuse.bn.bias: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: nonlocal_conv4_6_theta_b: (512,) => s4.pathway0_nonlocal6.conv_theta.bias: (512,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_4_branch2a_bn_riv: (32,) => s4.pathway1_res4.branch2.a_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_19_branch2c_bn_s: (128,) => s4.pathway1_res19.branch2.c_bn.weight: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_0_branch2c_bn_riv: (32,) => s2.pathway1_res0.branch2.c_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_14_branch2a_bn_riv: (32,) => s4.pathway1_res14.branch2.a_bn.running_var: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_s: (32,) => s2.pathway1_res2.branch2.c_bn.weight: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_19_branch2c_bn_b: (128,) => s4.pathway1_res19.branch2.c_bn.bias: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: nonlocal_conv4_6_theta_w: (512, 1024, 1, 1, 1) => s4.pathway0_nonlocal6.conv_theta.weight: (512, 1024, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: res2_1_branch2c_bn_riv: (256,) => s2.pathway0_res1.branch2.c_bn.running_var: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_b: (32,) => s2.pathway1_res2.branch2.c_bn.bias: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_9_branch2c_bn_rm: (1024,) => s4.pathway0_res9.branch2.c_bn.running_mean: (1024,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_2_branch2b_bn_s: (8,) => s2.pathway1_res2.branch2.b_bn.weight: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res2_2_branch2b_bn_b: (8,) => s2.pathway1_res2.branch2.b_bn.bias: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_8_branch2a_bn_riv: (256,) => s4.pathway0_res8.branch2.a_bn.running_var: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_21_branch2c_bn_b: (128,) => s4.pathway1_res21.branch2.c_bn.bias: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_16_branch2c_bn_riv: (1024,) => s4.pathway0_res16.branch2.c_bn.running_var: (1024,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_0_branch1_bn_riv: (128,) => s4.pathway1_res0.branch1_bn.running_var: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_21_branch2c_bn_s: (128,) => s4.pathway1_res21.branch2.c_bn.weight: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_3_branch2a_bn_riv: (16,) => s3.pathway1_res3.branch2.a_bn.running_var: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_8_branch2c_bn_riv: (1024,) => s4.pathway0_res8.branch2.c_bn.running_var: (1024,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_4_branch2a_w: (256, 1024, 3, 1, 1) => s4.pathway0_res4.branch2.a.weight: (256, 1024, 3, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_3_branch2a_bn_rm: (32,) => s4.pathway1_res3.branch2.a_bn.running_mean: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res5_0_branch1_bn_rm: (256,) => s5.pathway1_res0.branch1_bn.running_mean: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_4_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res4.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_17_branch2c_bn_s: (128,) => s4.pathway1_res17.branch2.c_bn.weight: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_0_branch2b_bn_riv: (16,) => s3.pathway1_res0.branch2.b_bn.running_var: (16,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res_conv1_bn_rm: (8,) => s1.pathway1_stem.bn.running_mean: (8,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_17_branch2c_bn_b: (128,) => s4.pathway1_res17.branch2.c_bn.bias: (128,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res3_1_branch2c_w: (64, 16, 1, 1, 1) => s3.pathway1_res1.branch2.c.weight: (64, 16, 1, 1, 1)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_13_branch2b_bn_s: (32,) => s4.pathway1_res13.branch2.b_bn.weight: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_18_branch2b_bn_b: (32,) => s4.pathway1_res18.branch2.b_bn.bias: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_13_branch2b_bn_b: (32,) => s4.pathway1_res13.branch2.b_bn.bias: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: t_res4_18_branch2b_bn_s: (32,) => s4.pathway1_res18.branch2.b_bn.weight: (32,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_11_branch2a_bn_b: (256,) => s4.pathway0_res11.branch2.a_bn.bias: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_11_branch2a_bn_s: (256,) => s4.pathway0_res11.branch2.a_bn.weight: (256,)
[10/25 14:59:25][INFO] checkpoint.py:  252: res4_20_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res20.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_9_branch2c_bn_b: (1024,) => s4.pathway0_res9.branch2.c_bn.bias: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_18_branch2c_bn_rm: (128,) => s4.pathway1_res18.branch2.c_bn.running_mean: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2c_bn_b: (64,) => s3.pathway1_res0.branch2.c_bn.bias: (64,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_13_branch2c_bn_riv: (1024,) => s4.pathway0_res13.branch2.c_bn.running_var: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res5_0_branch2b_w: (512, 512, 1, 3, 3) => s5.pathway0_res0.branch2.b.weight: (512, 512, 1, 3, 3)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_9_branch2c_bn_s: (1024,) => s4.pathway0_res9.branch2.c_bn.weight: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2c_bn_s: (64,) => s3.pathway1_res0.branch2.c_bn.weight: (64,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_0_branch2a_bn_riv: (32,) => s4.pathway1_res0.branch2.a_bn.running_var: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res2_1_branch2a_bn_s: (8,) => s2.pathway1_res1.branch2.a_bn.weight: (8,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2a_bn_rm: (64,) => s5.pathway1_res1.branch2.a_bn.running_mean: (64,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_2_branch2b_bn_s: (256,) => s4.pathway0_res2.branch2.b_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res2_1_branch2a_bn_b: (8,) => s2.pathway1_res1.branch2.a_bn.bias: (8,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_2_branch2b_bn_b: (256,) => s4.pathway0_res2.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_9_branch2a_bn_riv: (32,) => s4.pathway1_res9.branch2.a_bn.running_var: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_3_branch2a_bn_b: (32,) => s4.pathway1_res3.branch2.a_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: nonlocal_conv4_20_out_w: (1024, 512, 1, 1, 1) => s4.pathway0_nonlocal20.conv_out.weight: (1024, 512, 1, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_16_branch2b_bn_b: (256,) => s4.pathway0_res16.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_3_branch2a_bn_s: (32,) => s4.pathway1_res3.branch2.a_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_3_branch2c_bn_riv: (1024,) => s4.pathway0_res3.branch2.c_bn.running_var: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: nonlocal_conv4_20_out_b: (1024,) => s4.pathway0_nonlocal20.conv_out.bias: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_22_branch2b_bn_b: (256,) => s4.pathway0_res22.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_15_branch2b_bn_riv: (256,) => s4.pathway0_res15.branch2.b_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_22_branch2b_bn_s: (256,) => s4.pathway0_res22.branch2.b_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res3_0_branch2a_bn_s: (128,) => s3.pathway0_res0.branch2.a_bn.weight: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res3_0_branch2a_bn_b: (128,) => s3.pathway0_res0.branch2.a_bn.bias: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2c_bn_rm: (64,) => s3.pathway1_res0.branch2.c_bn.running_mean: (64,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_6_branch2b_bn_s: (32,) => s4.pathway1_res6.branch2.b_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_15_branch2b_bn_s: (256,) => s4.pathway0_res15.branch2.b_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2c_bn_riv: (64,) => s3.pathway1_res0.branch2.c_bn.running_var: (64,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_6_branch2b_bn_b: (32,) => s4.pathway1_res6.branch2.b_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_15_branch2b_bn_b: (256,) => s4.pathway0_res15.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_6_branch2c_bn_s: (1024,) => s4.pathway0_res6.branch2.c_bn.weight: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res5_1_branch2a_bn_s: (512,) => s5.pathway0_res1.branch2.a_bn.weight: (512,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_18_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res18.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_6_branch2c_bn_b: (1024,) => s4.pathway0_res6.branch2.c_bn.bias: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res5_1_branch2a_bn_b: (512,) => s5.pathway0_res1.branch2.a_bn.bias: (512,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_10_branch2b_bn_b: (32,) => s4.pathway1_res10.branch2.b_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_2_branch2b_bn_riv: (256,) => s4.pathway0_res2.branch2.b_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2b_bn_b: (16,) => s3.pathway1_res0.branch2.b_bn.bias: (16,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_10_branch2b_bn_s: (32,) => s4.pathway1_res10.branch2.b_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_0_branch2b_bn_s: (16,) => s3.pathway1_res0.branch2.b_bn.weight: (16,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_1_branch2a_bn_riv: (16,) => s3.pathway1_res1.branch2.a_bn.running_var: (16,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_5_branch2b_bn_riv: (256,) => s4.pathway0_res5.branch2.b_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_14_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res14.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_12_branch2c_bn_s: (128,) => s4.pathway1_res12.branch2.c_bn.weight: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_21_branch2a_bn_b: (32,) => s4.pathway1_res21.branch2.a_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_10_branch2c_bn_b: (128,) => s4.pathway1_res10.branch2.c_bn.bias: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_12_branch2c_bn_b: (128,) => s4.pathway1_res12.branch2.c_bn.bias: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_2_branch2a_bn_riv: (256,) => s4.pathway0_res2.branch2.a_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_21_branch2a_bn_s: (32,) => s4.pathway1_res21.branch2.a_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_10_branch2c_bn_s: (128,) => s4.pathway1_res10.branch2.c_bn.weight: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res3_0_branch2b_w: (128, 128, 1, 3, 3) => s3.pathway0_res0.branch2.b.weight: (128, 128, 1, 3, 3)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_19_branch2a_bn_rm: (32,) => s4.pathway1_res19.branch2.a_bn.running_mean: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_16_branch2b_bn_riv: (32,) => s4.pathway1_res16.branch2.b_bn.running_var: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2c_w: (256, 64, 1, 1, 1) => s5.pathway1_res1.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2a_w: (64, 256, 3, 1, 1) => s5.pathway1_res1.branch2.a.weight: (64, 256, 3, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_15_branch2c_bn_riv: (128,) => s4.pathway1_res15.branch2.c_bn.running_var: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_7_branch2b_bn_riv: (256,) => s4.pathway0_res7.branch2.b_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res5_0_branch1_w: (2048, 1280, 1, 1, 1) => s5.pathway0_res0.branch1.weight: (2048, 1280, 1, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res2_0_branch2c_bn_b: (32,) => s2.pathway1_res0.branch2.c_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res3_2_branch2c_bn_riv: (512,) => s3.pathway0_res2.branch2.c_bn.running_var: (512,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_2_branch2c_bn_b: (1024,) => s4.pathway0_res2.branch2.c_bn.bias: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_10_branch2c_bn_riv: (128,) => s4.pathway1_res10.branch2.c_bn.running_var: (128,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res3_1_branch2a_w: (16, 64, 3, 1, 1) => s3.pathway1_res1.branch2.a.weight: (16, 64, 3, 1, 1)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_15_branch2a_bn_riv: (256,) => s4.pathway0_res15.branch2.a_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_19_branch2b_bn_riv: (256,) => s4.pathway0_res19.branch2.b_bn.running_var: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_2_branch2b_bn_rm: (32,) => s4.pathway1_res2.branch2.b_bn.running_mean: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_14_branch2b_bn_s: (32,) => s4.pathway1_res14.branch2.b_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2b_w: (64, 64, 1, 3, 3) => s5.pathway1_res1.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_6_branch2b_bn_s: (256,) => s4.pathway0_res6.branch2.b_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_21_branch2b_bn_s: (32,) => s4.pathway1_res21.branch2.b_bn.weight: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_6_branch2b_bn_b: (256,) => s4.pathway0_res6.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_21_branch2b_bn_b: (32,) => s4.pathway1_res21.branch2.b_bn.bias: (32,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_1_branch2c_bn_b: (1024,) => s4.pathway0_res1.branch2.c_bn.bias: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_19_branch2b_bn_s: (256,) => s4.pathway0_res19.branch2.b_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2c_bn_s: (256,) => s5.pathway1_res1.branch2.c_bn.weight: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_1_branch2c_bn_s: (1024,) => s4.pathway0_res1.branch2.c_bn.weight: (1024,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res4_6_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res6.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_15_branch2a_bn_rm: (256,) => s4.pathway0_res15.branch2.a_bn.running_mean: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: res4_19_branch2b_bn_b: (256,) => s4.pathway0_res19.branch2.b_bn.bias: (256,)
[10/25 14:59:26][INFO] checkpoint.py:  252: t_res5_1_branch2c_bn_b: (256,) => s5.pathway1_res1.branch2.c_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_4_branch2a_bn_rm: (32,) => s4.pathway1_res4.branch2.a_bn.running_mean: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res2_1_branch2a_bn_riv: (64,) => s2.pathway0_res1.branch2.a_bn.running_var: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_1_branch2b_bn_s: (16,) => s3.pathway1_res1.branch2.b_bn.weight: (16,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_22_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res22.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_1_branch2b_bn_b: (16,) => s3.pathway1_res1.branch2.b_bn.bias: (16,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res2_0_branch1_bn_rm: (32,) => s2.pathway1_res0.branch1_bn.running_mean: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_14_branch2c_bn_riv: (1024,) => s4.pathway0_res14.branch2.c_bn.running_var: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_0_branch2b_bn_b: (256,) => s4.pathway0_res0.branch2.b_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_0_branch2b_bn_s: (256,) => s4.pathway0_res0.branch2.b_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_2_branch2a_bn_b: (256,) => s4.pathway0_res2.branch2.a_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_21_branch2b_bn_s: (256,) => s4.pathway0_res21.branch2.b_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res3_3_branch2b_bn_rm: (128,) => s3.pathway0_res3.branch2.b_bn.running_mean: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_2_branch2a_bn_s: (256,) => s4.pathway0_res2.branch2.a_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_21_branch2b_bn_b: (256,) => s4.pathway0_res21.branch2.b_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_16_branch2b_bn_riv: (256,) => s4.pathway0_res16.branch2.b_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res5_0_branch1_bn_riv: (256,) => s5.pathway1_res0.branch1_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_14_branch2c_bn_b: (128,) => s4.pathway1_res14.branch2.c_bn.bias: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_21_branch2c_bn_riv: (128,) => s4.pathway1_res21.branch2.c_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_0_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res0.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_14_branch2c_bn_s: (128,) => s4.pathway1_res14.branch2.c_bn.weight: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_13_branch2a_w: (256, 1024, 1, 1, 1) => s4.pathway0_res13.branch2.a.weight: (256, 1024, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_12_branch2b_bn_riv: (256,) => s4.pathway0_res12.branch2.b_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res2_1_branch2b_w: (64, 64, 1, 3, 3) => s2.pathway0_res1.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: res3_2_branch2a_bn_rm: (128,) => s3.pathway0_res2.branch2.a_bn.running_mean: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_9_branch2b_bn_riv: (256,) => s4.pathway0_res9.branch2.b_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res3_3_branch2b_bn_riv: (128,) => s3.pathway0_res3.branch2.b_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res5_1_branch2b_bn_s: (64,) => s5.pathway1_res1.branch2.b_bn.weight: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_14_branch2b_bn_riv: (256,) => s4.pathway0_res14.branch2.b_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res5_1_branch2b_bn_b: (64,) => s5.pathway1_res1.branch2.b_bn.bias: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: nonlocal_conv4_13_bn_riv: (1024,) => s4.pathway0_nonlocal13.bn.running_var: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_6_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res6.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_20_branch2c_bn_b: (1024,) => s4.pathway0_res20.branch2.c_bn.bias: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: nonlocal_conv4_13_bn_b: (1024,) => s4.pathway0_nonlocal13.bn.bias: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_1_branch2b_bn_riv: (32,) => s4.pathway1_res1.branch2.b_bn.running_var: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_14_branch2c_bn_riv: (128,) => s4.pathway1_res14.branch2.c_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: nonlocal_conv4_13_bn_s: (1024,) => s4.pathway0_nonlocal13.bn.weight: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_1_branch2c_bn_s: (64,) => s3.pathway1_res1.branch2.c_bn.weight: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_1_branch2c_bn_b: (64,) => s3.pathway1_res1.branch2.c_bn.bias: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_19_branch2a_bn_b: (32,) => s4.pathway1_res19.branch2.a_bn.bias: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_22_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res22.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_5_branch2b_bn_riv: (32,) => s4.pathway1_res5.branch2.b_bn.running_var: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: nonlocal_conv4_6_bn_riv: (1024,) => s4.pathway0_nonlocal6.bn.running_var: (1024,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_17_branch2a_bn_b: (32,) => s4.pathway1_res17.branch2.a_bn.bias: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_19_branch2a_bn_s: (32,) => s4.pathway1_res19.branch2.a_bn.weight: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_0_branch2c_bn_riv: (128,) => s4.pathway1_res0.branch2.c_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_9_branch2a_bn_riv: (256,) => s4.pathway0_res9.branch2.a_bn.running_var: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_7_branch2c_bn_riv: (128,) => s4.pathway1_res7.branch2.c_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_22_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res22.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res3_0_branch2b_bn_riv: (128,) => s3.pathway0_res0.branch2.b_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_9_branch2a_bn_s: (32,) => s4.pathway1_res9.branch2.a_bn.weight: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_3_branch2a_bn_b: (256,) => s4.pathway0_res3.branch2.a_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_9_branch2a_bn_b: (32,) => s4.pathway1_res9.branch2.a_bn.bias: (32,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res5_2_branch2b_bn_s: (512,) => s5.pathway0_res2.branch2.b_bn.weight: (512,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_21_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res21.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_0_branch2a_bn_s: (256,) => s4.pathway0_res0.branch2.a_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_21_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res21.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res3_1_branch2b_bn_riv: (128,) => s3.pathway0_res1.branch2.b_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_0_branch2a_bn_b: (256,) => s4.pathway0_res0.branch2.a_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res2_0_branch2c_bn_b: (256,) => s2.pathway0_res0.branch2.c_bn.bias: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res2_0_branch2c_bn_s: (256,) => s2.pathway0_res0.branch2.c_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_subsample_w: (128, 64, 5, 1, 1) => s3_fuse.conv_f2s.weight: (128, 64, 5, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_13_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res13.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_3_branch2c_bn_s: (128,) => s4.pathway1_res3.branch2.c_bn.weight: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_3_branch2b_w: (16, 16, 1, 3, 3) => s3.pathway1_res3.branch2.b.weight: (16, 16, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_15_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res15.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_11_branch2b_bn_rm: (256,) => s4.pathway0_res11.branch2.b_bn.running_mean: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res5_2_branch2c_bn_rm: (2048,) => s5.pathway0_res2.branch2.c_bn.running_mean: (2048,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_rm: (64,) => s3.pathway1_res3.branch2.c_bn.running_mean: (64,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_3_branch2c_bn_b: (128,) => s4.pathway1_res3.branch2.c_bn.bias: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_5_branch2c_bn_riv: (128,) => s4.pathway1_res5.branch2.c_bn.running_var: (128,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res2_1_branch2a_bn_riv: (8,) => s2.pathway1_res1.branch2.a_bn.running_var: (8,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res5_1_branch2b_bn_riv: (512,) => s5.pathway0_res1.branch2.b_bn.running_var: (512,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res4_11_branch2b_bn_s: (256,) => s4.pathway0_res11.branch2.b_bn.weight: (256,)
[10/25 14:59:27][INFO] checkpoint.py:  252: res5_2_branch2c_bn_s: (2048,) => s5.pathway0_res2.branch2.c_bn.weight: (2048,)
[10/25 14:59:27][INFO] checkpoint.py:  252: t_res4_1_branch2b_w: (32, 32, 1, 3, 3) => s4.pathway1_res1.branch2.b.weight: (32, 32, 1, 3, 3)
[10/25 14:59:27][INFO] checkpoint.py:  252: res2_0_branch2c_w: (256, 64, 1, 1, 1) => s2.pathway0_res0.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:27][INFO] checkpoint.py:  252: res5_2_branch2c_bn_b: (2048,) => s5.pathway0_res2.branch2.c_bn.bias: (2048,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_11_branch2b_bn_b: (256,) => s4.pathway0_res11.branch2.b_bn.bias: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: nonlocal_conv4_20_g_b: (512,) => s4.pathway0_nonlocal20.conv_g.bias: (512,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res5_0_branch2b_w: (64, 64, 1, 3, 3) => s5.pathway1_res0.branch2.b.weight: (64, 64, 1, 3, 3)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_16_branch2a_bn_b: (32,) => s4.pathway1_res16.branch2.a_bn.bias: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_2_branch2c_bn_riv: (1024,) => s4.pathway0_res2.branch2.c_bn.running_var: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_0_branch1_w: (32, 8, 1, 1, 1) => s2.pathway1_res0.branch1.weight: (32, 8, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_11_branch2a_bn_rm: (32,) => s4.pathway1_res11.branch2.a_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_16_branch2a_bn_s: (32,) => s4.pathway1_res16.branch2.a_bn.weight: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_7_branch2a_bn_riv: (32,) => s4.pathway1_res7.branch2.a_bn.running_var: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_11_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res11.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_21_branch2c_bn_s: (1024,) => s4.pathway0_res21.branch2.c_bn.weight: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_0_branch2a_bn_rm: (256,) => s4.pathway0_res0.branch2.a_bn.running_mean: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_21_branch2c_bn_b: (1024,) => s4.pathway0_res21.branch2.c_bn.bias: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res3_2_branch2b_bn_riv: (128,) => s3.pathway0_res2.branch2.b_bn.running_var: (128,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res5_2_branch2c_w: (256, 64, 1, 1, 1) => s5.pathway1_res2.branch2.c.weight: (256, 64, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_19_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res19.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res3_3_branch2c_bn_subsample_bn_rm: (128,) => s3_fuse.bn.running_mean: (128,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_11_branch2a_w: (32, 128, 1, 1, 1) => s4.pathway1_res11.branch2.a.weight: (32, 128, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_13_branch2a_bn_rm: (32,) => s4.pathway1_res13.branch2.a_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_19_branch2c_w: (128, 32, 1, 1, 1) => s4.pathway1_res19.branch2.c.weight: (128, 32, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_17_branch2b_bn_rm: (32,) => s4.pathway1_res17.branch2.b_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_18_branch2b_bn_riv: (256,) => s4.pathway0_res18.branch2.b_bn.running_var: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_0_branch1_bn_riv: (32,) => s2.pathway1_res0.branch1_bn.running_var: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_0_branch1_bn_riv: (1024,) => s4.pathway0_res0.branch1_bn.running_var: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_20_branch2b_bn_s: (256,) => s4.pathway0_res20.branch2.b_bn.weight: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res5_0_branch2c_bn_rm: (2048,) => s5.pathway0_res0.branch2.c_bn.running_mean: (2048,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res3_1_branch2c_bn_rm: (512,) => s3.pathway0_res1.branch2.c_bn.running_mean: (512,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_9_branch2a_bn_rm: (256,) => s4.pathway0_res9.branch2.a_bn.running_mean: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_1_branch2c_bn_rm: (32,) => s2.pathway1_res1.branch2.c_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_20_branch2b_bn_b: (256,) => s4.pathway0_res20.branch2.b_bn.bias: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_2_branch2a_bn_b: (8,) => s2.pathway1_res2.branch2.a_bn.bias: (8,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_12_branch2c_bn_b: (1024,) => s4.pathway0_res12.branch2.c_bn.bias: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res3_0_branch2c_bn_riv: (512,) => s3.pathway0_res0.branch2.c_bn.running_var: (512,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_12_branch2a_bn_rm: (256,) => s4.pathway0_res12.branch2.a_bn.running_mean: (256,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_12_branch2c_bn_s: (1024,) => s4.pathway0_res12.branch2.c_bn.weight: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_2_branch2a_bn_s: (8,) => s2.pathway1_res2.branch2.a_bn.weight: (8,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_19_branch2b_bn_s: (32,) => s4.pathway1_res19.branch2.b_bn.weight: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_10_branch2a_bn_riv: (32,) => s4.pathway1_res10.branch2.a_bn.running_var: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_19_branch2b_bn_b: (32,) => s4.pathway1_res19.branch2.b_bn.bias: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res3_2_branch2a_bn_riv: (128,) => s3.pathway0_res2.branch2.a_bn.running_var: (128,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_16_branch2a_bn_rm: (32,) => s4.pathway1_res16.branch2.a_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res3_0_branch2a_bn_rm: (16,) => s3.pathway1_res0.branch2.a_bn.running_mean: (16,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_0_branch1_bn_s: (1024,) => s4.pathway0_res0.branch1_bn.weight: (1024,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res3_3_branch2b_w: (128, 128, 1, 3, 3) => s3.pathway0_res3.branch2.b.weight: (128, 128, 1, 3, 3)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_6_branch2a_bn_rm: (32,) => s4.pathway1_res6.branch2.a_bn.running_mean: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_7_branch2b_bn_b: (32,) => s4.pathway1_res7.branch2.b_bn.bias: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_3_branch2a_w: (256, 1024, 3, 1, 1) => s4.pathway0_res3.branch2.a.weight: (256, 1024, 3, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res2_2_branch2c_bn_subsample_bn_riv: (64,) => s2_fuse.bn.running_var: (64,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_1_branch2b_w: (256, 256, 1, 3, 3) => s4.pathway0_res1.branch2.b.weight: (256, 256, 1, 3, 3)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_7_branch2b_bn_s: (32,) => s4.pathway1_res7.branch2.b_bn.weight: (32,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_2_branch2c_bn_b: (128,) => s4.pathway1_res2.branch2.c_bn.bias: (128,)
[10/25 14:59:28][INFO] checkpoint.py:  252: res4_3_branch2c_w: (1024, 256, 1, 1, 1) => s4.pathway0_res3.branch2.c.weight: (1024, 256, 1, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_2_branch2c_bn_s: (128,) => s4.pathway1_res2.branch2.c_bn.weight: (128,)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res5_2_branch2a_w: (64, 256, 3, 1, 1) => s5.pathway1_res2.branch2.a.weight: (64, 256, 3, 1, 1)
[10/25 14:59:28][INFO] checkpoint.py:  252: t_res4_11_branch2a_bn_riv: (32,) => s4.pathway1_res11.branch2.a_bn.running_var: (32,)
[10/25 14:59:28][INFO] predictor.py:   46: Finish loading model weights
/home/eraser/yes/envs/slowfast-env/lib/python3.10/site-packages/torch/functional.py:504: UserWarning: torch.meshgrid: in an upcoming release, it will be required to pass the indexing argument. (Triggered internally at /opt/conda/conda-bld/pytorch_1682343967769/work/aten/src/ATen/native/TensorShape.cpp:3483.)
  return _VF.meshgrid(tensors, **kwargs)  # type: ignore[attr-defined]
117it [01:25,  1.95it/s]

```

