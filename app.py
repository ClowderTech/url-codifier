import motor.motor_asyncio
import os
import random
import string
import aiohttp
import asyncio
import bcrypt
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from markupsafe import Markup
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates  # Add this import
from starlette.middleware.sessions import SessionMiddleware

# Initialize FastAPI application
app = FastAPI()

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.urandom(32))

salt = bcrypt.gensalt()

def hash_password(password):
    """Hash the password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), salt)

def verify_password(stored_hash, password):
    """Verify the provided password against the stored hash."""
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash)

# Retrieve MongoDB connection string and admin password from environment variables
MONGO_URI = os.environ.get('MONGO_URI')
ADMIN_PASSWORD = hash_password(os.environ.get('ADMIN_PASSWORD'))

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable is not set.")
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is not set.")

# Initialize Motor client
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.get_database()

templates = Jinja2Templates(directory="templates")

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Define the form data model using Pydantic for validation
class RedirectForm(BaseModel):
    code: str
    password: str

def generate_random_key(length=12):
    """Generate a random key consisting of uppercase letters, lowercase letters, and digits."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def execute_async_code(code):
    """Executes the dynamic code and returns a result by scheduling the async function."""
    exec_globals = {"fetch_data": fetch_data, "__builtins__": {}}

    # Execute the dynamic code
    exec(code, exec_globals)

    # Retrieve the handler function
    handler = exec_globals.get('main')

    if handler:
        # Use asyncio.ensure_future to schedule the async handler function without blocking
        task = asyncio.ensure_future(handler())
        return task
    else:
        raise ValueError("No handler function defined in the provided code.")

from typing import List, Tuple

def get_flashed_messages(session: dict, with_categories: bool = False) -> List[Tuple[str, str]]:
    """Retrieve flashed messages from the session."""
    messages = session.pop("_messages", [])
    if with_categories:
        return messages
    return [message[1] for message in messages]

def flash(session: dict, message: str, category: str = "message"):
    """Store a message in the session."""
    messages = session.get("_messages", [])
    messages.append((category, message))
    session["_messages"] = messages

async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.ok:
                # Check if the response content type is JSON
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    return await response.text()
            else:
                return f"Request failed with status code {response.status}"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with form."""
    messages = get_flashed_messages(request.session, with_categories=True)
    return templates.TemplateResponse("create_redirect.html", {
        "request": request,
        "messages": [],
        "form": None,  # form is None initially
        "errors": {}    # No errors initially
    })

@app.post("/", response_class=HTMLResponse)
async def create_redirect(request: Request, code: str = Form(...), password: str = Form(...)):
    """Handle form submission, hash password, generate random key, and store redirect info in MongoDB."""

    errors = {}

    # Simulate form validation
    if not code:
        errors["code"] = "Code is required."
    if not password:
        errors["password"] = "Password is required."

    # Hash the password before storing it in the database
    hashed_password = hash_password(password)

    if hashed_password != ADMIN_PASSWORD:
        message = ["danger", "The password was not correct, please try again."]
    else:
        # Generate a random key for the redirect
        key = generate_random_key()

        # Insert form data (including the hashed password, generated key, and redirect URL) into MongoDB
        collection = db.route_handlers
        await collection.insert_one({"code": code, "key": key})

        message = ["success", Markup(f"Redirect successfully created! Your key: <a href='/redirect/{key}'>{key}</a>")]

    return templates.TemplateResponse("create_redirect.html", {
        "request": request,
        "messages": [message],
        "form": {"code": code, "password": password},
        "errors": errors
    })

@app.get("/redirect/{key}", response_class=HTMLResponse)
async def dynamic_redirect(request: Request, key: str):
    """Dynamically handle redirects based on MongoDB data."""
    collection = db.route_handlers
    document = await collection.find_one({"key": key})
    if document:
        return RedirectResponse(url=execute_async_code(document['handler_function']))
    return "Handler function not found.", 404

# Run FastAPI with Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)