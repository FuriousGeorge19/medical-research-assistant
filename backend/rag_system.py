from typing import List, Tuple, Optional, Dict
import os
from document_processor import DocumentProcessor
from vector_store import VectorStore
from ai_generator import AIGenerator
from session_manager import SessionManager
from search_tools import ToolManager, MedicalLiteratureSearchTool
from models import Paper, PaperChunk

class RAGSystem:
    """Main orchestrator for the Retrieval-Augmented Generation system"""

    def __init__(self, config):
        self.config = config

        # Initialize core components
        self.document_processor = DocumentProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        self.vector_store = VectorStore(
            config.CHROMA_PATH,
            config.EMBEDDING_MODEL,
            config.MAX_RESULTS,
            config.CATALOG_COLLECTION,
            config.CONTENT_COLLECTION
        )
        self.ai_generator = AIGenerator(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
        self.session_manager = SessionManager(config.MAX_HISTORY)

        # Initialize search tools
        self.tool_manager = ToolManager()
        self.search_tool = MedicalLiteratureSearchTool(self.vector_store)
        self.tool_manager.register_tool(self.search_tool)

    def add_medical_paper(self, file_path: str, metadata_dir: str = "..") -> Tuple[Optional[Paper], int]:
        """
        Add a single medical paper to the knowledge base.

        Args:
            file_path: Path to the XML paper file
            metadata_dir: Directory containing metadata JSON files

        Returns:
            Tuple of (Paper object or None, number of chunks created)
        """
        try:
            # Process the document
            result = self.document_processor.process_medical_paper(file_path, metadata_dir)

            if result is None:
                # Paper was skipped (likely abstract-only)
                return None, 0

            paper, paper_chunks = result

            # Add paper metadata to vector store
            self.vector_store.add_paper_metadata(paper)

            # Add paper content chunks to vector store
            self.vector_store.add_paper_content(paper_chunks)

            return paper, len(paper_chunks)
        except Exception as e:
            print(f"Error processing medical paper {file_path}: {e}")
            return None, 0

    def add_papers_from_folder(self, folder_path: str, metadata_dir: str = "..", clear_existing: bool = False) -> Tuple[int, int]:
        """
        Add all medical papers from a folder.

        Args:
            folder_path: Path to folder containing XML paper files
            metadata_dir: Directory containing metadata JSON files
            clear_existing: Whether to clear existing data first

        Returns:
            Tuple of (total papers added, total chunks created)
        """
        total_papers = 0
        total_chunks = 0

        # Clear existing data if requested
        if clear_existing:
            print("Clearing existing data for fresh rebuild...")
            self.vector_store.clear_all_data()

        if not os.path.exists(folder_path):
            print(f"Folder {folder_path} does not exist")
            return 0, 0

        # Get existing paper titles to avoid re-processing
        existing_paper_titles = set(self.vector_store.get_existing_paper_titles())

        # Process each XML file in the folder
        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)
            if os.path.isfile(file_path) and file_name.lower().endswith('.xml'):
                try:
                    # Process the paper
                    result = self.document_processor.process_medical_paper(file_path, metadata_dir)

                    if result is None:
                        # Paper was skipped (abstract-only or error)
                        continue

                    paper, paper_chunks = result

                    if paper and paper.title not in existing_paper_titles:
                        # This is a new paper - add it to the vector store
                        self.vector_store.add_paper_metadata(paper)
                        self.vector_store.add_paper_content(paper_chunks)
                        total_papers += 1
                        total_chunks += len(paper_chunks)
                        print(f"Added paper: {paper.title[:80]}... ({len(paper_chunks)} chunks)")
                        existing_paper_titles.add(paper.title)
                    elif paper:
                        print(f"Paper already exists: {paper.title[:60]}... - skipping")
                except Exception as e:
                    print(f"Error processing {file_name}: {e}")

        return total_papers, total_chunks

    def query(self, query: str, session_id: Optional[str] = None) -> Tuple[str, List[Dict]]:
        """
        Process a user query using the RAG system with tool-based search.

        Args:
            query: User's medical research question
            session_id: Optional session ID for conversation context

        Returns:
            Tuple of (response, sources list with dicts containing 'text' and 'url')
        """
        # Get conversation history if session exists
        history = None
        if session_id:
            history = self.session_manager.get_conversation_history(session_id)

        # Generate response using AI with tools
        response = self.ai_generator.generate_response(
            query=query,
            conversation_history=history,
            tools=self.tool_manager.get_tool_definitions(),
            tool_manager=self.tool_manager
        )

        # Get sources from the search tool
        sources = self.tool_manager.get_last_sources()

        # Reset sources after retrieving them
        self.tool_manager.reset_sources()

        # Update conversation history
        if session_id:
            self.session_manager.add_exchange(session_id, query, response)

        # Return response with sources from tool searches
        return response, sources

    def get_paper_analytics(self) -> Dict:
        """Get analytics about the paper catalog"""
        return {
            "total_papers": self.vector_store.get_paper_count(),
            "paper_titles": self.vector_store.get_existing_paper_titles(),
            "topics": self.vector_store.get_unique_topics()
        }
