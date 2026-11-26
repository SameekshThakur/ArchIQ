from fastapi import APIRouter

from app.api.v1.routers import connections, core, delivery, design, files, knowledge, studio, workspace

api_router = APIRouter()
for module in (core, knowledge, design, delivery, files, workspace, connections, studio):
    api_router.include_router(module.router)
