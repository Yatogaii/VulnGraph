import os

from langgraph.graph import MessagesState

from langchain_core.messages import SystemMessage
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

# Initialize Jinja2 environment
env = Environment(
    loader=FileSystemLoader(os.path.dirname(__file__)),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)

def _get_prompt_template(prompt_name: str, **context) -> str:
    """
    Load and return a prompt template using Jinja2.

    Args:
        prompt_name: Name of the prompt template file (without .md extension)
        **context: Variables to substitute in the template

    Returns:
        The template string with proper variable substitution syntax
    """
    try:        
        # Try locale-specific template first (e.g., researcher.zh_CN.md)
        template = env.get_template(f"{prompt_name}.md")
        return template.render(**context)
    except Exception as e:
        raise ValueError(f"Error loading template {prompt_name}: {str(e)}")

def apply_prompt_template(prompt_name: str, state: MessagesState, **context) -> list:
    prompt_str = _get_prompt_template(prompt_name, **context)

    return [SystemMessage(content=prompt_str)] + state["messages"]