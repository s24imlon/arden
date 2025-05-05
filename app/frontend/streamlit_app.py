import streamlit as st
import requests
import os
from typing import Dict, List
from io import BytesIO
import time
from pathlib import Path

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
    .st-b7 {
        color: #000000;
    }
</style>
""", unsafe_allow_html=True)

def analyze_contract(text: str, is_file: bool = False) -> Dict:
    """Send contract content to backend for analysis"""
    try:
        if is_file:
            # For files, we already extracted the text
            upload_response = requests.post(
                f"{BACKEND_URL}/upload-contract",
                data={"text": text},  # Send as form data
                timeout=30
            )
        else:
            # For direct text input
            upload_response = requests.post(
                f"{BACKEND_URL}/upload-contract",
                data={"text": text},  # Send as form data
                timeout=30
            )

        upload_response.raise_for_status()
        doc_id = upload_response.json().get("document_id")

        # Analyze the contract
        analysis_response = requests.post(
            f"{BACKEND_URL}/analyze-contract",
            params={"document_id": doc_id},
            timeout=30
        )
        analysis_response.raise_for_status()
        return analysis_response.json()

    except requests.exceptions.RequestException as e:
        error_detail = e.response.json().get("detail", str(e)) if e.response else str(e)
        st.error(f"Backend error: {error_detail}")
        return {"error": error_detail}
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return {"error": str(e)}


def display_results(results: Dict) -> None:
    if not results.get("results"):
        st.warning("No analysis results found")
        return

    for result in results["results"]:
        with st.expander(f"🔍 Clause Analysis - Section: {result.get('section', 'N/A')}", expanded=True):
            col1, col2 = st.columns([1, 1])

            with col1:
                st.subheader("📜 Contract Clause")
                st.text_area("", result['clause_text'], height=200, disabled=True)

            with col2:
                analysis = result.get("analysis", {})

                # Handle cases where analysis might be malformed
                status = analysis.get("compliance_status", "Unknown")
                if isinstance(status, str):
                    if "compliant" in status.lower():
                        status = "Compliant" if "non" not in status.lower() else "Non-Compliant"

                if status == "Compliant":
                    st.success(f"✅ Status: {status}")
                elif status == "Non-Compliant":
                    st.error(f"❌ Status: {status}")
                else:
                    st.warning(f"⚠️ Status: {status}")

                if analysis.get("violated_articles"):
                    st.subheader("🚨 Violated Regulations")
                    for violation in analysis["violated_articles"]:
                        if isinstance(violation, str):
                            st.markdown(f"- {violation}")

                if analysis.get("required_changes"):
                    st.subheader("🔧 Required Changes")
                    for change in analysis["required_changes"]:
                        if isinstance(change, str):
                            st.markdown(f"- {change}")

def process_file_upload(uploaded_file) -> str:
    """Handle file uploads and save to temp location"""
    try:
        # Create temp directory if it doesn't exist
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)

        # Save the uploaded file temporarily
        file_path = temp_dir / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Process based on file type
        if uploaded_file.type == "text/plain":
            with open(file_path) as f:
                return f.read()
        elif uploaded_file.type == "application/pdf":
            from pdfminer.high_level import extract_text
            return extract_text(file_path)
        elif uploaded_file.type.endswith("wordprocessingml.document"):
            from docx import Document
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        else:
            st.error("Unsupported file type")
            return ""
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return ""
    finally:
        # Clean up temp file
        if 'file_path' in locals():
            try:
                file_path.unlink()
            except:
                pass

def main():
    st.title("🧠 Arden : AI-Powered Contract Watchdog")
    st.markdown("Upload contracts or paste text to check regulatory compliance")

    tab1, tab2 = st.tabs(["📋 Paste Text", "📤 Upload Document"])

    with tab1:
        contract_text = st.text_area(
            "Paste your contract clause here:",
            height=300,
            placeholder="Example:\n'The company may collect user data indefinitely without notification...'"
        )

        if st.button("Analyze Compliance", key="analyze_text"):
            if contract_text.strip():
                with st.spinner("Analyzing compliance..."):
                    results = analyze_contract(contract_text)
                    display_results(results)
            else:
                st.warning("Please enter contract text")

    with tab2:
        uploaded_file = st.file_uploader(
            "Choose a file (TXT, DOCX, or PDF)",
            type=["txt", "docx", "pdf"],
            accept_multiple_files=False
        )

        if uploaded_file:
            st.success(f"Uploaded: {uploaded_file.name}")
            extracted_text = process_file_upload(uploaded_file)

            if extracted_text:
                with st.expander("View Extracted Text"):
                    st.text_area("", extracted_text, height=200, key="extracted_text")

                if st.button("Analyze Uploaded Document", key="analyze_file"):
                    with st.spinner("Analyzing document..."):
                        results = analyze_contract(extracted_text, is_file=True)
                        display_results(results)


if __name__ == "__main__":
    main()