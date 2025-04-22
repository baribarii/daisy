import logging
import time
import json
import re
import requests
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
            # OAuth 토큰을 NID_AUT, NID_SES 쿠키로 변환
            # 접두사/접미사 분리 방식
            token_prefix = access_token[:16] if len(access_token) >= 16 else access_token
            token_suffix = access_token[-16:] if len(access_token) >= 16 else access_token
            
            # 주요 네이버 인증 쿠키 추가
            cookies = {
                'NID_AUT': token_prefix,
                'NID_SES': token_suffix,
                'NID_JKL': token_prefix[:8] if len(token_prefix) >= 8 else token_prefix,
                # 모바일 전용 인증 쿠키
                'MM_NEW': '1',
                'NID_M_CHECK': 'true',
                'NID_DEVICE': 'mobile',
                # 추가적인 네이버 쿠키로 인증 강화
                'NID_CHECK': 'naver',
                'JSESSIONID': token_suffix.replace('-', ''),
                'nid_inf': access_token.replace('-', '')[:12] if len(access_token) >= 12 else access_token,
            }
            
            # 쿠키 설정
            session.cookies.update(cookies)
            logger.debug("모바일 인증 쿠키 설정 성공")
            
        except Exception as e:
            logger.error(f"인증 쿠키 설정 중 오류: {str(e)}")
    
    # 세션 검증
    try:
        # 인증 확인
        test_url = "https://m.blog.naver.com/"
        response = session.get(test_url, timeout=5)
        if response.status_code == 200:
            logger.debug("모바일 세션 인증 확인 완료")
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
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"모바일 포스트 상세 조회 오류: {response.status_code}")
            return None
        
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
        
        # 비공개 여부 확인
        is_private = False
        page_text = soup.get_text()
        if "비공개" in page_text or "권한이 없습니다" in page_text:
            is_private = True
        
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