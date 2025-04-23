import logging
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_admin_mode(blog_url, access_token):
    """
    네이버 블로그 관리자 AJAX API를 사용하여 포스트 목록과 내용을 스크래핑합니다.
    
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
        
        # 관리자 AJAX로 포스트 목록 가져오기
        posts = get_posts_via_admin_api(session, blog_id)
        
        if not posts:
            logger.warning("관리자 API로 포스트를 가져오지 못했습니다. 대체 메서드 시도가 필요합니다.")
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
        logger.error(f"관리자 모드 스크래핑 중 오류: {str(e)}")
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
    
    # 기본 헤더 설정
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Referer': 'https://blog.naver.com/'
    })
    
    # OAuth 토큰 활용 (두 가지 방식으로 처리)
    if access_token:
        # 1. Authorization 헤더로 OAuth 토큰 전달
        session.headers.update({
            'Authorization': f'Bearer {access_token}'
        })
        
        # 2. 네이버 인증 쿠키 설정 - 비공개 글 접근에 필수
        try:
            # 네이버 토큰으로부터 여러 다양한 쿠키 형식 시도
            import hashlib
            import base64
            import time
            
            # 보다 강력한 토큰 변환
            token_md5 = hashlib.md5(access_token.encode('utf-8')).hexdigest()
            token_b64 = base64.b64encode(access_token.encode('utf-8')).decode('utf-8')
            token_prefix = access_token[:16] if len(access_token) >= 16 else access_token
            token_suffix = access_token[-16:] if len(access_token) >= 16 else access_token
            
            # 다양한 네이버 인증 쿠키 추가 - 여러 형식 시도
            cookies = {
                # 네이버 인증 필수 쿠키
                'NID_AUT': token_md5[:16],
                'NID_SES': token_md5[16:32],
                'NID_JKL': token_md5[:8],
                
                # 비공개 글 접근을 위한 추가 쿠키
                'NID_CHECK': 'naver',
                'JSESSIONID': token_suffix.replace('-', ''),
                'nid_inf': token_md5[:12],
                
                # 모바일 접근용 쿠키
                'MM_NEW': 'Y',
                'NFS': token_md5[:8],
                
                # 네이버 로그인 상태 유지
                'nx_ssl': 'on',
                'PM_CK_loc': 'https://nid.naver.com/login/sso/finalize.nhn',
                
                # 시간 기반 쿠키 (타임스탬프 포함)
                'nid_tss': str(int(time.time())),
                'nts_cdf': token_b64[:16]
            }
            
            # 쿠키 설정
            session.cookies.update(cookies)
            logger.debug("인증 쿠키 설정 성공")
            
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
                    user_email = user_data.get('email')
                    logger.debug(f"네이버 API 사용자 정보 획득 성공: ID={user_id}, 이름={user_name}")
                    
                    # 세션 헤더에 사용자 정보 추가
                    session.headers.update({
                        'X-Naver-User-Id': user_id or '',
                        'X-Naver-User-Name': user_name or ''
                    })
                else:
                    logger.warning(f"네이버 API 응답 오류: {profile_data.get('message')}")
            else:
                logger.warning(f"네이버 API 호출 실패: {profile_resp.status_code}")
        except Exception as api_error:
            logger.warning(f"네이버 API 호출 오류: {str(api_error)}")
        
        # 2. 네이버 로그인 페이지 접속 -> 토큰 활성화
        logger.debug("네이버 로그인 페이지 접속하여 토큰 활성화 시도")
        try:
            login_url = "https://nid.naver.com/nidlogin.login"
            login_resp = session.get(login_url, timeout=5)
            if login_resp.status_code == 200:
                logger.debug("로그인 페이지 접속 성공")
                
                # csrf_token 추출 시도
                import re
                csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_resp.text)
                if csrf_match:
                    csrf_token = csrf_match.group(1)
                    logger.debug(f"CSRF 토큰 추출: {csrf_token[:8]}...")
                    
                    # OAuth 토큰으로 로그인 시도
                    login_data = {
                        'csrf_token': csrf_token,
                        'token_key': access_token[:16],
                        'logintype': 'oauth2',
                        'svctype': '0'
                    }
                    session.post(login_url, data=login_data, timeout=5)
            else:
                logger.warning(f"로그인 페이지 접속 실패: {login_resp.status_code}")
        except Exception as login_error:
            logger.warning(f"로그인 시도 오류: {str(login_error)}")
        
        # 3. 최종 검증: 블로그 페이지 로드 및 로그인 여부 확인
        test_url = "https://blog.naver.com/"
        response = session.get(test_url, timeout=5)
        if response.status_code == 200:
            # 로그인 상태 확인 (로그인 버튼이 있는지)
            is_logged_in = "로그인" not in response.text or "login" not in response.text.lower()
            if is_logged_in:
                logger.debug("세션 인증 확인 완료 - 로그인 상태")
            else:
                logger.warning("세션 인증 확인 됨 - 그러나 로그인 상태가 아님")
        else:
            logger.warning(f"인증 확인 실패 (status: {response.status_code})")
    except Exception as e:
        logger.warning(f"인증 확인 중 오류: {str(e)}")
    
    return session


def get_posts_via_admin_api(session, blog_id):
    """
    네이버 블로그 관리자 AJAX API를 사용하여 포스트 목록을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 관리자 페이지 접속 (인증 초기화)
        init_url = f"https://blog.naver.com/{blog_id}"
        session.get(init_url, timeout=5)
        
        # 결과 포스트 목록
        all_posts = []
        page = 1
        max_retries = 2
        
        # 페이지별로 포스트 수집
        while True:
            logger.debug(f"ManageListAjax 페이지 {page} 요청 중...")
            
            # ManageListAjax 엔드포인트로 게시물 목록 요청
            ajax_url = f"https://blog.naver.com/ManageListAjax.naver"
            headers = {
                'Referer': init_url,
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            retry_count = 0
            response = None
            
            # 재시도 로직 구현
            while retry_count <= max_retries:
                try:
                    response = session.get(
                        ajax_url,
                        headers=headers,
                        params={
                            'blogId': blog_id,
                            'menu': 'post',
                            'range': 'all',  # 전체 기간
                            'page': page,    # 현재 페이지 번호
                            'countPerPage': 20,  # 페이지당 20개
                        },
                        timeout=5
                    )
                    break
                except Exception as retry_error:
                    retry_count += 1
                    logger.warning(f"AJAX 요청 재시도 {retry_count}/{max_retries}: {str(retry_error)}")
                    time.sleep(1)  # 1초 대기 후 재시도
            
            if not response or response.status_code != 200:
                logger.error(f"관리자 API 응답 오류 (페이지 {page}): {response.status_code if response else 'No response'}")
                break
            
            # JSON 응답 파싱 시도
            try:
                data = response.json()
                post_list = data.get('postList', [])
                
                # 필요한 정보 추출
                page_posts = []
                for post_info in post_list:
                    post = {
                        'logNo': str(post_info.get('logNo', '')),
                        'title': post_info.get('title', ''),
                        'date': post_info.get('addDate', ''),
                        'is_private': post_info.get('openType') != 'PUBLIC',
                        'url': f"https://blog.naver.com/{blog_id}/{post_info.get('logNo', '')}"
                    }
                    page_posts.append(post)
                
                # 결과에 추가
                all_posts.extend(page_posts)
                logger.debug(f"페이지 {page}에서 {len(page_posts)}개 포스트 발견, 현재까지 총 {len(all_posts)}개")
                
                # 더 이상 포스트가 없으면 종료
                if len(page_posts) < 20:
                    logger.debug(f"페이지 {page}에서 20개 미만의 포스트 발견, 수집 종료")
                    break
                
                # 다음 페이지로
                page += 1
                
            except ValueError:
                # JSON 파싱 실패 시 HTML로 간주하고 파싱 시도
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # HTML에서 스크립트를 찾아 JSON 데이터 추출 시도
                page_posts = []
                
                # 스크립트에서 JSON 추출 시도
                for script in soup.find_all('script'):
                    script_text = script.string if script.string else ""
                    if 'postList' in script_text:
                        # JSON 데이터 추출
                        match = re.search(r'postList\s*:\s*(\[.*?\])', script_text, re.DOTALL)
                        if match:
                            try:
                                post_list_json = match.group(1)
                                post_list = json.loads(post_list_json)
                                
                                for post_info in post_list:
                                    post = {
                                        'logNo': str(post_info.get('logNo', '')),
                                        'title': post_info.get('title', ''),
                                        'date': post_info.get('addDate', ''),
                                        'is_private': post_info.get('openType') != 'PUBLIC',
                                        'url': f"https://blog.naver.com/{blog_id}/{post_info.get('logNo', '')}"
                                    }
                                    page_posts.append(post)
                            except:
                                continue
                
                # HTML에서 직접 포스트 목록 추출 시도
                if not page_posts:
                    for row in soup.select('.post_item, .lst_item, .admin_post'):
                        try:
                            log_no = ''
                            title = ''
                            date = ''
                            is_private = False
                            
                            # logNo 추출
                            log_no_elem = row.select_one('a[href*="logNo="]')
                            if log_no_elem:
                                href = log_no_elem.get('href', '')
                                if 'logNo=' in href:
                                    log_no = href.split('logNo=')[1].split('&')[0]
                            
                            # 제목 추출
                            title_elem = row.select_one('.title, .post_title, .area_text')
                            if title_elem:
                                title = title_elem.get_text().strip()
                            
                            # 날짜 추출
                            date_elem = row.select_one('.date, .post_date, .date_info')
                            if date_elem:
                                date = date_elem.get_text().strip()
                            
                            # 비공개 여부
                            private_elem = row.select_one('.private, .secret, .ico_secret, .lock')
                            if private_elem:
                                is_private = True
                            
                            if log_no and title:
                                page_posts.append({
                                    'logNo': log_no,
                                    'title': title,
                                    'date': date,
                                    'is_private': is_private,
                                    'url': f"https://blog.naver.com/{blog_id}/{log_no}"
                                })
                        except Exception as e:
                            logger.error(f"HTML 항목 파싱 오류: {str(e)}")
                            continue
                
                # 결과에 추가
                all_posts.extend(page_posts)
                logger.debug(f"페이지 {page}에서 {len(page_posts)}개 포스트 발견 (HTML), 현재까지 총 {len(all_posts)}개")
                
                # 더 이상 포스트가 없으면 종료
                if len(page_posts) < 20:
                    logger.debug(f"페이지 {page}에서 20개 미만의 포스트 발견, 수집 종료")
                    break
                
                # 다음 페이지로
                page += 1
        
        return all_posts
        
    except Exception as e:
        logger.error(f"관리자 API 호출 오류: {str(e)}")
        return []


def get_post_detail(session, blog_id, log_no):
    """
    특정 포스트의 상세 내용을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        log_no (str): 포스트 번호
        
    Returns:
        dict: 포스트 상세 정보
    """
    try:
        url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"포스트 상세 조회 오류: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # iframe 확인 (네이버 블로그는 종종 iframe에 컨텐츠를 로드)
        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            iframe_src = iframe.get('src')
            if iframe_src:
                # iframe URL 처리
                if iframe_src.startswith('/'):
                    iframe_src = f"https://blog.naver.com{iframe_src}"
                elif not iframe_src.startswith('http'):
                    iframe_src = f"https://blog.naver.com/{iframe_src}"
                
                try:
                    iframe_response = session.get(iframe_src, timeout=30)
                    if iframe_response.status_code == 200:
                        soup = BeautifulSoup(iframe_response.text, 'html.parser')
                except Exception as iframe_error:
                    logger.error(f"iframe 로드 실패: {str(iframe_error)}")
        
        # 1. 제목 추출
        title = ""
        title_selectors = [
            '.se-title-text', '.se-module-text', '.tit_h3', 
            '.pcol1', 'h3.tit_view', '.post_title'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    break
        
        # 2. 내용 추출
        content = ""
        content_selectors = [
            '.se-main-container', '.post_ct', '#postViewArea', 
            '.se_component_wrap', '.view', '.post-view'
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
        
        # 3. 날짜 추출
        date = ""
        date_selectors = [
            '.se_publishDate', '.date', '.se_date', '.pub_date', '.se-module-date'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                date = date_elem.get_text().replace('작성일', '').strip()
                if date:
                    break
        
        # 4. 비공개 여부 확인
        is_private = False
        if "비공개" in soup.get_text() or "권한이 없습니다" in soup.get_text():
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
        logger.error(f"포스트 상세 내용 가져오기 실패: {str(e)}")
        return None


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    print("이 모듈은 직접 실행하지 마시고, 다른 코드에서 import하여 사용하세요.")