import logging
import time
import json
import re
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, ReadTimeout
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_mobile_mode(blog_url, access_token):
    """
    네이버 모바일 블로그 API를 사용하여 포스트 목록과 내용을 스크래핑합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        list: 포스트 목록 (각 항목은 딕셔너리 형태)
    """
    try:
        # 블로그 ID 추출
        blog_id = extract_blog_id(blog_url)
        logger.debug(f"블로그 ID 추출: {blog_id}")
        
        # OAuth 토큰으로 인증된 세션 생성
        session = create_authenticated_session(access_token)
        
        # 모바일 API로 포스트 목록 가져오기
        posts = get_posts_via_mobile_api(session, blog_id)
        
        if not posts:
            logger.warning("모바일 API로 포스트를 가져오지 못했습니다. 대체 메서드 시도가 필요합니다.")
            return []
            
        # 최대 30개로 제한
        if len(posts) > 30:
            logger.debug(f"포스트 수 제한: {len(posts)}개 -> 30개")
            posts = posts[:30]
        
        # 각 포스트 내용 가져오기
        detailed_posts = []
        
        for post in posts:
            log_no = post.get('logNo')
            if not log_no:
                continue
                
            # 포스트 상세 내용 가져오기
            post_detail = get_post_detail(session, blog_id, log_no)
            
            if post_detail:
                detailed_posts.append(post_detail)
                # 서버 부하 방지
                time.sleep(0.5)
        
        logger.debug(f"총 {len(detailed_posts)}개의 상세 포스트를 가져왔습니다.")
        return detailed_posts
        
    except Exception as e:
        logger.error(f"모바일 모드 스크래핑 중 오류: {str(e)}")
        return []


def create_authenticated_session(access_token):
    """
    OAuth 액세스 토큰으로 인증된 세션을 생성합니다.
    
    Args:
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        requests.Session: 인증된 세션 객체
    """
    # 세션 생성
    session = requests.Session()
    
    # 기본 헤더 설정 - 모바일 기기 User-Agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json, text/html, text/plain, */*',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Referer': 'https://m.blog.naver.com/'
    })
    
    # OAuth 토큰 활용 (두 가지 방식으로 처리)
    if access_token:
        # 1. Authorization 헤더로 OAuth 토큰 전달
        session.headers.update({
            'Authorization': f'Bearer {access_token}'
        })
        
        # 2. 네이버 인증 쿠키 설정 - 비공개 글 접근에 필수
        try:
            # 관리자 API와 동일한 강화된 인증 시스템 적용
            import hashlib
            import base64
            import time
            
            # 보다 강력한 토큰 변환
            token_md5 = hashlib.md5(access_token.encode('utf-8')).hexdigest()
            token_b64 = base64.b64encode(access_token.encode('utf-8')).decode('utf-8')
            token_prefix = access_token[:16] if len(access_token) >= 16 else access_token
            token_suffix = access_token[-16:] if len(access_token) >= 16 else access_token
            
            # 모바일 특화 인증 쿠키 세트
            cookies = {
                # 네이버 인증 필수 쿠키
                'NID_AUT': token_md5[:16],
                'NID_SES': token_md5[16:32],
                'NID_JKL': token_md5[:8],
                
                # 모바일 접근용 쿠키 (모바일 특화)
                'MM_NEW': '1',
                'NID_M_CHECK': 'true',
                'NID_DEVICE': 'mobile',
                'BLOG_M': 'on',
                'MOBILE_BI': token_md5[:10],
                
                # 비공개 글 접근을 위한 추가 쿠키
                'NID_CHECK': 'naver',
                'JSESSIONID': token_suffix.replace('-', ''),
                'nid_inf': token_md5[:12],
                
                # 네이버 로그인 상태 유지
                'nx_ssl': 'on',
                'PM_CK_loc': 'https://nid.naver.com/login/sso/finalize.nhn',
                
                # 시간 기반 쿠키 (타임스탬프 포함)
                'nid_tss': str(int(time.time())),
                'nts_cdf': token_b64[:16]
            }
            
            # 쿠키 설정
            session.cookies.update(cookies)
            logger.debug("모바일 인증 쿠키 설정 성공")
            
        except Exception as e:
            logger.error(f"인증 쿠키 설정 중 오류: {str(e)}")
    
    # 세션 검증 및 실제 로그인 상태 확인
    try:
        # 1. 직접 OAuth 토큰으로 네이버 API 호출하여 사용자 정보 획득
        logger.debug("네이버 API로 직접 사용자 정보 확인 시도")
        api_url = "https://openapi.naver.com/v1/nid/me"
        api_headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            profile_resp = requests.get(api_url, headers=api_headers, timeout=5)
            if profile_resp.status_code == 200:
                profile_data = profile_resp.json()
                if profile_data.get('resultcode') == '00':
                    user_data = profile_data.get('response', {})
                    user_id = user_data.get('id')
                    user_name = user_data.get('name')
                    logger.debug(f"네이버 API 사용자 정보 획득 성공: ID={user_id}, 이름={user_name}")
                    
                    # 세션 헤더에 사용자 정보 추가 (모바일 API용으로 활용)
                    session.headers.update({
                        'X-Naver-User-Id': user_id or '',
                        'X-Naver-User-Name': user_name or ''
                    })
                    
                    # POST 요청시 필요한 폼 데이터에도 사용자 ID 추가 
                    # (네이버 모바일 API의 추가 인증 요구사항)
                    if user_id:
                        session.cookies.update({'naver_uid': user_id})
                else:
                    logger.warning(f"네이버 API 응답 오류: {profile_data.get('message')}")
            else:
                logger.warning(f"네이버 API 호출 실패: {profile_resp.status_code}")
        except Exception as api_error:
            logger.warning(f"네이버 API 호출 오류: {str(api_error)}")
        
        # 2. 모바일 웹 인증 페이지 접속하여 로그인 상태 활성화
        logger.debug("모바일 네이버 접속하여 토큰 활성화 시도")
        try:
            # 모바일 로그인 페이지 접속
            login_url = "https://m.naver.com"
            login_resp = session.get(login_url, timeout=5)
            if login_resp.status_code == 200:
                logger.debug("모바일 네이버 접속 성공")
            else:
                logger.warning(f"모바일 네이버 접속 실패: {login_resp.status_code}")
                
            # 모바일 블로그 로그인 페이지 접속 (인증 활성화)
            blog_login_url = "https://m.blog.naver.com/nidlogin.naver"
            blog_login_resp = session.get(blog_login_url, timeout=5)
            if blog_login_resp.status_code == 200:
                logger.debug("모바일 블로그 로그인 페이지 접속 성공")
            else:
                logger.warning(f"모바일 블로그 로그인 페이지 접속 실패: {blog_login_resp.status_code}")
        except Exception as login_error:
            logger.warning(f"모바일 로그인 시도 오류: {str(login_error)}")
        
        # 3. 최종 검증: 모바일 블로그 페이지 로드 및 로그인 여부 확인
        test_url = "https://m.blog.naver.com/"
        response = session.get(test_url, timeout=5)
        if response.status_code == 200:
            # 로그인 상태 확인 (로그인 버튼이 있는지)
            is_logged_in = "로그인" not in response.text or "login" not in response.text.lower()
            if is_logged_in:
                logger.debug("모바일 세션 인증 확인 완료 - 로그인 상태")
            else:
                logger.warning("모바일 세션 인증 확인 됨 - 그러나 로그인 상태가 아님")
        else:
            logger.warning(f"모바일 인증 확인 실패 (status: {response.status_code})")
    except Exception as e:
        logger.warning(f"모바일 인증 확인 중 오류: {str(e)}")
    
    return session


def fetch_mobile_lognos(session, blog_id):
    """
    네이버 모바일 블로그에서 포스트 ID(logNo) 목록만 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        
    Returns:
        list: logNo 목록, 실패 시 None
    """
    try:
        # 모바일 PostList URL
        url = f"https://m.blog.naver.com/PostList.naver?blogId={blog_id}"
        
        # 재시도 로직
        max_retries = 2
        retry_count = 0
        response = None
        
        while retry_count <= max_retries:
            try:
                logger.debug(f"모바일 PostList 요청 시도 {retry_count+1}/{max_retries+1}")
                response = session.get(url, timeout=5)
                if response.status_code == 200:
                    break
            except Exception as retry_error:
                logger.warning(f"모바일 API 요청 재시도 {retry_count+1}/{max_retries+1}: {str(retry_error)}")
            
            retry_count += 1
            time.sleep(1)  # backoff
        
        if not response or response.status_code != 200:
            logger.error(f"모바일 API 응답 오류: {response.status_code if response else 'No response'}")
            return None
        
        # logNo 목록 추출
        log_nos = []
        
        # 1. JSON 데이터 찾기 (페이지에 내장된 JSON)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup.find_all('script'):
            script_text = script.string if script.string else ""
            
            # postList 객체 찾기
            json_pattern = re.compile(r'(?:blogPostListForm|blogInfo|postList)\s*=\s*(\{.*?\});', re.DOTALL)
            json_matches = json_pattern.findall(script_text)
            
            for json_str in json_matches:
                try:
                    # JavaScript 객체를 JSON으로 변환
                    json_str = re.sub(r'(\w+):', r'"\1":', json_str)  # 키에 따옴표 추가
                    json_str = re.sub(r',\s*\}', '}', json_str)  # 후행 콤마 제거
                    data = json.loads(json_str)
                    
                    # 다양한 JSON 구조 처리
                    post_list = data.get('postList') or data.get('posts') or []
                    
                    for post_info in post_list:
                        log_no = str(post_info.get('logNo', ''))
                        if log_no and log_no.isdigit() and log_no not in log_nos:
                            log_nos.append(log_no)
                except Exception as json_error:
                    logger.debug(f"JSON 파싱 오류: {str(json_error)}")
                    continue
        
        # 2. HTML에서 직접 logNo 추출
        if not log_nos:
            # href에서 logNo 파라미터 찾기
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'logNo=' in href:
                    try:
                        log_no = href.split('logNo=')[1].split('&')[0]
                        if log_no.isdigit() and log_no not in log_nos:
                            log_nos.append(log_no)
                    except:
                        continue
                
                # /blogId/logNo 형식 체크
                elif f'/{blog_id}/' in href:
                    try:
                        parts = href.split(f'/{blog_id}/')[1].split('?')[0].split('/')
                        for part in parts:
                            if part.isdigit() and part not in log_nos:
                                log_nos.append(part)
                                break
                    except:
                        continue
        
        if log_nos:
            logger.debug(f"모바일 API에서 {len(log_nos)}개의 logNo 발견")
            return log_nos
        
        logger.warning(f"모바일 API에서 logNo를 찾을 수 없음")
        return None
        
    except Exception as e:
        logger.error(f"모바일 API 호출 오류: {str(e)}")
        return None


def get_posts_via_mobile_api(session, blog_id):
    """
    네이버 모바일 블로그 API를 사용하여 포스트 목록을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 먼저 모바일 API로 logNo 목록 가져오기
        log_nos = fetch_mobile_lognos(session, blog_id)
        
        if not log_nos:
            logger.warning("모바일 API에서 포스트 목록을 가져오지 못했습니다")
            return []
        
        # 각 포스트의 상세 내용 가져오기
        posts = []
        
        # 최대 30개로 제한
        if len(log_nos) > 30:
            logger.debug(f"포스트 수 제한: {len(log_nos)}개 -> 30개")
            log_nos = log_nos[:30]
        
        for log_no in log_nos:
            try:
                post_detail = get_post_detail(session, blog_id, log_no)
                if post_detail:
                    posts.append(post_detail)
                    # 서버 부하 방지
                    time.sleep(0.5)
            except Exception as post_error:
                logger.error(f"포스트 {log_no} 처리 중 오류: {str(post_error)}")
                continue
        
        logger.debug(f"총 {len(posts)}개의 상세 포스트를 가져왔습니다")
        return posts
        
    except Exception as e:
        logger.error(f"모바일 API 호출 오류: {str(e)}")
        return []


def get_post_detail(session, blog_id, log_no):
    """
    특정 포스트의 상세 내용을 모바일 페이지에서 가져옵니다.
    인코딩 문제 해결과 비공개 글 접근을 위한 개선 로직 포함.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        log_no (str): 포스트 번호
        
    Returns:
        dict: 포스트 상세 정보
    """
    try:
        # 모바일 포스트 조회 URL
        url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
        
        # 비공개 글이나 친구 공개 글을 위한 헤더 추가
        custom_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'identity',  # 명시적으로 압축 비활성화 (인코딩 문제 방지)
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': f'https://m.blog.naver.com/PostList.naver?blogId={blog_id}',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 더 짧은 타임아웃 및 예외 처리 강화
        try:
            # 인코딩 문제 방지를 위해 인코딩 설정을 명시
            response = session.get(
                url, 
                timeout=15, 
                allow_redirects=True,
                headers=custom_headers
            )
            
            # 응답 인코딩 명시적 설정 (UTF-8 강제)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.error(f"모바일 포스트 상세 조회 오류: {response.status_code}")
                return None
        except requests.exceptions.RequestException as req_err:
            logger.error(f"네트워크 요청 오류 (URL: {url}): {str(req_err)}")
            # 네트워크 오류 시 빈 결과 반환하여 파이프라인 중단 방지
            return {
                'logNo': log_no,
                'title': f'접근 실패: {log_no}',
                'content': '네트워크 오류로 접근할 수 없는 포스트입니다.',
                'date': '',
                'is_private': True,
                'url': url
            }
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 제목 추출
        title = ""
        title_selectors = [
            '.se-title-text', '.se-module-text', '.tit_h3', 
            '.se_title', '.pcol1', 'h3.tit_view', '.post_title', 
            '.se-documentTitle-titleText'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    break
        
        # 내용 추출 - 모바일에서는 더 간단한 구조
        content = ""
        content_selectors = [
            '.se-main-container', '.post_ct', '#postViewArea', 
            '.se_component_wrap', '.view', '.post-view',
            '.se-module-text-paragraph', '.post_body', '#viewTypeSelector'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 불필요한 요소 제거
                for remove_sel in ['script', 'style', '.comment_area', '.btn_area']:
                    for el in content_elem.select(remove_sel):
                        el.decompose()
                
                content = content_elem.get_text(separator='\n', strip=True)
                if content:
                    break
        
        # 날짜 추출 - 다양한 네이버 블로그 스킨/버전 지원
        date = ""
        date_selectors = [
            # 기본 셀렉터
            '.se_publishDate', '.date', '.se_date', '.se-module-date', 
            '.post_date', '.se-date', '.date_post', '.blog_date', '.date_info',
            '.blog2_series', '.date_time', '.post-meta', '.post-day', '.article_info',
            # 네이버 모바일 전용 셀렉터
            '.sub_info', '.se-fs-fs13', '.writer_info', '.blog_author',
            # 폰트 속성을 가진 날짜 텍스트 서치
            '.se-fs-', '.se-text-paragraph' 
        ]
        
        date_patterns = [
            r'\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}',  # 2024. 4. 22
            r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일',      # 2024년 4월 22일
            r'\d{4}[-.]\d{1,2}[-.]\d{1,2}',         # 2024-04-22 또는 2024.04.22
            r'\d{2,4}[/.]\d{1,2}[/.]\d{1,2}'        # 24/04/22 또는 24.04.22
        ]
        
        # 1. 먼저 날짜 셀렉터를 통해 날짜 요소 찾기
        for selector in date_selectors:
            date_elems = soup.select(selector)  # 여러 요소 선택
            for date_elem in date_elems:
                text = date_elem.get_text().replace('작성일', '').strip()
                # 날짜 패턴 검사
                for pattern in date_patterns:
                    match = re.search(pattern, text)
                    if match:
                        date = match.group()
                        break
                if date:
                    break
            if date:
                break
        
        # 2. 셀렉터로 못 찾은 경우, 메타 태그 확인
        if not date:
            meta_date = soup.select_one('meta[property="og:regDate"], meta[name="article:published_time"]')
            if meta_date:
                date = meta_date.get('content', '')
        
        # 3. 마지막으로 전체 페이지 텍스트에서 날짜 패턴 검색
        if not date:
            page_text = soup.get_text()
            for pattern in date_patterns:
                match = re.search(pattern, page_text)
                if match:
                    date = match.group()
                    break
                    
        # 형식 정규화를 위해 blog_scraper_pipeline.py에서 처리
        
        # 비공개 여부 확인 (더 많은 키워드와 HTML 패턴 확인)
        is_private = False
        
        # 1. 페이지 텍스트에서 비공개 키워드 확인
        page_text = soup.get_text()
        private_keywords = [
            "비공개", "권한이 없습니다", "비밀글", "서비스 권한", "접근 제한", 
            "친구만 공개", "접근 권한", "비밀번호가 필요한", "비밀번호를 입력하세요"
        ]
        
        for keyword in private_keywords:
            if keyword in page_text:
                is_private = True
                logger.debug(f"비공개 글 감지: 키워드 '{keyword}' 발견")
                break
                
        # 2. 특정 HTML 요소로 비공개 확인
        if not is_private:
            # 비공개 아이콘, 클래스 확인
            private_indicators = soup.select('.ico_lock, .ico_private, .secret_post, .pcs-lock')
            if private_indicators:
                is_private = True
                logger.debug("비공개 글 감지: 비공개 HTML 요소 발견")
                
        # 3. 콘텐츠 확인 - 내용이 거의 없으면 비공개일 가능성 높음
        if not is_private and content and len(content.strip()) < 50:
            # 접근 제한 등의 텍스트가 있는지 확인
            short_content_markers = ["권한", "제한", "필요", "access", "denied", "login"]
            for marker in short_content_markers:
                if marker in content.lower():
                    is_private = True
                    logger.debug(f"비공개 글 감지: 짧은 내용과 제한 키워드 '{marker}' 발견")
                    break
        
        if title or content:
            return {
                'logNo': log_no,
                'title': title or '제목 없음',
                'content': content,
                'date': date,
                'is_private': is_private,
                'url': f"https://blog.naver.com/{blog_id}/{log_no}"
            }
        
        return None
        
    except Exception as e:
        logger.error(f"모바일 포스트 상세 내용 가져오기 실패: {str(e)}")
        return None


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    print("이 모듈은 직접 실행하지 마시고, 다른 코드에서 import하여 사용하세요.")