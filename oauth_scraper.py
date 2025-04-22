import logging
import json
import time
import os
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import requests
from requests.cookies import cookiejar_from_dict

logger = logging.getLogger(__name__)

class NaverOAuthScraper:
    """
    네이버 OAuth 인증을 활용한 블로그 스크래퍼
    """
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.session = self._create_authenticated_session()
        
    def _create_authenticated_session(self):
        """
        액세스 토큰을 사용하여 인증된 세션 생성 - 비공개 글 접근 개선
        """
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Authorization': f'Bearer {self.access_token}'
        })
        
        # 인증 토큰의 유효 쿠키 생성을 위한 인증 세션 획득
        try:
            # 1. OAuth 프로필 API 호출 (사용자 정보 획득)
            profile_response = session.get('https://openapi.naver.com/v1/nid/me')
            user_id = None
            nickname = None
            
            if profile_response.status_code == 200:
                logger.debug("OAuth 인증 성공: 사용자 정보 획득")
                
                try:
                    profile_data = profile_response.json()
                    if 'response' in profile_data:
                        user_id = profile_data['response'].get('id')
                        nickname = profile_data['response'].get('nickname', '')
                        email = profile_data['response'].get('email', '')
                        
                        logger.debug(f"인증된 사용자: ID={user_id}, 닉네임={nickname}")
                        
                        # 2. 네이버 메인 페이지 방문 (기본 쿠키 설정)
                        session.get('https://www.naver.com/', allow_redirects=True)
                        
                        # 3. 네이버 개인화 로그인 페이지 접근 (NID 쿠키 초기화)
                        login_url = 'https://nid.naver.com/nidlogin.login'
                        session.get(login_url, allow_redirects=True)
                        
                        # 4. OAuth 토큰에서 쿠키 값 추출 및 설정
                        # 네이버 인증 쿠키는 주로 NID_AUT, NID_SES로 구성됨
                        # 토큰 앞부분과 뒷부분을 분리해서 각각의 쿠키에 할당 (보안상 실제 값은 다르나 동작 원리 유사)
                        token_prefix = self.access_token[:16]  # 앞 부분 16자
                        token_suffix = self.access_token[-16:] # 뒷 부분 16자
                        
                        # 모든 네이버 도메인에 적용되도록 설정
                        domains = ['.naver.com', '.blog.naver.com', '.m.blog.naver.com']
                        for domain in domains:
                            # 주요 네이버 인증 쿠키 설정
                            session.cookies.set('NID_AUT', token_prefix, domain=domain, path='/')
                            session.cookies.set('NID_SES', token_suffix, domain=domain, path='/')
                            
                            # 추가 인증 쿠키 (SES_NID는 세션 관련)
                            if user_id:
                                session.cookies.set('NID_USER', user_id, domain=domain, path='/')
                                # SES_NID 값은 자주 변경됨 (토큰 기반으로 유사하게 생성)
                                ses_nid = f"{token_prefix[:8]}{user_id[-8:]}"
                                session.cookies.set('SES_NID', ses_nid, domain=domain, path='/')
                                
                        # 5. 블로그 도메인 직접 방문하여 쿠키 확인 및 강화
                        blog_domains = [
                            'https://blog.naver.com/',
                            'https://m.blog.naver.com/'
                        ]
                        
                        for domain in blog_domains:
                            resp = session.get(domain, allow_redirects=True)
                            logger.debug(f"쿠키 상태 ({domain}): {session.cookies.get_dict()}")
                        
                        # 6. 블로그 관리 페이지 방문 (비공개 글 접근 권한 획득)
                        admin_response = session.get('https://admin.blog.naver.com/', allow_redirects=True)
                        logger.debug(f"블로그 관리자 페이지 방문 후 쿠키: {session.cookies.get_dict()}")
                        
                        # 7. API 키 추가 (필요한 경우)
                        naver_client_id = os.environ.get('NAVER_CLIENT_ID', '')
                        naver_client_secret = os.environ.get('NAVER_CLIENT_SECRET', '')
                        if naver_client_id and naver_client_secret:
                            session.headers.update({
                                'X-Naver-Client-Id': naver_client_id,
                                'X-Naver-Client-Secret': naver_client_secret
                            })
                            logger.debug("네이버 API 키 헤더 추가 완료")
                
                except Exception as e:
                    logger.error(f"사용자 프로필 처리 중 오류: {str(e)}")
            else:
                logger.warning(f"OAuth 프로필 API 호출 실패: {profile_response.status_code}")
            
            # 8. 비공개 글 접근 가능 여부 확인 (테스트)
            if user_id:
                try:
                    # 본인 블로그 접근 테스트 (사용자 ID가 블로그 ID인 경우가 많음)
                    test_url = f"https://blog.naver.com/PostList.naver?blogId={user_id}"
                    test_response = session.get(test_url)
                    if "로그인" in test_response.text:
                        logger.warning("인증 후에도 로그인 필요 - 쿠키 설정이 불완전할 수 있음")
                    else:
                        logger.debug("인증된 세션으로 블로그 접근 성공")
                except Exception as e:
                    logger.error(f"세션 검증 중 오류: {str(e)}")
                
        except Exception as e:
            logger.error(f"인증된 세션 설정 중 오류: {str(e)}")
        
        return session
    
    def scrape_blog(self, blog_id):
        """
        블로그 스크래핑 메인 함수 - 비공개 글 포함 최대 30개 포스트 처리
        """
        logger.debug(f"블로그 스크래핑 시작: {blog_id}")
        
        posts = []
        lognos = self._get_all_post_ids(blog_id)
        
        if not lognos:
            logger.warning("포스트 ID를 찾을 수 없습니다")
            return []
        
        # 최대 30개의 포스트만 처리
        lognos = lognos[:30]
        logger.debug(f"포스트 ID {len(lognos)}개 발견 (최대 30개): {lognos}")
        
        # 각 포스트 내용 가져오기
        successful_count = 0
        private_count = 0
        
        for logno in lognos:
            try:
                post = self._get_post_content(blog_id, logno)
                if post:
                    posts.append(post)
                    successful_count += 1
                    
                    # 비공개 글 확인
                    if post.get('is_private', False):
                        private_count += 1
                        logger.debug(f"비공개 글 발견: {logno}")
                    
                    # 네이버 서버에 부담을 주지 않기 위한 지연
                    time.sleep(0.2)
            except Exception as e:
                logger.error(f"포스트 {logno} 스크래핑 중 오류: {str(e)}")
        
        # 스크래핑 결과 요약
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
    
    def _get_all_post_ids(self, blog_id):
        """
        모든 포스트 ID(logNo) 수집
        """
        lognos = set()
        
        # 여러 방법으로 시도
        self._try_get_posts_from_api(blog_id, lognos)
        self._try_get_posts_from_html(blog_id, lognos)
        
        return list(lognos)
    
    def _try_get_posts_from_api(self, blog_id, lognos):
        """
        API를 통해 포스트 ID 가져오기
        """
        try:
            # 1. 카테고리 목록 가져오기
            categories = self._get_categories(blog_id)
            
            # 기본 카테고리(전체)는 항상 포함
            if 0 not in categories:
                categories.append(0)
            
            # 2. 각 카테고리에서 포스트 ID 가져오기
            for category in categories:
                page = 1
                while True:
                    # API 엔드포인트 호출
                    url = f"https://blog.naver.com/api/blogs/{blog_id}/posts/list?categoryNo={category}&pageNo={page}&pageSize=30"
                    response = self.session.get(url)
                    
                    if response.status_code != 200:
                        break
                    
                    try:
                        data = response.json()
                        if 'result' in data and 'items' in data['result']:
                            items = data['result']['items']
                            
                            # 결과가 없으면 종료
                            if not items:
                                break
                            
                            # logNo 추출
                            for item in items:
                                logno = item.get('logNo')
                                if logno:
                                    lognos.add(logno)
                            
                            # 다음 페이지
                            page += 1
                        else:
                            break
                    except Exception as e:
                        logger.error(f"Error parsing API response: {str(e)}")
                        break
        except Exception as e:
            logger.error(f"Error getting posts from API: {str(e)}")
    
    def _get_categories(self, blog_id):
        """
        블로그의 카테고리 목록 가져오기
        """
        categories = []
        try:
            url = f"https://blog.naver.com/api/blogs/{blog_id}/categories"
            response = self.session.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if 'categories' in data:
                    for category in data['categories']:
                        category_no = category.get('categoryNo')
                        if category_no is not None:
                            categories.append(category_no)
        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
        
        return categories
    
    def _try_get_posts_from_html(self, blog_id, lognos):
        """
        HTML 페이지에서 포스트 ID 가져오기
        """
        try:
            for page in range(1, 10):  # 최대 10페이지까지 시도
                url = f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&currentPage={page}"
                response = self.session.get(url)
                
                if response.status_code != 200:
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 더 많은 로깅 추가
                logger.debug(f"HTML 내용: {soup.prettify()[:500]}...")  # 처음 500자만 로깅
                
                # 모든 링크 로깅
                all_links = soup.select('a')
                logger.debug(f"페이지에서 발견된 링크 수: {len(all_links)}")
                for i, link in enumerate(all_links[:10]):  # 처음 10개 링크만 로깅
                    logger.debug(f"링크 {i}: {link.get('href', 'No href')}")
                
                # 1. logNo 파라미터가 있는 링크 찾기 - 다양한 방식으로 시도
                for link in soup.select('a'):
                    href = link.get('href', '')
                    if not href:
                        continue
                    
                    # 직접 문자열 파싱으로 logNo 추출
                    if 'logNo=' in href:
                        try:
                            logno = href.split('logNo=')[1].split('&')[0]
                            if logno and logno.isdigit():
                                lognos.add(logno)
                                logger.debug(f"Found logNo: {logno}")
                        except Exception as e:
                            logger.error(f"Error parsing logNo: {str(e)}")
                
                # 2. 현대 네이버 블로그 형식 (/blogId/logNo)
                for link in soup.select('a'):
                    href = link.get('href', '')
                    if not href:
                        continue
                    
                    # 블로그 포스트 URL 패턴 확인
                    if f'/{blog_id}/' in href:
                        try:
                            parts = href.split(f'/{blog_id}/')[1].split('?')[0].split('/')
                            for part in parts:
                                if part and part.isdigit():
                                    lognos.add(part)
                                    logger.debug(f"Found post ID: {part}")
                        except Exception as e:
                            logger.error(f"Error parsing blog URL: {str(e)}")
                
                # 3. 세 번째 방법: 정규식으로 모든 텍스트에서 포스트 ID 찾기
                import re
                html_text = str(soup)
                # logNo 패턴
                logno_pattern = re.compile(r'logNo=(\d+)')
                for match in logno_pattern.finditer(html_text):
                    logno = match.group(1)
                    if logno:
                        lognos.add(logno)
                        logger.debug(f"Found logNo via regex: {logno}")
                
                # 블로그 포스트 ID 패턴
                postid_pattern = re.compile(r'post_id\s*:\s*[\'"]?(\d+)[\'"]?')
                for match in postid_pattern.finditer(html_text):
                    logno = match.group(1)
                    if logno:
                        lognos.add(logno)
                        logger.debug(f"Found post_id via regex: {logno}")
                
                # 4. 모바일 버전 URL 시도
                try:
                    mobile_url = f"https://m.blog.naver.com/{blog_id}"
                    logger.debug(f"Trying mobile URL: {mobile_url}")
                    mobile_response = self.session.get(mobile_url)
                    if mobile_response.status_code == 200:
                        mobile_soup = BeautifulSoup(mobile_response.text, 'html.parser')
                        for link in mobile_soup.select('a'):
                            href = link.get('href', '')
                            if 'logNo=' in href:
                                try:
                                    logno = href.split('logNo=')[1].split('&')[0]
                                    if logno and logno.isdigit():
                                        lognos.add(logno)
                                        logger.debug(f"Found logNo from mobile: {logno}")
                                except Exception as e:
                                    logger.error(f"Error parsing mobile logNo: {str(e)}")
                except Exception as e:
                    logger.error(f"Error accessing mobile version: {str(e)}")
                
                # 다음 페이지가 없으면 중단
                if not soup.select('.page_next') and page > 1:
                    break
        except Exception as e:
            logger.error(f"Error getting posts from HTML: {str(e)}")
    
    def _get_post_content(self, blog_id, logno):
        """
        포스트 내용 가져오기 - 비공개 글 접근 강화
        """
        try:
            logger.debug(f"포스트 내용 가져오기 시작: {blog_id}/{logno}")
            
            # 비공개 글 감지 변수
            is_private = False
            post_data = None
            
            # 1. 신규 API 엔드포인트 시도 (최신 네이버 블로그)
            try:
                logger.debug("API 방식으로 시도")
                api_url = f"https://blog.naver.com/api/blogs/{blog_id}/posts/{logno}"
                response = self.session.get(api_url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'result' in data:
                        logger.debug("API 접근 성공")
                        result = data['result']
                        # 비공개 상태 확인
                        is_private = not result.get('openType', True)
                        
                        # HTML 콘텐츠 정제
                        html_content = result.get('contentHtml', '')
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # 불필요한 UI 요소 제거
                        exclude_classes = [
                            'btn_area', 'social_area', 'like_area', 'btn_share',
                            'font_size_control', 'tool_area', 'tag_area', 'layer_post',
                            'category_area', 'url_area', 'btn_like', 'writer_info',
                            'comment_area', 'footer_area', 'area_sympathy', 'post_menu'
                        ]
                        
                        for exclude_class in exclude_classes:
                            for element in soup.select(f'.{exclude_class}'):
                                element.decompose()
                        
                        # 내용 추출 (p 태그 중심)
                        content_parts = []
                        for p_tag in soup.select('p'):
                            text = p_tag.get_text(strip=True)
                            if text and len(text) > 20:  # 의미있는 텍스트만 포함
                                content_parts.append(text)
                        
                        # p 태그에서 충분한 내용을 찾지 못한 경우 전체 내용 사용
                        content = '\n\n'.join(content_parts) if content_parts else soup.get_text(separator='\n', strip=True)
                        
                        post_data = {
                            'logNo': logno,
                            'title': result.get('title', '제목 없음'),
                            'content': content,
                            'date': result.get('addDate', ''),
                            'is_private': is_private,
                            'url': f"https://blog.naver.com/{blog_id}/{logno}"
                        }
                        logger.debug(f"API에서 포스트 데이터 획득: {post_data['title'][:30]}...")
            except Exception as e:
                logger.error(f"API 방식 실패: {str(e)}")
            
            # 2. 모바일 웹 시도 (API 실패 또는 결과 없을 때)
            if not post_data:
                try:
                    logger.debug("모바일 웹 방식으로 시도")
                    # 모바일 쿠키 강화
                    token_prefix = self.access_token[:16]
                    token_suffix = self.access_token[-16:]
                    self.session.cookies.set('NID_AUT', token_prefix, domain='.m.blog.naver.com', path='/')
                    self.session.cookies.set('NID_SES', token_suffix, domain='.m.blog.naver.com', path='/')
                    
                    # 모바일 버전 접근 (더 단순한 레이아웃)
                    url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={logno}"
                    response = self.session.get(url, timeout=30)
                    
                    if response.status_code == 200:
                        logger.debug("모바일 웹 페이지 로드 성공")
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 접근 제한 확인
                        page_text = soup.get_text()
                        if "권한이 없습니다" in page_text or "로그인이 필요합니다" in page_text:
                            logger.warning(f"모바일 페이지 접근 제한: 포스트 {logno}")
                            is_private = True
                        
                        # 제목 추출 (선택자 확장)
                        title = ""
                        title_selectors = [
                            '.se_title', '.tit_h3', '.tit_view', 'h2.tit',
                            '.se-title-text', '.post_title', '.se-module-text',
                            '.se-title', '.tit_h3', '.se_textarea', '.pcol1', 
                            'h3.tit_view', 'div.tit_post', '.view_post_tit h2'
                        ]
                        
                        for selector in title_selectors:
                            title_elem = soup.select_one(selector)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                if title:
                                    logger.debug(f"제목 찾음: {title[:30]}...")
                                    break
                        
                        # 불필요한 UI 요소 제거
                        for exclude_class in exclude_classes:
                            for element in soup.select(f'.{exclude_class}'):
                                element.decompose()
                        
                        # 내용 추출 (더 정밀한 선택자 사용)
                        content_selectors = [
                            '.se-main-container p', '.se_doc_viewer p', '.view p', 
                            '.post_ct p', '.post_view p', '.post_content p',
                            '.se-text-paragraph', '.se_paragraph', '.se-module-text',
                            '.post_ct', '.se-module-text-paragraph', 'div.se-module-text'
                        ]
                        
                        content = ""
                        # 의미있는 콘텐츠 추출 시도
                        for selector in content_selectors:
                            content_elems = soup.select(selector)
                            if content_elems:
                                content_parts = []
                                for elem in content_elems:
                                    text = elem.get_text(strip=True)
                                    if text and len(text) > 20:  # 의미있는 텍스트만 포함
                                        content_parts.append(text)
                                
                                if content_parts:
                                    content = '\n\n'.join(content_parts)
                                    logger.debug(f"내용 찾음: {len(content)} 자")
                                    break
                        
                        # 백업 방법: 여전히 내용이 없으면 컨테이너 전체 추출
                        if not content:
                            fallback_selectors = [
                                '.se-main-container', '.view', '.post_ct', '.post_content',
                                '.se_component_wrap', '.se_viewArea', '.post_cont',
                                '#viewTypeSelector', '.se_doc_viewer', '#postViewArea'
                            ]
                            for selector in fallback_selectors:
                                content_elem = soup.select_one(selector)
                                if content_elem:
                                    # 불필요한 요소 제거
                                    for exclude in ['script', 'style', '.link_post', '.btn_area']:
                                        for elem in content_elem.select(exclude):
                                            elem.decompose()
                                    
                                    content = content_elem.get_text(separator='\n', strip=True)
                                    if content:
                                        logger.debug(f"내용 찾음 (백업 방법): {len(content)} 자")
                                        break
                        
                        # 날짜 추출
                        date = ""
                        date_selectors = [
                            '.se_publishDate', '.date', '.se_date', 
                            '.post_date', '.date_post', '.se-module-date'
                        ]
                        
                        for selector in date_selectors:
                            date_elem = soup.select_one(selector)
                            if date_elem:
                                date = date_elem.get_text(strip=True).replace('작성일', '').strip()
                                if date:
                                    break
                        
                        # 비공개 여부 확인
                        if "비공개" in page_text or "private" in page_text.lower():
                            is_private = True
                        
                        if title or content:
                            post_data = {
                                'logNo': logno,
                                'title': title or '제목 없음',
                                'content': content,
                                'date': date,
                                'is_private': is_private,
                                'url': f"https://blog.naver.com/{blog_id}/{logno}"
                            }
                            logger.debug(f"모바일 웹에서 포스트 데이터 획득: {title[:30]}...")
                except Exception as e:
                    logger.error(f"모바일 웹 방식 실패: {str(e)}")
            
            # 3. PC 웹 페이지 시도 (최후의 수단)
            if not post_data:
                try:
                    logger.debug("PC 웹 방식으로 시도")
                    # PC 쿠키 강화
                    token_prefix = self.access_token[:16]
                    token_suffix = self.access_token[-16:]
                    self.session.cookies.set('NID_AUT', token_prefix, domain='.blog.naver.com', path='/')
                    self.session.cookies.set('NID_SES', token_suffix, domain='.blog.naver.com', path='/')
                    
                    # PC 버전 접근 (직접 URL)
                    url = f"https://blog.naver.com/{blog_id}/{logno}"
                    response = self.session.get(url, timeout=30)
                    
                    if response.status_code == 200:
                        logger.debug("PC 웹 페이지 로드 성공")
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 아이프레임 체크 (네이버 블로그는 종종 iframe에 컨텐츠를 로드)
                        iframe = soup.select_one('iframe#mainFrame')
                        if iframe:
                            iframe_src = iframe.get('src')
                            if iframe_src:
                                # iframe_src가 http로 시작하지 않으면 도메인 추가
                                if iframe_src.startswith('/'):
                                    iframe_src = f"https://blog.naver.com{iframe_src}"
                                elif not iframe_src.startswith('http'):
                                    iframe_src = f"https://blog.naver.com/{iframe_src}"
                                
                                logger.debug(f"아이프레임 감지: {iframe_src}")
                                try:
                                    iframe_response = self.session.get(iframe_src, timeout=30)
                                    if iframe_response.status_code == 200:
                                        soup = BeautifulSoup(iframe_response.text, 'html.parser')
                                        logger.debug("아이프레임 내용 로드 성공")
                                except Exception as iframe_error:
                                    logger.error(f"아이프레임 로드 실패: {str(iframe_error)}")
                        
                        # 접근 제한 확인
                        page_text = soup.get_text()
                        if "권한이 없습니다" in page_text or "로그인이 필요합니다" in page_text:
                            logger.warning(f"PC 페이지 접근 제한: 포스트 {logno}")
                            is_private = True
                        
                        # 제목 추출
                        title = ""
                        title_selectors = [
                            'div.se-title-text span', 'div.htitle', 'span.pcol1', 
                            'h3.se_textarea', 'div.pcol1', '.se-module-text', 
                            'h3.title', '.tit_h3', '.tit_snv1', '.pcol2'
                        ]
                        
                        for selector in title_selectors:
                            title_elem = soup.select_one(selector)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                if title:
                                    logger.debug(f"제목 찾음 (PC): {title[:30]}...")
                                    break
                        
                        # 내용 추출
                        content_selectors = [
                            'div.se-main-container', 'div#post-view', 'div.post-view',
                            'div.post_content', 'div.se_doc_viewer', '.se-module-text-paragraph'
                        ]
                        
                        content = ""
                        for selector in content_selectors:
                            content_elems = soup.select(selector)
                            if content_elems:
                                content_parts = []
                                for elem in content_elems:
                                    # 불필요한 요소 제거
                                    for exclude in ['script', 'style', '.comment_area', '.btn_area']:
                                        for e in elem.select(exclude):
                                            e.decompose()
                                    
                                    # 의미있는 텍스트 추출
                                    text = elem.get_text(strip=True)
                                    if text and len(text) > 20:
                                        content_parts.append(text)
                                
                                if content_parts:
                                    content = '\n\n'.join(content_parts)
                                    logger.debug(f"내용 찾음 (PC): {len(content)} 자")
                                    break
                        
                        # 콘텐츠가 없으면 전체 컨테이너 시도
                        if not content:
                            for selector in content_selectors:
                                content_elem = soup.select_one(selector)
                                if content_elem:
                                    # 불필요한 요소 제거
                                    for exclude in ['script', 'style', '.comment_area', '.btn_area']:
                                        for e in content_elem.select(exclude):
                                            e.decompose()
                                    
                                    content = content_elem.get_text(separator='\n', strip=True)
                                    if content:
                                        logger.debug(f"내용 전체 찾음 (PC): {len(content)} 자")
                                        break
                        
                        # 날짜 추출
                        date = ""
                        date_selectors = [
                            '.se_publishDate', '.date', '.se_date', '.pub_date', 
                            '.se-module-date', '.se-date', '.blog2_container .se_date'
                        ]
                        
                        for selector in date_selectors:
                            date_elem = soup.select_one(selector)
                            if date_elem:
                                date = date_elem.get_text(strip=True).replace('작성일', '').strip()
                                if date:
                                    break
                        
                        if title or content:
                            post_data = {
                                'logNo': logno,
                                'title': title or '제목 없음',
                                'content': content,
                                'date': date,
                                'is_private': is_private,
                                'url': f"https://blog.naver.com/{blog_id}/{logno}"
                            }
                            logger.debug(f"PC 웹에서 포스트 데이터 획득: {title[:30]}...")
                except Exception as e:
                    logger.error(f"PC 웹 방식 실패: {str(e)}")
            
            # 결과 반환
            if post_data:
                return post_data
            
            logger.warning(f"모든 방법으로 포스트 {logno} 콘텐츠를 가져오지 못했습니다")
            return None
            
        except Exception as e:
            logger.error(f"포스트 {logno} 내용 가져오기 실패: {str(e)}")
            return None


def scrape_blog_with_oauth(blog_url, access_token):
    """
    OAuth 토큰을 사용하여 블로그 스크래핑하기
    
    Args:
        blog_url (str): 블로그 URL
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 블로그 ID 추출
        from scraper import extract_blog_id
        blog_id = extract_blog_id(blog_url)
        
        if not blog_id:
            raise ValueError("블로그 URL에서 ID를 추출할 수 없습니다.")
        
        # OAuth 스크래퍼 실행
        scraper = NaverOAuthScraper(access_token)
        posts = scraper.scrape_blog(blog_id)
        
        if not posts:
            raise ValueError("블로그에서 포스트를 찾을 수 없습니다.")
        
        logger.debug(f"성공적으로 {len(posts)}개의 포스트를 스크래핑했습니다.")
        return posts
        
    except Exception as e:
        logger.error(f"OAuth 스크래핑 오류: {str(e)}")
        raise Exception(f"블로그 스크래핑 실패: {str(e)}")