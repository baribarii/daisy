// main.js - Main JavaScript for Daisy application

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Handle form submission
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
