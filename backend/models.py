from typing import List, Dict, Optional
from pydantic import BaseModel

class Paper(BaseModel):
    """Represents a medical research paper"""
    title: str                          # Full paper title (used as unique identifier)
    pmcid: Optional[str] = None         # PubMed Central ID (e.g., "PMC8129774")
    doi: Optional[str] = None           # Digital Object Identifier
    journal: Optional[str] = None       # Journal name
    year: Optional[int] = None          # Publication year
    authors: List[str] = []             # List of author names
    paper_type: Optional[str] = None    # Type (e.g., "Review", "Meta-Analysis")
    topic: Optional[str] = None         # Primary topic (e.g., "Type 2 Diabetes Management")
    keywords: List[str] = []            # Keywords from the paper

class PaperChunk(BaseModel):
    """Represents a text chunk from a medical paper for vector storage"""
    content: str                        # The actual text content
    paper_title: str                    # Which paper this chunk belongs to
    pmcid: Optional[str] = None         # PubMed Central ID
    doi: Optional[str] = None           # Digital Object Identifier
    journal: Optional[str] = None       # Journal name
    year: Optional[int] = None          # Publication year
    topic: Optional[str] = None         # Primary topic
    section_title: Optional[str] = None # Section this chunk is from (e.g., "Abstract", "Results")
    chunk_index: int                    # Position of this chunk in the document

class Source(BaseModel):
    """Represents a source citation with optional URL"""
    text: str                           # Display text (e.g., "Paper Title - 2021 - Journal Name")
    url: Optional[str] = None           # URL to the source (PMC or DOI link)