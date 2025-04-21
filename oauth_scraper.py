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
        액세스 토큰을 사용하여 인증된 세션 생성
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
        
        # 액세스 토큰을 사용하여 쿠키 획득
        try:
            # 네이버 메인 페이지에 액세스하여 쿠키 설정
            response = session.get('https://www.naver.com/', allow_redirects=True)
            
            # OAuth 프로필 API 호출
            profile_response = session.get('https://openapi.naver.com/v1/nid/me')
            if profile_response.status_code == 200:
                logger.debug("Successfully authenticated with OAuth token")
            else:
                logger.warning(f"OAuth profile API call failed: {profile_response.status_code}")
                
        except Exception as e:
            logger.error(f"Error setting up authenticated session: {str(e)}")
        
        return session
    
    def scrape_blog(self, blog_id):
        """
        블로그 스크래핑 메인 함수
        """
        logger.debug(f"Starting to scrape blog: {blog_id}")
        
        posts = []
        lognos = self._get_all_post_ids(blog_id)
        
        if not lognos:
            logger.warning("No post IDs found")
            return []
        
        logger.debug(f"Found {len(lognos)} post IDs")
        
        # 각 포스트 내용 가져오기
        for logno in lognos:
            try:
                post = self._get_post_content(blog_id, logno)
                if post:
                    posts.append(post)
                    # 네이버 서버에 부담을 주지 않기 위한 지연
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error scraping post {logno}: {str(e)}")
        
        return posts
    
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
        포스트 내용 가져오기
        """
        try:
            # 1. API로 시도
            api_url = f"https://blog.naver.com/api/blogs/{blog_id}/posts/{logno}"
            response = self.session.get(api_url)
            
            if response.status_code == 200:
                data = response.json()
                if 'result' in data:
                    result = data['result']
                    return {
                        'logNo': logno,
                        'title': result.get('title', ''),
                        'content': BeautifulSoup(result.get('contentHtml', ''), 'html.parser').get_text(separator='\n', strip=True),
                        'date': result.get('addDate', ''),
                        'is_private': not result.get('openType', True),
                        'url': f"https://blog.naver.com/{blog_id}/{logno}"
                    }
            
            # 2. HTML로 시도
            # 모바일 버전이 더 단순한 레이아웃
            url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={logno}"
            response = self.session.get(url)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch post {logno}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제목 추출
            title = ""
            title_selectors = [
                '.se_title', '.tit_h3', '.tit_view', 'h2.tit',
                '.se-title-text', '.post_title'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        break
            
            # 내용 추출
            content = ""
            content_selectors = [
                '.se_doc_viewer', '.view', '.post_ct', 
                '.post_view', '.post_content', '.se-main-container'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text(separator='\n', strip=True)
                    if content:
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
                    date = date_elem.get_text(strip=True)
                    if date:
                        break
            
            # 비공개 여부 확인
            is_private = "비공개" in soup.get_text() or "private" in soup.get_text().lower()
            
            if title or content:
                return {
                    'logNo': logno,
                    'title': title,
                    'content': content,
                    'date': date,
                    'is_private': is_private,
                    'url': f"https://blog.naver.com/{blog_id}/{logno}"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting post content for {logno}: {str(e)}")
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