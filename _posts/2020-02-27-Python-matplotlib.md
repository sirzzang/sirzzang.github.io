---
title:  "[Python] Matplotlib 라이브러리 정리"
excerpt: "Matplotlib 라이브러리 주요 사용법을 정리합니다."
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Python
tags:
  - Python
  - Matplotlib
  - visualization
last_modified_at: 2020-03-03
---







# _"Matplotlib 사용법 정리"_

> 강의에서 데이터를 차트나 플롯(plot)으로 그려주는 패키지인 Matplotlib에 대해 배웠습니다. 공모전, Kaggle 등 데이터 분석 연습을 진행하며 데이터를 시각화하는 것의 중요성에 대해 알게 됐습니다. 
>
> 이에 Matplotlib의 사용법에 대해 정리하면서 반복하여 공부하고자 합니다.



*이 글이 마지막으로 수정된 시각은 {{ page.last_modified_at }} 입니다.*





* alpha : 투명도.
* cmap : colormap





## rcParmas

* 폰트 크기, 그래프 색깔 등 plot parameter를 조정할 수 있는 class([공식 문서](https://matplotlib.org/3.1.1/api/matplotlib_configuration_api.html#matplotlib.RcParams)).

* 다음의 두 가지 방식을 통해 사용할 수 있다.

  * .rcParams[] : 직접적으로 하나씩 지정해 커스텀.

  ```py
  mpl.rcParams['lines.linewidth'] = 2
  mpl.rcParams['lines.color'] = 'r'
  plt.plot(data)
  ```

  * .rc() : 여러 세팅을 한 번에 바꿀 수 있음.

  ```python
  mpl.rc('lines', linewidth=4, color='g')
  plt.plot(data)
  ```

* 다음과 같은 옵션을 지정할 수 있다.
  * axes.labelsize : x축, y축 이름 폰트 크기.
  * xtick.labelsize, ytick.labelsize : x축, y축 tick의 폰트 크기.
  * `plt.rcParams['axes.unicode_minus'] = False` : 한글 깨짐 현상 해결.







## hist()

* 히스토그램을 그리는 데 사용하는 명령([공식문서](https://matplotlib.org/api/pyplot_api.html#matplotlib.pyplot.hist))으로, 주로 값의 분포를 시각적으로 확인하기 위해 사용한다.
* 인자로 다음의 값을 갖는다.
  * `n` : 각 구간에 포함된 값의 갯수 혹은 빈도 리스트.
  * `bins` : 구간의 경계값 리스트.
  * `patches` : 각 구간을 그리는 matplotlib patch 객체 리스트.



## scatter

* 산점도를 그려 두 변수 간 관계를 확인할 때 사용한다.
  * plt.scatter()
  * plt.plot(kind = "scatter")

* 인자로 다음의 값을 갖는다.
  * x, y: x축, y축에 들어갈 자료. list, nd.array와 같이 iterable한 자료형을 받는다.
  * s : 마커의 크기.
    * 마커의 크기를 바꿀 필요가 있을 때<sup>예) 인구를 나타내야 할 때</sup> 사용한다.
    * 스칼라로 입력할 경우 마커의 크기는 고정이다.
    * 요소수를 가지는 iterable을 입력받는 경우, 각 마커별로 크기를 다르게 설정할 수 있다.
  * c : 마커의 색상.
    * plot에서 선과 동일하게 코드를 입력할 수 있다.
    * iterable을 입력받는 경우, 마커별로 크기를 다르게 설정할 수 있다.



## image

> ```python
> import matplotlib.image as mpimg
> ```



* matplotlib에서 이미지를 처리할 때 사용한다.([공식문서](https://matplotlib.org/tutorials/introductory/images.html))
* 

