---
title:  "[PostgreSQL] 재귀 쿼리"
excerpt: 재귀 쿼리를 이용해 상향식, 하향식, 트리 탐색을 할 수 있다.
toc: true
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - PostgreSQL
  - Recursive
---

기능을 구현하다 재귀 쿼리를 사용하게 되어 정리한다.

<br>

# 개요

운영 중인 시스템에서 다루는 리소스는 다른 리소스로부터 파생될 수 있다. 베이스 리소스를 기점으로 해서 `베이스 리소스 → 파생 리소스 1 → 파생 리소스 2 → ...`와 같은 체인을 형성할 수 있다는 의미이다. 이를 위해 리소스 테이블은 아래와 같은 자기 참조 구조로 설계되어 있다.

```sql
CREATE TABLE resource (
    id BIGINT PRIMARY KEY,
    name VARCHAR(255),
    parent_id BIGINT,
    FOREIGN KEY (parent_id) REFERENCES resource(id)
);
```

> 참고: 자기 참조와 순환 참조
>
> 위의 테이블 구조만 놓고 보면, 테이블이 자기 자신을 참조하는 것 같아, 이거 뭔가 순환 참조 아닌가 하는 생각이 들 수 있지만, 엄연히 다르다.
>
> * 순환 참조: 여러 테이블이 체인처럼 서로를 참조하다가 다시 처음 테이블로 돌아오는 것
> * 자기 참조: 테이블 한 행이 같은 테이블의 다른 행을 참조하는 것
>
> 자기 참조의 경우, 계층 구조를 표현하는 표준적인 방법으로, 대부분의 RDBMS에서 지원된다. 표현할 수 있는 관계 예시로는 아래와 같은 것들이 있다.
>
> * 조직도: 직원 → 상사
> * 카테고리 트리: 하위 카테고리 → 상위 카테고리
> * 파일: 폴더 → 상위 폴더



<br>

이런 자기 참조 테이블에서, 재귀 쿼리를 이용하면 리소스 체인 혹은 리소스 트리 조회를 쉽게 할 수 있다. PostgreSQL 기준으로, 재귀 쿼리를 어떻게 사용할 수 있는지 알아 보자.



<br>

# 재귀 쿼리

아래와 같이 쿼리를 작성하면 된다. CTE가 쿼리 내에서 반복 실행되는 구조다.

```sql
WITH RECURSIVE cte_name AS (
    -- 1. Base Case: 재귀의 시작점
    SELECT ... WHERE 조건
    
    UNION ALL
    
    -- 2. Recursive Case: 반복 부분
    SELECT ... 
    FROM 원본테이블
    JOIN cte_name ON ...  -- 자기 자신(CTE)을 참조!
)
SELECT * FROM cte_name;
```

> 참고: [CTE(Common Table Expression)](http://postgresql.org/docs/current/queries-with.html)
>
> - 더 큰 쿼리에서 사용되기 위한 보조 구문으로, 하나의 쿼리를 위해 필요한 임시 결과 집합
> - 임시 결과 집합에 이름을 붙인 것

<br>

루트 리소스의 id가 1이라고 할 때, 루트 리소스로부터 이어지는 리소스 체인을 찾는 쿼리는 아래와 같이 작성할 수 있다.

```sql
WITH RECURSIVE resource_tree AS (
		-- 1. Base: 루트 리소스
		SELECT
				id,
				name,
				parent_id,
				0 AS depth -- 시작은 depth 0
		FROM resource
		WHERE id = 1 -- 리소스 id 1에서 시작
		
		UNION ALL
		
		-- 2~N. Recursive: 자식 찾기
		SELECT 
				r.id,
				r.name,
				r.parent_id,
				rt.depth + 1 -- 이전 depth + 1
		FROM resource r
		JOIN resource_tree rt ON r.parent_id = rt.id -- 이전 결과와 조인
) 
SELECT * FROM resource_tree
ORDER BY depth ASC, id ASC;
```





<br>

아래와 같은 데이터가 있다고 가정하자.

```sql
-- resource(id, name, parent_id)
resource(1, 'resource-a', NULL) 
resource(3, 'resource-b', 1)
resource(4, 'resource-c', 3)
resource(5, 'resource-d', 1)
```

그러면, 아래와 같은 과정을 거쳐,

* 1회차 실행
  * `(id = 1, depth = 0)`인 것 찾음
* 2회차 실행
  * resource_tree에 `(id = 1, depth = 0)` 있음 → 다음 JOIN 시 사용되는 id
  * parent_id = 1인 것 찾기 → `(id = 3, depth = 1)`, `(id = 5, depth = 1)` 추가
* 3회차 실행
  * resource_tree에 `(id = 3, depth = 1)`, `(id = 5, depth = 1)` 있음
  * parent_id = 3인 것 찾기 → `(id = 4, depth 2)` 추가
* 4회차 실행
  * resource_tree에 `(id = 4, depth 2)` 있음
  * parent_id = 4인 것 찾기 → 없음
  * 종료

아래와 같은 결과를 얻게 된다.

```sql
id | name       | depth
1  | resource-a | 0
3  | resource-b | 1
5  | resource-d | 1
4  | resource-c | 2
```

<br>







# 동작 원리

쿼리 실행 핵심은 다음과 같다.

* depth 증가: `rt.depth + 1` 로 각 재귀 단계마다 depth 증가

* 종료 조건: 더 이상 JOIN되는 행이 없으면 자동 종료

* `UNION ALL`: 여러 쿼리문을 합쳐서 하나의 쿼리문으로 만들어 줌 → Base Case와 Recursive Case의 결과를 **모두 포함**하게 됨

  > 참고: `UNION` vs. `UNION ALL`
  >
  > * UNION의 경우, 중복 체크를 위한 정렬 및 비교 과정이 들어가서 느림
  > * 재귀 쿼리의 경우, 하나의 트리 구조에서 한 리소스는 한 번만 나타나기 때문에, 중복 체크는 불필요한 오버헤드임
  > * 따라서 UNION ALL을 사용하는 것이 일반적



`UNION ALL`을 통해 모든 쿼리 결과를 위아래로 합쳐 주는 게 핵심인데, 살펴 보면 다음과 같다.

**1회차 실행(Base Case)**

| id   | name       | depth |
| ---- | ---------- | ----- |
| 1    | resource-a | 0     |

**2회차 실행(Recursive)**

| id   | name       | depth |
| ---- | ---------- | ----- |
| 3    | resource-b | 1     |
| 5    | resource-d | 1     |

**3회차 실행(Recursive)**

| id   | name       | depth |
| ---- | ---------- | ----- |
| 4    | resource-c | 2     |

**최종 결과(UNION ALL 병합)**

| id   | name       | depth |
| ---- | ---------- | ----- |
| 1    | resource-a | 0     |
| 3    | resource-b | 1     |
| 5    | resource-d | 1     |
| 4    | resource-c | 2     |

<br>

# 활용

시작 레코드와 JOIN 조건만 바꾸면, 상향, 하향 탐색이 가능하다.

* 하향식 탐색
* 상향식 탐색

<br>

## 하향식 탐색

특정 리소스의 모든 자식 리소스를 찾기 위해, 아래와 같은 쿼리를 사용하면 된다.

```sql
WITH RECURSIVE tree AS (
    SELECT id, name, parent_id, 0 AS depth
    FROM resource
    WHERE id = 1  -- 부모(루트)에서 시작
    
    UNION ALL
    
    SELECT r.id, r.name, r.parent_id, tree.depth + 1
    FROM resource r
    JOIN tree ON tree.id = r.parent_id -- tree의 각 행에 대해, resource에서 그것을 부모로 가진 행을 찾음 
)
SELECT * FROM tree;
```



<br>

## 상향식 탐색

특정 리소스의 모든 부모 리소스를 탐색할 때, 아래와 같은 쿼리를 사용하면 된다.

```sql
WITH RECURSIVE tree AS (
    SELECT id, name, parent_id, 0 AS depth
    FROM resource
    WHERE id = 4  -- 자식(리프)에서 시작
    
    UNION ALL
    
    SELECT r.id, r.name, r.parent_id, tree.depth + 1
    FROM resource r
    JOIN tree ON tree.parent_id = r.id -- tree의 각 행에 대해, 그것이 resource의 부모가 되는 행을 찾음
)
SELECT * FROM tree;
```



<br>

말장난 같아 이해하기 힘들 수도 있는데, CTE tree를 나라고 생각하고 보면 좀 이해할 수 있다. 내가 리소스의 부모가 되느냐, 내 부모가 리소스가 되느냐의 차이(?)이다.

| 요소               | 하향식                   | 상향식                   |
| ------------------ | ------------------------ | ------------------------ |
| **시작점 (WHERE)** | `WHERE id = 1` (부모)    | `WHERE id = 4` (자식)    |
| **JOIN 조건**      | `tree.id = r.parent_id`  | `tree.parent_id = r.id`  |
| **의미**           | "자식의 부모가 나"       | "나의 부모가 상대방"     |



<br>

## 트리 탐색

상향식 탐색과 하향식 탐색을 응용하면, 특정 리소스 id를 가지고 트리 탐색도 가능하다.

```sql
WITH RECURSIVE 
-- 조상 찾기 (위로 올라가기)
ancestors AS (
    SELECT 
        id, 
        name, 
        parent_id,
        0 AS depth  -- 시작점은 0
    FROM resource
    WHERE id = $1
    
    UNION ALL
    
    SELECT 
        r.id,
        r.name,
        r.parent_id,
        a.depth - 1  -- 위로 갈수록 depth 줄이기: -1, -2, -3, ...
    FROM resource r
    JOIN ancestors a ON a.parent_id = r.id  -- 부모 찾기
),
-- 후손 찾기 (아래로 내려가기)
descendants AS (
    SELECT 
        id,
        name,
        parent_id,
        0 AS depth  -- 시작점은 0
    FROM resource
    WHERE id = $1
    
    UNION ALL
    
    SELECT 
        r.id,
        r.name,
        r.parent_id,
        d.depth + 1  -- 아래로 갈수록 depth 늘리기: +1, +2, +3, ...
    FROM resource r
    JOIN descendants d ON d.id = r.parent_id  -- 자식 찾기
)
-- 합치기
SELECT DISTINCT 
    id,
    name,
    parent_id,
    depth
FROM (
    SELECT * FROM ancestors
    UNION
    SELECT * FROM descendants
) AS full_tree
ORDER BY depth ASC, id ASC; 
```



<br>

# 주의

재귀 쿼리를 사용할 때, 아래의 점에 주의하면 좋다.

- 인덱스 사용: 재귀 탐색 시 JOIN 대상이 되는 컬럼에 인덱스 생성
- 깊이 제한: 무한 루프 방지
  - `WHERE depth < 10` 등 최대 깊이 제한
- 순환 참조 방지

<br>

## 순환 참조

데이터에 순환 구조가 있으면 재귀 쿼리는 무한 루프에 빠져 버리게 된다.

> 위에서 말한 테이블의 순환 참조 구조와는 다른 의미의 순환 참조이다!

<br>

예컨대 아래와 같은 데이터가 있는 경우다.

```sql
(1, 'resource-a', 2),  -- 1의 부모가 2
(2, 'resource-b', 3),  -- 2의 부모가 3
(3, 'resource-c', 1);  -- 3의 부모가 1 
```

재귀 쿼리를 실행하면, 불행히도 무한 루프에 빠진다.

```sql
1회차: id=1, depth=0
2회차: id=2, depth=1
3회차: id=3, depth=2
4회차: id=1, depth=3
5회차: id=2, depth=4
6회차: id=3, depth=5
7회차: id=1, depth=6
```



<br>

순환 참조를 막기 위한 방법으로 아래와 같은 것들이 있음을 알아 두자.

- 쿼리 깊이 제한

  ```sql
  WITH RECURSIVE tree AS (
      SELECT id, name, parent_id, 0 AS depth
      FROM resource WHERE id = 1
      
      UNION ALL
      
      SELECT r.id, r.name, r.parent_id, tree.depth + 1
      FROM resource r
      JOIN tree ON tree.id = r.parent_id  -- 하향식 탐색
      WHERE tree.depth < 10  -- 최대 10단계
  )
  SELECT * FROM tree;
  ```

- PostgreSQL CYCLE 옵션: PostgreSQL 14 이상만 지원됨

  ```sql
  WITH RECURSIVE tree AS (
      SELECT id, name, parent_id, 0 AS depth
      FROM resource WHERE id = 1
      
      UNION ALL
      
      SELECT r.id, r.name, r.parent_id, tree.depth + 1
      FROM resource r
      JOIN tree ON tree.parent_id = r.id
  )
  CYCLE id SET is_cycle USING path  -- 순환 감지
  SELECT * FROM tree
  WHERE NOT is_cycle;  -- 순환 발생 전까지만
  ```

- 방문한 노드 추적: ~~그래프 탐색할 때 나오는 `visited` 와 닮은 방식~~

  ```sql
  WITH RECURSIVE tree AS (
      SELECT 
          id, 
          name, 
          parent_id,
          ARRAY[id] AS path,  -- 경로 추적
          0 AS depth
      FROM resource WHERE id = 1
      
      UNION ALL
      
      SELECT 
          r.id,
          r.name,
          r.parent_id,
          path || r.id,  -- 경로에 추가
          tree.depth + 1
      FROM resource r
      JOIN tree ON tree.parent_id = r.id
      WHERE NOT (r.id = ANY(tree.path))  -- 이미 방문한 노드면 제외
  )
  SELECT * FROM tree;
  ```

<br>

애초에, 어플리케이션 레벨에서 **자기 참조 컬럼 값을 설정할 때**, 순환 참조가 발생하는지 확인하는 것도 답이다.

```go
func (r *Repository) CreateResource(req *CreateResourceRequest) (*domain.Resource, error) {
    // parent 설정하려고 한다면 순환 체크
    if req.ParentID != nil {
        if err := r.validateParentChain(*req.ParentID); err != nil {
            return nil, fmt.Errorf("invalid parent: %w", err)
        }
    }
    
    // INSERT 쿼리 실행
    query := `
        INSERT INTO resource (name, parent_id, type, ...)
        VALUES ($1, $2, $3, ...)
        RETURNING id
    `
    var newID int64
    err := r.db.QueryRow(query, req.Name, req.ParentID, req.Type).Scan(&newID)
    // ...
}

// 부모 체인이 유효한지 체크 (순환 없는지)
func (r *Repository) validateParentChain(parentID int64) error {
    visited := make(map[int64]bool)
    currentID := parentID
    
    for currentID != 0 {
        if visited[currentID] {
            return errors.New("parent chain has circular reference")
        }
        visited[currentID] = true
        
        var nextParentID sql.NullInt64
        err := r.db.QueryRow(
            "SELECT parent_id FROM resource WHERE id = $1",
            currentID,
        ).Scan(&nextParentID)
        
        if err != nil {
            return fmt.Errorf("parent resource not found: %w", err)
        }
        
        if !nextParentID.Valid {
            break
        }
        currentID = nextParentID.Int64
    }
    
    return nil
}
```



<br>



# 결론

- 자기 참조와 재귀 쿼리를 잘 이용하면, DB 쿼리만으로 트리 탐색을 쉽게 할 수 있다! 어플리케이션 코드에서 힘들게 연결하지 않아도 된다.
- 보다 보니까 드는 생각인데, 그래프 탐색과 참 닮았다. 순환 참조 방지하려면 방문 체크를 해야 한다는 것까지..!
