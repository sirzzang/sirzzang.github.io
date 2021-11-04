---
title:  "3D, VR, AR"
excerpt: "공간의 개념에서 3D, VR, AR를 정의해 보자."
toc: false
toc_sticky: false
categories:
  - etc
tags:
  - 3D
  - VR
  - AR
  - 공간
use_math: true
---

<br>

 `공간`이 필요한 플랫폼을 설계할 때, 그 `공간`을 어떻게 설계할 것인가는 중요한 문제이다. 업무의 과정에서 현실감 있고 입체감 있는 `공간`을 설계하기 위한 논의를 이어 오다, `3D`, `VR`, `AR` 등의 키워드가 중요하게 등장했다. 

 일상 속에서 3D 영화, VR 게임 등 관련 용어를 자주 사용하고 있었음에도 불구하고, 정보가 산재되어 있다 보니 하나로 모아 마음에 드는 개념을 정립하는 것이 어려웠다. 이에 *~~내 마음대로~~* 각 개념을 정리해 보고자 한다.

<br>



# 1. 개념도

<br>

 각 개념을 모두 관통하는 나름대로의 개념도를 그려 봤다.

![3d-concepts]({{site.url}}/assets/images/3d-2d-comparison.png)

<br>

 공간으로서의 3D를 이해하기 위해서는 **차원**과 **구현 기술**이 중요한 개념이었다. 3D는 우리가 살고 있는 3차원 공간을 의미한다. 그리고 그것을 기술, 특히 컴퓨터적인 관점에서, 컴퓨터 안에 3D를 구현하는 것이 좁은 의미에서의 3D(혹은 3D 기술이라고도 지칭할 수 있을 듯하다)이다. 이러한 흐름에의 3D는 2D와 그대로 대응될 수 있다. 즉, 차원으로서의 2D 공간과 2D를 구현할 수 있는 기술이 존재한다는 의미이다. 

 3D의 틀 안에서 설명할 수 있는 용어로 3D 구현 기술을 활용한 다른 기술이 있다. 이들의 포지션을 잡는 것이 어려웠다. 3D와 2D처럼 대응되는 관계가 아니었기 때문이다.

 첫째로 생각해볼 수 있는 기술들은 3D TV, 3D 프린터, 3D 그래픽 등이다. 이들은 3D 기술을 이용해 3D 물체를 구현하면서도, 3D 기술 이외에 다른 기술들(예컨대 디스플레이, 애니메이션 등)을 사용한다. 둘째로는 이후에 살펴볼 VR, AR이 있다. VR, AR 모두 Reality의 개념에 기반을 둔 만큼, 3D 공간과 물체 및 그것을 구현할 수 있는 3D 기술을 필요로 한다. 그러나 3D TV, 영화 등과 달리 VR, AR을 구현하기 위해 필요한 다른 기술들이 있다. 그것을 구현할 수 있는 기술을 필요로 한다. 

<br>



# 2. 3D

<br>

## 2.1. 3차원 공간



 3차원 공간으로서의 3D를 사전적으로 정의하면 다음과 같다.

> geometeric setting in which three values are required to determine the position of an element

 즉, **특정 위치를 표현하기 위해 3차원 벡터가 필요한 환경**이다. 조금 더 일상적인 용어로 표현하자면 면과 면으로 이루어진 차원을 의미한다. ~~정의하려고 해서 그렇지, 그냥 우리 인간이 사는 공간이다.~~

 면과 면으로 이루어진 3D 차원이 2D와 가장 크게 다른 점은, 2D가 width, height의 두 가지 축만으로 표현될 수 있는 반면, 3D는 width, height에 더해 depth 축이 있어야 표현할 수 있다는 것이다. depth 축의 존재로 인해 비로소 우리가 사는(*혹은 인간의 뇌가 익숙해져 있는*) 3차원 공간을 표현할 수 있게 되며, 3D를 구현할 수 있어야만 생동감과 현실감을 느낄 수 있다.

> *참고* : 3D 구현의 필요성
>
>  2D 구현을 넘어 3D 구현이 필요한 순간이 있다. 그러한 이유로 후술할 기술들이 등장했기 때문이다. 3D 구현이 필요한 상황으로는 다음과 같은 것들이 있을 것이다.
>
> * 현실적인 시각적 표현을 보고 싶을 때
> * 2D 공간보다 더 다양한 정보를 표현하고 싶을 때(일반적으로 2D 공간에서는 간단한 수치, 예컨대 높이나 너비 등, 만으로 표현될 수 있는 정보를 표현한다)
> * 실제로 가 보거나 만져보는 등의 경험을 제공하고자 할 때
> * 정확한 물체의 표현이 필요할 때

<br>



## 2.2. 3차원 공간을 구현하기 위한 기술

  기술, 특히 컴퓨터 기술의 측면에서의 3D는, **3D 공간을 컴퓨터에 구현하기 위한 기술**을 의미한다. 그 하위 영역에 많은 기술들이 있겠지만, 그 중에서도 핵심이 되는 기술은 **3D 모델링**과 **3D 렌더링**이라 생각한다.



![3d modeling and rendering]({{site.url}}/assets/images/3d-modeling-rendering.png)

<center><sup>이미지 출처: http://learningthreejs.com/blog/2014/05/07/threejs-interview-online-3d-modeling-and-rendering-with-claraio/</sup></center>

 3D 모델링은 현실 세계의 물체를 컴퓨터가 이해할 수 있는 데이터 형태로 만들어내는 것을 의미한다. 가장 밑의 단계에서부터 살펴 보자면 3차원 벡터로 이루어진 좌표가 있고, 이 좌표들을 모아 면(삼각형, 원 등 다양한 형태)을 만들고, 그 면들을 모아 3D 모델을 만든다. 이렇게 만들어진 3D 모델을 2D 이미지로 바꾸는 과정이 바로 3D 렌더링이다. 렌더링 과정에서는 depth 표현을 위한 빛의 운반, 그림자 변화 등을 표현하는 것이 중요하다.

 그 외에 3D 물체를 투영하여 표현하는 3D projection, 현실의 3D 물체를 스캔하여 컴퓨터 속 3D 모델로 만드는 3D 스캐닝 등의 기술이 있다.

<br>

## 2.3. 3D 기술의 응용



### 3D 컴퓨터 그래픽



![3d-graphics]({{site.url}}/assets/images/3d-graphics.png){: .align-center}

<center><sup>이미지 출처: https://unity.com/kr/srp/High-Definition-Render-Pipeline</sup></center>

 3D 모델을 2차원으로 출력하여 보여주는 그래픽을 의미한다. 3D 모델링을 통해 만든 3D 모델에 레이아웃, 애니메이션 등의 기술을 적용하고, 3D 렌더링한다. 이렇게 만들어진 3D 그래픽은 3D 영화, 3D 게임 등에 자주 사용된다. 

<br>

### 3D 디스플레이



 3D 그래픽을 2D에서 느낄 수 있도록 하는 디스플레이 기술 및 장치이다. 2D에서도 3D 그래픽을 입체감 있게 느낄 수 있게 하는 기술이라고 생각하면 될 듯하다. 안경 방식과 무안경 방식이 있다고 하는데, 전자를 실현할 수 있는 대표적인 기술로는 스테레오스코피(3D 영화를 보러 갔을 때 쓰는 안경을 생각하면 된다)가 있고, 후자를 실현하기 위해서는 3D 카메라 등을 사용하여 영상을 찍는 방식 등이 있다. 

<br>

### 기타



 그 외 3D 디스플레이를 사용한 3D TV, 3D 영화 등이 있다. 또한 3D 모델을 프린팅하는 3D 프린팅 및 프린터 기술도 있다.

<br>

# 3. VR, AR



## 3.1. VR



 VR의 사전적 정의는 다음과 같다.

> computer-generated simulation of a three-dimensional image or environment that can be interacted with in a seemingly real or physical way by a person using special electronic equipment

 위의 사전적 정의에서 공간 및 기술로서의 VR을 정의하기 위해 필요한 핵심은 다음과 같다.

* 컴퓨터에 의해 만들어진
* 3차원 이미지 혹은 환경
* 특별한 기기를 통해 상호작용 가능

<br>

![vr]({{site.url}}/assets/images/run-bts-vr.png)

<center><sup>이미지 출처: vlive 달려라 방탄 81회</sup></center>

<br>

### 공간으로서의 VR

  결과적으로, 공간(space)으로서의 VR 개념은 실제와 유사하지만 실제가 아닌 **인공 현실**(*혹은 세계*)을 의미한다. 근본적으로는 3차원 공간이기 때문에 3D 개념에 포함되지만, 실제가 아니라는 차이점이 있다. 

<br>

### 기술로서의 VR

 사실 VR이라고 하면 VR 기술을 떠올리는 것이 대부분이다. **VR 기술**은 컴퓨터를 통해 가상의 세계를 만들고, 사용자의 오감에 직접 작용하여 사용자가 가상의 세계와 상호작용할 수 있도록 하는 기술을 말한다. 

 3D 공간에서 3D 기술을 정의했던 것과 마찬가지로 VR 공간을 구현하기 위한 기술이 VR 기술이 되는데, 이 때 VR 공간은 인공 현실이면서도, 사용자가 현실에서처럼 상호작용할 수 있는 공간이므로, 이러한 점을 실현시켜줄 수 있어야 한다. 즉, VR 기술은 3D 기술을 통해 존재하지 않는 가상의 3D 공간을 표현하면서, 사용자와의 상호작용 및 사용자의 몰입을 도울 수 있는 여러 기술들을 필요로 한다. 후자의 기술에는 몰입을 도울 수 있는 음향 기술 및 사용자의 감각 및 모션을 감지할 수 있는 기기들이 필요하다. 이 기기들에는 트레드밀, HMD(헤드 마운티드 디스플레이, 머리에 쓰는 그것을 떠올리면 된다.), 장갑 등이 있는데, 이 기기들을 통해 사용자는 자신의 움직임을 VR 공간으로 전달하고 VR 공간에서 돌아오는 반응을 느낄 수 있게 된다. (입력 및 출력을 담당하는 기기라고 이해하면 된다.)

<br>

> *참고* : 3D 디스플레이 vs. VR 디스플레이
>
>  3D 디스플레이도 안경 등 무언가 기기를 사용해 보아야 하기 때문에 VR과 굉장히 헷갈렸다. 두 기술의 차이점은 시야각이다. 3D 디스플레이는 시야각 안에 화면 프레임이 모두 들어오지만, VR 디스플레이는 실제 인간의 시야각과 비슷하게 볼 수 없는 영역이 존재하고, 사용자의 시선 움직임에 따라 시야가 변한다. 
>
>  따라서 전자의 경우 3D 디스플레이는 사용자가 입체감을 느낄 수는 있지만 프레임 밖에 있음을 인지할 수 있어 현장감은 느껴지지 않고, 후자의 경우 입체감과 현장감을 동시에 느낄 수 있는 것이다.

<br>

## 3.2. AR

 AR의 사전적 정의는 다음과 같다.

> an interactive real-world environment where the objects that reside in the real world are enhanced by computer-generated information

 위의 사전적 정의에서 공간 및 기술로서의 AR을 정의하기 위한 핵심은 다음과 같다.

* 컴퓨터에 의해 만들어진 정보
* 실제 세계에 더해짐
* 상호작용 가능



### 공간으로서의 AR

  결과적으로, 공간(space)으로서의 AR 개념은 실제 환경에 컴퓨터가 만들어 낸 그래픽 등 **디지털화된 물체**가 중첩되어 보여지는 공간을 의미한다. 근본적으로는 3차원 공간이기 때문에 3D 개념에 기반을 두며, VR과 달리 실제 현실의 공간이다.



### 기술로서의 AR

 **AR 기술**은 컴퓨터를 통해 현실의 세계를 인식하고, 가상의 영상을 만들어 내 그것을 더하는 기술이다. 3D 그래픽을 만들기 위해 3D 구현 기술이 필요하고, 현실 세계에서 얹기 위해 객체 검출, 이미지 합성 등을 지원하는 컴퓨터 비전 기술도 필요하다. 상호작용은 VR과 비슷하게 기기를 가지고 할 수도 있고(Google glass, 마이크로소프트 Hololens 등), 특별한 기기 없이 스마트폰의 동영상 카메라를 통해서도(포켓몬고) 할 수 있다.



> *참고* : AR 개념의 범위
>
>  기술로서의 AR 개념은 점차 좁아져 왔다고 한다. 예전에는 현실 세계의 뷰에 3D 가상 물체를 입힌 것을 AR 기술이라고 하며 AR, VR이 `현실:가상`의 비율이 `50:50`, `0:100` 정도로 이해될 수 있었던 듯하다. 그러나 점차 혼합현실, 증강가상 등 AR과 VR 사이에 더 다양한 기술 개념들이 등장하며 AR 기술은 가상 물체를 활용해서 정보를 덧붙여 주는 기술 정도로만 이해되고 있다고 한다. 
>
> ![vr-ar-concept]({{site.url}}/assets/images/vr-ar-concept.png){: .align-center}
>
>  관련해서 위의 그림에서 왼쪽 두 개의 벤 다이어그램들처럼 각 기술의 포함관계를 나타내는 그림도 있으나, 나는 저 정도로 명확하게 개념을 아는 것은 아니어서 오른쪽처럼 일단 각 기술들의 포지션을 이해하기로 했다.

<br>



## 3.3. VR vs. AR



 그렇다면 VR 기술과 AR 기술을 어떻게 구분해야 할까. 사실 처음 VR, AR 개념을 이해하는 데 힘들었던 것은 VR, AR 기술을 검색하면 수 많은 회사에서 만들어 낸 기술, 기기들이 먼저 나왔기 때문이기도 하다. 이제 와서 각 기술을 이해해 보건대, 결과적으로는 VR, AR 모두 3D 구현 기술이 바탕이 되고, 그 이후 더 집중하는 부분이 달라지는 것이라고 생각했다.

* VR: 가상현실을 만들고, 상호작용해야 하므로 사용자의 행동과 몸에 더 집중한다.
* AR: 실제 현실을 스캔하고, 디지털 오브젝트를 사용자의 환경에 놓는 데에 더 집중한다.

<br>

 결과적으로 관련된 기술이나 기기를 내놓는 회사들이 매우 많은데, 구글링을 통해 나와 비슷한 문제 의식으로 각 회사들을 정리해 놓은 좋은 도식이 있어 첨부한다. 나중에 플랫폼 설계 시 필요한 기술이 있다면 참고하면 좋을 듯하다.

<br>

![vr-ar-techs]({{site.url}}/assets/images/vr-ar-techs.png){: .align-center}

<center><sup>이미지 출처: https://blog.naver.com/fstory97/220743460716</sup></center>

<br>

# 4. 결론

<br>

 결과적으로 어떠한 기술을 바탕으로 `공간`을 설계할 것인지는 각 개념들이 갖는 키워드 중 어떤 것을 구현하고 싶은지에 따라 달라지는 게 아닐까 한다.  ~~*막상 정리하고 나니 별 거 없는 것 같다*~~

 입체감, 현실감을 갖는 공간을 보여주는 것만으로 충분하다면 **3D 기술**을, 그 중에서도 사용자 경험을 증진시키기 위한 모델링과 렌더링에 집중하면 될 것이다. 그에 더해 상호작용을 구현하고자 한다면, VR, AR 기술의 도입을 생각해 보아야 한다. 그 중에서도 가상 공간에서 사용자가 직접 상호작용하는 것을 더 중점을 두고 싶다면 **VR 기술**을, 실제 공간을 바탕으로 사용자가 어떠한 오브젝트를 통해 상상하고 생각해보는 것을 지원하는 공간을 구현하고 싶다면 **AR 기술**을 사용하면 될 것이다.