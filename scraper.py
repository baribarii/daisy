import logging
from blog_utils import extract_blog_id as utils_extract_blog_id

logger = logging.getLogger(__name__)

def extract_blog_id(blog_url):
    """
    네이버 블로그 URL에서 blogId를 추출합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        
    Returns:
        str: 블로그 ID (아이디)
        
    Raises:
        ValueError: URL이 네이버 블로그 형식이 아니거나 ID를 추출할 수 없는 경우
    """
    try:
        # 강화된 URL 추출 함수 사용
        return utils_extract_blog_id(blog_url)
    except ValueError as e:
        # 이전 방식과 호환성 유지를 위해 오류 메시지 변환
        raise ValueError("Could not extract blog ID from the provided URL")

# 쿠키 기반 스크래퍼는 제거되었습니다.
# OAuth 기반 스크래퍼만 사용합니다. (oauth_scraper.py 참조)
