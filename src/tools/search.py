from ddgs import DDGS
from logger import logger

def search_topic_by_ddgs(topic: str):
    logger.info(f"Searching DuckDuckGo for topic: {topic}")
    try:
        return list(DDGS().text(query=topic, region='us-en', safesearch='Off', time='y', max_results=10))
    except Exception as e:
        return {"error": str(e)}
