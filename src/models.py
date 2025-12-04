from settings import settings

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

def _init_chat_model_from_modelscope(model_name="deepseek-ai/DeepSeek-V3.2-Exp") -> BaseChatModel:
    '''
    Initialize a chat model from ModelScope.

    Args:
        model_name: the name of the model.
    Return:
        the initialized chat model.
    '''
    model = ChatOpenAI(model=model_name,
                             base_url="https://api-inference.modelscope.cn/v1",
                             api_key=SecretStr(settings.OPENAI_API_KEY))
    return model

def _init_kimi_k2() -> BaseChatModel:
    model = ChatOpenAI(model="kimi-k2-0905-preview",
                             base_url="https://api.moonshot.cn/v1",
                             api_key=SecretStr(settings.KIMI_API_KEY))
    return model

def _init_deepseek_v3_2() -> BaseChatModel:
    model = ChatOpenAI(model="deepseek-v3.2",
                             base_url="https://api.gptapi.us/v1/chat/completions",
                             api_key=SecretStr(settings.OPENAI_API_KEY))
    return model

def _init_ollama_model(model_name="qwen3:8b"):
    model = ChatOllama(model=model_name,
                             base_url=settings.OLLAMA_API_URL)
    return model

def get_model_by_type(model_type: str = "agentic") -> BaseChatModel:
    """根据模型类型获取相应的模型实例。"""
    if model_type == "normal":
        return _init_deepseek_v3_2()
    elif model_type == "agentic":
        return _init_kimi_k2()
    elif model_type == "free":
        return _init_ollama_model()
    else:
        raise ValueError(f"Unsupported model type: {model_type}")