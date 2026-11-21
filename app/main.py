"""Container Optimizer — FastAPI application."""
import hashlib
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app import environment
from app.routes.analyzer import router as analyzer_router

app = FastAPI(
    title="Dockercraft",
    description="Micro SaaS for analyzing and optimizing Dockerfiles.",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.environment = environment.APP_ENV
app.include_router(analyzer_router)

FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
FRONTEND_ORIGIN = urlsplit(FRONTEND_URL) if FRONTEND_URL else None

templates = Jinja2Templates(directory="app/templates")
static_dir = Path(__file__).resolve().parent / "static"
static_js = static_dir / "js" / "index.js"
static_css = static_dir / "css" / "landing.css"
templates.env.globals["STATIC_JS_VERSION"] = hashlib.sha256(static_js.read_bytes()).hexdigest()[:12]
templates.env.globals["STATIC_CSS_VERSION"] = hashlib.sha256(static_css.read_bytes()).hexdigest()[:12]

# Expose public site metadata to templates.
templates.env.globals["SITE_TITLE"] = os.getenv("SITE_TITLE", "dockercraft")
templates.env.globals["SITE_DESCRIPTION"] = os.getenv("SITE_DESCRIPTION", "Analyze & optimize your Dockerfile for best practices, security, and smaller images")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.middleware("http")
async def restrict_external_requests(request: Request, call_next):
    """Keep API calls same-origin and allow only GET for other site requests."""
    is_api = request.url.path.startswith("/api/")
    if is_api:
        origin = request.headers.get("origin")
        request_host = request.headers.get("host", "").casefold()
        expected_host = FRONTEND_ORIGIN.netloc.casefold() if FRONTEND_ORIGIN else request_host
        host_is_allowed = request_host == expected_host
        expected_scheme = FRONTEND_ORIGIN.scheme.casefold() if FRONTEND_ORIGIN else ""
        if origin:
            origin_parts = urlsplit(origin)
            same_origin = (
                host_is_allowed
                and origin_parts.scheme in {"http", "https"}
                and origin_parts.netloc.casefold() == expected_host
                and (not expected_scheme or origin_parts.scheme.casefold() == expected_scheme)
            )
        else:
            fetch_site = request.headers.get("sec-fetch-site", "").casefold()
            referer = urlsplit(request.headers.get("referer", ""))
            referer_is_allowed = (
                referer.scheme in {"http", "https"}
                and referer.netloc.casefold() == expected_host
                and (not expected_scheme or referer.scheme.casefold() == expected_scheme)
            )
            same_origin = host_is_allowed and (fetch_site == "same-origin" or referer_is_allowed)

        if not same_origin:
            return JSONResponse(
                status_code=403,
                content={"detail": "External API access is disabled."},
            )
    elif request.method != "GET":
        return JSONResponse(
            status_code=405,
            content={"detail": "Only GET requests are allowed for site pages."},
            headers={"Allow": "GET"},
        )

    return await call_next(request)


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    """Explain the Dockerfile audit rules used by the analyzer."""
    return templates.TemplateResponse("rules.html", {"request": request})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Serve a minimal privacy policy page."""
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """Serve a basic robots.txt for search engines."""
    content = """User-agent: *
Disallow: /api/
Disallow: /static/
Allow: /
Sitemap: /sitemap.xml
"""
    return PlainTextResponse(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap(request: Request):
    """Dynamically generate a simple sitemap for main pages."""
    host = request.headers.get("host")
    scheme = request.url.scheme
    site_url = FRONTEND_URL or f"{scheme}://{host}"
    now = datetime.utcnow().date().isoformat()
    urls = ["/", "/rules", "/privacy"]
    entries = []
    for u in urls:
        loc = f"{site_url}{u}"
        entries.append(f"  <url><loc>{loc}</loc><lastmod>{now}</lastmod></url>")
    body = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "\n".join(entries) + "\n</urlset>"
    return Response(content=body, media_type="application/xml")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


