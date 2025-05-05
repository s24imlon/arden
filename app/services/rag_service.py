import weaviate
from typing import List, Dict
from sentence_transformers import SentenceTransformer
import logging
from tenacity import retry, stop_after_attempt, wait_fixed
import os
from dotenv import load_dotenv
import requests
import time
import json
import re

logger = logging.getLogger(__name__)
load_dotenv()

class RAGService:
    def __init__(self):
        weaviate_url = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
        # 1. Initialize Weaviate client
        self.client = weaviate.Client(
            url=weaviate_url,
            additional_headers={"X-OpenAI-Api-Key": None}
        )

        # 2. Initialize embedding model
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # 3. Initialize LLM
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            logger.error("Missing GROQ_API_KEY in environment variables")

        self.groq_endpoint = "https://api.groq.com/openai/v1/chat/completions"
        self.llm_model = "llama3-70b-8192"
        self.llm_timeout = 30

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        return self.embedder.encode(text).tolist()

    @retry(stop=stop_after_attempt(3))
    def query_regulations(self, query: str, top_k: int = 3) -> List[Dict]:
        """Search relevant regulations in Weaviate"""
        try:
            # Generate embedding for the query
            query_vector = self._generate_embedding(query)

            # Search Weaviate
            result = self.client.query\
                .get("ComplianceClause", ["text", "doc_type", "section"])\
                .with_near_vector({
                    "vector": query_vector,
                    "certainty": 0.65
                })\
                .with_limit(top_k)\
                .with_autocut(1)\
                .do()

            return result["data"]["Get"]["ComplianceClause"]
        except Exception as e:
            logger.error(f"Weaviate query failed: {str(e)}")
            raise

    def analyze_compliance(self, contract_text: str) -> Dict:
        try:
            regulations = self.query_regulations(contract_text)
            regulations = regulations or []
            if not regulations:
                return {"error": "No regulations matched", "suggestion": "Try broadening your query"}

            prompt = self._build_analysis_prompt(contract_text, regulations)
            if len(prompt) > 4000:  # Prevent token overflow
                prompt = prompt[:3900] + "\n[TRUNCATED]"

            analysis = self._query_llm(prompt)
            logging.debug(f'This is logging analysis {analysis}')
            analysis = self._query_llm(prompt) or {}

            if "error" in analysis:
                return {
                    "contract_text": contract_text[:500] + ("..." if len(contract_text)>500 else ""),
                    "error": analysis["error"],
                    "matched_regulations": [reg["text"][:200] + "..." for reg in regulations]
                }

            return {
                "contract_text": contract_text,
                "matched_regulations": [reg.get("text", "") for reg in regulations],
                "analysis": analysis if isinstance(analysis, dict) else {"error": "Invalid analysis format"}
            }
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}")
            return {"error": "System error during analysis"}

    def _build_analysis_prompt(self, clause: str, regulations: List[Dict]) -> str:
        """Construct structured prompt for LLM"""
        reg_text = "\n\n".join([
            f"REGULATION {i+1} ({reg.get('doc_type', '')}):\n{reg['text']}"
            for i, reg in enumerate(regulations)
        ])
        return f"""Analyze this contract clause against regulations. Return ONLY JSON with:
        {{
            "compliance_status": ("Compliant"|"Non-Compliant"|"Partially-Compliant"),
            "violated_articles": ["exact phrases from regulations being violated"],
            "required_changes": ["specific wording modifications needed"]
        }}

        Contract Clause:
        {clause}

        Relevant Regulations:
        {reg_text}

        ONLY OUTPUT THE JSON OBJECT, NO OTHER TEXT:"""

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(15))
    def _query_llm(self, prompt: str) -> Dict:
        """Query Groq's API with proper error handling"""
        if not self.groq_api_key:
            logger.error("Missing GROQ_API_KEY")
            return {"error": "Missing API credentials"}

        try:
            logger.info(f"Sending prompt to Groq API (model: {self.llm_model})")
            logger.debug(f"Full prompt:\n{prompt[:1000]}...")  # Log first 1000 chars of prompt
            # Make the API request
            response = requests.post(
                self.groq_endpoint,
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a compliance analyst that ONLY returns valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"}
                },
                timeout=60
            )

            logger.info(f"Groq API response status: {response.status_code}")
            logger.debug(f"Full response: {response.text}")
            # Check response status
            response.raise_for_status()

            # Parse the response data
            response_data = response.json()

            # Validate response structure
            if not response_data.get("choices"):
                logger.error(f"Invalid Groq response format: {response_data}")
                return {"error": "Invalid API response format"}

            if len(response_data["choices"]) == 0:
                logger.error("Empty choices array in response")
                return {"error": "No completion generated"}

            message_content = response_data["choices"][0]["message"]["content"]
            logger.info("Received LLM response")
            logger.debug(f"Raw LLM response:\n{message_content}")

            return self._parse_llm_response(message_content)

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"API request failed: {str(e)}"}
        except KeyError as e:
            logger.error(f"Missing key in response: {str(e)}")
            return {"error": f"Malformed API response: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}"}

    def _parse_llm_response(self, text: str) -> Dict:
        """Handle incomplete JSON responses more gracefully"""
        try:
            text = text.strip()
            logging.info(f'text is {text}')
            # Try to complete obviously incomplete JSON
            # if '"violated_articles": [' in text and not text.endswith(']'):
            #     text += ']'
            # if text.count('{') > text.count('}'):
            #     text += '}' * (text.count('{') - text.count('}'))

            if text.count('[') != text.count(']'):
                logger.warning("Unbalanced arrays in response, attempting fix")
                text = text.replace('",\n]', '"\n]')  # Fix trailing commas

            if text.count('{') != text.count('}'):
                logger.warning("Unbalanced objects in response, attempting fix")
                text = text + '}' * (text.count('{') - text.count('}'))

            # Standard cleaning
            text = text.replace('```json', '').replace('```', '')

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # If still invalid, try wrapping in a valid structure
                return {
                    "compliance_status": "Non-Compliant" if "Non-Compliant" in text else "Unknown",
                    "violated_articles": self._extract_violations(text),
                    "required_changes": ["Please review manually - automated analysis incomplete"]
                }

        except Exception as e:
            logger.error(f"Parse failed: {str(e)}")
            return self._generate_fallback_response(text)

    def _extract_violations(self, text: str) -> List[str]:
        """Extract violation phrases from incomplete JSON"""
        violations = []
        # Look for lines that appear to be violation items
        for line in text.split('\n'):
            if '"' in line and ('must' in line.lower() or 'required' in line.lower()):
                violations.append(line.strip(' ,"'))
        return violations if violations else ["Unable to determine violations"]

    def _validate_result_structure(self, result: Dict) -> Dict:
        """Ensure required fields exist"""
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")

        # Set defaults for missing fields
        result.setdefault("compliance_status", "Unknown")
        result.setdefault("violated_articles", [])
        result.setdefault("required_changes", [])

        return result