import uvicorn

from .config import Settings


def run() -> None:
    settings = Settings()
    uvicorn.run(
        "skelly_ai.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()

