import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Get the OpenAI API key from environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai = OpenAI(api_key=OPENAI_API_KEY)

def analyze_blog_content(content):
    """
    Analyze blog content using OpenAI API to generate a comprehensive self-analysis.
    
    Args:
        content (str): The blog content to analyze
    
    Returns:
        dict: A dictionary containing the analysis results
    """
    try:
        logger.debug("Starting content analysis with OpenAI API")
        
        # Check if content is too large
        if len(content) > 100000:
            # If too large, use a representative sample
            logger.debug(f"Content too large ({len(content)} chars), truncating")
            content = content[:100000]  # Take first 100K chars
        
        # Define the analysis prompt
        prompt = """
        I have content from my personal blog, and I'd like you to analyze it to create a comprehensive 
        self-analysis report about me. Please analyze the following content and provide insights in the 
        following categories:
        
        1. Characteristics: Identify my defining personality traits and behavioral patterns.
        2. Strengths: What positive qualities or abilities do I demonstrate?
        3. Weaknesses: What areas could I improve upon?
        4. Thinking Patterns: How do I process information and approach problems?
        5. Decision Making: What patterns do you see in how I make decisions?
        6. Unconscious Biases: What cognitive biases might be influencing my thinking?
        7. Advice: Provide specific, actionable advice for personal growth in each area.
        
        For each category, please provide detailed analysis with specific examples from the content.
        Format your response as a JSON object with these categories as keys, each containing a detailed
        string of analysis.
        
        Here's the blog content:
        
        {content}
        """
        
        # Make the API call to gpt-4o
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a psychological analyst specializing in extracting insights from written content. Provide thoughtful, nuanced analysis based on the text provided."
                },
                {
                    "role": "user",
                    "content": prompt.format(content=content)
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=4000,
            temperature=0.7,
        )
        
        # Parse the response
        result = json.loads(response.choices[0].message.content)
        logger.debug("Analysis completed successfully")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during content analysis: {str(e)}")
        # Return a basic structure with error information
        return {
            "characteristics": f"Error during analysis: {str(e)}",
            "strengths": "",
            "weaknesses": "",
            "thinking_patterns": "",
            "decision_making": "",
            "unconscious_biases": "",
            "advice": "Please try again or contact support if the problem persists."
        }
