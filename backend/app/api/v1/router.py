from fastapi import APIRouter

from app.api.v1.endpoints import ai_generation, assignments, auth, course_materials, courses, submissions, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(courses.router)
api_router.include_router(course_materials.router)
# Before `assignments` so the fixed /assignments/generate-ai path is matched ahead of /{assignment_id} routes.
api_router.include_router(ai_generation.router)
api_router.include_router(assignments.router)
api_router.include_router(submissions.router)


@api_router.get("/health")
def api_health():
    return {
        "status": "healthy",
        "version": "v1"
    }
