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

# 서버 세션 저장소 설정 - 쿠키 크기 문제 해결을 위해 파일 시스템 세션 사용
# Flask 기본 세션은 쿠키에 데이터를 저장하므로 크기 제한이 있음
# 따라서 대용량 세션 데이터를 서버에 저장하도록 변경
import os
from flask_session import Session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

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
    
    # 컨텍스트 매니저를 사용한 세션 관리
    try:
        # 스크래핑 시작
        flash('블로그 콘텐츠 수집을 시작합니다...', 'info')
        
        # 세션 작업 시작 
        # 데이터베이스에 블로그 등록
        blog = Blog(url=blog_url)
        db.session.add(blog)
        db.session.flush()  # ID 생성을 위해 플러시 (아직 커밋은 안 함)
        
        # 세션에 blog_id 저장 - 서버 세션 사용
        session['blog_id'] = blog.id
        
        # OAuth 토큰을 사용하여 스크래핑 - 여기서는 Replit DB를 사용하지 않는 간소화된 방식 사용
        try:
            # 블로그 ID 추출
            from scraper import extract_blog_id
            blog_id = extract_blog_id(blog_url)
            
            if not blog_id:
                raise ValueError("블로그 URL에서 ID를 추출할 수 없습니다.")
            
            # 네이버 OAuth API를 사용하여 블로그 정보 직접 가져오기
            import time
            import requests
            from bs4 import BeautifulSoup
            
            # 인증된 세션 생성
            api_session = requests.Session()
            api_session.headers.update({
                'Authorization': f'Bearer {session["access_token"]}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            # 직접 API 호출 - 최근 게시물 30개 가져오기
            posts = []
            
            # 블로그 메인에서 게시물 ID 수집
            response = api_session.get(f'https://blog.naver.com/{blog_id}')
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                post_links = soup.select('a[href*="logNo="]')
                
                log_nos = []
                for link in post_links:
                    href = link.get('href', '')
                    if 'logNo=' in href:
                        log_no = href.split('logNo=')[1].split('&')[0]
                        if log_no.isdigit() and log_no not in log_nos:
                            log_nos.append(log_no)
                
                # 최대 30개로 제한
                log_nos = log_nos[:30]
                
                # 각 게시물 내용 가져오기
                for log_no in log_nos:
                    try:
                        post_url = f'https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}'
                        post_response = api_session.get(post_url)
                        
                        if post_response.status_code == 200:
                            post_soup = BeautifulSoup(post_response.text, 'html.parser')
                            
                            # 제목 추출
                            title_elem = post_soup.select_one('.se-title-text, .tit_h3, .pcol1, h3.tit_view')
                            title = title_elem.get_text().strip() if title_elem else '제목 없음'
                            
                            # 본문 추출
                            content_elem = post_soup.select_one('.se-main-container, #postViewArea, .post_ct')
                            content = content_elem.get_text().strip() if content_elem else ''
                            
                            # 날짜 추출
                            date_elem = post_soup.select_one('.se_publishDate, .date, .se_date')
                            date = date_elem.get_text().strip() if date_elem else ''
                            
                            # 비공개 여부 확인
                            is_private = '비공개' in post_soup.get_text() or '권한이 없습니다' in post_soup.get_text()
                            
                            posts.append({
                                'logNo': log_no,
                                'title': title,
                                'content': content,
                                'date': date,
                                'is_private': is_private,
                                'url': post_url
                            })
                            
                            # 서버 부하 방지를 위한 짧은 대기
                            time.sleep(0.5)
                            
                    except Exception as post_error:
                        logger.error(f"포스트 {log_no} 처리 중 오류: {str(post_error)}")
            
            if not posts:
                raise ValueError("블로그에서 포스트를 찾을 수 없습니다. 블로그 URL을 확인해주세요.")
                
            logger.debug(f"성공적으로 {len(posts)}개의 포스트를 추출했습니다.")
            
        except Exception as e:
            logger.error(f"스크래핑 오류: {str(e)}")
            db.session.rollback()
            flash(f'블로그 스크래핑 중 오류가 발생했습니다: {str(e)}', 'danger')
            return redirect(url_for('blog_form'))
        
        if not posts:
            # 롤백 후 리다이렉트
            db.session.rollback()
            flash('블로그에서 포스트를 찾을 수 없습니다.', 'danger')
            return redirect(url_for('blog_form'))
        
        # 로그 기록
        logger.debug(f"성공적으로 {len(posts)}개의 포스트를 추출했습니다.")
        
        # 세션에 큰 데이터 저장 금지 - 스크랩한 포스트 내용을 세션에 직접 저장하지 않음
        # 대신 포스트 ID만 저장하고 필요할 때 DB에서 조회
        
        # 데이터베이스에 포스트 저장
        try:
            for post in posts:
                # 네이버 블로그의 실제 logNo(포스트 ID) 저장
                blog_post = BlogPost(
                    blog_id=blog.id,
                    title=post.get('title', ''),
                    content=post.get('content', ''),
                    date=post.get('date', ''),
                    is_private=post.get('is_private', False),
                    logNo=post.get('logNo', '')  # 네이버 블로그 포스트 ID
                )
                db.session.add(blog_post)
            
            # 모든 작업이 성공하면 커밋
            db.session.commit()
            
            # 분석 페이지로 리다이렉트
            return redirect(url_for('analyze_blog', blog_id=blog.id))
            
        except Exception as inner_e:
            # 데이터베이스 오류 발생 시 롤백
            db.session.rollback()
            logger.error(f"포스트 저장 중 오류: {str(inner_e)}")
            flash(f'포스트 저장 중 오류가 발생했습니다: {str(inner_e)}', 'danger')
            return redirect(url_for('blog_form'))
    
    except Exception as e:
        # 외부 예외 처리 - 세션 확인 및 닫기
        if db.session.is_active:
            db.session.rollback()
        
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
        # 블로그 콘텐츠 분석을 위한 전처리
        all_content = ""
        post_count = len(posts)
        logger.debug(f"총 {post_count}개의 포스트를 분석합니다.")
        
        # 날짜 순으로 정렬하여 시간에 따른 변화 분석 가능하도록 함
        sorted_posts = sorted(posts, key=lambda p: p.created_at if hasattr(p, 'created_at') and p.created_at else p.date if p.date else "")
        
        # 포스트 메타데이터와 함께 콘텐츠 구성
        for i, post in enumerate(sorted_posts, 1):
            # 포스트 번호와 날짜 추가
            date_info = f"작성일: {post.date}" if post.date else ""
            privacy_info = "[비공개 글]" if post.is_private else "[공개 글]"
            
            # 각 포스트별 구분선 추가하여 가독성 향상
            post_header = f"===== 포스트 {i}/{post_count} {privacy_info} {date_info} =====\n"
            
            # HTML 태그 제거 및 텍스트 정리
            import re
            clean_content = re.sub(r'<[^>]+>', ' ', post.content)  # HTML 태그 제거
            clean_content = re.sub(r'\s+', ' ', clean_content)     # 여러 공백을 하나로 통일
            
            # 제목과 콘텐츠 추가
            all_content += f"{post_header}\n제목: {post.title}\n\n내용:\n{clean_content}\n\n"
        
        # 로그에 분석할 총 콘텐츠 길이 기록
        logger.debug(f"분석할 총 콘텐츠 길이: {len(all_content)} 글자")
        
        try:
            # 세션에 큰 데이터 저장 금지 - 텍스트 내용을 session에 저장하지 않음
            
            # 콘텐츠 분석 실행
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
            
            # 중첩된 트랜잭션 방지를 위한 명시적 세션 관리
            db.session.add(report)
            db.session.commit()
            
            return redirect(url_for('view_report', report_id=report.id))
            
        except Exception as inner_e:
            # 중첩된 예외 처리
            if db.session.is_active:
                db.session.rollback()
            logger.error(f"콘텐츠 분석 및 리포트 생성 중 오류: {str(inner_e)}")
            flash(f'콘텐츠 분석 중 오류가 발생했습니다: {str(inner_e)}', 'danger')
            return redirect(url_for('index'))
    
    except Exception as e:
        # 최상위 예외 처리
        if db.session.is_active:
            db.session.rollback()
        logger.error(f"Error during analysis: {str(e)}")
        flash(f'An error occurred during analysis: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/report/<int:report_id>')
def view_report(report_id):
    try:
        # Get the report
        report = Report.query.get_or_404(report_id)
        
        # Get the blog
        blog = Blog.query.get_or_404(report.blog_id)
        
        # Get the blog posts (최대 30개까지 표시 - 최신 순으로 정렬)
        posts = BlogPost.query.filter_by(blog_id=report.blog_id).order_by(BlogPost.date.desc()).limit(30).all()
        
        # 세션에서 큰 데이터 저장 안 함 - 디스플레이용 정보만 메모리에서 처리
        post_views = []
        
        # 각 포스트 컨텐츠 중 일부만 발췌 (미리보기용)
        for post in posts:
            post_view = {}
            
            # 본문이 길면 앞부분 150자만 표시하고 '...' 추가 (UI 레이아웃 개선)
            if len(post.content) > 150:
                post_view['preview'] = post.content[:150] + '...'
            else:
                post_view['preview'] = post.content
            
            # 비공개 글인 경우 표시 추가
            if post.is_private:
                post_view['preview'] = "[비공개 글] " + post_view['preview']
            
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
                post_view['url'] = f"https://blog.naver.com/{blog_user_id}/{post.logNo}"
            else:
                # content에서 logNo 추출 시도
                logno_match = re.search(r'logNo=(\d+)', post.content)
                if logno_match:
                    logno = logno_match.group(1)
                    post_view['url'] = f"https://blog.naver.com/{blog_user_id}/{logno}"
                else:
                    # 마지막 대안: 데이터베이스 ID 사용 (실제 네이버 URL과 다를 수 있음)
                    post_view['url'] = f"https://blog.naver.com/{blog_user_id}?Redirect=Log&logNo={post.id}"
            
            # 필요한 기타 정보
            post_view['title'] = post.title
            post_view['date'] = post.date
            post_view['is_private'] = post.is_private
            
            # 메모리 내 배열에 추가
            post_views.append(post_view)
        
        # 블로그 및 보고서 정보의 필수 부분만 템플릿에 전달
        blog_info = {
            'id': blog.id,
            'url': blog.url
        }
        
        # 세션에 큰 데이터 저장 금지 (필요한 경우 ID만 저장하고 매번 DB에서 다시 가져오기)
        # 렌더링에만 필요한 데이터는 request/response 사이클에만 존재
        
        return render_template('report.html', report=report, blog=blog_info, posts=post_views)
        
    except Exception as e:
        # 예외 처리 - 세션 닫기 확인
        if db.session.is_active:
            db.session.rollback()
            
        logger.error(f"보고서 조회 중 오류: {str(e)}")
        flash(f'보고서를 조회하는 중 오류가 발생했습니다: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/status/<int:blog_id>')
def status(blog_id):
    try:
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
        
        # 세션 데이터를 최소화 - 세션에 상태 데이터를 저장하지 않고 API 응답으로만 반환
        return jsonify(status_data)
        
    except Exception as e:
        # 예외 발생 시 세션 롤백
        if db.session.is_active:
            db.session.rollback()
            
        logger.error(f"상태 확인 중 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="404 - Page Not Found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="500 - Server Error"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
