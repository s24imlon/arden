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

# Custom CSS with FIXED TEXT COLOR - forcing black text everywhere
st.markdown("""
<style>
    /* Force dark background on text areas */
    .stTextArea textarea {
        color: black !important;
        background-color: #e0e0e0 !important;
    }

    /* Force black text on all elements */
    p, h1, h2, h3, h4, h5, h6, span, div, textarea, .stTextArea, .stText, .stMarkdown {
        color: black !important;
    }

    /* Ensure text inside expanders is black */
    .streamlit-expanderHeader, .streamlit-expanderContent {
        color: black !important;
    }

    /* Higher contrast for disabled elements */
    textarea[disabled], textarea:disabled {
        color: black !important;
        background-color: #d0d0d0 !important;
        opacity: 1 !important;
    }

    /* Ensure all st elements have black text */
    [data-testid="stText"] *, [data-testid="stMarkdown"] *, [data-testid="stTextArea"] * {
        color: black !important;
    }

    /* Fix for specific Streamlit components */
    .stTextInput > div > div > input {
        color: black !important;
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

        logger.info(f"Raw analysis response: {json.dumps(response_data)}")
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

    # Debug view in a collapsible section
    with st.expander("Show raw API response", expanded=False):
        st.code(json.dumps(results, indent=2), language="json")

    if "error" in results:
        st.error(f"Analysis error: {results['error']}")
        return

    # Check if we have results to display
    if not results.get("results"):
        st.warning("No analysis results found in the response")
        return

    # Display each result
    for i, result in enumerate(results["results"]):
        with st.expander(f"🔍 Clause Analysis #{i+1}", expanded=True):
            # Force contrast for text
            st.markdown("""
            <style>
            .clause-text {
                color: black !important;
                background-color: #e0e0e0 !important;
                padding: 10px;
                border-radius: 5px;
            }
            </style>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns([1, 1])

            with col1:
                st.subheader("📜 Contract Clause")
                # Use a div with custom class and style for better visibility
                clause_text = result.get('clause_text', 'No text available')
                st.markdown(f'<div class="clause-text">{clause_text}</div>', unsafe_allow_html=True)

                # Add a backup text area with forced styling
                st.text_area(
                    label="Contract Text (Backup View)",
                    value=clause_text,
                    height=200,
                    key=f"clause_text_{i}"
                )

            with col2:
                # NEW: Handle the NESTED structure based on your raw response
                analysis_data = result.get("analysis", {})

                # If there's a nested "analysis" field, use that
                if isinstance(analysis_data, dict) and "analysis" in analysis_data:
                    actual_analysis = analysis_data["analysis"]
                else:
                    actual_analysis = analysis_data

                # Extract compliance status
                compliance_status = "Unknown"
                if isinstance(actual_analysis, dict):
                    compliance_status = actual_analysis.get("compliance_status", "Unknown")

                # Display status with appropriate color
                if compliance_status.lower() == "compliant":
                    st.success(f"✅ Status: {compliance_status}")
                elif compliance_status.lower() == "non-compliant":
                    st.error(f"❌ Status: {compliance_status}")
                else:
                    st.warning(f"⚠️ Status: {compliance_status}")

                # Extract matched regulations if present
                if isinstance(analysis_data, dict) and "matched_regulations" in analysis_data:
                    st.subheader("📋 Matched Regulations")
                    for regulation in analysis_data["matched_regulations"]:
                        st.markdown(f"- {regulation}")

                # Extract violations
                if isinstance(actual_analysis, dict) and "violated_articles" in actual_analysis:
                    st.subheader("🚨 Violated Regulations")
                    for violation in actual_analysis["violated_articles"]:
                        st.markdown(f"- {violation}")

                # Extract required changes
                if isinstance(actual_analysis, dict) and "required_changes" in actual_analysis:
                    st.subheader("🔧 Required Changes")
                    for change in actual_analysis["required_changes"]:
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

        analyze_button = st.button("Analyze Document", key="analyze_file", use_container_width=True)

        if analyze_button:
            # Create a placeholder for status updates
            status_placeholder = st.empty()
            results_container = st.container()

            # Step 1: Upload the file
            status_placeholder.info("Step 1/2: Uploading document...")
            upload_result = upload_file_to_backend(uploaded_file)

            if "error" in upload_result:
                status_placeholder.error(f"Upload failed: {upload_result['error']}")
            else:
                doc_id = upload_result.get("document_id")
                status_placeholder.success(f"✅ Document uploaded successfully (ID: {doc_id})")

                # Step 2: Analyze the document
                status_placeholder.info("Step 2/2: Analyzing content...")
                analysis_results = analyze_contract(doc_id)

                # Clear status and show results
                status_placeholder.empty()

                with results_container:
                    st.header("📊 Analysis Results")
                    if "error" in analysis_results:
                        st.error(f"Analysis failed: {analysis_results['error']}")
                    else:
                        st.success("Analysis completed successfully!")
                        display_results(analysis_results)

if __name__ == "__main__":
    main()