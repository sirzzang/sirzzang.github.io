---
title:  "[DL] CNN_1. 개념"
excerpt: "한 줄 요약 : CNN 모델의 개념을 알아본다."
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-Lecture-Tensorflow.jpg

categories:
  - Lecture
tags:
  - Python
  - Deep Learning
  - CNN
  - Tensorflow
last_modified_at: 2020-03-01
---





# _CNN(Convolutional Neural Network)_

> 이미지 분석에 강점을 갖는 **합성곱 신경망**을 이용해 이미지를 예측하자.





## 1. CNN 개념

### 1.1. image processing

> CNN 모델은 특히 이미지를 판단하는 데에 있어 최적인 신경망 모델으로 알려져 있다.

* 기존의 neural network는 FC layer을 이용해 학습 및 예측을 진행한다. 그런데 이 방법으로 이미지를 학습하는 경우, 다음과 같은 어려움이 있다.

  > FC layer(완전 연결 신경망, Fully Connected Layer = Dense Layer)
  >
  > = 이전 layer의 모든 node가 다음 layer의 모든 node와 연결되어 학습되는 layer. 
  >
  > ![fclayer]({{site.url}}/assets/images/fclayer.png)

  * 이미지가 휘어 있거나, 크기가 제각각이거나, 색상, 모양 등 조금만 변형이 생긴다면 학습이 어렵다.
  * 학습하는 데에 시간이 오래 걸린다.
  * 이미지 픽셀을 1차원으로 평면화(flatten)하여 표현하는 과정에서 정보의 손실이 발생할 수 있다.

* CNN 모델은 사람의 학습 방식을 모방하여 이미지 학습을 진행한다.

  * 사람은 이미지에 변형이 생기더라도 특징을 비교해서 기억하고 있기 때문에, 이미지를 판단할 수 있다.
  * 즉, 데이터를 있는 그대로 기억하는 것이 아니라, 데이터가 가진 일부 특징을 기억한다.

* CNN 모델은 이미지 픽셀을 모두 입력하는 것이 아니라, 이미지를 대표하는 특징을 도출한다. 즉, 이미지를 대표하는 여러 개의 이미지를 만들어서 그 이미지의 특징적 픽셀을 학습한다.

![CNN 원리]({{ site.url }}/assets/images/CNN1.png)



### 1.2. 특징

> "이미지 크기를 줄이면서, 특징을 나타내는 여러 장의 이미지들을 뽑아낼 수 있다."

- 이미지의 공간 정보를 유지하면서(flatten 없음) , 인접한 이미지와의 특징을 효과적으로 인식한다.
- 추출한 이미지의 특징을 모으거나 강화할 수 있다.
- 일반 FC layer 학습 방식과 비교해, 학습해야 할 node의 수가 적다.



### 1.3. 주요 개념

> **Filter**가 **입력 데이터(이미지)**를 순회하며 **합성곱**을 계산하고, 그 계산 결과를 이용하여 **Feature Map**을 만든다. 이를 모아 한 이미지에 대한 **Activation Map**을 만드는데, 이 과정을 하나의 **Convolution**이라고 한다. **Convolution Layer**의 shape은 **Filter 크기, Stride, Padding 적용 여부, Max Pooling 크기**에 따라 달라진다.
>
> 출력된 **Convolution** 데이터를 또 하나의 입력 데이터로 삼아, 위의 과정을 반복한다. 이 과정에서 이미지의 size는 줄어들고, channel이 늘어나게 된다.



#### 1) input data type : height * weight * channel 

#### 2) Channel

* Convolution을 구성하는 layer의 수를 의미한다.

  * 처음에는 image의 depth.
  * 그 이후에는 필터의 개수.

* 최초의 input image가 컬러 이미지라면, RGB 스케일을 사용하기 때문에 channel이 3이다. 반면, 흑백 이미지라면, grey 스케일을 사용하기 때문에 channel이 1이다.

  ![channel]({{ site.url }}/assets/images/channel.jpg)

  * 높이가 39 픽셀이고 폭이 31 픽셀인 컬러 사진 데이터의 shape은 (39, 31, 3).
  * 높이가 39픽셀이고 폭이 31픽셀인 흑백 사진 데이터의 shape은 (39, 31, 1).

* 이후 convolution layer를 지날 때마다,  *filter의 수에 따라* channel이 달라지게 된다.



#### 3) Filter(=kernel), Stride

![filter]({{ site.url }}/assets/images/filter.png)

* 합성곱 연산을 수행하는 과정에서, 이미지의 특징을 뽑아낼 파라미터(거름망)이다.
* 즉, 이미지에서 detection을 위해 가중치를 주는 것이다.기존 머신러닝, 딥러닝 모델에서의 weight라고 봐도 된다. 
* 일반적으로 정사각 행렬로 정의된다. 초기에 random값을 부여하며, 학습을 통해 적절한 filter의 값을 찾아 나간다.



#### 4) Convolution(합성곱)

* 각 이미지 데이터에서 filter를 통해 feature을 추출하기 위해 사용하는 연산으로, [위키피디아]([https://ko.wikipedia.org/wiki/%ED%95%A9%EC%84%B1%EA%B3%B1](https://ko.wikipedia.org/wiki/합성곱)) 다음과 같이 정의한다.

  > *"합성곱 연산*은 두 함수 f, g 가운데 하나의 함수를 반전(reverse), 전이(shift)시킨 다음, 다른 하나의 함수와 곱한 결과를 적분하는 것을 의미한다."

* 이미지로 나타내면 다음과 같다.

![colvolution]({{site.url}}/assets/images/convolution23.png)

![colvolution detail]({{site.url}}/assets/images/convolution1.gif)



#### 5) Feature Map, Stride

* Feature map이란, 입력된 이미지 데이터에 합성곱 연산을 수행한 결과로, 각 이미지의 특징을 찾아낸 결과이다.

![feature map]({{ site.url }}/assets/images/featuremap.png)

* Feature map을 도출하기 위해, filter는 입력된 이미지 데이터를 일정한 간격으로 순회한다. 이 때, 필터를 순회하기 위해 지정하는 간격을 **stride**라고 한다.
  * stride가 1일 때 parameter가 SAME 옵션이면 처음 이미지 사이즈와 결과 이미지 사이즈가 동일하게 나온다.
  * stride가 2일 때 parameter가 SAME 옵션이면 처음 이미지 사이즈의 절반으로 줄어든다.

> 예시) 4X4 이미지에 2X2 필터를 stride 1로 적용했을 때의 feature map.
>
> ![stride example]({{ site.url}}/assets/images/stride.jpg){: width="70%" height="70%"}

* feature map의 size가 정수가 되게 stride를 설정해야 한다. feature map의 한 변의 길이는 다음과 같다.

$$
{(N-F)/stride + 1}
$$

* input data의 channel별로 하나씩의 feature map이 만들어진다.

![feature map2]({{ site.url }}/assets/images/featuredddmap.png)

* **입력 데이터의 channel 수와 필터의 channel 수가 같아야** 합성곱 연산이 수행될 수 있다.



#### 6) Activation map

* feature map을 모은 결과로, *convolution layer의 입력 데이터*가 된다.
* activation map의 shape 

$$
(feature map size) * filter 개수
$$

![activation map]({{site.url}}/asset/images/lecture.png)



####  7) Padding

* convolution layer를 중첩하여 지나며 출력 이미지 데이터의 크기가 입력 이미지 데이터의 크기보다 작아지게 된다. 이렇게 이미지가 축소되는 과정에서 공간 정보의 손실이 생길 수 있다.

* **이미지 데이터의 손실을 막기 위해** 이미지의 테두리에 지정된 픽셀만큼 0의 값을 할당하여 덧대어 주는 과정을 의미한다. 

* 이 때, 0의 값은 말 그대로 0이라기 보다는 *비어 있는 공간*을 의미한다고 이해한다.

![padding]({{site.url}}/asset/images/padding.png)

* 이미지 데이터의 외곽에 0의 픽셀값을 할당함으로써, 다음의 효과를 얻을 수 있다.
  * convolution layer의 출력 데이터가 줄어드는 것을 방지할 수 있다.
  * 출력 데이터의 크기를 조절할 수 있다.
  * 인공 신경망이 이미지의 외곽을 인식할 수 있다.

* `valid`(패딩 없음)와 `same`(feature map의 크기가 기존 입력 이미지 데이터의 크기와 같아짐)의 파라미터 옵션으로 조정한다.

![padding option]({{site.url}}/asset/images/paddingoption.png)

* padding을 진행한 결과 이미지의 한 변의 size는 다음과 같다.

$$
{(N + 2P - F)/S} + 1
$$



#### 8) Pooling layer

* convolution layer의 출력 데이터를 받아서, 출력 데이터의 크기를 줄이거나, 특정 데이터를 강조하기 위한 용도로 사용하는 layer이다.

* pooling layer의 처리 방식에는 Max pooling, Min pooling, Average Pooling 등이 있다. CNN에서는 주로 Max pooling을 사용한다.

![maxpulling]({{site.url}}/asset/images/maxpulling.png)



* Pooling 시 kernel의 크기와 stride를 정한다. 

* valid(패딩 없음)와 same(pooling 후의 크기가 기존 입력 이미지 데이터의 크기와 같음)의 옵션을 갖는다.

* Pooling의 결과는 다음과 같은 특징이 있다.
  * 학습 대상 파라미터(filter)가 없다. 대신 kernel이라고 부른다.
  * 출력 데이터의 크기가 감소한다.
  * 채널 수는 변경되지 않는다.