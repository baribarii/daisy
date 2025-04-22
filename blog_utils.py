import re
from urllib.parse import urlparse, parse_qs


def extract_blog_id(url):
    """
    네이버 블로그 URL에서 blogId를 추출합니다.
    
    지원 포맷:
    - https://blog.naver.com/{id}
    - https://{id}.blog.me/{path}
    - https://blog.naver.com/{id}/{logNo}
    - https://m.blog.naver.com/{id}
    - https://blog.naver.com/PostView.naver?blogId={id}&logNo={logNo}
    - https://m.blog.naver.com/PostView.naver?blogId={id}&logNo={logNo}
    
    Args:
        url (str): 네이버 블로그 URL
        
    Returns:
        str: 블로그 ID (아이디)
        
    Raises:
        ValueError: URL이 네이버 블로그 형식이 아니거나 ID를 추출할 수 없는 경우
    """
    if not url:
        raise ValueError("URL이 비어있습니다.")
    
    # URL 형식 검증 및 정규화
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # 네이버 블로그 도메인 확인
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc.lower()
    
    # 1. blog.me 형식 (예: https://myid.blog.me/...)
    if '.blog.me' in netloc:
        blog_id = netloc.split('.')[0]
        return blog_id
    
    # 2. 쿼리 파라미터 형식 (예: https://blog.naver.com/PostView.naver?blogId=myid)
    if 'blogid' in parsed_url.query.lower():
        query_params = parse_qs(parsed_url.query)
        blog_id_param = next((key for key in query_params if key.lower() == 'blogid'), None)
        
        if blog_id_param and query_params[blog_id_param]:
            return query_params[blog_id_param][0]
    
    # 3. 경로 형식 (예: https://blog.naver.com/myid 또는 https://blog.naver.com/myid/123456)
    if netloc in ('blog.naver.com', 'm.blog.naver.com'):
        path = parsed_url.path.strip('/')
        
        # PostList.naver, PostView.naver 등의 경로 처리
        if path.startswith(('PostList.naver', 'PostView.naver')):
            query_params = parse_qs(parsed_url.query)
            blog_id_param = next((key for key in query_params if key.lower() == 'blogid'), None)
            
            if blog_id_param and query_params[blog_id_param]:
                return query_params[blog_id_param][0]
            else:
                # blogId가 없으면 올바른 URL이 아님
                raise ValueError("blogId 파라미터가 없는 PostView/PostList URL입니다.")
        
        # 일반 경로에서 첫 번째 세그먼트가 ID
        if path:
            blog_id = path.split('/')[0]
            # 특수한 경로나 시스템 페이지가 아닌지 확인
            if blog_id in ('PostView.naver', 'PostList.naver', 'SympathyUpdateCenter.naver',
                          'CommentList.naver', 'api', 'BlogTagCloud.naver'):
                raise ValueError("네이버 블로그 URL에서 블로그 ID를 찾을 수 없습니다.")
            return blog_id
    
    # 지원하지 않는 URL 형식
    raise ValueError("네이버 블로그 URL 형식이 아니거나 블로그 ID를 추출할 수 없습니다.")


# 테스트 케이스
def test_extract_blog_id():
    test_cases = [
        # 기본 형식
        ("https://blog.naver.com/myid", "myid"),
        ("http://blog.naver.com/myid", "myid"),
        ("blog.naver.com/myid", "myid"),
        
        # blog.me 형식
        ("https://myid.blog.me", "myid"),
        ("http://myid.blog.me/12345", "myid"),
        ("myid.blog.me", "myid"),
        
        # 모바일 형식
        ("https://m.blog.naver.com/myid", "myid"),
        ("m.blog.naver.com/myid/12345", "myid"),
        
        # 경로에 logNo가 있는 형식
        ("https://blog.naver.com/myid/223456789", "myid"),
        ("blog.naver.com/myid/223456789", "myid"),
        
        # 쿼리 파라미터 형식
        ("https://blog.naver.com/PostView.naver?blogId=myid&logNo=223456789", "myid"),
        ("https://m.blog.naver.com/PostView.naver?blogId=myid&logNo=223456789", "myid"),
        ("blog.naver.com/PostList.naver?blogId=myid", "myid"),
        
        # 대소문자 혼합 URL
        ("https://BLOG.naver.com/myid", "myid"),
        ("https://blog.naver.com/PostView.naver?BlogId=myid", "myid"),
    ]
    
    # 실패해야 하는 케이스
    failure_cases = [
        "https://www.google.com",
        "https://naver.com",
        "https://blog.never.com/myid", # 오타 URL
        "https://blog.naver.com/", # ID 없음
        "https://blog.naver.com/PostView.naver?logNo=12345", # blogId 없음
    ]
    
    print("=== 성공 테스트 케이스 ===")
    for url, expected_id in test_cases:
        try:
            blog_id = extract_blog_id(url)
            assert blog_id == expected_id, f"실패: {url} => 기대값: {expected_id}, 실제값: {blog_id}"
            print(f"성공: {url} => {blog_id}")
        except Exception as e:
            print(f"예상치 못한 오류: {url} => {str(e)}")
    
    print("\n=== 실패 테스트 케이스 ===")
    for url in failure_cases:
        try:
            blog_id = extract_blog_id(url)
            print(f"실패해야 하는데 성공함: {url} => {blog_id}")
        except ValueError as e:
            print(f"예상대로 실패: {url} => {str(e)}")
        except Exception as e:
            print(f"다른 예외 발생: {url} => {str(e)}")


if __name__ == "__main__":
    test_extract_blog_id()