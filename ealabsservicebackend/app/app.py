# app.py  (proje kökü)
from app.main import app as app  # app/main.py içindeki FastAPI instance'ını kullan

if __name__ == "__main__":
    import uvicorn
    # Uygulamayı doğrudan "python app.py" ile çalıştırmak istersen:
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
