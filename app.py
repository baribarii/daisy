import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
import time
import urllib.parse
import markupsafe
import re

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1) # needed for url_for to generate with https

# configure the database, relative to the app instance folder
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///daisy.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# initialize the app with the extension
db.init_app(app)

# nl2br 필터 추가
@app.template_filter('nl2br')
def nl2br_filter(text):
    if not text:
        return ''
    # 개행 문자를 <br> 태그로 변경
    text = str(text)  # 문자열로 변환
    text = markupsafe.escape(text)  # HTML 이스케이프
    text = re.sub(r'\n', '<br>', text)
    return markupsafe.Markup(text)

with app.app_context():
    # Import the models here to create their tables
    from models import User, Blog, BlogPost, Report
    db.create_all()

from scraper import extract_blog_id
from analyzer import analyze_blog_content
from oauth_handler import get_authorization_url, get_token_from_code, get_user_info
from oauth_scraper import scrape_blog_with_oauth

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/oauth/login')
def oauth_login():
    """
    네이버 OAuth 로그인 시작
    """
    try:
        # 호스트 URL 가져오기 (Replit에서는 환경변수나 request.host_url 사용)
        host_url = request.host_url.rstrip('/')
        callback_url = f"{host_url}/oauth/callback"
        
        # 인증 URL 생성
        auth_url, state = get_authorization_url(callback_url)
        
        # 상태 저장
        session['oauth_state'] = state
        
        # 인증 페이지로 리다이렉트
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"OAuth 로그인 오류: {str(e)}")
        flash('로그인 과정에서 오류가 발생했습니다.', 'danger')
        return redirect(url_for('index'))

@app.route('/oauth/callback')
def oauth_callback():
    """
    네이버 OAuth 콜백 처리
    """
    try:
        # 인증 코드 및 상태 가져오기
        code = request.args.get('code')
        state = request.args.get('state')
        
        # 상태 확인
        stored_state = session.pop('oauth_state', None)
        if stored_state != state:
            flash('인증 과정에서 오류가 발생했습니다.', 'danger')
            return redirect(url_for('index'))
        
        # 액세스 토큰 발급
        token = get_token_from_code(code, state)
        if not token:
            flash('토큰 발급에 실패했습니다.', 'danger')
            return redirect(url_for('index'))
        
        # 사용자 정보 가져오기
        user_info = get_user_info(token)
        if not user_info:
            flash('사용자 정보를 가져오지 못했습니다.', 'danger')
            return redirect(url_for('index'))
        
        # 세션에 토큰 및 사용자 정보 저장
        session['access_token'] = token.get('access_token')
        session['refresh_token'] = token.get('refresh_token')
        session['user_id'] = user_info.get('id')
        session['user_name'] = user_info.get('name')
        session['user_email'] = user_info.get('email')
        
        # 블로그 수집 페이지로 리다이렉트
        flash('네이버 계정으로 로그인했습니다. 이제 블로그 주소를 입력하세요.', 'success')
        return redirect(url_for('blog_form'))
    except Exception as e:
        logger.error(f"OAuth 콜백 오류: {str(e)}")
        flash('로그인 콜백 처리 중 오류가 발생했습니다.', 'danger')
        return redirect(url_for('index'))

@app.route('/blog/form')
def blog_form():
    """
    블로그 URL 입력 폼
    """
    # 로그인 여부 확인
    if 'access_token' not in session:
        flash('먼저 네이버 계정으로 로그인해주세요.', 'warning')
        return redirect(url_for('index'))
    
    return render_template('blog_form.html', user_name=session.get('user_name'))

@app.route('/blog/submit', methods=['POST'])
def oauth_submit_blog():
    """
    OAuth 토큰을 사용하여 블로그 제출 처리
    """
    blog_url = request.form.get('blog_url', '')
    
    if not blog_url:
        flash('블로그 URL을 입력해주세요.', 'danger')
        return redirect(url_for('blog_form'))
    
    # 블로그 URL 검증
    if 'blog.naver.com' not in blog_url:
        flash('네이버 블로그 URL을 입력해주세요.', 'danger')
        return redirect(url_for('blog_form'))
    
    # 로그인 여부 확인
    if 'access_token' not in session:
        flash('세션이 만료되었습니다. 다시 로그인해주세요.', 'warning')
        return redirect(url_for('oauth_login'))
    
    try:
        # 스크래핑 시작
        flash('블로그 콘텐츠 수집을 시작합니다...', 'info')
        
        # 데이터베이스에 블로그 등록
        blog = Blog(url=blog_url)
        db.session.add(blog)
        db.session.commit()
        
        # 세션에 blog_id 저장
        session['blog_id'] = blog.id
        
        # OAuth 토큰을 사용하여 스크래핑
        posts = scrape_blog_with_oauth(blog_url, session['access_token'])
        
        if not posts:
            flash('블로그에서 포스트를 찾을 수 없습니다.', 'danger')
            return redirect(url_for('blog_form'))
        
        # 로그 기록
        logger.debug(f"성공적으로 {len(posts)}개의 포스트를 추출했습니다.")
        
        # 데이터베이스에 포스트 저장
        for post in posts:
            blog_post = BlogPost(
                blog_id=blog.id,
                title=post.get('title', ''),
                content=post.get('content', ''),
                date=post.get('date', ''),
                is_private=post.get('is_private', False)
            )
            db.session.add(blog_post)
        
        db.session.commit()
        
        # 분석 페이지로 리다이렉트
        return redirect(url_for('analyze_blog', blog_id=blog.id))
    
    except Exception as e:
        logger.error(f"블로그 제출 오류: {str(e)}")
        flash(f'오류가 발생했습니다: {str(e)}', 'danger')
        return redirect(url_for('blog_form'))

# 쿠키 기반 스크래핑이 제거되었으므로 submit_blog 라우트도 제거

@app.route('/analyze/<int:blog_id>')
def analyze_blog(blog_id):
    # Check if the blog exists
    blog = Blog.query.get_or_404(blog_id)
    
    # Fetch all posts for this blog
    posts = BlogPost.query.filter_by(blog_id=blog_id).all()
    
    if not posts:
        flash('No posts found for analysis', 'danger')
        return redirect(url_for('index'))
    
    # Check if a report already exists
    existing_report = Report.query.filter_by(blog_id=blog_id).first()
    if existing_report:
        return redirect(url_for('view_report', report_id=existing_report.id))
    
    try:
        # Prepare the blog content for analysis
        all_content = ""
        for post in posts:
            all_content += f"Title: {post.title}\nContent: {post.content}\nDate: {post.date}\n\n"
        
        # Analyze the content
        analysis_result = analyze_blog_content(all_content)
        
        # Create a new report
        report = Report(
            blog_id=blog_id,
            characteristics=analysis_result.get('characteristics', ''),
            strengths=analysis_result.get('strengths', ''),
            weaknesses=analysis_result.get('weaknesses', ''),
            thinking_patterns=analysis_result.get('thinking_patterns', ''),
            decision_making=analysis_result.get('decision_making', ''),
            unconscious_biases=analysis_result.get('unconscious_biases', ''),
            advice=analysis_result.get('advice', ''),
            created_at=time.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        db.session.add(report)
        db.session.commit()
        
        return redirect(url_for('view_report', report_id=report.id))
    
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        flash(f'An error occurred during analysis: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/report/<int:report_id>')
def view_report(report_id):
    # Get the report
    report = Report.query.get_or_404(report_id)
    
    # Get the blog
    blog = Blog.query.get_or_404(report.blog_id)
    
    # Get the blog posts (최대 30개까지 표시 - 최신 순으로 정렬)
    posts = BlogPost.query.filter_by(blog_id=report.blog_id).order_by(BlogPost.date.desc()).limit(30).all()
    
    # 각 포스트 컨텐츠 중 일부만 발췌 (미리보기용)
    for post in posts:
        # 본문이 길면 앞부분 150자만 표시하고 '...' 추가 (UI 레이아웃 개선)
        if len(post.content) > 150:
            post.preview = post.content[:150] + '...'
        else:
            post.preview = post.content
        
        # 비공개 글인 경우 표시 추가
        if post.is_private:
            post.preview = "[비공개 글] " + post.preview
        
        # 네이버 블로그 URL 형식으로 포스트 URL 구성
        # 블로그 URL에서 ID 추출
        import re
        from scraper import extract_blog_id
        
        # 블로그 URL에서 ID 추출
        blog_user_id = extract_blog_id(blog.url)
        if not blog_user_id:
            # URL에서 직접 추출 시도
            blog_user_id = blog.url.split('/')[-1]
            if '?' in blog_user_id:
                blog_user_id = blog_user_id.split('?')[0]
        
        # DB에 저장된 실제 logNo 사용 (BlogPost.logNo 필드 필요)
        # 데이터 모델에 logNo가 없으면 content에서 추출 시도
        if hasattr(post, 'logNo') and post.logNo:
            post.url = f"https://blog.naver.com/{blog_user_id}/{post.logNo}"
        else:
            # content에서 logNo 추출 시도
            logno_match = re.search(r'logNo=(\d+)', post.content)
            if logno_match:
                logno = logno_match.group(1)
                post.url = f"https://blog.naver.com/{blog_user_id}/{logno}"
            else:
                # 마지막 대안: 데이터베이스 ID 사용 (실제 네이버 URL과 다를 수 있음)
                post.url = f"https://blog.naver.com/{blog_user_id}?Redirect=Log&logNo={post.id}"
    
    return render_template('report.html', report=report, blog=blog, posts=posts)

@app.route('/status/<int:blog_id>')
def status(blog_id):
    # Check if the blog exists
    blog = Blog.query.get_or_404(blog_id)
    
    # Count posts for this blog
    post_count = BlogPost.query.filter_by(blog_id=blog_id).count()
    
    # Check if a report exists
    report = Report.query.filter_by(blog_id=blog_id).first()
    
    status_data = {
        'post_count': post_count,
        'has_report': report is not None,
        'report_id': report.id if report else None
    }
    
    return jsonify(status_data)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="404 - Page Not Found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="500 - Server Error"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
