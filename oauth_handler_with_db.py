import os
import logging
from flask import session, flash, redirect, url_for
from oauth_scraper import scrape_blog_with_oauth
from utils_browser import fetch_all_posts_with_playwright
from scraper import extract_blog_id
from db_utils import save_multiple_posts, get_total_post_count

# 로깅 설정
logger = logging.getLogger(__name__)

def handle_blog_submission(blog_url, use_playwright=True):
    """
    블로그 URL을 받아 OAuth 토큰으로 스크래핑한 후 Replit DB에 저장합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        use_playwright (bool, optional): Playwright를 사용할지 여부. 기본값은 True.
                                        True인 경우 더 강화된 비공개 글 스크래핑 지원.
        
    Returns:
        tuple: (성공 여부, 메시지, 저장된 포스트 수)
    """
    if not blog_url:
        return (False, "블로그 URL을 입력해주세요.", 0)
    
    # 블로그 URL 검증
    if 'blog.naver.com' not in blog_url:
        return (False, "네이버 블로그 URL을 입력해주세요.", 0)
    
    # 로그인 여부 확인
    if 'access_token' not in session:
        return (False, "세션이 만료되었습니다. 다시 로그인해주세요.", 0)
    
    try:
        # 블로그 ID 추출
        blog_id = extract_blog_id(blog_url)
        if not blog_id:
            return (False, "블로그 URL에서 ID를 추출할 수 없습니다.", 0)
        
        # 스크래핑 방식 선택
        posts = []
        access_token = session.get('access_token')
        
        if use_playwright:
            try:
                logger.debug("Playwright로 스크래핑 시도")
                posts = fetch_all_posts_with_playwright(blog_id, access_token=access_token)
                logger.debug(f"Playwright로 {len(posts)}개 포스트 스크래핑 성공")
            except Exception as playwright_error:
                logger.error(f"Playwright 스크래핑 실패: {str(playwright_error)}")
                # Playwright 실패 시 일반 방식으로 폴백
                logger.debug("일반 OAuth 스크래핑으로 대체")
                posts = scrape_blog_with_oauth(blog_url, access_token)
        else:
            # 기존 방식으로 스크래핑
            posts = scrape_blog_with_oauth(blog_url, access_token)
        
        if not posts:
            return (False, "블로그에서 포스트를 찾을 수 없습니다. 비공개 설정을 확인해주세요.", 0)
        
        # 로그 기록
        private_count = sum(1 for post in posts if post.get('is_private', False))
        logger.debug(f"총 {len(posts)}개 포스트 추출 성공 (비공개 글: {private_count}개)")
        
        # Replit DB에 포스트 저장
        success_count, fail_count = save_multiple_posts(posts)
        
        # 현재 DB에 저장된 총 포스트 수
        total_posts = get_total_post_count()
        
        message = f"{success_count}개 포스트를 저장했습니다"
        if private_count > 0:
            message += f" (비공개 글 {private_count}개 포함)"
        if fail_count > 0:
            message += f". {fail_count}개는 저장에 실패했습니다."
        
        return (True, message, success_count)
    
    except Exception as e:
        logger.error(f"블로그 제출 오류: {str(e)}")
        return (False, f"오류가 발생했습니다: {str(e)}", 0)

# Flask 라우트 핸들러 통합 예제
"""
@app.route('/blog/submit_to_db', methods=['POST'])
def oauth_submit_blog_to_db():
    blog_url = request.form.get('blog_url', '')
    
    success, message, saved_count = handle_blog_submission(blog_url)
    
    if success:
        flash(message, 'success')
        return redirect(url_for('blog_stats'))
    else:
        flash(message, 'danger')
        return redirect(url_for('blog_form'))
"""