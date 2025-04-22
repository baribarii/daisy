import logging
from db_utils import (
    save_blog_post, 
    get_blog_post, 
    list_all_posts, 
    delete_blog_post, 
    get_total_post_count,
    clear_all_posts
)

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_db_operations():
    """
    Replit DB의 블로그 포스트 저장 및 조회 기능을 테스트합니다.
    """
    print("=== Replit DB 블로그 포스트 저장 테스트 ===")
    
    # 테스트 데이터
    test_posts = [
        {
            "id": "223123456789",
            "title": "테스트 포스트 1",
            "content": "이것은 첫 번째 테스트 포스트입니다.",
            "date": "2025-04-22",
            "is_private": False
        },
        {
            "id": "223987654321",
            "title": "테스트 포스트 2",
            "content": "이것은 두 번째 테스트 포스트입니다. 비공개 글입니다.",
            "date": "2025-04-23",
            "is_private": True,
            "tags": ["테스트", "예제", "Replit"]  # 추가 메타데이터
        }
    ]
    
    # 테스트 전 기존 데이터 확인
    initial_count = get_total_post_count()
    print(f"테스트 전 DB에 저장된 포스트 수: {initial_count}")
    
    # 1. 포스트 저장 테스트
    print("\n1. 포스트 저장 테스트:")
    for post in test_posts:
        result = save_blog_post(
            post["id"], 
            post["title"], 
            post["content"], 
            post["date"], 
            post["is_private"],
            extra_data={k: v for k, v in post.items() if k not in ["id", "title", "content", "date", "is_private"]}
        )
        print(f"  - 포스트 {post['id']} 저장 결과: {'성공' if result else '실패'}")
    
    # 2. 저장된 포스트 목록 조회
    print("\n2. 저장된 포스트 ID 목록:")
    post_ids = list_all_posts()
    for pid in post_ids:
        print(f"  - {pid}")
    
    # 3. 개별 포스트 조회 테스트
    print("\n3. 개별 포스트 조회 테스트:")
    for post_id in [post["id"] for post in test_posts]:
        post_data = get_blog_post(post_id)
        if post_data:
            print(f"  - 포스트 {post_id} 조회 성공:")
            print(f"    제목: {post_data['title']}")
            print(f"    날짜: {post_data['date']}")
            print(f"    내용: {post_data['content'][:30]}...")
            
            # 추가 메타데이터 출력
            extra_fields = [k for k in post_data.keys() if k not in ["id", "title", "content", "date", "is_private"]]
            if extra_fields:
                print(f"    추가 필드: {', '.join(extra_fields)}")
        else:
            print(f"  - 포스트 {post_id} 조회 실패")
    
    # 4. 포스트 삭제 테스트
    print("\n4. 포스트 삭제 테스트:")
    for post_id in [post["id"] for post in test_posts]:
        result = delete_blog_post(post_id)
        print(f"  - 포스트 {post_id} 삭제 결과: {'성공' if result else '실패'}")
    
    # 5. 최종 상태 확인
    final_count = get_total_post_count()
    print(f"\n5. 테스트 후 DB에 저장된 포스트 수: {final_count}")
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    test_db_operations()
    
    # 주의: 아래 코드는 모든 포스트 데이터를 삭제합니다. 
    # 테스트 목적으로만 사용하세요.
    # clear_all_posts()