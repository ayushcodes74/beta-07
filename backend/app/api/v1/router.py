from fastapi import APIRouter

from app.api.v1.endpoints import assignments, auth, courses, submissions, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(courses.router)
api_router.include_router(assignments.router)
api_router.include_router(submissions.router)


@api_router.get("/health")
def api_health():
    return {
        "status": "healthy",
        "version": "v1"
    }
