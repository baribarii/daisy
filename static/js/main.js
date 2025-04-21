// main.js - Main JavaScript for Daisy application

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Handle form submission for OAuth form
    const oauthForm = document.querySelector('form[action*="oauth_submit_blog"]');
    if (oauthForm) {
        oauthForm.addEventListener('submit', function(e) {
            e.preventDefault(); // 기본 제출 동작 막기
            
            // 분석 버튼 숨기고 프로그레스 표시
            document.getElementById('analyze-btn').classList.add('d-none');
            const progressContainer = document.getElementById('progress-container');
            progressContainer.classList.remove('d-none');
            
            // 프로그레스 바 애니메이션 시작
            let progress = 0;
            const circle = document.querySelector('.progress-circle-value');
            const percentage = document.getElementById('progress-percentage');
            const status = document.getElementById('progress-status');
            const statuses = [
                "블로그 정보 수집 중...",
                "포스트 목록 가져오는 중...",
                "포스트 내용 분석 중...",
                "AI 분석 준비 중...",
                "보고서 생성 중..."
            ];
            
            // 원형 프로그레스 바 업데이트 함수
            const updateProgress = () => {
                const circumference = 2 * Math.PI * 45; // r=45
                const offset = circumference - (progress / 100) * circumference;
                circle.style.strokeDashoffset = offset;
                percentage.textContent = `${progress}%`;
                
                // 진행 상태 텍스트 업데이트
                const statusIndex = Math.min(Math.floor(progress / 20), statuses.length - 1);
                status.textContent = statuses[statusIndex];
            };
            
            // 진행률 증가 시뮬레이션
            const progressInterval = setInterval(() => {
                progress += 2;
                if (progress > 90) {
                    clearInterval(progressInterval);
                    progress = 90; // 90%에서 멈추고 실제 완료 시 100%
                }
                updateProgress();
            }, 500);
            
            // 폼 제출
            setTimeout(() => {
                oauthForm.submit();
            }, 1000);
        });
    }
    
    // 기존 블로그 폼 핸들링(쿠키 방식용)
    const blogForm = document.getElementById('blog-form');
    if (blogForm) {
        blogForm.addEventListener('submit', function(e) {
            // Show loading state
            document.getElementById('form-container').classList.add('d-none');
            document.getElementById('loading-container').classList.remove('d-none');
            
            // Form will be submitted normally
        });
    }
    
    // Show cookie info
    const cookieInfoBtn = document.getElementById('cookie-info-btn');
    if (cookieInfoBtn) {
        cookieInfoBtn.addEventListener('click', function() {
            showCookieInstructions();
        });
    }
    
    // Handle copying text to clipboard
    const copyBtns = document.querySelectorAll('.copy-btn');
    if (copyBtns.length > 0) {
        copyBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const textId = this.getAttribute('data-text-id');
                const textElement = document.getElementById(textId);
                
                if (textElement) {
                    copyToClipboard(textElement.innerText);
                    
                    // Change button text temporarily
                    const originalText = this.innerText;
                    this.innerText = 'Copied!';
                    setTimeout(() => {
                        this.innerText = originalText;
                    }, 2000);
                }
            });
        });
    }
    
    // Check for status updates if on the loading page
    const statusContainer = document.getElementById('status-container');
    if (statusContainer) {
        const blogId = statusContainer.getAttribute('data-blog-id');
        if (blogId) {
            pollStatus(blogId);
        }
    }
});

// Function to show cookie instructions
function showCookieInstructions() {
    const modalHtml = `
    <div class="modal fade" id="cookieInstructionsModal" tabindex="-1" aria-labelledby="cookieInstructionsModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="cookieInstructionsModalLabel">How to Get Your Naver Cookie Value</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="alert alert-info">
                        Follow these steps to get the cookie value needed to access your Naver blog:
                    </div>
                    <ol class="list-group list-group-numbered mb-3">
                        <li class="list-group-item">Log in to your Naver account</li>
                        <li class="list-group-item">Open your browser's developer tools (F12 or right-click → Inspect)</li>
                        <li class="list-group-item">Go to the "Network" tab</li>
                        <li class="list-group-item">Navigate to your Naver blog or refresh the page</li>
                        <li class="list-group-item">Click on any request to naver.com</li>
                        <li class="list-group-item">Look for "Request Headers" and find the "Cookie" header</li>
                        <li class="list-group-item">Copy the entire cookie string value</li>
                    </ol>
                    <div class="alert alert-warning">
                        <strong>Important:</strong> Your cookie value contains sensitive information. This tool only uses it to access your blog content and does not store the cookie value.
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>
    `;
    
    // Append modal to body
    const modalContainer = document.createElement('div');
    modalContainer.innerHTML = modalHtml;
    document.body.appendChild(modalContainer);
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('cookieInstructionsModal'));
    modal.show();
    
    // Clean up when modal is hidden
    document.getElementById('cookieInstructionsModal').addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(modalContainer);
    });
}

// Function to copy text to clipboard
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
}

// Function to poll for status updates
function pollStatus(blogId) {
    const statusUrl = `/status/${blogId}`;
    const loadingBar = document.getElementById('loading-progress');
    let progressValue = 10;
    
    // Update progress periodically
    const progressInterval = setInterval(() => {
        progressValue += 5;
        if (progressValue > 90) {
            progressValue = 90; // Cap at 90% until complete
        }
        loadingBar.style.width = `${progressValue}%`;
        loadingBar.setAttribute('aria-valuenow', progressValue);
    }, 3000);
    
    // Poll for status updates
    const checkStatus = () => {
        fetch(statusUrl)
            .then(response => response.json())
            .then(data => {
                document.getElementById('post-count').textContent = data.post_count;
                
                // If report is ready, redirect to it
                if (data.has_report) {
                    clearInterval(progressInterval);
                    loadingBar.style.width = '100%';
                    loadingBar.setAttribute('aria-valuenow', 100);
                    
                    setTimeout(() => {
                        window.location.href = `/report/${data.report_id}`;
                    }, 1000);
                } else {
                    // Check again in 5 seconds
                    setTimeout(checkStatus, 5000);
                }
            })
            .catch(error => {
                console.error('Error checking status:', error);
                // Continue checking despite errors
                setTimeout(checkStatus, 10000);
            });
    };
    
    // Start checking
    checkStatus();
}
