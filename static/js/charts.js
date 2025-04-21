// charts.js - Chart generation for Daisy reports

function initCharts() {
    // Create the traits radar chart
    createTraitsChart();
    
    // Create the strengths vs weaknesses chart
    createStrengthsWeaknessesChart();
}

function createTraitsChart() {
    const traitChartContainer = document.getElementById('traits-chart');
    if (!traitChartContainer) return;
    
    // Extract data from hidden elements
    const characteristics = document.getElementById('characteristics-text').innerText;
    const thinkingPatterns = document.getElementById('thinking-patterns-text').innerText;
    const decisionMaking = document.getElementById('decision-making-text').innerText;
    
    // Generate trait scores based on text length and keyword frequency
    // This is a simplified approach - in a real application, you would use more sophisticated analysis
    const characteristicsScore = Math.min(90, 40 + characteristics.length / 100);
    const thinkingScore = Math.min(90, 40 + thinkingPatterns.length / 100);
    const decisionScore = Math.min(90, 40 + decisionMaking.length / 100);
    
    // Count occurrences of positive and negative emotion words
    const positiveWords = ['good', 'great', 'excellent', 'positive', 'strength', 'strong', 'creative', 'logical'];
    const negativeWords = ['difficult', 'challenge', 'weakness', 'negative', 'problem', 'issue', 'struggle'];
    
    const creativityScore = countWordOccurrences(characteristics + thinkingPatterns, 
        ['creative', 'imagination', 'innovative', 'artistic', 'original']) * 10 + 40;
    
    const analyticalScore = countWordOccurrences(characteristics + thinkingPatterns, 
        ['analytical', 'logical', 'rational', 'systematic', 'methodical']) * 10 + 40;
    
    // Create the chart
    const ctx = document.getElementById('traits-radar-chart').getContext('2d');
    new Chart(ctx, {
        type: 'radar',
        data: {
            labels: [
                'Personality Traits', 
                'Thinking Patterns', 
                'Decision Making', 
                'Creativity', 
                'Analytical Thinking'
            ],
            datasets: [{
                label: 'Your Traits',
                data: [
                    characteristicsScore, 
                    thinkingScore, 
                    decisionScore, 
                    creativityScore, 
                    analyticalScore
                ],
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 2,
                pointBackgroundColor: 'rgba(54, 162, 235, 1)',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: 'rgba(54, 162, 235, 1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    angleLines: {
                        display: true
                    },
                    suggestedMin: 0,
                    suggestedMax: 100
                }
            }
        }
    });
}

function createStrengthsWeaknessesChart() {
    const chartContainer = document.getElementById('strengths-weaknesses-chart');
    if (!chartContainer) return;
    
    // Extract data from hidden elements
    const strengths = document.getElementById('strengths-text').innerText;
    const weaknesses = document.getElementById('weaknesses-text').innerText;
    
    // Generate strength categories and scores
    // In a real app, this would be from detailed analysis
    const strengthCategories = [
        'Communication', 
        'Problem Solving', 
        'Creativity', 
        'Focus', 
        'Empathy'
    ];
    
    const strengthScores = [
        calculateScore(strengths, ['communicate', 'articulate', 'express', 'clear']),
        calculateScore(strengths, ['solve', 'solution', 'approach', 'resolve']),
        calculateScore(strengths, ['creative', 'innovative', 'imagine', 'original']),
        calculateScore(strengths, ['focus', 'concentrate', 'attention', 'dedicated']),
        calculateScore(strengths, ['empathy', 'understand', 'compassion', 'relate'])
    ];
    
    const weaknessScores = [
        calculateScore(weaknesses, ['communicate', 'articulate', 'express', 'clear']),
        calculateScore(weaknesses, ['solve', 'solution', 'approach', 'resolve']),
        calculateScore(weaknesses, ['creative', 'innovative', 'imagine', 'original']),
        calculateScore(weaknesses, ['focus', 'concentrate', 'attention', 'dedicated']),
        calculateScore(weaknesses, ['empathy', 'understand', 'compassion', 'relate'])
    ];
    
    // Create the chart
    const ctx = document.getElementById('strengths-weaknesses-bar-chart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: strengthCategories,
            datasets: [
                {
                    label: 'Strengths',
                    data: strengthScores,
                    backgroundColor: 'rgba(40, 167, 69, 0.7)',
                    borderColor: 'rgba(40, 167, 69, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Areas for Growth',
                    data: weaknessScores,
                    backgroundColor: 'rgba(220, 53, 69, 0.7)',
                    borderColor: 'rgba(220, 53, 69, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            }
        }
    });
}

// Helper function to count word occurrences
function countWordOccurrences(text, wordList) {
    if (!text) return 0;
    
    const lowerText = text.toLowerCase();
    let count = 0;
    
    wordList.forEach(word => {
        const regex = new RegExp('\\b' + word + '\\b', 'gi');
        const matches = lowerText.match(regex);
        if (matches) {
            count += matches.length;
        }
    });
    
    return Math.min(5, count); // Cap at 5 for reasonable scores
}

// Helper function to calculate a score based on keyword presence
function calculateScore(text, keywords) {
    if (!text) return 30; // Default score
    
    const wordCount = text.split(/\s+/).length;
    const occurrences = countWordOccurrences(text, keywords);
    
    // Base score + bonus from text length and keyword occurrences
    return Math.min(95, 40 + (wordCount / 20) + (occurrences * 10));
}

// Initialize charts when the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Wait a moment for the DOM to fully initialize
    setTimeout(initCharts, 500);
});
