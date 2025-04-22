from playwright.sync_api import sync_playwright
import time
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def fetch_all_posts_with_playwright(blog_id: str, cookie_str: str = "", access_token: str = ""):
    """
    Playwright를 사용하여 네이버 블로그 콘텐츠를 수집합니다.
    OAuth 액세스 토큰 또는 쿠키 문자열을 사용하여 인증된 상태로 비공개 글을 포함한 
    모든 블로그 포스트를 스크래핑합니다.
    
    1) 인증 정보(OAuth 토큰 또는 쿠키)를 Playwright context에 설정
    2) 블로그 메인 PostList 페이지로 이동 → 스크롤 → 전체 logNo 추출
    3) 각 포스트 페이지 접속 → 콘텐츠 추출 (비공개 글 포함)
    
    Args:
        blog_id (str): 네이버 블로그 아이디
        cookie_str (str, optional): 네이버 쿠키 문자열 (로그인 상태 유지용)
        access_token (str, optional): OAuth 액세스 토큰 (OAuth 인증 사용 시)
        
    Returns:
        list: 블로그 포스트 목록 (각각 딕셔너리 형태)
    """
    logger.debug(f"Playwright를 사용한 블로그 스크래핑 시작: {blog_id}")
    posts = []
    
    try:
        with sync_playwright() as p:
            # Chromium 브라우저 실행 (headless 모드가 기본값)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # 인증 설정: 쿠키 또는 OAuth 토큰 기반
            if cookie_str:
                logger.debug("쿠키 문자열을 사용하여 인증 설정")
                for pair in cookie_str.split(';'):
                    if '=' not in pair:
                        continue
                    
                    name, value = pair.strip().split('=', 1)
                    logger.debug(f"쿠키 추가: {name}")
                    try:
                        # 여러 도메인에 쿠키 설정
                        for domain in ['.blog.naver.com', '.m.blog.naver.com', '.naver.com']:
                            context.add_cookies([{
                                'name': name,
                                'value': value,
                                'domain': domain,
                                'path': '/'
                            }])
                    except Exception as e:
                        logger.error(f"쿠키 추가 중 오류 ({name}): {str(e)}")
            
            # OAuth 토큰이 제공된 경우, 토큰에서 쿠키 생성
            elif access_token:
                logger.debug("OAuth 토큰을 사용하여 인증 설정")
                # 토큰을 분할하여 인증 쿠키 생성
                token_prefix = access_token[:16]  # 앞 부분
                token_suffix = access_token[-16:] # 뒷 부분
                
                # 주요 인증 쿠키 설정 (여러 도메인에)
                for domain in ['.blog.naver.com', '.m.blog.naver.com', '.naver.com']:
                    context.add_cookies([
                        {
                            'name': 'NID_AUT',
                            'value': token_prefix,
                            'domain': domain,
                            'path': '/'
                        },
                        {
                            'name': 'NID_SES',
                            'value': token_suffix,
                            'domain': domain,
                            'path': '/'
                        }
                    ])
                
                # Authorization 헤더 추가 (일반 헤더 설정)
                # Playwright 2.0 이상에서는 비동기 핸들러가 필요하지만, 
                # 헤더 추가만으로도 접근이 가능하므로 간소화
                logger.debug("OAuth 토큰으로 Authorization 헤더 설정")
                logger.debug("OAuth 인증 헤더 및 쿠키 설정 완료")
            else:
                logger.warning("인증 정보가 제공되지 않았습니다 - 일부 비공개 글에 접근할 수 없을 수 있습니다")
            
            page = context.new_page()
            
            # 1. 네이버 로그인 상태 초기화 (인증 쿠키 활성화)
            logger.debug("네이버 메인 페이지 방문하여 인증 초기화")
            try:
                page.goto("https://www.naver.com/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=10000)
                
                # 블로그 관련 쿠키 활성화를 위해 블로그 메인 방문
                page.goto("https://blog.naver.com/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=10000)
                
                logger.debug("인증 초기화 완료")
            except Exception as e:
                logger.error(f"인증 초기화 중 오류: {str(e)}")
            
            # 2. 포스트 ID(logNo) 수집
            lognos = set()
            
            # 여러 페이지에서 logNo 수집
            for page_num in range(1, 6):  # 최대 5 페이지까지 시도
                try:
                    logger.debug(f"블로그 목록 페이지 {page_num} 방문")
                    page.goto(f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&currentPage={page_num}", 
                              wait_until="domcontentloaded", timeout=30000)
                    
                    # 페이지 로딩 완료 대기
                    page.wait_for_load_state("networkidle", timeout=10000)
                    
                    # JavaScript가 실행된 후 더 많은 콘텐츠가 로드되도록 스크롤
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight / 2)")
                        time.sleep(1)
                    
                    # 페이지의 HTML 콘텐츠 가져오기
                    content = page.content()
                    
                    # logNo 찾기 (여러 패턴으로 시도)
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # 패턴 1: logNo 파라미터가 있는 링크 찾기
                    for link in soup.select('a[href*="logNo="]'):
                        href = link.get('href', '')
                        if 'logNo=' in href:
                            log_no = href.split('logNo=')[1].split('&')[0]
                            if log_no.isdigit():
                                lognos.add(log_no)
                                logger.debug(f"logNo 발견 (패턴1): {log_no}")
                    
                    # 패턴 2: 현대 네이버 블로그 형식 (/blogId/logNo)
                    for link in soup.select(f'a[href*="/{blog_id}/"]'):
                        href = link.get('href', '')
                        # 숫자만 있는 부분을 logNo로 간주
                        if f'/{blog_id}/' in href:
                            parts = href.split(f'/{blog_id}/')[1].split('?')[0].split('/')
                            for part in parts:
                                if part.isdigit():
                                    lognos.add(part)
                                    logger.debug(f"logNo 발견 (패턴2): {part}")
                    
                    # 패턴 3: 정규식 사용 (JavaScript 변수 등에서 logNo 추출)
                    import re
                    logno_pattern = re.compile(r'logNo=(\d+)')
                    for match in logno_pattern.finditer(content):
                        log_no = match.group(1)
                        if log_no.isdigit():
                            lognos.add(log_no)
                            logger.debug(f"logNo 발견 (정규식): {log_no}")
                    
                    # 또다른 패턴: post_id나 다른 식별자
                    postid_pattern = re.compile(r'post_id\s*:\s*[\'"]?(\d+)[\'"]?')
                    for match in postid_pattern.finditer(content):
                        log_no = match.group(1)
                        if log_no.isdigit():
                            lognos.add(log_no)
                            logger.debug(f"post_id 발견 (정규식): {log_no}")
                    
                    logger.debug(f"현재까지 고유한 logNo {len(lognos)}개 발견")
                    
                    # 다음 페이지가 없으면 중단
                    next_link = page.query_selector('a.page_next')
                    if not next_link and page_num > 1:
                        logger.debug(f"다음 페이지 없음, 페이지 {page_num}에서 중단")
                        break
                        
                except Exception as e:
                    logger.error(f"페이지 {page_num} 처리 중 오류: {str(e)}")
            
            # 모바일 버전에서도 시도
            try:
                logger.debug("모바일 블로그 목록 시도")
                page.goto(f"https://m.blog.naver.com/{blog_id}", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=10000)
                
                mobile_content = page.content()
                soup = BeautifulSoup(mobile_content, 'html.parser')
                
                # 모바일 링크에서 logNo 추출
                for link in soup.select('a[href*="logNo="]'):
                    href = link.get('href', '')
                    if 'logNo=' in href:
                        log_no = href.split('logNo=')[1].split('&')[0]
                        if log_no.isdigit():
                            lognos.add(log_no)
                            logger.debug(f"모바일에서 logNo 발견: {log_no}")
            except Exception as e:
                logger.error(f"모바일 버전 처리 중 오류: {str(e)}")
            
            logger.debug(f"총 {len(lognos)}개의 고유한 포스트 ID 발견")
            
            # 결과가 없으면 종료
            if not lognos:
                logger.warning("포스트 ID를 찾을 수 없습니다")
                browser.close()
                return []
            
            # 최대 30개로 제한 (너무 많은 경우)
            if len(lognos) > 30:
                logger.debug("30개 이상의 포스트 발견, 최근 30개로 제한합니다")
                lognos = list(lognos)[:30]
            
            # 3. 각 포스트 페이지를 방문하여 콘텐츠 수집
            successful_count = 0
            private_count = 0
            
            for logno in lognos:
                try:
                    # PC 버전과 모바일 버전 모두 시도
                    post_data = None
                    
                    # 먼저 모바일 버전 시도 (더 간단한 레이아웃)
                    try:
                        logger.debug(f"포스트 {logno} 모바일 버전 시도")
                        url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={logno}"
                        
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=10000)
                        
                        # 제목 추출
                        title = ""
                        title_selectors = [
                            '.se_title', '.tit_h3', '.se_textView .se_textarea', 
                            '.pcol1', 'h3.tit_view', '.se-title-text',
                            '.post_title', '.se-module-text', '.view_post_tit h2'
                        ]
                        
                        for selector in title_selectors:
                            title_elem = page.query_selector(selector)
                            if title_elem:
                                title = title_elem.inner_text().strip()
                                if title:
                                    logger.debug(f"제목 찾음: {title[:30]}...")
                                    break
                        
                        # 내용 추출
                        content = ""
                        content_selectors = [
                            '.se-main-container', '.se_component_wrap', '#viewTypeSelector', 
                            '.post_ct', '.se_doc_viewer', '.view', '#postViewArea', 
                            '.post-view', '.post_content', '.post_body', '.se-module-text'
                        ]
                        
                        for selector in content_selectors:
                            content_elem = page.query_selector(selector)
                            if content_elem:
                                content = content_elem.inner_text().strip()
                                if content:
                                    logger.debug(f"내용 찾음 ({len(content)} 자)")
                                    break
                        
                        # 날짜 추출
                        date = ""
                        date_selectors = [
                            '.se_publishDate', '.date', '.se_date', 
                            '.post_date', '.date_post', '.se-module-date'
                        ]
                        
                        for selector in date_selectors:
                            date_elem = page.query_selector(selector)
                            if date_elem:
                                date = date_elem.inner_text().replace('작성일', '').strip()
                                if date:
                                    break
                        
                        # 비공개 여부 확인
                        page_text = page.inner_text()
                        is_private = False
                        if "비공개" in page_text or "private" in page_text.lower() or "권한이 없습니다" in page_text:
                            is_private = True
                            logger.debug(f"비공개 글 감지: {logno}")
                        
                        # 결과 구성
                        if title or content:
                            post_data = {
                                "logNo": logno,
                                "title": title or "제목 없음",
                                "content": content,
                                "date": date,
                                "is_private": is_private,
                                "url": f"https://blog.naver.com/{blog_id}/{logno}"
                            }
                            logger.debug(f"모바일 버전에서 포스트 데이터 추출 성공: {title[:30]}...")
                    except Exception as e:
                        logger.error(f"모바일 버전 처리 중 오류: {str(e)}")
                    
                    # 모바일 버전이 실패하면 PC 버전 시도
                    if not post_data or not post_data.get('content'):
                        try:
                            logger.debug(f"포스트 {logno} PC 버전 시도")
                            url = f"https://blog.naver.com/{blog_id}/{logno}"
                            
                            page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_load_state("networkidle", timeout=10000)
                            
                            # iframe 확인 (네이버 블로그는 종종 iframe 사용)
                            iframe = page.query_selector('iframe#mainFrame')
                            if iframe:
                                iframe_src = iframe.get_attribute('src')
                                if iframe_src:
                                    # iframe URL 처리
                                    if iframe_src.startswith('/'):
                                        iframe_src = f"https://blog.naver.com{iframe_src}"
                                    elif not iframe_src.startswith('http'):
                                        iframe_src = f"https://blog.naver.com/{iframe_src}"
                                    
                                    logger.debug(f"아이프레임 감지: {iframe_src}")
                                    try:
                                        page.goto(iframe_src, wait_until="domcontentloaded", timeout=30000)
                                    except Exception as iframe_error:
                                        logger.error(f"아이프레임 이동 실패: {str(iframe_error)}")
                            
                            # 제목 추출
                            title_selectors = [
                                'div.se-title-text span', 'div.htitle', 'span.pcol1',
                                'h3.se_textarea', '.se-module-text', 'h3.title',
                                '.tit_h3', '.tit_view'
                            ]
                            
                            title = ""
                            for selector in title_selectors:
                                title_elem = page.query_selector(selector)
                                if title_elem:
                                    title = title_elem.inner_text().strip()
                                    if title:
                                        logger.debug(f"제목 찾음 (PC): {title[:30]}...")
                                        break
                            
                            # 내용 추출
                            content_selectors = [
                                'div.se-main-container', 'div#post-view', 'div.post-view',
                                'div.post_content', 'div.se_doc_viewer', '.se-module-text',
                                '.post_view', '.post_ct', '#postViewArea'
                            ]
                            
                            content = ""
                            for selector in content_selectors:
                                content_elem = page.query_selector(selector)
                                if content_elem:
                                    content = content_elem.inner_text().strip()
                                    if content:
                                        logger.debug(f"내용 찾음 (PC): {len(content)} 자")
                                        break
                            
                            # 날짜 추출
                            date_selectors = [
                                '.se_publishDate', '.date', '.se_date', '.pub_date',
                                '.se-module-date', '.blog2_container .se_date'
                            ]
                            
                            date = ""
                            for selector in date_selectors:
                                date_elem = page.query_selector(selector)
                                if date_elem:
                                    date = date_elem.inner_text().replace('작성일', '').strip()
                                    if date:
                                        break
                            
                            # 비공개 여부 확인
                            page_text = page.inner_text()
                            is_private = False
                            if "비공개" in page_text or "private" in page_text.lower() or "권한이 없습니다" in page_text:
                                is_private = True
                                logger.debug(f"비공개 글 감지 (PC): {logno}")
                            
                            # 결과 구성 또는 업데이트
                            if title or content:
                                if not post_data:
                                    post_data = {
                                        "logNo": logno,
                                        "title": title or "제목 없음",
                                        "content": content,
                                        "date": date,
                                        "is_private": is_private,
                                        "url": f"https://blog.naver.com/{blog_id}/{logno}"
                                    }
                                    logger.debug(f"PC 버전에서 포스트 데이터 추출 성공: {title[:30]}...")
                                else:
                                    # 기존 데이터가 있으면 내용만 보완
                                    if not post_data.get('content') and content:
                                        post_data['content'] = content
                                        logger.debug(f"PC 버전에서 내용 보완: {len(content)} 자")
                                    if not post_data.get('title') and title:
                                        post_data['title'] = title
                                        logger.debug(f"PC 버전에서 제목 보완: {title[:30]}...")
                        except Exception as e:
                            logger.error(f"PC 버전 처리 중 오류: {str(e)}")
                    
                    # 최종 결과 추가
                    if post_data and (post_data.get('title') or post_data.get('content')):
                        posts.append(post_data)
                        successful_count += 1
                        
                        if post_data.get('is_private', False):
                            private_count += 1
                        
                        logger.debug(f"포스트 {logno} 처리 완료: '{post_data.get('title', '')[:30]}...'")
                    else:
                        logger.warning(f"포스트 {logno}에서 콘텐츠를 추출하지 못했습니다")
                    
                    # 서버에 너무 빠른 요청을 보내지 않기 위한 대기
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"포스트 {logno} 처리 중 오류: {str(e)}")
            
            browser.close()
            
            logger.debug(f"총 {successful_count}개 포스트 스크래핑 완료 (비공개글: {private_count}개)")
            
            # 포스트 유효성 검사
            valid_posts = []
            for post in posts:
                # 최소한의 내용이 있는 포스트만 포함
                if post.get('content') and len(post.get('content', '')) > 50:
                    valid_posts.append(post)
                else:
                    logger.warning(f"내용이 부족한 포스트 제외: {post.get('logNo')}")
            
            logger.debug(f"유효한 포스트 {len(valid_posts)}개, 내용 부족 포스트 {len(posts) - len(valid_posts)}개")
            
            return valid_posts
        
    except Exception as e:
        logger.error(f"Playwright 스크래핑 중 오류: {str(e)}")
        raise Exception(f"Playwright로 블로그 스크래핑 실패: {str(e)}")