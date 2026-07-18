"""
Document chunking for RAG foundation.

Converts extracted document source sections into smaller, overlapping chunks
while preserving citation metadata (page numbers for PDF, paragraph numbers for DOCX).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from document_parser import SourceSection


@dataclass
class DocumentChunk:
    """A chunk of text extracted from a document.
    
    Preserves metadata for citation and retrieval.
    """
    chunk_index: int  # Global position in the chunk sequence (0-indexed)
    text: str  # The chunk content
    page: int | None = None  # Page number (PDF), 1-indexed
    paragraph: int | None = None  # Paragraph number (DOCX), 1-indexed
    source_section_id: int | None = None  # ID of the source section this came from
    char_start: int | None = None  # Start offset in the original section
    char_end: int | None = None  # End offset in the original section


class ChunkingConfig:
    """Configuration for the chunking process."""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """Initialize chunking configuration.
        
        Args:
            chunk_size: Maximum size of each chunk in characters. Must be > 0.
            overlap: Number of overlapping characters between consecutive chunks.
                    Must be >= 0 and < chunk_size.
        
        Raises:
            ValueError: If configuration is invalid.
        """
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
        if overlap < 0:
            raise ValueError(f"overlap must be >= 0, got {overlap}")
        if overlap >= chunk_size:
            raise ValueError(
                f"overlap must be < chunk_size ({overlap} >= {chunk_size})"
            )
        
        self.chunk_size = chunk_size
        self.overlap = overlap


class Chunker:
    """Converts source sections into chunks with preserved metadata."""
    
    # Regex for sentence splitting (works for most cases)
    _SENTENCE_SPLIT_REGEX = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
    
    def __init__(self, config: ChunkingConfig | None = None):
        """Initialize chunker with configuration.
        
        Args:
            config: ChunkingConfig instance. Defaults to ChunkingConfig() if not provided.
        """
        self.config = config or ChunkingConfig()
    
    def chunk(self, sections: list[SourceSection]) -> list[DocumentChunk]:
        """Convert source sections into chunks.
        
        Args:
            sections: List of SourceSection objects from document extraction.
        
        Returns:
            List of DocumentChunk objects in order, with metadata preserved.
        """
        chunks: list[DocumentChunk] = []
        chunk_index = 0
        
        for section in sections:
            section_chunks = self._chunk_section(section)
            for sc in section_chunks:
                sc.chunk_index = chunk_index
                chunks.append(sc)
                chunk_index += 1
        
        return chunks
    
    def _chunk_section(self, section: SourceSection) -> list[DocumentChunk]:
        """Split a single section into chunks while preserving metadata.
        
        Args:
            section: A single SourceSection to chunk.
        
        Returns:
            List of DocumentChunk objects from this section.
        """
        text = section.text.strip()
        
        # Empty sections produce no chunks
        if not text:
            return []
        
        # If section fits in one chunk, return as-is
        if len(text) <= self.config.chunk_size:
            return [
                DocumentChunk(
                    chunk_index=0,  # Will be reassigned by chunk()
                    text=text,
                    page=section.page,
                    paragraph=section.paragraph,
                    source_section_id=section.source_id,
                    char_start=0,
                    char_end=len(text),
                )
            ]
        
        # Split the section into chunks
        return self._split_with_overlap(
            text=text,
            page=section.page,
            paragraph=section.paragraph,
            source_section_id=section.source_id,
        )
    
    def _split_with_overlap(
        self,
        text: str,
        page: int | None,
        paragraph: int | None,
        source_section_id: int,
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks, preserving metadata.
        
        Tries to split at sentence boundaries first, then falls back to
        character-based splitting with overlap.
        
        Args:
            text: The text to split.
            page: Page number for PDF (retained in all chunks).
            paragraph: Paragraph number for DOCX (retained in all chunks).
            source_section_id: Source section identifier.
        
        Returns:
            List of DocumentChunk objects.
        """
        chunks: list[DocumentChunk] = []
        
        # Try sentence-based splitting first
        sentences = self._split_sentences(text)
        
        if len(sentences) > 1:
            # Use sentence boundaries
            chunks = self._chunk_by_sentences(
                sentences=sentences,
                page=page,
                paragraph=paragraph,
                source_section_id=source_section_id,
            )
        else:
            # Fall back to character-based splitting
            chunks = self._chunk_by_characters(
                text=text,
                page=page,
                paragraph=paragraph,
                source_section_id=source_section_id,
            )
        
        return chunks
    
    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex.
        
        Args:
            text: Text to split.
        
        Returns:
            List of sentences.
        """
        # Use regex to split at sentence boundaries
        sentences = self._SENTENCE_SPLIT_REGEX.split(text)
        # Filter empty sentences
        return [s.strip() for s in sentences if s.strip()]
    
    def _chunk_by_sentences(
        self,
        sentences: list[str],
        page: int | None,
        paragraph: int | None,
        source_section_id: int,
    ) -> list[DocumentChunk]:
        """Create chunks by grouping sentences.
        
        Args:
            sentences: List of sentences.
            page: Page number.
            paragraph: Paragraph number.
            source_section_id: Source section ID.
        
        Returns:
            List of DocumentChunk objects.
        """
        chunks: list[DocumentChunk] = []
        current_chunk_text = ""
        current_char_start = 0
        char_pos = 0
        
        for i, sentence in enumerate(sentences):
            sentence_with_space = sentence if i == 0 else " " + sentence
            
            # Would adding this sentence exceed the limit?
            if (
                current_chunk_text
                and len(current_chunk_text) + len(sentence_with_space) > self.config.chunk_size
            ):
                # Save current chunk
                if current_chunk_text.strip():
                    chunks.append(
                        DocumentChunk(
                            chunk_index=0,  # Reassigned later
                            text=current_chunk_text.strip(),
                            page=page,
                            paragraph=paragraph,
                            source_section_id=source_section_id,
                            char_start=current_char_start,
                            char_end=char_pos,
                        )
                    )
                
                # Start new chunk with overlap from previous
                if self.config.overlap > 0 and chunks:
                    # Extract last `overlap` characters from previous chunk
                    prev_text = chunks[-1].text
                    overlap_text = prev_text[-self.config.overlap:] if len(prev_text) > self.config.overlap else prev_text
                    current_chunk_text = overlap_text + " " + sentence
                    # Adjust char_start to account for overlap
                    current_char_start = char_pos - len(overlap_text)
                else:
                    current_chunk_text = sentence
                    current_char_start = char_pos
            else:
                # Add sentence to current chunk
                current_chunk_text += sentence_with_space
            
            char_pos += len(sentence_with_space)
        
        # Don't forget the last chunk
        if current_chunk_text.strip():
            chunks.append(
                DocumentChunk(
                    chunk_index=0,
                    text=current_chunk_text.strip(),
                    page=page,
                    paragraph=paragraph,
                    source_section_id=source_section_id,
                    char_start=current_char_start,
                    char_end=char_pos,
                )
            )
        
        return chunks
    
    def _chunk_by_characters(
        self,
        text: str,
        page: int | None,
        paragraph: int | None,
        source_section_id: int,
    ) -> list[DocumentChunk]:
        """Create chunks by character-based splitting with overlap.
        
        Args:
            text: Text to chunk.
            page: Page number.
            paragraph: Paragraph number.
            source_section_id: Source section ID.
        
        Returns:
            List of DocumentChunk objects.
        """
        chunks: list[DocumentChunk] = []
        step = self.config.chunk_size - self.config.overlap
        
        for start in range(0, len(text), step):
            end = min(start + self.config.chunk_size, len(text))
            chunk_text = text[start:end].strip()
            
            if chunk_text:  # Skip empty chunks
                chunks.append(
                    DocumentChunk(
                        chunk_index=0,  # Reassigned later
                        text=chunk_text,
                        page=page,
                        paragraph=paragraph,
                        source_section_id=source_section_id,
                        char_start=start,
                        char_end=end,
                    )
                )
        
        return chunks
