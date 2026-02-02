"""
Layer 4.5: Deep RAG External Search Processor
Hierarchical Orchestrated Thorough Document Oversight & Guidance - External Intelligence

Uses TAVILY AI Search to find similar projects by the same municipality, agency, or
engineering firm. Provides external context with appropriate disclaimers.

CRITICAL FEATURES:
- External search using TAVILY AI
- Searches for similar projects by owner/agency
- Searches for engineering firm track record
- All results include disclaimers about external sourcing
- Integrates with existing answer format
- Respects API rate limits

ENVIRONMENT VARIABLE:
- TAVILY_API_KEY: Your TAVILY API key for external search
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class DeepRAGProcessor:
    """
    Deep RAG processor for external search using TAVILY AI.

    Searches for similar projects and contextual information beyond the document,
    providing additional intelligence with appropriate disclaimers.

    Design Principles:
    - External sources clearly marked with disclaimers
    - Non-blocking - failures don't break analysis
    - Rate-limited to prevent API abuse
    - Results merged with internal answers
    """

    # Disclaimer to append to all RAG-sourced answers
    RAG_DISCLAIMER = (
        "[External Source] This information was found via external search and may not be "
        "directly applicable to this specific project. Verify with project documentation."
    )

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        max_results_per_query: int = 5,
        search_depth: str = "advanced"  # "basic" or "advanced"
    ):
        """
        Initialize the Deep RAG processor.

        Args:
            tavily_api_key: TAVILY API key (defaults to TAVILY_API_KEY env var)
            max_results_per_query: Maximum results per search query
            search_depth: Search depth ("basic" or "advanced")
        """
        self.api_key = tavily_api_key or os.environ.get('TAVILY_API_KEY')
        self.max_results = max_results_per_query
        self.search_depth = search_depth

        # Track usage
        self.total_searches = 0
        self.total_results_found = 0
        self.search_errors = 0

        if not self.api_key:
            logger.warning("TAVILY_API_KEY not found - Deep RAG will be disabled")
        else:
            logger.info("Deep RAG Processor initialized with TAVILY")
            logger.info(f"   Max results per query: {max_results_per_query}")
            logger.info(f"   Search depth: {search_depth}")

    @property
    def is_available(self) -> bool:
        """Check if TAVILY API is available."""
        return bool(self.api_key)

    async def search_similar_projects(
        self,
        owner: Optional[str] = None,
        engineer: Optional[str] = None,
        project_type: Optional[str] = None,
        location: Optional[str] = None,
        unanswered_questions: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Search for similar projects and contextual information.

        Args:
            owner: Owner/Agency name (e.g., "City of Springfield")
            engineer: Engineering firm name
            project_type: Type of project (e.g., "CIPP lining", "sewer rehabilitation")
            location: Geographic location
            unanswered_questions: List of questions to try to answer externally

        Returns:
            Dict with search results and any answered questions
        """
        if not self.is_available:
            return {
                'success': False,
                'error': 'TAVILY API not configured',
                'results': [],
                'answers': {}
            }

        results = {
            'success': True,
            'search_queries': [],
            'results': [],
            'answers': {},
            'disclaimers': [self.RAG_DISCLAIMER]
        }

        try:
            # Build search queries based on available context
            queries = self._build_search_queries(
                owner=owner,
                engineer=engineer,
                project_type=project_type,
                location=location
            )

            # Execute searches
            for query in queries:
                logger.info(f"Deep RAG search: {query}")
                search_results = await self._execute_tavily_search(query)

                if search_results:
                    results['search_queries'].append(query)
                    results['results'].extend(search_results)
                    self.total_results_found += len(search_results)

            # Try to answer specific questions from RAG results
            if unanswered_questions and results['results']:
                results['answers'] = await self._extract_answers_from_results(
                    unanswered_questions,
                    results['results']
                )

            logger.info(f"Deep RAG complete: {len(results['results'])} results from {len(queries)} queries")

        except Exception as e:
            logger.error(f"Deep RAG search failed: {e}")
            self.search_errors += 1
            results['success'] = False
            results['error'] = str(e)

        return results

    def _build_search_queries(
        self,
        owner: Optional[str] = None,
        engineer: Optional[str] = None,
        project_type: Optional[str] = None,
        location: Optional[str] = None
    ) -> List[str]:
        """Build search queries from available project context."""
        queries = []

        # Search by owner/agency
        if owner:
            clean_owner = self._clean_search_term(owner)
            if project_type:
                queries.append(f'"{clean_owner}" {project_type} project bid specifications')
            else:
                queries.append(f'"{clean_owner}" infrastructure project bid')

        # Search by engineering firm
        if engineer:
            clean_engineer = self._clean_search_term(engineer)
            if project_type:
                queries.append(f'"{clean_engineer}" {project_type} engineering specifications')
            else:
                queries.append(f'"{clean_engineer}" municipal infrastructure engineering')

        # Search by location + project type
        if location and project_type:
            clean_location = self._clean_search_term(location)
            queries.append(f'{project_type} project {clean_location} specifications requirements')

        # Fallback: search by project type
        if not queries and project_type:
            queries.append(f'{project_type} municipal bid requirements specifications')

        return queries[:3]  # Limit to 3 queries per RAG session

    def _clean_search_term(self, term: str) -> str:
        """Clean a term for use in search query."""
        # Remove special characters but keep spaces
        cleaned = re.sub(r'[^\w\s-]', '', term)
        # Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    async def _execute_tavily_search(self, query: str) -> List[Dict]:
        """Execute a single TAVILY search query."""
        try:
            import httpx

            self.total_searches += 1

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "search_depth": self.search_depth,
                        "max_results": self.max_results,
                        "include_answer": True,
                        "include_raw_content": False
                    }
                )

                if response.status_code != 200:
                    logger.error(f"TAVILY API error: {response.status_code} - {response.text}")
                    self.search_errors += 1
                    return []

                data = response.json()

                # Extract results
                results = []
                for item in data.get('results', []):
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'content': item.get('content', ''),
                        'score': item.get('score', 0),
                        'query': query
                    })

                # Include AI-generated answer if available
                if data.get('answer'):
                    results.append({
                        'title': 'AI Summary',
                        'url': 'tavily-ai-summary',
                        'content': data['answer'],
                        'score': 1.0,
                        'query': query,
                        'is_ai_summary': True
                    })

                return results

        except ImportError:
            logger.error("httpx not installed - required for TAVILY API")
            return []
        except Exception as e:
            logger.error(f"TAVILY search error: {e}")
            self.search_errors += 1
            return []

    async def _extract_answers_from_results(
        self,
        questions: List[Dict],
        results: List[Dict]
    ) -> Dict[str, Any]:
        """
        Try to extract answers to specific questions from RAG results.

        Returns a dict mapping question_id to potential answers with disclaimers.
        """
        answers = {}

        # Combine all result content
        combined_content = "\n\n".join([
            f"Source: {r['title']}\n{r['content']}"
            for r in results if r.get('content')
        ])

        if not combined_content:
            return answers

        # For each question, check if the combined content might answer it
        for question in questions:
            question_id = question.get('id') or question.get('question_id')
            question_text = question.get('text') or question.get('question_text', '')

            if not question_id or not question_text:
                continue

            # Simple keyword matching to find potentially relevant content
            keywords = self._extract_keywords(question_text)

            relevant_snippets = []
            for result in results:
                content = result.get('content', '').lower()
                if any(kw.lower() in content for kw in keywords):
                    relevant_snippets.append({
                        'content': result.get('content', ''),
                        'source': result.get('title', 'External Source'),
                        'url': result.get('url', '')
                    })

            if relevant_snippets:
                # Take best snippet and format as answer
                best_snippet = relevant_snippets[0]
                answer_text = (
                    f"{best_snippet['content'][:500]}... "
                    f"\n\n{self.RAG_DISCLAIMER}\n"
                    f"Source: {best_snippet['source']} ({best_snippet['url']})"
                )

                answers[question_id] = {
                    'text': answer_text,
                    'confidence': 0.3,  # Low confidence for external sources
                    'source': 'Deep RAG',
                    'is_external': True,
                    'disclaimer': self.RAG_DISCLAIMER
                }

        return answers

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from question text."""
        # Remove common words and extract key terms
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'which',
            'who', 'whom', 'this', 'that', 'these', 'those', 'for', 'with',
            'about', 'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'from', 'and', 'or', 'but', 'not', 'how', 'when', 'where',
            'why', 'does', 'do', 'did', 'have', 'has', 'had', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'any',
            'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
            'some', 'such', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'required', 'requirements', 'specify', 'specified', 'project'
        }

        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Return up to 5 keywords
        return keywords[:5]

    def get_statistics(self) -> str:
        """Get formatted statistics for Deep RAG processing."""
        stats = f"""
Deep RAG Statistics:
  API Available: {self.is_available}
  Total Searches: {self.total_searches}
  Total Results Found: {self.total_results_found}
  Search Errors: {self.search_errors}
"""
        return stats


# Environment variable for Render deployment
# Add to your Render environment variables:
# TAVILY_API_KEY=your_tavily_api_key_here
