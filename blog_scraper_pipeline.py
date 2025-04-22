import logging
import time
from blog_utils import extract_blog_id
from scrape_blog_admin import scrape_blog_admin_mode
from scrape_blog_mobile import scrape_blog_mobile_mode
from scrape_blog_rss import scrape_blog_rss_mode

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_pipeline(blog_url, access_token=None):
    """
    단계적 블로그 스크래핑 파이프라인을 실행합니다.
    
    1) 관리자 AJAX (OAuth 필요) - 비공개 글 포함 최상위 방법
    2) 모바일 API (OAuth 필요) - 최신 스킨 대응
    3) RSS 피드 (OAuth 필수 아님) - 공개 글만 수집 가능한 대안
    
    각 단계는 이전 단계가 실패하면 자동으로 시도됩니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str, optional): OAuth 액세스 토큰
        
    Returns:
        tuple: (성공 여부, 메시지, 포스트 목록)
    """
    try:
        # URL 유효성 검사
        try:
            blog_id = extract_blog_id(blog_url)
            logger.debug(f"블로그 ID 추출 성공: {blog_id}")
        except ValueError as ve:
            return False, f"블로그 URL이 올바르지 않습니다: {str(ve)}", []
        
        # 단계 1: 관리자 AJAX 방식 (OAuth 필수)
        if access_token:
            logger.debug("단계 1: 관리자 AJAX 방식 시작")
            start_time = time.time()
            
            try:
                posts = scrape_blog_admin_mode(blog_url, access_token)
                
                if posts:
                    duration = time.time() - start_time
                    logger.debug(f"관리자 AJAX 성공: {len(posts)}개 포스트, {duration:.2f}초 소요")
                    return True, f"관리자 API로 {len(posts)}개의 포스트를 성공적으로 가져왔습니다.", posts
                else:
                    logger.warning("관리자 AJAX 방식 실패, 다음 단계로 진행")
            except Exception as e:
                logger.error(f"관리자 AJAX 오류: {str(e)}")
        else:
            logger.warning("OAuth 토큰이 없어 관리자 AJAX 방식을 건너뜁니다.")
        
        # 단계 2: 모바일 API 방식 (OAuth 권장)
        logger.debug("단계 2: 모바일 API 방식 시작")
        start_time = time.time()
        
        try:
            posts = scrape_blog_mobile_mode(blog_url, access_token)
            
            if posts:
                duration = time.time() - start_time
                logger.debug(f"모바일 API 성공: {len(posts)}개 포스트, {duration:.2f}초 소요")
                return True, f"모바일 API로 {len(posts)}개의 포스트를 성공적으로 가져왔습니다.", posts
            else:
                logger.warning("모바일 API 방식 실패, 다음 단계로 진행")
        except Exception as e:
            logger.error(f"모바일 API 오류: {str(e)}")
        
        # 단계 3: RSS 피드 방식 (OAuth 필수 아님, 공개 글만)
        logger.debug("단계 3: RSS 피드 방식 시작")
        start_time = time.time()
        
        try:
            posts = scrape_blog_rss_mode(blog_url, access_token)
            
            if posts:
                duration = time.time() - start_time
                logger.debug(f"RSS 피드 성공: {len(posts)}개 포스트, {duration:.2f}초 소요")
                private_post_note = ""
                if access_token:
                    private_post_note = " RSS는 비공개 글은 포함하지 않습니다."
                return True, f"RSS 피드로 {len(posts)}개의 포스트를 성공적으로 가져왔습니다.{private_post_note}", posts
            else:
                logger.warning("RSS 피드 방식도 실패")
        except Exception as e:
            logger.error(f"RSS 피드 오류: {str(e)}")
        
        # 모든 방법 실패
        return False, "모든 스크래핑 방법이 실패했습니다. 블로그 URL과 계정 권한을 확인해주세요.", []
        
    except Exception as e:
        logger.error(f"스크래핑 파이프라인 오류: {str(e)}")
        return False, f"스크래핑 중 오류가 발생했습니다: {str(e)}", []


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    # 테스트 URL과 토큰 (실제 사용 시 교체 필요)
    test_url = "https://blog.naver.com/naver_search"  # 네이버 공식 블로그
    test_token = None  # 테스트용 토큰 없음
    
    success, message, posts = scrape_blog_pipeline(test_url, test_token)
    
    print(f"결과: {'성공' if success else '실패'}")
    print(f"메시지: {message}")
    print(f"포스트 수: {len(posts)}")
    
    if posts:
        print("\n최초 3개 포스트 제목:")
        for idx, post in enumerate(posts[:3]):
            print(f"{idx+1}. {post['title']}")