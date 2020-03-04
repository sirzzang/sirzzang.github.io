---
title:  "[핸즈온 머신러닝] 2. 머신러닝 프로젝트 처음부터 끝까지"
excerpt: "한 줄 요약 : 머신러닝 프로젝트의 전 과정을 이해하자."
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-SELF.jpg
categories:
  - SELF
tags:
  - 핸즈온 머신러닝
  - 머신러닝
  - 프로세스
  - 체크리스트
last_modified_at: 2020-03-03
---



# 2장. 머신러닝 프로젝트 처음부터 끝까지

> 1장에서 살펴봤듯, 머신러닝은 데이터 준비 단계, 모니터링 도구 구축, 사람의 평가 파이프라인 세팅, 주기적인 모델 학습 자동화의 단계로 이루어진다. 프로젝트를 진행하기 위해서는 **전체 프로세스**에 익숙해지는 것이 무엇보다 중요하다. 
>
> 예시로 제공되는 캘리포니아 주택 가격 예측 프로젝트를 따라가며, 전체 프로젝트의 과정을 알아보자.



## *머신러닝 체크리스트*

[머신러닝 체크리스트]({{site.url}}/self/SELF-handson-ml-checklist/)를 준비하고, 프로젝트에 따라 수정하며 전체적인 프로세스를 구축하자.





## 2.1. 큰 그림 그리기

### 1) 문제 정의

> 캘리포니아 인구조사 데이터를 활용해 캘리포니아의 주택 가격 예측 모델을 만든다.

* 비즈니스의 목적 : 중간 주택 가격을 예측하여 투자 가치를 결정하는 시스템에 투입한다.

* (만약 있다면) 현재 솔루션의 구성 : 전문가 수동 추정. 오류가 많다.
* 문제 정의 : 지도 학습, 예측(회귀), 배치 학습.



### 2) 성능지표 선택

> 이 프로젝트에서는 RMSE를 선택한다.

* 평균 제곱근 오차(RMSE) 
  * 회귀 문제의 전형적 성능 지표.
  * 유클리디안 노름 : 상대적으로 이상치에 민감.
* 평균 절대 오차(MAE)
  * 맨해튼 노름 : 상대적으로 이상치에 둔감.



### 3) 가정 검사

* 모든 가정을 나열하고 검사.
* 다른 시스템을 담당하는 팀과의 소통 중요.





## 2.2. 데이터 가져오기

* 작업 환경 구축.
* 함수로 로드 단계 자동화.



### 데이터의 분포 살피기

데이터를 가져온 뒤, 깊게 들여다 보기 전에 데이터의 구조, 분포만 확인한다. *테스트 세트* 를 떼어 놓기 전까지는 **절대 더 이상 탐색하지 않는다.**



* 데이터 훑어 보기 : `.head()`

* 데이터에 대한 간략한 설명 : `.info()`

  * 전체 행 수, 결측치가 포함된 열 확인.
  * 각 특성의 data type 확인.

* data type에 따라 분포 확인.

  * 문자열/범주형 : `.value_counts()`

  * 수치형 

    * `.describe()`

    * 히스토그램

      > ![correlation matrix]({{ site.url }}/assets/images/correlation_matrix.png)
      >
      > 
      >
      > 이 프로젝트에서는 다음의 사항을 확인할 수 있다.
      >
      > 1. 중간소득의 표시 단위 : 스케일이 무엇인지, 전처리되었는지 여부를 확인한다.
      >
      > 2. 중간 주택 연도와 중간 주택 가격의 최댓값, 최솟값 한정.
      >
      >    클라이언트 팀과 상의한 뒤,
      >
      >    * 한계 밖 구역에 대한 정확한 레이블을 구하거나,
      >    * 훈련 세트에서 이러한 구역을 제거한다.
      >
      > 3. 특성 간 측정 수치가 달라, 스케일링이 필요하다.
      >
      > 4. 분포를 종 모양으로 변환할 필요가 있다.





## 2.3. 테스트 세트 만들기

* 데이터 스누핑 편향을 방지하기 위해, 훈련 데이터의 일부를 테스트 세트로 떼어 놓는다.

  *"데이터 스누핑 편향이란? 테스트 세트를 미리 들여다봄으로 인해, **테스트 세트에서 겉으로 드러난 패턴에 속아 특정 머신러닝 모델을 선택**하는 것. 시스템 런칭 후 일반화되지 않을 수 있다."*

* 테스트 세트 생성 방법

  * 무작위 샘플링 : 사이킷런 `train_test_split`
  * 계층적 샘플링 : 사이킷런 `StratifiedShuffleSplit`
  * 기타(링크!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!)
    * test_ratio 지정, 수작업.
    * 해시값, 고유식별자(행 인덱스, 새로운 id 컬럼 생성) 활용 : 데이터 업데이트 시.



### 계층적 샘플링

웬만하면, 계층적 샘플링을 활용한다. 이 때 주의해야 할 사항은 다음과 같다.

* **domain knowledge, 전문가의 조언**을 활용해 타깃 속성을 예측하는 데에 중요한 특성을 선택한다.

* 해당 특성을 계층별로 나누어, 새로운 특성을 생성한다.

  > 실습 파일에서 중간 소득 카테고리를 형성한 결과
  >
  > ![income_cat]({{ site.url }}/assets/images/income_category_hist.png)

  * 너무 많은 계층으로 나누면 안 된다.
  * 각 계층 내 샘플의 수가 충분히 커야 한다.

* 테스트 세트를 만든 뒤, 계층 특성을 삭제하고 데이터를 원래 상태로 복원한다.





## 2.4. 데이터 이해를 위한 탐색과 시각화

테스트 세트를 떼어 놓았는지 충분히 확인한다. **훈련 세트에 대해서만 탐색을 진행한다.**

훈련 세트의 크기가 크다면, 탐색을 위한 세트로 훈련 세트를 별도로 샘플링한다. 그렇지 않다면, 전체 훈련 세트로 탐색을 진행한다.

훈련 세트는 절대로 손상되어서는 안 되므로, 반드시 **복사본**을 만들어 진행한다.

이 단계는, 어디까지나, **"반복적"**인 과정이다. 프로토타입을 만들고, 실행한 후, 그 결과를 분석해서 더 많은 통찰을 얻고, 다시 돌아오는 과정을 반복한다.



### 1) 지리적 데이터 시각화

위도, 경도 등 지리 정보가 있을 때 **산점도**를 그리는 것이 좋다. 산점도를 그리는 기본 코드는 다음과 같다.

```python
>>>data.plot(kind="scatter", x, y)
>>>plt.scatter(data, column)
```



* 데이터 포인트 밀집 구역 파악

위도와 경도에 따라 산점도를 그리면, 데이터 포인트가 밀집된 지역을 파악할 수 있다. 밀집된 구역을 잘 나타내기 위해서, 적절한 크기의 투명도 옵션(`alpha`)을 줄 수 있다. 

> 실습 예제에서는, 주택이 밀집되어 있는 영역을 나타낸다. 투명도 옵션에 따라 밀집된 구역이 어떻게 나타나는지 비교할 수 있다.
>
> | 좋은 시각화                                                  | 나쁜 시각화 예                                               |
> | ------------------------------------------------------------ | ------------------------------------------------------------ |
> | ![alpha]({{ site.url }}/assets/images/better_visualization_plot.png) | ![nonalpha]({{ site.url }}/assets/images/bad_visualization_plot.png) |



* 다른 데이터와 연결해 시각화

원의 반지름을 나타내는 `s`, 원의 색을 나타내는 `c` 옵션 등을 활용해 다른 데이터와 한 번에 시각화할 수 있다.

> 실습 예제에서는, 원의 반지름으로 구역의 인구를, 원의 색깔로 가격을 나타내어 시각화했다.
>
> ![scatter_additional]({{ site.url }}/assets/images/housing_prices_scatterplot.png)





이렇게 시각화한 자료를 지리 정보를 나타내는 지도 등과 함께 본다면, 더 좋은 통찰을 얻을 수 있다.

> ![california map]({{site.url}}/california_housing_prices_plot.png)
>
> 실습 예제에서의 시각화를 통해 다음과 같은 점을 알 수 있다.
>
> 1. Bay Area, LA, San Diego 등의 지역에 주택이 밀집되어 있다.
> 2. 주택 가격은 지역(*ex. 바다와 밀접한 곳*), 인구 밀도와 연관이 크다. 
> 3. 이후 군집 알고리즘을 사용해 주요 군집을 찾고, 군집 중심가지의 거리를 재는 특성을 추가할 수 있다.
>    - 해안 근집성 특성이 유용할 수 있을까?
>    - 북부 캘리포니아에서는 Bay Area를 제외하고는 해안가의 주택 가격 특징은 높게 나타나지 않는데?



### 2) 상관관계 조사



*""**상관계수***

*선형적 상관관계를 측정한다. 비선형적 관계가 있는 경우 잡아내지 못한다.*

*상관계수는 기울기와 관련이 없다.""*



수치형 특성 간 상관관계를 조사함으로써 특성 조합, 특성공학 등에 대한 통찰을 얻을 수 있다.



* 전체 특성 간 상관계수 조사 : `.corr()`
* 타깃 속성과 다른 특성 간 상관관계 조사.
* 산점도 행렬



### 산점도 행렬

* 숫자형 특성 사이에 산점도를 그리는 `scatter_matrix` 함수 사용.

* 모든 그래프를 한 페이지에 그릴 수 없는 경우, 타깃 속성과 상관관계가 높아 보이는 특성을 선택하여 살펴본다.

* 옵션을 설정해 대각선 방향에는 히스토그램(`hist`)을 그리거나 커널 밀도 추정(`kde`)을 그릴 수 있다.

  > 실습 예제에서 생성한 산점도 행렬은 다음과 같다.
  >
  > ![scatter matrix]({{site.url}}/assets/images/scatter_matrix_plot.png)

* 산점도 행렬에서 유용할 것 같은 특성은 확대하여 살펴본다.

  > 실습 예제에서는 중간 소득과의 연관성이 높아 보인다.
  >
  > ![median income scatter]({{site.url}}/assets/images/income_vs_house_value_scatterplot.png)
  >
  > 이를 통해 다음과 같은 통찰을 얻을 수 있다.
  >
  > 1. 상관관계가 매우 강하다. 위쪽으로 향하는 경향을 볼 수 있고, 포인트들이 멀리 퍼져 있지 않다.
  > 2. 가격 제한 값이 50만 달러에서 수평으로 형성되어 있다.
  > 3. 45만 달러, 35만 달러, 28만 달러 부근에 직선적으로 데이터 포인트들이 밀집되어 있다. 알고리즘이 이상한 데이터 형태를 학습하지 않도록 해당 구역을 제거하는 것이 좋다.



### 3) 특성 조합으로 실험

* 여러 특성을 조합해 의미 있는 특성을 만들어낼 수 있다.

* 특성을 조합한 후, 상관계수를 다시 조사함으로써 의미가 있었는지 파악할 수 있다. 특히, 상관계수 그 자체의 절대적 크기에만 집중하지 말고, 이전의 특성과 새로운 특성 간 상대적인 비교에 의의를 둔다.

  > 실습 예제에서는, 가구 당 방의 개수, 방의 개수 당 침실의 개수, 가구 당 인구의 수 특성을 새로 만들었다.
  >
  > 새로운 특성을 만들고 상관관계를 다시 조사한 결과는 다음과 같다.
  >
  > ![new correlation]({{site.url}}/assets/images/scatter_matrix_plot_new_features.png)



### 4) 기타

* 정제할 데이터를 확인한다.
* 상관관계가 있는 특성을 조합한다.
* 데이터를 변형하여 분포를 바꾼다(*ex. 꼬리가 두꺼운 분포는 로그스케일 적용*)





## 2.5. 머신러닝 알고리즘을 위한 데이터 준비

이 단계에서 가장 중요한 것은, 모든 데이터 준비 과정을 함수로 만들어 자동화하는 것이다. 함수를 만들어 자동화해야 하는 이유는 다음과 같다.

* 어떤 데이터셋에 대해서도 손쉽게 데이터 변환을 반복할 수 있다.
* 향후 프로젝트에 사용할 수 있는 변환 라이브러리를 점진적으로 구축할 수 있다.
* 실제 시스템에서 알고리즘에 새 데이터를 주입하기 전에 변환시키는 데 이 함수를 사용할 수 있다.
* 여러 가지 데이터 변환을 쉽게 시도할 수 있고, 어떤 조합이 가장 좋은지 확인할 수 있다.



### 1) 수치형 데이터 정제



**결측치**

데이터에서 누락된 특성을 다음과 같은 방식으로 처리할 수 있다.

* 해당 열 제거.
* 전체 특성 삭제.
* 어떤 값으로 채우기(0, 평균, 중간값).

다시 한 번 강조하지만, 이 과정은 절대로 독단적으로 진행되어서는 안 되며, 확신이나 배경지식이 없는 경우, 여러 가지 방법을 모두 시도해봐야 한다.



#### SimpleImputer

* 사이킷런의 `SimpleImputer`를 사용해 결측치를 채우는 효과적인 방법을 제공한다.

  ```python
  from sklearn.impute import SimpleImputer
  
  imputer = SimpleImputer(strategy=[])
  data = data.drop([], axis=1) # 수치형, 문자형 등 drop.
  imputer.fit(data)
  imputer.statistics_
  new_data = imputer.transfrom(data)
  ```

  * imputer 객체를 생성하고, strategy에 결측치를 어떻게 채울 것인지 지정한다.
  * `.fit()` 메서드를 통해 훈련 데이터에 적용한다.
    * 훈련 데이터와 달리, 이후 서비스를 제공할 때 어떤 값이 누락될 지 알 수 없으므로 모든 수치형 데이터에 적용한다.
    * 각 데이터 별로 계산된 결과 값을 `.statistics_` 속성에서 확인한다. 이 값들은 나중에 테스트 세트, 테스트 데이터의 결측치에도 동일하게 적용되어야 한다.
  * `.transform()` 메서드를 통해 훈련 세트의 누락된 값을 채운다.

* `SimpleImputer`는 numpy array를 반환하므로, 이를 데이터프레임으로 변환해야 한다.



**이상치**

이상치를 정제하는 방법은 나중에 다룬다.



**특성 스케일링**

머신러닝 알고리즘에서는 입력 숫자 특성들의 스케일이 많이 다르면 잘 작동하지 않는다. 따라서 수치형 범주의 입력 숫자 특성들의 스케일을 맞춘다. 

타깃 속성에 대한 스케일링은 진행하지 않는다.

사이킷런의 preprocessing 패키지에서 scaler를 import하여 사용할 수 있다.





#### minmax scaling

* 정규화 : 0 ~ 1 사이의 범주.
* 이상치에 상대적으로 민감.
* `feature_range` 매개변수 : 0 ~ 1 외에 다른 범주로 scaling하고 싶을 때 범위 변경.



#### standard scaling

* 표준정규분포화 : 평균이 0, 분산이 1인 정규분포.
* 상한과 하한이 없어 일부 알고리즘에서는 문제가 되지만, 이상치에 상대적으로 덜 민감.



*"**모든 스케일링은 훈련 데이터에 대해서만 `.fit()` 메서드를 적용하고, 훈련 세트와 테스트 세트, 새로운 데이터에 대해서는 맞춰진 scaler를 사용해 `.transform()` 메서드만 적용해야 한다.**"*





### 2) 문자열/범주형 데이터 정제



문자열 범주형 특성인지, 그냥 문자열 특성인지 판단해야 한다. 그냥 문자열 특성인 경우, [Kaggle Titanic 예제]()에서와 같이 의미 있는 정보를 추출할 수도 있다.

이 책에서는 문자열 범주형 특성을 다루는 방법을 소개한다.



**원핫 인코딩**

대부분의 머신러닝 알고리즘은 숫자형을 다루므로, 카테고리를 텍스트에서 숫자형으로 바꾸어야 한다. 이를 위해 다음과 같은 방법을 사용할 수 있다.

* pandas의 `.factorize()` 메서드로 텍스트를 정수값으로 매핑, 이후 `OneHotEncoder`를 통해 원핫 벡터로 반환.
* 사이킷런 모듈 활용.

사이킷런의 모듈을 활용하여 인코딩을 진행하는 편이 훨씬 더 쉽다. 다음과 같은 인코더가 있다.



#### CategoricalEncoder

* 하나 이상의 특성을 가진 2차원 배열을 입력한다.
* 그냥 사용하면 `NameError`가 나므로, class를 직접 소스에 추가한 후 사용해야 한다.
* sparse matrix를 반환하므로, 필요하다면 dense matrix로 변환한다.

```python
# module import
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils import check_array
from sklearn.preprocessing import LabelEncoder
from scipy import sparse

# categorical encoder class 추가
class CategoricalEncoder(BaseEstimator, TransformerMixin):    
    def __init__(self, encoding='onehot', categories='auto', dtype=np.float64,
                 handle_unknown='error'):
        self.encoding = encoding
        self.categories = categories
        self.dtype = dtype
        self.handle_unknown = handle_unknown

    def fit(self, X, y=None):
        if self.encoding not in ['onehot', 'onehot-dense', 'ordinal']:
            template = ("encoding should be either 'onehot', 'onehot-dense' "
                        "or 'ordinal', got %s")
            raise ValueError(template % self.handle_unknown)

        if self.handle_unknown not in ['error', 'ignore']:
            template = ("handle_unknown should be either 'error' or "
                        "'ignore', got %s")
            raise ValueError(template % self.handle_unknown)

        if self.encoding == 'ordinal' and self.handle_unknown == 'ignore':
            raise ValueError("handle_unknown='ignore' is not supported for"
                             " encoding='ordinal'")
            
        X = check_array(X, dtype=np.object, accept_sparse='csc', copy=True)
        n_samples, n_features = X.shape

        self._label_encoders_ = [LabelEncoder() for _ in range(n_features)]

        for i in range(n_features):
            le = self._label_encoders_[i]
            Xi = X[:, i]
            if self.categories == 'auto':
                le.fit(Xi)
            else:
                valid_mask = np.in1d(Xi, self.categories[i])
                if not np.all(valid_mask):
                    if self.handle_unknown == 'error':
                        diff = np.unique(Xi[~valid_mask])
                        msg = ("Found unknown categories {0} in column {1}"
                               " during fit".format(diff, i))
                        raise ValueError(msg)
                le.classes_ = np.array(np.sort(self.categories[i]))

        self.categories_ = [le.classes_ for le in self._label_encoders_]

        return self
        
    def transform(self, X):        
        X = check_array(X, accept_sparse='csc', dtype=np.object, copy=True)
        n_samples, n_features = X.shape
        X_int = np.zeros_like(X, dtype=np.int)
        X_mask = np.ones_like(X, dtype=np.bool)

        for i in range(n_features):
            valid_mask = np.in1d(X[:, i], self.categories_[i])
            
            if not np.all(valid_mask):
                if self.handle_unknown == 'error':
                    diff = np.unique(X[~valid_mask, i])
                    msg = ("Found unknown categories {0} in column {1}"
                           " during transform".format(diff, i))
                    raise ValueError(msg)
            else:
                X_mask[:, i] = valid_mask
                X[:, i][~valid_mask] = self.categories_[i][0]
                
            X_int[:, i] = self._label_encoders_[i].transform(X[:, i])

        if self.encoding == 'ordinal':
            return X_int.astype(self.dtype, copy=False)

        mask = X_mask.ravel()
        n_values = [cats.shape[0] for cats in self.categories_]
        n_values = np.array([0] + n_values)
        indices = np.cumsum(n_values)

        column_indices = (X_int + indices[:-1]).ravel()[mask]
        row_indices = np.repeat(np.arange(n_samples, dtype=np.int32),
                                n_features)[mask]
        data = np.ones(n_samples * n_features)[mask]

        out = sparse.csc_matrix((data, (row_indices, column_indices)),
                                shape=(n_samples, indices[-1]),
                                dtype=self.dtype).tocsr()
        if self.encoding == 'onehot-dense':
            return out.toarray()
        else:
            return out
        
# categorical encoder 사용
cat_encoder = CategoricalEncoder()
housing_cat_reshaped = housing_cat.values.reshape(-1,1)
housing_cat_onehot = cat_encoder.fit_transform(housing_cat_reshaped)

# dense matrix로 변환
housing_cat_onehot.toarray()

# 생성된 범주 확인
cat_encoder.categories_
```



#### OrdinalEncoder

* 입력 특성을 위해 설계되었다.
* Pipeline과 잘 작동한다
* 사용 방법은 동일하다.



#### OneHotEncoder

* `.factorize()` 없이 바로 문자형 변수를 입력하면 원핫 벡터로 바꿔준다.
* 사용 방법은 동일하다.





### 3) 변환 파이프라인 만들기

데이터를 준비하는 과정에 변환 단계가 많으며, 정확한 순서대로 실행되어야 한다. 이러한 과정을 자동화하기 위해 파이프라인을 만든다.



#### Pipeline

* 사이킷런의 `Pipeline` 클래스 이용. 연속된 변환을 순서대로 처리할 수 있도록 하는 클래스.

* 연속된 단계를 나타내는 이름과 변환기 혹은 추정기의 쌍을 모두 목록으로 입력받는다. 

  * 마지막 단계에서는 변환기와 추정기를 모두 사용할 수 있고,
  * 그 이전 단계에서는 모두 변환기여야 한다.
  * 변환기의 이름은 무엇이든 상관없으나, 이중 밑줄(`__`)은 포함할 수 없다.

* Pipeline에 대해 `.fit()` 호출 시 다음의 동작이 실행된다.

  * 마지막 단계 이전 : 모든 변환기의 `.fit_transform()` 메서드를 순서대로 호출한 후, 출력을 다음 단계의 입력으로 전달한다.
  * 마지막 단계 : `.fit()` 메서드만 호출한다.

* Pipeline 객체가 제공하는 메서드는 **마지막 추정기**가 가지는 메서드와 동일하다.

* 사이킷런은 pandas DataFrame을 직접 다룰 수 없으므로, 각 범주별 특성을 처리하는 변환기를 직접 만들어야 한다. 이후 전체 Pipeline에서는 `FeatureUnion`을 통해 변환기의 결과를 합쳐준다.

  > 실습 예제에서 생성한 Pipeline은 다음과 같다.
  >
  > * selector : 수치형인지, 문자열/범주형인지 선택.
  > * `CombinedAttributesAdder `: 열을 추가할 것인지, 아닌지 선택.
  > * `FeatureUnion`으로 합침.
  >
  > ```python
  > from sklearn.base import BaseEstimator, TransformerMixin
  > from sklearn.pipeline import Pipeline
  > from sklearn.pipeline import FeatureUnion
  > 
  > # selector
  > class DataFrameSelector(BaseEstimator, TransformerMixin):
  >     def __init__(self, attribute_names):
  >         self.attribute_names = attribute_names
  >     def fit(self, X, y=None):
  >         return self
  >     def transform(self, X):
  >         return X[self.attribute_names].values
  > 
  > # CombinedAttributesAdder
  > # column index
  > rooms_idx, bedrooms_idx, population_idx, household_idx = 3, 4, 5, 6
  > class CombinedAttributesAdder(BaseEstimator, TransformerMixin):
  >     def __init__(self, add_bedrooms_per_room=True):
  >         self.add_bedrooms_per_room = add_bedrooms_per_room
  >     def fit(self, X, y=None): # 변환할 y는 없고, 그냥 X에 대해서만 column 추가.
  >         return self
  >     def transform(self, X, y=None): # numpy array 반환
  >         rooms_per_household = X[:, rooms_idx] / X[:, household_idx]
  >         population_per_household = X[:, population_idx] / X[:, household_idx]
  >         if self.add_bedrooms_per_room:
  >             bedrooms_per_room = X[:, bedrooms_idx] / X[:, rooms_idx]
  >             return np.c_[X, rooms_per_household, population_per_household, bedrooms_per_room]
  >         else:
  >             return np.c_[X, rooms_per_household, population_per_household]
  > 
  > # 수치형 특성 pipeline
  > num_attribs = list(housing_num)
  > num_pipeline = Pipeline([
  >     ('selector', DataFrameSelector(num_attribs)),
  >     ('imputer', SimpleImputer(strategy="median")),
  >     ('attribs_adder', CombinedAttributesAdder()),
  >     ('std_scaler', StandardScaler())    
  > ])
  > 
  > # 범주형 특성 pipeline
  > cat_attribs = ["ocean_proximity"]
  > 
  > cat_pipeline = Pipeline([
  >     ('selector', DataFrameSelector(cat_attribs)),
  >     ('cat_encoder', CategoricalEncoder(encoding="onehot-dense")), 
  > ])
  > 
  > # 전체 pipeline
  > full_pipeline = FeatureUnion(transformer_list=[
  >     ("num_pipeline", num_pipeline),
  >     ("cat_pipeline", cat_pipeline),
  > ])
  > 
  > ```
  >
  > 변환기를 다음과 같이 실행한다.
  >
  > ```python
  > housing_prepared = full_pipeline.fit_transform(housing)
  > ```



* 다만, `ColumnTransformer`를 이용한다면, 범주별 특성을 선택하는 변환기와 `FeatureUnion` 없이도 간편하게 변환기를 생성할 수 있다.

  > 옮긴이가 소개한 방법은 다음과 같다.
  >
  > ```python
  > from sklearn.compose import ColumnTransformer
  > 
  > # 파이프라인 생성
  > num_attribs = list(housing_num)
  > cat_attribs = ["ocean_proximity"]
  > 
  > full_pipeline = ColumnTransformer([
  >     ("num_pipeline", num_pipeline, num_attribs),
  >     ("cat_pipeline",OneHotEncoder(categories="auto"), cat_attribs),
  > ])
  > 
  > # 파이프라인 실행
  > housing_prepared = full_pipeline.fit_transform(housing)
  > ```



* 변환기의 실행 결과 반환된 훈련 데이터를 알고리즘에 입력하여 훈련을 진행한다.





## 2.6. 모델 선택과 훈련



문제를 정의한 후, 데이터를 읽어 들이고 구조를 확인했다. 그리고 훈련 세트와 테스트 세트로 나누어 훈련 세트의 데이터를 탐색했다. 머신러닝 알고리즘에 주입할 데이터를 자동으로 정제하고 준비하기 위한 변환 파이프라인까지 작성했다. 

이제 머신러닝 모델을 선택하고 훈련시키면 된다.



**훈련 세트에서 훈련하고 평가하기**

다음과 같은 과정으로 진행한다.

* 모델을 만들어 훈련 세트로 학습시킨다.
* RMSE 등 성능지표를 통해 평가한다.

그러나, 이렇게 되면 과적합 문제가 나타날 수 있다. 훈련 데이터에서 나눠 놓은 테스트 세트는 마지막까지 절대 사용하지 않아야 하지만, 검증할 데이터가 없어 테스트 세트를 활용해야 하기 때문이다. 이렇게 된다면 테스트 세트에 맞춰지는 문제가 발생한다.



따라서 교차 검증을 사용해 훈련하고 평가한다.

### 1) 교차 검증을 사용한 평가

* 훈련 데이터를 훈련 세트와 테스트 세트로 나누고, 훈련 세트를 더 작은 훈련 세트와 검증 세트로 나눈다.

* 이 때, 훈련 세트를 k개의 서브셋으로 무작위 분할하고, 매번 (k-1)개의 폴드를 훈련에, 나머지 1개의 폴드를 평가에 사용해 검증하는 것이 교차 검증이다.

* 사이킷런의 `cross_val_score`을 사용해 구현한다.

  * `scoring : neg_mean_squared_error`

    사이킷런의 교차검증 기능은 scoring 매개변수로 효용 함수를 기대하므로, MSE의 반대를 계산하는 함수를 사용한다. RMSE를 구하고 싶을 경우, scoring의 결과에 (-) 부호를 붙이고, 제곱근을 씌운다.

  * `cv` : 교차검증 횟수.



### 2) 모델 저장

* `joblib`을 사용해 모델을 저장한다.

```python
from sklearn.externals import joblib

joblib.dump(my_model_RF, "my_model_RF.pkl")
load_my_model_RF = joblib.load("my_model_RF.pkl")
```



* 교차 검증 점수, 실제 예측값, 하이퍼파라미터, 훈련된 모델의 파라미터를 모두 저장한다.
* 이후 여러 모델의 점수와 오차를 비교한다.





한편, 위에서 만든 전처리 변환기와 예측에 사용하는 모델을 하나로 합쳐 파이프라인을 형성할 수도 있다.

```python
full_pipeline_with_RFmodel = Pipeline([
    ("preparation", full_pipeline),
    ("random_forest", RandomForestRegressor())
])

full_pipeline_with_RFmodel.fit(housing, housing_labels)
full_pipeline_with_RFmodel.predict(some_data)
```





## 2.7. 모델 세부 튜닝

하이퍼 파라미터를 탐색하거나, 앙상블 기법을 사용해 최상의 모델을 연결함으로써, 혹은 각 모델에 사용된 특성 중요도를 분석하고 특성 공학을 진행함으로써 모델을 세부적으로 튜닝할 수 있다.

앙상블 기법은 나중에 알아보고, 하이퍼파라미터를 탐색하는 방법과, 특성 중요도를 분석하는 방법을 알아 본다.



### 1) 하이퍼파라미터 탐색



#### 그리드 탐색

* 사이킷런 `GridSearchCV` 사용.
* 탐색하고자 하는 파라미터와 시도해볼 값을 지정.
* 가능한 모든 파라미터 조합에 대해 교차검증을 사용해 평가.

```python
from sklearn.model_selection import GridSearchCV

# 시도해볼 탐색
param_grid = [
    # 하이퍼파라미터  조합 = 15개, bootstrap True
    {'n_estimators': [100, 300, 500], 'max_features': [2,4,6,8,10]},
    # bootstrap은 False로 하고, 다시 조합을 시도한다.
    {'bootstrap': [False], 'n_estimators': [100, 500], 'max_features':[4,6,8]}
]

# 모델 객체
rf_model = RandomForestRegressor(random_state=42, verbose=1)

# 변수 탐색
grid_search = GridSearchCV(rf_model, param_grid, cv=10, scoring="neg_mean_squared_error",
                          return_train_score=True, n_jobs=-1, verbose=1)
grid_search.fit(housing_prepared, housing_labels)
```

* 다음의 메서드를 이용할 수 있다.

  * `.best_params_` : 최적의 하이퍼파라미터 조합.
  * `.best_estimator_` : 최적의 추정기.
  * `.cv_results_` : 평가 점수

  ```python
  cvres = grid_search.cv_results_
  
  for mean_score, params in zip(cvres["mean_test_score"], cvres["params"]):
      print(np.sqrt(-mean_score), params)
  ```

  

#### 랜덤 탐색

* 탐색 공간이 커져서 그리드 탐색을 적용하기 어려울 때 사용한다.
* 반복 횟수와 파라미터를 선택할 범위를 지정하면, 각 반복마다 임의의 수를 대입하여 지정한 횟수만큼 평가한다.
* 장점
  * 하이퍼파라미터마다 각기 다른 반복 횟수만큼의 값을 탐색한다.
  * 반복 횟수를 조절함으로써 컴퓨팅 자원을 제어할 수 있다.

```python
from sklearn.model_selection import RandomizedSearchCV
from scipy.stats import randint

param_distribs = {
    'n_estimators': randint(low=500, high=1000),
    'max_features': randint(low=1, high=8),
}

rf_model = RandomForestRegressor(random_state=42, verbose=1)
rnd_search = RandomizedSearchCV(rf_model, param_distributions=param_distribs,
                               n_iter=20, cv=10, scoring="neg_mean_squared_error",
                               random_state=42, n_jobs=-1,
                               verbose=1)
rnd_search.fit(housing_prepared, housing_labels)
```



### 2) 특성 중요도 분석

얻어 낸 최상의 모델에서 특성 중요도를 분석한다.

```python
feature_importances = grid_search.best_estimator_.feature_importances_
```





## 2.8. 런칭, 모니터링, 시스템 유지 보수

* 입력 데이터 소스를 시스템에 연결하고, 테스트 코드를 작성한다.
* 시스템의 성능을 체크하기 위해, 성능을 체크하는 코드와, 성능이 떨어질 때 알람을 통지하는 모니터링 코드를 작성한다.
* 시스템의 성능을 평가하기 위해 예측을 샘플링해서 평가한다.
* 시스템에 입력되는 데이터의 품질을 모니터링한다.
* 새로운 데이터를 사용해 정기적으로 모델을 훈련시킨다.

















---

# 실습

## 캘리포니아 주택 가격 예측 모델

>  실습 진행 파일 : [ae13655](https://github.com/sirzzang/Hands-on-Machine-Learning/blob/master/handon-ml-chap2-ML_endtoend_housing.ipynb)



* 히스토그램에서 중간 주택 연도, 중간 주택 가격에 이상치가 많은 줄 알았다. 알고 보니 상한값을 설정한 것이었다.

* 상관계수의 절대값은 중요하지 않다.

* RandomForest 모델 실습 진행 시, n_estimators를 100 이상으로 했더니 책에서보다 더 좋은 결과가 나왔다. 그렇지만, 그것도 아주 좋은 수준이라고까지는 할 수 없어 보인다.

  



---

# 배운 점

* 모든 단계에서 **판단**이 중요하다. 그러나 이 판단은 절대 혼자 진행해서는 안 된다. 같은 팀원, 다른 팀과 협업하고, domain 지식을 적용해야 한다면 전문가의 조언을 구해야 한다.
  * 문제를 정의하고, 현재 솔루션은 무엇이 있는지, 어떻게 활용될 것인지와 같은 큰 그림을 그리는 것뿐만 아니라, 중요한 특성을 선택하고, 결측치나 이상치를 처리하는 과정에 있어서 올바른 판단을 내려야 한다. 그렇지 않다면 머신러닝 시스템의 성능이 떨어지게 된다.
  * 그러나 이 판단은 혼자 진행해서는 안 된다. 반드시 다른 팀과 협업하고, 모든 단계별로 가정이나 작업 상황을 나열하며 팀원들과  진행 방향을 설정해야 한다. 한편 domain , 전문가의 조언을 구해야 한다.
* 가장 중요한 것은 통찰, 통찰, 통찰이다!!!!!!!!! 시각화, 데이터 탐색을 충분히 진행하며 데이터로부터 의미 있는 분석을 이끌어내고 싶다. 어쩌면, 알고리즘보다도 더 중요한 것이라 판단된다.

* 스파크 수업 때 변환기, 추정기에 대해 공부했다. 강사님께 사이킷런의 Pipeline에 대해 질문했었는데, 스파크와 크게 다르지 않을 것이라는 답을 들었다. 오늘 드디어 그 대답이 어떤 의미인지 깨달았다!
* 전체 과정을 훑고 나니, 이전에 내가 공모전을 진행하면서 알고리즘 하나 하나에 몰두했던 게, 그리고 알고리즘을 통해 결과를 내지 못해 무력함을 느꼈던 것이 얼마나 어리석었는지 깨닫는다. 이번에 참여하는 공모전에서는 **전체적인 과정**을 조망하면서, 그리고 **각 과정을 함수와 파이프라인을 통해 자동화**하면서 진행할 것이다.



---

# 더 공부하고 싶은 것

* 무엇보다 matplotlib 패키지를 파고들고 싶다.
* 캘리포니아 예제에서, "군집 알고리즘을 사용해 주요 군집을 찾고, 군집 중심가지의 거리를 재는 특성을 추가할 수 있다."고 했는데, 어떻게 할 수 있을까?
* 변환기, 추정기에 대해 더 궁금하다면 [강의 내용](), 그리고 [여기]()를 참고하자.
  * 사이킷런, 스파크의 개념이 겹치는 듯한 느낌인데, 연결고리가 있을까?
* 사이킷런의 설계 방식(p.101) 및 그 참고문헌이 있다. 계속해서 다시 읽으며 변환기, 추정기에 대해 이해하자.
* 본격적으로 객체가 등장한다. 상속, 다형성, duck type 등 이전에 미뤄 놓았던 개념을 보고 공부해야 할 것 같다. 일단 책에서는 두루뭉술한 개념만 가지고 이해하는 수준으로 넘어갔지만, 다시 공부한 뒤 돌아오자.



