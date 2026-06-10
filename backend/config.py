from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ollama_base_url: str = "http://localhost:11434"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    llm_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"
    pg_conn: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    collection_name: str = "rag_documents"
    uploads_path: str = "./uploads"
    rerank: bool = True
    watch_dir: str = ""
    api_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
