import os
import re
import json
import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional, Dict
from models import Paper, PaperChunk

class DocumentProcessor:
    """Processes medical research papers in JATS XML format"""

    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._topic_mapping = None  # Cache for metadata topic mapping

    def read_file(self, file_path: str) -> str:
        """Read content from file with UTF-8 encoding"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # If UTF-8 fails, try with error handling
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                return file.read()


    def chunk_text(self, text: str) -> List[str]:
        """Split text into sentence-based chunks with overlap using config settings"""

        # Clean up the text
        text = re.sub(r'\s+', ' ', text.strip())  # Normalize whitespace

        # Better sentence splitting that handles abbreviations
        # This regex looks for periods followed by whitespace and capital letters
        # but ignores common abbreviations
        sentence_endings = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\!|\?)\s+(?=[A-Z])')
        sentences = sentence_endings.split(text)

        # Clean sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        i = 0

        while i < len(sentences):
            current_chunk = []
            current_size = 0

            # Build chunk starting from sentence i
            for j in range(i, len(sentences)):
                sentence = sentences[j]

                # Calculate size with space
                space_size = 1 if current_chunk else 0
                total_addition = len(sentence) + space_size

                # Check if adding this sentence would exceed chunk size
                if current_size + total_addition > self.chunk_size and current_chunk:
                    break

                current_chunk.append(sentence)
                current_size += total_addition

            # Add chunk if we have content
            if current_chunk:
                chunks.append(' '.join(current_chunk))

                # Calculate overlap for next chunk
                if hasattr(self, 'chunk_overlap') and self.chunk_overlap > 0:
                    # Find how many sentences to overlap
                    overlap_size = 0
                    overlap_sentences = 0

                    # Count backwards from end of current chunk
                    for k in range(len(current_chunk) - 1, -1, -1):
                        sentence_len = len(current_chunk[k]) + (1 if k < len(current_chunk) - 1 else 0)
                        if overlap_size + sentence_len <= self.chunk_overlap:
                            overlap_size += sentence_len
                            overlap_sentences += 1
                        else:
                            break

                    # Move start position considering overlap
                    next_start = i + len(current_chunk) - overlap_sentences
                    i = max(next_start, i + 1)  # Ensure we make progress
                else:
                    # No overlap - move to next sentence after current chunk
                    i += len(current_chunk)
            else:
                # No sentences fit, move to next
                i += 1

        return chunks


    def _load_topic_mapping(self, metadata_dir: str) -> Dict[str, str]:
        """Load topic mapping from metadata JSON files"""
        if self._topic_mapping is not None:
            return self._topic_mapping

        self._topic_mapping = {}

        # Load both metadata files
        metadata_files = [
            os.path.join(metadata_dir, 'medical_papers_metadata.json'),
            os.path.join(metadata_dir, 'replacement_papers_metadata.json')
        ]

        for metadata_file in metadata_files:
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        papers = data.get('papers', [])
                        for paper in papers:
                            title = paper.get('title', '')
                            topic = paper.get('topic', '')
                            if title and topic:
                                self._topic_mapping[title] = topic
                except Exception as e:
                    print(f"Warning: Could not load metadata from {metadata_file}: {e}")

        return self._topic_mapping


    def _extract_text_from_element(self, element: Optional[ET.Element]) -> str:
        """Recursively extract all text from an XML element"""
        if element is None:
            return ""

        text = element.text or ""
        for child in element:
            text += self._extract_text_from_element(child)
            if child.tail:
                text += child.tail

        return text.strip()


    def _check_if_abstract_only(self, root: ET.Element) -> bool:
        """Check if XML contains only abstract (no full text)"""
        # Look for the publisher restriction comment
        xml_str = ET.tostring(root, encoding='unicode')
        if "does not allow downloading of the full text in XML form" in xml_str:
            return True

        # Also check if <body> element exists
        body = root.find('.//body')
        if body is None or len(list(body)) == 0:
            return True

        return False


    def _parse_authors(self, root: ET.Element) -> List[str]:
        """Extract author names from XML"""
        authors = []
        contrib_group = root.find('.//contrib-group')
        if contrib_group is not None:
            for contrib in contrib_group.findall('.//contrib[@contrib-type="author"]'):
                surname_elem = contrib.find('.//surname')
                given_names_elem = contrib.find('.//given-names')

                if surname_elem is not None:
                    surname = surname_elem.text or ""
                    given_names = ""
                    if given_names_elem is not None:
                        given_names = given_names_elem.text or ""

                    if given_names:
                        authors.append(f"{given_names} {surname}")
                    else:
                        authors.append(surname)

        return authors


    def _parse_keywords(self, root: ET.Element) -> List[str]:
        """Extract keywords from XML"""
        keywords = []
        for kwd in root.findall('.//kwd'):
            if kwd.text:
                keywords.append(kwd.text.strip())
        return keywords


    def _extract_abstract(self, root: ET.Element) -> Optional[str]:
        """Extract abstract text from XML"""
        abstract = root.find('.//abstract')
        if abstract is not None:
            abstract_text = self._extract_text_from_element(abstract)
            # Clean up extra whitespace
            abstract_text = re.sub(r'\s+', ' ', abstract_text).strip()
            return abstract_text if abstract_text else None
        return None


    def _extract_body_sections(self, root: ET.Element) -> List[Tuple[str, str]]:
        """Extract body sections with titles and content"""
        sections = []
        body = root.find('.//body')

        if body is None:
            return sections

        for sec in body.findall('.//sec'):
            # Get section title
            title_elem = sec.find('title')
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Untitled Section"

            # Get section content (paragraphs)
            content_parts = []
            for p in sec.findall('.//p'):
                p_text = self._extract_text_from_element(p)
                if p_text:
                    content_parts.append(p_text)

            if content_parts:
                content = ' '.join(content_parts)
                # Clean up extra whitespace
                content = re.sub(r'\s+', ' ', content).strip()
                sections.append((title, content))

        return sections


    def process_medical_paper(self, file_path: str, metadata_dir: str = ".") -> Optional[Tuple[Paper, List[PaperChunk]]]:
        """
        Process a medical research paper in JATS XML format.

        Args:
            file_path: Path to the XML file
            metadata_dir: Directory containing metadata JSON files

        Returns:
            Tuple of (Paper, List[PaperChunk]) or None if paper should be skipped
        """
        try:
            # Parse XML
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Check if abstract-only (skip these papers)
            if self._check_if_abstract_only(root):
                print(f"Skipping abstract-only paper: {os.path.basename(file_path)}")
                return None

            # Extract metadata
            title_elem = root.find('.//article-title')
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else os.path.basename(file_path)

            # Get PMCID
            pmcid = None
            pmcid_elem = root.find('.//article-id[@pub-id-type="pmcid"]')
            if pmcid_elem is not None and pmcid_elem.text:
                pmcid = pmcid_elem.text.strip()

            # Get DOI
            doi = None
            doi_elem = root.find('.//article-id[@pub-id-type="doi"]')
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.strip()

            # Get journal name
            journal = None
            journal_elem = root.find('.//journal-title')
            if journal_elem is not None and journal_elem.text:
                journal = journal_elem.text.strip()

            # Get publication year
            year = None
            year_elem = root.find('.//pub-date/year')
            if year_elem is not None and year_elem.text:
                try:
                    year = int(year_elem.text.strip())
                except ValueError:
                    pass

            # Get article type
            paper_type = None
            type_elem = root.find('.//subj-group[@subj-group-type="heading"]/subject')
            if type_elem is not None and type_elem.text:
                paper_type = type_elem.text.strip()

            # Get authors and keywords
            authors = self._parse_authors(root)
            keywords = self._parse_keywords(root)

            # Get topic from metadata
            topic_mapping = self._load_topic_mapping(metadata_dir)
            topic = topic_mapping.get(title)

            # Create Paper object
            paper = Paper(
                title=title,
                pmcid=pmcid,
                doi=doi,
                journal=journal,
                year=year,
                authors=authors,
                paper_type=paper_type,
                topic=topic,
                keywords=keywords
            )

            # Extract content and create chunks
            paper_chunks = []
            chunk_counter = 0

            # 1. Process abstract as a single chunk
            abstract = self._extract_abstract(root)
            if abstract:
                chunk_with_context = f"Paper: {title} | Section: Abstract\n{abstract}"
                paper_chunk = PaperChunk(
                    content=chunk_with_context,
                    paper_title=title,
                    pmcid=pmcid,
                    doi=doi,
                    journal=journal,
                    year=year,
                    topic=topic,
                    section_title="Abstract",
                    chunk_index=chunk_counter
                )
                paper_chunks.append(paper_chunk)
                chunk_counter += 1

            # 2. Process body sections
            sections = self._extract_body_sections(root)
            for section_title, section_content in sections:
                # Chunk the section content
                chunks = self.chunk_text(section_content)
                for chunk in chunks:
                    chunk_with_context = f"Paper: {title} | Section: {section_title}\n{chunk}"
                    paper_chunk = PaperChunk(
                        content=chunk_with_context,
                        paper_title=title,
                        pmcid=pmcid,
                        doi=doi,
                        journal=journal,
                        year=year,
                        topic=topic,
                        section_title=section_title,
                        chunk_index=chunk_counter
                    )
                    paper_chunks.append(paper_chunk)
                    chunk_counter += 1

            return paper, paper_chunks

        except ET.ParseError as e:
            print(f"XML parsing error in {file_path}: {e}")
            return None
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            return None
