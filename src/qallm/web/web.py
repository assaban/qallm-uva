# src/qallm/web.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()
app.mount("/reports", StaticFiles(directory="outputs/reports"), name="reports")

@app.get("/")
def index():
    return FileResponse("src/qallm/web/index.html")