"""
Lexical search layer for Hybrid Search.

This module performs keyword-based search over document chunks.
It uses a lightweight BM25 implementation and does not require
an external search engine such as Elasticsearch.
"""

from collections import defaultdict
from typing import Any, Dict, List
import math
import re


def normalize_text(text: str) -> str:
    """
    Normalize Persian and Arabic characters
    to make lexical matching more reliable.
    """

    # Arabic Yeh -> Persian Yeh
    text = text.replace("ي", "ی")

    # Arabic Kaf -> Persian Kaf
    text = text.replace("ك", "ک")

    # Arabic Alef Maksura -> Persian Yeh
    text = text.replace("ى", "ی")

    # Remove Persian half-space
    text = text.replace("\u200c", " ")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    # Case-insensitive search
    text = text.lower()

    return text.strip()


def tokenize(text: str) -> List[str]:
    """
    Convert text into searchable tokens.

    Persian words, English words, numbers and codes
    are preserved, minus Persian function-word stopwords (they carry no
    discriminative weight and pollute BM25's IDF). The same filter applies
    at index time and query time, so both sides stay symmetric.
    """

    text = normalize_text(text)

    tokens = re.findall(
        r"[\w\u0600-\u06FF]+",
        text,
        flags=re.UNICODE,
    )
    return [t for t in tokens if t not in PERSIAN_STOPWORDS]


# Persian/Arabic function words only - never content words. Kept literal and
# auditable on purpose (see docs/improvement-workflow.md §3).
PERSIAN_STOPWORDS = frozenset({
    "و", "در", "به", "از", "که", "این", "را", "با", "برای", "تا",
    "است", "هست", "بر", "آن", "های", "ها", "می", "هر", "یا", "هم",
    "یک", "شد", "شده", "خود", "کند", "کنید", "بود", "باشد", "نیز",
    "اما", "همه", "چه", "اگر", "بین", "روی", "درباره", "برای",
})


class LexicalIndex:
    """
    Lightweight in-memory BM25 index.

    The index is rebuilt from the chunks stored in ChromaDB.
    """

    def __init__(self, documents: List[Dict[str, Any]] | None = None,):
        # Store all indexed chunks
        self.documents: List[Dict[str, Any]] = []

        # Term frequencies for every chunk
        self.term_frequencies: List[Dict[str, int]] = []

        # Number of chunks containing each term
        self.document_frequencies: Dict[str, int] = (
            defaultdict(int)
        )

        # Average number of tokens per chunk
        self.average_document_length = 0.0

        if documents:
            self.build(documents)

    def build(self, documents: List[Dict[str, Any]],) -> None:
        """
        Build the lexical index from document chunks.
        """

        # Save the chunks
        self.documents = list(documents)

        # Reset old index data
        self.term_frequencies = []

        self.document_frequencies = defaultdict(int)

        total_length = 0

        # Process every chunk
        for document in self.documents:

            # Get chunk content
            content = document.get(
                "content",
                "",
            )

            # Convert content to tokens
            tokens = tokenize(content)

            # Add its length to the total
            total_length += len(tokens)

            # Count each token in this chunk
            term_frequency = defaultdict(int)

            for token in tokens:
                term_frequency[token] += 1

            # Save term frequencies
            self.term_frequencies.append(
                dict(term_frequency)
            )

            # Count how many chunks contain each token
            for token in term_frequency:
                self.document_frequencies[token] += 1

        # Calculate average chunk length
        if self.documents:
            self.average_document_length = (
                total_length / len(self.documents)
            )
        else:
            self.average_document_length = 0.0

    def search(
        self,
        query: str,
        top_k: int = 8,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """
        Search the index using BM25 scoring.
        """

        # Convert query into tokens
        query_tokens = tokenize(query)

        # Nothing to search
        if not query_tokens:
            return []

        # Number of chunks
        document_count = len(
            self.documents
        )

        if document_count == 0:
            return []

        # Precompute the BM25 IDF per unique query term once (it depends
        # only on the corpus, not on the chunk), then score each chunk that
        # actually contains at least one query term. Scanning the postings
        # instead of every chunk keeps this O(matching chunks x terms)
        # instead of O(chunks x terms).
        term_idf: Dict[str, float] = {}
        for term in set(query_tokens):
            document_frequency = self.document_frequencies.get(term, 0)
            if document_frequency == 0:
                continue
            term_idf[term] = math.log(
                1
                + (
                    document_count
                    - document_frequency
                    + 0.5
                )
                / (
                    document_frequency
                    + 0.5
                )
            )

        avg_dl = max(self.average_document_length, 1)
        matching = []
        for index, term_frequency in enumerate(self.term_frequencies):
            score = 0.0
            for term, idf in term_idf.items():
                frequency = term_frequency.get(term, 0)
                if frequency == 0:
                    continue
                score += (
                    idf
                    * frequency
                    * (k1 + 1)
                    / (
                        frequency
                        + k1
                        * (
                            1
                            - b
                            + b
                            * (sum(term_frequency.values()) or 1)
                            / avg_dl
                        )
                    )
                )
            if score > 0:
                matching.append((index, score))

        # Rank only the chunks with a positive score (same ranking as before,
        # computed without touching zero-score chunks).
        matching.sort(key=lambda pair: pair[1], reverse=True)
        results = []
        for index, score in matching[:top_k]:
            result = dict(self.documents[index])
            result["lexical_score"] = round(score, 4)
            results.append(result)
        return results
