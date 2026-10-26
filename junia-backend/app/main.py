
from fastapi import FastAPI

app = FastAPI(title="Antarctic Data Preparation Platform")

@app.get("/")
def home():
    return {
        "message": "Junia's Antarctic backend is running!",
        "status": "ready"
    }
