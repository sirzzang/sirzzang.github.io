---
title:  "[NLP] Transformers 라이브러리 사용하기"
excerpt: "이제 HuggingFace Transformers 라이브러리를 Keras Functional API처럼 사용할 수 있다!"
toc: true
toc_sticky: true
permalink: /ai/AI-huggingface-keras/
categories:
  - ai-llm
  - study
tags:
  - 자연어처리
  - NLP
  - Transformers
  - Keras

last_modified_at: 2020-08-19
---

<sup>출처 : [huggingface.co/transformers](https://huggingface.co/transformers)</sup>

<br>

# _더 편해진 HuggingFace Transformers_



<br>

 HuggingFace의 Transformers 트랜스포머 기반의 모델들을 쉽게 사용할 수 있도록 해 놓았다. 예전에 프로젝트할 때도 유용하게 썼었는데, 그 때에는 PyTorch로만 사용할 수 있었다. 그런데 이제는 **Tensorflow 2.x 버전에서, 특히나 사전학습된 모델을 Keras 모델처럼** 사용할 수 있다! 



> *참고* 
>
> * **Models** are standard [torch.nn.Module](https://pytorch.org/docs/stable/nn.html#torch.nn.Module) or [tf.**keras**.Model](https://www.tensorflow.org/api_docs/python/tf/keras/Model) so you can use them in your usual training loop. 🤗 
> * **Model classes** such as [`BertModel`](https://huggingface.co/transformers/model_doc/bert.html#transformers.BertModel), which are 30+ PyTorch models ([torch.nn.Module](https://pytorch.org/docs/stable/nn.html#torch.nn.Module)) or Keras models ([tf.keras.Model](https://www.tensorflow.org/api_docs/python/tf/keras/Model)) that work with the pretrained weights provided in the library.



사전학습한 모델을 불러 와서, Keras의 *functional API*처럼 컴파일하고, 훈련시킬 수 있다.

 [이 글](https://towardsdatascience.com/working-with-hugging-face-transformers-and-tf-2-0-89bf35e3555a)을 참고하여, 어떻게 HuggingFace의 Transformers 라이브러리를 Keras 모델처럼 사용할 수 있는지 정리해 본다.

 <br>



## 1. 개요



 기본적으로 Transformers 라이브러리의 모델을 사용할 때 적용되는 큰 작업 흐름은 모두 동일하다. 사전학습된 모델로부터 토크나이저를 불러 와 문서를 토크나이징하고, 사전학습된 모델을 불러온 뒤 그 출력인 임베딩을 활용해 파인튜닝하면 된다.

<br>

### Tokenizer

 토크나이저를 불러 오고, `encode` 메소드를 사용하면 바로 사전학습된 모델의 `word2idx`에 따라 인코딩된 수치 벡터가 나온다. BERT 모델에서 한국어는 `bert-base-multilingual-cased` 모델에 사전 학습되어 있으므로, 해당 모델의 이름을 인자로 넘긴다. 사전학습된 모델의 어휘집에 무엇이 있는지 알고 싶다면, `get_vocab()` 메소드를 사용한다. 

```python
# 토크나이저 설정
tokenizer = BertTokenizer.from_pretrained('bert-base-multilingual-cased')

# 어휘집 생성
word2idx = tokenizer.get_vocab()
idx2word = {idx:word for idx, word in enumerate(word2idx)}

# 데이터 예시 확인
for idx in tokenizer.encode('뭐야 이 평점들은 나쁘진 않지만 점 짜리는 더더욱 아니잖아'):
    print(idx2word[idx], end=' ')
```



 전처리한 데이터를 토크나이저로 인코딩하고, 어휘집에서 인덱스를 찾아 결과를 확인한다. 다음과 같이 special token과 wordpiece 토크나이징된 모습을 확인할 수 있다.

```python
[CLS] 뭐 ##야 이 평 ##점 ##들은 나 ##쁘 ##진 않 ##지만 점 짜 ##리는 더 ##더 ##욱 [UNK] [SEP] 
```

<br>

 토크나이저에 파라미터로 `padding`, `truncating` 등의 옵션을 줄 수 있다. 별도의 전처리를 거치지 않아도 한 번에 문장의 길이를 맞출 수 있어 편리하다. `return_tensors` 옵션을 사용하면 Pytorch 혹은 Tensorflow 형태의 텐서로 인코딩한다. 결과로는 dictionary가 반환된다. 주로 사용할 것은 `input_ids`, `token_type_ids`, `attention_mask` 등이므로, 해당 키를 사용하면 된다.

```python
# 인코딩
train_encoded = tokenizer(train_sentences, padding=True, truncation=True, max_length=MAX_SEQUENCE_LEN, return_tensors='tf')

# 인코딩된 문장
X_train = train_encoded['input_ids']

# attention mask
X_train_masks = train_encoded['attention_mask']

# 데이터 예시
print(X_train[0]) # 인코딩된 문장
print(tokenizer.decode(X_train[0])) # 디코딩
```

 인코딩된 결과 텐서와 그것을 디코딩한 결과를 확인하면 다음과 같다.

```python
tf.Tensor(
[   101   9519   9074 119005   9708 119235   9715 119230  16439  77884
  48549   9284  22333  12692    102      0      0      0      0      0
      0      0      0      0      0      0      0      0      0      0
      0      0      0      0      0      0      0      0      0      0
      0      0      0      0      0      0      0      0      0      0
      0      0      0      0      0      0      0      0      0      0
      0      0      0      0], shape=(64,), dtype=int32)
[CLS] 아 더빙 진짜 짜증나네요 목소리 [SEP] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD] [PAD]
```



<br>

### Model



 HuggingFace가 이미 Transformers 라이브러리에 **각 목적에 맞는, 언어 모델**을 구현해 놓았다. 분류 모델을 예로 들면, `BertForSequenceClassification`(*BERT*), `AlbertForSequenceClassification`(*ALBERT*) 와 같은 식이다. 각 언어 모델 및 목적을 선택하는 것은 documentation을 참고하면 된다.  Pytorch와 Tensorflow에서 모두 활용할 수 있는데, Tensorflow 라이브러리에서 사용할 수 있는 모델의 이름에는 `TF`가 붙는다. `TFBertForSequenceClassification`과 같은 식이다.

 사전학습된 모델을 불러 올 때  모델 설정을 위해 `Config`를 인자로 넘긴다. 모델을 사용하는 목적에 따라 다르므로, 이 역시 documentation을 참고하면 된다.  BERT 모델은 `logits` (로짓 값)을 반환한다.

```python
# 분류 모델 config 설정
my_config = BertConfig.from_pretrained(
    'bert-base-multilingual-cased',
    num_labels=2,
    output_hidden_states=False,
    output_attentions=False
)

# 사전학습 모델 불러오기
bert_model = TFBertForSequenceClassification.from_pretrained('bert-base-multilingual-cased', config=my_config)
```



<br>

## 2. Keras에서 모델 사용하기



 업데이트된 Transformers 라이브러리에서 가장 마음에 드는 부분이다. `TF`가 붙어서 Tensorflow 버전으로 사용할 수 있는 모델은 `tf.keras.Model` 클래스를 상속받는다. Keras에서 모델을 설정하고 커스텀하는 방식을 그대로 사용할 수 있다. 

 언어 모델에서 임베딩 레이어 활용, 네트워크 구성 등에 따라, 크게 사용법을 다음과 같이 **세 가지**로 정리해 보았다. 네이버 영화 감성분석을 수행하는 모델을 만들어 보자. (전처리는 이미 진행했다고 가정한다.)

<br>

### 바로 사용하기

 가장 쉬운 사용법이다. 사전학습된 BERT 모델을 불러와 바로 임베딩으로 사용한 뒤, Dense 층만 얹는다.

```python
# 모델 네트워크 설정
input_ids = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='input_ids')
input_masks = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='attention_masks')
embedding = bert_model([input_ids, input_masks])[0] # logit값 반환
y_output = Dense(1, activation='sigmoid')(embedding) # sigmoid: 이진 분류

# 모델 구성 및 컴파일
model = Model(inputs=[input_ids, attention_masks], outputs=output, name='Bert_Classification_1')
model.compile(optimizer=Adam(learning_rate=0.0001),
              loss='binary_crossentropy',
              metrics=['acc'])
```



 모델 전체 구조를 확인하면 다음과 같다. 

![UseDirectly]({{site.url}}/assets/images/huggingface1.svg){: width="500"}{: .align-center}



```python
Model: "Bert_Classification"
__________________________________________________________________________________________________
Layer (type)                    Output Shape         Param #     Connected to                     
==================================================================================================
input_ids (InputLayer)          [(None, 64)]         0                                            
__________________________________________________________________________________________________
attention_masks (InputLayer)    [(None, 64)]         0                                            
__________________________________________________________________________________________________
tf_bert_for_sequence_classifica ((None, 2),)         177854978   input_ids[0][0]                  
                                                                 attention_masks[0][0]            
__________________________________________________________________________________________________
dense (Dense)                   (None, 1)            3           tf_bert_for_sequence_classificati
==================================================================================================
Total params: 177,854,981
Trainable params: 177,854,981
Non-trainable params: 0
__________________________________________________________________________________________________
None
```

<br>

### Embedding 레이어 추출 후 사용하기

 사전학습된 BERT 모델에서 latent feature로서의 임베딩 레이어만 추출하여 사용한다. Keras에서 Embedding 레이어를 사전학습하였을 때, `trainable=False` 옵션을 주었던 것을 상기하면 된다. 입력 및 임베딩에 대한 train 설정을 해제하면 된다. 이후 층은 자유롭게 구성한다.

```python
# 입력층
input_ids = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='input_ids')
input_masks = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='attention_masks')

# latent feature 추출
embedding = bert_model(input_ids, attention_mask=input_masks)[0]
cls_tokens = embedding[:, 0, :]

# train 해제
input_ids.trainable = False
input_masks.trainable = False
embedding.trainble = False

# 층 쌓기
X_latent = BatchNormalization()(cls_tokens)
X_dense = Dense(192, activation='relu')(X_latent)
X_dense = Dropout(0.3)(X_dense)
y_output = Dense(1, activation='sigmoid')(X_dense)

# 모델 구성 및 컴파일
model = Model(inputs=[input_ids, input_masks], outputs=y_output, name='Bert_Classification_2')
model.compile(optimizer=Adam(learning_rate=3e-5),
              loss='binary_crossentropy',
              metrics=['acc'])
```



모델 전체 구조를 확인하면 다음과 같다. 

![latentExtract]({{site.url}}/assets/images/huggingface2.svg){: width="500"}{: .align-center}

```python
Model: "Bert_Classification_2"
__________________________________________________________________________________________________
Layer (type)                    Output Shape         Param #     Connected to                     
==================================================================================================
input_ids (InputLayer)          [(None, 64)]         0                                            
__________________________________________________________________________________________________
attention_masks (InputLayer)    [(None, 64)]         0                                            
__________________________________________________________________________________________________
tf_bert_model (TFBertModel)     ((None, 64, 768), (N 177853440   input_ids[0][0]                  
                                                                 attention_masks[0][0]            
__________________________________________________________________________________________________
tf_op_layer_strided_slice (Tens [(None, 768)]        0           tf_bert_model[6][0]              
__________________________________________________________________________________________________
batch_normalization (BatchNorma (None, 768)          3072        tf_op_layer_strided_slice[0][0]  
__________________________________________________________________________________________________
dense (Dense)                   (None, 192)          147648      batch_normalization[0][0]        
__________________________________________________________________________________________________
dropout (Dropout)               (None, 192)          0           dense[0][0]                      
__________________________________________________________________________________________________
dense_1 (Dense)                 (None, 1)            193         dropout[0][0]                    
==================================================================================================
Total params: 178,004,353
Trainable params: 178,002,817
Non-trainable params: 1,536
__________________________________________________________________________________________________
None
```





<br>

### Embedding 레이어 추출 후 Fine-Tune

 Embedding 레이어를 추출한 후, 해당 Embedding 레이어에 또 다른 네트워크를 적용하여 *Fine-Tuning* 과정을 거칠 수도 있다. 

```python
# 입력층
input_ids = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='input_ids')
input_masks = Input(batch_shape=(None, MAX_SEQUENCE_LEN), dtype=tf.int32, name='attention_masks')

# latent feature 추출
embedding = bert_model(input_ids, attention_mask=input_masks)[0]

# train 해제
input_ids.trainable = False
input_masks.trainable = False
embedding.trainble = False

# embedding layer fine-tune
X_embed = Bidirectional(LSTM(50, return_sequences=True, dropout=0.1, recurrent_dropout=0.1))(embedding)
X_embed = GlobalMaxPool1D()(X_embed)  

# 층 쌓기
X_latent = BatchNormalization()(X_embed)
X_dense = Dense(192, activation='relu')(X_latent)
X_dense = Dropout(0.3)(X_dense)
y_output = Dense(1, activation='sigmoid')(X_dense)

# 모델 구성 및 컴파일
model = Model(inputs=[input_ids, input_masks], outputs=y_output, name='Bert_Classification_2')
model.compile(optimizer=Adam(learning_rate=3e-5),
              loss='binary_crossentropy',
              metrics=['acc'])
```



모델 전체 구조를 확인하면 다음과 같다. 

![latentExtractFineTune]({{site.url}}/assets/images/huggingface3.svg){: width="500"}{: .align-center}

```python
Model: "Bert_Classification_2"
__________________________________________________________________________________________________
Layer (type)                    Output Shape         Param #     Connected to                     
==================================================================================================
input_ids (InputLayer)          [(None, 64)]         0                                            
__________________________________________________________________________________________________
attention_masks (InputLayer)    [(None, 64)]         0                                            
__________________________________________________________________________________________________
tf_bert_model (TFBertModel)     ((None, 64, 768), (N 177853440   input_ids[0][0]                  
                                                                 attention_masks[0][0]            
__________________________________________________________________________________________________
bidirectional (Bidirectional)   (None, 64, 100)      327600      tf_bert_model[0][0]              
__________________________________________________________________________________________________
global_max_pooling1d (GlobalMax (None, 100)          0           bidirectional[0][0]              
__________________________________________________________________________________________________
batch_normalization (BatchNorma (None, 100)          400         global_max_pooling1d[0][0]       
__________________________________________________________________________________________________
dense (Dense)                   (None, 192)          19392       batch_normalization[0][0]        
__________________________________________________________________________________________________
dropout (Dropout)               (None, 192)          0           dense[0][0]                      
__________________________________________________________________________________________________
dense_1 (Dense)                 (None, 1)            193         dropout[0][0]                    
==================================================================================================
Total params: 178,201,025
Trainable params: 178,200,825
Non-trainable params: 200
__________________________________________________________________________________________________
None
```

<br>

### 모델 훈련 및 예측

 `model.fit`, `model.predict`와 같이 Keras 방식대로 모델을 훈련하면 된다. 다만, 입력 층에 인자로 `input_id`와 `mask`를 함께 넘겨 주어야 한다. (* 아주 당연하겠지만, 만약 `token_type_ids`가 있다면 이 역시 넘겨 주도록 모델을 구성해야 한다.*)

```python
# 훈련
hist = model.fit([X_train, X_train_masks], y_train,
                 validation_data=([X_test, X_test_masks], y_test),
                 batch_size=128,
                 epochs=3,
                 shuffle=True)

# 예측
y_pred = model.predict([X_test, X_test_masks])
y_pred = np.where(y_pred > 0.5, 1, 0).reshape(-1, 1)
print('Accuracy = %.4f' % np.mean(y_test == y_pred))
```

