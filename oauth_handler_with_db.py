import os
import logging
from flask import session, flash, redirect, url_for
from oauth_scraper import scrape_blog_with_oauth
from db_utils import save_multiple_posts, get_total_post_count

# 로깅 설정
logger = logging.getLogger(__name__)

def handle_blog_submission(blog_url):
    """
    블로그 URL을 받아 OAuth 토큰으로 스크래핑한 후 Replit DB에 저장합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        
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
        # OAuth 토큰을 사용하여 스크래핑
        posts = scrape_blog_with_oauth(blog_url, session['access_token'])
        
        if not posts:
            return (False, "블로그에서 포스트를 찾을 수 없습니다.", 0)
        
        # 로그 기록
        logger.debug(f"성공적으로 {len(posts)}개의 포스트를 추출했습니다.")
        
        # Replit DB에 포스트 저장
        success_count, fail_count = save_multiple_posts(posts)
        
        # 현재 DB에 저장된 총 포스트 수
        total_posts = get_total_post_count()
        
        return (
            True, 
            f"{success_count}개 포스트를 저장했습니다. {fail_count}개 저장 실패.", 
            success_count
        )
    
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