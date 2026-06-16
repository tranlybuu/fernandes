import os
from pydantic_settings import BaseSettings

import json

class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    
    # Local LLM config (Ollama, vLLM, etc.)
    local_llm_url: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "llama3")

    # Workflow storage
    workflows_dir: str = os.getenv("WORKFLOWS_DIR", "workflows")

    class Config:
        env_file = ".env"
        extra = "ignore"

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "local_llm_url": "http://localhost:11434/v1",
    "local_llm_model": "llama3"
}

def load_persistent_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            print(f"Generated default configuration file: {CONFIG_FILE}")
            return DEFAULT_CONFIG
        except Exception as e:
            print(f"Error creating default config.json: {e}")
            return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r") as f:
            config_data = json.load(f)
            # Ensure all default keys exist in the loaded config
            updated = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in config_data:
                    config_data[k] = v
                    updated = True
            if updated:
                save_persistent_config(config_data)
            return config_data
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return DEFAULT_CONFIG

def save_persistent_config(data: dict) -> bool:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config.json: {e}")
        return False

settings = Settings()

# Load persistent config if exists
p_config = load_persistent_config()
if p_config.get("gemini_api_key"):
    settings.gemini_api_key = p_config["gemini_api_key"]
if p_config.get("openai_api_key"):
    settings.openai_api_key = p_config["openai_api_key"]
if p_config.get("anthropic_api_key"):
    settings.anthropic_api_key = p_config["anthropic_api_key"]
if p_config.get("local_llm_url"):
    settings.local_llm_url = p_config["local_llm_url"]
if p_config.get("local_llm_model"):
    settings.local_llm_model = p_config["local_llm_model"]

def update_settings_in_runtime(data: dict):
    if "gemini_api_key" in data:
        settings.gemini_api_key = data["gemini_api_key"]
    if "openai_api_key" in data:
        settings.openai_api_key = data["openai_api_key"]
    if "anthropic_api_key" in data:
        settings.anthropic_api_key = data["anthropic_api_key"]
    if "local_llm_url" in data:
        settings.local_llm_url = data["local_llm_url"]
    if "local_llm_model" in data:
        settings.local_llm_model = data["local_llm_model"]
    save_persistent_config(data)

# Ensure workflows directory exists
os.makedirs(settings.workflows_dir, exist_ok=True)
