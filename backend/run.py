import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"Starting {settings.PROJECT_NAME} on http://localhost:{settings.PORT}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.PORT, reload=True)
