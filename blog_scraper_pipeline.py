import logging
import time
import re
import datetime
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, ReadTimeout
from blog_utils import extract_blog_id
from scrape_blog_admin import scrape_blog_admin_mode, get_posts_via_admin_api, create_authenticated_session as create_admin_session
from scrape_blog_mobile import scrape_blog_mobile_mode, fetch_mobile_lognos, get_post_detail
from scrape_blog_rss import scrape_blog_rss_mode, fetch_rss_lognos

# 로깅 설정
logger = logging.getLogger(__name__)

def normalize_date_format(date_str):
    """
    다양한 네이버 블로그 날짜 형식을 YYYY-MM-DD 형식으로 정규화합니다.
    
    Args:
        date_str (str): 원본 날짜 문자열
        
    Returns:
        str: YYYY-MM-DD 형식의 날짜, 변환 실패 시 원본 문자열 반환
    """
    if not date_str:
        # 현재 날짜 기본값 사용
        return datetime.datetime.now().strftime("%Y-%m-%d")
    
    date_str = date_str.strip()
    
    # 이미 YYYY-MM-DD 형식이면 그대로 반환
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    try:
        # 네이버 날짜 형식 1: "YYYY. MM. DD."
        if re.match(r'^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?$', date_str):
            cleaned = re.sub(r'[\.\s]', '', date_str)
            if len(cleaned) >= 8:
                year = cleaned[0:4]
                month = cleaned[4:6].zfill(2)
                day = cleaned[6:8].zfill(2)
                return f"{year}-{month}-{day}"
        
        # 네이버 날짜 형식 2: "YYYY년 MM월 DD일"
        elif re.search(r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일', date_str):
            match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', date_str)
            if match:
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # 네이버 날짜 형식 3: "MMM DD, YYYY" (영문)
        elif re.match(r'[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}', date_str):
            try:
                dt = datetime.datetime.strptime(date_str, "%b %d, %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                try:
                    dt = datetime.datetime.strptime(date_str, "%B %d, %Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        # 네이버 날짜 형식 4: "MM-DD (요일)"
        elif re.match(r'\d{1,2}-\d{1,2}\s*\([월화수목금토일]\)', date_str):
            match = re.match(r'(\d{1,2})-(\d{1,2})', date_str)
            if match:
                month, day = match.groups()
                year = datetime.datetime.now().year
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Unix 타임스탬프 (밀리초)
        elif re.match(r'^\d{10,13}$', date_str):
            timestamp = int(date_str)
            if timestamp > 10000000000:  # 밀리초 타임스탬프
                timestamp = timestamp / 1000
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d")
    
    except Exception as e:
        logger.error(f"날짜 정규화 오류: {str(e)}")
    
    # 정규화 실패 시 원본 반환
    return date_str

def scrape_blog_pipeline(blog_url, access_token=None, use_playwright=True):
    """
    단계적 블로그 스크래핑 파이프라인을 실행합니다.
    
    0) Playwright 자동화 (OAuth 필요, 최상의 비공개 글 접근)
    1) 관리자 AJAX (OAuth 필요) - 비공개 글 포함 최상위 방법
    2) 모바일 API (OAuth 필요) - 최신 스킨 대응
    3) RSS 피드 (OAuth 필수 아님) - 공개 글만 수집 가능한 대안
    4) 직접 HTML 파싱 (마지막 대안) - 성능 낮음, 안정성 문제
    
    각 단계는 이전 단계가 실패하면 자동으로 시도됩니다.
    OAuth 토큰이 제공된 경우, 비공개 글이나 서로이웃/이웃 공개 글에 접근을 시도합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str, optional): OAuth 액세스 토큰
        use_playwright (bool, optional): Playwright 자동화를 사용할지 여부. 기본값은 True.
                                         비공개 글 접근에 가장 효과적이지만 시간이 조금 더 소요됨.
        
    Returns:
        tuple: (성공 여부, 메시지, 포스트 목록)
    """
    # OAuth 토큰으로부터 인증 쿠키 생성 (비공개 글 접근 향상)
    auth_cookies = {}
    if access_token:
        try:
            from oauth_handler import generate_auth_cookies_from_token
            auth_cookies = generate_auth_cookies_from_token(access_token)
            if auth_cookies:
                logger.debug(f"OAuth 토큰으로부터 {len(auth_cookies)}개의 인증 쿠키를 생성했습니다")
        except Exception as cookie_error:
            logger.warning(f"인증 쿠키 생성 중 오류: {str(cookie_error)}")
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
        
        # 단계 0: Playwright 웹 자동화 방식 (OAuth 사용 시 최고의 비공개 접근성)
        if use_playwright and access_token:
            logger.debug("단계 0: Playwright 자동화로 스크래핑 시작")
            start_time = time.time()
            
            try:
                # 웹 자동화를 통한 포스트 수집
                from utils_browser import fetch_all_posts_with_playwright
                
                # 쿠키 문자열 생성 (auth_cookies 딕셔너리에서)
                cookie_str = ""
                if auth_cookies:
                    cookie_str = "; ".join([f"{key}={value}" for key, value in auth_cookies.items()])
                    logger.debug(f"인증 쿠키 문자열 생성: {len(cookie_str)} 바이트")
                
                # Playwright로 직접 포스트 수집
                logger.debug(f"Playwright로 블로그 스크래핑 시작: {blog_id}")
                playwright_posts = fetch_all_posts_with_playwright(
                    blog_id=blog_id, 
                    cookie_str=cookie_str, 
                    access_token=access_token
                )
                
                if playwright_posts:
                    duration = time.time() - start_time
                    logger.debug(f"Playwright 성공: {len(playwright_posts)}개 포스트, {duration:.2f}초 소요")
                    return True, f"Playwright로 {len(playwright_posts)}개의 포스트를 가져왔습니다.", playwright_posts
                else:
                    logger.warning("Playwright 방식 실패, 다음 방법으로 진행")
            except Exception as pw_error:
                logger.error(f"Playwright 스크래핑 오류: {str(pw_error)}")
                logger.debug("대체 방법으로 진행합니다")
        
        # 스크래핑 메소드 순서 변경: 모바일 API를 먼저 시도합니다 (비공개 글 접근성 향상)
        
        # 단계 1: 모바일 API 방식 (OAuth 권장, 비공개 글 접근 가능)
        logger.debug("단계 1: 모바일 API 방식으로 logNo 수집 시작")
        start_time = time.time()
        
        try:
            # 모바일 API로 logNo 목록 가져오기 (비공개 글 포함)
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
        
        # 단계 2: 관리자 AJAX 방식 (OAuth 필수)
        if not all_log_nos and access_token:
            logger.debug("단계 2: 관리자 AJAX 방식으로 logNo 수집 시작")
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
        elif not all_log_nos and not access_token:
            logger.warning("OAuth 토큰이 없어 관리자 AJAX 방식을 건너뜁니다.")
        
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
        
        # 최대 10개로 제한 (기존 20개에서 추가 축소하여 타임아웃 방지)
        # logNo 형식이 숫자이므로 역순 정렬 - 최신글이 일반적으로 큰 숫자
        all_log_nos = sorted(all_log_nos, reverse=True)
        if len(all_log_nos) > 10:
            logger.debug(f"logNo 수 제한: {len(all_log_nos)}개 -> 10개")
            all_log_nos = all_log_nos[:10]
        
        # 포스트 상세 내용 수집
        posts = []
        session = create_admin_session(access_token)
        
        # 생성된 인증 쿠키를 세션에 직접 적용 (비공개 글 접근 개선)
        if auth_cookies:
            logger.debug("인증 쿠키를 세션에 직접 적용합니다")
            session.cookies.update(auth_cookies)
        
        for log_no in all_log_nos:
            try:
                # 네트워크 오류 재시도 메커니즘 추가
                max_retries = 2
                retry_count = 0
                post_detail = None
                
                # 현재 세션 환경에 맞는 함수 선택 (모바일)
                from scrape_blog_mobile import get_post_detail
                
                while retry_count <= max_retries and not post_detail:
                    try:
                        logger.debug(f"포스트 {log_no} 상세 내용 가져오기 시도 {retry_count+1}/{max_retries+1}")
                        post_detail = get_post_detail(session, blog_id, log_no)
                        break  # 성공하면 루프 종료
                    except (RequestException, ConnectionError, Timeout, ReadTimeout) as req_err:
                        logger.warning(f"포스트 {log_no} 네트워크 오류 (재시도 {retry_count+1}/{max_retries+1}): {str(req_err)}")
                        retry_count += 1
                        if retry_count <= max_retries:
                            time.sleep(1)  # 재시도 전 대기
                    except Exception as other_err:
                        logger.error(f"포스트 {log_no} 처리 중 오류: {str(other_err)}")
                        break  # 네트워크 오류가 아닌 경우 재시도하지 않음
                
                if post_detail:
                    # 필요한 필드 확인 및 추가
                    if 'logNo' not in post_detail:
                        post_detail['logNo'] = log_no
                    if 'url' not in post_detail:
                        post_detail['url'] = f"https://blog.naver.com/{blog_id}/{log_no}"
                    
                    # 비공개 글 감지 개선: 제목이나 내용에 특정 키워드가 있으면 비공개 글로 처리
                    title = post_detail.get('title', '제목 없음')
                    content = post_detail.get('content', '')
                    is_private = post_detail.get('is_private', False)
                    
                    # 자동 비공개 글 감지 (추가 검사)
                    private_keywords = ["접근 실패", "접근 권한이 없", "비공개", "권한이 없습니다", "비밀글"]
                    for keyword in private_keywords:
                        if keyword in title or (content and keyword in content[:100]):  # 제목이나 내용 앞부분에서 검사
                            is_private = True
                            logger.debug(f"비공개 글 감지: 키워드 '{keyword}' 발견")
                            break
                    
                    # 매우 짧은 내용이면 비공개일 가능성 높음 (예외적 상황 시)
                    if not is_private and content and len(content.strip()) < 50:
                        is_private = True
                        logger.debug(f"비공개 글 감지: 짧은 내용 (길이 {len(content.strip())})")
                    
                    # 업데이트된 is_private 상태 반영
                    post_detail['is_private'] = is_private
                    
                    # 날짜 형식 정규화 (YYYY-MM-DD)
                    if 'date' in post_detail and post_detail['date']:
                        post_detail['date'] = normalize_date_format(post_detail['date'])
                    
                    posts.append(post_detail)
                    # 서버 부하 방지 (0.5초 → 0.1초로 단축)
                    time.sleep(0.1)
                else:
                    # 최대 재시도 후에도 실패하면 최소한의 정보로 기록
                    fallback_post = {
                        'logNo': log_no,
                        'title': f'접근 실패: {log_no}',
                        'content': '네트워크 오류로 접근할 수 없는 포스트입니다.',
                        'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                        'is_private': True,
                        'url': f"https://blog.naver.com/{blog_id}/{log_no}"
                    }
                    posts.append(fallback_post)
                    logger.warning(f"포스트 {log_no} 가져오기 실패 후 대체 정보 사용")
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
        
        # 안전한 메서드 이름 표시 
        method_display = method_names[method_used] if method_used in method_names else str(method_used)
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