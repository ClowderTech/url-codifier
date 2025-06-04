import motor.motor_asyncio
import os
import random
import string
import aiohttp
import asyncio
import bcrypt
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markupsafe import Markup
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates  # Add this import
from starlette.middleware.sessions import SessionMiddleware
import re
import traceback
from typing import List, Tuple
from playwright.async_api import async_playwright, Response
from playwright._impl._errors import Error as PlaywrightError
from bs4 import BeautifulSoup
import json


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
BROWSER_WS = os.environ.get('BROWSER_WS')

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

safe_builtins = {
    'abs': abs,
    'all': all,
    'any': any,
    'ascii': ascii,
    'bin': bin,
    'bool': bool,
    'chr': chr,
    'complex': complex,
    'dict': dict,
    'divmod': divmod,
    'enumerate': enumerate,
    'filter': filter,
    'float': float,
    'format': format,
    'frozenset': frozenset,
    'hash': hash,
    'hex': hex,
    'int': int,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'list': list,
    'map': map,
    'max': max,
    'min': min,
    'next': next,
    'object': object,
    'oct': oct,
    'ord': ord,
    'pow': pow,
    'range': range,
    'repr': repr,
    'reversed': reversed,
    'round': round,
    'set': set,
    'slice': slice,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'zip': zip,
    "True": True,
    "False": False,
    "None": None
}

def is_valid_url(url):
    """Checks if a string is a valid URL."""
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # ...or ipv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # ...or ipv6
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

async def execute_async_code(code):
    """Executes the dynamic code asynchronously and returns a result."""
    exec_globals = {"fetch_data": fetch_data, "html_parser": html_parser, "fetch": Fetch, "__builtins__": safe_builtins}
    try:
        # Execute the dynamic code
        exec(code, exec_globals)
        handler = exec_globals.get('main')
        if handler:
            task = asyncio.create_task(handler())
            result = await task
            if task.exception():
                # Handle the exception from the task
                raise task.exception()
            
            # Check if result is a valid URL
            if not is_valid_url(result):
                raise ValueError(f"Result '{result}' is not a valid URL.")
            
            return result
        else:
            raise ValueError("No handler function defined in the provided code.")
    except Exception as e:
        # Capture the traceback details
        tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        # Log the traceback to the console (or a log file)
        print(tb_str)
        # Raise a custom exception with the traceback details
        raise RuntimeError("Error executing dynamic code.") from e

async def html_parser(html):
    return BeautifulSoup(html, "html5lib")

async def fetch_data(url):
    if not BROWSER_WS:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.ok:
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError):
                        return await response.text()
                else:
                    return f"Request failed with status code {response.status}"
    else:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect(BROWSER_WS)
            async with browser:
                context = await browser.new_context()
                page = await browser.new_page()
                try:
                    response = await page.goto(url)
                    if response.ok:
                        try:
                            return await response.json()
                        except (json.JSONDecodeError):
                            return await response.text()
                    else:
                        return f"Request failed with status code {response.status}"
                finally:
                    await page.close()
            await browser.close()

class Fetch:
    def __init__(self, url: string):
        self.url = url
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect(BROWSER_WS)
        self.context = await self.browser.new_context()
        self.page = await self.browser.new_page()
        response = await self.page.goto(self.url)
        return response

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.page.close()
        await self.browser.close()
        await self.playwright.stop()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with form."""
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

import traceback

@app.head("/redirect/{key}", response_class=HTMLResponse)
@app.get("/redirect/{key}", response_class=HTMLResponse)
async def dynamic_redirect(request: Request, key: str):
    """Dynamically handle redirects based on MongoDB data."""
    collection = db.route_handlers
    document = await collection.find_one({"key": key})
    if document:
        # Check if 'code' exists and is not empty
        code = document.get("code")
        if code:
            try:
                result = await execute_async_code(code)
                return RedirectResponse(url=result)
            except Exception as e:
                # Extract the traceback from the exception
                tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
                # Pass the traceback to the template
                return templates.TemplateResponse("error_page.html", {
                    "request": request,
                    "error_message": "An error occurred while processing your code.",
                    "traceback": tb_str,
                    "messages": [["danger", "An error occurred while executing your code."]]
                })
        else:
            return "The 'code' field is empty.", 400  # Bad request error for empty 'code'
    return "Handler function not found.", 404  # Not found error if document doesn't exist.

@app.head("/download/{key}", response_class=HTMLResponse)
@app.get("/download/{key}", response_class=HTMLResponse)
async def dynamic_download(request: Request, key: str, file_name: str = Query(..., description="The desired filename for the downloaded file")):
    """Dynamically handle redirects based on MongoDB data."""
    collection = db.route_handlers
    document = await collection.find_one({"key": key})
    if document:
        # Check if 'code' exists and is not empty
        code = document.get("code")
        if code:
            try:
                result = await execute_async_code(code)
                print(result)

                content: bytes = bytes()
                media_type: str = 'application/octet-stream'

                if not BROWSER_WS:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(result) as response:
                            response.raise_for_status()
                            content = await response.read()
                else:
                    async with async_playwright() as playwright:
                        browser = await playwright.chromium.connect(BROWSER_WS)
                        try:
                            context = await browser.new_context()
                            page = await context.new_page()
                            response = await page.goto(result)
                            if response.ok:
                                content = await response.body()
                                media_type = response.headers.get('Content-Type', 'application/octet-stream')
                        except PlaywrightError:
                            context = await browser.new_context(accept_downloads=True)
                            page = await context.new_page()
                            try:
                                async with page.expect_download() as download_info:
                                    await page.goto(result)
                                download = await download_info.value
                                stream = await download.create_read_stream()
                                buffer = io.BytesIO()
                                async for chunk in stream:
                                    buffer.write(chunk)
                                content = buffer.getvalue()
                                media_type = response.headers.get('Content-Type', 'application/octet-stream')
                            except:
                                pass
                        finally:
                            await page.close()
                            await browser.close()

                return StreamingResponse(
                    iter([content]),
                    media_type=media_type,
                    headers={'Content-Disposition': f'attachment; filename="{file_name}"'}
                )
            except Exception as e:
                # Extract the traceback from the exception
                tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
                # Pass the traceback to the template
                return templates.TemplateResponse("error_page.html", {
                    "request": request,
                    "error_message": "An error occurred while processing your code.",
                    "traceback": tb_str,
                    "messages": [["danger", "An error occurred while executing your code."]]
                })
        else:
            return "The 'code' field is empty.", 400  # Bad request error for empty 'code'
    return "Handler function not found.", 404  # Not found error if document doesn't exist.


# Run FastAPI with Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)