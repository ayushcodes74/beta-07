from fastapi import FastAPI

app = FastAPI(
    title="TrustGrade API",
    description="AI-Assisted Grading You Can Trust",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Welcome to TrustGrade API",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}