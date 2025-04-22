import logging
import time
from blog_utils import extract_blog_id
from scrape_blog_admin import scrape_blog_admin_mode, get_posts_via_admin_api, create_authenticated_session as create_admin_session
from scrape_blog_mobile import scrape_blog_mobile_mode, fetch_mobile_lognos, get_post_detail as get_mobile_post_detail
from scrape_blog_rss import scrape_blog_rss_mode, fetch_rss_lognos

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_pipeline(blog_url, access_token=None):
    """
    단계적 블로그 스크래핑 파이프라인을 실행합니다.
    
    1) 관리자 AJAX (OAuth 필요) - 비공개 글 포함 최상위 방법
    2) 모바일 API (OAuth 필요) - 최신 스킨 대응
    3) RSS 피드 (OAuth 필수 아님) - 공개 글만 수집 가능한 대안
    4) 직접 HTML 파싱 (마지막 대안) - 성능 낮음, 안정성 문제
    
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
        
        # 통합된 방식으로 logNo 목록 추출
        all_log_nos = None
        method_used = None
        
        # 단계 1: 관리자 AJAX 방식 (OAuth 필수)
        if access_token:
            logger.debug("단계 1: 관리자 AJAX 방식으로 logNo 수집 시작")
            start_time = time.time()
            
            try:
                # 인증된 세션 생성
                admin_session = create_admin_session(access_token)
                # 관리자 API로 포스트 목록 가져오기
                admin_posts = get_posts_via_admin_api(admin_session, blog_id)
                
                if admin_posts:
                    all_log_nos = [post.get('logNo') for post in admin_posts if post.get('logNo')]
                    method_used = "admin"
                    duration = time.time() - start_time
                    logger.debug(f"관리자 AJAX 성공: {len(all_log_nos)}개 logNo, {duration:.2f}초 소요")
                else:
                    logger.warning("관리자 AJAX 방식 실패, 다음 단계로 진행")
            except Exception as e:
                logger.error(f"관리자 AJAX logNo 수집 오류: {str(e)}")
        else:
            logger.warning("OAuth 토큰이 없어 관리자 AJAX 방식을 건너뜁니다.")
        
        # 단계 2: 모바일 API 방식 (OAuth 권장)
        if not all_log_nos:
            logger.debug("단계 2: 모바일 API 방식으로 logNo 수집 시작")
            start_time = time.time()
            
            try:
                # 모바일 API로 logNo 목록 가져오기
                mobile_session = create_admin_session(access_token)
                mobile_log_nos = fetch_mobile_lognos(mobile_session, blog_id)
                
                if mobile_log_nos:
                    all_log_nos = mobile_log_nos
                    method_used = "mobile"
                    duration = time.time() - start_time
                    logger.debug(f"모바일 API 성공: {len(all_log_nos)}개 logNo, {duration:.2f}초 소요")
                else:
                    logger.warning("모바일 API 방식 실패, 다음 단계로 진행")
            except Exception as e:
                logger.error(f"모바일 API logNo 수집 오류: {str(e)}")
        
        # 단계 3: RSS 피드 방식 (OAuth 필수 아님, 공개 글만)
        if not all_log_nos:
            logger.debug("단계 3: RSS 피드 방식으로 logNo 수집 시작")
            start_time = time.time()
            
            try:
                # RSS 피드로 logNo 목록 가져오기
                rss_log_nos = fetch_rss_lognos(blog_id)
                
                if rss_log_nos:
                    all_log_nos = rss_log_nos
                    method_used = "rss"
                    duration = time.time() - start_time
                    logger.debug(f"RSS 피드 성공: {len(all_log_nos)}개 logNo, {duration:.2f}초 소요")
                else:
                    logger.warning("RSS 피드 방식도 실패")
            except Exception as e:
                logger.error(f"RSS 피드 logNo 수집 오류: {str(e)}")
        
        # logNo 목록을 얻지 못한 경우
        if not all_log_nos:
            # 각 방법을 직접 시도 (전체 파이프라인)
            logger.debug("개별 logNo 수집 실패, 전체 스크래핑 파이프라인 시도")
            
            # 관리자 AJAX 방식 시도
            if access_token:
                logger.debug("관리자 AJAX 전체 스크래핑 시도")
                try:
                    admin_posts = scrape_blog_admin_mode(blog_url, access_token)
                    if admin_posts:
                        return True, f"관리자 API로 {len(admin_posts)}개의 포스트를 가져왔습니다.", admin_posts
                except Exception as e:
                    logger.error(f"관리자 AJAX 전체 스크래핑 오류: {str(e)}")
            
            # 모바일 API 방식 시도
            logger.debug("모바일 API 전체 스크래핑 시도")
            try:
                mobile_posts = scrape_blog_mobile_mode(blog_url, access_token)
                if mobile_posts:
                    return True, f"모바일 API로 {len(mobile_posts)}개의 포스트를 가져왔습니다.", mobile_posts
            except Exception as e:
                logger.error(f"모바일 API 전체 스크래핑 오류: {str(e)}")
            
            # RSS 피드 방식 시도
            logger.debug("RSS 피드 전체 스크래핑 시도")
            try:
                rss_posts = scrape_blog_rss_mode(blog_url, access_token)
                if rss_posts:
                    return True, f"RSS 피드로 {len(rss_posts)}개의 포스트를 가져왔습니다.", rss_posts
            except Exception as e:
                logger.error(f"RSS 피드 전체 스크래핑 오류: {str(e)}")
            
            # 모든 방법 실패
            return False, "모든 스크래핑 방법이 실패했습니다. 블로그 URL과 계정 권한을 확인해주세요.", []
        
        # logNo 목록을 얻었으므로 포스트 상세 내용 수집
        logger.debug(f"{method_used} 방식으로 얻은 {len(all_log_nos)}개 logNo로 상세 내용 수집 시작")
        
        # 최대 30개로 제한
        if len(all_log_nos) > 30:
            logger.debug(f"logNo 수 제한: {len(all_log_nos)}개 -> 30개")
            all_log_nos = all_log_nos[:30]
        
        # 포스트 상세 내용 수집
        posts = []
        session = create_admin_session(access_token)
        
        for log_no in all_log_nos:
            try:
                post_detail = get_mobile_post_detail(session, blog_id, log_no)
                if post_detail:
                    # 필요한 필드 확인 및 추가
                    if 'logNo' not in post_detail:
                        post_detail['logNo'] = log_no
                    if 'url' not in post_detail:
                        post_detail['url'] = f"https://blog.naver.com/{blog_id}/{log_no}"
                    
                    posts.append(post_detail)
                    # 서버 부하 방지
                    time.sleep(0.5)
            except Exception as post_error:
                logger.error(f"포스트 {log_no} 처리 중 오류: {str(post_error)}")
                continue
        
        if not posts:
            return False, "포스트 상세 내용을 가져올 수 없습니다.", []
        
        # 성공 메시지 구성
        method_names = {
            "admin": "관리자 API",
            "mobile": "모바일 API",
            "rss": "RSS 피드"
        }
        
        method_display = method_names.get(method_used, str(method_used))
        private_post_note = ""
        if method_used == "rss" and access_token:
            private_post_note = " (RSS는 비공개 글은 포함하지 않습니다.)"
        
        success_message = f"{method_display}로 {len(posts)}개의 포스트를 성공적으로 가져왔습니다.{private_post_note}"
        return True, success_message, posts
        
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