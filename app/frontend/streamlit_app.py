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

# Custom CSS with CONTROLLED BACKGROUNDS for text visibility
st.markdown("""
<style>
    /* === GLOBAL STYLES === */
    /* Force light background for the entire app */
    .main, .block-container, .stApp {
        background-color: #f0f0f0 !important;
    }

    /* === TEXT COLOR FIXES === */
    /* Force black text everywhere */
    p, h1, h2, h3, h4, h5, h6, span, div, label, a, li {
        color: black !important;
    }

    /* === TEXT AREAS AND INPUTS === */
    /* Fix text areas */
    .stTextArea textarea {
        color: black !important;
        background-color: #e0e0e0 !important;
    }

    /* Fix inputs */
    .stTextInput > div > div > input {
        color: black !important;
        background-color: #e0e0e0 !important;
    }

    /* === MARKDOWN AND TEXT ELEMENTS === */
    /* Ensure markdown has black text */
    .stMarkdown {
        color: black !important;
        background-color: #f0f0f0 !important;
    }

    /* Force code elements to have dark text */
    code {
        color: #1e1e1e !important;
    }

    /* === EXPANDERS AND CONTAINERS === */
    /* Force expander background */
    .streamlit-expanderHeader, .streamlit-expanderContent {
        background-color: #f0f0f0 !important;
        color: black !important;
    }

    /* === CUSTOM TEXT DISPLAY === */
    /* Our custom clause text display */
    .clause-text {
        color: black !important;
        background-color: #e0e0e0 !important;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
        font-family: monospace;
        white-space: pre-wrap;
    }

    /* Contract analysis section */
    .analysis-section {
        background-color: #f5f5f5 !important;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #4CAF50;
        margin: 10px 0;
    }

    /* Style for violations */
    .violation-item {
        background-color: #fff0f0 !important;
        padding: 8px;
        margin: 5px 0;
        border-left: 3px solid #f44336;
        border-radius: 3px;
    }

    /* Style for required changes */
    .change-item {
        background-color: #e8f4fd !important;
        padding: 8px;
        margin: 5px 0;
        border-left: 3px solid #2196F3;
        border-radius: 3px;
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
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown('<h3 style="color: black; background-color: #f0f0f0;">📜 Contract Clause</h3>', unsafe_allow_html=True)

                # Display clause text with guaranteed visibility
                clause_text = result.get('clause_text', 'No text available')

                # Method 1: Markdown with custom class
                st.markdown(f'<div class="clause-text">{clause_text}</div>', unsafe_allow_html=True)

                # Method 2: Code block (always visible)
                st.code(clause_text, language=None)

            with col2:
                st.markdown('<h3 style="color: black; background-color: #f0f0f0;">📊 Analysis Results</h3>', unsafe_allow_html=True)

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
                    st.markdown('<div style="background-color: #dff0d8; color: black; padding: 10px; border-radius: 5px; border-left: 4px solid #5cb85c;">✅ <b>Status:</b> Compliant</div>', unsafe_allow_html=True)
                elif compliance_status.lower() == "non-compliant":
                    st.markdown('<div style="background-color: #f2dede; color: black; padding: 10px; border-radius: 5px; border-left: 4px solid #d9534f;">❌ <b>Status:</b> Non-Compliant</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="background-color: #fcf8e3; color: black; padding: 10px; border-radius: 5px; border-left: 4px solid #f0ad4e;">⚠️ <b>Status:</b> Unknown</div>', unsafe_allow_html=True)

                # Extract matched regulations if present
                if isinstance(analysis_data, dict) and "matched_regulations" in analysis_data:
                    st.markdown('<h4 style="color: black; background-color: #f0f0f0; margin-top: 20px;">📋 Matched Regulations</h4>', unsafe_allow_html=True)
                    for regulation in analysis_data["matched_regulations"]:
                        st.markdown(f'<div style="background-color: #f5f5f5; color: black; padding: 8px; margin: 5px 0; border-radius: 3px;">• {regulation}</div>', unsafe_allow_html=True)

                # Extract violations
                if isinstance(actual_analysis, dict) and "violated_articles" in actual_analysis:
                    st.markdown('<h4 style="color: black; background-color: #f0f0f0; margin-top: 20px;">🚨 Violated Regulations</h4>', unsafe_allow_html=True)
                    for violation in actual_analysis["violated_articles"]:
                        st.markdown(f'<div class="violation-item">• {violation}</div>', unsafe_allow_html=True)

                # Extract required changes
                if isinstance(actual_analysis, dict) and "required_changes" in actual_analysis:
                    st.markdown('<h4 style="color: black; background-color: #f0f0f0; margin-top: 20px;">🔧 Required Changes</h4>', unsafe_allow_html=True)
                    for change in actual_analysis["required_changes"]:
                        st.markdown(f'<div class="change-item">• {change}</div>', unsafe_allow_html=True)

def main():
    st.markdown('<h1 style="color: black; background-color: #f0f0f0;">🧠 Arden : AI-Powered Contract Watchdog</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: black; background-color: #f0f0f0;">Upload contracts to check regulatory compliance</p>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        label="Upload Document",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=False,
        label_visibility="visible"
    )

    if uploaded_file:
        st.markdown(f'<div style="background-color: #d4edda; color: black; padding: 10px; border-radius: 5px; margin: 10px 0;">✅ Uploaded: {uploaded_file.name}</div>', unsafe_allow_html=True)

        # Display file info
        st.markdown(f'<div style="background-color: #d1ecf1; color: black; padding: 10px; border-radius: 5px; margin: 10px 0;">ℹ️ File type: {uploaded_file.type}, Size: {uploaded_file.size/1024:.2f} KB</div>', unsafe_allow_html=True)

        analyze_button = st.button("Analyze Document", key="analyze_file", use_container_width=True)

        if analyze_button:
            # Create a placeholder for status updates
            status_placeholder = st.empty()
            results_container = st.container()

            # Step 1: Upload the file
            status_placeholder.markdown('<div style="background-color: #d1ecf1; color: black; padding: 10px; border-radius: 5px;">Step 1/2: Uploading document...</div>', unsafe_allow_html=True)
            upload_result = upload_file_to_backend(uploaded_file)

            if "error" in upload_result:
                status_placeholder.markdown(f'<div style="background-color: #f8d7da; color: black; padding: 10px; border-radius: 5px;">❌ Upload failed: {upload_result["error"]}</div>', unsafe_allow_html=True)
            else:
                doc_id = upload_result.get("document_id")
                status_placeholder.markdown(f'<div style="background-color: #d4edda; color: black; padding: 10px; border-radius: 5px;">✅ Document uploaded successfully (ID: {doc_id})</div>', unsafe_allow_html=True)

                # Step 2: Analyze the document
                status_placeholder.markdown('<div style="background-color: #d1ecf1; color: black; padding: 10px; border-radius: 5px;">Step 2/2: Analyzing content...</div>', unsafe_allow_html=True)
                analysis_results = analyze_contract(doc_id)

                # Clear status and show results
                status_placeholder.empty()

                with results_container:
                    st.markdown('<h2 style="color: black; background-color: #f0f0f0;">🧠 Analysis Results</h2>', unsafe_allow_html=True)
                    if "error" in analysis_results:
                        st.markdown(f'<div style="background-color: #f8d7da; color: black; padding: 10px; border-radius: 5px;">❌ Analysis failed: {analysis_results["error"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="background-color: #d4edda; color: black; padding: 10px; border-radius: 5px; margin-bottom: 20px;">✅ Analysis completed successfully!</div>', unsafe_allow_html=True)
                        display_results(analysis_results)

if __name__ == "__main__":
    main()