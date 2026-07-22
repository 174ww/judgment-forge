"""
为何存在：集中管理运行时配置（DATABASE_URL、材料落盘目录、上传上限、LLM Provider 等），
        让路由、仓储与 provider 工厂共用。
谁调用：judgment_forge.app（create_app → app.state.settings）、schema/db、
        auth·projects·materials·runs 仓储、provider.factory。
调用谁：pydantic-settings（读环境变量与 api/.env）。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定读 api/.env，不依赖进程 cwd（无论从仓库根还是 api/ 启动 uvicorn）。
_API_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _API_ROOT / ".env"


class Settings(BaseSettings):
    """加载进程配置；DATABASE_URL 必须指向可达的 Postgres。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        extra="ignore",
    )

    database_url: str = (
        "postgresql://judgment:judgment@localhost:5432/judgment_forge"
    )
    # 上传原文件本地落盘根目录（v1 对象存储；可换成 S3 而不改业务语义）。
    materials_dir: Path = _API_ROOT / "data" / "materials"
    # 单文件上传上限（字节）；超限在入口拒绝，不落库。
    max_upload_bytes: int = 10 * 1024 * 1024

    # 模型提供方：fake（本地/CI）| openai_compatible（OpenAI 或 DashScope 兼容模式）。
    llm_provider: str = "fake"
    llm_api_key: str = ""
    # OpenAI：https://api.openai.com/v1 ；百炼兼容：.../compatible-mode/v1
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    """带缓存的 Settings 工厂；测试用例间可 clear_cache() 重置。"""
    return Settings()
