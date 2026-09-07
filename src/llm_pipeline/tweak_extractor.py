"""
Step 1: Tweak Extraction & Parsing

This module extracts structured modifications from review text using LLM processing.
It converts natural language descriptions of recipe changes into structured
ModificationObject instances.
"""

import json
import os
from typing import Optional

from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

from .models import ModificationObject, Recipe, Review
from .prompts import build_simple_prompt


class TweakExtractor:
    """Extracts structured modifications from review text using LLM processing."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        """
        Initialize the TweakExtractor.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use for extraction
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        logger.info(f"Initialized TweakExtractor with model: {model}")

    def extract_modifications(
        self,
        review: Review,
        recipe: Recipe,
        max_retries: int = 2,
    ) -> List[ModificationObject]:
        """
        Extract ALL structured modifications from a review.

        Args:
            review: Review object containing modification text
            recipe: Original recipe being modified
            max_retries: Number of retry attempts if parsing fails

        Returns:
            List of ModificationObjects extracted from the review
        """
        if not review.has_modification:
            logger.warning("Review has no modification flag set")
            return []

        # Build the prompt - use simple prompt to avoid format string issues
        prompt = build_simple_prompt(
            review.text, recipe.title, recipe.ingredients, recipe.instructions
        )

        logger.debug(
            "Extracting modifications from review: {}...".format(review.text[:100])
        )

        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,  # Low temperature for consistent extractions
                    max_tokens=2000,  # Increased for multiple modifications
                )

                raw_output = response.choices[0].message.content
                logger.debug(f"LLM raw output: {raw_output}")

                # Check if we got a response
                if not raw_output:
                    logger.warning(f"Attempt {attempt + 1}: Empty response from LLM")
                    continue

                # Parse and validate the JSON response
                response_data = json.loads(raw_output)

                # Handle both array and single object responses for backward compatibility
                if isinstance(response_data, dict):
                    # Check if it's wrapped in a key
                    if "modifications" in response_data:
                        modifications_data = response_data["modifications"]
                    else:
                        # Single modification object - wrap in list
                        modifications_data = [response_data]
                elif isinstance(response_data, list):
                    modifications_data = response_data
                else:
                    logger.warning(f"Unexpected response format: {type(response_data)}")
                    continue

                # Validate each modification
                modifications = []
                for mod_data in modifications_data:
                    try:
                        modification = ModificationObject(**mod_data)
                        modifications.append(modification)
                    except ValidationError as e:
                        logger.warning(f"Skipping invalid modification: {e}")
                        continue

                logger.info(
                    f"Successfully extracted {len(modifications)} modifications "
                    f"with {sum(len(m.edits) for m in modifications)} total edits"
                )
                return modifications

            except json.JSONDecodeError as e:
                logger.warning(f"Attempt {attempt + 1}: Failed to parse JSON: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached. Raw output: {raw_output}")

            except ValidationError as e:
                logger.warning(f"Attempt {attempt + 1}: Validation error: {e}")
                if attempt == max_retries:
                    logger.error(
                        f"Max retries reached. Invalid data: {response_data}"
                    )

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error: {e}")
                if attempt == max_retries:
                    return []

        return []

    def extract_modification(
        self,
        review: Review,
        recipe: Recipe,
        max_retries: int = 2,
    ) -> Optional[ModificationObject]:
        """
        Extract modifications and return the first one (backward compatibility).

        Args:
            review: Review object containing modification text
            recipe: Original recipe being modified
            max_retries: Number of retry attempts if parsing fails

        Returns:
            First ModificationObject if extraction successful, None otherwise
        """
        modifications = self.extract_modifications(review, recipe, max_retries)
        return modifications[0] if modifications else None

    def select_best_reviews(
        self, reviews: list[Review], max_reviews: int = 5
    ) -> list[Review]:
        """
        Select the best quality reviews for processing.

        Prioritizes:
        1. Featured reviews (is_featured=True)
        2. High-rated reviews (4-5 stars)
        3. Sorted by rating descending

        Args:
            reviews: List of reviews to choose from
            max_reviews: Maximum number of reviews to return

        Returns:
            List of best quality reviews
        """
        # Filter to reviews with modifications
        modification_reviews = [r for r in reviews if r.has_modification]

        if not modification_reviews:
            logger.warning("No reviews with modifications found")
            return []

        # Priority 1: Featured reviews
        featured_reviews = [
            r for r in modification_reviews if getattr(r, "is_featured", False)
        ]

        if featured_reviews:
            logger.info(f"Found {len(featured_reviews)} featured reviews")
            # Sort featured reviews by rating (highest first)
            sorted_reviews = sorted(
                featured_reviews, key=lambda r: r.rating or 0, reverse=True
            )
            selected = sorted_reviews[:max_reviews]
            logger.info(
                f"Selected {len(selected)} featured reviews (ratings: "
                f"{[r.rating for r in selected]})"
            )
            return selected

        # Priority 2: High-rated reviews (4-5 stars)
        high_rated = [r for r in modification_reviews if (r.rating or 0) >= 4]

        if high_rated:
            logger.info(f"Found {len(high_rated)} high-rated reviews (no featured)")
            sorted_reviews = sorted(high_rated, key=lambda r: r.rating or 0, reverse=True)
            selected = sorted_reviews[:max_reviews]
            logger.info(
                f"Selected {len(selected)} high-rated reviews (ratings: "
                f"{[r.rating for r in selected]})"
            )
            return selected

        # Fallback: Sort all by rating
        logger.info("No featured or high-rated reviews, using top-rated")
        sorted_reviews = sorted(
            modification_reviews, key=lambda r: r.rating or 0, reverse=True
        )
        selected = sorted_reviews[:max_reviews]
        logger.info(
            f"Selected {len(selected)} reviews (ratings: {[r.rating for r in selected]})"
        )
        return selected

    def extract_single_modification(
        self, reviews: list[Review], recipe: Recipe
    ) -> tuple[ModificationObject, Review] | tuple[None, None]:
        """
        Extract modification from best quality review (backward compatibility).

        Args:
            reviews: List of reviews to choose from
            recipe: Original recipe being modified

        Returns:
            Tuple of (ModificationObject, source_Review) if successful, (None, None) otherwise
        """
        # Select best review (not random anymore!)
        best_reviews = self.select_best_reviews(reviews, max_reviews=1)

        if not best_reviews:
            logger.warning("No reviews with modifications found")
            return None, None

        selected_review = best_reviews[0]
        logger.info(
            f"Selected review (rating: {selected_review.rating}, "
            f"featured: {getattr(selected_review, 'is_featured', False)}): "
            f"{selected_review.text[:100]}..."
        )

        modification = self.extract_modification(selected_review, recipe)
        if modification:
            logger.info("Successfully extracted modification from selected review")
            return modification, selected_review
        else:
            logger.warning("Failed to extract modification from selected review")
            return None, None

    def extract_multiple_modifications(
        self, reviews: list[Review], recipe: Recipe, max_reviews: int = 5
    ) -> list[tuple[List[ModificationObject], Review]]:
        """
        Extract modifications from multiple best quality reviews.

        Args:
            reviews: List of reviews to choose from
            recipe: Original recipe being modified
            max_reviews: Maximum number of reviews to process

        Returns:
            List of (modifications_list, source_review) tuples
        """
        best_reviews = self.select_best_reviews(reviews, max_reviews=max_reviews)

        if not best_reviews:
            logger.warning("No reviews with modifications found")
            return []

        results = []
        for review in best_reviews:
            logger.info(f"Processing review (rating: {review.rating})...")
            modifications = self.extract_modifications(review, recipe)
            if modifications:
                results.append((modifications, review))
                logger.info(
                    f"Extracted {len(modifications)} modifications from this review"
                )
            else:
                logger.warning("Failed to extract modifications from this review")

        logger.info(
            f"Successfully processed {len(results)}/{len(best_reviews)} reviews, "
            f"extracted {sum(len(mods) for mods, _ in results)} total modifications"
        )
        return results

    def test_extraction(
        self, review_text: str, recipe_data: dict
    ) -> Optional[ModificationObject]:
        """
        Test extraction with raw text and recipe data.

        Args:
            review_text: Raw review text
            recipe_data: Raw recipe dictionary

        Returns:
            ModificationObject if successful
        """
        review = Review(text=review_text, has_modification=True)
        recipe = Recipe(
            recipe_id=recipe_data.get("recipe_id", "test"),
            title=recipe_data.get("title", "Test Recipe"),
            ingredients=recipe_data.get("ingredients", []),
            instructions=recipe_data.get("instructions", []),
        )

        return self.extract_modification(review, recipe)
