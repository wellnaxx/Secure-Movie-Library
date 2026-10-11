from fastapi import FastAPI

from routers.movies import movies_router
from routers.users import users_router

app = FastAPI(
    title="Secure Movie Library",
    description=(
        "A secure FastAPI application for managing movies "
        "and enriching them with OMDb ratings in the background."
    ),
    version="1.0.0",
)

app.include_router(users_router)
app.include_router(movies_router)
