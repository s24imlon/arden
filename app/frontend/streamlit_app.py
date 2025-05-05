import streamlit as st
import requests
import os
from typing import Dict, List
from io import BytesIO
import time
from pathlib import Path
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - points to your backend service in Docker
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Set up the Streamlit page
st.set_page_config(
    page_title="Arden : AI-Powered Contract Watchdog",
    layout="wide",
    page_icon="🧠"
)

# Custom CSS for better visuals
st.markdown("""
<style>
    .stTextArea [data-baseweb=base-input] {
        background-color: #f8f9fa;
    }
    .reportview-container .main .block-container {
        padding-top: 2rem;
    }
    .stMarkdown p, .stText, .stAlert {
        color: #000000 !important;
    }
    textarea[disabled] {
        color: #000000 !important;
    }
    .st-ae {
        color: #000000 !important;
    }
    .st-b7 {
        color: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

def upload_file_to_backend(uploaded_file) -> Dict:
    """Upload file directly to backend without pre-processing"""
    try:
        # Prepare the file for upload
        files = {
            'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
        }

        logger.info(f"Uploading file: {uploaded_file.name} (type: {uploaded_file.type})")

        # Upload the file
        upload_response = requests.post(
            f"{BACKEND_URL}/upload-contract",
            files=files,
            timeout=60  # Increased timeout for large files
        )
        upload_response.raise_for_status()

        # Get document ID
        response_data = upload_response.json()
        doc_id = response_data.get("document_id")

        if not doc_id:
            logger.error("No document ID returned in response")
            return {"error": "No document ID returned"}

        logger.info(f"File uploaded successfully, document ID: {doc_id}")
        return response_data

    except requests.exceptions.RequestException as e:
        error_detail = e.response.json().get("detail", str(e)) if hasattr(e, 'response') else str(e)
        logger.error(f"Backend upload error: {error_detail}")
        return {"error": f"Backend error: {error_detail}"}
    except Exception as e:
        logger.error(f"Unexpected error during upload: {str(e)}")
        return {"error": str(e)}

def analyze_contract(doc_id: str) -> Dict:
    """Send document ID to backend for analysis"""
    try:
        logger.info(f"Analyzing document ID: {doc_id}")

        # Analyze the contract
        analysis_response = requests.post(
            f"{BACKEND_URL}/analyze-contract",
            params={"document_id": doc_id},
            timeout=60  # Increased timeout for analysis
        )
        analysis_response.raise_for_status()

        # Parse and validate response
        response_data = analysis_response.json()
        if not isinstance(response_data, dict):
            logger.error("Invalid response format from analysis endpoint")
            return {"error": "Invalid response format"}

        return response_data

    except requests.exceptions.RequestException as e:
        error_detail = e.response.json().get("detail", str(e)) if hasattr(e, 'response') else str(e)
        logger.error(f"Backend analysis error: {error_detail}")
        return {"error": f"Backend error: {error_detail}"}
    except Exception as e:
        logger.error(f"Unexpected error during analysis: {str(e)}")
        return {"error": str(e)}

def display_results(results: Dict) -> None:
    """Display analysis results with proper formatting"""
    if not results:
        st.warning("No results to display")
        return

    # Debug view (temporary)
    if st.checkbox("Show raw API response"):
        st.json(results)

    if not results.get("results"):
        st.warning("No analysis results found")
        return

    for result in results["results"]:
        with st.expander(f"🔍 Clause Analysis - Section: {result.get('section', 'N/A')}", expanded=True):
            col1, col2 = st.columns([1, 1])

            with col1:
                st.subheader("📜 Contract Clause")
                st.text_area(
                    label="Contract Text",
                    value=result.get('clause_text', 'No text available'),
                    height=200,
                    disabled=True,
                    label_visibility="collapsed"
                )

            with col2:
                analysis = result.get("analysis", {})

                # Handle cases where analysis might be a string
                if isinstance(analysis, str):
                    try:
                        analysis = json.loads(analysis)
                    except json.JSONDecodeError:
                        analysis = {"error": "Invalid analysis format"}

                # Status display
                status = analysis.get("compliance_status", "Unknown")
                if status.lower() == "compliant":
                    st.success(f"✅ Status: {status}")
                elif status.lower() == "non-compliant":
                    st.error(f"❌ Status: {status}")
                else:
                    st.warning(f"⚠️ Status: {status}")

                # Violations
                if analysis.get("violated_articles"):
                    st.subheader("🚨 Violated Regulations")
                    for violation in analysis["violated_articles"]:
                        if isinstance(violation, str):
                            st.markdown(f"- {violation}")

                # Required changes
                if analysis.get("required_changes"):
                    st.subheader("🔧 Required Changes")
                    for change in analysis["required_changes"]:
                        if isinstance(change, str):
                            st.markdown(f"- {change}")

def main():
    st.title("🧠 Arden : AI-Powered Contract Watchdog")
    st.markdown("Upload contracts to check regulatory compliance")

    uploaded_file = st.file_uploader(
        label="Upload Document",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=False,
        label_visibility="visible"
    )

    if uploaded_file:
        st.success(f"Uploaded: {uploaded_file.name}")

        # Display file info
        st.info(f"File type: {uploaded_file.type}, Size: {uploaded_file.size/1024:.2f} KB")

        if st.button("Analyze Document", key="analyze_file"):
            with st.spinner("Uploading and analyzing document..."):
                # Step 1: Upload the file
                upload_result = upload_file_to_backend(uploaded_file)

                if "error" in upload_result:
                    st.error(f"Upload failed: {upload_result['error']}")
                else:
                    doc_id = upload_result.get("document_id")
                    st.success(f"Document uploaded successfully (ID: {doc_id})")

                    # Step 2: Analyze the document
                    with st.spinner("Analyzing content..."):
                        analysis_results = analyze_contract(doc_id)
                        display_results(analysis_results)

if __name__ == "__main__":
    main()