import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from models import Paper, PaperChunk
from sentence_transformers import SentenceTransformer

@dataclass
class SearchResults:
    """Container for search results with metadata"""
    documents: List[str]
    metadata: List[Dict[str, Any]]
    distances: List[float]
    error: Optional[str] = None

    @classmethod
    def from_chroma(cls, chroma_results: Dict) -> 'SearchResults':
        """Create SearchResults from ChromaDB query results"""
        return cls(
            documents=chroma_results['documents'][0] if chroma_results['documents'] else [],
            metadata=chroma_results['metadatas'][0] if chroma_results['metadatas'] else [],
            distances=chroma_results['distances'][0] if chroma_results['distances'] else []
        )

    @classmethod
    def empty(cls, error_msg: str) -> 'SearchResults':
        """Create empty results with error message"""
        return cls(documents=[], metadata=[], distances=[], error=error_msg)

    def is_empty(self) -> bool:
        """Check if results are empty"""
        return len(self.documents) == 0

class VectorStore:
    """Vector storage using ChromaDB for medical research papers"""

    def __init__(self, chroma_path: str, embedding_model: str, max_results: int = 5,
                 catalog_collection: str = "paper_catalog", content_collection: str = "paper_content"):
        self.max_results = max_results
        self.catalog_collection_name = catalog_collection
        self.content_collection_name = content_collection

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False)
        )

        # Set up sentence transformer embedding function
        self.embedding_function = chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )

        # Create collections for different types of data
        self.paper_catalog = self._create_collection(catalog_collection)  # Paper metadata
        self.paper_content = self._create_collection(content_collection)  # Paper chunks

    def _create_collection(self, name: str):
        """Create or get a ChromaDB collection"""
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embedding_function
        )

    def search(self,
               query: str,
               topic: Optional[str] = None,
               paper_type: Optional[str] = None,
               year_range: Optional[tuple] = None,
               limit: Optional[int] = None) -> SearchResults:
        """
        Main search interface for medical literature.

        Args:
            query: What to search for in paper content
            topic: Optional topic to filter by (e.g., "Type 2 Diabetes Management")
            paper_type: Optional paper type to filter by (e.g., "Review", "Meta-Analysis")
            year_range: Optional tuple of (min_year, max_year) to filter by
            limit: Maximum results to return

        Returns:
            SearchResults object with documents and metadata
        """
        # Build filter for content search
        filter_dict = self._build_filter(topic, paper_type, year_range)

        # Search paper content
        search_limit = limit if limit is not None else self.max_results

        try:
            results = self.paper_content.query(
                query_texts=[query],
                n_results=search_limit,
                where=filter_dict
            )
            return SearchResults.from_chroma(results)
        except Exception as e:
            return SearchResults.empty(f"Search error: {str(e)}")

    def _build_filter(self, topic: Optional[str], paper_type: Optional[str],
                      year_range: Optional[tuple]) -> Optional[Dict]:
        """Build ChromaDB filter from search parameters"""
        filters = []

        if topic:
            filters.append({"topic": topic})

        if paper_type:
            filters.append({"paper_type": paper_type})

        if year_range:
            min_year, max_year = year_range
            filters.append({"year": {"$gte": min_year, "$lte": max_year}})

        if not filters:
            return None

        if len(filters) == 1:
            return filters[0]

        return {"$and": filters}

    def add_paper_metadata(self, paper: Paper):
        """Add paper information to the catalog for semantic search"""
        import json

        # Create searchable text combining title and keywords
        paper_text = f"{paper.title} {' '.join(paper.keywords)}"

        # Build metadata
        metadata = {
            "title": paper.title,
            "topic": paper.topic,
            "journal": paper.journal,
            "year": paper.year,
            "paper_type": paper.paper_type,
            "pmcid": paper.pmcid,
            "doi": paper.doi,
            "authors_json": json.dumps(paper.authors),  # Serialize as JSON string
            "keywords_json": json.dumps(paper.keywords),
            "author_count": len(paper.authors)
        }

        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        self.paper_catalog.add(
            documents=[paper_text],
            metadatas=[metadata],
            ids=[paper.title]
        )

    def add_paper_content(self, chunks: List[PaperChunk]):
        """Add paper content chunks to the vector store"""
        if not chunks:
            return

        documents = [chunk.content for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            metadata = {
                "paper_title": chunk.paper_title,
                "topic": chunk.topic,
                "section_title": chunk.section_title,
                "chunk_index": chunk.chunk_index,
                "pmcid": chunk.pmcid,
                "doi": chunk.doi,
                "journal": chunk.journal,
                "year": chunk.year
            }
            # Remove None values
            metadata = {k: v for k, v in metadata.items() if v is not None}
            metadatas.append(metadata)

        # Use title with chunk index for unique IDs
        ids = [f"{chunk.paper_title.replace(' ', '_').replace('/', '_')}_{chunk.chunk_index}" for chunk in chunks]

        self.paper_content.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    def clear_all_data(self):
        """Clear all data from both collections"""
        try:
            self.client.delete_collection(self.catalog_collection_name)
            self.client.delete_collection(self.content_collection_name)
            # Recreate collections
            self.paper_catalog = self._create_collection(self.catalog_collection_name)
            self.paper_content = self._create_collection(self.content_collection_name)
        except Exception as e:
            print(f"Error clearing data: {e}")

    def get_existing_paper_titles(self) -> List[str]:
        """Get all existing paper titles from the vector store"""
        try:
            # Get all documents from the catalog
            results = self.paper_catalog.get()
            if results and 'ids' in results:
                return results['ids']
            return []
        except Exception as e:
            print(f"Error getting existing paper titles: {e}")
            return []

    def get_paper_count(self) -> int:
        """Get the total number of papers in the vector store"""
        try:
            results = self.paper_catalog.get()
            if results and 'ids' in results:
                return len(results['ids'])
            return 0
        except Exception as e:
            print(f"Error getting paper count: {e}")
            return 0

    def get_all_papers_metadata(self) -> List[Dict[str, Any]]:
        """Get metadata for all papers in the vector store"""
        import json
        try:
            results = self.paper_catalog.get()
            if results and 'metadatas' in results:
                # Parse JSON fields for each paper
                parsed_metadata = []
                for metadata in results['metadatas']:
                    paper_meta = metadata.copy()
                    if 'authors_json' in paper_meta:
                        paper_meta['authors'] = json.loads(paper_meta['authors_json'])
                        del paper_meta['authors_json']
                    if 'keywords_json' in paper_meta:
                        paper_meta['keywords'] = json.loads(paper_meta['keywords_json'])
                        del paper_meta['keywords_json']
                    parsed_metadata.append(paper_meta)
                return parsed_metadata
            return []
        except Exception as e:
            print(f"Error getting papers metadata: {e}")
            return []

    def get_paper_url(self, paper_title: str) -> Optional[str]:
        """Get URL for a given paper title (prefers PMC, falls back to DOI)"""
        try:
            # Get paper by ID (title is the ID)
            results = self.paper_catalog.get(ids=[paper_title])
            if results and 'metadatas' in results and results['metadatas']:
                metadata = results['metadatas'][0]
                pmcid = metadata.get('pmcid')
                if pmcid:
                    return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
                doi = metadata.get('doi')
                if doi:
                    return f"https://doi.org/{doi}"
            return None
        except Exception as e:
            print(f"Error getting paper URL: {e}")
            return None

    def get_papers_by_topic(self, topic: str) -> List[str]:
        """Get all paper titles for a given topic"""
        try:
            results = self.paper_catalog.get(
                where={"topic": topic}
            )
            if results and 'ids' in results:
                return results['ids']
            return []
        except Exception as e:
            print(f"Error getting papers by topic: {e}")
            return []

    def get_unique_topics(self) -> List[str]:
        """Get list of unique topics in the vector store"""
        try:
            results = self.paper_catalog.get()
            if results and 'metadatas' in results:
                topics = set()
                for metadata in results['metadatas']:
                    topic = metadata.get('topic')
                    if topic:
                        topics.add(topic)
                return sorted(list(topics))
            return []
        except Exception as e:
            print(f"Error getting unique topics: {e}")
            return []
