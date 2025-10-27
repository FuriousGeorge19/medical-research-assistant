import warnings
warnings.filterwarnings("ignore", message="resource_tracker: There appear to be.*")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import traceback  # TEMPORARY: For debugging - remove before student testing module

from config import config
from rag_system import RAGSystem

# Initialize FastAPI app
app = FastAPI(title="Medical Research Assistant", root_path="")

# Add trusted host middleware for proxy
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Enable CORS with proper settings for proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize RAG system
rag_system = RAGSystem(config)

# Pydantic models for request/response
class QueryRequest(BaseModel):
    """Request model for medical research queries"""
    query: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    """Response model for medical research queries"""
    answer: str
    sources: List[Dict[str, Optional[str]]]  # Each source has "text" and "url" keys
    session_id: str

class PaperStats(BaseModel):
    """Response model for paper catalog statistics"""
    total_papers: int
    topics: List[str]

# API Endpoints

@app.post("/api/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Process a query and return response with sources"""
    try:
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = rag_system.session_manager.create_session()

        # Process query using RAG system
        answer, sources = rag_system.query(request.query, session_id)

        return QueryResponse(
            answer=answer,
            sources=sources,
            session_id=session_id
        )
    except Exception as e:
        # TEMPORARY: Detailed error logging for debugging - remove before student module
        print("=" * 80)
        print("ERROR IN /api/query:")
        print(f"Query: {request.query}")
        print(f"Session ID: {request.session_id}")
        print(f"Error: {e}")
        print("Full traceback:")
        traceback.print_exc()
        print("=" * 80)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/papers", response_model=PaperStats)
async def get_paper_stats():
    """Get paper catalog analytics and statistics"""
    try:
        analytics = rag_system.get_paper_analytics()
        return PaperStats(
            total_papers=analytics["total_papers"],
            topics=analytics["topics"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Load medical papers on startup"""
    papers_path = config.DOCS_PATH
    metadata_path = config.METADATA_PATH

    if os.path.exists(papers_path):
        print("Loading medical research papers...")
        try:
            papers, chunks = rag_system.add_papers_from_folder(
                papers_path,
                metadata_path,
                clear_existing=False
            )
            print(f"Loaded {papers} papers with {chunks} chunks")

            # Print topics available
            analytics = rag_system.get_paper_analytics()
            topics = analytics.get("topics", [])
            if topics:
                print(f"Available topics: {', '.join(topics)}")
        except Exception as e:
            print(f"Error loading medical papers: {e}")
    else:
        print(f"Warning: Medical papers directory not found at {papers_path}")

# Custom static file handler with no-cache headers for development
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path


class DevStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, FileResponse):
            # Add no-cache headers for development
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    
    
# Serve static files for the frontend
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")