import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
import time

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

with app.app_context():
    # Import the models here to create their tables
    from models import User, Blog, BlogPost, Report
    db.create_all()

from scraper import scrape_naver_blog
from analyzer import analyze_blog_content

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit_blog', methods=['POST'])
def submit_blog():
    blog_url = request.form.get('blog_url', '')
    cookie_value = request.form.get('cookie_value', '')
    
    if not blog_url or not cookie_value:
        flash('Blog URL and cookie value are required', 'danger')
        return redirect(url_for('index'))
    
    # Validate the blog URL
    if 'blog.naver.com' not in blog_url:
        flash('Please enter a valid Naver blog URL', 'danger')
        return redirect(url_for('index'))
    
    try:
        # Start the scraping process
        flash('Starting to collect blog content...', 'info')
        
        # Create a new blog entry in the database
        blog = Blog(url=blog_url)
        db.session.add(blog)
        db.session.commit()
        
        # Store blog_id in session for tracking
        session['blog_id'] = blog.id
        
        # 여러 스크래핑 방법 시도
        try:
            # 1. 먼저 원래 스크래퍼 시도
            from scraper import scrape_naver_blog
            logger.debug("Trying original scraper...")
            posts = scrape_naver_blog(blog_url, cookie_value)
        except Exception as e:
            logger.warning(f"Original scraper failed: {str(e)}")
            
            # 2. 대체 스크래퍼 시도
            try:
                logger.debug("Trying fallback scraper...")
                from fallback_scraper import scrape_naver_blog_with_fallback
                posts = scrape_naver_blog_with_fallback(blog_url, cookie_value)
            except Exception as e2:
                logger.error(f"Fallback scraper also failed: {str(e2)}")
                raise Exception(f"Failed to extract any posts from the blog. Please check the blog URL and cookie value.")
        
        if not posts:
            flash('No posts found or unable to access the blog', 'danger')
            return redirect(url_for('index'))
        
        # Log number of posts found
        logger.debug(f"Successfully extracted {len(posts)} posts")
        
        # Save posts to database
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
        
        # Redirect to the analysis process
        return redirect(url_for('analyze_blog', blog_id=blog.id))
    
    except Exception as e:
        logger.error(f"Error during blog submission: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('index'))

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
    
    return render_template('report.html', report=report, blog=blog)

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
