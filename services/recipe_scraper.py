import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def scrape_recipe_text(url: str) -> str:
    """
    Fetches HTML from a given URL and extracts the text content.
    This raw text is intended to be passed to the LLM for structured ingredient extraction.
    """
    logger.info(f"Attempting to scrape recipe from: {url}")
    try:
        # Define headers to mimic a common browser to avoid blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script, style, and navigation components to reduce noise
        for script_or_style in soup(['script', 'style', 'nav', 'footer', 'header']):
            script_or_style.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        
        # Simple heuristic to limit context window size to roughly the most relevant parts.
        # In a real scenario, this might be more sophisticated.
        if len(text) > 15000:
            logger.warning(f"Scraped text from {url} is very long ({len(text)} chars). Truncating.")
            text = text[:15000]
            
        return text

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error scraping {url}: {e}")
        return f"Error: Timeout while scraping {url}"
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request error scraping {url}: {e}")
        return f"Error: Request failed for {url}"
    except Exception as e:
        logger.error(f"Unexpected error scraping {url}: {e}")
        return f"Error: An unexpected issue occurred."
